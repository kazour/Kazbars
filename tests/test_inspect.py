"""
Tests for `inspect` — the pure config layer for the target inspect panel.

Covers default keys, clamping, and the sanitized-shape guarantees that feed
the `include_inspect` build gate (off by default, so the SWF carries no
inspect-panel code when the feature is unused).
"""

from kazbars.grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from kazbars.inspect import (
    INSPECT_DEFAULTS,
    get_default_config,
    validate_config,
)


def test_defaults_disabled():
    cfg = get_default_config()
    assert cfg["enabled"] is False
    assert cfg["fontSize"] == 12
    # A fresh copy, not the shared module dict.
    cfg["enabled"] = True
    assert INSPECT_DEFAULTS["enabled"] is False


def test_validate_fills_missing_and_drops_unknown():
    out = validate_config({"enabled": True, "bogus": 123})
    assert out["enabled"] is True
    assert "bogus" not in out
    assert set(out) == set(INSPECT_DEFAULTS)


def test_validate_clamps_position():
    out = validate_config({"x": -50, "y": SCREEN_MAX_Y + 999})
    assert out["x"] == 0
    assert out["y"] == SCREEN_MAX_Y
    out = validate_config({"x": SCREEN_MAX_X + 1, "y": -1})
    assert out["x"] == SCREEN_MAX_X
    assert out["y"] == 0


def test_validate_clamps_font_size():
    assert validate_config({"fontSize": 4})["fontSize"] == 8
    assert validate_config({"fontSize": 99})["fontSize"] == 48


def test_start_collapsed_defaults_off_and_coerces():
    assert get_default_config()["startCollapsed"] is False
    assert validate_config({"startCollapsed": 1})["startCollapsed"] is True
    assert validate_config({"startCollapsed": "garbage"})["startCollapsed"] is True
    assert validate_config({"startCollapsed": 0})["startCollapsed"] is False


def test_validate_bad_values_fall_back():
    out = validate_config({"x": "garbage", "y": None, "enabled": 1, "fontSize": "big"})
    assert out["x"] == INSPECT_DEFAULTS["x"]
    assert out["y"] == INSPECT_DEFAULTS["y"]
    assert out["enabled"] is True
    assert out["fontSize"] == INSPECT_DEFAULTS["fontSize"]


def test_section_toggles_default_on_and_coerce():
    cfg = get_default_config()
    assert cfg["showPvp"] is True
    assert cfg["showPerks"] is True
    assert validate_config({"showPvp": 0})["showPvp"] is False
    assert validate_config({"showPerks": 0})["showPerks"] is False
    assert validate_config({"showPerks": "garbage"})["showPerks"] is True


def test_validate_non_dict_returns_defaults():
    assert validate_config(None) == INSPECT_DEFAULTS
    assert validate_config("nope") == INSPECT_DEFAULTS
