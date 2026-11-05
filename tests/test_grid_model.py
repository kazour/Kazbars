"""Tests for `grid_model` load-time sanitation — `validate_grid` and
`dedupe_grid_ids` — plus the fraction↔pixel projection primitives
(`unproject_px`/`project_px`).

Profiles are hand-editable JSON (and arrive via share-string import), so
validate_grid must coerce junk values to defaults instead of raising — a bad
value in `last_profile` would otherwise crash the app at launch — and
duplicate grid names (which key the generated AS2 whitelist tables) must be
renamed, not trusted.

Projection is the fraction coordinate model's boundary: fractions store full
floats and rounding happens only in `project_px`, so px → fraction → px must
round-trip exactly at the same resolution.

Run: `pytest tests/test_grid_model.py` (from repo root).
"""

from kazbars.grid_model import (
    BAND_ROW_CAP_DEFAULT,
    BAND_ROW_CAPS,
    BAND_SLOTS_DEFAULT,
    CLAMP_SPECS,
    FRACTION_SPECS,
    MAX_GRID_SLOTS,
    PLATE_DISTANCE_DEFAULT,
    PLATE_OFFSET_DEFAULT,
    TIMER_STYLES,
    create_default_grid,
    dedupe_grid_ids,
    is_band,
    max_shape,
    max_slots,
    project_px,
    slot_count,
    snap_row_cap,
    unproject_px,
    validate_grid,
)


def test_junk_numeric_values_fall_back_to_defaults():
    grid = validate_grid({"rows": None, "cols": "abc", "fx": [], "scale": {}})
    assert grid["rows"] == CLAMP_SPECS["rows"][0]
    assert grid["cols"] == CLAMP_SPECS["cols"][0]
    assert grid["fx"] == FRACTION_SPECS["fx"]
    assert grid["scale"] == CLAMP_SPECS["scale"][0]


def test_fractions_clamp_and_reject_nan_and_pop_legacy_px():
    grid = validate_grid({"fx": 1.5, "fy": float("nan"), "x": 640, "y": 480})
    assert grid["fx"] == 1.0
    assert grid["fy"] == FRACTION_SPECS["fy"]
    assert "x" not in grid and "y" not in grid  # legacy px keys never zombie


def test_numeric_strings_still_coerce():
    grid = validate_grid({"rows": "3", "cols": 4})
    assert grid["rows"] == 3
    assert grid["cols"] == 4


def test_infinity_falls_back_to_default():
    # json.loads parses 1e999 to inf, and int(inf) raises OverflowError —
    # that's junk like any other, not a crash.
    grid = validate_grid({"rows": float("inf"), "cols": float("-inf")})
    assert grid["rows"] == CLAMP_SPECS["rows"][0]
    assert grid["cols"] == CLAMP_SPECS["cols"][0]


def test_out_of_range_values_clamp():
    grid = validate_grid({"rows": 999, "gap": -99})
    assert grid["rows"] == CLAMP_SPECS["rows"][2]  # max
    assert grid["gap"] == CLAMP_SPECS["gap"][1]    # min


def test_valid_default_grid_passes_through_unchanged():
    grid = create_default_grid()
    assert validate_grid(dict(grid)) == grid


def test_dedupe_grid_ids_renames_duplicates_first_wins():
    grids = [{"id": "X"}, {"id": "X"}, {"id": "Y"}, {"id": "X"}]
    renamed = dedupe_grid_ids(grids)
    assert [g["id"] for g in grids] == ["X", "X_2", "Y", "X_3"]
    assert renamed == [("X", "X_2"), ("X", "X_3")]


def test_dedupe_grid_ids_skips_taken_suffixes():
    grids = [{"id": "X_2"}, {"id": "X"}, {"id": "X"}]
    dedupe_grid_ids(grids)
    assert [g["id"] for g in grids] == ["X_2", "X", "X_3"]


def test_dedupe_grid_ids_rename_dodges_later_names():
    # The rename for the second 'X' must not take 'X_2' — a later grid owns it,
    # which would force a cascading second rename.
    grids = [{"id": "X"}, {"id": "X"}, {"id": "X_2"}]
    renamed = dedupe_grid_ids(grids)
    assert [g["id"] for g in grids] == ["X", "X_3", "X_2"]
    assert renamed == [("X", "X_3")]


