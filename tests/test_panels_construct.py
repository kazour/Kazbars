"""Panel-construction smoke test — boots a real KazBarsApp and opens every
satellite panel through its app-side opener, catching "panel won't even
construct" breakage (bad widget kwarg, renamed design token, missing app
attribute, broken import wiring) in seconds instead of at manual QA.

Scope: construction + the panel's own close path, plus ui_widgets binding
hygiene (which must ride this module's Tk instance — see the section note at
the bottom). Event flow, visual correctness, and drag/animation behavior stay
manual QA. Deferred to v2 (need a
data context or block on wait_window): BuffSelectorDialog,
BuffEditDialog, the first-launch dialog,
show_close_game_required_dialog, BuildLoadingScreen, the settings_backup
dialog, show_welcome_popup.

The fixture neutralizes the two network entry points fired by
KazBarsApp.__init__ (update_orchestrator), relocates userdata/ to a
tmp dir (patch seam: kazbars.userdata.app_path — userdata binds the name at
import, so patching kazbars.paths.app_path would miss), and pre-seeds
prefs.json with a game_path so the first-launch modal never fires.
"""

import ast
import sys
import tkinter as tk
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32',
    reason='Tk UI smoke is Windows-only (matches CI)',
)

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PY = REPO_ROOT / 'src' / 'kazbars' / 'app.py'


# ============================================================================
# FIXTURE
# ============================================================================
@pytest.fixture(scope='module')
def app(tmp_path_factory):
    """Boot one real KazBarsApp (withdrawn) shared by all tests in this module."""
    from kazbars import content_update, update_orchestrator, userdata
    from kazbars.prefs import PREFS_SCHEMA
    from kazbars.settings_core import Store

    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp('userdata_home')
    fake_game = root / 'AoC'
    (fake_game / 'Data' / 'Gui' / 'Default' / 'Flash').mkdir(parents=True)

    mp.setattr(userdata, 'app_path', lambda: root)
    mp.setattr(update_orchestrator, 'check_on_launch', lambda *a, **k: None)
    mp.setattr(update_orchestrator, 'finish_startup', lambda *a, **k: None)
    mp.setattr(content_update, 'check_and_apply', lambda *a, **k: None)

    # Pre-seed prefs with a game_path BEFORE the app constructs — __init__
    # reads it and schedules the first-launch modal when it's missing.
    userdata.ensure_layout()
    prefs = Store(PREFS_SCHEMA, userdata.userdata_root())
    prefs.set('game_path', str(fake_game))
    prefs.save()

    from kazbars.app import KazBarsApp
    a = KazBarsApp()
    a.withdraw()
    a.update()
    yield a
    try:
        # _on_close runs the DB-editor guard, which raises a blocking dialog
        # when dirty — force clean so teardown can never hang. (The profile
        # itself autosaves; no profile flag exists anymore.)
        a.db_panel.modified = False
        a._on_close()
    except tk.TclError:
        pass
    finally:
        mp.undo()


def _close_via_protocol(window):
    """Close like the title-bar X: invoke the registered WM_DELETE_WINDOW
    handler (withdraw for Deeps/Live Tracker, destroy for the rest)."""
    cmd = window.protocol('WM_DELETE_WINDOW')
    if cmd:
        window.tk.eval(cmd)
    else:
        window.destroy()


def _find_buff_display_dialog(a):
    """open_buff_display_editor stores no app reference — find the dialog."""
    from kazbars.buff_display_editor import BuffDisplayDialog
    for w in a.winfo_children():
        if isinstance(w, BuffDisplayDialog):
            return w
    return None


def _find_damage_number_colors_panel(a):
    """open_damage_number_colors_panel is modal and stores no app reference — find it."""
    from kazbars.damageinfo_colors_panel import DamageNumberColorsPanel
    for w in a.winfo_children():
        if isinstance(w, DamageNumberColorsPanel):
            return w
    return None


# ============================================================================
# OPENERS UNDER TEST
# ============================================================================
# (KazBarsApp method, getter for the window it constructs). Openers are the
# contract users hit — raw constructors would pass while the menu wiring 404s.
OPENERS = [
    ('_open_boss_timer', lambda a: a.boss_timer_panel),
    ('_open_deeps_panel', lambda a: a.deeps_panel),
    ('_open_damage_numbers', lambda a: a.damage_numbers_panel),
    ('_open_damage_number_colors', _find_damage_number_colors_panel),
    ('_open_buff_display_editor', _find_buff_display_dialog),
    ('_open_stopwatch_settings', lambda a: a.stopwatch_dialog),
    ('_open_inspect_settings', lambda a: a.inspect_dialog),
    ('_open_cast_timer_settings', lambda a: a.cast_timer_dialog),
    ('_open_console_settings', lambda a: a.console_dialog),
    ('_open_onslaught_settings', lambda a: a.onslaught_dialog),
    ('_show_about', lambda a: a._about_popup),
]

# Opener-shaped KazBarsApp methods this test deliberately does not exercise.
DEFERRED = {
    '_open_backup_dialog': 'settings_backup dialog — v2',
    '_open_game_in_explorer': 'os.startfile shell-out, not a panel',
    '_open_profiles_folder': 'os.startfile shell-out, not a panel',
    '_show_first_launch_dialog': 'blocking first-launch modal — v2',
    '_show_game_context_menu': 'tk.Menu popup, needs a real click event',
}


# ============================================================================
# TESTS
# ============================================================================
def test_app_boots(app):
    """Booting the app constructs GridsPanel, DatabaseEditorTab,
    InstructionsPanel, the menu bar, and the header — free coverage."""
    assert app.winfo_exists()
    assert app.game_path  # first-launch modal must not have been armed
    for widget in (app.grids_panel, app.db_panel, app.instructions_panel,
                   app._menubar, app._header_canvas):
        assert widget.winfo_exists()


@pytest.mark.parametrize('method,getter', OPENERS, ids=[m for m, _ in OPENERS])
def test_panel_constructs(app, method, getter):
    getattr(app, method)()
    app.update()
    panel = getter(app)
    assert panel is not None, f'{method} did not construct its panel'
    assert panel.winfo_exists()
    _close_via_protocol(panel)
    app.update()


def test_openers_cover_known_panels():
    """Canary: every _open_*/_show_* method on KazBarsApp must be in OPENERS
    or explicitly DEFERRED — new panels enroll themselves or fail here."""
    tree = ast.parse(APP_PY.read_text(encoding='utf-8'))
    app_class = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == 'KazBarsApp'
    )
    methods = {
        n.name for n in app_class.body
        if isinstance(n, ast.FunctionDef)
        and n.name.startswith(('_open_', '_show_'))
    }
    tested = {m for m, _ in OPENERS}

    unaccounted = methods - tested - set(DEFERRED)
    assert not unaccounted, (
        'New opener(s) on KazBarsApp not covered by this test: '
        f'{sorted(unaccounted)} — add to OPENERS (or DEFERRED with a reason)'
    )
    stale = (tested | set(DEFERRED)) - methods
    assert not stale, f'OPENERS/DEFERRED reference methods gone from app.py: {sorted(stale)}'
    assert len(OPENERS) >= 6


