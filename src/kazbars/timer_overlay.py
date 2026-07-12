"""KazBars — Live Tracker overlay (a HudOverlay consumer).

The Ethram-Fal seed-timer overlay. Holds the current phase dict and draws the
two text rows + cycle-timer dock; the shared `overlay_engine.HudOverlay` owns
the backdrop, lock chrome, drag, focus-suppression, and position persistence
(over `LayeredOverlay`'s win32 per-pixel-alpha blit).

Visual structure:
  ┌────────────────────────────────────────────┐
  │ row1_msg row1_player              row1_timer│
  │ row2_msg row2_player              row2_timer│
  │ ──────────────────────────────────────────── │  ← 1 px separator (with bg)
  │ cycle_timer                            ●     │  ← lock dot (unlocked only)
  └────────────────────────────────────────────┘

`bg_opacity` (0.0-1.0) drives the alpha of the dark backdrop (drawn by
HudOverlay). Numbers and labels are always fully opaque with a dark stroke so
they stay crisp at any backdrop opacity.

Interactions (all via HudOverlay): drag to move; click the lock dot to lock
(while locked the overlay is click-through, so unlock from the panel button).
"""

from __future__ import annotations

import logging
import math
import tkinter as tk
from collections.abc import Callable

from PIL import ImageDraw, ImageFont

from .live_tracker_settings import (
    COLORS,
    TIMERS_DEFAULTS,
    overlay_config_from_timer,
    overlay_config_to_timer,
)
from .overlay_engine import HudOverlay, hex_to_rgb, load_font

logger = logging.getLogger(__name__)


# =========================================================================== #
# Visual constants                                                            #
# =========================================================================== #

_BG_BORDER_RGB = (51, 51, 51)           # 1 px row/dock separator (only with bg)
_STROKE_RGB = (10, 10, 10)              # text outline
_BODY_PAD = 5                           # inner left/right padding

MIN_WIDTH = 150

# Auto-size: width is the widest realistic phase line measured at the current
# font, so the overlay fits its content snugly and tracks the font size without
# jittering as the phase text changes. These are the longest strings the overlay
# actually renders; the seed sample bakes in a right-aligned timer after a name
# (`msg  …  timer`), so the measured width leaves room for both with a gap.
_WIDTH_SAMPLES = (
    "Bring Scorpion to the pile",
    "First Seed - Scorpion Soon",
    "Seed: Charactername   Done",
    "Kill Scorpion!!!   0s",
)


# --------------------------------------------------------------------------- #
# Sizing math — pure functions of the font (no display needed; unit-tested).  #
# --------------------------------------------------------------------------- #

def _timer_row_height(font_size: int) -> int:
    return max(font_size + 13, int(font_size * 1.8))


def _timer_cycle_height(font_size: int) -> int:
    return font_size + 14


def _timer_min_height(font_size: int) -> int:
    rows = 2 * _timer_row_height(font_size) + 6
    chrome = 8
    return _timer_cycle_height(font_size) + 1 + rows + chrome


