import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.job_store import IdempotencyConflict, JobStore


def submit(store, content_hash="hash-a"):
    return store.accept(
        key="invoice-001",
        content_hash=content_hash,
        input_ref="inputs/example.pdf",
    )


def test_acceptance_persists_job_and_outbox(tmp_path):
    database = tmp_path / "jobs.db"
    job = submit(JobStore(database))

    reopened = JobStore(database)
    with reopened.connection() as conn:
        saved = conn.execute("SELECT * FROM jobs").fetchone()
        pending = conn.execute("SELECT * FROM outbox").fetchone()

    assert saved["job_id"] == job["job_id"]
    assert saved["status"] == "ACCEPTED"
    assert pending["job_id"] == job["job_id"]
    assert pending["status"] == "PENDING"


def test_concurrent_duplicates_create_one_job(tmp_path):
    store = JobStore(tmp_path / "jobs.db")

    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: submit(store), range(8)))

    assert len({job["job_id"] for job in jobs}) == 1

    with store.connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM outbox"
        ).fetchone()[0] == 1


def test_same_key_with_different_content_is_rejected(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    submit(store)

    with pytest.raises(IdempotencyConflict):
        submit(store, content_hash="different-content")


def test_outbox_failure_rolls_back_job(tmp_path):
    store = JobStore(tmp_path / "jobs.db")

    with store.connection() as conn:
        conn.executescript("""
            CREATE TRIGGER fail_outbox
            BEFORE INSERT ON outbox
            BEGIN
                SELECT RAISE(ABORT, 'injected outbox failure');
            END;
        """)

    with pytest.raises(sqlite3.IntegrityError):
        submit(store)

    with store.connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM outbox"
        ).fetchone()[0] == 0