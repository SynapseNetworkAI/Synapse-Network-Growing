#!/usr/bin/env bash
# Local scoped PR gate. Use --scope full for the canonical full gate.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$("$ROOT_DIR/scripts/ci/detect_python.sh")"
SCOPE="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --scope=*)
      SCOPE="${1#*=}"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

if [[ "${SYNAPSE_CI_SCOPE:-}" == "full" ]]; then
  SCOPE="full"
fi

if [[ "$SCOPE" == "full" ]]; then
  echo "[ci:local] full scope requested"
  exec bash "$ROOT_DIR/scripts/ci/pr_checks.sh"
fi

if [[ "$SCOPE" != "auto" ]]; then
  echo "Unsupported scope: $SCOPE" >&2
  exit 2
fi

DIFF_BASE="$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")"
SCOPE_JSON="$(mktemp)"
"$PYTHON" "$ROOT_DIR/scripts/ci/ci_scope.py" --base "$DIFF_BASE" --json "$SCOPE_JSON"

run_full="$("$PYTHON" -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["run_full"]).lower())' "$SCOPE_JSON")"
run_backend="$("$PYTHON" -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["run_backend"]).lower())' "$SCOPE_JSON")"
run_dashboard="$("$PYTHON" -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["run_dashboard"]).lower())' "$SCOPE_JSON")"
scope_name="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["scope"])' "$SCOPE_JSON")"
backend_mode="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("backend_mode", "targeted"))' "$SCOPE_JSON")"

echo "[ci:local] scope: $scope_name"

if [[ "$run_full" == "true" ]]; then
  echo "[ci:local] full gate required by changed files"
  exec bash "$ROOT_DIR/scripts/ci/pr_checks.sh"
fi

echo "[ci:local] guardrails"
bash "$ROOT_DIR/scripts/ci/agent_guardrails.sh"

if [[ "$run_backend" == "true" ]]; then
  BACKEND_CHECK_MODE="$backend_mode" bash "$ROOT_DIR/scripts/ci/backend_checks.sh" "$DIFF_BASE"
fi

if [[ "$run_dashboard" == "true" ]]; then
  bash "$ROOT_DIR/scripts/ci/dashboard_checks.sh" "$DIFF_BASE"
fi

echo "[ci:local] whitespace"
git diff --check

echo "[ci:local] ok"
