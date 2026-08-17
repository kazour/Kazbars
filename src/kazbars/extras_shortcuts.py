"""
KazBars — Extras shortcuts row.

Four toggle cards pinned above the grid list — one per SWF-build extra, in
Extras-menu order (Damage numbers, Stopwatch, Inspect panel, Cast timer) so
the row and the menu read as the same list. Each card shows whether its
feature ships in the next Build & Install and flips the same profile-document
section its Extras dialog writes (autosaved by the profile store;
`apply_document` resyncs the cards on every profile switch). Configuration
stays in the dialogs, which push `refresh()` back through
`GridsPanel.refresh_extras_shortcuts()` on Apply.

Semantic color only: "in the next build" lights the card border, status line
and toggle in the success green the tip bar and Build & Install already use.
Identity comes from the label — the cards rest neutral when off.
"""

import tkinter as tk
from tkinter import ttk

from .ui_helpers import (
    FONT_SECTION,
    FONT_SMALL,
    PAD_LF,
    PAD_SMALL,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip, app_toast, bind_card_events


# ============================================================================
# PER-FEATURE STORE ACCESS (the same writes the Extras dialogs make)
# ============================================================================
def _read_section(app, key):
    # The row is built with GridsPanel, before startup_profile installs the
    # store; apply_document resyncs the cards right after, so rest off here.
    store = app.profile_store
    return store is not None and bool(store.get_section(key).get('enabled'))


def _make_section_setter(key, side_flags=()):
    def _set(app, on):
        patch = {'enabled': on}
        # The cast timer's per-side flags ride the master (is_enabled needs
        # master AND a side, and no UI has ever split them).
        for flag in side_flags:
            patch[flag] = on
        app.profile_store.update_section(key, patch)
    return _set


# (key, title, off-toast tail, tooltip) + read/set — menu order.
_FEATURES = (
    ('damage_numbers', 'Damage numbers', 'next build restores stock',
     "Re-tunes AoC's floating combat numbers. Configure in Extras ▸ Damage number mod…",
     lambda app: _read_section(app, 'damage_numbers'),
     _make_section_setter('damage_numbers')),
    ('stopwatch', 'Stopwatch', 'next build removes it',
     'In-game Start / Pause / Reset timer panel. Configure in Extras ▸ Stopwatch…',
     lambda app: _read_section(app, 'stopwatch'),
     _make_section_setter('stopwatch')),
    ('inspect', 'Inspect panel', 'next build removes it',
     'Combat sheet for your current target. Configure in Extras ▸ Inspect panel…',
     lambda app: _read_section(app, 'inspect'),
     _make_section_setter('inspect')),
    ('cast_timer', 'Cast timer', 'next build removes it',
     'Cast-time readout for you and your target. Configure in Extras ▸ Cast timer…',
     lambda app: _read_section(app, 'cast_timer'),
     _make_section_setter('cast_timer', side_flags=('enableP', 'enableT'))),
)


# ============================================================================
# ROW WIDGET
# ============================================================================
class ExtrasShortcutsRow(ttk.Frame):
    """One row of four equal-width toggle cards for the SWF-build extras."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._tiles = {}
        for col, spec in enumerate(_FEATURES):
            self.columnconfigure(col, weight=1, uniform='extras')
            self._build_tile(col, spec)
        self.refresh()

    def _build_tile(self, col, spec):
        key, title, off_tail, tooltip, read, write = spec
        card = tk.Frame(self,
                        highlightbackground=TK_COLORS['border'],
                        highlightcolor=TK_COLORS['border'],
                        highlightthickness=1)
        card.grid(row=0, column=col, sticky='nsew',
                  padx=(0 if col == 0 else PAD_LF, 0))

        body = ttk.Frame(card)
        body.pack(fill='x', padx=PAD_LF, pady=PAD_SMALL)

        var = tk.BooleanVar(value=False)
        toggle = ttk.Checkbutton(
            body, variable=var,
            command=lambda k=key: self._on_toggle(k),
            bootstyle='success-round-toggle',  # type: ignore[call-arg]
        )
        toggle.pack(side='right', padx=(PAD_XS, 0))

        text = ttk.Frame(body)
        text.pack(side='left', fill='x', expand=True)
        title_lbl = ttk.Label(text, text=title, font=FONT_SECTION,
                              foreground=THEME_COLORS['body'])
        title_lbl.pack(anchor='w')
        status_lbl = ttk.Label(text, text='Off', font=FONT_SMALL,
                               foreground=TK_COLORS['dim_text'])
        status_lbl.pack(anchor='w')

        tile = {'key': key, 'title': title, 'off_tail': off_tail,
                'read': read, 'write': write, 'var': var, 'card': card,
                'status': status_lbl, 'resting': TK_COLORS['border'], 'on': None}
        self._tiles[key] = tile

        # The whole card is one big toggle target; the checkbutton keeps its
        # own press so the two never double-fire.
        for widget in (card, body, text, title_lbl, status_lbl):
            widget.bind('<Button-1>', lambda e, k=key: self._on_card_click(k))
            widget.configure(cursor='hand2')
        bind_card_events(card, lambda t=tile: t['resting'])
        add_tooltip(card, tooltip)
        add_tooltip(toggle, tooltip)

    # ------------------------------------------------------------------
    # Toggling & state
    # ------------------------------------------------------------------
    def _on_card_click(self, key):
        tile = self._tiles[key]
        tile['var'].set(not tile['var'].get())
        self._on_toggle(key)

    def _on_toggle(self, key):
        """Write the flipped state to the feature's own store, then resync."""
        tile = self._tiles[key]
        on = bool(tile['var'].get())
        tile['write'](self.app, on)
        self.refresh()
        if on:
            msg = f"{tile['title']} on — Build & Install to apply"
            app_toast(self, msg, 'success', key=f'extras_{key}')
        else:
            msg = f"{tile['title']} off — {tile['off_tail']}"
            app_toast(self, msg, 'info', key=f'extras_{key}')

    def refresh(self):
        """Resync every card from its store; no-ops for unchanged tiles."""
        for tile in self._tiles.values():
            on = tile['read'](self.app)
            if on == tile['on']:
                continue
            tile['on'] = on
            tile['var'].set(on)
            border = THEME_COLORS['success'] if on else TK_COLORS['border']
            tile['resting'] = border
            tile['card'].configure(highlightbackground=border, highlightcolor=border)
            tile['status'].configure(
                text='In next build' if on else 'Off',
                foreground=THEME_COLORS['success'] if on else TK_COLORS['dim_text'])
