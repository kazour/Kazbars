"""
KazBars — Grid Dialogs
AddGridWizard, BuffSelectorDialog (the Tracked Buffs picker, for a whitelist or one
static slot: the grid card opens it from its preview).
"""

import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

from ttkbootstrap.dialogs import Messagebox

from .grid_model import (
    BAND_ROW_CAPS,
    MAX_GRID_SLOTS,
    create_default_grid,
    default_grid_name,
    is_plate,
    max_shape,
    max_slots,
    snap_row_cap,
)
from .settings_manager import get_setting, set_setting
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_DIALOG,
    BTN_MEDIUM,
    FONT_FORM_LABEL,
    FONT_SECTION,
    FONT_SMALL,
    FONT_TINY,
    INPUT_WIDTH_FILTER,
    INPUT_WIDTH_NUM,
    INPUT_WIDTH_SEARCH,
    INPUT_WIDTH_TYPE,
    MODULE_COLORS,
    PAD_BUTTON_GAP,
    PAD_INNER,
    PAD_LIST_ITEM,
    PAD_MICRO,
    PAD_RADIO_INDENT,
    PAD_SECTION_GAP,
    PAD_SMALL,
    PAD_TAB,
    PAD_TINY,
    PAD_XS,
    SLOT_CHIP_GAP,
    SLOT_CHIP_PX,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import style_tk_listbox
from .ui_widgets import add_tooltip, app_toast, debounced_callback, refresh_tooltip
from .window_position import (
    bind_window_position_save,
    fit_window_height,
    restore_window_position,
)

ADD_GRID_WIZARD_SIZE = (460, 600)   # measured content height at the stock font; the
                                    # dialog is fixed-size, so `fit_window_height` re-fits
                                    # it rather than clip the button row at larger text
WIZARD_TYPE_DESC_WRAP = 180  # px, the type descriptions under the two kind columns
BUFF_SELECTOR_SIZE = (800, 600)
BUFF_SELECTOR_MIN = (640, 400)

BUFF_LIST_WIDTH = 40
BUFF_LIST_HEIGHT = 22


def _section(parent, text):
    """LabelFrame with standard padding/packing — used by AddGridWizard."""
    lf = ttk.LabelFrame(parent, text=text, padding=PAD_SMALL)
    lf.pack(fill='x', pady=PAD_SMALL)
    return lf


