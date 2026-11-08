"""
KazBars — Target inspect panel dialog.

Extras-menu settings for the in-game target inspect panel (KazBarsInspect
stub): the build gate, the baked default position, its Size (a percent of the
profile's overlay size, hinted in pt) and the stat rows it shows. Reads/writes the profile document's `inspect` section (data
layer: `inspect.py`, rows from `inspect_catalog`; the store autosaves).
Positions are stored as fractions of the game resolution; the X/Y fields
display projected px at the current resolution (the grid editor convention).
The build bakes the values into the generated SWF. The shell is
`extras_dialog.ExtrasShell`. Functions take the KazBarsApp instance as first arg.

**Stat rows**: `Default` (rows absent: the Summary group, shown as Active) or
`Custom list` (that list pinned so it can be edited; any move made in Default
pins it too). Search and Group filter Available only; Active lists the rows as
the panel draws them, section by section in the catalog's group order, each
section in the user's order. Add puts a row last in its section; Move up/down
moves the selected rows within their section as a block.
"""

import tkinter as tk
from tkinter import ttk

from . import inspect_catalog as catalog
from .extras_dialog import ExtrasShell, raise_if_open
from .grid_model import get_game_resolution_or_default
from .inspect import validate_config
from .overlay_size import panel_fs
from .ui_forms import create_card, picker_list, position_fields, size_slider
from .ui_helpers import (
    BTN_MEDIUM,
    FONT_SMALL,
    INPUT_WIDTH_FILTER,
    INPUT_WIDTH_SEARCH,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import add_tooltip, app_toast

_WIDTH = 820
_HEIGHT = 700
_ROW_LIST_WIDTH = 34
_ROW_LIST_HEIGHT = 16


def _row_text(row):
    """A row as the lists show it: Armor, the protections, the chances and the
    taps exist in a PvE group and in PvP Combat, so the group goes with it."""
    return f"{row.label} · {row.group.label}"


def _selected(listbox, shown):
    """The keys of the list's selected rows (`shown` is what it lists)."""
    return [shown[i] for i in listbox.curselection()]


def open_inspect_dialog(app):
    """Open or focus the inspect-panel settings dialog (modal). On apply,
    persist the config — it takes effect in-game on the next Build & Install."""
    if raise_if_open(app.inspect_dialog):
        return app.inspect_dialog

    cfg = validate_config(app.profile_store.get_section('inspect'))
    game_w, game_h = get_game_resolution_or_default()
    shell = ExtrasShell(
        app, 'inspect_dialog', title="Inspect Target",
        tip="Your target's combat sheet, in-game. Apply, then Build & Install to see it.",
        gate_text="Include the Inspect Target in builds",
        gate_tip="Adds the Inspect Target to the in-game overlay: target "
                 "something and see its combat sheet — armor, protections, "
                 "crit, critigation and more, with a PvP tab on players.",
        enabled=cfg['enabled'], width=_WIDTH)
    dialog, content, enabled_var = shell.dialog, shell.content, shell.enabled_var
    sink: list = []  # descriptor labels collected from the gated rows

    top = ttk.Frame(content)
    top.pack(fill='x')

    pos_card = create_card(top, "Position")
    pos_card.pack(side='left', fill='both', expand=True, padx=(0, PAD_SMALL), pady=(0, PAD_ROW))
    pos_blurb = ttk.Label(
        pos_card,
        text="Where the panel first appears in-game. Drag its name\n"
             "strip to move it — the game remembers. X/Y here only\n"
             "seed a first-ever session.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
    pos_blurb.pack(anchor='w', pady=(0, PAD_XS))
    shell.dim(pos_blurb)
    pos_row = ttk.Frame(pos_card)
    pos_row.pack(anchor='w')
    x_spin, y_spin, read_pos = position_fields(pos_row, cfg['fx'], cfg['fy'], game_w, game_h,
                                               label_sink=sink)
    shell.gate(x_spin, y_spin)

    look_card = create_card(top, "Size")
    look_card.pack(side='left', fill='both', expand=True, pady=(0, PAD_ROW))
    size_row = ttk.Frame(look_card)
    size_row.pack(anchor='w')

    # ---- Stat rows ---------------------------------------------------------
    rows_card = create_card(content, "Stat rows")
    rows_card.pack(fill='both', expand=True, pady=(0, PAD_ROW))

    # The mode is the radio; `custom` is the user's list, kept across a
    # Default detour (the validator stores it in the panel's order).
    custom = list(cfg['rows']) if cfg['rows'] is not None else catalog.default_keys()
    mode_var = tk.StringVar(value='default' if cfg['rows'] is None else 'custom')

    def _active():
        return catalog.default_keys() if mode_var.get() == 'default' else list(custom)

    mode_row = ttk.Frame(rows_card)
    mode_row.pack(fill='x', pady=(0, PAD_XS))
    for text, value, tip in (
        ("Default", 'default', "The twelve Summary lines, as every new panel shows them"),
        ("Custom list", 'custom', "Pick the rows yourself, in your own order within each section"),
    ):
        rb = ttk.Radiobutton(mode_row, text=text, value=value, variable=mode_var,
                             command=lambda: _on_mode(), bootstyle='toolbutton')  # type: ignore[call-arg]
        rb.pack(side='left', padx=(0, PAD_XS))
        add_tooltip(rb, tip)
        shell.gate(rb)

    filter_row = ttk.Frame(rows_card)
    filter_row.pack(fill='x', pady=(0, PAD_XS))
    search_lbl = ttk.Label(filter_row, text="Search:")
    search_lbl.pack(side='left')
    sink.append(search_lbl)
    search_var = tk.StringVar()
    search_entry = ttk.Entry(filter_row, textvariable=search_var, width=INPUT_WIDTH_SEARCH)
    search_entry.pack(side='left', padx=PAD_SMALL)
    add_tooltip(search_entry, "Matches a row's name, group and the stat ids it reads (1382 finds Kills)")
    shell.gate(search_entry)
    group_lbl = ttk.Label(filter_row, text="Group:")
    group_lbl.pack(side='left', padx=(PAD_TAB, 0))
    sink.append(group_lbl)
    group_var = tk.StringVar(value="All")
    group_combo = ttk.Combobox(filter_row, textvariable=group_var, state='readonly',
                               values=["All"] + [g.label for g in catalog.Group],
                               width=INPUT_WIDTH_FILTER)
    group_combo.pack(side='left', padx=PAD_SMALL)
    shell.gate(group_combo, live='readonly')

    lists = ttk.Frame(rows_card)
    lists.pack(fill='both', expand=True)
    avail_frame, avail_list = picker_list(lists, "Available", _ROW_LIST_WIDTH, _ROW_LIST_HEIGHT,
                                          exportselection=False)
    avail_frame.pack(side='left', fill='both', expand=True, padx=(0, PAD_SMALL))
    buttons = ttk.Frame(lists)
    buttons.pack(side='left', padx=PAD_SMALL)
    active_frame, active_list = picker_list(lists, "Active", _ROW_LIST_WIDTH, _ROW_LIST_HEIGHT,
                                            exportselection=False)
    active_frame.pack(side='left', fill='both', expand=True, padx=(PAD_SMALL, 0))
    shown_avail: list[str] = []
    shown_active: list[str] = []

    status_lbl = ttk.Label(rows_card, font=FONT_SMALL, foreground=THEME_COLORS['muted'],
                           wraplength=_WIDTH - 60, justify='left')
    status_lbl.pack(fill='x', pady=(PAD_XS, 0))
    shell.dim(status_lbl)

    def _refresh_status(*_):
        active = _active()
        keys = _selected(avail_list, shown_avail) + _selected(active_list, shown_active)
        if len(keys) == 1:
            row = catalog.find(keys[0])
            parts = [row.note, row.kind.encoding_note.capitalize(), row.fresh.sentence,
                     "Reads " + ", ".join(str(i) for i in row.kind.needed_ids) + "."]
            status_lbl.configure(text="  ".join(p if p.endswith('.') else p + '.' for p in parts if p))
            return
        text = (f"{len(active)} of {len(catalog.ROWS)} rows selected." if active
                else "The panel will show its title line only.")
        if catalog.height_warning(catalog.select(active), panel_fs(shell.base, size_var.get())):
            text += " Taller than the game screen at this size."
        status_lbl.configure(text=text)

    def _refresh_lists(keep_active=()):
        active = _active()
        group = group_var.get()
        shown_avail[:] = [r.key for r in catalog.ROWS
                          if r.key not in active and (group == "All" or r.group.label == group)
                          and catalog.matches(r, search_var.get())]
        shown_active[:] = active
        avail_list.delete(0, 'end')
        for key in shown_avail:
            avail_list.insert('end', _row_text(catalog.find(key)))
        active_list.delete(0, 'end')
        for i, key in enumerate(shown_active):
            active_list.insert('end', _row_text(catalog.find(key)))
            if key in keep_active:
                active_list.selection_set(i)
        active_frame.configure(text=f"Active ({len(active)})")
        _refresh_status()

    def _set_rows(keys, keep_active=()):
        """A change to the list pins it as a Custom list."""
        custom[:] = keys
        mode_var.set('custom')
        _refresh_lists(keep_active)

    def _on_mode():
        # Custom list brings the user's list back; emptied, it starts from the Default sheet.
        if mode_var.get() == 'custom' and not custom:
            custom[:] = catalog.default_keys()
        _refresh_lists()

    def _add():
        keys = _selected(avail_list, shown_avail)
        if keys:
            _set_rows(catalog.add_keys(_active(), keys), keep_active=keys)

    def _remove():
        keys = _selected(active_list, shown_active)
        if keys:
            _set_rows([k for k in _active() if k not in keys])

    def _move(delta):
        keys = _selected(active_list, shown_active)
        if keys:
            _set_rows(catalog.move_keys(_active(), keys, delta), keep_active=keys)

    for text, command, style, pady in (
        ("Add >>", _add, 'info-outline', PAD_SMALL),
        ("<< Remove", _remove, 'info-outline', PAD_SMALL),
        ("Move up", lambda: _move(-1), 'info-outline', (PAD_TAB, PAD_SMALL)),
        ("Move down", lambda: _move(1), 'info-outline', PAD_SMALL),
        ("Add All", lambda: _set_rows([r.key for r in catalog.ROWS]), 'info-outline', (PAD_TAB, PAD_SMALL)),
        ("Clear", lambda: _set_rows([]), 'warning-outline', PAD_SMALL),
    ):
        btn = ttk.Button(buttons, text=text, command=command, width=BTN_MEDIUM,
                         bootstyle=style)  # type: ignore[call-arg]
        btn.pack(pady=pady)
        shell.gate(btn)
    # A disabled Listbox still fires its bindings: the master switch gates them.
    avail_list.bind('<Double-1>', lambda e: enabled_var.get() and _add())
    active_list.bind('<Double-1>', lambda e: enabled_var.get() and _remove())
    for lb in (avail_list, active_list):
        lb.bind('<<ListboxSelect>>', _refresh_status)
        shell.gate(lb)
    search_var.trace_add('write', lambda *_: _refresh_lists())
    group_combo.bind('<<ComboboxSelected>>', lambda e: _refresh_lists())

    size_scale, size_var = size_slider(
        size_row, shell.base, cfg['scale'],
        on_commit=_refresh_status,
        tooltip="Text size in game, 8-28 pt; the whole panel scales with it, collapsed "
                "bar included. Moves with the Overlay size on the Grids tab.",
        label_sink=sink)
    shell.gate(size_scale)

    shell.dim(*sink)
    _refresh_lists()
    shell.sync()

    def _apply():
        fx, fy = read_pos()
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'fx': fx,
            'fy': fy,
            'scale': size_var.get(),
            'rows': None if mode_var.get() == 'default' else custom,
        })
        app.profile_store.set_section('inspect', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg == cfg:
            app_toast(app, "No changes to apply", 'info')
        elif new_cfg['enabled']:
            app_toast(app, "Inspect Target saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Inspect Target off — next build removes it", 'info')
        dialog.destroy()

    shell.finish(_apply, _HEIGHT, enter_except=search_entry)
    return dialog
