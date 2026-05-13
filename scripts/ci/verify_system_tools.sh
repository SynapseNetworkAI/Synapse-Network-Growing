#!/usr/bin/env bash
# Verify lightweight system tools, installing only when the runner image lacks them.

set -euo pipefail

if ! command -v rg >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "ripgrep/rg missing from runner image; installing ripgrep as a conditional fallback." >&2
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends ripgrep
  else
    echo "FATAL CI-RUNNER-TOOLS-001: missing ripgrep/rg and no apt-get fallback is available." >&2
    exit 1
  fi
fi

rg --version
