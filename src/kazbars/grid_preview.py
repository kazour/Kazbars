"""
KazBars — grid preview geometry and text (pure).

What a grid card draws and says, with no Tk in sight: where each slot sits
under the grid's fill direction (the AS2 runtime's `place()`, a band's
`band()`), the to-scale ratio a preview draws at, the hit test behind a click,
and the card's lines of text (the summary, a slot's tip, the names line, the
nudge on a grid that holds nothing). The card's canvas (`grid_preview_canvas`)
and the empty-state preset cards both draw from `layout()`.

Scale: `num` app px per `den` game px of the baked icon; each gap is the grid's
gap plus `spacing` game px at the same ratio, so overlapping icons still read
apart. Every cell and gap is a whole pixel, a gap never under one. A grid too
big for its room steps to the next whole `num:den` that fits.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import gcd
from typing import Any

from .grid_model import is_band, ref_list
from .grids_generator import grid_ships

Rect = tuple[int, int, int, int]

# The steepest step-down tried before a preview gives up fitting (2:64).
_DEN_LIMIT = 64


# ============================================================================
# PLACEMENT
# ============================================================================
def slot_pos(rows: int, cols: int, fill: str, idx: int) -> tuple[int, int]:
    """(row, col) on screen of a box grid's slot `idx`, as the AS2 `place()`."""
    if rows == 1:
        return 0, (cols - 1 - idx) if fill == 'RL' else idx
    if cols == 1:
        return (rows - 1 - idx) if fill == 'BT' else idx, 0
    r, c = divmod(idx, cols)
    if fill in ('TR-BL', 'BR-TL'):
        c = cols - 1 - c
    if fill in ('BL-TR', 'BR-TL'):
        r = rows - 1 - r
    return r, c


