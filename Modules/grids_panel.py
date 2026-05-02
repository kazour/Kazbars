"""
Kaz Grids — Grid Editor Panel
Grid configuration UI: add/edit/delete grids, whitelist editing, slot assignment.
"""

import hashlib
import json
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
    THEME_COLORS, TK_COLORS, GRID_TYPE_COLORS,
    BTN_MEDIUM,
    PAD_TAB, PAD_ROW, PAD_XS, PAD_MICRO, PAD_SMALL, PAD_MID, PAD_LF,
    PAD_LIST_ITEM, PAD_SECTION_GAP, PAD_BUTTON_GAP,
    GRID_PREVIEW_PX, STEP_BADGE_PX, CELL_PX, CELL_PX_LARGE, CELL_GAP,
    PRESET_CARD_SQUARE, PRESET_CARD_BAR_LONG, PRESET_CARD_BAR_SHORT, PRESET_LABEL_AREA,
)
from .ui_widgets import (
    CollapsibleSection, add_tooltip, bind_card_events,
    bind_label_press_effect, bind_label_hover_colors, app_toast,
)
from .ui_components import create_scrollable_frame, DragReorderManager
from .settings_manager import get_setting, set_setting
from ttkbootstrap.dialogs import Messagebox


# ============================================================================
# SHARED HELPERS
# ============================================================================

