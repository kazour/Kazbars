"""
KazBars — Profile I/O.

The app holds one profile document, `userdata/profile.yml`, behind
`profile_store` (runtime document + autosave). Functions take the KazBarsApp
instance as first arg. There is no Save/Open/dirty machinery and no profile
list: the store autosaves to the one file, Import / Reset replace the
document in place (so Revert to session start undoes them), and Export writes
a self-contained copy.

`startup_profile` resolves the document at launch: `profile.yml`, else its
session snapshot `profile.yml.bak` (the damaged file kept as
`profile.damaged.yml`), else the active profile of a 3.1 library
(`userdata/profiles/`, read once, never written), else the template seed.

`apply_document` is the dispatch step (grids panel, live overlays, extras
cards). It runs before `app.deiconify()` at startup so panels are
populated before the window shows. Unresolved buff refs raise no dialog —
they surface as greyed rows in the buff selector and as the build summary's
skipped-count line.
"""

import copy
import json
import logging
import os
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox, MessageDialog

from . import content_update, grid_templates, profile_share, yaml_io
from .buff_db_layers import DeltaStore
from .grid_model import get_game_resolution_or_default
from .overlay import size_for_height
from .profile_document import mint_id, new_document, validate_document
from .profile_share import slugify
from .profile_store import ProfileStore
from .settings_manager import safe_write_text
from .ui_widgets import app_toast
from .userdata import (
    database_user_path,
    prefs_path,
    profile_bak_path,
    profile_damaged_path,
    profile_path,
    profiles_dir,
    userdata_root,
)

logger = logging.getLogger(__name__)

SEED_NAME = 'My Setup'
_UNREADABLE = "That file couldn't be read as a KazBars profile."


def file_mtime(path: Path) -> float:
    """`path`'s mtime, or 0.0 if it can no longer be stat'd — a file can
    vanish between being listed/read and being compared."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def template_paths(app):
    """The template chain, best first: OTA content (only while it's active —
    active_content_dir() yields to stock when an app upgrade has moved the
    baseline past it), then the shipped stock Default.yml."""
    active_content = content_update.active_content_dir()
    paths = [active_content / 'Default.yml'] if active_content else []
    paths.append(app.assets_path / 'kazbars' / 'Default.yml')
    return tuple(paths)


# ============================================================================
# FILES
# ============================================================================
def read_profile_file(registry, path):
    """A profile file through the gate → ``(doc, embedded_buffs)``. `.json`
    reads as JSON (a 3.1 export or library document), anything else as YAML.
    Raises ``ValueError`` with a user-presentable message."""
    try:
        raw = yaml_io.read_file(path)
    except (OSError, ValueError) as e:
        raise ValueError(_UNREADABLE) from e
    profile_raw, embedded = profile_share.parse_profile_file(raw)
    return validate_document(registry, profile_raw), embedded


def _profile_text(app, doc):
    return yaml_io.dumps(profile_share.build_profile_file(validate_document(app.registry, doc)))


def write_profile(app, doc):
    """Validate and write `doc` to `profile.yml`. Returns the path, or None on
    failure (the store's writer contract: None is a failed autosave, retried
    and surfaced on exit) — a disk error, or a value YAML can't hold."""
    path = profile_path()
    try:
        safe_write_text(path, _profile_text(app, doc))
        return path
    except (OSError, TypeError) as e:
        logger.warning('Could not write the profile: %s', e)
        return None


def write_bak(app, doc):
    """The session-start snapshot behind File ▸ Revert and the damaged-file
    fallback. Best effort, never raises."""
    try:
        safe_write_text(profile_bak_path(), _profile_text(app, doc))
    except (OSError, TypeError) as e:
        logger.debug('Session snapshot skipped: %s', e)


