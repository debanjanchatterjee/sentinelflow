import asyncio
import time
import re
import pytest


@pytest.mark.asyncio
async def test_scheduled_job_end_to_end(client):
    """Starts scheduler and worker, submits a scheduled job, and asserts it completes and metrics increment.

    Uses the `client` fixture from tests/conftest.py which sets TESTING=1 and provides an httpx AsyncClient
    bound to the FastAPI app.
    """
    # Capture metrics baseline
    res0 = await client.get("/metrics")
    assert res0.status_code == 200
    metrics_before = res0.text

    # Start scheduler and worker in background
    from scripts.scheduler import run_scheduler
    from scripts.worker import run_worker

    sched_task = asyncio.create_task(run_scheduler())
    worker_task = asyncio.create_task(run_worker())

    try:
        # schedule job ~1s in the future
        schedule_at = time.time() + 1.0
        payload = {"type": "integration", "payload": {"ok": True}, "schedule_at": schedule_at}
        submit = await client.post("/jobs", json=payload, headers={"X-API-Key": "dev-key"})
        assert submit.status_code == 200
        job_id = submit.json()["job_id"]

        # Immediately job should be scheduled
        r = await client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "scheduled"

        # Wait up to ~10s for the worker to process the job
        completed = False
        for _ in range(20):
            await asyncio.sleep(0.5)
            r = await client.get(f"/jobs/{job_id}")
            if r.status_code == 200 and r.json().get("status") == "completed":
                completed = True
                break
        assert completed, "Job did not reach 'completed' status in time"

        # Check metrics after processing
        res_after = await client.get("/metrics")
        assert res_after.status_code == 200
        metrics_after = res_after.text

        def get_counter(text: str, name: str) -> float:
            m = re.search(rf'^{name}\s+(\d+\.?\d*)', text, re.M)
            return float(m.group(1)) if m else 0.0

        before_exec = get_counter(metrics_before, "jobs_executed_total")
        after_exec = get_counter(metrics_after, "jobs_executed_total")
        assert after_exec >= before_exec + 1

    finally:
        sched_task.cancel()
        worker_task.cancel()
        await asyncio.gather(sched_task, worker_task, return_exceptions=True)