# ============================================================================
# UI-WIDGET BINDING HYGIENE (rides the same app instance)
# ============================================================================
# These attach to the module's live app rather than a tk.Tk() of their own:
# ttkbootstrap wraps Tk.__init__ process-wide, and on the hosted CI runner a
# SECOND Tcl interpreter (created after the first is destroyed) fails to
# initialize (init.tcl unreadable in the toolcache Tcl tree). One interp per
# process is the portable pattern.
#
# Two pinned behaviors (verified against a live Tk before fixing):
#   1. `add_tooltip` is idempotent per widget — a repeat call updates the
#      existing tooltip's text instead of stacking another live instance.
#      Refresh paths (the game-path label re-adds its tooltip on every folder
#      change) would otherwise accumulate <Enter> bindings and pop overlapping
#      stale tooltips on a single hover.
#   2. `bind_label_hover_colors` appends (add="+") rather than overwriting,
#      so a tooltip bound to the same widget first keeps working.

def _handler_count(widget, sequence):
    script = widget.bind(sequence) or ''
    return len([ln for ln in script.splitlines() if ln.strip()])


def test_add_tooltip_is_idempotent_per_widget(app):
    from kazbars.ui_widgets import add_tooltip
    lbl = tk.Label(app, text='x')
    try:
        add_tooltip(lbl, 'first')
        first_instance = lbl._kz_tooltip
        assert _handler_count(lbl, '<Enter>') == 1

        add_tooltip(lbl, 'second')
        # Same instance, updated text, no stacked bindings.
        assert lbl._kz_tooltip is first_instance
        assert lbl._kz_tooltip.text == 'second'
        assert _handler_count(lbl, '<Enter>') == 1
    finally:
        lbl.destroy()


def test_add_tooltip_accepts_callable_text_on_update(app):
    from kazbars.ui_widgets import add_tooltip
    lbl = tk.Label(app, text='x')
    try:
        add_tooltip(lbl, 'static')
        add_tooltip(lbl, lambda: 'dynamic')
        assert lbl._kz_tooltip.text() == 'dynamic'
    finally:
        lbl.destroy()


def test_hover_colors_preserves_existing_enter_bindings(app):
    from kazbars.ui_widgets import add_tooltip, bind_label_hover_colors
    lbl = tk.Label(app, text='x')
    try:
        add_tooltip(lbl, 'tip')
        assert _handler_count(lbl, '<Enter>') == 1
        bind_label_hover_colors(lbl, '#888888', '#ffffff')
        # Appended, not replaced — the tooltip's handler survives.
        assert _handler_count(lbl, '<Enter>') == 2
        assert _handler_count(lbl, '<Leave>') == 2
    finally:
        lbl.destroy()


# ============================================================================
# GRID-CARD AUTOSAVE SEAM (rides the same app instance)
# ============================================================================
# The profile revamp has no Save prompt: every card widget must arm the
# store's debounced autosave via on_edit → _mark_modified. An unwired widget
# is silent data loss (edit → close → relaunch → edit gone), so these pin the
# two commit mechanisms — spinbox focus-out and combobox selection — plus the
# flush-point gather that captures a field still being typed in.

def _find_widget(root, cls, textvariable):
    """Depth-first search for the `cls` widget bound to `textvariable`."""
    for w in root.winfo_children():
        if isinstance(w, cls) and str(w.cget('textvariable')) == str(textvariable):
            return w
        found = _find_widget(w, cls, textvariable)
        if found is not None:
            return found
    return None


def _add_seam_grid(app, name):
    from kazbars.grid_model import create_default_grid
    gp = app.grids_panel
    gp.grids.append(create_default_grid(
        grid_type='player', rows=1, cols=5, mode='dynamic', grid_id=name))
    gp.refresh_panels()
    app.update()
    return gp.grid_panels[-1], len(gp.grids) - 1


def _stored_grid(app, index):
    return app.profile_store.get_section('grids')['grids'][index]


def _settings(card):
    """Open the card's Grid Settings (the cog)."""
    from kazbars.grid_settings_dialog import open_grid_settings
    return open_grid_settings(card)


def test_grid_settings_apply_reaches_profile_store(app):
    card, idx = _add_seam_grid(app, 'SeamSpin')
    dlg = _settings(card)
    dlg.gap_var.set('7')
    rl_label = dlg.fill_combo['values'][1]  # 1×5 grid → (Left → Right, Right → Left)
    dlg.fill_var.set(rl_label)
    dlg.apply()
    assert not dlg.winfo_exists()
    stored = _stored_grid(app, idx)
    assert (stored['gap'], stored['fillDirection']) == (7, 'RL')


def test_grid_settings_cancel_leaves_the_config_and_redraws_the_card(app):
    import copy
    card, idx = _add_seam_grid(app, 'SeamCancel')
    before = copy.deepcopy(card.grid_config)
    width = card.preview.layout.width
    dlg = _settings(card)
    dlg.cols_var.set('8')
    dlg._on_shape('cols')
    assert card.preview.layout.width > width, "the card previews the draft"
    dlg.cancel()
    assert card.grid_config == before
    assert card.preview.layout.width == width


def _find_scale(root):
    from tkinter import ttk
    for w in root.winfo_children():
        if isinstance(w, ttk.Scale):
            return w
        found = _find_scale(w)
        if found is not None:
            return found
    return None


def test_size_slider_previews_live_and_lands_on_apply(app):
    card, idx = _add_seam_grid(app, 'SeamSize')
    cell = card.preview.layout.cell
    dlg = _settings(card)
    scale = _find_scale(dlg)
    assert scale is not None
    scale.set(152.6)  # a drag: snapped to 155, the card's preview follows
    app.update()
    assert dlg.scale_var.get() == 155
    assert card.preview.layout.cell > cell
    assert card.grid_config['scale'] == 100
    dlg.apply()
    assert _stored_grid(app, idx)['scale'] == 155


def test_size_slider_keys_step_a_notch(app):
    card, _ = _add_seam_grid(app, 'SeamKeys')
    dlg = _settings(card)
    scale = _find_scale(dlg)
    assert scale is not None
    def fire(seq):
        # The test app never holds keyboard focus, so a generated key event
        # never lands; call the widget's own binding instead.
        name = scale.bind(seq).split('[', 1)[1].split()[0]
        return scale.tk.call(name, *(['0'] * 14 + [str(scale)] + ['0'] * 4))

    try:
        for key, want in (('Right', 105), ('Right', 110), ('Left', 105), ('End', 200), ('Home', 50)):
            assert fire(f'<{key}>') == 'break', key
            fire('<KeyRelease>')
            assert (dlg.scale_var.get(), round(float(scale.get()))) == (want, want), key
    finally:
        dlg.cancel()


