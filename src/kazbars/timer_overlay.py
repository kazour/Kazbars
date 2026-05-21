"""KazBars — Live Tracker overlay (PIL + win32 layered window).

The Ethram-Fal seed-timer overlay, rendered via the shared
`overlay_engine.LayeredOverlay`. Uses true per-pixel alpha for both
the bg fill and the text — bypassing Tk's `-alpha` /
`-transparentcolor` machinery which is broken on this Tk install.

Visual structure:
  ┌────────────────────────────────────────────┐
  │ row1_msg row1_player              row1_timer│
  │ row2_msg row2_player              row2_timer│
  │ ──────────────────────────────────────────── │  ← 1 px separator
  │ cycle_timer                       ●   ◢    │
  └────────────────────────────────────────────┘

`bg_opacity` (0.0-1.0) drives the alpha of the dark backdrop:

  - 0.0 → no backdrop, text floats over the game with a dark stroke for
    legibility.
  - 1.0 → solid dark panel.

Numbers and labels are always fully opaque so they stay crisp at any
backdrop opacity — same model as the Deeps overlay.

Lock indicator (○/●) and resize handle (◢) are drawn as PIL shapes
(circle, triangle) rather than as glyphs so they render consistently
regardless of which font is selected.

Interactions:
  - click on lock indicator → toggle lock (engine's set_locked toggles
    `WS_EX_TRANSPARENT` for OS-level click-through)
  - drag on resize handle → resize
  - drag anywhere else → move
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

from .live_tracker_settings import COLORS, TIMERS_DEFAULTS
from .overlay_engine import LayeredOverlay, load_font
from .ui_helpers import TK_COLORS

logger = logging.getLogger(__name__)


# =========================================================================== #
# Visual constants                                                            #
# =========================================================================== #

_BG_FILL_RGB = (10, 10, 10)             # near-black backdrop fill
_BG_BORDER_RGB = (51, 51, 51)           # 1 px frame border (only visible with bg)
_STROKE_RGB = (10, 10, 10)              # text outline
_CHROME_FG = TK_COLORS["border"]        # lock indicator + resize handle color

# Chrome hit-test rectangles in overlay-local coordinates.
_CHROME_HIT_W = 16
_CHROME_HIT_H = 16
_CHROME_PAD = 2

MIN_WIDTH = 150


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# =========================================================================== #
# TimerOverlay                                                                #
# =========================================================================== #

class TimerOverlay:
    """Live Tracker overlay. Public API matches the pre-port shape so
    `live_tracker_panel.py` doesn't need changes."""

    MIN_WIDTH = MIN_WIDTH

    def __init__(
        self,
        root: tk.Misc,
        settings: dict,
        on_settings_changed: Callable[[], None] | None = None,
    ) -> None:
        self._on_settings_changed = on_settings_changed

        # Persisted state
        self.is_visible: bool = settings.get("visible", TIMERS_DEFAULTS["visible"])
        self.bg_opacity: float = settings.get(
            "bg_opacity", TIMERS_DEFAULTS["bg_opacity"]
        )
        self.font_family: str = settings.get(
            "font_family", TIMERS_DEFAULTS["font_family"]
        )
        self.font_size: int = settings.get("font_size", TIMERS_DEFAULTS["font_size"])
        self.overlay_width: int = settings.get("width", TIMERS_DEFAULTS["width"])
        self.overlay_height: int = settings.get("height", TIMERS_DEFAULTS["height"])
        self.is_locked: bool = False  # set below via set_locked

        # Current display state — same dict shape the panel/boss_timer push.
        self._display_state: dict = {
            "row1_msg": "Waiting for Seed...",
            "row1_player": "", "row1_timer": "", "row1_color": COLORS["default"],
            "row2_msg": "", "row2_player": "", "row2_timer": "",
            "row2_color": COLORS["default"],
            "cycle_timer": "",
        }

        # Compute initial position (center on first run).
        x = settings.get("x", TIMERS_DEFAULTS["x"])
        y = settings.get("y", TIMERS_DEFAULTS["y"])
        if not settings.get("positioned", False):
            try:
                screen_w = root.winfo_screenwidth()
                x = screen_w // 2 - self.overlay_width // 2
            except tk.TclError:
                pass

        # Build the engine.
        self._engine = LayeredOverlay(
            root,
            render_callback=self._render,
            width=self.overlay_width,
            height=self.overlay_height,
        )
        self._engine.set_position(x, y)

        # Custom input — lock-click / resize / move dispatch.
        self._drag_mode: str | None = None  # None | "move" | "resize"
        self._drag_anchor_x = 0
        self._drag_anchor_y = 0
        self._drag_start_w = 0
        self._drag_start_h = 0
        self._engine.root.bind("<Button-1>", self._on_press)
        self._engine.root.bind("<B1-Motion>", self._on_drag)
        self._engine.root.bind("<ButtonRelease-1>", self._on_release)

        # Apply initial lock — set_locked is idempotent and configures click-through.
        self.set_locked(
            settings.get("locked", TIMERS_DEFAULTS["locked"]), notify=False,
        )

        # Visibility — hide() pushes a fully-transparent bitmap; show() repaints.
        if self.is_visible:
            self._engine.show()
        else:
            self._engine.hide()

    # ------------------------------------------------------------------ #
    # Public API (preserved from the pre-port class)                      #
    # ------------------------------------------------------------------ #

    def update_display(self, state: dict) -> None:
        """Push a new phase dict from BossTimer. No-op when unchanged."""
        if state == self._display_state:
            return
        self._display_state = state
        if self.is_visible:
            self._engine.paint()

    def set_locked(self, locked: bool, notify: bool = True) -> None:
        if locked == self.is_locked:
            return
        self.is_locked = bool(locked)
        self._engine.set_locked(self.is_locked)
        if self.is_visible:
            self._engine.paint()
        if notify:
            self._notify_settings_changed()

    def toggle_lock(self) -> None:
        self.set_locked(not self.is_locked)

    def set_bg_opacity(self, value: float, notify: bool = True) -> None:
        self.bg_opacity = max(0.0, min(float(value), 1.0))
        if self.is_visible:
            self._engine.paint()
        if notify:
            self._notify_settings_changed()

    # Backwards-compat alias — panel/profile-load code may still call
    # `set_opacity`. Forwards to the bg-opacity setter so old call sites
    # keep working without surprises.
    def set_opacity(self, value: float, notify: bool = True) -> None:
        self.set_bg_opacity(value, notify=notify)

    def set_font(self, family: str, size: int, notify: bool = True) -> None:
        size = int(size)
        if family == self.font_family and size == self.font_size:
            return
        self.font_family = family
        self.font_size = size
        # Re-clamp height in case the new font would push past the natural minimum.
        min_h = self._min_height()
        if self.overlay_height < min_h:
            self.overlay_height = min_h
            self._engine.set_size(self.overlay_width, self.overlay_height)
        if self.is_visible:
            self._engine.paint()
        if notify:
            self._notify_settings_changed()

    def set_font_size(self, size: int, notify: bool = True) -> None:
        """Backwards-compat — sets only the size, family unchanged."""
        self.set_font(self.font_family, size, notify=notify)

    def set_font_family(self, family: str, notify: bool = True) -> None:
        self.set_font(family, self.font_size, notify=notify)

    def show(self, notify: bool = True) -> None:
        self.is_visible = True
        self._engine.show()
        if notify:
            self._notify_settings_changed()

    def hide(self, notify: bool = True) -> None:
        self.is_visible = False
        self._engine.hide()
        if notify:
            self._notify_settings_changed()

    def destroy(self) -> None:
        self._engine.destroy()

    def apply_settings(self, settings: dict) -> None:
        """Bulk apply (used by profile load). Defers a single settings save."""
        self.set_bg_opacity(
            settings.get("bg_opacity", TIMERS_DEFAULTS["bg_opacity"]), notify=False,
        )
        self.set_font(
            settings.get("font_family", TIMERS_DEFAULTS["font_family"]),
            settings.get("font_size", TIMERS_DEFAULTS["font_size"]),
            notify=False,
        )
        self.set_locked(settings.get("locked", TIMERS_DEFAULTS["locked"]), notify=False)
        if settings.get("visible", TIMERS_DEFAULTS["visible"]):
            self.show(notify=False)
        else:
            self.hide(notify=False)
        x = settings.get("x")
        y = settings.get("y")
        width = max(self.MIN_WIDTH, settings.get("width", self.overlay_width))
        height = max(self._min_height(), settings.get("height", self.overlay_height))
        self.overlay_width = width
        self.overlay_height = height
        self._engine.set_size(width, height)
        if x is not None and y is not None:
            self._engine.set_position(int(x), int(y))
        if self.is_visible:
            self._engine.paint()
        self._notify_settings_changed()

    def get_settings(self) -> dict:
        return {
            "x": self._engine._x,
            "y": self._engine._y,
            "width": self.overlay_width,
            "height": self.overlay_height,
            "locked": self.is_locked,
            "bg_opacity": self.bg_opacity,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "visible": self.is_visible,
            "positioned": True,
        }

    # ------------------------------------------------------------------ #
    # Geometry helpers                                                    #
    # ------------------------------------------------------------------ #

    def _cycle_timer_height(self) -> int:
        return self.font_size + 14

    def _row_line_height(self) -> int:
        return max(self.font_size + 13, int(self.font_size * 1.8))

    def _min_height(self) -> int:
        rows = 2 * self._row_line_height() + 6
        chrome = 8
        return self._cycle_timer_height() + 1 + rows + chrome

    def _lock_bounds(self) -> tuple[int, int, int, int]:
        """(x1, y1, x2, y2) for the lock indicator hit zone."""
        w, h = self.overlay_width, self.overlay_height
        # Resize handle anchors bottom-right; lock sits to its left.
        x2 = w - _CHROME_PAD - _CHROME_HIT_W - _CHROME_PAD
        y2 = h - _CHROME_PAD
        return (x2 - _CHROME_HIT_W, y2 - _CHROME_HIT_H, x2, y2)

    def _resize_bounds(self) -> tuple[int, int, int, int]:
        w, h = self.overlay_width, self.overlay_height
        return (w - _CHROME_PAD - _CHROME_HIT_W, h - _CHROME_PAD - _CHROME_HIT_H,
                w - _CHROME_PAD, h - _CHROME_PAD)

    def _hit_test(self, x: int, y: int) -> str:
        """Map a click in overlay-local coordinates to an interaction zone."""
        if self.is_locked:
            return "none"
        lx1, ly1, lx2, ly2 = self._lock_bounds()
        if lx1 <= x <= lx2 and ly1 <= y <= ly2:
            return "lock"
        rx1, ry1, rx2, ry2 = self._resize_bounds()
        if rx1 <= x <= rx2 and ry1 <= y <= ry2:
            return "resize"
        return "move"

    # ------------------------------------------------------------------ #
    # Input handlers                                                      #
    # ------------------------------------------------------------------ #

    def _on_press(self, event: tk.Event) -> None:
        if self.is_locked:
            return
        local_x = event.x_root - self._engine._x
        local_y = event.y_root - self._engine._y
        zone = self._hit_test(local_x, local_y)
        if zone == "lock":
            self._drag_mode = None
            self.toggle_lock()
            return
        self._drag_mode = zone
        self._drag_anchor_x = event.x_root
        self._drag_anchor_y = event.y_root
        self._drag_start_w = self.overlay_width
        self._drag_start_h = self.overlay_height

    def _on_drag(self, event: tk.Event) -> None:
        if self.is_locked or self._drag_mode is None:
            return
        if self._drag_mode == "move":
            dx = event.x_root - self._drag_anchor_x
            dy = event.y_root - self._drag_anchor_y
            self._engine.set_position(self._engine._x + dx, self._engine._y + dy)
            self._drag_anchor_x = event.x_root
            self._drag_anchor_y = event.y_root
        elif self._drag_mode == "resize":
            dw = event.x_root - self._drag_anchor_x
            dh = event.y_root - self._drag_anchor_y
            new_w = max(self.MIN_WIDTH, self._drag_start_w + dw)
            new_h = max(self._min_height(), self._drag_start_h + dh)
            if (new_w, new_h) != (self.overlay_width, self.overlay_height):
                self.overlay_width = new_w
                self.overlay_height = new_h
                self._engine.set_size(new_w, new_h)
        if self.is_visible:
            self._engine.paint()

    def _on_release(self, _event: tk.Event) -> None:
        if self._drag_mode is None:
            return
        self._drag_mode = None
        self._notify_settings_changed()

    def _notify_settings_changed(self) -> None:
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    # ------------------------------------------------------------------ #
    # Render callback (PIL bitmap)                                        #
    # ------------------------------------------------------------------ #

    def _render(self, width: int, height: int) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # BG fill — bg_opacity drives the alpha of a near-black rectangle.
        # At 0.0 nothing is drawn; the dark stroke under each text glyph
        # carries legibility. At 1.0 the panel is fully opaque.
        if self.bg_opacity > 0.0:
            alpha = round(self.bg_opacity * 255)
            draw.rectangle((0, 0, width - 1, height - 1),
                           fill=(*_BG_FILL_RGB, alpha))
            # Hairline border at the same alpha — gives a subtle frame edge
            # without competing with the bg fill.
            draw.rectangle((0, 0, width - 1, height - 1),
                           outline=(*_BG_BORDER_RGB, alpha), width=1)

        # Layout dimensions (mirrors the pre-port _redraw_text_canvas math).
        body_pad = 5
        row_h = self._row_line_height()
        cycle_h = self._cycle_timer_height()
        sep_y = height - cycle_h - 1
        row1_y = body_pad
        row2_y = row1_y + row_h

        msg_font = load_font(self.font_family, self.font_size, bold=True)
        timer_font = load_font(self.font_family, self.font_size + 4, bold=True)

        s = self._display_state

        # Text rows
        self._draw_row(draw, row1_y, row_h, width,
                       s["row1_msg"], s["row1_player"], s["row1_timer"],
                       s["row1_color"], msg_font)
        self._draw_row(draw, row2_y, row_h, width,
                       s["row2_msg"], s["row2_player"], s["row2_timer"],
                       s["row2_color"], msg_font)

        # 1px separator above the cycle dock — only when there's a bg to be
        # separated from. With no bg, the stroked text doesn't need a divider.
        if self.bg_opacity > 0.0:
            alpha = round(self.bg_opacity * 255)
            draw.line(
                (body_pad, sep_y, width - body_pad - 1, sep_y),
                fill=(*_BG_BORDER_RGB, alpha), width=1,
            )

        # Cycle timer — left-aligned in the bottom dock.
        if s["cycle_timer"]:
            cy = sep_y + 1 + cycle_h // 2
            self._draw_text(
                draw, body_pad + 1, cy, s["cycle_timer"], COLORS["default"],
                timer_font, anchor="lm",
            )

        # Chrome — drawn as shapes so they're font-independent.
        self._draw_lock_indicator(draw)
        if not self.is_locked:
            self._draw_resize_handle(draw)

        return image

    def _draw_row(
        self,
        draw: ImageDraw.ImageDraw,
        y: int,
        row_h: int,
        width: int,
        msg: str,
        player: str,
        timer_text: str,
        color: str,
        font: ImageFont.ImageFont,
    ) -> None:
        body_pad = 5
        cy = y + row_h // 2
        if timer_text:
            self._draw_text(draw, width - body_pad - 1, cy, timer_text, color,
                            font, anchor="rm")
        if msg:
            msg_w = self._draw_text(
                draw, body_pad, cy, msg, color, font, anchor="lm",
            )
            if player:
                self._draw_text(
                    draw, body_pad + msg_w, cy, player, COLORS["player"],
                    font, anchor="lm",
                )
        elif player:
            self._draw_text(
                draw, body_pad, cy, player, COLORS["player"], font, anchor="lm",
            )

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        color: str,
        font: ImageFont.ImageFont,
        anchor: str = "la",
    ) -> int:
        """Draw text with an 8-direction dark stroke for legibility against
        arbitrary backdrops. Always strokes — at low bg opacity the stroke
        is what keeps text readable over game scenery; at high bg opacity
        the stroke is visually hidden against the dark panel so the cost is
        zero."""
        if not text:
            return 0
        fill = (*_hex_to_rgb(color), 255)
        draw.text(
            (x, y), text, font=font, fill=fill, anchor=anchor,
            stroke_width=1, stroke_fill=(*_STROKE_RGB, 255),
        )
        try:
            bbox = draw.textbbox((x, y), text, font=font, anchor=anchor)
            return max(0, bbox[2] - x)
        except Exception:
            return 0

    def _draw_lock_indicator(self, draw: ImageDraw.ImageDraw) -> None:
        """Outline circle (○) when unlocked, filled circle (●) when locked.

        Drawn as PIL shapes instead of Unicode glyphs so they render the
        same regardless of the selected font (some monospace fonts on
        Windows ship without ●/○ in their core glyph table).
        """
        x1, y1, x2, y2 = self._lock_bounds()
        # Center a 8x8 circle inside the hit rectangle.
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        r = 4
        fg = (*_hex_to_rgb(_CHROME_FG), 255)
        bbox = (cx - r, cy - r, cx + r, cy + r)
        if self.is_locked:
            draw.ellipse(bbox, fill=fg)
        else:
            draw.ellipse(bbox, outline=fg, width=1)

    def _draw_resize_handle(self, draw: ImageDraw.ImageDraw) -> None:
        """Lower-right diagonal triangle (◢) drawn as a polygon."""
        x1, y1, x2, y2 = self._resize_bounds()
        # Triangle filling the bottom-right corner of the hit rect.
        inset = 2
        fg = (*_hex_to_rgb(_CHROME_FG), 255)
        draw.polygon(
            [(x1 + inset, y2 - inset),
             (x2 - inset, y2 - inset),
             (x2 - inset, y1 + inset)],
            fill=fg,
        )
