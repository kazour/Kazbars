"""Smoke tests for kazbars.deeps_overlay.

Limits: the overlay is a Tk Toplevel that paints to a Canvas. We don't
spin up a display in CI — these tests cover the pure helpers
(`_format_rate`, `_lerp_color`) and confirm the module is importable.
Visual behaviour is covered by manual smoke (`/smoke` skill).

Run: `pytest tests/test_deeps_overlay.py` (from repo root).
"""

import pytest

from kazbars.deeps_overlay import (
    ALL_CELL_IDS,
    CELL_LABELS,
    _format_rate,
    _format_signed_int,
    _lerp_color,
    visible_cells_in_order,
)

# =========================================================================== #
# _format_rate                                                                #
# =========================================================================== #

class TestFormatRate:
    def test_none_is_dashes(self) -> None:
        assert _format_rate(None) == "---"

    def test_zero(self) -> None:
        assert _format_rate(0.0) == "0"

    def test_integer_value(self) -> None:
        assert _format_rate(1247.0) == "1247"

    def test_rounds_to_nearest_integer(self) -> None:
        assert _format_rate(1247.4) == "1247"
        assert _format_rate(1247.6) == "1248"

    def test_no_thousands_separator(self) -> None:
        """Plain integers per the locked decision — no '1,247' formatting."""
        assert _format_rate(123_456.0) == "123456"


# =========================================================================== #
# _format_signed_int                                                          #
# =========================================================================== #

class TestFormatSignedInt:
    def test_none_is_dashes(self) -> None:
        assert _format_signed_int(None) == "---"

    def test_zero_has_no_sign(self) -> None:
        assert _format_signed_int(0.0) == "0"
        # Rounding into zero — still no sign.
        assert _format_signed_int(0.3) == "0"
        assert _format_signed_int(-0.3) == "0"

    def test_positive_has_plus_sign(self) -> None:
        assert _format_signed_int(34.0) == "+34"

    def test_negative_uses_proper_minus_glyph(self) -> None:
        """Per the plan: U+2212 (proper minus), not U+002D (ASCII hyphen)."""
        result = _format_signed_int(-180.0)
        assert result == "−180"
        assert result.startswith("−")  # not "-"

    def test_rounds_to_nearest_integer(self) -> None:
        assert _format_signed_int(34.6) == "+35"
        assert _format_signed_int(-180.4) == "−180"


# =========================================================================== #
# _lerp_color                                                                 #
# =========================================================================== #

class TestLerpColor:
    def test_t_zero_is_first_color(self) -> None:
        assert _lerp_color("#000000", "#ffffff", 0.0) == "#000000"

    def test_t_one_is_second_color(self) -> None:
        assert _lerp_color("#000000", "#ffffff", 1.0) == "#ffffff"

    def test_t_half_is_midpoint(self) -> None:
        assert _lerp_color("#000000", "#ffffff", 0.5) == "#808080"

    def test_t_clamped_below(self) -> None:
        """Negative t shouldn't produce a malformed color."""
        assert _lerp_color("#000000", "#ffffff", -10.0) == "#000000"

    def test_t_clamped_above(self) -> None:
        assert _lerp_color("#000000", "#ffffff", 99.0) == "#ffffff"

    @pytest.mark.parametrize(
        ("c1", "c2", "t"),
        [
            ("#e8e6e0", "#e74c3c", 0.0),
            ("#e8e6e0", "#e74c3c", 0.5),
            ("#e8e6e0", "#e74c3c", 1.0),
        ],
    )
    def test_alarm_pulse_endpoints_are_valid_hex(
        self, c1: str, c2: str, t: float
    ) -> None:
        """Sanity: the alarm pulse lerp produces parseable #RRGGBB strings."""
        result = _lerp_color(c1, c2, t)
        assert result.startswith("#")
        assert len(result) == 7
        # Each pair is a hex byte.
        for i in (1, 3, 5):
            int(result[i : i + 2], 16)


# =========================================================================== #
# Cells — IDs, labels, visibility order                                       #
# =========================================================================== #

class TestCells:
    def test_five_cells_in_fixed_order(self) -> None:
        assert ALL_CELL_IDS == ("dps", "dpis", "hps", "hps-out", "net")

    def test_labels_match_requested_names(self) -> None:
        assert CELL_LABELS == {
            "dps": "DPS out",
            "dpis": "DPS in",
            "hps": "HPS in",
            "hps-out": "HPS out",
            "net": "ΔHP in",
        }

    def test_every_cell_has_a_label(self) -> None:
        assert all(cid in CELL_LABELS for cid in ALL_CELL_IDS)

    def test_visible_order_follows_all_cell_ids(self) -> None:
        # Selection order in the input doesn't matter; render order is fixed.
        assert visible_cells_in_order({"net", "dps", "hps"}) == ["dps", "hps", "net"]

    def test_visible_order_empty(self) -> None:
        assert visible_cells_in_order(set()) == []




