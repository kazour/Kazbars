"""Tests for grid_preview — the pure geometry and text behind a grid card's
preview: slot placement per fill direction (pinned against the AS2 runtime's
`place()` / `band()` by hand-drawn tables), the to-scale ratio and its
step-down, the hit test and arrow-key steps, and the card's text lines.

No Tk: everything here is plain data.

Run: `pytest tests/test_grid_preview.py` (from repo root).
"""

import pytest

from kazbars import grid_preview as gp
from kazbars.grids_generator import grid_ships

# Each table is the grid as drawn on screen, row by row: the slot index at
# every (row, col). These are the AS2 runtime's placements.
_DRAWN = {
    (2, 3, 'TL-BR'): ((0, 1, 2), (3, 4, 5)),
    (2, 3, 'TR-BL'): ((2, 1, 0), (5, 4, 3)),
    (2, 3, 'BL-TR'): ((3, 4, 5), (0, 1, 2)),
    (2, 3, 'BR-TL'): ((5, 4, 3), (2, 1, 0)),
    (1, 3, 'LR'): ((0, 1, 2),),
    (1, 3, 'RL'): ((2, 1, 0),),
    (3, 1, 'TB'): ((0,), (1,), (2,)),
    (3, 1, 'BT'): ((2,), (1,), (0,)),
}


@pytest.mark.parametrize('key', list(_DRAWN))
def test_slots_sit_where_the_runtime_places_them(key):
    rows, cols, fill = key
    for r, line in enumerate(_DRAWN[key]):
        for c, slot in enumerate(line):
            assert gp.slot_pos(rows, cols, fill, slot) == (r, c)


def test_a_band_grows_from_the_bottom_each_row_centred():
    assert gp.band_positions(5, 1) == [(0, 0)]
    assert gp.band_positions(5, 2) == [(0, -1), (0, 1)]
    assert gp.band_positions(5, 5) == [(0, -4), (0, -2), (0, 0), (0, 2), (0, 4)]
    assert gp.band_positions(5, 7)[5:] == [(0, -1), (0, 1)]
    assert gp.band_positions(5, 7)[:5] == [(1, -4), (1, -2), (1, 0), (1, 2), (1, 4)]


def _lay(rows, cols, fill='LR', icon=48, gap=-1, band=None, max_w=600, max_h=128):
    return gp.layout(rows, cols, fill, icon=icon, gap=gap, band=band,
                     num=2, den=3, spacing=4, max_w=max_w, max_h=max_h)


def test_cells_and_gaps_round_to_whole_pixels_and_a_gap_never_closes():
    assert gp.cell_px(48, -1, 2, 3, 4) == (32, 2)
    assert gp.cell_px(52, 0, 2, 3, 4) == (35, 3)
    assert gp.cell_px(48, -5, 2, 3, 4) == (32, 1)
    assert gp.cell_px(48, -1, 2, 4, 4) == (24, 2)  # 1.5 rounds up


def test_the_default_grid_draws_two_px_per_three():
    lay = _lay(3, 4)
    assert (lay.den, lay.cell, lay.gap, lay.width, lay.height) == (3, 32, 2, 134, 100)
    assert gp.ratio_text(2, lay.den, 3) == ''


def test_a_tall_grid_steps_down_to_the_next_whole_ratio_that_fits():
    four = _lay(4, 4)
    assert (four.den, four.height) == (4, 102)
    assert gp.ratio_text(2, four.den, 3) == ' · shown at 1:2'
    six = _lay(6, 6)
    assert six.height <= 128 and gp.ratio_text(2, six.den, 3) == ' · shown at 2:5'
    wide = _lay(1, 64)
    assert wide.width <= 600 and wide.den > 3


def test_a_band_draws_at_its_max_slots_rows_from_the_bottom():
    lay = _lay(2, 5, band=(5, 7))
    assert (lay.width, lay.height) == (5 * 34 - 2, 2 * 34 - 2)
    bottom_left, top_left = lay.rects[0], lay.rects[5]
    assert bottom_left[1] == 34 and top_left[1] == 0
    # The two top icons sit astride the centre line.
    assert top_left[0] + lay.rects[6][2] == lay.width


