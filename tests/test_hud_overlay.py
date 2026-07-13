"""Headless regression tests for HudOverlay's visibility gate.

The real overlay paints through win32 UpdateLayeredWindow, so the visual path
is manual-QA (`/smoke`) territory. But the *gate* — content updates never paint
while the overlay is hidden — is pure control flow, and worth pinning: a
`resize()` (font/cell/layout change) or a `set_locked()` made while the overlay
is stopped must NOT float a ghost on screen. We stub the LayeredOverlay engine
with a paint-counter so the gate can be exercised without a display.

Run: `pytest tests/test_hud_overlay.py` (from repo root).
"""

import kazbars.overlay_engine as oe
from kazbars.overlay_engine import HudOverlay, OverlayConfig


class _FakeRoot:
    def bind(self, _seq, _fn):
        pass

    def winfo_screenwidth(self):
        return 1920


class _FakeEngine:
    """Stand-in for LayeredOverlay: records paint()/show()/hide() so the
    HudOverlay-level visibility gate is observable without win32/Tk."""

    def __init__(self, parent, *, render_callback, width, height):
        self.render_callback = render_callback
        self._width = width
        self._height = height
        self._x = 0
        self._y = 0
        self._locked = False
        self._suppressed = False
        self.root = _FakeRoot()
        self.paint_calls = 0

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    def set_size(self, width, height):
        self._width, self._height = width, height

    def set_position(self, x, y):
        self._x, self._y = int(x), int(y)

    def set_locked(self, locked):
        self._locked = bool(locked)

    def is_locked(self):
        return self._locked

    def set_suppressed(self, suppressed):
        changed = bool(suppressed) != self._suppressed
        self._suppressed = bool(suppressed)
        return changed

    def show(self):
        self.paint()

    def hide(self):
        pass

    def paint(self):
        self.paint_calls += 1

    def destroy(self):
        pass


def _make_hud(monkeypatch, *, measured=(120, 50)):
    monkeypatch.setattr(oe, "LayeredOverlay", _FakeEngine)
    cfg = OverlayConfig(x=100, y=100, positioned=True)
    hud = HudOverlay(
        None, cfg,
        render_content=lambda *_a: None,
        measure=lambda: measured,
    )
    return hud, hud._engine


def test_resize_while_hidden_does_not_paint(monkeypatch):
    hud, engine = _make_hud(monkeypatch)
    assert not hud.is_visible
    hud.resize()
    assert engine.paint_calls == 0  # gated — no ghost


def test_resize_still_updates_geometry_while_hidden(monkeypatch):
    hud, engine = _make_hud(monkeypatch, measured=(200, 80))
    # The size state must update even though we don't paint, so a later show()
    # renders at the new dimensions.
    hud.resize()
    assert (engine.width, engine.height) == (200, 80)


def test_set_locked_while_hidden_does_not_paint(monkeypatch):
    hud, engine = _make_hud(monkeypatch)
    hud.set_locked(True)
    assert engine.is_locked()       # state change still applies
    assert engine.paint_calls == 0  # but no paint while hidden


def test_resize_paints_once_visible(monkeypatch):
    hud, engine = _make_hud(monkeypatch)
    hud.show()                       # one paint via show()
    baseline = engine.paint_calls
    hud.resize()
    assert engine.paint_calls == baseline + 1


def test_set_locked_paints_once_visible(monkeypatch):
    hud, engine = _make_hud(monkeypatch)
    hud.show()
    baseline = engine.paint_calls
    hud.set_locked(True)
    assert engine.paint_calls == baseline + 1


def test_hide_then_resize_stays_blank(monkeypatch):
    hud, engine = _make_hud(monkeypatch)
    hud.show()
    hud.hide()
    baseline = engine.paint_calls
    hud.resize()
    assert engine.paint_calls == baseline  # no repaint after hide
