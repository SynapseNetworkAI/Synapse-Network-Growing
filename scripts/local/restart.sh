#!/usr/bin/env bash
# Restart the Ops Dashboard backend (local environment)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate venv if exists
VENV="${OPS_VENV:-$PROJECT_ROOT/../.venv}"
if [[ -f "$VENV/bin/activate" ]]; then
  source "$VENV/bin/activate"
fi

export OPS_ENV=local
PORT=${OPS_PORT:-9600}

if [[ "${OPS_PRESERVE_RUNTIME_ENV:-0}" != "1" ]]; then
  for key in ORCHESTRATION_BACKEND LLM_PROVIDER LLM_MODEL LLM_EXECUTION_MODE COPILOT_SDK_MODEL CODEX_CLI_MODEL; do
    if [[ -n "${!key:-}" ]]; then
      echo "[$(date '+%H:%M:%S')] Clearing inherited $key so backend selection falls back to repo config (.env)."
      unset "$key"
    fi
  done
fi

echo "[$(date '+%H:%M:%S')] Stopping existing uvicorn on port $PORT ..."
EXISTING_PIDS="$(lsof -ti:"$PORT" 2>/dev/null || true)"
if [[ -n "$EXISTING_PIDS" ]]; then
  # `xargs kill` exits non-zero on macOS when stdin is empty; guard it explicitly.
  echo "$EXISTING_PIDS" | xargs kill -9 2>/dev/null || true
fi
sleep 1

echo "[$(date '+%H:%M:%S')] Restarting Ops Dashboard (local) on port $PORT ..."
echo "[$(date '+%H:%M:%S')] Project root: $PROJECT_ROOT"
echo "[$(date '+%H:%M:%S')] Python: $(which python)"
exec uvicorn server.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --reload \
  --log-level debug
