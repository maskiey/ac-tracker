#!/usr/bin/env python3
"""
桌面端：本机嵌入窗口 + 后台 uvicorn。
开发运行: python run_desktop.py
打包参见 packaging/README.md
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True


def _project_root() -> Path:
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return Path(__file__).resolve().parent


def _prepare_user_paths() -> None:
    """可写目录：数据库与 .env（覆盖 app/main.py、database 的默认路径）。"""
    if os.getenv("ACM_TRACKER_SKIP_USER_DIR"):
        return
    base = Path.home() / ".acm-tracker"
    base.mkdir(parents=True, exist_ok=True)
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    env_file = base / ".env"
    os.environ.setdefault("ACM_TRACKER_DATA_DIR", str(data_dir))
    os.environ.setdefault("ACM_TRACKER_ENV_FILE", str(env_file))
    if not env_file.exists():
        env_file.write_text(
            "# AC Tracker 桌面版配置\n"
            "# DATABASE_URL=sqlite:///" + str(data_dir / "submissions.db").replace("\\", "/") + "\n"
            "DEFAULT_HEATMAP_YEAR=\n",
            encoding="utf-8",
        )


def _wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.35):
                return True
        except OSError:
            time.sleep(0.08)
    return False


def _serve(port: int) -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


def main() -> None:
    root = _project_root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _prepare_user_paths()

    port = int(os.environ.get("ACM_TRACKER_PORT", "17890"))

    thread = threading.Thread(target=lambda: _serve(port), daemon=True)
    thread.start()
    if not _wait_port("127.0.0.1", port):
        print("AC Tracker: 本地服务未能启动，请检查端口", port, file=sys.stderr)
        sys.exit(1)

    import webview

    webview.create_window(
        "AC Tracker",
        f"http://127.0.0.1:{port}/",
        width=1100,
        height=760,
        min_size=(800, 520),
    )
    webview.start()


if __name__ == "__main__":
    main()
