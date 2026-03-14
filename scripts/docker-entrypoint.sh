#!/bin/bash
set -e

# Start Redis in background (data in /app/.redis, runs as appuser)
mkdir -p /app/.redis
redis-server --daemonize yes --dir /app/.redis

# Run FastAPI as main process (replace shell so signals propagate)
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
