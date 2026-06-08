"""KazBars — userdata/ storage root (paths + layout). Pure, no Tk.

All user + machine-local data lives under one ``userdata/`` folder next to the
exe (``app_path()/userdata``), created fresh on first launch. ``assets/`` stays
read-only — the editor and the OTA updater never write there, so a reinstall
always has a clean floor.

There is **no legacy migration**: a fresh install (and every tester) starts at
defaults; any pre-overhaul ``settings/`` or ``profiles/`` sitting next to the exe
are ignored — never read, moved, archived, or deleted. ``ensure_layout()`` is the
whole startup-data story.

Layout::

    userdata/
      prefs.json                     ← machine-local prefs (schema in prefs.py)
      settings/                      ← deeps / live_tracker / damageinfo settings
      profiles/*.json
      database_user.json             ← user buff deltas (seeded empty; Phase 3)
      content/                       ← OTA reference content (Phase 4)
        .bak/                        ← OTA rollback snapshots (Phase 4)
"""

import json
import logging
from pathlib import Path

from .paths import app_path

logger = logging.getLogger(__name__)

PREFS_FILENAME = "prefs.json"
DATABASE_USER_FILENAME = "database_user.json"

# Seed for a fresh database_user.json — the v2 delta format Phase 3's DeltaStore
# reads (user buff additions/overrides in `buffs`, hidden stock/content buffs as
# tombstones in `deleted`).
_EMPTY_USER_DB = {"version": 2, "buffs": [], "deleted": []}


def userdata_root() -> Path:
    return app_path() / "userdata"


def prefs_path() -> Path:
    return userdata_root() / PREFS_FILENAME


def settings_dir() -> Path:
    return userdata_root() / "settings"


def profiles_dir() -> Path:
    return userdata_root() / "profiles"


def database_user_path() -> Path:
    return userdata_root() / DATABASE_USER_FILENAME


def content_dir() -> Path:
    return userdata_root() / "content"


def content_backup_dir() -> Path:
    return content_dir() / ".bak"


def ensure_layout() -> None:
    """Create the ``userdata/`` tree and seed an empty ``database_user.json`` +
    ``content/`` dirs if absent. Idempotent — a second run is a no-op. Never
    raises; failures are logged and the app falls back to shipped stock."""
    try:
        for d in (
            userdata_root(),
            settings_dir(),
            profiles_dir(),
            content_dir(),
            content_backup_dir(),
        ):
            d.mkdir(parents=True, exist_ok=True)
        db_user = database_user_path()
        if not db_user.exists():
            db_user.write_text(json.dumps(_EMPTY_USER_DB, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error("Could not create userdata layout: %s", e)
