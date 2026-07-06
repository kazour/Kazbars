"""Tests for `grid_model` load-time sanitation — `validate_grid` and
`dedupe_grid_ids`.

Profiles are hand-editable JSON (and arrive via share-string import), so
validate_grid must coerce junk values to defaults instead of raising — a bad
value in `last_profile` would otherwise crash the app at launch — and
duplicate grid names (which key the generated AS2 whitelist tables) must be
renamed, not trusted.

Run: `pytest tests/test_grid_model.py` (from repo root).
"""

from kazbars.grid_model import (
    CLAMP_SPECS,
    create_default_grid,
    dedupe_grid_ids,
    validate_grid,
)


def test_junk_numeric_values_fall_back_to_defaults():
    grid = validate_grid({"rows": None, "cols": "abc", "x": [], "iconSize": {}})
    assert grid["rows"] == CLAMP_SPECS["rows"][0]
    assert grid["cols"] == CLAMP_SPECS["cols"][0]
    assert grid["x"] == CLAMP_SPECS["x"][0]
    assert grid["iconSize"] == CLAMP_SPECS["iconSize"][0]


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
