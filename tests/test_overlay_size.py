"""Tests for `overlay_size` — the size model's arithmetic — and the `overlay`
section that carries the base size and the font.

Hand-computed rows for every base size, the floor and the caps, ties (every
rounding is half up, as AS2's `Math.round`), and a sweep of every size at
every scale for the invariants the in-game text relies on.

Run: `pytest tests/test_overlay_size.py` (from repo root).
"""

from kazbars import overlay
from kazbars.overlay_size import (
    GUTTER,
    INSET,
    MIN_TEXT_PT,
    SCALE_MAX,
    SCALE_MIN,
    SCALE_STEP,
    cast_fs,
    clamp_scale,
    grid_metrics,
    icon_metrics,
    panel_fs,
    scale_from,
    snap_scale,
    text_box_h,
)

SIZES = [s for s, _ in overlay.SIZE_CHOICES]
SCALES = range(SCALE_MIN, SCALE_MAX + 1, SCALE_STEP)


def _round_div(n, d):
    return (2 * n + d) // (2 * d)


# --------------------------------------------------------------------------
# The overlay section
# --------------------------------------------------------------------------


def test_the_size_choices_and_their_labels():
    assert SIZES == [10, 11, 12, 13, 14, 16, 18, 20, 24]
    labels = dict(overlay.SIZE_CHOICES)
    assert labels[10] == "10 · Compact"
    assert labels[12] == "12 · Default (1080p)"
    assert labels[14] == "14 · Large (1080p)"
    assert labels[16] == "16 · 1440p"
    assert labels[20] == "20 · Large (1440p)"
    assert labels[24] == "24 · 4K"
    for plain in (11, 13, 18):
        assert labels[plain] == str(plain)
    assert overlay.DEFAULT_SIZE in SIZES


def test_the_font_list_and_its_labels():
    assert overlay.FONT_CHOICES == (
        "Arial", "Verdana", "GG", "Roboto", "Inter", "Noto Sans", "Source Sans 3",
        "PT Sans", "Fira Sans", "Barlow Semi Condensed", "Exo 2", "Alegreya Sans")
    assert overlay.font_label("Verdana") == "Verdana (game font)"
    assert overlay.font_label("Hyborian") == "Hyborian (game font)"
    assert overlay.font_label("Inter") == "Inter"
    assert overlay.as2_face("Verdana") == "_StandardFont"
    assert overlay.as2_face("Arial") == overlay.as2_face("Exo 2") == "Arial"


def test_every_baked_face_has_a_slug_and_arial_and_verdana_have_none():
    assert overlay.font_slug("Arial") is None
    assert overlay.font_slug("Verdana") is None
    for unknown in ("Ubuntu", "arial", "roboto", "", "Comic Sans"):
        assert overlay.font_slug(unknown) is None, unknown
    slugs = [overlay.font_slug(f) for f in overlay.FONT_CHOICES[2:]]
    assert slugs == ["gg", "roboto", "inter", "noto-sans", "source-sans-3", "pt-sans",
                     "fira-sans", "barlow-semi-condensed", "exo-2", "alegreya-sans"]


def test_the_section_reads_a_size_that_is_a_choice_and_a_font_on_the_list():
    assert overlay.validate_config(None) == {"size": 12, "font": "Arial"}
    assert overlay.validate_config([1, 2]) == {"size": 12, "font": "Arial"}
    assert overlay.validate_config({"size": 24, "font": "Exo 2"}) == {"size": 24, "font": "Exo 2"}
    for size in SIZES:
        assert overlay.validate_config({"size": size})["size"] == size
    for font in overlay.FONT_CHOICES:
        assert overlay.validate_config({"font": font})["font"] == font


def test_anything_else_is_the_default_size_and_font():
    for raw in (15, 0, -12, True, None, [12], "big", float("nan"), float("inf")):
        assert overlay.validate_config({"size": raw})["size"] == 12, raw
    for raw in ("Comic Sans", "arial", "", 7, None, ["Roboto"], "Ubuntu"):
        assert overlay.validate_config({"font": raw})["font"] == "Arial", raw
    assert overlay.validate_config({"size": "16"})["size"] == 16
    assert overlay.validate_config({"size": 20.9})["size"] == 20


def test_the_section_is_written_in_declared_order_and_is_idempotent():
    section = overlay.validate_config({"font": "Inter", "size": 14, "junk": 1})
    assert list(section) == ["size", "font"]
    assert overlay.validate_config(section) == section
    assert overlay.PROFILE_SECTION.key == "overlay"
    assert overlay.PROFILE_SECTION.lane == "build"
    assert overlay.PROFILE_SECTION.defaults() == {"size": 12, "font": "Arial"}


def test_size_for_height_picks_the_tier():
    assert [overlay.size_for_height(h) for h in (720, 1080, 1081, 1440, 1441, 2160)] == [
        12, 12, 16, 16, 24, 24]


# --------------------------------------------------------------------------
# Scale
# --------------------------------------------------------------------------


