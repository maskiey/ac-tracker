#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m pip install -r requirements-desktop.txt
python3 -m PyInstaller packaging/acm_tracker.spec --noconfirm
echo "输出: $ROOT/dist/AC Tracker.app（及 dist/AC-Tracker/）"
