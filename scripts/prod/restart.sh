#!/usr/bin/env bash
# Restart the Ops Dashboard backend (prod environment)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate venv if exists
VENV="${OPS_VENV:-$PROJECT_ROOT/../.venv}"
if [[ -f "$VENV/bin/activate" ]]; then
  source "$VENV/bin/activate"
fi

export OPS_ENV=prod
PORT=${OPS_PORT:-9600}
WORKERS=${OPS_WORKERS:-4}

if [[ "${OPS_PRESERVE_RUNTIME_ENV:-0}" != "1" ]]; then
  for key in ORCHESTRATION_BACKEND LLM_PROVIDER LLM_EXECUTION_MODE COPILOT_SDK_MODEL; do
    if [[ -n "${!key:-}" ]]; then
      echo "[$(date '+%H:%M:%S')] Clearing inherited $key so backend selection falls back to repo config (.env)."
      unset "$key"
    fi
  done
fi

echo "[$(date '+%H:%M:%S')] Stopping existing uvicorn on port $PORT ..."
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
sleep 1

echo "[$(date '+%H:%M:%S')] Restarting Ops Dashboard (prod) on port $PORT with $WORKERS workers ..."
exec uvicorn server.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --log-level info
