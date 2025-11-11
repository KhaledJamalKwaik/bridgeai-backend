#!/usr/bin/env bash
set -euo pipefail
LOG=/tmp/uvicorn_dev.log
echo "Starting uvicorn dev server (reload) logging to $LOG"
nohup uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > "$LOG" 2>&1 &
echo $!
