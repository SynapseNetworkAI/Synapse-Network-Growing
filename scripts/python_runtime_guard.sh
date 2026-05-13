#!/usr/bin/env bash
# Shared Python runtime guard for Ops Dashboard scripts.

require_ops_python_runtime() {
  local required_major="${OPS_REQUIRED_PYTHON_MAJOR:-3}"
  local required_minor="${OPS_REQUIRED_PYTHON_MINOR:-12}"
  local probe_timeout="${PYTHON_RUNTIME_PROBE_TIMEOUT_SEC:-2}"
  local python_bin="${1:-python}"

  if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "Ops Dashboard requires Python ${required_major}.${required_minor}+ but '$python_bin' was not found." >&2
    echo "Set PYTHON_BIN or recreate OPS_VENV with Python ${required_major}.${required_minor}+ and retry." >&2
    return 1
  fi

  local probe_file output_file pid elapsed exit_code output
  probe_file="$(mktemp -t synapse-python-guard)"
  output_file="$(mktemp -t synapse-python-guard)"
  cat >"$probe_file" <<'PY'
import sys
import json
import pathlib
import subprocess

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
subprocess.run([sys.executable, "--version"], check=True, capture_output=True, text=True)
print("python-runtime-ok")
PY
  "$python_bin" "$probe_file" "$required_major" "$required_minor" >"$output_file" 2>/dev/null &
  pid="$!"

  elapsed=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( elapsed >= probe_timeout )); then
      kill -9 "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
      rm -f "$probe_file" "$output_file"
      echo "Ops Dashboard Python runtime probe timed out for '$python_bin'." >&2
      echo "Set PYTHON_BIN to a healthy Python ${required_major}.${required_minor}+ runtime and retry." >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if wait "$pid" >/dev/null 2>&1; then
    exit_code="0"
  else
    exit_code="$?"
  fi

  output="$(cat "$output_file" 2>/dev/null || true)"
  rm -f "$probe_file" "$output_file"
  if [[ "$exit_code" != "0" || "$output" != "python-runtime-ok" ]]; then
    echo "Ops Dashboard Python runtime probe failed for '$python_bin'." >&2
    return 1
  fi
}
