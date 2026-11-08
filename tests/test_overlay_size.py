"""Tests for `overlay_size` — the size model's arithmetic — and the `overlay`
section that carries the base size and the font.

Hand-computed rows for every base size, the floor and the caps, ties (every
rounding is half up, as AS2's `Math.round`), and a sweep of every size at
every scale for the invariants the in-game text relies on.

Run: `pytest tests/test_overlay_size.py` (from repo root).
"""

from kazbars import overlay, yaml_io
from kazbars.overlay_size import (
    GUTTER,
    MIN_TEXT_PT,
    SCALE_MAX,
    SCALE_MIN,
    SCALE_STEP,
    cast_fs,
    clamp_scale,
    default_gap,
    default_timer_y,
    grid_metrics,
    icon_metrics,
    inset,
    panel_fs,
    scale_from,
    snap_scale,
    stack_pt,
    text_box_h,
)
from kazbars.paths import KAZBARS_ASSETS
from kazbars.swf_font import DN_FONTS

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
    assert labels[11] == "11 · 720p"
    assert labels[13] == "13 · Default (1080p)"
    assert labels[14] == "14 · 1440p"
    assert labels[16] == "16 · 4K"
    for plain in (12, 18, 20, 24):
        assert labels[plain] == str(plain)
    assert overlay.DEFAULT_SIZE == 13


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


def test_each_slug_ships_its_tags_and_its_licence_and_nothing_else_does():
    fonts = KAZBARS_ASSETS / "fonts"
    slugs = sorted({overlay.font_slug(f) for f in (*overlay.FONT_CHOICES, *DN_FONTS)} - {None})
    assert sorted(p.stem for p in fonts.glob("*.bin")) == slugs
    assert sorted(p.stem for p in (fonts / "LICENSES").glob("*.txt")) == slugs
    for slug in slugs:
        text = (fonts / "LICENSES" / f"{slug}.txt").read_text(encoding="utf-8")
        whole = "github.com/BooroH/GigaUI-Ultimate" if slug.startswith("gg") \
            else "SIL OPEN FONT LICENSE Version 1.1"
        assert whole in text, slug


def test_the_section_reads_a_size_that_is_a_choice_and_a_font_on_the_list():
    assert overlay.validate_config(None) == {"size": 13, "font": "Arial"}
    assert overlay.validate_config([1, 2]) == {"size": 13, "font": "Arial"}
    assert overlay.validate_config({"size": 24, "font": "Exo 2"}) == {"size": 24, "font": "Exo 2"}
    for size in SIZES:
        assert overlay.validate_config({"size": size})["size"] == size
    for font in overlay.FONT_CHOICES:
        assert overlay.validate_config({"font": font})["font"] == font


def test_anything_else_is_the_default_size_and_font():
    for raw in (15, 0, -12, True, None, [12], "big", float("nan"), float("inf")):
        assert overlay.validate_config({"size": raw})["size"] == 13, raw
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
    assert overlay.PROFILE_SECTION.defaults() == {"size": 13, "font": "Arial"}


def test_the_stock_profile_follows_the_size_rules():
    """The template is a 1080p profile at the default scale: its overlay size
    is the 1080p tier and every grid carries a new grid's gap and timer Y."""
    text = (KAZBARS_ASSETS / "Default.yml").read_text(encoding="utf-8")
    modules = yaml_io.loads(text)["modules"]
    size = modules["overlay"]["size"]
    assert size == overlay.size_for_height(1080) == overlay.DEFAULT_SIZE
    for grid in modules["grids"]["grids"]:
        assert grid["scale"] == 100, grid["id"]
        assert (grid["gap"], grid["timerYOffset"]) == (default_gap(size), default_timer_y(size)), grid["id"]


def test_size_for_height_picks_the_tier():
    assert [overlay.size_for_height(h) for h in (600, 720, 721, 1080, 1081, 1440, 1441, 2160)] == [
        11, 11, 13, 13, 14, 14, 16, 16]


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


# The maintainer's table, measured in game: s, stack pt, gap, timer Y offset.
TABLE = [(8, 8, 0, -2), (9, 8, 0, -2), (10, 10, -1, -2), (11, 10, -1, -3), (12, 10, -1, -4),
         (13, 11, -1, -4), (14, 12, -2, -5), (15, 13, -2, -5), (16, 14, -2, -5)]


