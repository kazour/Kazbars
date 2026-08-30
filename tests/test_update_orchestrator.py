"""Tests for kazbars.update_orchestrator — the one update routine (no network,
no Tk, no threads).

Mirrors test_content_update's shape: a fake synchronous app whose `after` runs
main-thread hops inline, `threading.Thread` replaced by a run-now stand-in,
`app_toast` captured, and the release lookup / staging / content check injected
or monkeypatched.

Run: `pytest tests/test_update_orchestrator.py` (from repo root).
"""

import os

import pytest

from kazbars import self_update as S
from kazbars import update_orchestrator as O

RELEASE = {"tag_name": "v9.9.9", "html_url": "http://x/rel", "assets": []}


class _FakeApp:
    def __init__(self, tmp_path):
        self.app_version = "3.0.1"
        self.app_path = tmp_path
        self.settings = {"content_version": 1}
        self._app_update_phase = None
        self._app_update_staged = None
        self.close_result = True
        self.closed = 0

    def after(self, _delay, fn, *args):
        fn(*args)

    def winfo_exists(self):
        return True

    def _on_close(self):
        self.closed += 1
        return self.close_result


class _SyncThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.fixture
def app(tmp_path):
    return _FakeApp(tmp_path)


@pytest.fixture
def toasts(monkeypatch):
    calls = []
    monkeypatch.setattr(
        O, "app_toast",
        lambda app, msg, style, dur, key=None, on_click=None: calls.append((msg, style, on_click)))
    return calls


@pytest.fixture
def content_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(O.content_update, "check_and_apply",
                        lambda *a, **k: calls.append((a, k)))
    return calls


@pytest.fixture
def sync_threads(monkeypatch):
    monkeypatch.setattr(O.threading, "Thread", _SyncThread)


# --------------------------------------------------------------------------- #
# the check: app first, content second
# --------------------------------------------------------------------------- #

def test_update_available_offers_install_and_skips_content(app, toasts, content_calls):
    O._check_worker(app, False, fetch=lambda _v: ("update", RELEASE))
    assert [(m, s) for m, s, _ in toasts] == [("KazBars v9.9.9 is available — click to install", "info")]
    assert content_calls == []


def test_current_runs_the_content_check_with_manual_propagated(app, toasts, content_calls):
    O._check_worker(app, True, fetch=lambda _v: ("current", None))
    assert toasts == []
    (args, kwargs), = content_calls
    assert args == (app, "3.0.1", 1) and kwargs == {"manual": True}
    O._check_worker(app, False, fetch=lambda _v: ("current", None))
    assert content_calls[-1][1] == {"manual": False}


def test_error_manual_warns_once_and_stops(app, toasts, content_calls):
    O._check_worker(app, True, fetch=lambda _v: ("error", None))
    assert [(m, s) for m, s, _ in toasts] == [("Couldn't reach GitHub — check your connection", "warning")]
    assert content_calls == []


def test_error_on_launch_is_silent_and_still_checks_content(app, toasts, content_calls):
    O._check_worker(app, False, fetch=lambda _v: ("error", None))
    assert toasts == [] and len(content_calls) == 1


def test_check_now_runs_the_worker(app, toasts, content_calls, sync_threads, monkeypatch):
    monkeypatch.setattr(O.update_check, "fetch_release", lambda _v: ("current", None))
    O.check_now(app)
    assert content_calls[0][1] == {"manual": True}
    O.check_on_launch(app)
    assert content_calls[1][1] == {"manual": False}


# --------------------------------------------------------------------------- #
# click 1: stage in the background
# --------------------------------------------------------------------------- #

def test_offer_click_starts_the_download(app, toasts, sync_threads, monkeypatch):
    staged = app.app_path / ".update" / "KazBars" / "KazBars.exe"
    monkeypatch.setattr(O.self_update, "stage_release", lambda *a, **k: staged)
    O._offer_install(app, RELEASE)
    _msg, _style, on_click = toasts[-1]
    on_click()
    assert app._app_update_phase == "ready" and app._app_update_staged == staged
    assert toasts[-1][:2] == ("KazBars v9.9.9 downloaded — click to restart and install", "success")


