"""Smoke tests for kazbars.deeps_overlay.

Limits: the overlay is a Tk Toplevel that paints to a Canvas. We don't
spin up a display in CI — these tests cover the pure helpers
(`_format_rate`, `_lerp_color`) and confirm the module is importable.
Visual behaviour is covered by manual smoke (`/smoke` skill).

Run: `pytest tests/test_deeps_overlay.py` (from repo root).
"""

from dataclasses import replace

import pytest

from kazbars.deeps_meter import MeterSnapshot
from kazbars.deeps_overlay import (
    ALL_CELL_IDS,
    CELL_LABELS,
    _DisplaySmoother,
    _dpis_ramp_color,
    _dps_color,
    _format_rate,
    _format_signed_int,
    _lerp_color,
    _net_color,
    _Palette,
    _RenderContext,
    _tint_colors,
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


# =========================================================================== #
# _DisplaySmoother — EMA + coarse rounding + redraw cadence                   #
# =========================================================================== #

class TestDisplaySmoother:
    @staticmethod
    def _vals(dps=None, dpis=None, hps=None, hps_out=None) -> dict[str, float | None]:
        return {"dps": dps, "dpis": dpis, "hps": hps, "hps-out": hps_out}

    def test_smoothing_off_snaps_each_sample(self) -> None:
        s = _DisplaySmoother(smoothing=0, round_step=1, refresh_ms=100)
        assert s.update(self._vals(dps=1000), 0.0)["dps"] == 1000
        # No easing — jumps straight to the new value.
        assert s.update(self._vals(dps=2000), 0.5)["dps"] == 2000

    def test_first_real_sample_snaps_even_when_smoothing_on(self) -> None:
        """A fresh channel snaps to its first value rather than easing up from 0."""
        s = _DisplaySmoother(smoothing=100, round_step=1, refresh_ms=100)
        assert s.update(self._vals(dps=1500), 0.0)["dps"] == 1500

    def test_ema_eases_between_samples(self) -> None:
        s = _DisplaySmoother(smoothing=100, round_step=1, refresh_ms=100)
        s.update(self._vals(dps=1000), 0.0)               # snap to 1000
        out = s.update(self._vals(dps=2000), 1.0)["dps"]  # ~one tau later
        assert 1000 < out < 2000

    def test_ema_converges_over_time(self) -> None:
        s = _DisplaySmoother(smoothing=100, round_step=1, refresh_ms=100)
        s.update(self._vals(dps=0), 0.0)
        t = 0.0
        out = 0.0
        for _ in range(50):
            t += 0.5
            out = s.update(self._vals(dps=1000), t)["dps"]
        assert abs(out - 1000) < 5

    def test_none_resets_channel_to_dashes(self) -> None:
        s = _DisplaySmoother(smoothing=50, round_step=1, refresh_ms=100)
        assert s.update(self._vals(dps=1000), 0.0)["dps"] == 1000
        assert s.update(self._vals(dps=None), 1.0)["dps"] is None

    def test_round_step_quantizes_committed_value(self) -> None:
        s = _DisplaySmoother(smoothing=0, round_step=25, refresh_ms=100)
        assert s.update(self._vals(dps=1037), 0.0)["dps"] == 1025

    def test_refresh_cadence_holds_drawn_value(self) -> None:
        s = _DisplaySmoother(smoothing=0, round_step=1, refresh_ms=1000)
        assert s.update(self._vals(dps=1000), 0.0)["dps"] == 1000     # first commit
        # Before the 1s cadence elapses the drawn value holds despite new input.
        assert s.update(self._vals(dps=2000), 0.5)["dps"] == 1000
        # Once it elapses, it commits the latest eased value.
        assert s.update(self._vals(dps=2000), 1.0)["dps"] == 2000


# =========================================================================== #
# Tint helpers — _dpis_ramp_color, _tint_colors, _net_color, _dps_color       #
# =========================================================================== #

def _make_ctx(
    *,
    snapshot: MeterSnapshot | None = None,
    tint_start: float = 200.0,
    tint_full: float = 300.0,
    flash: float = 500.0,
    flash_active: bool = False,
    hpis_green: float = 50.0,
    now: float = 0.0,
    alarm_active: bool = False,
) -> _RenderContext:
    """Build a _RenderContext for the tint helpers. Fields the helpers don't
    read (font, label_font, display, scale, alarm_threshold) get inert
    placeholders so we don't need a PIL font or a real display dict."""
    return _RenderContext(
        snapshot=snapshot if snapshot is not None else MeterSnapshot.empty(),
        display={},
        now=now,
        font=None,           # type: ignore[arg-type]  # unread by tint helpers
        label_font=None,     # type: ignore[arg-type]  # unread by tint helpers
        alarm_active=alarm_active,
        alarm_threshold=2500.0,
        hpis_green=hpis_green,
        dpis_tint_start=tint_start,
        dpis_tint_full=tint_full,
        dpis_flash=flash,
        dpis_flash_active=flash_active,
        scale=1.0,
    )


def _lerp_expected(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """Mirror of _lerp_rgb so tests assert exact tuples without importing it."""
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )


class TestDpisRampColor:
    def test_hps_none_returns_default(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=None, dpis=100.0)
        assert _dpis_ramp_color(_make_ctx(snapshot=snap)) == _Palette.DEFAULT

    def test_dpis_none_returns_default(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=None)
        assert _dpis_ramp_color(_make_ctx(snapshot=snap)) == _Palette.DEFAULT

    def test_deficit_below_tint_start_returns_default(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=100.0)
        ctx = _make_ctx(snapshot=snap, tint_start=200.0, tint_full=300.0)
        assert _dpis_ramp_color(ctx) == _Palette.DEFAULT

    def test_deficit_exactly_at_tint_start_returns_default(self) -> None:
        # `< tint_start` is strict — equality falls into the lerp branch with
        # t=0, which also yields DEFAULT. Either way the boundary reads as
        # untinted.
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=200.0)
        ctx = _make_ctx(snapshot=snap, tint_start=200.0, tint_full=300.0)
        assert _dpis_ramp_color(ctx) == _Palette.DEFAULT

    def test_deficit_inside_lerp_range_is_between_default_and_yellow(self) -> None:
        # Mid-range of the fade (t≈0.5) — clearly neither endpoint, and each
        # channel sits between DEFAULT and YELLOW_TINT.
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=250.0)
        ctx = _make_ctx(snapshot=snap, tint_start=200.0, tint_full=300.0)
        result = _dpis_ramp_color(ctx)
        assert result != _Palette.DEFAULT
        assert result != _Palette.YELLOW_TINT
        for ch, (lo, hi) in enumerate(zip(_Palette.DEFAULT, _Palette.YELLOW_TINT)):
            low, high = (lo, hi) if lo <= hi else (hi, lo)
            assert low <= result[ch] <= high

    def test_deficit_above_tint_full_no_flash_is_yellow(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=400.0)
        ctx = _make_ctx(
            snapshot=snap, tint_start=200.0, tint_full=300.0,
            flash=500.0, flash_active=False,
        )
        assert _dpis_ramp_color(ctx) == _Palette.YELLOW_TINT

    def test_deficit_above_flash_no_flash_active_is_yellow(self) -> None:
        # Steady-flash zone but the hysteresis gate is off → no pulse.
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=600.0)
        ctx = _make_ctx(
            snapshot=snap, tint_start=200.0, tint_full=300.0,
            flash=500.0, flash_active=False,
        )
        assert _dpis_ramp_color(ctx) == _Palette.YELLOW_TINT

    def test_deficit_above_flash_active_pulses(self) -> None:
        # now=0.0 → sin(0)=0 → phase=0.5 → midpoint between YELLOW and
        # DPIS_FLASH_PEAK.
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=600.0)
        ctx = _make_ctx(
            snapshot=snap, tint_start=200.0, tint_full=300.0,
            flash=500.0, flash_active=True, now=0.0,
        )
        expected = _lerp_expected(_Palette.YELLOW_TINT, _Palette.DPIS_FLASH_PEAK, 0.5)
        assert _dpis_ramp_color(ctx) == expected


