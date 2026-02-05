from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry
from prometheus_client import multiprocess
from starlette.responses import Response

# Keep metrics module-level singletons
jobs_submitted_total = Counter("jobs_submitted_total", "Total jobs submitted via API")
jobs_enqueued_total = Counter("jobs_enqueued_total", "Jobs enqueued into ready queue")
error_count = Counter("error_count", "Total errors encountered by the control plane")
enqueue_latency_seconds = Histogram("enqueue_latency_seconds", "Time to enqueue a job")
request_latency_seconds = Histogram("request_latency_seconds", "HTTP request latency seconds")
active_background_tasks = Gauge("active_background_tasks", "Number of active background tasks")

# Worker / execution metrics
jobs_executed_total = Counter("jobs_executed_total", "Total jobs executed by workers")
execution_latency_seconds = Histogram("execution_latency_seconds", "Job execution latency seconds")


def metrics_response():
    # Return prometheus metrics as a Response
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
