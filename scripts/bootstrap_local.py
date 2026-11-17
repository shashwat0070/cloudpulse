"""Create CloudPulse resources in the local emulator only."""

import json

import boto3
from botocore.config import Config

ENDPOINT = "http://localhost:4566"
TABLE_NAME = "cloudpulse"

options = {
    "endpoint_url": ENDPOINT,
    "region_name": "us-east-1",
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
    "config": Config(
        connect_timeout=3,
        read_timeout=5,
        retries={"mode": "standard", "max_attempts": 2},
    ),
}

sqs = boto3.client("sqs", **options)
dynamodb = boto3.client("dynamodb", **options)


def ensure_queue(name):
    try:
        response = sqs.get_queue_url(QueueName=name)
    except sqs.exceptions.QueueDoesNotExist:
        response = sqs.create_queue(QueueName=name)

    return response["QueueUrl"]


def queue_arn(url):
    response = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["QueueArn"],
    )
    return response["Attributes"]["QueueArn"]


def main():
    dlq_url = ensure_queue("cloudpulse-jobs-dlq")
    jobs_url = ensure_queue("cloudpulse-jobs")

    dlq_arn = queue_arn(dlq_url)
    jobs_arn = queue_arn(jobs_url)

    sqs.set_queue_attributes(
        QueueUrl=dlq_url,
        Attributes={
            "MessageRetentionPeriod": "604800",
            "RedriveAllowPolicy": json.dumps(
                {
                    "redrivePermission": "byQueue",
                    "sourceQueueArns": [jobs_arn],
                }
            ),
        },
    )

    sqs.set_queue_attributes(
        QueueUrl=jobs_url,
        Attributes={
            "VisibilityTimeout": "60",
            "MessageRetentionPeriod": "86400",
            "ReceiveMessageWaitTimeSeconds": "20",
            "RedrivePolicy": json.dumps(
                {
                    "deadLetterTargetArn": dlq_arn,
                    "maxReceiveCount": "5",
                }
            ),
        },
    )

    try:
        dynamodb.describe_table(TableName=TABLE_NAME)
    except dynamodb.exceptions.ResourceNotFoundException:
        dynamodb.create_table(
            TableName=TABLE_NAME,
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

    dynamodb.get_waiter("table_exists").wait(
        TableName=TABLE_NAME,
        WaiterConfig={"Delay": 1, "MaxAttempts": 30},
    )

    table = dynamodb.describe_table(TableName=TABLE_NAME)["Table"]
    actual_keys = {
        item["AttributeName"]: item["KeyType"]
        for item in table["KeySchema"]
    }

    if actual_keys != {"pk": "HASH", "sk": "RANGE"}:
        raise RuntimeError("Existing table has an unexpected key schema")

    print(
        json.dumps(
            {
                "status": "ready",
                "endpoint": ENDPOINT,
                "jobs_queue": jobs_url,
                "dead_letter_queue": dlq_url,
                "table": TABLE_NAME,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()