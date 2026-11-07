"""
KazBars — a grid card's to-scale preview (Canvas).

`GridPreview` draws one grid from `grid_preview.layout()`: every slot at its
true place, filled in the type accent where the slot has content (a static
grid's assigned slot; every cell of a dynamic grid that tracks something),
the input surface where empty, drained to the border colour while the grid is
disabled. Each slot is three items tagged `slot_<i>` (`rect`, `num`,
`count`), created once per geometry and repainted in place: a hover, a key or
a slot write touches only the slots it changes.

Input: the pointer hovers a slot (light outline, hand cursor) and clicks it;
Tab reaches the canvas, arrows move the highlight, Enter/space activates and
Delete clears. The card owns what happens: `on_pick(slot)` (None on a dynamic
grid: the whole preview opens its picker), `on_clear(slot)` and `tip_for(slot)`
(the tooltip line, built when it shows).
"""

import tkinter as tk

from . import grid_preview
from .grid_model import is_band
from .ui_helpers import (
    FONT_SMALL,
    FONT_TINY,
    PREVIEW_MAX_H,
    PREVIEW_MAX_W,
    PREVIEW_NUMBER_MIN,
    PREVIEW_RATIO,
    PREVIEW_SLOT_SPACING,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip, refresh_tooltip

_NUM_INSET = 2
# The 1 px focus ring is drawn inside the canvas, over its outer pixels, and
# a margin keeps the cells off it so an outline is never cut at an edge:
# every item sits _INSET in, and a pointer reads that far back.
_RING = 1
_MARGIN = 2
_INSET = _RING + _MARGIN


class GridPreview(tk.Canvas):
    """The grid drawn to scale; see the module docstring."""

    def __init__(self, parent, *, accent, on_pick, on_clear, tip_for,
                 max_w=PREVIEW_MAX_W, max_h=PREVIEW_MAX_H):
        super().__init__(parent, width=1, height=1, bd=0, takefocus=True)
        # After the constructor: ttkbootstrap restyles every tk.Canvas as it
        # is built, the ring's thickness to 0 among it.
        self.configure(bg=TK_COLORS['bg'], highlightthickness=_RING,
                       highlightbackground=TK_COLORS['bg'], highlightcolor=accent)
        self._accent = accent
        self._on_pick = on_pick
        self._on_clear = on_clear
        self._tip_for = tip_for
        self._max = (max_w, max_h)
        self._cfg: dict = {}
        self._enabled = True
        self._layout: grid_preview.Layout | None = None
        self._hot = -1
        # The slot the keyboard sits on: kept while the picker has focus or
        # the pointer wanders off, so Tab back lands where it was.
        self._kept = 0
        self._hand = False

        self.bind('<Motion>', self._on_motion)
        self.bind('<Leave>', lambda e: self._set_hot(self._kept if self._focused() else -1))
        self.bind('<Button-1>', self._on_click)
        self.bind('<Button-3>', self._on_right_click)
        self.bind('<FocusIn>', lambda e: self._set_hot(self._kept))
        self.bind('<FocusOut>', lambda e: self._set_hot(-1))
        for key, dx, dy in (('Left', -1, 0), ('Right', 1, 0), ('Up', 0, -1), ('Down', 0, 1)):
            self.bind(f'<{key}>', lambda e, x=dx, y=dy: self._on_arrow(x, y))
        for key in ('<Return>', '<space>'):
            self.bind(key, lambda e: self._activate(self._hot))
        self.bind('<Delete>', lambda e: self._clear(self._hot))
        add_tooltip(self, lambda: self._tip_for(self._hot))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    @property
    def ratio(self):
        """The `den` of `PREVIEW_RATIO[0]:den` the preview is drawn at."""
        return self._layout.den if self._layout is not None else PREVIEW_RATIO[1]

    @property
    def layout(self):
        return self._layout

    def set_config(self, cfg, icon, enabled):
        """Draw `cfg` with `icon` px game icons. Items are rebuilt only when
        the geometry moved; otherwise every slot repaints in place."""
        self._cfg, self._enabled = cfg, enabled
        band = (cfg.get('rowCap', 5), cfg.get('maxSlots', 10)) if is_band(cfg) else None
        lay = grid_preview.layout(
            cfg.get('rows', 1), cfg.get('cols', 1), cfg.get('fillDirection', 'LR'),
            icon=icon, gap=cfg.get('gap', -1), band=band,
            num=PREVIEW_RATIO[0], den=PREVIEW_RATIO[1], spacing=PREVIEW_SLOT_SPACING,
            max_w=self._max[0], max_h=self._max[1])
        if self._layout is None or lay.rects != self._layout.rects:
            self._layout = lay
            self._hot = min(self._hot, len(lay.rects) - 1)
            self._kept = min(self._kept, len(lay.rects) - 1)
            self.redraw()
        else:
            self._layout = lay
            for i in range(len(lay.rects)):
                self.repaint_slot(i)

    def redraw(self):
        """Recreate every slot's items (a geometry change only)."""
        lay = self._layout
        if lay is None:
            return
        self.delete('all')
        # Tk adds the ring around this.
        self.configure(width=lay.width + 2 * _MARGIN, height=lay.height + 2 * _MARGIN)
        for i, (x0, y0, x1, y1) in enumerate(lay.rects):
            tag = f'slot_{i}'
            x0, y0, x1, y1 = x0 + _INSET, y0 + _INSET, x1 + _INSET, y1 + _INSET
            self.create_rectangle(x0, y0, x1 - 1, y1 - 1, width=1, tags=(tag, 'rect'))
            self.create_text(x0 + _NUM_INSET, y0 + _NUM_INSET - 1, anchor='nw',
                             font=FONT_SMALL, tags=(tag, 'num'))
            self.create_text(x1 - _NUM_INSET, y1 - _NUM_INSET, anchor='se',
                             font=FONT_TINY, tags=(tag, 'count'))
            self.repaint_slot(i)

    def _has_content(self, i):
        if self._cfg.get('slotMode') == 'static':
            return bool(grid_preview.slot_ids(self._cfg, i))
        return bool(grid_preview.held_ids(self._cfg))

    def repaint_slot(self, i):
        """Repaint slot `i`'s three items from the config as it is now."""
        lay = self._layout
        if lay is None or not 0 <= i < len(lay.rects):
            return
        tag = f'slot_{i}'
        full = self._has_content(i)
        fill = (self._accent if self._enabled else TK_COLORS['border']) if full else TK_COLORS['input_bg']
        # A dynamic grid opens one picker for all its cells, so it lights whole.
        hot = i == self._hot if self._static() else self._hot >= 0
        outline = THEME_COLORS['heading'] if hot else (fill if full else TK_COLORS['border'])
        self.itemconfigure(f'{tag}&&rect', fill=fill, outline=outline)
        labels = lay.cell >= PREVIEW_NUMBER_MIN
        ink = TK_COLORS['bg'] if full else TK_COLORS['dim_text']
        self.itemconfigure(f'{tag}&&num', text=str(i) if labels else '', fill=ink)
        count = ''
        if labels and full and self._cfg.get('slotMode') == 'static':
            count = str(len(grid_preview.slot_ids(self._cfg, i)))
        self.itemconfigure(f'{tag}&&count', text=count, fill=ink)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def _static(self):
        return self._cfg.get('slotMode') == 'static'

    def _slot_at(self, event):
        if self._layout is None:
            return -1
        return grid_preview.slot_at(self._layout, int(self.canvasx(event.x)) - _INSET,
                                    int(self.canvasy(event.y)) - _INSET)

    def _focused(self):
        try:
            return self.focus_get() is self
        except (KeyError, tk.TclError):  # focus in a window Tk can't name
            return False

    def _set_hot(self, i):
        if i >= 0:
            self._kept = i
        if i == self._hot:
            return
        if not self._static():
            # Every cell of a dynamic grid looks alike: one outline for all.
            self._hot = i
            full = bool(grid_preview.held_ids(self._cfg))
            rest = (self._accent if self._enabled else TK_COLORS['border']) if full else TK_COLORS['border']
            self.itemconfigure('rect', outline=THEME_COLORS['heading'] if i >= 0 else rest)
            return
        prev, self._hot = self._hot, i
        self.repaint_slot(prev)
        self.repaint_slot(i)

    def _on_motion(self, event):
        # Anywhere over a dynamic grid is the whole grid.
        i = self._slot_at(event) if self._static() else 0
        hand = i >= 0 or not self._static()
        if hand != self._hand:
            self._hand = hand
            self.configure(cursor='hand2' if hand else '')
        if i < 0 and self._focused():
            i = self._kept  # a gap under the pointer keeps the keyboard's slot
        if i != self._hot:
            self._set_hot(i)
            if self._static():  # a dynamic grid's tip is one line for the whole preview
                refresh_tooltip(self)

    def _on_click(self, event):
        self.focus_set()
        i = self._slot_at(event) if self._static() else 0
        self._set_hot(i)
        self._activate(i)

    def _on_right_click(self, event):
        i = self._slot_at(event)
        self._set_hot(i)
        self._clear(i)

    def _on_arrow(self, dx, dy):
        if self._layout is not None and self._static():
            self._set_hot(grid_preview.step(self._layout, self._hot, dx, dy))
        return 'break'

    def _activate(self, i):
        if not self._static():
            self._on_pick(None)
        elif i >= 0:
            self._on_pick(i)

    def _clear(self, i):
        if self._static() and i >= 0 and grid_preview.slot_ids(self._cfg, i):
            self._on_clear(i)
