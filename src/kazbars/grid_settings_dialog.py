"""
KazBars — Grid Settings dialog (a grid card's cog).

One modal window per grid, in the family of the Extras dialogs: a header,
titled cards, Cancel / Apply (Enter applies, Esc cancels). It opens just
under its card (above it where the screen has no room), never over the
preview it drives. Cards, built only where they apply:

- **Grid**: Name; Rows × Cols, or a band's Row cap and Max slots; a screen
  grid's Position (X / Y).
- **Icons**: Size, Gap, Timers (Bar / Digits / Off) and their Y offset,
  Flash and its threshold, Applied by me.
- **Overhead** (overhead grids): Height, Range; Over me (friendly).
- **Sorting** (dynamic grids): Fill (a band's reads Centred), Sort, Order.

Every change rebuilds a draft (the config with this dialog's values on top)
and hands it to the card, whose preview draws it live (`preview_draft`).
Cancel redraws the card from the stored config (`cancel_draft`); Apply hands
the draft to `apply_settings`, which lands it and runs the resize rules. The
dialog never writes the config itself.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import (
    BAND_ROW_CAPS,
    CLAMP_SPECS,
    PLATE_MAX_SLOTS,
    band_shape,
    get_game_resolution_or_default,
    is_band,
    is_plate,
    max_shape,
    max_slots,
    project_px,
    unproject_px,
    valid_fills,
)
from .overlay_size import grid_metrics
from .ui_forms import create_card, labeled_combobox, labeled_spinbox, position_entry, size_slider
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_DIALOG,
    FONT_FORM_LABEL,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_BUTTON_GAP,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import clamp_to_screen

_WIDTH = 720

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
_BAND_FILL_LABEL = 'Centred'

_TIMER_OPTIONS = [
    # (persisted code, user-facing label, tooltip description)
    ('bar',    'Bar',    'A line inside the icon\'s bottom edge that shrinks as time runs out'),
    ('digits', 'Digits', 'Seconds left, under each icon'),
    ('off',    'Off',    'No timer'),
]

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


def open_grid_settings(card):
    """Open (or raise) the card's Grid Settings window."""
    existing = card.settings_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
    card.settings_dialog = GridSettingsDialog(card)
    return card.settings_dialog


def _int(var, fallback, lo, hi):
    """A field's value clamped to [lo, hi]; `fallback` while it reads as
    nothing ('' or '-' mid-edit)."""
    try:
        return max(lo, min(int(var.get()), hi))
    except (ValueError, tk.TclError):
        return fallback


def _row(parent):
    row = ttk.Frame(parent)
    row.pack(fill='x', pady=(0, PAD_ROW))
    return row


