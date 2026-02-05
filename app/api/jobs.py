import time
import uuid
import os
from fastapi import APIRouter, Depends, HTTPException
from ..schemas import JobCreate, JobResponse
from .. import redis_helper
from .. import metrics
from ..auth import require_api_key

router = APIRouter()


@router.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate, authorized: bool = Depends(require_api_key)):
    redis_client = await redis_helper.get_redis()
    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "type": job.type,
        "payload": job.payload,
        "status": "queued",
        "idempotency_key": job.idempotency_key,
        "attempts": 0,
        "max_retries": job.max_retries,
        "created_at": time.time(),
    }
    start = time.time()
    try:
        if job.schedule_at:
            # schedule for future — mark scheduled status
            payload["status"] = "scheduled"
            await redis_helper.schedule_job(redis_client, job_id, payload, job.schedule_at)
        else:
            await redis_helper.enqueue_job(redis_client, job_id, payload)
            metrics.jobs_enqueued_total.inc()
        metrics.jobs_submitted_total.inc()
    except Exception as exc:
        metrics.error_count.inc()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        metrics.enqueue_latency_seconds.observe(time.time() - start)

    return JobResponse(job_id=job_id, status=payload["status"], payload=payload["payload"])


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    redis_client = await redis_helper.get_redis()
    data = await redis_helper.get_job(redis_client, job_id)
    if not data:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(job_id=job_id, status=data.get("status"), payload=data.get("payload"))


@router.get("/jobs")
async def list_jobs():
    redis_client = await redis_helper.get_redis()
    all_jobs = await redis_helper.list_jobs(redis_client)
    return {"jobs": all_jobs}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, authorized: bool = Depends(require_api_key)):
    redis_client = await redis_helper.get_redis()
    data = await redis_helper.get_job(redis_client, job_id)
    if not data:
        raise HTTPException(status_code=404, detail="job not found")
    data["status"] = "queued"
    data["attempts"] = 0
    await redis_helper.set_job(redis_client, job_id, data)
    await redis_helper.enqueue_job(redis_client, job_id, data)
    metrics.jobs_enqueued_total.inc()
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, authorized: bool = Depends(require_api_key)):
    redis_client = await redis_helper.get_redis()
    data = await redis_helper.get_job(redis_client, job_id)
    if not data:
        raise HTTPException(status_code=404, detail="job not found")
    data["status"] = "cancelled"
    await redis_helper.set_job(redis_client, job_id, data)
    return {"ok": True}
