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
    FONT_FORM_LABEL,
    FONT_SMALL,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    THEME_COLORS,
)
from .ui_widgets import CollapsibleSection, ColorSwatch, add_tooltip, labeled_spinbox

logger = logging.getLogger(__name__)

_DISPLAY_LABELS = [("Elapsed", "elapsed"), ("Total", "total"), ("Both", "both")]
_DISPLAY_TO_LABEL = {v: k for k, v in _DISPLAY_LABELS}
_LABEL_TO_DISPLAY = {k: v for k, v in _DISPLAY_LABELS}


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
        self.section = CollapsibleSection(
            self,
            "Cast Timer",
            accent_color=THEME_COLORS["accent"],
            initially_open=False,
            badge_text="overlay",
        )
        self.section.pack(fill="x")
        c = self.section.content

        intro = ttk.Label(
            c,
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
            text="Timer-only overlay (no bar) for cast time. Drag to position "
            "in-game (Shift+Ctrl+Alt); X/Y below are the baked default.",
        )
        intro.pack(anchor="w", pady=(0, PAD_ROW))

        self._player_row, self._player_xy = self._side_row(
            c, "Player", self.enable_p, self.px, self.py
        )
        self._target_row, self._target_xy = self._side_row(
            c, "Target", self.enable_t, self.tx, self.ty
        )

        ttk.Separator(c, orient="horizontal").pack(fill="x", pady=PAD_ROW)

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

    def _side_row(self, parent, label, enable_var, x_var, y_var):
        """Build one side's row: Enable toggle + X/Y entries. Returns
        (row_frame, [x_entry, y_entry]) so the entries can be enabled/disabled
        with the toggle."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=PAD_MICRO)
        ttk.Checkbutton(
            row,
            text=label,
            variable=enable_var,
            command=self._on_toggle,
            bootstyle="success-round-toggle",  # type: ignore[call-arg]
        ).pack(side="left")
        entries = []
        for lbl, var in (("X:", x_var), ("Y:", y_var)):
            entries.append(self._pos_entry(row, lbl, var))
        return row, entries

    def _pos_entry(self, parent, label, var):
        """Screen-pixel coordinate entry (spinbox stepping doesn't fit thousands
        of px), validated to int and clamped to screen bounds on focus-out."""
        hi = SCREEN_MAX_X if label == "X:" else SCREEN_MAX_Y
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL, foreground=THEME_COLORS["muted"]).pack(
            side="left", padx=(PAD_MID, 0)
        )
        vcmd = (self.register(self._validate_int), "%P")
        entry = ttk.Entry(
            parent, textvariable=var, width=5, justify="right", validate="key", validatecommand=vcmd
        )
        entry.pack(side="left", padx=(PAD_MICRO, 0))
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
        self.section.set_dimmed(not (self.enable_p.get() or self.enable_t.get()))

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
        p, t = self.enable_p.get(), self.enable_t.get()
        if p and t:
            self.section.set_summary("Player + Target")
        elif p:
            self.section.set_summary("Player")
        elif t:
            self.section.set_summary("Target")
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
