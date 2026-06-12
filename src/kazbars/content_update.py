"""KazBars — OTA reference-content updates (silent, reversible, never captive).

On launch the app polls a published manifest; if it advertises a newer
``content_version`` than the client holds (``prefs.json.content_version``), the
running app is new enough (``min_app_version``), and the auto-update toggle is
on, this downloads the pinned ``Database.json`` + ``Default.json`` payloads,
verifies sha256, **atomically** swaps them into ``userdata/content/`` with a
``.bak/`` rollback, re-merges the live DB, and shows **one** toast. Anything that
fails swaps nothing. It never applies while the DB editor has unsaved edits or a
build is running — it defers to the next launch.

Three version markers, kept distinct:
  - the **manifest** (server, ``ota/manifest.json`` on ``main``) advertises the
    latest ``content_version``;
  - ``prefs.json.content_version`` (client) is the **authoritative comparison
    key**, defaulting to the shipped ``CONTENT_BASELINE_VERSION``;
  - ``userdata/content/manifest.json`` (client) is the on-disk record of what is
    *currently in* ``content/`` (the step-5 commit marker), not the comparison
    source.

Split: pure helpers (``parse_manifest``/``is_newer``/``app_supports``/
``verify_sha256``/``apply_content``/``rollback``/``summarize_changes``) carry the
logic and are unit-tested with an injected downloader (no network in tests); a
thin Tk dispatcher (``check_and_apply``/``revert``) does the threading + toasts.
Mirrors ``update_check``'s shape but doesn't cross-import it.
"""

import hashlib
import json
import logging
import os
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import CONTENT_BASELINE_VERSION, buff_db_layers
from .ui_widgets import app_toast
from .userdata import content_dir

logger = logging.getLogger(__name__)

# The published manifest pointer. Overridable via env for local/CI OTA testing
# (a fake manifest + payloads); unset = the live GitHub raw URL on main.
MANIFEST_URL = os.environ.get(
    "KAZBARS_OTA_MANIFEST_URL",
    "https://raw.githubusercontent.com/kazour/Kazbars/main/ota/manifest.json",
)
RELEASES_URL = "https://github.com/kazour/Kazbars/releases/latest"
DOWNLOAD_TIMEOUT = 8
MANIFEST_NAME = "manifest.json"
# The reference files OTA manages in content/ (snapshot + rollback cover these).
CONTENT_FILES = ("Database.json", "Default.json")


# =========================================================================== #
# PURE HELPERS (no Tk — unit-tested with an injected downloader)               #
# =========================================================================== #

def _version_parts(version):
    """('2.1.0') -> (2, 1, 0) for ordered comparison; () on garbage. Inlined
    rather than importing update_check (the two update modules stay decoupled)."""
    try:
        return tuple(int(p) for p in str(version).split('.'))
    except ValueError:
        return ()


