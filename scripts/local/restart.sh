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
source "$PROJECT_ROOT/scripts/python_runtime_guard.sh"
require_ops_python_runtime python

export OPS_ENV=local
PORT=${OPS_PORT:-9600}

if [[ -z "${OPS_DATABASE_URL:-}" && -f "$PROJECT_ROOT/.env" ]]; then
  OPS_DATABASE_URL="$(grep -E '^OPS_DATABASE_URL=' "$PROJECT_ROOT/.env" | tail -n 1 | cut -d= -f2- || true)"
  export OPS_DATABASE_URL
fi
if [[ -z "${OPS_DATABASE_URL:-}" || "$OPS_DATABASE_URL" != postgresql* ]]; then
  cat >&2 <<'EOF'
OPS_DATABASE_URL must be set to a PostgreSQL DSN before restarting the local Ops Dashboard.
Start docker-compose.postgres.yml and use:
  OPS_DATABASE_URL=postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing_local
SQLite runtime fallback has been removed.
EOF
  exit 2
fi
python - <<'PY'
import os
import sys

from sqlalchemy import create_engine, text

url = os.environ["OPS_DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True)
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception as exc:  # pragma: no cover - shell diagnostic
    print(f"Cannot connect to PostgreSQL OPS_DATABASE_URL: {exc}", file=sys.stderr)
    print("Start docker-compose.postgres.yml and create the configured database before restarting.", file=sys.stderr)
    raise SystemExit(2)
finally:
    engine.dispose()
PY

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
RELOAD_EXCLUDES=(
  "--reload-exclude" "runtime/*"
  "--reload-exclude" "server/logs/*"
  "--reload-exclude" "roles/*/outputs/*"
)
exec uvicorn server.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --reload \
  --log-level debug \
  "${RELOAD_EXCLUDES[@]}"
