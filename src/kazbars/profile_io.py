"""
KazBars — Profile I/O.

The app-facing satellite over `profile_library` (disk) and `profile_store`
(runtime document + autosave). Functions take the KazBarsApp instance as
first arg. There is no Save/Open/dirty machinery: the store autosaves, the
library owns files, and the only pointers are the in-document id and the
`active_profile` pref.

`apply_document` is the dispatch step (grids panel, live overlays, extras
cards, pointer, title, File menu). It runs before `app.deiconify()` at
startup so panels are populated before the window shows. Unresolved buff
refs raise no dialog — they surface as greyed rows in the buff selector and
as the build summary's skipped-count line.
"""

import copy
import json
import logging
import os
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox, MessageDialog, Querybox

from . import content_update, profile_share
from .buff_db_layers import DeltaStore
from .grid_model import get_game_resolution_or_default
from .profile_document import DocumentError, mint_id, new_document, validate_document
from .profile_library import SEED_NAME, file_mtime, slugify
from .profile_store import ProfileStore
from .settings_manager import safe_save_json
from .ui_widgets import app_toast
from .userdata import database_user_path

logger = logging.getLogger(__name__)


def template_paths(app):
    """The template chain, best first: OTA content (only while it's active —
    active_content_dir() yields to stock when an app upgrade has moved the
    baseline past it), then the shipped stock Default.json."""
    active_content = content_update.active_content_dir()
    paths = [active_content / 'Default.json'] if active_content else []
    paths.append(app.assets_path / 'kazbars' / 'Default.json')
    return tuple(paths)


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


def release_store(app) -> bool:
    """Mirror the grid cards, then flush the current store before it's about
    to be replaced or the app closes. False (after a danger toast) means the
    write failed — the caller must keep the old store, not drop it: it stays
    armed and RETRY_MS keeps trying, so a dropped store can't orphan a dirty
    document nobody will ever write again."""
    app._on_grids_edited()
    if app.profile_store.flush():
        return True
    app_toast(
        app, "Profile not saved — check free space and permissions, then try again.",
        'danger')
    return False


def _newest_doc(app):
    """Newest library entry. `ensure_nonempty` is best-effort — when the disk
    refused every seed write the library is still empty, so fall back to an
    in-memory blank: the app opens, the store's write-retry keeps trying, and
    the exit rescue dialog surfaces the failure."""
    entries = app.library.list_profiles()
    if entries:
        return max(entries, key=lambda e: file_mtime(e[0]))[1]
    logger.warning("Profile library empty and unseedable — using an in-memory profile")
    return new_document(app.registry, SEED_NAME, get_game_resolution_or_default())


def startup_profile(app):
    """Resolve and open the startup profile: seed the library if empty, then
    `active_profile` pref → newest file → in-memory blank (unwritable disk)."""
    app.library.ensure_nonempty(get_game_resolution_or_default())
    doc = None
    active = app.settings.get('active_profile')
    if active:
        held = app.library.load(active)
        if held:
            doc = held[1]
    if doc is None:
        doc = _newest_doc(app)
    app.profile_store = make_store(app, doc)
    apply_document(app)


def apply_document(app):
    """Dispatch the store's document into the running app.

    Side effects: grids panel, live BossTimer + Deeps overlays (if open),
    extras shortcut cards, `active_profile` pref, window title, File menu
    profile rows. Positions are fractions — no resolution rescale exists;
    `authored_at` is display-only provenance.
    """
    store = app.profile_store
    grids = copy.deepcopy(store.get_section('grids').get('grids', []))
    missing_by_grid = app.grids_panel.load_profile_data(grids)
    if missing_by_grid:
        # No dialog: inert refs are visible as greyed rows in the buff
        # selector, and the build summary reports the skipped count.
        logger.info("Unresolved buff refs (kept, skipped at build): %s", missing_by_grid)

    if bt := app._boss_timer_if_alive():
        bt.load_profile_data(store.get_section('boss_timer'))
    if dp := app._deeps_panel_if_alive():
        dp.load_profile_data(store.get_section('deeps'))

    # The baked extras (stopwatch/inspect/cast timer) travel with the profile —
    # resync the main-screen shortcut cards to the incoming sections.
    app.grids_panel.refresh_extras_shortcuts()

    app.settings.set('active_profile', store.document['id'])
    app.settings.save()
    app._update_title()
    app._refresh_file_menu()


def switch_profile(app, profile_id):
    """Flush the outgoing profile (autosave — never a prompt) and open the
    target. A vanished target refreshes the menu instead of erroring."""
    if profile_id == app.profile_store.document['id']:
        return
    if not release_store(app):
        return
    held = app.library.load(profile_id)
    if held is None:
        app_toast(app, "That profile is gone — list refreshed.", 'warning')
        app._refresh_file_menu()
        return
    app.profile_store = make_store(app, held[1])
    apply_document(app)


def new_blank_profile(app):
    if not release_store(app):
        return
    doc = app.library.create_blank(
        app.library.unique_name('New Profile'), get_game_resolution_or_default())
    if doc is None:
        Messagebox.show_error("Could not create the profile file.", title="New Profile")
        return
    app.profile_store = make_store(app, doc)
    apply_document(app)


def new_from_template(app):
    if not release_store(app):
        return
    doc = app.library.create_from_template(
        app.library.unique_name('Default'), get_game_resolution_or_default())
    if doc is None:
        Messagebox.show_warning("No profile template is available.", title="New Profile")
        return
    app.profile_store = make_store(app, doc)
    apply_document(app)


def duplicate_current(app):
    """A safety copy of the current profile; stays on the current one."""
    if not release_store(app):
        return
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
    # Flush before the file moves: an orphaned debounce timer firing after the
    # delete would re-write the trashed document under a fresh slug.
    if not release_store(app):
        return
    app.library.delete(store.document['id'])
    app.library.ensure_nonempty(get_game_resolution_or_default())
    doc = _newest_doc(app)
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
    release_store(app)  # best-effort; export reads the in-memory doc either way
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

    if not release_store(app):
        return
    doc['id'] = mint_id()
    doc['name'] = app.library.unique_name(doc['name'])
    if app.library.write(doc) is None:
        Messagebox.show_error("Could not save the imported profile.",
                              title="Import Failed")
        return

    added = skipped = 0
    buffs_failed = False
    if embedded:
        existing_names = {b.get('name') for b in app.database.buffs if b.get('name')}
        try:
            added, skipped = profile_share.merge_imported_buffs(
                DeltaStore(database_user_path()), embedded,
                existing_ids=set(app.database.by_id), existing_names=existing_names)
        except OSError as e:
            logger.warning("Could not merge imported buffs: %s", e)
            buffs_failed = True
        else:
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
    if buffs_failed:
        parts.append("custom buffs not added")
    app_toast(app, " — ".join(parts), 'success')
