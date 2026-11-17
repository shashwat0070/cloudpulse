import json
import logging
from datetime import datetime, timezone

from app.job_store import JobStore

logger = logging.getLogger("cloudpulse.dispatcher")


def log_event(event, job_id, **details):
    logger.info(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "job_id": job_id,
                **details,
            }
        )
    )


def dispatch_pending(store: JobStore, send, batch_size=10):
    """
    send(message) must return after queue acknowledgment.
    If acknowledgment is uncertain, it must raise an exception.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    with store.connection() as conn:
        pending = conn.execute(
            """
            SELECT jobs.job_id, jobs.input_ref, jobs.content_hash
            FROM outbox
            JOIN jobs ON jobs.job_id = outbox.job_id
            WHERE outbox.status = 'PENDING'
            ORDER BY jobs.job_id
            LIMIT ?
            """,
            (batch_size,),
        ).fetchall()

    sent = 0
    failed = 0

    for row in pending:
        message = {
            "schema_version": 1,
            "job_id": row["job_id"],
            "input_ref": row["input_ref"],
            "content_hash": row["content_hash"],
        }

        # Queue calls happen outside the database transaction.
        try:
            send(message)
        except Exception as error:
            failed += 1
            log_event(
                "dispatch_failed",
                row["job_id"],
                error_type=type(error).__name__,
                delivery_state="unknown",
            )
            continue

        # An error here leaves the entry pending for another attempt.
        with store.connection() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status = 'SENT'
                WHERE job_id = ? AND status = 'PENDING'
                """,
                (row["job_id"],),
            )

        sent += 1
        log_event("job_dispatched", row["job_id"])

    return {"sent": sent, "failed": failed}