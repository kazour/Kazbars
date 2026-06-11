"""
Tests for `stopwatch` — the pure config layer for the in-game stopwatch.

Covers default keys, clamping, and the sanitized-shape guarantees that feed
the `include_stopwatch` build gate (off by default, so the SWF carries no
stopwatch code when the feature is unused).
"""

from kazbars.grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from kazbars.stopwatch import (
    STOPWATCH_DEFAULTS,
    get_default_config,
    validate_config,
)


def test_defaults_disabled():
    cfg = get_default_config()
    assert cfg["enabled"] is False
    assert cfg["startCollapsed"] is False
    # A fresh copy, not the shared module dict.
    cfg["enabled"] = True
    assert STOPWATCH_DEFAULTS["enabled"] is False


def test_validate_fills_missing_and_drops_unknown():
    out = validate_config({"enabled": True, "bogus": 123})
    assert out["enabled"] is True
    assert "bogus" not in out
    assert set(out) == set(STOPWATCH_DEFAULTS)


def test_validate_clamps_position():
    out = validate_config({"x": -50, "y": SCREEN_MAX_Y + 999})
    assert out["x"] == 0
    assert out["y"] == SCREEN_MAX_Y
    out = validate_config({"x": SCREEN_MAX_X + 1, "y": -1})
    assert out["x"] == SCREEN_MAX_X
    assert out["y"] == 0


def test_validate_bad_values_fall_back():
    out = validate_config({"x": "garbage", "y": None, "enabled": 1, "startCollapsed": ""})
    assert out["x"] == STOPWATCH_DEFAULTS["x"]
    assert out["y"] == STOPWATCH_DEFAULTS["y"]
    assert out["enabled"] is True
    assert out["startCollapsed"] is False


def test_validate_non_dict_returns_defaults():
    assert validate_config(None) == STOPWATCH_DEFAULTS
    assert validate_config("nope") == STOPWATCH_DEFAULTS
