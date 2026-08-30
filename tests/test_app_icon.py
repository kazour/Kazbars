"""The app icon contract: one .ico under assets/icon/, carried by the bundle,
baked into the exe resource, and installed as the default window icon.

Run: `pytest tests/test_app_icon.py` (from repo root).
"""

import struct
from pathlib import Path

from kazbars.paths import APP_ICON

REPO = Path(__file__).resolve().parent.parent
SPEC = (REPO / "kazbars.spec").read_text(encoding="utf-8")
APP = (REPO / "src" / "kazbars" / "app.py").read_text(encoding="utf-8")


def _frames(path):
    """(width, is_png) per ICONDIR entry; width 0 means 256."""
    b = path.read_bytes()
    assert b[:4] == b"\x00\x00\x01\x00", "not an ICO"
    count = struct.unpack("<H", b[4:6])[0]
    out = []
    for i in range(count):
        w, _h, _cc, _r, _planes, _bpp, _size, off = struct.unpack("<BBBBHHII", b[6 + 16 * i:22 + 16 * i])
        out.append((w or 256, b[off:off + 8] == b"\x89PNG\r\n\x1a\n"))
    return out


def test_icon_exists_with_the_title_bar_taskbar_and_explorer_frames():
    assert APP_ICON.is_file()
    frames = dict(_frames(APP_ICON))
    assert {16, 32, 48, 256} <= set(frames), sorted(frames)
    assert frames[256] is True and frames[16] is False   # 256 PNG-compressed, small ones DIB


def test_spec_bundles_the_asset_and_bakes_the_exe_icon():
    assert '(str(ASSETS / "icon"), "kazbars/assets/icon")' in SPEC
    assert 'icon=str(ASSETS / "icon" / "KazBars.ico")' in SPEC


def test_window_installs_the_icon_and_suppresses_the_ttkbootstrap_logo():
    assert 'iconphoto=None' in APP
    assert 'self.iconbitmap(default=str(APP_ICON))' in APP