def test_dedupe_grid_ids_no_duplicates_is_a_no_op():
    grids = [{"id": "A"}, {"id": "B"}]
    assert dedupe_grid_ids(grids) == []
    assert [g["id"] for g in grids] == ["A", "B"]


# --------------------------------------------------------------------------- #
# Fraction ↔ pixel projection
# --------------------------------------------------------------------------- #

RESOLUTIONS = [(1920, 1080), (2560, 1440), (3840, 2160)]


def test_projection_round_trips_every_pixel_at_common_resolutions():
    for w, h in RESOLUTIONS:
        for extent in (w, h):
            for px in range(extent + 1):
                assert project_px(unproject_px(px, extent), extent) == px


def test_unproject_clamps_to_unit_range():
    assert unproject_px(-50, 1920) == 0.0
    assert unproject_px(5000, 1920) == 1.0
    assert unproject_px(0, 1920) == 0.0
    assert unproject_px(1920, 1920) == 1.0


def test_unproject_non_positive_extent_is_zero():
    assert unproject_px(100, 0) == 0.0
    assert unproject_px(100, -1) == 0.0


def test_project_clamps_fraction_overshoot():
    assert project_px(-0.25, 1920) == 0
    assert project_px(1.25, 1920) == 1920


def test_projection_is_proportional_across_resolutions():
    # A 1440p-authored point lands at the same screen spot proportionally
    # on other resolutions — the whole point of storing fractions.
    f = unproject_px(1280, 2560)
    assert f == 0.5
    assert project_px(f, 1920) == 960
    assert project_px(f, 3840) == 1920
    assert project_px(unproject_px(1224, 1440), 1080) == 918


# --------------------------------------------------------------------------- #
# Size, timer style, Applied by me, slot cap
# --------------------------------------------------------------------------- #

def test_scale_clamps_and_the_retired_pixel_sizes_never_zombie():
    grid = validate_grid({"scale": 999, "iconSize": 64, "timerFontSize": 20,
                          "stackFontSize": 18, "showTimers": True})
    assert grid["scale"] == CLAMP_SPECS["scale"][2]
    assert validate_grid({"scale": 10})["scale"] == CLAMP_SPECS["scale"][1]
    assert validate_grid({"scale": "junk"})["scale"] == 100
    for key in ("iconSize", "timerFontSize", "stackFontSize", "showTimers"):
        assert key not in grid, key


def test_timer_style_reads_bar_digits_or_off():
    # The retired `showTimers` is the schema 2 -> 3 rung's to convert (test_overlay_rung).
    def style(raw):
        return validate_grid(raw)["timerStyle"]
    assert style({"timerStyle": "bar"}) == "bar"
    assert style({"timerStyle": "off"}) == "off"
    assert style({}) == "digits"
    assert style({"timerStyle": "BAR"}) == "digits"
    assert TIMER_STYLES == ("bar", "digits", "off")


def test_applied_by_me_is_kept_only_when_true():
    assert "selfCastOnly" not in validate_grid({})
    assert validate_grid({"selfCastOnly": True})["selfCastOnly"] is True
    assert "selfCastOnly" not in validate_grid({"selfCastOnly": False})
    assert "selfCastOnly" not in validate_grid({"selfCastOnly": 1})


def test_the_slot_cap_is_per_grid():
    assert MAX_GRID_SLOTS == 64


# --------------------------------------------------------------------------- #
# Overhead grids and bands
# --------------------------------------------------------------------------- #

def test_a_band_reads_its_cap_and_slots_and_derives_its_shape():
    g = validate_grid({"type": "hostile", "rowCap": 5, "maxSlots": 12})
    assert is_band(g)
    assert (g["rowCap"], g["maxSlots"], g["rows"], g["cols"], g["fillDirection"]) == (5, 12, 3, 5, "C")
    assert slot_count(g) == 12
    g = validate_grid({"type": "friendly", "rowCap": 4, "maxSlots": 99})
    assert (g["rowCap"], g["maxSlots"]) == (5, 16)
    assert validate_grid({"type": "friendly", "rowCap": 6})["rowCap"] == 7
    assert validate_grid({"type": "friendly", "rowCap": 1})["rowCap"] == 3
    assert validate_grid({"type": "friendly", "rowCap": 70})["rowCap"] == 7
    g = validate_grid({"type": "friendly", "rowCap": 7, "maxSlots": 3})
    assert (g["rows"], g["cols"]) == (1, 7)


