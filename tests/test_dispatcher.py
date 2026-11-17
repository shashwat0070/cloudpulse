import sqlite3

import pytest

from app.dispatcher import dispatch_pending
from app.job_store import JobStore


@pytest.fixture
def store(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.accept(
        key="invoice-001",
        content_hash="example-hash",
        input_ref="inputs/example.pdf",
    )
    return store


def outbox_status(store):
    with store.connection() as conn:
        return conn.execute(
            "SELECT status FROM outbox"
        ).fetchone()[0]


def test_success_marks_sent_and_skips_next_dispatch(store):
    messages = []

    assert dispatch_pending(store, messages.append) == {
        "sent": 1,
        "failed": 0,
    }
    assert outbox_status(store) == "SENT"

    assert dispatch_pending(store, messages.append)["sent"] == 0
    assert len(messages) == 1


def test_queue_failure_keeps_job_pending(store):
    def unavailable_queue(message):
        raise ConnectionError("Injected queue outage")

    assert dispatch_pending(store, unavailable_queue) == {
        "sent": 0,
        "failed": 1,
    }
    assert outbox_status(store) == "PENDING"


def test_lost_acknowledgment_can_produce_duplicate(store):
    messages = []

    def lose_acknowledgment(message):
        messages.append(message)
        raise TimeoutError("Injected lost acknowledgment")

    dispatch_pending(store, lose_acknowledgment)
    assert outbox_status(store) == "PENDING"

    dispatch_pending(store, messages.append)

    assert outbox_status(store) == "SENT"
    assert len(messages) == 2
    assert messages[0] == messages[1]


def test_failed_dispatch_record_is_retried(store):
    messages = []

    with store.connection() as conn:
        conn.executescript("""
            CREATE TRIGGER fail_dispatch_update
            BEFORE UPDATE ON outbox
            BEGIN
                SELECT RAISE(ABORT, 'injected database failure');
            END;
        """)

    with pytest.raises(sqlite3.IntegrityError):
        dispatch_pending(store, messages.append)

    assert outbox_status(store) == "PENDING"

    with store.connection() as conn:
        conn.execute("DROP TRIGGER fail_dispatch_update")

    dispatch_pending(store, messages.append)

    assert outbox_status(store) == "SENT"
    assert len(messages) == 2
    assert messages[0] == messages[1]