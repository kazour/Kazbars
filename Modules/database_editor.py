"""
Kaz Grids — Database Editor Module
Handles buff database loading, editing, and the Database view UI.

v2 Format:
{
    "name": "Buff Name",
    "ids": [id1, id2, ...],
    "category": "#Category",
    "type": "buff" | "debuff" | "misc",
    "stacking": true,      // optional - IDs represent stack levels
    "partialList": true,   // optional - IDs don't start from stack 1
    "stackStart": 1,       // optional - first stack level to track (default: 1)
    "stackEnd": 10         // optional - last stack level to track, complete list only (0 = all)
}
"""

import logging
import tkinter as tk
from tkinter import ttk, filedialog
from ttkbootstrap.dialogs import Messagebox, Querybox
from .ui_helpers import (
    THEME_COLORS, TK_COLORS, FONT_SMALL, style_tk_text, BTN_SMALL, BTN_MEDIUM,
    add_tooltip, debounced_callback,
    create_dialog_header, MODULE_COLORS, PAD_INNER,
    PAD_SMALL, PAD_TAB, PAD_XS, PAD_BUTTON_GAP, PAD_SECTION_GAP,
)
from .window_position import restore_window_position, bind_window_position_save
import json
import re

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================
TYPE_FILTER_MAP = {"Buff": "buff", "Debuff": "debuff", "Misc": "misc"}