def draw_grid_cells(canvas, rows, cols, type_color, area_w, area_h, tag='cells'):
    """Draw a miniature grid of colored rectangles on *canvas*."""
    canvas.delete(tag)
    cell_border = TK_COLORS['separator']
    display_rows = min(rows, 5)
    display_cols = min(cols, 5)
    cell = CELL_PX_LARGE if rows == 1 and cols == 1 else CELL_PX
    gap = CELL_GAP
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
    """A collapsible grid editor card."""

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
        self._resting_border_color = self._accent_color

        self._card = tk.Frame(self,
                               highlightbackground=self._accent_color,
                               highlightcolor=self._accent_color,
                               highlightthickness=1)
        card = self._card
        card.pack(fill='x')

        self.drag_handle = ttk.Label(card, text=" \u2630 ", font=FONT_BODY_LG,
                                      foreground=THEME_COLORS['muted'], cursor='fleur')
        self.drag_handle.pack(side='left', fill='y', padx=(PAD_MICRO, 0))
        bind_label_hover_colors(self.drag_handle, THEME_COLORS['muted'], THEME_COLORS['heading'])
        add_tooltip(self.drag_handle, "Drag to reorder")

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
            content_wrapper, width=GRID_PREVIEW_PX, height=GRID_PREVIEW_PX,
            bg=TK_COLORS['bg'], highlightthickness=0)
        self._preview_canvas.pack(side='right', padx=(PAD_XS, 0), pady=PAD_XS)

        self._build_top_row(settings_col)
        self._build_icon_row(settings_col)
        self._build_info_and_dynamic(settings_col)

        self.load_from_config()
        self._apply_enabled_styling(self.enabled_var.get())

        bind_card_events(card, lambda: self._resting_border_color)

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
                        command=self._on_enabled_toggled,
                        bootstyle="success-round-toggle").pack(side='right', padx=(0, PAD_XS))  # type: ignore[call-arg]

        pos_frame = ttk.Frame(header)
        pos_frame.pack(side='right', padx=(0, PAD_LF))
        self.x_var = tk.StringVar(value=str(cfg.get('x', 0)))
        self._add_position_entry(pos_frame, "X:", self.x_var, 0, SCREEN_MAX_X,
                                 "Horizontal position on screen (pixels from left edge)",
                                 padx=(PAD_MICRO, PAD_MID))
        self.y_var = tk.StringVar(value=str(cfg.get('y', 0)))
        self._add_position_entry(pos_frame, "Y:", self.y_var, 0, SCREEN_MAX_Y,
                                 "Vertical position on screen (pixels from top edge)",
                                 padx=(PAD_MICRO, 0))

        ttk.Button(header, text="Tracked Buffs...",
                   command=self._on_mode_btn_click, width=BTN_MEDIUM,
                   bootstyle='info-outline').pack(side='right', padx=(0, PAD_LF))  # type: ignore[call-arg]

    def _add_str_spin(self, parent, label, var, lo, hi, tooltip, padx, width=5, command=None):
        """Spinbox bound to a caller-owned StringVar with key-validation and FocusOut clamp."""
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        vcmd = (self.register(lambda P, lo=lo, hi=hi: self._validate_spinbox(P, lo, hi)), '%P')
        spin = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=width,
                           validate='key', validatecommand=vcmd, command=command or '')
        spin.pack(side='left', padx=padx)
        spin.bind('<FocusOut>',
                  lambda e, v=var, l=lo, h=hi: self._clamp_str_int(v, l, h))
        if command is not None:
            spin.bind('<FocusOut>', lambda e: command(), add='+')
        add_tooltip(spin, tooltip)

    def _add_position_entry(self, parent, label, var, lo, hi, tooltip, padx):
        """Entry for screen-pixel coordinates: spinbox stepping doesn't fit thousands of px."""
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL,
                  foreground=THEME_COLORS['muted']).pack(side='left')
        vcmd = (self.register(lambda P, lo=lo, hi=hi: self._validate_spinbox(P, lo, hi)), '%P')
        entry = ttk.Entry(parent, textvariable=var, width=5,
                          validate='key', validatecommand=vcmd, justify='right')
        entry.pack(side='left', padx=padx)
        entry.bind('<FocusOut>',
                   lambda e, v=var, l=lo, h=hi: self._clamp_str_int(v, l, h))
        add_tooltip(entry, tooltip)

    @staticmethod
    def _clamp_str_int(var, lo, hi):
        try:
            v = int(var.get())
        except (ValueError, tk.TclError):
            v = lo
        var.set(str(max(lo, min(v, hi))))

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
        self._name_entry.bind('<FocusIn>',
                              lambda e: self._name_entry.configure(bootstyle='default'))  # type: ignore[call-overload]
        self._name_entry.bind('<FocusOut>', lambda e: self._validate_name())
        add_tooltip(self._name_entry, "Display name for this grid (shown in preview mode)")

        self._rows_var = tk.StringVar(value=str(cfg.get('rows', 1)))
        self._add_str_spin(top_row, "Rows:", self._rows_var, 1, MAX_ROWS,
                           "Grid rows (height). Total slots across all grids cannot exceed 64.",
                           padx=(PAD_MICRO, PAD_MID), width=4,
                           command=lambda: self._on_dimension_changed('rows'))
        self._cols_var = tk.StringVar(value=str(cfg.get('cols', 5)))
        self._add_str_spin(top_row, "Cols:", self._cols_var, 1, MAX_COLS,
                           "Grid columns (width). Total slots across all grids cannot exceed 64.",
                           padx=(PAD_MICRO, 0), width=4,
                           command=lambda: self._on_dimension_changed('cols'))

    def _build_icon_row(self, parent):
        """Pack icon size, gap, stack font, and the Timers / Flash toggle groups."""
        icon_row = ttk.Frame(parent)
        icon_row.pack(fill='x', pady=(0, PAD_ROW))
        self.icon_var = self._add_spinbox(icon_row, "Icon:", 24, 64, 2,
            "Size of each buff icon in pixels (24-64)")
        self.gap_var = self._add_spinbox(icon_row, "Gap:", -5, 10, 3,
            "Space between icons (-5 = overlapping, 0 = touching, 10 = spaced out)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        ttk.Separator(icon_row, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.stack_font_var = self._add_spinbox(icon_row,
            "Stack Font:", 8, 24, 2, "Font size for stack counter at top-right of icons (8-24)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        timer_group = ttk.Frame(icon_row)
        timer_group.pack(side='left')
        ttk.Separator(timer_group, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.timers_var = tk.BooleanVar()
        timers_cb = ttk.Checkbutton(timer_group, text="Timers",
                                     variable=self.timers_var,
                                     bootstyle="success-round-toggle",  # type: ignore[call-arg]
                                     command=self._on_timers_toggled)
        timers_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(timers_cb, "Display remaining duration below each buff icon")

        self._timer_options_frame = ttk.Frame(timer_group)
        self._timer_options_frame.pack(side='left')
        self.timer_font_var = self._add_spinbox(self._timer_options_frame,
            "Font:", 8, 24, 2, "Font size for timer text below icons (8-24)")
        self.timer_y_offset_var = self._add_spinbox(self._timer_options_frame,
            "Y Offset:", -10, 10, 3,
            "Shift timer text up/down relative to the icon (-10 to 10)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        flash_group = ttk.Frame(icon_row)
        flash_group.pack(side='left')
        ttk.Separator(flash_group, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.flashing_var = tk.BooleanVar()
        flash_cb = ttk.Checkbutton(flash_group, text="Flash",
                                    variable=self.flashing_var,
                                    bootstyle="success-round-toggle",  # type: ignore[call-arg]
                                    command=self._on_flash_toggled)
        flash_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(flash_cb, "Icons flash when buff timer is about to expire")

        self._flash_threshold_frame = ttk.Frame(flash_group)
        self._flash_threshold_frame.pack(side='left')
        self.flash_threshold_var = self._add_spinbox(
            self._flash_threshold_frame, "Under:", 0, 11, 2,
            "Icons flash when timer drops below this many seconds (0-11)",
            padx=(PAD_BUTTON_GAP, 0))
        ttk.Label(self._flash_threshold_frame, text="s",
                  foreground=THEME_COLORS['muted'],
                  font=FONT_SMALL).pack(side='left')

    def _build_info_and_dynamic(self, parent):
        """Pack whitelist/slot summary row and the Fill/Sort/Group dynamic options."""
        info_row = ttk.Frame(parent)
        info_row.pack(fill='x', pady=(0, PAD_ROW))

        self.info_text = tk.StringVar(value="No buffs tracked. Click 'Tracked Buffs...' to add some.")
        ttk.Label(info_row, textvariable=self.info_text,
                  foreground=THEME_COLORS['muted'], font=FONT_SMALL).pack(side='left', padx=(0, PAD_LF))
        self.whitelist_preview_var = tk.StringVar(value="")
        self.whitelist_preview_label = ttk.Label(
            parent, textvariable=self.whitelist_preview_var,
            foreground=THEME_COLORS['muted'], font=FONT_SMALL)

        self.dynamic_frame = ttk.Frame(parent)
        dyn_row = ttk.Frame(self.dynamic_frame)
        dyn_row.pack(fill='x', pady=(0, PAD_ROW))

        self.fill_var = tk.StringVar()
        self.fill_combo = self._add_combobox(dyn_row, "Fill:", self.fill_var, [], 22,
            lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"))

        self.sort_var = tk.StringVar()
        self._add_combobox(dyn_row, "Sort:", self.sort_var,
            [label for _, label, _ in _SORT_OPTIONS], 16,
            lambda: _SORT_DESCRIPTIONS.get(self.sort_var.get(), "How buffs are ordered"))

        self.layout_var = tk.StringVar()
        self._add_combobox(dyn_row, "Order:", self.layout_var,
            [label for _, label in _LAYOUT_OPTIONS], 11,
            "In Buffs First and Debuffs First, misc effects always lead. In Mixed, all buffs sort together by time.",
            padx=(PAD_BUTTON_GAP, 0))

    def _add_spinbox(self, parent, label, from_, to, width, tooltip, padx=(PAD_BUTTON_GAP, PAD_TAB)):
        ttk.Label(parent, text=label, font=FONT_FORM_LABEL).pack(side='left')
        var = tk.IntVar()
        vcmd = (self.register(lambda P, f=from_, t=to: self._validate_spinbox(P, f, t)), '%P')
        spin = ttk.Spinbox(parent, from_=from_, to=to, textvariable=var, width=width,
                           validate='key', validatecommand=vcmd)
        spin.pack(side='left', padx=padx)
        spin.bind('<FocusOut>', lambda e, v=var, lo=from_, hi=to: self._clamp_spinbox(v, lo, hi))
        add_tooltip(spin, tooltip)
        return var

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
        rows = cfg.get('rows', 1)
        cols = cfg.get('cols', 5)
        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        self.x_var.set(str(min(cfg.get('x', 100), SCREEN_MAX_X)))
        self.y_var.set(str(min(cfg.get('y', 400), SCREEN_MAX_Y)))
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
        self.fill_var.set(_FILL_LABEL_BY_CODE.get(cfg.get('fillDirection', 'LR'),
                                                   _FILL_LABEL_BY_CODE['LR']))
        self.sort_var.set(_SORT_LABEL_BY_CODE.get(cfg.get('sortOrder', 'longest'),
                                                   _SORT_LABEL_BY_CODE['longest']))
        self.layout_var.set(_LAYOUT_LABEL_BY_CODE.get(cfg.get('layout', 'buffFirst'),
                                                       _LAYOUT_LABEL_BY_CODE['buffFirst']))

        self._update_fill_options(rows, cols)

        if cfg.get('slotMode') == 'static':
            self.dynamic_frame.pack_forget()
        else:
            self.dynamic_frame.pack(fill='x')

        self.update_labels()
        self._update_preview()

    def _update_preview(self):
        """Redraw the small grid shape preview in the card."""
        rows = self.grid_config.get('rows', 1)
        cols = self.grid_config.get('cols', 5)
        draw_grid_cells(self._preview_canvas, rows, cols,
                        self._accent_color, GRID_PREVIEW_PX, GRID_PREVIEW_PX)

    def _validate_name(self):
        """Red on empty, commit on valid. Never rewrites the field — deleting and blurring would otherwise snap the old name back."""
        name = self.id_var.get().strip()
        if not name:
            self._name_entry.configure(bootstyle='danger')  # type: ignore[call-overload]
        else:
            self._name_entry.configure(bootstyle='default')  # type: ignore[call-overload]
            self.grid_config['id'] = name

    def save_to_config(self):
        """Write current widget values back into the grid configuration dict."""
        self._validate_name()
        self.grid_config['enabled'] = self.enabled_var.get()
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
            try:
                v = int(var.get())
            except (ValueError, tk.TclError):
                # Validator allows transient '' / '-' mid-edit; fall back to current value.
                v = self.grid_config.get(key, lo)
            self.grid_config[key] = max(lo, min(v, hi))
        self.grid_config['showTimers'] = self.timers_var.get()
        self.grid_config['enableFlashing'] = self.flashing_var.get()
        self.grid_config['fillDirection'] = _FILL_CODE_BY_LABEL.get(
            self.fill_var.get(), self.grid_config.get('fillDirection', 'LR'))
        self.grid_config['sortOrder'] = _SORT_CODE_BY_LABEL.get(
            self.sort_var.get(), self.grid_config.get('sortOrder', 'longest'))
        self.grid_config['layout'] = _LAYOUT_CODE_BY_LABEL.get(
            self.layout_var.get(), self.grid_config.get('layout', 'buffFirst'))

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

        sa = cfg.get('slotAssignments', {})
        assigned_ids = []
        for v in sa.values():
            if isinstance(v, list):
                assigned_ids.extend(b for b in v if b)
            elif v:
                assigned_ids.append(v)
        configured = sum(1 for v in sa.values() if v)

        if cfg.get('slotMode') == 'static':
            self.info_text.set(f"{configured} of {rows * cols} slots assigned")
        else:
            self.info_text.set(
                f"Tracking {len(wl)} buffs" if wl
                else "No buffs tracked. Click 'Tracked Buffs...' to add some."
            )

        preview_ids = assigned_ids if cfg.get('slotMode') == 'static' else wl
        if preview_ids:
            self.whitelist_preview_var.set(self._format_buff_preview(preview_ids))
            self.whitelist_preview_label.pack(fill='x', pady=(0, PAD_BUTTON_GAP))
        else:
            self.whitelist_preview_var.set("")
            self.whitelist_preview_label.pack_forget()

        self.section.set_title(cfg.get('id', 'Grid'))
        self.section.set_summary(f"  {rows}\u00d7{cols} \u00b7 {cfg.get('slotMode', 'dynamic')}")

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

    def _on_enabled_toggled(self):
        self._apply_enabled_styling(self.enabled_var.get())

    def _apply_enabled_styling(self, enabled):
        """Drain the grid's identity colors when it's excluded from the build.

        Title, badge, and accent strips drop to greys; the card frame border
        falls back from the player/target accent to the neutral border. The
        Enabled toggle is the affordance — this is the visual consequence.
        """
        self._resting_border_color = self._accent_color if enabled else TK_COLORS['border']
        self._card.configure(highlightbackground=self._resting_border_color,
                             highlightcolor=self._resting_border_color)
        self.section.set_dimmed(not enabled)

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
        if self.grid_config.get('slotMode') == 'static':
            if new_total < old_total:
                self._trim_slot_assignments(new_total)
            elif new_total > old_total:
                self._restore_orphaned_assignments(new_total)
        if new_rows == 1 and new_cols == 1 and self.grid_config.get('slotMode') == 'dynamic':
            new_cols = 2
            self.grid_config['cols'] = new_cols
            self._cols_var.set('2')
            app_toast(self, "Dynamic grids need at least 2 slots, switched to 1×2", 'info',
                      key='grid_resize')
        self._update_fill_options(new_rows, new_cols)
        self.update_labels()
        self._update_preview()
        if self._on_resize:
            self._on_resize()

    def _trim_slot_assignments(self, new_total):
        """Drop assignments past new_total; stash dropped IDs on the grid for later restore."""
        sa = self.grid_config.get('slotAssignments', {})
        dropped_ids = []
        for k, v in sa.items():
            if int(k) >= new_total and v:
                ids = v if isinstance(v, list) else [v]
                dropped_ids.extend(b for b in ids if b)
        self.grid_config['slotAssignments'] = {
            k: v for k, v in sa.items() if int(k) < new_total
        }
        if not dropped_ids:
            return
        existing = self.grid_config.get('_orphanedAssignments', [])
        self.grid_config['_orphanedAssignments'] = list(dict.fromkeys(existing + dropped_ids))
        # Non-blocking toast: a modal here would let the spinbox arrow's auto-repeat
        # keep firing during the popup, recursively trimming further. Coalesce-key
        # collapses an arrow-hold burst into a single in-place-updating toast.
        noun = "buff" if len(dropped_ids) == 1 else "buffs"
        app_toast(
            self,
            f"Unassigned {len(dropped_ids)} {noun} (resize back up to restore): "
            f"{self._format_buff_preview(dropped_ids)}",
            'warning',
            key='grid_resize'
        )

    def _restore_orphaned_assignments(self, new_total):
        """Fill any empty slots in the new range with previously-orphaned assignments."""
        orphans = list(self.grid_config.get('_orphanedAssignments', []))
        if not orphans:
            return
        sa = dict(self.grid_config.get('slotAssignments', {}))
        restored = []
        for k in range(new_total):
            if not orphans:
                break
            slot_key = str(k)
            current = sa.get(slot_key)
            is_empty = not current or (isinstance(current, list) and not any(current))
            if is_empty:
                sa[slot_key] = [orphans.pop(0)]
                restored.append(sa[slot_key][0])
        if not restored:
            return
        self.grid_config['slotAssignments'] = sa
        self.grid_config['_orphanedAssignments'] = orphans
        noun = "buff" if len(restored) == 1 else "buffs"
        app_toast(
            self,
            f"Restored {len(restored)} {noun}: {self._format_buff_preview(restored)}",
            'success',
            key='grid_resize'
        )

    def _update_fill_options(self, rows, cols):
        if rows == 1:
            valid_codes = ['LR', 'RL']
            default = 'LR'
        elif cols == 1:
            valid_codes = ['TB', 'BT']
            default = 'BT'
        else:
            valid_codes = ['TL-BR', 'TR-BL', 'BL-TR', 'BR-TL']
            default = 'BL-TR'
        valid_labels = [_FILL_LABEL_BY_CODE[c] for c in valid_codes]
        self.fill_combo['values'] = valid_labels
        if self.fill_var.get() not in valid_labels:
            self.fill_var.set(_FILL_LABEL_BY_CODE[default])
            self.grid_config['fillDirection'] = default


_FILL_OPTIONS = [
    # (persisted code, user-facing label, tooltip description)
    ('LR',    'Left → Right',           'New buffs appear on the right'),
    ('RL',    'Right → Left',           'New buffs appear on the left'),
    ('TB',    'Top → Bottom',           'New buffs appear at the bottom'),
    ('BT',    'Bottom → Top',           'New buffs appear at the top'),
    ('TL-BR', 'Top-left → Bottom-right', 'Fills from the top-left corner'),
    ('TR-BL', 'Top-right → Bottom-left', 'Fills from the top-right corner'),
    ('BL-TR', 'Bottom-left → Top-right', 'Fills from the bottom-left corner'),
    ('BR-TL', 'Bottom-right → Top-left', 'Fills from the bottom-right corner'),
]
_FILL_LABEL_BY_CODE = {code: label for code, label, _ in _FILL_OPTIONS}
_FILL_CODE_BY_LABEL = {label: code for code, label, _ in _FILL_OPTIONS}
_FILL_DESCRIPTIONS = {label: desc for _, label, desc in _FILL_OPTIONS}

_LAYOUT_OPTIONS = [
    ('buffFirst',   'Buffs first'),
    ('debuffFirst', 'Debuffs first'),
    ('mixed',       'Mixed'),
]
_LAYOUT_LABEL_BY_CODE = {code: label for code, label in _LAYOUT_OPTIONS}
_LAYOUT_CODE_BY_LABEL = {label: code for code, label in _LAYOUT_OPTIONS}

_SORT_OPTIONS = [
    ('shortest',    'Shortest first', 'Buffs about to expire appear first'),
    ('longest',     'Longest first',  'Buffs with the most time remaining appear first'),
    ('application', 'Order applied',  'Buffs appear in the order they were applied'),
]
_SORT_LABEL_BY_CODE = {code: label for code, label, _ in _SORT_OPTIONS}
_SORT_CODE_BY_LABEL = {label: code for code, label, _ in _SORT_OPTIONS}
_SORT_DESCRIPTIONS = {label: desc for _, label, desc in _SORT_OPTIONS}

# ============================================================================
# GRIDS PANEL
# ============================================================================
class GridsPanel(ttk.Frame):
    """Grid editor panel: switches between empty state and toolbar+cards normal view."""

    def __init__(self, parent, database, on_modified=None):
        super().__init__(parent)
        self.database = database
        self.on_modified = on_modified

        self.grids = []
        self.grid_panels = []
        self._tip_dismissed = False
        self._build_done = False

        self._create_widgets()
        self.refresh_panels()

    def _create_widgets(self):
        """Build normal view (toolbar + scroll) and empty state frame."""
        self._normal_view = ttk.Frame(self)

        toolbar = ttk.Frame(self._normal_view)
        toolbar.pack(fill='x', padx=PAD_TAB, pady=PAD_SMALL)
        ttk.Button(toolbar, text="+ Add Grid", command=self.add_grid,
                   width=BTN_MEDIUM).pack(side='left', padx=PAD_BUTTON_GAP)
        self.slot_count_label = tk.StringVar(value=f"0 / {MAX_TOTAL_SLOTS} slots")
        self._slot_count_lbl = ttk.Label(toolbar, textvariable=self.slot_count_label,
                                          font=FONT_BODY, foreground=THEME_COLORS['muted'])
        self._slot_count_lbl.pack(side='right')

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

        self._empty_state = self._build_empty_state()

    def _build_tip_bar(self):
        """Build the contextual next-step guide (tip bar) shown above grids/empty state."""
        self._tip_frame = tk.Frame(self, bg=TK_COLORS['status_bg'],
                                    highlightbackground=TK_COLORS['border'],
                                    highlightcolor=TK_COLORS['border'],
                                    highlightthickness=1)
        tip_inner = tk.Frame(self._tip_frame, bg=TK_COLORS['status_bg'])
        tip_inner.pack(fill='x', padx=PAD_LF, pady=PAD_XS)

        muted = THEME_COLORS['muted']
        bg = TK_COLORS['status_bg']
        self._step_badges = []
        self._step_labels = []
        for i, step_text in enumerate(["Set game folder below", "Add Grid", "Choose Tracked Buffs", "Build"]):
            if i > 0:
                ttk.Label(tip_inner, text="→", font=FONT_BODY,
                          foreground=muted).pack(side='left', padx=PAD_XS)
            badge = tk.Canvas(tip_inner, width=STEP_BADGE_PX, height=STEP_BADGE_PX,
                              bg=bg, highlightthickness=0)
            badge.pack(side='left', padx=(PAD_XS, 2))
            badge.create_oval(1, 1, STEP_BADGE_PX - 1, STEP_BADGE_PX - 1,
                              fill='', outline=muted, tags='oval')
            badge.create_text(STEP_BADGE_PX // 2, STEP_BADGE_PX // 2,
                              text=str(i + 1), fill=muted,
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

        ttk.Label(center, text="No grids yet. Pick a layout to start.",
                  font=FONT_HEADING, foreground=THEME_COLORS['heading']).pack(
                      pady=(0, PAD_SECTION_GAP))

        self._empty_type_var = tk.StringVar(value="player")
        self._radio_player, self._radio_target = self._build_radio_row(
            center, "Source:", self._empty_type_var,
            [("Player", "player"), ("Target", "target")],
            command=self._redraw_empty_cards, pady=(0, PAD_LF))
        # ttkbootstrap strips custom style= at construction; apply via configure() after.
        self._radio_player.configure(style='Player.TRadiobutton')
        self._radio_target.configure(style='Target.TRadiobutton')

        self._empty_mode_var = tk.StringVar(value="dynamic")
        self._radio_dynamic, self._radio_static = self._build_radio_row(
            center, "Mode:", self._empty_mode_var,
            [("Dynamic", "dynamic"), ("Static", "static")],
            command=None, pady=(0, PAD_TAB))

        cards_frame = ttk.Frame(center)
        cards_frame.pack(pady=(0, PAD_SECTION_GAP), fill='x')

        presets = [
            ("1\u00d710 Bar", 1, 10, "dynamic", PRESET_CARD_BAR_LONG, PRESET_CARD_BAR_SHORT,
             "Horizontal bar, great for tracking player buffs across the top"),
            ("10\u00d71 Bar", 10, 1, "dynamic", PRESET_CARD_BAR_SHORT, PRESET_CARD_SQUARE,
             "Vertical bar, stack buffs along the side of your screen"),
            ("3\u00d73 Grid", 3, 3, "dynamic", PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Compact grid, fits many buffs in a small area"),
            ("1\u00d71 Slot \u00b7 static", 1, 1, "static", PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Single slot. Pin one specific buff. Mode is locked to Static."),
            ("Custom", None, None, None, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Open the Add Grid wizard to set custom rows, columns, and options"),
        ]
        self._empty_cards = []
        for i, (label, rows, cols, mode, w, h, desc) in enumerate(presets):
            card = self._build_preset_card(cards_frame, label, rows, cols, mode, w, h, desc)
            card.grid(row=0, column=i, padx=PAD_LF, sticky='s')

        cards_frame.bind('<Configure>', self._reflow_preset_cards)

        self._redraw_empty_cards()

        add_tooltip(self._radio_player, "Track buffs/debuffs on yourself")
        add_tooltip(self._radio_target, "Track buffs/debuffs on your current target")
        add_tooltip(self._radio_dynamic,
                    "Slots fill automatically as buffs activate. "
                    "You control fill direction, sort order, and grouping.")
        add_tooltip(self._radio_static,
                    "Each slot is pinned to specific buffs. "
                    "Shows the buff when active, stays empty when it's not.")

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

    def _build_preset_card(self, parent, label, rows, cols, mode, card_w, card_h, description):
        """Create a preset shape card. Caller grid()s it so _reflow_preset_cards can re-row on resize."""
        border = TK_COLORS['border']
        accent = THEME_COLORS['accent']

        card = tk.Canvas(parent, width=card_w, height=card_h,
                         highlightthickness=1, highlightbackground=border,
                         bg=TK_COLORS['bg'], cursor='hand2', takefocus=True)
        card.create_text(card_w // 2, card_h - PRESET_LABEL_AREA // 2,
                         text=label, anchor='center',
                         fill=THEME_COLORS['muted'], font=FONT_SMALL)
        add_tooltip(card, description)

        self._empty_cards.append((card, rows, cols, card_w, card_h))

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
        return card

    def _reflow_preset_cards(self, event):
        """Wrap preset cards into multiple grid rows when the wrapper is too narrow."""
        avail = event.width
        if avail < 100 or not getattr(self, '_empty_cards', None):
            return
        if getattr(self, '_last_cards_width', None) == avail:
            return
        self._last_cards_width = avail

        gap = PAD_LF * 2
        row, col, row_w = 0, 0, 0
        for card, _, _, card_w, _ in self._empty_cards:
            if col > 0 and row_w + card_w + gap > avail:
                row += 1
                col = 0
                row_w = 0
            # pady gives a row gap only when cards wrap; harmless on a single row.
            card.grid_configure(row=row, column=col, padx=PAD_LF, pady=(0, PAD_XS), sticky='s')
            row_w += card_w + gap
            col += 1

    def _redraw_empty_cards(self):
        """Redraw grid shape previews on empty state cards using current type color."""
        type_color = GRID_TYPE_COLORS[self._empty_type_var.get()]
        for card, rows, cols, card_w, card_h in self._empty_cards:
            card.delete('cells')
            preview_h = card_h - PRESET_LABEL_AREA
            if rows is None:
                card.create_text(card_w // 2, preview_h // 2 + 10, text="+",
                                 anchor='center', fill=type_color,
                                 font=FONT_HEADING, tags='cells')
                continue
            draw_grid_cells(card, rows, cols, type_color, card_w, preview_h)

    def _dismiss_tip(self):
        """Dismiss the tip bar permanently for this session."""
        self._tip_dismissed = True
        self._tip_frame.pack_forget()

    def notify_build_done(self, aoc_installed, profile_path):
        """Called after a successful build — mark step 4 complete and re-show panel.
        Persists a signature of {profile path, built grids} so relaunching the app
        with the same profile and unchanged grids restores the green Build step.
        Loading a different profile (even one whose grids hash to the same shape)
        won't false-match because the profile path is part of the signature."""
        self._build_done = True
        self._tip_dismissed = False
        set_setting('last_build_signature', self._compute_grids_signature(profile_path))
        self._update_tip()

    def _compute_grids_signature(self, profile_path):
        """Stable hash of {profile, grids}. `profile_path` is the loaded profile
        path or `None` for the bundled default — both are valid identities, so
        signatures pin to whichever the user actually built."""
        payload = json.dumps(
            {'profile': profile_path, 'grids': self.grids},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha1(payload.encode('utf-8')).hexdigest()

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
        border = THEME_COLORS['success'] if ready else TK_COLORS['border']
        self._tip_frame.configure(highlightbackground=border, highlightcolor=border)

        state_widget = self._normal_view if has_grids else self._empty_state
        self._tip_frame.pack_forget()
        self._tip_frame.pack(fill='x', padx=PAD_TAB, pady=(PAD_XS, PAD_XS),
                             before=state_widget)

    def _create_from_empty_state(self, rows, cols, mode):
        """Create a grid from the empty state preset shortcuts."""
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

    def load_profile_data(self, grids, profile_path=None):
        """Load grid configs, validate/clamp values, and rebuild panels.

        `profile_path` identifies the profile being loaded (None for bundled
        default). Used to pin the build signature: only the same profile +
        same grids shape restores `_build_done`.

        Returns dict of {grid_name: [missing_refs]} for any buffs that couldn't
        be resolved during migration. Caller decides when/how to surface it,
        so the warning doesn't race other startup/first-launch dialogs.
        """
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
        # Restore _build_done from the persisted signature only when both the
        # profile identity and the grids hash match: relaunch on the same
        # profile keeps step 4 green; cross-profile load resets it.
        stored_sig = get_setting('last_build_signature')
        self._build_done = bool(stored_sig) and stored_sig == self._compute_grids_signature(profile_path)
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

    def _update_slot_counter(self):
        total = self.get_total_slots()
        pct = total / MAX_TOTAL_SLOTS
        base = f"{total} / {MAX_TOTAL_SLOTS} slots"
        if pct >= 0.95:
            color = THEME_COLORS['danger']
            text = f"! {base}"
        elif pct >= 0.80:
            color = THEME_COLORS['warning']
            text = base
        else:
            color = THEME_COLORS['muted']
            text = base
        self.slot_count_label.set(text)
        self._slot_count_lbl.configure(foreground=color)

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

        self._update_slot_counter()
        self._update_tip()

    def _attach_panel(self, panel, index):
        """Pack a grid panel at index with separator and drag handle binding."""
        if index > 0:
            tk.Frame(self.grids_frame, height=1, bg=TK_COLORS['border']).pack(
                fill='x', padx=PAD_LIST_ITEM, pady=PAD_ROW)
        panel.pack(fill='x', pady=(0, PAD_ROW), padx=PAD_SMALL)
        self._drag_manager.bind_handle(panel.drag_handle, index, panel_widget=panel)

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
                widget.pack_forget()  # type: ignore[attr-defined]
        for i, panel in enumerate(self.grid_panels):
            self._attach_panel(panel, i)

    def _on_grid_resized(self):
        self._update_slot_counter()
        self._mark_modified()

    def _mark_modified(self):
        """Signal that grids have changed. Any in-memory edit after a build
        means the deployed SWF no longer matches, so the Build step un-ticks."""
        if self._build_done:
            self._build_done = False
            self._update_tip()
        if self.on_modified:
            self.on_modified()
