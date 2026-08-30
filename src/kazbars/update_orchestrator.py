"""KazBars — the one update routine (Tk dispatcher).

One launch check and one "Check for updates now" cover both channels: the
app release on GitHub and the OTA buff database. The app comes first — a
newer release is offered (click to download, click again to restart) and the
content check is skipped, since the new build ships current content;
otherwise the content channel runs as before (`content_update`). Every
cross-thread and close-boundary hop is a named function.

Phase lives on the app: `_app_update_phase` is None → 'downloading' →
'ready', with `_app_update_staged` holding the staged exe once ready. The
pure work (download, verify, unpack, apply) is `self_update`.
"""

import logging
import os
import threading
import tkinter as tk
import webbrowser

from . import content_update, self_update, update_check
from .content_update import _post
from .ui_widgets import app_toast

logger = logging.getLogger(__name__)

# One toast slot for the whole app-update story: every re-emit (progress,
# ready, failure) coalesces into it instead of stacking.
TOAST_KEY = 'app-update'


def check_on_launch(app):
    threading.Thread(target=_check_worker, args=(app, False), daemon=True).start()


def check_now(app):
    """Updates ▸ Check for updates now — same path, but reports every outcome."""
    threading.Thread(target=_check_worker, args=(app, True), daemon=True).start()


def _check_worker(app, manual, *, fetch=None):
    """Worker thread. App release first; the content channel only when there
    is nothing to install (a manual check that can't reach GitHub stops here
    rather than reporting twice)."""
    status, release = (fetch or update_check.fetch_release)(app.app_version)
    if status == 'update':
        _post(app, _offer_install, app, release)
        return
    if status == 'error' and manual:
        _post(app, _toast, app, "Couldn't reach GitHub — check your connection", 'warning')
        return
    content_update.check_and_apply(
        app, app.app_version, app.settings.get('content_version'), manual=manual)


def _offer_install(app, release):
    """Main thread. A download already running is left alone; a staged tree
    waiting for its restart is offered again."""
    phase = getattr(app, '_app_update_phase', None)
    if phase == 'downloading':
        return
    if phase == 'ready':
        _show_ready(app, release, app._app_update_staged)
        return
    tag = update_check.release_tag(release)
    _toast(app, f"KazBars v{tag} is available — click to install", 'info',
           duration=20, on_click=lambda: start_install(app, release))


def start_install(app, release):
    """Click 1 — stage the release in the background. Public: the About
    popup's check lands here too."""
    if app._app_update_phase is not None:
        _offer_install(app, release)
        return
    app._app_update_phase = 'downloading'
    threading.Thread(target=_install_worker, args=(app, release), daemon=True).start()


def _install_worker(app, release, *, stage=None):
    tag = update_check.release_tag(release)
    try:
        staged_exe = (stage or self_update.stage_release)(
            app.app_path, release,
            progress=lambda done, total: _post(app, _show_progress, app, tag, done, total))
    except self_update.StageError as e:
        _post(app, _show_failed, app, release, str(e))
        return
    _post(app, _show_ready, app, release, staged_exe)


def _show_progress(app, tag, done, total):
    if total and done >= total:
        _toast(app, f"Unpacking KazBars v{tag}…", 'info', duration=30)
        return
    pct = done * 100 // total if total else 0
    _toast(app, f"Downloading KazBars v{tag} — {pct}%", 'info', duration=30)


def _show_ready(app, release, staged_exe):
    app._app_update_phase = 'ready'
    app._app_update_staged = staged_exe
    tag = update_check.release_tag(release)
    _toast(app, f"KazBars v{tag} downloaded — click to restart and install", 'success',
           duration=30, on_click=lambda: restart_to_install(app, staged_exe))


def restart_to_install(app, staged_exe):
    """Click 2 — the normal close path first (its unsaved-work guards may
    cancel, in which case the staged tree waits), then hand off to the staged
    exe, which waits for this process to exit before swapping the install."""
    if not app._on_close():
        return
    self_update.spawn_apply(staged_exe, app.app_path, os.getpid())


def _show_failed(app, release, message):
    app._app_update_phase = None
    app._app_update_staged = None
    self_update.discard_staging(app.app_path)
    url = release.get('html_url') or update_check.FALLBACK_RELEASES_URL
    _toast(app, f"{message} — click to open the release page", 'warning',
           on_click=lambda: webbrowser.open(url))


def finish_startup(app):
    """Main thread, shortly after launch: report how an apply went and drop
    the staging dir. Deferred because the staged exe is still tearing down
    while the new app boots; best-effort — leftovers go on the next launch."""
    action, pending = self_update.startup_action(app.app_path, app.app_version)
    if action == 'none':
        return
    url = (pending or {}).get('html_url') or update_check.FALLBACK_RELEASES_URL
    if action == 'updated':
        _toast(app, f"KazBars updated to v{app.app_version} — click for what's new",
               'success', on_click=lambda: webbrowser.open(url))
    elif action == 'failed':
        _toast(app, "The update couldn't be installed — click to download it manually",
               'warning', on_click=lambda: webbrowser.open(url))
    self_update.discard_staging(app.app_path)


def _toast(app, message, style, *, duration=12, on_click=None):
    try:
        if app.winfo_exists():
            app_toast(app, message, style, duration, key=TOAST_KEY, on_click=on_click)
    except tk.TclError:
        pass
