"""
KazBars — Grid Editor Panel
Grid configuration UI: the class tabs and the list of grid cards (add, delete,
reorder by drag or Alt+arrows), the empty state's presets, and grids files (a
card's Export grid…; File ▸ Import grid… lands in `append_grids`).
"""

import copy
import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)


from . import grid_preview, grid_templates
from .classes import CLASSES, by_id
from .extras_shortcuts import ExtrasShortcutsRow
from .grid_dialogs import AddGridWizard
from .grid_editor_panel import GridEditorPanel
from .grid_model import (
    create_default_grid,
    dedupe_grid_ids,
    default_grid_name,
    get_game_resolution_or_default,
    is_plate,
    set_class,
    snap_row_cap,
    validate_grid,
)
from .grids_generator import free_id, grid_holds
from .overlay import DEFAULT_FONT, DEFAULT_SIZE, FONT_CHOICES, SIZE_CHOICES, font_label
from .overlay_size import SCALE_DEFAULT, grid_metrics
from .prefs import ANCHOR_SIDE_DEFAULT, ANCHOR_UP_DEFAULT
from .profile_document import build_signature
from .profile_io import custom_buffs_suffix, save_yaml_file
from .profile_share import GRIDS_EXT
from .settings_manager import get_setting, set_setting
from .ui_components import (
    DragReorderManager,
    create_scrollable_frame,
    scroll_widget_into_view,
)
from .ui_helpers import (
    BTN_MEDIUM,
    FONT_BODY,
    FONT_BODY_LG,
    FONT_HEADING,
    FONT_SMALL,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_LIST_ITEM,
    PAD_ROW,
    PAD_SECTION_GAP,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    PRESET_CARD_BAR_LONG,
    PRESET_CARD_BAR_SHORT,
    PRESET_CARD_SQUARE,
    PRESET_LABEL_AREA,
    PREVIEW_RATIO,
    PREVIEW_SLOT_SPACING,
    STEP_BADGE_PX,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import (
    add_tooltip,
    app_toast,
    bind_label_hover_colors,
    bind_label_press_effect,
)


# ============================================================================
# GRIDS PANEL
# ============================================================================
class GridsPanel(ttk.Frame):
    """Grid editor panel: switches between empty state and toolbar+cards normal view."""

    def __init__(self, parent, database, on_modified=None, app=None):
        super().__init__(parent)
        self.database = database
        self.on_modified = on_modified
        self.app = app

        self.grids = []
        self.grid_panels = []
        self._tip_dismissed = False
        # The step guide is a first-run thing: it retires for good once a build
        # has ever landed. Latched at construction rather than read live, because
        # `has_built_before` flips one line after notify_build_done() — a live
        # read would yank the completed checklist out from under the first-time
        # user on whatever they touched next, before they'd seen it go green.
        self._onboarding = not get_setting('has_built_before')
        self._build_done = False
        self._profile_generation = 0

        self._create_widgets()
        self.refresh_panels()

    def _create_widgets(self):
        """Build normal view (toolbar + scroll) and empty state frame."""
        self._normal_view = ttk.Frame(self)

        # A child of self, packed first: the Overlay row sizes the extras too,
        # so it stays on screen in the zero-grids empty state.
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', padx=PAD_TAB, pady=PAD_SMALL)
        ttk.Button(toolbar, text="+ Add Grid", command=self.add_grid,
                   width=BTN_MEDIUM).pack(side='left', padx=PAD_BUTTON_GAP)
        self._build_overlay_row(toolbar)
        self._build_class_tabs()

        self._build_tip_bar()

        # Extras shortcuts — a child of self (not _normal_view) packed once
        # right here, so the row stays on screen in the zero-grids empty state
        # too. `side='bottom'` before the state widgets claims the bottom strip
        # next to Build & Install, so off-by-default add-ons never push the
        # grids down the page; the state widgets take what is left, and the tip
        # bar still anchors `before` it (pack order, not position).
        self.extras_row = None
        self.build_status_lbl = None
        if self.app is not None:
            self.extras_row = ExtrasShortcutsRow(self, self.app)
            self.extras_row.pack(side='bottom', fill='x', padx=PAD_TAB,
                                 pady=(PAD_XS, 0))
            # In-game status line above the cards (both pack side='bottom',
            # so `after` puts this one on top of them) — packed by
            # refresh_build_status() once a build has been recorded.
            self.build_status_lbl = ttk.Label(self, font=FONT_SMALL,
                                               foreground=THEME_COLORS['muted'])

        content = ttk.Frame(self._normal_view)
        content.pack(fill='both', expand=True, padx=PAD_SMALL, pady=PAD_SMALL)

        grids_container = ttk.Frame(content)
        grids_container.pack(fill='both', expand=True)
        outer, self.grids_frame, self.grids_canvas = create_scrollable_frame(
            grids_container)
        outer.pack(fill='both', expand=True)
        self._tab_empty_lbl = ttk.Label(self.grids_frame, font=FONT_BODY,
                                        foreground=THEME_COLORS['muted'])

        self._drag_manager = DragReorderManager(
            self.grids_canvas, self.grids_frame, self._reorder_grid)

        self._empty_state = self._build_empty_state()

    def _build_overlay_row(self, toolbar):
        """`Overlay: [size] Font: [face]` — the profile-wide base size every
        in-game size derives from, and the face of every text KazBars.swf
        draws. Written to the `overlay` section on selection."""
        self._size_labels = {size: label for size, label in SIZE_CHOICES}
        self._size_by_label = {label: size for size, label in SIZE_CHOICES}
        self._font_by_label = {font_label(f): f for f in FONT_CHOICES}
        self._overlay_font_var = tk.StringVar()
        font_combo = ttk.Combobox(toolbar, textvariable=self._overlay_font_var,
                                  values=list(self._font_by_label), width=22, state='readonly')
        font_combo.pack(side='right')
        font_combo.bind('<<ComboboxSelected>>', lambda _e: self._on_overlay_changed())
        add_tooltip(font_combo, "The font of everything KazBars draws in game")
        ttk.Label(toolbar, text="Font:", font=FONT_BODY,
                  foreground=THEME_COLORS['muted']).pack(side='right', padx=(PAD_TAB, PAD_XS))
        self._overlay_size_var = tk.StringVar()
        size_combo = ttk.Combobox(toolbar, textvariable=self._overlay_size_var,
                                  values=list(self._size_by_label), width=20, state='readonly')
        size_combo.pack(side='right')
        size_combo.bind('<<ComboboxSelected>>', lambda _e: self._on_overlay_changed())
        add_tooltip(size_combo,
                    "The base size of everything KazBars draws in game. Each grid and "
                    "panel has its own Size, a percent of this.")
        ttk.Label(toolbar, text="Overlay:", font=FONT_BODY,
                  foreground=THEME_COLORS['muted']).pack(side='right', padx=(0, PAD_XS))

    def _build_class_tabs(self):
        """`All classes | Guard Conq DT | PoM ToS BS | Barb Sin Ranger | Demo Necro
        HoX`: one group per archetype, each tab showing a count of its own grids,
        the tabs stretched to the row's width. A tab lists its own grids only —
        All classes the classless grids, a class tab the grids with its class (in
        game a class builds both). The tab is the `grids_tab` pref, so the panel
        reopens where it was left."""
        row = ttk.Frame(self)
        row.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
        self._tab_var = tk.IntVar(value=get_setting('grids_tab') or 0)
        self._tab_buttons: dict[int, tuple[ttk.Radiobutton, str]] = {}
        groups = [[(0, "All classes", "Grids built for every class. In game each class gets "
                              "these as well as its own.")]]
        for archetype in range(4):
            groups.append([(c.id, c.short, f"{c.name}: its own grids.")
                           for c in CLASSES if c.archetype == archetype])
        col = 0
        for gi, group in enumerate(groups):
            for k, (cid, short, tip) in enumerate(group):
                rb = ttk.Radiobutton(row, text=short, value=cid, variable=self._tab_var,
                                     command=self._on_tab_changed,
                                     bootstyle='toolbutton')  # type: ignore[call-arg]
                rb.grid(row=0, column=col, sticky='ew',
                        padx=(PAD_TAB if gi and k == 0 else 0, 0))
                row.columnconfigure(col, weight=1)
                col += 1
                add_tooltip(rb, tip)
                self._tab_buttons[cid] = (rb, short)

    def _tab_class(self):
        """The current tab's class id, or None for All."""
        return self._tab_var.get() or None

    def _visible(self):
        """Indexes into `self.grids` of the grids the current tab lists."""
        cls = self._tab_class()
        return [i for i, g in enumerate(self.grids) if g.get('class') == cls]

    def _update_tab_counts(self):
        for cid, (rb, short) in self._tab_buttons.items():
            n = sum(1 for g in self.grids if g.get('class') == (cid or None))
            rb.configure(text=f"{short} {n}" if n else short)

    def _on_tab_changed(self):
        set_setting('grids_tab', self._tab_var.get())
        self._repack_panels()

    def move_or_copy(self, panel, class_id, copy_it):
        """Move to… (the grid's `class` set to `class_id`, 0 All) or Copy to… (a
        duplicate for that class, its id `<id> <short>` kept clear of every
        other grid's archive key). Says what it did in a toast."""
        grid = panel.grid_config
        short = by_id(class_id).short if class_id else "All"
        if copy_it:
            dup = copy.deepcopy(grid)
            dup['id'] = free_id([g['id'] for g in self.grids], f"{grid['id']} {short}")
            set_class(dup, class_id)
            self.grids.append(dup)
            self._mark_modified()
            self.refresh_panels()
            app_toast(self, f"Copied '{grid['id']}' to {short} as '{dup['id']}'", 'info',
                      key='grids_class')
        else:
            set_class(grid, class_id)
            self._mark_modified()
            self._repack_panels()
            app_toast(self, f"Moved '{grid['id']}' to {short}", 'info', key='grids_class')

    # ------------------------------------------------------------------
    # Grids files: Export grid… (a card's Move… menu); File ▸ Import grid…
    # lands in `append_grids`
    # ------------------------------------------------------------------
    def export_grid(self, panel):
        """One grid, with the custom buffs it references, to a grids file."""
        grid = panel.grid_config
        db = self.database
        value = grid_templates.build([grid], db.by_id, db.by_name, db.provenance)
        path = save_yaml_file(value, title="Export Grid", ext=GRIDS_EXT, label="KazBars grids",
                              stem=grid['id'], noun="grids")
        if path is None:
            return
        suffix = custom_buffs_suffix(len(value.get('buffs', [])))
        app_toast(self, f"Exported ‘{grid['id']}’ to “{path.name}”{suffix}", 'success')

    def append_grids(self, grids):
        """A grids file's grids appended to the current tab: each validated,
        on the tab's class, under a free name (`grid_templates.import_into`),
        its refs normalised as a load does (unresolved ones kept, greyed).
        Returns ``(appended, renames)``."""
        appended, renames = grid_templates.import_into(self.grids, grids, self._tab_class())
        for grid in appended:
            self._migrate_grid(grid, [])
        self.grids.extend(appended)
        self._mark_modified()
        self.refresh_panels()
        if appended:
            # The new cards land at the end of the tab: bring the first into view
            # once the Grids view shows.
            first = self.grid_panels[-len(appended)]
            self.after_idle(lambda: first.winfo_exists()
                            and scroll_widget_into_view(self.grids_canvas, first))
        return appended, renames

    def tab_name(self):
        """The current tab's class name, or "All classes"."""
        tab = by_id(self._tab_var.get())
        return tab.name if tab else "All classes"

    def _join_current_tab(self, grid):
        """A new grid joins the tab it was made on."""
        set_class(grid, self._tab_var.get())
        return grid

    def _store(self):
        return self.app.profile_store if self.app is not None else None

    def _overlay(self):
        store = self._store()
        return store.get_section('overlay') if store is not None else {}

    def base_size(self):
        """The profile's overlay size (the grid cards' previews read it live)."""
        return self._overlay().get('size', DEFAULT_SIZE)

    def load_overlay(self):
        """Show the loaded profile's overlay size and font, and redraw every
        card's preview (profile load or import, first-launch seeding)."""
        overlay = self._overlay()
        self._overlay_size_var.set(self._size_labels.get(overlay.get('size', DEFAULT_SIZE), ''))
        self._overlay_font_var.set(font_label(overlay.get('font', DEFAULT_FONT)))
        for panel in self.grid_panels:
            panel.refresh_view()
        self._redraw_empty_cards()

    def _on_overlay_changed(self):
        size = self._size_by_label.get(self._overlay_size_var.get(), DEFAULT_SIZE)
        font = self._font_by_label.get(self._overlay_font_var.get(), DEFAULT_FONT)
        store = self._store()
        if store is not None:
            if store.get_section('overlay') == {'size': size, 'font': font}:
                return
            store.update_section('overlay', {'size': size, 'font': font})
        for panel in self.grid_panels:
            panel.refresh_view()
        self._redraw_empty_cards()
        # The deployed SWF was baked at the old size/font: un-tick Build.
        self._mark_modified()

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
        radios = self._build_radio_row(
            center, "Source:", self._empty_type_var,
            [("Player", "player"), ("Target", "target"),
             ("Friendly", "friendly"), ("Hostile", "hostile")],
            command=self._on_empty_type_changed, pady=(0, PAD_LF))
        # ttkbootstrap strips custom style= at construction; apply via configure() after.
        for rb, (style, tip) in zip(radios, (
            ('Player', "Track buffs/debuffs on yourself"),
            ('Target', "Track buffs/debuffs on your current target"),
            ('Friendly', "Overhead: over you, your group and friendly players"),
            ('Hostile', "Overhead: over your target and anyone fighting you"),
        )):
            rb.configure(style=f'{style}.TRadiobutton')
            add_tooltip(rb, tip)

        self._empty_mode_var = tk.StringVar(value="dynamic")
        self._radio_dynamic, self._radio_static = self._build_radio_row(
            center, "Mode:", self._empty_mode_var,
            [("Dynamic", "dynamic"), ("Static", "static")],
            command=self._redraw_empty_cards, pady=(0, PAD_TAB))

        self._cards_frame = ttk.Frame(center)
        self._cards_frame.pack(pady=(0, PAD_SECTION_GAP), fill='x')
        self._cards_frame.bind('<Configure>', self._reflow_preset_cards)
        self._empty_cards = []
        self._cards_overhead = None
        self._on_empty_type_changed()

        add_tooltip(self._radio_dynamic,
                    "Slots fill automatically as buffs activate. "
                    "You control fill direction, sort order, and grouping.")
        add_tooltip(self._radio_static,
                    "Each slot is pinned to specific buffs. "
                    "Shows the buff when active, stays empty when it's not.")

        return frame

    # (label, rows, cols, card w, card h, description) per kind: floating, overhead.
    _PRESETS = {
        False: (
            ("1\u00d710 Bar", 1, 10, PRESET_CARD_BAR_LONG, PRESET_CARD_BAR_SHORT,
             "Horizontal bar, great for tracking player buffs across the top"),
            ("10\u00d71 Bar", 10, 1, PRESET_CARD_BAR_SHORT, PRESET_CARD_SQUARE,
             "Vertical bar, stack buffs along the side of your screen"),
            ("3\u00d73 Grid", 3, 3, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Compact grid, fits many buffs in a small area"),
            ("1\u00d71 Slot \u00b7 static", 1, 1, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Single slot. Pin one specific buff. Mode is locked to Static."),
        ),
        True: (
            ("1\u00d73 Row", 1, 3, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Three icons over each head"),
            ("2\u00d75 Band", 2, 5, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Up to ten icons, five to a row"),
            ("3\u00d73 Grid", 3, 3, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "Up to nine icons, three to a row"),
            ("1\u00d71 Single", 1, 1, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
             "One icon over each head"),
        ),
    }

    def _on_empty_type_changed(self):
        """Floating and overhead grids have their own presets: rebuild the cards
        when the source moves between the two kinds, else just recolour them."""
        overhead = is_plate(self._empty_type_var.get())
        if overhead != self._cards_overhead:
            self._cards_overhead = overhead
            for card, *_ in self._empty_cards:
                card.destroy()
            self._empty_cards = []
            presets = (*self._PRESETS[overhead],
                       ("Custom", None, None, PRESET_CARD_SQUARE, PRESET_CARD_SQUARE,
                        "Open the Add Grid wizard to set custom rows, columns, and options"))
            for i, (label, rows, cols, w, h, desc) in enumerate(presets):
                card = self._build_preset_card(self._cards_frame, label, rows, cols, w, h, desc)
                card.grid(row=0, column=i, padx=PAD_LF, sticky='s')
            self._last_cards_width = None
            self._reflow_preset_cards()
        self._redraw_empty_cards()

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

    def _build_preset_card(self, parent, label, rows, cols, card_w, card_h, description):
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

        def _on_click(e, r=rows, c=cols):
            self._create_from_empty_state(r, c, self._empty_mode_var.get())

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

    def _reflow_preset_cards(self, event=None):
        """Wrap preset cards into multiple grid rows when the wrapper is too narrow
        (on resize, and when the cards are rebuilt for another kind of grid)."""
        avail = event.width if event is not None else self._cards_frame.winfo_width()
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
        """Redraw grid shape previews on empty state cards using current type
        color; an overhead dynamic preset draws as the band it makes. Drawn
        like a grid card's preview (`grid_preview.layout`, a new grid's icons),
        stepped down to fit the card."""
        gtype = self._empty_type_var.get()
        type_color = GRID_TYPE_COLORS[gtype]
        band = is_plate(gtype) and self._empty_mode_var.get() == 'dynamic'
        icon = grid_metrics(self.base_size(), SCALE_DEFAULT).icon
        for card, rows, cols, card_w, card_h in self._empty_cards:
            card.delete('cells')
            preview_h = card_h - PRESET_LABEL_AREA
            if rows is None:
                card.create_text(card_w // 2, preview_h // 2 + 10, text="+",
                                 anchor='center', fill=type_color,
                                 font=FONT_HEADING, tags='cells')
                continue
            lay = grid_preview.layout(
                rows, cols, icon=icon, gap=-1,
                band=(snap_row_cap(cols), rows * cols) if band else None,
                num=PREVIEW_RATIO[0], den=PREVIEW_RATIO[1], spacing=PREVIEW_SLOT_SPACING,
                max_w=card_w - 2 * PAD_LF, max_h=preview_h - PAD_LF)
            ox, oy = (card_w - lay.width) // 2, (preview_h - lay.height) // 2
            for x0, y0, x1, y1 in lay.rects:
                card.create_rectangle(ox + x0, oy + y0, ox + x1 - 1, oy + y1 - 1, fill=type_color,
                                      outline=TK_COLORS['separator'], tags='cells')

    def _dismiss_tip(self):
        """Dismiss the tip bar permanently for this session."""
        self._tip_dismissed = True
        self._tip_frame.pack_forget()

    def notify_build_done(self):
        """Called after a successful build — mark step 4 complete.
        A dismissed guide stays dismissed: the user closed it, and the build they
        went on to run is no reason to put it back in front of them."""
        self._build_done = True
        self._update_tip()
        # build_action recorded last_build just before this call.
        self.refresh_build_status()

    def notify_game_path_changed(self):
        """Called when the active game folder changes."""
        self._update_tip()

    def refresh_extras_shortcuts(self):
        """Resync the extras shortcut cards after an Extras dialog Apply (and,
        via apply_document, on every profile load, import or reset). The status row rides
        along — every path that changes a BUILD section goes through here or
        `_mark_modified`."""
        if self.extras_row is not None:
            self.extras_row.refresh()
        self.refresh_build_status()

    def refresh_build_status(self):
        """Sync the in-game status line: which profile the installed SWF was
        built from, and whether the live document (BUILD sections + target
        resolution) still matches it. No modal anywhere — staleness is a quiet
        row, not an interruption. Hidden until a build is recorded."""
        if self.build_status_lbl is None:
            return
        last = self.app.settings.get('last_build') or {}
        store = self.app.profile_store
        if not last or store is None:
            self.build_status_lbl.pack_forget()
            return
        name = last.get('profile_name') or 'another profile'
        if last.get('profile_id') != store.document['id']:
            text = f"In game: {name} — not the loaded profile"
            fg = THEME_COLORS['warning']
        elif (
            build_signature(self.app.registry, store.document) != last.get('hash')
            or list(get_game_resolution_or_default()) != last.get('target_resolution')
            or [self.app.settings.get('anchor_side'), self.app.settings.get('anchor_up')]
            != last.get('anchor', [ANCHOR_SIDE_DEFAULT, ANCHOR_UP_DEFAULT])
        ):
            text = f"In game: {name} — differs from the current setup"
            fg = THEME_COLORS['warning']
        else:
            text = f"In game: {name}"
            fg = THEME_COLORS['muted']
        self.build_status_lbl.configure(text=text, foreground=fg)
        # `after` is pack order; with side='bottom' that lands it directly
        # above the extras tiles, under the cards it describes.
        self.build_status_lbl.pack(side='bottom', fill='x', padx=PAD_TAB,
                                    pady=(PAD_XS, 0), after=self.extras_row)

    def _update_tip(self):
        """Update step guide state and show/hide the tip panel."""
        if self._tip_dismissed or not self._onboarding:
            self._tip_frame.pack_forget()
            return

        has_game_path = bool(get_setting('game_path'))
        has_grids = bool(self.grids)
        buffs_done = has_grids and all(grid_holds(g) for g in self.grids)
        self._update_step_guide([has_game_path, has_grids, buffs_done, self._build_done])

        ready = has_game_path and buffs_done
        border = THEME_COLORS['success'] if ready else TK_COLORS['border']
        self._tip_frame.configure(highlightbackground=border, highlightcolor=border)

        # Anchor `before` the always-packed extras row when there is one — a
        # stable target. The state-widget fallback (app=None) can be mid-swap
        # when _mark_modified() fires before refresh_panels() repacks the view
        # (e.g. deleting the last grid un-ticks Build while _normal_view is
        # still packed); anchoring `before` an unpacked widget raises TclError,
        # so skip the repack and let the follow-up _update_tip() place it once
        # the view has swapped.
        anchor = self.extras_row
        if anchor is None:
            anchor = self._normal_view if has_grids else self._empty_state
        self._tip_frame.pack_forget()
        if anchor.winfo_manager() == 'pack':
            self._tip_frame.pack(fill='x', padx=PAD_TAB, pady=(PAD_XS, PAD_XS),
                                 before=anchor)

    def _create_from_empty_state(self, rows, cols, mode):
        """Create a grid from the empty state preset shortcuts (the Custom
        card, with no shape, opens the wizard; a floating 1x1 is static
        whatever the mode picked, as `create_default_grid` makes it)."""
        if rows is None:
            self.add_grid()
            return
        grid_type = self._empty_type_var.get()
        existing = {g['id'] for g in self.grids}
        grid_config = create_default_grid(
            grid_type=grid_type, rows=rows, cols=cols, mode=mode,
            grid_id=default_grid_name(grid_type, existing),
            base_size=self.base_size(),
        )
        self.grids.append(self._join_current_tab(grid_config))
        self._mark_modified()
        self.refresh_panels()

    def get_profile_data(self):
        """The grid configs as they are: a card writes its one live control
        (Enabled) the moment it is toggled, so nothing needs flushing."""
        return self.grids

    def _migrate_whitelist(self, whitelist, missing):
        """Normalize whitelist entries to primary spell IDs.

        Accepts legacy int IDs and legacy name strings. Orphans are appended
        to `missing` (list of strings) but PRESERVED in the result — the
        profile autosaves, so a load-time drop would destroy the ref within
        seconds; unresolved entries are inert (the build skips them) and
        revive when the buff exists again.
        """
        result = []
        for item in whitelist:
            if isinstance(item, int):
                entry = self.database.by_id.get(item)
                if entry and entry.get('ids'):
                    result.append(entry['ids'][0])
                else:
                    missing.append(f"id:{item}")
                    result.append(item)
            elif isinstance(item, str):
                entry = self.database.get_entry_by_name(item)
                if entry and entry.get('ids'):
                    result.append(entry['ids'][0])
                else:
                    missing.append(item)
                    result.append(item)
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
        # A pending delete-undo toast belongs to the outgoing profile; bump the
        # generation so its click-through can't insert a stale grid into this one.
        self._profile_generation += 1
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
        for old, new in dedupe_grid_ids(validated):
            logger.warning("Duplicate grid name '%s' renamed to '%s'", old, new)
        self.grids = validated
        # Whatever was built, it wasn't this: a freshly loaded profile un-ticks
        # step 4 the same way an in-place edit does.
        self._build_done = False
        self.refresh_panels()
        return missing_by_grid

    def add_grid(self):
        """Open AddGridWizard dialog."""
        existing_ids = {g['id'] for g in self.grids}
        wizard = AddGridWizard(self.winfo_toplevel(), existing_ids,
                               name_in_use=self._grid_name_in_use, base_size=self.base_size())
        self.winfo_toplevel().wait_window(wizard)
        if wizard.result:
            self.grids.append(self._join_current_tab(wizard.result))
            self._mark_modified()
            self.refresh_panels()

    def delete_grid(self, panel):
        """Delete a single grid — undoable via toast instead of a confirm."""
        for i, p in enumerate(self.grid_panels):
            if p == panel:
                removed = self.grids.pop(i)
                self._mark_modified()
                self.refresh_panels()
                gen = self._profile_generation
                app_toast(self, f"Deleted grid '{removed['id']}' — click to undo",
                          'info', 8, key='grid-delete-undo',
                          on_click=lambda g=removed, idx=i, gn=gen: self._undo_delete_grid(g, idx, gn))
                break

    def _undo_delete_grid(self, grid, index, generation):
        """Reinsert a deleted grid at its old position (undo-toast click-through).

        A profile loaded since the delete invalidates the undo — reinserting would
        drop the old profile's grid into the new one. Re-check the insert
        invariant too: a grid added since the delete may have taken the name
        (names key the AS2 whitelist tables)."""
        if generation != self._profile_generation:
            app_toast(self, "Undo expired — a different profile was loaded", 'info', 4)
            return
        if any(g.get('id') == grid.get('id') for g in self.grids):
            app_toast(self, f"Can't undo — a grid named '{grid.get('id')}' exists now",
                      'warning', 4)
            return
        index = min(index, len(self.grids))
        self.grids.insert(index, grid)
        self._mark_modified()
        self.refresh_panels()

    def refresh_panels(self):
        """Rebuild GridEditorPanel widgets or show empty state.

        Destroys and recreates every card from self.grids: a card holds no
        state of its own (Enabled is written as it is toggled, everything
        else by Grid Settings' Apply), so nothing is lost."""
        self._drag_manager.clear()

        if not self.grids:
            self._update_tab_counts()
            self._normal_view.pack_forget()
            self._empty_state.pack(fill='both', expand=True)
            self._update_tip()
            return

        self._empty_state.pack_forget()
        self._normal_view.pack(fill='both', expand=True)

        for widget in self.grids_frame.winfo_children():
            if widget is not self._tab_empty_lbl:
                widget.destroy()
        self.grid_panels.clear()

        for grid_config in self.grids:
            panel = GridEditorPanel(
                self.grids_frame, self.database, grid_config,
                on_delete=self.delete_grid,
                get_base_size=self.base_size,
                on_whitelist_changed=self._on_card_buffs_changed,
                name_in_use=self._grid_name_in_use,
                on_edit=self._mark_modified,
                on_move=self.move_or_copy,
                find_card=self._card_for,
                on_export=self.export_grid,
            )
            self.grid_panels.append(panel)
        self._repack_panels()

        self._update_tip()

    def _attach_panel(self, panel, index):
        """Pack a grid panel at its index among the listed cards, with separator
        and drag handle binding."""
        if index > 0:
            tk.Frame(self.grids_frame, height=1, bg=TK_COLORS['border']).pack(
                fill='x', padx=PAD_LIST_ITEM, pady=PAD_ROW)
        panel.pack(fill='x', pady=(0, PAD_ROW), padx=PAD_SMALL)
        self._drag_manager.bind_handle(panel.drag_handle, index, panel_widget=panel)
        panel.drag_handle.bind('<Alt-Up>', lambda e, i=index: self._move_grid(i, -1))
        panel.drag_handle.bind('<Alt-Down>', lambda e, i=index: self._move_grid(i, 1))

    def _card_for(self, config):
        """The card showing `config` now, or None once that grid left the list
        (deleted, or another profile loaded)."""
        for grid, panel in zip(self.grids, self.grid_panels):
            if grid is config:
                return panel
        return None

    def _move_grid(self, index, delta):
        """Keyboard equivalent of dragging the ☰ handle. Clamps at both ends
        (no wrap) and moves focus with the grid, so Alt+↓ can be repeated to
        walk a card down the list."""
        new_index = index + delta
        visible = self._visible()
        if 0 <= new_index < len(visible):
            self._reorder_grid(index, new_index)
            moved = self.grid_panels[self._visible()[new_index]]
            moved.drag_handle.focus_set()
            scroll_widget_into_view(self.grids_canvas, moved)
        return 'break'

    def _reorder_grid(self, old_index, new_index):
        """Move the listed grid at old_index to new_index (indexes among the
        current tab's cards) and repack panels."""
        visible = self._visible()
        old_index, new_index = visible[old_index], visible[new_index]
        grid = self.grids.pop(old_index)
        self.grids.insert(new_index, grid)
        panel = self.grid_panels.pop(old_index)
        self.grid_panels.insert(new_index, panel)
        self._mark_modified()
        self._repack_panels()

    def _repack_panels(self):
        """Repack the current tab's cards in order without destroying any: a
        tab switch only changes which cards are packed."""
        self._drag_manager.clear()
        for widget in self.grids_frame.winfo_children():
            if isinstance(widget, tk.Frame) and not isinstance(widget, GridEditorPanel):
                widget.destroy()
            else:
                widget.pack_forget()  # type: ignore[attr-defined]
        visible = self._visible()
        for n, i in enumerate(visible):
            self._attach_panel(self.grid_panels[i], n)
        if self.grids and not visible:
            tab = by_id(self._tab_var.get())
            self._tab_empty_lbl.configure(
                text=f"No grids for {tab.name} yet. + Add Grid makes one for this class."
                if tab else "No grids for every class. + Add Grid makes one.")
            self._tab_empty_lbl.pack(pady=PAD_SECTION_GAP)
        self._update_tab_counts()

    def _grid_name_in_use(self, name, exclude_config):
        """True if a grid other than `exclude_config` already uses `name`.
        Names key the generated AS2 whitelist tables, so they must stay unique
        — Grid Settings asks it (through the card's `name_problem`) to block
        duplicates (the Add Grid wizard has its own check)."""
        return any(g is not exclude_config and g.get('id') == name for g in self.grids)

    def _on_card_buffs_changed(self):
        """A card's whitelist / slot-assignment dialog committed — refresh the
        step guide and mirror the change into the profile store."""
        self._update_tip()
        self._mark_modified()

    def _mark_modified(self):
        """Signal that grids have changed. Any in-memory edit after a build
        means the deployed SWF no longer matches, so the Build step un-ticks."""
        if self._build_done:
            self._build_done = False
            self._update_tip()
        if self.on_modified:
            self.on_modified()
        # on_modified pushed the edit into the profile store — the status row
        # re-hashes the document it just changed.
        self.refresh_build_status()
