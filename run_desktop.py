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
import traceback
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


def _wait_until_serving(host: str, port: int, fatal: list[BaseException], timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fatal:
            return False
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _first_free_port(host: str, start: int, count: int = 20) -> int | None:
    for port in range(start, start + count):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return port
        except OSError:
            continue
    return None


def _serve(port: int, fatal: list[BaseException]) -> None:
    try:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    except BaseException as exc:
        fatal.append(exc)


def _ensure_app_imports() -> None:
    """在主线程先导入应用，避免后台线程里失败时只看到端口超时。"""
    import app.main  # noqa: F401


# 与 manifest / 页面 <title> 一致，避免任务栏或窗口标题被 URL、短名覆盖
APP_WINDOW_TITLE = "AC Tracker · 刷题轨迹"


def main() -> None:
    root = _project_root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _prepare_user_paths()

    try:
        _ensure_app_imports()
    except Exception:
        if _is_frozen():
            print("AC Tracker: 无法加载内置后端。请重新下载安装包或向开发者反馈下列错误：", file=sys.stderr)
        else:
            print("AC Tracker: 无法加载后端应用（app.main），请在项目根目录运行并执行 pip install -r requirements.txt：", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    base = int(os.environ.get("ACM_TRACKER_PORT", "17890"))
    port = _first_free_port("127.0.0.1", base, 24)
    if port is None:
        print(
            "AC Tracker: 在",
            base,
            "–",
            base + 23,
            "范围内没有可用端口。请关闭占用端口的程序或设置 ACM_TRACKER_PORT。",
            file=sys.stderr,
        )
        sys.exit(1)
    if port != base:
        print(f"AC Tracker: 端口 {base} 被占用，已改用 {port}。", file=sys.stderr)

    fatal: list[BaseException] = []
    thread = threading.Thread(target=lambda: _serve(port, fatal), daemon=True)
    thread.start()
    time.sleep(0.2)
    if fatal:
        print("AC Tracker: 启动 uvicorn 失败：", file=sys.stderr)
        traceback.print_exception(type(fatal[0]), fatal[0], fatal[0].__traceback__)
        sys.exit(1)
    if not _wait_until_serving("127.0.0.1", port, fatal):
        if fatal:
            print("AC Tracker: 启动 uvicorn 失败：", file=sys.stderr)
            traceback.print_exception(type(fatal[0]), fatal[0], fatal[0].__traceback__)
        else:
            print(
                "AC Tracker: 本地服务在",
                port,
                "端口未及时就绪。若机器较慢可稍等；或检查防火墙/安全软件是否拦截本机回连。",
                file=sys.stderr,
            )
        sys.exit(1)

    chosen = port

    import webview

    # ?app=desktop 供前端加 html.desktop-shell，主滚动落在 body 上，避免 WKWebView 不向内层 overflow 传滚轮
    url = f"http://127.0.0.1:{chosen}/?app=desktop"
    window = webview.create_window(
        APP_WINDOW_TITLE,
        url,
        width=1100,
        height=760,
        min_size=(800, 520),
        text_select=True,
    )

    def _sync_window_title() -> None:
        """页面加载后部分平台会用 document.title 覆盖原生标题，再对齐一次。"""
        try:
            window.set_title(APP_WINDOW_TITLE)
        except Exception:
            pass

    try:
        window.events.loaded += _sync_window_title
    except Exception:
        pass

    webview.start()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
