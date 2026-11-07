"""
KazBars — Target inspect panel dialog.

Extras-menu settings for the in-game target inspect panel (KazBarsInspect
stub): the build gate, the baked default position, its Size (a percent of the
profile's overlay size, hinted in pt), the start-collapsed flag, and the stat
rows it shows. Reads/writes the profile document's `inspect` section (data
layer: `inspect.py`, rows from `inspect_catalog`; the store autosaves).
Positions are stored as fractions of the game resolution; the X/Y fields
display projected px at the current resolution (the grid editor convention).
The build bakes the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

**Stat rows**: `Default` (rows absent: the Summary group, shown as Active) or
`Custom list` (that list pinned so it can be edited; any move made in Default
pins it too). Search and Group filter Available only; Active lists the rows as
the panel draws them, section by section in the catalog's group order, each
section in the user's order. Add puts a row last in its section; Move up/down
moves the selected rows within their section as a block.

Layout follows the Damage Numbers panel conventions: tip bar under the header,
a master gate row above titled cards, and every control greying with the gate.
"""

import tkinter as tk
from tkinter import ttk

from . import inspect_catalog as catalog
from .grid_model import get_game_resolution_or_default, project_px, unproject_px
from .inspect import validate_config
from .overlay_size import panel_fs
from .ui_forms import create_card, labeled_spinbox, size_slider
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    BTN_MEDIUM,
    FONT_SMALL,
    INPUT_WIDTH_FILTER,
    INPUT_WIDTH_SEARCH,
    MODULE_COLORS,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar, style_tk_listbox
from .ui_widgets import add_tooltip, app_toast
from .window_position import center_on_parent

_WIDTH = 820
_HEIGHT = 700
_ROW_LIST_WIDTH = 34
_ROW_LIST_HEIGHT = 16


