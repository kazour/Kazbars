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
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

from .deeps_meter import MeterSnapshot
from .overlay_engine import LayeredOverlay, load_font
from .ui_helpers import THEME_COLORS

logger = logging.getLogger(__name__)


# =========================================================================== #
# Visual constants                                                            #
# =========================================================================== #

_BASE_FONT_SIZE = 22
_LABEL_FONT_SIZE = 8

# Layout dimensions at the baseline 22 pt font. Each value scales linearly
# with `_font_size / _BASE_FONT_SIZE` so font changes resize the overlay.
_PAD_OUTER = 8
_H_CELL_WIDTH = 84            # one number + label below
_H_HEIGHT = 56
_V_CELL_WIDTH = 84
_V_ROW_HEIGHT = 38
_V_SEP_HEIGHT = 1

# Alarm pulse — 2 Hz sine wave on the DPS cell when active.
_ALARM_BLINK_HZ = 2.0

# Bg fill — solid dark, the alpha channel does the work. Premultiplied at
# `_draw_background`.
_BG_FILL_RGB = (10, 10, 10)


# =========================================================================== #
# Color helpers                                                               #
# =========================================================================== #

class _Palette:
    STROKE = (10, 10, 10)
    DEFAULT = (232, 230, 224)            # warm off-white
    LABEL = (176, 176, 176)              # muted
    SEPARATOR = (64, 64, 64)
    ALARM_PEAK = (231, 76, 60)           # #E74C3C — pulse target
    GREEN_TINT = (130, 195, 130)         # sage HPS-positive
    YELLOW_TINT = (215, 165, 95)         # warm-orange DPIS-deficit


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# Pull the alarm-peak from the theme so any palette tweak in DESIGN.md ripples.
try:
    _Palette.ALARM_PEAK = _hex_to_rgb(THEME_COLORS["danger"])
except Exception:
    pass


def _lerp_rgb(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )


# Legacy hex-string helper retained for the existing _lerp_color tests.
def _lerp_color(c1: str, c2: str, t: float) -> str:
    r, g, b = _lerp_rgb(_hex_to_rgb(c1), _hex_to_rgb(c2), t)
    return f"#{r:02x}{g:02x}{b:02x}"


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
# Render context + cell renderers                                             #
# =========================================================================== #

class _RenderContext:
    """Bundle of state a cell renderer needs."""

    __slots__ = ("alarm_active", "alarm_threshold", "dpis_yellow",
                 "font", "hpis_green", "label_font", "now", "scale", "snapshot")

    def __init__(
        self,
        snapshot: MeterSnapshot,
        now: float,
        font: ImageFont.ImageFont,
        label_font: ImageFont.ImageFont,
        alarm_active: bool,
        alarm_threshold: float,
        hpis_green: float,
        dpis_yellow: float,
        scale: float,
    ) -> None:
        self.snapshot = snapshot
        self.now = now
        self.font = font
        self.label_font = label_font
        self.alarm_active = alarm_active
        self.alarm_threshold = alarm_threshold
        self.hpis_green = hpis_green
        self.dpis_yellow = dpis_yellow
        self.scale = scale


def _dps_color(ctx: _RenderContext) -> tuple[int, int, int]:
    """White by default; pulsing red sine wave when alarm is active."""
    if not ctx.alarm_active:
        return _Palette.DEFAULT
    phase = (math.sin(2 * math.pi * _ALARM_BLINK_HZ * ctx.now) + 1.0) * 0.5
    return _lerp_rgb(_Palette.DEFAULT, _Palette.ALARM_PEAK, phase)


