"""
KazBars — Grid Editor Panel
Grid configuration UI: add/edit/delete grids, whitelist editing, slot assignment.
"""

import hashlib
import json
import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

from ttkbootstrap.dialogs import Messagebox

from .cast_timer_strip import CastTimerStrip
from .grid_dialogs import AddGridWizard
from .grid_editor_panel import (
    GridEditorPanel,
)
from .grid_model import (
    MAX_TOTAL_SLOTS,
    create_default_grid,
    dedupe_grid_ids,
    default_grid_name,
    parse_resolution,
    scale_grid_position,
    validate_grid,
)
from .settings_manager import get_setting, set_setting
from .ui_components import DragReorderManager, create_scrollable_frame
from .ui_forms import draw_grid_cells
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
    STEP_BADGE_PX,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import (
    add_tooltip,
    app_toast,
    bind_label_hover_colors,
    bind_label_press_effect,
    confirm,
)


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
        self._profile_generation = 0

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

        # Frozen cast-timer strip — pinned above the grid list, collapsed + off by default.
        self.cast_strip = CastTimerStrip(self._normal_view, on_modified=self._mark_modified)
        self.cast_strip.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_SMALL))

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
        # state_widget can be mid-swap when _mark_modified() fires before
        # refresh_panels() repacks the view (e.g. deleting the last grid
        # un-ticks Build while _normal_view is still packed). Anchoring
        # `before` an unpacked widget raises TclError, so skip the repack and
        # let the follow-up _update_tip() place it once the view has swapped.
        if state_widget.winfo_manager() == 'pack':
            self._tip_frame.pack(fill='x', padx=PAD_TAB, pady=(PAD_XS, PAD_XS),
                                 before=state_widget)

    def _create_from_empty_state(self, rows, cols, mode):
        """Create a grid from the empty state preset shortcuts."""
        if rows is None:
            self.add_grid()
            return
        grid_type = self._empty_type_var.get()
        existing = {g['id'] for g in self.grids}
        grid_config = create_default_grid(
            grid_type=grid_type, rows=rows, cols=cols, mode=mode,
            grid_id=default_grid_name(grid_type, existing)
        )
        self.grids.append(grid_config)
        self._mark_modified()
        self.refresh_panels(expand_index=len(self.grids) - 1)

    def get_profile_data(self):
        """Return current grid configurations (save all panel values first)."""
        self.save_settings()
        return self.grids

    def get_cast_timer_config(self):
        """Return the current cast-timer overlay config (validated dict)."""
        return self.cast_strip.get_config()

    def load_cast_timer_config(self, config):
        """Load a cast-timer overlay config into the strip (defaults if empty)."""
        self.cast_strip.load_config(config or {})

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
        n = len(self.grids)
        if not confirm(f"Remove all {n} grids?\n\nThis can't be undone.",
                       title="Clear All Grids",
                       action=f"Remove {n} grid{'s' if n != 1 else ''}", danger=True):
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
        """Scale grid x/y from reference_resolution to the given game resolution
        using anchor-based positioning (X center-anchored, Y bottom-anchored)
        to match AoC's fixed-pixel HUD behavior. Returns True if applied."""
        game_res = parse_resolution(resolution_str)
        if not game_res or not reference_resolution or len(reference_resolution) != 2:
            return False
        ref_w, ref_h = reference_resolution
        game_w, game_h = game_res
        if (ref_w, ref_h) == (game_w, game_h):
            return False
        # Flush before scaling: we mutate x/y on the configs below and then
        # rebuild, so unsaved card edits must be persisted first — and we scale
        # the just-flushed x/y, not a stale last-saved value.
        self.save_settings()
        for grid in self.grids:
            grid['x'], grid['y'] = scale_grid_position(
                grid['x'], grid['y'], ref_w, ref_h, game_w, game_h)
        self.refresh_panels()
        return True

    def add_grid(self):
        """Open AddGridWizard dialog."""
        existing_ids = {g['id'] for g in self.grids}
        current_slots = self.get_total_slots()
        if current_slots >= MAX_TOTAL_SLOTS:
            Messagebox.show_warning(f"Maximum {MAX_TOTAL_SLOTS} total slots reached.\n\nRemove a grid or reduce grid sizes to free up slots.", title="Slot Limit")
            return
        wizard = AddGridWizard(self.winfo_toplevel(), existing_ids, current_slots,
                               name_in_use=self._grid_name_in_use)
        self.winfo_toplevel().wait_window(wizard)
        if wizard.result:
            # refresh_panels() rebuilds every card from self.grids, so flush the
            # live widget state of existing cards first — otherwise their unsaved
            # edits (Enabled, icon size, position, …) revert to the last save.
            self.save_settings()
            self.grids.append(wizard.result)
            self._mark_modified()
            self.refresh_panels(expand_index=len(self.grids) - 1)

    def delete_grid(self, panel):
        """Delete a single grid — undoable via toast instead of a confirm."""
        for i, p in enumerate(self.grid_panels):
            if p == panel:
                self.save_settings()  # flush sibling cards before refresh_panels rebuilds them
                removed = self.grids.pop(i)
                self._mark_modified()
                self.refresh_panels(expand_index=-1)
                gen = self._profile_generation
                app_toast(self, f"Deleted grid '{removed['id']}' — click to undo",
                          'info', 8, key='grid-delete-undo',
                          on_click=lambda g=removed, idx=i, gn=gen: self._undo_delete_grid(g, idx, gn))
                break

    def _undo_delete_grid(self, grid, index, generation):
        """Reinsert a deleted grid at its old position (undo-toast click-through).

        A profile loaded since the delete invalidates the undo — reinserting would
        drop the old profile's grid into the new one. Re-check the insert
        invariants too: grids added since the delete may have taken the name
        (names key the AS2 whitelist tables) or the slot budget."""
        if generation != self._profile_generation:
            app_toast(self, "Undo expired — a different profile was loaded", 'info', 4)
            return
        if any(g.get('id') == grid.get('id') for g in self.grids):
            app_toast(self, f"Can't undo — a grid named '{grid.get('id')}' exists now",
                      'warning', 4)
            return
        if self.get_total_slots() + grid['rows'] * grid['cols'] > MAX_TOTAL_SLOTS:
            app_toast(self, "Can't undo — not enough free slots", 'warning', 4)
            return
        index = min(index, len(self.grids))
        self.save_settings()  # flush live cards before the rebuild
        self.grids.insert(index, grid)
        self._mark_modified()
        self.refresh_panels(expand_index=index)

    def refresh_panels(self, expand_index=-1):
        """Rebuild GridEditorPanel widgets or show empty state.

        Destroys and recreates every card from self.grids, so the live widget
        state of existing cards is discarded. Callers that mutate self.grids
        while cards are open must save_settings() first or in-progress edits
        revert to the last save (load/clear deliberately skip the flush).

        Cards collapse by default; only an explicit expand_index (a just-created
        or restored grid) opens one. Startup and profile loads pass no index, so
        every card starts collapsed."""
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
                name_in_use=self._grid_name_in_use,
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

    def _grid_name_in_use(self, name, exclude_config):
        """True if a grid other than `exclude_config` already uses `name`.
        Names key the generated AS2 whitelist tables, so they must stay unique
        — the card's rename validator calls this to block duplicates (the Add
        Grid wizard has its own check)."""
        return any(g is not exclude_config and g.get('id') == name for g in self.grids)

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
