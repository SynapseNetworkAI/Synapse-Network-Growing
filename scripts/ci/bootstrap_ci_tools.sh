#!/usr/bin/env bash
# Bootstrap pinned lightweight CI tools without apt-get runner tax.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RIPGREP_VERSION="${RIPGREP_VERSION:-15.1.0}"
TOOL_DIR="$ROOT_DIR/.ci-tools/ripgrep/$RIPGREP_VERSION"
RG_BIN="$TOOL_DIR/rg"

add_tool_path() {
  if [[ -n "${GITHUB_PATH:-}" ]]; then
    echo "$TOOL_DIR" >>"$GITHUB_PATH"
  fi
  export PATH="$TOOL_DIR:$PATH"
}

if [[ -x "$RG_BIN" ]]; then
  echo "Using cached ripgrep $RIPGREP_VERSION from $RG_BIN"
  add_tool_path
  rg --version
  exit 0
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64 | Linux-amd64)
    RIPGREP_TARGET="x86_64-unknown-linux-musl"
    ;;
  *)
    if command -v rg >/dev/null 2>&1; then
      echo "Using local system ripgrep on non-Linux runner: $(uname -s) $(uname -m)"
      rg --version
      exit 0
    fi
    echo "FATAL CI-RUNNER-TOOLS-001: unsupported runner for pinned ripgrep bootstrap and no local rg found: $(uname -s) $(uname -m)" >&2
    exit 1
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "FATAL CI-RUNNER-TOOLS-002: curl is required to bootstrap ripgrep." >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "FATAL CI-RUNNER-TOOLS-003: tar is required to bootstrap ripgrep." >&2
  exit 1
fi

ARCHIVE="ripgrep-$RIPGREP_VERSION-$RIPGREP_TARGET.tar.gz"
URL="https://github.com/BurntSushi/ripgrep/releases/download/$RIPGREP_VERSION/$ARCHIVE"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TOOL_DIR"
echo "Downloading ripgrep $RIPGREP_VERSION for $RIPGREP_TARGET"
curl -fsSL "$URL" -o "$TMP_DIR/$ARCHIVE"
tar -xzf "$TMP_DIR/$ARCHIVE" -C "$TMP_DIR"

RG_EXTRACTED="$(find "$TMP_DIR" -type f -name rg | head -n 1)"
if [[ -z "$RG_EXTRACTED" ]]; then
  echo "FATAL CI-RUNNER-TOOLS-004: ripgrep archive did not contain rg binary." >&2
  exit 1
fi

install -m 0755 "$RG_EXTRACTED" "$RG_BIN"
add_tool_path
rg --version
