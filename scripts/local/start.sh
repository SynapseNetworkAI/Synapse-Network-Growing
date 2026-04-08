#!/usr/bin/env bash
# Start the Ops Dashboard backend (local environment)
set -euo pipefail
cd "$(dirname "$0")/.."

export OPS_ENV=local

echo "Starting Ops Dashboard (local) on port 9600 ..."
exec uvicorn server.main:app \
  --host 127.0.0.1 \
  --port 9600 \
  --reload \
  --log-level debug
