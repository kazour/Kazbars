"""
KazBars — CollapsibleSection widget.

A section with a clickable header (arrow + accent + title + badge) whose
content area toggles via pack/pack_forget. Used by the buff-display editor.
"""

import tkinter as tk
from tkinter import ttk

from .ui_helpers import (
    FONT_SECTION,
    FONT_SMALL,
    PAD_COLLAPSE_INDENT,
    PAD_LF,
    PAD_MID,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import blend_alpha


class CollapsibleSection(ttk.Frame):
    """A section with a clickable header that shows/hides its content.

    The header shows an arrow indicator, title text, and optional right-side
    widgets (passed via add_header_widget). The content frame is toggled
    via pack/pack_forget.

    Usage:
        section = CollapsibleSection(parent, "Grid Name", initially_open=True)
        section.pack(fill='x', pady=2)
        # Add widgets to section.header_frame (right side) and section.content
        ttk.Label(section.content, text="Settings go here").pack()
    """

    def __init__(
        self,
        parent,
        title="",
        accent_color=None,
        initially_open=False,
        badge_text=None,
        badge_color=None,
    ):
        """Initialize a collapsible section with a clickable header and togglable content area."""
        super().__init__(parent)
        self._is_open = initially_open

        # --- Header bar (always visible) ---
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x")

        # Clickable left side: arrow + accent + title + badge.
        # Exposed as `header_left` so callers can pack always-visible widgets
        # (e.g. status indicators) right after the title.
        left = ttk.Frame(self.header_frame)
        left.pack(side="left", fill="x", expand=True)
        self.header_left = left
        clickable = [left]

        arrow_text = "▼" if initially_open else "▶"
        self._arrow_label = ttk.Label(
            left, text=arrow_text, font=FONT_SMALL, foreground=THEME_COLORS["muted"], width=2
        )
        self._arrow_label.pack(side="left")
        clickable.append(self._arrow_label)

        if accent_color:
            tk.Canvas(
                left, width=3, height=16, highlightthickness=0, bg=accent_color
            ).pack(side="left", padx=(0, PAD_MID))

        self._title_label = ttk.Label(
            left, text=title, font=FONT_SECTION, foreground=THEME_COLORS["heading"]
        )
        self._title_label.pack(side="left")
        clickable.append(self._title_label)

        if badge_text:
            badge_label = ttk.Label(
                left,
                text=badge_text,
                font=FONT_SMALL,
                foreground=badge_color or THEME_COLORS["muted"],
            )
            badge_label.pack(side="left", padx=(PAD_LF, 0))
            clickable.append(badge_label)

        # Keyboard accessibility — left frame is focusable
        left.configure(takefocus=True)
        left.bind("<Return>", lambda e: self.toggle())
        left.bind("<space>", lambda e: self.toggle())

        def _on_focus_in(e):
            self._arrow_label.config(foreground=THEME_COLORS["accent"])
            self._title_label.config(foreground=THEME_COLORS["accent"])

        def _on_focus_out(e):
            self._arrow_label.config(foreground=THEME_COLORS["muted"])
            self._title_label.config(foreground=THEME_COLORS["heading"])

        left.bind("<FocusIn>", _on_focus_in)
        left.bind("<FocusOut>", _on_focus_out)

        # Bind click on all header elements
        for widget in clickable:
            widget.bind("<Button-1>", lambda e: self.toggle())

        # Hover highlight on the container frame — avoids flicker when
        # moving between child widgets by checking winfo_containing on Leave
        _left = left

        def _on_header_enter(e):
            self._arrow_label.config(foreground=THEME_COLORS["heading"])

        def _on_header_leave(e):
            try:
                w = _left.winfo_containing(e.x_root, e.y_root)
                while w is not None:
                    if w is _left:
                        return
                    w = getattr(w, "master", None)
            except (tk.TclError, RuntimeError):
                pass
            self._arrow_label.config(foreground=THEME_COLORS["muted"])

        _left.bind("<Enter>", _on_header_enter)
        _left.bind("<Leave>", _on_header_leave)

        # --- Content area (toggled) ---
        self._content_wrapper = ttk.Frame(self)
        if badge_color:
            tint = blend_alpha(badge_color, TK_COLORS["bg"], 8)
            style_name = f"Tint_{tint.replace('#', '')}.TFrame"
            ttk.Style().configure(style_name, background=tint)
            self.content = ttk.Frame(self._content_wrapper, style=style_name)
        else:
            self.content = ttk.Frame(self._content_wrapper)
        self.content.pack(side="left", fill="x", expand=True)
        if initially_open:
            self._content_wrapper.pack(fill="x", padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))

    def toggle(self):
        if self._is_open:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if not self._is_open:
            self._is_open = True
            self._arrow_label.config(text="▼")
            self._content_wrapper.pack(fill="x", padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))

    def collapse(self):
        if self._is_open:
            self._is_open = False
            self._arrow_label.config(text="▶")
            self._content_wrapper.pack_forget()

    @property
    def is_open(self):
        return self._is_open
