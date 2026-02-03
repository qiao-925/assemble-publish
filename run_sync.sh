#!/usr/bin/env bash
set -euo pipefail

# 运行方式（示例）：
#   # 同步（首次运行会自动初始化发布记录）
#   ./run_sync.sh
#
# 需要的环境变量：
#   CNBLOGS_RPC_URL         博客园 RPC 地址
#   CNBLOGS_USERNAME        博客园用户名
#   CNBLOGS_TOKEN           博客园 Token（兼容 CNBLOGS_PASSWORD）
#   SYNC_REPO_URL           主仓库地址（普通 HTTPS URL；仅支持公共仓库）

: "${SYNC_REPO_URL?Need SYNC_REPO_URL (public repo URL, e.g. https://github.com/user/main-repo.git)}"
: "${SYNC_REPO_BRANCH:=main}"
: "${SYNC_REPO_DEPTH:=50}"
: "${WORKDIR:=/tmp/assemble-main-repo}"
: "${INSTALL_DEPS:=true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${WORKDIR}" ] || [ "${WORKDIR}" = "/" ] || [ "${WORKDIR}" = "." ] || [ "${WORKDIR}" = ".." ]; then
  echo "❌ WORKDIR 非法：'${WORKDIR}'"
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

export GIT_TERMINAL_PROMPT=0

if [ -d "$WORKDIR/.git" ]; then
  echo "ℹ️  发现已存在的主仓库工作区：$WORKDIR"
  cd "$WORKDIR"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$SYNC_REPO_URL"
  else
    git remote add origin "$SYNC_REPO_URL"
  fi

  if [ "$SYNC_REPO_DEPTH" != "0" ]; then
    git fetch --prune --depth "$SYNC_REPO_DEPTH" origin "$SYNC_REPO_BRANCH"
  else
    git fetch --prune origin "$SYNC_REPO_BRANCH"
    if git rev-parse --is-shallow-repository >/dev/null 2>&1; then
      if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
        git fetch --prune --unshallow origin
      fi
    fi
  fi

  git checkout -B "$SYNC_REPO_BRANCH" "origin/$SYNC_REPO_BRANCH"
  git reset --hard "origin/$SYNC_REPO_BRANCH"
else
  echo "ℹ️  主仓库工作区不存在，执行 clone：$WORKDIR"
  rm -rf "$WORKDIR"

  CLONE_ARGS=(clone --branch "$SYNC_REPO_BRANCH")
  if [ "$SYNC_REPO_DEPTH" != "0" ]; then
    CLONE_ARGS+=(--depth "$SYNC_REPO_DEPTH")
  fi

  git "${CLONE_ARGS[@]}" "$SYNC_REPO_URL" "$WORKDIR"
  cd "$WORKDIR"
fi

# 默认把去重记录/增量状态放到主仓库工作区（并由 sync-state 分支持久化）
: "${SYNC_RECORD_PATH:=.cnblogs_sync/.cnblogs_sync_record.json}"
: "${SYNC_STATE_PATH:=.cnblogs_sync/state.json}"

export SYNC_REPO_ROOT="$WORKDIR"
export SYNC_RECORD_PATH
export SYNC_STATE_PATH

# 可选：安装依赖（仅 python-dotenv）
if [ "$INSTALL_DEPS" = "true" ]; then
  "$PYTHON_BIN" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"
fi

# 运行同步脚本（脚本在本仓库；内容/状态在主仓库）
# 同步脚本内部会自动初始化发布记录（若缺失）
args=()
for arg in "$@"; do
  if [ "$arg" = "--init" ]; then
    echo "ℹ️  已忽略 --init：脚本会自动初始化发布记录"
    continue
  fi
  args+=("$arg")
done

"$PYTHON_BIN" "$SCRIPT_DIR/cnblogs_sync/sync_to_cnblogs.py" "${args[@]}"
