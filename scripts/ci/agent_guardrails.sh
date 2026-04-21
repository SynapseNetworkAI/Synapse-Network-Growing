#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[agent-guardrails] architecture contracts"
bash "$ROOT_DIR/scripts/ci/code_quality_architecture_scan.sh"

echo "[agent-guardrails] changed-source test evidence"
bash "$ROOT_DIR/scripts/ci/diff_coverage_gate.sh"

echo "[agent-guardrails] docs sync"
bash "$ROOT_DIR/scripts/ci/docs_sync_scan.sh"

echo "[agent-guardrails] git diff hygiene"
git -C "$ROOT_DIR" diff --check

echo "[agent-guardrails] passed"
