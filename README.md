# sentinelflow

## Developer Guide

This guide explains how to setup a development environment, run the FastAPI control plane against your local Redis, and validate the key metrics declared in DESIGN.md.

Prerequisites
- Python 3.10+ installed
- Redis running locally (default: redis://localhost:6379/0)

1) Create a virtual environment and activate it

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2) Install runtime and dev dependencies using `pyproject.toml`

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
```

3) Start Redis (if not already running)

macOS (Homebrew):

```bash
brew services start redis
# or run directly
redis-server /usr/local/etc/redis.conf
```

4) Run the control plane

```bash
# using the helper script
API_KEY=dev-key REDIS_URL=redis://localhost:6379/0 ./scripts/run.sh

# or directly with uvicorn
API_KEY=dev-key REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --reload
```

API notes
- Write endpoints require an API key in header `X-API-Key` (default `dev-key`).
- Endpoints:
  - `POST /jobs` — submit a job
  - `GET /jobs/{job_id}` — job status
  - `GET /jobs` — list jobs
  - `POST /jobs/{job_id}/retry` — manual retry
  - `POST /jobs/{job_id}/cancel` — cancel job
  - `GET /healthz`, `GET /readyz` — health/readiness
  - `GET /metrics` — Prometheus metrics

Metrics validation (smoke tests)
- Submit a job and verify counters increment

```bash
curl -sS -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -d '{"type":"email","payload":{"to":"alice@example.com"}}' | jq

# Get the job_id from the response and verify status
curl -sS http://localhost:8000/jobs/<JOB_ID> | jq

# Check counters
curl -sS http://localhost:8000/metrics | grep jobs_submitted_total -n
curl -sS http://localhost:8000/metrics | grep jobs_enqueued_total -n
```

Run tests (uses in-memory async Redis when `TESTING=1`)

```bash
TESTING=1 pytest -q
```

Notes
- Counters are process-local and will reset when you restart the control plane. For multi-process deployment use Prometheus multiprocess mode (not configured by default here).
- If you want me to add a lightweight worker that consumes the ready queue and emits execution metrics, tell me and I will implement it under `scripts/worker.py`.
