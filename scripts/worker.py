#!/usr/bin/env python3
"""Lightweight async worker that pops job IDs from the Redis `ready_queue`, marks job status,
simulates execution, and updates metrics.

Usage:
  API_KEY=dev-key REDIS_URL=redis://localhost:6379/0 python scripts/worker.py

Set TESTING=1 to use the in-memory AsyncInMemoryRedis implementation used by the tests.
"""
import asyncio
import os
import time
import random
from typing import Any

from app.redis_helper import get_redis
from app import metrics

TESTING = os.getenv("TESTING") == "1"
SLEEP_BETWEEN_POLLS = float(os.getenv("WORKER_POLL_SECONDS", "0.5"))


async def handle_job(redis_client, job_id: str):
    # Mark running
    job = await redis_client.hget("jobs", job_id)
    if job is None:
        return
    import json

    data = json.loads(job)
    data["status"] = "running"
    data["started_at"] = time.time()
    await redis_client.hset("jobs", job_id, json.dumps(data))

    # Simulate work
    start = time.time()
    work_time = random.uniform(0.01, 0.1) if TESTING else random.uniform(0.1, 1.0)
    await asyncio.sleep(work_time)

    # Mark completed
    data["status"] = "completed"
    data["completed_at"] = time.time()
    data["attempts"] = data.get("attempts", 0) + 1
    await redis_client.hset("jobs", job_id, json.dumps(data))

    # Metrics
    metrics.jobs_executed_total.inc()
    metrics.execution_latency_seconds.observe(time.time() - start)


async def run_worker():
    redis_client = await get_redis()
    print("worker: connected, testing=", TESTING)
    try:
        while True:
            job_id = await redis_client.lpop("ready_queue")
            if job_id:
                try:
                    await handle_job(redis_client, job_id)
                except Exception as e:
                    print("worker: error handling job", job_id, e)
            else:
                await asyncio.sleep(SLEEP_BETWEEN_POLLS)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("worker: exiting")