# ============================================================================
# ADD GRID WIZARD
# ============================================================================
class AddGridWizard(tk.Toplevel):
    """Dialog wizard for creating a new grid: where it sits (a floating grid on
    the player or the target, or an overhead grid over friendly or hostile
    characters), its mode and its shape. An overhead dynamic grid is a band:
    its columns are the row cap (3, 5 or 7) and the rows give way to its 16
    slots; every other shape stays inside its grid's own limit, the columns
    giving way."""

    # (label, rows, cols) per kind of grid: floating (False) or overhead (True).
    _PRESETS = {
        False: (("H-bar 1x10", 1, 10), ("V-bar 10x1", 10, 1), ("Grid 3x3", 3, 3), ("Single 1x1", 1, 1)),
        True: (("Row 1x3", 1, 3), ("Band 2x5", 2, 5), ("Grid 3x3", 3, 3), ("Single 1x1", 1, 1)),
    }
    _TYPE_STYLES = {'player': 'Player', 'target': 'Target', 'friendly': 'Friendly', 'hostile': 'Hostile'}
    _PRESET_STYLES = {'player': 'info-outline', 'target': 'warning-outline',
                      'friendly': 'success-outline', 'hostile': 'danger-outline'}

    def __init__(self, parent, existing_ids, name_in_use):
        super().__init__(parent)
        self.withdraw()
        self.title("Add New Grid")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.existing_ids = existing_ids
        # One owner for the uniqueness rule (grids_panel._grid_name_in_use);
        # existing_ids stays for the default-name suggestion only.
        self.name_in_use = name_in_use
        self.result = None
        self.parent = parent

        self._mode_forced_static = False
        self._mode_before_force = "dynamic"
        self._name_is_auto = True

        self.create_widgets()
        restore_window_position(self, 'add_grid_wizard', *ADD_GRID_WIZARD_SIZE, parent, resizable=False)
        # The constant is measured at the stock Segoe UI 9. Windows text scaling
        # grows every row, and this dialog can't be resized or scrolled, so fit
        # it to what the content actually asks for or Cancel/Create fall off.
        fit_window_height(self, ADD_GRID_WIZARD_SIZE[0])
        bind_window_position_save(self, 'add_grid_wizard', save_size=False)
        self.deiconify()
        self.name_entry.focus_set()
        self.name_entry.select_range(0, 'end')

    def _on_name_edited(self, _event=None):
        """User typed in the name field — stop auto-filling it from the type."""
        self._name_is_auto = False

    def _band(self):
        return is_plate(self.type_var.get()) and self.mode_var.get() == 'dynamic'

    def create_widgets(self):
        create_dialog_header(self, "CREATE NEW GRID", MODULE_COLORS['grids'])

        frame = ttk.Frame(self, padding=PAD_INNER)
        frame.pack(fill='both', expand=True)

        name_frame = ttk.Frame(frame)
        name_frame.pack(fill='x', pady=PAD_TINY)
        ttk.Label(name_frame, text="Grid Name:", font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        self.id_var = tk.StringVar(value=default_grid_name('player', self.existing_ids))
        self.name_entry = ttk.Entry(name_frame, textvariable=self.id_var, width=20)
        self.name_entry.pack(side='left', padx=PAD_SMALL)
        self.name_entry.bind('<KeyRelease>', self._on_name_edited)

        self.type_var = tk.StringVar(value="player")
        kinds = ttk.Frame(frame)
        kinds.pack(fill='x')
        for col, (title, options) in enumerate((
            ("Floating", (("Player", "player", "On yourself, at a spot on screen"),
                          ("Target", "target", "On your current target, at a spot on screen"))),
            ("Overhead", (("Friendly", "friendly", "Over you, your group and friendly players"),
                          ("Hostile", "hostile", "Over your target and anyone fighting you"))),
        )):
            lf = ttk.LabelFrame(kinds, text=title, padding=PAD_SMALL)
            lf.grid(row=0, column=col, sticky='nsew', padx=(0, PAD_SMALL) if col == 0 else 0,
                    pady=PAD_SMALL)
            kinds.columnconfigure(col, weight=1)
            for k, (text, value, desc) in enumerate(options):
                rb = ttk.Radiobutton(lf, text=text, variable=self.type_var, value=value,
                                     command=self._on_type_changed)
                # ttkbootstrap strips custom style= at construction; apply via configure() after.
                rb.configure(style=f'{self._TYPE_STYLES[value]}.TRadiobutton')
                rb.pack(anchor='w', pady=(PAD_TINY if k else 0, 0))
                ttk.Label(lf, text=desc, foreground=THEME_COLORS['muted'], font=FONT_SMALL,
                          wraplength=WIZARD_TYPE_DESC_WRAP, justify='left'
                          ).pack(anchor='w', padx=PAD_RADIO_INDENT)

        mode_lf = _section(frame, "Mode")
        self.mode_var = tk.StringVar(value="dynamic")
        self.mode_dynamic = ttk.Radiobutton(mode_lf, text="Dynamic", variable=self.mode_var,
                                            value="dynamic", command=self._on_mode_changed)
        self.mode_dynamic.pack(anchor='w')
        self._dynamic_desc = ttk.Label(mode_lf, foreground=THEME_COLORS['muted'], font=FONT_SMALL)
        self._dynamic_desc.pack(anchor='w', padx=PAD_RADIO_INDENT)
        self.mode_static = ttk.Radiobutton(mode_lf, text="Static", variable=self.mode_var,
                                           value="static", command=self._on_mode_changed)
        self.mode_static.pack(anchor='w', pady=(PAD_TINY, 0))
        ttk.Label(mode_lf, text="Fixed slots for specific buffs. Empty when buff not active",
                  foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(anchor='w', padx=PAD_RADIO_INDENT)

        dim_frame = _section(frame, "Dimensions")
        dim_row = ttk.Frame(dim_frame)
        dim_row.pack(fill='x')
        ttk.Label(dim_row, text="Rows:", font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        self.rows_var = tk.StringVar(value="1")
        self.rows_spin = ttk.Spinbox(dim_row, from_=1, to=MAX_GRID_SLOTS,
                                     textvariable=self.rows_var, width=INPUT_WIDTH_NUM,
                                     command=self.on_rows_changed)
        self.rows_spin.pack(side='left', padx=(PAD_BUTTON_GAP, PAD_LIST_ITEM))
        self.rows_spin.bind('<KeyRelease>', lambda e: self.on_rows_changed())
        ttk.Label(dim_row, text="Columns:", font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        self.cols_var = tk.StringVar(value="10")
        self.cols_spin = ttk.Spinbox(dim_row, from_=1, to=MAX_GRID_SLOTS,
                                     textvariable=self.cols_var, width=INPUT_WIDTH_NUM,
                                     command=self.on_cols_changed)
        self.cols_spin.pack(side='left', padx=(PAD_BUTTON_GAP, 0))
        self.cols_spin.bind('<KeyRelease>', lambda e: self.on_cols_changed())

        self.shape_var = tk.StringVar(value="")
        ttk.Label(dim_frame, textvariable=self.shape_var, font=FONT_SECTION).pack(pady=(PAD_SMALL, PAD_BUTTON_GAP))
        self.limit_var = tk.StringVar(value="")
        ttk.Label(dim_frame, textvariable=self.limit_var, font=FONT_SMALL,
                  foreground=THEME_COLORS['info_value']).pack()

        preset_frame = ttk.Frame(dim_frame)
        preset_frame.pack(pady=(PAD_XS, 0))
        self._preset_buttons = []
        for _ in range(4):
            btn = ttk.Button(preset_frame, width=BTN_MEDIUM, bootstyle='info-outline')
            btn.pack(side='left', padx=PAD_MICRO)
            self._preset_buttons.append(btn)

        self.warning_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.warning_var,
                  foreground=THEME_COLORS['danger_text']).pack(pady=PAD_BUTTON_GAP)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=PAD_TAB)
        ttk.Button(btn_frame, text="Cancel", command=self.on_cancel, width=BTN_DIALOG, bootstyle='secondary').pack(side='left', padx=PAD_SMALL)
        ttk.Button(btn_frame, text="Create", command=self.on_create, width=BTN_DIALOG, bootstyle='success').pack(side='left', padx=PAD_SMALL)

        self.bind('<Escape>', lambda e: self.on_cancel())
        self.bind('<Return>', lambda e: self.on_create())
        self._on_type_changed()

    def _on_type_changed(self):
        gtype = self.type_var.get()
        overhead = is_plate(gtype)
        for btn, (label, r, c) in zip(self._preset_buttons, self._PRESETS[overhead]):
            btn.configure(text=label, bootstyle=self._PRESET_STYLES[gtype],
                          command=lambda r=r, c=c: self.apply_preset(r, c))
        self._dynamic_desc.configure(
            text="A band centred over the head: rows of up to 7 icons, growing up"
            if overhead else "Shows all tracked buffs, auto-sorted")
        if self._name_is_auto:
            self.id_var.set(default_grid_name(gtype, self.existing_ids))
        self._reshape()

    def _on_mode_changed(self):
        self._reshape()

    def _reshape(self):
        """Clamp the shape for the kind and mode now in force. update_display
        settles the mode first (a floating 1x1 forces Static, which an
        overhead grid lifts), so it runs on both sides of the clamp."""
        self.update_display()
        self._clamp_shape()
        self.update_display()

    def apply_preset(self, rows, cols):
        self.rows_var.set(str(rows))
        self.cols_var.set(str(cols))
        self._clamp_shape()
        self.update_display()

    def safe_get_int(self, var, default=1):
        try:
            val = var.get().strip()
            if not val:
                return default
            return max(1, int(val))
        except (ValueError, tk.TclError):
            return default

    def _clamp_shape(self, changed='rows'):
        """Keep the shape inside the grid's limit. A band's columns are its row
        cap, snapped to 3, 5 or 7 (a typed 4 reads 5) — but a Single 1x1 band
        stays one icon, three to a row — and its rows give way to the 16
        slots; any other grid keeps its rows and columns inside its max shape,
        the other one giving way to its slot limit."""
        gtype = self.type_var.get()
        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        limit = max_slots(gtype)
        max_rows, max_cols = max_shape(gtype)
        if self._band():
            if (rows, cols) != (1, 1):
                cols = snap_row_cap(cols)
            rows = min(rows, max(1, limit // cols))
            self.cols_spin.config(values=BAND_ROW_CAPS)
            self.rows_spin.config(from_=1, to=max(1, limit // cols))
        else:
            self.cols_spin.config(values=())
            rows, cols = min(rows, max_rows), min(cols, max_cols)
            if changed == 'rows':
                cols = min(cols, max(1, limit // rows))
            else:
                rows = min(rows, max(1, limit // cols))
            self.rows_spin.config(from_=1, to=min(max_rows, max(1, limit // cols)))
            self.cols_spin.config(from_=1, to=min(max_cols, max(1, limit // rows)))
        self.rows_var.set(str(rows))
        self.cols_var.set(str(cols))

    def on_rows_changed(self):
        self._clamp_shape('rows')
        self.update_display()

    def on_cols_changed(self):
        self._clamp_shape('cols')
        self.update_display()

    def update_display(self):
        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        total = rows * cols
        gtype = self.type_var.get()
        limit = max_slots(gtype)

        # A floating 1x1 is a single static slot; an overhead 1x1 may be a band of one.
        if rows == 1 and cols == 1 and not is_plate(gtype):
            shape = "Single Slot"
            if not self._mode_forced_static:
                self._mode_before_force = self.mode_var.get()
                self._mode_forced_static = True
            self.mode_var.set("static")
            self.mode_dynamic.config(state='disabled')
        else:
            if self._mode_forced_static:
                self._mode_forced_static = False
                self.mode_var.set(self._mode_before_force)
            self.mode_dynamic.config(state='normal')
            if self._band():
                n = min(total, limit)
                shape = f"Band: up to {n} icon{'s' if n != 1 else ''}, {snap_row_cap(cols)} to a row"
            elif rows == 1:
                shape = f"Horizontal Bar ({cols} slots)"
            elif cols == 1:
                shape = f"Vertical Bar ({rows} slots)"
            else:
                shape = f"Grid ({rows}x{cols} = {total} slots)"
        self.shape_var.set(shape)
        max_rows, max_cols = max_shape(gtype)
        self.limit_var.set(f"An overhead grid holds up to {limit} slots, at most {max_rows} rows "
                           f"or {max_cols} columns" if is_plate(gtype)
                           else f"A grid holds up to {limit} slots")
        self.warning_var.set("" if total <= limit else f"A grid holds at most {limit} slots")

    def on_create(self):
        grid_id = self.id_var.get().strip()
        if not grid_id:
            Messagebox.show_error("Enter a name for the grid.", title="Grid Name Required")
            return

        if self.name_in_use(grid_id, None):
            Messagebox.show_error(f"Grid name '{grid_id}' already exists.", title="Name Taken")
            return

        self._clamp_shape()
        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        limit = max_slots(self.type_var.get())
        if rows * cols > limit:
            app_toast(self.parent, f"A grid holds at most {limit} slots. Reduce rows or columns.", 'warning')
            return

        self.result = create_default_grid(
            grid_type=self.type_var.get(),
            rows=rows,
            cols=cols,
            mode=self.mode_var.get(),
            grid_id=grid_id
        )
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


# ============================================================================
# BUFF SELECTOR DIALOG
# ============================================================================
class BuffSelectorDialog(tk.Toplevel):
    """Dual-list dialog for selecting buff names from the database.

    Refs the database can't resolve (a shared profile's custom buff that never
    arrived, a removed catalog entry) are *inert, not lost*: they render as
    greyed "unknown buff" rows at the bottom of the Selected list, survive OK
    untouched, and can be removed like any other row — the one place a stored
    ref may be dropped is this explicit act. They revive on their own once a
    database update or import supplies the buff again.

    With a `walker` (a static grid's cell opened it) the picker walks the
    grid's slots itself: a strip of numbered chips under the header, ◀ ▶
    beside Cancel and Ctrl+PageUp / Ctrl+PageDown anywhere in the window. A
    move commits the slot it leaves (`walker.commit`) and loads the next; the
    window, the search and the focus stay. Done commits the current slot;
    Cancel drops only the current slot's unsaved edit. A walker answers
    `count`, `start`, `accent`, `ids(i)`, `assigned(i)`, `commit(i, ids)` and
    `tip(i)`.
    """

    def __init__(self, parent, database, title="Select Buffs", initial_ids=None, layout='mixed',
                 walker=None):
        super().__init__(parent)
        self.withdraw()
        self.walker = walker
        self.slot = walker.start if walker is not None else None
        self.title(title)
        self._header_text = "SLOT BUFFS" if walker is not None else title.upper()
        self.transient(parent)
        self.grab_set()

        self.database = database
        self.layout = layout
        self._load(walker.ids(self.slot) if walker is not None else initial_ids)
        self.result = None
        self._search_cache_key = None
        self._search_cache_value = None

        self._debounced_refresh = debounced_callback(self, 200, self.refresh_lists)

        self.create_widgets()

        last_cat = get_setting('buff_selector_category', 'All')
        last_type = get_setting('buff_selector_type', 'All')
        if last_cat in ["All"] + self.database.categories:
            self.category_var.set(last_cat)
        if last_type in ["All", "Buffs", "Debuffs", "Misc"]:
            self.type_var.set(last_type)

        self.refresh_lists()
        restore_window_position(self, 'buff_selector', *BUFF_SELECTOR_SIZE, parent)
        bind_window_position_save(self, 'buff_selector')
        self.minsize(*BUFF_SELECTOR_MIN)
        self.deiconify()
        self.search_entry.focus_set()

    def _load(self, ids):
        """Select `ids`: database refs by name, the rest kept as inert refs."""
        self.selected_names = set()
        self.unknown_refs = []  # unresolvable refs (int id / legacy name), kept inert
        for bid in (ids or []):
            if isinstance(bid, str):
                entry = self.database.get_entry_by_name(bid)
            else:
                entry = self.database.by_id.get(bid)
            if entry:
                self.selected_names.add(entry['name'])
            else:
                self.unknown_refs.append(bid)

    def save_filter_state(self):
        set_setting('buff_selector_category', self.category_var.get())
        set_setting('buff_selector_type', self.type_var.get())

    def create_widgets(self):
        create_dialog_header(self, self._header_text, MODULE_COLORS['grids'])
        if self.walker is not None:
            self._build_slot_strip()

        search_frame = ttk.Frame(self, padding=PAD_SMALL)
        search_frame.pack(fill='x')

        ttk.Label(search_frame, text="Search:").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._debounced_refresh())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=INPUT_WIDTH_SEARCH)
        self.search_entry.pack(side='left', padx=PAD_SMALL)

        ttk.Label(search_frame, text="Category:").pack(side='left', padx=(PAD_TAB, 0))
        self.category_var = tk.StringVar(value="All")
        cat_combo = ttk.Combobox(search_frame, textvariable=self.category_var,
                                  values=["All"] + self.database.categories, width=INPUT_WIDTH_FILTER, state='readonly')
        cat_combo.pack(side='left', padx=PAD_SMALL)
        cat_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_lists())

        ttk.Label(search_frame, text="Type:").pack(side='left', padx=(PAD_TAB, 0))
        self.type_var = tk.StringVar(value="All")
        type_combo = ttk.Combobox(search_frame, textvariable=self.type_var,
                                   values=["All", "Buffs", "Debuffs", "Misc"], width=INPUT_WIDTH_TYPE, state='readonly')
        type_combo.pack(side='left', padx=PAD_SMALL)
        type_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_lists())

        lists_frame = ttk.Frame(self, padding=PAD_SMALL)
        lists_frame.pack(fill='both', expand=True)

        def _make_listbox(parent, label, padx, on_activate):
            frame = ttk.LabelFrame(parent, text=label, padding=PAD_SMALL)
            frame.pack(side='left', fill='both', expand=True, padx=padx)
            scroll = ttk.Scrollbar(frame)
            scroll.pack(side='right', fill='y')
            lb = tk.Listbox(frame, yscrollcommand=scroll.set,
                            selectmode='extended',
                            width=BUFF_LIST_WIDTH, height=BUFF_LIST_HEIGHT)
            style_tk_listbox(lb)
            lb.pack(side='left', fill='both', expand=True)
            scroll.config(command=lb.yview)
            lb.bind('<Double-1>', lambda e: on_activate())

            def _on_return(event):
                on_activate()
                return 'break'
            lb.bind('<Return>', _on_return)
            return lb

        self.avail_list = _make_listbox(lists_frame, "Available", (0, PAD_SMALL), self.add_selected)

        btn_frame = ttk.Frame(lists_frame)
        btn_frame.pack(side='left', padx=PAD_SMALL)
        ttk.Button(btn_frame, text="Add >>", command=self.add_selected, width=12, bootstyle='info-outline').pack(pady=PAD_SMALL)
        ttk.Button(btn_frame, text="<< Remove", command=self.remove_selected, width=12, bootstyle='info-outline').pack(pady=PAD_SMALL)
        ttk.Button(btn_frame, text="Add All", command=self.add_all, width=12, bootstyle='info-outline').pack(pady=PAD_SECTION_GAP)
        ttk.Button(btn_frame, text="Clear", command=self.clear_all, width=12, bootstyle='warning-outline').pack(pady=PAD_SMALL)

        self.sel_list = _make_listbox(lists_frame, "Selected", (PAD_SMALL, 0), self.remove_selected)

        bottom_frame = ttk.Frame(self, padding=PAD_SMALL)
        bottom_frame.pack(fill='x')
        self.status_var = tk.StringVar(value="0 buffs selected. Add from the left list.")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side='left')
        ttk.Button(bottom_frame, text="Done", command=self.on_ok, width=BTN_DIALOG, bootstyle='success').pack(side='right', padx=PAD_SMALL)
        ttk.Button(bottom_frame, text="Cancel", command=self.on_cancel, width=BTN_DIALOG, bootstyle='secondary').pack(side='right', padx=PAD_SMALL)
        if self.walker is not None:
            self._step_buttons = {}
            for glyph, delta, tip in (("▶", 1, "Next slot (Ctrl+PageDown)"),
                                      ("◀", -1, "Previous slot (Ctrl+PageUp)")):
                btn = ttk.Button(bottom_frame, text=glyph, width=3, bootstyle='secondary',
                                 command=lambda d=delta: self.go_to(self.slot + d))
                btn.pack(side='right', padx=(PAD_MICRO, 0))
                add_tooltip(btn, tip)
                self._step_buttons[delta] = btn
            # On the window, so they work wherever focus is (the search box too).
            self.bind('<Control-Prior>', lambda e: self._step_key(-1))
            self.bind('<Control-Next>', lambda e: self._step_key(1))

        self.bind('<Escape>', lambda e: self.on_cancel())
        self.bind('<Return>', lambda e: self.on_ok())

    # ------------------------------------------------------------------
    # Slot walker (a static grid's cell opened the picker)
    # ------------------------------------------------------------------
    def _build_slot_strip(self):
        """One row of numbered chips, one per slot in slot order; scrolls
        sideways when they don't fit."""
        frame = ttk.Frame(self, padding=(PAD_SMALL, PAD_XS, PAD_SMALL, 0))
        frame.pack(fill='x')
        stride = SLOT_CHIP_PX + SLOT_CHIP_GAP
        self._chips = tk.Canvas(frame, height=SLOT_CHIP_PX + 2, bg=TK_COLORS['bg'],
                                highlightthickness=0, bd=0)
        self._chips.pack(fill='x')
        self._chips_bar = ttk.Scrollbar(frame, orient='horizontal', command=self._chips.xview)
        self._chips.configure(xscrollcommand=self._chips_bar.set,
                              scrollregion=(0, 0, self.walker.count * stride, SLOT_CHIP_PX + 2))
        for i in range(self.walker.count):
            x = i * stride
            self._chips.create_rectangle(x + 1, 1, x + SLOT_CHIP_PX, SLOT_CHIP_PX,
                                         tags=(f'chip_{i}', 'rect'))
            self._chips.create_text(x + 1 + SLOT_CHIP_PX // 2, 1 + SLOT_CHIP_PX // 2, text=str(i),
                                    font=FONT_TINY, tags=(f'chip_{i}', 'num'))
        self._chip_hot = -1
        self._chips.bind('<Button-1>', self._on_chip_click)
        self._chips.bind('<Motion>', self._on_chip_motion)
        self._chips.bind('<Configure>', lambda e: self._fit_chip_bar())
        add_tooltip(self._chips, lambda: self.walker.tip(self._chip_hot) if self._chip_hot >= 0 else "")
        self._paint_chips()

    def _chip_at(self, event):
        x = int(self._chips.canvasx(event.x))
        i, off = divmod(x, SLOT_CHIP_PX + SLOT_CHIP_GAP)
        return i if off <= SLOT_CHIP_PX and 0 <= i < self.walker.count else -1

    def _on_chip_click(self, event):
        i = self._chip_at(event)
        if i >= 0:
            self.go_to(i)

    def _on_chip_motion(self, event):
        i = self._chip_at(event)
        if i != self._chip_hot:
            self._chip_hot = i
            refresh_tooltip(self._chips)

    def _fit_chip_bar(self):
        """The scrollbar shows only while the chips overflow the strip."""
        overflow = self.walker.count * (SLOT_CHIP_PX + SLOT_CHIP_GAP) > self._chips.winfo_width()
        if overflow and not self._chips_bar.winfo_ismapped():
            self._chips_bar.pack(fill='x')
        elif not overflow and self._chips_bar.winfo_ismapped():
            self._chips_bar.pack_forget()

    def _paint_chips(self):
        """The current chip filled with the type accent, an assigned one
        outlined in it, an empty one in the input border; the current one
        scrolled into view."""
        accent = self.walker.accent
        for i in range(self.walker.count):
            current = i == self.slot
            held = bool(self._selected_ids()) if current else self.walker.assigned(i)
            fill = accent if current else TK_COLORS['input_bg']
            outline = accent if (current or held) else TK_COLORS['border']
            self._chips.itemconfigure(f'chip_{i}&&rect', fill=fill, outline=outline)
            self._chips.itemconfigure(f'chip_{i}&&num',
                                      fill=TK_COLORS['bg'] if current else THEME_COLORS['body'])
        total = self.walker.count * (SLOT_CHIP_PX + SLOT_CHIP_GAP)
        left, right = self._chips.xview()
        pos = self.slot * (SLOT_CHIP_PX + SLOT_CHIP_GAP) / total
        if not left <= pos < right - SLOT_CHIP_PX / total:
            self._chips.xview_moveto(max(0.0, pos - (right - left) / 2))

    def _step_key(self, delta):
        self.go_to(self.slot + delta)
        return 'break'

    def go_to(self, slot):
        """Commit the slot being edited, then load `slot` in the same window."""
        if not 0 <= slot < self.walker.count or slot == self.slot:
            return
        self.walker.commit(self.slot, self._selected_ids())
        self.slot = slot
        self._load(self.walker.ids(slot))
        self.title(f"Slot {slot} Buffs")
        self.refresh_lists()

    def _sync_walker(self):
        for delta, btn in self._step_buttons.items():
            live = 0 <= self.slot + delta < self.walker.count
            btn.configure(state='normal' if live else 'disabled')
        self._paint_chips()

    def refresh_lists(self):
        query = self.search_var.get()
        category = self.category_var.get()
        if category == "All":
            category = None

        type_map = {"Buffs": "buff", "Debuffs": "debuff", "Misc": "misc"}
        buff_type = type_map.get(self.type_var.get())

        cache_key = (query, category, buff_type)
        if cache_key == self._search_cache_key:
            available = self._search_cache_value
        else:
            available = self.database.search(query, category, buff_type=buff_type)
            self._search_cache_key = cache_key
            self._search_cache_value = available

        type_fg = {
            'debuff': THEME_COLORS['type_debuff'],
            'misc': THEME_COLORS['type_misc'],
        }

        self.avail_list.delete(0, tk.END)
        self.avail_data = []
        for buff in available:
            if buff['name'] not in self.selected_names:
                idx = self.avail_list.size()
                self.avail_list.insert(tk.END, buff['name'])
                fg = type_fg.get(buff.get('type', 'buff'))
                if fg:
                    self.avail_list.itemconfig(idx, foreground=fg)
                self.avail_data.append(buff)

        self.sel_list.delete(0, tk.END)
        self.sel_data = []
        selected_entries = []
        for buff in self.database.grouped_buffs:
            if buff['name'] in self.selected_names:
                selected_entries.append({
                    'name': buff['name'], 'ids': buff.get('ids', []),
                    'type': buff.get('type', 'buff'),
                })
        _type_order = (
            {'misc': 0, 'buff': 1, 'debuff': 2} if self.layout == 'buffFirst' else
            {'misc': 0, 'debuff': 1, 'buff': 2} if self.layout == 'debuffFirst' else
            None
        )
        if _type_order:
            selected_entries.sort(key=lambda e: (_type_order.get(e.get('type', 'buff'), 1), e['name'].lower()))
        else:
            selected_entries.sort(key=lambda e: e['name'].lower())
        for entry in selected_entries:
            idx = self.sel_list.size()
            self.sel_list.insert(tk.END, entry['name'])
            fg = type_fg.get(entry.get('type', 'buff'))
            if fg:
                self.sel_list.itemconfig(idx, foreground=fg)
            self.sel_data.append({'name': entry['name'], 'ids': entry['ids']})

        # Inert refs cluster at the bottom, greyed — present so they can be
        # removed on purpose, dim so they read as not-in-the-next-build.
        for ref in self.unknown_refs:
            idx = self.sel_list.size()
            label = f"unknown buff (#{ref})" if isinstance(ref, int) else f"unknown buff ({ref})"
            self.sel_list.insert(tk.END, label)
            self.sel_list.itemconfig(idx, foreground=TK_COLORS['dim_text'])
            self.sel_data.append({'unknown': ref})

        count = len(self.selected_names)
        unresolved = f" + {len(self.unknown_refs)} unresolved" if self.unknown_refs else ""
        if count == 0 and not self.unknown_refs:
            if self.avail_data:
                status = "0 buffs selected. Add from the left list."
            else:
                status = "0 buffs selected. No buffs match the current filters."
        else:
            status = f"{count} buffs selected{unresolved}"
        if self.walker is not None:
            n = self.walker.count
            if all(self.walker.assigned(i) for i in range(n) if i != self.slot) and self._selected_ids():
                status += f" · All {n} slots are assigned."
            self._sync_walker()
        self.status_var.set(status)

    def add_selected(self):
        for i in self.avail_list.curselection():
            self.selected_names.add(self.avail_data[i]['name'])
        self.refresh_lists()

    def remove_selected(self):
        for i in self.sel_list.curselection():
            entry = self.sel_data[i]
            if 'unknown' in entry:
                self.unknown_refs.remove(entry['unknown'])
            else:
                self.selected_names.discard(entry['name'])
        self.refresh_lists()

    def add_all(self):
        for buff in self.avail_data:
            self.selected_names.add(buff['name'])
        self.refresh_lists()

    def clear_all(self):
        self.selected_names.clear()
        self.unknown_refs.clear()
        self.refresh_lists()

    def _selected_ids(self):
        """The selection as refs: each selected entry's primary id, then the
        inert refs the user didn't explicitly remove, unchanged."""
        out = []
        for name in self.selected_names:
            entry = self.database.get_entry_by_name(name)
            if entry and entry.get('ids'):
                out.append(entry['ids'][0])
        return out + list(self.unknown_refs)

    def on_ok(self):
        self.save_filter_state()
        self.result = self._selected_ids()
        if self.walker is not None:
            self.walker.commit(self.slot, self.result)
        self.destroy()

    def on_cancel(self):
        self.save_filter_state()
        self.result = None
        self.destroy()
