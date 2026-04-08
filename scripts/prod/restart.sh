#!/usr/bin/env bash
# Restart the Ops Dashboard backend (prod environment)
set -euo pipefail
cd "$(dirname "$0")/.."

export OPS_ENV=prod
PORT=${OPS_PORT:-9600}
WORKERS=${OPS_WORKERS:-4}

echo "Stopping existing uvicorn on port $PORT ..."
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
sleep 1

echo "Restarting Ops Dashboard (prod) on port $PORT with $WORKERS workers ..."
exec uvicorn server.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --log-level info
