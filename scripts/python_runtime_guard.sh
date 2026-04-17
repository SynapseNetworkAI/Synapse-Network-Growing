#!/usr/bin/env bash
# Shared Python runtime guard for Ops Dashboard scripts.

require_ops_python_runtime() {
  local required_major="${OPS_REQUIRED_PYTHON_MAJOR:-3}"
  local required_minor="${OPS_REQUIRED_PYTHON_MINOR:-14}"
  local python_bin="${1:-python}"

  if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "Ops Dashboard requires Python ${required_major}.${required_minor}+ but '$python_bin' was not found." >&2
    echo "Recreate OPS_VENV with /opt/homebrew/bin/python3.14 and retry." >&2
    return 1
  fi

  if ! "$python_bin" - "$required_major" "$required_minor" <<'PY'
import sys

required_major = int(sys.argv[1])
required_minor = int(sys.argv[2])
if sys.version_info[:2] < (required_major, required_minor):
    print(
        f"Ops Dashboard requires Python {required_major}.{required_minor}+ because "
        "Pydantic evaluates PEP 604 type annotations.",
        file=sys.stderr,
    )
    print(f"Current Python: {sys.version.split()[0]}", file=sys.stderr)
    print("Recreate OPS_VENV with /opt/homebrew/bin/python3.14 and retry.", file=sys.stderr)
    raise SystemExit(1)
PY
  then
    return 1
  fi
}
