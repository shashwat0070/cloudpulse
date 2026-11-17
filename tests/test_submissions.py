import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.submissions import MAX_DOCUMENT_BYTES, build_router


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(build_router(tmp_path))

    with TestClient(app) as test_client:
        yield test_client


def submit(client, content=b"%PDF-1.4\nsynthetic test input"):
    return client.post(
        "/jobs",
        content=content,
        headers={
            "Content-Type": "application/pdf",
            "Idempotency-Key": "invoice-001",
        },
    )


def test_submit_and_retrieve_job(client, tmp_path):
    response = submit(client)

    assert response.status_code == 202
    job = response.json()

    status = client.get(job["status_url"])
    assert status.status_code == 200
    assert status.json()["status"] == "ACCEPTED"

    inputs = list((tmp_path / "inputs").glob("*.pdf"))
    assert len(inputs) == 1
    assert inputs[0].read_bytes() == b"%PDF-1.4\nsynthetic test input"


def test_duplicate_submission_returns_same_job(client):
    first = submit(client)
    second = submit(client)

    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_conflicting_submission_returns_409(client):
    assert submit(client).status_code == 202
    assert submit(client, b"different document").status_code == 409


@pytest.mark.parametrize(
    "content,expected_status",
    [
        (b"", 400),
        (b"x" * (MAX_DOCUMENT_BYTES + 1), 413),
    ],
)
def test_invalid_upload_sizes(client, content, expected_status):
    assert submit(client, content).status_code == expected_status


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/not-a-real-job").status_code == 404