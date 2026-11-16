# ADR 002: Start with an ECS Fargate worker; benchmark Lambda as the alternative

Status: provisional lab decision. Production recommendation and cost winner are unresolved.
Date: 2026-11-16

## Decision question

What should run the document-processing worker, given the requirements in the customer brief?

The first extractor handles text PDFs, not general OCR. We do not yet know its CPU/memory needs, processing-time distribution, or how much of its time will be spent waiting for dependencies.

## Alternatives

| Option | Advantages | Trade-offs and when it wins |
| --- | --- | --- |
| Lambda with SQS event source mapping | Minimal worker-fleet management; capacity follows invocations | Strong candidate for short, bursty, stateless work; benchmark this instead of assuming Fargate is cheaper |
| ECS Fargate service polling SQS | Reuses our container; explicit worker lifecycle, polling, leases, and shutdown behavior | Persistent capacity can cost money while idle; scaling response and capacity planning need measurement |
| EKS | Useful when an existing Kubernetes platform or Kubernetes-specific requirements justify it | Cluster/platform overhead is unjustified for this single workload |

An ordinary Lambda Event Function has a configurable timeout up to 900 seconds. Other Lambda execution modes have different limits; do not generalize that ceiling to every Lambda offering. Our initial document-processing job is not expected to require 15 minutes of compute, so timeout alone does not justify choosing Fargate.

## Provisional decision

Use Fargate for the first AWS reliability lab, building from the existing Docker worker. It lets us investigate worker termination, message visibility, shutdown behavior, and replacement directly.

This includes a learning objective, not proof that it is the best production choice. The customer-facing recommendation remains conditional on measurements. If a representative Lambda comparison is cheaper and satisfies the requirements with less operational work, recommend Lambda.

Use a separate worker task role. Keep execution-role permissions for image pulls/log delivery separate from runtime access. Scope runtime object, queue, and database operations to the intended resources. Avoid passing long-lived AWS credentials into containers.

Keep native ECS replacement enabled. Deployment rollback uses native ECS capabilities. CloudPulse incident handling is initially read-only/dry-run; a mutating controller role is deferred until an experiment establishes a justified action. Chaos experiments use a separate, scoped execution role.

## Evaluation plan

Run the same corpus and extraction implementation in both candidate environments if the comparison fits the time box. Do not benchmark one extractor and extrapolate to a different OCR/model workload.

Record:
- Document bytes/pages and workload arrival pattern.
- Runtime/dependency versions and architecture.
- Allocated memory, CPU where applicable, and concurrency.
- Processing and end-to-end p50/p95, error rate, and backlog drain time.
- Cold-start/scale-out effects where observable.
- Idle and loaded cost, queue requests, storage/database requests, and logs.

Compare using recorded regional prices and test-window usage:
- Fargate: provisioned CPU/memory time, idle capacity, networking, and supporting services.
- Lambda: configured memory, execution time, requests, and supporting services.
- Both: extraction costs, retries, storage, state, observability, and data transfer.

Documents/day is only an arrival-rate input. It cannot establish a universal cost crossover. Larger-scale models must show their assumptions and capacity limits.

ARM/Graviton is an optional comparison after baseline correctness. Verify library compatibility and compare identical workloads against x86 before reporting savings.

## Availability and operational consequences

One worker can demonstrate retry after a crash but cannot establish uninterrupted processing through an AZ outage. More than one appropriately placed worker may improve availability at additional cost; test scope and deployed topology must be explicit.

A graceful shutdown should stop receiving new work and either finish within its allowed time or leave the message undeleted. Abrupt termination must still be safe. Result correctness depends on durable commit guards, not graceful shutdown alone.

Fargate means owning polling, heartbeat, and fleet behavior. Lambda moves some of that into the event source mapping, while duplicate-safe job processing still matters. Neither runtime removes the need for a documented acceptance boundary.

## Revisit triggers

Recommend Lambda for a short/bursty workload if measurements meet latency and cost objectives with less operational effort. Retain Fargate if measured runtime needs, dependency packaging, sustained utilization, or lifecycle requirements justify it. Reconsider EKS only if a real platform/customer constraint appears.

If time does not permit a Lambda benchmark, publish a cost model and label the comparison unvalidated; do not present an inferred winner as an experiment result.

## Sources

- [Lambda timeout and execution-mode caveats](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html)
- [ECS service recovery behavior](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_HealthCheck.html)
- [ECS deployment failure detection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-failure-detection.html)
- [ECS IAM authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html)
