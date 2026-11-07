"""KazBars — the size model of KazBars.swf (pure arithmetic, no Tk).

The profile has ONE base size `B` (`overlay.size`, the Grids toolbar's Overlay
dropdown) and every size in game derives from it, so one value moves
everything in proportion. A module that should differ has its own `scale` `p`
(percent, 50-200, default 100) and works from `s = B x p / 100`:

- Panels (inspect, stopwatch, onslaught, console): `panel_fs`, the body size
  `max(8, round(s))`; the AS2 role scale (small, title, alert) hangs off it in
  `KazBarsPanel`.
- Cast timer: `cast_fs`, the Title role of `s`, `max(8, round(1.25 s))`.
- The preview control panel and the layout-preview labels take `B` itself.
- A buff grid: `grid_metrics`, icon `4 x round(s)` px, timer and stack counter
  `round(s)` pt, then the legibility floor and the fit caps.

The generator bakes these results and the dialogs read them back for their
hints, so the two cannot drift. Every rounding is half-up in integer
arithmetic (AS2's `Math.round`), so a tie such as `1.25 x 10 = 12.5` is 13 on
both sides.
"""

from dataclasses import dataclass
from typing import Any

SCALE_MIN = 50
SCALE_MAX = 200
SCALE_STEP = 5
SCALE_DEFAULT = 100

# A panel never draws its body text under this many points.
PANEL_MIN_PT = 8
# A slot's timer and stack counter are never drawn under this many points.
MIN_TEXT_PT = 9
# A grid's icon is this many px per point of round(s).
ICON_PX_PER_PT = 4
# Flash's text gutter, both sides of a field together, in px.
GUTTER = 4
# The stack counter's inset from the icon's top and right edges, in px.
INSET = 4
# Four Arial Bold digits, in ten-thousandths of an em (a digit is 0.5566 em):
# the widest timer is a one-hour buff, "3600".
TIMER_DIGITS_EM_E4 = 22_264


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


def snap_scale(p: int) -> int:
    """`p` snapped to the nearest step of 5 inside the range: what a Size
    slider commits, whatever value it was dragged to."""
    return clamp_scale((p + SCALE_STEP // 2) // SCALE_STEP * SCALE_STEP)


def _round_div(n: int, d: int) -> int:
    """`n / d` rounded half up, for `n >= 0` (AS2's `Math.round`)."""
    return (2 * n + d) // (2 * d)


def _scaled(base: int, scale: int) -> int:
    return _round_div(base * clamp_scale(scale), 100)


def panel_fs(base: int, scale: int) -> int:
    """A panel's body size, `FS` in `KazBarsPanel`: `max(8, round(s))`."""
    return max(_scaled(base, scale), PANEL_MIN_PT)


def cast_fs(base: int, scale: int) -> int:
    """The cast timer's text size, `max(8, round(1.25 s))` as one rounding."""
    return max(_round_div(base * clamp_scale(scale) * 5, 400), PANEL_MIN_PT)


@dataclass(frozen=True)
class GridMetrics:
    """A grid slot on screen: icon px, timer and stack pt (the slot clip scales
    the art, not the text)."""
    icon: int
    timer: int
    stack: int


def text_box_h(pt: int) -> int:
    """A text field's height for one line of `pt` points: `ceil(1.2 pt)` plus
    the gutter. `KazBarsGridView.createTexts` clamps the timer with the same."""
    return (6 * pt + 4) // 5 + GUTTER


def icon_metrics(icon: int, want_stack: int, want_timer: int) -> GridMetrics:
    """The floor and the fit caps on an icon of a fixed size: nothing under
    MIN_TEXT_PT; the timer fits the icon (four digits and the gutter across its
    width, its box between the stack counter's box and the bottom edge). The
    floor wins over the caps, so on a tiny icon the timer stays legible."""
    stack = max(want_stack, MIN_TEXT_PT)
    below = icon - INSET - text_box_h(stack)
    cap_width = (icon - GUTTER) * 10_000 // TIMER_DIGITS_EM_E4
    cap_height = (below - GUTTER) * 5 // 6
    timer = max(min(want_timer, cap_width, cap_height), MIN_TEXT_PT)
    return GridMetrics(icon=icon, timer=timer, stack=stack)


def grid_metrics(base: int, scale: int) -> GridMetrics:
    """A grid's slot from the base size and the grid's own scale."""
    s = _scaled(base, scale)
    return icon_metrics(ICON_PX_PER_PT * s, s, s)
