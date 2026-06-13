"""KazBars — Deeps overlay (PIL + win32 layered window).

Glanceable per-pixel-alpha overlay showing five rolling numbers — DPS out,
DPS in, HPS out, HPS in, and ΔHP in — over the game window. Renders to a PIL
bitmap that the shared `overlay_engine.LayeredOverlay` pushes to a
`WS_EX_LAYERED` window via `UpdateLayeredWindow` — bypasses Tk's `-alpha` /
`-transparentcolor` machinery, which is broken on this Tk 9.0 build when
descended from a ttkb.Window root.

Two layouts (user-selectable from the Deeps panel):

  Horizontal — single row of cells with tiny labels below. Default.

  Vertical — cells stacked, no labels (row position IS the label once you
    learn it). Narrower; better for screen-edge placement.

Each cell is a single number; the user picks which of the five are shown via
the panel. Render order is fixed (`ALL_CELL_IDS`); display names live in
`CELL_LABELS`, shared with the panel so the two surfaces always agree.
"""

from __future__ import annotations

import logging
import math
import time
import tkinter as tk
from collections.abc import Callable

from PIL import ImageDraw, ImageFont

from .deeps_meter import MeterSnapshot
from .deeps_settings import overlay_config_from_deeps
from .overlay_engine import HudOverlay, hex_to_rgb, load_font
from .ui_helpers import THEME_COLORS

logger = logging.getLogger(__name__)

# Pulse animation cadence — runs only while a pulse is active so the 2 Hz sine
# reads as a smooth glide rather than the 10 Hz "on/off" stutter you get from
# sampling at the data-tick rate. ~30 Hz (33 ms) is plenty for human-eye smooth
# at 2 Hz and stays cheap because it ONLY runs while alarm/flash is active.
_PULSE_REPAINT_MS = 33


# =========================================================================== #
# Visual constants                                                            #
# =========================================================================== #

_BASE_FONT_SIZE = 22
_LABEL_FONT_SIZE = 11         # cell title below each number (was 8 — too small)

# Layout dimensions at the baseline 22 pt font. Each value scales linearly
# with `_font_size / _BASE_FONT_SIZE` so font changes resize the overlay.
# Tightened from the original (84/56/84/38) to read as a compact cluster.
_PAD_OUTER = 6
_H_CELL_WIDTH = 68            # one number + title below
_H_HEIGHT = 50
_V_CELL_WIDTH = 68
_V_ROW_HEIGHT = 30
_V_SEP_HEIGHT = 1

# Alarm pulse — 2 Hz sine wave on the DPS cell when active.
_ALARM_BLINK_HZ = 2.0


# =========================================================================== #
# Color helpers                                                               #
# =========================================================================== #

class _Palette:
    STROKE = (10, 10, 10)
    DEFAULT = (232, 230, 224)            # warm off-white
    LABEL = (176, 176, 176)              # muted
    SEPARATOR = (64, 64, 64)
    ALARM_PEAK = (231, 76, 60)           # #E74C3C — DPS-out (threat) pulse target
    GREEN_TINT = (130, 195, 130)         # sage HPS-positive
    YELLOW_TINT = (215, 165, 95)         # warm-orange DPIS-deficit (steady tint)
    DPIS_FLASH_PEAK = (240, 130, 40)     # deeper amber — DPIS/ΔHP pulse target,
                                         # distinct from ALARM_PEAK red so threat
                                         # and survival signals don't blend


# Pull the alarm-peak from the theme so any palette tweak in DESIGN.md ripples.
try:
    _Palette.ALARM_PEAK = hex_to_rgb(THEME_COLORS["danger"])
except Exception:
    logger.debug("Could not derive alarm-peak from theme; keeping default", exc_info=True)


def _lerp_rgb(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )


def _format_rate(value: float | None) -> str:
    """Render a rolling-rate value. None (warm-up) → three dashes; otherwise
    rounded integer (no thousands separator — locked decision)."""
    if value is None:
        return "---"
    return str(round(value))


