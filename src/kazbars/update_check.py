"""
KazBars — Update check.

Background check for a newer GitHub release. The worker thread fetches the
latest release tag; if it's newer than the running version, it schedules a
named main-thread dispatcher that toasts the user. The dispatcher is named
(not inlined) so the cross-thread boundary is visible at every call site.
"""

import json
import logging
import re
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser

from .ui_widgets import app_toast

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/kazour/Kazbars/releases/latest"
FALLBACK_RELEASES_URL = "https://github.com/kazour/Kazbars/releases/latest"


def check_for_updates(app, current_version):
    """Fire-and-forget: toasts the app on the main thread if a newer release exists."""
    threading.Thread(target=_worker, args=(app, current_version), daemon=True).start()


def fetch_latest(current_version):
    """Blocking release lookup. Returns ('update', tag, url) when a newer
    release exists, ('current', None, None) when up to date, or
    ('error', None, None) on any network/parse failure. Shared by the launch
    check and the About popup's manual check."""
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = (data.get('tag_name') or '').lstrip('v')
        if not tag or _parts(tag) <= _parts(current_version):
            return ('current', None, None)
        return ('update', tag, data.get('html_url', FALLBACK_RELEASES_URL))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return ('error', None, None)


def _worker(app, current_version):
    status, tag, url = fetch_latest(current_version)
    if status != 'update':
        return
    try:
        app.after(0, _show_update_toast, app, tag, url)
    except tk.TclError:
        pass


def _parts(version):
    """Leading digits of each dot-component, stopping at the first non-numeric
    one — so a suffixed tag like '2.3.0-rc1' still compares as (2, 3, 0)
    instead of silently reading as up-to-date."""
    parts = []
    for p in version.split('.'):
        m = re.match(r'\d+', p)
        if m is None:
            break
        parts.append(int(m.group()))
    return tuple(parts)


def _show_update_toast(app, tag, url):
    """Main-thread dispatcher. Bails if the app was closed while the fetch was in flight."""
    try:
        if not app.winfo_exists():
            return
        app_toast(
            app,
            f"Update available: v{tag} — click for release notes",
            'info', 12,
            on_click=lambda: webbrowser.open(url),
        )
    except tk.TclError:
        pass


def check_for_updates_manual(app, current_version):
    """Explicit user check (Updates ▸ Check for app updates now) — unlike the
    silent launch check, always answers with a toast."""
    def worker():
        status, tag, url = fetch_latest(current_version)
        try:
            app.after(0, _show_manual_result, app, status, tag, url)
        except tk.TclError:
            pass
    threading.Thread(target=worker, daemon=True).start()


def _show_manual_result(app, status, tag, url):
    """Main-thread dispatcher for the manual check."""
    try:
        if not app.winfo_exists():
            return
        if status == 'update':
            _show_update_toast(app, tag, url)
        elif status == 'current':
            app_toast(app, "You're on the latest version", 'success')
        else:
            app_toast(app, "Couldn't reach GitHub — check your connection", 'warning')
    except tk.TclError:
        pass