def test_an_overlay_size_change_unticks_the_build_step(app):
    panel = app.grids_panel
    size_label, other = list(panel._size_by_label)[:2]
    panel._overlay_size_var.set(size_label)
    panel._on_overlay_changed()
    panel._build_done = True
    panel._on_overlay_changed()  # same size again: nothing moved
    assert panel._build_done is True
    panel._overlay_size_var.set(other)
    panel._on_overlay_changed()
    assert panel._build_done is False
    assert app.profile_store.get_section('overlay')['size'] == panel._size_by_label[other]


def test_extras_switch_on_with_nothing_to_build_stays_off(app):
    store = app.profile_store
    store.update_section('console', {'enabled': False, 'tabs': []})
    app.grids_panel.refresh_extras_shortcuts()
    tile = app.grids_panel.extras_row._tiles['console']
    tile['var'].set(True)
    app.grids_panel.extras_row._on_toggle('console')
    assert store.get_section('console')['enabled'] is False
    assert tile['var'].get() is False


# ============================================================================
# FIRST-LAUNCH PRE-FILL (rides the same app instance)
# ============================================================================
# The dialog never calls wait_window, so it can be opened, inspected and
# destroyed inline. It does grab_set — every case releases the grab.

def _widgets(root, cls):
    """Every `cls` widget under `root`, depth-first."""
    out = []
    for w in root.winfo_children():
        if isinstance(w, cls):
            out.append(w)
        out.extend(_widgets(w, cls))
    return out


def _open_first_launch(app, monkeypatch, paths):
    from tkinter import ttk

    from kazbars import first_launch
    monkeypatch.setattr(first_launch, 'COMMON_INSTALL_PATHS', [str(p) for p in paths])
    first_launch.show_first_launch_dialog(
        app, 'KazBars', lambda p: None, lambda r: None,
        on_resolution_set=lambda r: None, default_profile_exists=True,
        on_start_empty=lambda: None)
    app.update()
    dialog = next(w for w in app.winfo_children()
                  if isinstance(w, tk.Toplevel) and w.title() == 'Welcome to KazBars')
    entry = _widgets(dialog, ttk.Entry)[0]
    buttons = {b.cget('text'): b for b in _widgets(dialog, ttk.Button)}
    texts = {str(lbl.cget('text')) for lbl in _widgets(dialog, ttk.Label)}
    return dialog, entry, buttons, texts


GATE_HINT = 'Set your game folder above to start.'


def test_first_launch_prefills_single_install(app, monkeypatch):
    dialog, entry, buttons, texts = _open_first_launch(
        app, monkeypatch, [app.game_path])
    try:
        assert entry.get() == str(app.game_path)
        assert str(buttons['Load Defaults'].cget('state')) == 'normal'
        assert str(buttons['Start Empty'].cget('state')) == 'normal'
        assert GATE_HINT not in texts
    finally:
        dialog.grab_release()
        dialog.destroy()
        app.update()


def test_enter_can_reach_a_focused_button(app):
    """The first-launch pre-fill focuses Load Defaults so Enter proceeds, and no
    dialog-level `<Return>` binding backs that up. What makes it work is
    ttkbootstrap's Window, which installs a `<Return>` class binding on TButton
    that a bare `tk.Tk()` root does not — verified live: Enter and KP_Enter both
    invoke a focused ttk.Button under `ttkb.Window`, neither does under `tk.Tk`.
    Delivering the keypress needs real focus, which the withdrawn fixture cannot
    give, so pin the mechanism: if ttkbootstrap ever drops it, Enter dies
    silently on the app's first screen."""
    import ttkbootstrap as ttkb
    assert isinstance(app, ttkb.Window)
    assert app.bind_class('TButton', '<Return>')


def test_first_launch_leaves_ambiguous_install_blank(app, monkeypatch, tmp_path):
    second = tmp_path / 'AoC2'
    (second / 'Data' / 'Gui' / 'Default').mkdir(parents=True)
    dialog, entry, buttons, texts = _open_first_launch(
        app, monkeypatch, [app.game_path, second])
    try:
        assert entry.get() == ''
        assert str(buttons['Load Defaults'].cget('state')) == 'disabled'
        assert str(buttons['Start Empty'].cget('state')) == 'disabled'
        assert GATE_HINT in texts
    finally:
        dialog.grab_release()
        dialog.destroy()
        app.update()


def test_first_launch_found_list_hides_the_matched_path(app, monkeypatch):
    """The suggestion block repeats whatever the entry already holds —
    noise, not help — so the single-install pre-fill hides it immediately;
    editing away from every listed path brings it back, and retyping an
    exact match hides it again. `winfo_children()` returns a pack_forget'd
    widget same as a packed one, so this checks the frame's own geometry
    manager, not label text — 'pack' if shown, '' once forgotten."""
    from tkinter import ttk
    dialog, entry, _buttons, _texts = _open_first_launch(
        app, monkeypatch, [app.game_path])
    try:
        found_lbl = next(lbl for lbl in _widgets(dialog, ttk.Label)
                         if str(lbl.cget('text')) == 'Found on this PC:')
        found_frame = found_lbl.master

        assert found_frame.winfo_manager() == ''      # pre-filled match: hidden

        entry.delete(0, 'end')
        entry.insert(0, 'Z:\\not-a-real-install')
        app.update()
        assert found_frame.winfo_manager() == 'pack'   # no match: shown

        entry.delete(0, 'end')
        entry.insert(0, str(app.game_path))
        app.update()
        assert found_frame.winfo_manager() == ''       # matches again: hidden
    finally:
        dialog.grab_release()
        dialog.destroy()
        app.update()


# ============================================================================
# BUFF-DB AUTOSAVE SEAM (rides the same app instance)
# ============================================================================
# There is no Save button: every confirmed edit must be on disk before the
# next one. A failed write is the only path that leaves the panel dirty.

SEAM_BUFF = {'name': 'SeamAutosave', 'ids': [99000001], 'category': 'Misc',
             'type': 'buff', 'stacking': False}


def _user_delta(app):
    from kazbars import userdata
    from kazbars.buff_db_layers import DeltaStore
    return DeltaStore(userdata.database_user_path()).load()


def test_db_change_autosaves(app):
    db = app.db_panel
    db.database.add_buff(dict(SEAM_BUFF))
    assert db._after_db_change() is True
    names = {b['name'] for b in _user_delta(app)['buffs']}
    assert 'SeamAutosave' in names
    assert db.modified is False


def test_db_autosave_failure_keeps_dirty(app, monkeypatch):
    from ttkbootstrap.dialogs import Messagebox
    db = app.db_panel
    monkeypatch.setattr(db._delta_store, 'save',
                        lambda delta: (_ for _ in ()).throw(OSError('disk full')))
    monkeypatch.setattr(Messagebox, 'show_error', lambda *a, **k: None)
    # False is what suppresses the caller's "Added: X" toast — a green success
    # line behind the error dialog would tell the user the opposite of the truth.
    assert db._after_db_change() is False
    assert db.modified is True
    monkeypatch.undo()
    db.save()  # leave the panel clean for the module teardown guard
    assert db.modified is False