def _format_signed_int(value: float | None) -> str:
    """Signed integer for the ΔHP-in cell. Uses U+2212 (proper minus) instead of
    the ASCII hyphen so the glyph reads as a math symbol, not punctuation.
    None (warm-up) → three dashes; exact zero → `0` with no sign."""
    if value is None:
        return "---"
    n = round(value)
    if n > 0:
        return f"+{n}"
    if n < 0:
        return f"−{-n}"
    return "0"


# =========================================================================== #
# Display smoother — EMA + coarse rounding + redraw cadence                   #
# =========================================================================== #

# Numeric channels the smoother eases. The ΔHP-in cell is derived from the
# smoothed `hps`/`dpis` at render time, so it isn't a channel of its own.
_SMOOTH_CHANNELS: tuple[str, ...] = ("dps", "dpis", "hps", "hps-out")

# Smoothing strength 100 maps to this EMA time constant (seconds). The drawn
# digit covers ~63% of a step toward the true value in one tau; bigger = calmer
# but laggier. 1.5 s reads as a gentle glide without feeling stale.
_MAX_TAU = 1.5


class _DisplaySmoother:
    """Presentation-layer easing for the overlay numbers.

    Pure (the caller supplies a monotonic `now`), so it's unit-tested without a
    display. Three independent knobs, each disable-able:

      - `smoothing` (0-100): EMA strength. 0 = off (the drawn value snaps to the
        true value). Mapped to a time constant `tau = pct/100 * _MAX_TAU`.
      - `round_step` (>=1): coarse rounding of the committed value. 1 = off.
      - `refresh_ms` (>=100): how often the committed (drawn) value is allowed to
        change. 100 = live (every call). Larger holds the last drawn digits
        between commits while the EMA keeps gliding underneath.

    The EMA advances every `update()` call; the rounded result is *committed*
    (becomes the drawn value) only when `refresh_ms` has elapsed since the last
    commit. `None` (warm-up) resets a channel so the next real sample snaps in
    rather than easing up from a stale number.

    Colors/tints/alarm are NOT smoothed — callers read those off the raw
    snapshot so the "am I dying" signal stays instant. Only digits ease.
    """

    def __init__(self, smoothing: int = 0, round_step: int = 1, refresh_ms: int = 100) -> None:
        self._tau = max(0, min(int(smoothing), 100)) / 100.0 * _MAX_TAU
        self._step = max(1, int(round_step))
        self._refresh = max(0.0, int(refresh_ms) / 1000.0)
        self._ema: dict[str, float | None] = dict.fromkeys(_SMOOTH_CHANNELS)
        self._shown: dict[str, float | None] = dict.fromkeys(_SMOOTH_CHANNELS)
        self._last_now: float | None = None
        self._last_commit: float | None = None

    def set_smoothing(self, pct: int) -> None:
        self._tau = max(0, min(int(pct), 100)) / 100.0 * _MAX_TAU

    def set_round_step(self, step: int) -> None:
        self._step = max(1, int(step))

    def set_refresh_ms(self, ms: int) -> None:
        self._refresh = max(0.0, int(ms) / 1000.0)

    def _round(self, value: float | None) -> float | None:
        if value is None:
            return None
        if self._step <= 1:
            return float(round(value))
        return float(round(value / self._step) * self._step)

    def update(self, values: dict[str, float | None], now: float) -> dict[str, float | None]:
        """Advance the EMA for each channel, commit on the cadence, return the
        drawn values. Keys mirror `_SMOOTH_CHANNELS`."""
        dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now

        for ch in _SMOOTH_CHANNELS:
            raw = values.get(ch)
            prev = self._ema.get(ch)
            if raw is None:
                self._ema[ch] = None
            elif prev is None or self._tau <= 0.0 or dt <= 0.0:
                # First real sample after warm-up, or smoothing off → snap.
                self._ema[ch] = float(raw)
            else:
                alpha = 1.0 - math.exp(-dt / self._tau)
                self._ema[ch] = prev + alpha * (float(raw) - prev)

        if self._last_commit is None or (now - self._last_commit) >= self._refresh:
            self._last_commit = now
            for ch in _SMOOTH_CHANNELS:
                self._shown[ch] = self._round(self._ema[ch])
        return dict(self._shown)


# =========================================================================== #
# Render context + cell renderers                                             #
# =========================================================================== #

