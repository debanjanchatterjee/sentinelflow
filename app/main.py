from fastapi import FastAPI, Request
from .api import jobs as jobs_api
from .metrics import metrics_response, request_latency_seconds

app = FastAPI(title="SentinelFlow Control Plane")

app.include_router(jobs_api.router)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start = time.time()
    try:
        response = await call_next(request)
        return response
    finally:
        request_latency_seconds.observe(time.time() - start)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # Could add redis readiness check
    return {"ready": True}


@app.get("/metrics")
async def metrics():
    return metrics_response()
