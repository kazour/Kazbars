"""KazBars — Per-pixel-alpha overlay engine.

Renders an overlay to a PIL `Image` with a full RGBA alpha channel and
pushes it to a `WS_EX_LAYERED` window via win32 `UpdateLayeredWindow`.
Bypasses Tk's `-alpha` / `-transparentcolor` machinery entirely — which
is silently no-op'd on this Python 3.14 / Tk 9.0 build when the Toplevel
is descended from a `ttkb.Window` root.

The engine is intentionally minimal: it owns the win32 plumbing, a thin
Tk Toplevel shell (for HWND + event delivery + drag), and exposes a
`paint()` method that delegates rendering to a user-supplied callback.
Cells, fonts, layout, colors — all the cluster-specific concerns live
in the consumer (`deeps_overlay.py`, eventually `timer_overlay.py`).

Why this shape:
  - Wave C wants modular cells. A cell is just `draw(image, bounds, ctx)`.
  - The engine doesn't know what a "cell" is. It just blits a bitmap.
  - Same engine reuses verbatim for the Live Tracker overlay (different
    render callback, same plumbing).
"""

import ctypes
import logging
import os
import tkinter as tk
from collections.abc import Callable
from ctypes import wintypes
from functools import lru_cache

from PIL import Image, ImageChops, ImageFont

logger = logging.getLogger(__name__)


# =========================================================================== #
# Shared font infrastructure (used by every PIL-rendered overlay)             #
# =========================================================================== #

# Curated list of Win10+ shipping faces that read well as overlay text.
# Keeping the dropdown small avoids cross-machine surprises; the same list
# powers both the Deeps and Live Tracker panels.
FONT_FAMILY_CHOICES: tuple[str, ...] = (
    "Segoe UI",
    "Consolas",
    "Cascadia Code",
    "Courier New",
)

_FONT_FILES: dict[tuple[str, bool], str] = {
    ("Segoe UI", False):      "segoeui.ttf",
    ("Segoe UI", True):       "segoeuib.ttf",
    ("Consolas", False):      "consola.ttf",
    ("Consolas", True):       "consolab.ttf",
    ("Cascadia Code", False): "CascadiaCode.ttf",
    ("Cascadia Code", True):  "CascadiaCode.ttf",   # variable font
    ("Courier New", False):   "cour.ttf",
    ("Courier New", True):    "courbd.ttf",
}

_FONTS_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


