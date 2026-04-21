#!/usr/bin/env bash
# Deterministic local guardrails for agent-authored control-plane changes.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OPS_PYTHON="${OPS_PYTHON:-/Users/cliff/workspace/agent/.venv/bin/python}"

cd "$ROOT_DIR"

# shellcheck source=../python_runtime_guard.sh
source "$ROOT_DIR/scripts/python_runtime_guard.sh"
require_ops_python_runtime "$OPS_PYTHON"

echo "[guardrails] python compile"
"$OPS_PYTHON" -m py_compile \
  server/services/workflows/declarative.py \
  server/services/scheduling/recurring_workflows.py \
  server/services/workflows/ci_scheduler.py \
  scripts/ci/ci_runner.py

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
if rg -n "capture_output\\s*=\\s*True" scripts/ci/ci_runner.py; then
  echo "ci_runner.py must stream stdout/stderr to a log file, not capture full output in memory." >&2
  exit 1
fi

if ! rg -n "os\\.replace|replace\\(" scripts/ci/ci_runner.py >/dev/null; then
  echo "ci_runner.py must write exit code markers with an atomic rename." >&2
  exit 1
fi

echo "[guardrails] docs sync markers"
rg -n "awaiting_ci|ci_status_sweep|runtime cap|流式写日志" \
  ARCHITECTURE.md \
  docs/design-docs/declarative-agent-workflow-factory.md \
  docs/design-docs/recurring-workflow-control-plane.md \
  docs/design-docs/system-design-principles.md >/dev/null

echo "[guardrails] whitespace"
git diff --check

echo "[guardrails] ok"
