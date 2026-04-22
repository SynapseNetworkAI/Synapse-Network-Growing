#!/usr/bin/env bash
# Resolve a stable diff base for local and CI quality gates.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUALITY_BASE_REF="${QUALITY_BASE_REF:-origin/main}"

cd "$ROOT_DIR"

if git remote get-url origin >/dev/null 2>&1; then
  if ! git fetch --quiet origin main; then
    echo "[diff-base] warning: could not refresh origin/main; using local refs" >&2
  fi
fi

if merge_base="$(git merge-base HEAD "$QUALITY_BASE_REF" 2>/dev/null)"; then
  printf '%s\n' "$merge_base"
  exit 0
fi

cat >&2 <<EOF
FATAL DIFF-BASE-001: could not find merge-base with ${QUALITY_BASE_REF}.
Run 'git fetch origin main' and retry, or set QUALITY_BASE_REF to a reachable base.
EOF
exit 1
