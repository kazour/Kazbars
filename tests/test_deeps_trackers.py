"""Smoke tests for kazbars.deeps_trackers.

Covers each tracker's warm-up, post-warm-up decay, reset behaviour, and
the per-bucket warm-up rule for heals (which is the bit most likely to
go wrong on refactor). Uses synthetic timestamps.

Run: `pytest tests/test_deeps_trackers.py` (from repo root).
"""

import pytest

from kazbars.deeps_parsers import HealKind, IncomingHeal
from kazbars.deeps_trackers import (
    DamageInTracker,
    DamageOutTracker,
    HealsInTracker,
    HealsOutTracker,
    TrackerSnapshot,
    build_snapshot,
)

BASE = 1_000_000.0


def at(ms: int) -> float:
    return BASE + ms / 1000.0


def heal(kind: HealKind, amount: int) -> IncomingHeal:
    return IncomingHeal(amount=amount, kind=kind, source=None)


# =========================================================================== #
# DamageOutTracker                                                            #
# =========================================================================== #

class TestDamageOutTracker:
    def test_fresh_tracker_returns_none(self) -> None:
        tr = DamageOutTracker()
        assert tr.rolling_rate(at(0)) is None

    def test_warm_up_returns_none(self) -> None:
        """Before 5s have elapsed since first event, rate is None."""
        tr = DamageOutTracker()
        tr.record(at(0), 1000)
        # 4.9 s in — still warming up.
        assert tr.rolling_rate(at(4900)) is None

    def test_warm_up_clears_at_exact_window(self) -> None:
        """At exactly window_seconds after first event, warm-up clears."""
        tr = DamageOutTracker()
        tr.record(at(0), 1000)
        assert tr.rolling_rate(at(5000)) == pytest.approx(1000.0 / 5.0)

    def test_rolling_rate_decays_to_zero_during_silence(self) -> None:
        """After warm-up, silence should let the value trend to 0.0 — not None."""
        tr = DamageOutTracker()
        tr.record(at(0), 1000)
        # Warm-up clears at t=5s. At t=15s the event is 15s old, out of any
        # 5s window. Expected: 0.0, not None.
        assert tr.rolling_rate(at(15_000)) == 0.0

    def test_multiple_events_in_window(self) -> None:
        tr = DamageOutTracker()
        tr.record(at(0), 100)
        tr.record(at(1000), 200)
        tr.record(at(2000), 300)
        # Sample at t=5s: window covers t=[0,5], all three events qualify.
        assert tr.rolling_rate(at(5000)) == pytest.approx(600.0 / 5.0)

    def test_pet_damage_feeds_same_rate(self) -> None:
        """`record_pet` adds to the rolling window identically to `record`."""
        tr = DamageOutTracker()
        tr.record(at(0), 500)
        tr.record_pet(at(1000), 300)
        # Sample at t=5s, 5s window → both events in range.
        assert tr.rolling_rate(at(5000)) == pytest.approx(800.0 / 5.0)

    def test_reset_returns_to_fresh_state(self) -> None:
        tr = DamageOutTracker()
        tr.record(at(0), 1000)
        tr.reset()
        assert tr.rolling_rate(at(5000)) is None

    def test_record_after_reset_re_anchors_warm_up(self) -> None:
        """A new first event after reset starts a fresh 5s warm-up."""
        tr = DamageOutTracker()
        tr.record(at(0), 100)
        tr.reset()
        tr.record(at(10_000), 500)
        # Only 4.9s since the new first event — still warming up.
        assert tr.rolling_rate(at(14_900)) is None
        # 5s in — warm-up clears.
        assert tr.rolling_rate(at(15_000)) == pytest.approx(500.0 / 5.0)


# =========================================================================== #
# DamageInTracker                                                             #
# =========================================================================== #

