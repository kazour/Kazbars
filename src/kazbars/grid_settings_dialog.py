"""
KazBars — Grid Settings dialog (a grid card's cog).

One modal window per grid, in the family of the Extras dialogs: a header,
titled cards, Cancel / Apply (Enter applies, Esc cancels), centred on the
app every time. Each card is one label / field grid whose label column is
the dialog's widest label, so fields start at one x across the window.
Cards, built only where they apply:

- **Grid**: Name; Rows × Cols, or a band's Row cap and Max slots; a screen
  grid's Position (X / Y).
- **Icons**: Size, Timer text and Stack text (Auto, or the grid's own pt),
  Gap, Timers (Bar / Digits / Off), their Y offset, Flash and its threshold.
- **Overhead** (overhead grids): Height, Range; Over me (friendly).
- **Sorting** (dynamic grids): Fill (a band's reads Centred), Sort, Order.

Every change rebuilds a draft (the settings this dialog owns, the shape
already through `grid_model.settle_box`) and hands it to the card, whose
preview draws it over the config live (`preview_draft`).
Cancel redraws the card from the stored config (`cancel_draft`); Apply hands
the draft to `apply_settings`, which lands it. The dialog never writes the
config itself.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import (
    BAND_ROW_CAP_DEFAULT,
    BAND_ROW_CAPS,
    BAND_SLOTS_DEFAULT,
    CLAMP_SPECS,
    PLATE_MAX_SLOTS,
    PLATE_SPECS,
    TEXT_PT_MAX,
    TEXT_PT_MIN,
    band_fields,
    get_game_resolution_or_default,
    is_band,
    is_plate,
    max_shape,
    max_slots,
    project_px,
    settle_box,
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
    INPUT_WIDTH_SORTING,
    MODULE_COLORS,
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
from .window_position import center_on_parent

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


class GridSettingsDialog(tk.Toplevel):
    """See the module docstring."""

    def __init__(self, card):
        top = card.winfo_toplevel()
        super().__init__(top)
        self.withdraw()
        self.card = card
        cfg = self._cfg = card.grid_config
        self._type = cfg.get('type', 'player')
        self._band = is_band(cfg)
        self._plate = is_plate(self._type)
        self._static = cfg.get('slotMode') == 'static'
        self.title(f"Grid Settings — {cfg.get('id', 'Grid')}")
        self.resizable(False, False)
        self.transient(top)
        self.grab_set()
        self._label_w = 0  # the widest label `_field` has made

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
            # sticky nsew: the two cards of a row share its height.
            c.grid(row=i // 2, column=i % 2, sticky='nsew',
                   padx=(0, PAD_SMALL) if i % 2 == 0 else 0, pady=(0, PAD_SMALL))
        body.columnconfigure(0, weight=1, uniform='card')
        body.columnconfigure(1, weight=1, uniform='card')
        for c in cards:
            c.columnconfigure(0, minsize=self._label_w + PAD_XS)

        footer = ttk.Frame(self, padding=(PAD_TAB, PAD_XS, PAD_TAB, PAD_TAB))
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text="Apply", bootstyle="success",  # type: ignore[call-arg]
                   command=self.apply, width=BTN_DIALOG).pack(side='right')
        self._cancel_btn = ttk.Button(footer, text="Cancel", bootstyle="secondary",  # type: ignore[call-arg]
                                      command=self.cancel, width=BTN_DIALOG)
        self._cancel_btn.pack(side='right', padx=(0, PAD_SMALL))

        self._sync_timer_fields()
        self._sync_flash_fields()

        center_on_parent(self, top)
        self.deiconify()
        self.bind('<Return>', self._on_return)
        self.bind('<Escape>', lambda e: self.cancel())
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Map>', lambda e: apply_dark_titlebar(self) if e.widget is self else None, add='+')
        self.after(0, self._name_entry.focus_set)

    # ------------------------------------------------------------------
    # Cards: one label / field grid each
    # ------------------------------------------------------------------
    @staticmethod
    def _card(parent, title):
        card = create_card(parent, title)
        card.next_row = 0  # type: ignore[attr-defined]
        return card

    def _field(self, card, label=None):
        """The next row of `card`: its label right-aligned in the label column
        (none for a hint row), and the frame its field widgets pack into.
        Returns (cell, label widget or None). Every label is measured, so
        the column the cards share fits the widest once they are built."""
        r = card.next_row
        card.next_row += 1
        lbl = None
        if label is not None:
            self._label_w = max(self._label_w, self.tk.call('font', 'measure', FONT_FORM_LABEL, label))
            lbl = ttk.Label(card, text=label, font=FONT_FORM_LABEL)
            lbl.grid(row=r, column=0, sticky='e', padx=(0, PAD_XS), pady=(0, PAD_ROW))
        cell = ttk.Frame(card)
        cell.grid(row=r, column=1, sticky='w', pady=(0, PAD_ROW))
        return cell, lbl

    @staticmethod
    def _unit(cell, text, padx=(PAD_XS, 0)):
        lbl = ttk.Label(cell, text=text, font=FONT_SMALL, foreground=THEME_COLORS['muted'])
        lbl.pack(side='left', padx=padx)
        return lbl

    def _build_grid_card(self, parent):
        cfg = self._cfg
        card = self._card(parent, "Grid")
        cell, _ = self._field(card, "Name:")
        self.id_var = tk.StringVar(value=cfg.get('id', 'Grid'))
        self._name_entry = ttk.Entry(cell, textvariable=self.id_var, width=22)
        self._name_entry.pack(side='left')
        add_tooltip(self._name_entry, "Display name for this grid (shown in preview mode)")
        # Always in place, empty until a failed Apply: the window never resizes.
        cell, _ = self._field(card)
        self._name_hint = ttk.Label(cell, font=FONT_SMALL, foreground=THEME_COLORS['danger_text'])
        self._name_hint.pack(side='left')
        self.id_var.trace_add('write', lambda *_: self._name_hint.configure(text=''))

        if self._band:
            self.row_cap_var = tk.IntVar(value=cfg.get('rowCap', BAND_ROW_CAP_DEFAULT))
            cell, _ = self._field(card, "Row cap:")
            for cap in BAND_ROW_CAPS:
                rb = ttk.Radiobutton(cell, text=str(cap), value=cap, variable=self.row_cap_var,
                                     command=self._changed, bootstyle='toolbutton')  # type: ignore[call-arg]
                rb.pack(side='left', padx=(0, PAD_MICRO))
                add_tooltip(rb, "Icons to a row, centred over the head, before the next row starts above")
            self.max_slots_var = tk.StringVar(value=str(cfg.get('maxSlots', BAND_SLOTS_DEFAULT)))
            cell, _ = self._field(card, "Max slots:")
            labeled_spinbox(cell, None, self.max_slots_var, from_=1, to=PLATE_MAX_SLOTS, width=4,
                            tooltip=f"The most icons the band shows (1-{PLATE_MAX_SLOTS})",
                            on_change=self._changed)
        else:
            max_rows, max_cols = max_shape(self._type)
            limit = max_slots(self._type)
            self.rows_var = tk.StringVar(value=str(cfg.get('rows', 1)))
            self.cols_var = tk.StringVar(value=str(cfg.get('cols', 1)))
            cell, _ = self._field(card, "Rows × Cols:")
            labeled_spinbox(cell, None, self.rows_var, from_=1, to=max_rows, width=4,
                            tooltip=f"Grid rows (height). A grid holds up to {limit} slots.",
                            on_change=lambda: self._on_shape('rows'))
            self._unit(cell, "×", padx=PAD_XS)
            labeled_spinbox(cell, None, self.cols_var, from_=1, to=max_cols, width=4,
                            tooltip=f"Grid columns (width). A grid holds up to {limit} slots.",
                            on_change=lambda: self._on_shape('cols'))
            # The shape as last settled: a side typed into since (no arrow,
            # focus-out or Enter yet) is the one `draft` lets give way, and a
            # field read as nothing mid-edit reads as its settled value.
            self._settled = (cfg.get('rows', 1), cfg.get('cols', 1))
            self._settled = self._shape()

        if not self._plate:
            # Positions are fractions; the fields show px at the game resolution.
            self._res = get_game_resolution_or_default()
            self._px0 = (project_px(cfg.get('fx', 0.0), self._res[0]),
                         project_px(cfg.get('fy', 0.0), self._res[1]))
            self.x_var = tk.StringVar(value=str(self._px0[0]))
            self.y_var = tk.StringVar(value=str(self._px0[1]))
            cell, _ = self._field(card, "Position:")
            position_entry(cell, "X", self.x_var, lo=0, hi=self._res[0],
                           tooltip="Horizontal position on screen (pixels from left edge)",
                           label_color=THEME_COLORS['muted'], padx=(PAD_XS, PAD_MID))
            position_entry(cell, "Y", self.y_var, lo=0, hi=self._res[1],
                           tooltip="Vertical position on screen (pixels from top edge)",
                           label_color=THEME_COLORS['muted'], padx=(PAD_XS, 0))
        return card

    def _build_icons_card(self, parent):
        cfg = self._cfg
        card = self._card(parent, "Icons")
        cell, _ = self._field(card, "Size:")
        _, self.scale_var = size_slider(
            cell, cfg.get('scale', CLAMP_SPECS['scale'][0]),
            lambda p: f"{grid_metrics(self.card.base_size(), p).icon} px icons",
            label=None, on_move=lambda p: self._on_size_move(),
            tooltip="Icon size, and timer and stack text on Auto, as a percent of the overlay size "
                    "(Overlay, top of the Grids tab)")
        # key -> (auto var, pt var, spinbox, row label): Auto shows the size
        # rules' value and follows the slider; unticked, the grid's own pt.
        self._text_rows = {}
        for key, label, what in (('timerPt', "Timer text:", "timer digits"),
                                 ('stackPt', "Stack text:", "stack count")):
            cell, lbl = self._field(card, label)
            own = cfg.get(key)
            auto_var = tk.BooleanVar(value=own is None)
            pt_var = tk.StringVar(value=str(own if own is not None else self._auto_pt(key)))
            auto_cb = ttk.Checkbutton(cell, text="Auto", variable=auto_var,
                                      command=self._on_text_auto)
            auto_cb.pack(side='left', padx=(0, PAD_MID))
            add_tooltip(auto_cb, f"Size the {what} from the Size slider; "
                                 f"untick to set your own pt")
            spin = labeled_spinbox(cell, None, pt_var, from_=TEXT_PT_MIN, to=TEXT_PT_MAX, width=4,
                                   tooltip=f"The {what} in game, {TEXT_PT_MIN}-{TEXT_PT_MAX} pt. "
                                           f"Your own size is used exactly, whatever Size says; "
                                           f"large text can spill past the icon",
                                   on_change=self._changed)
            self._unit(cell, "pt")
            self._text_rows[key] = (auto_var, pt_var, spin, lbl)
        default, lo, hi = CLAMP_SPECS['gap']
        self.gap_var = tk.StringVar(value=str(max(lo, min(cfg.get('gap', default), hi))))
        cell, _ = self._field(card, "Gap:")
        labeled_spinbox(cell, None, self.gap_var, from_=lo, to=hi, width=4,
                        tooltip=f"Space between icons ({lo} = overlapping, 0 = touching, "
                                f"{hi} = spaced out)",
                        on_change=self._changed)

        cell, _ = self._field(card, "Timers:")
        self.timer_style_var = tk.StringVar(value=cfg.get('timerStyle', 'digits'))
        for code, label, tip in _TIMER_OPTIONS:
            rb = ttk.Radiobutton(cell, text=label, value=code, variable=self.timer_style_var,
                                 command=self._on_timers, bootstyle='toolbutton')  # type: ignore[call-arg]
            rb.pack(side='left', padx=(0, PAD_MICRO))
            add_tooltip(rb, tip)
        default, lo, hi = CLAMP_SPECS['timerYOffset']
        self.timer_y_offset_var = tk.StringVar(value=str(cfg.get('timerYOffset', default)))
        cell, self._timer_offset_label = self._field(card, "Y offset:")
        self._timer_offset_spin = labeled_spinbox(
            cell, None, self.timer_y_offset_var, from_=lo, to=hi, width=4,
            tooltip=f"Shift the timer digits up/down relative to the icon ({lo} to {hi})")

        cell, _ = self._field(card, "Flash:")
        self.flashing_var = tk.BooleanVar(value=cfg.get('enableFlashing', True))
        flash_cb = ttk.Checkbutton(cell, variable=self.flashing_var,
                                   bootstyle="success-round-toggle",  # type: ignore[call-arg]
                                   command=self._sync_flash_fields)
        flash_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(flash_cb, "Icons flash when buff timer is about to expire")
        default, lo, hi = CLAMP_SPECS['timerFlashThreshold']
        self.flash_threshold_var = tk.StringVar(value=str(cfg.get('timerFlashThreshold', default)))
        under = ttk.Label(cell, text="Under", font=FONT_FORM_LABEL)
        under.pack(side='left', padx=(0, PAD_XS))
        self._flash_spin = labeled_spinbox(
            cell, None, self.flash_threshold_var, from_=lo, to=hi, width=4,
            tooltip=f"Icons flash when timer drops below this many seconds ({lo}-{hi})")
        self._flash_labels = [(under, ''), (self._unit(cell, "s"), THEME_COLORS['muted'])]
        return card

    def _build_overhead_card(self, parent):
        cfg = self._cfg
        card = self._card(parent, "Overhead")
        default, lo, hi = PLATE_SPECS['plateOffset']
        self.plate_offset_var = tk.StringVar(value=str(cfg.get('plateOffset', default)))
        cell, _ = self._field(card, "Height:")
        labeled_spinbox(cell, None, self.plate_offset_var, from_=lo, to=hi, width=4,
                        tooltip="Room left for the game's nameplate between the head and the grid, in px")
        self._unit(cell, "px")
        default, lo, hi = PLATE_SPECS['maxDistance']
        self.max_distance_var = tk.StringVar(value=str(cfg.get('maxDistance', default)))
        who = ("you (Over me), your group and friendly players" if self._type == 'friendly'
               else "your target and anyone fighting you or your group")
        cell, _ = self._field(card, "Range:")
        labeled_spinbox(cell, None, self.max_distance_var, from_=lo, to=hi, width=4,
                        tooltip=f"Hidden past this distance. It shows over {who}.")
        self._unit(cell, "m")
        self.show_self_var = tk.BooleanVar(value=cfg.get('showSelf', True))
        if self._type == 'friendly':
            cell, _ = self._field(card, "Over me:")
            cb = ttk.Checkbutton(cell, variable=self.show_self_var,
                                 bootstyle="success-round-toggle")  # type: ignore[call-arg]
            cb.pack(side='left')
            add_tooltip(cb, "Also float this grid over your own character")
        return card

    def _build_sorting_card(self, parent):
        cfg = self._cfg
        card = self._card(parent, "Sorting")
        self.fill_var = tk.StringVar()
        cell, _ = self._field(card, "Fill:")
        self.fill_combo = labeled_combobox(
            cell, None, self.fill_var, [], width=INPUT_WIDTH_SORTING,
            tooltip=lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"),
            on_change=self._changed)
        if self._band:
            # A band has no fill to choose: its rows centre over the head.
            self.fill_combo['values'] = [_BAND_FILL_LABEL]
            self.fill_var.set(_BAND_FILL_LABEL)
            self.fill_combo.configure(state='disabled')
        else:
            self.fill_var.set(_FILL_LABEL_BY_CODE.get(cfg.get('fillDirection', 'LR'), ''))
            self._sync_fill_options()
        self.sort_var = tk.StringVar(value=_SORT_LABEL_BY_CODE.get(cfg.get('sortOrder', 'longest'),
                                                                   _SORT_LABEL_BY_CODE['longest']))
        cell, _ = self._field(card, "Sort:")
        labeled_combobox(cell, None, self.sort_var, [label for _, label, _ in _SORT_OPTIONS],
                         width=INPUT_WIDTH_SORTING,
                         tooltip=lambda: _SORT_DESCRIPTIONS.get(self.sort_var.get(), "How buffs are ordered"))
        self.layout_var = tk.StringVar(value=_LAYOUT_LABEL_BY_CODE.get(cfg.get('layout', 'buffFirst'),
                                                                       _LAYOUT_LABEL_BY_CODE['buffFirst']))
        cell, _ = self._field(card, "Order:")
        labeled_combobox(cell, None, self.layout_var, [label for _, label in _LAYOUT_OPTIONS],
                         width=INPUT_WIDTH_SORTING,
                         tooltip="In Buffs First and Debuffs First, misc effects always lead. "
                                 "In Mixed, all buffs sort together by time.")
        return card

    # ------------------------------------------------------------------
    # Field rules
    # ------------------------------------------------------------------
    def _shape(self):
        """(rows, cols) as the fields read now, each inside its max; one that
        reads as nothing mid-edit is its settled value, as its Enter restores."""
        max_rows, max_cols = max_shape(self._type)
        return (_int(self.rows_var, self._settled[0], 1, max_rows),
                _int(self.cols_var, self._settled[1], 1, max_cols))

    def _on_shape(self, dim):
        """Rows or Cols (`dim`) moved: the shape rules (`settle_box`, the
        edited side giving way to the slot limit) run at once and the fields
        show their result, with a toast when one gave way."""
        rows, cols = self._shape()
        new_rows, new_cols, _ = settle_box(rows, cols, '', self._type, not self._static, give=dim)
        self._settled = (new_rows, new_cols)
        if (new_rows, new_cols) != (rows, cols):
            self.rows_var.set(str(new_rows))
            self.cols_var.set(str(new_cols))
            msg = (f"A grid holds at most {max_slots(self._type)} slots" if rows * cols > 1
                   else "Dynamic grids need at least 2 slots, switched to 1×2")
            app_toast(self.card, msg, 'info', key='grid_resize')
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
        self._timer_offset_label.configure(foreground='' if digits else TK_COLORS['dim_text'])
        self._sync_text_fields()

    def _auto_pt(self, key):
        """What the size rules give the timer / stack at the slider's Size."""
        m = grid_metrics(self.card.base_size(), self.scale_var.get())
        return m.timer if key == 'timerPt' else m.stack

    def _sync_text_fields(self):
        """An Auto size shows the rules' value, greyed; Timer text sizes the
        digits only, so the whole row is greyed for Bar and Off."""
        digits = self.timer_style_var.get() == 'digits'
        for key, (auto_var, pt_var, spin, lbl) in self._text_rows.items():
            auto = auto_var.get()
            if auto:
                pt_var.set(str(self._auto_pt(key)))
            live = key != 'timerPt' or digits
            spin.configure(state='normal' if live and not auto else 'disabled')
            lbl.configure(foreground='' if live else TK_COLORS['dim_text'])

    def _on_size_move(self):
        self._sync_text_fields()
        self._changed()

    def _on_text_auto(self):
        self._sync_text_fields()
        self._changed()

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
        """The settings this dialog owns, as Apply would land them: the shape
        through `settle_box` (a band's from its row cap and max slots)."""
        cfg = self._cfg
        out = {'id': self.id_var.get().strip()}
        if self._band:
            slots = _int(self.max_slots_var, cfg.get('maxSlots', BAND_SLOTS_DEFAULT), 1, PLATE_MAX_SLOTS)
            out.update(band_fields(self.row_cap_var.get(), slots))
        else:
            fill = (_FILL_CODE_BY_LABEL.get(self.fill_var.get(), cfg.get('fillDirection'))
                    if not self._static else cfg.get('fillDirection'))
            rows, cols = self._shape()
            give = 'rows' if rows != self._settled[0] else 'cols'
            out['rows'], out['cols'], out['fillDirection'] = settle_box(
                rows, cols, fill, self._type, not self._static, give=give)
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
            default, lo, hi = CLAMP_SPECS[key]
            out[key] = _int(var, cfg.get(key, default), lo, hi)
        for key, (auto_var, pt_var, _, _) in self._text_rows.items():
            out[key] = (None if auto_var.get()
                        else _int(pt_var, cfg.get(key) or self._auto_pt(key), TEXT_PT_MIN, TEXT_PT_MAX))
        out['timerStyle'] = self.timer_style_var.get()
        out['enableFlashing'] = bool(self.flashing_var.get())
        if self._plate:
            for key, var in (('plateOffset', self.plate_offset_var),
                             ('maxDistance', self.max_distance_var)):
                default, lo, hi = PLATE_SPECS[key]
                out[key] = _int(var, cfg.get(key, default), lo, hi)
            if self._type == 'friendly':
                out['showSelf'] = bool(self.show_self_var.get())
        if not self._static:
            out['sortOrder'] = _SORT_CODE_BY_LABEL.get(self.sort_var.get(), cfg.get('sortOrder', 'longest'))
            out['layout'] = _LAYOUT_CODE_BY_LABEL.get(self.layout_var.get(), cfg.get('layout', 'buffFirst'))
        return out

    def _changed(self):
        """Any field moved: the card's preview draws the draft."""
        self.card.preview_draft(self.draft())

    def _on_return(self, _event):
        # Enter on the focused Cancel button cancels; anywhere else it applies.
        if self.focus_get() is self._cancel_btn:
            self.cancel()
        else:
            self.apply()

    def apply(self):
        draft = self.draft()
        problem = self.card.name_problem(draft['id'])
        if problem:
            self._name_hint.configure(text=problem)
            self._name_entry.focus_set()
            return
        card = self._close()
        if card is not None:
            card.apply_settings(draft)

    def cancel(self):
        card = self._close()
        if card is not None:
            card.cancel_draft()

    def _close(self):
        """Close first, then touch the card: a dialog that fails before it
        closes keeps its grab. Returns the card, None if it is gone (nothing
        rebuilds the list under the dialog's grab: the app's shortcuts wait)."""
        card = self.card
        self.destroy()
        try:
            if card.winfo_exists():
                card.settings_dialog = None
                return card
        except tk.TclError:
            pass
        return None