def test_db_toolbar_has_no_save_button(app):
    from tkinter import ttk
    labels = {str(b.cget('text')) for b in _widgets(app.db_panel, ttk.Button)}
    assert 'Save Database' not in labels
    assert {'Add', 'Edit', 'Delete', 'Import...', 'Export...'} <= labels
    for b in _widgets(app.db_panel, ttk.Button):
        if str(b.cget('text')) in ('Import...', 'Export...'):
            assert 'info' in str(b.cget('style')) and 'Outline' in str(b.cget('style'))


# ============================================================================
# KEYBOARD + CARD CHROME (rides the same app instance)
# ============================================================================

def test_alt_arrow_moves_grid(app):
    gp = app.grids_panel
    _add_seam_grid(app, 'SeamMoveA')
    _, last = _add_seam_grid(app, 'SeamMoveB')

    gp._move_grid(last, -1)
    app.update()
    assert _stored_grid(app, last - 1)['id'] == 'SeamMoveB'
    assert _stored_grid(app, last)['id'] == 'SeamMoveA'
    # Focus-follows-the-grid needs manual QA to confirm: focus_set is a no-op
    # while the fixture's app is withdrawn. What is checkable here is that the
    # repack re-bound the keys at the new indices.
    for handle in (gp.grid_panels[last - 1].drag_handle,
                   gp.grid_panels[last].drag_handle):
        assert handle.bind('<Alt-Up>') and handle.bind('<Alt-Down>')

    before = [g['id'] for g in app.profile_store.get_section('grids')['grids']]
    gp._move_grid(0, -1)  # clamps at the top edge
    assert [g['id'] for g in app.profile_store.get_section('grids')['grids']] == before


@pytest.mark.parametrize('method,attr', [('_open_deeps_panel', 'deeps_panel'),
                                         ('_open_boss_timer', 'boss_timer_panel')])
def test_escape_hides_monitor_window(app, method, attr):
    getattr(app, method)()
    app.update()
    window = getattr(app, attr)
    assert window.bind('<Escape>')
    window.event_generate('<Escape>')
    app.update()
    assert window.state() == 'withdrawn'


def test_grid_preview_draws_once_and_repaints_in_place(app):
    from types import SimpleNamespace

    from kazbars.grid_preview_canvas import GridPreview
    from kazbars.ui_helpers import GRID_TYPE_COLORS, THEME_COLORS
    picked, cleared = [], []
    preview = GridPreview(app, accent=GRID_TYPE_COLORS['player'], on_pick=picked.append,
                          on_clear=cleared.append, tip_for=lambda i: f'slot {i}')
    try:
        cfg = {'slotMode': 'static', 'rows': 8, 'cols': 8, 'gap': -1,
               'fillDirection': 'TL-BR', 'slotAssignments': {'9': [1]}}
        preview.set_config(cfg, 48, True)
        items = preview.find_all()
        assert len(items) == 192
        assert preview.ratio > 3  # 8 rows step down to fit

        painted = []
        real = preview.repaint_slot
        preview.repaint_slot = lambda i: (painted.append(i), real(i))
        x0, y0, *_ = preview.layout.rects[9]
        # The fixture's app is withdrawn, so a generated pointer event never
        # lands; the handlers take the event as Tk hands it over.
        at = SimpleNamespace(x=x0 + 2, y=y0 + 2)
        preview._on_motion(at)
        assert sorted(painted) == [-1, 9]  # nothing was hot: one real repaint
        rect = preview.find_withtag('slot_9&&rect')
        assert preview.itemcget(rect, 'outline') == THEME_COLORS['heading']
        painted.clear()

        preview.set_config(dict(cfg, slotAssignments={}), 48, False)
        assert preview.find_all() == items, "same geometry, no new items"
        assert len(painted) == 64

        preview.set_config(dict(cfg, slotAssignments={'9': [1]}), 48, True)
        preview._on_click(at)
        preview._on_right_click(at)
        assert (picked, cleared) == ([9], [9])

        preview.set_config(dict(cfg, rows=2, cols=2), 48, True)
        assert len(preview.find_all()) == 12, "a new shape rebuilds"
    finally:
        preview.destroy()


def test_grid_card_stripe(app):
    from kazbars.ui_helpers import GRID_TYPE_COLORS, TK_COLORS
    card, _ = _add_seam_grid(app, 'SeamStripe')
    assert str(card._stripe.cget('bg')) == GRID_TYPE_COLORS['player']
    assert str(card._card.cget('highlightbackground')) == TK_COLORS['border']

    # The stripe must never drive the card's height: a tk.Canvas with no
    # explicit height asks for 7c (265px), which fill='y' does not shrink, and
    # one collapsed card would then fill the whole list.
    app.update_idletasks()
    assert card._card.winfo_reqheight() < 100

    card.enabled_var.set(False)
    card._on_enabled_toggled()
    app.update()
    assert str(card._stripe.cget('bg')) == TK_COLORS['border']
    assert str(card._card.cget('highlightbackground')) == TK_COLORS['border']


def test_drag_handle_stays_lit_while_focused(app):
    """Hover and focus are independent inputs: mousing off a focused handle
    must not erase the only cue that Alt+↑/↓ is armed."""
    from kazbars.ui_helpers import THEME_COLORS
    card, _ = _add_seam_grid(app, 'SeamHandle')
    card._paint_drag_handle(focus=True)
    card._paint_drag_handle(hover=True)
    card._paint_drag_handle(hover=False)
    assert str(card.drag_handle.cget('foreground')) == THEME_COLORS['heading']
    card._paint_drag_handle(focus=False)
    assert str(card.drag_handle.cget('foreground')) == THEME_COLORS['muted']


def test_extras_row_packed_at_bottom(app):
    assert app.grids_panel.extras_row.pack_info()['side'] == 'bottom'


def test_toast_guards_the_whole_bottom_strip(app):
    """Both widgets the Grids tab pins to the toast strip are guarded, in the
    order they stack."""
    gp = app.grids_panel
    assert app.toast._bottom_guards == (gp.extras_row, gp.build_status_lbl)


# ============================================================================
# ROUND-2 LAYOUT GUARDS (rides the same app instance)
# ============================================================================
# Real geometry is unreadable here — the fixture's app is withdrawn, so every
# winfo_width/height is 1 and geometry() is "1x1+0+0". Requested sizes DO
# resolve, so these pin the two things that are checkable headlessly: the pure
# fit function, and that each panel's status render is wired to it. Whether the
# window visibly follows needs manual QA.

class _StubWindow:
    """Minimal window surface `fit_window_height` touches."""

    def __init__(self, height, reqheight):
        self._height, self._reqheight = height, reqheight
        self.geometry_calls = []

    def update_idletasks(self):
        pass

    def winfo_reqheight(self):
        return self._reqheight

    def winfo_height(self):
        return self._height

    def winfo_x(self):
        return 100

    def winfo_y(self):
        return 100

    def geometry(self, spec):
        self.geometry_calls.append(spec)


