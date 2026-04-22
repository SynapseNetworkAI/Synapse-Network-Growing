#!/usr/bin/env bash
# Install repository-local git hooks for local push quality gates.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

git -C "$ROOT_DIR" config core.hooksPath .githooks
echo "[git-hooks] core.hooksPath set to .githooks"
