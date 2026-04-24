"""
Kaz Grids — Raw tkinter widget styling.

Helpers that configure raw tk.* widgets (Listbox, Text, Canvas, Toplevel)
to match the darkly theme, since ttkbootstrap only styles ttk.* widgets.
"""

import tkinter as tk

from .ui_helpers import TK_COLORS


def style_tk_listbox(listbox):
    """Style a raw tk.Listbox to match the darkly theme."""
    listbox.configure(
        bg=TK_COLORS['input_bg'], fg=TK_COLORS['input_fg'],
        selectbackground=TK_COLORS['select_bg'], selectforeground=TK_COLORS['select_fg'],
        highlightbackground=TK_COLORS['border'], highlightcolor=TK_COLORS['border'])


def style_tk_text(text_widget):
    """Style a raw tk.Text widget to match the darkly theme."""
    text_widget.configure(
        bg=TK_COLORS['input_bg'], fg=TK_COLORS['input_fg'],
        insertbackground=TK_COLORS['input_fg'],
        selectbackground=TK_COLORS['select_bg'], selectforeground=TK_COLORS['select_fg'],
        highlightbackground=TK_COLORS['border'], highlightcolor=TK_COLORS['border'])


def style_tk_canvas(canvas):
    """Style a raw tk.Canvas to match the darkly theme."""
    canvas.configure(bg=TK_COLORS['bg'], highlightthickness=0)


def apply_dark_titlebar(window):
    """Apply dark title bar on Windows 11 via pywinstyles."""
    try:
        import pywinstyles
        pywinstyles.apply_style(window, 'dark')
        pywinstyles.change_header_color(window, TK_COLORS['bg'])
    except (ImportError, Exception):
        pass  # Silently skip if pywinstyles unavailable or not on Windows 11


def enable_global_dark_titlebar():
    """Monkey-patch tk.Toplevel so every popup gets a dark title bar automatically."""
    _original_init = tk.Toplevel.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        # Defer until window is mapped so the HWND exists
        def _apply(event=None):
            self.unbind('<Map>', _map_id[0])
            apply_dark_titlebar(self)
        _map_id = [self.bind('<Map>', _apply)]

    tk.Toplevel.__init__ = _patched_init
