"""Windows ICO：按指定顺序写入多帧（BMP/DIB），避免 Pillow 保存时对尺寸排序导致「首帧为 16×16」。

Windows 资源管理器 / PyInstaller / 快捷方式常优先使用 ICO 目录中的**第一项**；
若第一项是 16×16，大图标会像糊块或异常；部分环境会退化为「白纸」占位图标。

参考：PIL.IcoImagePlugin._save（帧顺序改为调用方指定，且固定使用 DIB/BMP）。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import BmpImagePlugin, Image
from PIL.IcoImagePlugin import _MAGIC
from PIL._binary import o8, o16le as o16, o32le as o32


def write_ico_bmp_ordered(path: Path | str, frames: list[Image.Image]) -> None:
    """将多帧 RGBA 图像按给定顺序写入 .ico（每帧为 32bpp DIB，与 Pillow 行为一致）。"""
    if not frames:
        raise ValueError("frames must not be empty")
    path = Path(path)
    with path.open("wb") as fp:
        fp.write(_MAGIC)
        fp.write(o16(len(frames)))
        offset = fp.tell() + len(frames) * 16
        for frame in frames:
            width, height = frame.size
            fp.write(o8(width if width < 256 else 0))
            fp.write(o8(height if height < 256 else 0))
            bits, colors = BmpImagePlugin.SAVE[frame.mode][1:]
            fp.write(o8(colors))
            fp.write(b"\0")
            fp.write(b"\0\0")
            fp.write(o16(bits))
            image_io = BytesIO()
            frame.save(image_io, "dib")
            image_bytes = image_io.getvalue()
            image_bytes = image_bytes[:8] + o32(height * 2) + image_bytes[12:]
            bytes_len = len(image_bytes)
            fp.write(o32(bytes_len))
            fp.write(o32(offset))
            current = fp.tell()
            fp.seek(offset)
            fp.write(image_bytes)
            offset = offset + bytes_len
            fp.seek(current)
