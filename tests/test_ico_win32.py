"""ICO 目录顺序：首项须为 256×256，避免 Windows 显示异常图标。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

_PACK = Path(__file__).resolve().parents[1] / "packaging"
if str(_PACK) not in sys.path:
    sys.path.insert(0, str(_PACK))

from ico_win32 import write_ico_bmp_ordered


def test_write_ico_first_directory_entry_is_256(tmp_path: Path) -> None:
    frames = [Image.new("RGBA", (s, s), (200, 100, 50, 255)) for s in (256, 128, 32)]
    out = tmp_path / "t.ico"
    write_ico_bmp_ordered(out, frames)
    raw = out.read_bytes()
    # ICONDIR 6 bytes；首条 ICONDIRENTRY：宽/高为 0 表示 256（ICO 规范）
    assert raw[6] == 0 and raw[7] == 0