class _RenderContext:
    """Bundle of state a cell renderer needs."""

    __slots__ = ("alarm_active", "alarm_threshold", "display",
                 "dpis_flash", "dpis_flash_active", "dpis_tint_full",
                 "dpis_tint_start", "font", "hpis_green",
                 "label_font", "now", "scale", "snapshot")

    def __init__(
        self,
        snapshot: MeterSnapshot,
        display: dict[str, float | None],
        now: float,
        font: ImageFont.ImageFont,
        label_font: ImageFont.ImageFont,
        alarm_active: bool,
        alarm_threshold: float,
        hpis_green: float,
        dpis_tint_start: float,
        dpis_tint_full: float,
        dpis_flash: float,
        dpis_flash_active: bool,
        scale: float,
    ) -> None:
        self.snapshot = snapshot
        self.display = display
        self.now = now
        self.font = font
        self.label_font = label_font
        self.alarm_active = alarm_active
        self.alarm_threshold = alarm_threshold
        self.hpis_green = hpis_green
        self.dpis_tint_start = dpis_tint_start
        self.dpis_tint_full = dpis_tint_full
        self.dpis_flash = dpis_flash
        self.dpis_flash_active = dpis_flash_active
        self.scale = scale


def _dps_color(ctx: _RenderContext) -> tuple[int, int, int]:
    """White by default; pulsing red sine wave when alarm is active."""
    if not ctx.alarm_active:
        return _Palette.DEFAULT
    phase = (math.sin(2 * math.pi * _ALARM_BLINK_HZ * ctx.now) + 1.0) * 0.5
    return _lerp_rgb(_Palette.DEFAULT, _Palette.ALARM_PEAK, phase)


def _dpis_ramp_color(ctx: _RenderContext) -> tuple[int, int, int]:
    """Three-step ramp for the DPIS / ΔHP-in cells driven by `-net` (incoming
    damage minus heals):

      < tint_start          → DEFAULT (no tint)
      tint_start → tint_full → linear fade DEFAULT → YELLOW_TINT
      tint_full → flash      → solid YELLOW_TINT
      >= flash + flash_active → YELLOW_TINT pulse-flashing to DPIS_FLASH_PEAK

    `dpis_flash_active` is hysteresis-tracked in the overlay (on at `flash`,
    off at `flash * 0.9`) so the pulse doesn't strobe on/off at the boundary.
    Reads `ctx.snapshot` (raw) so the tint stays instant while digits ease.
    """
    snap = ctx.snapshot
    if snap.hps is None or snap.dpis is None:
        return _Palette.DEFAULT
    net_deficit = snap.dpis - snap.hps  # = -net
    if net_deficit < ctx.dpis_tint_start:
        return _Palette.DEFAULT
    if net_deficit < ctx.dpis_tint_full:
        span = max(1e-6, ctx.dpis_tint_full - ctx.dpis_tint_start)
        t = (net_deficit - ctx.dpis_tint_start) / span
        return _lerp_rgb(_Palette.DEFAULT, _Palette.YELLOW_TINT, t)
    if not ctx.dpis_flash_active:
        return _Palette.YELLOW_TINT
    phase = (math.sin(2 * math.pi * _ALARM_BLINK_HZ * ctx.now) + 1.0) * 0.5
    return _lerp_rgb(_Palette.YELLOW_TINT, _Palette.DPIS_FLASH_PEAK, phase)


