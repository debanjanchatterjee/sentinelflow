#!/usr/bin/env bash
set -euo pipefail

API_KEY=${API_KEY:-dev-key}
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}

# Run uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
