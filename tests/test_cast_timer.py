"""
Tests for `cast_timer` — the pure config layer for the cast-timer overlay.

Covers default keys, clamping, color/enum sanitization, and the `is_enabled`
build gate (False unless a side is on, so the SWF carries no cast-timer code
when the feature is off).
"""

from kazbars.cast_timer import (
    CAST_TIMER_DEFAULTS,
    get_default_config,
    is_enabled,
    validate_config,
)
from kazbars.grid_model import SCREEN_MAX_X, SCREEN_MAX_Y


def test_defaults_disabled():
    cfg = get_default_config()
    assert cfg["enableP"] is False
    assert cfg["enableT"] is False
    assert not is_enabled(cfg)
    # A fresh copy, not the shared module dict.
    cfg["enableP"] = True
    assert CAST_TIMER_DEFAULTS["enableP"] is False


def test_is_enabled_either_side():
    assert is_enabled({"enableP": True, "enableT": False})
    assert is_enabled({"enableP": False, "enableT": True})
    assert not is_enabled({"enableP": False, "enableT": False})
    assert not is_enabled({})


def test_validate_fills_missing_and_drops_unknown():
    out = validate_config({"enableP": True, "bogus": 123})
    assert out["enableP"] is True
    assert "bogus" not in out
    assert set(out) == set(CAST_TIMER_DEFAULTS)


def test_validate_non_dict_returns_defaults():
    assert validate_config(None) == CAST_TIMER_DEFAULTS
    assert validate_config("nope") == CAST_TIMER_DEFAULTS


def test_clamp_positions_and_size():
    out = validate_config(
        {
            "playerX": -50,
            "playerY": 10_000_000,
            "targetX": 999_999_999,
            "targetY": -1,
            "fontSize": 999,
        }
    )
    assert out["playerX"] == 0
    assert out["playerY"] == SCREEN_MAX_Y
    assert out["targetX"] == SCREEN_MAX_X
    assert out["targetY"] == 0
    assert out["fontSize"] == 48


def test_invalid_numeric_falls_back_to_default():
    out = validate_config({"fontSize": "huge", "playerX": "x"})
    assert out["fontSize"] == CAST_TIMER_DEFAULTS["fontSize"]
    assert out["playerX"] == CAST_TIMER_DEFAULTS["playerX"]


def test_bold_and_display_sanitized():
    assert validate_config({"bold": 0})["bold"] is False
    assert validate_config({"bold": 1})["bold"] is True
    assert validate_config({"display": "weird"})["display"] == CAST_TIMER_DEFAULTS["display"]
    assert validate_config({"display": "total"})["display"] == "total"


def test_color_sanitized():
    assert validate_config({"color": "#ff8800"})["color"] == "FF8800"
    assert validate_config({"color": "xyz"})["color"] == "FFFFFF"
    assert validate_config({"color": "12"})["color"] == "FFFFFF"
