"""KazBars — Grid editor card (per-row CollapsibleSection).

`GridEditorPanel` is one card in the grids list. The container `GridsPanel`
(in `grids_panel.py`) creates/destroys these as the grid list changes.

Module-level option maps (`_FILL_*`, `_LAYOUT_*`, `_SORT_*`) are private to
this module — the container does not read them.
"""

import tkinter as tk
from tkinter import ttk

from ttkbootstrap.dialogs import Messagebox

from .grid_dialogs import BuffSelectorDialog, SlotAssignmentDialog
from .grid_model import (
    CLAMP_SPECS,
    MAX_COLS,
    MAX_ROWS,
    MAX_TOTAL_SLOTS,
    get_game_resolution_or_default,
)
from .ui_helpers import (
    BTN_MEDIUM,
    FONT_BODY_LG,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    FONT_SYMBOL,
    GRID_PREVIEW_PX,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import (
    CollapsibleSection,
    add_tooltip,
    app_toast,
    bind_card_events,
    bind_label_hover_colors,
    bind_label_press_effect,
    draw_grid_cells,
    labeled_combobox,
    labeled_spinbox,
    position_entry,
)


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

        self.drag_handle = ttk.Label(card, text=" ☰ ", font=FONT_BODY_LG,
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
        max_x, max_y = get_game_resolution_or_default()

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
        position_entry(pos_frame, "X:", self.x_var, lo=0, hi=max_x,
                       tooltip="Horizontal position on screen (pixels from left edge)",
                       label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, PAD_MID))
        self.y_var = tk.StringVar(value=str(cfg.get('y', 0)))
        position_entry(pos_frame, "Y:", self.y_var, lo=0, hi=max_y,
                       tooltip="Vertical position on screen (pixels from top edge)",
                       label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, 0))

        ttk.Button(header, text="Tracked Buffs...",
                   command=self._on_mode_btn_click, width=BTN_MEDIUM,
                   bootstyle='info-outline').pack(side='right', padx=(0, PAD_LF))  # type: ignore[call-arg]

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
        labeled_spinbox(
            top_row, "Rows:", self._rows_var, from_=1, to=MAX_ROWS, width=4,
            tooltip="Grid rows (height). Total slots across all grids cannot exceed 64.",
            on_change=lambda: self._on_dimension_changed('rows'),
            label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, PAD_MID),
        )
        self._cols_var = tk.StringVar(value=str(cfg.get('cols', 5)))
        labeled_spinbox(
            top_row, "Cols:", self._cols_var, from_=1, to=MAX_COLS, width=4,
            tooltip="Grid columns (width). Total slots across all grids cannot exceed 64.",
            on_change=lambda: self._on_dimension_changed('cols'),
            label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, 0),
        )

    def _build_icon_row(self, parent):
        """Pack icon size, gap, stack font, and the Timers / Flash toggle groups."""
        icon_row = ttk.Frame(parent)
        icon_row.pack(fill='x', pady=(0, PAD_ROW))
        self.icon_var = tk.IntVar()
        labeled_spinbox(icon_row, "Icon:", self.icon_var, from_=24, to=64, width=2,
            tooltip="Size of each buff icon in pixels (24-64)",
            padx=(PAD_BUTTON_GAP, PAD_TAB))
        self.gap_var = tk.IntVar()
        labeled_spinbox(icon_row, "Gap:", self.gap_var, from_=-5, to=10, width=3,
            tooltip="Space between icons (-5 = overlapping, 0 = touching, 10 = spaced out)",
            padx=(PAD_BUTTON_GAP, PAD_MID))

        ttk.Separator(icon_row, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.stack_font_var = tk.IntVar()
        labeled_spinbox(icon_row, "Stack Font:", self.stack_font_var, from_=8, to=24, width=2,
            tooltip="Font size for stack counter at top-right of icons (8-24)",
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
        self.timer_font_var = tk.IntVar()
        labeled_spinbox(self._timer_options_frame, "Font:", self.timer_font_var,
            from_=8, to=24, width=2,
            tooltip="Font size for timer text below icons (8-24)",
            padx=(PAD_BUTTON_GAP, PAD_TAB))
        self.timer_y_offset_var = tk.IntVar()
        labeled_spinbox(self._timer_options_frame, "Y Offset:", self.timer_y_offset_var,
            from_=-10, to=10, width=3,
            tooltip="Shift timer text up/down relative to the icon (-10 to 10)",
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
        self.flash_threshold_var = tk.IntVar()
        labeled_spinbox(self._flash_threshold_frame, "Under:", self.flash_threshold_var,
            from_=0, to=11, width=2,
            tooltip="Icons flash when timer drops below this many seconds (0-11)",
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
        self.fill_combo = labeled_combobox(dyn_row, "Fill:", self.fill_var, [], width=22,
            tooltip=lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"),
            padx=(PAD_BUTTON_GAP, PAD_TAB))

        self.sort_var = tk.StringVar()
        labeled_combobox(dyn_row, "Sort:", self.sort_var,
            [label for _, label, _ in _SORT_OPTIONS], width=16,
            tooltip=lambda: _SORT_DESCRIPTIONS.get(self.sort_var.get(), "How buffs are ordered"),
            padx=(PAD_BUTTON_GAP, PAD_TAB))

        self.layout_var = tk.StringVar()
        labeled_combobox(dyn_row, "Order:", self.layout_var,
            [label for _, label in _LAYOUT_OPTIONS], width=11,
            tooltip="In Buffs First and Debuffs First, misc effects always lead. In Mixed, all buffs sort together by time.",
            padx=(PAD_BUTTON_GAP, 0))

    def load_from_config(self):
        """Populate all editor widgets from the current grid configuration dict."""
        cfg = self.grid_config
        self.id_var.set(cfg.get('id', 'Grid'))
        self.enabled_var.set(cfg.get('enabled', True))
        rows = cfg.get('rows', 1)
        cols = cfg.get('cols', 5)
        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        max_x, max_y = get_game_resolution_or_default()
        self.x_var.set(str(min(cfg.get('x', 100), max_x)))
        self.y_var.set(str(min(cfg.get('y', 400), max_y)))
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
        self.section.set_summary(f"  {rows}×{cols} · {cfg.get('slotMode', 'dynamic')}")

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