class GridSettingsDialog(tk.Toplevel):
    """See the module docstring."""

    def __init__(self, card):
        super().__init__(card.winfo_toplevel())
        self.withdraw()
        self.card = card
        cfg = self._cfg = card.grid_config
        self._type = cfg.get('type', 'player')
        self._band = is_band(cfg)
        self._plate = is_plate(self._type)
        self._static = cfg.get('slotMode') == 'static'
        self.title(f"Grid Settings — {cfg.get('id', 'Grid')}")
        self.resizable(False, False)
        self.transient(card.winfo_toplevel())
        self.grab_set()

        create_dialog_header(self, f"GRID SETTINGS — {cfg.get('id', 'Grid')}",
                             MODULE_COLORS['grids'], width=_WIDTH)
        body = ttk.Frame(self, padding=(PAD_TAB, PAD_SMALL, PAD_TAB, 0))
        body.pack(fill='both', expand=True)
        cards = [self._build_grid_card(body), self._build_icons_card(body)]
        if self._plate:
            cards.append(self._build_overhead_card(body))
        if not self._static:
            cards.append(self._build_sorting_card(body))
        for i, c in enumerate(cards):
            c.grid(row=i // 2, column=i % 2, sticky='nsew',
                   padx=(0, PAD_SMALL) if i % 2 == 0 else 0, pady=(0, PAD_SMALL))
        body.columnconfigure(0, weight=1, uniform='card')
        body.columnconfigure(1, weight=1, uniform='card')

        footer = ttk.Frame(self, padding=(PAD_TAB, PAD_XS, PAD_TAB, PAD_TAB))
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text="Apply", bootstyle="success",  # type: ignore[call-arg]
                   command=self.apply, width=BTN_DIALOG).pack(side='right')
        ttk.Button(footer, text="Cancel", bootstyle="secondary",  # type: ignore[call-arg]
                   command=self.cancel, width=BTN_DIALOG).pack(side='right', padx=(0, PAD_SMALL))

        self._sync_timer_fields()
        self._sync_flash_fields()

        self._place_by_card()
        self.deiconify()
        self.bind('<Return>', lambda e: self.apply())
        self.bind('<Escape>', lambda e: self.cancel())
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Map>', lambda e: apply_dark_titlebar(self) if e.widget is self else None, add='+')
        self.after(0, self._name_entry.focus_set)

    def _place_by_card(self):
        """Under the card, right edges aligned; above it when the screen has
        no room below. The card's preview stays in view either way."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        card = self.card
        x = card.winfo_rootx() + card.winfo_width() - w
        below = card.winfo_rooty() + card.winfo_height() + PAD_XS
        y = below
        if clamp_to_screen(x, below, w, h)[1] < below:
            y = card.winfo_rooty() - h - PAD_XS
        x, y = clamp_to_screen(x, y, w, h)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------
    def _build_grid_card(self, parent):
        cfg = self._cfg
        card = create_card(parent, "Grid")
        row = _row(card)
        ttk.Label(row, text="Name:", font=FONT_FORM_LABEL).pack(side='left')
        self.id_var = tk.StringVar(value=cfg.get('id', 'Grid'))
        self._name_entry = ttk.Entry(row, textvariable=self.id_var, width=22)
        self._name_entry.pack(side='left', padx=(PAD_XS, 0))
        add_tooltip(self._name_entry, "Display name for this grid (shown in preview mode)")
        self._name_hint = ttk.Label(card, font=FONT_SMALL, foreground=THEME_COLORS['danger_text'])
        self.id_var.trace_add('write', lambda *_: self._name_hint.configure(text=''))

        row = _row(card)
        if self._band:
            self.row_cap_var = tk.IntVar(value=cfg.get('rowCap', 5))
            self.max_slots_var = tk.StringVar(value=str(cfg.get('maxSlots', 10)))
            ttk.Label(row, text="Row cap:", font=FONT_FORM_LABEL).pack(side='left')
            for cap in BAND_ROW_CAPS:
                rb = ttk.Radiobutton(row, text=str(cap), value=cap, variable=self.row_cap_var,
                                     command=self._changed, bootstyle='toolbutton')  # type: ignore[call-arg]
                rb.pack(side='left', padx=(PAD_MICRO, 0))
                add_tooltip(rb, "Icons to a row, centred over the head, before the next row starts above")
            labeled_spinbox(row, "Max slots:", self.max_slots_var, from_=1, to=PLATE_MAX_SLOTS, width=4,
                            tooltip=f"The most icons the band shows (1-{PLATE_MAX_SLOTS})",
                            on_change=self._changed, padx=(PAD_MICRO, 0))
        else:
            max_rows, max_cols = max_shape(self._type)
            limit = max_slots(self._type)
            self.rows_var = tk.StringVar(value=str(cfg.get('rows', 1)))
            self.cols_var = tk.StringVar(value=str(cfg.get('cols', 1)))
            labeled_spinbox(row, "Rows:", self.rows_var, from_=1, to=max_rows, width=4,
                            tooltip=f"Grid rows (height). A grid holds up to {limit} slots.",
                            on_change=lambda: self._on_shape('rows'), padx=(PAD_MICRO, PAD_MID))
            labeled_spinbox(row, "Cols:", self.cols_var, from_=1, to=max_cols, width=4,
                            tooltip=f"Grid columns (width). A grid holds up to {limit} slots.",
                            on_change=lambda: self._on_shape('cols'), padx=(PAD_MICRO, 0))

        if not self._plate:
            # Positions are fractions; the fields show px at the game resolution.
            self._res = get_game_resolution_or_default()
            self._px0 = (project_px(cfg.get('fx', 0.0), self._res[0]),
                         project_px(cfg.get('fy', 0.0), self._res[1]))
            self.x_var = tk.StringVar(value=str(self._px0[0]))
            self.y_var = tk.StringVar(value=str(self._px0[1]))
            row = _row(card)
            ttk.Label(row, text="Position:", font=FONT_FORM_LABEL).pack(side='left', padx=(0, PAD_XS))
            position_entry(row, "X:", self.x_var, lo=0, hi=self._res[0],
                           tooltip="Horizontal position on screen (pixels from left edge)",
                           padx=(PAD_MICRO, PAD_MID))
            position_entry(row, "Y:", self.y_var, lo=0, hi=self._res[1],
                           tooltip="Vertical position on screen (pixels from top edge)",
                           padx=(PAD_MICRO, 0))
        return card

    def _build_icons_card(self, parent):
        cfg = self._cfg
        card = create_card(parent, "Icons")
        row = _row(card)
        _, self.scale_var, _ = size_slider(
            row, cfg.get('scale', 100),
            lambda p: f"{grid_metrics(self.card.base_size(), p).icon} px icons",
            on_commit=self._changed, on_move=lambda p: self._changed(),
            tooltip="Icon, timer and stack size, as a percent of the overlay size "
                    "(Overlay, top of the Grids tab)")
        row = _row(card)
        self.gap_var = tk.StringVar(value=str(max(-5, min(cfg.get('gap', -1), 10))))
        labeled_spinbox(row, "Gap:", self.gap_var, from_=-5, to=10, width=3,
                        tooltip="Space between icons (-5 = overlapping, 0 = touching, 10 = spaced out)",
                        on_change=self._changed, padx=(PAD_BUTTON_GAP, 0))

        row = _row(card)
        ttk.Label(row, text="Timers:", font=FONT_FORM_LABEL).pack(side='left')
        self.timer_style_var = tk.StringVar(value=cfg.get('timerStyle', 'digits'))
        for code, label, tip in _TIMER_OPTIONS:
            rb = ttk.Radiobutton(row, text=label, value=code, variable=self.timer_style_var,
                                 command=self._on_timers, bootstyle='toolbutton')  # type: ignore[call-arg]
            rb.pack(side='left', padx=(PAD_MICRO, 0))
            add_tooltip(rb, tip)
        self._timer_offset_labels: list = []
        self.timer_y_offset_var = tk.StringVar(value=str(cfg.get('timerYOffset', -3)))
        self._timer_offset_spin = labeled_spinbox(
            row, "Y offset:", self.timer_y_offset_var, from_=-10, to=10, width=3,
            tooltip="Shift the timer digits up/down relative to the icon (-10 to 10)",
            padx=(PAD_BUTTON_GAP, 0), label_sink=self._timer_offset_labels)
        self._timer_offset_labels[0].pack_configure(padx=(PAD_MID, 0))

        row = _row(card)
        self.flashing_var = tk.BooleanVar(value=cfg.get('enableFlashing', True))
        flash_cb = ttk.Checkbutton(row, text="Flash", variable=self.flashing_var,
                                   bootstyle="success-round-toggle",  # type: ignore[call-arg]
                                   command=self._sync_flash_fields)
        flash_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(flash_cb, "Icons flash when buff timer is about to expire")
        self._flash_labels: list = []
        self.flash_threshold_var = tk.StringVar(value=str(cfg.get('timerFlashThreshold', 6)))
        self._flash_spin = labeled_spinbox(
            row, "Under:", self.flash_threshold_var, from_=0, to=11, width=3,
            tooltip="Icons flash when timer drops below this many seconds (0-11)",
            padx=(PAD_BUTTON_GAP, 0), label_sink=self._flash_labels)
        unit = ttk.Label(row, text="s", font=FONT_SMALL, foreground=THEME_COLORS['muted'])
        unit.pack(side='left')
        self._flash_labels = [(lbl, '') for lbl in self._flash_labels] + [(unit, THEME_COLORS['muted'])]

        row = _row(card)
        self.self_cast_var = tk.BooleanVar(value=cfg.get('selfCastOnly') is True)
        cb = ttk.Checkbutton(row, text="Applied by me", variable=self.self_cast_var,
                             command=self._changed)
        cb.pack(side='left')
        add_tooltip(cb, "Show an effect only while you are the one who applied it")
        return card

    def _build_overhead_card(self, parent):
        cfg = self._cfg
        card = create_card(parent, "Overhead")
        row = _row(card)
        self.plate_offset_var = tk.StringVar(value=str(cfg.get('plateOffset', 75)))
        labeled_spinbox(row, "Height:", self.plate_offset_var, from_=0, to=400, width=4,
                        tooltip="Room left for the game's nameplate between the head and the grid, in px",
                        padx=(PAD_BUTTON_GAP, PAD_XS))
        ttk.Label(row, text="px", font=FONT_SMALL, foreground=THEME_COLORS['muted']).pack(side='left')
        row = _row(card)
        self.max_distance_var = tk.StringVar(value=str(cfg.get('maxDistance', 40)))
        who = ("you (Over me), your group and friendly players" if self._type == 'friendly'
               else "your target and anyone fighting you or your group")
        labeled_spinbox(row, "Range:", self.max_distance_var, from_=5, to=100, width=4,
                        tooltip=f"Hidden past this distance. It shows over {who}.",
                        padx=(PAD_BUTTON_GAP, PAD_XS))
        ttk.Label(row, text="m", font=FONT_SMALL, foreground=THEME_COLORS['muted']).pack(side='left')
        self.show_self_var = tk.BooleanVar(value=cfg.get('showSelf', True))
        if self._type == 'friendly':
            row = _row(card)
            cb = ttk.Checkbutton(row, text="Over me", variable=self.show_self_var)
            cb.pack(side='left')
            add_tooltip(cb, "Also float this grid over your own character")
        return card

    def _build_sorting_card(self, parent):
        cfg = self._cfg
        card = create_card(parent, "Sorting")
        row = _row(card)
        self.fill_var = tk.StringVar()
        self.fill_combo = labeled_combobox(
            row, "Fill:", self.fill_var, [], width=22,
            tooltip=lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"),
            on_change=self._changed, padx=(PAD_BUTTON_GAP, 0))
        if self._band:
            # A band has no fill to choose: its rows centre over the head.
            self.fill_combo['values'] = [_BAND_FILL_LABEL]
            self.fill_var.set(_BAND_FILL_LABEL)
            self.fill_combo.configure(state='disabled')
        else:
            self.fill_var.set(_FILL_LABEL_BY_CODE.get(cfg.get('fillDirection', 'LR'), ''))
            self._sync_fill_options()
        row = _row(card)
        self.sort_var = tk.StringVar(value=_SORT_LABEL_BY_CODE.get(cfg.get('sortOrder', 'longest'),
                                                                   _SORT_LABEL_BY_CODE['longest']))
        labeled_combobox(row, "Sort:", self.sort_var, [label for _, label, _ in _SORT_OPTIONS], width=16,
                         tooltip=lambda: _SORT_DESCRIPTIONS.get(self.sort_var.get(), "How buffs are ordered"),
                         padx=(PAD_BUTTON_GAP, 0))
        row = _row(card)
        self.layout_var = tk.StringVar(value=_LAYOUT_LABEL_BY_CODE.get(cfg.get('layout', 'buffFirst'),
                                                                       _LAYOUT_LABEL_BY_CODE['buffFirst']))
        labeled_combobox(row, "Order:", self.layout_var, [label for _, label in _LAYOUT_OPTIONS], width=16,
                         tooltip="In Buffs First and Debuffs First, misc effects always lead. "
                                 "In Mixed, all buffs sort together by time.",
                         padx=(PAD_BUTTON_GAP, 0))
        return card

    # ------------------------------------------------------------------
    # Field rules
    # ------------------------------------------------------------------
    def _shape(self):
        """(rows, cols) as the fields read now, inside the grid's limits."""
        max_rows, max_cols = max_shape(self._type)
        return (_int(self.rows_var, self._cfg.get('rows', 1), 1, max_rows),
                _int(self.cols_var, self._cfg.get('cols', 1), 1, max_cols))

    def _on_shape(self, dim):
        """Rows or Cols moved: the edited one gives way to the slot limit."""
        rows, cols = self._shape()
        limit = max_slots(self._type)
        if rows * cols > limit:
            if dim == 'rows':
                rows = max(1, limit // cols)
                self.rows_var.set(str(rows))
            else:
                cols = max(1, limit // rows)
                self.cols_var.set(str(cols))
            app_toast(self.card, f"A grid holds at most {limit} slots", 'info', key='grid_resize')
        if not self._static:
            self._sync_fill_options()
        self._changed()

    def _sync_fill_options(self):
        """The Fill choices for the shape as it reads now; a fill that no
        longer fits falls back to the shape's default."""
        codes, default = valid_fills(*self._shape())
        labels = [_FILL_LABEL_BY_CODE[c] for c in codes]
        self.fill_combo['values'] = labels
        if self.fill_var.get() not in labels:
            self.fill_var.set(_FILL_LABEL_BY_CODE[default])

    def _on_timers(self):
        self._sync_timer_fields()
        self._changed()

    def _sync_timer_fields(self):
        """The Y offset moves the digits only, so it is greyed for Bar and Off."""
        digits = self.timer_style_var.get() == 'digits'
        self._timer_offset_spin.configure(state='normal' if digits else 'disabled')
        for lbl in self._timer_offset_labels:
            lbl.configure(foreground='' if digits else TK_COLORS['dim_text'])

    def _sync_flash_fields(self):
        """Under is greyed while Flash is off; every field stays, so the
        window never changes size."""
        on = bool(self.flashing_var.get())
        self._flash_spin.configure(state='normal' if on else 'disabled')
        for lbl, normal_fg in self._flash_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])

    # ------------------------------------------------------------------
    # Draft, Apply, Cancel
    # ------------------------------------------------------------------
    def draft(self):
        """The config with this dialog's values on top — what Apply would land."""
        cfg = self._cfg
        out = dict(cfg)
        out['id'] = self.id_var.get().strip()
        if self._band:
            slots = _int(self.max_slots_var, cfg.get('maxSlots', 10), 1, PLATE_MAX_SLOTS)
            cap = self.row_cap_var.get()
            rows, cols = band_shape(cap, slots)
            out.update(rowCap=cap, maxSlots=slots, rows=rows, cols=cols)
        else:
            out['rows'], out['cols'] = self._shape()
        if not self._plate:
            x = _int(self.x_var, self._px0[0], 0, self._res[0])
            y = _int(self.y_var, self._px0[1], 0, self._res[1])
            # Only a moved field rewrites its fraction: a px round trip would drift it.
            if x != self._px0[0]:
                out['fx'] = unproject_px(x, self._res[0])
            if y != self._px0[1]:
                out['fy'] = unproject_px(y, self._res[1])
        for key, var in (('scale', self.scale_var), ('gap', self.gap_var),
                         ('timerYOffset', self.timer_y_offset_var),
                         ('timerFlashThreshold', self.flash_threshold_var)):
            _, lo, hi = CLAMP_SPECS[key]
            out[key] = _int(var, cfg.get(key, lo), lo, hi)
        out['timerStyle'] = self.timer_style_var.get()
        out['enableFlashing'] = bool(self.flashing_var.get())
        out['selfCastOnly'] = bool(self.self_cast_var.get())
        if self._plate:
            out['plateOffset'] = _int(self.plate_offset_var, cfg.get('plateOffset', 75), 0, 400)
            out['maxDistance'] = _int(self.max_distance_var, cfg.get('maxDistance', 40), 5, 100)
            if self._type == 'friendly':
                out['showSelf'] = bool(self.show_self_var.get())
        if not self._static:
            if not self._band:
                out['fillDirection'] = _FILL_CODE_BY_LABEL.get(self.fill_var.get(), cfg.get('fillDirection'))
            out['sortOrder'] = _SORT_CODE_BY_LABEL.get(self.sort_var.get(), cfg.get('sortOrder', 'longest'))
            out['layout'] = _LAYOUT_CODE_BY_LABEL.get(self.layout_var.get(), cfg.get('layout', 'buffFirst'))
        return out

    def _changed(self):
        """Any field moved: the card's preview draws the draft."""
        self.card.preview_draft(self.draft())

    def apply(self):
        draft = self.draft()
        problem = self.card.name_problem(draft['id'])
        if problem:
            self._name_hint.configure(text=problem)
            self._name_hint.pack(anchor='w', after=self._name_entry.master, pady=(0, PAD_ROW))
            self._name_entry.focus_set()
            return
        self.card.apply_settings(draft)
        self._close()

    def cancel(self):
        self.card.cancel_draft()
        self._close()

    def _close(self):
        self.card.settings_dialog = None
        self.destroy()
