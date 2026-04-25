"""
Kaz Grids — Grid Editor Panel
Grid configuration UI: add/edit/delete grids, whitelist editing, slot assignment.
"""

import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

from .grid_dialogs import AddGridWizard, BuffSelectorDialog, SlotAssignmentDialog
from .grid_model import (
    create_default_grid, validate_grid, parse_resolution,
    MAX_TOTAL_SLOTS, MAX_ROWS, MAX_COLS, SCREEN_MAX_X, SCREEN_MAX_Y,
    CLAMP_SPECS,
)
from .ui_helpers import (
    FONT_HEADING, FONT_BODY, FONT_BODY_LG, FONT_SMALL, FONT_SMALL_BOLD, FONT_FORM_LABEL, FONT_SYMBOL,
    THEME_COLORS, TK_COLORS, _RETRO_COLORS, GRID_TYPE_COLORS,
    SCANLINE_ALPHA,
    BTN_MEDIUM,
    PAD_TAB, PAD_ROW, PAD_XS, PAD_MICRO, PAD_SMALL, PAD_MID, PAD_LF,
    PAD_LIST_ITEM, PAD_SECTION_GAP, PAD_BUTTON_GAP,
)
from .ui_widgets import (
    blend_alpha, CollapsibleSection, add_tooltip, bind_card_events,
    bind_label_press_effect, bind_label_hover_colors,
)
from .ui_components import create_scrollable_frame, DragReorderManager
from .settings_manager import get_setting
from ttkbootstrap.dialogs import Messagebox


# ============================================================================
# SHARED HELPERS
# ============================================================================

def draw_grid_cells(canvas, rows, cols, type_color, area_w, area_h, tag='cells'):
    """Draw a miniature grid of colored rectangles on *canvas*."""
    canvas.delete(tag)
    cell_border = _RETRO_COLORS['pixel_border']
    display_rows = min(rows, 5)
    display_cols = min(cols, 5)
    cell = 7
    gap = 2
    if rows == 1 and cols == 1:
        cell = 14
    while display_rows * cell + (display_rows - 1) * gap > area_h - 8 and cell > 3:
        cell -= 1
    while display_cols * cell + (display_cols - 1) * gap > area_w - 16 and cell > 3:
        cell -= 1
    total_w = display_cols * cell + (display_cols - 1) * gap
    total_h = display_rows * cell + (display_rows - 1) * gap
    sx = (area_w - total_w) // 2
    sy = (area_h - total_h) // 2
    for r in range(display_rows):
        for c in range(display_cols):
            x = sx + c * (cell + gap)
            y = sy + r * (cell + gap)
            canvas.create_rectangle(x, y, x + cell, y + cell,
                                    fill=type_color, outline=cell_border, tags=tag)


