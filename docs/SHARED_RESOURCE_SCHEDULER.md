# Shared Resource Scheduler Contract

## Purpose

Coordinate GPU, VRAM, CPU, storage, provider concurrency and spend across the Content Factory and Movie Studio. Each division retains its own workflow, project state, priorities and budget.

## Request model

A scheduler request should carry:

| Field | Meaning |
|---|---|
| `job_id` | Stable idempotent job identifier |
| `division` | `content_factory` or `movie_studio` |
| `owner_id` | Channel, movie project or other owning entity |
| `workload` | `llm`, `image`, `video`, `audio`, `render`, `qa` |
| `execution_mode` | `local`, `cloud`, `hybrid` |
| `priority` | Policy-controlled priority class |
| `resource_estimate` | VRAM, GPU slots, CPU slots, RAM and storage |
| `cost_ceiling` | Maximum permitted provider spend |
| `deadline` | Optional target completion time |
| `resumable` | Whether work can be safely paused/retried |
| `idempotency_key` | Prevent duplicate dispatch |

## Admission and lease lifecycle

`QUEUED -> ADMITTED -> RUNNING -> SUCCEEDED`

Alternative outcomes: `WAITING_FOR_CAPACITY`, `PAUSED`, `RETRYABLE_FAILURE`, `FAILED`, `CANCELLED`.

Admission reserves capacity atomically before dispatch. A lease records the reservation, owner, start time, expiry/heartbeat and terminal release. A worker must not start expensive generation without an active lease. Lease expiry/recovery must be designed for the actual queue and database semantics before production use.

## Fairness and isolation

- Apply per-division concurrency caps and global hardware/provider caps.
- Use weighted fair scheduling or round-robin between divisions so either division can make progress.
- Allow priority boosts for deadlines, but prevent unbounded starvation.
- Apply per-project and per-channel spend ceilings.
- A movie project cannot consume a channel's budget, and a channel cannot consume a movie project's budget.
- Keep queue metrics and failure reporting partitioned by division.

## Local/cloud routing

Local execution is eligible only when current resource telemetry and workload estimates indicate safe capacity. Cloud execution requires explicit project/provider policy and an available budget. Hybrid mode may choose per workload, but every route and cost must be recorded.

If telemetry is missing or stale, fail closed for GPU-heavy local admission rather than assuming free VRAM. The initial deterministic scheduler can use configured capacity limits; telemetry-aware routing is a later implementation step.

## Required observability

Record queue wait, execution duration, estimated and actual resource use, provider/model, retry count, output asset, estimated and actual cost, lease lifecycle and final status. Surface shortfalls and blocked reasons in both dashboards.

## Acceptance tests

1. Two divisions submitting simultaneously never exceed global configured GPU slots.
2. A division at its concurrency cap does not block eligible work from the other division.
3. A failed or cancelled job releases its reservation.
4. Duplicate idempotency keys do not dispatch duplicate work.
5. Budget exhaustion blocks cloud work with an explicit reason.
6. A resumable shot retry does not rerun completed shots.
7. Fairness policy prevents indefinite starvation under sustained load.
8. Missing/stale telemetry blocks GPU-heavy local admission when configured to fail closed.

This document is a contract, not a claim that the scheduler is already implemented.