def test_stack_pt_follows_the_maintainers_table():
    for s, stack, _, _ in TABLE:
        assert stack_pt(s) == stack, s
    assert stack_pt(20) == 18 and stack_pt(48) == 46
    assert stack_pt(5) == stack_pt(7) == 8


def test_new_grid_defaults_follow_the_size():
    for s, _, gap, y in TABLE:
        assert (default_gap(s), default_timer_y(s)) == (gap, y), s
    assert (default_gap(24), default_timer_y(24)) == (-4, -7)
    assert (default_gap(48), default_timer_y(48)) == (-10, -14)
    assert (default_gap(5), default_timer_y(5)) == (0, -2)
    # Never a jump past the table, and never less overlap as the size grows.
    gaps = [default_gap(s) for s in range(5, 49)]
    ys = [default_timer_y(s) for s in range(5, 49)]
    assert gaps == sorted(gaps, reverse=True) and ys == sorted(ys, reverse=True)


def test_the_inset_scales_with_the_icon():
    assert [inset(i) for i in (20, 24, 32, 48, 52, 56, 64, 96, 192)] == [
        2, 2, 3, 4, 4, 5, 5, 8, 16]


def test_every_choice_at_the_default_scale_is_a_clean_derivative():
    for base in SIZES:
        m = grid_metrics(base, 100)
        assert (m.icon, m.timer, m.stack) == (4 * base, base, stack_pt(base)), base


def test_the_scale_moves_the_icon_by_four_px_per_rounded_point():
    assert grid_metrics(12, 110).icon == 4 * 13
    assert grid_metrics(12, 150).icon == 72
    assert grid_metrics(12, 200).icon == 96
    assert grid_metrics(24, 200).icon == 192
    m = grid_metrics(13, 100)
    assert (m.icon, m.timer, m.stack) == (52, 13, 11)
    m = grid_metrics(24, 200)
    assert (m.icon, m.timer, m.stack) == (192, 48, 46)


def test_both_texts_are_floored_at_eight_points():
    assert MIN_TEXT_PT == 8
    m = grid_metrics(12, 50)
    assert (m.icon, m.stack, m.timer) == (24, 8, 8)
    m = grid_metrics(10, 90)
    assert (m.icon, m.stack, m.timer) == (36, 8, 9)
    m = grid_metrics(10, 50)
    assert (m.icon, m.stack, m.timer) == (20, 8, 8)


def test_the_fit_caps_stay_a_net_the_body_role_timer_never_falls_into():
    m = grid_metrics(12, 70)
    assert (m.icon, m.stack, m.timer) == (32, 8, 8)
    # Uncapped, the timer is the scaled size and never under the stack counter.
    for b in SIZES:
        for p in SCALES:
            m = grid_metrics(b, p)
            assert m.timer >= m.stack, (b, p)
    # A fixed icon asking for big text is capped to fit it.
    assert icon_metrics(40, 12, 30).timer < 30


def test_the_box_height_is_one_line_box_plus_the_gutter():
    for pt, h in [(8, 14), (9, 15), (10, 16), (12, 19), (13, 20), (15, 22), (24, 33), (30, 40), (48, 62)]:
        assert text_box_h(pt) == h, pt


def test_the_sweep_of_every_size_and_scale_keeps_every_rule():
    for base in SIZES:
        for scale in SCALES:
            m = grid_metrics(base, scale)
            at = (base, scale, m)
            asked = _round_div(base * scale, 100)
            assert m.icon % 4 == 0 and 20 <= m.icon <= 192, at
            assert m.stack >= MIN_TEXT_PT and m.timer >= MIN_TEXT_PT, at
            assert m.stack == stack_pt(max(asked, MIN_TEXT_PT)), at
            assert m.timer <= max(asked, MIN_TEXT_PT), at
            if m.timer > MIN_TEXT_PT:
                assert m.timer * 2.2264 + GUTTER <= m.icon + 1e-9, at
                assert inset(m.icon) + text_box_h(m.stack) + text_box_h(m.timer) <= m.icon, at
