"""
KazBars — Profile I/O.

The app-facing satellite over `profile_library` (disk) and `profile_store`
(runtime document + autosave). Functions take the KazBarsApp instance as
first arg. There is no Save/Open/dirty machinery: the store autosaves, the
library owns files, and the only pointers are the in-document id and the
`active_profile` pref.

`apply_document` is the dispatch step (grids panel, boss timer, authored_at
rescale, pointer, title, File menu). It must run before `app.deiconify()`
at startup so `warn_missing_buffs` correctly defers via `app.after()` while
the main window is withdrawn.
"""

import copy
import json
import logging
import os
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox, MessageDialog, Querybox

from . import profile_share
from .buff_db_layers import DeltaStore
from .grid_model import get_game_resolution_or_default
from .profile_document import DocumentError, mint_id, validate_document
from .profile_library import slugify
from .profile_store import ProfileStore
from .settings_manager import safe_save_json
from .ui_widgets import app_toast
from .userdata import content_dir, database_user_path

logger = logging.getLogger(__name__)


def template_paths(app):
    """The template chain, best first: OTA content (once it ships the new
    format — old-format entries fail the gate and fall through), the interim
    new-format template, the shipped stock Default.json (old format until the
    release-day flip, so it currently falls through too)."""
    return (
        content_dir() / 'Default.json',
        app.assets_path / 'kazbars' / 'templates' / 'Default.json',
        app.assets_path / 'kazbars' / 'Default.json',
    )


def make_store(app, doc):
    """A ProfileStore wired to this app: library writer, Tk scheduler, session
    snapshot hook."""
    return ProfileStore(
        doc,
        writer=app.library.write,
        schedule=lambda ms, fn: app.after(ms, fn),
        cancel=app.after_cancel,
        write_bak=app.library.write_session_bak,
    )


def startup_profile(app):
    """Resolve and open the startup profile: seed the library if empty, then
    `active_profile` pref → newest file → (already-guaranteed) seed."""
    app.library.ensure_nonempty(get_game_resolution_or_default())
    doc = None
    active = app.settings.get('active_profile')
    if active:
        held = app.library.load(active)
        if held:
            doc = held[1]
    if doc is None:
        entries = app.library.list_profiles()
        doc = max(entries, key=lambda e: e[0].stat().st_mtime)[1]
    app.profile_store = make_store(app, doc)
    apply_document(app)


def apply_document(app):
    """Dispatch the store's document into the running app.

    Side effects: grids panel (missing-ref warning), live BossTimer (if open),
    authored_at rescale (persisted via the store), `active_profile` pref,
    window title, File menu profile rows.
    """
    store = app.profile_store
    grids = copy.deepcopy(store.get_section('grids').get('grids', []))
    missing_by_grid = app.grids_panel.load_profile_data(grids)
    if missing_by_grid:
        warn_missing_buffs(app, missing_by_grid)

    if bt := app._boss_timer_if_alive():
        bt.load_profile_data(store.get_section('boss_timer'))

    game_w, game_h = get_game_resolution_or_default()
    authored = store.document.get('authored_at')
    if authored and tuple(authored) != (game_w, game_h):
        app.grids_panel.scale_to_resolution(f'{game_w}x{game_h}', list(authored))
        store.set_section('grids', {'grids': copy.deepcopy(app.grids_panel.get_profile_data())})
        store.set_authored_at((game_w, game_h))

    app.settings.set('active_profile', store.document['id'])
    app.settings.save()
    app._update_title()
    app._refresh_file_menu()


def warn_missing_buffs(app, missing_by_grid):
    """Show the missing-buff warning, deferring if the main window isn't viewable yet."""
    lines = [f"• {name}: {', '.join(str(r) for r in refs)}" for name, refs in missing_by_grid.items()]
    message = (
        "Some tracked buffs weren't found in the database:\n\n"
        + "\n".join(lines) +
        "\n\nThey stay in this profile but are skipped at build until the "
        "buff exists again (a database update can bring them back)."
    )
    def _show():
        Messagebox.show_warning(message, title="Missing Buff References")
    # During startup apply_document runs while the main window is still
    # withdrawn; show sync otherwise so the dialog blocks further code
    # (e.g. first-launch welcome popup) instead of stacking on top of it.
    if app.winfo_viewable():
        _show()
    else:
        app.after(200, _show)


def switch_profile(app, profile_id):
    """Flush the outgoing profile (autosave — never a prompt) and open the
    target. A vanished target refreshes the menu instead of erroring."""
    if profile_id == app.profile_store.document['id']:
        return
    app.profile_store.flush()
    held = app.library.load(profile_id)
    if held is None:
        app_toast(app, "That profile is gone — list refreshed.", 'warning')
        app._refresh_file_menu()
        return
    app.profile_store = make_store(app, held[1])
    apply_document(app)


def new_blank_profile(app):
    app.profile_store.flush()
    doc = app.library.create_blank(
        app.library.unique_name('New Profile'), get_game_resolution_or_default())
    if doc is None:
        Messagebox.show_error("Could not create the profile file.", title="New Profile")
        return
    app.profile_store = make_store(app, doc)
    apply_document(app)


