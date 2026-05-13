#!/usr/bin/env bash
# Verify tools expected from GitHub-hosted Ubuntu runner images.

set -euo pipefail

missing=()

if ! command -v rg >/dev/null 2>&1; then
  missing+=("ripgrep/rg")
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "FATAL CI-RUNNER-TOOLS-001: missing expected runner tool(s): ${missing[*]}" >&2
  echo "GitHub-hosted Ubuntu runners should include these tools; check runner image changes before adding apt installs back to PR CI." >&2
  exit 1
fi

rg --version
