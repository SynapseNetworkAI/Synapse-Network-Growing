#!/usr/bin/env bash
# Static quality gates that complement tests/build/coverage.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIFF_BASE="${1:-}"
OPS_PYTHON="${OPS_PYTHON:-$(bash "$ROOT_DIR/scripts/ci/detect_python.sh")}"
QUALITY_RUN_DASHBOARD="${QUALITY_RUN_DASHBOARD:-1}"
QUALITY_RUN_DEP_AUDIT="${QUALITY_RUN_DEP_AUDIT:-1}"
QUALITY_RUN_BRANCH_PROTECTION="${QUALITY_RUN_BRANCH_PROTECTION:-1}"

if [[ -z "$DIFF_BASE" ]]; then
  DIFF_BASE="$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")"
fi

cd "$ROOT_DIR"

echo "[quality] static size/function ratchet"
"$OPS_PYTHON" "$ROOT_DIR/scripts/ci/static_quality_gate.py" --base "$DIFF_BASE"

# Enforce typed public service returns separately from size/complexity ratchets.
# Raw maps remain allowed for private serializers and payload/metadata fields.
echo "[quality] public object return contracts"
"$OPS_PYTHON" "$ROOT_DIR/scripts/ci/source_quality_checks.py" --base "$DIFF_BASE"

declare -a changed_files=()
while IFS= read -r file; do
  [[ -n "$file" ]] && changed_files+=("$file")
done < <("$OPS_PYTHON" "$ROOT_DIR/scripts/ci/static_quality_gate.py" --base "$DIFF_BASE" --print-changed)

declare -a changed_python=()
declare -a new_python=()
declare -a new_runtime_python=()
declare -a changed_dashboard=()
for file in "${changed_files[@]+"${changed_files[@]}"}"; do
  case "$file" in
    *.py)
      changed_python+=("$file")
      if git diff --name-status "$DIFF_BASE" -- "$file" | awk '$1 == "A" { found=1 } END { exit found ? 0 : 1 }'; then
        new_python+=("$file")
      elif ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
        new_python+=("$file")
      fi
      case "$file" in
        tests/*)
          ;;
        *)
          if git diff --name-status "$DIFF_BASE" -- "$file" | awk '$1 == "A" { found=1 } END { exit found ? 0 : 1 }'; then
            new_runtime_python+=("$file")
          elif ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
            new_runtime_python+=("$file")
          fi
          ;;
      esac
      ;;
    dashboard/src/*.ts|dashboard/src/*.tsx|dashboard/src/**/*.ts|dashboard/src/**/*.tsx)
      changed_dashboard+=("$file")
      ;;
  esac
done

echo "[quality] python lint"
if [[ ${#changed_python[@]} -gt 0 ]]; then
  uvx ruff check --select F401,F541,F821,F841 "${changed_python[@]}"
else
  echo "[quality] no changed Python files; skipping changed-file ruff"
fi

echo "[quality] python format ratchet"
if [[ ${#new_python[@]} -gt 0 ]]; then
  uvx ruff format --check "${new_python[@]}"
else
  echo "[quality] no new Python files; legacy formatting is tracked separately"
fi

echo "[quality] python complexity ratchet"
if [[ ${#new_runtime_python[@]} -gt 0 ]]; then
  uvx xenon --max-absolute B --max-modules B --max-average A "${new_runtime_python[@]}"
else
  echo "[quality] no new runtime Python files; legacy/test complexity is protected by size/function ratchet"
fi

if [[ "$QUALITY_RUN_DASHBOARD" == "1" ]]; then
  echo "[quality] dashboard typecheck"
  npm --prefix dashboard run typecheck

  echo "[quality] dashboard lint"
  QUALITY_DIFF_BASE="$DIFF_BASE" npm --prefix dashboard run lint
else
  echo "[quality] dashboard checks disabled for scoped backend run"
fi

echo "[quality] duplicate code ratchet"
"$OPS_PYTHON" "$ROOT_DIR/scripts/ci/duplicate_code_gate.py" --base "$DIFF_BASE"

echo "[quality] secret scan"
if [[ -f "$ROOT_DIR/.secrets.baseline" ]]; then
  uvx detect-secrets scan --baseline "$ROOT_DIR/.secrets.baseline" >/tmp/synapse_detect_secrets_scan.json
else
  echo "[quality] .secrets.baseline missing; running changed-file entropy/token scan"
  "$OPS_PYTHON" "$ROOT_DIR/scripts/ci/secret_diff_scan.py" --base "$DIFF_BASE"
fi

echo "[quality] python security lint"
if [[ ${#new_python[@]} -gt 0 ]]; then
  uvx bandit -q -r "${new_python[@]}" -x tests
else
  echo "[quality] no new Python files; legacy security debt is tracked separately"
fi

if [[ "$QUALITY_RUN_DEP_AUDIT" == "1" ]]; then
  echo "[quality] python dependency audit"
  uvx pip-audit --no-deps --disable-pip -r requirements.txt

  if [[ -f "$ROOT_DIR/dashboard/yarn.lock" ]]; then
    echo "[quality] dashboard dependency audit"
    "$OPS_PYTHON" "$ROOT_DIR/scripts/ci/yarn_audit_gate.py"
  fi
else
  echo "[quality] dependency audits disabled for scoped PR run"
fi

if [[ "$QUALITY_RUN_BRANCH_PROTECTION" == "1" ]]; then
  echo "[quality] branch protection diagnostic"
  bash "$ROOT_DIR/scripts/ci/check_branch_protection.sh"
else
  echo "[quality] branch protection diagnostic disabled for scoped PR run"
fi

echo "[quality] ok"
