#!/usr/bin/env bash
# Read-only branch protection diagnostic. Private repos may not support
# enforcement without GitHub Pro or a public repository.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if ! command -v gh >/dev/null 2>&1; then
  echo "[branch-protection] gh not available; skipping read-only diagnostic"
  exit 0
fi

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
if [[ -z "$repo" ]]; then
  echo "[branch-protection] repository not available to gh; skipping read-only diagnostic"
  exit 0
fi

tmp="$(mktemp)"
status=0
if ! gh api "repos/$repo/branches/main/protection" >"$tmp" 2>"$tmp.err"; then
  status=$?
fi

if [[ $status -ne 0 ]]; then
  message="$(cat "$tmp.err" "$tmp" 2>/dev/null || true)"
  if grep -qiE "GitHub Pro|private repos|protected branches|403|Resource not accessible" <<<"$message"; then
    echo "[branch-protection] diagnostic: private repo plan does not expose branch protection enforcement through this token/plan."
    echo "[branch-protection] keep pre-push + PR CI active; enable GitHub Pro or public repo to require pr-checks."
    rm -f "$tmp" "$tmp.err"
    exit 0
  fi
  echo "[branch-protection] warning: could not read branch protection: ${message}" >&2
  rm -f "$tmp" "$tmp.err"
  exit 0
fi

if ! grep -q "required_status_checks" "$tmp"; then
  echo "[branch-protection] diagnostic: main protection is readable but missing required_status_checks."
  echo "[branch-protection] required checks cannot be assumed enforced; keep pre-push + PR CI active."
  rm -f "$tmp" "$tmp.err"
  exit 0
fi

echo "[branch-protection] readable protection configured for $repo main"
rm -f "$tmp" "$tmp.err"
