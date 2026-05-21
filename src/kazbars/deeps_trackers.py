"""KazBars — Deeps trackers: rolling DPS / DPIS / HPS counters.

Three small classes, one per metric, plus a `TrackerSnapshot` dataclass that
bundles the rolling rates into one read-only value for the UI tick.

Slimmed from `Deeps/rust/deeps/src/trackers/`:

  - One window per tracker (5 s by default), not Deeps's two (fixed `ma_5s`
    + cyclable `display_avg`). v1 has no user-cyclable window.
  - No totals, hit counts, max hits, or crit aggregates — those don't reach
    the overlay in v1.
  - Heals still keep 3 internal buckets (spell / potion / health_tap)
    because per-bucket warm-up is load-bearing: an early spell heal must
    not unblock the potion bucket's average. The aggregate is composed at
    snapshot time.

Time is float seconds supplied by the caller (the meter thread reads
`time.monotonic()` once per tick); trackers never read the clock
themselves, so tests run with synthetic timestamps.

Contract for `rolling_rate(t)`:

  - Returns `None` while warm-up is closed (no events, or first event less
    than one window-width in the past).
  - Returns `0.0` during silence after warm-up has cleared — honest decay,
    not a frozen last-known value.
  - Returns the sum-of-events-in-window divided by window-seconds otherwise.
"""

from dataclasses import dataclass

from .deeps_parsers import HealKind, IncomingHeal
from .deeps_rolling_window import RollingWindow

DEFAULT_WINDOW_SECONDS = 5.0


# =========================================================================== #
# Outgoing damage (DPS)                                                       #
# =========================================================================== #

class DamageOutTracker:
    """Rolling outgoing damage rate (player + optionally pet damage).

    Player damage and pet damage feed the same rolling window — the meter
    decides whether to call `record_pet` based on the `include_pet_damage`
    toggle. Pet hits contribute to the rate identically to player hits.
    """

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self._window = RollingWindow(window_seconds)
        self._window_seconds = window_seconds

    def record(self, t: float, amount: int) -> None:
        """Record a player-authored damage hit."""
        self._window.record(t, amount)

    def record_pet(self, t: float, amount: int) -> None:
        """Record a pet-authored damage hit (only called when the toggle is on)."""
        self._window.record(t, amount)

    def rolling_rate(self, t: float) -> float | None:
        first = self._window.first_event()
        if first is None or t - first < self._window_seconds:
            return None
        return self._window.sum_since(t, self._window_seconds) / self._window_seconds

    def reset(self) -> None:
        self._window.reset()


# =========================================================================== #
# Incoming damage (DPIS)                                                      #
# =========================================================================== #

class DamageInTracker:
    """Rolling incoming damage rate.

    Self-damage (e.g. drain self-DoT, AoE rebound) IS counted here — the
    parser accepts `target == "you"` regardless of who fired it. That's the
    locked behaviour from the design discussion.
    """

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self._window = RollingWindow(window_seconds)
        self._window_seconds = window_seconds

    def record(self, t: float, amount: int) -> None:
        self._window.record(t, amount)

    def rolling_rate(self, t: float) -> float | None:
        first = self._window.first_event()
        if first is None or t - first < self._window_seconds:
            return None
        return self._window.sum_since(t, self._window_seconds) / self._window_seconds

    def reset(self) -> None:
        self._window.reset()


# =========================================================================== #
# Incoming heals (HPS) — 3 buckets, aggregated at snapshot                    #
# =========================================================================== #

class HealsInTracker:
    """Rolling incoming-heal rate, summed across spell / potion / health-tap.

    Each `HealKind` keeps its own rolling window and its own first-event
    marker, so warm-up is per-bucket. The aggregate `rolling_rate` only
    counts buckets that have individually cleared their warm-up — a single
    early spell heal can't unblock the potion bucket's average.

    Returns `None` when no bucket has cleared warm-up, the sum of cleared
    buckets' per-second rates otherwise (so 0.0 is a valid post-warm-up
    "no recent heals" reading).
    """

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self._spell = RollingWindow(window_seconds)
        self._potion = RollingWindow(window_seconds)
        self._health_tap = RollingWindow(window_seconds)
        self._window_seconds = window_seconds

    def record(self, t: float, heal: IncomingHeal) -> None:
        if heal.kind is HealKind.SPELL:
            self._spell.record(t, heal.amount)
        elif heal.kind is HealKind.POTION:
            self._potion.record(t, heal.amount)
        elif heal.kind is HealKind.HEALTH_TAP:
            self._health_tap.record(t, heal.amount)

    def _cleared_buckets(self, t: float) -> list[RollingWindow]:
        """Return the subset of buckets that have cleared their warm-up at `t`."""
        cleared: list[RollingWindow] = []
        for w in (self._spell, self._potion, self._health_tap):
            first = w.first_event()
            if first is None or t - first < self._window_seconds:
                continue
            cleared.append(w)
        return cleared

    def rolling_rate(self, t: float) -> float | None:
        cleared = self._cleared_buckets(t)
        if not cleared:
            return None
        total_per_sec = 0.0
        for w in cleared:
            total_per_sec += w.sum_since(t, self._window_seconds) / self._window_seconds
        return total_per_sec

    def reset(self) -> None:
        self._spell.reset()
        self._potion.reset()
        self._health_tap.reset()


# =========================================================================== #
# Outgoing heals (HPS-out) — heals you cast on other players                  #
# =========================================================================== #

class HealsOutTracker:
    """Rolling outgoing-heal rate (heals you cast on other players).

    Single window — the meter is responsible for filtering self-heals,
    own-pet heals, other players' pets/totems, and bubble-converted mob
    heals BEFORE calling `record`; this tracker just sums what it's given.
    """

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self._window = RollingWindow(window_seconds)
        self._window_seconds = window_seconds

    def record(self, t: float, amount: int) -> None:
        self._window.record(t, amount)

    def rolling_rate(self, t: float) -> float | None:
        first = self._window.first_event()
        if first is None or t - first < self._window_seconds:
            return None
        return self._window.sum_since(t, self._window_seconds) / self._window_seconds

    def reset(self) -> None:
        self._window.reset()


# =========================================================================== #
# Snapshot — bundle the rolling rates for the UI tick                         #
# =========================================================================== #

@dataclass(frozen=True)
class TrackerSnapshot:
    """Read-only view of the rolling rates at a single instant.

    Rate fields are float-per-second (possibly 0.0 during post-warm-up
    silence) or None (warming up).
    """

    dps: float | None
    dpis: float | None
    hps: float | None
    hps_out: float | None


def build_snapshot(
    out_tracker: DamageOutTracker,
    in_tracker: DamageInTracker,
    heals_tracker: HealsInTracker,
    heals_out_tracker: HealsOutTracker,
    t: float,
) -> TrackerSnapshot:
    """Compose a `TrackerSnapshot` from the four trackers at time `t`.

    Lock-internal helper: the meter holds its lock while calling this so
    the four reads are mutually consistent.
    """
    return TrackerSnapshot(
        dps=out_tracker.rolling_rate(t),
        dpis=in_tracker.rolling_rate(t),
        hps=heals_tracker.rolling_rate(t),
        hps_out=heals_out_tracker.rolling_rate(t),
    )
