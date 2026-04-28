"""
Kaz Grids — Profile I/O.

Load, save, create, and open profile JSON files. Functions take the
KzGridsApp instance as first arg and mutate its state (grids_panel,
current_profile, modified, reference_resolution, settings, title). Kept out
of kzgrids.py so the entry point file only carries root-window concerns.

Load is split into a pure read step (`read_profile_file`) and a dispatch
step (`apply_profile_data`) so the boss-timer fan-out is visible at every
call site. Save retains `do_save_profile` as orchestrator (error-handling
boilerplate makes caller composition awkward); its body is factored into
`build_profile_payload` / `write_profile_file` / `_commit_saved_profile`,
and `build_profile_payload` names the boss-timer pull explicitly.
"""

import json
import logging
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox

from .settings_manager import safe_save_json
from .ui_widgets import flash_status_bar, app_toast

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
        data, corrupt = read_profile_file(Path(path))
        apply_profile_data(app, Path(path), data, corrupt=corrupt)


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
    data, corrupt = read_profile_file(default_path)
    apply_profile_data(app, default_path, data, corrupt=corrupt)


def read_profile_file(path):
    """Pure I/O: parse a profile JSON file. Returns `(data, is_corrupt)`.
    On any decode/IO error or non-dict root, returns `({}, True)`."""
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            return raw, False
        return {}, True
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}, True


def apply_profile_data(app, path, data, *, corrupt=False):
    """Dispatch parsed profile data into app state.

    Side effects: grids panel, missing-buff warning, **live BossTimer
    (if open)**, `reference_resolution`, `current_profile`, `modified`,
    `last_profile` setting, window title.

    Must run before `app.deiconify()` at startup so `warn_missing_buffs`
    correctly defers via `app.after()` while the main window is withdrawn.
    """
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
    # During startup apply_profile_data runs while the main window is still
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


def build_profile_payload(app):
    """Assemble the profile dict for serialization: `version`, `grids`,
    optional `reference_resolution`, **and `boss_timer` pulled from the
    live BossTimer if one is open**. Pure data assembly — no I/O."""
    data = {
        'version': app.app_version,
        'grids': app.grids_panel.get_profile_data(),
    }
    if app.reference_resolution:
        data['reference_resolution'] = app.reference_resolution
    if bt := app._boss_timer_if_alive():
        data['boss_timer'] = bt.get_profile_data()
    return data


def write_profile_file(path, data):
    """Pure I/O: serialize `data` and write to `path` via safe_save_json.
    Raises `OSError` (incl. `IOError`, `PermissionError`) on failure."""
    safe_save_json(path, data)


def _commit_saved_profile(app, path, silent=False):
    """Post-save state updates: anchor `current_profile`, clear `modified`,
    persist `last_profile`, refresh title, toast, status flash. `silent=True`
    suppresses the toast + status flash for piggyback saves whose surrounding
    flow has its own success feedback (e.g. the auto-save before a build)."""
    app.current_profile = str(path)
    app.modified = False
    app.settings.set('last_profile', str(path))
    app.settings.save()
    app._update_title()
    if not silent:
        app_toast(app, f"Saved: {path.name}", 'success')
        flash_status_bar(app.bottom_bar)


def do_save_profile(app, path, silent=False):
    """Save profile to disk: build payload → write → commit. Returns True
    on success, False on error. Composition wrapper kept (rather than
    pushed to callers) because the error-handling Messagebox + bool return
    would otherwise repeat at every save site."""
    try:
        data = build_profile_payload(app)
        write_profile_file(path, data)
    except (IOError, OSError) as e:
        Messagebox.show_error(
            f"Failed to save profile.\n\nCheck that the file isn't read-only or in use by another program.\n\n({e})",
            title="Save Error"
        )
        return False
    _commit_saved_profile(app, path, silent=silent)
    return True


def get_profile_name(app):
    """Return the current profile display name."""
    if app.current_profile:
        return Path(app.current_profile).stem
    return "Untitled"
