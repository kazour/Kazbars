"""
KazBars — Target inspect panel config (pure data layer).

Defaults + validation for the in-game target inspect panel: a minimal combat
sheet for the current target, rendered by the KazBars module (KazBarsInspect
stub) in the visual language of the game's default inspect window. Configured
via the Extras-menu dialog (`inspect_panel.py`); persisted machine-local in
prefs.json under `inspect` (like `stopwatch` — not per-profile, since screen
position depends on the machine's resolution). No Tk — importable by the
codegen, prefs schema, and tests.

`fontSize` is baked at build time (cast-timer precedent) and drives the whole
panel: every dimension in the stub derives from it, so the panel scales as one
piece. It is **nullable**: `None` means "follow the shared `panel_font_size`",
which is what all four in-game panels do by default; a number is a deliberate
per-panel override. This dialog hosts the shared control (as it already hosts
the console's build gate), and the build path is the only place the two are
resolved into one number. `x`/`y` are baked into the generated SWF (the only position that
survives relaunch on `/loadclip` default clients — the panel shows live
coordinates while its name strip is dragged so users can copy them here);
aoc.exe clients persist drag position and collapsed state via the module
config archive.
"""

import logging

from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .settings_core import Field, Schema, get_defaults, nullable_int, validate_all

logger = logging.getLogger(__name__)

# Master on/off. Off by default — nothing compiles until the user turns it on,
# so the SWF carries no inspect-panel code when unused.
_SCHEMA = Schema('inspect', 1, {
    "enabled": Field(False, kind='bool'),
    "x": Field(40, kind='int', min=0, max=SCREEN_MAX_X),
    "y": Field(240, kind='int', min=0, max=SCREEN_MAX_Y),
    "fontSize": Field(None, validate=nullable_int(min=8, max=48)),
    "startCollapsed": Field(False, kind='bool'),
    "showPvp": Field(True, kind='bool'),
    "showPerks": Field(True, kind='bool'),
})

INSPECT_DEFAULTS = get_defaults(_SCHEMA)


def get_default_config():
    """Return a fresh copy of the default inspect-panel config."""
    return get_defaults(_SCHEMA)


def validate_config(config):
    """Validate/clamp an inspect-panel config on load. Returns a sanitized dict
    containing exactly the default keys (unknown keys dropped, missing keys
    filled with defaults)."""
    return validate_all(_SCHEMA, config)
