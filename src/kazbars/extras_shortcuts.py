"""
KazBars — Extras shortcuts row.

Toggle cards along the bottom of the Grids tab, beside Build & Install —
one per SWF-build extra, in Extras-menu order (Cast timer, Console, Damage
numbers, Inspect panel, Onslaught tracker, Stopwatch) so the row and the menu
read as the same list. Each
card carries two controls, not one: the **card body** opens that feature's
Extras dialog (the same opener the menu item calls), and the **round switch**
flips whether it ships in the next Build & Install, writing the same
profile-document section that dialog writes (autosaved by the profile store;
`apply_document` resyncs the cards on every profile load, import or reset). The switch's hit
area is the switch — a click anywhere else on the card opens settings, so the
two never race. Configuration still lives in the dialogs, which push `refresh()`
back through `GridsPanel.refresh_extras_shortcuts()` on Apply.

Semantic color only: "in the next build" lights the card border, status line
and toggle in the success green the tip bar and Build & Install already use.
Identity comes from the label — the cards rest neutral when off.
"""

import tkinter as tk
from tkinter import ttk

from . import onslaught
from .console import ships as console_ships
from .ui_helpers import (
    FONT_SECTION,
    FONT_SMALL,
    PAD_LF,
    PAD_SMALL,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip, app_toast


# ============================================================================
# PER-FEATURE STORE ACCESS (the same writes the Extras dialogs make)
# ============================================================================
def _read_section(app, key):
    # The row is built with GridsPanel, before startup_profile installs the
    # store; apply_document resyncs the cards right after, so rest off here.
    store = app.profile_store
    return store is not None and bool(store.get_section(key).get('enabled'))


def _read_console(app):
    # The console ships only with a tab, so its card says so too.
    store = app.profile_store
    return store is not None and console_ships(store.get_section('console'))


def _read_onslaught(app):
    # The tracker ships only with a display on, so its card says so too.
    store = app.profile_store
    return store is not None and onslaught.ships(store.get_section('onslaught'))


def _make_section_setter(key, side_flags=()):
    def _set(app, on):
        patch = {'enabled': on}
        # The cast timer's per-side flags ride the master (is_enabled needs
        # master AND a side, and no UI has ever split them).
        for flag in side_flags:
            patch[flag] = on
        app.profile_store.update_section(key, patch)
    return _set


# Shared by every switch — they do the same thing on every card.
_TOGGLE_TOOLTIP = 'Whether this ships in your next Build & Install'

# The hover cue for whichever zone the pointer is over — same white as the
# round-1 drag handle's lit state, not a new token.
_HOVER_BORDER = '#ffffff'


def _is_descendant(widget, ancestor):
    w = widget
    while w is not None:
        if w is ancestor:
            return True
        w = getattr(w, 'master', None)
    return False


# (key, title, off-toast tail, tooltip, opener) + read/set — menu order.
# `opener` is the KazBarsApp method the matching Extras menu item calls.
_FEATURES = (
    ('cast_timer', 'Cast timer', 'next build removes it',
     'Cast-time readout for you and your target. Click to open Extras ▸ Cast timer…',
     '_open_cast_timer_settings',
     lambda app: _read_section(app, 'cast_timer'),
     _make_section_setter('cast_timer', side_flags=('enableP', 'enableT'))),
    ('console', 'Console', 'next build removes it',
     'Buff IDs and casts, logged in game. Click to open Extras ▸ Console…',
     '_open_console_settings',
     _read_console,
     _make_section_setter('console')),
    ('damage_numbers', 'Damage numbers', 'next build restores stock',
     "Re-tunes AoC's floating combat numbers. Click to open Extras ▸ Damage number mod…",
     '_open_damage_numbers',
     lambda app: _read_section(app, 'damage_numbers'),
     _make_section_setter('damage_numbers')),
    ('inspect', 'Inspect panel', 'next build removes it',
     'Combat sheet for your current target. Click to open Extras ▸ Inspect panel…',
     '_open_inspect_settings',
     lambda app: _read_section(app, 'inspect'),
     _make_section_setter('inspect')),
    ('onslaught', 'Onslaught tracker', 'next build removes it',
     'Bosses, waves and spawn alerts in Skull Gate and Kuthchemes. '
     'Click to open Extras ▸ Onslaught tracker…',
     '_open_onslaught_settings',
     _read_onslaught,
     _make_section_setter('onslaught')),
    ('stopwatch', 'Stopwatch', 'next build removes it',
     'In-game Start / Pause / Reset timer panel. Click to open Extras ▸ Stopwatch…',
     '_open_stopwatch_settings',
     lambda app: _read_section(app, 'stopwatch'),
     _make_section_setter('stopwatch')),
)


# ============================================================================
# ROW WIDGET
# ============================================================================
class ExtrasShortcutsRow(ttk.Frame):
    """One row of equal-width toggle cards for the SWF-build extras."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._tiles = {}
        for col, spec in enumerate(_FEATURES):
            self.columnconfigure(col, weight=1, uniform='extras')
            self._build_tile(col, spec)
        self.refresh()

    def _build_tile(self, col, spec):
        key, title, off_tail, tooltip, opener, read, write = spec
        card = tk.Frame(self,
                        highlightbackground=TK_COLORS['border'],
                        highlightcolor=TK_COLORS['border'],
                        highlightthickness=1)
        card.grid(row=0, column=col, sticky='nsew',
                  padx=(0 if col == 0 else PAD_LF, 0))

        body = ttk.Frame(card)
        body.pack(fill='x', padx=PAD_LF, pady=PAD_SMALL)

        # A cell of its own, not just the checkbutton, so the switch gets a
        # hover border to answer with — same highlightthickness trick as the
        # card, one size down, resting at the card's own background.
        switch_cell = tk.Frame(body, bg=TK_COLORS['bg'],
                               highlightbackground=TK_COLORS['bg'],
                               highlightcolor=TK_COLORS['bg'],
                               highlightthickness=1, cursor='hand2')
        switch_cell.pack(side='right', padx=(PAD_XS, 0))

        var = tk.BooleanVar(value=False)
        toggle = ttk.Checkbutton(
            switch_cell, variable=var,
            command=lambda k=key: self._on_toggle(k),
            bootstyle='success-round-toggle',  # type: ignore[call-arg]
            cursor='hand2',
        )
        toggle.pack()

        text = ttk.Frame(body)
        text.pack(side='left', fill='x', expand=True)
        title_lbl = ttk.Label(text, text=title, font=FONT_SECTION,
                              foreground=THEME_COLORS['body'])
        title_lbl.pack(anchor='w')
        status_lbl = ttk.Label(text, text='Off', font=FONT_SMALL,
                               foreground=TK_COLORS['dim_text'])
        status_lbl.pack(anchor='w')

        tile = {'key': key, 'title': title, 'off_tail': off_tail,
                'read': read, 'write': write, 'opener': opener, 'var': var,
                'card': card, 'switch_cell': switch_cell, 'status': status_lbl,
                'on': None, 'hover': None}
        self._tiles[key] = tile

        # The card body opens settings. Tk delivers <Button-1> to the widget
        # under the pointer and does not walk it up to the parent, so the
        # checkbutton's own press is the switch's whole hit area — the two
        # can't double-fire, and the switch needs no binding of its own.
        for widget in (card, body, text, title_lbl, status_lbl):
            widget.bind('<Button-1>', lambda e, k=key: self._open_settings(k))
            widget.configure(cursor='hand2')
            self._bind_zone(widget, key, card, 'body')
            add_tooltip(widget, tooltip)
        self._bind_zone(switch_cell, key, card, 'switch')
        add_tooltip(toggle, _TOGGLE_TOOLTIP)

    def _bind_zone(self, widget, key, card, zone):
        """Enter always claims the zone; Leave only releases it once the
        pointer is confirmed outside the card — moving straight from the
        body onto the switch cell (or back) must not flicker through None."""
        widget.bind('<Enter>', lambda e: self._set_hover(key, zone))
        widget.bind('<Leave>', lambda e: self._on_zone_leave(e, key, card))

    def _on_zone_leave(self, event, key, card):
        try:
            under = card.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, RuntimeError):
            under = None
        if under is not None and _is_descendant(under, card):
            return
        self._set_hover(key, None)

    def _set_hover(self, key, zone):
        tile = self._tiles[key]
        if tile['hover'] != zone:
            tile['hover'] = zone
            self._paint_tile(tile)

    # ------------------------------------------------------------------
    # Toggling & state
    # ------------------------------------------------------------------
    def _open_settings(self, key):
        """Card body click — open the feature's Extras dialog, exactly as its
        menu item does. The dialog owns Apply/Cancel; nothing is written here.
        Clears hover first: the dialog's grab_set() can steal every pointer
        event the app gets from here on, so the card may never see the
        <Leave> that would otherwise turn its border off, and it would stay
        lit long after the pointer — and the dialog — are gone."""
        self._set_hover(key, None)
        getattr(self.app, self._tiles[key]['opener'])()

    def _on_toggle(self, key):
        """Write the flipped state to the feature's own store, then resync."""
        tile = self._tiles[key]
        on = bool(tile['var'].get())
        tile['write'](self.app, on)
        empty = on and not tile['read'](self.app)
        if empty:
            # Switched on with nothing to build (a console with no tab): the
            # card stays off, so the store does too.
            tile['write'](self.app, False)
        self.refresh()
        # The row's parent is GridsPanel; a flipped gate changes what the next
        # build bakes, so its status row re-checks.
        self.master.refresh_build_status()
        if empty:
            app_toast(self, f"{tile['title']} has nothing to build — open its settings",
                      'warning', key=f'extras_{key}')
        elif on:
            msg = f"{tile['title']} on — Build & Install to apply"
            app_toast(self, msg, 'success', key=f'extras_{key}')
        else:
            msg = f"{tile['title']} off — {tile['off_tail']}"
            app_toast(self, msg, 'info', key=f'extras_{key}')

    def refresh(self):
        """Resync every card from its store; no-ops for unchanged tiles."""
        for tile in self._tiles.values():
            on = tile['read'](self.app)
            # The switch can be ahead of the state: switched on with nothing
            # to build (a console with no tab), it falls back to off.
            if on == tile['on'] and tile['var'].get() == on:
                continue
            tile['on'] = on
            tile['var'].set(on)
            tile['status'].configure(
                text='In next build' if on else 'Off',
                foreground=THEME_COLORS['success'] if on else TK_COLORS['dim_text'])
            self._paint_tile(tile)

    def _paint_tile(self, tile):
        """The one place that touches either border — hover and on/off state
        both flow through here, so a switch flip mid-hover (refresh() above)
        repaints from the pointer's actual position instead of resetting to
        resting underneath it."""
        state_color = THEME_COLORS['success'] if tile['on'] else TK_COLORS['border']
        card_color = _HOVER_BORDER if tile['hover'] == 'body' else state_color
        tile['card'].configure(highlightbackground=card_color, highlightcolor=card_color)
        switch_color = _HOVER_BORDER if tile['hover'] == 'switch' else TK_COLORS['bg']
        tile['switch_cell'].configure(highlightbackground=switch_color,
                                      highlightcolor=switch_color)