def test_install_worker_reports_progress_then_ready(app, toasts):
    def stage(_path, _release, *, progress):
        progress(50, 100)
        progress(100, 100)
        return "exe"
    O._install_worker(app, RELEASE, stage=stage)
    msgs = [m for m, _, _ in toasts]
    assert msgs == ["Downloading KazBars v9.9.9 — 50%", "Unpacking KazBars v9.9.9…",
                    "KazBars v9.9.9 downloaded — click to restart and install"]


def test_install_worker_failure_resets_phase_and_discards(app, toasts, monkeypatch):
    app._app_update_phase = "downloading"
    (app.app_path / S.UPDATE_DIR).mkdir()
    opened = []
    monkeypatch.setattr(O.webbrowser, "open", lambda url: opened.append(url))

    def stage(*_a, **_k):
        raise S.StageError("The update download didn't verify")
    O._install_worker(app, RELEASE, stage=stage)
    msg, style, on_click = toasts[-1]
    assert (msg, style) == ("The update download didn't verify — click to open the release page", "warning")
    assert app._app_update_phase is None
    assert not (app.app_path / S.UPDATE_DIR).exists()
    on_click()
    assert opened == ["http://x/rel"]


def test_offer_while_downloading_is_ignored_and_ready_is_reoffered(app, toasts):
    app._app_update_phase = "downloading"
    O._offer_install(app, RELEASE)
    assert toasts == []
    app._app_update_phase = "ready"
    app._app_update_staged = "exe"
    O._offer_install(app, RELEASE)
    assert toasts[-1][1] == "success"


def test_start_install_twice_does_not_restage(app, toasts, sync_threads, monkeypatch):
    calls = []
    monkeypatch.setattr(O.self_update, "stage_release", lambda *a, **k: calls.append(1) or "exe")
    O.start_install(app, RELEASE)
    O.start_install(app, RELEASE)
    assert calls == [1] and app._app_update_phase == "ready"


# --------------------------------------------------------------------------- #
# click 2: restart through the close path
# --------------------------------------------------------------------------- #

def test_restart_hands_off_only_when_close_succeeds(app, monkeypatch):
    spawned = []
    monkeypatch.setattr(O.self_update, "spawn_apply", lambda *a: spawned.append(a))
    app.close_result = False
    O.restart_to_install(app, "exe")
    assert app.closed == 1 and spawned == []
    app.close_result = True
    O.restart_to_install(app, "exe")
    assert spawned == [("exe", app.app_path, os.getpid())]


# --------------------------------------------------------------------------- #
# next launch
# --------------------------------------------------------------------------- #

def _pending(app, **fields):
    update_dir = app.app_path / S.UPDATE_DIR
    update_dir.mkdir(exist_ok=True)
    S.write_pending(update_dir, **fields)
    return update_dir


def test_finish_startup_after_success(app, toasts, monkeypatch):
    opened = []
    monkeypatch.setattr(O.webbrowser, "open", lambda url: opened.append(url))
    _pending(app, state="applied", version="3.0.1", html_url="http://x/rel")
    O.finish_startup(app)
    msg, style, on_click = toasts[-1]
    assert (msg, style) == ("KazBars updated to v3.0.1 — click for what's new", "success")
    assert not (app.app_path / S.UPDATE_DIR).exists()
    on_click()
    assert opened == ["http://x/rel"]


def test_finish_startup_after_failure(app, toasts):
    _pending(app, state="failed", version="9.9.9", error="locked")
    O.finish_startup(app)
    assert toasts[-1][1] == "warning"
    assert not (app.app_path / S.UPDATE_DIR).exists()


def test_finish_startup_quiet_paths(app, toasts):
    O.finish_startup(app)                                  # no staging dir
    assert toasts == []
    _pending(app, state="staged", version="9.9.9")         # stale download → just cleaned
    O.finish_startup(app)
    assert toasts == [] and not (app.app_path / S.UPDATE_DIR).exists()
