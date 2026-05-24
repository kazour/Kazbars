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

logger = logging.getLogger(__name__)

# Font is fixed to Arial: it's the only face embedded in base.swf, and AoC's
# Flash runtime can't fall back to OS device fonts, so any other choice would
# render blank. Bold is exposed instead (Arial Bold is embedded too).

# display: what the timer text shows.
#   "elapsed" — count up,        e.g. "1.2"
#   "total"   — EMA estimate,    e.g. "2.5"
#   "both"    — elapsed / total, e.g. "1.2 / 2.5"
DISPLAY_MODES = ("elapsed", "total", "both")

CAST_TIMER_DEFAULTS = {
    # Master on/off for the whole overlay. Per-side enableP/enableT pick which
    # sides show when the master is on. Off by default — nothing compiles until
    # the user turns it on.
    "enabled": False,
    "enableP": False,
    "enableT": False,
    "playerX": 910,
    "playerY": 620,
    "targetX": 910,
    "targetY": 560,
    "bold": True,
    "fontSize": 12,
    "display": "elapsed",
    "color": "FFFFFF",
}

# key → (default, min, max)
_CLAMP = {
    "playerX": (910, 0, SCREEN_MAX_X),
    "playerY": (620, 0, SCREEN_MAX_Y),
    "targetX": (910, 0, SCREEN_MAX_X),
    "targetY": (560, 0, SCREEN_MAX_Y),
    "fontSize": (12, 8, 48),
}


def get_default_config():
    """Return a fresh copy of the default cast-timer config."""
    return dict(CAST_TIMER_DEFAULTS)


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


def validate_config(config):
    """Validate/clamp a cast-timer config on load. Returns a sanitized dict
    containing exactly the default keys (unknown keys dropped, missing keys
    filled with defaults)."""
    result = get_default_config()
    if not isinstance(config, dict):
        return result
    for key in result:
        if key not in config:
            continue
        value = config[key]
        if key in ("enabled", "enableP", "enableT", "bold"):
            result[key] = bool(value)
        elif key == "display":
            result[key] = value if value in DISPLAY_MODES else CAST_TIMER_DEFAULTS["display"]
        elif key == "color":
            result[key] = validate_color(value)
        elif key in _CLAMP:
            _default, lo, hi = _CLAMP[key]
            try:
                result[key] = max(lo, min(int(value), hi))
            except (ValueError, TypeError):
                result[key] = _default
    # Migrate profiles that predate the master enable: derive it from the sides
    # so an existing player/target-on config keeps rendering after the upgrade.
    if "enabled" not in config:
        result["enabled"] = bool(config.get("enableP")) or bool(config.get("enableT"))
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
