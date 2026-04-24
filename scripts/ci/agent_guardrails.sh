#!/usr/bin/env bash
# Deterministic local guardrails for agent-authored control-plane changes.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OPS_PYTHON="${OPS_PYTHON:-$("$ROOT_DIR/scripts/ci/detect_python.sh")}"

cd "$ROOT_DIR"

search_text() {
  if command -v rg >/dev/null 2>&1; then
    rg -n "$@"
  else
    grep -nE "$@"
  fi
}

# shellcheck source=../python_runtime_guard.sh
source "$ROOT_DIR/scripts/python_runtime_guard.sh"
require_ops_python_runtime "$OPS_PYTHON"

echo "[guardrails] python compile"
"$OPS_PYTHON" -m py_compile \
  server/services/workflows/declarative.py \
  server/services/scheduling/recurring_workflows.py \
  server/services/workflows/ci_scheduler.py \
  scripts/ci/ci_runner.py
"$OPS_PYTHON" -m compileall -q server scripts

echo "[guardrails] architecture import boundaries"
"$OPS_PYTHON" - <<'PY'
from pathlib import Path

violations: list[str] = []
for path in Path("server/services").rglob("*.py"):
    text = path.read_text(encoding="utf-8", errors="replace")
    if "server.routers" in text or "from server import routers" in text:
        violations.append(str(path))

if violations:
    print("server/services must not import server/routers:")
    for violation in violations:
        print(f" - {violation}")
    raise SystemExit(1)
PY

echo "[guardrails] CI runner streaming contract"
if search_text "capture_output\\s*=\\s*True" scripts/ci/ci_runner.py; then
  echo "ci_runner.py must stream stdout/stderr to a log file, not capture full output in memory." >&2
  exit 1
fi

if ! search_text "os\\.replace|replace\\(" scripts/ci/ci_runner.py >/dev/null; then
  echo "ci_runner.py must write exit code markers with an atomic rename." >&2
  exit 1
fi

echo "[guardrails] docs sync markers"
search_text "awaiting_ci|ci_status_sweep|runtime cap|流式写日志" \
  ARCHITECTURE.md \
  docs/design-docs/declarative-agent-workflow-factory.md \
  docs/design-docs/recurring-workflow-control-plane.md \
  docs/design-docs/system-design-principles.md >/dev/null
search_text "Acceptance Matrix Is Executable Contract|liveness diagnostic only|required_db_lineage.*informational|workflow_run_id" \
  ARCHITECTURE.md \
  docs/design-docs/system-design-principles.md \
  docs/design-docs/current-feature-inventory.md >/dev/null

echo "[guardrails] whitespace"
git diff --check

echo "[guardrails] ok"
