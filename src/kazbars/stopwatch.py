"""
KazBars — In-game stopwatch config (pure data layer).

Defaults + validation for the in-game stopwatch: a count-up Start/Pause/Reset
panel rendered by the KazBars module (KazBarsStopwatch stub). Configured via
the Game-menu dialog (`stopwatch_panel.py`); persisted machine-local in
prefs.json under `stopwatch` (like `build_console` — not per-profile, since
screen position depends on the machine's resolution). No Tk — importable by
the codegen, prefs schema, and tests.

Positioning mirrors the cast timer: `x`/`y` are baked into the generated SWF
(the only position that survives relaunch on `/loadclip` default clients —
the panel shows live coordinates while its title bar is dragged so users can
copy them here); aoc.exe clients persist drag position and collapsed state
via the module config archive.
"""

import logging

from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y

logger = logging.getLogger(__name__)

STOPWATCH_DEFAULTS = {
    # Master on/off. Off by default — nothing compiles until the user turns it
    # on, so the SWF carries no stopwatch code when the feature is unused.
    "enabled": False,
    "x": 850,
    "y": 300,
    # Start as just the title-bar strip (expand with the panel's + button).
    "startCollapsed": False,
}

# key → (default, min, max)
_CLAMP = {
    "x": (850, 0, SCREEN_MAX_X),
    "y": (300, 0, SCREEN_MAX_Y),
}


def get_default_config():
    """Return a fresh copy of the default stopwatch config."""
    return dict(STOPWATCH_DEFAULTS)


def validate_config(config):
    """Validate/clamp a stopwatch config on load. Returns a sanitized dict
    containing exactly the default keys (unknown keys dropped, missing keys
    filled with defaults)."""
    result = get_default_config()
    if not isinstance(config, dict):
        return result
    for key in result:
        if key not in config:
            continue
        value = config[key]
        if key in ("enabled", "startCollapsed"):
            result[key] = bool(value)
        elif key in _CLAMP:
            _default, lo, hi = _CLAMP[key]
            try:
                result[key] = max(lo, min(int(value), hi))
            except (ValueError, TypeError):
                result[key] = _default
    return result
