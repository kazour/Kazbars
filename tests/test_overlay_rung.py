"""Tests for the document schema 2 → 3 rung: per-module pixel and point sizes
become a percent `scale` of one profile-wide base size (`modules.overlay`).

The base size is seeded from `authored_at`'s height on the tiers the old seed
sizes used, so a profile built today keeps its in-game sizes: the shipped seeds
(48 / 56 / 64 px icons at 1080p / 1440p / 4K) land exactly, a tuned size keeps
to within one 5 % step, positions are untouched. The rung is frozen history
inside `profile_document` and must never mutate the caller's raw dict.

Run: `pytest tests/test_overlay_rung.py` (from repo root).
"""

import copy

import pytest

from kazbars import cast_timer, grid_model, inspect, overlay, stopwatch
from kazbars.overlay_size import cast_fs, grid_metrics, panel_fs
from kazbars.profile_document import DOC_SCHEMA_VERSION, SectionRegistry, validate_document


def _registry():
    reg = SectionRegistry()
    for module in (grid_model, overlay, stopwatch, inspect, cast_timer):
        reg.register(module.PROFILE_SECTION)
    return reg


def _schema2_doc(height=1080, **modules):
    grid = {"id": "G", "iconSize": 48, "timerFontSize": 17, "stackFontSize": 16,
            "showTimers": True, "fx": 0.25, "fy": 0.5, "whitelist": [1]}
    base = {
        "schema": 2,
        "id": "a3f81c2e",
        "name": "Setup",
        "authored_at": [1920 * height // 1080, height],
        "modules": {"grids": {"grids": [grid]}},
    }
    base["modules"].update(modules)
    return base


def _migrated(raw):
    return validate_document(_registry(), raw)["modules"]


@pytest.mark.parametrize("height, size, icon, scale", [
    (1080, 12, 48, 100), (1440, 16, 56, 90), (2160, 24, 64, 65)])
def test_the_shipped_seeds_land_on_the_same_icons(height, size, icon, scale):
    raw = _schema2_doc(height)
    raw["modules"]["grids"]["grids"][0]["iconSize"] = icon
    out = _migrated(raw)
    assert out["overlay"] == {"size": size, "font": "Arial"}
    grid = out["grids"]["grids"][0]
    assert grid["scale"] == scale
    assert grid_metrics(size, scale).icon == icon


def test_a_tuned_icon_keeps_within_one_step():
    for height in (1080, 1440, 2160):
        size = overlay.size_for_height(height)
        for icon in range(24, 129, 4):
            raw = _schema2_doc(height)
            raw["modules"]["grids"]["grids"][0]["iconSize"] = icon
            scale = _migrated(raw)["grids"]["grids"][0]["scale"]
            baked = grid_metrics(size, scale).icon
            if 50 < scale < 200:
                assert abs(baked - icon) <= 4 * max(1, round(size * 0.05)), (height, icon, baked)


def test_the_retired_grid_keys_go_and_the_timer_style_follows_show_timers():
    raw = _schema2_doc()
    off = dict(raw["modules"]["grids"]["grids"][0], id="Off", showTimers=False)
    raw["modules"]["grids"]["grids"].append(off)
    on, off = _migrated(raw)["grids"]["grids"]
    for key in ("iconSize", "timerFontSize", "stackFontSize", "showTimers"):
        assert key not in on and key not in off
    assert (on["timerStyle"], off["timerStyle"]) == ("digits", "off")
    assert (on["fx"], on["fy"], on["whitelist"]) == (0.25, 0.5, [1])


def test_an_absent_or_junk_icon_size_reads_as_the_default_scale():
    raw = _schema2_doc()
    raw["modules"]["grids"]["grids"][0].pop("iconSize")
    raw["modules"]["grids"]["grids"].append({"id": "J", "iconSize": "big"})
    a, j = _migrated(raw)["grids"]["grids"]
    assert (a["scale"], j["scale"]) == (100, 100)


def test_panel_and_cast_sizes_become_scales_that_bake_back():
    raw = _schema2_doc(1440,
                       stopwatch={"enabled": True, "fontSize": 20},
                       inspect={"enabled": True, "fontSize": None, "showPvp": True, "showPerks": False},
                       cast_timer={"enabled": True, "fontSize": 20})
    out = _migrated(raw)
    assert panel_fs(16, out["stopwatch"]["scale"]) == 20
    assert out["inspect"]["scale"] == 100
    assert "showPvp" not in out["inspect"] and "showPerks" not in out["inspect"]
    assert cast_fs(16, out["cast_timer"]["scale"]) == 20
    for key in ("stopwatch", "inspect", "cast_timer"):
        assert "fontSize" not in out[key]


def test_the_1080p_cast_default_keeps_its_size():
    out = _migrated(_schema2_doc(cast_timer={"fontSize": 12}))
    assert cast_fs(12, out["cast_timer"]["scale"]) == 12


def test_an_overlay_section_already_present_is_kept_and_sizes_against_it():
    raw = _schema2_doc(1080, overlay={"size": 24, "font": "Inter"})
    raw["modules"]["grids"]["grids"][0]["iconSize"] = 96
    out = _migrated(raw)
    assert out["overlay"] == {"size": 24, "font": "Inter"}
    assert out["grids"]["grids"][0]["scale"] == 100


def test_the_rung_never_mutates_input_and_stamps_the_schema():
    raw = _schema2_doc(stopwatch={"fontSize": 14})
    snapshot = copy.deepcopy(raw)
    doc = validate_document(_registry(), raw)
    assert raw == snapshot
    assert doc["schema"] == DOC_SCHEMA_VERSION == 3


def test_the_rung_survives_non_dict_modules():
    for bad in (None, [], "hello", 42):
        raw = _schema2_doc()
        raw["modules"] = bad
        assert validate_document(_registry(), raw)["schema"] == DOC_SCHEMA_VERSION


def test_a_schema_1_document_climbs_both_rungs():
    raw = {"schema": 1, "id": "a3f81c2e", "name": "Old", "authored_at": [2560, 1440],
           "modules": {"grids": {"grids": [{"id": "G", "x": 1280, "y": 720, "iconSize": 56}]}}}
    out = _migrated(raw)
    grid = out["grids"]["grids"][0]
    assert (grid["fx"], grid["fy"], grid["scale"]) == (0.5, 0.5, 90)
    assert out["overlay"]["size"] == 16


def test_an_overlay_section_with_a_size_off_the_list_takes_the_one_its_scales_use():
    raw = _schema2_doc(1440, overlay={"size": 15, "font": "Inter"})
    out = _migrated(raw)
    assert out["overlay"] == {"size": 16, "font": "Inter"}
    assert grid_metrics(16, out["grids"]["grids"][0]["scale"]).icon == 48