def _row_text(row):
    """A row as the lists show it: Armor, the protections, the chances and the
    taps exist in a PvE group and in PvP Combat, so the group goes with it."""
    return f"{row.label} · {row.group.label}"


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

    cfg = validate_config(app.profile_store.get_section('inspect'))
    game_w, game_h = get_game_resolution_or_default()

    dialog = tk.Toplevel(app)
    app.inspect_dialog = dialog
    dialog.withdraw()
    dialog.title("Inspect Panel")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Inspect Panel",
                         MODULE_COLORS['grids'], width=_WIDTH)
    create_tip_bar(dialog, "Your target's combat sheet, in-game. "
                           "Apply, then Build & Install to see it.")

    # Master gate row above the cards; everything below greys when it's off.
    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the inspect panel in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb,
                "Adds a target inspect panel to the in-game overlay: target "
                "something and see its combat sheet — armor, protections, "
                "crit, critigation and more, with a PvP tab on players.")

    # Footer first so it reserves height before the cards claim the rest.
    footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
    footer.pack(fill='x', side='bottom')

    content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
    content.pack(fill='both', expand=True)

    # Everything registered here greys in step with the master gate — controls
    # by ttk state, static text by foreground — so a disabled panel reads
    # fully-off, not half-on (the Damage Numbers convention).
    gated: list = []
    dim_labels: list[tuple[ttk.Label, str]] = []
    sink: list = []  # descriptor labels collected from gated rows

    def _register_dim(*labels):
        for lbl in labels:
            dim_labels.append((lbl, str(lbl.cget('foreground'))))

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
    _register_dim(pos_blurb)

    # Fractions display as projected px at the current game resolution.
    x_var = tk.IntVar(value=project_px(cfg['fx'], game_w))
    y_var = tk.IntVar(value=project_px(cfg['fy'], game_h))
    pos_row = ttk.Frame(pos_card)
    pos_row.pack(anchor='w')
    gated.append(labeled_spinbox(pos_row, "X ", x_var, from_=0, to=game_w,
                                 width=6, padx=(0, PAD_SMALL * 2), label_sink=sink))
    gated.append(labeled_spinbox(pos_row, "Y ", y_var, from_=0, to=game_h,
                                 width=6, label_sink=sink))

    look_card = create_card(top, "Size")
    look_card.pack(side='left', fill='both', expand=True, pady=(0, PAD_ROW))
    base = app.profile_store.get_section('overlay')['size']
    size_row = ttk.Frame(look_card)
    size_row.pack(anchor='w')

    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(look_card, text="Start collapsed (name strip only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w', pady=(PAD_SMALL, 0))
    add_tooltip(collapsed_cb,
                "The panel loads folded to just its name strip — click its "
                "+ button in-game to expand.")
    gated.append(collapsed_cb)

    # ---- Stat rows ---------------------------------------------------------
    rows_card = create_card(content, "Stat rows")
    rows_card.pack(fill='both', expand=True, pady=(0, PAD_ROW))

    # None: the Default sheet. A list: the user's rows, kept in panel order.
    state = {'rows': None if cfg['rows'] is None else [r.key for r in catalog.select(cfg['rows'])]}
    mode_var = tk.StringVar(value='default' if state['rows'] is None else 'custom')

    def _active():
        return catalog.default_keys() if state['rows'] is None else list(state['rows'])

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
        gated.append(rb)

    filter_row = ttk.Frame(rows_card)
    filter_row.pack(fill='x', pady=(0, PAD_XS))
    search_lbl = ttk.Label(filter_row, text="Search:")
    search_lbl.pack(side='left')
    sink.append(search_lbl)
    search_var = tk.StringVar()
    search_entry = ttk.Entry(filter_row, textvariable=search_var, width=INPUT_WIDTH_SEARCH)
    search_entry.pack(side='left', padx=PAD_SMALL)
    add_tooltip(search_entry, "Matches a row's name, group and the stat ids it reads (1382 finds Kills)")
    gated.append(search_entry)
    group_lbl = ttk.Label(filter_row, text="Group:")
    group_lbl.pack(side='left', padx=(PAD_TAB, 0))
    sink.append(group_lbl)
    group_var = tk.StringVar(value="All")
    group_combo = ttk.Combobox(filter_row, textvariable=group_var, state='readonly',
                               values=["All"] + [g.label for g in catalog.Group],
                               width=INPUT_WIDTH_FILTER)
    group_combo.pack(side='left', padx=PAD_SMALL)

    lists = ttk.Frame(rows_card)
    lists.pack(fill='both', expand=True)

    def _make_list(label):
        frame = ttk.LabelFrame(lists, text=label, padding=PAD_SMALL)
        scroll = ttk.Scrollbar(frame)
        scroll.pack(side='right', fill='y')
        lb = tk.Listbox(frame, yscrollcommand=scroll.set, selectmode='extended',
                        width=_ROW_LIST_WIDTH, height=_ROW_LIST_HEIGHT, exportselection=False)
        style_tk_listbox(lb)
        lb.pack(side='left', fill='both', expand=True)
        scroll.config(command=lb.yview)
        return frame, lb

    avail_frame, avail_list = _make_list("Available")
    avail_frame.pack(side='left', fill='both', expand=True, padx=(0, PAD_SMALL))
    buttons = ttk.Frame(lists)
    buttons.pack(side='left', padx=PAD_SMALL)
    active_frame, active_list = _make_list("Active")
    active_frame.pack(side='left', fill='both', expand=True, padx=(PAD_SMALL, 0))
    shown_avail: list[str] = []
    shown_active: list[str] = []

    status_var = tk.StringVar()
    status_lbl = ttk.Label(rows_card, textvariable=status_var, font=FONT_SMALL,
                           foreground=THEME_COLORS['muted'], wraplength=_WIDTH - 60, justify='left')
    status_lbl.pack(fill='x', pady=(PAD_XS, 0))
    _register_dim(status_lbl)

    def _refresh_status(*_):
        active = _active()
        picked = [catalog.find(k) for k in _picked()]
        if len(picked) == 1 and picked[0] is not None:
            row = picked[0]
            parts = [row.note, row.kind.encoding_note.capitalize(), row.fresh.sentence,
                     "Reads " + ", ".join(str(i) for i in row.kind.needed_ids) + "."]
            status_var.set("  ".join(p if p.endswith('.') else p + '.' for p in parts if p))
            return
        text = (f"{len(active)} of {len(catalog.ROWS)} rows selected." if active
                else "The panel will show its title line only.")
        if catalog.height_warning(catalog.select(active), panel_fs(base, size_var.get())):
            text += " Taller than the game screen at this size."
        status_var.set(text)

    def _picked():
        return ([shown_avail[i] for i in avail_list.curselection()]
                + [shown_active[i] for i in active_list.curselection()])

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
        state['rows'] = list(keys)
        mode_var.set('custom')
        _refresh_lists(keep_active)

    def _on_mode():
        # Default sets the custom list aside; Custom list brings it back.
        if mode_var.get() == 'default':
            if state['rows'] is not None:
                state['custom'] = state['rows']
            state['rows'] = None
        elif state['rows'] is None:
            state['rows'] = state.get('custom') or catalog.default_keys()
        _refresh_lists()

    def _add(keys):
        if keys:
            _set_rows(catalog.add_keys(_active(), keys), keep_active=keys)

    def _remove(keys):
        if keys:
            _set_rows([k for k in _active() if k not in keys])

    def _move(delta):
        keys = [shown_active[i] for i in active_list.curselection()]
        if keys:
            _set_rows(catalog.move_keys(_active(), keys, delta), keep_active=keys)

    for text, command, style, pady in (
        ("Add >>", lambda: _add([shown_avail[i] for i in avail_list.curselection()]), 'info-outline', PAD_SMALL),
        ("<< Remove", lambda: _remove([shown_active[i] for i in active_list.curselection()]), 'info-outline', PAD_SMALL),
        ("Move up", lambda: _move(-1), 'info-outline', (PAD_TAB, PAD_SMALL)),
        ("Move down", lambda: _move(1), 'info-outline', PAD_SMALL),
        ("Add All", lambda: _set_rows([r.key for r in catalog.ROWS]), 'info-outline', (PAD_TAB, PAD_SMALL)),
        ("Clear", lambda: _set_rows([]), 'warning-outline', PAD_SMALL),
    ):
        btn = ttk.Button(buttons, text=text, command=command, width=BTN_MEDIUM,
                         bootstyle=style)  # type: ignore[call-arg]
        btn.pack(pady=pady)
        gated.append(btn)
    # A disabled Listbox still fires its bindings: the master switch gates them.
    avail_list.bind('<Double-1>', lambda e: enabled_var.get() and _add(
        [shown_avail[i] for i in avail_list.curselection()]))
    active_list.bind('<Double-1>', lambda e: enabled_var.get() and _remove(
        [shown_active[i] for i in active_list.curselection()]))
    for lb in (avail_list, active_list):
        lb.bind('<<ListboxSelect>>', _refresh_status)
        gated.append(lb)
    search_var.trace_add('write', lambda *_: _refresh_lists())
    group_combo.bind('<<ComboboxSelected>>', lambda e: _refresh_lists())

    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(base, p)} pt text",
        on_commit=_refresh_status,
        tooltip="A percent of the overlay size (Overlay, top of the Grids tab). "
                "The whole panel scales with it, collapsed bar included.",
        label_sink=sink)
    gated.append(size_scale)

    _register_dim(*sink)

    def _sync_enabled(*_):
        on = enabled_var.get()
        for widget in gated:
            widget.configure(state='normal' if on else 'disabled')
        # The combobox's live state is readonly, not normal — normal would make it editable.
        group_combo.configure(state='readonly' if on else 'disabled')
        for lbl, normal_fg in dim_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])

    enable_cb.configure(command=_sync_enabled)
    _refresh_lists()
    _sync_enabled()

    def _read_frac(var, frac, extent):
        # Position fields carry projected px; typed overshoot clamps to the
        # screen edge (the grid editor convention), then unprojects back to
        # the stored fraction. An emptied spinbox keeps the loaded fraction.
        try:
            px = max(0, min(int(var.get()), extent))
        except (ValueError, tk.TclError):
            return frac
        return unproject_px(px, extent)

    def _apply():
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'fx': _read_frac(x_var, cfg['fx'], game_w),
            'fy': _read_frac(y_var, cfg['fy'], game_h),
            'scale': size_var.get(),
            'startCollapsed': collapsed_var.get(),
            'rows': state['rows'],
        })
        app.profile_store.set_section('inspect', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg == cfg:
            app_toast(app, "No changes to apply", 'info')
        elif new_cfg['enabled']:
            app_toast(app, "Inspect panel saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Inspect panel off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

    center_on_parent(dialog, app, _WIDTH, _HEIGHT)
    dialog.deiconify()

    dialog.bind("<Return>", lambda e: _apply() if e.widget is not search_entry else None)
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    # The global one-shot dark-titlebar patch can miss a Toplevel built this
    # late, so re-assert it on the dialog's own map (as damageinfo_colors_panel).
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
