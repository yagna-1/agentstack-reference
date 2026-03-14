#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPS_DIR="$ROOT_DIR/deps"
mkdir -p "$DEPS_DIR"

clone_or_update() {
  local repo_url="$1"
  local dir_name="$2"
  local target="$DEPS_DIR/$dir_name"

  if [[ -d "$target/.git" ]]; then
    echo "[bootstrap] updating $dir_name"
    git -C "$target" fetch --all --prune
    git -C "$target" pull --ff-only
  else
    echo "[bootstrap] cloning $dir_name"
    git clone --depth=1 "$repo_url" "$target"
  fi
}

clone_or_update https://github.com/yagna-1/nexusgate.git nexusgate
clone_or_update https://github.com/yagna-1/fluxroute.git fluxroute
clone_or_update https://github.com/yagna-1/recast.git recast
clone_or_update https://github.com/yagna-1/mcp-test.git mcp-test
clone_or_update https://github.com/yagna-1/astragraph.git astragraph

echo "[bootstrap] done"