def make_store(app, doc):
    """A ProfileStore wired to this app: `profile.yml` writer, Tk scheduler,
    session snapshot."""
    return ProfileStore(
        doc,
        writer=lambda d: write_profile(app, d),
        schedule=lambda ms, fn: app.after(ms, fn),
        cancel=app.after_cancel,
        write_bak=lambda d: write_bak(app, d),
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


# ============================================================================
# STARTUP
# ============================================================================
def startup_profile(app, active_hint=None):
    """Open the profile: `profile.yml` → its `.bak` (a damaged file) → the
    active profile of a 3.1 library → the template seed (blank if no template
    reads). `active_hint` names the library profile to adopt when prefs.json
    no longer does (a 3.1 backup restored without its prefs). Toasts wait for
    the window."""
    doc, toast = None, None
    path = profile_path()
    if path.exists():
        doc = _read_or_set_aside(app, path)
        if doc is None:
            bak = profile_bak_path()
            doc = _read_or_set_aside(app, bak, keep=True) if bak.exists() else None
            if doc is not None:
                write_profile(app, doc)
                toast = ("Your profile file was damaged — restored the copy from your last "
                         "session", 'warning', None)
            else:
                toast = ("Your profile file was damaged and no copy could be read — "
                         "starting from the defaults", 'warning', None)
    else:
        doc = _adopt_library(app, active_hint)
        if doc is not None:
            write_profile(app, doc)
            toast = (f"Adopted “{doc['name']}” as your profile — your other profiles stay in "
                     "userdata/profiles; File ▸ Import profile… opens one", 'info', 8)
    if doc is None:
        doc = _from_template(app, SEED_NAME, get_game_resolution_or_default())
        if doc is None:
            logger.warning("No profile template reads — starting from a blank profile")
            doc = new_document(app.registry, SEED_NAME, get_game_resolution_or_default())
        write_profile(app, doc)
    app.profile_store = make_store(app, doc)
    apply_document(app)
    if toast:
        msg, style, duration = toast
        app.after(0, lambda: app_toast(app, msg, style, *([duration] if duration else [])))


def _read_or_set_aside(app, path, keep=False):
    """`path` through the gate, or None — the damaged `profile.yml` moved to
    `profile.damaged.yml` first, never over an earlier one (`keep`: leave the
    file where it is)."""
    try:
        return read_profile_file(app.registry, path)[0]
    except ValueError as e:
        logger.warning('Profile file %s unreadable: %s', path.name, e)
    if not keep:
        aside, n = profile_damaged_path(), 2
        while aside.exists():
            aside = aside.with_name(f'profile.damaged-{n}.yml')
            n += 1
        try:
            os.replace(path, aside)
        except OSError as e:
            logger.warning('Could not set the damaged profile aside: %s', e)
    return None


def _adopt_library(app, active_hint=None):
    """The profile a 3.1 library was on: the `active_profile` id its
    prefs.json still holds (or `active_hint`), else its newest file. None
    without one. Reads only; `profiles/` stays as it is."""
    entries = []
    for path in sorted(profiles_dir().glob('*.json')):
        try:
            entries.append((path, read_profile_file(app.registry, path)[0]))
        except ValueError:
            continue
    if not entries:
        return None
    try:
        active = json.loads(prefs_path().read_text(encoding='utf-8')).get('active_profile')
    except (OSError, ValueError, AttributeError):
        active = None
    # The prefs id, then the hint, then the newest: a stale prefs id that names
    # none of the files never hides the hint.
    by_id = {doc['id']: doc for _path, doc in entries}
    for wanted in (active, active_hint):
        if wanted in by_id:
            return by_id[wanted]
    return max(entries, key=lambda e: file_mtime(e[0]))[1]


def _template(app):
    for path in template_paths(app):
        if path.is_file():
            try:
                return read_profile_file(app.registry, path)[0]
            except ValueError as e:
                logger.debug('Skipping template %s: %s', path, e)
    return None


def has_template(app):
    """Whether any template on the chain reads (first launch's Use Defaults)."""
    return _template(app) is not None


def _from_template(app, name, resolution):
    """The first template that reads, instantiated: fresh id, `name`, the
    overlay size for `resolution`'s height (grid positions are fractions and
    land proportionally). None when no template reads."""
    doc = _template(app)
    if doc is None:
        return None
    doc['id'] = mint_id()
    doc['name'] = name
    doc['modules'].setdefault('overlay', {})['size'] = size_for_height(resolution[1])
    return doc


# ============================================================================
# DISPATCH
# ============================================================================
def apply_document(app):
    """Dispatch the store's document into the running app.

    Side effects: grids panel, live BossTimer + Deeps overlays (if open),
    extras shortcut cards. Positions are fractions — no
    resolution rescale exists; `authored_at` is display-only provenance.
    """
    store = app.profile_store
    grids = copy.deepcopy(store.get_section('grids').get('grids', []))
    missing_by_grid = app.grids_panel.load_profile_data(grids)
    if missing_by_grid:
        # No dialog: inert refs are visible as greyed rows in the buff
        # selector, and the build summary reports the skipped count.
        logger.info("Unresolved buff refs (kept, skipped at build): %s", missing_by_grid)
    app.grids_panel.load_overlay()

    if bt := app._boss_timer_if_alive():
        bt.load_profile_data(store.get_section('boss_timer'))
    if dp := app._deeps_panel_if_alive():
        dp.load_profile_data(store.get_section('deeps'))

    # The baked extras (stopwatch/inspect/cast timer) travel with the profile —
    # resync the main-screen shortcut cards to the incoming sections.
    app.grids_panel.refresh_extras_shortcuts()


# ============================================================================
# FILE MENU
# ============================================================================
def revert_session(app):
    """File ▸ Revert to session start — restore the session-open snapshot and
    re-dispatch it (the revert autosaves like any edit)."""
    app.profile_store.revert_to_session_start()
    apply_document(app)
    app_toast(app, "Reverted to session start", 'info')


def open_data_folder(app):
    os.startfile(str(userdata_root()))


def export_profile(app):
    """File ▸ Export profile… — one self-contained `.kazbars.yml`: the flushed
    document plus every referenced custom buff."""
    store = app.profile_store
    release_store(app)  # best-effort; export reads the in-memory doc either way
    doc = store.document
    path = filedialog.asksaveasfilename(
        title="Export Profile",
        defaultextension=".kazbars.yml",
        initialfile=f"{slugify(doc['name'])}.kazbars.yml",
        filetypes=[("KazBars profile", "*.kazbars.yml"), ("YAML files", "*.yml *.yaml")],
    )
    if not path:
        return
    buffs = profile_share.collect_embedded_buffs(
        app.registry, doc, app.database.by_id, app.database.by_name,
        app.database.provenance)
    try:
        safe_write_text(Path(path), yaml_io.dumps(profile_share.build_profile_file(doc, buffs)))
    except (OSError, TypeError) as e:  # a disk error, or a value YAML can't hold
        Messagebox.show_error(f"Could not write the export file.\n\n({e})",
                              title="Export Failed")
        return
    n = len(buffs)
    suffix = f" (+{n} custom buff{'s' if n != 1 else ''})" if n else ""
    app_toast(app, f"Exported “{doc['name']}”{suffix}", 'success')


def import_profile(app):
    """File ▸ Import profile… — read a profile file (YAML, a 3.1 `.kazbars.json`
    export or a bare library document), run it through the gate, mint a fresh
    id, merge its custom buffs, and put it in place of the open profile (Revert
    to session start brings that back)."""
    path = filedialog.askopenfilename(
        title="Import Profile",
        initialdir=str(userdata_root()),
        filetypes=[("KazBars profile", "*.kazbars.yml *.yml *.yaml *.kazbars.json *.json"),
                   ("All files", "*.*")],
    )
    if not path:
        return
    try:
        doc, embedded = read_profile_file(app.registry, path)
    except ValueError as e:  # user-presentable, incl. the gate's "older KazBars"
        Messagebox.show_error(str(e), title="Import Failed")
        return
    app._on_grids_edited()
    doc['id'] = mint_id()
    app.profile_store.replace_document(doc)
    added, skipped, failed = merge_embedded_buffs(app, embedded)
    apply_document(app)
    app_toast(app, " — ".join([f"Imported “{doc['name']}”", *buff_merge_parts(added, skipped, failed)]),
              'success')


def import_grids(app):
    """File ▸ Import grid… — a grids file's grids onto the class tab the Grids
    view shows (`GridsPanel.append_grids`), its custom buffs merged first so
    the grids' refs resolve. True once grids landed; False on cancel or a
    refused file."""
    path = filedialog.askopenfilename(
        title="Import Grid",
        filetypes=[("KazBars grids", "*.kazbars-grids.yml"), ("YAML files", "*.yml *.yaml"),
                   ("All files", "*.*")],
    )
    if not path:
        return False
    try:
        raw = yaml_io.read_file(path)
    except (OSError, ValueError):
        Messagebox.show_error("That file couldn't be read as a KazBars grids file.",
                              title="Import Failed")
        return False
    try:
        grids, buffs = grid_templates.parse(raw)
    except ValueError as e:
        Messagebox.show_error(str(e), title="Import Failed")
        return False
    merged = merge_embedded_buffs(app, buffs)
    panel = app.grids_panel
    appended, renames = panel.append_grids(grids)
    n = len(appended)
    parts = [f"Imported {n} grid{'s' if n != 1 else ''} into {panel.tab_name()}"]
    parts += [f"renamed ‘{old}’ to ‘{new}’ (name taken)" for old, new in renames]
    app_toast(app, " — ".join([*parts, *buff_merge_parts(*merged)]), 'success')
    return True


def merge_embedded_buffs(app, embedded):
    """Merge a file's custom buffs into `database_user.json` (skip on an id
    collision, rename on a name one), reloading the DB when any landed.
    Returns ``(added, skipped, failed)``; a write failure is logged, never
    raised — the profile or grids still import."""
    if not embedded:
        return 0, 0, False
    existing_names = {b.get('name') for b in app.database.buffs if b.get('name')}
    try:
        added, skipped = profile_share.merge_imported_buffs(
            DeltaStore(database_user_path()), embedded,
            existing_ids=set(app.database.by_id), existing_names=existing_names)
    except OSError as e:
        logger.warning("Could not merge imported buffs: %s", e)
        return 0, 0, True
    if added:
        app.database.reload()
        app.db_panel.refresh_from_database()
    return added, skipped, False


def buff_merge_parts(added, skipped, failed):
    """The toast phrases for a custom-buff merge."""
    parts = []
    if added:
        parts.append(f"{added} custom buff{'s' if added != 1 else ''} added")
    if skipped:
        parts.append(f"{skipped} already existed")
    if failed:
        parts.append("custom buffs not added")
    return parts


def reset_to_defaults(app):
    """File ▸ Reset profile to defaults… — the stock (or OTA) template in place
    of the open profile, sized for the game resolution, after a confirm. The
    profile keeps its name."""
    dialog = MessageDialog(
        "Reset your profile to the defaults?\n\nEvery grid and extra goes back to the "
        "starter layout. Revert to session start brings your profile back.",
        title="Reset Profile", parent=app, buttons=['Cancel:secondary', 'Reset:danger'])
    dialog.show()
    if dialog.result != 'Reset':
        return
    doc = _from_template(app, app.profile_store.document['name'], get_game_resolution_or_default())
    if doc is None:
        Messagebox.show_warning("No profile template is available.", title="Reset Profile")
        return
    app._on_grids_edited()
    app.profile_store.replace_document(doc)
    apply_document(app)
    app_toast(app, "Reset to defaults", 'info')
