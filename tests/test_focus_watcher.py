"""Tests for the shared ForegroundWatcher.

The Tk `after` loop itself needs a display (covered by /smoke); here we drive
`_tick` directly with an injected probe and assert the suppression fan-out plus
register/unregister bookkeeping.
"""

from kazbars.focus_watcher import ForegroundWatcher


class _FakeOverlay:
    def __init__(self):
        self.suppressed = None
        self.calls = 0

    def set_focus_suppressed(self, suppressed):
        self.suppressed = suppressed
        self.calls += 1


class _FakeRoot:
    """Stand-in for the Tk root: records after() but never actually schedules."""

    def after(self, _ms, _cb):
        return "after#1"

    def after_cancel(self, _id):
        pass


def _watcher(foreground):
    state = {"fg": foreground}
    w = ForegroundWatcher(_FakeRoot(), probe=lambda: state["fg"])
    return w, state


def test_register_pushes_current_state_immediately():
    w, _ = _watcher(foreground=True)
    ov = _FakeOverlay()
    w.register(ov)
    assert ov.suppressed is False  # foreground -> not suppressed
    assert ov.calls == 1


def test_register_when_backgrounded_suppresses():
    w, _ = _watcher(foreground=False)
    ov = _FakeOverlay()
    w.register(ov)
    assert ov.suppressed is True


def test_tick_fans_out_to_all_registered():
    w, state = _watcher(foreground=True)
    a, b = _FakeOverlay(), _FakeOverlay()
    w.register(a)
    w.register(b)
    state["fg"] = False
    w._tick()
    assert a.suppressed is True
    assert b.suppressed is True


def test_unregister_stops_updates():
    w, state = _watcher(foreground=True)
    ov = _FakeOverlay()
    w.register(ov)
    calls_before = ov.calls
    w.unregister(ov)
    state["fg"] = False
    w._tick()
    assert ov.calls == calls_before  # no further pushes after unregister


def test_register_is_idempotent():
    w, _ = _watcher(foreground=True)
    ov = _FakeOverlay()
    w.register(ov)
    w.register(ov)
    w._tick()
    # one entry only -> exactly one push per tick (plus the initial register push)
    assert ov.calls == 2


def test_failing_overlay_does_not_break_fanout():
    w, state = _watcher(foreground=True)

    class _Boom:
        def set_focus_suppressed(self, _s):
            raise RuntimeError("boom")

    good = _FakeOverlay()
    w.register(_Boom())
    w.register(good)
    state["fg"] = False
    w._tick()  # must not raise
    assert good.suppressed is True