class TestTintColors:
    def test_hps_none_returns_pair_of_defaults(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=None, dpis=100.0)
        assert _tint_colors(_make_ctx(snapshot=snap)) == (_Palette.DEFAULT, _Palette.DEFAULT)

    def test_net_above_green_threshold_returns_green_and_dpis_default(self) -> None:
        # hps=200, dpis=0 → net=+200 > 50; deficit=-200 < tint_start so dpis
        # side returns DEFAULT.
        snap = replace(MeterSnapshot.empty(), hps=200.0, dpis=0.0)
        ctx = _make_ctx(snapshot=snap, hpis_green=50.0, tint_start=200.0)
        assert _tint_colors(ctx) == (_Palette.GREEN_TINT, _Palette.DEFAULT)

    def test_net_below_green_defers_dpis_to_ramp(self) -> None:
        # hps=0, dpis=400 → net=-400 ≤ 50; deficit=400 > tint_full=300 with no
        # flash active → YELLOW_TINT.
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=400.0)
        ctx = _make_ctx(
            snapshot=snap, hpis_green=50.0,
            tint_start=200.0, tint_full=300.0,
            flash=500.0, flash_active=False,
        )
        assert _tint_colors(ctx) == (_Palette.DEFAULT, _Palette.YELLOW_TINT)


class TestNetColor:
    def test_hps_none_returns_default(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=None, dpis=100.0)
        assert _net_color(_make_ctx(snapshot=snap)) == _Palette.DEFAULT

    def test_net_above_green_threshold_is_green(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=200.0, dpis=0.0)
        ctx = _make_ctx(snapshot=snap, hpis_green=50.0)
        assert _net_color(ctx) == _Palette.GREEN_TINT

    def test_net_below_green_falls_through_to_dpis_ramp(self) -> None:
        snap = replace(MeterSnapshot.empty(), hps=0.0, dpis=400.0)
        ctx = _make_ctx(
            snapshot=snap, hpis_green=50.0,
            tint_start=200.0, tint_full=300.0,
            flash=500.0, flash_active=False,
        )
        assert _net_color(ctx) == _dpis_ramp_color(ctx)


class TestDpsColor:
    def test_alarm_inactive_is_default(self) -> None:
        # Snapshot contents must not matter when the alarm is off.
        snap = replace(MeterSnapshot.empty(), dps=99_999.0)
        ctx = _make_ctx(snapshot=snap, alarm_active=False)
        assert _dps_color(ctx) == _Palette.DEFAULT

    def test_alarm_active_at_phase_midpoint(self) -> None:
        # now=0.0 → sin(0)=0 → phase=0.5 → midpoint DEFAULT ↔ ALARM_PEAK.
        ctx = _make_ctx(alarm_active=True, now=0.0)
        expected = _lerp_expected(_Palette.DEFAULT, _Palette.ALARM_PEAK, 0.5)
        assert _dps_color(ctx) == expected

    def test_alarm_active_at_peak_phase(self) -> None:
        # now=0.125 → 2π·2·0.125 = π/2 → sin=1 → phase=1.0 → exactly ALARM_PEAK.
        ctx = _make_ctx(alarm_active=True, now=0.125)
        assert _dps_color(ctx) == _Palette.ALARM_PEAK

