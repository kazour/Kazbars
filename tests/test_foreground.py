"""Tests for the shared foreground probe.

The win32 calls are monkeypatched so each branch is exercised without a real
foreground window. The load-bearing case is `test_snapshot_failure_defaults_to_show`
— it locks in the fix for the old divergence where the Deeps copy hid the overlay
on a snapshot failure.
"""

import sys

import pytest

from kazbars import foreground
from kazbars.foreground import AOC_EXE_NAMES, app_or_game_foreground

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows ctypes probe")


def test_non_windows_stub_returns_true(monkeypatch):
    monkeypatch.setattr(foreground, "_IS_WINDOWS", False)
    assert app_or_game_foreground() is True


def test_aoc_exe_names_are_the_known_clients():
    assert AOC_EXE_NAMES == ("AgeOfConan.exe", "AgeOfConanDX10.exe")


@win_only
def test_no_foreground_window_returns_false(monkeypatch):
    monkeypatch.setattr(foreground._user32, "GetForegroundWindow", lambda: 0)
    assert app_or_game_foreground() is False


def _set_foreground_pid(monkeypatch, pid):
    monkeypatch.setattr(foreground._user32, "GetForegroundWindow", lambda: 123)

    def fake_gwtpid(_hwnd, pid_ptr):
        pid_ptr._obj.value = pid
        return 1

    monkeypatch.setattr(foreground._user32, "GetWindowThreadProcessId", fake_gwtpid)


@win_only
def test_own_process_returns_true(monkeypatch):
    _set_foreground_pid(monkeypatch, 4242)
    monkeypatch.setattr(foreground._kernel32, "GetCurrentProcessId", lambda: 4242)
    assert app_or_game_foreground() is True


@win_only
def test_snapshot_failure_defaults_to_show(monkeypatch):
    """The divergence-bug fix: a failed snapshot must return True (show), never
    hide a working overlay."""
    _set_foreground_pid(monkeypatch, 9999)
    monkeypatch.setattr(foreground._kernel32, "GetCurrentProcessId", lambda: 4242)
    monkeypatch.setattr(
        foreground._kernel32,
        "CreateToolhelp32Snapshot",
        lambda *_a: foreground._INVALID_HANDLE_VALUE,
    )
    assert app_or_game_foreground() is True


@win_only
def test_aoc_match_returns_true(monkeypatch):
    _set_foreground_pid(monkeypatch, 9999)
    monkeypatch.setattr(foreground._kernel32, "GetCurrentProcessId", lambda: 4242)
    monkeypatch.setattr(foreground._kernel32, "CreateToolhelp32Snapshot", lambda *_a: 77)
    monkeypatch.setattr(foreground._kernel32, "CloseHandle", lambda _h: 1)

    def fake_first(_snap, entry_ptr):
        entry_ptr._obj.th32ProcessID = 9999
        entry_ptr._obj.szExeFile = "AgeOfConan.exe"
        return 1

    monkeypatch.setattr(foreground._kernel32, "Process32FirstW", fake_first)
    assert app_or_game_foreground() is True


@win_only
def test_other_process_returns_false(monkeypatch):
    _set_foreground_pid(monkeypatch, 9999)
    monkeypatch.setattr(foreground._kernel32, "GetCurrentProcessId", lambda: 4242)
    monkeypatch.setattr(foreground._kernel32, "CreateToolhelp32Snapshot", lambda *_a: 77)
    monkeypatch.setattr(foreground._kernel32, "CloseHandle", lambda _h: 1)

    def fake_first(_snap, entry_ptr):
        entry_ptr._obj.th32ProcessID = 1111
        entry_ptr._obj.szExeFile = "explorer.exe"
        return 1

    monkeypatch.setattr(foreground._kernel32, "Process32FirstW", fake_first)
    monkeypatch.setattr(foreground._kernel32, "Process32NextW", lambda *_a: 0)
    assert app_or_game_foreground() is False
