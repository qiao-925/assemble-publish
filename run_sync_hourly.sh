#!/usr/bin/env bash
set -euo pipefail

# 内置整点循环：每个整点触发一次 run_sync.sh
# 用法示例：
#   # 启动整点循环（可选：先立刻跑一次）
#   RUN_IMMEDIATELY=true ./run_sync_hourly.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

: "${RUN_IMMEDIATELY:=true}"

run_once() {
  "$SCRIPT_DIR/run_sync.sh"
}

sleep_to_next_hour() {
  "$PYTHON_BIN" - <<'PY'
import datetime

now = datetime.datetime.now()
next_hour = (now.replace(minute=0, second=0, microsecond=0) +
             datetime.timedelta(hours=1))
sleep_seconds = int((next_hour - now).total_seconds())
if sleep_seconds <= 0:
    sleep_seconds = 1
print(sleep_seconds)
PY
}

if [ "$RUN_IMMEDIATELY" = "true" ]; then
  echo "▶️  立即执行一次同步"
  if run_once; then
    echo "✅ 本次同步完成"
  else
    echo "⚠️ 本次同步失败，仍将进入整点循环"
  fi
fi

while true; do
  sleep_sec="$(sleep_to_next_hour)"
  echo "⏱  距离下个整点还有 ${sleep_sec}s"
  sleep "$sleep_sec"
  echo "▶️  整点触发同步"
  if run_once; then
    echo "✅ 本次同步完成"
  else
    echo "⚠️ 本次同步失败，将等待下个整点"
  fi
done
