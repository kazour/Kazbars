"""Smoke tests for kazbars.deeps_settings.

Covers defaults, per-key validation (clamping, type coercion, bool
canonicalisation, layout enum), unknown-key drop, file-missing fallback,
load/save round-trip, and corrupt-file fallback. Uses pytest's `tmp_path`
fixture so the tests never touch the real settings folder.

Run: `pytest tests/test_deeps_settings.py` (from repo root).
"""

from pathlib import Path

import pytest

from kazbars.deeps_settings import (
    DEEPS_DEFAULTS,
    FONT_FAMILY_CHOICES,
    SETTINGS_FILENAME,
    get_default_settings,
    get_settings_path,
    load_settings,
    save_settings,
    validate_all_settings,
    validate_setting,
)

# =========================================================================== #
# Defaults                                                                    #
# =========================================================================== #

def test_defaults_match_locked_decisions() -> None:
    """The three threshold defaults are the user-locked numbers."""
    d = get_default_settings()
    assert d["alarm_threshold"] == 2500.0
    assert d["hpis_green_threshold"] == 50.0
    assert d["dpis_yellow_threshold"] == 300.0


def test_pet_damage_default_on() -> None:
    """Pet damage toggle starts ON by default."""
    assert get_default_settings()["include_pet_damage"] is True


def test_layout_default_horizontal() -> None:
    assert get_default_settings()["layout"] == "horizontal"


def test_readout_defaults() -> None:
    """Readout card ships with a 5s window and gentle smoothing on."""
    d = get_default_settings()
    assert d["window_seconds"] == 5
    assert d["smoothing"] == 50
    assert d["round_step"] == 5
    assert d["refresh_ms"] == 100


def test_overlay_starts_unlocked_unpositioned() -> None:
    d = get_default_settings()
    assert d["overlay_locked"] is False
    assert d["overlay_positioned"] is False


def test_overlay_appearance_defaults() -> None:
    """Font is the design-system default; bg has a partial backdrop on first run."""
    d = get_default_settings()
    assert d["overlay_font_family"] == "Segoe UI"
    assert d["overlay_font_size"] == 22
    assert d["overlay_bg_opacity"] == 0.66


def test_font_family_choices_includes_default() -> None:
    """The default font must appear in the curated dropdown."""
    assert DEEPS_DEFAULTS["overlay_font_family"] in FONT_FAMILY_CHOICES


def test_get_default_settings_returns_fresh_copy() -> None:
    """Mutating the returned dict must not mutate the module-level defaults."""
    d1 = get_default_settings()
    d1["alarm_threshold"] = 9999.0
    d2 = get_default_settings()
    assert d2["alarm_threshold"] == 2500.0
    assert DEEPS_DEFAULTS["alarm_threshold"] == 2500.0


# =========================================================================== #
# Single-key validation                                                       #
# =========================================================================== #

