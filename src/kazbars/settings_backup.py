"""
KazBars — Game settings backup & restore.

Backs up the Age of Conan config tree (``%LOCALAPPDATA%\\Funcom\\Conan\\Prefs``
— keybinds, HUD layouts, chat, graphics/audio, waypoints) plus KazBars's own
user data (``profiles/`` + ``settings/kazbars_settings.json``) into a single
portable zip, and restores it later — the recovery path after a Windows
reformat or profile corruption, neither of which AoC guards against itself.

Split into a pure layer (``funcom_prefs_path`` / ``locate_funcom_prefs`` /
``write_backup_zip`` / ``read_manifest`` / ``restore_zip`` — no Tk,
unit-tested) and a Tk dialog/flow layer (``open_backup_dialog`` +
``backup_settings`` / ``restore_settings``), mirroring profile_io's read/
dispatch split. The Tk-layer functions take the KazBarsApp instance first.
"""

import json
import logging
import os
import tkinter as tk
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from ttkbootstrap.dialogs import Messagebox

from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_DIALOG,
    FONT_BODY,
    FONT_SECTION,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import app_toast
from .window_position import restore_window_position

logger = logging.getLogger(__name__)

BACKUP_FORMAT = "kazbars-settings-backup"
BACKUP_VERSION = 1
FUNCOM_ARC = "funcom"
KAZBARS_ARC = "kazbars"
MANIFEST_NAME = "manifest.json"


# ============================================================================
# PURE LAYER — no Tk, unit-tested
# ============================================================================
def funcom_prefs_path():
    """The AoC prefs dir (``%LOCALAPPDATA%\\Funcom\\Conan\\Prefs``) whether or
    not it exists yet. None only if LOCALAPPDATA is unset (never on Windows)."""
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "Funcom" / "Conan" / "Prefs" if local else None


def locate_funcom_prefs():
    """Return the AoC prefs dir if it currently exists on disk, else None."""
    prefs = funcom_prefs_path()
    return prefs if prefs and prefs.is_dir() else None


def _add_tree(zf, root, arc_prefix):
    """Add every file under `root` to `zf` as `arc_prefix/<relpath>`. Skips
    *.tmp; counts unreadable/locked files rather than aborting. Returns
    (added, skipped)."""
    added = skipped = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix == ".tmp":
            continue
        arcname = f"{arc_prefix}/{path.relative_to(root).as_posix()}"
        try:
            zf.write(path, arcname)
            added += 1
        except OSError as e:
            logger.warning("Backup skipped %s: %s", path, e)
            skipped += 1
    return added, skipped


def write_backup_zip(zip_path, *, funcom_dir, profiles_dir, settings_dir, app_version):
    """Build a backup zip at `zip_path` from whichever sources exist: the
    Funcom prefs tree under ``funcom/``, KazBars profiles + the whole
    ``settings/`` dir (so `kazbars_settings.json` plus the Deeps and Live
    Tracker settings come along) under ``kazbars/``. Writes ``manifest.json``
    last. Returns the `sections` dict."""
    sections = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if funcom_dir and Path(funcom_dir).is_dir():
            added, skipped = _add_tree(zf, Path(funcom_dir), FUNCOM_ARC)
            sections["funcom"] = {"files": added, "skipped": skipped, "source": str(funcom_dir)}
        kz = {}
        if profiles_dir and Path(profiles_dir).is_dir():
            added, _ = _add_tree(zf, Path(profiles_dir), f"{KAZBARS_ARC}/profiles")
            kz["profiles"] = added
        if settings_dir and Path(settings_dir).is_dir():
            added, _ = _add_tree(zf, Path(settings_dir), f"{KAZBARS_ARC}/settings")
            kz["settings"] = added
        if kz:
            sections["kazbars"] = kz
        zf.writestr(
            MANIFEST_NAME,
            json.dumps(
                {
                    "format": BACKUP_FORMAT,
                    "version": BACKUP_VERSION,
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "app_version": app_version,
                    "sections": sections,
                },
                indent=2,
            ),
        )
    return sections