# ============================================================================
# BUFF DATABASE
# ============================================================================
class BuffDatabase:
    """Handles loading, searching, and managing the buff database."""

    def __init__(self):
        self.buffs = []
        self.categories = []
        self.by_id = {}
        self.by_name = {}
        self.grouped_buffs = []

    def load(self, json_path):
        """Load database from JSON file."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.buffs = data.get('buffs', [])
            self._rebuild_indexes()
            return True
        except (IOError, OSError, json.JSONDecodeError) as e:
            logger.error("Error loading buff database: %s", e)
            return False

    def _rebuild_indexes(self):
        """Rebuild internal indexes after data changes."""
        cats = set()
        self.by_id = {}
        self.by_name = {}
        for b in self.buffs:
            cats.add(b.get('category', 'Unknown'))
            ids = b.get('ids', [])
            for bid in ids:
                self.by_id[bid] = b
            self.by_name[b['name']] = b
        self.categories = sorted(list(cats))
        self.grouped_buffs = list(self.buffs)

    def search(self, query="", category=None, buff_type=None):
        """
        Search buffs by query, category, and type.

        Args:
            query: Search string (matches name or ID)
            category: Category filter (None = all)
            buff_type: Type filter - "buff", "debuff", "misc" (None = all)
        """
        results = []
        query_lower = query.lower() if query else ""

        for buff in self.grouped_buffs:
            if category and buff.get('category') != category:
                continue
            if buff_type and buff.get('type', 'buff') != buff_type:
                continue
            if query_lower:
                name_match = query_lower in buff.get('name', '').lower()
                id_match = any(query_lower in str(bid) for bid in buff.get('ids', []))
                if not name_match and not id_match:
                    continue
            results.append(buff)

        type_order = {'buff': 0, 'debuff': 1, 'misc': 2}
        return sorted(results, key=lambda b: (type_order.get(b.get('type', 'buff'), 9), b.get('name', '')))

    def get_type(self, buff_id):
        """Get buff type by ID (buff/debuff/misc)."""
        buff = self.by_id.get(buff_id)
        if buff:
            return buff.get('type', 'buff')
        return 'buff'

    def is_debuff(self, buff_id):
        """Check if buff is a debuff."""
        return self.get_type(buff_id) == 'debuff'

    def find_entry_by_id(self, bid):
        """Return entry dict for the given buff ID, or None."""
        return self.by_id.get(bid)

    def get_entry_by_name(self, name):
        """Return entry dict for the given entry name, or None."""
        return self.by_name.get(name)

    def add_buff(self, buff_data):
        """Add a new buff entry."""
        self.buffs.append(buff_data)
        self._rebuild_indexes()

    def update_buff(self, old_ids, new_data):
        """Update an existing buff entry."""
        for i, buff in enumerate(self.buffs):
            buff_ids = buff.get('ids', [])
            if set(buff_ids) == set(old_ids):
                self.buffs[i] = new_data
                break
        self._rebuild_indexes()

    def remove_buff(self, ids):
        """Remove a buff entry by its IDs."""
        self.buffs = [b for b in self.buffs if set(b.get('ids', [])) != set(ids)]
        self._rebuild_indexes()

    def rename_category(self, old_name, new_name):
        """Rename a category across all buff entries."""
        for buff in self.buffs:
            if buff.get('category') == old_name:
                buff['category'] = new_name
        self._rebuild_indexes()

    def save(self, json_path):
        """Save database to JSON file."""
        data = {
            "version": 2,
            "description": "KzGrids buff/debuff database v2",
            "buffs": self.buffs
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================================
# BUFF EDIT DIALOG
# ============================================================================
class BuffEditDialog(tk.Toplevel):
    """Dialog for adding/editing buff entries."""

    DIALOG_WIDTH = 450
    DIALOG_HEIGHT = 560

    def __init__(self, parent, title, categories, buff=None, validate=None):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        action = title.split()[0] if title else "OK"
        self._action_label = "Save" if action == "Edit" else action

        self.categories = categories
        self.result = None
        self._validate = validate
        self.create_widgets(buff)

        app_window = parent.winfo_toplevel()
        restore_window_position(self, 'buff_edit_dialog',
                                self.DIALOG_WIDTH, self.DIALOG_HEIGHT,
                                app_window, resizable=False)
        bind_window_position_save(self, 'buff_edit_dialog', save_size=False)
        self.deiconify()

    def create_widgets(self, buff):
        header_text = f"{self._action_label.upper()} BUFF"
        create_dialog_header(self, header_text, MODULE_COLORS['grids'])

        frame = ttk.Frame(self, padding=PAD_INNER)
        frame.pack(fill='both', expand=True)

        # Name
        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky='w', pady=PAD_SMALL)
        self.name_var = tk.StringVar(value=buff['name'] if buff else "")
        ttk.Entry(frame, textvariable=self.name_var, width=35).grid(row=0, column=1, sticky='w', pady=PAD_SMALL)

        # IDs
        ttk.Label(frame, text="ID(s):").grid(row=1, column=0, sticky='nw', pady=PAD_SMALL)
        id_frame = ttk.Frame(frame)
        id_frame.grid(row=1, column=1, sticky='w', pady=PAD_SMALL)

        self.ids_text = tk.Text(id_frame, width=25, height=10)
        style_tk_text(self.ids_text)
        self.ids_text.pack(side='left')

        if buff:
            ids = buff.get('ids', [])
            self.ids_text.insert('1.0', '\n'.join(str(i) for i in ids))

        ttk.Label(id_frame, text="One per line or\ncomma-separated",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(side='left', padx=PAD_TAB)

        # Category
        ttk.Label(frame, text="Category:").grid(row=2, column=0, sticky='w', pady=PAD_SMALL)
        self.category_var = tk.StringVar(value=buff.get('category', '') if buff else "")
        ttk.Combobox(frame, textvariable=self.category_var, values=self.categories, width=32).grid(row=2, column=1, sticky='w', pady=PAD_SMALL)

        # Type
        ttk.Label(frame, text="Type:").grid(row=3, column=0, sticky='w', pady=PAD_SMALL)
        initial_type = buff.get('type', 'buff') if buff else 'buff'
        self.type_var = tk.StringVar(value=initial_type)

        type_frame = ttk.Frame(frame)
        type_frame.grid(row=3, column=1, sticky='w', pady=PAD_SMALL)
        ttk.Radiobutton(type_frame, text="Buff", variable=self.type_var, value='buff').pack(side='left')
        ttk.Radiobutton(type_frame, text="Debuff", variable=self.type_var, value='debuff').pack(side='left', padx=PAD_TAB)
        ttk.Radiobutton(type_frame, text="Misc", variable=self.type_var, value='misc').pack(side='left', padx=PAD_TAB)

        # Stacking
        ttk.Label(frame, text="Stacking:").grid(row=4, column=0, sticky='w', pady=PAD_SMALL)
        self.stacking_var = tk.BooleanVar(value=buff.get('stacking', False) if buff else False)
        stack_frame = ttk.Frame(frame)
        stack_frame.grid(row=4, column=1, sticky='w', pady=PAD_SMALL)
        ttk.Checkbutton(stack_frame, text="This buff has stack levels",
                       variable=self.stacking_var,
                       command=self._on_stacking_changed,
                       bootstyle="success-round-toggle").pack(side='left')
        ttk.Label(stack_frame, text="(IDs ordered by stack)",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(side='left', padx=PAD_TAB)

        # Partial list
        self.partial_label = ttk.Label(frame, text="")
        self.partial_label.grid(row=5, column=0, sticky='w', pady=PAD_SMALL)
        self.partial_frame = ttk.Frame(frame)
        self.partial_frame.grid(row=5, column=1, sticky='w', pady=PAD_SMALL)
        self.partial_var = tk.BooleanVar(value=buff.get('partialList', False) if buff else False)
        ttk.Checkbutton(self.partial_frame, text="Partial list",
                       variable=self.partial_var,
                       command=self._on_partial_changed,
                       bootstyle="info-round-toggle").pack(side='left')
        ttk.Label(self.partial_frame, text="(IDs don't start from stack 1)",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(side='left', padx=PAD_TAB)

        # Stack Start
        self.start_label = ttk.Label(frame, text="Start at:")
        self.start_label.grid(row=6, column=0, sticky='w', pady=PAD_SMALL)
        self.stack_start_frame = ttk.Frame(frame)
        self.stack_start_frame.grid(row=6, column=1, sticky='w', pady=PAD_SMALL)

        self.stack_start_var = tk.IntVar(value=buff.get('stackStart', 1) if buff else 1)
        self.stack_start_spin = ttk.Spinbox(
            self.stack_start_frame, textvariable=self.stack_start_var,
            from_=1, to=99, width=5
        )
        self.stack_start_spin.pack(side='left')
        self.start_hint = ttk.Label(self.stack_start_frame, text="",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL)
        self.start_hint.pack(side='left', padx=PAD_TAB)

        # Stack End
        self.end_label = ttk.Label(frame, text="End at:")
        self.end_label.grid(row=7, column=0, sticky='w', pady=PAD_SMALL)
        self.stack_end_frame = ttk.Frame(frame)
        self.stack_end_frame.grid(row=7, column=1, sticky='w', pady=PAD_SMALL)

        default_end = buff.get('stackEnd', 0) if buff else 0
        self.stack_end_var = tk.IntVar(value=default_end)
        self.stack_end_spin = ttk.Spinbox(
            self.stack_end_frame, textvariable=self.stack_end_var,
            from_=0, to=99, width=5
        )
        self.stack_end_spin.pack(side='left')
        ttk.Label(self.stack_end_frame, text="Last stack level to show (0 = show all)",
                 foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(side='left', padx=PAD_TAB)

        self._on_stacking_changed()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=PAD_SECTION_GAP)
        ttk.Button(btn_frame, text="Cancel", command=self.on_cancel,
                   width=10, bootstyle='secondary').pack(side='left', padx=PAD_SMALL)
        ttk.Button(btn_frame, text=self._action_label, command=self.on_ok,
                   width=10, bootstyle='success').pack(side='left', padx=PAD_SMALL)

        self.bind('<Return>', self._on_return)
        self.bind('<Escape>', lambda e: self.on_cancel())

    def _on_return(self, event):
        if event.widget == self.ids_text:
            return
        self.on_ok()

    def parse_ids(self):
        text = self.ids_text.get('1.0', 'end').strip()
        parts = re.split(r'[\n,]+', text)
        ids, rejected = [], []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                rejected.append(part)
        return ids, rejected

    def _on_stacking_changed(self):
        if self.stacking_var.get():
            self.partial_label.grid()
            self.partial_frame.grid()
            self.partial_frame.winfo_children()[0].configure(state='normal')
            self.start_label.grid()
            self.stack_start_frame.grid()
            self.stack_start_spin.configure(state='normal')
            self._on_partial_changed()
        else:
            self.partial_label.grid_remove()
            self.partial_frame.grid_remove()
            self.start_label.grid_remove()
            self.stack_start_frame.grid_remove()
            self.end_label.grid_remove()
            self.stack_end_frame.grid_remove()

    def _on_partial_changed(self):
        if self.partial_var.get():
            self.start_hint.configure(text="First ID = this stack level")
            self.stack_end_spin.configure(state='disabled')
            self.end_label.grid_remove()
            self.stack_end_frame.grid_remove()
        else:
            self.start_hint.configure(text="Track from this stack level")
            self.stack_end_spin.configure(state='normal')
            self.end_label.grid()
            self.stack_end_frame.grid()

    def on_ok(self):
        ids, rejected = self.parse_ids()
        if rejected:
            preview = ', '.join(rejected[:5]) + ('...' if len(rejected) > 5 else '')
            if Messagebox.yesno(
                f"These entries weren't valid numbers and will be skipped:\n\n"
                f"{preview}\n\nSave anyway?",
                title="Invalid IDs"
            ) != "Yes":
                return
        if not ids:
            Messagebox.show_error("Enter at least one buff ID — find IDs on AoC database sites.",
                                  title="Missing Buff ID")
            return

        name = self.name_var.get().strip()
        if not name:
            Messagebox.show_error("Give this buff a name so you can find it later.",
                                  title="Missing Name")
            return

        category = self.category_var.get().strip()
        if not category:
            Messagebox.show_error("Pick a category to keep the database organized.",
                                  title="Missing Category")
            return

        buff_type = self.type_var.get()
        is_stacking = self.stacking_var.get()

        self.result = {
            'name': name,
            'ids': ids,
            'category': category,
            'type': buff_type
        }

        if is_stacking:
            self.result['stacking'] = True
            is_partial = self.partial_var.get()
            stack_start = self.stack_start_var.get()
            if is_partial:
                self.result['partialList'] = True
                if stack_start != 1:
                    self.result['stackStart'] = stack_start
            else:
                if stack_start != 1:
                    self.result['stackStart'] = stack_start
                stack_end = self.stack_end_var.get()
                if stack_end > 0:
                    self.result['stackEnd'] = stack_end

        if self._validate:
            error = self._validate(self.result)
            if error:
                Messagebox.show_error(error, title="Can't Save")
                self.result = None
                return

        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def format_ids_display(ids, max_show=3):
    """Format a list of IDs for display, truncating if needed."""
    if len(ids) <= max_show:
        return ','.join(str(i) for i in ids)
    return ','.join(str(i) for i in ids[:max_show]) + f"...+{len(ids)-max_show}"


# ============================================================================
# DATABASE EDITOR TAB
# ============================================================================
class DatabaseEditorTab(ttk.Frame):
    """Database editor panel for the main application."""

    def __init__(self, parent, database, assets_path, on_modified=None, get_grids=None, toast=None):
        super().__init__(parent)

        self.database = database
        self.assets_path = assets_path
        self.on_modified = on_modified
        self._get_grids = get_grids
        self.toast = toast
        self.modified = False

        self.sort_column = 'type'
        self.sort_reverse = False

        self._debounced_refresh = debounced_callback(self, 200, self.refresh_list)

        self.create_widgets()
        self.update_categories()
        self.refresh_list()

    def create_widgets(self):
        # Filter frame
        filter_frame = ttk.Frame(self, padding=PAD_SMALL)
        filter_frame.pack(fill='x')

        ttk.Label(filter_frame, text="Search:").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._debounced_refresh())
        ttk.Entry(filter_frame, textvariable=self.search_var, width=20).pack(side='left', padx=PAD_SMALL)

        ttk.Label(filter_frame, text="Category:").pack(side='left', padx=(PAD_TAB, 0))
        self.category_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(filter_frame, textvariable=self.category_var,
                                           values=["All"], width=18, state='readonly')
        self.category_combo.pack(side='left', padx=PAD_SMALL)
        self.category_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_list())
        self.category_combo.bind('<Button-3>', self._show_category_menu)

        ttk.Label(filter_frame, text="Type:").pack(side='left', padx=(PAD_TAB, 0))
        self.type_var = tk.StringVar(value="All")
        type_combo = ttk.Combobox(filter_frame, textvariable=self.type_var,
                                  values=["All", "Buff", "Debuff", "Misc"], width=10, state='readonly')
        type_combo.pack(side='left', padx=PAD_SMALL)
        self.type_var.trace_add('write', lambda *a: self.refresh_list())

        self.count_var = tk.StringVar(value="0 entries")
        ttk.Label(filter_frame, textvariable=self.count_var).pack(side='right', padx=PAD_TAB)

        # Tree view
        list_frame = ttk.Frame(self, padding=PAD_SMALL)
        list_frame.pack(fill='both', expand=True)

        columns = ('name', 'ids', 'category', 'type', 'stacking', 'grids')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='browse')
        # Force dark bg on empty area below entries — must use after_idle
        # so it applies after ttkbootstrap finishes its theme configuration
        def _fix_tree_bg():
            s = ttk.Style()
            bg = TK_COLORS['bg']
            s.configure('Treeview', fieldbackground=bg, background=bg)
        self.tree.after_idle(_fix_tree_bg)

        self.tree.heading('name', text='Name', command=lambda: self.sort_by('name'))
        self.tree.heading('ids', text='ID(s)', command=lambda: self.sort_by('ids'))
        self.tree.heading('category', text='Category', command=lambda: self.sort_by('category'))
        self.tree.heading('type', text='Type', command=lambda: self.sort_by('type'))
        self.tree.heading('stacking', text='Stack', command=lambda: self.sort_by('stacking'))
        self.tree.heading('grids', text='Grids', command=lambda: self.sort_by('grids'))

        self.tree.column('name', width=220, minwidth=100, stretch=True, anchor='w')
        self.tree.column('ids', width=180, minwidth=80, stretch=True, anchor='w')
        self.tree.column('category', width=120, minwidth=80, stretch=True, anchor='w')
        self.tree.column('type', width=60, minwidth=50, stretch=False, anchor='center')
        self.tree.column('stacking', width=50, minwidth=40, stretch=False, anchor='center')
        self.tree.column('grids', width=45, minwidth=35, stretch=False, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.tree.tag_configure('evenrow', background=TK_COLORS['bg'])
        self.tree.tag_configure('oddrow', background=TK_COLORS['bg'])

        self.tree.bind('<Double-1>', lambda e: self.edit_buff())
        self.tree.bind('<Return>', lambda e: self.edit_buff())
        self.tree.bind('<Delete>', lambda e: self.delete_buff())

        # Button frame
        btn_frame = ttk.Frame(self, padding=PAD_SMALL)
        btn_frame.pack(fill='x')

        save_btn = ttk.Button(btn_frame, text="Save Database", command=self.save)
        save_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(save_btn, "Save all buff entries to database file")
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=PAD_TAB)

        add_btn = ttk.Button(btn_frame, text="Add", command=self.add_buff, width=BTN_SMALL)
        add_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(add_btn, "Create a new buff entry")
        edit_btn = ttk.Button(btn_frame, text="Edit", command=self.edit_buff, width=BTN_SMALL)
        edit_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(edit_btn, "Edit the selected buff entry")
        del_btn = ttk.Button(btn_frame, text="Delete", command=self.delete_buff, width=BTN_SMALL)
        del_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(del_btn, "Delete the selected buff entry")
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=PAD_TAB)
        imp_btn = ttk.Button(btn_frame, text="Import...", command=self.import_buffs, width=BTN_MEDIUM)
        imp_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(imp_btn, "Import buff entries from a JSON file")
        exp_btn = ttk.Button(btn_frame, text="Export...", command=self.export_buffs, width=BTN_MEDIUM)
        exp_btn.pack(side='left', padx=PAD_XS)
        add_tooltip(exp_btn, "Export selected buffs to a JSON file")


    def update_categories(self):
        """Update category dropdown with current categories."""
        self.category_combo['values'] = ["All"] + self.database.categories

    def _get_grid_usage(self):
        """Build a dict of entry_name → count of grids referencing it."""
        if not self._get_grids:
            return {}
        usage = {}
        for grid in self._get_grids():
            primary_ids = list(grid.get('whitelist', []))
            for val in grid.get('slotAssignments', {}).values():
                if isinstance(val, list):
                    primary_ids.extend(v for v in val if isinstance(v, int))
                elif isinstance(val, int):
                    primary_ids.append(val)
            seen_entries = set()
            for pid in primary_ids:
                entry = self.database.by_id.get(pid)
                if entry:
                    seen_entries.add(entry['name'])
            for name in seen_entries:
                usage[name] = usage.get(name, 0) + 1
        return usage

    def refresh_list(self):
        """Refresh the buff list based on current filters."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        search = self.search_var.get().lower()
        category = self.category_var.get()
        type_filter = self.type_var.get()

        buff_type = TYPE_FILTER_MAP.get(type_filter)

        filtered = self.database.search(
            search,
            category if category != "All" else None,
            buff_type=buff_type
        )
        grid_usage = self._get_grid_usage()
        filtered.sort(key=lambda b: self._get_sort_key(b, grid_usage), reverse=self.sort_reverse)

        for i, buff in enumerate(filtered):
            ids = buff.get('ids', [])
            ids_str = format_ids_display(ids)

            type_str = buff.get('type', 'buff').capitalize()
            if buff.get('stacking', False):
                stack_start = buff.get('stackStart', 1)
                if buff.get('partialList', False):
                    stack_str = f"P:{stack_start}+" if stack_start != 1 else "P"
                else:
                    stack_str = f"x{stack_start}+" if stack_start != 1 else "Yes"
            else:
                stack_str = ""

            name = buff.get('name', '')
            count = grid_usage.get(name, 0)
            grids_str = str(count) if count > 0 else ""

            row_tag = 'oddrow' if i % 2 else 'evenrow'
            self.tree.insert('', 'end', values=(
                name,
                ids_str,
                buff.get('category', ''),
                type_str,
                stack_str,
                grids_str
            ), tags=(row_tag,))

        has_filters = search or category != "All" or type_filter != "All"
        if len(filtered) == 0 and has_filters:
            self.count_var.set("0 entries \u2014 try adjusting filters")
            self.tree.insert('', 'end', values=("No matches found", "", "", "", "", ""),
                             tags=('placeholder',))
            self.tree.tag_configure('placeholder', foreground=THEME_COLORS['muted'])
        else:
            self.count_var.set(f"{len(filtered)} / {len(self.database.grouped_buffs)} entries")

    def sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self.refresh_list()

    def _get_sort_key(self, buff, grid_usage=None):
        name = buff.get('name', '').lower()
        if self.sort_column == 'ids':
            ids = buff.get('ids', [])
            return (ids[0] if ids else 0, name)
        elif self.sort_column == 'name':
            return (name,)
        elif self.sort_column == 'category':
            return (buff.get('category', '').lower(), name)
        elif self.sort_column == 'type':
            return ({'buff': 0, 'debuff': 1, 'misc': 2}.get(buff.get('type', 'buff'), 0), name)
        elif self.sort_column == 'stacking':
            return (0 if buff.get('stacking', False) else 1, name)
        elif self.sort_column == 'grids':
            if grid_usage is None:
                grid_usage = self._get_grid_usage()
            return (-grid_usage.get(buff.get('name', ''), 0), name)
        return ('',)

    def _get_selected_buff(self):
        """Get currently selected buff and its IDs."""
        selection = self.tree.selection()
        if not selection:
            return None, None
        item = self.tree.item(selection[0])
        buff_name = item['values'][0]
        buff_type = item['values'][3].lower()

        for buff in self.database.grouped_buffs:
            if buff['name'] == buff_name and buff.get('type', 'buff') == buff_type:
                return buff, buff.get('ids', [])
        return None, None

    def _check_id_collision(self, new_ids, exclude_ids=None):
        """Check if any IDs already exist in database."""
        exclude = set(exclude_ids or [])
        for buff in self.database.buffs:
            existing = set(buff.get('ids', [])) - exclude
            overlap = new_ids & existing
            if overlap:
                return overlap
        return None

    def _make_add_validator(self):
        """Create validator for add/duplicate: check ID collision and name uniqueness."""
        def validate(result):
            overlap = self._check_id_collision(set(result['ids']))
            if overlap:
                return f"ID(s) {overlap} already used by another buff."
            if self.database.get_entry_by_name(result['name']):
                return f"An entry named '{result['name']}' already exists."
            return None
        return validate

    def add_buff(self):
        """Add a new buff entry."""
        dialog = BuffEditDialog(self.winfo_toplevel(), "Add Buff", self.database.categories,
                                validate=self._make_add_validator())
        self.winfo_toplevel().wait_window(dialog)

        if dialog.result:
            self.database.add_buff(dialog.result)
            self._set_modified()
            self.update_categories()
            self.refresh_list()
            self.toast.show(f"Added: {dialog.result['name']}", 'success')

    def edit_buff(self):
        """Edit selected buff entry."""
        buff, old_ids = self._get_selected_buff()
        if buff is None:
            Messagebox.show_warning("Select a buff to edit.", title="No Selection")
            return

        old_name = buff['name']
        def validate_edit(result):
            overlap = self._check_id_collision(set(result['ids']), exclude_ids=old_ids)
            if overlap:
                return f"ID(s) {overlap} already used by another buff."
            if result['name'] != old_name and self.database.get_entry_by_name(result['name']):
                return f"An entry named '{result['name']}' already exists."
            return None

        dialog = BuffEditDialog(self.winfo_toplevel(), "Edit Buff", self.database.categories, buff,
                                validate=validate_edit)
        self.winfo_toplevel().wait_window(dialog)

        if dialog.result:
            self.database.update_buff(old_ids, dialog.result)
            self._set_modified()
            self.update_categories()
            self.refresh_list()
            self.toast.show(f"Updated: {dialog.result['name']}", 'success')

    def delete_buff(self):
        """Delete selected buff entry."""
        buff, ids = self._get_selected_buff()
        if buff is None:
            Messagebox.show_warning("Select a buff to delete.", title="No Selection")
            return

        ids_str = format_ids_display(ids)

        if Messagebox.yesno(f"Delete '{buff['name']}' (IDs: {ids_str})?", title="Confirm Delete") == "Yes":
            self.database.remove_buff(ids)
            self._set_modified()
            self.update_categories()
            self.refresh_list()
            self.toast.show(f"Deleted: {buff['name']}", 'info')

    def import_buffs(self):
        """Import buffs from JSON file."""
        path = filedialog.askopenfilename(
            title="Import Buff List",
            filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            import_buffs = data if isinstance(data, list) else data.get('buffs', [])
            if not import_buffs:
                Messagebox.show_warning("No buff entries found in this file.\n\nExpected a .json file exported from Kaz Grids.", title="Warning")
                return

            existing_ids = set()
            for buff in self.database.buffs:
                for bid in buff.get('ids', []):
                    existing_ids.add(bid)

            added = 0
            skipped = 0

            for buff in import_buffs:
                buff_ids = buff.get('ids', [buff.get('id')] if 'id' in buff else [])
                if any(bid in existing_ids for bid in buff_ids):
                    skipped += 1
                else:
                    if 'id' in buff and 'ids' not in buff:
                        buff['ids'] = [buff['id']]
                        del buff['id']
                    if 'isDebuff' in buff:
                        if 'type' not in buff:
                            buff['type'] = 'debuff' if buff['isDebuff'] else 'buff'
                        del buff['isDebuff']
                    if 'type' not in buff:
                        buff['type'] = 'buff'

                    self.database.add_buff(buff)
                    for bid in buff_ids:
                        existing_ids.add(bid)
                    added += 1

            self._set_modified()
            self.update_categories()
            self.refresh_list()

            msg = f"Imported {added} buffs"
            if skipped > 0:
                msg += f" ({skipped} duplicates skipped)"
            self.toast.show(msg, 'success')
            Messagebox.show_info(msg, title="Import Complete")

        except (IOError, OSError, json.JSONDecodeError, ValueError) as e:
            Messagebox.show_error(f"Failed to import buffs.\n\nThe file may be damaged or in an unexpected format.\n\n({e})", title="Error")

    def export_buffs(self):
        """Export filtered buffs to JSON file."""
        search = self.search_var.get().lower()
        category = self.category_var.get()
        type_filter = self.type_var.get()

        buff_type = TYPE_FILTER_MAP.get(type_filter)

        export_list = self.database.search(
            search,
            category if category != "All" else None,
            buff_type=buff_type
        )

        if not export_list:
            Messagebox.show_warning("No buffs match the current filters. Adjust your search or category filter and try again.", title="Nothing to Export")
            return

        default_name = "Db_export"
        if category != "All":
            default_name = f"Db_{category.replace(' ', '_').replace('#', '')}"

        path = filedialog.asksaveasfilename(
            title="Export Buff List",
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if not path:
            return

        try:
            data = {
                "version": 2,
                "description": "KzGrids buff list export",
                "buffs": export_list
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.toast.show(f"Exported {len(export_list)} buffs", 'success')
            Messagebox.show_info(f"Exported {len(export_list)} buffs to:\n{path}", title="Export Complete")
        except (IOError, OSError, ValueError, TypeError) as e:
            Messagebox.show_error(f"Failed to export buffs.\n\nCheck that the destination isn't read-only.\n\n({e})", title="Error")

    def save(self):
        """Save database to file."""
        self.assets_path.mkdir(exist_ok=True)
        db_path = self.assets_path / "Database.json"

        try:
            self.database.save(db_path)
            self.modified = False
            self.toast.show("Database saved", 'success')
        except (IOError, OSError) as e:
            Messagebox.show_error(f"Failed to save the buff database.\n\nCheck that the file isn't in use by another program.\n\n({e})", title="Error")

    def _show_category_menu(self, event):
        """Show right-click context menu on category dropdown."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename Category", command=self._rename_category)
        menu.tk_popup(event.x_root, event.y_root)

    def _rename_category(self):
        """Rename the currently selected category."""
        old_name = self.category_var.get()
        if old_name == "All":
            Messagebox.show_error("Select a specific category first, not 'All'.", title="No Category Selected")
            return

        new_name = Querybox.get_string(
            prompt=f"Rename '{old_name}' to:",
            title="Rename Category",
            parent=self.winfo_toplevel()
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if new_name in self.database.categories:
            Messagebox.show_error(f"Category '{new_name}' already exists.", title="Name Taken")
            return

        self.database.rename_category(old_name, new_name)
        self.category_var.set(new_name)
        self.update_categories()
        self.refresh_list()
        self._set_modified()

    def _set_modified(self):
        self.modified = True
        if self.on_modified:
            self.on_modified()
