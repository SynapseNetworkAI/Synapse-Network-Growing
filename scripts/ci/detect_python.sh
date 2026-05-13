#!/usr/bin/env bash
# Print the healthy Python runtime used by local and CI quality gates.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
PROBE_TIMEOUT_SEC="${PYTHON_RUNTIME_PROBE_TIMEOUT_SEC:-2}"
REQUIRED_MAJOR="${OPS_REQUIRED_PYTHON_MAJOR:-3}"
REQUIRED_MINOR="${OPS_REQUIRED_PYTHON_MINOR:-12}"

probe_python() {
  local python_bin="$1"
  [[ -n "$python_bin" && -x "$python_bin" ]] || return 1

  local probe_file output_file pid elapsed exit_code output
  probe_file="$(mktemp -t synapse-python-probe)"
  output_file="$(mktemp -t synapse-python-probe)"
  cat >"$probe_file" <<'PY'
import sys
import json
import pathlib
import subprocess

required_major = int(sys.argv[1])
required_minor = int(sys.argv[2])
if sys.version_info[:2] < (required_major, required_minor):
    raise SystemExit(42)
subprocess.run([sys.executable, "--version"], check=True, capture_output=True, text=True)
print("python-runtime-ok")
PY

  "$python_bin" "$probe_file" "$REQUIRED_MAJOR" "$REQUIRED_MINOR" >"$output_file" 2>/dev/null &
  pid="$!"

  elapsed=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( elapsed >= PROBE_TIMEOUT_SEC )); then
      kill -9 "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
      rm -f "$probe_file" "$output_file"
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
  [[ "$exit_code" == "0" && "$output" == "python-runtime-ok" ]]
}

declare -a candidates=()
[[ -n "${PYTHON_BIN:-}" ]] && candidates+=("$PYTHON_BIN")
[[ -n "${OPS_PYTHON:-}" ]] && candidates+=("$OPS_PYTHON")
candidates+=(
  "$ROOT_DIR/.venv/bin/python"
  "/Users/cliff/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  "/Users/cliff/workspace/agent/.venv/bin/python"
  "/opt/homebrew/opt/python@3.14/bin/python3.14"
  "/opt/homebrew/opt/python@3.13/bin/python3.13"
  "/opt/homebrew/opt/python@3.12/bin/python3.12"
  "/opt/homebrew/opt/python@3.11/bin/python3.11"
  "/usr/bin/python3"
)
if command -v python3 >/dev/null 2>&1; then
  candidates+=("$(command -v python3)")
fi

seen_paths="|"
for python_bin in "${candidates[@]}"; do
  [[ -n "$python_bin" ]] || continue
  case "$seen_paths" in
    *"|$python_bin|"*) continue ;;
  esac
  seen_paths="${seen_paths}${python_bin}|"
  if probe_python "$python_bin"; then
    printf '%s\n' "$python_bin"
    exit 0
  fi
  echo "[detect_python] skipping unhealthy Python runtime: $python_bin" >&2
done

echo "FATAL: healthy Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ runtime not found." >&2
echo "Set PYTHON_BIN to a runtime that can execute a .py file, or repair the local Python installation." >&2
exit 1
