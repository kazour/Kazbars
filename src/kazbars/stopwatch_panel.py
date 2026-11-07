"""
KazBars — In-game stopwatch dialog.

Extras-menu settings for the in-game stopwatch panel (KazBarsStopwatch stub):
the build gate, the baked default position, its Size (a percent of the
profile's overlay size, hinted in pt) and the start-collapsed flag.
Reads/writes the profile document's `stopwatch` section (data layer:
`stopwatch.py`; the store autosaves). Positions are stored as fractions of the
game resolution; the X/Y fields display projected px at the current resolution
(the grid editor convention). The build bakes the values into the generated SWF.
The shell is `extras_dialog.ExtrasShell`.
Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from .extras_dialog import ExtrasShell, raise_if_open
from .grid_model import get_game_resolution_or_default
from .overlay_size import panel_fs
from .stopwatch import validate_config
from .ui_forms import create_card, position_fields, size_slider
from .ui_helpers import FONT_SMALL, PAD_ROW, PAD_XS, THEME_COLORS
from .ui_widgets import add_tooltip, app_toast

_WIDTH = 470
_HEIGHT = 380


def open_stopwatch_dialog(app):
    """Open or focus the stopwatch settings dialog (modal). On apply, persist
    the config — it takes effect in-game on the next Build & Install."""
    if raise_if_open(app.stopwatch_dialog):
        return app.stopwatch_dialog

    cfg = validate_config(app.profile_store.get_section('stopwatch'))
    game_w, game_h = get_game_resolution_or_default()
    shell = ExtrasShell(
        app, 'stopwatch_dialog', title="Stopwatch",
        tip="A Start / Pause / Reset stopwatch in-game. Apply, then Build & Install to see it.",
        gate_text="Include the stopwatch in builds",
        gate_tip="Adds a Start / Pause / Reset stopwatch panel to the in-game overlay.",
        enabled=cfg['enabled'], width=_WIDTH)
    dialog, content, enabled_var = shell.dialog, shell.content, shell.enabled_var
    sink: list = []  # descriptor labels collected from the gated rows

    pos_card = create_card(content, "Position")
    pos_card.pack(fill='x', pady=(0, PAD_ROW))
    pos_blurb = ttk.Label(
        pos_card,
        text="Where the panel first appears in-game. Drag its title bar\n"
             "to move it — the game remembers, across relogs and restarts.\n"
             "X/Y here only seed a first-ever session.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
    pos_blurb.pack(anchor='w', pady=(0, PAD_XS))
    shell.dim(pos_blurb)
    pos_row = ttk.Frame(pos_card)
    pos_row.pack(anchor='w')
    x_spin, y_spin, read_pos = position_fields(pos_row, cfg['fx'], cfg['fy'], game_w, game_h,
                                               label_sink=sink)
    shell.gate(x_spin, y_spin)

    size_card = create_card(content, "Size")
    size_card.pack(fill='x', pady=(0, PAD_ROW))
    size_row = ttk.Frame(size_card)
    size_row.pack(anchor='w')
    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(shell.base, p)} pt text",
        tooltip="A percent of the overlay size (Overlay, top of the Grids tab). "
                "The whole panel scales with it, collapsed bar included.",
        label_sink=sink)
    shell.gate(size_scale)

    behavior_card = create_card(content, "Behavior")
    behavior_card.pack(fill='x', pady=(0, PAD_ROW))
    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(behavior_card, text="Start collapsed (title bar only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w')
    add_tooltip(collapsed_cb,
                "The panel loads as just its title bar — click its + button "
                "in-game to expand.")
    shell.gate(collapsed_cb)

    shell.dim(*sink)
    shell.sync()

    def _apply():
        fx, fy = read_pos()
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'fx': fx,
            'fy': fy,
            'scale': size_var.get(),
            'startCollapsed': collapsed_var.get(),
        })
        app.profile_store.set_section('stopwatch', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg['enabled']:
            app_toast(app, "Stopwatch saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Stopwatch off — next build removes it", 'info')
        dialog.destroy()

    shell.finish(_apply, _HEIGHT)
    return dialog