class TestDamageInTracker:
    def test_fresh_returns_none(self) -> None:
        tr = DamageInTracker()
        assert tr.rolling_rate(at(0)) is None

    def test_warm_up_then_active(self) -> None:
        tr = DamageInTracker()
        tr.record(at(0), 600)
        assert tr.rolling_rate(at(4000)) is None  # warm-up
        assert tr.rolling_rate(at(5000)) == pytest.approx(600.0 / 5.0)  # active

    def test_decay_during_silence(self) -> None:
        tr = DamageInTracker()
        tr.record(at(0), 600)
        assert tr.rolling_rate(at(20_000)) == 0.0

    def test_reset_clears(self) -> None:
        tr = DamageInTracker()
        tr.record(at(0), 600)
        tr.reset()
        assert tr.rolling_rate(at(10_000)) is None


# =========================================================================== #
# HealsInTracker                                                              #
# =========================================================================== #

class TestHealsInTracker:
    def test_fresh_returns_none(self) -> None:
        tr = HealsInTracker()
        assert tr.rolling_rate(at(0)) is None

    def test_single_bucket_warm_up_and_active(self) -> None:
        tr = HealsInTracker()
        tr.record(at(0), heal(HealKind.SPELL, 500))
        assert tr.rolling_rate(at(4000)) is None
        assert tr.rolling_rate(at(5000)) == pytest.approx(500.0 / 5.0)

    def test_per_bucket_warm_up(self) -> None:
        """An early spell event must NOT unblock the potion bucket.

        This is the load-bearing reason we keep 3 internal buckets even
        though we only display one merged HPS number.
        """
        tr = HealsInTracker()
        # Spell at t=0; potion at t=10s.
        tr.record(at(0), heal(HealKind.SPELL, 500))
        tr.record(at(10_000), heal(HealKind.POTION, 200))

        # At t=11s: spell bucket has 11s elapsed (cleared); spell rate = 0
        # (event at t=0 is 11s old, out of 5s window). Potion has only 1s
        # elapsed → potion still warming up, contributes nothing.
        # Aggregate = 0.0 (spell cleared, contributing 0; potion not
        # cleared, ignored). Total 0.0 with `any_cleared=True`.
        assert tr.rolling_rate(at(11_000)) == 0.0

        # At t=15s: spell rate = 0, potion warm-up clears at exactly t=15s,
        # potion rate = 200/5 = 40. Aggregate = 40.
        assert tr.rolling_rate(at(15_000)) == pytest.approx(40.0)

    def test_aggregate_sums_populated_buckets(self) -> None:
        tr = HealsInTracker()
        tr.record(at(0), heal(HealKind.SPELL, 500))
        tr.record(at(1000), heal(HealKind.POTION, 100))
        tr.record(at(2000), heal(HealKind.HEALTH_TAP, 50))
        # All three buckets clear at different times — spell at 5s, potion
        # at 6s, health_tap at 7s. At t=7s all three contribute.
        # spell sum = 500 (event at t=0, 7s old, OUT of 5s window? cutoff = 2.
        # Event at t=0 < cutoff=2 → out. spell sum = 0.)
        # Wait — let me recompute. At t=7s, 5s window covers t=[2,7].
        # spell event at t=0 → out. potion at t=1 → out. health_tap at t=2 → in.
        # So aggregate = 50/5 = 10.0.
        assert tr.rolling_rate(at(7000)) == pytest.approx(10.0)

    def test_aggregate_after_all_active(self) -> None:
        """All three buckets recently active → aggregate is sum of rates."""
        tr = HealsInTracker()
        tr.record(at(0), heal(HealKind.SPELL, 500))
        tr.record(at(0), heal(HealKind.POTION, 100))
        tr.record(at(0), heal(HealKind.HEALTH_TAP, 50))
        # At t=5s — all warm-ups just cleared, all events still in 5s window.
        # spell rate=100, potion rate=20, health_tap rate=10 → total 130.
        assert tr.rolling_rate(at(5000)) == pytest.approx(130.0)

    def test_decay_during_silence_after_any_cleared(self) -> None:
        """Once any bucket clears warm-up, silence trends to 0.0, not None."""
        tr = HealsInTracker()
        tr.record(at(0), heal(HealKind.SPELL, 500))
        # At t=20s — spell cleared at 5s, decayed since 5s, all events out of window.
        # Aggregate is 0.0 (cleared, but no recent events).
        assert tr.rolling_rate(at(20_000)) == 0.0

    def test_reset_clears_all_buckets(self) -> None:
        tr = HealsInTracker()
        tr.record(at(0), heal(HealKind.SPELL, 500))
        tr.record(at(100), heal(HealKind.POTION, 50))
        tr.record(at(200), heal(HealKind.HEALTH_TAP, 25))
        tr.reset()
        assert tr.rolling_rate(at(10_000)) is None