class TestValidateSetting:
    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            # Booleans
            ("include_pet_damage", True, True),
            ("include_pet_damage", False, False),
            ("include_pet_damage", 1, True),
            ("include_pet_damage", 0, False),
            ("include_pet_damage", "yes", True),  # bool() of any non-empty string
            ("overlay_locked", True, True),
            ("overlay_positioned", False, False),
        ],
    )
    def test_bool_keys(self, key: str, value: object, expected: bool) -> None:
        assert validate_setting(key, value) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("horizontal", "horizontal"),
            ("vertical", "vertical"),
            ("diagonal", "horizontal"),  # unknown → default
            ("HORIZONTAL", "horizontal"),  # case-sensitive → default
            ("", "horizontal"),
            (None, "horizontal"),
        ],
    )
    def test_layout_enum(self, value: object, expected: str) -> None:
        assert validate_setting("layout", value) == expected

    def test_float_within_range(self) -> None:
        assert validate_setting("alarm_threshold", 1500.0) == 1500.0
        assert validate_setting("alarm_threshold", 1500) == 1500.0  # int → float

    def test_float_clamped_high(self) -> None:
        assert validate_setting("alarm_threshold", 10_000_000.0) == 999_999.0

    def test_float_clamped_low(self) -> None:
        assert validate_setting("alarm_threshold", -50.0) == 0.0

    def test_int_within_range(self) -> None:
        assert validate_setting("overlay_x", 1920) == 1920
        assert validate_setting("overlay_y", 0) == 0

    def test_int_clamped(self) -> None:
        assert validate_setting("overlay_x", -100) == 0
        assert validate_setting("overlay_x", 99_999) == 7680

    def test_unparsable_falls_back_to_default(self) -> None:
        """Garbage in a numeric field → use the default, don't crash."""
        assert validate_setting("alarm_threshold", "not a number") == 2500.0
        assert validate_setting("overlay_x", "junk") == 0

    def test_unknown_key_passes_through(self) -> None:
        """Unknown keys aren't validated; caller is responsible."""
        # validate_setting doesn't filter unknown keys — validate_all_settings does.
        assert validate_setting("totally_unknown", "whatever") == "whatever"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Segoe UI", "Segoe UI"),
            ("Consolas", "Consolas"),
            ("Cascadia Code", "Cascadia Code"),
            ("Courier New", "Courier New"),
            ("Comic Sans MS", "Segoe UI"),   # off-list → default
            ("segoe ui", "Segoe UI"),         # case-sensitive → default
            ("", "Segoe UI"),
            (None, "Segoe UI"),
        ],
    )
    def test_font_family_enum(self, value: object, expected: str) -> None:
        assert validate_setting("overlay_font_family", value) == expected

    def test_font_size_within_range(self) -> None:
        assert validate_setting("overlay_font_size", 22) == 22
        assert validate_setting("overlay_font_size", 12) == 12
        assert validate_setting("overlay_font_size", 48) == 48

    def test_font_size_clamped(self) -> None:
        assert validate_setting("overlay_font_size", 8) == 12     # below min
        assert validate_setting("overlay_font_size", 100) == 48   # above max

    def test_font_size_unparsable_falls_back(self) -> None:
        assert validate_setting("overlay_font_size", "huge") == 22

    def test_bg_opacity_within_range(self) -> None:
        assert validate_setting("overlay_bg_opacity", 0.0) == 0.0
        assert validate_setting("overlay_bg_opacity", 0.5) == 0.5
        assert validate_setting("overlay_bg_opacity", 1.0) == 1.0

    def test_bg_opacity_clamped(self) -> None:
        assert validate_setting("overlay_bg_opacity", -0.5) == 0.0
        assert validate_setting("overlay_bg_opacity", 2.0) == 1.0

    # ----- Readout tuning keys -------------------------------------------- #

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (5, 5), (7, 7), (11, 11), (13, 13),
            ("7", 7),               # string coerced
            (6, 5),                 # off-list → default
            (0, 5), (99, 5),
            ("junk", 5), (None, 5),  # unparsable → default
        ],
    )
    def test_window_seconds_choice(self, value: object, expected: int) -> None:
        assert validate_setting("window_seconds", value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, 1), (5, 5), (10, 10), (25, 25), (50, 50), (100, 100),
            ("25", 25),
            (3, 5),                 # off-list → default
            ("junk", 5), (None, 5),
        ],
    )
    def test_round_step_choice(self, value: object, expected: int) -> None:
        assert validate_setting("round_step", value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (100, 100), (250, 250), (500, 500), (1000, 1000),
            ("500", 500),
            (200, 100),             # off-list → default
            ("junk", 100), (None, 100),
        ],
    )
    def test_refresh_ms_choice(self, value: object, expected: int) -> None:
        assert validate_setting("refresh_ms", value) == expected

    def test_smoothing_within_range(self) -> None:
        assert validate_setting("smoothing", 0) == 0
        assert validate_setting("smoothing", 50) == 50
        assert validate_setting("smoothing", 100) == 100

    def test_smoothing_clamped(self) -> None:
        assert validate_setting("smoothing", -10) == 0
        assert validate_setting("smoothing", 250) == 100

    def test_smoothing_unparsable_falls_back(self) -> None:
        assert validate_setting("smoothing", "lots") == 50


