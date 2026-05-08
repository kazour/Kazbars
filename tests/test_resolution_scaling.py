"""
Tests for `grid_model.scale_grid_position` — the anchor-based resolution scaler.

Locks in the formula (X center-anchored at α=0.5, Y bottom-anchored at α=1.0)
so future refactors don't silently regress it. The bundled `Default.json` is
the canonical 1080p reference; predictions for 1440p and 4K are computed from
it deterministically.

Run: `pytest tests/test_resolution_scaling.py` (from repo root).
"""

import json

from kazbars.grid_model import scale_grid_position
from kazbars.paths import KAZBARS_ASSETS


def _default_grids():
    data = json.loads((KAZBARS_ASSETS / "Default.json").read_text(encoding='utf-8'))
    return data['grids'], tuple(data['reference_resolution'])


def test_scale_identity_when_ref_equals_game():
    """No drift when source and target resolutions are the same."""
    assert scale_grid_position(350, 640, 1920, 1080, 1920, 1080) == (350, 640)
    assert scale_grid_position(0, 0, 1920, 1080, 1920, 1080) == (0, 0)


def test_scale_default_to_1440p_matches_predicted():
    """Anchor formula reproduces the predicted 1440p positions for every grid
    in the bundled Default.json. Predicted values are documented in the
    resolution-scaling plan and serve as the load-bearing regression check."""
    grids, ref = _default_grids()
    assert ref == (1920, 1080), "Default.json reference_resolution must be 1920x1080"

    # (id, predicted_x_at_1440p, predicted_y_at_1440p)
    expected = {
        "Raid Debuffs":         (670, 1000),
        "Heals & Protections":  (670, 1080),
        "Grid1":                (594,  695),
        "Fass Mod +":          (1720,  945),
        "Debuffs":             (1720, 1080),
        "Grid2":               (1904,  695),
    }
    for grid in grids:
        gid = grid['id']
        if gid not in expected:
            continue
        got = scale_grid_position(grid['x'], grid['y'], 1920, 1080, 2560, 1440)
        assert got == expected[gid], f"{gid}: expected {expected[gid]}, got {got}"


def test_scale_default_to_4k_matches_predicted():
    """4K extrapolation is deterministic — verify the published values."""
    grids, _ = _default_grids()
    expected = {
        "Raid Debuffs":        (1310, 1720),
        "Heals & Protections": (1310, 1800),
        "Grid1":               (1234, 1415),
        "Fass Mod +":          (2360, 1665),
        "Debuffs":             (2360, 1800),
        "Grid2":               (2544, 1415),
    }
    for grid in grids:
        gid = grid['id']
        if gid not in expected:
            continue
        got = scale_grid_position(grid['x'], grid['y'], 1920, 1080, 3840, 2160)
        assert got == expected[gid], f"{gid}: expected {expected[gid]}, got {got}"


def test_scale_x_is_center_anchored():
    """Two grids equidistant from horizontal center stay equidistant after scale."""
    # Pick offsets ±400 from the 1920p center (960).
    left = scale_grid_position(560, 500, 1920, 1080, 3840, 2160)
    right = scale_grid_position(1360, 500, 1920, 1080, 3840, 2160)
    new_center = 1920
    assert (new_center - left[0]) == (right[0] - new_center)


def test_scale_y_is_bottom_anchored():
    """A grid's offset from the screen bottom stays constant across resolutions."""
    # Grid at y=900 on 1080p → 180px from bottom.
    new_x, new_y = scale_grid_position(500, 900, 1920, 1080, 3840, 2160)
    assert (2160 - new_y) == (1080 - 900)


def test_scale_clamps_to_zero_floor():
    """Down-scaling can push near-edge coords negative — must clamp to 0."""
    # Top-left grid at (0,0) on 4K, scaled down to 1080p.
    # X: 0 + 0.5 * (1920-3840) = -960 → clamps to 0.
    # Y: 0 + 1.0 * (1080-2160) = -1080 → clamps to 0.
    assert scale_grid_position(0, 0, 3840, 2160, 1920, 1080) == (0, 0)
