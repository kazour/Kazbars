"""Tests for the timer overlay's font-derived auto-sizing.

The size must come from the font + a fixed column budget — never from the phase
text — so the overlay can't jitter as the seed cycle advances, and must grow
monotonically with the font size.
"""

from kazbars.overlay_engine import FONT_FAMILY_CHOICES
from kazbars.timer_overlay import MIN_WIDTH, measure_timer_overlay


def test_width_clears_minimum():
    for size in (12, 24, 36, 48):
        w, _h = measure_timer_overlay("Segoe UI", size)
        assert w >= MIN_WIDTH


def test_width_and_height_monotonic_in_font_size():
    sizes = [12, 18, 24, 30, 36, 42, 48]
    dims = [measure_timer_overlay("Segoe UI", s) for s in sizes]
    widths = [w for w, _ in dims]
    heights = [h for _, h in dims]
    assert widths == sorted(widths)
    assert heights == sorted(heights)
    # Strictly grows overall (not flat across the whole range).
    assert widths[-1] > widths[0]
    assert heights[-1] > heights[0]


def test_size_is_independent_of_any_phase_text():
    # Deterministic: same font args -> identical size, regardless of call count.
    a = measure_timer_overlay("Segoe UI", 12)
    b = measure_timer_overlay("Segoe UI", 12)
    assert a == b


def test_each_font_family_produces_sane_dims():
    for family in FONT_FAMILY_CHOICES:
        w, h = measure_timer_overlay(family, 12)
        assert w >= MIN_WIDTH
        assert h > 0
