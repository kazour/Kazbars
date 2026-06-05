"""
KazBars — Cast Timer strip.

A frozen, collapsible card pinned above the grid list. Edits the cast-timer
overlay config (the timer-only Flash overlay for player/target cast time).
Collapsed and disabled by default — the master enable is off, so nothing is
compiled into the SWF until the user turns it on.

The header carries one master Enabled toggle plus title-adjacent Player/Target
status indicators; the body holds one settings row (independent Player/Target
X/Y plus the shared Bold / Size / Display / Color controls) and a sample preview.
Font is fixed to Arial (the only embedded face in base.swf; see cast_timer.py).
X/Y are baked into the build: on `/loadclip` default clients they are the only
positions that survive relaunch; aoc.exe clients additionally persist
preview-drag positions via the config archive (see cast_timer.py).
"""

import logging
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .cast_timer import (
    get_default_config,
    validate_config,
)
from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .ui_collapsible import CollapsibleSection
from .ui_forms import ColorSwatch, labeled_spinbox, position_entry
from .ui_helpers import (
    CAST_TIMER_ACCENT,
    FONT_BODY_LG,
    FONT_FORM_LABEL,
    FONT_SMALL,
    FONT_SYMBOL,
    GRID_PREVIEW_PX,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip

logger = logging.getLogger(__name__)

_DISPLAY_LABELS = [("Elapsed", "elapsed"), ("Total", "total"), ("Both", "both")]
_DISPLAY_TO_LABEL = {v: k for k, v in _DISPLAY_LABELS}
_LABEL_TO_DISPLAY = {k: v for k, v in _DISPLAY_LABELS}

# Grid cards reserve a × delete column right of their Enabled toggle and sit
# inside the scrolled list, losing the scrollbar gutter on the right; this pinned
# strip has neither. To land its Enabled toggle in the grid Enabled column, the
# header mirrors the grid's trailing structure: an invisible twin of the × column
# (an exact-spec ttk.Label, so the width tracks the real × instead of guessing it)
# plus this padding standing in for the scrollbar the grid loses. Eyeball-tuned;
# nudge if the toggle still drifts left/right of the grid toggles.
_SCROLLBAR_GUTTER_PX = 11

# Extra vertical padding on the (invisible) gutter so the collapsed strip matches
# the grid cards' taller headers. Eyeball-tuned; nudge if the heights drift.
_CARD_HEIGHT_PAD = 8


class CastTimerStrip(ttk.Frame):
    """Collapsible cast-timer config card. `on_modified` fires on any edit."""

    def __init__(self, parent, on_modified=None):
        super().__init__(parent)
        self.on_modified = on_modified
        self._loading = False
        self._color = get_default_config()["color"]

        self.enabled_var = tk.BooleanVar()
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
        # Bordered card, like a grid stripe — rose when the master enable is on,
        # neutral when off (matching the grid card's enabled/disabled border).
        # Content is inset by PAD_ROW so it doesn't touch the border.
        self._card = tk.Frame(
            self,
            highlightbackground=CAST_TIMER_ACCENT,
            highlightcolor=CAST_TIMER_ACCENT,
            highlightthickness=1,
        )
        self._card.pack(fill="x")

        # Reserve the gutter the grid cards spend on their ☰ reorder handle, so
        # this pinned strip's title lines up with the grid titles below. The
        # strip can't be reordered, so the slot stays empty: the same glyph + font
        # claims the identical width without hardcoding font metrics, rendered in
        # the card's own (live-read) colour so the glyph stays invisible whatever
        # the surface resolves to. `ipady` also lifts the collapsed card to the
        # grid cards' height (their headers are taller — button + spinboxes — than
        # this strip's toggle); the gutter spans fill="y" so the section centres.
        gutter = ttk.Label(self._card, text=" ☰ ", font=FONT_BODY_LG,
                           foreground=self._card.cget("background"))
        gutter.pack(side="left", fill="y", padx=(PAD_MICRO, 0), ipady=_CARD_HEIGHT_PAD)

        self.section = CollapsibleSection(
            self._card,
            "Cast Timer",
            initially_open=False,
        )
        self.section.pack(side="left", fill="x", expand=True,
                          padx=PAD_ROW, pady=(PAD_BUTTON_GAP, PAD_ROW))

        # Title-adjacent status: Player / Target light their grid-type colour
        # when that side is live, followed by a muted "overlay" tag — so which
        # sides are on reads at a glance without expanding. Clicking toggles the
        # card like the rest of the header. Identity colour also rides the border.
        # Anchor before the (empty, unused) summary frame so the tags sit flush
        # after the title; PAD_LF leading matches a grid card's title→badge gap.
        hl = self.section.header_left
        anchor = self.section.summary_frame
        self._ind_player = ttk.Label(hl, text="Player", font=FONT_SMALL)
        self._ind_player.pack(side="left", padx=(PAD_LF, 0), before=anchor)
        self._ind_target = ttk.Label(hl, text="Target", font=FONT_SMALL)
        self._ind_target.pack(side="left", padx=(PAD_MID, 0), before=anchor)
        overlay_tag = ttk.Label(hl, text="overlay", font=FONT_SMALL,
                                foreground=THEME_COLORS["muted"])
        overlay_tag.pack(side="left", padx=(PAD_LF, 0), before=anchor)
        for w in (self._ind_player, self._ind_target, overlay_tag):
            w.bind("<Button-1>", lambda e: self.section.toggle())

        # Master Enabled toggle in the right rail, like a grid card's. To land it
        # in the grid Enabled column, mirror the grid's trailing structure: an
        # invisible twin of the × delete column (same widget spec → same width as
        # the real ×) plus the scrollbar gutter the grid loses but this strip
        # doesn't. The twin is rendered in the card colour so it stays unseen.
        header = self.section.header_frame
        x_twin = ttk.Label(header, text="×", font=FONT_SYMBOL,
                           foreground=self._card.cget("background"),
                           padding=(PAD_XS, PAD_MICRO))
        x_twin.pack(side="right", padx=(PAD_XS, _SCROLLBAR_GUTTER_PX))
        ttk.Checkbutton(
            header,
            text="Enabled",
            variable=self.enabled_var,
            command=self._on_master_toggle,
            bootstyle="success-round-toggle",  # type: ignore[call-arg]
        ).pack(side="right", padx=(0, PAD_XS))

        # Content mirrors a grid card: settings on the left, a square preview on
        # the right. The preview shows a sample of the timer text in the chosen
        # colour/size/weight, so the card's right edge reads like the grid cards'
        # mini grid preview.
        c = self.section.content
        content_wrapper = ttk.Frame(c)
        content_wrapper.pack(fill="x")
        settings_col = ttk.Frame(content_wrapper)
        settings_col.pack(side="left", fill="x", expand=True)
        self._preview_canvas = tk.Canvas(
            content_wrapper, width=GRID_PREVIEW_PX, height=GRID_PREVIEW_PX,
            bg=TK_COLORS["bg"], highlightthickness=0,
        )
        self._preview_canvas.pack(side="right", padx=(PAD_XS, 0), pady=PAD_XS)

        # All settings on one row: independent Player / Target positions, then
        # the shared appearance controls. The master Enabled toggle (header)
        # turns both sides on together; X/Y grey out when it's off.
        row = ttk.Frame(settings_col)
        row.pack(fill="x")
        self._xy_entries = []
        for label, x_var, y_var in (
            ("Player", self.px, self.py),
            ("Target", self.tx, self.ty),
        ):
            ttk.Label(row, text=label, font=FONT_FORM_LABEL,
                      foreground=THEME_COLORS["muted"]).pack(side="left", padx=(0, PAD_XS))
            self._xy_entries += [
                position_entry(row, "X:", x_var, lo=0, hi=SCREEN_MAX_X,
                               label_color=THEME_COLORS["muted"], on_change=self._changed,
                               padx=(PAD_MICRO, PAD_MID)),
                position_entry(row, "Y:", y_var, lo=0, hi=SCREEN_MAX_Y,
                               label_color=THEME_COLORS["muted"], on_change=self._changed,
                               padx=(PAD_MICRO, PAD_LF)),
            ]

        ttk.Checkbutton(
            row, text="Bold", variable=self.bold_var, command=self._changed,
            bootstyle="success-round-toggle",  # type: ignore[call-arg]
        ).pack(side="left", padx=(0, PAD_MID))

        labeled_spinbox(
            row, "Size:", self.size_var, from_=8, to=48, width=3,
            tooltip="Timer text size in pixels (8-48)", on_change=self._changed,
            label_color=THEME_COLORS["muted"], padx=(0, PAD_MID),
        )

        ttk.Label(row, text="Show:", font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS["muted"]).pack(side="left")
        disp_cb = ttk.Combobox(
            row, textvariable=self.display_var,
            values=[lbl for lbl, _ in _DISPLAY_LABELS], state="readonly", width=8,
        )
        disp_cb.pack(side="left", padx=(PAD_MICRO, PAD_MID))
        disp_cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
        add_tooltip(
            disp_cb,
            "Elapsed = count up (1.2). Total = estimated cast length (2.5). Both = 1.2 / 2.5.",
        )

        ttk.Label(row, text="Color:", font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS["muted"]).pack(side="left")
        self._swatch = ColorSwatch(row, initial_color=f"#{self._color}", on_change=self._on_color)
        self._swatch.pack(side="left", padx=(PAD_MICRO, 0))
        add_tooltip(self._swatch, "Timer text color (click to change)")

        # Description sits at the bottom of the card, like a grid card's info line.
        ttk.Label(
            settings_col,
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
            text="Cast time for player/target. Drag in-game with Shift+Ctrl+Alt "
            "to reposition.",
        ).pack(anchor="w", pady=(PAD_ROW, 0))

    # --------------------------------------------------------------- handlers
    def _on_master_toggle(self):
        self._sync_enabled_state()
        self._changed()

    def _sync_enabled_state(self):
        """The master enable gates the strip: every X/Y is live only when it's
        on; the card border + title dim when it's off."""
        master = self.enabled_var.get()
        for entry in self._xy_entries:
            entry.configure(state="normal" if master else "disabled")
        self.section.set_dimmed(not master)
        # Border tracks the master: rose identity when on, neutral when off
        # (mirrors a grid card's enabled/disabled border).
        border = CAST_TIMER_ACCENT if master else TK_COLORS["border"]
        self._card.configure(highlightbackground=border, highlightcolor=border)
        self._update_indicators()

    def _on_color(self, hex_str):
        """ColorSwatch picked a color (#RRGGBB) — store as bare hex and mark dirty."""
        self._color = hex_str.lstrip("#").upper()
        self._changed()

    def _changed(self):
        if self._loading:
            return
        self._update_indicators()
        self._update_preview()
        if self.on_modified:
            self.on_modified()

    def _update_preview(self):
        """Draw a sample of the timer text in the chosen colour/size/weight.
        Arial mirrors the only face embedded in base.swf; the font shrinks to
        fit the square canvas so large sizes still read as a single sample."""
        canvas = self._preview_canvas
        canvas.delete("sample")
        disp = _LABEL_TO_DISPLAY.get(self.display_var.get(), "both")
        sample = {"elapsed": "1.2", "total": "2.5"}.get(disp, "1.2 / 2.5")
        try:
            size = int(self.size_var.get())
        except (ValueError, tk.TclError):
            size = 18
        font = tkfont.Font(family="Arial", size=size,
                           weight="bold" if self.bold_var.get() else "normal")
        while size > 7 and font.measure(sample) > GRID_PREVIEW_PX - 8:
            size -= 1
            font.configure(size=size)
        canvas.create_text(
            GRID_PREVIEW_PX // 2, GRID_PREVIEW_PX // 2,
            text=sample, fill=f"#{self._color}", font=font, anchor="center", tags="sample",
        )

    def _update_indicators(self):
        """Title-adjacent Player/Target tags light their grid-type colour
        (Player blue / Target orange) when the master is on — both sides run
        together — and grey when it's off. Matches the card colours below."""
        master = self.enabled_var.get()
        self._ind_player.configure(
            foreground=GRID_TYPE_COLORS["player"] if master else TK_COLORS["dim_text"])
        self._ind_target.configure(
            foreground=GRID_TYPE_COLORS["target"] if master else TK_COLORS["dim_text"])

    # ------------------------------------------------------------ config I/O
    def get_config(self):
        """Read widget state into a validated cast-timer config dict. The master
        Enabled toggle drives both sides together (enableP == enableT == enabled)."""
        enabled = self.enabled_var.get()
        return validate_config(
            {
                "enabled": enabled,
                "enableP": enabled,
                "enableT": enabled,
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
            self.enabled_var.set(cfg["enabled"])
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
            self._update_preview()
        finally:
            self._loading = False

    @staticmethod
    def _int(var):
        try:
            return int(var.get())
        except (ValueError, tk.TclError):
            return 0
