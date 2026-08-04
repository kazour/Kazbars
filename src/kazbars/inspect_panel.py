"""
KazBars — Target inspect panel dialog.

Extras-menu settings for the in-game target inspect panel (KazBarsInspect
stub): the build gate, the baked default position, the baked font size, and
the start-collapsed flag.
Persists machine-local in prefs.json under `inspect` (data layer:
`inspect.py`); the build bakes the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .inspect import validate_config
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


def open_inspect_dialog(app):
    """Open or focus the inspect-panel settings dialog (modal). On apply,
    persist the config — it takes effect in-game on the next Build & Install."""
    existing = app.inspect_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.settings.get('inspect'))

    dialog = tk.Toplevel(app)
    app.inspect_dialog = dialog
    dialog.title("Target Inspect Panel")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    restore_window_position(dialog, 'inspect_settings', _WIDTH, 470, app, resizable=False)

    create_dialog_header(dialog, "Target Inspect Panel",
                         MODULE_COLORS['grids'], width=_WIDTH)

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    enable_cb = ttk.Checkbutton(content, text="Include the inspect panel in builds",
                                variable=enabled_var)
    enable_cb.pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    add_tooltip(enable_cb,
                "Adds a target inspect panel to the in-game overlay: target "
                "something and see its combat sheet — armor, protections, "
                "crit, critigation and more. Takes effect on the next "
                "Build & Install.")

    ttk.Label(content, text="Position",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    ttk.Label(content,
              text="Where the panel appears in-game. Dragging its name strip shows\n"
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

    ttk.Label(content, text="Text size",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    size_var = tk.IntVar(value=cfg['fontSize'])
    size_row = ttk.Frame(content)
    size_row.pack(anchor='w', pady=(0, PAD_SMALL))
    size_spin = labeled_spinbox(size_row, "Font size ", size_var, from_=8, to=48, width=6)
    add_tooltip(size_spin,
                "Baked at build time — the whole panel scales with it. "
                "Takes effect on the next Build & Install.")

    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(content, text="Start collapsed (name strip only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w', pady=(PAD_SMALL, PAD_SMALL))
    add_tooltip(collapsed_cb,
                "The panel loads folded to just its name strip — click its "
                "+ button in-game to expand.")

    ttk.Label(content, text="Sections",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    pvp_var = tk.BooleanVar(value=cfg['showPvp'])
    pvp_cb = ttk.Checkbutton(content, text="Show the PvP section",
                             variable=pvp_var)
    pvp_cb.pack(anchor='w', pady=(0, PAD_XS))
    add_tooltip(pvp_cb,
                "PvP armor, protections, spell damage, combat rating and "
                "kills / deaths — shown on player targets only. Takes "
                "effect on the next Build & Install.")
    perks_var = tk.BooleanVar(value=cfg['showPerks'])
    perks_cb = ttk.Checkbutton(content, text="Track slotted perks",
                               variable=perks_var)
    perks_cb.pack(anchor='w', pady=(0, PAD_SMALL))
    add_tooltip(perks_cb,
                "Adds a row of buff icons at the bottom of the panel showing "
                "the AA perks detected on a player target — each player can "
                "slot up to six. Takes effect on the next Build & Install.")

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
            'fontSize': _read(size_var, cfg['fontSize']),
            'startCollapsed': collapsed_var.get(),
            'showPvp': pvp_var.get(),
            'showPerks': perks_var.get(),
        })
        app.settings.set('inspect', new_cfg)
        app.settings.save()
        if new_cfg['enabled']:
            app_toast(app, "Inspect panel saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Inspect panel off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    return dialog
