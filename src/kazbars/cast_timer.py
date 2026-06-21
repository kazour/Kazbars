"""
KazBars — Cast Timer config (pure data layer).

Defaults + validation for the cast-timer overlay: a timer-only Flash overlay
(no bar) showing cast time for the player and/or target. Configured via the
frozen strip at the top of the Grids panel; persisted in the profile under
`cast_timer` (like `boss_timer`). No Tk — importable by the codegen and tests.

Positioning mirrors grids: `playerX/Y` and `targetX/Y` are baked into the
generated SWF (the only positions that survive relaunch on `/loadclip` default
clients) and also serve as the preview-drag starting point; aoc.exe clients
persist drag positions via the config archive.
"""

import logging

from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .settings_core import Field, Schema, get_defaults, validate_all

logger = logging.getLogger(__name__)

# Font is fixed to Arial: it's the only face embedded in base.swf, and AoC's
# Flash runtime can't fall back to OS device fonts, so any other choice would
# render blank. Bold is exposed instead (Arial Bold is embedded too).

# display: what the timer text shows.
#   "elapsed" — count up,        e.g. "1.2"
#   "total"   — EMA estimate,    e.g. "2.5"
#   "both"    — elapsed / total, e.g. "1.2 / 2.5"
DISPLAY_MODES = ("elapsed", "total", "both")

def validate_color(hex_str):
    """Validate a hex color string. Returns cleaned 6-char hex or white."""
    hex_str = str(hex_str).strip().lstrip("#").upper()
    if len(hex_str) == 6:
        try:
            int(hex_str, 16)
            return hex_str
        except ValueError:
            pass
    return "FFFFFF"


# Master on/off for the whole overlay; per-side enableP/enableT pick which sides
# show when the master is on. Off by default — nothing compiles until the user
# turns it on.
_SCHEMA = Schema('cast_timer', 1, {
    "enabled": Field(False, kind='bool'),
    "enableP": Field(False, kind='bool'),
    "enableT": Field(False, kind='bool'),
    "playerX": Field(910, kind='int', min=0, max=SCREEN_MAX_X),
    "playerY": Field(620, kind='int', min=0, max=SCREEN_MAX_Y),
    "targetX": Field(910, kind='int', min=0, max=SCREEN_MAX_X),
    "targetY": Field(560, kind='int', min=0, max=SCREEN_MAX_Y),
    "bold": Field(True, kind='bool'),
    "fontSize": Field(12, kind='int', min=8, max=48),
    "display": Field("elapsed", choices=DISPLAY_MODES),
    "color": Field("FFFFFF", validate=validate_color),
})

CAST_TIMER_DEFAULTS = get_defaults(_SCHEMA)


def get_default_config():
    """Return a fresh copy of the default cast-timer config."""
    return get_defaults(_SCHEMA)


def validate_config(config):
    """Validate/clamp a cast-timer config on load. Returns a sanitized dict
    containing exactly the default keys (unknown keys dropped, missing keys
    filled with defaults)."""
    result = validate_all(_SCHEMA, config)
    # Migrate profiles that predate the master enable: derive it from the sides
    # so an existing player/target-on config keeps rendering after the upgrade.
    if isinstance(config, dict) and "enabled" not in config:
        result["enabled"] = result["enableP"] or result["enableT"]
    return result


def is_enabled(config):
    """True iff the overlay would emit any timer: the master enable is on AND at
    least one side is on. Legacy configs that predate the master enable (no
    `enabled` key) fall back to "any side on". Drives the build-time
    `include_cast_timer` gate — when False, no cast-timer code is compiled."""
    sides = bool(config.get("enableP")) or bool(config.get("enableT"))
    if "enabled" not in config:
        return sides
    return bool(config.get("enabled")) and sides
