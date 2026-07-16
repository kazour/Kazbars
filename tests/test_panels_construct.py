"""Panel-construction smoke test — boots a real KazBarsApp and opens every
satellite panel through its app-side opener, catching "panel won't even
construct" breakage (bad widget kwarg, renamed design token, missing app
attribute, broken import wiring) in seconds instead of at manual QA.

Scope: construction + the panel's own close path, plus ui_widgets binding
hygiene (which must ride this module's Tk instance — see the section note at
the bottom). Event flow, visual correctness, and drag/animation behavior stay
manual QA. Deferred to v2 (need a
data context or block on wait_window): AddGridWizard, BuffSelectorDialog,
SlotAssignmentDialog, BuffEditDialog, the first-launch dialog,
show_close_game_required_dialog, BuildLoadingScreen, the settings_backup
dialog, show_welcome_popup.

The fixture neutralizes the two network entry points fired by
KazBarsApp.__init__ (update_check, content_update), relocates userdata/ to a
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
    from kazbars import content_update, update_check, userdata
    from kazbars.prefs import PREFS_SCHEMA
    from kazbars.settings_core import Store

    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp('userdata_home')
    fake_game = root / 'AoC'
    (fake_game / 'Data' / 'Gui' / 'Default' / 'Flash').mkdir(parents=True)

    mp.setattr(userdata, 'app_path', lambda: root)
    mp.setattr(update_check, 'check_for_updates', lambda *a, **k: None)
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
        # _on_close runs _check_unsaved_changes, which raises a blocking
        # Messagebox when dirty — force clean so teardown can never hang.
        a.modified = False
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
    ('_open_profile_manager', lambda a: a._profile_manager),
    ('_open_buff_display_editor', _find_buff_display_dialog),
    ('_open_stopwatch_settings', lambda a: a.stopwatch_dialog),
    ('_show_about', lambda a: a._about_popup),
]

# Opener-shaped KazBarsApp methods this test deliberately does not exercise.
DEFERRED = {
    '_open_backup_dialog': 'settings_backup dialog — v2',
    '_open_game_in_explorer': 'os.startfile shell-out, not a panel',
    '_open_profile': 'native file-open dialog — blocks, not a panel',
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
