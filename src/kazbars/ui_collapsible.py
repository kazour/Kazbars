"""
KazBars — CollapsibleSection widget.

A section with a clickable header (arrow + title) whose content area toggles
via pack/pack_forget. Used by the buff-display editor.
"""

from tkinter import ttk

from .ui_helpers import FONT_SECTION, FONT_SMALL, PAD_COLLAPSE_INDENT, PAD_XS, THEME_COLORS
from .ui_widgets import pointer_inside


class CollapsibleSection(ttk.Frame):
    """A section with a clickable header that shows/hides its content.

    The header shows an arrow indicator and the title; the content frame is
    toggled via pack/pack_forget.

    Usage:
        section = CollapsibleSection(parent, "Grid Name", initially_open=True)
        section.pack(fill='x', pady=2)
        # Add widgets to section.header_frame (right side) and section.content
        ttk.Label(section.content, text="Settings go here").pack()
    """

    def __init__(self, parent, title="", initially_open=False):
        """Initialize a collapsible section with a clickable header and togglable content area."""
        super().__init__(parent)
        self._is_open = initially_open

        # --- Header bar (always visible) ---
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x")

        # Clickable left side: arrow + title. Exposed as `header_left` so
        # callers can pack always-visible widgets (e.g. status indicators)
        # right after the title.
        left = ttk.Frame(self.header_frame)
        left.pack(side="left", fill="x", expand=True)
        self.header_left = left

        arrow_text = "▼" if initially_open else "▶"
        self._arrow_label = ttk.Label(
            left, text=arrow_text, font=FONT_SMALL, foreground=THEME_COLORS["muted"], width=2
        )
        self._arrow_label.pack(side="left")

        self._title_label = ttk.Label(
            left, text=title, font=FONT_SECTION, foreground=THEME_COLORS["heading"]
        )
        self._title_label.pack(side="left")

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
        for widget in (left, self._arrow_label, self._title_label):
            widget.bind("<Button-1>", lambda e: self.toggle())

        # Hover highlight on the container frame — a Leave onto a child
        # widget is no leave, so the arrow never flickers.
        def _on_header_leave(e):
            if not pointer_inside(left, e):
                self._arrow_label.config(foreground=THEME_COLORS["muted"])

        left.bind("<Enter>", lambda e: self._arrow_label.config(foreground=THEME_COLORS["heading"]))
        left.bind("<Leave>", _on_header_leave)

        # --- Content area (toggled) ---
        self._content_wrapper = ttk.Frame(self)
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