def band_positions(row_cap: int, max_slots: int) -> list[tuple[int, int]]:
    """Each band slot as (row from the top, offset from the centre line in half
    strides), as the AS2 `band()` grows it: `row_cap` to a row, rows from the
    bottom, each row centred (0 is dead centre; -1 and 1 a pair astride it)."""
    cap, n = max(1, row_cap), max(1, max_slots)
    rows = -(-n // cap)
    out = []
    for i in range(n):
        r, k = divmod(i, cap)
        width = min(cap, n - r * cap)
        out.append((rows - 1 - r, 2 * k - (width - 1)))
    return out


# ============================================================================
# SCALE
# ============================================================================
def _half_up(n: int, d: int) -> int:
    """n / d to the nearest whole, a half going up (n may be negative)."""
    return (2 * n + d) // (2 * d)


def cell_px(icon: int, gap: int, num: int, den: int, spacing: int) -> tuple[int, int]:
    """(cell, gap) in whole app px for a game `icon` and `gap` at `num:den`."""
    return max(1, _half_up(icon * num, den)), max(1, _half_up((gap + spacing) * num, den))


def ratio_text(num: int, den: int, base_den: int) -> str:
    """` · shown at 1:2` (reduced) once a preview stepped down; else empty."""
    if den == base_den:
        return ''
    g = gcd(num, den)
    return f" · shown at {num // g}:{den // g}"


@dataclass(frozen=True)
class Layout:
    """A preview at one ratio: every slot's rect (x0, y0, x1, y1) in slot order."""
    rects: tuple[Rect, ...]
    width: int
    height: int
    cell: int
    gap: int
    den: int


def _place(rows: int, cols: int, fill: str, band: tuple[int, int] | None,
           cell: int, gap: int, den: int) -> Layout:
    stride = cell + gap
    if band is not None:
        cap, n = max(1, band[0]), max(1, band[1])
        widest, band_rows = min(cap, n), -(-n // cap)
        width = widest * stride - gap
        rects = []
        for row, half in band_positions(cap, n):
            x = (width - cell + half * stride) // 2
            y = row * stride
            rects.append((x, y, x + cell, y + cell))
        return Layout(tuple(rects), width, band_rows * stride - gap, cell, gap, den)
    rects = []
    for i in range(rows * cols):
        r, c = slot_pos(rows, cols, fill, i)
        rects.append((c * stride, r * stride, c * stride + cell, r * stride + cell))
    return Layout(tuple(rects), cols * stride - gap, rows * stride - gap, cell, gap, den)


def layout(rows: int, cols: int, fill: str = 'LR', *, icon: int, gap: int,
           band: tuple[int, int] | None = None, num: int, den: int, spacing: int,
           max_w: int, max_h: int) -> Layout:
    """The preview of a `rows` x `cols` grid (or a band of (row cap, max slots))
    at `num:den`, stepping to the next whole `num:N` until it fits `max_w` x
    `max_h`."""
    for n in range(den, _DEN_LIMIT + 1):
        out = _place(rows, cols, fill, band, *cell_px(icon, gap, num, n, spacing), n)
        if out.width <= max_w and out.height <= max_h:
            return out
    return out


def slot_at(lay: Layout, x: int, y: int) -> int:
    """The slot under (x, y), or -1 over a gap or off the grid. Where two
    cells overlap the later one is drawn on top, so it wins."""
    for i in range(len(lay.rects) - 1, -1, -1):
        x0, y0, x1, y1 = lay.rects[i]
        if x0 <= x < x1 and y0 <= y < y1:
            return i
    return -1


def step(lay: Layout, idx: int, dx: int, dy: int) -> int:
    """The slot an arrow key moves to from `idx` on screen (dx, dy each -1, 0
    or 1): the nearest one that way, the same row or column first; `idx`
    itself at an edge."""
    if not lay.rects:
        return -1
    if not 0 <= idx < len(lay.rects):
        return 0
    x0, y0, _, _ = lay.rects[idx]
    best, best_key = idx, None
    for i, (cx, cy, _, _) in enumerate(lay.rects):
        along = (cx - x0) * dx + (cy - y0) * dy
        if along <= 0:
            continue
        across = abs((cx - x0) * dy) + abs((cy - y0) * dx)
        key = (across > lay.cell // 2, along, across)
        if best_key is None or key < best_key:
            best, best_key = i, key
    return best


# ============================================================================
# CONTENT
# ============================================================================
def slot_ids(cfg: dict, idx: int) -> list:
    """The buff refs static slot `idx` holds (a bare scalar reads as one)."""
    sa = cfg.get('slotAssignments') or {}
    return ref_list(sa.get(str(idx), sa.get(idx)))


def slot_total(cfg: dict) -> int:
    return cfg.get('rows', 1) * cfg.get('cols', 1)


def assigned_slots(cfg: dict) -> int:
    """How many slots inside the shape hold a buff — `grid_ships`'s count."""
    return sum(1 for i in range(slot_total(cfg)) if slot_ids(cfg, i))


def held_ids(cfg: dict) -> list:
    """The refs the grid holds in its order: the whitelist, or the slots in
    slot order (a ref in two slots once)."""
    if cfg.get('slotMode') == 'static':
        out: list = []
        for i in range(slot_total(cfg)):
            out.extend(slot_ids(cfg, i))
        return list(dict.fromkeys(out))
    return ref_list(cfg.get('whitelist'))


def _named(refs: Sequence, name_of: Callable[[Any], str]) -> str:
    """`Lash, Bloodlust x2`: names in first-seen order, repeats counted."""
    counts: dict[str, int] = {}
    for ref in refs:
        name = name_of(ref)
        counts[name] = counts.get(name, 0) + 1
    return ', '.join(f"{n} x{c}" if c > 1 else n for n, c in counts.items())


def slot_tip(cfg: dict, name_of: Callable[[Any], str], idx: int) -> str:
    """A static cell's tooltip: what the slot holds and what a click does."""
    refs = slot_ids(cfg, idx)
    if not refs:
        return f"Slot {idx}: empty — click to fill"
    return f"Slot {idx}: {_named(refs, name_of)} — click to edit, right-click to clear"


def empty_nudge(cfg: dict) -> str | None:
    """What a grid holding nothing says instead of its names. The build's own
    rule decides (`grid_ships`, enabled or not): such a grid is left out."""
    if grid_ships(dict(cfg, enabled=True)):
        return None
    if cfg.get('slotMode') == 'static':
        return ("No slots assigned yet, so it is not built. Click a slot to choose "
                f"its buffs ({slot_total(cfg)} slots).")
    return "No buffs tracked yet, so it is not built. Click the preview to choose them."


def join_names(names: Sequence[str], k: int) -> str:
    """The first `k` names, comma-joined, then ` + N more` for the rest."""
    more = f" + {len(names) - k} more" if k < len(names) else ''
    return ', '.join(names[:k]) + more


def names_line(names: Sequence[str], measure: Callable[[str], int], width: int) -> str:
    """As many names as fit `width` (per `measure`), then ` + N more`. The
    first name alone is cut with an ellipsis when even it is too wide."""
    if not names:
        return ''
    if measure(join_names(names, len(names))) <= width:
        return join_names(names, len(names))
    # Short of the whole list every text carries its ` + N more`, so the
    # widths grow with k: bisect for the most that fit.
    lo, hi = 0, len(names) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(join_names(names, mid)) <= width:
            lo = mid
        else:
            hi = mid - 1
    if lo:
        return join_names(names, lo)
    more = f" + {len(names) - 1} more" if len(names) > 1 else ''
    head = names[0]
    while head and measure(head + '…' + more) > width:
        head = head[:-1]
    return head + '…' + more


def summary(cfg: dict, *, shown_at: str, icon: int | None = None) -> str:
    """The title line's muted summary: shape, mode, what it holds, then the
    icon size (`icon`, given when off the default), the preview ratio and
    Applied by me when they apply."""
    mode = cfg.get('slotMode', 'dynamic')
    tracked = len(ref_list(cfg.get('whitelist')))
    if mode == 'static':
        parts = [f"{cfg.get('rows', 1)}×{cfg.get('cols', 1)}", 'static',
                 f"{assigned_slots(cfg)} of {slot_total(cfg)} assigned"]
    else:
        if is_band(cfg):
            parts = [f"up to {cfg.get('maxSlots', 10)}", f"{cfg.get('rowCap', 5)} wide", 'dynamic']
        else:
            parts = [f"{cfg.get('rows', 1)}×{cfg.get('cols', 1)}", 'dynamic']
        if tracked:
            parts.append(f"tracking {tracked} buff{'s' if tracked != 1 else ''}")
    if icon is not None:
        parts.append(f"{icon} px icons")
    applied = ' · applied by me' if cfg.get('selfCastOnly') is True else ''
    return ' · '.join(parts) + shown_at + applied
