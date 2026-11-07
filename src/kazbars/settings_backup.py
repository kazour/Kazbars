"""
KazBars — Game settings backup & restore.

Backs up the Age of Conan config tree (``%LOCALAPPDATA%\\Funcom\\Conan\\Prefs``
— keybinds, HUD layouts, chat, graphics/audio, waypoints) plus KazBars's own
user data from ``userdata/`` — an allowlist of ``profile.yml`` (and a 3.1
``profiles/`` library while one is still there), ``database_user.json``
(custom buffs), plus the machine-local ``prefs.json`` —
into a single portable zip, and restores it later. It is the recovery path after
a Windows reformat or profile corruption, neither of which AoC guards itself.

The allowlist is deliberate: the OTA ``content/`` cache (and its ``.bak/``
rollbacks) is regenerable and machine-bound, so it never enters a backup.
``prefs.json`` IS written to the zip but is machine-local (window geometry, game
path), so restore leaves it out by default — a checkbox opts in for a same-PC
restore.

Split into a pure layer (``locate_funcom_prefs`` over ``userdata.funcom_prefs_path`` /
``write_backup_zip`` / ``read_manifest`` / ``restore_zip`` — no Tk,
unit-tested) and a Tk dialog/flow layer (``open_backup_dialog`` +
``backup_settings`` / ``restore_settings``), mirroring profile_io's read/
dispatch split. The Tk-layer functions take the KazBarsApp instance first.
"""

import json
import logging
import tkinter as tk
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from ttkbootstrap.dialogs import Messagebox

from . import profile_io
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
from .ui_widgets import app_toast, confirm
from .userdata import (
    DATABASE_USER_FILENAME,
    PREFS_FILENAME,
    database_user_path,
    funcom_prefs_path,
    prefs_path,
    profile_path,
    profiles_dir,
    userdata_root,
)
from .window_position import center_on_parent

logger = logging.getLogger(__name__)

BACKUP_FORMAT = "kazbars-settings-backup"
BACKUP_VERSION = 1
FUNCOM_ARC = "funcom"
KAZBARS_ARC = "kazbars"
PROFILE_ARC = "profile.yml"
MANIFEST_NAME = "manifest.json"


# ============================================================================
# PURE LAYER — no Tk, unit-tested
# ============================================================================
def locate_funcom_prefs():
    """Return the AoC prefs dir if it currently exists on disk, else None."""
    prefs = funcom_prefs_path()
    return prefs if prefs and prefs.is_dir() else None


def _add_tree(zf, root, arc_prefix, skip_suffixes=(), skip_dirs=()):
    """Add every file under `root` to `zf` as `arc_prefix/<relpath>`. Skips
    *.tmp plus any `skip_suffixes`/`skip_dirs` (top-level dir names) the
    caller names; counts unreadable/locked files rather than aborting. Returns
    (added, skipped)."""
    added = skipped = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix in (".tmp", *skip_suffixes):
            continue
        rel = path.relative_to(root)
        if skip_dirs and rel.parts[0] in skip_dirs:
            continue
        arcname = f"{arc_prefix}/{rel.as_posix()}"
        try:
            zf.write(path, arcname)
            added += 1
        except OSError as e:
            logger.warning("Backup skipped %s: %s", path, e)
            skipped += 1
    return added, skipped


def _add_file(zf, src, arcname):
    """Add one file to `zf` as `arcname`; returns 1 if added, 0 if absent or
    unreadable (logged, not fatal)."""
    try:
        if src and Path(src).is_file():
            zf.write(src, arcname)
            return 1
    except OSError as e:
        logger.warning("Backup skipped %s: %s", src, e)
    return 0


