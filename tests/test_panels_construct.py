"""Panel-construction smoke test — boots a real KazBarsApp and opens every
satellite panel through its app-side opener, catching "panel won't even
construct" breakage (bad widget kwarg, renamed design token, missing app
attribute, broken import wiring) in seconds instead of at manual /smoke.

Scope: construction + the panel's own close path only. Event flow, visual
correctness, and drag/animation behavior stay /smoke. Deferred to v2 (need a
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
    reason='Tk UI smoke is Windows-only (matches /smoke and CI)',
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
    from kazbars.prefs import Prefs

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
    prefs = Prefs(userdata.userdata_root())
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


# ============================================================================
# OPENERS UNDER TEST
# ============================================================================
# (KazBarsApp method, getter for the window it constructs). Openers are the
# contract users hit — raw constructors would pass while the menu wiring 404s.
OPENERS = [
    ('_open_boss_timer', lambda a: a.boss_timer_panel),
    ('_open_deeps_panel', lambda a: a.deeps_panel),
    ('_open_damage_numbers', lambda a: a.damage_numbers_panel),
    ('_open_damage_number_colors', lambda a: a.damage_number_colors_panel),
    ('_open_profile_manager', lambda a: a._profile_manager),
    ('_open_buff_display_editor', _find_buff_display_dialog),
    ('_show_about', lambda a: a._about_popup),
]

# Opener-shaped KazBarsApp methods this test deliberately does not exercise.
DEFERRED = {
    '_open_backup_dialog': 'settings_backup dialog — v2',
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
