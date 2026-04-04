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


def _configure_pythonnet_for_frozen_windows() -> None:
    """PyInstaller + pywebview：WinForms 后端通过 pythonnet 加载 CLR，须指向内嵌 python3xx.dll。

    未设置 PYTHONNET_PYDLL 时，目标机上常见表现为双击无界面、进程瞬间退出（日志里多为
    Failed to resolve Python.Runtime / cannot call null pointer）。
    """
    if sys.platform != "win32" or not _is_frozen():
        return
    if os.environ.get("PYTHONNET_PYDLL"):
        return
    root = _project_root()
    candidates = sorted(root.glob("python3*.dll"), key=lambda p: p.name, reverse=True)
    for p in candidates:
        if p.is_file():
            os.environ["PYTHONNET_PYDLL"] = str(p.resolve())
            if _is_frozen():
                _append_log("PYTHONNET_PYDLL=" + os.environ["PYTHONNET_PYDLL"])
            return


def _show_windows_message(title: str, text: str, *, error: bool = False) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        flags = 0x10 if error else 0x40  # MB_ICONERROR | MB_ICONINFORMATION
        t = (title or "AC Tracker")[:256]
        x = (text or "")[:1024]
        ctypes.windll.user32.MessageBoxW(None, x, t, flags)
    except Exception:
        pass


def _project_root() -> Path:
    """PyInstaller onedir：资源在 exe 同级的 _internal；_MEIPASS 指向该目录。"""
    if _is_frozen():
        mp = getattr(sys, "_MEIPASS", None)
        if mp:
            return Path(mp)
        exe_dir = Path(sys.executable).resolve().parent
        internal = exe_dir / "_internal"
        return internal if internal.is_dir() else exe_dir
    return Path(__file__).resolve().parent


def _log_file() -> Path:
    return Path.home() / ".acm-tracker" / "ac-tracker.log"


def _append_log(msg: str) -> None:
    try:
        p = _log_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


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
    """非 Windows：在守护线程中启动 uvicorn（单进程）。"""
    try:
        if sys.platform == "win32":
            import asyncio

            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
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


def _uvicorn_child_main(port: int) -> None:
    """Windows 专用：在子进程的「主线程」里跑 uvicorn。

    CPython 在 Windows 上默认使用 ProactorEventLoop；在子线程里跑 uvicorn 时易出现无法监听、
    或长时间无法就绪，界面即报「本地服务启动失败」。独立进程可避免该问题。
    """
    root = _project_root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _prepare_user_paths()
    try:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    except BaseException:
        try:
            _append_log("uvicorn 子进程异常:\n" + traceback.format_exc())
        except Exception:
            pass
        raise


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
    _configure_pythonnet_for_frozen_windows()
    # 无控制台时 stderr 不可见，启动失败请查看 %USERPROFILE%\.acm-tracker\ac-tracker.log
    if _is_frozen():
        _append_log("---\n启动: cwd=" + str(Path.cwd()) + " root=" + str(root) + " exe=" + sys.executable)

    _prepare_user_paths()

    if sys.platform != "win32":
        try:
            _ensure_app_imports()
        except Exception:
            if _is_frozen():
                print("AC Tracker: 无法加载内置后端。请重新下载安装包或向开发者反馈下列错误：", file=sys.stderr)
                _append_log("导入 app.main 失败:\n" + traceback.format_exc())
            else:
                print("AC Tracker: 无法加载后端应用（app.main），请在项目根目录运行并执行 pip install -r requirements.txt：", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

    base = int(os.environ.get("ACM_TRACKER_PORT", "17890"))
    port = _first_free_port("127.0.0.1", base, 24)
    if port is None:
        msg = (
            f"AC Tracker: 在 {base}–{base + 23} 范围内没有可用端口。"
            "请关闭占用端口的程序或设置环境变量 ACM_TRACKER_PORT。"
        )
        print(msg, file=sys.stderr)
        if _is_frozen() and sys.platform == "win32":
            _append_log(msg)
            _show_windows_message("AC Tracker", msg, error=True)
        sys.exit(1)
    if port != base:
        print(f"AC Tracker: 端口 {base} 被占用，已改用 {port}。", file=sys.stderr)

    uvicorn_proc = None
    if sys.platform == "win32":
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        uvicorn_proc = ctx.Process(target=_uvicorn_child_main, args=(port,), name="acm-uvicorn")
        uvicorn_proc.start()
        deadline = time.time() + 45.0
        ready = False
        while time.time() < deadline:
            if not uvicorn_proc.is_alive():
                _append_log("uvicorn 进程已退出 exitcode=" + str(uvicorn_proc.exitcode))
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    ready = True
                    break
            except OSError:
                time.sleep(0.1)
        if not ready:
            if uvicorn_proc.is_alive():
                uvicorn_proc.terminate()
            try:
                uvicorn_proc.join(timeout=5)
            except Exception:
                pass
            msg = (
                "AC Tracker: 本地服务未能启动。"
                "请查看 %USERPROFILE%\\.acm-tracker\\ac-tracker.log"
            )
            print(msg, file=sys.stderr)
            if _is_frozen():
                _append_log(msg)
                _show_windows_message("AC Tracker", msg, error=True)
            sys.exit(1)
    else:
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

    # WebView2 用户数据放用户目录，避免从「开始」启动时工作目录异常导致无法创建缓存
    webview_data = Path.home() / ".acm-tracker" / "webview2"
    try:
        webview_data.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(webview_data))
    except Exception:
        pass

    try:
        import webview
    except Exception:
        _append_log("导入 webview 失败:\n" + traceback.format_exc())
        if uvicorn_proc is not None and uvicorn_proc.is_alive():
            uvicorn_proc.terminate()
            try:
                uvicorn_proc.join(timeout=5)
            except Exception:
                pass
        if _is_frozen() and sys.platform == "win32":
            _show_windows_message(
                "AC Tracker",
                "无法加载界面组件（pywebview）。若已排除杀毒软件拦截，"
                "请安装 Microsoft Edge WebView2 运行时后重试；"
                "详情见日志 %USERPROFILE%\\.acm-tracker\\ac-tracker.log",
                error=True,
            )
        raise

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

    try:
        webview.start()
    except Exception:
        _append_log("webview.start 失败:\n" + traceback.format_exc())
        if _is_frozen() and sys.platform == "win32":
            _show_windows_message(
                "AC Tracker",
                "窗口启动失败。请安装 WebView2 运行时或查看日志："
                "%USERPROFILE%\\.acm-tracker\\ac-tracker.log",
                error=True,
            )
        raise
    finally:
        if uvicorn_proc is not None and uvicorn_proc.is_alive():
            uvicorn_proc.terminate()
            try:
                uvicorn_proc.join(timeout=10)
            except Exception:
                pass


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        if _is_frozen():
            _append_log("未捕获异常:\n" + traceback.format_exc())
            if sys.platform == "win32":
                tb = traceback.format_exc()
                _show_windows_message(
                    "AC Tracker",
                    "启动失败。详情见 %USERPROFILE%\\.acm-tracker\\ac-tracker.log\n\n" + tb[-900:],
                    error=True,
                )
        raise
