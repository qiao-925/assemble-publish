#!/usr/bin/env bash
set -euo pipefail

# 运行方式（示例）：
#   # 首次初始化
#   ./run_sync.sh --init
#
#   # 正常同步
#   ./run_sync.sh
#
# 需要的环境变量：
#   SYNC_REPO_URL           主仓库地址（建议用带 PAT 的 HTTPS；私有仓库必须）
# 可选：
#   SYNC_REPO_BRANCH        默认 main
#   SYNC_REPO_DEPTH         默认 50；设为 0 表示完整克隆
#   WORKDIR                默认 /tmp/assemble-main-repo（如果 WORKDIR 可持久化，则可复用以避免每次 clone）
#   PYTHON_BIN             默认 python3（不存在则回退 python）
#   INSTALL_DEPS           默认 true（安装 python-dotenv）
#   SYNC_RECORD_PATH       默认 .cnblogs_sync/.cnblogs_sync_record.json
#   SYNC_STATE_PATH        默认 .cnblogs_sync/state.json

: "${SYNC_REPO_URL?Need SYNC_REPO_URL (e.g. https://<PAT>@github.com/user/main-repo.git)}"
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
"$PYTHON_BIN" "$SCRIPT_DIR/cnblogs_sync/sync_to_cnblogs.py" "$@"
