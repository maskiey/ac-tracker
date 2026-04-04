# 在项目根目录执行: pyinstaller packaging/acm_tracker.spec
# 依赖: pip install -r requirements.txt pyinstaller pywebview

import sys
from pathlib import Path

# Analysis 阶段遍历 FastAPI/SQLAlchemy 等依赖时，默认递归深度可能不够导致构建失败
sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))

from PyInstaller.utils.hooks import collect_all

# PyInstaller 提供 SPECPATH = 本 spec 所在目录
ROOT = Path(SPECPATH).parent.resolve()  # noqa: F821

datas = [("app", "app")]
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
):
    try:
        d, b, h = collect_all(pkg)
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
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleName": "AC Tracker",
            "CFBundleDisplayName": "AC Tracker",
        },
    )
