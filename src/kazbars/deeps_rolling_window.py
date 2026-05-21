"""KazBars — Rolling-window primitive for the Deeps trackers.

Ports `Deeps/rust/deeps/src/trackers/window.rs`. Stores `(timestamp, value)`
events bounded by a `capacity` duration (the longest window ever queried).
On `record`, drops events older than `now - capacity`. Sample queries
(`sum_since`, `count_since`) walk from the back, stopping at the first event
older than the requested window — events are time-ordered by construction.

Time is float-valued seconds, supplied by the caller (typically
`time.monotonic()`). The struct never reads the clock itself, so tests can
drive it with synthetic timestamps.
"""

from collections import deque


class RollingWindow:
    """A FIFO of (timestamp, value) pairs bounded by a capacity duration.

    The capacity must be at least the longest window ever passed to
    `sum_since` / `count_since`, otherwise samples can drop events that are
    still in range.
    """

    def __init__(self, capacity_seconds: float):
        self._events: deque[tuple[float, int]] = deque()
        self._capacity = capacity_seconds
        self._first_event: float | None = None

    def record(self, t: float, value: int) -> None:
        """Append `(t, value)` and prune events older than `t - capacity`."""
        if self._first_event is None:
            self._first_event = t
        self._events.append((t, value))
        self.prune(t)

    def prune(self, now: float) -> None:
        """Drop events older than `now - capacity` from the front."""
        cutoff = now - self._capacity
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def sum_since(self, now: float, window_seconds: float) -> int:
        """Sum of values whose timestamp is within `[now - window, now]`.

        Walks from the back and stops at the first out-of-range event — the
        deque is time-ordered, so older events can't reappear after a newer
        one is rejected.
        """
        cutoff = now - window_seconds
        total = 0
        for t, v in reversed(self._events):
            if t >= cutoff:
                total += v
            else:
                break
        return total

    def count_since(self, now: float, window_seconds: float) -> int:
        """Count of events within `[now - window, now]`."""
        cutoff = now - window_seconds
        n = 0
        for t, _ in reversed(self._events):
            if t >= cutoff:
                n += 1
            else:
                break
        return n

    def first_event(self) -> float | None:
        """Timestamp of the first ever recorded event, or None if reset/empty.

        Survives pruning — used by trackers to gate the warm-up dash state
        ("avg_display = None until elapsed >= window").
        """
        return self._first_event

    def reset(self) -> None:
        """Clear all events and the first-event marker."""
        self._events.clear()
        self._first_event = None