def test_fit_window_height_follows_its_content():
    from kazbars.window_position import fit_window_height
    grown = _StubWindow(height=744, reqheight=759)
    fit_window_height(grown, 440)
    assert grown.geometry_calls and grown.geometry_calls[0].startswith('440x759+')

    settled = _StubWindow(height=744, reqheight=744)
    fit_window_height(settled, 440)
    assert settled.geometry_calls == []          # no churn on the status tick


def test_deeps_status_render_refits_the_panel(app, monkeypatch):
    """A long log filename wraps the status line to two rows. The panel locked
    its height at build time, so without this the pet caveat — its own last
    line, with no scrollbar to reach it — falls off the bottom edge."""
    from kazbars import deeps_panel as dp
    from kazbars.deeps_meter import MeterSnapshot, Status
    app._open_deeps_panel()
    app.update()
    panel = app.deeps_panel
    panel.update_idletasks()
    before = panel.winfo_reqheight()

    calls = []
    monkeypatch.setattr(dp, 'fit_window_height', lambda w, width: calls.append((w, width)))
    monkeypatch.setattr(panel.meter, 'is_running', lambda: True)
    panel._render_status(MeterSnapshot(
        dps=None, dpis=None, hps=None, hps_out=None, status=Status.OLD_LOG,
        log_filename='Combat_2026-09-22_18-42-11_Kazour_Fury_of_Crom.txt'))
    panel.update_idletasks()

    assert panel.winfo_reqheight() > before      # the wrap really does grow it
    assert calls == [(panel, dp._PANEL_DEFAULT_WIDTH)]
    _close_via_protocol(panel)
    app.update()


def test_live_tracker_status_render_refits_the_panel(app, monkeypatch):
    from kazbars import live_tracker_panel as lt
    app._open_boss_timer()
    app.update()
    panel = app.boss_timer_panel

    calls = []
    monkeypatch.setattr(lt, 'fit_window_height', lambda w, width: calls.append((w, width)))
    panel._render_status()
    assert calls == [(panel, lt._PANEL_DEFAULT_WIDTH)]
    _close_via_protocol(panel)
    app.update()


def test_start_button_label_fits_its_button(app):
    """`BTN_LARGE` is 20 average character widths (146px here), not 20 glyphs.
    Rendered pixels are the rule that matters — pins the disabled label, which a
    character count reads as one over budget and clipped when it is neither."""
    from tkinter import font as tkfont

    from kazbars.ui_forms import toggle_button_state
    app._open_deeps_panel()
    app.update()
    panel = app.deeps_panel
    label = toggle_button_state(running=False, enabled=False,
                                disabled_label='Set game folder first')[0]
    panel._start_btn.configure(text=label)
    app.update_idletasks()
    assert tkfont.Font(font='TkDefaultFont').measure(label) < panel._start_btn.winfo_reqwidth()
    _close_via_protocol(panel)
    app.update()


# ============================================================================
# EXTRAS CARDS: TWO CONTROLS (rides the same app instance)
# ============================================================================
# The card body opens the feature's Extras dialog; the round switch flips what
# the next build bakes. Tk delivers <Button-1> to the widget under the pointer
# and never walks it up to the parent, so the switch's hit area is the switch.

EXTRAS_OPENERS = {
    'cast_timer': '_open_cast_timer_settings',
    'console': '_open_console_settings',
    'damage_numbers': '_open_damage_numbers',
    'inspect': '_open_inspect_settings',
    'onslaught': '_open_onslaught_settings',
    'stopwatch': '_open_stopwatch_settings',
}


def test_extras_openers_exist_on_the_app(app):
    """A card routes its click through `getattr(app, opener)`. Renaming an
    opener would break the card silently — nothing else resolves these names."""
    from kazbars.extras_shortcuts import _FEATURES
    named = {spec[0]: spec[4] for spec in _FEATURES}
    assert named == EXTRAS_OPENERS
    for opener in named.values():
        assert callable(getattr(app, opener))


@pytest.mark.parametrize('key', list(EXTRAS_OPENERS))
def test_extras_card_click_opens_settings(app, monkeypatch, key):
    opened = []
    for feature_key, opener in EXTRAS_OPENERS.items():
        monkeypatch.setattr(app, opener, lambda k=feature_key: opened.append(k))
    tile = app.grids_panel.extras_row._tiles[key]
    before = bool(tile['var'].get())

    tile['card'].event_generate('<Button-1>', x=5, y=5)
    app.update()

    assert opened == [key]
    assert bool(tile['var'].get()) is before      # the click did not flip it


def test_extras_switch_toggles_without_opening_settings(app, monkeypatch):
    from tkinter import ttk
    opened = []
    for opener in EXTRAS_OPENERS.values():
        monkeypatch.setattr(app, opener, lambda: opened.append(opener))
    tile = app.grids_panel.extras_row._tiles['stopwatch']
    switch = _widgets(tile['card'], ttk.Checkbutton)[0]
    before = bool(tile['var'].get())

    switch.event_generate('<Button-1>', x=5, y=5)
    switch.event_generate('<ButtonRelease-1>', x=5, y=5)
    app.update()

    assert bool(tile['var'].get()) is not before
    assert app.profile_store.get_section('stopwatch')['enabled'] is not before
    assert opened == []


def test_extras_card_hover_zones(app):
    """One painter drives both zones: hovering the body lights the card
    border; hovering the switch cell lights the switch instead and leaves
    the card at its resting/state colour; and a state flip while the body
    is hovered must not drop the border back to resting underneath the
    pointer (the measured bug — refresh() used to repaint unconditionally)."""
    from kazbars.extras_shortcuts import _HOVER_BORDER
    row = app.grids_panel.extras_row
    tile = row._tiles['inspect']
    card, switch_cell = tile['card'], tile['switch_cell']

    card.event_generate('<Enter>')
    app.update()
    assert str(card.cget('highlightbackground')) == _HOVER_BORDER

    switch_cell.event_generate('<Enter>')
    app.update()
    assert str(card.cget('highlightbackground')) != _HOVER_BORDER
    assert str(switch_cell.cget('highlightbackground')) == _HOVER_BORDER

    card.event_generate('<Enter>')
    app.update()
    before = tile['on']
    try:
        app.profile_store.update_section('inspect', {'enabled': not before})
        row.refresh()
        assert str(card.cget('highlightbackground')) == _HOVER_BORDER
    finally:
        app.profile_store.update_section('inspect', {'enabled': before})
        row.refresh()


def test_extras_card_click_clears_the_hover(app, monkeypatch):
    """Opening a dialog can grab_set() every pointer event the app gets from
    here on, so the card may never see the <Leave> that would otherwise turn
    its border off — it used to stay lit long after the dialog opened."""
    from kazbars.extras_shortcuts import _HOVER_BORDER
    row = app.grids_panel.extras_row
    tile = row._tiles['cast_timer']
    monkeypatch.setattr(app, '_open_cast_timer_settings', lambda: None)

    tile['card'].event_generate('<Enter>')
    app.update()
    assert str(tile['card'].cget('highlightbackground')) == _HOVER_BORDER

    tile['card'].event_generate('<Button-1>', x=5, y=5)
    app.update()
    assert str(tile['card'].cget('highlightbackground')) != _HOVER_BORDER


