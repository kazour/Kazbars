"""
KazBars — CRT-styled header builders.

The dialog/app header canvases (accent strip + scanlines + glow title) and the
compact single-line tip bar. Shared by every dialog, the main window, and the
config panels.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .ui_helpers import (
    FONT_DIALOG_HEADER,
    FONT_HEADING,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    PAD_TAB,
    PAD_TIP_BAR,
    SCANLINE_ALPHA,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import blend_alpha


def create_dialog_header(parent, title_text, accent_color, width=460, accent_segments=None):
    """CRT-styled header canvas strip for dialogs — matches BuildLoadingScreen aesthetic.

    Resize-aware: accent strip and scanlines stretch when the dialog is resizable.
    Fixed-width dialogs still work — initial draw uses the provided width.

    Args:
        parent: Parent frame/toplevel
        title_text: Title to display (will be wrapped in Unicode brackets)
        accent_color: Hex color string for accent strip (e.g. MODULE_COLORS['grids'])
        width: Canvas width in pixels
        accent_segments: Optional list of (text, color) drawn smaller (FONT_SMALL)
            to the right of the bracketed title — e.g. a "by <name>" credit.

    Returns:
        The canvas widget (already packed).
    """
    height = 50
    bg = TK_COLORS["status_bg"]  # #1a1a1a

    canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0, bg=bg)
    canvas.pack(fill="x")

    display_text = f"〔 {title_text} 〕"
    scanline_color = blend_alpha("#000000", bg, SCANLINE_ALPHA)
    glow_color = blend_alpha(accent_color, bg, 25)
    mid_glow = blend_alpha(accent_color, bg, 50)

    # Measure title + optional smaller accent suffix so the pair stays centered.
    _title_font = tkfont.Font(font=FONT_DIALOG_HEADER)
    _accent_font = tkfont.Font(font=FONT_SMALL)
    _title_w = _title_font.measure(display_text)
    _accent_gap = 8
    _accent_w = (
        _accent_gap + sum(_accent_font.measure(t) for t, _ in accent_segments)
        if accent_segments
        else 0
    )

    def _draw(w):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, 3, fill=accent_color, outline="")
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cy = height // 2 + 2
        left = w // 2 - (_title_w + _accent_w) // 2
        cx = left + _title_w // 2
        canvas.create_text(
            cx, cy, text=display_text, anchor="center", fill=glow_color, font=FONT_DIALOG_HEADER
        )
        canvas.create_text(
            cx, cy, text=display_text, anchor="center", fill=mid_glow, font=FONT_DIALOG_HEADER
        )
        canvas.create_text(
            cx,
            cy,
            text=display_text,
            anchor="center",
            fill=THEME_COLORS["heading"],
            font=FONT_DIALOG_HEADER,
        )
        if accent_segments:
            sx = left + _title_w + _accent_gap
            for _seg_text, _seg_fill in accent_segments:
                canvas.create_text(
                    sx, cy, text=_seg_text, anchor="w", fill=_seg_fill, font=FONT_SMALL
                )
                sx += _accent_font.measure(_seg_text)

    _draw(width)
    _dlg_after = [None]
    _dlg_last_w = [0]

    def _on_dlg_configure(e):
        if e.width <= 1 or e.width == _dlg_last_w[0]:
            return
        _dlg_last_w[0] = e.width
        if _dlg_after[0] is not None:
            try:
                canvas.after_cancel(_dlg_after[0])
            except (ValueError, tk.TclError):
                pass
        _dlg_after[0] = canvas.after(33, lambda w=e.width: _draw(w))

    canvas.bind("<Configure>", _on_dlg_configure)

    return canvas


def create_app_header(parent, title_text, accent_color):
    """CRT-styled header canvas for the main application window.

    Scaled-up variant of create_dialog_header: 4px accent strip (vs 3px),
    no bracket decoration, taller canvas, larger font.
    Resize-aware: accent strip and scanlines stretch on window resize.

    Args:
        parent: Parent frame/toplevel
        title_text: App name to display
        accent_color: Hex color string for accent strip

    Returns:
        The canvas widget (already packed).
    """
    height = 55
    bg = TK_COLORS["status_bg"]  # #1a1a1a

    canvas = tk.Canvas(parent, width=1, height=height, highlightthickness=0, bg=bg)
    canvas.pack(fill="x")

    scanline_color = blend_alpha("#000000", bg, SCANLINE_ALPHA)
    _state = {"accent": accent_color}

    def _draw(w, color=None):
        if color:
            _state["accent"] = color
        ac = _state["accent"]
        glow_color = blend_alpha(ac, bg, 25)
        mid_glow = blend_alpha(ac, bg, 50)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, 4, fill=ac, outline="")
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cx, cy = w // 2, height // 2 + 2
        canvas.create_text(
            cx, cy, text=title_text, anchor="center", fill=glow_color, font=FONT_HEADING
        )
        canvas.create_text(
            cx, cy, text=title_text, anchor="center", fill=mid_glow, font=FONT_HEADING
        )
        canvas.create_text(
            cx,
            cy,
            text=title_text,
            anchor="center",
            fill=THEME_COLORS["heading"],
            font=FONT_HEADING,
        )

    _header_last_w = [0]
    canvas._redraw = _draw
    canvas._last_w = _header_last_w

    def _on_header_configure(e):
        if e.width <= 1 or e.width == _header_last_w[0]:
            return
        _header_last_w[0] = e.width
        _draw(e.width)

    canvas.bind("<Configure>", _on_header_configure)

    return canvas


def update_app_header_color(canvas, new_color):
    """Update the app header accent strip and glow to a new color."""
    w = canvas._last_w[0] or canvas.winfo_width() or 900
    canvas._redraw(w, color=new_color)


def create_tip_bar(parent, text):
    """Create a compact single-line tip bar replacing verbose description boxes."""
    tip_frame = ttk.Frame(parent)
    tip_frame.pack(fill="x", padx=PAD_TAB, pady=PAD_TIP_BAR)
    ttk.Label(
        tip_frame, text="?", font=FONT_SMALL_BOLD, foreground=THEME_COLORS["accent"], width=2
    ).pack(side="left")
    ttk.Label(tip_frame, text=text, font=FONT_SMALL, foreground=THEME_COLORS["muted"]).pack(
        side="left", fill="x"
    )
    return tip_frame
