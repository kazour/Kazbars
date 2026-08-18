"""Pin the panel-family layout ratios to their historical FS-12 values.

The stubs used to carry their dimensions as literals baked at font size 12;
they are now ``Math.round(FS * ratio)``, so the four in-game panels fold to the
same bar at *every* size rather than only at 12. The family-shared block lives
in ``KazBarsPanel.applyBaseSize`` and each panel declares only its extras. This
test is the proof the ratio-isation changed nothing at 12: every ratio below,
evaluated at FS 12, must equal the literal the stub used to ship.

Nothing else reads either stub's content -- ``test_build_compile.py`` proves only
that the AS2 compiles -- so a mistyped ratio would otherwise reach a build
silently. See docs/inspect-panel.md section 5.
"""

import math
import re
from pathlib import Path

import pytest

STUBS = (
    Path(__file__).resolve().parents[1]
    / 'src' / 'kazbars' / 'assets' / 'kazbars' / 'stubs'
)

# constant -> (ratio, the literal the stub shipped before ratio-isation)
# The family-shared block lives in KazBarsPanel.applyBaseSize; panels declare
# only their own extras on top of it.
BASE_RATIOS = {
    'PAD': (0.85, 10),
    'TITLE_H': (1.85, 22),
    'LINE': (1.4, 17),
    'BOX': (1.0, 12),
    'BTN': (1.1, 13),
    'BTN_W': (5.0, 60),
    'BTN_H': (1.85, 22),
    'NAME_FS': (1.15, 14),
    'COLL_W': (15.8, 190),
    'COLL_H': (2.0, 24),
    'COLL_PAD': (0.55, 7),
}

CONSOLE_RATIOS = {
    'HDR_Y': (2.75, 33),
    'BODY_Y': (4.67, 56),
    'COL_W': (19.17, 230),
    # Were inline `CH - 35` / `CH - BODY_Y - 40` -- the Clear button's band.
    'RULE_BOT': (2.92, 35),
    'LOG_BOT': (3.33, 40),
    'CW_FULL': (41.67, 500),
    'CW_ONE': (23.33, 280),
    'CH_FULL': (26.67, 320),
    'CH_NONE': (8.33, 100),
    'CB_OFF': (9.17, 110),
}

PREVIEW_RATIOS = {
    'ROW_H': (1.667, 20),
    'COL_W': (18.33, 220),
}

# Text sizes are written inline at the makeTF call, the family's idiom, so they
# are pinned by formula rather than by constant name.
TEXT_RATIOS = {0.9: 11, 0.8: 10}

STUB_TABLES = {
    'KazBarsPanel.as': BASE_RATIOS,
    'KazBarsConsole.as': CONSOLE_RATIOS,
    'KazBarsPreviewPanel.as': PREVIEW_RATIOS,
}

# The two stubs that build without ever being configured first (the stopwatch
# and inspect panel are always configured before createPanel).
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


@pytest.mark.parametrize('stub', sorted(STUB_TABLES))
def test_stub_declares_exactly_the_pinned_ratios(stub):
    assert _declared_ratios(stub) == {
        name: ratio for name, (ratio, _) in STUB_TABLES[stub].items()
    }, f'{stub} ratio block drifted from the pinned table'


@pytest.mark.parametrize('stub', sorted(STUB_TABLES))
def test_every_ratio_lands_on_its_historical_value_at_fs_12(stub):
    for name, (ratio, expected) in STUB_TABLES[stub].items():
        assert _as2_round(12 * ratio) == expected, (
            f'{stub}: {name} = round(12 * {ratio}) is {_as2_round(12 * ratio)}, '
            f'not the {expected} it shipped at'
        )


def test_text_size_ratios_land_on_their_historical_values_at_fs_12():
    for ratio, expected in TEXT_RATIOS.items():
        assert max(9, _as2_round(12 * ratio)) == expected


def test_preview_panel_row_offsets_land_on_their_historical_values_at_fs_12():
    # BTN_Y / ROWS_Y stack off the constants above rather than off FS alone.
    title_h, btn_h = 22, 22
    btn_y = title_h + _as2_round(12 * 0.5)
    rows_y = btn_y + btn_h + _as2_round(12 * 0.85)
    assert (btn_y, rows_y) == (28, 60)


def test_checkmark_path_reproduces_the_12px_box_coordinates():
    # Was moveTo(2, 6) / lineTo(5, 10) / lineTo(10, 2) at lineStyle(2, ...).
    # The drawing lives once, in the family base.
    box = 12
    assert max(1, _as2_round(box / 6)) == 2
    assert (_as2_round(box / 6), _as2_round(box / 2)) == (2, 6)
    assert (_as2_round(box * 5 / 12), _as2_round(box * 5 / 6)) == (5, 10)
    assert (_as2_round(box * 5 / 6), _as2_round(box / 6)) == (10, 2)
    assert 'chk.lineStyle(Math.max(1, Math.round(BOX / 6))' in _source('KazBarsPanel.as')


def test_console_log_entry_font_keeps_its_face_and_reproduces_size_11():
    # Scaleform re-parses htmlText from scratch: an untagged run falls through
    # to Times New Roman via the Win32 font provider, whatever the TextFormat says.
    src = _source('KazBarsConsole.as')
    assert '\'<font face="Arial" size="\'' in src
    assert 'Math.max(9, Math.round(FS * 0.9)) + \'" color="\'' in src
    assert max(9, _as2_round(12 * 0.9)) == 11


@pytest.mark.parametrize('stub', sorted(SELF_INIT_STUBS))
def test_stub_self_initialises_instead_of_bailing_on_a_null_config(stub):
    # Neither stub is configured before it builds today, so copying the
    # stopwatch's `if (cfg == null) return;` would leave every constant NaN --
    # and MTASC would still compile it.
    src = _source(stub)
    assert 'if (cfg == null) cfg = {};' in src
    assert 'if (cfg == null) return;' not in src
    assert 'configure(null);' in src
