#!/usr/bin/env bash
# Shared Python runtime guard for Ops Dashboard scripts.

require_ops_python_runtime() {
  local required_major="${OPS_REQUIRED_PYTHON_MAJOR:-3}"
  local required_minor="${OPS_REQUIRED_PYTHON_MINOR:-12}"
  local python_bin="${1:-python}"

  if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "Ops Dashboard requires Python ${required_major}.${required_minor}+ but '$python_bin' was not found." >&2
    echo "Set PYTHON_BIN or recreate OPS_VENV with Python ${required_major}.${required_minor}+ and retry." >&2
    return 1
  fi

  if ! "$python_bin" - "$required_major" "$required_minor" <<'PY'
import sys

required_major = int(sys.argv[1])
required_minor = int(sys.argv[2])
if sys.version_info[:2] < (required_major, required_minor):
    print(
        f"Ops Dashboard requires Python {required_major}.{required_minor}+ because "
        "the control plane depends on modern typing/runtime behavior.",
        file=sys.stderr,
    )
    print(f"Current Python: {sys.version.split()[0]}", file=sys.stderr)
    print(f"Set PYTHON_BIN or recreate OPS_VENV with Python {required_major}.{required_minor}+ and retry.", file=sys.stderr)
    raise SystemExit(1)
PY
  then
    return 1
  fi
}
