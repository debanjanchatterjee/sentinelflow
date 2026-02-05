from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class JobCreate(BaseModel):
    type: str
    payload: Dict[str, Any]
    idempotency_key: Optional[str] = None
    max_retries: int = Field(default=3, ge=0)
    schedule_at: Optional[float] = None  # epoch seconds; if set, job will be scheduled


class JobResponse(BaseModel):
    job_id: str
    status: str
    payload: Dict[str, Any]


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
