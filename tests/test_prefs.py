"""Tests for prefs' structured machine-local records: `last_build` (what the
last successful Build & Install baked — drives the grids panel's status row)
and `last_patch` (what a PATCH-lane editor last wrote into a game folder's
XML — drives the editors' sync hint). Both validators must reject malformed
shapes outright rather than let a corrupt prefs.json poison the comparisons.

Run: `pytest tests/test_prefs.py` (from repo root).
"""

from kazbars.prefs import PREFS_SCHEMA, record_last_patch
from kazbars.settings_core import Store, validate_all


def _coerce(key, value):
    return validate_all(PREFS_SCHEMA, {key: value})[key]


def test_last_build_keeps_a_complete_record():
    rec = {"profile_id": "a3f81c2e", "profile_name": "Raid", "hash": "ab" * 32,
           "target_resolution": [2560, 1440]}
    assert _coerce("last_build", rec) == rec


def test_last_build_requires_id_and_hash():
    assert _coerce("last_build", {}) == {}
    assert _coerce("last_build", {"profile_id": "a3f81c2e"}) == {}
    assert _coerce("last_build", {"hash": "ab" * 32}) == {}
    assert _coerce("last_build", "junk") == {}
    assert _coerce("last_build", {"profile_id": "", "hash": ""}) == {}


def test_last_build_drops_malformed_optional_fields_keeps_core():
    rec = {"profile_id": "a3f81c2e", "hash": "ab" * 32,
           "profile_name": 7, "target_resolution": [0, -1]}
    assert _coerce("last_build", rec) == {"profile_id": "a3f81c2e", "hash": "ab" * 32}


def test_last_patch_keeps_per_game_sections_drops_junk():
    val = {
        "C:/AoC": {"damage_colors": {"colors": {"self_healed": "00FF00"}}, "bogus": "x"},
        7: {"damage_colors": {}},
        "D:/AoC": "junk",
    }
    assert _coerce("last_patch", val) == {
        "C:/AoC": {"damage_colors": {"colors": {"self_healed": "00FF00"}}}}


def test_record_last_patch_merges_per_game_and_saves(tmp_path):
    store = Store(PREFS_SCHEMA, tmp_path)
    record_last_patch(store, "C:/AoC", "damage_colors", {"colors": {}})
    record_last_patch(store, "C:/AoC", "buff_bars", {"Player": {"icon_size": 40}})
    record_last_patch(store, "D:/AoC", "damage_colors", {"colors": {"self_healed": "00FF00"}})
    reloaded = Store(PREFS_SCHEMA, tmp_path)
    assert reloaded.get("last_patch") == {
        "C:/AoC": {"damage_colors": {"colors": {}},
                   "buff_bars": {"Player": {"icon_size": 40}}},
        "D:/AoC": {"damage_colors": {"colors": {"self_healed": "00FF00"}}},
    }
