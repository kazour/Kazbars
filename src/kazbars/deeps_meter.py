"""KazBars — Deeps meter (background tail thread).

Ports `Deeps/rust/deeps/src/meter.rs` and `platform_win.rs`. Owns the
worker thread that:

  1. Finds the newest `CombatLog-*.txt` in the configured game folder.
  2. Probes whether AoC currently holds it open (the Windows
     `CreateFile` exclusive-share trick).
  3. Tails the file, parsing every new line and recording matches into
     the three trackers.
  4. On a 100 ms tick, polls AoC focus and refreshes the snapshot the
     panel/overlay reads.
  5. Detects log rotation (truncation or a newer file appearing) and
     resets the trackers for a clean re-tail.

Threading model: one daemon thread owns the parsing pipeline; the UI
thread reads a fresh `MeterSnapshot` via `snapshot()`. A single
`threading.Lock` guards every shared mutation — record writes inside,
snapshot reads outside.

Alarm hysteresis and HPIS/DPIS tint logic deliberately live in the
panel/UI tick, not here — matches Deeps's split (main.rs owns alarm
state) and keeps this module focused on parsing + I/O.
"""

import ctypes
import logging
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .deeps_parsers import (
    parse_incoming_damage,
    parse_incoming_heal,
    parse_outgoing_damage_with_target,
    parse_outgoing_heal,
    parse_pet_hit_with_target,
    strip_log_timestamp,
)
from .deeps_trackers import (
    DamageInTracker,
    DamageOutTracker,
    HealsInTracker,
    HealsOutTracker,
)

logger = logging.getLogger(__name__)


# =========================================================================== #
# Status                                                                      #
# =========================================================================== #

class Status(Enum):
    """High-level meter state, surfaced to the panel for the status row."""

    NOT_STARTED = "not_started"          # before start() or after stop()
    WAITING_FOR_LOG = "waiting_for_log"  # game folder set, no CombatLog yet
    OLD_LOG = "old_log"                  # found a log but AoC isn't writing it
    TAILING = "tailing"                  # actively reading a live log


# =========================================================================== #
# Snapshot                                                                    #
# =========================================================================== #

@dataclass(frozen=True)
class MeterSnapshot:
    """Frozen view of the meter state, read by the UI tick.

    Rates carry the trackers' rolling values (None during warm-up, 0.0
    during post-warm-up silence, a number otherwise). `aoc_in_focus` is the
    auto-hide gate.
    """

    dps: float | None
    dpis: float | None
    hps: float | None
    hps_out: float | None
    aoc_in_focus: bool
    status: Status
    log_filename: str | None

    @classmethod
    def empty(cls) -> "MeterSnapshot":
        return cls(
            dps=None,
            dpis=None,
            hps=None,
            hps_out=None,
            aoc_in_focus=False,
            status=Status.NOT_STARTED,
            log_filename=None,
        )


# =========================================================================== #
# Windows API bindings (focus poll + live-log probe)                          #
# =========================================================================== #

_IS_WINDOWS = sys.platform == "win32"

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


def aoc_is_foreground() -> bool:
    """True iff AoC (or this process itself) is the foreground window.

    Mirrors `Deeps/rust/deeps/src/platform_win.rs::aoc_is_foreground` —
    `GetForegroundWindow` → `GetWindowThreadProcessId` → match the PID
    against `AgeOfConan.exe` / `AgeOfConanDX10.exe` via
    `CreateToolhelp32Snapshot` (which doesn't require `OpenProcess`
    access on the target).

    The own-process branch is the "overlay drag doesn't hide overlay"
    trick — any window owned by KazBars counts as AoC focus, so the
    Deeps panel and the overlay itself keep the show-gate open.
    """
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
        # Our own process counts as AoC for the show-gate.
        if pid_val == _kernel32.GetCurrentProcessId():
            return True

        snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == _INVALID_HANDLE_VALUE or snap is None:
            return False
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            if not _kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                return False
            while True:
                if entry.th32ProcessID == pid_val:
                    name = entry.szExeFile
                    return name in ("AgeOfConan.exe", "AgeOfConanDX10.exe")
                if not _kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    return False
        finally:
            _kernel32.CloseHandle(snap)
    except OSError:
        # Failing the probe should not hide the overlay — default to show.
        logger.debug("aoc_is_foreground probe failed", exc_info=True)
        return True


