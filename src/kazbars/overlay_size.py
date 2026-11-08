"""KazBars — the size model of KazBars.swf (pure arithmetic, no Tk).

The profile has ONE base size `B` (`overlay.size`, the Grids toolbar's Overlay
dropdown, 8..17: a 32..68 px icon) and every size in game derives from it, so
one value moves everything in proportion. A module that should differ has its
own `scale` `p` (a whole percent, 40-300, default 100). Its Size slider shows
the absolute size `p` gives at the current base (pt for a panel, icon px for
a grid) and stores the percent that gives the size picked (`panel_scale`,
`grid_scale`), so a new base moves the slider with the item.

- A buff grid: `grid_metrics`, scaled size `s = round(B x p / 100)` held to
  8..23, icon `4 s` px (32..92), timer and stack pt straight from the size
  table. A new grid's gap and timer Y offset come from the base size
  (`default_gap`, `default_timer_y`); stored per grid after that, they are
  the user's.
- Panels (inspect, stopwatch, onslaught, console) and the cast timer:
  `panel_fs`, the table's timer pt for `B` times `p`, held to 8..28; the AS2 role
  scale (small, title, alert) hangs off it in `KazBarsPanel`. The preview
  control panel and the layout-preview labels take it at 100 %.

The generator bakes these results and the dialogs read them back for their
hints, so the two cannot drift. Every rounding is half-up in integer
arithmetic (AS2's `Math.round`), so a tie such as `10 pt x 125 % = 12.5` is
13 on both sides.
"""

from dataclasses import dataclass
from typing import Any

SCALE_MIN = 40
SCALE_MAX = 300
SCALE_DEFAULT = 100

# A panel's body text, pt: what its Size slider offers and what it bakes.
PANEL_MIN_PT = 8
PANEL_MAX_PT = 28
# A grid's icon is this many px per point of s.
ICON_PX_PER_PT = 4
# Flash's text gutter, both sides of a field together, in px.
GUTTER = 4
# Four Arial Bold digits, in ten-thousandths of an em (a digit is 0.5566 em):
# the widest timer is a one-hour buff, "3600". The stack field fits as many
# ("x" and three digits).
TIMER_DIGITS_EM_E4 = 22_264
# The maintainer's table, set in game, per scaled size s = 8..23 (32..92 px
# icons; a grid's s is held to it): timer and stack pt, a new grid's gap and
# its timer Y offset (px).
SIZE_MIN = 8
SIZE_MAX = 23
ICON_MIN_PX = ICON_PX_PER_PT * SIZE_MIN
ICON_MAX_PX = ICON_PX_PER_PT * SIZE_MAX
TIMER_PT = (10, 10, 12, 12, 14, 14, 16, 16, 18, 18, 20, 20, 22, 22, 24, 24)
STACK_PT = (10, 10, 10, 12, 12, 12, 14, 14, 16, 16, 18, 18, 20, 20, 22, 22)
GAP_BY_SIZE = (0, 0, -1, -1, -1, -1, -2, -2, -2, -2, -3, -3, -3, -3, -4, -4)
TIMER_Y_BY_SIZE = (-2, -2, -2, -3, -4, -4, -5, -5, -5, -5, -5, -6, -6, -6, -7, -7)


def clamp_scale(p: int) -> int:
    return max(SCALE_MIN, min(p, SCALE_MAX))


def scale_from(value: Any) -> int:
    """A module's stored `scale`: `int()`-coerced (unparsable or absent → 100),
    then clamped. The `validate` of every module's `scale` field."""
    try:
        p = int(value)
    except (TypeError, ValueError, OverflowError):
        p = SCALE_DEFAULT
    return clamp_scale(p)


def _round_div(n: int, d: int) -> int:
    """`n / d` rounded half up, for `n >= 0` (AS2's `Math.round`)."""
    return (2 * n + d) // (2 * d)


def _row(table: tuple[int, ...], s: int) -> int:
    """`table`'s value for `s`, held to the table's ends."""
    return table[max(SIZE_MIN, min(s, SIZE_MAX)) - SIZE_MIN]


def default_gap(s: int) -> int:
    """A new grid's gap at size `s`."""
    return _row(GAP_BY_SIZE, s)


def default_timer_y(s: int) -> int:
    """A new grid's timer Y offset at size `s`."""
    return _row(TIMER_Y_BY_SIZE, s)


def inset(icon: int) -> int:
    """The stack counter's inset from the icon's top and right edges, px:
    `max(2, round(icon / 12))`, 4 at 48 px (`KazBarsGridView.createTexts`)."""
    return max(2, _round_div(icon, 12))


def panel_fs(base: int, scale: int) -> int:
    """A panel's body size, `FS` in `KazBarsPanel`: the base size's timer pt
    times the scale, held to 8..28."""
    pt = _round_div(_row(TIMER_PT, base) * clamp_scale(scale), 100)
    return max(PANEL_MIN_PT, min(pt, PANEL_MAX_PT))


def panel_scale(base: int, pt: int) -> int:
    """The scale that gives a panel `pt` at `base`: `panel_fs`'s inverse."""
    return clamp_scale(_round_div(pt * 100, _row(TIMER_PT, base)))


def grid_scale(base: int, icon: int) -> int:
    """The scale that gives a grid `icon` px at `base`: `grid_metrics`'s
    inverse (`s = icon / 4`)."""
    return clamp_scale(_round_div(icon * 100, ICON_PX_PER_PT * base))


@dataclass(frozen=True)
class GridMetrics:
    """A grid slot on screen: icon px, timer and stack pt (the slot clip scales
    the art, not the text)."""
    icon: int
    timer: int
    stack: int


def grid_metrics(base: int, scale: int) -> GridMetrics:
    """A grid's slot from the base size and the grid's own scale: the table's
    row for `s`, held to 8..23."""
    s = max(SIZE_MIN, min(_round_div(base * clamp_scale(scale), 100), SIZE_MAX))
    return GridMetrics(icon=ICON_PX_PER_PT * s, timer=_row(TIMER_PT, s), stack=_row(STACK_PT, s))
