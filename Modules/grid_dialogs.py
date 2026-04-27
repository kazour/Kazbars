"""
Kaz Grids — Grid Dialogs
AddGridWizard, BuffSelectorDialog, SlotAssignmentDialog.
"""

import logging
import math
import tkinter as tk
from tkinter import ttk
from collections import Counter

logger = logging.getLogger(__name__)

from .ui_helpers import (
    FONT_HEADING, FONT_SECTION, FONT_BODY, FONT_SMALL, FONT_TINY, FONT_FORM_LABEL,
    THEME_COLORS, TK_COLORS, GRID_TYPE_COLORS, _RETRO_COLORS,
    BTN_DIALOG, INPUT_WIDTH_NUM, INPUT_WIDTH_TYPE, INPUT_WIDTH_FILTER, INPUT_WIDTH_SEARCH,
    PAD_INNER, PAD_ROW, PAD_RADIO_INDENT,
    PAD_XS, PAD_MICRO, PAD_TINY, PAD_SMALL, PAD_TAB, PAD_LF, PAD_LIST_ITEM,
    PAD_SECTION_GAP, PAD_BUTTON_GAP,
    MODULE_COLORS,
)
from .ui_widgets import (
    debounced_callback, blend_alpha, add_tooltip, create_dialog_header,
)
from .ui_components import create_scrollable_frame
from .ui_tk_style import style_tk_listbox
from .settings_manager import get_setting, set_setting
from .window_position import restore_window_position, bind_window_position_save
from ttkbootstrap.dialogs import Messagebox
from .grid_model import create_default_grid, MAX_TOTAL_SLOTS

ADD_GRID_WIZARD_SIZE = (460, 600)
BUFF_SELECTOR_SIZE = (800, 600)
SLOT_ASSIGNMENT_SIZE = (620, 520)


def _section(parent, text):
    """LabelFrame with standard padding/packing — used by AddGridWizard."""
    lf = ttk.LabelFrame(parent, text=text, padding=PAD_SMALL)
    lf.pack(fill='x', pady=PAD_SMALL)
    return lf


