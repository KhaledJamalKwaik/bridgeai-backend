#!/usr/bin/env bash
# Start production server using gunicorn with Uvicorn workers.
# Keeps the server running (process manager recommended for real deployment).

set -euo pipefail

APP_MODULE="app.main:app"
BIND="127.0.0.1:8000"
WORKERS=${WORKERS:-4}
LOG_FILE="/tmp/bridgeai_gunicorn.log"

echo "Starting gunicorn with $WORKERS workers, logging to $LOG_FILE"
nohup gunicorn -k uvicorn.workers.UvicornWorker "$APP_MODULE" -w "$WORKERS" -b "$BIND" --access-logfile - --error-logfile - > "$LOG_FILE" 2>&1 &
echo $!