def parse_manifest(raw):
    """Parse + validate a manifest (bytes or str). Returns the dict, or None if
    malformed — a missing/wrong-typed required field rejects the whole thing."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get('content_version'), int):
        return None
    if not isinstance(data.get('min_app_version'), str):
        return None
    files = data.get('files')
    if not isinstance(files, dict) or not files:
        return None
    for info in files.values():
        if not isinstance(info, dict):
            return None
        if not isinstance(info.get('url'), str) or not isinstance(info.get('sha256'), str):
            return None
    return data


def is_newer(manifest, current_content_version):
    """True if the manifest advertises content newer than the client holds."""
    return int(manifest['content_version']) > int(current_content_version)


def app_supports(manifest, app_version):
    """True if the running app is new enough for this content (``app_version >=
    min_app_version``) — the app-compat boundary that enforces DB+Default
    moving together."""
    return _version_parts(app_version) >= _version_parts(manifest['min_app_version'])


def verify_sha256(data, expected_hex):
    """Constant-shape sha256 check of downloaded bytes against the manifest."""
    return hashlib.sha256(data).hexdigest() == (expected_hex or '').lower()


def summarize_changes(old_buffs, new_buffs):
    """``(added, changed)`` counts between two buff lists, keyed on ``ids[0]``."""
    old_by = {}
    for b in old_buffs:
        key = buff_db_layers._identity(b)
        if key is not None:
            old_by[key] = b
    added = changed = 0
    for b in new_buffs:
        key = buff_db_layers._identity(b)
        if key is None:
            continue
        if key not in old_by:
            added += 1
        elif not buff_db_layers._buffs_equal(old_by[key], b):
            changed += 1
    return added, changed


def _read_content_manifest(content_path):
    """The applied-content marker (``content/manifest.json``), or None."""
    try:
        p = Path(content_path) / MANIFEST_NAME
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _applied_version(content_path):
    """The content_version currently in ``content/`` (from its marker), or the
    shipped baseline when ``content/`` holds no OTA content."""
    m = _read_content_manifest(content_path)
    v = m.get('content_version') if m else None
    return v if isinstance(v, int) else CONTENT_BASELINE_VERSION


def _is_consistent(content_path):
    """True iff ``content/`` matches its own commit marker — every payload the
    marker lists is present with the recorded sha256. Because the marker is
    written LAST (step 5), a state that died mid-swap (a payload already replaced
    while the marker still names the old one) fails this check. ``apply_content``
    snapshots a prior state into ``.bak/prev/`` only when it is consistent, so a
    half-applied attempt can never become a rollback target — revert then falls
    back to the always-consistent stock floor instead of a mismatched
    Database/Default pair. No marker (first-ever / cleared) → not consistent."""
    m = _read_content_manifest(content_path)
    if not m:
        return False
    files = m.get('files')
    if not isinstance(files, dict) or not files:
        return False
    content_path = Path(content_path)
    for name, info in files.items():
        p = content_path / name
        if not p.exists() or not isinstance(info, dict):
            return False
        if not verify_sha256(p.read_bytes(), info.get('sha256', '')):
            return False
    return True


def apply_content(content_path, manifest, payloads):
    """Atomic swap (steps 3-5; download + verify happen in the caller):
    snapshot the current ``content/`` into ``.bak/prev/``, stage every verified
    payload into ``.bak/incoming/`` and then ``os.replace`` them back-to-back,
    and write ``content/manifest.json`` LAST as the commit marker. A crash
    between the replaces and the marker re-applies next launch (sha256 matches) —
    never a half-applied state. Returns the applied version."""
    content_path = Path(content_path)
    content_path.mkdir(parents=True, exist_ok=True)
    prev = content_path / ".bak" / "prev"
    incoming = content_path / ".bak" / "incoming"
    prev.mkdir(parents=True, exist_ok=True)
    incoming.mkdir(parents=True, exist_ok=True)

    # 3. Snapshot the current content/ (payload files + marker) into prev/ so
    #    revert can restore it — but ONLY a state that matches its own commit
    #    marker (see _is_consistent). A half-applied prior attempt, or a first-ever
    #    update with no prior content, is recorded as absent (its prev copy is
    #    removed), so a later revert falls back to the always-consistent stock
    #    floor rather than a mismatched Database/Default pair.
    committed = _is_consistent(content_path)
    for name in (*payloads, MANIFEST_NAME):
        src = content_path / name
        dst = prev / name
        if committed and src.exists():
            dst.write_bytes(src.read_bytes())
        elif dst.exists():
            dst.unlink()

    # 4. Stage every verified payload fully, THEN replace them back-to-back —
    #    all the fallible work (writing the temp copies) happens before any swap,
    #    so the only gap left is between consecutive same-volume os.replace calls:
    #    the half-applied window is as tight as the filesystem allows.
    staged = []
    for name, data in payloads.items():
        tmp = incoming / name
        tmp.write_bytes(data)
        staged.append((tmp, content_path / name))
    for tmp, dst in staged:
        os.replace(tmp, dst)

    # 5. Marker LAST — the applied version only advances once both payloads land.
    (content_path / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return {'content_version': manifest['content_version']}


def rollback(content_path):
    """Restore ``content/`` from ``.bak/prev/`` (the previous payloads + marker).
    A file absent from ``prev/`` is removed — reverting a first-ever update
    clears ``content/`` back to the shipped stock floor. User deltas are never
    touched. Returns True if anything was restored."""
    content_path = Path(content_path)
    prev = content_path / ".bak" / "prev"
    if not prev.exists():
        return False
    restored = False
    for name in (*CONTENT_FILES, MANIFEST_NAME):
        src = prev / name
        dst = content_path / name
        if src.exists():
            dst.write_bytes(src.read_bytes())
            restored = True
        elif dst.exists():
            dst.unlink()
            restored = True
    return restored


def _download(url, timeout=DOWNLOAD_TIMEOUT):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


# =========================================================================== #
# TK DISPATCHER (thread + main-thread hops + toasts)                          #
# =========================================================================== #

def check_and_apply(app, app_version, current_content_version, *, manual=False, downloader=None):
    """Fire-and-forget OTA check. Auto runs only with the toggle on; ``manual``
    (Check now) runs regardless and reports the outcome. Network is on a daemon
    thread; the swap + re-merge + toast hop to the main thread (and defer if the
    user is mid-edit or building)."""
    if not manual and not app.settings.get('auto_update_content', True):
        return
    threading.Thread(
        target=_worker,
        args=(app, app_version, current_content_version),
        kwargs={'manual': manual, 'downloader': downloader or _download},
        daemon=True,
    ).start()


def _post(app, fn, *args):
    """Schedule `fn(*args)` on the Tk main loop; quietly no-op if the app is gone."""
    try:
        app.after(0, fn, *args)
    except (RuntimeError, tk.TclError):
        pass


def _worker(app, app_version, current_content_version, *, manual, downloader):
    try:
        manifest = parse_manifest(downloader(MANIFEST_URL))
        if manifest is None:
            if manual:
                _post(app, _notify, app, "Couldn't check for updates — try again later", 'warning')
            return
        if not app_supports(manifest, app_version):
            _post(app, _notify_app_update, app)
            return
        if not is_newer(manifest, current_content_version):
            if manual:
                _post(app, _notify, app, "Buff database is already up to date", 'info')
            return
        payloads = {}
        for name, info in manifest['files'].items():
            data = downloader(info['url'])
            if not verify_sha256(data, info['sha256']):
                logger.warning("OTA payload %s failed sha256 — aborting", name)
                if manual:
                    _post(app, _notify, app, "Update download was corrupt — nothing changed", 'warning')
                return
            payloads[name] = data
        _post(app, _apply_on_main, app, manifest, payloads)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        logger.debug("OTA check failed: %s", e)
        if manual:
            _post(app, _notify, app, "Couldn't reach the update server", 'warning')


def _apply_on_main(app, manifest, payloads):
    """Main thread: apply guard, atomic swap, re-merge, one toast. Defers (does
    nothing — retries next launch) if the DB editor is dirty or a build runs."""
    try:
        if not app.winfo_exists():
            return
        db_panel = getattr(app, 'db_panel', None)
        if (db_panel is not None and getattr(db_panel, 'modified', False)) or getattr(app, '_building', False):
            logger.info("OTA deferred — DB editor dirty or build running")
            return
        old_buffs = list(app.database.buffs)
        apply_content(content_dir(), manifest, payloads)
        app.settings.set('content_version', manifest['content_version'])
        app.settings.save()
        try:
            app.database.reload()
        except Exception:
            logger.exception("OTA re-merge failed — rolling back")
            rollback(content_dir())
            app.settings.set('content_version', _applied_version(content_dir()))
            app.settings.save()
            app.database.reload()
            _notify(app, "Buff-database update failed — reverted to the previous version", 'warning')
            return
        _refresh_db_views(app, db_panel)
        added, changed = summarize_changes(old_buffs, app.database.buffs)
        notes = manifest.get('notes', '')
        _notify(app, f"Buff database updated — {added} added, {changed} changed", 'success',
                on_click=lambda: _show_changes(added, changed, notes))
    except (OSError, tk.TclError) as e:
        logger.warning("OTA apply failed: %s", e)


def revert(app):
    """Updates ▸ Revert last buff-database update — restore content/ from .bak/prev/
    and re-merge. User deltas are untouched."""
    if not rollback(content_dir()):
        _notify(app, "Nothing to revert — no buff-database update has been applied", 'info')
        return
    app.settings.set('content_version', _applied_version(content_dir()))
    app.settings.save()
    app.database.reload()
    _refresh_db_views(app, getattr(app, 'db_panel', None))
    _notify(app, "Reverted to the previous buff database", 'success')


def _refresh_db_views(app, db_panel):
    """Re-pull the editor's floor + redraw the DB list after a live re-merge.
    Grids resolve against `app.database` at build time, so no card rebuild is
    forced (that would risk clobbering an in-progress grid edit)."""
    if db_panel is not None:
        try:
            db_panel._refresh_floor()
            db_panel.refresh_list()
        except tk.TclError:
            pass


def _notify(app, message, style='info', on_click=None):
    try:
        if app.winfo_exists():
            app_toast(app, message, style, 12, on_click=on_click)
    except tk.TclError:
        pass


def _notify_app_update(app):
    """Compat gate: newer content needs a newer app. Surfaced once per session."""
    try:
        if not app.winfo_exists() or getattr(app, '_ota_app_update_notified', False):
            return
        app._ota_app_update_notified = True
        app_toast(app, "New buffs are available — update KazBars to get them", 'info', 12,
                  on_click=lambda: webbrowser.open(RELEASES_URL))
    except tk.TclError:
        pass


def _show_changes(added, changed, notes):
    """Click-through from the update toast — a short what-changed note."""
    from ttkbootstrap.dialogs import Messagebox
    body = f"{added} added, {changed} changed."
    if notes:
        body += f"\n\n{notes}"
    body += "\n\nTo undo, use Updates ▸ Revert last buff-database update."
    Messagebox.show_info(body, title="Buff Database Updated")
