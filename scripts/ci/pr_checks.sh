#!/usr/bin/env bash
# Local push and PR quality gates for Synapse-Network-Growing.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$("$ROOT_DIR/scripts/ci/detect_python.sh")"
DIFF_BASE="$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")"
QUALITY_BASE_REF="${QUALITY_BASE_REF:-origin/main}"
PR_CHECKS_PHASE="${PR_CHECKS_PHASE:-all}"

cd "$ROOT_DIR"

echo "[ci:pr] running Synapse-Network-Growing quality gates"
echo "[ci:pr] python: $PYTHON"
echo "[ci:pr] diff base: $DIFF_BASE"
echo "[ci:pr] phase: $PR_CHECKS_PHASE"

export OPS_PYTHON="$PYTHON"

run_quality_phase() {
  echo "[ci:pr] guardrails"
  bash "$ROOT_DIR/scripts/ci/agent_guardrails.sh"

  echo "[ci:pr] static quality gates"
  bash "$ROOT_DIR/scripts/ci/code_quality_gates.sh" "$DIFF_BASE"

  echo "[ci:pr] whitespace"
  git diff --check
}

run_backend_phase() {
  changed_python_files=()
  while IFS= read -r file; do
    [[ -n "$file" ]] && changed_python_files+=("$file")
  done < <(
    {
      git diff --name-only "$DIFF_BASE" -- server scripts tests
      git ls-files --others --exclude-standard -- server scripts tests
    } | awk '/\.py$/ { print }' | sort -u
  )

  if [[ ${#changed_python_files[@]} -gt 0 ]]; then
    echo "[ci:pr] backend tests with diff coverage for ${#changed_python_files[@]} changed Python file(s)"
    if ! command -v uvx >/dev/null 2>&1; then
      echo "FATAL DIFF-COVERAGE-TOOL-001: uvx is required to run diff-cover." >&2
      echo "Install uv/uvx locally or use GitHub Actions, which installs uv before pr_checks." >&2
      exit 1
    fi
    PYTHONPATH=. "$PYTHON" -m pytest -q \
      --cov=server \
      --cov=scripts \
      --cov-report=xml:coverage.xml
    uvx --from diff-cover diff-cover coverage.xml \
      --compare-branch "$QUALITY_BASE_REF" \
      --fail-under=90 \
      --include-untracked \
      --src-roots "$ROOT_DIR"
  else
    echo "[ci:pr] backend tests"
    PYTHONPATH=. "$PYTHON" -m pytest -q
    echo "[ci:pr] no backend/script/test Python changes; skipping diff coverage"
  fi
}

run_dashboard_phase() {
  echo "[ci:pr] dashboard typecheck"
  (
    cd "$ROOT_DIR/dashboard"
    npm run typecheck
  )

  echo "[ci:pr] dashboard lint"
  (
    cd "$ROOT_DIR/dashboard"
    QUALITY_DIFF_BASE="$DIFF_BASE" npm run lint
  )

  echo "[ci:pr] dashboard tests"
  (
    cd "$ROOT_DIR/dashboard"
    npm test -- --run
  )

  echo "[ci:pr] dashboard build"
  (
    cd "$ROOT_DIR/dashboard"
    npm run build
  )
}

case "$PR_CHECKS_PHASE" in
  all)
    run_quality_phase
    run_backend_phase
    run_dashboard_phase
    ;;
  quality)
    run_quality_phase
    ;;
  backend)
    run_backend_phase
    ;;
  dashboard)
    run_dashboard_phase
    ;;
  *)
    echo "Unsupported PR_CHECKS_PHASE: $PR_CHECKS_PHASE" >&2
    exit 2
    ;;
esac

echo "[ci:pr] ok"
