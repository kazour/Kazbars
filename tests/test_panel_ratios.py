"""Pin the panel family's layout ratios and type roles.

Every dimension of the in-game panels is ``Math.round(FS * ratio)`` off the
panel's body size FS (baked from the overlay size, ``overlay_size.panel_fs``),
so the panels fold to the same bar at every size. The family-shared block lives
in ``KazBarsPanel.applyBaseSize`` and each panel declares only its extras; the
type sizes come from ``KazBarsPanel.roleFS`` and every text field is
``KazBarsPanel.lh`` tall. Nothing else reads the stubs' content —
``test_build_compile.py`` proves only that the AS2 compiles — so a mistyped
ratio would otherwise reach a build silently. Each table pins a stub's
declarations exactly, with the value it draws at the default FS 12.
"""

import math
import re
from pathlib import Path

import pytest

STUBS = (
    Path(__file__).resolve().parents[1]
    / 'src' / 'kazbars' / 'assets' / 'kazbars' / 'stubs'
)

# constant -> (ratio, its value at FS 12)
BASE_RATIOS = {
    'LEAD': (0.15, 2),
    'PAD': (0.85, 10),
    'BOX': (1.0, 12),
    'BTN': (1.1, 13),
    'BTN_W': (5.0, 60),
    'BTN_H': (1.85, 22),
    'BTN_GAP': (0.42, 5),
    'COLL_W': (15.8, 190),
    'COLL_H': (2.0, 24),
    'COLL_PAD': (0.55, 7),
}

CONSOLE_RATIOS = {
    'CW': (41.67, 500),
    'CH': (28.67, 344),
    'STRIP_Y': (2.6, 31),
    'TAB_GAP': (1.2, 14),
    'RULE_Y': (4.4, 53),
    'HEAD_Y': (4.85, 58),
    'COL_W': (19.17, 230),
    'RULE_BOT': (2.92, 35),
    'LOG_BOT': (3.33, 40),
}

PREVIEW_RATIOS = {
    'ROW_H': (1.667, 20),
    'COL_W': (18.33, 220),
    'HDR_GAP': (0.4, 5),
}

STOPWATCH_RATIOS = {
    'W': (15.8, 190),
    'H': (8.0, 96),
    'H_COLLAPSED': (2.0, 24),
    'TIME_FS': (2.0, 24),
    'TIME_H': (2.7, 32),
    'BTN_PAD': (0.5, 6),
}

STUB_TABLES = {
    'KazBarsPanel.as': BASE_RATIOS,
    'KazBarsConsole.as': CONSOLE_RATIOS,
    'KazBarsPreviewPanel.as': PREVIEW_RATIOS,
    'KazBarsStopwatch.as': STOPWATCH_RATIOS,
}

# The two stubs that build without ever being configured first (the stopwatch
# and inspect panel are always configured before create()).
SELF_INIT_STUBS = ('KazBarsConsole.as', 'KazBarsPreviewPanel.as')

# `NAME = Math.round(FS * 0.85);` and the bare `BOX = Math.round(FS);`
_ASSIGN = re.compile(r'^\s*([A-Z][A-Z0-9_]*) = Math\.round\(FS(?: \* ([0-9.]+))?\);$')


def _as2_round(value):
    """AS2 Math.round is round-half-up; Python's round() is round-half-even."""
    return math.floor(value + 0.5)


def _source(name):
    return (STUBS / name).read_text(encoding='utf-8')


def _declared_ratios(name):
    found = {}
    for line in _source(name).splitlines():
        m = _ASSIGN.match(line)
        if m:
            found[m.group(1)] = float(m.group(2)) if m.group(2) else 1.0
    return found


def _role_fs(base, k):
    """`KazBarsPanel.roleFS`: a role below Body is held at 9 and never above Body."""
    if k < 1:
        return max(min(9, base), _as2_round(base * k))
    return _as2_round(base * k)


@pytest.mark.parametrize('stub', sorted(STUB_TABLES))
def test_stub_declares_exactly_the_pinned_ratios(stub):
    assert _declared_ratios(stub) == {
        name: ratio for name, (ratio, _) in STUB_TABLES[stub].items()
    }, f'{stub} ratio block drifted from the pinned table'


@pytest.mark.parametrize('stub', sorted(STUB_TABLES))
def test_every_ratio_lands_on_its_pinned_value_at_fs_12(stub):
    for name, (ratio, expected) in STUB_TABLES[stub].items():
        assert _as2_round(12 * ratio) == expected, (
            f'{stub}: {name} = round(12 * {ratio}) is {_as2_round(12 * ratio)}, not {expected}')


def test_the_roles_and_the_line_box_are_the_ones_the_base_declares():
    src = _source('KazBarsPanel.as')
    assert 'return Math.round(size * 1.4);' in src
    assert 'if (k < 1) return Math.max(Math.min(9, base), Math.round(base * k));' in src
    for role, k in (('SMALL_FS', 0.8), ('NAME_FS', 1.25), ('ALERT_FS', 1.6)):
        assert f'{role} = roleFS(FS, {k});' in src, role
    assert 'TITLE_H = NAME_H + Math.round(FS * 0.25) * 2;' in src
    # At 12: Small 10, Title 15, Alert 19; Small never under 9 nor over Body.
    assert [_role_fs(12, k) for k in (0.8, 1.25, 1.6)] == [10, 15, 19]
    assert [_role_fs(b, 0.8) for b in (8, 9, 10, 11)] == [8, 9, 9, 9]


def test_the_stopwatch_folds_to_the_family_bar_at_every_size():
    # Its collapsed plate is the inspect panel's and the console's: COLL_W x COLL_H.
    assert STOPWATCH_RATIOS['W'][0] == BASE_RATIOS['COLL_W'][0]
    assert STOPWATCH_RATIOS['H_COLLAPSED'][0] == BASE_RATIOS['COLL_H'][0]


def test_checkmark_path_reproduces_the_12px_box_coordinates():
    box = 12
    assert max(1, _as2_round(box / 6)) == 2
    assert (_as2_round(box / 6), _as2_round(box / 2)) == (2, 6)
    assert (_as2_round(box * 5 / 12), _as2_round(box * 5 / 6)) == (5, 10)
    assert (_as2_round(box * 5 / 6), _as2_round(box / 6)) == (10, 2)
    assert 'chk.lineStyle(Math.max(1, Math.round(BOX / 6))' in _source('KazBarsPanel.as')


def test_every_text_field_asks_for_the_builds_face():
    # Scaleform re-parses htmlText from scratch: an untagged run falls through to
    # a serif device font, so the console's entries spell out the face and size.
    assert 'fmt.font = KazBarsPreview.FACE;' in _source('KazBarsPanel.as')
    assert ('ENTRY_FONT = \'<font face="\' + KazBarsPreview.FACE + \'" size="\' + FS + '
            '\'" color="#\';') in _source('KazBarsConsole.as')


@pytest.mark.parametrize('stub', sorted(SELF_INIT_STUBS))
def test_stub_self_initialises_instead_of_bailing_on_a_null_config(stub):
    # Copying the stopwatch's `if (cfg == null) return;` into a stub that builds
    # unconfigured would leave every constant NaN -- and as2c would still compile it.
    src = _source(stub)
    assert 'if (cfg == null) cfg = {};' in src
    assert 'if (cfg == null) return;' not in src
    assert 'configure(null);' in src
