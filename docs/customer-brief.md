# Customer brief: CloudPulse

Status: draft design assumptions, 2026-11-16. No customer engagement, production deployment, or performance result is implied.

## Executive brief

LedgerLane is a fictional accounts-payable automation company. It wants invoice-processing jobs to remain recoverable when a worker fails, duplicate deliveries to avoid duplicate committed results, and malformed documents to be isolated for review.

CloudPulse will demonstrate these behaviors with synthetic documents. We will publish the evidence and explain the trade-offs. An API responding successfully is insufficient evidence that processing recovered: a valid pending job must finish.

## Requirements and assumptions

| Area | Proposed requirement or assumption | How to assess it |
| --- | --- | --- |
| Design workload | 50,000 documents/day, approximately 0.58 documents/second on average; assume a 10x short peak, approximately 5.8/second | Model only until a stated load test supports it |
| Processing objective | At least 95% of valid accepted jobs complete within 15 minutes under a declared load profile | Acceptance-to-result timestamps; publish p50/p95 and failures |
| Lab corpus | Synthetic, text-based PDF invoices, at most 5 pages and 5 MiB each | Fixed versioned corpus and explicit validation |
| Extraction scope | Extract available text and a few fields from a known template | Compare against fixture ground truth; do not claim general OCR accuracy |
| Recoverability | Every acknowledged submission remains discoverable as pending, processing, succeeded, or quarantined within the documented retention boundary | Reconcile accepted IDs against durable records and outputs |
| Duplicate safety | At most one canonical committed result per job ID, including concurrent deliveries and worker takeover | Concurrency and crash-boundary tests |
| Poison messages | Repeatedly failing messages reach a DLQ; healthy jobs continue | Mixed valid/invalid workload and DLQ evidence |
| Dependency outage | Bounded retries and an observable terminal or pending state; avoid restart loops | Controlled outage and restoration |
| Data handling | Synthetic documents only in the lab; no real invoices or customer credentials | Corpus review and log checks |
| Lab spend | Local phase first; AWS budget and experiment spend limits must be agreed before deployment | Priced plan, approval, actual usage, teardown verification |

The modeled daily volume is not a measured capacity claim. The 15-minute objective is a proposed service-level objective, not a contractual SLA. Monthly production cost is unresolved until processing time, deployment topology, retention, and extraction choice are modeled.

## What acceptance means

Return HTTP 202 only after the input object is stored and a job record plus a pending-dispatch outbox record are durably committed. SQS publication may follow. A failed publication must remain visible as pending dispatch and be retried by a reconciler.

The client supplies an idempotency key. Repeating the same key and content returns the existing job. Reusing the key for different content returns a conflict. An upload that never reaches durable acceptance may leave an orphan object; cleanup must distinguish those objects from accepted inputs.

The guarantee is bounded by retention, correct configuration, and the tested failure model. This lab does not establish zero data loss during arbitrary corruption, malicious deletion, or a Region-wide disaster.

## Small first release

Build:
- Submission/status API, private document storage, queue and DLQ, one worker implementation, and durable job/outbox state.
- Native ECS task replacement and SQS redelivery.
- Structured logs, useful metrics, and a dashboard.
- Four experiments with raw results.
- Terraform, scoped IAM, keyless OIDC deployment, and teardown.
- Incident recording; custom remediation remains dry-run.

Defer:
- General-purpose OCR, paid LLM extraction, live customer integrations, and payment side effects.
- EKS, a generic remediation platform, automatic DLQ redrive, and automatic cross-Region failover.
- Broad infrastructure fault coverage and production availability claims.

A second lab worker can make takeover easier to observe, but worker count is a priced configuration decision. Two configured subnets do not demonstrate survival of an AZ outage.

## Four experiments

| Question | Injection and observation | Pass criterion |
| --- | --- | --- |
| Worker dies mid-job | Stop a worker after receipt and before result commit; record receive, lease, failure, redelivery, and completion times | Accepted job eventually has one canonical result; interrupted attempt cannot overwrite its replacement |
| Duplicate delivery | Deliberately enqueue duplicate job references and overlap processing attempts | One canonical result, with duplicate and lease-conflict decisions visible |
| Poison document | Mix malformed or unsupported documents with valid ones | Bad job reaches quarantine/DLQ; valid jobs finish; no automatic blind redrive |
| Dependency outage | Make the extraction adapter return controlled transient failures, then restore it | Retries remain bounded; every accepted job is accounted for; recovery is verified using completed work |

Use FIS for supported infrastructure faults, initially ECS task stop with scoped targets and CloudWatch stop conditions. Use the application test harness for duplicates and poison documents. Dependency-fault injection must match the actual supported mechanism; do not imply FIS supplies every application failure.

For each experiment aim for at least 10 independent, reset runs. Record configuration and input size. Publish every run, the median and range, and timeouts or failures. Report latency percentiles from an adequately sized job sample; ten experiment runs alone do not make a robust tail-latency estimate.

## Observability and evidence

Application logs include timestamp, event name, job_id, attempt_id, worker identity, and outcome. System-only events have job_id=null and an experiment_id where applicable. Never log document text or credentials.

Put per-job identifiers in logs, not metric dimensions. Use bounded dimensions such as service, environment, and outcome. Emit job duration and processing-attempt metrics through EMF. Use native SQS metrics for queue age and depth, with their approximate semantics documented.

Distinguish queue wait, processing duration, end-to-end job latency, task replacement time, and time until useful work resumes. A successful stop/restart API call is not a recovery measurement.

## Delivery and cost boundaries

1. Design and local correctness tests.
2. Local adapters/emulation and all four scenarios.
3. Terraform and OIDC pipeline; offline checks first.
4. Approved AWS deployment, observability, and FIS experiments.
5. Load/cost evaluation and teardown.
6. Executive summary, technical findings, runbook, demo, and lessons.

Target 2–3 weeks, subject to available time. Time-box optional features before expanding services.

Infrastructure estimates and measured usage must be separate. Model 1k, 100k, and 1M documents/day using explicit pages/document, bytes/document, duration, memory/CPU, concurrency, retention, request counts, and idle capacity. Report test-window cost per 1,000 completed documents and disclose exclusions, credits, and shared costs. Include networking, logs, FIS, and extraction charges where used. ARM/x86 comparisons require identical inputs and recorded configurations.

No apply, paid CI plan against AWS, remote-state bootstrap, FIS run, or paid extraction call is authorized by this document. Budget alerts are not a guaranteed spending cap.
