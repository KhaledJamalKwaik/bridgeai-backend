#!/usr/bin/env bash
set -euo pipefail
echo "Stopping processes matching 'uvicorn app.main:app' or gunicorn"
pkill -f 'uvicorn app.main:app' || true
pkill -f 'gunicorn' || true
sleep 1
echo "Remaining listeners on :8000:"
lsof -iTCP:8000 -sTCP:LISTEN -Pn || echo "none"
