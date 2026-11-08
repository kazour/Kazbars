"""Tests for `overlay_size` — the size model's arithmetic — and the `overlay`
section that carries the base size and the font.

The maintainer's size table row by row, the 32..92 px hold, ties (every
rounding is half up, as AS2's `Math.round`), and a sweep of every size at
every scale.

Run: `pytest tests/test_overlay_size.py` (from repo root).
"""

from kazbars import overlay, yaml_io
from kazbars.overlay_size import (
    SCALE_MAX,
    SCALE_MIN,
    SCALE_STEP,
    cast_fs,
    clamp_scale,
    default_gap,
    default_timer_y,
    grid_metrics,
    inset,
    panel_fs,
    scale_from,
    snap_scale,
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
    assert overlay.SIZE_CHOICES == (
        (8, "720p compact"), (9, "720p"), (10, "1080p compact"), (11, "1080p"),
        (12, "1440p compact"), (13, "1440p"), (14, "1440p large"),
        (15, "2160p compact"), (16, "2160p"), (17, "2160p large"))
    assert [grid_metrics(b, 100).icon for b in SIZES] == list(range(32, 69, 4))
    assert overlay.DEFAULT_SIZE == 11


def test_the_font_list_and_its_labels():
    assert overlay.FONT_CHOICES == (
        "GG", "Arial", "Verdana", "Roboto", "Inter", "Noto Sans", "Source Sans 3",
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
    slugs = [overlay.font_slug(f) for f in overlay.FONT_CHOICES if f not in ("Arial", "Verdana")]
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
    assert overlay.validate_config(None) == {"size": 11, "font": "GG"}
    assert overlay.validate_config([1, 2]) == {"size": 11, "font": "GG"}
    assert overlay.validate_config({"size": 17, "font": "Exo 2"}) == {"size": 17, "font": "Exo 2"}
    for size in SIZES:
        assert overlay.validate_config({"size": size})["size"] == size
    for font in overlay.FONT_CHOICES:
        assert overlay.validate_config({"font": font})["font"] == font


def test_anything_else_is_the_default_size_and_font():
    for raw in (7, 18, 20, 24, 0, -12, True, None, [12], "big", float("nan"), float("inf")):
        assert overlay.validate_config({"size": raw})["size"] == 11, raw
    for raw in ("Comic Sans", "arial", "", 7, None, ["Roboto"], "Ubuntu"):
        assert overlay.validate_config({"font": raw})["font"] == "GG", raw
    assert overlay.validate_config({"size": "16"})["size"] == 16
    assert overlay.validate_config({"size": 15.9})["size"] == 15


def test_the_section_is_written_in_declared_order_and_is_idempotent():
    section = overlay.validate_config({"font": "Inter", "size": 14, "junk": 1})
    assert list(section) == ["size", "font"]
    assert overlay.validate_config(section) == section
    assert overlay.PROFILE_SECTION.key == "overlay"
    assert overlay.PROFILE_SECTION.lane == "build"
    assert overlay.PROFILE_SECTION.defaults() == {"size": 11, "font": "GG"}


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
        9, 9, 11, 11, 13, 13, 16, 16]


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
# The size table
# --------------------------------------------------------------------------


# The maintainer's table, set in game: icon px, timer pt, stack pt.
TABLE = [(32, 10, 10), (36, 10, 10), (40, 12, 10), (44, 12, 12), (48, 14, 12), (52, 14, 12),
         (56, 16, 14), (60, 16, 14), (64, 18, 16), (68, 18, 16), (72, 20, 18), (76, 20, 18),
         (80, 22, 20), (84, 22, 20), (88, 24, 22), (92, 24, 22)]
# A new grid's gap and timer Y offset per s = 8..23.
NEW_GRID = [(0, -2), (0, -2), (-1, -2), (-1, -3), (-1, -4), (-1, -4), (-2, -5), (-2, -5),
            (-2, -5), (-2, -5), (-3, -5), (-3, -6), (-3, -6), (-3, -6), (-4, -7), (-4, -7)]


def test_every_row_of_the_table_is_what_a_grid_bakes():
    for icon, timer, stack in TABLE:
        s = icon // 4
        m = grid_metrics(s, 100)
        assert (m.icon, m.timer, m.stack) == (icon, timer, stack), icon
    m = grid_metrics(12, 150)
    assert (m.icon, m.timer, m.stack) == (72, 20, 18)


def test_a_grid_icon_is_held_to_32_92_px():
    assert grid_metrics(8, 50).icon == 32
    assert grid_metrics(17, 200).icon == 92
    assert grid_metrics(17, 200).timer == 24
    assert grid_metrics(8, 50).timer == 10
    for base in SIZES:
        for scale in SCALES:
            m = grid_metrics(base, scale)
            asked = _round_div(base * scale, 100)
            assert m.icon == 4 * max(8, min(asked, 23)), (base, scale)
            assert (m.icon, m.timer, m.stack) in TABLE, (base, scale)


def test_new_grid_defaults_follow_the_size():
    for s, (gap, y) in enumerate(NEW_GRID, start=8):
        assert (default_gap(s), default_timer_y(s)) == (gap, y), s
    assert (default_gap(5), default_timer_y(5)) == NEW_GRID[0]
    assert (default_gap(48), default_timer_y(48)) == NEW_GRID[-1]


def test_the_inset_scales_with_the_icon():
    assert [inset(i) for i in (20, 24, 32, 48, 52, 56, 64, 92, 96)] == [
        2, 2, 3, 4, 4, 5, 5, 8, 8]


# --------------------------------------------------------------------------
# Panels and the cast timer
# --------------------------------------------------------------------------


def test_panels_take_the_timer_column_times_the_scale_with_a_floor_of_eight():
    for b, timer, _ in [(icon // 4, t, st) for icon, t, st in TABLE[:10]]:
        assert panel_fs(b, 100) == timer, b
    for b, p, want in [(11, 85, 10), (11, 150, 18), (17, 200, 36), (8, 50, 8), (9, 75, 8),
                       (13, 105, 15), (16, 110, 20)]:
        assert panel_fs(b, p) == want, (b, p)
    assert panel_fs(9, 125) == 13, "12.5 ties up"


def test_the_cast_timer_takes_the_title_role_of_the_panel_size():
    for b, p, want in [(8, 100, 13), (9, 100, 13), (11, 100, 15), (13, 100, 18), (16, 100, 23),
                       (17, 200, 45), (8, 50, 8), (11, 70, 11)]:
        assert cast_fs(b, p) == want, (b, p)