# ============================================================================
# GRID EDITOR PANEL
# ============================================================================
class GridEditorPanel(ttk.Frame):
    """A collapsible grid editor card.

    Collapsed: shows name + badge + dims + enabled toggle + × delete
    Expanded: Name row, Position & Size, Timer Display, Mode Options
    """

    def __init__(self, parent, database, grid_config, on_delete=None, initially_open=False,
                 get_total_slots=None, on_resize=None, on_whitelist_changed=None):
        super().__init__(parent)
        self.database = database
        self.grid_config = grid_config
        self.on_delete = on_delete
        self._get_total_slots = get_total_slots
        self._on_resize = on_resize
        self._on_whitelist_changed = on_whitelist_changed

        grid_type = grid_config.get('type', 'player')
        self._accent_color = GRID_TYPE_COLORS.get(grid_type, GRID_TYPE_COLORS['player'])

        card = tk.Frame(self,
                        highlightbackground=self._accent_color,
                        highlightcolor=self._accent_color,
                        highlightthickness=1)
        card.pack(fill='x')

        # Drag handle
        self.drag_handle = ttk.Label(card, text=" \u2630 ", font=FONT_BODY_LG,
                                      foreground=THEME_COLORS['muted'], cursor='fleur')
        self.drag_handle.pack(side='left', fill='y', padx=(PAD_MICRO, 0))
        self.drag_handle.bind('<Enter>', lambda e: self.drag_handle.config(
            foreground=THEME_COLORS['heading']))
        self.drag_handle.bind('<Leave>', lambda e: self.drag_handle.config(
            foreground=THEME_COLORS['muted']))

        self.section = CollapsibleSection(
            card, title=grid_config.get('id', 'Grid'),
            badge_text=grid_type,
            badge_color=self._accent_color,
            initially_open=initially_open,
        )
        self.section.pack(side='left', fill='x', expand=True,
                          padx=PAD_ROW, pady=(PAD_BUTTON_GAP, PAD_ROW))

        self._build_header_widgets()

        content_wrapper = ttk.Frame(self.section.content)
        content_wrapper.pack(fill='x')
        settings_col = ttk.Frame(content_wrapper)
        settings_col.pack(side='left', fill='x', expand=True)

        self._preview_canvas = tk.Canvas(
            content_wrapper, width=70, height=70,
            bg=TK_COLORS['bg'], highlightthickness=0)
        self._preview_canvas.pack(side='right', padx=(PAD_XS, 0), pady=PAD_XS)

        self.type_var = tk.StringVar()
        self.mode_var = tk.StringVar()

        self._build_top_row(settings_col)
        self._build_icon_row(settings_col)
        self._build_info_and_dynamic(settings_col)

        self.load_from_config()

        bind_card_events(card, self._accent_color)
        self._card = card

    def _build_header_widgets(self):
        """Pack right-side header controls: × delete, Enabled toggle, X/Y, mode button."""
        cfg = self.grid_config
        header = self.section.header_frame

        self.enabled_var = tk.BooleanVar(value=True)
        delete_label = ttk.Label(header, text="×",
                                 font=FONT_SYMBOL, foreground=THEME_COLORS['muted'],
                                 cursor='hand2', takefocus=True,
                                 padding=(PAD_XS, PAD_MICRO))
        delete_label.pack(side='right', padx=(PAD_XS, 0))
        for seq in ('<Button-1>', '<Return>', '<space>'):
            delete_label.bind(seq, lambda e: self.delete_grid())
        bind_label_hover_colors(delete_label, THEME_COLORS['muted'], THEME_COLORS['danger'])
        bind_label_press_effect(delete_label, THEME_COLORS['danger'])
        add_tooltip(delete_label, "Delete this grid")
        ttk.Checkbutton(header, text="Enabled",
                        variable=self.enabled_var,
                        bootstyle="success-round-toggle").pack(side='right', padx=(0, PAD_XS))

        pos_frame = ttk.Frame(header)
        pos_frame.pack(side='right', padx=(0, PAD_LF))
        self.x_var = tk.StringVar(value=str(cfg.get('x', 0)))
        self._x_spin = self._add_str_spin(pos_frame, "X:", self.x_var, 0, SCREEN_MAX_X,
                                          "Horizontal position on screen (pixels from left edge)",
                                          padx=(PAD_MICRO, PAD_MID))
        self.y_var = tk.StringVar(value=str(cfg.get('y', 0)))
        self._y_spin = self._add_str_spin(pos_frame, "Y:", self.y_var, 0, SCREEN_MAX_Y,
                                          "Vertical position on screen (pixels from top edge)",
                                          padx=(PAD_MICRO, 0))

        self._mode_btn = ttk.Button(header, text="Tracked Buffs...",
                                     command=self._on_mode_btn_click, width=12,
                                     bootstyle='info-outline')
        self._mode_btn.pack(side='right', padx=(0, PAD_LF))

    def _add_str_spin(self, parent, label, var, lo, hi, tooltip, padx, width=5, command=None):
        """Spinbox bound to a StringVar (vs IntVar in _add_spinbox).

        If *command* is provided, also binds <FocusOut>.
        """
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        kwargs = {'from_': lo, 'to': hi, 'textvariable': var, 'width': width}
        if command is not None:
            kwargs['command'] = command
        spin = ttk.Spinbox(parent, **kwargs)
        spin.pack(side='left', padx=padx)
        if command is not None:
            spin.bind('<FocusOut>', lambda e: command())
        add_tooltip(spin, tooltip)
        return spin

    def _build_top_row(self, parent):
        """Pack the Name + Rows + Cols controls."""
        cfg = self.grid_config
        top_row = ttk.Frame(parent)
        top_row.pack(fill='x', pady=(0, PAD_ROW))

        ttk.Label(top_row, text="Name:", font=FONT_SMALL_BOLD,
                  foreground=THEME_COLORS['body']).pack(side='left')
        self.id_var = tk.StringVar()
        self.id_var.trace_add('write', lambda *_: self.section.set_title(self.id_var.get() or 'Grid'))
        self._name_entry = ttk.Entry(top_row, textvariable=self.id_var, width=14)
        self._name_entry.pack(side='left', padx=(PAD_XS, PAD_MID))
        add_tooltip(self._name_entry, "Display name for this grid (shown in preview mode)")

        self._rows_var = tk.StringVar(value=str(cfg.get('rows', 1)))
        self._rows_spin = self._add_str_spin(top_row, "Rows:", self._rows_var, 1, MAX_ROWS,
                                             "Grid rows (height). Total slots across all grids cannot exceed 64.",
                                             padx=(PAD_MICRO, PAD_MID), width=4,
                                             command=lambda: self._on_dimension_changed('rows'))
        self._cols_var = tk.StringVar(value=str(cfg.get('cols', 5)))
        self._cols_spin = self._add_str_spin(top_row, "Cols:", self._cols_var, 1, MAX_COLS,
                                             "Grid columns (width). Total slots across all grids cannot exceed 64.",
                                             padx=(PAD_MICRO, 0), width=4,
                                             command=lambda: self._on_dimension_changed('cols'))

    def _build_icon_row(self, parent):
        """Pack icon size, gap, stack font, and the Timers / Flash toggle groups."""
        icon_row = ttk.Frame(parent)
        icon_row.pack(fill='x', pady=(0, PAD_ROW))
        self.icon_var, _ = self._add_spinbox(icon_row, "Icon:", 24, 64, 2,
            "Size of each buff icon in pixels (24-64)")
        self.gap_var, _ = self._add_spinbox(icon_row, "Gap:", -5, 10, 2,
            "Space between icons (-5 = overlapping, 0 = touching, 10 = spaced out)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        ttk.Separator(icon_row, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.stack_font_var, _ = self._add_spinbox(icon_row,
            "Stack Font:", 8, 24, 2, "Font size for stack counter at top-right of icons (8-24)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        self._timer_group = ttk.Frame(icon_row)
        self._timer_group.pack(side='left')
        ttk.Separator(self._timer_group, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.timers_var = tk.BooleanVar()
        timers_cb = ttk.Checkbutton(self._timer_group, text="Timers",
                                     variable=self.timers_var,
                                     bootstyle="success-round-toggle",
                                     command=self._on_timers_toggled)
        timers_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(timers_cb, "Display remaining duration below each buff icon")

        self._timer_options_frame = ttk.Frame(self._timer_group)
        self._timer_options_frame.pack(side='left')
        self.timer_font_var, _ = self._add_spinbox(self._timer_options_frame,
            "Font:", 8, 24, 2, "Font size for timer text below icons (8-24)")
        self.timer_y_offset_var, _ = self._add_spinbox(self._timer_options_frame,
            "Y Offset:", -10, 10, 2,
            "Shift timer text up/down relative to the icon (-10 to 10)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        self._flash_group = ttk.Frame(icon_row)
        self._flash_group.pack(side='left')
        ttk.Separator(self._flash_group, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.flashing_var = tk.BooleanVar()
        flash_cb = ttk.Checkbutton(self._flash_group, text="Flash",
                                    variable=self.flashing_var,
                                    bootstyle="success-round-toggle",
                                    command=self._on_flash_toggled)
        flash_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(flash_cb, "Icons flash when buff timer is about to expire")

        self._flash_threshold_frame = ttk.Frame(self._flash_group)
        self._flash_threshold_frame.pack(side='left')
        self.flash_threshold_var, _ = self._add_spinbox(
            self._flash_threshold_frame, "Under:", 0, 11, 2,
            "Icons flash when timer drops below this many seconds (0-11)",
            padx=(PAD_BUTTON_GAP, 0))
        ttk.Label(self._flash_threshold_frame, text="s",
                  foreground=THEME_COLORS['muted'],
                  font=FONT_SMALL).pack(side='left')

    def _build_info_and_dynamic(self, parent):
        """Pack whitelist/slot summary row and the Fill/Sort/Group dynamic options."""
        self._info_row = ttk.Frame(parent)
        self._info_row.pack(fill='x', pady=(0, PAD_ROW))

        self.whitelist_label = tk.StringVar(value="No buffs tracked — grid will show nothing")
        self.slots_label = tk.StringVar(value="0 of 0 slots assigned")
        self._info_label = ttk.Label(self._info_row, textvariable=self.whitelist_label,
                  foreground=THEME_COLORS['muted'], font=FONT_SMALL)
        self._info_label.pack(side='left', padx=(0, PAD_LF))
        self.whitelist_preview_var = tk.StringVar(value="")
        self.whitelist_preview_label = ttk.Label(
            parent, textvariable=self.whitelist_preview_var,
            foreground=THEME_COLORS['muted'], font=FONT_SMALL)

        self.dynamic_frame = ttk.Frame(parent)
        dyn_row = ttk.Frame(self.dynamic_frame)
        dyn_row.pack(fill='x', pady=(0, PAD_ROW))

        self.fill_var = tk.StringVar()
        self.fill_combo = self._add_combobox(dyn_row, "Fill:", self.fill_var, [], 10,
            lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"))

        self.sort_var = tk.StringVar()
        self._add_combobox(dyn_row, "Sort:", self.sort_var,
            ['shortest', 'longest', 'application'], 10,
            "How buffs are ordered (by shortest/longest remaining time, or order applied)")

        self.layout_var = tk.StringVar()
        self._add_combobox(dyn_row, "Group:", self.layout_var,
            ['buffFirst', 'debuffFirst', 'mixed'], 10,
            "In Buff First and Debuff First modes, misc effects always lead. In Mixed, all buffs sort together by time.",
            padx=(PAD_BUTTON_GAP, 0))

    def bind_reorder_keys(self, move_callback):
        """Bind Alt+Up/Down on the card for keyboard reorder."""
        self._card.bind('<Alt-Up>', lambda e: move_callback(self, -1))
        self._card.bind('<Alt-Down>', lambda e: move_callback(self, 1))
        self.section.header_frame.bind('<Alt-Up>', lambda e: move_callback(self, -1))
        self.section.header_frame.bind('<Alt-Down>', lambda e: move_callback(self, 1))

    def _add_spinbox(self, parent, label, from_, to, width, tooltip, padx=(PAD_BUTTON_GAP, PAD_TAB)):
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL).pack(side='left')
        var = tk.IntVar()
        vcmd = (self.register(lambda P, f=from_, t=to: self._validate_spinbox(P, f, t)), '%P')
        spin = ttk.Spinbox(parent, from_=from_, to=to, textvariable=var, width=width,
                           validate='key', validatecommand=vcmd)
        spin.pack(side='left', padx=padx)
        spin.bind('<FocusOut>', lambda e, v=var, lo=from_, hi=to: self._clamp_spinbox(v, lo, hi))
        add_tooltip(spin, tooltip)
        return var, spin

    @staticmethod
    def _validate_spinbox(value, from_, to):
        if value == '' or value == '-':
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _clamp_spinbox(var, from_, to):
        try:
            v = var.get()
        except tk.TclError:
            v = from_
        var.set(max(from_, min(to, v)))

    def _add_combobox(self, parent, label, var, values, width, tooltip, padx=(PAD_BUTTON_GAP, PAD_TAB)):
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL).pack(side='left')
        combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state='readonly')
        combo.pack(side='left', padx=padx)
        add_tooltip(combo, tooltip)
        return combo

    def load_from_config(self):
        """Populate all editor widgets from the current grid configuration dict."""
        cfg = self.grid_config
        self.id_var.set(cfg.get('id', 'Grid'))
        self.enabled_var.set(cfg.get('enabled', True))
        self.type_var.set(cfg.get('type', 'player').title())
        rows = cfg.get('rows', 1)
        cols = cfg.get('cols', 5)
        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        self.mode_var.set(cfg.get('slotMode', 'dynamic').title())
        self.x_var.set(min(cfg.get('x', 100), SCREEN_MAX_X))
        self.y_var.set(min(cfg.get('y', 400), SCREEN_MAX_Y))
        self.icon_var.set(min(cfg.get('iconSize', 56), 64))
        self.gap_var.set(max(-5, min(cfg.get('gap', -1), 10)))
        self.timers_var.set(cfg.get('showTimers', True))
        self.stack_font_var.set(cfg.get('stackFontSize', 14))
        self.timer_font_var.set(cfg.get('timerFontSize', 18))
        self.flash_threshold_var.set(cfg.get('timerFlashThreshold', 6))
        self.timer_y_offset_var.set(cfg.get('timerYOffset', 0))
        self.flashing_var.set(cfg.get('enableFlashing', True))
        self._on_timers_toggled()
        self._on_flash_toggled()
        self.fill_var.set(cfg.get('fillDirection', 'LR'))
        self.sort_var.set(cfg.get('sortOrder', 'longest'))
        self.layout_var.set(cfg.get('layout', 'buffFirst'))

        self._update_fill_options(rows, cols)

        if cfg.get('slotMode') == 'static':
            self.dynamic_frame.pack_forget()
            self._info_label.configure(textvariable=self.slots_label)
        else:
            self.dynamic_frame.pack(fill='x')
            self._info_label.configure(textvariable=self.whitelist_label)
        self._mode_btn.configure(text="Tracked Buffs...")

        self.update_labels()
        self._update_preview()

    def _update_preview(self):
        """Redraw the small grid shape preview in the card."""
        rows = self.grid_config.get('rows', 1)
        cols = self.grid_config.get('cols', 5)
        draw_grid_cells(self._preview_canvas, rows, cols,
                        self._accent_color, 70, 70)

    def save_to_config(self):
        """Write current widget values back into the grid configuration dict."""
        name = self.id_var.get().strip()
        if not name:
            self.grid_config['id'] = self.grid_config.get('id', 'Grid')
            self.id_var.set(self.grid_config['id'])
            self._name_entry.configure(bootstyle='danger')
            self._name_entry.after(600, lambda: self._name_entry.configure(bootstyle=''))
        else:
            self.grid_config['id'] = name
        self.grid_config['enabled'] = self.enabled_var.get()
        # Clamp numerics via shared spec
        var_map = {
            'rows': self._rows_var, 'cols': self._cols_var,
            'x': self.x_var, 'y': self.y_var,
            'iconSize': self.icon_var, 'gap': self.gap_var,
            'stackFontSize': self.stack_font_var,
            'timerFontSize': self.timer_font_var,
            'timerFlashThreshold': self.flash_threshold_var,
            'timerYOffset': self.timer_y_offset_var,
        }
        for key, var in var_map.items():
            _, lo, hi = CLAMP_SPECS[key]
            self.grid_config[key] = max(lo, min(int(var.get()), hi))
        self.grid_config['showTimers'] = self.timers_var.get()
        self.grid_config['enableFlashing'] = self.flashing_var.get()
        self.grid_config['fillDirection'] = self.fill_var.get()
        self.grid_config['sortOrder'] = self.sort_var.get()
        self.grid_config['layout'] = self.layout_var.get()

    def _format_buff_preview(self, ids, max_show=4):
        """Comma-separated preview of buff names for up to *max_show* IDs."""
        names = [
            (self.database.by_id.get(bid) or {}).get('name', f"(missing #{bid})")
            for bid in ids[:max_show]
        ]
        extra = f" + {len(ids) - max_show} more" if len(ids) > max_show else ""
        return ", ".join(names) + extra

    def update_labels(self):
        """Refresh whitelist, slot assignment, and header summary labels."""
        cfg = self.grid_config
        wl = cfg.get('whitelist', [])
        rows = cfg.get('rows', 1)
        cols = cfg.get('cols', 5)

        self.whitelist_label.set(
            f"Tracking {len(wl)} buffs" if wl
            else "No buffs tracked \u2014 grid will show nothing"
        )

        sa = cfg.get('slotAssignments', {})
        assigned_ids = []
        for v in sa.values():
            if isinstance(v, list):
                assigned_ids.extend(b for b in v if b)
            elif v:
                assigned_ids.append(v)
        configured = sum(1 for v in sa.values() if v)
        self.slots_label.set(f"{configured} of {rows * cols} slots assigned")

        preview_ids = assigned_ids if cfg.get('slotMode') == 'static' else wl
        if preview_ids:
            self.whitelist_preview_var.set(self._format_buff_preview(preview_ids))
            self.whitelist_preview_label.pack(fill='x', pady=(0, PAD_BUTTON_GAP))
        else:
            self.whitelist_preview_var.set("")
            self.whitelist_preview_label.pack_forget()

        self.section.set_title(cfg.get('id', 'Grid'))
        self.section.set_summary(f"  {rows}x{cols} \u00B7 {cfg.get('slotMode', 'dynamic')}")

    def _on_mode_btn_click(self):
        if self.grid_config.get('slotMode') == 'static':
            self.edit_slots()
        else:
            self.edit_whitelist()

    def edit_whitelist(self):
        self.save_to_config()
        dialog = BuffSelectorDialog(
            self.winfo_toplevel(), self.database, "Edit Tracked Buffs",
            initial_ids=self.grid_config.get('whitelist', []),
            layout=self.grid_config.get('layout', 'mixed'),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.grid_config['whitelist'] = dialog.result
            self.update_labels()
            if self._on_whitelist_changed:
                self._on_whitelist_changed()

    def edit_slots(self):
        self.save_to_config()
        dialog = SlotAssignmentDialog(self.winfo_toplevel(), self.database, self.grid_config)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.grid_config['slotAssignments'] = dialog.result
            self.update_labels()
            if self._on_whitelist_changed:
                self._on_whitelist_changed()

    def delete_grid(self):
        if Messagebox.yesno(f"Delete grid '{self.id_var.get()}'?", title="Delete Grid") == "Yes":
            if self.on_delete:
                self.on_delete(self)

    def _on_timers_toggled(self):
        if self.timers_var.get():
            self._timer_options_frame.pack(side='left')
        else:
            self._timer_options_frame.pack_forget()

    def _on_flash_toggled(self):
        if self.flashing_var.get():
            self._flash_threshold_frame.pack(side='left')
        else:
            self._flash_threshold_frame.pack_forget()

    def _on_dimension_changed(self, dim):
        var = self._rows_var if dim == 'rows' else self._cols_var
        limit = MAX_ROWS if dim == 'rows' else MAX_COLS
        try:
            new_val = max(1, min(int(var.get()), limit))
        except (ValueError, tk.TclError):
            var.set(str(self.grid_config.get(dim, 1)))
            return
        old_val = self.grid_config.get(dim, 1)
        other_dim = self.grid_config.get('cols' if dim == 'rows' else 'rows', 1)
        if self._get_total_slots:
            old_total = old_val * other_dim
            other_slots = self._get_total_slots() - old_total
            if other_slots + new_val * other_dim > MAX_TOTAL_SLOTS:
                new_val = max(1, (MAX_TOTAL_SLOTS - other_slots) // other_dim)
                var.set(str(new_val))
        new_rows = new_val if dim == 'rows' else other_dim
        new_cols = other_dim if dim == 'rows' else new_val
        self._apply_dimension_change(new_rows, new_cols, old_val * other_dim)

    def _apply_dimension_change(self, new_rows, new_cols, old_total):
        new_total = new_rows * new_cols
        self.grid_config['rows'] = new_rows
        self.grid_config['cols'] = new_cols
        if self.grid_config.get('slotMode') == 'static' and new_total < old_total:
            sa = self.grid_config.get('slotAssignments', {})
            dropped = sum(len(v) for k, v in sa.items() if int(k) >= new_total and v)
            self.grid_config['slotAssignments'] = {
                k: v for k, v in sa.items() if int(k) < new_total
            }
            if dropped > 0:
                Messagebox.show_warning(
                    f"Grid resized: {dropped} buff(s) from removed slots were unassigned.",
                    title="Slots Trimmed"
                )
        if new_rows == 1 and new_cols == 1 and self.grid_config.get('slotMode') == 'dynamic':
            new_cols = 2
            self.grid_config['cols'] = new_cols
            self._cols_var.set('2')
        self._update_fill_options(new_rows, new_cols)
        self.update_labels()
        self._update_preview()
        if self._on_resize:
            self._on_resize()

    def _update_fill_options(self, rows, cols):
        current = self.fill_var.get()
        if rows == 1:
            self.fill_combo['values'] = ['LR', 'RL']
            if current not in ['LR', 'RL']:
                self.fill_var.set('LR')
                self.grid_config['fillDirection'] = 'LR'
        elif cols == 1:
            self.fill_combo['values'] = ['TB', 'BT']
            if current not in ['TB', 'BT']:
                self.fill_var.set('BT')
                self.grid_config['fillDirection'] = 'BT'
        else:
            self.fill_combo['values'] = ['TL-BR', 'TR-BL', 'BL-TR', 'BR-TL']
            if current not in ['TL-BR', 'TR-BL', 'BL-TR', 'BR-TL']:
                self.fill_var.set('BL-TR')
                self.grid_config['fillDirection'] = 'BL-TR'


_FILL_DESCRIPTIONS = {
    'LR':    'Left to right — new buffs appear on the right',
    'RL':    'Right to left — new buffs appear on the left',
    'TB':    'Top to bottom — new buffs appear at the bottom',
    'BT':    'Bottom to top — new buffs appear at the top',
    'TL-BR': 'Top-left to bottom-right — fills from the top-left corner',
    'TR-BL': 'Top-right to bottom-left — fills from the top-right corner',
    'BL-TR': 'Bottom-left to top-right — fills from the bottom-left corner',
    'BR-TL': 'Bottom-right to top-left — fills from the bottom-right corner',
}

# ============================================================================
# GRIDS PANEL
# ============================================================================
class GridsPanel(ttk.Frame):
    """Grid editor panel — manages grid list and editor cards.

    Switches between empty state (no grids) and normal view (toolbar + cards).
    """

    def __init__(self, parent, database, on_modified=None):
        super().__init__(parent)
        self.database = database
        self.on_modified = on_modified

        self.grids = []
        self.grid_panels = []
        self._tip_dismissed = False
        self._build_done = False
        self._from_empty_state = False

        self._create_widgets()
        self.refresh_panels()

    def _create_widgets(self):
        """Build normal view (toolbar + scroll) and empty state frame."""
        # --- Normal view ---
        self._normal_view = ttk.Frame(self)

        toolbar = ttk.Frame(self._normal_view)
        toolbar.pack(fill='x', padx=PAD_TAB, pady=PAD_SMALL)
        ttk.Button(toolbar, text="+ Add Grid", command=self.add_grid,
                   width=BTN_MEDIUM).pack(side='left', padx=PAD_BUTTON_GAP)
        self.slot_count_label = tk.StringVar(value=f"0 / {MAX_TOTAL_SLOTS} slots")
        ttk.Label(toolbar, textvariable=self.slot_count_label,
                  font=FONT_SMALL, foreground=THEME_COLORS['muted']).pack(side='right')

        self._build_tip_bar()

        content = ttk.Frame(self._normal_view)
        content.pack(fill='both', expand=True, padx=PAD_SMALL, pady=PAD_SMALL)

        grids_container = ttk.Frame(content)
        grids_container.pack(fill='both', expand=True)
        outer, self.grids_frame, self.grids_canvas = create_scrollable_frame(
            grids_container)
        outer.pack(fill='both', expand=True)

        self._drag_manager = DragReorderManager(
            self.grids_canvas, self.grids_frame, self._reorder_grid)

        # --- Empty state ---
        self._empty_state = self._build_empty_state()

    def _build_tip_bar(self):
        """Build the contextual next-step guide (tip bar) shown above grids/empty state."""
        self._tip_frame = tk.Frame(self, bg=TK_COLORS['status_bg'],
                                    highlightbackground=TK_COLORS['border'],
                                    highlightcolor=TK_COLORS['border'],
                                    highlightthickness=1)
        tip_inner = tk.Frame(self._tip_frame, bg=TK_COLORS['status_bg'])
        tip_inner.pack(fill='x', padx=PAD_LF, pady=PAD_XS)

        self._tip_accent = tk.Frame(self._tip_frame, bg=THEME_COLORS['accent'], width=3)
        self._tip_accent.place(x=0, y=0, relheight=1)

        muted = THEME_COLORS['muted']
        bg = TK_COLORS['status_bg']
        self._step_badges = []
        self._step_labels = []
        for i, step_text in enumerate(["Set game folder below", "Add Grid", "Choose Tracked Buffs", "Build"]):
            if i > 0:
                ttk.Label(tip_inner, text="→", font=FONT_BODY,
                          foreground=muted).pack(side='left', padx=PAD_XS)
            badge = tk.Canvas(tip_inner, width=20, height=20,
                              bg=bg, highlightthickness=0)
            badge.pack(side='left', padx=(PAD_XS, 2))
            badge.create_oval(1, 1, 19, 19, fill='', outline=muted, tags='oval')
            badge.create_text(10, 10, text=str(i + 1), fill=muted,
                              font=FONT_SMALL, anchor='center', tags='num')
            lbl = ttk.Label(tip_inner, text=step_text, font=FONT_BODY, foreground=muted)
            lbl.pack(side='left')
            self._step_badges.append(badge)
            self._step_labels.append(lbl)

        dismiss_label = ttk.Label(tip_inner, text="×", font=FONT_BODY_LG,
                                   foreground=muted, cursor='hand2',
                                   takefocus=True)
        dismiss_label.pack(side='right', padx=(PAD_SMALL, 0))
        for seq in ('<Button-1>', '<Return>', '<space>'):
            dismiss_label.bind(seq, lambda e: self._dismiss_tip())
        bind_label_hover_colors(dismiss_label, muted, THEME_COLORS['heading'])
        bind_label_press_effect(dismiss_label)

    def _update_step_guide(self, done):
        """Update steps. done: list of bools per step. Done=green, first not-done=active, rest=muted."""
        done_tuple = tuple(done)
        if getattr(self, '_prev_step_state', None) == done_tuple:
            return
        self._prev_step_state = done_tuple

        muted = THEME_COLORS['muted']
        active_set = False
        for badge, lbl, is_done in zip(self._step_badges, self._step_labels, done):
            if is_done:
                badge.itemconfigure('oval', fill=THEME_COLORS['success'], outline=THEME_COLORS['success'])
                badge.itemconfigure('num', fill=TK_COLORS['bg'])
                lbl.configure(foreground=THEME_COLORS['success'])
            elif not active_set:
                badge.itemconfigure('oval', fill=THEME_COLORS['accent'], outline=THEME_COLORS['accent'])
                badge.itemconfigure('num', fill=TK_COLORS['bg'])
                lbl.configure(foreground=THEME_COLORS['body'])
                active_set = True
            else:
                badge.itemconfigure('oval', fill='', outline=muted)
                badge.itemconfigure('num', fill=muted)
                lbl.configure(foreground=muted)

    def _build_empty_state(self):
        """Create the empty state frame shown when no grids exist."""
        frame = ttk.Frame(self)
        center = ttk.Frame(frame)
        center.pack(expand=True)

        ttk.Label(center, text="No grids yet \u2014 pick a layout to start",
                  font=FONT_HEADING, foreground=THEME_COLORS['heading']).pack(
                      pady=(0, PAD_SECTION_GAP))

        self._empty_type_var = tk.StringVar(value="player")
        self._radio_player, self._radio_target = self._build_radio_row(
            center, "Source:", self._empty_type_var,
            [("Player", "player"), ("Target", "target")],
            command=self._redraw_empty_cards, pady=(0, PAD_XS))

        self._empty_mode_var = tk.StringVar(value="dynamic")
        self._radio_dynamic, self._radio_static = self._build_radio_row(
            center, "Mode:", self._empty_mode_var,
            [("Dynamic", "dynamic"), ("Static", "static")],
            command=None, pady=(0, PAD_TAB))

        cards_frame = ttk.Frame(center)
        cards_frame.pack(pady=(0, PAD_SECTION_GAP))

        presets = [
            ("1\u00d710 Bar", 1, 10, "dynamic"),
            ("10\u00d71 Bar", 10, 1, "dynamic"),
            ("3\u00d73 Grid", 3, 3, "dynamic"),
            ("1\u00d71 Slot", 1, 1, "static"),
            ("Custom", None, None, None),
        ]
        self._empty_cards = []
        for label, rows, cols, mode in presets:
            self._build_preset_card(cards_frame, label, rows, cols, mode)

        self._redraw_empty_cards()

        add_tooltip(self._radio_player, "Track buffs/debuffs on yourself")
        add_tooltip(self._radio_target, "Track buffs/debuffs on your current target")
        add_tooltip(self._radio_dynamic,
                    "Slots fill automatically as buffs activate. "
                    "You control fill direction, sort order, and grouping.")
        add_tooltip(self._radio_static,
                    "Each slot is pinned to specific buffs. "
                    "Shows the buff when active, stays empty when it's not.")
        _card_descriptions = {
            "1\u00d710 Bar": "Horizontal bar \u2014 great for tracking player buffs across the top",
            "10\u00d71 Bar": "Vertical bar \u2014 stack buffs along the side of your screen",
            "3\u00d73 Grid": "Compact grid \u2014 fits many buffs in a small area",
            "1\u00d71 Slot": "Single slot \u2014 pin one specific buff (always Static mode)",
            "Custom": "Open the Add Grid wizard to set custom rows, columns, and options",
        }
        for (card_canvas, _, _), (label, _, _, _) in zip(self._empty_cards, presets):
            if label in _card_descriptions:
                add_tooltip(card_canvas, _card_descriptions[label])

        return frame

    def _build_radio_row(self, parent, label_text, var, options, command, pady):
        """Pack a label + horizontal Radiobutton group; return the Radiobutton widgets."""
        frame = ttk.Frame(parent)
        frame.pack(pady=pady)
        ttk.Label(frame, text=label_text, font=FONT_SMALL, width=6,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        radios = []
        for text, value in options:
            rb = ttk.Radiobutton(frame, text=text, variable=var, value=value,
                                 command=command)
            rb.pack(side='left', padx=PAD_XS)
            radios.append(rb)
        return radios

    def _build_preset_card(self, parent, label, rows, cols, mode):
        """Create one preset shape card with click/focus highlight bindings."""
        bg = TK_COLORS['bg']
        border = TK_COLORS['border']
        accent = THEME_COLORS['accent']
        scanline = blend_alpha('#000000', bg, SCANLINE_ALPHA)
        card_w, card_h = 110, 110

        card = tk.Canvas(parent, width=card_w, height=card_h,
                         highlightthickness=1, highlightbackground=border,
                         bg=bg, cursor='hand2', takefocus=True)
        card.pack(side='left', padx=PAD_LF)
        card.create_rectangle(0, 0, card_w, card_h, fill=bg, outline='')
        for y in range(0, card_h, 3):
            card.create_line(0, y, card_w, y, fill=scanline)
        card.create_text(card_w // 2, card_h - 14, text=label, anchor='center',
                         fill=THEME_COLORS['muted'], font=FONT_SMALL)

        self._empty_cards.append((card, rows, cols))

        def _on_click(e, r=rows, c=cols, m=mode):
            if r is None:
                self._create_from_empty_state(r, c, m)
                return
            effective_mode = 'static' if (r == 1 and c == 1) else self._empty_mode_var.get()
            self._create_from_empty_state(r, c, effective_mode)

        def _highlight(e, color, c=card):
            c.configure(highlightbackground=color)

        card.bind('<Button-1>', _on_click)
        card.bind('<Return>', _on_click)
        card.bind('<space>', _on_click)
        card.bind('<ButtonPress-1>', lambda e: _highlight(e, accent), add='+')
        card.bind('<ButtonRelease-1>', lambda e: _highlight(e, border), add='+')
        card.bind('<FocusIn>', lambda e: _highlight(e, accent))
        card.bind('<FocusOut>', lambda e: _highlight(e, border))

    def _redraw_empty_cards(self):
        """Redraw grid shape previews on empty state cards using current type color."""
        type_color = GRID_TYPE_COLORS[self._empty_type_var.get()]
        card_w, card_h = 110, 110
        preview_h = card_h - 28  # area above the label

        for card, rows, cols in self._empty_cards:
            card.delete('cells')
            if rows is None:
                card.create_text(card_w // 2, preview_h // 2 + 10, text="+",
                                 anchor='center', fill=THEME_COLORS['heading'],
                                 font=FONT_HEADING, tags='cells')
                continue
            draw_grid_cells(card, rows, cols, type_color, card_w, preview_h)

    def _stagger_empty_cards(self):
        """Reveal empty state cards one by one with a staggered delay."""
        border = TK_COLORS['border']
        for card, _, _ in self._empty_cards:
            card.configure(highlightbackground=TK_COLORS['bg'])
            card.itemconfigure('all', state='hidden')

        def _reveal(idx):
            if idx >= len(self._empty_cards):
                return
            try:
                card = self._empty_cards[idx][0]
                card.itemconfigure('all', state='normal')
                card.configure(highlightbackground=border)
            except tk.TclError:
                return
            card.after(60, lambda: _reveal(idx + 1))

        if self._empty_cards:
            self._empty_cards[0][0].after(100, lambda: _reveal(0))

    def _dismiss_tip(self):
        """Dismiss the tip bar permanently for this session."""
        self._tip_dismissed = True
        self._tip_frame.pack_forget()

    def notify_build_done(self, aoc_installed):
        """Called after a successful build — mark step 4 complete and re-show panel."""
        self._build_done = True
        self._tip_dismissed = False
        self._update_tip()

    def notify_game_path_changed(self):
        """Called when the active game folder changes."""
        self._update_tip()

    def _update_tip(self):
        """Update step guide state and show/hide the tip panel."""
        if self._tip_dismissed:
            self._tip_frame.pack_forget()
            return

        has_game_path = bool(get_setting('game_path'))
        has_grids = bool(self.grids)

        needs_setup = False
        if has_grids:
            for g in self.grids:
                if g.get('slotMode') == 'static':
                    if not any(v for v in g.get('slotAssignments', {}).values()):
                        needs_setup = True
                        break
                elif not g.get('whitelist'):
                    needs_setup = True
                    break

        buffs_done = has_grids and not needs_setup
        self._update_step_guide([has_game_path, has_grids, buffs_done, self._build_done])

        ready = has_game_path and buffs_done
        self._tip_accent.configure(
            bg=THEME_COLORS['success'] if ready else THEME_COLORS['accent'])

        state_widget = self._normal_view if has_grids else self._empty_state
        self._tip_frame.pack_forget()
        self._tip_frame.pack(fill='x', padx=PAD_TAB, pady=(PAD_XS, PAD_XS),
                             before=state_widget)

    def _create_from_empty_state(self, rows, cols, mode):
        """Create a grid from the empty state preset shortcuts."""
        self._from_empty_state = True
        if rows is None:
            self.add_grid()
            return
        grid_type = self._empty_type_var.get()
        existing = {g['id'] for g in self.grids}
        base = f"{grid_type.title()}Grid"
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        grid_config = create_default_grid(
            grid_type=grid_type, rows=rows, cols=cols, mode=mode,
            grid_id=f"{base}{i}"
        )
        self.grids.append(grid_config)
        self._mark_modified()
        self.refresh_panels(expand_index=len(self.grids) - 1)

    def get_profile_data(self):
        """Return current grid configurations (save all panel values first)."""
        self.save_settings()
        return self.grids

    def _migrate_whitelist(self, whitelist, missing):
        """Normalize whitelist entries to primary spell IDs.

        Accepts legacy int IDs and legacy name strings. Orphans are appended
        to `missing` (list of strings) and dropped from the result.
        """
        result = []
        for item in whitelist:
            if isinstance(item, int):
                entry = self.database.by_id.get(item)
                if entry and entry.get('ids'):
                    result.append(entry['ids'][0])
                else:
                    missing.append(f"id:{item}")
            elif isinstance(item, str):
                entry = self.database.get_entry_by_name(item)
                if entry and entry.get('ids'):
                    result.append(entry['ids'][0])
                else:
                    missing.append(item)
        return result

    def _migrate_grid(self, grid, missing):
        if 'whitelist' in grid:
            grid['whitelist'] = self._migrate_whitelist(grid['whitelist'], missing)
        if 'slotAssignments' in grid:
            migrated = {}
            for k, v in grid['slotAssignments'].items():
                if isinstance(v, list):
                    migrated[k] = self._migrate_whitelist(v, missing)
                elif isinstance(v, str):
                    sub_missing = []
                    migrated[k] = self._migrate_whitelist([v], sub_missing)
                    missing.extend(sub_missing)
                else:
                    migrated[k] = v
            grid['slotAssignments'] = migrated
        return grid

    def load_profile_data(self, grids):
        """Load grid configs, validate/clamp values, and rebuild panels.

        Returns dict of {grid_name: [missing_refs]} for any buffs that couldn't
        be resolved during migration. Caller decides when/how to surface it,
        so the warning doesn't race other startup/first-launch dialogs.
        """
        self._tip_active = False
        self._from_empty_state = False
        missing_by_grid = {}
        validated = []
        for g in grids:
            if not isinstance(g, dict):
                logger.warning("Skipping non-dict grid entry in profile")
                continue
            grid_name = g.get('id', 'Unnamed')
            missing = []
            g = self._migrate_grid(g, missing)
            if missing:
                missing_by_grid[grid_name] = missing
            validated.append(validate_grid(g))
        self.grids = validated
        self.refresh_panels()
        return missing_by_grid

    def clear_all_grids(self):
        """Remove all grids with confirmation."""
        if not self.grids:
            return
        if Messagebox.yesno(f"Remove all {len(self.grids)} grids?\n\nThis can't be undone.", title="Clear All Grids") == "No":
            return
        self.grids.clear()
        self._mark_modified()
        self.refresh_panels()

    def get_total_slots(self):
        """Return total slot count across all grids."""
        return sum(g['rows'] * g['cols'] for g in self.grids)

    def save_settings(self):
        """Persist all panel UI values back to grid configs."""
        for panel in self.grid_panels:
            panel.save_to_config()

    def scale_to_resolution(self, resolution_str, reference_resolution):
        """Scale grid x/y from reference_resolution to the given game resolution.
        Returns True if scaling was applied."""
        game_res = parse_resolution(resolution_str)
        if not game_res:
            return False
        if not reference_resolution or len(reference_resolution) != 2:
            return False
        ref_w, ref_h = reference_resolution
        game_w, game_h = game_res
        if ref_w == game_w and ref_h == game_h:
            return False
        for grid in self.grids:
            grid['x'] = min(round(grid['x'] * game_w / ref_w), SCREEN_MAX_X)
            grid['y'] = min(round(grid['y'] * game_h / ref_h), SCREEN_MAX_Y)
        self.refresh_panels()
        return True

    def add_grid(self):
        """Open AddGridWizard dialog."""
        existing_ids = {g['id'] for g in self.grids}
        current_slots = self.get_total_slots()
        if current_slots >= MAX_TOTAL_SLOTS:
            Messagebox.show_warning(f"Maximum {MAX_TOTAL_SLOTS} total slots reached.\n\nRemove a grid or reduce grid sizes to free up slots.", title="Slot Limit")
            return
        wizard = AddGridWizard(self.winfo_toplevel(), existing_ids, current_slots)
        self.winfo_toplevel().wait_window(wizard)
        if wizard.result:
            self.grids.append(wizard.result)
            self._mark_modified()
            self.refresh_panels(expand_index=len(self.grids) - 1)

    def delete_grid(self, panel):
        """Delete a single grid."""
        for i, p in enumerate(self.grid_panels):
            if p == panel:
                del self.grids[i]
                self._mark_modified()
                self.refresh_panels()
                break

    def refresh_panels(self, expand_index=0):
        """Rebuild GridEditorPanel widgets or show empty state."""
        self._drag_manager.clear()

        if not self.grids:
            self._normal_view.pack_forget()
            self._empty_state.pack(fill='both', expand=True)
            self._stagger_empty_cards()
            self._from_empty_state = False
            self._update_tip()
            return

        self._empty_state.pack_forget()
        self._normal_view.pack(fill='both', expand=True)

        for widget in self.grids_frame.winfo_children():
            widget.destroy()
        self.grid_panels.clear()

        for i, grid_config in enumerate(self.grids):
            panel = GridEditorPanel(
                self.grids_frame, self.database, grid_config,
                on_delete=self.delete_grid, initially_open=(i == expand_index),
                get_total_slots=self.get_total_slots,
                on_resize=self._on_grid_resized,
                on_whitelist_changed=self._update_tip,
            )
            self.grid_panels.append(panel)
            self._attach_panel(panel, i)

        self.slot_count_label.set(f"{self.get_total_slots()} / {MAX_TOTAL_SLOTS} slots")
        self._update_tip()

    def _attach_panel(self, panel, index):
        """Pack a grid panel at index with separator, drag handle, and reorder bindings."""
        if index > 0:
            tk.Frame(self.grids_frame, height=1, bg=TK_COLORS['border']).pack(
                fill='x', padx=PAD_LIST_ITEM, pady=PAD_ROW)
        panel.pack(fill='x', pady=(0, PAD_ROW), padx=PAD_SMALL)
        self._drag_manager.bind_handle(panel.drag_handle, index, panel_widget=panel)
        panel.bind_reorder_keys(self._keyboard_reorder)

    def _reorder_grid(self, old_index, new_index):
        """Move a grid from old_index to new_index and repack panels."""
        grid = self.grids.pop(old_index)
        self.grids.insert(new_index, grid)
        panel = self.grid_panels.pop(old_index)
        self.grid_panels.insert(new_index, panel)
        self._mark_modified()
        self._repack_panels()

    def _repack_panels(self):
        """Repack existing panels in current order without destroying them."""
        self._drag_manager.clear()
        for widget in self.grids_frame.winfo_children():
            if isinstance(widget, tk.Frame) and not isinstance(widget, GridEditorPanel):
                widget.destroy()
            else:
                widget.pack_forget()
        for i, panel in enumerate(self.grid_panels):
            self._attach_panel(panel, i)

    def _keyboard_reorder(self, panel, direction):
        """Move a panel up (-1) or down (+1) via Alt+Arrow keys."""
        try:
            idx = self.grid_panels.index(panel)
        except ValueError:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.grid_panels):
            return
        self._reorder_grid(idx, new_idx)

    def _on_grid_resized(self):
        self.slot_count_label.set(f"{self.get_total_slots()} / {MAX_TOTAL_SLOTS} slots")
        self._mark_modified()

    def _mark_modified(self):
        """Signal that grids have changed."""
        if self.on_modified:
            self.on_modified()
