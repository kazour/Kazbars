"""
KazBars — Console dialog.

Extras-menu settings for the in-game Console (KazBarsConsole stub): the build
gate, its Size (a percent of the profile's overlay size, hinted in pt) and the
tabs it holds, in the strip's order. Reads/writes the profile document's
`console` section (data layer: `console.py`; the store autosaves). No position
fields: the console is placed in game, in preview mode. The build bakes the
values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

Tabs: one row per tab — the chosen ones first, in the strip's order, then the
others. Ticking a tab adds it after the chosen ones, unticking removes it;
the up/down buttons move a chosen tab past a chosen neighbour. With no tab
ticked the console does not ship.

Layout follows the Damage Numbers panel conventions: tip bar under the header,
a master gate row above titled cards, and every control greying with the gate.
"""

import tkinter as tk
from tkinter import ttk

from .console import TABS, validate_config
from .overlay_size import panel_fs
from .ui_forms import create_card, size_slider
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_MICRO,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

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
    existing = app.console_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.profile_store.get_section('console'))

    dialog = tk.Toplevel(app)
    app.console_dialog = dialog
    dialog.withdraw()
    dialog.title("Console")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Console", MODULE_COLORS['grids'], width=_WIDTH)
    create_tip_bar(dialog, "Buff IDs and casts, logged in-game. "
                           "Apply, then Build & Install to see it.")

    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the console in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb,
                "Adds an in-game console of tabs to the overlay. Show or hide it from "
                "the preview panel (Shift+Ctrl+Alt).")

    footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
    footer.pack(fill='x', side='bottom')
    content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
    content.pack(fill='both', expand=True)

    gated: list = []
    dim_labels: list[tuple[ttk.Label, str]] = []
    sink: list = []

    size_card = create_card(content, "Size")
    size_card.pack(fill='x', pady=(0, PAD_ROW))
    base = app.profile_store.get_section('overlay')['size']
    size_row = ttk.Frame(size_card)
    size_row.pack(anchor='w')
    size_scale, size_var, _ = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(base, p)} pt text",
        tooltip="A percent of the overlay size (Overlay, top of the Grids tab).",
        label_sink=sink)
    gated.append(size_scale)

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
        if ticked and tab not in chosen:
            chosen.append(tab)
        elif not ticked and tab in chosen:
            chosen.remove(tab)
        _draw_rows()

    def _on_move(tab, delta):
        i = chosen.index(tab)
        chosen[i], chosen[i + delta] = chosen[i + delta], chosen[i]
        _draw_rows()

    for lbl in sink:
        dim_labels.append((lbl, str(lbl.cget('foreground'))))

    def _sync_enabled(*_):
        on = enabled_var.get()
        for widget in gated:
            widget.configure(state='normal' if on else 'disabled')
        for lbl, normal_fg in dim_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])
        _draw_rows()

    enable_cb.configure(command=_sync_enabled)
    _sync_enabled()

    def _apply():
        new_cfg = validate_config({'enabled': enabled_var.get(), 'scale': size_var.get(),
                                   'tabs': chosen})
        app.profile_store.set_section('console', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg == cfg:
            app_toast(app, "No changes to apply", 'info')
        elif new_cfg['enabled'] and new_cfg['tabs']:
            app_toast(app, "Console saved — Build & Install to apply", 'success')
        elif new_cfg['enabled']:
            app_toast(app, "Console has no tab — the next build leaves it out", 'warning')
        else:
            app_toast(app, "Console off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

    restore_window_position(dialog, 'console_settings', _WIDTH, _HEIGHT, app,
                            resizable=False, offset=(60, 60))
    bind_window_position_save(dialog, 'console_settings', save_size=False)
    dialog.deiconify()

    dialog.bind("<Return>", lambda e: _apply())
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