# =========================================================================== #
# validate_all_settings                                                       #
# =========================================================================== #

class TestValidateAll:
    def test_empty_dict_returns_defaults(self) -> None:
        assert validate_all_settings({}) == get_default_settings()

    def test_known_keys_are_kept(self) -> None:
        result = validate_all_settings({"alarm_threshold": 1234.0})
        assert result["alarm_threshold"] == 1234.0
        # Other keys take their defaults.
        assert result["hpis_green_threshold"] == 50.0

    def test_unknown_keys_are_dropped(self) -> None:
        result = validate_all_settings({"definitely_not_a_real_key": "hello"})
        assert "definitely_not_a_real_key" not in result

    def test_out_of_range_values_get_clamped(self) -> None:
        result = validate_all_settings({
            "alarm_threshold": 50_000_000.0,
            "overlay_x": -999,
        })
        assert result["alarm_threshold"] == 999_999.0
        assert result["overlay_x"] == 0

    def test_invalid_layout_falls_back_to_default(self) -> None:
        result = validate_all_settings({"layout": "diagonal"})
        assert result["layout"] == "horizontal"


# =========================================================================== #
# File I/O                                                                    #
# =========================================================================== #

class TestFileIO:
    def test_settings_path_appends_filename(self, tmp_path: Path) -> None:
        assert get_settings_path(tmp_path) == str(tmp_path / SETTINGS_FILENAME)

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """First-run path: no file yet → caller gets sensible defaults."""
        assert load_settings(tmp_path) == get_default_settings()

    def test_save_creates_folder_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "does" / "not" / "exist"
        assert save_settings(nested, get_default_settings()) is True
        assert (nested / SETTINGS_FILENAME).exists()

    def test_round_trip_preserves_known_keys(self, tmp_path: Path) -> None:
        original = get_default_settings()
        original["alarm_threshold"] = 3500.0
        original["hpis_green_threshold"] = 75.0
        original["dpis_yellow_threshold"] = 400.0
        original["include_pet_damage"] = True
        original["layout"] = "vertical"
        original["overlay_font_family"] = "Consolas"
        original["overlay_font_size"] = 32
        original["overlay_bg_opacity"] = 0.5
        original["overlay_x"] = 1234
        original["overlay_y"] = 567
        original["overlay_locked"] = True
        original["overlay_positioned"] = True

        assert save_settings(tmp_path, original) is True
        loaded = load_settings(tmp_path)
        assert loaded == original

    def test_load_corrupt_file_returns_defaults(self, tmp_path: Path) -> None:
        """A truncated/invalid JSON shouldn't crash startup — fall back."""
        (tmp_path / SETTINGS_FILENAME).write_text("{not valid json", encoding="utf-8")
        assert load_settings(tmp_path) == get_default_settings()

    def test_load_partial_file_fills_missing_with_defaults(
        self, tmp_path: Path
    ) -> None:
        """An older settings file with fewer keys gets filled out cleanly."""
        (tmp_path / SETTINGS_FILENAME).write_text(
            '{"alarm_threshold": 1234.0}', encoding="utf-8"
        )
        loaded = load_settings(tmp_path)
        assert loaded["alarm_threshold"] == 1234.0
        # All other fields default.
        for key, default in DEEPS_DEFAULTS.items():
            if key == "alarm_threshold":
                continue
            assert loaded[key] == default

    def test_save_validates_before_writing(self, tmp_path: Path) -> None:
        """Out-of-range values are clamped on disk, not just on load."""
        bad = get_default_settings()
        bad["alarm_threshold"] = 99_999_999.0  # well over the max
        save_settings(tmp_path, bad)
        loaded = load_settings(tmp_path)
        assert loaded["alarm_threshold"] == 999_999.0
