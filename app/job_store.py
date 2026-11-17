import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4


class IdempotencyConflict(Exception):
    pass


class JobStore:
    def __init__(self, database: Path):
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)

        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    content_hash TEXT NOT NULL,
                    input_ref TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACCEPTED'
                );

                CREATE TABLE IF NOT EXISTS outbox (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                );
            """)

    @contextmanager
    def connection(self):
        with closing(
            sqlite3.connect(self.database, timeout=30)
        ) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn

    def accept(self, *, key: str, content_hash: str, input_ref: str):
        with self.connection() as conn:
            # Serialize competing submissions before checking the key.
            conn.execute("BEGIN IMMEDIATE")

            existing = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?",
                (key,),
            ).fetchone()

            if existing:
                if existing["content_hash"] != content_hash:
                    raise IdempotencyConflict(
                        "This key was used for different document content"
                    )
                return dict(existing)

            job_id = uuid4().hex

            conn.execute(
                """
                INSERT INTO jobs
                    (job_id, idempotency_key, content_hash, input_ref)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, key, content_hash, input_ref),
            )

            conn.execute(
                "INSERT INTO outbox (job_id) VALUES (?)",
                (job_id,),
            )

            return dict(
                conn.execute(
                    "SELECT * FROM jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
            )