def test_extras_card_tooltip_reaches_labels(app):
    """Every widget the open-settings click is bound to also carries its own
    tooltip — Tk hides a parent's tooltip the instant the pointer crosses
    onto a child, so the card frame alone isn't enough to reach the title
    or status line."""
    tile = app.grids_panel.extras_row._tiles['damage_numbers']
    card = tile['card']
    body = card.winfo_children()[0]
    text = next(w for w in body.winfo_children() if w is not tile['switch_cell'])
    title_lbl, status_lbl = text.winfo_children()
    for w in (card, body, text, title_lbl, status_lbl):
        assert getattr(w, '_kz_tooltip', None) is not None


# ============================================================================
# EVERY DIALOG CONFIRMS ON ENTER (WHERE ONE EXISTS) AND OPENS FOCUSED
# ============================================================================
# focus_set() is a no-op while the fixture's app is withdrawn (real focus
# needs a mapped window — see test_alt_arrow_moves_grid above), so this pins
# that a focus_set call happened at all, not which widget ended up focused;
# whether the right one did needs manual QA. show_about isn't part of this
# dialog inventory (a frameless popup, not one of the 16) and is excluded.
_DIALOG_OPENERS = [(m, g) for m, g in OPENERS if m != '_show_about']

# The two persistent panels have no single OK — Start/Stop takes the initial
# focus instead, and ttkbootstrap's own TButton class binding already lets
# Enter reach a focused button for free, so they deliberately bind no <Return>.
_NO_RETURN_BINDING = {'_open_boss_timer', '_open_deeps_panel'}

# damage_number_colors and buff_display_editor only pick an initial focus
# target once they find real game XML to read — the fixture's fake install
# is otherwise just an empty Data/Gui tree, which parks both in their
# "nothing to show" state before ever reaching that code.
_MIN_BUFFLISTVIEW = '<BuffListView icon_size="31" icon_spacing="2" max_columns="6" filter="friendly"/>'


def _seed_game_xml(app):
    from kazbars.buff_xml import BUFF_FILES
    gui_default = Path(app.game_path) / 'Data' / 'Gui' / 'Default'
    (gui_default / 'TextColors.xml').write_text('<TextColors/>', encoding='utf-8')
    for _label, relpath in BUFF_FILES:
        path = gui_default / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_MIN_BUFFLISTVIEW, encoding='utf-8')


@pytest.mark.parametrize('method,getter', _DIALOG_OPENERS, ids=[m for m, _ in _DIALOG_OPENERS])
def test_dialogs_confirm_and_focus(app, monkeypatch, method, getter):
    """Runs after the rest of the module, so the two single-instance panels
    (Deeps, Live Tracker) may already be alive-but-withdrawn from an earlier
    test — their opener then re-shows with focus_force(), not the fresh
    focus_set() __init__ sets on a real first open. Both count here."""
    _seed_game_xml(app)
    calls = []
    orig_focus_set = tk.Misc.focus_set
    orig_focus_force = tk.Misc.focus_force

    def _record(fn):
        def _wrapped(self, *a, **k):
            calls.append(self)
            return fn(self, *a, **k)
        return _wrapped

    monkeypatch.setattr(tk.Misc, 'focus_set', _record(orig_focus_set))
    monkeypatch.setattr(tk.Misc, 'focus_force', _record(orig_focus_force))

    getattr(app, method)()
    app.update()
    panel = getter(app)
    assert panel is not None
    assert calls, f'{method}: no focus_set/focus_force call while opening'

    bound = bool(panel.bind('<Return>'))
    if method in _NO_RETURN_BINDING:
        assert not bound, f'{method}: persistent panel should not bind <Return>'
    else:
        assert bound, f'{method}: no <Return> bound for its primary action'

    _close_via_protocol(panel)
    app.update()


def _card_for(app, grid):
    gp = app.grids_panel
    gp.grids.append(grid)
    gp.refresh_panels()
    app.update()
    return gp.grid_panels[-1]


class _FakePicker:
    """BuffSelectorDialog stand-in: records how it was opened, answers `result`."""
    opened: list = []
    result = None

    def __init__(self, parent, database, title, initial_ids=None, layout='mixed', walker=None):
        start = walker.ids(walker.start) if walker is not None else initial_ids
        _FakePicker.opened.append((title, list(start or [])))
        self.result = _FakePicker.result
        if walker is not None and self.result is not None:
            walker.commit(walker.start, self.result)  # what Done does


def test_a_static_cell_opens_the_picker_on_its_slot_and_repaints_that_cell(app, monkeypatch):
    from kazbars import grid_editor_panel
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, dict(create_default_grid('player', 3, 3, 'static', 'SeamSlots'),
                               slotAssignments={'4': [11]}))
    monkeypatch.setattr(grid_editor_panel, 'BuffSelectorDialog', _FakePicker)
    monkeypatch.setattr(card, 'wait_window', lambda d: None)
    painted = []
    real = card.preview.repaint_slot
    monkeypatch.setattr(card.preview, 'repaint_slot', lambda i: (painted.append(i), real(i)))
    _FakePicker.opened, _FakePicker.result = [], [21, 22]

    card.preview._activate(4)
    assert _FakePicker.opened == [('Slot 4 Buffs', [11])]
    assert card.grid_config['slotAssignments'] == {'4': [21, 22]}
    assert painted == [4], "only that cell repaints"
    assert card.summary_label.cget('text') == 'static'
    stored = app.profile_store.get_section('grids')['grids'][-1]
    assert stored['slotAssignments'] == {'4': [21, 22]}


