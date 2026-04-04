# 在项目根目录执行: pyinstaller packaging/acm_tracker.spec
# 依赖: pip install -r requirements.txt pyinstaller pywebview

import sys
from pathlib import Path

# Analysis 阶段遍历 FastAPI/SQLAlchemy 等依赖时，默认递归深度可能不够导致构建失败
sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

# PyInstaller 提供 SPECPATH = 本 spec 所在目录
ROOT = Path(SPECPATH).parent.resolve()  # noqa: F821

ICON_ICO = ROOT / "packaging" / "icons" / "app.ico"
ICON_ICNS = ROOT / "packaging" / "icons" / "app.icns"

# 必须用项目根下的绝对路径；相对路径会相对 .spec 所在目录，误变成 packaging/app
datas = [(str(ROOT / "app"), "app")]
# Windows：把 app.ico 放在与 AC-Tracker.exe 同级，供 Inno 快捷方式 IconFilename / 安装向导使用（仅靠 EXE 内嵌图标在部分环境仍显示旧图标）
if sys.platform == "win32" and ICON_ICO.is_file():
    datas.append((str(ICON_ICO), "."))
binaries = []
hiddenimports: list[str] = []

for pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "jinja2",
    "dotenv",
    "requests",
    "bs4",
    "webview",
    "tzdata",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Windows：与 pywebview 自带 PyInstaller hook 对齐，并打入 pythonnet/clr（WinForms + WebView2 必需）
if sys.platform == "win32":
    try:
        datas += collect_data_files("webview", subdir="lib")
        datas += collect_data_files("webview", subdir="js")
        binaries += collect_dynamic_libs("webview")
    except Exception:
        pass
    for _pkg in ("pythonnet", "clr_loader"):
        try:
            d, b, h = collect_all(_pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:
            pass

hiddenimports += [
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "clr",
    "clr_loader",
]

a = Analysis(
    [str(ROOT / "run_desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AC-Tracker",
    debug=False,
    console=False,
    icon=str(ICON_ICO) if sys.platform == "win32" and ICON_ICO.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    name="AC-Tracker",
)

if sys.platform == "darwin":
    BUNDLE(
        coll,
        name="AC Tracker.app",
        bundle_identifier="dev.maskiey.acmtracker",
        icon=str(ICON_ICNS) if ICON_ICNS.is_file() else None,
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleName": "AC Tracker",
            "CFBundleDisplayName": "AC Tracker",
        },
    )