def write_backup_zip(
    zip_path,
    *,
    funcom_dir,
    profile_file=None,
    profiles_dir=None,
    database_user=None,
    prefs_file=None,
    app_version,
):
    """Build a backup zip at `zip_path` from whichever sources exist: the Funcom
    prefs tree under ``funcom/``, and the KazBars ``userdata/`` allowlist under
    ``kazbars/`` — ``profile.yml`` (Deeps, Live Tracker, and Damage Numbers
    travel inside the profile document), a 3.1 ``profiles/`` library while the
    userdata still carries one, ``database_user.json`` (custom buffs), and the
    machine-local ``prefs.json``. The OTA ``content/`` cache is intentionally
    NOT a parameter, so it never lands in a backup. Writes ``manifest.json``
    last. Returns the `sections` dict."""
    sections = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if funcom_dir and Path(funcom_dir).is_dir():
            added, skipped = _add_tree(zf, Path(funcom_dir), FUNCOM_ARC)
            sections["funcom"] = {"files": added, "skipped": skipped, "source": str(funcom_dir)}
        kz = {}
        if profile_file:
            kz["profile"] = _add_file(zf, profile_file, f"{KAZBARS_ARC}/{PROFILE_ARC}")
        if profiles_dir and Path(profiles_dir).is_dir():
            # Session snapshots and trashed profiles are local recovery state,
            # not the user's data — they stay out of backups.
            added, _ = _add_tree(zf, Path(profiles_dir), f"{KAZBARS_ARC}/profiles",
                                 skip_suffixes=(".bak",), skip_dirs=("trash",))
            kz["profiles"] = added
        if database_user:
            kz["database_user"] = _add_file(
                zf, database_user, f"{KAZBARS_ARC}/{DATABASE_USER_FILENAME}"
            )
        if prefs_file:
            kz["prefs"] = _add_file(zf, prefs_file, f"{KAZBARS_ARC}/{PREFS_FILENAME}")
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


def _is_library_backup(zip_path):
    """A 3.1 backup: profiles under ``kazbars/profiles/`` and no
    ``kazbars/profile.yml``."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
    except (OSError, zipfile.BadZipFile):
        return False
    return (f"{KAZBARS_ARC}/{PROFILE_ARC}" not in names
            and any(n.startswith(f"{KAZBARS_ARC}/profiles/") for n in names))


def _zip_active_profile(zip_path):
    """The `active_profile` a 3.1 backup's own prefs.json names (restored or
    not), or None."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            prefs = json.loads(zf.read(f"{KAZBARS_ARC}/{PREFS_FILENAME}").decode("utf-8"))
        return prefs.get("active_profile") if isinstance(prefs, dict) else None
    except (OSError, KeyError, zipfile.BadZipFile, ValueError):
        return None


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