def test_the_slot_picker_walks_the_grid_committing_each_slot_it_leaves(app):
    from kazbars.grid_dialogs import BuffSelectorDialog
    from kazbars.grid_editor_panel import _SlotWalker
    from kazbars.grid_model import create_default_grid
    a, b = (e['ids'][0] for e in app.database.grouped_buffs[:2])
    card = _card_for(app, dict(create_default_grid('player', 1, 3, 'static', 'SeamWalk'),
                               slotAssignments={'0': [a]}))
    walker = _SlotWalker(card, 0)
    dlg = BuffSelectorDialog(app, app.database, "Slot 0 Buffs", walker=walker)
    try:
        dlg.go_to(1)
        dlg.go_to(0)
        assert not walker.committed, "walking past an untouched slot writes nothing"
        assert len(dlg._chips.find_withtag('rect')) == 3
        assert str(dlg._step_buttons[-1].cget('state')) == 'disabled'
        dlg.selected_names.add(app.database.by_id[b]['name'])
        dlg.go_to(1)  # leaving slot 0 commits it
        assert sorted(card.grid_config['slotAssignments']['0']) == sorted([a, b])
        assert (dlg.slot, dlg.title(), dlg.selected_names) == (1, 'Slot 1 Buffs', set())
        assert dlg._step_key(1) == 'break' and dlg.slot == 2
        assert str(dlg._step_buttons[1].cget('state')) == 'disabled'
        dlg.selected_names.add(app.database.by_id[a]['name'])
        dlg.on_cancel()  # drops only the current slot's edit
        assert '2' not in card.grid_config['slotAssignments'] and walker.committed
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_a_right_click_clears_a_slot_and_the_toast_puts_it_back(app, monkeypatch):
    from kazbars import grid_editor_panel
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, dict(create_default_grid('target', 2, 2, 'static', 'SeamClear'),
                               slotAssignments={'0': [7], '3': [8]}))
    toasts = []
    monkeypatch.setattr(grid_editor_panel, 'app_toast',
                        lambda w, msg, *a, **k: toasts.append((msg, k.get('on_click'))))
    card.preview._clear(0)
    card.preview._clear(3)
    assert card.grid_config['slotAssignments'] == {}
    assert toasts[-1][0] == 'Cleared slot 3 — click to undo'
    assert grid_editor_panel.grid_preview.empty_nudge(card.grid_config) == card.names_var.get()
    toasts[-1][1]()  # the toast's click
    assert card.grid_config['slotAssignments'] == {'0': [7], '3': [8]}
    rect = card.preview.find_withtag('slot_3&&rect')
    assert card.preview.itemcget(rect, 'fill') == card._accent_color
    card.preview._clear(1)  # an empty slot: nothing to clear
    assert len(toasts) == 2

    # A slot the grid shrank past stays cleared on undo.
    card.preview._clear(3)
    card.apply_settings(dict(card.grid_config, rows=1))
    toasts[-1][1]()
    assert '3' not in card.grid_config['slotAssignments']


def test_an_undo_lands_on_the_card_a_rebuild_put_in_its_place(app, monkeypatch):
    from kazbars import grid_editor_panel
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, dict(create_default_grid('player', 1, 3, 'static', 'SeamRebuilt'),
                               slotAssignments={'1': [9]}))
    toasts = []
    monkeypatch.setattr(grid_editor_panel, 'app_toast',
                        lambda w, msg, *a, **k: toasts.append(k.get('on_click')))
    card.preview._clear(1)
    app.grids_panel.refresh_panels()  # an add, delete or move within the toast's life
    toasts[-1]()
    fresh = app.grids_panel.grid_panels[-1]
    assert fresh is not card and fresh.grid_config['slotAssignments'] == {'1': [9]}
    assert app.profile_store.get_section('grids')['grids'][-1]['slotAssignments'] == {'1': [9]}


def test_the_draft_previews_what_apply_stores(app):
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('player', 1, 5, 'static', 'SeamDraftFill'))
    dlg = _settings(card)
    dlg.rows_var.set('3')
    dlg.cols_var.set('3')  # typed, no arrow or focus-out: Enter applies it as is
    assert dlg.draft()['fillDirection'] == 'BL-TR', "a row's LR no longer fits a box"
    dlg.rows_var.set('10')
    dlg.cols_var.set('8')
    assert (dlg.draft()['rows'], dlg.draft()['cols']) == (10, 6), "the slot limit holds"
    dlg.apply()
    cfg = card.grid_config
    assert (cfg['rows'], cfg['cols'], cfg['fillDirection']) == (10, 6, 'BL-TR')


def test_applying_a_smaller_shape_trims_slots_with_the_warning(app, monkeypatch):
    from kazbars import grid_editor_panel
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, dict(create_default_grid('player', 3, 3, 'static', 'SeamTrim'),
                               slotAssignments={'0': [1], '8': [2]}))
    toasts = []
    monkeypatch.setattr(grid_editor_panel, 'app_toast', lambda w, msg, *a, **k: toasts.append(msg))
    dlg = _settings(card)
    dlg.rows_var.set('4')
    dlg._on_shape('rows')
    assert (dlg.rows_var.get(), dlg.cols_var.get()) == ('4', '3'), "under the limit: as typed"
    dlg.rows_var.set('2')
    dlg.cols_var.set('2')
    dlg._on_shape('cols')
    dlg.apply()
    cfg = card.grid_config
    assert (cfg['rows'], cfg['cols'], cfg['slotAssignments']) == (2, 2, {'0': [1]})
    assert toasts and toasts[-1].startswith('Unassigned 1 buff')


def test_the_keyboard_slot_survives_the_picker_and_the_pointer_leaving(app):
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('player', 2, 3, 'static', 'SeamKeep'))
    preview = card.preview
    preview._set_hot(4)
    preview._set_hot(-1)  # what FocusOut does while the picker holds focus
    preview._set_hot(preview._kept)  # what FocusIn does on its return
    assert preview._hot == 4


def test_a_tall_grid_says_its_preview_stepped_down(app):
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('player', 6, 6, 'static', 'SeamTall'))
    summary = card.summary_label.cget('text')
    assert summary.endswith('· shown at 2:5')
    assert card.preview.layout.height <= 128


def test_a_disabled_card_drains_its_preview(app):
    from kazbars.grid_model import create_default_grid
    from kazbars.ui_helpers import TK_COLORS
    card = _card_for(app, dict(create_default_grid('player', 1, 3, 'dynamic', 'SeamDrain'),
                               whitelist=[5]))
    rect = card.preview.find_withtag('slot_0&&rect')
    assert card.preview.itemcget(rect, 'fill') == card._accent_color
    card.enabled_var.set(False)
    card._on_enabled_toggled()
    assert card.preview.itemcget(rect, 'fill') == TK_COLORS['border']
    assert card.names_var.get()  # the names line stays


def test_a_band_card_redraws_when_its_row_cap_changes(app):
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('friendly', 2, 5, 'dynamic', 'SeamBandDraw'))
    lay = card.preview.layout
    assert len(lay.rects) == 10 and lay.rects[0][1] > lay.rects[9][1]  # rows from the bottom
    dlg = _settings(card)
    dlg.row_cap_var.set(3)
    dlg._changed()
    assert card.preview.layout.width < lay.width and len(card.preview.layout.rects) == 10
    dlg.apply()
    assert card.grid_config['rowCap'] == 3


def test_step_arrows_move_a_card_and_grey_at_the_ends(app):
    from kazbars.ui_helpers import TK_COLORS
    gp = app.grids_panel
    _add_seam_grid(app, 'SeamStepA')
    _add_seam_grid(app, 'SeamStepB')
    first, last = gp.grid_panels[0], gp.grid_panels[-1]
    assert not first._step_labels[-1].live and first._step_labels[1].live
    assert not last._step_labels[1].live
    assert str(last._step_labels[1].cget('foreground')) == TK_COLORS['menu_disabled_fg']
    last._on_step(last, -1)
    ids = [g['id'] for g in app.profile_store.get_section('grids')['grids']]
    assert ids[-2:] == ['SeamStepB', 'SeamStepA']


