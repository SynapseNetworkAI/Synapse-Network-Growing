#!/usr/bin/env bash

set -euo pipefail

# Optional branch argument lets callers override inference during tests.
EXPLICIT_BRANCH="${1:-}"
if [[ -n "$EXPLICIT_BRANCH" ]]; then
  BRANCH="$EXPLICIT_BRANCH"
else
  BRANCH="${CI_BRANCH:-${GITHUB_REF_NAME:-${BRANCH_NAME:-}}}"
  if [[ -z "$BRANCH" && -n "${GITHUB_REF:-}" ]]; then
    BRANCH="${GITHUB_REF#refs/heads/}"
  fi
fi

if [[ -n "${CI_FORCE_EXPENSIVE_BRANCH:-}" ]]; then
  echo "[ci:expensive-branch] override detected (CI_FORCE_EXPENSIVE_BRANCH); forcing expensive branch mode"
  exit 0
fi

read -r -a DEFAULT_PATTERNS <<<"${CI_EXPENSIVE_BRANCH_PATTERNS:-main release/* hotfix/*}"

if [[ -z "$BRANCH" ]]; then
  echo "[ci:expensive-branch] unable to determine branch; treating as non-expensive"
  exit 1
fi

for pattern in "${DEFAULT_PATTERNS[@]}"; do
  if [[ "$BRANCH" == $pattern ]]; then
    echo "[ci:expensive-branch] branch '$BRANCH' matches pattern '$pattern'"
    exit 0
  fi
done

echo "[ci:expensive-branch] branch '$BRANCH' is not in expensive set (${DEFAULT_PATTERNS[*]}); skipping"
exit 1
