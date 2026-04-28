#!/usr/bin/env bash
# Resolve changed dashboard files and run dependency-light frontend lint.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="${QUALITY_DIFF_BASE:-}"
if [[ -z "$BASE" ]]; then
  BASE="$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")"
fi

python3 "$ROOT_DIR/scripts/ci/dashboard_lint.py" --base "$BASE"
