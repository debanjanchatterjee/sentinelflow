#!/usr/bin/env python3
"""Simple scheduler that periodically moves due jobs from `scheduled_zset` into `ready_queue`.

Usage:
  python scripts/scheduler.py

Environment variables:
- REDIS_URL (optional)
- TESTING=1 to use in-memory redis
- POLL_SECONDS (optional, default 0.5)
"""
import asyncio
import os
import time
from app.redis_helper import get_redis, pop_due_jobs, enqueue_job, get_job

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "0.5"))


async def run_scheduler():
    redis_client = await get_redis()
    print("scheduler: connected")
    try:
        while True:
            now = time.time()
            due = await pop_due_jobs(redis_client, now, count=100)
            if due:
                for job_id in due:
                    # fetch job metadata and enqueue
                    data = await get_job(redis_client, job_id)
                    if data:
                        # ensure status
                        data["status"] = "queued"
                        await enqueue_job(redis_client, job_id, data)
                        # metrics
                        try:
                            from app import metrics

                            metrics.jobs_enqueued_total.inc()
                        except Exception:
                            pass
                        print(f"scheduler: enqueued {job_id}")
            await asyncio.sleep(POLL_SECONDS)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        print("scheduler: exiting")