def test_a_scale_is_an_int_clamped_to_50_200_defaulting_to_100():
    assert scale_from(None) == 100
    assert (scale_from(50), scale_from(200), scale_from(130)) == (50, 200, 130)
    assert [scale_from(v) for v in (49, 0, -5, 201, 9999)] == [50, 50, 50, 200, 200]
    assert (scale_from("75"), scale_from(110.9), scale_from(True)) == (75, 110, 50)
    for junk in ("x", None, [1], float("nan"), float("inf"), {}):
        assert scale_from(junk) == 100, junk
    assert clamp_scale(10) == 50 and clamp_scale(300) == 200


def test_snapping_rounds_to_the_nearest_five_inside_the_range():
    table = [(100, 100), (102, 100), (103, 105), (107, 105), (108, 110), (50, 50), (52, 50),
             (48, 50), (10, 50), (198, 200), (203, 200), (999, 200)]
    for given, want in table:
        assert snap_scale(given) == want, given
    assert all(snap_scale(p) % SCALE_STEP == 0 for p in range(SCALE_MIN, SCALE_MAX + 1))


# --------------------------------------------------------------------------
# Panels and the cast timer
# --------------------------------------------------------------------------


def test_panels_take_the_rounded_scaled_size_with_a_floor_of_eight():
    for b, p, want in [(12, 100, 12), (10, 100, 10), (24, 100, 24), (12, 50, 8), (10, 50, 8),
                       (12, 150, 18), (13, 110, 14), (11, 105, 12), (24, 200, 48)]:
        assert panel_fs(b, p) == want, (b, p)
    assert panel_fs(12, 105) == 13
    assert panel_fs(14, 105) == 15, "14.7"
    assert panel_fs(10, 125) == 13, "12.5 ties up"


def test_the_cast_timer_takes_the_title_role_of_the_scaled_size():
    for b, p, want in [(12, 100, 15), (10, 100, 13), (11, 100, 14), (13, 100, 16), (14, 100, 18),
                       (16, 100, 20), (18, 100, 23), (20, 100, 25), (24, 100, 30), (12, 50, 8),
                       (24, 200, 60), (12, 70, 11)]:
        assert cast_fs(b, p) == want, (b, p)


# --------------------------------------------------------------------------
# Grids
# --------------------------------------------------------------------------


def test_every_choice_at_the_default_scale_is_a_clean_derivative():
    for base in SIZES:
        m = grid_metrics(base, 100)
        assert (m.icon, m.timer, m.stack) == (4 * base, base, base), base
        assert not (m.timer_capped or m.timer_floored or m.stack_floored), base


def test_the_scale_moves_the_icon_by_four_px_per_rounded_point():
    assert grid_metrics(12, 110).icon == 4 * 13
    assert grid_metrics(12, 150).icon == 72
    assert grid_metrics(12, 200).icon == 96
    assert grid_metrics(24, 200).icon == 192
    m = grid_metrics(13, 100)
    assert (m.icon, m.timer, m.stack) == (52, 13, 13)


def test_both_texts_are_floored_at_nine_points():
    m = grid_metrics(12, 50)
    assert (m.icon, m.stack, m.timer) == (24, 9, 9)
    assert m.stack_floored and m.timer_floored and not m.timer_capped
    m = grid_metrics(10, 90)
    assert (m.icon, m.stack, m.timer) == (36, 9, 9)
    assert not (m.stack_floored or m.timer_floored)


def test_the_fit_caps_stay_a_net_the_body_role_timer_never_falls_into():
    m = grid_metrics(12, 70)
    assert (m.icon, m.stack, m.timer) == (32, 9, 9)
    assert m.timer_floored and not m.timer_capped
    assert not any(grid_metrics(b, p).timer_capped for b in SIZES for p in SCALES)
    # A fixed icon asking for big text is capped to fit it.
    m = icon_metrics(40, 12, 30)
    assert m.timer_capped and m.timer < 30


def test_the_box_height_is_one_line_box_plus_the_gutter():
    for pt, h in [(9, 15), (10, 16), (12, 19), (13, 20), (15, 22), (24, 33), (30, 40), (48, 62)]:
        assert text_box_h(pt) == h, pt


def test_the_sweep_of_every_size_and_scale_keeps_every_rule():
    for base in SIZES:
        for scale in SCALES:
            m = grid_metrics(base, scale)
            at = (base, scale, m)
            asked = _round_div(base * scale, 100)
            assert m.icon % 4 == 0 and 20 <= m.icon <= 192, at
            assert m.stack >= MIN_TEXT_PT and m.timer >= MIN_TEXT_PT, at
            assert m.stack == max(asked, MIN_TEXT_PT), at
            assert m.timer <= max(asked, MIN_TEXT_PT), at
            assert m.timer_capped == (m.timer < asked), at
            if m.timer > MIN_TEXT_PT:
                assert m.timer * 2.2264 + GUTTER <= m.icon + 1e-9, at
                assert INSET + text_box_h(m.stack) + text_box_h(m.timer) <= m.icon, at