@lru_cache(maxsize=128)
def load_font(family: str, size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Cached PIL FreeType font lookup. Falls back to PIL's bitmap default
    if the on-disk file is missing or unreadable."""
    file_map = _FONT_FILES.get((family, bold))
    if file_map is None:
        file_map = _FONT_FILES.get((family, False), _FONT_FILES[("Segoe UI", False)])
    path = os.path.join(_FONTS_DIR, file_map)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        logger.debug("Could not load font %s @ %d, falling back", path, size)
        return ImageFont.load_default()


# =========================================================================== #
# Win32 constants + ctypes plumbing                                           #
# =========================================================================== #

_GWL_STYLE = -16
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_CHILD = 0x40000000
_WS_POPUP = 0x80000000

_ULW_ALPHA = 0x00000002
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01
_BI_RGB = 0

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


# --------------------------------------------------------------------------- #
# Foreground detection — the overlay visibility gate                          #
# --------------------------------------------------------------------------- #
# Intentionally mirrors `deeps_meter.aoc_is_foreground` instead of importing
# it: the Deeps and Live Tracker clusters must not cross-import (enforced by
# tests/test_cluster_isolation.py), and `overlay_engine` is the shared layer
# both reach through.
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_AOC_EXE_NAMES = ("AgeOfConan.exe", "AgeOfConanDX10.exe")


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    )


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.GetCurrentProcessId.restype = wintypes.DWORD

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def app_or_game_foreground() -> bool:
    """True iff KazBars (this process) or Age of Conan owns the foreground
    window — the gate for overlay visibility. Any probe failure returns True
    so a transient error never hides a working overlay.

    Mirrors `deeps_meter.aoc_is_foreground`; kept separate to honor the
    Deeps / Live Tracker cluster isolation.
    """
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        if pid_val == 0:
            return False
        if pid_val == _kernel32.GetCurrentProcessId():
            return True  # any KazBars window (panel, overlay) keeps the gate open

        snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == _INVALID_HANDLE_VALUE or snap is None:
            return True
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            if not _kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                return True
            while True:
                if entry.th32ProcessID == pid_val:
                    return entry.szExeFile in _AOC_EXE_NAMES
                if not _kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    return False
        finally:
            _kernel32.CloseHandle(snap)
    except OSError:
        logger.debug("app_or_game_foreground probe failed", exc_info=True)
        return True


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


# Function prototypes (cleanly typed so ctypes does the right marshalling).
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long

_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int

_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_user32.SetParent.restype = wintypes.HWND

_user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(_POINT),
    ctypes.POINTER(_SIZE),
    wintypes.HDC,
    ctypes.POINTER(_POINT),
    wintypes.COLORREF,
    ctypes.POINTER(_BLENDFUNCTION),
    wintypes.DWORD,
]
_user32.UpdateLayeredWindow.restype = wintypes.BOOL

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL

_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL

_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(_BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP


# =========================================================================== #
# PIL helpers                                                                 #
# =========================================================================== #

def _to_premultiplied_bgra_bytes(image: Image.Image) -> bytes:
    """Convert a PIL RGBA image to premultiplied BGRA bytes for layered-window
    composition. `UpdateLayeredWindow` with `AC_SRC_ALPHA` requires both
    premultiplication AND BGRA channel order."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    r, g, b, a = image.split()
    r = ImageChops.multiply(r, a)
    g = ImageChops.multiply(g, a)
    b = ImageChops.multiply(b, a)
    return Image.merge("RGBA", (r, g, b, a)).tobytes("raw", "BGRA")


# =========================================================================== #
# LayeredOverlay                                                              #
# =========================================================================== #

class LayeredOverlay:
    """Win32 per-pixel-alpha overlay wrapping a thin Tk Toplevel.

    The Tk Toplevel exists for event delivery (drag) and lifecycle
    (show/hide/destroy) only — its visible pixels are entirely produced
    by `UpdateLayeredWindow` against a PIL bitmap, so it doesn't matter
    that the Toplevel itself is descended from a ttkb.Window root.

    The render callback gets the current pane size and returns a PIL
    RGBA Image of EXACTLY that size. Re-rendered on every `paint()`.

    Lock state toggles `WS_EX_TRANSPARENT` for OS-level click-through.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        render_callback: Callable[[int, int], Image.Image],
        width: int,
        height: int,
        on_drag_end: Callable[[int, int], None] | None = None,
    ) -> None:
        self._render_callback = render_callback
        self._on_drag_end = on_drag_end
        self._width = max(1, int(width))
        self._height = max(1, int(height))
        self._x = 0
        self._y = 0
        self._locked = False
        self._suppressed = False  # focus gate: hold the surface blank when off-focus
        self._drag_dx = 0
        self._drag_dy = 0

        # Tk Toplevel — owns the HWND + receives mouse events.
        self.root = tk.Toplevel(parent)
        # Opt out of pywinstyles' DWM call; we're a borderless layered window.
        self.root._skip_dark_titlebar = True  # type: ignore[attr-defined]
        self.root.overrideredirect(True)
        self.root.geometry(f"{self._width}x{self._height}+0+0")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        # Realise the window so wm_frame() returns a real HWND. `wm_frame()`
        # is Tk's canonical way to get the actual top-level HWND on Windows —
        # more reliable than `GetParent(winfo_id())` which is sensitive to
        # whether overrideredirect has been applied and to widget vs. frame
        # ambiguity in Tk's HWND layering.
        self.root.update_idletasks()
        try:
            self._hwnd = int(self.root.wm_frame(), 16)
        except (tk.TclError, ValueError):
            self._hwnd = self.root.winfo_id()
        if not self._hwnd:
            raise RuntimeError("Could not obtain HWND for layered overlay")

        # Inspect the window's actual styles. UpdateLayeredWindow rejects
        # any window with WS_CHILD (top-level windows only). Tk on Windows
        # gives Toplevels a WS_POPUP top-level, but when the parent is
        # itself a Toplevel (the panel), Tk can mark the resulting window
        # as owned/child in subtle ways. Detach the parent defensively.
        style = _user32.GetWindowLongW(self._hwnd, _GWL_STYLE)
        if style & _WS_CHILD:
            logger.info(
                "Overlay HWND 0x%x has WS_CHILD; detaching from parent for "
                "layered-window compatibility", self._hwnd,
            )
            _user32.SetParent(self._hwnd, None)
            # Clear WS_CHILD, set WS_POPUP.
            _user32.SetWindowLongW(
                self._hwnd, _GWL_STYLE, (style & ~_WS_CHILD) | _WS_POPUP,
            )

        # Promote to a layered window. UpdateLayeredWindow requires this bit;
        # without it, the call silently no-ops and the window stays blank.
        ex = _user32.GetWindowLongW(self._hwnd, _GWL_EXSTYLE)
        _user32.SetWindowLongW(self._hwnd, _GWL_EXSTYLE, ex | _WS_EX_LAYERED)
        ex_after = _user32.GetWindowLongW(self._hwnd, _GWL_EXSTYLE)
        style_after = _user32.GetWindowLongW(self._hwnd, _GWL_STYLE)
        logger.debug(
            "Overlay HWND 0x%x ready: style=0x%x ex_style=0x%x "
            "(WS_CHILD=%s, WS_POPUP=%s, WS_EX_LAYERED=%s)",
            self._hwnd, style_after, ex_after,
            bool(style_after & _WS_CHILD),
            bool(style_after & _WS_POPUP),
            bool(ex_after & _WS_EX_LAYERED),
        )
        if not (ex_after & _WS_EX_LAYERED):
            logger.error("Failed to set WS_EX_LAYERED on overlay HWND")

        # Default drag handlers are NOT installed automatically — consumers
        # that want simple drag-to-move call `bind_drag_to_move()`. Overlays
        # with richer interaction (lock-click + resize handle, etc.) bind
        # their own handlers via `self.root.bind(...)`.

        # Establish the layered surface NOW with a fully-transparent bitmap.
        # The HWND stays MAPPED for the engine's whole lifetime — visibility
        # is controlled by the bitmap content (transparent = invisible to
        # both rendering and mouse hit-testing). withdraw/deiconify would
        # unmap the HWND and UpdateLayeredWindow would reject subsequent
        # calls with ERROR_INVALID_PARAMETER (87).
        try:
            self.root.update_idletasks()
            blank = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
            self._push_to_window(blank)
        except Exception:
            logger.exception("Initial layered-window establish failed")

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def show(self) -> None:
        """Make the overlay visible by painting actual content. The HWND
        stays mapped across the entire lifetime — withdraw would unmap it
        and the next UpdateLayeredWindow call would fail with
        ERROR_INVALID_PARAMETER (87)."""
        self.paint()

    def hide(self) -> None:
        """Hide by painting a fully-transparent bitmap.

        Keeps the HWND mapped (so layered-window state survives) but the
        per-pixel alpha makes every pixel invisible to both rendering and
        mouse hit-testing. Cheaper than withdraw + safer for layered state.
        """
        try:
            blank = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
            self._push_to_window(blank)
        except Exception:
            logger.debug("hide() failed to push transparent bitmap", exc_info=True)

    def set_suppressed(self, suppressed: bool) -> bool:
        """Focus gate: while suppressed, hold the surface blank regardless of
        paint() calls. Returns True if the state changed, so the caller can
        decide whether to repaint on un-suppress (it knows if its consumer
        wants the overlay visible)."""
        suppressed = bool(suppressed)
        if suppressed == self._suppressed:
            return False
        self._suppressed = suppressed
        if suppressed:
            self.hide()
        return True

    def destroy(self) -> None:
        """Tear down the Toplevel. Safe to call multiple times."""
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def set_position(self, x: int, y: int) -> None:
        """Move the overlay. Tk geometry sets the HWND position; the layered
        bitmap is re-anchored on the next paint."""
        self._x = int(x)
        self._y = int(y)
        try:
            self.root.geometry(f"{self._width}x{self._height}+{self._x}+{self._y}")
        except tk.TclError:
            pass

    def set_size(self, width: int, height: int) -> None:
        """Resize the overlay. The next paint allocates a DIB of the new size."""
        new_w = max(1, int(width))
        new_h = max(1, int(height))
        if (new_w, new_h) == (self._width, self._height):
            return
        self._width = new_w
        self._height = new_h
        try:
            self.root.geometry(f"{self._width}x{self._height}+{self._x}+{self._y}")
        except tk.TclError:
            pass

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def set_locked(self, locked: bool) -> None:
        """Toggle OS-level click-through via `WS_EX_TRANSPARENT`."""
        self._locked = bool(locked)
        try:
            ex = _user32.GetWindowLongW(self._hwnd, _GWL_EXSTYLE)
            if self._locked:
                ex |= _WS_EX_TRANSPARENT
            else:
                ex &= ~_WS_EX_TRANSPARENT
            _user32.SetWindowLongW(self._hwnd, _GWL_EXSTYLE, ex)
        except Exception:
            logger.exception("Failed to toggle layered overlay click-through")

    def is_locked(self) -> bool:
        return self._locked

    def bind_drag_to_move(self, on_drag_end: Callable[[int, int], None] | None = None) -> None:
        """Install simple drag-to-move handlers on the Tk root.

        Consumers that need richer input (hit-test on click, resize handle,
        etc.) skip this and bind their own `<Button-1>` / `<B1-Motion>` /
        `<ButtonRelease-1>` handlers on `self.root`.
        """
        if on_drag_end is not None:
            self._on_drag_end = on_drag_end
        self.root.bind("<Button-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._on_drag_release)

    def paint(self) -> None:
        """Invoke the render callback and push the resulting bitmap.

        While suppressed (neither app nor game focused) the surface is held
        blank: paint() no-ops so incoming content updates can't un-hide it.
        """
        if self._suppressed:
            return
        try:
            image = self._render_callback(self._width, self._height)
        except Exception:
            logger.exception("Overlay render callback raised")
            return
        if image is None:
            return
        if image.size != (self._width, self._height):
            logger.warning(
                "Overlay render returned %dx%d; expected %dx%d",
                image.size[0], image.size[1], self._width, self._height,
            )
            return
        self._push_to_window(image)

    # ------------------------------------------------------------------ #
    # Drag handling                                                       #
    # ------------------------------------------------------------------ #

    def _on_drag_start(self, event: tk.Event) -> None:
        if self._locked:
            return
        self._drag_dx = event.x_root - self._x
        self._drag_dy = event.y_root - self._y

    def _on_drag(self, event: tk.Event) -> None:
        if self._locked:
            return
        self.set_position(event.x_root - self._drag_dx, event.y_root - self._drag_dy)

    def _on_drag_release(self, _event: tk.Event) -> None:
        if self._locked:
            return
        if self._on_drag_end is not None:
            self._on_drag_end(self._x, self._y)

    # ------------------------------------------------------------------ #
    # Win32 plumbing                                                      #
    # ------------------------------------------------------------------ #

    def _push_to_window(self, image: Image.Image) -> None:
        """Render the image to a fresh DIB and call `UpdateLayeredWindow`.

        Allocates per frame — at 10 Hz the overhead is ~0.1 ms. Pays off in
        not having to manage cache invalidation across resize/destroy paths.
        """
        bgra = _to_premultiplied_bgra_bytes(image)
        expected = self._width * self._height * 4
        if len(bgra) != expected:
            logger.error(
                "Pixel buffer size mismatch: got %d, expected %d", len(bgra), expected,
            )
            return

        screen_dc = _user32.GetDC(None)
        if not screen_dc:
            logger.warning("GetDC(None) returned NULL")
            return
        mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            _user32.ReleaseDC(None, screen_dc)
            logger.warning("CreateCompatibleDC returned NULL")
            return

        # Allocate the DIB section with mem_dc as the reference DC. Passing
        # NULL works on most systems but can produce a bitmap that's
        # incompatible with the destination DC on others.
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self._width
        bmi.bmiHeader.biHeight = -self._height  # negative → top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = _BI_RGB

        pbits = ctypes.c_void_p()
        hbm = _gdi32.CreateDIBSection(
            mem_dc, ctypes.byref(bmi), 0, ctypes.byref(pbits), None, 0,
        )
        if not hbm or not pbits.value:
            err = ctypes.get_last_error()
            logger.error(
                "CreateDIBSection failed: GetLastError=%d, size=%dx%d",
                err, self._width, self._height,
            )
            _gdi32.DeleteDC(mem_dc)
            _user32.ReleaseDC(None, screen_dc)
            return

        ctypes.memmove(pbits, bgra, expected)

        old = _gdi32.SelectObject(mem_dc, hbm)
        try:
            blend = _BLENDFUNCTION(
                BlendOp=_AC_SRC_OVER,
                BlendFlags=0,
                SourceConstantAlpha=255,
                AlphaFormat=_AC_SRC_ALPHA,
            )
            src_pos = _POINT(0, 0)
            dst_pos = _POINT(self._x, self._y)
            size = _SIZE(self._width, self._height)
            ok = _user32.UpdateLayeredWindow(
                self._hwnd,
                screen_dc,  # non-NULL — standalone diagnostic needs this to work
                ctypes.byref(dst_pos),
                ctypes.byref(size),
                mem_dc,
                ctypes.byref(src_pos),
                0,
                ctypes.byref(blend),
                _ULW_ALPHA,
            )
            if not ok:
                err = ctypes.get_last_error()
                if err != getattr(self, "_last_update_err", None):
                    style = _user32.GetWindowLongW(self._hwnd, _GWL_STYLE)
                    ex = _user32.GetWindowLongW(self._hwnd, _GWL_EXSTYLE)
                    logger.warning(
                        "UpdateLayeredWindow failed: GetLastError=%d, "
                        "hwnd=0x%x, style=0x%x (WS_CHILD=%s, WS_POPUP=%s), "
                        "ex_style=0x%x (WS_EX_LAYERED=%s), size=%dx%d, "
                        "pos=(%d,%d)",
                        err, self._hwnd, style,
                        bool(style & _WS_CHILD), bool(style & _WS_POPUP),
                        ex, bool(ex & _WS_EX_LAYERED),
                        self._width, self._height, self._x, self._y,
                    )
                    self._last_update_err = err
        finally:
            _gdi32.SelectObject(mem_dc, old)
            _gdi32.DeleteObject(hbm)
            _gdi32.DeleteDC(mem_dc)
            _user32.ReleaseDC(None, screen_dc)