# =========================================================================== #
# HealsOutTracker                                                             #
# =========================================================================== #

class TestHealsOutTracker:
    def test_fresh_returns_none(self) -> None:
        tr = HealsOutTracker()
        assert tr.rolling_rate(at(0)) is None

    def test_warm_up_then_active(self) -> None:
        tr = HealsOutTracker()
        tr.record(at(0), 800)
        assert tr.rolling_rate(at(4000)) is None  # warm-up
        assert tr.rolling_rate(at(5000)) == pytest.approx(800.0 / 5.0)  # active

    def test_decay_during_silence(self) -> None:
        tr = HealsOutTracker()
        tr.record(at(0), 800)
        assert tr.rolling_rate(at(20_000)) == 0.0

    def test_multiple_events_sum_in_window(self) -> None:
        tr = HealsOutTracker()
        tr.record(at(0), 192)
        tr.record(at(1000), 645)
        tr.record(at(2000), 384)
        assert tr.rolling_rate(at(5000)) == pytest.approx((192 + 645 + 384) / 5.0)

    def test_reset_clears(self) -> None:
        tr = HealsOutTracker()
        tr.record(at(0), 500)
        tr.reset()
        assert tr.rolling_rate(at(10_000)) is None


# =========================================================================== #
# Snapshot composition                                                        #
# =========================================================================== #

class TestSnapshot:
    def test_fresh_trackers_produce_all_none_snapshot(self) -> None:
        s = build_snapshot(
            DamageOutTracker(),
            DamageInTracker(),
            HealsInTracker(),
            HealsOutTracker(),
            at(0),
        )
        assert s == TrackerSnapshot(dps=None, dpis=None, hps=None, hps_out=None)

    def test_partial_warm_up_mixes_none_and_float(self) -> None:
        """One tracker cleared, another warming up, another empty."""
        out_tr = DamageOutTracker()
        in_tr = DamageInTracker()
        heals_tr = HealsInTracker()
        heals_out_tr = HealsOutTracker()
        # Out: cleared at t=5s.
        out_tr.record(at(0), 1000)
        # In: still warming up at t=5s (only 2s in).
        in_tr.record(at(3000), 500)
        # Heals + Heals-out: empty.
        s = build_snapshot(out_tr, in_tr, heals_tr, heals_out_tr, at(5000))
        assert s.dps == pytest.approx(200.0)
        assert s.dpis is None
        assert s.hps is None
        assert s.hps_out is None

    def test_full_active(self) -> None:
        out_tr = DamageOutTracker()
        in_tr = DamageInTracker()
        heals_tr = HealsInTracker()
        heals_out_tr = HealsOutTracker()
        out_tr.record(at(0), 1000)
        in_tr.record(at(0), 500)
        heals_tr.record(at(0), heal(HealKind.SPELL, 250))
        heals_out_tr.record(at(0), 400)
        s = build_snapshot(out_tr, in_tr, heals_tr, heals_out_tr, at(5000))
        assert s.dps == pytest.approx(200.0)
        assert s.dpis == pytest.approx(100.0)
        assert s.hps == pytest.approx(50.0)
        assert s.hps_out == pytest.approx(80.0)

    def test_snapshot_is_frozen(self) -> None:
        """TrackerSnapshot is immutable so the UI can share it without
        worrying about the meter mutating fields mid-read."""
        s = TrackerSnapshot(dps=1.0, dpis=2.0, hps=3.0, hps_out=4.0)
        with pytest.raises((AttributeError, Exception)):
            s.dps = 999.0  # type: ignore[misc]
