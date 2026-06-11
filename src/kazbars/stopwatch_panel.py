"""
KazBars — In-game stopwatch dialog.

Game-menu settings for the in-game stopwatch panel (KazBarsStopwatch stub):
the build gate, the baked default position, and the start-collapsed flag.
Persists machine-local in prefs.json under `stopwatch` (data layer:
`stopwatch.py`); the build bakes the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .stopwatch import validate_config
from .ui_forms import labeled_spinbox
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_SMALL,
    FONT_SECTION,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import add_tooltip, app_toast
from .window_position import restore_window_position

_WIDTH = 400


def open_stopwatch_dialog(app):
    """Open or focus the stopwatch settings dialog (modal). On apply, persist
    the config — it takes effect in-game on the next Build & Install."""
    existing = app.stopwatch_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.settings.get('stopwatch'))

    dialog = tk.Toplevel(app)
    app.stopwatch_dialog = dialog
    dialog.title("In-Game Stopwatch")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    restore_window_position(dialog, 'stopwatch_settings', _WIDTH, 330, app, resizable=False)

    create_dialog_header(dialog, "In-Game Stopwatch",
                         MODULE_COLORS['grids'], width=_WIDTH)

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    enable_cb = ttk.Checkbutton(content, text="Include the stopwatch in builds",
                                variable=enabled_var)
    enable_cb.pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    add_tooltip(enable_cb,
                "Adds a Start / Pause / Reset stopwatch panel to the in-game "
                "overlay. Takes effect on the next Build & Install.")

    ttk.Label(content, text="Position",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content,
              text="Where the panel appears in-game. Dragging its title bar shows\n"
                   "live coordinates — copy them here to make a spot permanent.\n"
                   "Aoc.exe clients remember drags automatically.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left'
              ).pack(anchor='w', pady=(0, PAD_XS))

    x_var = tk.IntVar(value=cfg['x'])
    y_var = tk.IntVar(value=cfg['y'])
    pos_row = ttk.Frame(content)
    pos_row.pack(anchor='w', pady=(0, PAD_SMALL))
    labeled_spinbox(pos_row, "X ", x_var, from_=0, to=SCREEN_MAX_X,
                    width=6, padx=(0, PAD_SMALL * 2))
    labeled_spinbox(pos_row, "Y ", y_var, from_=0, to=SCREEN_MAX_Y, width=6)

    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(content, text="Start collapsed (title bar only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w', pady=(0, PAD_SMALL))
    add_tooltip(collapsed_cb,
                "The panel loads as just its title bar — click its + button "
                "in-game to expand.")

    btns = ttk.Frame(content)
    btns.pack(fill='x', side='bottom', pady=(PAD_SMALL, 0))

    def _read(var, default):
        # An emptied spinbox makes IntVar.get() raise before validate_config
        # can clamp it — fall back to the loaded value.
        try:
            return var.get()
        except tk.TclError:
            return default

    def _apply():
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'x': _read(x_var, cfg['x']),
            'y': _read(y_var, cfg['y']),
            'startCollapsed': collapsed_var.get(),
        })
        app.settings.set('stopwatch', new_cfg)
        app.settings.save()
        if new_cfg['enabled']:
            app_toast(app, "Stopwatch saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Stopwatch off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    return dialog
