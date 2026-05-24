"""KazBars — shared foreground-focus watcher.

One ticking service, owned by `KazBarsApp` for the app's whole life, that
probes the foreground window once per tick and pushes a suppression flag to
every registered overlay. Replaces the two per-cluster focus gates (the Deeps
meter's 100 ms focus poll on its tail thread + the Live Tracker panel's 250 ms
`_focus_tick`) with a single probe on the Tk main loop.

Registered overlays only need to expose `set_focus_suppressed(bool)`; the
watcher never touches their content. Probe is injectable so the loop is
testable without a display.
"""

import logging
import tkinter as tk
from collections.abc import Callable

from .foreground import app_or_game_foreground

logger = logging.getLogger(__name__)


class ForegroundWatcher:
    """Polls foreground state and fans out suppression to registered overlays."""

    def __init__(
        self,
        root: tk.Misc,
        *,
        interval_ms: int = 250,
        probe: Callable[[], bool] = app_or_game_foreground,
    ) -> None:
        self._root = root
        self._interval_ms = max(50, int(interval_ms))
        self._probe = probe
        self._overlays: list = []
        self._after_id: str | None = None
        self._last: bool | None = None  # last foreground state pushed

    def register(self, overlay) -> None:
        """Add an overlay (must expose `set_focus_suppressed(bool)`). The current
        focus state is pushed immediately so a freshly-created overlay is gated
        without waiting a full tick."""
        if overlay in self._overlays:
            return
        self._overlays.append(overlay)
        if self._last is None:
            self._last = bool(self._probe())
        self._push(overlay, self._last)

    def unregister(self, overlay) -> None:
        try:
            self._overlays.remove(overlay)
        except ValueError:
            pass

    def start(self) -> None:
        """Begin ticking (idempotent)."""
        if self._after_id is None:
            self._tick()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except (ValueError, tk.TclError):
                pass
            self._after_id = None

    def _tick(self) -> None:
        foreground = bool(self._probe())
        self._last = foreground
        for overlay in list(self._overlays):
            self._push(overlay, foreground)
        try:
            self._after_id = self._root.after(self._interval_ms, self._tick)
        except tk.TclError:
            self._after_id = None  # root gone during teardown

    @staticmethod
    def _push(overlay, foreground: bool) -> None:
        try:
            overlay.set_focus_suppressed(not foreground)
        except Exception:
            logger.debug("ForegroundWatcher push failed", exc_info=True)
