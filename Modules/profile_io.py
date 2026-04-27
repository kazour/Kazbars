"""
Kaz Grids — Profile I/O.

Load, save, create, and open profile JSON files. Functions take the
KzGridsApp instance as first arg and mutate its state (grids_panel,
current_profile, modified, reference_resolution, settings, title). Kept out
of kzgrids.py so the entry point file only carries root-window concerns.
"""

import json
import logging
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox

from .settings_manager import safe_save_json

logger = logging.getLogger(__name__)


def new_profile(app):
    """Start a new empty profile."""
    if not app._check_unsaved_changes():
        return
    app.grids_panel.load_profile_data([])
    app.current_profile = None
    app.reference_resolution = None
    app.modified = False
    app._update_title()


def open_profile(app):
    """Open a profile from file."""
    if not app._check_unsaved_changes():
        return
    path = filedialog.askopenfilename(
        title="Open Profile",
        initialdir=str(app.profiles_path),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if path:
        load_profile(app, Path(path))


def load_default_profile(app):
    """Load the bundled Default.json profile from assets/kzgrids."""
    if not app._check_unsaved_changes():
        return
    default_path = app.assets_path / "kzgrids" / "Default.json"
    if not default_path.exists():
        Messagebox.show_warning(
            "Default.json not found in assets/kzgrids folder.",
            title="Default Profile Missing"
        )
        return
    load_profile(app, default_path)


def load_profile(app, path):
    """Load a profile from a JSON file. Also dispatches `data['boss_timer']`
    to the live `BossTimer` panel if one is open."""
    corrupt = False
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        data = raw if isinstance(raw, dict) else {}
        if not isinstance(raw, dict):
            corrupt = True
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        corrupt = True
        data = {}

    if corrupt:
        Messagebox.show_warning(
            f"Profile appears corrupt — starting with empty grids.\n\n{Path(path).name}",
            title="Profile Warning"
        )

    grids = data.get('grids', [])
    missing_by_grid = app.grids_panel.load_profile_data(grids)
    if missing_by_grid:
        warn_missing_buffs(app, missing_by_grid)

    if bt := app._boss_timer_if_alive():
        bt.load_profile_data(data.get('boss_timer', {}))

    ref = data.get('reference_resolution')
    app.reference_resolution = list(ref) if isinstance(ref, list) and len(ref) == 2 else None

    # Don't anchor saves to the bundled Default.json: a subsequent Save would
    # overwrite the shipped templates. Force Save As instead.
    bundled_default = (app.assets_path / "kzgrids" / "Default.json").resolve()
    if Path(path).resolve() == bundled_default:
        app.current_profile = None
    else:
        app.current_profile = str(path)
    app.modified = False
    app.settings.set('last_profile', str(path))
    app.settings.save()
    app._update_title()


def warn_missing_buffs(app, missing_by_grid):
    """Show the missing-buff warning, deferring if the main window isn't viewable yet."""
    lines = [f"• {name}: {', '.join(refs)}" for name, refs in missing_by_grid.items()]
    message = (
        "Some tracked buffs weren't found in the database and were removed:\n\n"
        + "\n".join(lines) +
        "\n\nRe-add them via Tracked Buffs or Slot Assignments if needed."
    )
    def _show():
        Messagebox.show_warning(message, title="Missing Buff References")
    # During startup load_profile runs while the main window is still
    # withdrawn; show sync otherwise so the dialog blocks further code
    # (e.g. first-launch welcome popup) instead of stacking on top of it.
    if app.winfo_viewable():
        _show()
    else:
        app.after(200, _show)


def save_profile(app):
    """Save current profile (or Save As if no path). Returns True if saved."""
    if app.current_profile:
        return do_save_profile(app, Path(app.current_profile))
    return save_profile_as(app)


def save_profile_as(app):
    """Save profile to a new file. Returns True if saved, False if cancelled."""
    path = filedialog.asksaveasfilename(
        title="Save Profile As",
        defaultextension=".json",
        initialdir=str(app.profiles_path),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if path:
        return do_save_profile(app, Path(path))
    return False


def do_save_profile(app, path):
    """Write profile data to disk. If the live `BossTimer` is open, pulls its
    state via `bt.get_profile_data()` into the saved JSON. Returns True on
    success, False on error."""
    try:
        data = {
            'version': app.app_version,
            'grids': app.grids_panel.get_profile_data(),
        }
        if app.reference_resolution:
            data['reference_resolution'] = app.reference_resolution
        if bt := app._boss_timer_if_alive():
            data['boss_timer'] = bt.get_profile_data()
        safe_save_json(path, data)

        app.current_profile = str(path)
        app.modified = False
        app.settings.set('last_profile', str(path))
        app.settings.save()
        app._update_title()
        app.toast.show(f"Saved: {path.name}", 'success')
        app._flash_status_bar()
        return True
    except (IOError, OSError) as e:
        Messagebox.show_error(
            f"Failed to save profile.\n\nCheck that the file isn't read-only or in use by another program.\n\n({e})",
            title="Save Error"
        )
        return False


def get_profile_name(app):
    """Return the current profile display name."""
    if app.current_profile:
        return Path(app.current_profile).stem
    return "Untitled"
