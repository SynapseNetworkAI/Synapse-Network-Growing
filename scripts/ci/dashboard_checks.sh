#!/usr/bin/env bash
# Scoped dashboard checks for PRs that touch the Ops Console frontend.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$("$ROOT_DIR/scripts/ci/detect_python.sh")"
DIFF_BASE="${1:-$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")}"

cd "$ROOT_DIR"

export OPS_PYTHON="$PYTHON"
export QUALITY_RUN_DEP_AUDIT=0
export QUALITY_RUN_BRANCH_PROTECTION=0

echo "[ci:dashboard] static quality gates"
bash "$ROOT_DIR/scripts/ci/code_quality_gates.sh" "$DIFF_BASE"

echo "[ci:dashboard] tests"
(
  cd "$ROOT_DIR/dashboard"
  npm test -- --run
)

echo "[ci:dashboard] build"
(
  cd "$ROOT_DIR/dashboard"
  npm run build
)

echo "[ci:dashboard] whitespace"
git diff --check

echo "[ci:dashboard] ok"
