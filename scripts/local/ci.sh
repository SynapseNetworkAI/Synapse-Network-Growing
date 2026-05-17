#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OPS_API_BASE="${OPS_API_BASE:-http://127.0.0.1:9700/api}"
PYTHON_BIN="${PYTHON_BIN:-${PYTHON:-}}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "/Users/cliff/workspace/agent/.venv/bin/python" ]]; then
    PYTHON_BIN="/Users/cliff/workspace/agent/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi
BRANCH_NAME="$(git rev-parse --abbrev-ref HEAD)"
COMMIT_SHA="$(git rev-parse HEAD)"
BASE_REF="${OPS_CI_BASE_REF:-origin/main}"
SCOPE="${OPS_CI_SCOPE:-auto}"
ACTOR="${OPS_OPERATOR:-operator}"

payload="$(
  "$PYTHON_BIN" - <<'PY' "$ROOT" "$BRANCH_NAME" "$COMMIT_SHA" "$BASE_REF" "$SCOPE" "$ACTOR"
import json
import sys

repo_path, branch, commit, base_ref, scope, actor = sys.argv[1:]
print(json.dumps({
    "repo_path": repo_path,
    "branch_name": branch,
    "commit_sha": commit,
    "base_ref": base_ref,
    "scope": scope,
    "actor": actor,
}, ensure_ascii=False))
PY
)"

response="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$OPS_API_BASE/ci/runs"
)"
run_id="$("$PYTHON_BIN" - <<'PY' "$response"
import json
import sys

print(json.loads(sys.argv[1])["id"])
PY
)"

echo "[local-ci] created run #${run_id} for ${BRANCH_NAME}@${COMMIT_SHA:0:12}"
PYTHONPATH="$ROOT" "$PYTHON_BIN" "$ROOT/scripts/local/run_ci_worker.py" --once --run-id "$run_id"
