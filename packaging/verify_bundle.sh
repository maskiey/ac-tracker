#!/usr/bin/env bash
# 在「已执行过 PyInstaller」的机器上，验证冻结程序能拉起本地 HTTP 服务（不依赖系统 Python）。
# 用法：bash packaging/verify_bundle.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$OSTYPE" == darwin* ]]; then
  BIN="$ROOT/dist/AC Tracker.app/Contents/MacOS/AC-Tracker"
else
  BIN="$ROOT/dist/AC-Tracker/AC-Tracker"
  if [[ ! -f "$BIN" ]]; then
    BIN="$ROOT/dist/AC-Tracker/AC-Tracker.exe"
  fi
fi

if [[ ! -x "$BIN" ]] && [[ ! -f "$BIN" ]]; then
  echo "未找到打包产物，请先在项目根目录执行: python -m PyInstaller packaging/acm_tracker.spec"
  exit 1
fi

echo "使用二进制: $BIN"

# 避免与开发环境端口冲突
export ACM_TRACKER_PORT="${ACM_TRACKER_PORT:-17990}"

"$BIN" &
PID=$!

cleanup() {
  kill "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
}
trap cleanup EXIT

for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${ACM_TRACKER_PORT}/api/health" | grep -q success; then
    echo "OK: /api/health 响应正常（冻结包可在无系统 Python 下启动服务）。"
    exit 0
  fi
  sleep 0.5
done

echo "FAIL: 超时未收到健康检查响应，请查看进程输出或提高等待时间。"
exit 1
