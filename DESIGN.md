# SentinelFlow — System Design & Implementation Guide

Small, interview-friendly scheduler/worker system with a RAG-based ops analysis pipeline.

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)  
2. [Core Components](#core-components)  
   - [Redis Data Model](#redis-data-model)  
   - [Scheduler](#scheduler)  
   - [Worker](#worker)  
   - [Idempotency](#idempotency)  
   - [Retry & Backoff](#retry--backoff)  
3. [Logging & Observability](#logging--observability)  
4. [Control Plane (FastAPI)](#control-plane-fastapi)  
5. [RAG-Based Ops Agent](#rag-based-ops-agent)  
6. [Implementation Plan (Weekend MVP)](#implementation-plan-weekend-mvp)  
7. [Testing & Validation](#testing--validation)  
8. [Scalability Discussion (Interview)](#scalability-discussion-interview)  
9. [Trade-offs & Limitations](#trade-offs--limitations)  
10. [Why This Design Works for Interviews](#why-this-design-works-for-interviews)  
11. [Next Possible Extensions (Optional)](#next-possible-extensions-optional)

---

## High-Level Architecture

System follows a scheduler → Redis → worker architecture. Logs and configs feed an ops analysis pipeline that uses FAISS and Ollama for RAG.

    Users / CI
        |
        v
    +---------+
    | FastAPI |   <-- Control Plane (job submit, cancel, retry, health/metrics)
    +----+----+
         |
         v
    +-------------------+
    |   Redis (state)   |
    | - jobs:{job_id}   |
    | - ready_queue      <- workers BLPOP / ZPOPMIN
    | - scheduled_zset   <- scheduler moves due jobs -> ready_queue
    | - completed:{id}   <- idempotency markers
    | - dlq (failed_jobs)|
    +----+-------+------+
         |       |
         v       v
   +-----------+ +------------+
   | Scheduler | |  Worker(s) |
   | (enqueue, | | (claim,    |
   |  scheduled)| | execute,   |
   +-----------+ | update Redis|
                 +------+------+
                        |
                        v
                   Execution logs
                        |
        +---------------+----------------+
        |                                |
 +------+-----+                  +-------+-------+
 | Metrics /  |                  | Logs for RAG  |
 | Prometheus |                  | (persist ->   |
 | / Tracing  |                  |  FAISS index) |
 +------------+                  +---------------+
                                          |
                                          v
                                       Ollama
                                       (RAG Ops Agent)

Notes:
- FastAPI is the control plane: it writes job metadata and enqueues/schedules jobs in Redis and publishes control signals (pub/sub or control queue) for cancellations/retries.
- Scheduler periodically moves due jobs from `scheduled_zset` into `ready_queue` atomically.
- Workers atomically claim jobs (using locks/visibility timeouts), execute handlers, and update job state; repeated failures route jobs to `dlq`.
- Logs and metrics are emitted by FastAPI, Scheduler and Workers; logs are indexed (FAISS) for the RAG pipeline which Ollama consumes.

---

## Core Components

### Redis Data Model

Keys:
- `jobs:{job_id}` → job metadata
- `ready_queue` → list or sorted set of runnable jobs
- `in_progress:{job_id}` → execution lock
- `completed:{job_id}` → idempotency marker
- `failed_jobs` → failed job records

Why Redis?
- Atomic operations
- Fast local setup
- Familiar to interviewers

### Scheduler

Responsibilities:
- Scan scheduled jobs
- Determine if a job is runnable
- Enqueue runnable jobs once

Implementation approach:
- Periodic loop (e.g., every 500ms)
- Use Redis sorted sets with timestamps for scheduling
- Use `SETNX` (or `SET ... NX`) to prevent duplicate enqueue

Failure tolerance:
- Scheduler restart is safe because state is persisted in Redis

### Worker

Responsibilities:
- Poll Redis for jobs
- Claim job atomically
- Execute handler
- Update job state

Execution flow:
1. BLPOP / ZPOPMIN job from queue
2. `SETNX` in-progress lock (or use Redis transactions)
3. Execute job
4. On success: mark completed
5. On failure: increment retry count and re-enqueue or mark failed

### Idempotency

- Each job has an `idempotency_key`
- Worker checks `completed:{idempotency_key}` before execution
- Prevents duplicate execution across retries and restarts

### Retry & Backoff

- Maintain `attempt_count` per job
- If `attempt_count < max_retries`: re-enqueue job with delay (sorted set score = next run timestamp)
- Else: mark job as permanently failed and record in `failed_jobs`

---

## Logging & Observability

Each execution produces a log record (example JSON):

    {
        "job_id": "...",
        "job_type": "...",
        "status": "success|failed|running",
        "error_message": null,
        "timestamp": "2024-01-01T00:00:00Z",
        "retry_count": 0
    }

Logs storage options:
- Append logs to a local file (per-instance)
- Or push to a Redis list for centralized short-term storage
- Periodically persist or export logs to long-term storage for RAG indexing

Log fields should be consistent and indexed where possible (job_id, status, timestamp).

---

## Control Plane (FastAPI)

Responsibilities
- Expose an HTTP API for job submission, status, management, and observability.
- Validate and normalize job payloads before persisting to Redis.
- Enqueue jobs into Redis (ready queue or scheduled sorted set).
- Provide health, readiness, and metrics endpoints for orchestration and automation.

Core API Endpoints (MVP)
1. `POST /jobs` — submit a job (accepts job payload, returns `job_id` and `status`)
2. `GET /jobs/{job_id}` — fetch job status and metadata
3. `GET /jobs` — list / search jobs (filters: status, type, time range, idempotency_key)
4. `POST /jobs/{job_id}/retry` — trigger a manual retry
5. `POST /jobs/{job_id}/cancel` — cancel a queued or running job
6. `GET /healthz`, `GET /readyz` — liveness/readiness checks
7. `GET /metrics` — Prometheus-compatible metrics endpoint

Authentication & Validation
- Require API keys or JWTs for control operations (at least for write operations).
- Validate job schema at submission time (type, payload shape, idempotency_key, max_retries).
- Enforce rate limits for public endpoints and provide elevated scopes for ops users.

Integration with Scheduler & Workers
- FastAPI writes job metadata to `jobs:{job_id}` and enqueues to `ready_queue` or a scheduled sorted set.
- Use optimistic checks for `completed:{idempotency_key}` to avoid duplicate submission/execution.
- For cancellation or manual retry requests, update job state in Redis and publish control signals (control queue or Redis pub/sub) that the scheduler/worker can observe.
- Keep the API layer stateless; persistent state lives in Redis.

Background Tasks & Long-running Control Actions
- Use FastAPI background tasks or a dedicated control queue for heavier control-plane work (e.g., large replay, bulk cancel).
- Ensure background tasks use the same Redis connection pool and follow the same idempotency checks.

Observability & Telemetry
- Emit structured request logs (include job_id when present) and correlate with execution logs.
- Expose Prometheus metrics: request latencies, enqueue counts, error rates, active background tasks.
- Provide traces (OpenTelemetry) for requests that touch the scheduler or enqueue operations.

Deployment Notes
- Run FastAPI as a separate process/service from workers; scale independently based on control-plane load.
- Use connection pooling and circuit breakers for Redis access.
- Keep the control plane stateless and horizontally scalable; use an API gateway/load balancer for routing and auth.

MVP Implementation Checklist
- Add FastAPI skeleton and routes for the endpoints above
- Input validation and simple API key auth middleware
- Redis integration for job creation/enqueue and control signals
- Health/metrics endpoints and basic logging
- Update `DESIGN.md` TOC to include this section

---

## RAG-Based Ops Agent

### Data Sources
- Job configuration snapshots
- Execution logs
- Failure traces and stack traces

### Indexing Pipeline
1. Convert logs/configs to text chunks
2. Generate embeddings locally
3. Store vectors in FAISS (or another vector DB)

### Query Flow
1. User asks a failure-related question
2. Retrieve Top-K similar documents from FAISS
3. Pass context (documents + logs) to Ollama
4. Generate a summarized root cause and retry suggestion

---

## Implementation Plan (Weekend MVP)

Day 1
- Redis schema
- Scheduler loop
- Basic worker execution
- Retry logic

Day 2
- Logging and failure capture
- FAISS indexing pipeline
- Ollama integration
- Ops agent CLI

---

## Testing & Validation

Load Testing
- Spawn multiple workers
- Generate 500+ jobs
- Measure enqueue → execution latency and throughput

Failure Simulation
- Kill worker mid-job to ensure lock/timeouts behave correctly
- Inject timeouts and handler errors
- Verify retry behavior and eventual failure handling

---

## Scalability Discussion (Interview)

- Horizontal scaling: add more workers
- Replace Redis if needed:
  - Kafka for durable, partitioned queueing
  - Database for persistent metadata and state
- Ops agent can scale independently from execution plane

---

## Trade-offs & Limitations

- At-least-once execution semantics (MVP)
- Redis is the single coordination point (simplicity vs single point of failure)
- No built-in UI or DAG support (intentionally minimal for MVP)

---

## Why This Design Works for Interviews

- Uses standard scheduler-worker patterns
- Clear separation of responsibilities
- Demonstrates realistic failure handling and retry strategies
- Provides natural extensions (RAG ops agent, priority queues, DLQ)

---

## Next Possible Extensions (Optional)

- Priority queues
- Dead-letter queue (DLQ)
- REST API for job submission and status
- Web dashboard for monitoring and manual retries
