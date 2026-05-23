#!/usr/bin/env bash
# Start the Ops Dashboard backend (local environment)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate venv if exists
VENV="${OPS_VENV:-$PROJECT_ROOT/../.venv}"
if [[ -f "$VENV/bin/activate" ]]; then
  source "$VENV/bin/activate"
fi
source "$PROJECT_ROOT/scripts/python_runtime_guard.sh"
require_ops_python_runtime python

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

echo "[$(date '+%H:%M:%S')] Starting Ops Dashboard (local) on port $PORT ..."
echo "[$(date '+%H:%M:%S')] Project root: $PROJECT_ROOT"
echo "[$(date '+%H:%M:%S')] Python: $(which python)"
if [[ -z "${OPS_DATABASE_URL:-}" ]]; then
  echo "[$(date '+%H:%M:%S')] OPS_DATABASE_URL is unset; using local SQLite fallback."
  echo "[$(date '+%H:%M:%S')] Recommended dev DB: docker compose -f docker-compose.postgres.yml up -d postgres"
fi
RELOAD_EXCLUDES=(
  "--reload-exclude" "runtime/*"
  "--reload-exclude" "server/logs/*"
  "--reload-exclude" "server/ops.db*"
  "--reload-exclude" "roles/*/outputs/*"
)
exec uvicorn server.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --reload \
  --log-level debug \
  "${RELOAD_EXCLUDES[@]}"