def restore_zip(zip_path, *, funcom_dest, userdata_dest, include_prefs=False):
    """Extract a backup's sections to their destinations (created as needed — a
    fresh machine has no Funcom folder yet). `funcom_dest` is the AoC prefs dir;
    `userdata_dest` is the ``userdata/`` root (``profile.yml``, a 3.1
    ``profiles/`` and ``database_user.json`` land directly under it). The machine-local
    ``prefs.json`` is restored only when `include_prefs` is True (default off, so
    a cross-PC restore doesn't drag a dead game path / window geometry along). A
    pre-P8 backup's ``settings/`` entries (Deeps/Live Tracker/Damage Numbers
    disk files, since retired) are skipped rather than resurrecting the
    directory. Guards against zip-slip. Returns a per-section count."""
    roots = {FUNCOM_ARC: Path(funcom_dest).resolve(), KAZBARS_ARC: Path(userdata_dest).resolve()}
    restored = {FUNCOM_ARC: 0, KAZBARS_ARC: 0}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name == MANIFEST_NAME or name.endswith("/"):
                continue
            section, _, rel = name.partition("/")
            if section not in roots or not rel:
                continue
            if section == KAZBARS_ARC and rel == PREFS_FILENAME and not include_prefs:
                continue
            if section == KAZBARS_ARC and rel.startswith("settings/"):
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
    center_on_parent(dialog, app, width, 400)
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
        text="•  KazBars data — your profile + custom buffs",
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

    # Machine-local prefs (window positions, game folder) ride along in the zip
    # but are left out of a restore unless the user opts in — a same-PC restore
    # wants them; a backup carried to another machine does not.
    include_prefs_var = tk.BooleanVar(value=False)
    include_prefs_cb = ttk.Checkbutton(
        content,
        text="On restore, also bring back this PC's settings (window positions, game folder)",
        variable=include_prefs_var,
    )
    include_prefs_cb.pack(anchor="w", pady=(0, PAD_SMALL))

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
        bootstyle="info-outline",
        width=BTN_DIALOG,
        command=lambda: restore_settings(app, dialog, include_prefs_var.get()),
    ).pack(side="left", padx=(PAD_XS, 0))
    ttk.Button(
        btns, text="Close", bootstyle="secondary", width=BTN_DIALOG, command=dialog.destroy
    ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind('<Escape>', lambda e: dialog.destroy())
    # No Enter binding: Back up… and Restore… are two peer actions, not one
    # primary — each already opens its own file dialog for the actual commit.
    include_prefs_cb.focus_set()


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
            profile_file=profile_path(),
            profiles_dir=profiles_dir(),
            database_user=database_user_path(),
            prefs_file=prefs_path(),
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
    profile = " + your profile" if sections.get("kazbars", {}).get("profile") else ""
    app_toast(app, f"Backed up {funcom_n} AoC files{profile}", "success", 8)


def restore_settings(app, dialog, include_prefs=False):
    """Restore settings from a user-chosen backup zip, snapshotting current
    state first so a bad restore is reversible. `include_prefs` (from the dialog
    checkbox, default off) decides whether the machine-local ``prefs.json`` is
    restored too."""
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

    db_panel = getattr(app, 'db_panel', None)
    unsaved_db = ("\n\nYou have unsaved buff-database edits — restoring discards them."
                  if db_panel is not None and db_panel.modified else "")
    if not confirm(
        f"Restore settings from this backup?\n\nCreated: {manifest.get('created', 'unknown')}\n\n"
        "Your current Age of Conan and KazBars settings will be replaced — "
        "close Age of Conan first.\n\n"
        f"A pre-restore snapshot of your current settings is saved automatically.{unsaved_db}",
        title="Restore Settings", action="Restore settings", parent=dialog,
    ):
        return

    # Flush the live profile before anything on disk changes under it — a
    # failed flush means unsaved edits, so bail rather than restore over them.
    if not profile_io.release_store(app):
        return

    # Best-effort safety snapshot of current state (don't block restore on it).
    snapshot = app.app_path / f"KazBars_PreRestore_{datetime.now():%Y%m%d_%H%M%S}.zip"
    try:
        write_backup_zip(
            snapshot,
            funcom_dir=locate_funcom_prefs(),
            profile_file=profile_path(),
            profiles_dir=profiles_dir(),
            database_user=database_user_path(),
            prefs_file=prefs_path(),
            app_version=app.app_version,
        )
    except OSError as e:
        logger.warning("Pre-restore snapshot failed: %s", e)
        snapshot = None

    library = _is_library_backup(path)
    try:
        restored = restore_zip(
            path,
            funcom_dest=funcom_dest,
            userdata_dest=userdata_root(),
            include_prefs=include_prefs,
        )
    except OSError as e:
        tail = f"\n\nA pre-restore snapshot was saved to:\n{snapshot}" if snapshot else ""
        Messagebox.show_error(
            f"Restore failed partway through.\n\n({e}){tail}", title="Restore Failed"
        )
        return

    # A 3.1 backup holds a profile library, no profile.yml: once it has landed,
    # drop ours so the reopen below adopts from the restored library.
    if library:
        try:
            profile_path().unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not clear the profile for the library restore: %s", e)

    # The running app holds prefs in memory and re-saves on exit; resync from
    # disk so a freshly-restored prefs.json (when opted in) isn't clobbered.
    app.settings.reload()

    # Re-merge the buff DB from the restored database_user.json — else the next
    # Database-editor save recomputes deltas from pre-restore memory and clobbers
    # the restored custom buffs.
    app.database.reload()
    # The in-memory profile store still holds the pre-restore document; reopen
    # the restored profile.yml (or adopt from a restored 3.1 library).
    profile_io.startup_profile(app, active_hint=_zip_active_profile(path) if library else None)
    if db_panel is not None:
        db_panel.refresh_from_database()
        db_panel.modified = False   # in-memory now equals the restored disk state

    dialog.destroy()
    snap_line = f"\n\nPre-restore snapshot: {snapshot}" if snapshot else ""
    Messagebox.show_info(
        f"Restored {restored['funcom']} AoC files + {restored['kazbars']} KazBars files.\n\n"
        f"Restart KazBars to fully apply window and game-folder settings.{snap_line}",
        title="Restore Complete",
    )
