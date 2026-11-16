# ADR 001: Use an SQS Standard queue with a DLQ

Status: proposed for the first implementation; cloud behavior and operating parameters remain unvalidated.
Date: 2026-11-16

## Decision question

How should accepted invoice-processing jobs be buffered and retried independently of worker availability?

Documents are independent. The initial requirement does not need strict ordering, stream replay for multiple consumers, or broker-protocol compatibility.

## Alternatives

| Option | Fits when | Trade-off for this case |
| --- | --- | --- |
| SQS Standard | Independent work, competing consumers, native redelivery and DLQ | Duplicate delivery and ordering assumptions must be handled in the application |
| SQS FIFO | Per-group ordering or send-side deduplication is required | Adds ordering/group decisions; does not remove the need for safe side effects and result commits |
| Amazon MQ | Existing applications require protocols such as AMQP or JMS | Broker operations and compatibility benefits do not serve our initial requirements |
| Kinesis Data Streams | Ordered stream consumption, retention/replay, and multiple independent consumers are central | Requires stream/consumer design for a workload currently modeled as independent jobs |

EventBridge Pipes is an integration mechanism that can connect a queue to a target; it is not a queue substitute. Step Functions is a separate orchestration decision if extraction develops into a multi-stage workflow with explicit waits or branching.

## Decision

Use SQS Standard plus a DLQ, long polling, and explicit deletion after a durable result commit. Put job ID, schema version, and an input-object reference in each message. Keep document bytes in object storage.

Use a durable outbox. Commit the job and its outbox entry in one database transaction after the input object exists. A small reconciler publishes pending entries and records delivery. An ambiguous send outcome may cause a duplicate; consumer idempotency must tolerate it. This avoids silently acknowledging a job whose database write succeeded but queue publication failed.

Outbox publication can initially be handled by the existing worker process with bounded polling. DynamoDB job/outbox items use a transaction; a local adapter uses a transaction with equivalent application-level tests. A separate dispatcher service is deferred.

## Initial parameters: hypotheses to test

| Parameter | Lab starting point | Reason and revision rule |
| --- | --- | --- |
| Visibility timeout | 60 seconds | Balances crash retry delay with short initial jobs; revisit from measured processing and commit times |
| Heartbeat interval | 15 seconds | Renew only while the attempt owns its lease and is within its absolute deadline |
| Processing lease | 45 seconds | Renew with ownership checks; result commits require a current, unexpired lease |
| Attempt deadline | 120 seconds | Prevent a live heartbeat thread from renewing a hung attempt indefinitely |
| maxReceiveCount | 5 | Bounds repeated delivery before quarantine; not a count of successful processing starts |
| Source retention | 1 day | Lab scope only; not a production recommendation |
| DLQ retention | 7 days | Longer than source retention; accepted input and job records must remain available at least through this review window |

Message visibility expiry permits another delivery; it does not kill the old worker or prove exclusive ownership. Extending visibility does not replace the result-commit guard.

Do not delete a duplicate while another valid attempt is processing the same job. Defer it with bounded visibility handling. A message for an already committed job can be acknowledged safely.

Queue depth and oldest-message age are approximate indicators, not a per-job audit ledger. Queue age alone cannot diagnose worker failure. Mixed traffic, retries, dependency health, progress, and active worker count all matter.

## Consequences and evidence required

Benefits: separates API latency from processing, makes native retry behavior observable, and provides a bounded poison-message path.

Costs: outbox reconciliation, duplicate-safe completion, lease takeover, and DLQ inspection are real implementation work. No automatic poison-message redrive.

Before accepting this decision:
- Crash between object storage, job/outbox transaction, queue send, and dispatch marking.
- Deliver the same job concurrently and allow an old lease to expire.
- Crash after writing output but before committing the canonical pointer.
- Verify valid work proceeds while poison documents reach the DLQ.
- Test at least one deliberately undersized visibility timeout and retain the observed findings.

Choose differently if strict per-customer ordering becomes necessary (evaluate FIFO), stream replay/multiple independent consumers become primary (evaluate Kinesis), or a legacy protocol becomes mandatory (evaluate MQ). Introduce orchestration only when the workflow requires it.

## Sources

- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [EventBridge Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes.html)