def test_the_hit_test_names_the_cell_and_misses_the_gaps():
    lay = _lay(2, 3, 'BL-TR')
    assert gp.slot_at(lay, 0, 0) == 3
    assert gp.slot_at(lay, 33, 0) == -1  # in the gap after the first cell
    assert gp.slot_at(lay, 34 + 31, 34 + 31) == 1
    assert gp.slot_at(lay, lay.width + 5, 0) == -1


def test_arrow_steps_move_on_screen_and_stop_at_the_edges():
    lay = _lay(2, 3, 'TL-BR')
    assert gp.step(lay, 0, 1, 0) == 1
    assert gp.step(lay, 2, 1, 0) == 2
    assert gp.step(lay, 0, 0, 1) == 3
    assert gp.step(lay, -1, 1, 0) == 0
    band = _lay(2, 5, band=(5, 7))
    assert gp.step(band, 0, 0, -1) == 5  # up from the bottom-left, the nearer top icon


def _names(ref):
    return {1: 'Lash', 2: 'Bloodlust', 3: 'Fury'}.get(ref, f"(missing #{ref})")


def test_a_slot_tip_names_its_buffs_and_counts_repeats():
    cfg = {'slotMode': 'static', 'rows': 1, 'cols': 3,
           'slotAssignments': {'0': [1, 2, 2], '1': 3}}
    assert gp.slot_tip(cfg, _names, 0) == 'Slot 0: Lash, Bloodlust x2 — click to edit, right-click to clear'
    assert gp.slot_tip(cfg, _names, 1).startswith('Slot 1: Fury')
    assert gp.slot_tip(cfg, _names, 2) == 'Slot 2: empty — click to fill'
    assert gp.held_ids(cfg) == [1, 2, 3]


def test_the_names_line_fits_what_it_can_then_counts_the_rest():
    names = ['Lash', 'Bloodlust', 'Fury']
    assert gp.names_line(names, len, 100) == 'Lash, Bloodlust, Fury'
    assert gp.names_line(['Lash', 'Bloodlust', 'Fury of the Ages'], len, 24) == 'Lash, Bloodlust + 1 more'
    assert gp.names_line(names, len, 20) == 'Lash + 2 more'
    assert gp.names_line(names, len, 10) == '… + 2 more'
    assert gp.names_line(['Bloodlust'], len, 5) == 'Bloo…'
    assert gp.names_line([], len, 100) == ''
    # The whole list carries no " + N more", so it can fit where one name plus its tail can't.
    two = ['Bloodlust of the Ancients', 'Lash']
    assert gp.names_line(two, len, len('Bloodlust of the Ancients, Lash')) == 'Bloodlust of the Ancients, Lash'


@pytest.mark.parametrize('cfg', [
    {'slotMode': 'dynamic', 'whitelist': []},
    {'slotMode': 'dynamic', 'whitelist': [5]},
    {'slotMode': 'static', 'rows': 3, 'cols': 3, 'slotAssignments': {}},
    {'slotMode': 'static', 'rows': 3, 'cols': 3, 'slotAssignments': {'2': [5]}},
    {'slotMode': 'static', 'rows': 1, 'cols': 2, 'slotAssignments': {'7': [5]}},  # outside the shape
    {'slotMode': 'static', 'rows': 1, 'cols': 2, 'slotAssignments': {'0': []}},
])
def test_the_nudge_follows_the_builds_own_rule(cfg):
    assert (gp.empty_nudge(cfg) is None) == grid_ships(dict(cfg, enabled=True))


def test_the_nudges_say_what_to_click():
    assert gp.empty_nudge({'slotMode': 'dynamic'}) == (
        'No buffs tracked yet, so it is not built. Click the preview to choose them.')
    assert gp.empty_nudge({'slotMode': 'static', 'rows': 3, 'cols': 3}) == (
        'No slots assigned yet, so it is not built. Click a slot to choose its buffs (9 slots).')