def read_manifest(zip_path):
    """Return the parsed manifest if `zip_path` is a KazBars backup, else None."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            data = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, dict) and data.get("format") == BACKUP_FORMAT:
        return data
    return None


def restore_zip(zip_path, *, funcom_dest, kazbars_dest):
    """Extract a backup's sections to their destinations (created as needed —
    a fresh machine has no Funcom folder yet). `funcom_dest` is the AoC prefs
    dir; `kazbars_dest` is app_path() (``profiles/`` and ``settings/`` land
    directly under it). Guards against zip-slip. Returns a per-section count."""
    roots = {FUNCOM_ARC: Path(funcom_dest).resolve(), KAZBARS_ARC: Path(kazbars_dest).resolve()}
    restored = {FUNCOM_ARC: 0, KAZBARS_ARC: 0}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name == MANIFEST_NAME or name.endswith("/"):
                continue
            section, _, rel = name.partition("/")
            if section not in roots or not rel:
                continue
            dest_root = roots[section]
            target = (dest_root / rel).resolve()
            if dest_root not in target.parents:
                logger.warning("Skipping unsafe backup entry: %s", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            restored[section] += 1
    return restored


def _tree_stats(root):
    """Return (total_bytes, file_count) for everything under `root`."""
    size = count = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                size += p.stat().st_size
                count += 1
            except OSError:
                pass
    return size, count


def _funcom_summary(prefs):
    """Summarize a Funcom prefs dir for display: (account_names, char_count,
    total_bytes). Accounts are its immediate subfolders (the top-level
    ``Prefs_*.xml`` are global, not accounts); characters are the ``Char*``
    subfolders within each account."""
    accounts = sorted(p.name for p in prefs.iterdir() if p.is_dir())
    chars = sum(
        1
        for acct in accounts
        for c in (prefs / acct).iterdir()
        if c.is_dir() and c.name.lower().startswith("char")
    )
    size, _files = _tree_stats(prefs)
    return accounts, chars, size


def _human_size(num):
    """Human-readable byte count, e.g. '1.8 MB'."""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# ============================================================================
# TK LAYER — dialog + flows (app-first-arg)
# ============================================================================
def open_backup_dialog(app):
    """Open the modal Backup & Restore dialog: shows what's included and offers
    Back up… / Restore… actions."""
    dialog = tk.Toplevel(app)
    dialog.title("Backup & Restore Settings")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    width = 480
    restore_window_position(dialog, "settings_backup", width, 400, app, resizable=False)
    create_dialog_header(dialog, "Backup & Restore", MODULE_COLORS["grids"], width=width)

    content = ttk.Frame(dialog)
    content.pack(fill="both", expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    prefs = locate_funcom_prefs()
    accounts = []
    if prefs:
        accounts, chars, size = _funcom_summary(prefs)
        aoc_line = (
            f"Age of Conan settings — {len(accounts)} account(s), "
            f"{chars} character(s) ({_human_size(size)})"
        )
        aoc_color = THEME_COLORS["body"]
    else:
        aoc_line = "Age of Conan settings — not detected on this PC"
        aoc_color = THEME_COLORS["muted"]

    n_profiles = sum(1 for _ in app.profiles_path.glob("*.json"))

    ttk.Label(
        content, text="What's included", font=FONT_SECTION, foreground=THEME_COLORS["heading"]
    ).pack(anchor="w", pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content, text=f"•  {aoc_line}", font=FONT_BODY, foreground=aoc_color).pack(
        anchor="w", pady=(0, PAD_XS)
    )
    if accounts:
        ttk.Label(
            content,
            text="     " + ", ".join(accounts),
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
            wraplength=width - PAD_TAB * 4,
            justify="left",
        ).pack(anchor="w", pady=(0, PAD_XS))
    ttk.Label(
        content,
        text=f"•  KazBars data — {n_profiles} profile(s) + settings (app, Deeps, Live Tracker)",
        font=FONT_BODY,
        foreground=THEME_COLORS["body"],
        wraplength=width - PAD_TAB * 4,
        justify="left",
    ).pack(anchor="w", pady=(0, PAD_SMALL))

    ttk.Label(
        content,
        text="⚠  Close Age of Conan before backing up or restoring.",
        font=FONT_SMALL,
        foreground=THEME_COLORS["warning"],
    ).pack(anchor="w", pady=(PAD_XS, PAD_SMALL))

    ttk.Separator(content, orient="horizontal").pack(fill="x", pady=PAD_SMALL)

    ttk.Label(
        content,
        text="Restoring replaces your current settings. A pre-restore "
        "snapshot is saved automatically so you can undo.",
        font=FONT_SMALL,
        foreground=THEME_COLORS["muted"],
        wraplength=width - PAD_TAB * 4,
    ).pack(anchor="w", pady=(0, PAD_SMALL))

    btns = ttk.Frame(content)
    btns.pack(fill="x", pady=(PAD_SMALL, 0))
    ttk.Button(
        btns,
        text="Back up…",
        bootstyle="success",
        width=BTN_DIALOG,
        command=lambda: backup_settings(app, dialog),
    ).pack(side="left")
    ttk.Button(
        btns,
        text="Restore…",
        bootstyle="outline",
        width=BTN_DIALOG,
        command=lambda: restore_settings(app, dialog),
    ).pack(side="left", padx=(PAD_XS, 0))
    ttk.Button(
        btns, text="Close", bootstyle="secondary", width=BTN_DIALOG, command=dialog.destroy
    ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)


def backup_settings(app, dialog):
    """Write a backup zip to a user-chosen path."""
    path = filedialog.asksaveasfilename(
        title="Save Settings Backup",
        initialfile=f"KazBars_Backup_{datetime.now():%Y-%m-%d}.zip",
        defaultextension=".zip",
        filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        sections = write_backup_zip(
            path,
            funcom_dir=locate_funcom_prefs(),
            profiles_dir=app.profiles_path,
            settings_dir=app.settings_path,
            app_version=app.app_version,
        )
    except OSError as e:
        Messagebox.show_error(
            "Failed to write the backup.\n\nCheck that the destination isn't "
            f"read-only or in use by another program.\n\n({e})",
            title="Backup Failed",
        )
        return
    dialog.destroy()
    funcom_n = sections.get("funcom", {}).get("files", 0)
    profiles_n = sections.get("kazbars", {}).get("profiles", 0)
    app_toast(app, f"Backed up {funcom_n} AoC files + {profiles_n} profile(s)", "success", 8)


def restore_settings(app, dialog):
    """Restore settings from a user-chosen backup zip, snapshotting current
    state first so a bad restore is reversible."""
    path = filedialog.askopenfilename(
        title="Restore Settings Backup",
        filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")],
    )
    if not path:
        return

    manifest = read_manifest(path)
    if not manifest:
        Messagebox.show_error("This file isn't a KazBars settings backup.", title="Restore Failed")
        return

    funcom_dest = funcom_prefs_path()
    if funcom_dest is None:
        Messagebox.show_error(
            "Couldn't locate the Windows LocalAppData folder.", title="Restore Failed"
        )
        return

    if (
        Messagebox.yesno(
            f"Restore settings from this backup?\n\nCreated: {manifest.get('created', 'unknown')}\n\n"
            "Your current Age of Conan and KazBars settings will be replaced — "
            "close Age of Conan first.\n\n"
            "A pre-restore snapshot of your current settings is saved automatically.",
            title="Restore Settings",
        )
        != "Yes"
    ):
        return

    # Best-effort safety snapshot of current state (don't block restore on it).
    snapshot = app.app_path / f"KazBars_PreRestore_{datetime.now():%Y%m%d_%H%M%S}.zip"
    try:
        write_backup_zip(
            snapshot,
            funcom_dir=locate_funcom_prefs(),
            profiles_dir=app.profiles_path,
            settings_dir=app.settings_path,
            app_version=app.app_version,
        )
    except OSError as e:
        logger.warning("Pre-restore snapshot failed: %s", e)
        snapshot = None

    try:
        restored = restore_zip(path, funcom_dest=funcom_dest, kazbars_dest=app.app_path)
    except OSError as e:
        tail = f"\n\nA pre-restore snapshot was saved to:\n{snapshot}" if snapshot else ""
        Messagebox.show_error(
            f"Restore failed partway through.\n\n({e}){tail}", title="Restore Failed"
        )
        return

    # The running app holds settings in memory and re-saves on exit; resync from
    # disk so the freshly-restored kazbars_settings.json isn't clobbered.
    app.settings.reload()

    dialog.destroy()
    snap_line = f"\n\nPre-restore snapshot: {snapshot}" if snapshot else ""
    Messagebox.show_info(
        f"Restored {restored['funcom']} AoC files + {restored['kazbars']} KazBars files.\n\n"
        f"Restart KazBars to fully apply window and game-folder settings.{snap_line}",
        title="Restore Complete",
    )
