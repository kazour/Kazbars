"""
KazBars — Game resolution dialog.

UI + persistence for the user's game resolution. Positions are stored as
fractions, so picking a new resolution moves nothing in the document — the
editor's pixel fields and the next build simply project against the new
size. Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import get_game_resolution_or_default, parse_resolution
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_SMALL,
    FONT_BODY,
    FONT_SECTION,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import app_toast
from .window_position import restore_window_position

COMMON_RESOLUTIONS = ["1920x1080", "2560x1440", "3840x2160"]


def change_game_resolution(app):
    """Open the modal resolution picker. On confirm, anchor-scale all grids
    from the previous resolution to the new one, persist the setting, and
    rebuild the editor panels."""
    current_w, current_h = get_game_resolution_or_default()
    current = f"{current_w}x{current_h}"

    detected = f"{app.winfo_screenwidth()}x{app.winfo_screenheight()}"
    options = list(COMMON_RESOLUTIONS)
    if detected not in options:
        options.insert(0, detected)
    if current not in options:
        options.insert(0, current)

    dialog = tk.Toplevel(app)
    dialog.title("Game Resolution")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    restore_window_position(dialog, 'game_resolution', 380, 240, app, resizable=False)

    create_dialog_header(dialog, "Game Resolution",
                         MODULE_COLORS['grids'], width=380)

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    ttk.Label(content, text="Resolution",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content,
              text="Grids keep their screen-relative positions; the editor's\n"
                   "pixel fields re-read for the new size.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted']
              ).pack(anchor='w', pady=(0, PAD_XS))

    res_var = tk.StringVar(value=current)
    ttk.Combobox(content, textvariable=res_var, values=options,
                 width=14, font=FONT_BODY).pack(anchor='w', pady=(0, PAD_SMALL))

    btns = ttk.Frame(content)
    btns.pack(fill='x', pady=(PAD_SMALL, 0))

    def _apply():
        new_res = parse_resolution(res_var.get())
        if not new_res:
            dialog.destroy()
            return
        new_w, new_h = new_res
        if (new_w, new_h) != (current_w, current_h):
            # Positions are fractions — nothing in the document moves. Flush
            # the widgets at the OLD resolution first (their px unprojects
            # against it), then persist and rebuild so every pixel field
            # re-projects at the new one.
            app.grids_panel.save_settings()
            app.settings.set('game_resolution', [new_w, new_h])
            app.settings.save()
            app.grids_panel.refresh_panels()
            app_toast(app, f"Resolution set to {new_w}×{new_h}", 'info')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
