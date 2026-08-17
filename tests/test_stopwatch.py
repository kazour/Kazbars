"""
Tests for `stopwatch` — the pure config layer for the in-game stopwatch.

Covers default keys, fraction-position clamping, and the sanitized-shape
guarantees that feed the `include_stopwatch` build gate (off by default, so
the SWF carries no stopwatch code when the feature is unused), plus the
PROFILE_SECTION contract app.py registers (BUILD lane, flat config-as-section).
"""

from kazbars.profile_document import LANE_BUILD
from kazbars.stopwatch import (
    PROFILE_SECTION,
    STOPWATCH_DEFAULTS,
    get_default_config,
    validate_config,
)


def test_defaults_disabled():
    cfg = get_default_config()
    assert cfg["enabled"] is False
    assert cfg["startCollapsed"] is False
    # None = follow the shared panel_font_size; a number is a deliberate override.
    assert cfg["fontSize"] is None
    # A fresh copy, not the shared module dict.
    cfg["enabled"] = True
    assert STOPWATCH_DEFAULTS["enabled"] is False


def test_default_position_matches_the_old_px_seed():
    # 850,300 at 1920×1080 — the pre-fraction default, kept as provenance.
    assert STOPWATCH_DEFAULTS["fx"] == 850 / 1920
    assert STOPWATCH_DEFAULTS["fy"] == 300 / 1080


def test_validate_fills_missing_and_drops_unknown():
    out = validate_config({"enabled": True, "bogus": 123})
    assert out["enabled"] is True
    assert "bogus" not in out
    assert set(out) == set(STOPWATCH_DEFAULTS)


def test_validate_clamps_fraction_position():
    out = validate_config({"fx": -0.5, "fy": 1.5})
    assert out["fx"] == 0.0
    assert out["fy"] == 1.0
    # In-range fractions store as full floats, unrounded.
    assert validate_config({"fx": 0.4375})["fx"] == 0.4375


def test_legacy_px_position_keys_are_dropped():
    # Sections are fractions-from-birth; a hand-added px key must not zombie.
    out = validate_config({"x": 850, "y": 300})
    assert "x" not in out and "y" not in out
    assert out["fx"] == STOPWATCH_DEFAULTS["fx"]


def test_validate_clamps_font_size():
    assert validate_config({"fontSize": 4})["fontSize"] == 8
    assert validate_config({"fontSize": 99})["fontSize"] == 48
    assert validate_config({"fontSize": 16})["fontSize"] == 16


def test_font_size_override_can_be_cleared():
    # An emptied or absent override means "follow the shared size", and has to
    # survive a save/load round trip as None rather than snapping back to 12.
    assert validate_config({"fontSize": None})["fontSize"] is None
    assert validate_config({"fontSize": ""})["fontSize"] is None
    assert validate_config({})["fontSize"] is None


def test_validate_bad_values_fall_back():
    out = validate_config({"fx": "garbage", "fy": None, "enabled": 1,
                           "startCollapsed": "", "fontSize": "big"})
    assert out["fx"] == STOPWATCH_DEFAULTS["fx"]
    assert out["fy"] == STOPWATCH_DEFAULTS["fy"]
    assert out["fontSize"] == STOPWATCH_DEFAULTS["fontSize"]
    assert out["enabled"] is True
    assert out["startCollapsed"] is False


def test_nan_fraction_lands_on_the_min_bound():
    # json.loads accepts bare NaN, so a hand-edited profile can carry one.
    # Field's float clamp applies the min bound first, deterministically.
    assert validate_config({"fx": float("nan")})["fx"] == 0.0


def test_validate_non_dict_returns_defaults():
    assert validate_config(None) == STOPWATCH_DEFAULTS
    assert validate_config("nope") == STOPWATCH_DEFAULTS


def test_profile_section_contract():
    # Flat section: the config dict itself. BUILD lane (baked by Build &
    # Install), dense (validate_all fills), no buff refs to harvest.
    assert PROFILE_SECTION.key == "stopwatch"
    assert PROFILE_SECTION.lane == LANE_BUILD
    assert PROFILE_SECTION.sparse is False
    assert PROFILE_SECTION.harvest_refs is None
    assert PROFILE_SECTION.defaults() == STOPWATCH_DEFAULTS
    assert PROFILE_SECTION.validate({"enabled": True})["enabled"] is True
