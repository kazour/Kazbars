"""
Tests for `cast_timer` — the pure config layer for the cast-timer overlay.

Covers default keys, fraction-position clamping, color/enum sanitization, and
the `is_enabled` build gate (master on AND a side on, so the SWF carries no
cast-timer code when the feature is off), plus the PROFILE_SECTION contract
app.py registers (BUILD lane, flat config-as-section).
"""

from kazbars.cast_timer import (
    CAST_TIMER_DEFAULTS,
    PROFILE_SECTION,
    get_default_config,
    is_enabled,
    validate_config,
)
from kazbars.profile_document import LANE_BUILD


def test_defaults_disabled():
    cfg = get_default_config()
    assert cfg["enabled"] is False
    assert cfg["enableP"] is False
    assert cfg["enableT"] is False
    assert not is_enabled(cfg)
    # A fresh copy, not the shared module dict.
    cfg["enableP"] = True
    assert CAST_TIMER_DEFAULTS["enableP"] is False


def test_default_positions_match_the_old_px_seeds():
    # 910,620 / 910,560 at 1920×1080 — the pre-fraction defaults, kept as
    # provenance.
    assert CAST_TIMER_DEFAULTS["playerFx"] == 910 / 1920
    assert CAST_TIMER_DEFAULTS["playerFy"] == 620 / 1080
    assert CAST_TIMER_DEFAULTS["targetFx"] == 910 / 1920
    assert CAST_TIMER_DEFAULTS["targetFy"] == 560 / 1080


def test_is_enabled_needs_master_and_a_side():
    assert is_enabled({"enabled": True, "enableP": True, "enableT": False})
    assert is_enabled({"enabled": True, "enableP": False, "enableT": True})
    assert not is_enabled({"enabled": False, "enableP": True, "enableT": True})
    assert not is_enabled({"enabled": True, "enableP": False, "enableT": False})
    # No master key means off — sections always carry it, this is pure junk.
    assert not is_enabled({"enableP": True, "enableT": True})
    assert not is_enabled({})


def test_validate_missing_master_defaults_off():
    # Fractions-from-birth sections always carry `enabled`; a raw dict without
    # it fills with the default (False) — no side-derived legacy shim.
    assert validate_config({"enableP": True})["enabled"] is False
    assert validate_config({"enabled": False, "enableP": True})["enabled"] is False


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
            "playerFx": -0.5,
            "playerFy": 99.0,
            "targetFx": 1.0001,
            "targetFy": -0.0001,
            "fontSize": 999,
        }
    )
    assert out["playerFx"] == 0.0
    assert out["playerFy"] == 1.0
    assert out["targetFx"] == 1.0
    assert out["targetFy"] == 0.0
    assert out["fontSize"] == 48
    # In-range fractions store as full floats, unrounded.
    assert validate_config({"playerFx": 0.4739583})["playerFx"] == 0.4739583


def test_legacy_px_position_keys_are_dropped():
    # Sections are fractions-from-birth; a hand-added px key must not zombie.
    out = validate_config({"playerX": 910, "playerY": 620})
    assert "playerX" not in out and "playerY" not in out
    assert out["playerFx"] == CAST_TIMER_DEFAULTS["playerFx"]


def test_invalid_numeric_falls_back_to_default():
    out = validate_config({"fontSize": "huge", "playerFx": "x"})
    assert out["fontSize"] == CAST_TIMER_DEFAULTS["fontSize"]
    assert out["playerFx"] == CAST_TIMER_DEFAULTS["playerFx"]


def test_bold_and_display_sanitized():
    assert validate_config({"bold": 0})["bold"] is False
    assert validate_config({"bold": 1})["bold"] is True
    assert validate_config({"display": "weird"})["display"] == CAST_TIMER_DEFAULTS["display"]
    assert validate_config({"display": "total"})["display"] == "total"


def test_color_sanitized():
    assert validate_config({"color": "#ff8800"})["color"] == "FF8800"
    assert validate_config({"color": "xyz"})["color"] == "FFFFFF"
    assert validate_config({"color": "12"})["color"] == "FFFFFF"


def test_profile_section_contract():
    # Flat section: the config dict itself. BUILD lane (baked by Build &
    # Install), dense (validate_all fills), no buff refs to harvest.
    assert PROFILE_SECTION.key == "cast_timer"
    assert PROFILE_SECTION.lane == LANE_BUILD
    assert PROFILE_SECTION.sparse is False
    assert PROFILE_SECTION.harvest_refs is None
    assert PROFILE_SECTION.defaults() == CAST_TIMER_DEFAULTS
    assert PROFILE_SECTION.validate({"enabled": True})["enabled"] is True
