# CloudPulse design and evidence

This is a fictional customer case study. The document-processing architecture is proposed; it is not deployed or benchmarked.

Read in this order:

1. [Customer brief](customer-brief.md): requirements, boundaries, and acceptance criteria.
2. [ADR 001: Messaging](adr/001-messaging.md): SQS, retries, and the acceptance boundary.
3. [ADR 002: Compute](adr/002-compute.md): provisional Fargate choice and the Lambda comparison.
4. [Job lifecycle and idempotency](job-lifecycle.md): implementation contract to test before Terraform.

## Evidence status on 2026-11-16

| Item | Evidence |
| --- | --- |
| FastAPI health and demo controls | App and tests are committed; four passing tests reported by the builder |
| Docker health detection and manual recovery | Successful local test reported by the builder; Docker files remain local at this checkpoint |
| Generic recovery-policy tests | Code supplied during development; execution result not yet recorded |
| Document submission, queue, worker, and idempotency | Planned |
| AWS infrastructure, OIDC, FIS, and cloud dashboards | Planned; deployment requires explicit approval |
| Latency, recovery time, throughput, extraction quality, and cost | Not measured |

A reported local result is not an independently reproduced cloud result. Future experiment reports must identify commit SHA, environment, configuration, input corpus, run IDs, and raw evidence. Failed and timed-out runs remain in the report.

Next implementation milestone: a local submission/outbox/worker slice with tests for acceptance gaps, duplicate delivery, lease takeover, and stale-worker commits.
