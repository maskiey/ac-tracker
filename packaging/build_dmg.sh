#!/usr/bin/env bash
# 在 PyInstaller 生成 dist/AC Tracker.app 之后执行；输出仓库根目录 AC-Tracker-macos.dmg
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/AC Tracker.app"
DMG_OUT="$ROOT/AC-Tracker-macos.dmg"
if [[ ! -d "$APP" ]]; then
  echo "未找到: $APP（请先运行 PyInstaller）" >&2
  exit 1
fi
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/ac-tracker-dmg.XXXXXX")"
trap 'rm -rf "$STAGING"' EXIT
cp -R "$APP" "$STAGING/"
ln -sf /Applications "$STAGING/Applications"
rm -f "$DMG_OUT"
hdiutil create \
  -volname "AC Tracker" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  "$DMG_OUT"
echo "DMG: $DMG_OUT"
