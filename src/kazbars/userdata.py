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
      prefs3_snapshot.xml            ← Prefs_3.xml copy, insurance for Repair
      profiles/*.json                ← profile documents (identity = in-doc id)
        *.json.bak                   ← per-profile session-start snapshots
        trash/                       ← deleted profiles, pruned to the 10 newest
      database_user.json             ← user buff deltas (seeded empty; Phase 3)
      content/                       ← OTA reference content (Phase 4)
        .bak/                        ← OTA rollback snapshots (Phase 4)
"""

import json
import logging
import os
from pathlib import Path

from .paths import app_path

logger = logging.getLogger(__name__)

PREFS_FILENAME = "prefs.json"
DATABASE_USER_FILENAME = "database_user.json"
PREFS3_SNAPSHOT_FILENAME = "prefs3_snapshot.xml"

# Seed for a fresh database_user.json — the v2 delta format Phase 3's DeltaStore
# reads (user buff additions/overrides in `buffs`, hidden stock/content buffs as
# tombstones in `deleted`).
_EMPTY_USER_DB = {"version": 2, "buffs": [], "deleted": []}


def userdata_root() -> Path:
    return app_path() / "userdata"


def prefs_path() -> Path:
    return userdata_root() / PREFS_FILENAME


def profiles_dir() -> Path:
    return userdata_root() / "profiles"


def profiles_trash_dir() -> Path:
    return profiles_dir() / "trash"


def database_user_path() -> Path:
    return userdata_root() / DATABASE_USER_FILENAME


def content_dir() -> Path:
    return userdata_root() / "content"


def content_backup_dir() -> Path:
    return content_dir() / ".bak"


def funcom_prefs_path() -> Path | None:
    """The *game's* prefs dir (``%LOCALAPPDATA%\\Funcom\\Conan\\Prefs``), whether or
    not it exists yet. None only if LOCALAPPDATA is unset (never on Windows).

    Outside ``userdata/`` — it belongs to Age of Conan, not to us — but resolved
    here because two unrelated features read it (Backup & Restore bundles the
    whole tree; the persistence layer reads `Prefs_3.xml` inside it), and a
    second copy of this path is a silent way for them to drift apart.
    """
    local = os.environ.get('LOCALAPPDATA')
    return Path(local) / "Funcom" / "Conan" / "Prefs" if local else None


def prefs3_snapshot_path() -> Path:
    """Our copy of the game's Prefs_3.xml, taken while the install is healthy so
    Repair can put back archives a patcher run stripped. Deliberately outside the
    backup allowlist — it mirrors game state, not the user's own data."""
    return userdata_root() / PREFS3_SNAPSHOT_FILENAME


def ensure_layout() -> None:
    """Create the ``userdata/`` tree and seed an empty ``database_user.json`` +
    ``content/`` dirs if absent. Idempotent — a second run is a no-op. Never
    raises; failures are logged and the app falls back to shipped stock."""
    try:
        for d in (
            userdata_root(),
            profiles_dir(),
            profiles_trash_dir(),
            content_dir(),
            content_backup_dir(),
        ):
            d.mkdir(parents=True, exist_ok=True)
        db_user = database_user_path()
        if not db_user.exists():
            db_user.write_text(json.dumps(_EMPTY_USER_DB, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error("Could not create userdata layout: %s", e)
