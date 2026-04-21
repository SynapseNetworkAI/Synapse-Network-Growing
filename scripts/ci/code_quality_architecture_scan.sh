#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/Users/cliff/workspace/agent/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "[architecture-quality] scanning Growing boundaries and complexity"
"$PYTHON_BIN" "$ROOT_DIR/scripts/ci/code_quality_architecture_scan.py"