def _tint_colors(ctx: _RenderContext) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Compute (hps_color, dpis_color) from net HP rate vs thresholds."""
    snap = ctx.snapshot
    if snap.hps is None or snap.dpis is None:
        return (_Palette.DEFAULT, _Palette.DEFAULT)
    net = snap.hps - snap.dpis
    hps = _Palette.GREEN_TINT if net > ctx.hpis_green else _Palette.DEFAULT
    dpis = _Palette.YELLOW_TINT if -net > ctx.dpis_yellow else _Palette.DEFAULT
    return (hps, dpis)


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
        cy_number = y + round(h * 0.42)
        cy_label = y + round(h * 0.78)
        _draw_stroked_text(draw, (cx, cy_number), text, ctx.font, color)
        draw.text(
            (cx, cy_label), label, font=ctx.label_font,
            fill=_Palette.LABEL, anchor="mm",
        )
    else:
        cy = y + h // 2
        _draw_stroked_text(draw, (cx, cy), text, ctx.font, color)


def _net_color(ctx: _RenderContext) -> tuple[int, int, int]:
    """Tint for the ΔHP-in cell, derived from the existing HPIS/DPIS thresholds.

    Mirrors `_tint_colors` so the net cell agrees with the HPS / DPIS cells:
    when HPS would tint green, net tints green; when DPIS would tint warm-
    orange, net tints warm-orange; otherwise default white.
    """
    snap = ctx.snapshot
    if snap.hps is None or snap.dpis is None:
        return _Palette.DEFAULT
    net = snap.hps - snap.dpis
    if net > ctx.hpis_green:
        return _Palette.GREEN_TINT
    if -net > ctx.dpis_yellow:
        return _Palette.YELLOW_TINT
    return _Palette.DEFAULT


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
    """Formatted value + render color for one cell at the current snapshot."""
    snap = ctx.snapshot
    if cell_id == "dps":
        return _format_rate(snap.dps), _dps_color(ctx)
    if cell_id == "dpis":
        return _format_rate(snap.dpis), _tint_colors(ctx)[1]
    if cell_id == "hps":
        return _format_rate(snap.hps), _tint_colors(ctx)[0]
    if cell_id == "hps-out":
        return _format_rate(snap.hps_out), _Palette.DEFAULT
    # net (ΔHP in) — signed HPS-in minus DPS-in, tinted to match the cells.
    net = snap.hps - snap.dpis if (snap.hps is not None and snap.dpis is not None) else None
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
    """Owns the per-pixel-alpha overlay surface for the Deeps cluster.

    Thin wrapper around `LayeredOverlay` — holds the per-snapshot state
    (current numbers, alarm flag, thresholds, layout, font, bg-opacity)
    and exposes a render closure to the engine. The panel's UI tick
    drives `paint(snapshot, now)` at ~10 Hz.
    """

    def __init__(
        self,
        root: tk.Misc,
        settings: dict,
        on_position_changed: Callable[[int, int, bool], None] | None = None,
    ) -> None:
        # Mutable state
        self._layout: str = settings.get("layout", "horizontal")
        self._x: int = int(settings.get("overlay_x", 0))
        self._y: int = int(settings.get("overlay_y", 50))
        self._positioned: bool = bool(settings.get("overlay_positioned", False))
        self._font_family: str = str(settings.get("overlay_font_family", "Segoe UI"))
        self._font_size: int = int(settings.get("overlay_font_size", _BASE_FONT_SIZE))
        self._bg_opacity: float = float(settings.get("overlay_bg_opacity", 0.0))

        self._alarm_threshold: float = 2000.0
        self._hpis_green: float = 50.0
        self._dpis_yellow: float = 300.0
        self._alarm_active: bool = False

        self._snapshot: MeterSnapshot = MeterSnapshot.empty()
        self._now: float = 0.0
        # User-selected subset of `ALL_CELL_IDS`. Defaults to all visible.
        raw_visible = settings.get("visible_cells", ALL_CELL_IDS)
        self._visible: frozenset[str] = frozenset(
            c for c in raw_visible if c in ALL_CELL_IDS
        )

        self._on_position_changed_external = on_position_changed

        # Compute initial pane size from the current layout + font.
        w, h = self._compute_size()

        self._engine = LayeredOverlay(
            root,
            render_callback=self._render,
            width=w,
            height=h,
        )
        self._engine.bind_drag_to_move(on_drag_end=self._on_drag_end)

        if self._positioned:
            self._engine.set_position(self._x, self._y)
        else:
            self._center_on_screen()

        self._engine.set_locked(bool(settings.get("overlay_locked", False)))

    # ------------------------------------------------------------------ #
    # Public API (mirrors the previous Toplevel-based shape)              #
    # ------------------------------------------------------------------ #

    def show(self) -> None:
        self._engine.show()

    def hide(self) -> None:
        self._engine.hide()

    def destroy(self) -> None:
        self._engine.destroy()

    def set_layout(self, layout: str) -> None:
        if layout not in ("horizontal", "vertical") or layout == self._layout:
            return
        self._layout = layout
        self._resize_for_current()

    def set_font(self, family: str, size: int) -> None:
        size = max(12, min(int(size), 48))
        if family == self._font_family and size == self._font_size:
            return
        self._font_family = family
        self._font_size = size
        self._resize_for_current()

    def set_bg_opacity(self, opacity: float) -> None:
        self._bg_opacity = max(0.0, min(float(opacity), 1.0))
        # No resize needed; next paint reflects the new alpha.

    def set_visible_cells(self, cells: list[str] | tuple[str, ...] | set[str]) -> None:
        """Set which cells are visible. Unknown IDs are ignored defensively."""
        new = frozenset(c for c in cells if c in ALL_CELL_IDS)
        if new == self._visible:
            return
        self._visible = new
        self._resize_for_current()

    def set_locked(self, locked: bool) -> None:
        self._engine.set_locked(locked)

    def is_locked(self) -> bool:
        return self._engine.is_locked()

    def update_thresholds(self, alarm: float, green: float, yellow: float) -> None:
        self._alarm_threshold = float(alarm)
        self._hpis_green = float(green)
        self._dpis_yellow = float(yellow)

    def update_alarm_active(self, active: bool) -> None:
        self._alarm_active = bool(active)

    def paint(self, snapshot: MeterSnapshot, now: float) -> None:
        """Called by the panel's tick. Snapshots the state, delegates to engine."""
        self._snapshot = snapshot
        self._now = now
        self._engine.paint()

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    def _font_scale(self) -> float:
        return self._font_size / _BASE_FONT_SIZE

    def _compute_size(self) -> tuple[int, int]:
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

    def _resize_for_current(self) -> None:
        w, h = self._compute_size()
        self._engine.set_size(w, h)
        # Re-apply position (set_size keeps it but be explicit).
        self._engine.set_position(self._x, self._y)
        # Trigger a repaint immediately if visible.
        try:
            self._engine.paint()
        except Exception:
            logger.debug("Repaint after resize raised", exc_info=True)

    def _center_on_screen(self) -> None:
        try:
            screen_w = self._engine.root.winfo_screenwidth()
        except tk.TclError:
            screen_w = 1920
        self._x = screen_w // 2 - self._engine.width // 2
        self._y = 50
        self._engine.set_position(self._x, self._y)

    def _on_drag_end(self, x: int, y: int) -> None:
        self._x = x
        self._y = y
        self._positioned = True
        if self._on_position_changed_external is not None:
            self._on_position_changed_external(x, y, True)

    # ------------------------------------------------------------------ #
    # The render callback — produces the bitmap                          #
    # ------------------------------------------------------------------ #

    def _render(self, width: int, height: int) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Bg backdrop — true per-pixel alpha, smooth across the 0.0-1.0 range.
        if self._bg_opacity > 0.0:
            alpha = round(self._bg_opacity * 255)
            draw.rectangle(
                (0, 0, width, height),
                fill=(*_BG_FILL_RGB, alpha),
            )

        # Build the render context once per frame.
        scale = self._font_scale()
        font = load_font(self._font_family, self._font_size, bold=True)
        label_size = max(6, round(_LABEL_FONT_SIZE * scale))
        label_font = load_font(self._font_family, label_size, bold=False)
        ctx = _RenderContext(
            snapshot=self._snapshot,
            now=self._now,
            font=font,
            label_font=label_font,
            alarm_active=self._alarm_active,
            alarm_threshold=self._alarm_threshold,
            hpis_green=self._hpis_green,
            dpis_yellow=self._dpis_yellow,
            scale=scale,
        )

        # Layout + paint each cell.
        if self._layout == "horizontal":
            self._render_horizontal(draw, width, height, ctx)
        else:
            self._render_vertical(draw, width, height, ctx)

        return image

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
