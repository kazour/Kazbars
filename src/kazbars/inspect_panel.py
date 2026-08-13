"""
KazBars — Target inspect panel dialog.

Extras-menu settings for the in-game target inspect panel (KazBarsInspect
stub): the build gate, the baked default position, the baked font size, and
the start-collapsed flag. It also hosts two settings that are not the inspect
panel's own, for the same "these belong together" reason: the buff-discovery
console's build gate (flat prefs key `build_console`), and the text size the
four in-game panels share (flat prefs key `panel_font_size`) — the console and
the preview control panel have no dialog of their own to host either.
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
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

_WIDTH = 400
_HEIGHT = 680


def open_inspect_dialog(app):
    """Open or focus the inspect-panel settings dialog (modal). On apply,
    persist the config — it takes effect in-game on the next Build & Install."""
    existing = app.inspect_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.settings.get('inspect'))

    dialog = tk.Toplevel(app)
    app.inspect_dialog = dialog
    dialog.withdraw()
    dialog.title("Inspect Panel")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Inspect Panel",
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
              text="Where the panel first appears in-game. Drag its name strip\n"
                   "to move it — the game remembers, across relogs and restarts.\n"
                   "X/Y here only seed a first-ever session.",
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
    ttk.Label(content,
              text="One size for all four in-game panels — stopwatch, inspect panel,\n"
                   "buff console and control panel. It's set here because the last two\n"
                   "have no dialog of their own.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left'
              ).pack(anchor='w', pady=(0, PAD_XS))

    shared_before = app.settings.get('panel_font_size')
    shared_var = tk.IntVar(value=shared_before)
    shared_row = ttk.Frame(content)
    shared_row.pack(anchor='w', pady=(0, PAD_XS))
    shared_spin = labeled_spinbox(shared_row, "All panels ", shared_var,
                                  from_=8, to=48, width=6)
    add_tooltip(shared_spin,
                "Each panel scales as one piece, collapsed bars included, so they "
                "keep matching at any size. Takes effect on the next "
                "Build & Install.")

    # fontSize is None when the panel follows the shared size. The spinbox still
    # shows a number so unticking the box has somewhere to start from.
    follow_var = tk.BooleanVar(value=cfg['fontSize'] is None)
    follow_cb = ttk.Checkbutton(content, text="Use the shared size for this panel",
                                variable=follow_var)
    follow_cb.pack(anchor='w', pady=(0, PAD_XS))
    add_tooltip(follow_cb,
                "Untick to make the inspect panel bigger or smaller than the rest.")

    size_var = tk.IntVar(value=shared_before if cfg['fontSize'] is None else cfg['fontSize'])
    size_row = ttk.Frame(content)
    size_row.pack(anchor='w', pady=(0, PAD_SMALL))
    size_spin = labeled_spinbox(size_row, "Inspect panel only ", size_var,
                                from_=8, to=48, width=6)
    add_tooltip(size_spin,
                "This panel's own size, used instead of the shared one. "
                "Takes effect on the next Build & Install.")

    def _sync_size_override(*_):
        size_spin.configure(state='disabled' if follow_var.get() else 'normal')

    follow_var.trace_add('write', _sync_size_override)
    _sync_size_override()

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

    ttk.Label(content, text="Console",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    console_var = tk.BooleanVar(value=bool(app.settings.get('build_console', False)))
    console_cb = ttk.Checkbutton(content, text="Include the buff-discovery console in builds",
                                 variable=console_var)
    console_cb.pack(anchor='w', pady=(0, PAD_SMALL))
    add_tooltip(console_cb,
                "Adds an in-game window that logs every buff and debuff on you "
                "and your target with its buff ID — the ID you need to track "
                "something the database doesn't carry. Opens in preview mode "
                "(Shift+Ctrl+Alt). Takes effect on the next Build & Install.")

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
        shared = _read(shared_var, shared_before)
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'x': _read(x_var, cfg['x']),
            'y': _read(y_var, cfg['y']),
            # Checked means "no opinion" — never the number left in the disabled
            # spinbox, or unticking once would freeze the panel off the shared value.
            'fontSize': None if follow_var.get() else _read(size_var, shared),
            'startCollapsed': collapsed_var.get(),
            'showPvp': pvp_var.get(),
            'showPerks': perks_var.get(),
        })
        # The shared size and the console gate ride along on the same Apply —
        # one save() covers all three keys.
        app.settings.set('panel_font_size', shared)
        app.settings.set('build_console', console_var.get())
        app.settings.set('inspect', new_cfg)
        app.settings.save()
        app.grids_panel.refresh_extras_shortcuts()
        # Three separate settings live in this dialog, so name whichever moved
        # rather than reporting an inspect save that isn't one.
        if new_cfg != cfg:
            if new_cfg['enabled']:
                app_toast(app, "Inspect panel saved — Build & Install to apply", 'success')
            else:
                app_toast(app, "Inspect panel off — next build removes it", 'info')
        elif shared != shared_before:
            app_toast(app, "Panel text size saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Console saved — Build & Install to apply", 'success')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    # withdraw → build → restore → deiconify, then keep the drag: the dialog
    # reopens where the user left it (clamped to a live monitor), like the
    # panels it configures. Staggered off the stopwatch dialog's first-launch
    # centre so opening both doesn't stack them exactly.
    restore_window_position(dialog, 'inspect_settings', _WIDTH, _HEIGHT, app,
                            resizable=False, offset=(30, 30))
    bind_window_position_save(dialog, 'inspect_settings', save_size=False)
    dialog.deiconify()

    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    # The global one-shot dark-titlebar patch can miss a Toplevel built this
    # late, so re-assert it on the dialog's own map (as damageinfo_colors_panel).
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
