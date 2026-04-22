#!/usr/bin/env bash
# Print the Python runtime used by local and CI quality gates.

set -euo pipefail

if [[ -n "${PYTHON_BIN:-}" ]]; then
  printf '%s\n' "$PYTHON_BIN"
elif [[ -x "/Users/cliff/workspace/agent/.venv/bin/python" ]]; then
  printf '%s\n' "/Users/cliff/workspace/agent/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  command -v python3
else
  echo "FATAL: python runtime not found. Set PYTHON_BIN or install python3." >&2
  exit 1
fi
