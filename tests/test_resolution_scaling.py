"""
Tests for `grid_model.scale_grid_position` — the anchor-based resolution scaler.

Locks in the formula (X center-anchored at α=0.5, Y bottom-anchored at α=1.0)
so future refactors don't silently regress it. Predictions for 1440p and 4K are
computed deterministically from fixed 1080p-authored coordinates, independent of
any shipped profile.

Run: `pytest tests/test_resolution_scaling.py` (from repo root).
"""

from kazbars.grid_model import scale_grid_position


def test_scale_identity_when_ref_equals_game():
    """No drift when source and target resolutions are the same."""
    assert scale_grid_position(350, 640, 1920, 1080, 1920, 1080) == (350, 640)
    assert scale_grid_position(0, 0, 1920, 1080, 1920, 1080) == (0, 0)


def test_scale_1080p_to_1440p_matches_predicted():
    """Anchor formula reproduces predicted 1440p positions for fixed 1080p
    coordinates spanning left/center/right and top/bottom, plus the (0,0)
    corner. X shifts +320 (half the 640px width gain), Y shifts +360 (the
    full height gain)."""
    # (x, y) at 1080p -> (x, y) at 1440p
    expected = {
        (350, 640): (670, 1000),
        (960, 1080): (1280, 1440),
        (1570, 200): (1890, 560),
        (0, 0): (320, 360),
    }
    for (x, y), want in expected.items():
        assert scale_grid_position(x, y, 1920, 1080, 2560, 1440) == want


def test_scale_1080p_to_4k_matches_predicted():
    """Same formula extrapolated to 4K: X shifts +960, Y shifts +1080."""
    # (x, y) at 1080p -> (x, y) at 4K
    expected = {
        (350, 640): (1310, 1720),
        (960, 1080): (1920, 2160),
        (1570, 200): (2530, 1280),
        (0, 0): (960, 1080),
    }
    for (x, y), want in expected.items():
        assert scale_grid_position(x, y, 1920, 1080, 3840, 2160) == want


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
