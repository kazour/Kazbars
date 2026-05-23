"""
KazBars — Cast Timer strip.

A frozen, collapsible card pinned above the grid list. Edits the cast-timer
overlay config (the timer-only Flash overlay for player/target cast time).
Collapsed and disabled by default — both timers off, so nothing is compiled
into the SWF until the user turns one on.

Per-side controls (Enable + X + Y) plus shared Bold / Size / Display / Color.
Font is fixed to Arial (the only embedded face in base.swf; see cast_timer.py).
X/Y are baked into the build: on `/loadclip` default clients they are the only
positions that survive relaunch; aoc.exe clients additionally persist
preview-drag positions via the config archive (see cast_timer.py).
"""

import logging
import tkinter as tk
from tkinter import ttk

from .cast_timer import (
    get_default_config,
    validate_config,
)
from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .ui_helpers import (
    CAST_TIMER_ACCENT,
    FONT_FORM_LABEL,
    FONT_SMALL,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import CollapsibleSection, ColorSwatch, add_tooltip, labeled_spinbox

logger = logging.getLogger(__name__)

_DISPLAY_LABELS = [("Elapsed", "elapsed"), ("Total", "total"), ("Both", "both")]
_DISPLAY_TO_LABEL = {v: k for k, v in _DISPLAY_LABELS}
_LABEL_TO_DISPLAY = {k: v for k, v in _DISPLAY_LABELS}

# Right inset that lands the Player X/Y + toggle in the same column as a grid
# stripe's X/Y + Enabled rail. With the matching card border + PAD_ROW content
# inset (see _build), this strip's content edge differs from a grid card's only
# by the scrollable list's scrollbar gutter (~16px); a grid card also reserves a
# × delete column (~25px) right of its Enabled toggle, which this strip has none
# of. Summed and applied as the Player toggle's right padding. Eyeball-tuned —
# nudge if the rails drift after a layout change.
_GRID_RAIL_INSET = 40


class CastTimerStrip(ttk.Frame):
    """Collapsible cast-timer config card. `on_modified` fires on any edit."""

    def __init__(self, parent, on_modified=None):
        super().__init__(parent)
        self.on_modified = on_modified
        self._loading = False
        self._color = get_default_config()["color"]

        self.enable_p = tk.BooleanVar()
        self.enable_t = tk.BooleanVar()
        self.px = tk.StringVar()
        self.py = tk.StringVar()
        self.tx = tk.StringVar()
        self.ty = tk.StringVar()
        self.bold_var = tk.BooleanVar()
        self.size_var = tk.IntVar()
        self.display_var = tk.StringVar()

        self._build()
        self.load_config(get_default_config())

    # ------------------------------------------------------------------ build
    def _build(self):
        # Bordered card, like a grid stripe — turquoise when a timer is on,
        # neutral when both are off (matching the grid card's enabled/disabled
        # border). Content is inset by PAD_ROW so it doesn't touch the border.
        self._card = tk.Frame(
            self,
            highlightbackground=CAST_TIMER_ACCENT,
            highlightcolor=CAST_TIMER_ACCENT,
            highlightthickness=1,
        )
        self._card.pack(fill="x")

        self.section = CollapsibleSection(
            self._card,
            "Cast Timer",
            accent_color=CAST_TIMER_ACCENT,
            initially_open=False,
            badge_text="overlay",  # stays muted — color lives on the strip + summary
        )
        self.section.pack(fill="x", padx=PAD_ROW, pady=(PAD_BUTTON_GAP, PAD_ROW))

        # Per-side enable + X/Y live in the always-visible header so positions
        # stay tweakable while the card is collapsed — same affordance as the
        # grid stripes. Shared appearance controls stay in the content area.
        self._build_header_controls(self.section.header_frame)

        c = self.section.content

        shared = ttk.Frame(c)
        shared.pack(fill="x")
        ttk.Checkbutton(
            shared,
            text="Bold",
            variable=self.bold_var,
            command=self._changed,
            bootstyle="success-round-toggle",  # type: ignore[call-arg]
        ).pack(side="left", padx=(0, PAD_MID))

        labeled_spinbox(
            shared,
            "Size:",
            self.size_var,
            from_=8,
            to=48,
            width=3,
            tooltip="Timer text size in pixels (8-48)",
            on_change=self._changed,
            label_color=THEME_COLORS["muted"],
            padx=(0, PAD_MID),
        )

        ttk.Label(
            shared, text="Show:", font=FONT_FORM_LABEL, foreground=THEME_COLORS["muted"]
        ).pack(side="left")
        disp_cb = ttk.Combobox(
            shared,
            textvariable=self.display_var,
            values=[lbl for lbl, _ in _DISPLAY_LABELS],
            state="readonly",
            width=8,
        )
        disp_cb.pack(side="left", padx=(PAD_MICRO, PAD_MID))
        disp_cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
        add_tooltip(
            disp_cb,
            "Elapsed = count up (1.2). Total = estimated cast length (2.5). Both = 1.2 / 2.5.",
        )

        ttk.Label(
            shared, text="Color:", font=FONT_FORM_LABEL, foreground=THEME_COLORS["muted"]
        ).pack(side="left")
        self._swatch = ColorSwatch(
            shared, initial_color=f"#{self._color}", on_change=self._on_color
        )
        self._swatch.pack(side="left", padx=(PAD_MICRO, 0))
        add_tooltip(self._swatch, "Timer text color (click to change)")

        # Description sits at the bottom of the card, like a grid card's info line.
        ttk.Label(
            c,
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
            text="Cast time for player/target. Drag in-game with Shift+Ctrl+Alt "
            "to reposition.",
        ).pack(anchor="w", pady=(PAD_ROW, 0))

    def _build_header_controls(self, header):
        """One-line right-rail in the always-visible header: per-side X/Y
        spinboxes + enable toggle. Player is rightmost (packed first) so it
        lands in the same column as a grid stripe's X/Y + Enabled toggle;
        Target sits to its left. So, left → right:
        Target X/Y · Target toggle · Player X/Y · Player toggle."""
        self._player_xy = self._side_controls(
            header, "Player", self.enable_p, self.px, self.py,
            trailing_pad=_GRID_RAIL_INSET,
        )
        self._target_xy = self._side_controls(
            header, "Target", self.enable_t, self.tx, self.ty,
            trailing_pad=PAD_LF,
        )

    def _side_controls(self, header, label, enable_var, x_var, y_var, trailing_pad):
        """Pack one side's X/Y spinboxes + enable toggle (right-aligned).
        Returns [x_entry, y_entry] so the toggle can grey them when off.
        Geometry mirrors the grid stripe's pos_frame + Enabled rail."""
        # width=7 pads "Player"/"Target" to the same field width as a grid
        # stripe's "Enabled" toggle, so the X/Y column to its left lines up too.
        ttk.Checkbutton(
            header,
            text=label,
            width=7,
            variable=enable_var,
            command=self._on_toggle,
            bootstyle="success-round-toggle",  # type: ignore[call-arg]
        ).pack(side="right", padx=(0, trailing_pad))
        pos = ttk.Frame(header)
        pos.pack(side="right", padx=(0, PAD_LF))
        return [self._pos_entry(pos, "X:", x_var), self._pos_entry(pos, "Y:", y_var)]

    def _pos_entry(self, parent, label, var):
        """Screen-pixel coordinate entry (spinbox stepping doesn't fit thousands
        of px), validated to int and clamped to screen bounds on focus-out.
        Padding mirrors the grid stripe's X/Y entries so the columns line up."""
        hi = SCREEN_MAX_X if label == "X:" else SCREEN_MAX_Y
        ttk.Label(
            parent, text=label, font=FONT_FORM_LABEL, foreground=THEME_COLORS["muted"]
        ).pack(side="left")
        vcmd = (self.register(self._validate_int), "%P")
        entry = ttk.Entry(
            parent, textvariable=var, width=5, justify="right", validate="key", validatecommand=vcmd
        )
        entry.pack(side="left", padx=(PAD_MICRO, PAD_MID) if label == "X:" else (PAD_MICRO, 0))
        entry.bind("<FocusOut>", lambda e, v=var, h=hi: self._clamp(v, h))
        return entry

    # --------------------------------------------------------------- handlers
    @staticmethod
    def _validate_int(value):
        if value in ("", "-"):
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False

    def _clamp(self, var, hi):
        try:
            v = int(var.get())
        except (ValueError, tk.TclError):
            v = 0
        var.set(str(max(0, min(v, hi))))
        self._changed()

    def _on_toggle(self):
        self._sync_enabled_state()
        self._changed()

    def _sync_enabled_state(self):
        """Grey out a side's X/Y when that side's timer is off, and dim the
        whole card when neither timer is on (the 'disabled' resting state)."""
        for entries, on in (
            (self._player_xy, self.enable_p.get()),
            (self._target_xy, self.enable_t.get()),
        ):
            for entry in entries:
                entry.configure(state="normal" if on else "disabled")
        any_on = self.enable_p.get() or self.enable_t.get()
        self.section.set_dimmed(not any_on)
        # Border tracks the dim state: turquoise identity when active, neutral
        # when both timers are off (mirrors a grid card's enabled/disabled border).
        border = CAST_TIMER_ACCENT if any_on else TK_COLORS["border"]
        self._card.configure(highlightbackground=border, highlightcolor=border)

    def _on_color(self, hex_str):
        """ColorSwatch picked a color (#RRGGBB) — store as bare hex and mark dirty."""
        self._color = hex_str.lstrip("#").upper()
        self._changed()

    def _changed(self):
        if self._loading:
            return
        self._update_summary()
        if self.on_modified:
            self.on_modified()

    def _update_summary(self):
        """Collapsed-state summary, each side tinted by its grid-type color
        (Player blue / Target orange) to match the cards below."""
        p, t = self.enable_p.get(), self.enable_t.get()
        pc, tc = GRID_TYPE_COLORS["player"], GRID_TYPE_COLORS["target"]
        if p and t:
            self.section.set_summary_segments([("Player", pc), (" + ", None), ("Target", tc)])
        elif p:
            self.section.set_summary_segments([("Player", pc)])
        elif t:
            self.section.set_summary_segments([("Target", tc)])
        else:
            self.section.set_summary("Off")

    # ------------------------------------------------------------ config I/O
    def get_config(self):
        """Read widget state into a validated cast-timer config dict."""
        return validate_config(
            {
                "enableP": self.enable_p.get(),
                "enableT": self.enable_t.get(),
                "playerX": self._int(self.px),
                "playerY": self._int(self.py),
                "targetX": self._int(self.tx),
                "targetY": self._int(self.ty),
                "bold": self.bold_var.get(),
                "fontSize": self.size_var.get(),
                "display": _LABEL_TO_DISPLAY.get(self.display_var.get(), "both"),
                "color": self._color,
            }
        )

    def load_config(self, config):
        """Load a (validated) cast-timer config into the widgets. Suppresses
        the modified callback so loading a profile doesn't flag it dirty."""
        cfg = validate_config(config)
        self._loading = True
        try:
            self.enable_p.set(cfg["enableP"])
            self.enable_t.set(cfg["enableT"])
            self.px.set(str(cfg["playerX"]))
            self.py.set(str(cfg["playerY"]))
            self.tx.set(str(cfg["targetX"]))
            self.ty.set(str(cfg["targetY"]))
            self.bold_var.set(cfg["bold"])
            self.size_var.set(cfg["fontSize"])
            self.display_var.set(_DISPLAY_TO_LABEL.get(cfg["display"], "Both"))
            self._color = cfg["color"]
            self._swatch.set_color(f"#{self._color}")
            self._sync_enabled_state()
            self._update_summary()
        finally:
            self._loading = False

    @staticmethod
    def _int(var):
        try:
            return int(var.get())
        except (ValueError, tk.TclError):
            return 0
