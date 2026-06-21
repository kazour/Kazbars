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
from .settings_core import Field, Schema, get_defaults, validate_all

logger = logging.getLogger(__name__)

# Master on/off. Off by default — nothing compiles until the user turns it on,
# so the SWF carries no stopwatch code when unused. startCollapsed starts the
# panel as just the title-bar strip (expand with its + button).
_SCHEMA = Schema('stopwatch', 1, {
    "enabled": Field(False, kind='bool'),
    "x": Field(850, kind='int', min=0, max=SCREEN_MAX_X),
    "y": Field(300, kind='int', min=0, max=SCREEN_MAX_Y),
    "startCollapsed": Field(False, kind='bool'),
})

STOPWATCH_DEFAULTS = get_defaults(_SCHEMA)


def get_default_config():
    """Return a fresh copy of the default stopwatch config."""
    return get_defaults(_SCHEMA)


def validate_config(config):
    """Validate/clamp a stopwatch config on load. Returns a sanitized dict
    containing exactly the default keys (unknown keys dropped, missing keys
    filled with defaults)."""
    return validate_all(_SCHEMA, config)