def test_a_band_card_writes_its_cap_slots_and_overhead_keys(app):
    from kazbars.grid_model import create_default_grid
    gp = app.grids_panel
    gp.grids.append(create_default_grid('friendly', 2, 5, 'dynamic', 'SeamBand'))
    gp.refresh_panels()
    app.update()
    card = gp.grid_panels[-1]
    dlg = _settings(card)
    assert not hasattr(dlg, 'x_var'), "a band has no screen position"
    assert dlg.fill_var.get() == 'Centred'
    dlg.row_cap_var.set(7)
    dlg.max_slots_var.set('9')
    dlg.max_distance_var.set('60')
    dlg.show_self_var.set(False)
    dlg.apply()
    cfg = card.grid_config
    assert (cfg['rowCap'], cfg['maxSlots'], cfg['rows'], cfg['cols']) == (7, 9, 2, 7)
    assert (cfg['maxDistance'], cfg['showSelf'], cfg['fillDirection']) == (60, False, 'C')


def test_applied_by_me_is_a_toggle_on_the_card(app):
    card, idx = _add_seam_grid(app, 'SeamSelfCast')
    card.self_cast_var.set(True)
    card._on_self_cast_toggled()
    assert _stored_grid(app, idx)['selfCastOnly'] is True
    card.self_cast_var.set(False)
    card._on_self_cast_toggled()
    assert 'selfCastOnly' not in _stored_grid(app, idx)
    assert card.summary_label.cget('text') == 'dynamic'


def test_the_dialog_lines_its_labels_up_in_one_column(app):
    from tkinter import ttk

    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('friendly', 2, 5, 'dynamic', 'SeamAlign'))
    dlg = _settings(card)
    try:
        cards = _widgets(dlg, ttk.LabelFrame)
        assert len(cards) == 4
        widths = {int(c.columnconfigure(0)['minsize']) for c in cards}
        assert len(widths) == 1 and widths.pop() > 0
    finally:
        dlg.cancel()


def test_enter_on_cancel_cancels_and_hotkeys_wait_for_the_dialog(app, monkeypatch):
    import copy
    card, _ = _add_seam_grid(app, 'SeamEnter')
    before = copy.deepcopy(card.grid_config)
    dlg = _settings(card)
    fired = []
    app._hotkey(lambda: fired.append(1))(None)
    assert fired == [], "a shortcut under the dialog's grab is swallowed"
    dlg.gap_var.set('9')
    monkeypatch.setattr(dlg, 'focus_get', lambda: dlg._cancel_btn)
    dlg._on_return(None)
    assert not dlg.winfo_exists() and card.grid_config == before
    app._hotkey(lambda: fired.append(1))(None)
    assert fired == [1]


def test_a_hostile_box_has_overhead_settings_and_no_sorting(app):
    from kazbars.grid_model import create_default_grid
    card = _card_for(app, create_default_grid('hostile', 2, 3, 'static', 'SeamHostileBox'))
    dlg = _settings(card)
    try:
        from tkinter import ttk
        titles = {str(w.cget('text')) for w in _widgets(dlg, ttk.LabelFrame)}
        assert titles == {'Grid', 'Icons', 'Overhead'}
        assert hasattr(dlg, 'rows_var') and not hasattr(dlg, 'fill_var')
    finally:
        dlg.cancel()


def test_the_cog_opens_settings_and_a_taken_name_blocks_apply(app):
    card, _ = _add_seam_grid(app, 'SeamCog')
    _add_seam_grid(app, 'SeamTaken')
    card = app.grids_panel.grid_panels[-2]
    assert card.cog_label.bind('<Return>') and card.cog_label.cget('takefocus')
    card.open_settings()
    dlg = card.settings_dialog
    assert dlg is not None and dlg.winfo_exists()
    dlg.id_var.set('SeamTaken')
    dlg.apply()
    assert dlg.winfo_exists() and 'already' in dlg._name_hint.cget('text')
    assert card.grid_config['id'] == 'SeamCog'
    dlg.cancel()


def _wizard_grid(app, gtype, setup):
    from kazbars.grid_dialogs import AddGridWizard
    wiz = AddGridWizard(app, set(), name_in_use=lambda name, cfg: False)
    try:
        wiz.type_var.set(gtype)
        wiz._on_type_changed()
        setup(wiz)
        wiz.on_create()
        return wiz.result
    finally:
        if wiz.winfo_exists():
            wiz.destroy()


def test_the_add_grid_wizard_makes_bands_with_a_snapped_row_cap(app):
    def custom(wiz):
        wiz.mode_var.set('dynamic')
        wiz._on_mode_changed()
        wiz.cols_var.set('4')
        wiz.rows_var.set('9')
        wiz.on_cols_changed()
        assert (wiz.rows_var.get(), wiz.cols_var.get()) == ('3', '5')
        assert wiz.shape_var.get() == 'Band: up to 15 icons, 5 to a row'
        assert wiz.limit_var.get() == ('An overhead grid holds up to 16 slots, '
                                       'at most 4 rows or 8 columns')
    grid = _wizard_grid(app, 'hostile', custom)
    assert (grid['type'], grid['rowCap'], grid['maxSlots']) == ('hostile', 5, 15)

    def single(wiz):
        wiz.mode_var.set('dynamic')
        wiz._on_mode_changed()
        wiz.apply_preset(1, 1)
        assert wiz.shape_var.get() == 'Band: up to 1 icon, 3 to a row'
    grid = _wizard_grid(app, 'friendly', single)
    assert (grid['slotMode'], grid['rowCap'], grid['maxSlots']) == ('dynamic', 3, 1)


def test_class_tabs_list_their_own_grids_and_switching_recreates_no_card(app):
    from kazbars.grid_model import create_default_grid
    gp = app.grids_panel
    gp._tab_var.set(0)
    gp.grids.append(create_default_grid('player', 1, 5, 'dynamic', 'TabAll'))
    gp.grids.append(dict(create_default_grid('player', 1, 5, 'dynamic', 'TabDT'), **{'class': 31}))
    gp.refresh_panels()
    app.update()
    cards = list(gp.grid_panels)
    by_id = {p.grid_config['id']: p for p in cards}
    assert by_id['TabAll'].winfo_manager() == 'pack'
    assert by_id['TabDT'].winfo_manager() == ''
    gp._tab_var.set(31)
    gp._on_tab_changed()
    app.update()
    assert gp.grid_panels == cards, "a tab switch only repacks"
    assert by_id['TabDT'].winfo_manager() == 'pack' and by_id['TabAll'].winfo_manager() == ''
    assert gp._tab_buttons[31][0].cget('text') == 'DT 1'
    gp.move_or_copy(by_id['TabDT'], 0, copy_it=True)
    copied = gp.grids[-1]
    assert copied['id'] == 'TabDT All' and 'class' not in copied
    gp.move_or_copy(gp.grid_panels[gp.grids.index(next(g for g in gp.grids if g['id'] == 'TabDT'))], 22, copy_it=False)
    assert next(g for g in gp.grids if g['id'] == 'TabDT')['class'] == 22
    gp._tab_var.set(0)
    gp._on_tab_changed()
