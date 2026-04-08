#!/usr/bin/env bash
# Restart the Ops Dashboard backend (local environment)
set -euo pipefail
cd "$(dirname "$0")/.."

export OPS_ENV=local
PORT=${OPS_PORT:-9600}

echo "Stopping existing uvicorn on port $PORT ..."
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
sleep 1

echo "Restarting Ops Dashboard (local) on port $PORT ..."
exec uvicorn server.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --reload \
  --log-level debug
