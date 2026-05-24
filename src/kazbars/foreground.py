"""KazBars — shared foreground probe (pure ctypes, no Tk/PIL).

The single source of truth for "is KazBars or Age of Conan the foreground
window?" — the gate for overlay visibility. Both the Deeps meter and the
shared `focus_watcher.ForegroundWatcher` reach through this module, replacing
the two near-identical copies that used to live in `deeps_meter` and
`overlay_engine` (and which had drifted on their failure-fallback behavior).

Mirrors `Deeps/rust/deeps/src/platform_win.rs::aoc_is_foreground`:
`GetForegroundWindow` → `GetWindowThreadProcessId` → match the PID against the
AoC executables via `CreateToolhelp32Snapshot` (which doesn't require
`OpenProcess` access on the target). The own-process branch is the
"dragging the overlay doesn't hide the overlay" trick — any window owned by
KazBars counts as in-focus, so the panels and the overlays keep the gate open.

Failure policy: any probe failure returns True. A transient error must never
hide a working overlay.
"""

import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

AOC_EXE_NAMES = ("AgeOfConan.exe", "AgeOfConanDX10.exe")

if _IS_WINDOWS:
    _TH32CS_SNAPPROCESS = 0x00000002
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

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
    _kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    _kernel32.Process32NextW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetCurrentProcessId.restype = wintypes.DWORD

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def app_or_game_foreground() -> bool:
    """True iff KazBars (this process) or Age of Conan owns the foreground
    window. Any probe failure returns True so a transient error never hides a
    working overlay."""
    if not _IS_WINDOWS:
        return True  # non-Windows stub: always show

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
                    return entry.szExeFile in AOC_EXE_NAMES
                if not _kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    return False
        finally:
            _kernel32.CloseHandle(snap)
    except OSError:
        logger.debug("app_or_game_foreground probe failed", exc_info=True)
        return True