def test_a_band_saved_as_a_box_reads_its_cap_off_its_columns_and_its_slots_off_its_shape():
    g = validate_grid({"type": "hostile", "rows": 2, "cols": 8})
    assert (g["rowCap"], g["maxSlots"], g["rows"], g["cols"]) == (7, 16, 3, 7)
    g = validate_grid({"type": "friendly", "rows": 1, "cols": 4})
    assert (g["rowCap"], g["maxSlots"], g["rows"], g["cols"]) == (5, 4, 1, 5)
    g = validate_grid({"type": "friendly"})
    assert (g["rowCap"], g["maxSlots"]) == (7, 8), "the default 1x10 clamps to 1x8 first"


def test_a_box_has_no_cap_and_keeps_its_shape():
    g = validate_grid({"type": "hostile", "slotMode": "static", "rows": 2, "cols": 8,
                       "rowCap": 5, "maxSlots": 3})
    assert not is_band(g)
    assert "rowCap" not in g and "maxSlots" not in g
    assert (g["rows"], g["cols"], slot_count(g)) == (2, 8, 16)
    g = validate_grid({"type": "player", "rows": 2, "cols": 8, "rowCap": 5})
    assert "rowCap" not in g and g["fillDirection"] == "LR"


def test_an_overhead_box_is_capped_at_sixteen_slots():
    assert (lambda g: (g["rows"], g["cols"]))(validate_grid(
        {"type": "friendly", "slotMode": "static", "rows": 10, "cols": 10})) == (4, 4)
    assert (lambda g: (g["rows"], g["cols"]))(validate_grid(
        {"type": "hostile", "slotMode": "static", "rows": 3, "cols": 8})) == (3, 5)
    assert (lambda g: (g["rows"], g["cols"]))(validate_grid(
        {"type": "hostile", "slotMode": "static"})) == (1, 8)
    assert validate_grid({"type": "target", "rows": 10})["rows"] == 10
    assert (max_slots("hostile"), max_slots("player")) == (16, 64)
    assert max_shape("friendly") == (4, 8) and max_shape("target") == (64, 64)


def test_only_an_overhead_grid_carries_height_and_range():
    g = validate_grid({"type": "hostile"})
    assert (g["plateOffset"], g["maxDistance"]) == (PLATE_OFFSET_DEFAULT, PLATE_DISTANCE_DEFAULT)
    g = validate_grid({"type": "hostile", "plateOffset": 9999, "maxDistance": 1})
    assert (g["plateOffset"], g["maxDistance"]) == (400, 5)
    g = validate_grid({"type": "target", "plateOffset": 90, "maxDistance": 30})
    assert "plateOffset" not in g and "maxDistance" not in g


def test_only_a_friendly_grid_carries_over_me():
    assert validate_grid({"type": "friendly"})["showSelf"] is True
    assert validate_grid({"type": "friendly", "showSelf": False})["showSelf"] is False
    assert validate_grid({"type": "friendly", "showSelf": 0})["showSelf"] is True
    assert "showSelf" not in validate_grid({"type": "hostile", "showSelf": False})
    assert "showSelf" not in validate_grid({"type": "player", "showSelf": False})


def test_a_new_overhead_grid_is_a_band_or_a_box_with_bar_timers():
    band = create_default_grid("friendly", 2, 5, "dynamic", "F")
    assert (band["rowCap"], band["maxSlots"], band["rows"], band["cols"]) == (5, 10, 2, 5)
    assert band["timerStyle"] == "bar" and band["showSelf"] is True
    assert validate_grid(dict(band)) == band
    single = create_default_grid("hostile", 1, 1, "dynamic", "H")
    assert (single["slotMode"], single["rowCap"], single["maxSlots"]) == ("dynamic", 3, 1)
    assert single["layout"] == "debuffFirst" and "showSelf" not in single
    box = create_default_grid("hostile", 3, 3, "static", "B")
    assert "rowCap" not in box and (box["rows"], box["cols"]) == (3, 3)
    assert validate_grid(dict(box)) == box
    assert create_default_grid("player", 1, 1)["slotMode"] == "static"
    assert snap_row_cap(4) == 5 and snap_row_cap(2) == 3 and snap_row_cap(6) == 7
    assert (BAND_ROW_CAPS, BAND_ROW_CAP_DEFAULT, BAND_SLOTS_DEFAULT) == ((3, 5, 7), 5, 10)