def new_from_template(app):
    app.profile_store.flush()
    doc = app.library.create_from_template(app.library.unique_name('Default'))
    if doc is None:
        Messagebox.show_warning("No profile template is available.", title="New Profile")
        return
    app.profile_store = make_store(app, doc)
    apply_document(app)


def duplicate_current(app):
    """A safety copy of the current profile; stays on the current one."""
    app.profile_store.flush()
    doc = app.library.duplicate(app.profile_store.document['id'])
    if doc is None:
        Messagebox.show_error("Could not duplicate the profile.", title="Duplicate Profile")
        return
    app_toast(app, f"Duplicated as “{doc['name']}”", 'success')
    app._refresh_file_menu()


def rename_current(app):
    store = app.profile_store
    new_name = Querybox.get_string(
        prompt="New profile name:", title="Rename Profile",
        initialvalue=store.document['name'], parent=app)
    if not new_name or not new_name.strip():
        return
    if app.library.rename(store.document['id'], new_name) is None:
        Messagebox.show_error("Could not rename the profile.", title="Rename Profile")
        return
    # The library already persisted the rename; sync the in-memory envelope
    # without arming a redundant autosave.
    store.document['name'] = new_name.strip()
    app._update_title()
    app._refresh_file_menu()


def delete_current(app):
    store = app.profile_store
    name = store.document['name']
    dialog = MessageDialog(
        f"Delete “{name}”?\n\nIt moves to the profile trash "
        "(userdata/profiles/trash).",
        title="Delete Profile", parent=app,
        buttons=['Cancel:secondary', 'Delete:danger'])
    dialog.show()
    if dialog.result != 'Delete':
        return
    app.library.delete(store.document['id'])
    app.library.ensure_nonempty(get_game_resolution_or_default())
    entries = app.library.list_profiles()
    doc = max(entries, key=lambda e: e[0].stat().st_mtime)[1]
    app.profile_store = make_store(app, doc)
    apply_document(app)


def revert_session(app):
    """File ▸ Revert to session start — restore the session-open snapshot and
    re-dispatch it (the revert autosaves like any edit)."""
    app.profile_store.revert_to_session_start()
    apply_document(app)
    app_toast(app, "Reverted to session start", 'info')


def open_profiles_folder(app):
    os.startfile(str(app.library.profiles_dir))


def export_profile(app):
    """File ▸ Export profile… — one self-contained `.kazbars.json` envelope:
    the flushed document plus every referenced custom buff."""
    store = app.profile_store
    store.flush()
    doc = store.document
    path = filedialog.asksaveasfilename(
        title="Export Profile",
        defaultextension=".kazbars.json",
        initialfile=f"{slugify(doc['name'])}.kazbars.json",
        filetypes=[("KazBars profile", "*.kazbars.json"), ("JSON files", "*.json")],
    )
    if not path:
        return
    envelope = profile_share.build_export(
        app.registry, doc, app.database.by_id, app.database.by_name,
        app.database.provenance)
    try:
        safe_save_json(Path(path), envelope)
    except OSError as e:
        Messagebox.show_error(f"Could not write the export file.\n\n({e})",
                              title="Export Failed")
        return
    n = len(envelope['buffs'])
    suffix = f" (+{n} custom buff{'s' if n != 1 else ''})" if n else ""
    app_toast(app, f"Exported “{doc['name']}”{suffix}", 'success')


def import_profile(app):
    """File ▸ Import profile… — read an export envelope (or a bare document
    file), run it through the gate, mint a fresh id, merge embedded custom
    buffs, and switch to it."""
    path = filedialog.askopenfilename(
        title="Import Profile",
        initialdir=str(app.library.profiles_dir),
        filetypes=[("KazBars profile", "*.json *.kazbars.json"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        profile_raw, embedded = profile_share.parse_export(raw)
        doc = validate_document(app.registry, profile_raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        Messagebox.show_error("That file couldn't be read as a KazBars profile.",
                              title="Import Failed")
        return
    except (ValueError, DocumentError) as e:
        # DocumentError is a ValueError; both carry user-presentable messages
        # (incl. the old-format "older KazBars" rejection).
        Messagebox.show_error(str(e), title="Import Failed")
        return

    app.profile_store.flush()
    doc['id'] = mint_id()
    doc['name'] = app.library.unique_name(doc['name'])
    if app.library.write(doc) is None:
        Messagebox.show_error("Could not save the imported profile.",
                              title="Import Failed")
        return

    added = skipped = 0
    if embedded:
        existing_names = {b.get('name') for b in app.database.buffs if b.get('name')}
        added, skipped = profile_share.merge_imported_buffs(
            DeltaStore(database_user_path()), embedded,
            existing_ids=set(app.database.by_id), existing_names=existing_names)
        if added:
            app.database.reload()
            app.db_panel.refresh_from_database()

    app.profile_store = make_store(app, doc)
    apply_document(app)
    parts = [f"Imported “{doc['name']}”"]
    if added:
        parts.append(f"{added} custom buff{'s' if added != 1 else ''} added")
    if skipped:
        parts.append(f"{skipped} already existed")
    app_toast(app, " — ".join(parts), 'success')