def _tint_colors(ctx: _RenderContext) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Compute (hps_color, dpis_color). HPS-in is the same binary green; DPIS
    runs through the new three-step ramp."""
    snap = ctx.snapshot
    if snap.hps is None or snap.dpis is None:
        return (_Palette.DEFAULT, _Palette.DEFAULT)
    net = snap.hps - snap.dpis
    hps = _Palette.GREEN_TINT if net > ctx.hpis_green else _Palette.DEFAULT
    return (hps, _dpis_ramp_color(ctx))


def _draw_stroked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    stroke_width: int = 1,
) -> None:
    """Center-anchored text with an 8-direction dark stroke for legibility
    against arbitrary game scenery. PIL handles the stroke natively."""
    draw.text(
        xy, text, font=font, fill=fill,
        anchor="mm",
        stroke_width=stroke_width,
        stroke_fill=_Palette.STROKE,
    )


def _draw_solo_cell(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    text: str,
    color: tuple[int, int, int],
    label: str | None,
    ctx: _RenderContext,
    show_label: bool,
) -> None:
    """Centered single number, optional label below. Used by every cell."""
    x, y, w, h = bounds
    cx = x + w // 2
    if show_label and label:
        cy_number = y + round(h * 0.40)
        cy_label = y + round(h * 0.80)
        _draw_stroked_text(draw, (cx, cy_number), text, ctx.font, color)
        draw.text(
            (cx, cy_label), label, font=ctx.label_font,
            fill=_Palette.LABEL, anchor="mm",
            stroke_width=1, stroke_fill=_Palette.STROKE,
        )
    else:
        cy = y + h // 2
        _draw_stroked_text(draw, (cx, cy), text, ctx.font, color)


def _net_color(ctx: _RenderContext) -> tuple[int, int, int]:
    """Tint for the ΔHP-in cell. Positive side mirrors the HPS-in green; negative
    side runs through the same `_dpis_ramp_color` ramp so the DPIS and ΔHP
    cells always agree visually (they're two views of the same signal)."""
    snap = ctx.snapshot
    if snap.hps is None or snap.dpis is None:
        return _Palette.DEFAULT
    net = snap.hps - snap.dpis
    if net > ctx.hpis_green:
        return _Palette.GREEN_TINT
    return _dpis_ramp_color(ctx)


# =========================================================================== #
# Cells — fixed render order + display labels                                 #
# =========================================================================== #

# Cell IDs the user can toggle on/off via the panel, in fixed render order.
ALL_CELL_IDS: tuple[str, ...] = ("dps", "dpis", "hps", "hps-out", "net")

# Display label per cell — the single source of truth for cell naming, shared
# with the Deeps panel's visibility picker so the overlay and panel agree.
CELL_LABELS: dict[str, str] = {
    "dps": "DPS out",
    "dpis": "DPS in",
    "hps": "HPS in",
    "hps-out": "HPS out",
    "net": "ΔHP in",
}


def _cell_text_and_color(
    cell_id: str, ctx: _RenderContext,
) -> tuple[str, tuple[int, int, int]]:
    """Formatted value + render color for one cell at the current snapshot.

    The number text comes from the smoothed `ctx.display` values; the color
    comes from the raw `ctx.snapshot` (via the tint/alarm helpers) so tints stay
    instant while the digits ease.
    """
    disp = ctx.display
    if cell_id == "dps":
        return _format_rate(disp["dps"]), _dps_color(ctx)
    if cell_id == "dpis":
        return _format_rate(disp["dpis"]), _tint_colors(ctx)[1]
    if cell_id == "hps":
        return _format_rate(disp["hps"]), _tint_colors(ctx)[0]
    if cell_id == "hps-out":
        return _format_rate(disp["hps-out"]), _Palette.DEFAULT
    # net (ΔHP in) — signed smoothed-HPS-in minus smoothed-DPS-in, tinted to
    # match the cells (tint still derived from the raw snapshot).
    d_hps, d_dpis = disp["hps"], disp["dpis"]
    net = d_hps - d_dpis if (d_hps is not None and d_dpis is not None) else None
    return _format_signed_int(net), _net_color(ctx)


def visible_cells_in_order(visible: set[str] | frozenset[str]) -> list[str]:
    """Return the visible cell IDs in fixed render order."""
    return [cid for cid in ALL_CELL_IDS if cid in visible]


def _cell_width(scale: float, layout: str) -> int:
    """Pixel width of a cell at the given font scale and layout."""
    base = _H_CELL_WIDTH if layout == "horizontal" else _V_CELL_WIDTH
    return round(base * scale)


# =========================================================================== #
# DeepsOverlay                                                                #
# =========================================================================== #

class DeepsOverlay:
    """Deeps numbers overlay — a `HudOverlay` consumer.

    Holds the per-snapshot content state (numbers, alarm flag, thresholds,
    layout, visible cells) and draws it; `HudOverlay` owns the backdrop, lock
    chrome, drag, focus-suppression, and position persistence. The panel's UI
    tick drives `paint(snapshot, now)` at ~10 Hz.
    """

    def __init__(
        self,
        root: tk.Misc,
        settings: dict,
        on_position_changed: Callable[[int, int, bool], None] | None = None,
        on_lock_changed: Callable[[bool], None] | None = None,
    ) -> None:
        # Geometry + appearance + lock live in the shared OverlayConfig.
        self._config = overlay_config_from_deeps(settings)

        # Content state owned by this consumer.
        self._layout: str = settings.get("layout", "horizontal")
        raw_visible = settings.get("visible_cells", ALL_CELL_IDS)
        self._visible: frozenset[str] = frozenset(
            c for c in raw_visible if c in ALL_CELL_IDS
        )
        self._alarm_threshold: float = 2000.0
        self._hpis_green: float = 50.0
        self._dpis_tint_start: float = 200.0
        self._dpis_tint_full: float = 300.0
        self._dpis_flash: float = 500.0
        self._alarm_active: bool = False
        self._dpis_flash_active: bool = False
        self._snapshot: MeterSnapshot = MeterSnapshot.empty()
        self._now: float = 0.0

        # Self-driven ~30 Hz repaint loop that only runs while a pulse is
        # active. Without it the 2 Hz sine would be sampled at 10 Hz
        # (the panel's data tick) → ~5 frames per cycle → reads as on/off.
        self._root: tk.Misc = root
        self._pulse_after_id: str | None = None

        # Presentation-layer easing of the drawn numbers (see _DisplaySmoother).
        # Reads its three knobs from settings; the meter owns `window_seconds`.
        self._smoother = _DisplaySmoother(
            smoothing=int(settings.get("smoothing", 0)),
            round_step=int(settings.get("round_step", 1)),
            refresh_ms=int(settings.get("refresh_ms", 100)),
        )
        self._display: dict[str, float | None] = dict.fromkeys(_SMOOTH_CHANNELS)

        self._on_position_changed_external = on_position_changed
        self._on_lock_changed = on_lock_changed

        self._hud = HudOverlay(
            root, self._config,
            render_content=self._render_content,
            measure=self._measure,
            on_config_changed=self._on_hud_config_changed,
        )

    # ------------------------------------------------------------------ #
    # Public API (mirrors the previous Toplevel-based shape)              #
    # ------------------------------------------------------------------ #

    def show(self) -> None:
        self._hud.show()

    def hide(self) -> None:
        self._hud.hide()
        # Tear down pulse state + animation so Stop->Start doesn't paint
        # against stale flags and the 30 Hz loop doesn't fire while hidden.
        self._alarm_active = False
        self._dpis_flash_active = False
        self._cancel_pulse_tick()

    def set_focus_suppressed(self, suppressed: bool) -> None:
        self._hud.set_focus_suppressed(suppressed)

    def destroy(self) -> None:
        self._cancel_pulse_tick()
        self._hud.destroy()

    def set_layout(self, layout: str) -> None:
        if layout not in ("horizontal", "vertical") or layout == self._layout:
            return
        self._layout = layout
        self._hud.resize()

    def set_font(self, family: str, size: int) -> None:
        size = max(12, min(int(size), 48))
        if family == self._config.font_family and size == self._config.font_size:
            return
        self._config.font_family = family
        self._config.font_size = size
        self._hud.resize()

    def set_bg_opacity(self, opacity: float) -> None:
        self._config.bg_opacity = max(0.0, min(float(opacity), 1.0))
        self._hud.request_paint()

    def set_smoothing(self, pct: int) -> None:
        """Display-easing strength 0-100 (0 = off). Takes effect on the next tick."""
        self._smoother.set_smoothing(pct)

    def set_round_step(self, step: int) -> None:
        """Coarse-rounding step for the drawn value (1 = off)."""
        self._smoother.set_round_step(step)

    def set_refresh_ms(self, ms: int) -> None:
        """How often the drawn digits may change (100 = live)."""
        self._smoother.set_refresh_ms(ms)

    def set_visible_cells(self, cells: list[str] | tuple[str, ...] | set[str]) -> None:
        """Set which cells are visible. Unknown IDs are ignored defensively."""
        new = frozenset(c for c in cells if c in ALL_CELL_IDS)
        if new == self._visible:
            return
        self._visible = new
        self._hud.resize()

    def set_locked(self, locked: bool) -> None:
        self._hud.set_locked(locked)

    def is_locked(self) -> bool:
        return self._hud.is_locked()

    def update_thresholds(
        self,
        alarm: float,
        green: float,
        dpis_tint_start: float,
        dpis_tint_full: float,
        dpis_flash: float,
    ) -> None:
        """Push the DPS-out alarm + ΔHP-in tint ramp thresholds.

        Three ramp values define the DPIS / ΔHP cells' tint zones (see
        `_dpis_ramp_color` for the curve). Caller's responsibility to keep them
        ordered (`tint_start < tint_full < dpis_flash`) — the overlay doesn't
        re-sort, since the user is the one configuring them.
        """
        self._alarm_threshold = float(alarm)
        self._hpis_green = float(green)
        self._dpis_tint_start = float(dpis_tint_start)
        self._dpis_tint_full = float(dpis_tint_full)
        self._dpis_flash = float(dpis_flash)

    def update_alarm_active(self, active: bool) -> None:
        was = self._alarm_active
        self._alarm_active = bool(active)
        if was != self._alarm_active:
            self._sync_pulse_animation()

    def paint(self, snapshot: MeterSnapshot, now: float) -> None:
        """Called by the panel's tick. Snapshots the state, advances the display
        smoother, repaints. The smoother advances here (the time-driven entry
        point) — not in `_render_content`, which also runs on resize/appearance
        changes and must not move the easing."""
        self._snapshot = snapshot
        self._now = now
        self._display = self._smoother.update(
            {
                "dps": snapshot.dps,
                "dpis": snapshot.dpis,
                "hps": snapshot.hps,
                "hps-out": snapshot.hps_out,
            },
            now,
        )
        self._update_dpis_flash_state(snapshot)
        self._hud.request_paint()

    # ------------------------------------------------------------------ #
    # DPIS flash hysteresis + self-driven pulse repaint loop              #
    # ------------------------------------------------------------------ #

    # Mirrors the DPS-out alarm hysteresis (in deeps_panel) to keep the pulse
    # from strobing when -net hovers around the flash threshold.
    _DPIS_FLASH_HYSTERESIS = 0.9

    def _update_dpis_flash_state(self, snapshot: MeterSnapshot) -> None:
        if snapshot.hps is None or snapshot.dpis is None:
            return
        deficit = snapshot.dpis - snapshot.hps  # = -net
        on = self._dpis_flash
        off = on * self._DPIS_FLASH_HYSTERESIS
        prev = self._dpis_flash_active
        if not prev and deficit >= on:
            self._dpis_flash_active = True
        elif prev and deficit < off:
            self._dpis_flash_active = False
        if prev != self._dpis_flash_active:
            self._sync_pulse_animation()

    def _wants_pulse(self) -> bool:
        return self._alarm_active or self._dpis_flash_active

    def _sync_pulse_animation(self) -> None:
        """Start the ~30 Hz repaint loop iff a pulse is wanted; cancel otherwise."""
        if self._wants_pulse():
            if self._pulse_after_id is None:
                self._schedule_pulse_tick()
        elif self._pulse_after_id is not None:
            self._cancel_pulse_tick()

    def _schedule_pulse_tick(self) -> None:
        try:
            self._pulse_after_id = self._root.after(_PULSE_REPAINT_MS, self._pulse_tick)
        except tk.TclError:
            # Root vanished mid-schedule (shutdown race) — drop the loop.
            self._pulse_after_id = None

    def _cancel_pulse_tick(self) -> None:
        if self._pulse_after_id is None:
            return
        try:
            self._root.after_cancel(self._pulse_after_id)
        except (ValueError, tk.TclError):
            pass
        self._pulse_after_id = None

    def _pulse_tick(self) -> None:
        """Advance `now` and repaint between data ticks so the sine reads
        smoothly. The data tick (panel-driven) keeps writing snapshot/display;
        we only move the clock forward and re-render."""
        self._pulse_after_id = None
        if not self._wants_pulse():
            return
        self._now = time.monotonic()
        try:
            self._hud.request_paint()
        except tk.TclError:
            return
        self._schedule_pulse_tick()

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    def _on_hud_config_changed(self, cfg) -> None:
        """Drag-end or lock-toggle from the overlay — persist via the panel's
        existing position/lock callbacks (the panel owns the deeps_settings keys)."""
        if self._on_position_changed_external is not None:
            self._on_position_changed_external(cfg.x, cfg.y, cfg.positioned)
        if self._on_lock_changed is not None:
            self._on_lock_changed(cfg.locked)

    def _font_scale(self) -> float:
        return self._config.font_size / _BASE_FONT_SIZE

    def _measure(self) -> tuple[int, int]:
        scale = self._font_scale()
        n = len(visible_cells_in_order(self._visible))
        if self._layout == "horizontal":
            w = n * _cell_width(scale, "horizontal") + 2 * _PAD_OUTER
            h = round(_H_HEIGHT * scale)
        else:
            row_h = round(_V_ROW_HEIGHT * scale)
            w = _cell_width(scale, "vertical") + 2 * _PAD_OUTER
            h = n * row_h + max(0, n - 1) * _V_SEP_HEIGHT + 2 * _PAD_OUTER
        return (max(1, w), max(1, h))

    def _render_content(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        """Draw the cells. `HudOverlay` has already drawn the backdrop and will
        composite the lock dot on top."""
        scale = self._font_scale()
        font = load_font(self._config.font_family, self._config.font_size, bold=True)
        label_size = max(6, round(_LABEL_FONT_SIZE * scale))
        label_font = load_font(self._config.font_family, label_size, bold=False)
        ctx = _RenderContext(
            snapshot=self._snapshot,
            display=self._display,
            now=self._now,
            font=font,
            label_font=label_font,
            alarm_active=self._alarm_active,
            alarm_threshold=self._alarm_threshold,
            hpis_green=self._hpis_green,
            dpis_tint_start=self._dpis_tint_start,
            dpis_tint_full=self._dpis_tint_full,
            dpis_flash=self._dpis_flash,
            dpis_flash_active=self._dpis_flash_active,
            scale=scale,
        )
        if self._layout == "horizontal":
            self._render_horizontal(draw, width, height, ctx)
        else:
            self._render_vertical(draw, width, height, ctx)

    def _render_horizontal(
        self, draw: ImageDraw.ImageDraw, width: int, height: int, ctx: _RenderContext,
    ) -> None:
        x = _PAD_OUTER
        for cell_id in visible_cells_in_order(self._visible):
            cell_w = _cell_width(ctx.scale, "horizontal")
            bounds = (x, 0, cell_w, height)
            text, color = _cell_text_and_color(cell_id, ctx)
            _draw_solo_cell(
                draw, bounds, text, color, CELL_LABELS[cell_id], ctx, show_label=True,
            )
            x += cell_w

    def _render_vertical(
        self, draw: ImageDraw.ImageDraw, width: int, height: int, ctx: _RenderContext,
    ) -> None:
        cells = visible_cells_in_order(self._visible)
        n = len(cells)
        usable_h = height - 2 * _PAD_OUTER - max(0, n - 1) * _V_SEP_HEIGHT
        row_h = usable_h // n if n else height
        cell_w = width - 2 * _PAD_OUTER
        for i, cell_id in enumerate(cells):
            top = _PAD_OUTER + i * (row_h + _V_SEP_HEIGHT)
            bounds = (_PAD_OUTER, top, cell_w, row_h)
            text, color = _cell_text_and_color(cell_id, ctx)
            _draw_solo_cell(
                draw, bounds, text, color, CELL_LABELS[cell_id], ctx, show_label=False,
            )
            # Hairline separator between rows (skip after last).
            if i < n - 1:
                sep_y = top + row_h
                draw.line(
                    (_PAD_OUTER + 12, sep_y, _PAD_OUTER + cell_w - 12, sep_y),
                    fill=(*_Palette.SEPARATOR, 255),
                    width=_V_SEP_HEIGHT,
                )
