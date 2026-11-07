"""
KazBars — Console dialog.

Extras-menu settings for the in-game Console (KazBarsConsole stub): the build
gate, its Size (a percent of the profile's overlay size, hinted in pt) and the
tabs it holds, in the strip's order. Reads/writes the profile document's
`console` section (data layer: `console.py`; the store autosaves). No position
fields: the console is placed in game, in preview mode. The build bakes the
values into the generated SWF. The shell is `extras_dialog.ExtrasShell`.
Functions take the KazBarsApp instance as first arg.

Tabs: one row per tab — the chosen ones first, in the strip's order, then the
others. Ticking a tab adds it after the chosen ones, unticking removes it;
the up/down buttons move a chosen tab past a chosen neighbour. With no tab
ticked the console does not ship.
"""

import tkinter as tk
from tkinter import ttk

from .console import TABS, ships, validate_config
from .extras_dialog import ExtrasShell, raise_if_open
from .overlay_size import panel_fs
from .ui_forms import create_card, size_slider
from .ui_helpers import FONT_SMALL, PAD_MICRO, PAD_ROW, PAD_XS, THEME_COLORS
from .ui_widgets import add_tooltip, app_toast

_WIDTH = 470
_HEIGHT = 380

# (label, what it logs) per tab.
_TAB_INFO = {
    'buffs': ("Buffs", "Every buff and debuff applied to you and your target, with its buff ID — "
                       "the ID you need to track something the database doesn't carry."),
    'casts': ("Casts", "Your and your target's casts as they end: finished, interrupted or lost, "
                       "and how long they took."),
}


def open_console_dialog(app):
    """Open or focus the Console settings dialog (modal). On apply, persist the
    config — it takes effect in-game on the next Build & Install."""
    if raise_if_open(app.console_dialog):
        return app.console_dialog

    cfg = validate_config(app.profile_store.get_section('console'))
    shell = ExtrasShell(
        app, 'console_dialog', title="Console",
        tip="Buff IDs and casts, logged in-game. Apply, then Build & Install to see it.",
        gate_text="Include the console in builds",
        gate_tip="Adds an in-game console of tabs to the overlay. Show or hide it from "
                 "the preview panel (Shift+Ctrl+Alt).",
        enabled=cfg['enabled'], width=_WIDTH)
    dialog, content, enabled_var = shell.dialog, shell.content, shell.enabled_var
    sink: list = []

    size_card = create_card(content, "Size")
    size_card.pack(fill='x', pady=(0, PAD_ROW))
    size_row = ttk.Frame(size_card)
    size_row.pack(anchor='w')
    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(shell.base, p)} pt text",
        tooltip="A percent of the overlay size (Overlay, top of the Grids tab).",
        label_sink=sink)
    shell.gate(size_scale)

    tabs_card = create_card(content, "Tabs")
    tabs_card.pack(fill='x', pady=(0, PAD_ROW))
    blurb = ttk.Label(tabs_card, text="In the console's strip order. With no tab ticked the "
                                      "console is not built.",
                      font=FONT_SMALL, foreground=THEME_COLORS['muted'])
    blurb.pack(anchor='w', pady=(0, PAD_XS))
    sink.append(blurb)
    rows_frame = ttk.Frame(tabs_card)
    rows_frame.pack(fill='x')
    chosen = list(cfg['tabs'])

    def _draw_rows():
        for w in rows_frame.winfo_children():
            w.destroy()
        on = enabled_var.get()
        order = chosen + [t for t in TABS if t not in chosen]
        for tab in order:
            label, tip = _TAB_INFO[tab]
            row = ttk.Frame(rows_frame)
            row.pack(fill='x', pady=PAD_MICRO)
            var = tk.BooleanVar(value=tab in chosen)
            cb = ttk.Checkbutton(row, text=label, variable=var,
                                 command=lambda t=tab, v=var: _on_tick(t, v.get()),
                                 state='normal' if on else 'disabled')
            cb.pack(side='left')
            add_tooltip(cb, tip)
            i = chosen.index(tab) if tab in chosen else -1
            for glyph, delta, hint in (("▼", 1, "Move down the strip"), ("▲", -1, "Move up the strip")):
                live = on and i >= 0 and 0 <= i + delta < len(chosen)
                btn = ttk.Button(row, text=glyph, width=2, bootstyle='secondary',  # type: ignore[call-arg]
                                 command=lambda t=tab, d=delta: _on_move(t, d),
                                 state='normal' if live else 'disabled')
                btn.pack(side='right', padx=(PAD_XS, 0))
                add_tooltip(btn, hint)

    def _on_tick(tab, ticked):
        # The row's var is set from `chosen` on every draw, so a click always flips it.
        if ticked:
            chosen.append(tab)
        else:
            chosen.remove(tab)
        _draw_rows()

    def _on_move(tab, delta):
        i = chosen.index(tab)
        chosen[i], chosen[i + delta] = chosen[i + delta], chosen[i]
        _draw_rows()

    shell.dim(*sink)
    shell.on_sync = lambda on: _draw_rows()
    shell.sync()

    def _apply():
        new_cfg = validate_config({'enabled': enabled_var.get(), 'scale': size_var.get(),
                                   'tabs': chosen})
        app.profile_store.set_section('console', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg == cfg:
            app_toast(app, "No changes to apply", 'info')
        elif ships(new_cfg):
            app_toast(app, "Console saved — Build & Install to apply", 'success')
        elif new_cfg['enabled']:
            app_toast(app, "Console has no tab — the next build leaves it out", 'warning')
        else:
            app_toast(app, "Console off — next build removes it", 'info')
        dialog.destroy()

    shell.finish(_apply, _HEIGHT)
    return dialog
