"""KazBars — Grid editor card (per-row CollapsibleSection).

`GridEditorPanel` is one card in the grids list. The container `GridsPanel`
(in `grids_panel.py`) creates/destroys these as the grid list changes.

Every card shows, collapsed or not: the title line (name, type, summary;
Move…, Enabled, ▲ ▼, ×), the grid drawn to scale (`GridPreview`) and the
names line under it. The preview is where buffs are chosen: a dynamic grid's
opens the Tracked Buffs picker, a static grid's cell opens it on that slot,
and a right-click (or Delete) clears a slot with an undo toast. The chevron
opens the settings form, every change redrawing the preview.

Module-level option maps (`_FILL_*`, `_LAYOUT_*`, `_SORT_*`) are private to
this module — the container does not read them.
"""

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import grid_preview
from .classes import CLASSES
from .grid_dialogs import BuffSelectorDialog
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
)
from .grid_preview_canvas import GridPreview
from .overlay import DEFAULT_SIZE
from .overlay_size import grid_metrics
from .ui_collapsible import CollapsibleSection
from .ui_forms import (
    labeled_combobox,
    labeled_spinbox,
    position_entry,
    size_slider,
)
from .ui_helpers import (
    CARD_STRIPE_PX,
    FONT_BODY_LG,
    FONT_FORM_LABEL,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    FONT_SYMBOL,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_MICRO,
    PAD_MID,
    PAD_ROW,
    PAD_TAB,
    PAD_XS,
    PREVIEW_RATIO,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import (
    add_tooltip,
    app_toast,
    bind_card_events,
    bind_label_hover_colors,
    bind_label_press_effect,
)

# How long a cleared slot stays undoable — the undo toast's own life.
_CLEAR_UNDO_S = 8
# The names line's width before the card is first laid out.
_NAMES_FALLBACK_W = 600


def _names_measure(widget):
    """`measure(text)` in the names line's font: one Font per Tk root, shared
    by every card under it."""
    root = widget._root()
    font = getattr(root, '_kz_names_font', None)
    if font is None:
        font = root._kz_names_font = tkfont.Font(root=root, font=FONT_SMALL)
    return font.measure


class GridEditorPanel(ttk.Frame):
    """A collapsible grid editor card."""

    def __init__(self, parent, database, grid_config, on_delete=None, initially_open=False,
                 get_base_size=None, on_resize=None, on_whitelist_changed=None,
                 name_in_use=None, on_edit=None, on_move=None, on_step=None):
        super().__init__(parent)
        self.database = database
        self.grid_config = grid_config
        self.on_delete = on_delete
        # The profile's overlay size, read live: the Size hint follows the
        # Grids toolbar's Overlay dropdown.
        self._get_base_size = get_base_size or (lambda: DEFAULT_SIZE)
        self._on_resize = on_resize
        self._on_whitelist_changed = on_whitelist_changed
        self._name_in_use = name_in_use
        self._on_edit = on_edit
        # on_move(card, class_id, copy): Move to… / Copy to… another class tab.
        self._on_move = on_move
        # on_step(card, delta): ▲ / ▼, one place up or down the listed cards.
        self._on_step = on_step
        # Cleared slots still undoable: slot -> (refs, when cleared).
        self._cleared = {}
        self._names = []
        self._names_w = 0
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()

        grid_type = grid_config.get('type', 'player')
        self._accent_color = GRID_TYPE_COLORS.get(grid_type, GRID_TYPE_COLORS['player'])
        # The type and slot mode are fixed at creation, so the card is built for them.
        self._plate = is_plate(grid_type)
        self._band = is_band(grid_config)

        self._resting_border_color = TK_COLORS['border']
        self._card = tk.Frame(self,
                               highlightbackground=self._resting_border_color,
                               highlightcolor=self._resting_border_color,
                               highlightthickness=1)
        card = self._card
        card.pack(fill='x')

        # Player/target identity lives on one 3px edge, not a full bright
        # outline — a column of cards reads as a list, not a stack of boxes.
        # Canvas, not Frame: an empty tk.Frame can repaint in the theme bg.
        # BOTH sizes must be explicit — the defaults are 378x265, and fill='y'
        # stretches the canvas without shrinking what it asks the card for.
        self._stripe = tk.Canvas(card, width=CARD_STRIPE_PX, height=1,
                                 highlightthickness=0, bg=self._accent_color)
        self._stripe.pack(side='left', fill='y')

        self.drag_handle = ttk.Label(card, text=" ☰ ", font=FONT_BODY_LG,
                                      foreground=THEME_COLORS['muted'], cursor='fleur',
                                      takefocus=True)
        self.drag_handle.pack(side='left', fill='y', padx=(PAD_MICRO, 0))
        self._handle_hovered = False
        self._handle_focused = False
        self.drag_handle.bind('<Enter>', lambda e: self._paint_drag_handle(hover=True))
        self.drag_handle.bind('<Leave>', lambda e: self._paint_drag_handle(hover=False))
        self.drag_handle.bind('<FocusIn>', lambda e: self._paint_drag_handle(focus=True))
        self.drag_handle.bind('<FocusOut>', lambda e: self._paint_drag_handle(focus=False))
        add_tooltip(self.drag_handle, "Drag to reorder — or Tab here, then Alt+↑/↓")

        self.section = CollapsibleSection(
            card, title=grid_config.get('id', 'Grid'),
            badge_text=grid_type,
            badge_color=self._accent_color,
            initially_open=initially_open,
            keep_summary=True,
        )
        self.section.pack(side='left', fill='x', expand=True,
                          padx=PAD_ROW, pady=(PAD_BUTTON_GAP, PAD_ROW))

        self._build_header_widgets()
        self._build_body()

        settings_col = ttk.Frame(self.section.content)
        settings_col.pack(fill='x')
        if not self._plate:
            self._build_position_row(settings_col)
        self._build_top_row(settings_col)
        self._build_icon_row(settings_col)
        if self._plate:
            self._build_overhead_row(settings_col)
        self._build_timer_row(settings_col)
        self._build_dynamic_row(settings_col)

        self.load_from_config()
        self._apply_enabled_styling(self.enabled_var.get())

        bind_card_events(card, lambda: self._resting_border_color)

    def _paint_drag_handle(self, *, hover=None, focus=None):
        """Hover and keyboard focus both light the ☰ handle, and either one alone
        keeps it lit — moving the mouse off a focused handle must not erase the
        only cue that Alt+↑/↓ is armed."""
        if hover is not None:
            self._handle_hovered = hover
        if focus is not None:
            self._handle_focused = focus
        lit = self._handle_hovered or self._handle_focused
        self.drag_handle.configure(
            foreground=THEME_COLORS['heading'] if lit else THEME_COLORS['muted'])

    def _build_header_widgets(self):
        """Pack the right-side header controls, left to right: Move…, Enabled,
        ▲ ▼ and × delete."""
        header = self.section.header_frame

        self.enabled_var = tk.BooleanVar(value=True)
        delete_label = ttk.Label(header, text="×",
                                 font=FONT_SYMBOL, foreground=THEME_COLORS['muted'],
                                 cursor='hand2', takefocus=True,
                                 padding=(PAD_XS, PAD_MICRO))
        delete_label.pack(side='right', padx=(PAD_XS, 0))
        for seq in ('<Button-1>', '<Return>', '<space>'):
            delete_label.bind(seq, lambda e: self.delete_grid())
        bind_label_hover_colors(delete_label, THEME_COLORS['muted'], THEME_COLORS['danger_text'])
        bind_label_press_effect(delete_label, THEME_COLORS['danger_text'])
        add_tooltip(delete_label, "Delete this grid")
        self._step_labels = {}
        for glyph, delta, tip in (("▼", 1, "Move this grid down the list"),
                                  ("▲", -1, "Move this grid up the list")):
            self._step_labels[delta] = self._make_step_label(header, glyph, delta, tip)
        if self._on_move is not None:
            move_label = ttk.Label(header, text="Move…", font=FONT_SMALL,
                                   foreground=THEME_COLORS['muted'], cursor='hand2',
                                   takefocus=True, padding=(PAD_XS, PAD_MICRO))
            move_label.pack(side='right', padx=(PAD_XS, 0))
            for seq in ('<Button-1>', '<Return>', '<space>'):
                move_label.bind(seq, lambda e, w=move_label: self._show_move_menu(w))
            bind_label_hover_colors(move_label, THEME_COLORS['muted'], THEME_COLORS['heading'])
            add_tooltip(move_label, "Move this grid to another class tab, or copy it there")
        ttk.Checkbutton(header, text="Enabled",
                        variable=self.enabled_var,
                        command=self._on_enabled_toggled,
                        bootstyle="success-round-toggle").pack(side='right', padx=(0, PAD_XS))  # type: ignore[call-arg]

    def _make_step_label(self, header, glyph, delta, tip):
        """▲ or ▼: a glyph label like ×, live unless the card sits at that end
        of the list (`set_step_state`)."""
        lbl = ttk.Label(header, text=glyph, font=FONT_SMALL, foreground=THEME_COLORS['muted'],
                        cursor='hand2', takefocus=True, padding=(PAD_MICRO, PAD_MICRO))
        lbl.pack(side='right', padx=(PAD_XS, 0))
        lbl.live = True  # type: ignore[attr-defined]

        def paint(hot):
            if lbl.live:  # type: ignore[attr-defined]
                lbl.configure(foreground=THEME_COLORS['heading'] if hot else THEME_COLORS['muted'])

        def fire(_e):
            if lbl.live and self._on_step is not None:  # type: ignore[attr-defined]
                self._on_step(self, delta)

        for seq in ('<Button-1>', '<Return>', '<space>'):
            lbl.bind(seq, fire)
        for seq, hot in (('<Enter>', True), ('<FocusIn>', True), ('<Leave>', False), ('<FocusOut>', False)):
            lbl.bind(seq, lambda e, h=hot: paint(h), add='+')
        add_tooltip(lbl, tip)
        return lbl

    def set_step_state(self, can_up, can_down):
        """Grey ▲ at the top of the list and ▼ at the bottom."""
        for delta, live in ((-1, can_up), (1, can_down)):
            lbl = self._step_labels[delta]
            lbl.live = live  # type: ignore[attr-defined]
            lbl.configure(foreground=THEME_COLORS['muted'] if live else TK_COLORS['menu_disabled_fg'],
                          cursor='hand2' if live else '', takefocus=live)

    def _build_body(self):
        """The always-visible part: the to-scale preview and the names line."""
        body = self.section.body
        self.preview = GridPreview(body, accent=self._accent_color, on_pick=self._on_pick,
                                   on_clear=self.clear_slot, tip_for=self._preview_tip)
        self.preview.pack(anchor='w', pady=(PAD_XS, PAD_MICRO))
        self.names_var = tk.StringVar()
        self._names_label = ttk.Label(body, textvariable=self.names_var, font=FONT_SMALL,
                                      foreground=THEME_COLORS['muted'])
        self._names_label.pack(anchor='w', fill='x')
        add_tooltip(self._names_label, self._names_tip)
        body.bind('<Configure>', self._on_body_resized, add='+')

    def _build_position_row(self, parent):
        """A screen grid's X / Y (an overhead grid floats over each character
        it shows on: no screen position)."""
        max_x, max_y = get_game_resolution_or_default()
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, PAD_ROW))
        ttk.Label(row, text="Position:", font=FONT_SMALL_BOLD,
                  foreground=THEME_COLORS['body']).pack(side='left', padx=(0, PAD_XS))
        position_entry(row, "X:", self.x_var, lo=0, hi=max_x,
                       tooltip="Horizontal position on screen (pixels from left edge)",
                       on_change=self._notify_edit,
                       label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, PAD_MID))
        position_entry(row, "Y:", self.y_var, lo=0, hi=max_y,
                       tooltip="Vertical position on screen (pixels from top edge)",
                       on_change=self._notify_edit,
                       label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, 0))

    def _show_move_menu(self, anchor):
        """Move to / Copy to, each listing All classes and the twelve classes;
        Move greys the grid's own. Built once per card, re-greyed per click."""
        targets = ((0, "All classes"), *((c.id, c.name) for c in CLASSES))
        menu = getattr(self, '_move_menu', None)
        if menu is None:
            menu = self._move_menu = tk.Menu(self, tearoff=0)
            for title, copy_it in (("Move to", False), ("Copy to", True)):
                sub = tk.Menu(menu, tearoff=0)
                for cid, name in targets:
                    sub.add_command(label=name,
                                    command=lambda c=cid, cp=copy_it: self._on_move(self, c, cp))
                menu.add_cascade(label=title, menu=sub)
                if not copy_it:
                    self._move_sub = sub
        own = self.grid_config.get('class', 0)
        for i, (cid, _name) in enumerate(targets):
            self._move_sub.entryconfigure(i, state='disabled' if cid == own else 'normal')
        menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

    def _build_top_row(self, parent):
        """Pack the Name + shape controls: Rows + Cols, or a band's Row cap +
        Max slots."""
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
        self._cols_var = tk.StringVar(value=str(cfg.get('cols', 5)))
        self._row_cap_var = tk.IntVar(value=cfg.get('rowCap', 5))
        self._max_slots_var = tk.StringVar(value=str(cfg.get('maxSlots', 10)))
        if self._band:
            ttk.Label(top_row, text="Row cap:", font=FONT_FORM_LABEL,
                      foreground=THEME_COLORS['muted']).pack(side='left')
            for cap in BAND_ROW_CAPS:
                rb = ttk.Radiobutton(top_row, text=str(cap), value=cap, variable=self._row_cap_var,
                                     command=self._on_band_changed, bootstyle='toolbutton')  # type: ignore[call-arg]
                rb.pack(side='left', padx=(PAD_MICRO, 0))
                add_tooltip(rb, "Icons to a row, centred over the head, before the next row starts above")
            labeled_spinbox(
                top_row, "Max slots:", self._max_slots_var, from_=1, to=PLATE_MAX_SLOTS, width=4,
                tooltip=f"The most icons the band shows (1-{PLATE_MAX_SLOTS})",
                on_change=self._on_band_changed,
                label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, 0),
            )
            return
        max_rows, max_cols = max_shape(cfg.get('type', 'player'))
        limit = max_slots(cfg.get('type', 'player'))
        labeled_spinbox(
            top_row, "Rows:", self._rows_var, from_=1, to=max_rows, width=4,
            tooltip=f"Grid rows (height). A grid holds up to {limit} slots.",
            on_change=lambda: self._on_dimension_changed('rows'),
            label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, PAD_MID),
        )
        labeled_spinbox(
            top_row, "Cols:", self._cols_var, from_=1, to=max_cols, width=4,
            tooltip=f"Grid columns (width). A grid holds up to {limit} slots.",
            on_change=lambda: self._on_dimension_changed('cols'),
            label_color=THEME_COLORS['muted'], padx=(PAD_MICRO, 0),
        )

    def _build_overhead_row(self, parent):
        """An overhead grid's Height (room for the nameplate) and Range, and a
        friendly grid's Over me."""
        cfg = self.grid_config
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, PAD_ROW))
        self._plate_offset_var = tk.IntVar(value=cfg.get('plateOffset', 75))
        labeled_spinbox(row, "Height:", self._plate_offset_var, from_=0, to=400, width=4,
            tooltip="Room left for the game's nameplate between the head and the grid, in px",
            on_change=self._notify_edit, padx=(PAD_BUTTON_GAP, PAD_XS))
        ttk.Label(row, text="px", foreground=THEME_COLORS['muted'],
                  font=FONT_SMALL).pack(side='left', padx=(0, PAD_TAB))
        self._max_distance_var = tk.IntVar(value=cfg.get('maxDistance', 40))
        who = ("you (Over me), your group and friendly players" if cfg.get('type') == 'friendly'
               else "your target and anyone fighting you or your group")
        labeled_spinbox(row, "Range:", self._max_distance_var, from_=5, to=100, width=4,
            tooltip=f"Hidden past this distance. It shows over {who}.",
            on_change=self._notify_edit, padx=(PAD_BUTTON_GAP, PAD_XS))
        ttk.Label(row, text="m", foreground=THEME_COLORS['muted'],
                  font=FONT_SMALL).pack(side='left', padx=(0, PAD_TAB))
        self._show_self_var = tk.BooleanVar(value=cfg.get('showSelf', True))
        if cfg.get('type') == 'friendly':
            cb = ttk.Checkbutton(row, text="Over me", variable=self._show_self_var,
                                 command=self._notify_edit)
            cb.pack(side='left')
            add_tooltip(cb, "Also float this grid over your own character")

    def _build_icon_row(self, parent):
        """Pack the Size slider (with its icon-size hint) and the gap."""
        icon_row = ttk.Frame(parent)
        icon_row.pack(fill='x', pady=(0, PAD_ROW))
        _, self.scale_var, self._refresh_size = size_slider(
            icon_row, self.grid_config.get('scale', 100),
            lambda p: f"{grid_metrics(self._get_base_size(), p).icon} px icons",
            on_commit=self._on_look_edit, on_move=self._on_size_moved,
            tooltip="Icon, timer and stack size, as a percent of the overlay size "
                    "(Overlay, top of the Grids tab)",
            padx=PAD_TAB)
        ttk.Separator(icon_row, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.gap_var = tk.IntVar()
        labeled_spinbox(icon_row, "Gap:", self.gap_var, from_=-5, to=10, width=3,
            tooltip="Space between icons (-5 = overlapping, 0 = touching, 10 = spaced out)",
            on_change=self._on_look_edit,
            padx=(PAD_BUTTON_GAP, PAD_MID))

    def refresh_size_hint(self):
        """The overlay size changed under this card: redraw the Size hint and
        the preview, which draws the icons at their baked size."""
        self._refresh_size()
        self._refresh_view()

    def _build_timer_row(self, parent):
        """Pack the Timers style + Y offset, the Flash group and Applied by me."""
        timer_row = ttk.Frame(parent)
        timer_row.pack(fill='x', pady=(0, PAD_ROW))
        self.timer_style_var = tk.StringVar()
        labeled_combobox(timer_row, "Timers:", self.timer_style_var,
            [label for _, label, _ in _TIMER_OPTIONS], width=6,
            tooltip=lambda: _TIMER_DESCRIPTIONS.get(self.timer_style_var.get(),
                                                    "How each icon shows its time left"),
            on_change=self._on_timers_clicked,
            padx=(PAD_BUTTON_GAP, PAD_MID))
        self._timer_offset_labels: list = []
        self.timer_y_offset_var = tk.IntVar()
        self._timer_offset_spin = labeled_spinbox(timer_row, "Y Offset:", self.timer_y_offset_var,
            from_=-10, to=10, width=3,
            tooltip="Shift the timer digits up/down relative to the icon (-10 to 10)",
            on_change=self._notify_edit,
            padx=(PAD_BUTTON_GAP, PAD_MID), label_sink=self._timer_offset_labels)

        flash_group = ttk.Frame(timer_row)
        flash_group.pack(side='left')
        ttk.Separator(flash_group, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.flashing_var = tk.BooleanVar()
        flash_cb = ttk.Checkbutton(flash_group, text="Flash",
                                    variable=self.flashing_var,
                                    bootstyle="success-round-toggle",  # type: ignore[call-arg]
                                    command=self._on_flash_clicked)
        flash_cb.pack(side='left', padx=(0, PAD_MID))
        add_tooltip(flash_cb, "Icons flash when buff timer is about to expire")

        self._flash_threshold_frame = ttk.Frame(flash_group)
        self._flash_threshold_frame.pack(side='left')
        self.flash_threshold_var = tk.IntVar()
        labeled_spinbox(self._flash_threshold_frame, "Under:", self.flash_threshold_var,
            from_=0, to=11, width=2,
            tooltip="Icons flash when timer drops below this many seconds (0-11)",
            on_change=self._notify_edit,
            padx=(PAD_BUTTON_GAP, 0))
        ttk.Label(self._flash_threshold_frame, text="s",
                  foreground=THEME_COLORS['muted'],
                  font=FONT_SMALL).pack(side='left')

        ttk.Separator(timer_row, orient='vertical').pack(side='left', fill='y', padx=PAD_XS)
        self.self_cast_var = tk.BooleanVar()
        self_cast_cb = ttk.Checkbutton(timer_row, text="Applied by me",
                                       variable=self.self_cast_var,
                                       command=self._on_look_edit)
        self_cast_cb.pack(side='left')
        add_tooltip(self_cast_cb, "Show an effect only while you are the one who applied it")

    def _build_dynamic_row(self, parent):
        """Pack the Fill/Sort/Order dynamic options."""
        self.dynamic_frame = ttk.Frame(parent)
        dyn_row = ttk.Frame(self.dynamic_frame)
        dyn_row.pack(fill='x', pady=(0, PAD_ROW))

        self.fill_var = tk.StringVar()
        self.fill_combo = labeled_combobox(dyn_row, "Fill:", self.fill_var, [], width=22,
            tooltip=lambda: _FILL_DESCRIPTIONS.get(self.fill_var.get(), "Direction buffs fill into the grid"),
            on_change=self._on_look_edit,
            padx=(PAD_BUTTON_GAP, PAD_TAB))

        self.sort_var = tk.StringVar()
        labeled_combobox(dyn_row, "Sort:", self.sort_var,
            [label for _, label, _ in _SORT_OPTIONS], width=16,
            tooltip=lambda: _SORT_DESCRIPTIONS.get(self.sort_var.get(), "How buffs are ordered"),
            on_change=self._notify_edit,
            padx=(PAD_BUTTON_GAP, PAD_TAB))

        self.layout_var = tk.StringVar()
        labeled_combobox(dyn_row, "Order:", self.layout_var,
            [label for _, label in _LAYOUT_OPTIONS], width=11,
            tooltip="In Buffs First and Debuffs First, misc effects always lead. In Mixed, all buffs sort together by time.",
            on_change=self._notify_edit,
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
        # Positions are stored as fractions; the fields display projected px at
        # the current game resolution. Display-only — never written back here
        # (a clamp writeback would silently corrupt the stored value).
        game_w, game_h = get_game_resolution_or_default()
        self.x_var.set(str(project_px(cfg.get('fx', 100 / 1920), game_w)))
        self.y_var.set(str(project_px(cfg.get('fy', 400 / 1080), game_h)))
        if self._band:
            self._row_cap_var.set(cfg.get('rowCap', 5))
            self._max_slots_var.set(str(cfg.get('maxSlots', 10)))
        if self._plate:
            self._plate_offset_var.set(cfg.get('plateOffset', 75))
            self._max_distance_var.set(cfg.get('maxDistance', 40))
            self._show_self_var.set(cfg.get('showSelf', True))
        self.scale_var.set(cfg.get('scale', 100))
        self._refresh_size()
        self.gap_var.set(max(-5, min(cfg.get('gap', -1), 10)))
        self.timer_style_var.set(_TIMER_LABEL_BY_CODE.get(cfg.get('timerStyle', 'digits'),
                                                           _TIMER_LABEL_BY_CODE['digits']))
        self.flash_threshold_var.set(cfg.get('timerFlashThreshold', 6))
        self.timer_y_offset_var.set(cfg.get('timerYOffset', 0))
        self.flashing_var.set(cfg.get('enableFlashing', True))
        self.self_cast_var.set(cfg.get('selfCastOnly') is True)
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

        self._refresh_view()

    def _refresh_view(self):
        """Redraw the preview, then the lines that read it (the summary says
        the ratio the preview settled on)."""
        self._update_preview()
        self.update_labels()

    def _update_preview(self, scale=None):
        """Draw the grid to scale: its icons at their baked size (`scale`,
        mid-drag, ahead of the stored one)."""
        if scale is None:
            scale = self.grid_config.get('scale', 100)
        icon = grid_metrics(self._get_base_size(), scale).icon
        self.preview.set_config(self.grid_config, icon, bool(self.enabled_var.get()))

    def _on_size_moved(self, scale):
        """A Size drag step: the preview and its ratio follow at once; the
        value itself commits on release."""
        self._update_preview(scale)
        self._update_summary()

    def _on_look_edit(self):
        """A field the preview or summary draws from changed (size, gap, fill,
        Applied by me): commit it, then redraw. The commit flushes every card's
        widgets into its config (`save_to_config`), so the redraw reads it."""
        self._notify_edit()
        if self._on_edit is None:
            self.save_to_config()
        self._refresh_view()

    def _validate_name(self, interactive=True):
        """Red on empty or duplicate, commit on valid. Never rewrites the field —
        deleting and blurring would otherwise snap the old name back. Duplicates
        are rejected because grid names key the generated AS2 whitelist tables:
        two grids sharing a name would silently share one whitelist in-game.
        `interactive=False` (the save_to_config flush) skips the toast so a
        duplicate left sitting in the field doesn't re-warn on every save.
        TclError-safe: the <FocusOut> binding can fire on a card mid-teardown
        during refresh_panels."""
        try:
            name = self.id_var.get().strip()
            if not name:
                self._name_entry.configure(bootstyle='danger')  # type: ignore[call-overload]
                return
            if self._name_in_use is not None and self._name_in_use(name, self.grid_config):
                self._name_entry.configure(bootstyle='danger')  # type: ignore[call-overload]
                if interactive:
                    app_toast(self, f"Grid name '{name}' is already used by another grid",
                              'warning', key='grid-name-dup')
                return
            self._name_entry.configure(bootstyle='default')  # type: ignore[call-overload]
            changed = self.grid_config.get('id') != name
            self.grid_config['id'] = name
            # interactive only: the save_to_config flush calls this with
            # interactive=False, and notifying from there would recurse
            # (notify → store mirror → save_to_config → here).
            if interactive and changed:
                self._notify_edit()
        except tk.TclError:
            pass

    def save_to_config(self):
        """Write current widget values back into the grid configuration dict."""
        self._validate_name(interactive=False)
        self.grid_config['enabled'] = self.enabled_var.get()
        var_map = {
            'scale': self.scale_var, 'gap': self.gap_var,
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
        if self._band:
            self._store_band_shape()
        else:
            max_rows, max_cols = max_shape(self.grid_config.get('type', 'player'))
            for key, var, hi in (('rows', self._rows_var, max_rows), ('cols', self._cols_var, max_cols)):
                try:
                    v = int(var.get())
                except (ValueError, tk.TclError):
                    v = self.grid_config.get(key, 1)
                self.grid_config[key] = max(1, min(v, hi))
        if self._plate:
            for key, var, lo, hi in (('plateOffset', self._plate_offset_var, 0, 400),
                                     ('maxDistance', self._max_distance_var, 5, 100)):
                try:
                    v = int(var.get())
                except (ValueError, tk.TclError):
                    v = self.grid_config.get(key, lo)
                self.grid_config[key] = max(lo, min(v, hi))
            if self.grid_config.get('type') == 'friendly':
                self.grid_config['showSelf'] = bool(self._show_self_var.get())
        else:
            # Position fields carry projected px; unproject back to fractions at
            # the current game resolution (typed overshoot clamps to the screen).
            game_w, game_h = get_game_resolution_or_default()
            for key, var, extent in (('fx', self.x_var, game_w), ('fy', self.y_var, game_h)):
                try:
                    px = max(0, min(int(var.get()), extent))
                except (ValueError, tk.TclError):
                    px = project_px(self.grid_config.get(key, 0.0), extent)
                self.grid_config[key] = unproject_px(px, extent)
        self.grid_config['timerStyle'] = _TIMER_CODE_BY_LABEL.get(
            self.timer_style_var.get(), self.grid_config.get('timerStyle', 'digits'))
        self.grid_config['enableFlashing'] = self.flashing_var.get()
        # Written only when on, so a grid that never set it saves unchanged.
        if self.self_cast_var.get():
            self.grid_config['selfCastOnly'] = True
        else:
            self.grid_config.pop('selfCastOnly', None)
        self.grid_config['fillDirection'] = _FILL_CODE_BY_LABEL.get(
            self.fill_var.get(), self.grid_config.get('fillDirection', 'LR'))
        self.grid_config['sortOrder'] = _SORT_CODE_BY_LABEL.get(
            self.sort_var.get(), self.grid_config.get('sortOrder', 'longest'))
        self.grid_config['layout'] = _LAYOUT_CODE_BY_LABEL.get(
            self.layout_var.get(), self.grid_config.get('layout', 'buffFirst'))

    def _name_of(self, ref):
        """A buff ref as its database name, `(missing #id)` when gone."""
        if isinstance(ref, str):
            return ref
        return (self.database.by_id.get(ref) or {}).get('name', f"(missing #{ref})")

    def _format_buff_preview(self, ids, max_show=4):
        """Comma-separated preview of buff names for up to *max_show* IDs."""
        names = [self._name_of(bid) for bid in ids[:max_show]]
        extra = f" + {len(ids) - max_show} more" if len(ids) > max_show else ""
        return ", ".join(names) + extra

    def _update_summary(self):
        cfg = self.grid_config
        shown_at = grid_preview.ratio_text(PREVIEW_RATIO[0], self.preview.ratio, PREVIEW_RATIO[1])
        self.section.set_summary("  " + grid_preview.summary(
            cfg, applied_by_me=bool(self.self_cast_var.get()), shown_at=shown_at))

    def update_labels(self):
        """Refresh the title, the summary and the names line."""
        self.section.set_title(self.grid_config.get('id', 'Grid'))
        self._update_summary()
        self._names = [self._name_of(ref) for ref in grid_preview.held_ids(self.grid_config)]
        self._draw_names()

    def _draw_names(self):
        """The names line, cut to the card's width: the buffs the grid holds,
        or what to click while it holds nothing."""
        nudge = grid_preview.empty_nudge(self.grid_config)
        if nudge is not None:
            self.names_var.set(nudge)
            return
        width = self.section.body.winfo_width()
        self._names_w = width
        self.names_var.set(grid_preview.names_line(
            self._names, _names_measure(self), width if width > 1 else _NAMES_FALLBACK_W))

    def _on_body_resized(self, event):
        if event.width != self._names_w:
            self._draw_names()

    def _names_tip(self):
        if not self._names:
            return grid_preview.empty_nudge(self.grid_config) or ""
        n = len(self._names)
        return f"{n} buff{'s' if n != 1 else ''}: " + ", ".join(self._names)

    def _preview_tip(self, slot):
        cfg = self.grid_config
        if cfg.get('slotMode') == 'static':
            if slot < 0:
                return "Click a slot to choose its buffs"
            return grid_preview.slot_tip(cfg, self._name_of, slot)
        if self._band:
            return f"Click to choose the buffs this grid tracks — it shows up to {cfg.get('maxSlots', 10)}"
        return "Click to choose the buffs this grid tracks"

    def _on_pick(self, slot):
        if slot is None:
            self.edit_whitelist()
        else:
            self.edit_slot(slot)

    def _buffs_changed(self):
        self.update_labels()
        if self._on_whitelist_changed:
            self._on_whitelist_changed()

    def edit_whitelist(self):
        """The Tracked Buffs picker on the whitelist (a dynamic grid's preview)."""
        self.save_to_config()
        dialog = BuffSelectorDialog(
            self.winfo_toplevel(), self.database, "Edit Tracked Buffs",
            initial_ids=self.grid_config.get('whitelist', []),
            layout=self.grid_config.get('layout', 'mixed'),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.grid_config['whitelist'] = dialog.result
            self._update_preview()
            self._buffs_changed()

    def edit_slot(self, slot):
        """The same picker on one static slot (a click on its cell)."""
        self.save_to_config()
        dialog = BuffSelectorDialog(
            self.winfo_toplevel(), self.database, f"Slot {slot} Buffs",
            initial_ids=grid_preview.slot_ids(self.grid_config, slot),
            layout=self.grid_config.get('layout', 'mixed'),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self._write_slot(slot, dialog.result)
            self._buffs_changed()

    def _write_slot(self, slot, refs):
        """Set (or, with no refs, drop) static slot `slot` and repaint its cell."""
        sa = self.grid_config.setdefault('slotAssignments', {})
        sa.pop(slot, None)
        if refs:
            sa[str(slot)] = list(refs)
        else:
            sa.pop(str(slot), None)
        self.preview.repaint_slot(slot)

    def clear_slot(self, slot):
        """Empty a static slot at once (right-click or Delete on its cell); the
        toast's click puts back every slot cleared while it showed."""
        refs = grid_preview.slot_ids(self.grid_config, slot)
        if not refs:
            return
        now = time.monotonic()
        self._cleared = {s: v for s, v in self._cleared.items() if now - v[1] < _CLEAR_UNDO_S}
        self._cleared[slot] = (refs, now)
        self._write_slot(slot, [])
        self._buffs_changed()
        app_toast(self, f"Cleared slot {slot} — click to undo", 'info', _CLEAR_UNDO_S,
                  key=f'grid-slot-clear-{id(self)}', on_click=self._undo_clear)

    def _undo_clear(self):
        """Refill the slots still empty since their clear; a slot filled again
        meanwhile keeps what it holds now."""
        cleared, self._cleared = self._cleared, {}
        if not self.winfo_exists():
            return
        restored = False
        for slot, (refs, _when) in cleared.items():
            if not grid_preview.slot_ids(self.grid_config, slot):
                self._write_slot(slot, refs)
                restored = True
        if restored:
            self._buffs_changed()

    def delete_grid(self):
        # No confirm — grids_panel shows an undo toast instead.
        if self.on_delete:
            self.on_delete(self)

    def _notify_edit(self):
        # Non-structural field edit → the container mirrors grids into the
        # profile store (structural changes notify via _on_resize instead).
        if self._on_edit:
            self._on_edit()

    def _on_enabled_toggled(self):
        self._apply_enabled_styling(self.enabled_var.get())
        self._notify_edit()

    def _apply_enabled_styling(self, enabled):
        """Drain the grid's identity colors when it's excluded from the build.

        Title, badge, and accent strips drop to greys; the left stripe falls
        back from the player/target accent to the neutral border color (the
        card outline is already neutral and stays put for hover). The Enabled
        toggle is the affordance — this is the visual consequence.
        """
        self._stripe.configure(
            bg=self._accent_color if enabled else TK_COLORS['border'])
        self.section.set_dimmed(not enabled)
        self._update_preview()

    def _on_timers_clicked(self):
        """Timers dropdown handler — load_from_config calls _on_timers_toggled
        directly so a profile load never arms the autosaver."""
        self._on_timers_toggled()
        self._notify_edit()

    def _on_timers_toggled(self):
        """The Y offset moves the digits only, so it is greyed for Bar and Off."""
        digits = _TIMER_CODE_BY_LABEL.get(self.timer_style_var.get()) == 'digits'
        self._timer_offset_spin.configure(state='normal' if digits else 'disabled')
        fg = '' if digits else TK_COLORS['dim_text']
        for lbl in self._timer_offset_labels:
            lbl.configure(foreground=fg)

    def _on_flash_clicked(self):
        self._on_flash_toggled()
        self._notify_edit()

    def _on_flash_toggled(self):
        if self.flashing_var.get():
            self._flash_threshold_frame.pack(side='left')
        else:
            self._flash_threshold_frame.pack_forget()

    def _store_band_shape(self):
        """A band's row cap and max slots, and the shape derived from them."""
        cap = self._row_cap_var.get()
        try:
            slots = max(1, min(int(self._max_slots_var.get()), PLATE_MAX_SLOTS))
        except (ValueError, tk.TclError):
            slots = self.grid_config.get('maxSlots', 10)
        rows, cols = band_shape(cap, slots)
        self.grid_config.update(rowCap=cap, maxSlots=slots, rows=rows, cols=cols, fillDirection='C')

    def _on_band_changed(self):
        self._store_band_shape()
        self._refresh_view()
        if self._on_resize:
            self._on_resize()

    def _on_dimension_changed(self, dim):
        gtype = self.grid_config.get('type', 'player')
        var = self._rows_var if dim == 'rows' else self._cols_var
        max_rows, max_cols = max_shape(gtype)
        limit = max_rows if dim == 'rows' else max_cols
        slots = max_slots(gtype)
        try:
            new_val = max(1, min(int(var.get()), limit))
        except (ValueError, tk.TclError):
            var.set(str(self.grid_config.get(dim, 1)))
            return
        old_val = self.grid_config.get(dim, 1)
        other_dim = self.grid_config.get('cols' if dim == 'rows' else 'rows', 1)
        if new_val * other_dim > slots:
            new_val = max(1, slots // other_dim)
            var.set(str(new_val))
            app_toast(self, f"A grid holds at most {slots} slots", 'info',
                      key='grid_resize')
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
        self._refresh_view()
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
        if self._band:
            # A band has no fill to choose: its rows centre over the head.
            self.fill_combo['values'] = [_BAND_FILL_LABEL]
            self.fill_var.set(_BAND_FILL_LABEL)
            self.fill_combo.configure(state='disabled')
            return
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
_BAND_FILL_LABEL = 'Centred'

_FILL_CODE_BY_LABEL = {label: code for code, label, _ in _FILL_OPTIONS}
_FILL_DESCRIPTIONS = {label: desc for _, label, desc in _FILL_OPTIONS}

_TIMER_OPTIONS = [
    # (persisted code, user-facing label, tooltip description)
    ('digits', 'Digits', 'Seconds left, under each icon'),
    ('bar',    'Bar',    'A line inside the icon\'s bottom edge that shrinks as time runs out'),
    ('off',    'Off',    'No timer'),
]
_TIMER_LABEL_BY_CODE = {code: label for code, label, _ in _TIMER_OPTIONS}
_TIMER_CODE_BY_LABEL = {label: code for code, label, _ in _TIMER_OPTIONS}
_TIMER_DESCRIPTIONS = {label: desc for _, label, desc in _TIMER_OPTIONS}

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
