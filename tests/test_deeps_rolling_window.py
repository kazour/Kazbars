"""Smoke tests for kazbars.deeps_rolling_window.

Ports the Rust tests in `Deeps/rust/deeps/src/trackers/window.rs` and adds
a few Python-specific cases (decay-during-silence, exact-boundary
inclusion). Uses synthetic timestamps so behaviour is deterministic and
independent of wall-clock state.

Run: `pytest tests/test_deeps_rolling_window.py` (from repo root).
"""

from kazbars.deeps_rolling_window import RollingWindow

BASE = 1_000_000.0  # arbitrary monotonic origin


def at(ms: int) -> float:
    """Convenience: BASE + ms milliseconds, as a float of seconds."""
    return BASE + ms / 1000.0


# =========================================================================== #
# Ported from window.rs::tests                                                #
# =========================================================================== #

def test_empty_returns_zero() -> None:
    w = RollingWindow(capacity_seconds=20.0)
    assert w.sum_since(at(0), 3.0) == 0
    assert w.count_since(at(0), 3.0) == 0
    assert w.first_event() is None


def test_single_event_within_window() -> None:
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 100)
    assert w.sum_since(at(1000), 3.0) == 100
    assert w.count_since(at(1000), 3.0) == 1


def test_event_outside_window_excluded() -> None:
    """Event recorded at t=0, sampled at t=5s with 3s window → excluded."""
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 100)
    assert w.sum_since(at(5000), 3.0) == 0


def test_multiple_events_summed() -> None:
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 10)
    w.record(at(1000), 20)
    w.record(at(2000), 30)
    assert w.sum_since(at(2500), 3.0) == 60
    assert w.count_since(at(2500), 3.0) == 3


def test_pruning_drops_old_events() -> None:
    """`record` triggers a prune; events older than capacity disappear forever."""
    w = RollingWindow(capacity_seconds=5.0)
    w.record(at(0), 10)
    w.record(at(1000), 20)
    w.record(at(6000), 30)  # triggers prune at t=6s; event at t=0 is gone
    # Only the second and third remain.
    assert w.sum_since(at(6000), 10.0) == 50


def test_first_event_tracked() -> None:
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 10)
    w.record(at(100), 20)
    assert w.first_event() == at(0)


def test_reset_clears() -> None:
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 10)
    w.reset()
    assert w.sum_since(at(1000), 3.0) == 0
    assert w.first_event() is None


def test_sum_stops_at_first_old_event() -> None:
    """Walking from the back must break at the first out-of-range event.

    The deque is time-ordered, so once we hit a too-old event, older ones
    can't suddenly be in-range.
    """
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 1000)
    w.record(at(17_000), 5)
    w.record(at(18_000), 7)
    # 3 s window at t=19s → should include only the 17s and 18s events.
    assert w.sum_since(at(19_000), 3.0) == 12


# =========================================================================== #
# Python-specific extras                                                      #
# =========================================================================== #

def test_decay_during_silence() -> None:
    """Without any new `record`, sample value drops to zero as time passes.

    This is the correctness property the meter's 100 ms tick relies on:
    silence should let rolling values trend to zero, not freeze the last
    on-screen number.
    """
    w = RollingWindow(capacity_seconds=20.0)
    w.record(at(0), 100)
    # 1 s later, 5 s window → still in range.
    assert w.sum_since(at(1000), 5.0) == 100
    # 6 s later, 5 s window → falls out.
    assert w.sum_since(at(6000), 5.0) == 0
    # 100 s later, 5 s window → still zero, not stale.
    assert w.sum_since(at(100_000), 5.0) == 0


def test_exact_boundary_inclusive_on_high_side() -> None:
    """An event at t=0, sampled with cutoff=t=0, is included.

    The implementation uses `t >= cutoff` (inclusive lower bound) so an
    event exactly at the boundary counts.
    """
    w = RollingWindow(capacity_seconds=10.0)
    w.record(at(0), 100)
    # 5 s later, 5 s window → cutoff is at(0), event timestamp is at(0).
    assert w.sum_since(at(5000), 5.0) == 100


def test_first_event_survives_pruning() -> None:
    """`first_event()` is set on the first record and stays put across prunes.

    Trackers rely on it for warm-up gating — even after the original event
    is pruned out of the rolling window, the timestamp is still the
    canonical "first ever event" marker.
    """
    w = RollingWindow(capacity_seconds=5.0)
    w.record(at(0), 10)
    w.record(at(10_000), 20)  # prunes the first event
    assert w.first_event() == at(0)
    # And it survives further records.
    w.record(at(20_000), 30)
    assert w.first_event() == at(0)


def test_capacity_zero_keeps_only_current() -> None:
    """Capacity 0 means every prune empties everything older than now.

    Edge case — not used in practice but the math must not break.
    """
    w = RollingWindow(capacity_seconds=0.0)
    w.record(at(0), 10)
    # Record at the same instant — cutoff is now, event is not older, kept.
    assert w.sum_since(at(0), 0.0) == 10
    # 1 ms later — event at(0) is older than cutoff at(1), pruned away.
    w.record(at(1), 20)
    assert w.sum_since(at(1), 1.0) == 20


def test_zero_window_includes_only_now() -> None:
    """`sum_since(now, 0)` includes events with timestamp exactly at `now`.

    Mirrors the Rust contract: the lower bound is inclusive (`t >= cutoff`)
    and there is no upper-bound check. Callers always pass `now >= latest
    event` in practice (the meter thread reads the clock once per tick), so
    "events in the future of `now`" can't occur in production.
    """
    w = RollingWindow(capacity_seconds=10.0)
    w.record(at(1000), 20)
    assert w.sum_since(at(1000), 0.0) == 20
    # Sample one tick later, zero window → empty (the event is now in the past).
    assert w.sum_since(at(1001), 0.0) == 0
