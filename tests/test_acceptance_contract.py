import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config

from app.dynamo_store import DynamoJobStore
from app.job_store import IdempotencyConflict, JobStore


@pytest.fixture
def dynamo_store():
    # Explicit local endpoint and dummy credentials.
    client = boto3.client(
        "dynamodb",
        endpoint_url="http://127.0.0.1:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(
            connect_timeout=2,
            read_timeout=5,
            retries={"mode": "standard", "max_attempts": 1},
        ),
    )

    table_name = f"cloudpulse-test-{uuid4().hex}"

    client.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )

    try:
        client.get_waiter("table_exists").wait(
            TableName=table_name,
            WaiterConfig={"Delay": 1, "MaxAttempts": 30},
        )
        yield DynamoJobStore(client, table_name), client, table_name
    finally:
        # Remove only this test's uniquely named local table.
        client.delete_table(TableName=table_name)


@pytest.fixture(params=["sqlite", "dynamodb"])
def acceptance_store(request, tmp_path):
    if request.param == "sqlite":
        return JobStore(tmp_path / "jobs.db")

    return request.getfixturevalue("dynamo_store")[0]


def submit(store, content_hash="hash-a"):
    return store.accept(
        key="invoice-001",
        content_hash=content_hash,
        input_ref="inputs/example.pdf",
    )


def test_acceptance_contract(acceptance_store):
    first = submit(acceptance_store)
    repeated = submit(acceptance_store)

    assert first["status"] == "ACCEPTED"
    assert repeated == first

    with pytest.raises(IdempotencyConflict):
        submit(acceptance_store, content_hash="different-content")


def test_concurrent_acceptance_contract(acceptance_store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(
            pool.map(
                lambda _: submit(acceptance_store),
                range(8),
            )
        )

    assert len({job["job_id"] for job in jobs}) == 1


def test_dynamo_transaction_rolls_back_job(dynamo_store):
    store, client, table_name = dynamo_store
    job_id = hashlib.sha256(b"invoice-001").hexdigest()

    # Deliberately create a conflicting outbox entry.
    client.put_item(
        TableName=table_name,
        Item={
            "pk": {"S": "OUTBOX#PENDING"},
            "sk": {"S": f"JOB#{job_id}"},
        },
    )

    with pytest.raises(client.exceptions.TransactionCanceledException):
        submit(store)

    response = client.get_item(
        TableName=table_name,
        Key={
            "pk": {"S": f"JOB#{job_id}"},
            "sk": {"S": "META"},
        },
        ConsistentRead=True,
    )

    # The job write must roll back when the outbox write fails.
    assert "Item" not in response