def is_live(path: Path) -> bool:
    """True iff `path` is held open exclusively by another process.

    Mirrors `Deeps/rust/deeps/src/meter.rs::is_live`. Tries an exclusive
    `CreateFile` (FILE_SHARE_NONE); a sharing-violation failure means AoC
    holds the file → live.

    Non-Windows fallback: file modified in the last ~10 s = live.
    """
    if not _IS_WINDOWS:
        try:
            return (time.time() - path.stat().st_mtime) < 10.0
        except OSError:
            return False

    import win32con
    import win32file

    try:
        handle = win32file.CreateFile(
            str(path),
            win32con.GENERIC_READ,
            0,  # share_mode=0 — fail if anyone holds it
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
    except Exception:
        return True
    win32file.CloseHandle(handle)
    return False


def newest_combat_log(folder: Path) -> Path | None:
    """Return the newest `CombatLog-*.txt` in `folder` by mtime, or None.

    Files that don't start with `CombatLog` or don't end with `.txt` are
    filtered out — AoC writes only this name shape.
    """
    try:
        candidates = [
            p
            for p in folder.iterdir()
            if p.is_file()
            and p.name.startswith("CombatLog")
            and p.name.endswith(".txt")
        ]
    except OSError:
        return None
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


# =========================================================================== #
# DeepsMeter                                                                  #
# =========================================================================== #

class DeepsMeter:
    """Background tail thread + tracker holder.

    Lifecycle: construct → set_include_pet_damage(...) → start(folder)
    → snapshot() ... → stop(). Restart is supported (start() after stop()
    spawns a fresh thread with reset trackers).
    """

    TICK_INTERVAL = 0.1   # seconds between housekeeping ticks
    EOF_SLEEP = 0.05      # seconds to wait after EOF before retrying readline
    SCAN_SLEEP = 2.0      # seconds between scans when no live log is found

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._game_folder: Path | None = None

        self._out_tracker = DamageOutTracker()
        self._in_tracker = DamageInTracker()
        self._heals_tracker = HealsInTracker()
        self._heals_out_tracker = HealsOutTracker()
        self._include_pet_damage = False

        # Targets you (or your pets) have damaged in this session. Used to
        # filter bubble-converted boss heals out of HPS-out — boss bubbles
        # emit `Your X heals/critically healed <Boss> for N` lines that are
        # syntactically indistinguishable from real group heals. Cleared on
        # start() and on log-rotation boundary.
        self._known_mobs: set[str] = set()

        # State updated only under `_lock`.
        self._status: Status = Status.NOT_STARTED
        self._log_filename: str | None = None
        self._aoc_in_focus = False
        self._snapshot: MeterSnapshot = MeterSnapshot.empty()

    # ------------------------------------------------------------------ #
    # Public API (called from the main thread / panel)                   #
    # ------------------------------------------------------------------ #

    def start(self, game_folder: str | Path) -> None:
        """Spawn the daemon thread pointed at `game_folder`.

        No-op (logged) if already running. Resets trackers so the new
        session measures from zero.
        """
        with self._lock:
            if self._running:
                logger.warning("DeepsMeter.start called while already running")
                return
            self._game_folder = Path(game_folder)
            self._running = True
            self._reset_trackers_locked()
            self._status = Status.NOT_STARTED
            self._log_filename = None
            self._snapshot = MeterSnapshot.empty()

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="deeps-meter"
        )
        self._thread.start()

    def stop(self, timeout: float = 0.5) -> None:
        """Ask the worker to exit; wait up to `timeout` seconds for it.

        Always safe to call — no-op if not running.
        """
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._status = Status.NOT_STARTED
            self._log_filename = None
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=timeout)
        with self._lock:
            self._snapshot = MeterSnapshot.empty()

    def snapshot(self) -> MeterSnapshot:
        """Latest snapshot. Safe to call from any thread."""
        with self._lock:
            return self._snapshot

    def set_include_pet_damage(self, on: bool) -> None:
        """Toggle pet damage attribution. Effective on the next parsed line."""
        with self._lock:
            self._include_pet_damage = on

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # ------------------------------------------------------------------ #
    # Worker-thread internals (only touched by the daemon thread)        #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        """Outer loop: scan for a live log, then tail it."""
        while True:
            with self._lock:
                if not self._running:
                    return
                game_folder = self._game_folder

            if game_folder is None or not game_folder.exists():
                self._update_state(Status.NOT_STARTED, None)
                time.sleep(0.5)
                continue

            path = newest_combat_log(game_folder)
            if path is None:
                self._update_state(Status.WAITING_FOR_LOG, None)
                time.sleep(self.SCAN_SLEEP)
                continue

            if not is_live(path):
                self._update_state(Status.OLD_LOG, path.name)
                time.sleep(self.SCAN_SLEEP)
                continue

            # Live log found — tail it. Returns on log boundary or stop.
            self._update_state(Status.TAILING, path.name)
            try:
                self._tail_file(path)
            except OSError:
                logger.exception("Tail loop failed; will rescan")

    def _tail_file(self, path: Path) -> None:
        """Inner loop: read lines from `path`, run the parsers, tick housekeeping."""
        try:
            f = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return
        try:
            last_size = 0
            last_tick = time.monotonic()
            while True:
                with self._lock:
                    if not self._running:
                        return

                now = time.monotonic()
                if now - last_tick >= self.TICK_INTERVAL:
                    self._tick(now)
                    last_tick = now

                line = f.readline()
                if not line:
                    # EOF — check for log boundary.
                    try:
                        cur_size = path.stat().st_size
                    except OSError:
                        return
                    if cur_size < last_size:
                        # Truncated → AoC started a new session.
                        self._reset_for_log_boundary()
                        return
                    last_size = cur_size

                    # Also check for a newer CombatLog file appearing.
                    with self._lock:
                        folder = self._game_folder
                    if folder is not None:
                        newer = newest_combat_log(folder)
                        if newer is not None and newer != path:
                            self._reset_for_log_boundary()
                            return

                    time.sleep(self.EOF_SLEEP)
                    continue

                stripped = line.rstrip("\r\n")
                stripped = strip_log_timestamp(stripped)
                if stripped:
                    self._process_line(now, stripped)
        finally:
            f.close()

    def _process_line(self, now: float, line: str) -> None:
        """Run every parser; record matches under lock.

        Outgoing damage and pet hits also populate `_known_mobs` so the
        HPS-out path can reject heal lines whose target is a bubble boss.
        """
        out_dmg = parse_outgoing_damage_with_target(line)
        in_dmg = parse_incoming_damage(line)
        heal = parse_incoming_heal(line)
        pet_dmg = parse_pet_hit_with_target(line)
        out_heal = parse_outgoing_heal(line)

        if (
            out_dmg is None
            and in_dmg is None
            and heal is None
            and pet_dmg is None
            and out_heal is None
        ):
            return

        with self._lock:
            if out_dmg is not None:
                amount, target = out_dmg
                self._out_tracker.record(now, amount)
                self._known_mobs.add(target)
            if in_dmg is not None:
                self._in_tracker.record(now, in_dmg)
            if heal is not None:
                self._heals_tracker.record(now, heal)
            if pet_dmg is not None:
                amount, target = pet_dmg
                self._known_mobs.add(target)
                if self._include_pet_damage:
                    self._out_tracker.record_pet(now, amount)
            if out_heal is not None:
                amount, target = out_heal
                if target not in self._known_mobs:
                    self._heals_out_tracker.record(now, amount)

    def _tick(self, now: float) -> None:
        """100 ms housekeeping: poll AoC focus, refresh the snapshot."""
        in_focus = aoc_is_foreground()
        with self._lock:
            self._aoc_in_focus = in_focus
            self._snapshot = self._build_snapshot_locked(now)

    def _update_state(self, status: Status, log_filename: str | None) -> None:
        """Set status + log filename and rebuild the snapshot accordingly."""
        in_focus = aoc_is_foreground()
        now = time.monotonic()
        with self._lock:
            self._status = status
            self._log_filename = log_filename
            self._aoc_in_focus = in_focus
            self._snapshot = self._build_snapshot_locked(now)

    def _build_snapshot_locked(self, now: float) -> MeterSnapshot:
        """Compose a `MeterSnapshot` from current tracker state. Caller holds the lock."""
        return MeterSnapshot(
            dps=self._out_tracker.rolling_rate(now),
            dpis=self._in_tracker.rolling_rate(now),
            hps=self._heals_tracker.rolling_rate(now),
            hps_out=self._heals_out_tracker.rolling_rate(now),
            aoc_in_focus=self._aoc_in_focus,
            status=self._status,
            log_filename=self._log_filename,
        )

    def _reset_trackers_locked(self) -> None:
        """Zero the four trackers and the known-mobs set (caller holds the lock)."""
        self._out_tracker.reset()
        self._in_tracker.reset()
        self._heals_tracker.reset()
        self._heals_out_tracker.reset()
        self._known_mobs.clear()

    def _reset_for_log_boundary(self) -> None:
        """Log rotated or truncated → zero trackers so the new session measures fresh."""
        with self._lock:
            self._reset_trackers_locked()
            self._snapshot = self._build_snapshot_locked(time.monotonic())
