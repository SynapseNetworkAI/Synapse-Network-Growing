#!/usr/bin/env bash
# Scoped backend checks for PRs that only touch Python/backend code.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$("$ROOT_DIR/scripts/ci/detect_python.sh")"
DIFF_BASE="${1:-$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")}"
QUALITY_BASE_REF="${QUALITY_BASE_REF:-origin/main}"

cd "$ROOT_DIR"

export OPS_PYTHON="$PYTHON"
export QUALITY_RUN_DASHBOARD=0
export QUALITY_RUN_DEP_AUDIT=0
export QUALITY_RUN_BRANCH_PROTECTION=0
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export CLOUDSDK_PYTHON="$PYTHON"
PYTEST_CMD=(uv run --python "$PYTHON" --with-requirements requirements.txt --isolated python -m pytest)

echo "[ci:backend] static quality gates"
bash "$ROOT_DIR/scripts/ci/code_quality_gates.sh" "$DIFF_BASE"

changed_python_files=()
while IFS= read -r file; do
  [[ -n "$file" ]] && changed_python_files+=("$file")
done < <(
  {
    git diff --name-only "$DIFF_BASE" -- server scripts tests
    git ls-files --others --exclude-standard -- server scripts tests
  } | awk '/\.py$/ { print }' | sort -u
)

if [[ ${#changed_python_files[@]} -eq 0 ]]; then
  echo "[ci:backend] no Python changes; skipping backend pytest"
else
  echo "[ci:backend] pytest with diff coverage"
  if ! command -v uvx >/dev/null 2>&1; then
    echo "FATAL DIFF-COVERAGE-TOOL-001: uvx is required to run diff-cover." >&2
    echo "Install uv/uvx locally or use GitHub Actions, which installs uv before backend_checks." >&2
    exit 1
  fi
  PYTHONPATH=. "${PYTEST_CMD[@]}" -q \
    --cov=server \
    --cov=scripts \
    --cov-report=xml:coverage.xml
  uvx --from diff-cover diff-cover coverage.xml \
    --compare-branch "$QUALITY_BASE_REF" \
    --fail-under=90 \
    --include-untracked \
    --src-roots "$ROOT_DIR"
fi

echo "[ci:backend] whitespace"
git diff --check

echo "[ci:backend] ok"
