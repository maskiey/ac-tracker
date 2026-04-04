#!/usr/bin/env python3
"""从 packaging/icon_source.png 生成 Web 用 icon.png、Windows app.ico；在 macOS 上可再生成 app.icns。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = ROOT / "app" / "static" / "icon.png"
# 优先设计稿；否则用已生成的 Web 图标（便于 CI 只检出仓库即可打 Windows .ico）
SRC = ROOT / "packaging" / "icon_source.png"
if not SRC.is_file():
    SRC = OUT_PNG
ICO = ROOT / "packaging" / "icons" / "app.ico"
ICNS = ROOT / "packaging" / "icons" / "app.icns"
ICONSET = ROOT / "packaging" / "icons" / "AppIcon.iconset"


def build_rgba_icon() -> Image.Image:
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    im = im.crop((left, top, left + s, top + s))
    size = 1024
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    alpha = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(alpha)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    r, g, b, a = im.split()
    a_new = ImageChops.multiply(a, alpha)
    return Image.merge("RGBA", (r, g, b, a_new))


def main() -> None:
    if not SRC.is_file():
        print("缺少图标源文件：packaging/icon_source.png 或", OUT_PNG, file=sys.stderr)
        sys.exit(1)
    ICO.parent.mkdir(parents=True, exist_ok=True)
    im = build_rgba_icon()
    if SRC.resolve() != OUT_PNG.resolve():
        im.save(OUT_PNG, "PNG")
        print("Wrote", OUT_PNG)
    else:
        print("使用已有", OUT_PNG, "生成 .ico/.icns")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    imgs = [im.resize(sz, Image.Resampling.LANCZOS) for sz in sizes]
    imgs[0].save(ICO, format="ICO", sizes=[(i.width, i.height) for i in imgs], append_images=imgs[1:])
    print("Wrote", ICO)

    if sys.platform != "darwin":
        print("非 macOS：跳过 app.icns（请在 Mac 上执行或提交已生成的 packaging/icons/app.icns）")
        return

    if shutil.which("sips") and shutil.which("iconutil"):
        ICONSET.mkdir(parents=True, exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            subprocess.run(
                ["sips", "-z", str(s), str(s), str(OUT_PNG), "--out", str(ICONSET / f"icon_{s}x{s}.png")],
                check=True,
                capture_output=True,
            )
        shutil.copy(ICONSET / "icon_32x32.png", ICONSET / "icon_16x16@2x.png")
        subprocess.run(["sips", "-z", "64", "64", str(OUT_PNG), "--out", str(ICONSET / "icon_32x32@2x.png")], check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)], check=True)
        print("Wrote", ICNS)
        shutil.rmtree(ICONSET)
    else:
        print("未找到 sips/iconutil", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
