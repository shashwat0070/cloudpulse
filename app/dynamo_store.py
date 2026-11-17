import hashlib
import time


from app.job_store import IdempotencyConflict


class DynamoJobStore:
    """Implements the same accept(...) operation as the SQLite store."""

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def _read_job(self, job_id):
        response = self.client.get_item(
            TableName=self.table_name,
            Key={
                "pk": {"S": f"JOB#{job_id}"},
                "sk": {"S": "META"},
            },
            ConsistentRead=True,
        )

        item = response.get("Item")
        if item is None:
            return None

        return {
            field: item[field]["S"]
            for field in (
                "job_id",
                "idempotency_key",
                "content_hash",
                "input_ref",
                "status",
            )
        }

    @staticmethod
    def _check_content(existing, content_hash):
        if existing["content_hash"] != content_hash:
            raise IdempotencyConflict(
                "This key was used for different document content"
            )
        return existing

    def accept(self, *, key, content_hash, input_ref):
        # Job IDs are opaque. This backend derives one from the key.
        job_id = hashlib.sha256(key.encode()).hexdigest()

        job = {
            "job_id": job_id,
            "idempotency_key": key,
            "content_hash": content_hash,
            "input_ref": input_ref,
            "status": "ACCEPTED",
        }

        job_item = {
            "pk": {"S": f"JOB#{job_id}"},
            "sk": {"S": "META"},
            **{name: {"S": value} for name, value in job.items()},
        }

        outbox_item = {
            "pk": {"S": "OUTBOX#PENDING"},
            "sk": {"S": f"JOB#{job_id}"},
            "job_id": {"S": job_id},
            "content_hash": {"S": content_hash},
            "input_ref": {"S": input_ref},
        }

        for attempt in range(6):
            existing = self._read_job(job_id)
            if existing:
                return self._check_content(existing, content_hash)

            try:
                self.client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self.table_name,
                                "Item": item,
                                "ConditionExpression":
                                    "attribute_not_exists(pk)",
                            }
                        }
                        for item in (job_item, outbox_item)
                    ]
                )
                return job

            except self.client.exceptions.TransactionCanceledException as error:
                # Another submission may have committed first.
                existing = self._read_job(job_id)
                if existing:
                    return self._check_content(existing, content_hash)

                reasons = {
                    reason.get("Code")
                    for reason in error.response.get(
                        "CancellationReasons", []
                    )
                }

                if not reasons.issubset({"None", "TransactionConflict"}):
                    raise

                if "TransactionConflict" not in reasons:
                    raise

                time.sleep(min(0.01 * (2 ** attempt), 0.2))

        raise RuntimeError("Transaction remained conflicted after retries")