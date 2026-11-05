"""
KazBars — Game resolution dialog.

UI + persistence for the user's game resolution and the overhead anchor.
Positions are stored as fractions and sizes as a percent of the profile's
overlay size, so picking a new resolution changes nothing in the document —
the editor's pixel fields and the next build simply project against the new
size. The overhead anchor (where an overhead grid sits against a character's
reported point) depends on this PC's field of view, so it is a pref, never
profile data. Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import get_game_resolution_or_default, parse_resolution
from .prefs import ANCHOR_MAX, ANCHOR_MIN
from .ui_forms import position_entry
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
    """Open the modal resolution picker. On confirm, persist the resolution
    and the overhead anchor and rebuild the editor panels (positions are
    fractions and sizes a percent, so the document needs nothing)."""
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

    restore_window_position(dialog, 'game_resolution', 380, 330, app, resizable=False)

    create_dialog_header(dialog, "Game Resolution",
                         MODULE_COLORS['grids'], width=380)

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    ttk.Label(content, text="Resolution",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content,
              text="Grids keep their screen-relative positions and sizes.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted']
              ).pack(anchor='w', pady=(0, PAD_XS))

    res_var = tk.StringVar(value=current)
    res_combo = ttk.Combobox(content, textvariable=res_var, values=options,
                             width=14, font=FONT_BODY)
    res_combo.pack(anchor='w', pady=(0, PAD_SMALL))

    ttk.Label(content, text="Overhead anchor",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content,
              text="Where overhead grids sit against a character's head, in px at\n"
                   "a 1440 px tall screen per metre away. This PC only.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted']
              ).pack(anchor='w', pady=(0, PAD_XS))
    anchor_row = ttk.Frame(content)
    anchor_row.pack(anchor='w', pady=(0, PAD_SMALL))
    side_var = tk.StringVar(value=str(app.settings.get('anchor_side')))
    up_var = tk.StringVar(value=str(app.settings.get('anchor_up')))
    position_entry(anchor_row, "Right:", side_var, lo=ANCHOR_MIN, hi=ANCHOR_MAX,
                   tooltip="Positive moves overhead grids right, negative left",
                   label_color=THEME_COLORS['muted'], padx=(PAD_XS, PAD_TAB))
    position_entry(anchor_row, "Up:", up_var, lo=ANCHOR_MIN, hi=ANCHOR_MAX,
                   tooltip="Positive moves overhead grids up, negative down",
                   label_color=THEME_COLORS['muted'], padx=(PAD_XS, 0))

    btns = ttk.Frame(content)
    btns.pack(fill='x', pady=(PAD_SMALL, 0))

    def _apply():
        new_res = parse_resolution(res_var.get())
        if not new_res or min(new_res) <= 0:
            # Nothing is saved — the anchor waits for a resolution that reads.
            app_toast(app, "Type a resolution as width x height, like 2560x1440", 'warning')
            return
        anchor_changed = _apply_anchor(app, side_var.get(), up_var.get())
        new_w, new_h = new_res
        res_changed = (new_w, new_h) != (current_w, current_h)
        if res_changed:
            # Positions are fractions — nothing in the document moves. Flush
            # the widgets at the OLD resolution first (their px unprojects
            # against it), then persist and rebuild so every pixel field
            # re-projects at the new one.
            app.grids_panel.save_settings()
            app.settings.set('game_resolution', [new_w, new_h])
            app.settings.save()
            app.grids_panel.refresh_panels()
            app._on_grids_edited()
            # The installed SWF was baked at the old resolution — flip the
            # status row stale without touching the document.
            app.grids_panel.refresh_build_status()
        if res_changed and anchor_changed:
            app_toast(app, f"Resolution set to {new_w}×{new_h} and overhead anchor saved — "
                           "Build & Install to apply", 'info')
        elif res_changed:
            app_toast(app, f"Resolution set to {new_w}×{new_h}", 'info')
        elif anchor_changed:
            app_toast(app, "Overhead anchor saved — Build & Install to apply", 'info')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind('<Escape>', lambda e: dialog.destroy())
    dialog.bind('<Return>', lambda e: _apply())
    res_combo.focus_set()


def _apply_anchor(app, side_text, up_text):
    """Persist the overhead anchor fields (clamped like the pref). Returns
    whether either moved — a change owes a rebuild, which `_apply` says."""
    changed = False
    for key, text in (('anchor_side', side_text), ('anchor_up', up_text)):
        try:
            value = max(ANCHOR_MIN, min(int(text), ANCHOR_MAX))
        except ValueError:
            continue
        if value != app.settings.get(key):
            app.settings.set(key, value)
            changed = True
    if changed:
        app.settings.save()
        # The installed SWF was baked with the old anchor.
        app.grids_panel.refresh_build_status()
    return changed
