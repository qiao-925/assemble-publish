#!/usr/bin/env bash
set -euo pipefail

: "${SYNC_REPO_URL?Need SYNC_REPO_URL (e.g. https://github.com/user/assemble.git)}"
: "${SYNC_REPO_BRANCH:=main}"
: "${WORKDIR:=/tmp/assemble-repo}"
: "${INSTALL_DEPS:=true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

export GIT_TERMINAL_PROMPT=0

rm -rf "$WORKDIR"

git clone --depth=1 --branch "$SYNC_REPO_BRANCH" "$SYNC_REPO_URL" "$WORKDIR"

cd "$WORKDIR"

# 可选：安装依赖
if [ "$INSTALL_DEPS" = "true" ]; then
  "$PYTHON_BIN" -m pip install --disable-pip-version-check -r \
    "$SCRIPT_DIR/requirements.txt"
fi

# 运行同步脚本（位于主仓库内）
"$PYTHON_BIN" "🗀 04-cnblogs_sync (6个文件，1.3%)/sync_to_cnblogs.py"
