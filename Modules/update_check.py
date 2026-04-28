"""
Kaz Grids — Update check.

Background check for a newer GitHub release. The worker thread fetches the
latest release tag; if it's newer than the running version, it schedules a
named main-thread dispatcher that toasts the user. The dispatcher is named
(not inlined) so the cross-thread boundary is visible at every call site.
"""

import json
import logging
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser

from .ui_widgets import app_toast

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/kazour/Kaz-Grids/releases/latest"
FALLBACK_RELEASES_URL = "https://github.com/kazour/Kaz-Grids/releases/latest"


def check_for_updates(app, current_version):
    """Fire-and-forget: toasts the app on the main thread if a newer release exists."""
    threading.Thread(target=_worker, args=(app, current_version), daemon=True).start()


def _worker(app, current_version):
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = (data.get('tag_name') or '').lstrip('v')
        if not tag or tag == current_version:
            return
        if _parts(tag) <= _parts(current_version):
            return
        url = data.get('html_url', FALLBACK_RELEASES_URL)
        app.after(0, _show_update_toast, app, tag, url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, tk.TclError):
        pass


def _parts(version):
    try:
        return tuple(int(p) for p in version.split('.'))
    except ValueError:
        return ()


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
