#!/usr/bin/env bash
# Resolve changed dashboard files and run dependency-light frontend lint.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OPS_PYTHON="${OPS_PYTHON:-$(bash "$ROOT_DIR/scripts/ci/detect_python.sh")}"
BASE="${QUALITY_DIFF_BASE:-}"
if [[ -z "$BASE" ]]; then
  BASE="$("$ROOT_DIR/scripts/ci/resolve_diff_base.sh")"
fi

"$OPS_PYTHON" "$ROOT_DIR/scripts/ci/dashboard_lint.py" --base "$BASE"
