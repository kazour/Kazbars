"""KazBars — Grid editor card (one row of the grids list).

`GridEditorPanel` is one card in the grids list. The container `GridsPanel`
(in `grids_panel.py`) creates/destroys these as the grid list changes.

A card is a row, never expanded: the title line (name, type, mode, Applied
by me; the settings cog, Move…, Enabled, ▲ ▼, ×), the grid drawn to scale
(`GridPreview`) and the names line under it. The preview is where buffs are
chosen: a dynamic grid's opens the Tracked Buffs picker, a static grid's cell
opens it on that slot (walking the grid's slots from there), and a
right-click (or Delete) clears a slot with an undo toast. The cog opens Grid
Settings (`grid_settings_dialog`), whose draft the preview follows live;
Apply lands it through `apply_settings` (the shape through `settle_box`, a
static grid's slot assignments trimmed or restored).
"""

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import grid_preview
from .classes import CLASSES
from .grid_dialogs import BuffSelectorDialog
from .grid_model import is_band, is_plate, ref_list, settle_box
from .grid_preview_canvas import GridPreview
from .grid_settings_dialog import open_grid_settings
from .overlay import DEFAULT_SIZE
from .overlay_size import SCALE_DEFAULT, grid_metrics
from .ui_helpers import (
    CARD_STRIPE_PX,
    FONT_BODY_LG,
    FONT_SECTION,
    FONT_SMALL,
    FONT_SYMBOL,
    GRID_TYPE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_MICRO,
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


# Applied by me's round toggle, and its dimmed twin for a disabled grid (the
# label greys with the title; the switch keeps working).
_TOGGLE_STYLE = 'success.Round.Toggle'
_DIM_TOGGLE_STYLE = 'Dim.' + _TOGGLE_STYLE


def _dim_toggle_style():
    ttk.Style().configure(_DIM_TOGGLE_STYLE, foreground=TK_COLORS['dim_text'])
    return _DIM_TOGGLE_STYLE


class _SlotWalker:
    """What the slot picker walks: a static grid's slots, read and written
    through its card (`BuffSelectorDialog`'s `walker`)."""

    def __init__(self, card, start):
        self.card = card
        self.start = start
        self.count = grid_preview.slot_total(card.grid_config)
        self.accent = card._accent_color
        self.committed = False

    def ids(self, slot):
        return grid_preview.slot_ids(self.card.grid_config, slot)

    def assigned(self, slot):
        return bool(self.ids(slot))

    def tip(self, slot, refs=None):
        """What `slot` holds: as stored, or `refs` (the picker's live selection)."""
        cfg = self.card.grid_config if refs is None else {'slotAssignments': {str(slot): refs}}
        return grid_preview.slot_tip(cfg, self.card._name_of, slot, actions=False)

    def commit(self, slot, refs):
        """Write `slot` back: the picker calls this only for a slot it edited."""
        self.card._write_slot(slot, refs)
        self.committed = True


def _names_measure(widget):
    """`measure(text)` in the names line's font: one Font per Tk root, shared
    by every card under it."""
    root = widget._root()
    font = getattr(root, '_kz_names_font', None)
    if font is None:
        font = root._kz_names_font = tkfont.Font(root=root, font=FONT_SMALL)
    return font.measure


class GridEditorPanel(ttk.Frame):
    """One grid's row: title line, to-scale preview, names line."""

    def __init__(self, parent, database, grid_config, on_delete=None,
                 get_base_size=None, on_whitelist_changed=None,
                 name_in_use=None, on_edit=None, on_move=None, on_step=None, find_card=None):
        super().__init__(parent)
        self.database = database
        self.grid_config = grid_config
        self.on_delete = on_delete
        # The profile's overlay size, read live: the preview and the Size hint
        # follow the Grids toolbar's Overlay dropdown.
        self._get_base_size = get_base_size or (lambda: DEFAULT_SIZE)
        self._on_whitelist_changed = on_whitelist_changed
        self._name_in_use = name_in_use
        self._on_edit = on_edit
        # on_move(card, class_id, copy): Move to… / Copy to… another class tab.
        self._on_move = on_move
        # on_step(card, delta): ▲ / ▼, one place up or down the listed cards.
        self._on_step = on_step
        # find_card(config): the card showing that config now, None once it left
        # the list — a rebuild within the undo toast's life replaces this card.
        self._find_card = find_card
        # Cleared slots still undoable: slot -> (refs, when cleared).
        self._cleared = {}
        self._names = []
        self._names_cut = (None, None)  # (names, width) the line was cut for
        self.settings_dialog = None

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

        self._row = ttk.Frame(card)
        self._row.pack(side='left', fill='x', expand=True,
                       padx=PAD_ROW, pady=(PAD_BUTTON_GAP, PAD_ROW))
        self._build_title_line()
        self._build_body()

        self.enabled_var.set(grid_config.get('enabled', True))
        self._apply_enabled_styling(self.enabled_var.get())
        self._refresh_view()

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

    # ------------------------------------------------------------------
    # Title line
    # ------------------------------------------------------------------
    def _build_title_line(self):
        """Name, type badge, mode and Applied by me on the left; on the right,
        left to right: the settings cog, Move…, Enabled, ▲ ▼ and ×."""
        header = ttk.Frame(self._row)
        header.pack(fill='x')
        self._title_label = ttk.Label(header, font=FONT_SECTION, foreground=THEME_COLORS['heading'])
        self._title_label.pack(side='left')
        self._badge_label = ttk.Label(header, text=self.grid_config.get('type', 'player'),
                                      font=FONT_SMALL, foreground=self._accent_color)
        self._badge_label.pack(side='left', padx=(PAD_LF, 0))
        self.summary_label = ttk.Label(header, font=FONT_SMALL, foreground=THEME_COLORS['muted'])
        self.summary_label.pack(side='left', padx=(PAD_TAB, 0))
        self.self_cast_var = tk.BooleanVar(value=self.grid_config.get('selfCastOnly') is True)
        self._self_cast_cb = ttk.Checkbutton(header, text="Applied by me",
                                             variable=self.self_cast_var,
                                             command=self._on_self_cast_toggled,
                                             bootstyle="success-round-toggle")  # type: ignore[call-arg]
        add_tooltip(self._self_cast_cb, "Show only effects you cast, with your own timer, even when "
                                        "other players cast the same effect on the same character.")

        self.enabled_var = tk.BooleanVar(value=True)
        delete_label = self._glyph_label(header, "×", FONT_SYMBOL, "Delete this grid",
                                         lambda: self.delete_grid(), THEME_COLORS['danger_text'],
                                         padding=(PAD_XS, PAD_MICRO))
        bind_label_press_effect(delete_label, THEME_COLORS['danger_text'])
        self._step_labels = {}
        for glyph, delta, tip in (("▼", 1, "Move this grid down the list"),
                                  ("▲", -1, "Move this grid up the list")):
            self._step_labels[delta] = self._make_step_label(header, glyph, delta, tip)
        enabled_cb = ttk.Checkbutton(header, text="Enabled",
                                     variable=self.enabled_var,
                                     command=self._on_enabled_toggled,
                                     bootstyle="success-round-toggle")  # type: ignore[call-arg]
        enabled_cb.pack(side='right', padx=(0, PAD_XS))
        in_view = [enabled_cb, self._step_labels[-1], self._step_labels[1], delete_label]
        if self._on_move is not None:
            move_label = self._glyph_label(header, "Move…", FONT_SMALL,
                                           "Move this grid to another class tab, or copy it there",
                                           None, THEME_COLORS['heading'])
            move_label.bind('<Button-1>', lambda e: self._show_move_menu(move_label))
            for seq in ('<Return>', '<space>'):
                move_label.bind(seq, lambda e: self._show_move_menu(move_label))
            in_view.insert(0, move_label)
        self.cog_label = self._glyph_label(header, "⚙", FONT_BODY_LG, "This grid's settings",
                                           self.open_settings, THEME_COLORS['heading'])
        in_view.insert(0, self.cog_label)
        # Packed after the right cluster, so a narrow header squeezes the
        # toggle before the cog or ×; side='left' still lands it after the mode.
        self._self_cast_cb.pack(side='left', padx=(PAD_LF, 0))
        # The right cluster is packed right to left; raise everything left to
        # right so Tab walks it as seen.
        for w in [self._self_cast_cb, *in_view]:
            w.lift()

    def _glyph_label(self, header, text, font, tip, command, hover_color, padding=(PAD_XS, PAD_MICRO)):
        """A clickable muted label on the title line (hand cursor, Tab stop,
        Enter/space like a click)."""
        lbl = ttk.Label(header, text=text, font=font, foreground=THEME_COLORS['muted'],
                        cursor='hand2', takefocus=True, padding=padding)
        lbl.pack(side='right', padx=(PAD_XS, 0))
        if command is not None:
            for seq in ('<Button-1>', '<Return>', '<space>'):
                lbl.bind(seq, lambda e: command())
        bind_label_hover_colors(lbl, THEME_COLORS['muted'], hover_color)
        add_tooltip(lbl, tip)
        return lbl

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

    def focus_step(self, delta):
        """Keyboard focus to ▲ (-1) or ▼ (1) after a move by it, so Enter
        repeats; the ☰ handle once the move reached the end and greyed it."""
        lbl = self._step_labels[delta]
        (lbl if lbl.live else self.drag_handle).focus_set()  # type: ignore[attr-defined]

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

    # ------------------------------------------------------------------
    # Preview and names line
    # ------------------------------------------------------------------
    def _build_body(self):
        """The to-scale preview and the names line under it."""
        body = ttk.Frame(self._row)
        body.pack(fill='x', padx=(PAD_XS, 0))
        self._body = body
        self.preview = GridPreview(body, accent=self._accent_color, on_pick=self._on_pick,
                                   on_clear=self.clear_slot, tip_for=self._preview_tip)
        self.preview.pack(anchor='w', pady=(PAD_XS, PAD_MICRO))
        self.names_var = tk.StringVar()
        self._names_label = ttk.Label(body, textvariable=self.names_var, font=FONT_SMALL,
                                      foreground=THEME_COLORS['muted'])
        self._names_label.pack(anchor='w', fill='x')
        add_tooltip(self._names_label, self._names_tip)
        body.bind('<Configure>', lambda e: self._draw_names(), add='+')

    def base_size(self):
        return self._get_base_size()

    def _icon(self, cfg):
        return grid_metrics(self._get_base_size(), cfg.get('scale', SCALE_DEFAULT)).icon

    def _refresh_view(self, cfg=None):
        """Redraw the preview, then the lines that read it (the summary says
        the ratio the preview settled on). `cfg` is a Grid Settings draft
        while one is open; the stored config otherwise."""
        cfg = self.grid_config if cfg is None else cfg
        self.preview.set_config(cfg, self._icon(cfg), bool(self.enabled_var.get()))
        self._refresh_labels(cfg)

    def _refresh_labels(self, cfg=None):
        """The title, summary and names line (a slot write repaints only its
        cell, then these)."""
        cfg = self.grid_config if cfg is None else cfg
        self._title_label.configure(text=cfg.get('id', 'Grid'))
        # The mode only: the preview shows the shape, the names line the buffs.
        shown_at = grid_preview.ratio_text(PREVIEW_RATIO[0], self.preview.ratio, PREVIEW_RATIO[1])
        self.summary_label.configure(text=cfg.get('slotMode', 'dynamic') + shown_at)
        self._names = [self._name_of(ref) for ref in grid_preview.held_ids(cfg)]
        self._draw_names()

    def refresh_size_hint(self):
        """The overlay size changed under this card: the preview draws the
        icons at their baked size, so it redraws."""
        self._refresh_view()

    def _draw_names(self):
        """The names line, cut to the card's width: the buffs the grid holds,
        or what to click while it holds nothing. Cut once per (names, width)."""
        nudge = grid_preview.empty_nudge(self.grid_config)
        if nudge is not None:
            self._names_cut = (None, None)
            self.names_var.set(nudge)
            return
        width = self._body.winfo_width()
        width = width if width > 1 else _NAMES_FALLBACK_W
        key = (tuple(self._names), width)
        if key == self._names_cut:
            return
        self._names_cut = key
        self.names_var.set(grid_preview.names_line(self._names, _names_measure(self), width))

    def _name_of(self, ref):
        """A buff ref as its database name, `(missing #id)` when gone."""
        if isinstance(ref, str):
            return ref
        return (self.database.by_id.get(ref) or {}).get('name', f"(missing #{ref})")

    def _format_buff_preview(self, ids, max_show=4):
        """Up to *max_show* names, then ` + N more`."""
        return grid_preview.join_names([self._name_of(bid) for bid in ids], max_show)

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

    # ------------------------------------------------------------------
    # Buffs: the picker from the preview, clearing a slot
    # ------------------------------------------------------------------
    def _on_pick(self, slot):
        if slot is None:
            self.edit_whitelist()
        else:
            self.edit_slot(slot)

    def _buffs_changed(self):
        self._refresh_labels()
        if self._on_whitelist_changed:
            self._on_whitelist_changed()

    def edit_whitelist(self):
        """The Tracked Buffs picker on the whitelist (a dynamic grid's preview)."""
        dialog = BuffSelectorDialog(
            self.winfo_toplevel(), self.database, "Edit Tracked Buffs",
            initial_ids=self.grid_config.get('whitelist', []),
            layout=self.grid_config.get('layout', 'mixed'),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.grid_config['whitelist'] = dialog.result
            self._refresh_view()  # every cell of a dynamic grid shows it holds something
            self._buffs_changed()

    def edit_slot(self, slot):
        """The same picker on one static slot (a click on its cell), walking
        the grid's slots from there: every slot it leaves, and the one Done
        closes on, is written back as it goes."""
        walker = _SlotWalker(self, slot)
        dialog = BuffSelectorDialog(
            self.winfo_toplevel(), self.database, f"Slot {slot} Buffs",
            layout=self.grid_config.get('layout', 'mixed'), walker=walker,
        )
        self.wait_window(dialog)
        if walker.committed:
            self._buffs_changed()

    def _write_slot(self, slot, refs):
        """Set (or, with no refs, drop) static slot `slot` and repaint its cell."""
        sa = dict(self.grid_config.get('slotAssignments') or {})
        sa.pop(slot, None)
        if refs:
            sa[str(slot)] = list(refs)
        else:
            sa.pop(str(slot), None)
        self.grid_config['slotAssignments'] = sa
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
        meanwhile keeps what it holds now, and one the grid shrank past stays
        cleared. Lands on whichever card shows this grid now (a rebuild since
        the clear replaced this one); a grid gone from the list is left be."""
        cleared, self._cleared = self._cleared, {}
        if self._find_card is not None:
            card = self._find_card(self.grid_config)
        else:
            card = self if self.winfo_exists() else None
        if card is None:
            return
        cfg = card.grid_config
        restored = False
        for slot, (refs, _when) in cleared.items():
            if slot < grid_preview.slot_total(cfg) and not grid_preview.slot_ids(cfg, slot):
                card._write_slot(slot, refs)
                restored = True
        if restored:
            card._buffs_changed()

    # ------------------------------------------------------------------
    # Grid Settings (the cog)
    # ------------------------------------------------------------------
    def open_settings(self):
        return open_grid_settings(self)

    def name_problem(self, name):
        """Why `name` can't be this grid's name, or None. Names key the
        generated AS2 whitelist tables: two grids sharing one would silently
        share a whitelist in game."""
        if not name:
            return "A grid needs a name"
        if self._name_in_use is not None and self._name_in_use(name, self.grid_config):
            return f"'{name}' is already another grid's name"
        return None

    def preview_draft(self, draft):
        """Draw a Grid Settings draft over the stored config."""
        self._refresh_view(dict(self.grid_config, **draft))

    def cancel_draft(self):
        """The dialog closed without Apply: back to the stored config."""
        self._refresh_view()

    def apply_settings(self, draft):
        """Land a Grid Settings draft (the settings it owns) on the config.
        The shape goes through `settle_box` again — the draft already did, so
        this guards only a caller that skipped it — and a static grid's change
        of slot count trims its assignments (restored on a regrow)."""
        cfg = self.grid_config
        old_total = grid_preview.slot_total(cfg)
        cfg.update(draft)
        if not self._band:
            rows, cols, fill = settle_box(cfg['rows'], cfg['cols'], cfg.get('fillDirection'),
                                          cfg.get('type', 'player'), cfg.get('slotMode') == 'dynamic')
            cfg.update(rows=rows, cols=cols, fillDirection=fill)
            if cfg.get('slotMode') == 'static':
                if rows * cols < old_total:
                    self._trim_slot_assignments(rows * cols)
                elif rows * cols > old_total:
                    self._restore_orphaned_assignments(rows * cols)
        self._refresh_view()
        self._notify_edit()

    def _trim_slot_assignments(self, new_total):
        """Drop assignments past new_total; stash dropped IDs on the grid for later restore."""
        sa = self.grid_config.get('slotAssignments') or {}
        dropped_ids = []
        for k, v in sa.items():
            if int(k) >= new_total:
                dropped_ids.extend(ref_list(v))
        self.grid_config['slotAssignments'] = {
            k: v for k, v in sa.items() if int(k) < new_total
        }
        if not dropped_ids:
            return
        existing = self.grid_config.get('_orphanedAssignments', [])
        self.grid_config['_orphanedAssignments'] = list(dict.fromkeys(existing + dropped_ids))
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
        sa = dict(self.grid_config.get('slotAssignments') or {})
        restored = []
        for k in range(new_total):
            if not orphans:
                break
            slot_key = str(k)
            if not ref_list(sa.get(slot_key)):
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

    # ------------------------------------------------------------------
    # Row state
    # ------------------------------------------------------------------
    def save_to_config(self):
        """Write the card's one live control (Enabled) into the config. Every
        other setting is written by Grid Settings' Apply."""
        self.grid_config['enabled'] = bool(self.enabled_var.get())

    def delete_grid(self):
        # No confirm — grids_panel shows an undo toast instead.
        if self.on_delete:
            self.on_delete(self)

    def _notify_edit(self):
        # Any settled edit → the container mirrors grids into the profile store.
        if self._on_edit:
            self._on_edit()

    def _on_self_cast_toggled(self):
        """Applied by me: written only when on, so a grid that never set it
        saves unchanged."""
        if self.self_cast_var.get():
            self.grid_config['selfCastOnly'] = True
        else:
            self.grid_config.pop('selfCastOnly', None)
        self._notify_edit()

    def _on_enabled_toggled(self):
        self.save_to_config()
        self._apply_enabled_styling(self.enabled_var.get())
        self._refresh_view()
        self._notify_edit()

    def _apply_enabled_styling(self, enabled):
        """Drain the grid's identity colors when it's excluded from the build.

        Title, badge and the left stripe drop to greys (the card outline is
        already neutral and stays put for hover); the preview drains with them
        (`_refresh_view`). The Enabled toggle is the affordance — this is the
        visual consequence.
        """
        self._stripe.configure(
            bg=self._accent_color if enabled else TK_COLORS['border'])
        self._title_label.configure(
            foreground=THEME_COLORS['heading'] if enabled else TK_COLORS['dim_text'])
        self._badge_label.configure(
            foreground=self._accent_color if enabled else TK_COLORS['dim_text'])
        self._self_cast_cb.configure(style=_TOGGLE_STYLE if enabled else _dim_toggle_style())
