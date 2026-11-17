import hashlib
import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.job_store import IdempotencyConflict, JobStore

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


def build_router(data_dir: Path):
    data_dir = data_dir.resolve()
    inputs = data_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    store = JobStore(data_dir / "jobs.sqlite3")
    router = APIRouter(tags=["Jobs"])

    def persist_and_accept(content: bytes, key: str):
        digest = hashlib.sha256(content).hexdigest()
        destination = inputs / f"{digest}.pdf"

        # Write completely before making the input available.
        descriptor, temporary_name = tempfile.mkstemp(dir=inputs)
        temporary_path = Path(temporary_name)

        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())

            os.replace(temporary_path, destination)

            directory_fd = os.open(inputs, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary_path.unlink(missing_ok=True)

        return store.accept(
            key=key,
            content_hash=digest,
            input_ref=f"inputs/{digest}.pdf",
        )

    @router.post("/jobs", status_code=202)
    async def submit_document(
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=200,
            ),
        ],
    ):
        if not idempotency_key.strip():
            raise HTTPException(400, "Idempotency key cannot be blank")

        media_type = request.headers.get(
            "content-type", ""
        ).split(";")[0].strip().lower()

        if media_type != "application/pdf":
            raise HTTPException(415, "Use Content-Type: application/pdf")

        content = bytearray()

        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise HTTPException(413, "Maximum document size is 5 MiB")
            content.extend(chunk)

        if not content:
            raise HTTPException(400, "Document cannot be empty")

        try:
            job = await run_in_threadpool(
                persist_and_accept,
                bytes(content),
                idempotency_key,
            )
        except IdempotencyConflict as error:
            raise HTTPException(409, str(error)) from error

        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "status_url": f"/jobs/{job['job_id']}",
        }

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str):
        with store.connection() as conn:
            job = conn.execute(
                "SELECT job_id, status FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

        if job is None:
            raise HTTPException(404, "Job not found")

        return dict(job)

    return router