def measure_timer_overlay(font_family: str, font_size: int) -> tuple[int, int]:
    """Font-derived (width, height) for the timer overlay. Deterministic — the
    width is a fixed glyph-column budget so it never jitters as the phase text
    changes; the height is the natural minimum for two rows + the cycle dock."""
    font = load_font(font_family, font_size, bold=True)
    try:
        ref_w = max(math.ceil(font.getlength(s)) for s in _WIDTH_SAMPLES)
    except Exception:
        ref_w = MIN_WIDTH
    width = max(MIN_WIDTH, ref_w + 2 * _BODY_PAD)
    return (width, _timer_min_height(font_size))


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

        # Geometry + appearance + lock live in the shared OverlayConfig. Size is
        # auto-derived from the font (`_measure`); the persisted width/height
        # keys are accepted on load but ignored (kept for back-compat).
        self._config = overlay_config_from_timer(settings)

        # Current display state — same dict shape the panel/boss_timer push.
        self._display_state: dict = {
            "row1_msg": "Waiting for Seed...",
            "row1_player": "", "row1_timer": "", "row1_color": COLORS["default"],
            "row2_msg": "", "row2_player": "", "row2_timer": "",
            "row2_color": COLORS["default"],
            "cycle_timer": "",
        }

        self._hud = HudOverlay(
            root, self._config,
            render_content=self._render_content,
            measure=self._measure,
            on_config_changed=self._on_hud_config_changed,
        )
        # Born hidden — visibility is panel-driven (Hide-on-Stop): Start/Test
        # shows it, Stop hides it. The persisted `visible` flag is not honored
        # on open (it would float the overlay before monitoring).

    # ------------------------------------------------------------------ #
    # Properties the panel reads as attributes                            #
    # ------------------------------------------------------------------ #

    @property
    def is_visible(self) -> bool:
        return self._hud.is_visible

    @property
    def is_locked(self) -> bool:
        return self._hud.is_locked()

    @property
    def bg_opacity(self) -> float:
        return self._config.bg_opacity

    @property
    def font_family(self) -> str:
        return self._config.font_family

    @property
    def font_size(self) -> int:
        return self._config.font_size

    # ------------------------------------------------------------------ #
    # Public API (preserved from the pre-port class)                      #
    # ------------------------------------------------------------------ #

    def update_display(self, state: dict) -> None:
        """Push a new phase dict from BossTimer. No-op when unchanged."""
        if state == self._display_state:
            return
        self._display_state = state
        self._hud.request_paint()

    def set_locked(self, locked: bool, notify: bool = True) -> None:
        if locked == self.is_locked:
            return
        self._hud.set_locked(locked)
        if notify:
            self._notify_settings_changed()

    def toggle_lock(self) -> None:
        self.set_locked(not self.is_locked)

    def set_bg_opacity(self, value: float, notify: bool = True) -> None:
        self._config.bg_opacity = max(0.0, min(float(value), 1.0))
        self._hud.request_paint()
        if notify:
            self._notify_settings_changed()

    def set_font(self, family: str, size: int, notify: bool = True) -> None:
        size = int(size)
        if family == self._config.font_family and size == self._config.font_size:
            return
        self._config.font_family = family
        self._config.font_size = size
        self._hud.resize()  # size is font-derived; re-measures for the new font
        if notify:
            self._notify_settings_changed()

    def set_font_size(self, size: int, notify: bool = True) -> None:
        """Backwards-compat — sets only the size, family unchanged."""
        self.set_font(self._config.font_family, size, notify=notify)

    def show(self, notify: bool = True) -> None:
        self._hud.show()
        if notify:
            self._notify_settings_changed()

    def hide(self, notify: bool = True) -> None:
        self._hud.hide()
        if notify:
            self._notify_settings_changed()

    def set_focus_suppressed(self, suppressed: bool) -> None:
        """Hide while neither KazBars nor the game is focused (driven by the
        shared ForegroundWatcher), without disturbing the user's visible pref."""
        self._hud.set_focus_suppressed(suppressed)

    def destroy(self) -> None:
        self._hud.destroy()

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
        # Visibility is not applied here — it follows Start/Stop (Hide-on-Stop),
        # not the persisted flag, so a profile load can't float a stopped overlay.
        self._hud.resize()  # size is font-derived; stored width/height ignored
        x = settings.get("x")
        y = settings.get("y")
        if x is not None and y is not None:
            self._hud.set_position(int(x), int(y))
        self._notify_settings_changed()

    def get_settings(self) -> dict:
        # Reflect the live wanted-visible state + a real placed position.
        self._config.visible = self._hud.is_visible
        self._config.positioned = True
        data = overlay_config_to_timer(self._config)
        w, h = self._measure()
        data["width"] = w
        data["height"] = h
        return data

    # ------------------------------------------------------------------ #
    # HudOverlay callback + geometry                                      #
    # ------------------------------------------------------------------ #

    def _on_hud_config_changed(self, _cfg) -> None:
        """Drag-end or lock-toggle from the overlay — persist via the panel."""
        self._notify_settings_changed()

    def _notify_settings_changed(self) -> None:
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    def _cycle_timer_height(self) -> int:
        return _timer_cycle_height(self._config.font_size)

    def _row_line_height(self) -> int:
        return _timer_row_height(self._config.font_size)

    def _measure(self) -> tuple[int, int]:
        return measure_timer_overlay(self._config.font_family, self._config.font_size)

    # ------------------------------------------------------------------ #
    # Content rendering (HudOverlay draws bg + lock dot)                  #
    # ------------------------------------------------------------------ #

    def _render_content(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        body_pad = _BODY_PAD
        row_h = self._row_line_height()
        cycle_h = self._cycle_timer_height()
        sep_y = height - cycle_h - 1
        row1_y = body_pad
        row2_y = row1_y + row_h

        msg_font = load_font(self._config.font_family, self._config.font_size, bold=True)
        timer_font = load_font(self._config.font_family, self._config.font_size + 4, bold=True)

        s = self._display_state

        self._draw_row(draw, row1_y, row_h, width,
                       s["row1_msg"], s["row1_player"], s["row1_timer"],
                       s["row1_color"], msg_font)
        self._draw_row(draw, row2_y, row_h, width,
                       s["row2_msg"], s["row2_player"], s["row2_timer"],
                       s["row2_color"], msg_font)

        # 1px separator above the cycle dock — only when there's a bg to be
        # separated from. With no bg, the stroked text doesn't need a divider.
        if self._config.bg_opacity > 0.0:
            alpha = round(self._config.bg_opacity * 255)
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
        body_pad = _BODY_PAD
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
        fill = (*hex_to_rgb(color), 255)
        draw.text(
            (x, y), text, font=font, fill=fill, anchor=anchor,
            stroke_width=1, stroke_fill=(*_STROKE_RGB, 255),
        )
        try:
            bbox = draw.textbbox((x, y), text, font=font, anchor=anchor)
            return int(max(0, bbox[2] - x))
        except Exception:
            return 0
