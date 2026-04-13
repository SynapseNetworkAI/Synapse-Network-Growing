#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_REPO="${TARGET_SYNAPSE_REPO:-$REPO_ROOT/../Synapse-Network}"
GUARD_SCRIPT="$REPO_ROOT/scripts/ci/allow_expensive_branch.sh"

if [[ ! -d "$TARGET_REPO" ]]; then
  echo "[ci:approval-automation] target repo not found at $TARGET_REPO" >&2
  exit 1
fi

if "$GUARD_SCRIPT" "${1:-}"; then
  TARGET_ROOT="$(cd "$TARGET_REPO" && pwd)"
  echo "[ci:approval-automation] branch allowed — running gateway-admin execution worker regression"
  bash "$TARGET_ROOT/scripts/ci/run_pytest_checks.sh" \
    "ci:approval-automation" \
    "$TARGET_ROOT/services/gateway-admin" \
    "tests/test_execution_worker.py"
else
  echo "[ci:approval-automation] branch not in expensive set; skipping automation job"
fi
