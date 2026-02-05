import os
import pytest
import asyncio


@pytest.mark.asyncio
async def test_submit_and_metrics(client):
    # Submit a job
    res = await client.post("/jobs", json={"type": "email", "payload": {"to": "a@b.com"}}, headers={"X-API-Key": "dev-key"})
    assert res.status_code == 200
    body = res.json()
    job_id = body["job_id"]

    # Verify job is retrievable
    res2 = await client.get(f"/jobs/{job_id}")
    assert res2.status_code == 200
    data = res2.json()
    assert data["status"] == "queued"

    # Check metrics contain counters
    resm = await client.get("/metrics")
    assert resm.status_code == 200
    text = resm.text
    assert "jobs_submitted_total" in text
    assert "jobs_enqueued_total" in text


@pytest.mark.asyncio
async def test_retry_and_cancel(client):
    # Submit a job
    res = await client.post("/jobs", json={"type": "task", "payload": {"x": 1}}, headers={"X-API-Key": "dev-key"})
    job_id = res.json()["job_id"]

    # Cancel it
    rc = await client.post(f"/jobs/{job_id}/cancel", headers={"X-API-Key": "dev-key"})
    assert rc.status_code == 200
    rcj = await client.get(f"/jobs/{job_id}")
    assert rcj.json()["status"] == "cancelled"

    # Retry
    rr = await client.post(f"/jobs/{job_id}/retry", headers={"X-API-Key": "dev-key"})
    assert rr.status_code == 200
    rrj = await client.get(f"/jobs/{job_id}")
    assert rrj.json()["status"] == "queued"