# ============================================================================
# ADD GRID WIZARD
# ============================================================================
class AddGridWizard(tk.Toplevel):
    """Dialog wizard for creating a new grid with type, size, and mode options."""

    def __init__(self, parent, existing_ids, current_total_slots):
        super().__init__(parent)
        self.withdraw()
        self.title("Add New Grid")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.existing_ids = existing_ids
        self.current_total_slots = current_total_slots
        self.available_slots = MAX_TOTAL_SLOTS - current_total_slots
        self.result = None
        self.parent = parent

        self.create_widgets()
        restore_window_position(self, 'add_grid_wizard', *ADD_GRID_WIZARD_SIZE, parent, resizable=False)
        bind_window_position_save(self, 'add_grid_wizard', save_size=False)
        self.deiconify()

    def generate_unique_name(self, base="Grid"):
        counter = 1
        while True:
            name = f"{base}{counter}"
            if name not in self.existing_ids:
                return name
            counter += 1

    def create_widgets(self):
        create_dialog_header(self, "CREATE NEW GRID", MODULE_COLORS['grids'])

        frame = ttk.Frame(self, padding=PAD_INNER)
        frame.pack(fill='both', expand=True)

        self.avail_label = ttk.Label(frame, text=f"Available slots: {self.available_slots} of {MAX_TOTAL_SLOTS}",
                                     font=FONT_SMALL, foreground=THEME_COLORS['info_value'])
        self.avail_label.pack(pady=(0, PAD_LF))

        name_frame = ttk.Frame(frame)
        name_frame.pack(fill='x', pady=PAD_TINY)
        ttk.Label(name_frame, text="Grid Name:", font=FONT_FORM_LABEL,
                 foreground=THEME_COLORS['muted']).pack(side='left')
        self.id_var = tk.StringVar(value=self.generate_unique_name())
        ttk.Entry(name_frame, textvariable=self.id_var, width=20).pack(side='left', padx=PAD_SMALL)

        source_frame = _section(frame, "Source")

        self.type_var = tk.StringVar(value="player")
        ttk.Radiobutton(source_frame, text="Player", variable=self.type_var, value="player").pack(anchor='w')
        ttk.Label(source_frame, text="Track buffs/debuffs on yourself",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(anchor='w', padx=PAD_RADIO_INDENT)
        ttk.Radiobutton(source_frame, text="Target", variable=self.type_var, value="target").pack(anchor='w', pady=(PAD_TINY, 0))
        ttk.Label(source_frame, text="Track buffs/debuffs on your current target",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(anchor='w', padx=PAD_RADIO_INDENT)

        mode_lf = _section(frame, "Mode")

        self.mode_var = tk.StringVar(value="dynamic")
        self.mode_dynamic = ttk.Radiobutton(mode_lf, text="Dynamic", variable=self.mode_var, value="dynamic")
        self.mode_dynamic.pack(anchor='w')
        ttk.Label(mode_lf, text="Shows all tracked buffs, auto-sorted",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(anchor='w', padx=PAD_RADIO_INDENT)

        self.mode_static = ttk.Radiobutton(mode_lf, text="Static", variable=self.mode_var, value="static")
        self.mode_static.pack(anchor='w', pady=(PAD_TINY, 0))
        ttk.Label(mode_lf, text="Fixed slots for specific buffs. Empty when buff not active",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(anchor='w', padx=PAD_RADIO_INDENT)

        dim_frame = _section(frame, "Dimensions")

        dim_row = ttk.Frame(dim_frame)
        dim_row.pack(fill='x')

        ttk.Label(dim_row, text="Rows:", font=FONT_FORM_LABEL,
                 foreground=THEME_COLORS['muted']).pack(side='left')
        self.rows_var = tk.StringVar(value="1")
        self.rows_spin = ttk.Spinbox(dim_row, from_=1, to=self.available_slots,
                                      textvariable=self.rows_var, width=INPUT_WIDTH_NUM,
                                      command=self.on_rows_changed)
        self.rows_spin.pack(side='left', padx=(PAD_BUTTON_GAP, PAD_LIST_ITEM))
        self.rows_spin.bind('<KeyRelease>', lambda e: self.on_rows_changed())

        ttk.Label(dim_row, text="Columns:", font=FONT_FORM_LABEL,
                 foreground=THEME_COLORS['muted']).pack(side='left')
        self.cols_var = tk.StringVar(value="10")
        self.cols_spin = ttk.Spinbox(dim_row, from_=1, to=self.available_slots,
                                      textvariable=self.cols_var, width=INPUT_WIDTH_NUM,
                                      command=self.on_cols_changed)
        self.cols_spin.pack(side='left', padx=(PAD_BUTTON_GAP, 0))
        self.cols_spin.bind('<KeyRelease>', lambda e: self.on_cols_changed())

        self.shape_var = tk.StringVar(value="")
        ttk.Label(dim_frame, textvariable=self.shape_var, font=FONT_SECTION).pack(pady=(PAD_SMALL, PAD_BUTTON_GAP))

        preset_frame = ttk.Frame(dim_frame)
        preset_frame.pack(pady=(PAD_XS, 0))

        for label, r, c in [("H-bar 1x10", 1, 10), ("V-bar 10x1", 10, 1),
                             ("Grid 3x3", 3, 3), ("Single 1x1", 1, 1)]:
            ttk.Button(preset_frame, text=label, width=11, bootstyle='info-outline',
                       command=lambda r=r, c=c: self.apply_preset(r, c)).pack(side='left', padx=PAD_MICRO)

        self.warning_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.warning_var, foreground=THEME_COLORS['danger']).pack(pady=PAD_BUTTON_GAP)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=PAD_TAB)
        ttk.Button(btn_frame, text="Cancel", command=self.on_cancel, width=BTN_DIALOG, bootstyle='secondary').pack(side='left', padx=PAD_SMALL)
        ttk.Button(btn_frame, text="Create", command=self.on_create, width=BTN_DIALOG, bootstyle='success').pack(side='left', padx=PAD_SMALL)

        self.bind('<Escape>', lambda e: self.on_cancel())
        self.bind('<Return>', lambda e: self.on_create())
        self.update_display()

    def apply_preset(self, rows, cols):
        total = rows * cols
        if total > self.available_slots:
            if rows == 1:
                cols = self.available_slots
            elif cols == 1:
                rows = self.available_slots
            else:
                scale = math.sqrt(self.available_slots / total)
                rows = max(1, int(rows * scale))
                cols = max(1, int(cols * scale))
        self.rows_var.set(str(rows))
        self.cols_var.set(str(cols))
        if rows == 1 and cols == 1:
            self.mode_var.set("static")
        self.update_display()

    def safe_get_int(self, var, default=1):
        try:
            val = var.get().strip()
            if not val:
                return default
            return max(1, int(val))
        except (ValueError, tk.TclError):
            return default

    def _on_dimension_changed(self, changed='rows'):
        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        if changed == 'rows':
            rows = min(rows, self.available_slots)
            max_other = self.available_slots if rows == 1 else self.available_slots // rows
            if cols > max_other:
                self.cols_var.set(str(max_other))
            self.cols_spin.config(to=max_other)
        else:
            cols = min(cols, self.available_slots)
            max_other = self.available_slots if cols == 1 else self.available_slots // cols
            if rows > max_other:
                self.rows_var.set(str(max_other))
            self.rows_spin.config(to=max_other)
        self.update_display()

    def on_rows_changed(self):
        self._on_dimension_changed('rows')

    def on_cols_changed(self):
        self._on_dimension_changed('cols')

    def update_display(self):
        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        total = rows * cols

        if rows == 1 and cols == 1:
            shape = "Single Slot"
            self.mode_var.set("static")
            self.mode_dynamic.config(state='disabled')
        elif rows == 1:
            shape = f"Horizontal Bar ({cols} slots)"
            self.mode_dynamic.config(state='normal')
        elif cols == 1:
            shape = f"Vertical Bar ({rows} slots)"
            self.mode_dynamic.config(state='normal')
        else:
            shape = f"Grid ({rows}x{cols} = {total} slots)"
            self.mode_dynamic.config(state='normal')

        remaining = self.available_slots - total
        if remaining >= 0:
            self.shape_var.set(f"{shape}  \u00b7  {remaining} remaining")
            self.warning_var.set("")
        else:
            self.shape_var.set(shape)
            self.warning_var.set(f"Exceeds available slots by {-remaining}!")

    def on_create(self):
        grid_id = self.id_var.get().strip()
        if not grid_id:
            Messagebox.show_error("Enter a name for the grid.", title="Grid Name Required")
            return

        has_special = any(not (c.isalnum() or c == '_' or c == ' ') for c in grid_id)
        if has_special:
            if Messagebox.yesno(
                f"Grid name '{grid_id}' contains special characters.\n"
                "These will be converted to underscores.\nContinue?",
                title="Special Characters") == "No":
                return

        if grid_id in self.existing_ids:
            Messagebox.show_error(f"Grid name '{grid_id}' already exists.", title="Name Taken")
            return

        rows = self.safe_get_int(self.rows_var, 1)
        cols = self.safe_get_int(self.cols_var, 1)
        total = rows * cols

        if total > self.available_slots:
            Messagebox.show_error(f"Only {self.available_slots} slots available.\n\nReduce rows or columns, or remove another grid to free up slots.", title="Slot Limit")
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
    """Dual-list dialog for selecting buff names from the database."""

    def __init__(self, parent, database, title="Select Buffs", initial_ids=None, layout='mixed'):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent)
        self.grab_set()

        self.database = database
        self.layout = layout
        self.selected_names = set()
        for bid in (initial_ids or []):
            entry = database.by_id.get(bid)
            if entry:
                self.selected_names.add(entry['name'])
        self.result = None

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
        self.deiconify()

    def save_filter_state(self):
        set_setting('buff_selector_category', self.category_var.get())
        set_setting('buff_selector_type', self.type_var.get())

    def create_widgets(self):
        create_dialog_header(self, "SELECT BUFFS", MODULE_COLORS['grids'])

        search_frame = ttk.Frame(self, padding=PAD_SMALL)
        search_frame.pack(fill='x')

        ttk.Label(search_frame, text="Search:").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._debounced_refresh())
        ttk.Entry(search_frame, textvariable=self.search_var, width=INPUT_WIDTH_SEARCH).pack(side='left', padx=PAD_SMALL)

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

        def _make_listbox(parent, label, padx, on_double_click):
            frame = ttk.LabelFrame(parent, text=label, padding=PAD_SMALL)
            frame.pack(side='left', fill='both', expand=True, padx=padx)
            scroll = ttk.Scrollbar(frame)
            scroll.pack(side='right', fill='y')
            lb = tk.Listbox(frame, yscrollcommand=scroll.set,
                            selectmode='extended', width=40, height=22)
            style_tk_listbox(lb)
            lb.pack(side='left', fill='both', expand=True)
            scroll.config(command=lb.yview)
            lb.bind('<Double-1>', lambda e: on_double_click())
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
        self.status_var = tk.StringVar(value="0 buffs selected — add from the left list")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side='left')
        ttk.Button(bottom_frame, text="Done", command=self.on_ok, width=BTN_DIALOG, bootstyle='success').pack(side='right', padx=PAD_SMALL)
        ttk.Button(bottom_frame, text="Cancel", command=self.on_cancel, width=BTN_DIALOG, bootstyle='secondary').pack(side='right')

        self.bind('<Escape>', lambda e: self.on_cancel())

    def refresh_lists(self):
        query = self.search_var.get()
        category = self.category_var.get()
        if category == "All":
            category = None

        type_map = {"Buffs": "buff", "Debuffs": "debuff", "Misc": "misc"}
        buff_type = type_map.get(self.type_var.get())

        available = self.database.search(query, category, buff_type=buff_type)

        self.avail_list.delete(0, tk.END)
        self.avail_data = []
        for buff in available:
            if buff['name'] not in self.selected_names:
                self.avail_list.insert(tk.END, buff['name'])
                self.avail_data.append(buff)

        self.sel_list.delete(0, tk.END)
        self.sel_data = []
        selected_entries = []
        for buff in self.database.grouped_buffs:
            if buff['name'] in self.selected_names:
                tag = {"debuff": "(D)", "misc": "(M)"}.get(buff.get('type', 'buff'), "(B)")
                selected_entries.append({
                    'name': buff['name'], 'ids': buff.get('ids', []),
                    'type': buff.get('type', 'buff'),
                    'display': f"{buff['name']} {tag}"
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
            self.sel_list.insert(tk.END, entry['display'])
            self.sel_data.append({'name': entry['name'], 'ids': entry['ids']})

        count = len(self.selected_names)
        if count == 0:
            self.status_var.set("0 buffs selected \u2014 add from the left list")
        else:
            self.status_var.set(f"{count} buffs selected")

    def add_selected(self):
        for i in self.avail_list.curselection():
            self.selected_names.add(self.avail_data[i]['name'])
        self.refresh_lists()

    def remove_selected(self):
        for i in self.sel_list.curselection():
            self.selected_names.discard(self.sel_data[i]['name'])
        self.refresh_lists()

    def add_all(self):
        for buff in self.avail_data:
            self.selected_names.add(buff['name'])
        self.refresh_lists()

    def clear_all(self):
        self.selected_names.clear()
        self.refresh_lists()

    def on_ok(self):
        self.save_filter_state()
        self.result = []
        for name in self.selected_names:
            entry = self.database.get_entry_by_name(name)
            if entry and entry.get('ids'):
                self.result.append(entry['ids'][0])
        self.destroy()

    def on_cancel(self):
        self.save_filter_state()
        self.result = None
        self.destroy()


# ============================================================================
# SLOT ASSIGNMENT DIALOG
# ============================================================================
class SlotAssignmentDialog(tk.Toplevel):
    """Dialog for assigning specific buffs to individual grid slots."""

    def __init__(self, parent, database, grid_config):
        super().__init__(parent)
        self.withdraw()
        self.title(f"Slot Assignments - {grid_config['id']}")
        self.transient(parent)
        self.grab_set()

        self.database = database
        self.grid_config = grid_config
        self.total_slots = grid_config['rows'] * grid_config['cols']
        self._type_color = GRID_TYPE_COLORS.get(grid_config.get('type', 'player'), GRID_TYPE_COLORS['player'])

        sa = grid_config.get('slotAssignments', {})
        self.assignments = {}
        for i in range(self.total_slots):
            v = sa.get(str(i), sa.get(i, []))
            if isinstance(v, str):
                self.assignments[i] = [v] if v else []
            else:
                self.assignments[i] = list(v)

        self.result = None
        self.create_widgets()
        restore_window_position(self, 'slot_assignment', *SLOT_ASSIGNMENT_SIZE, parent)
        bind_window_position_save(self, 'slot_assignment')
        self.deiconify()

    def create_widgets(self):
        create_dialog_header(self, "SLOT ASSIGNMENTS", MODULE_COLORS['grids'])

        self.summary_var = tk.StringVar()
        self._hovered = -1

        body = ttk.Frame(self)
        body.pack(fill='both', expand=True, padx=PAD_SMALL, pady=(0, PAD_SMALL))

        self._build_grid_canvas(body)
        self._build_summary(body)

        bottom = ttk.Frame(self, padding=PAD_SMALL)
        bottom.pack(fill='x')
        ttk.Button(bottom, text="Done", command=self.on_ok, width=BTN_DIALOG, bootstyle='success').pack(side='right', padx=PAD_SMALL)
        ttk.Button(bottom, text="Cancel", command=self.on_cancel, width=BTN_DIALOG, bootstyle='secondary').pack(side='right')

        self.bind('<Escape>', lambda e: self.on_cancel())
        self.refresh_slot_displays()

    def _build_grid_canvas(self, parent):
        cols = self.grid_config['cols']
        rows = self.grid_config['rows']
        MAX_W, MAX_H = 540, 340
        self._cell = 34
        self._gap = 4
        stride = self._cell + self._gap

        grid_w = cols * stride
        grid_h = rows * stride
        display_w = min(grid_w, MAX_W)
        display_h = min(grid_h, MAX_H)

        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(anchor='center', pady=(PAD_SMALL, PAD_TINY))

        self._canvas = tk.Canvas(
            canvas_frame,
            width=display_w,
            height=display_h,
            bg=TK_COLORS['bg'],
            highlightthickness=0,
            cursor='hand2',
        )
        self._canvas.configure(scrollregion=(0, 0, grid_w, grid_h))

        if grid_w > MAX_W:
            hbar = ttk.Scrollbar(canvas_frame, orient='horizontal', command=self._canvas.xview)
            hbar.pack(side='bottom', fill='x')
            self._canvas.configure(xscrollcommand=hbar.set)
        if grid_h > MAX_H:
            vbar = ttk.Scrollbar(canvas_frame, orient='vertical', command=self._canvas.yview)
            vbar.pack(side='right', fill='y')
            self._canvas.configure(yscrollcommand=vbar.set)

        self._canvas.pack(side='left')
        self._canvas.bind("<Button-1>", self._on_canvas_click)
        self._canvas.bind("<Motion>", self._on_canvas_motion)
        self._canvas.bind("<Leave>", self._on_canvas_leave)

        ttk.Label(parent, textvariable=self.summary_var,
                  font=FONT_SMALL, foreground=THEME_COLORS['muted']).pack(anchor='center')

    def _build_summary(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=(PAD_SMALL, 0))

        self._summary_text = tk.Text(
            frame, height=5, font=FONT_SMALL,
            bg=TK_COLORS['input_bg'], fg=TK_COLORS['input_fg'],
            relief='flat', bd=0, state='disabled',
            highlightthickness=1, highlightbackground=TK_COLORS['border'],
        )
        sb = ttk.Scrollbar(frame, orient='vertical', command=self._summary_text.yview)
        self._summary_text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self._summary_text.pack(side='left', fill='both', expand=True)

    def _slot_pos(self, idx):
        """Map slot index to (row, col) using fillDirection — matches AS2 posSlot."""
        rows = self.grid_config['rows']
        cols = self.grid_config['cols']
        fill = self.grid_config.get('fillDirection', 'TL-BR')
        if rows == 1:
            return (0, (cols - 1 - idx) if fill == 'RL' else idx)
        if cols == 1:
            return ((rows - 1 - idx) if fill == 'BT' else idx, 0)
        br, bc = idx // cols, idx % cols
        if fill == 'TR-BL':
            return (br, cols - 1 - bc)
        if fill == 'BL-TR':
            return (rows - 1 - br, bc)
        if fill == 'BR-TL':
            return (rows - 1 - br, cols - 1 - bc)
        return (br, bc)  # TL-BR default

    def _pos_to_slot(self, r, c):
        """Reverse of _slot_pos: map (row, col) back to slot index."""
        rows = self.grid_config['rows']
        cols = self.grid_config['cols']
        fill = self.grid_config.get('fillDirection', 'TL-BR')
        if rows == 1:
            bc = (cols - 1 - c) if fill == 'RL' else c
            return bc
        if cols == 1:
            br = (rows - 1 - r) if fill == 'BT' else r
            return br
        if fill == 'TR-BL':
            return r * cols + (cols - 1 - c)
        if fill == 'BL-TR':
            return (rows - 1 - r) * cols + c
        if fill == 'BR-TL':
            return (rows - 1 - r) * cols + (cols - 1 - c)
        return r * cols + c  # TL-BR default

    def _draw_grid(self):
        self._canvas.delete('all')
        cols = self.grid_config['cols']
        cell = self._cell
        stride = cell + self._gap
        _pixel_border = _RETRO_COLORS['pixel_border']

        for i in range(self.total_slots):
            r, c = self._slot_pos(i)
            x0 = c * stride
            y0 = r * stride
            x1 = x0 + cell
            y1 = y0 + cell

            tag = f'slot_{i}'
            self._canvas.create_rectangle(x0, y0, x1, y1,
                                          fill='', outline=_pixel_border, tags=(tag, 'rect'))
            self._canvas.create_text(x0 + 4, y0 + 4, text=str(i),
                                     anchor='nw', font=FONT_SMALL,
                                     fill='', tags=(tag, 'num'))
            self._canvas.create_text(x1 - 3, y1 - 3, text='',
                                     anchor='se', font=FONT_TINY,
                                     fill='', tags=(tag, 'count'))
            self._update_slot_visual(i)

    def _update_slot_visual(self, i):
        if i < 0 or i >= self.total_slots:
            return
        tag = f'slot_{i}'
        assigned = bool(self.assignments.get(i))
        hovered = (i == self._hovered)
        _bg = TK_COLORS['bg']
        _tc = self._type_color

        if hovered and assigned:
            fill = blend_alpha(_tc, _bg, 80)
        elif assigned:
            fill = _tc
        elif hovered:
            fill = TK_COLORS['select_bg']
        else:
            fill = TK_COLORS['input_bg']

        self._canvas.itemconfigure(tag + '&&rect', fill=fill)

        num_color = _bg if assigned else (TK_COLORS['dim_text'] if not hovered else THEME_COLORS['muted'])
        self._canvas.itemconfigure(tag + '&&num', fill=num_color)

        count = len(self.assignments.get(i, []))
        self._canvas.itemconfigure(tag + '&&count',
                                   text=str(count) if count else '',
                                   fill=_bg if count else '')

    def _on_canvas_click(self, event):
        cols = self.grid_config['cols']
        stride = self._cell + self._gap
        x = int(self._canvas.canvasx(event.x))
        y = int(self._canvas.canvasy(event.y))
        c = x // stride
        r = y // stride
        if 0 <= c < cols and 0 <= r < self.grid_config['rows']:
            idx = self._pos_to_slot(r, c)
            if 0 <= idx < self.total_slots:
                self.edit_slot(idx)

    def _on_canvas_motion(self, event):
        cols = self.grid_config['cols']
        stride = self._cell + self._gap
        x = int(self._canvas.canvasx(event.x))
        y = int(self._canvas.canvasy(event.y))
        c = x // stride
        r = y // stride
        if 0 <= c < cols and 0 <= r < self.grid_config['rows']:
            idx = self._pos_to_slot(r, c)
            if idx < self.total_slots and idx != self._hovered:
                prev = self._hovered
                self._hovered = idx
                self._update_slot_visual(prev)
                self._update_slot_visual(idx)
        elif self._hovered != -1:
            prev = self._hovered
            self._hovered = -1
            self._update_slot_visual(prev)

    def _on_canvas_leave(self, event):
        if self._hovered != -1:
            prev = self._hovered
            self._hovered = -1
            self._update_slot_visual(prev)

    def _refresh_summary(self):
        lines = []
        for i in range(self.total_slots):
            buffs = self.assignments.get(i, [])
            if buffs:
                counts = Counter()
                for bid in buffs:
                    entry = self.database.by_id.get(bid)
                    name = entry['name'] if entry else f"(missing #{bid})"
                    counts[name] += 1
                parts = [f"{n} x{c}" if c > 1 else n for n, c in counts.items()]
                lines.append(f"Slot {i}: {', '.join(parts)}")

        self._summary_text.configure(state='normal')
        self._summary_text.delete('1.0', tk.END)
        self._summary_text.insert(tk.END, '\n'.join(lines) if lines else "Click any cell to assign buffs.")
        self._summary_text.configure(state='disabled')

    def refresh_slot_displays(self):
        assigned_count = sum(1 for v in self.assignments.values() if v)
        self.summary_var.set(f"{assigned_count} of {self.total_slots} slots assigned — click a slot to edit")
        self._draw_grid()
        self._refresh_summary()

    def edit_slot(self, slot_index):
        dialog = BuffSelectorDialog(
            self, self.database, f"Slot {slot_index} Buffs",
            initial_ids=self.assignments.get(slot_index, []),
            layout=self.grid_config.get('layout', 'mixed'),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.assignments[slot_index] = dialog.result
            self.refresh_slot_displays()

    def on_ok(self):
        self.result = {str(k): v for k, v in self.assignments.items() if v}
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()
