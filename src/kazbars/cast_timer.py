"""
KazBars — Cast Timer config (pure data layer).

Defaults + validation for the cast-timer overlay: a timer-only Flash overlay
(no bar) showing cast time for the player and/or target. Configured via the
Extras-menu dialog (`cast_timer_panel.py`); lives in the profile document as
the `cast_timer` section (BUILD lane, like `stopwatch` and `inspect`), so the
overlay travels with the profile. No Tk — importable by the codegen, the
section registry, and tests.

Positioning mirrors grids: the player/target positions are stored as fractions
of the game resolution (full floats 0..1 — pixels exist only at dialog display
and AS2 emit via `grid_model.project_px`/`unproject_px`) and are baked into
the generated SWF as the first-session seed and the preview-drag starting
point. From then on the game itself persists drag positions in the module
config archive, for every user (`game_persistence`).
"""

import logging

from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
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
# show when the master is on. No UI splits them — the dialog writes all three from
# its one master toggle — but the generator reads them per side, so they stay in the
# schema as its contract and as the hook a per-side option would use. Off by
# default — nothing compiles until the user turns it on.
_SCHEMA = Schema('', 1, {
    "enabled": Field(False, kind='bool'),
    "enableP": Field(False, kind='bool'),
    "enableT": Field(False, kind='bool'),
    "playerFx": Field(910 / 1920, kind='float', min=0.0, max=1.0),
    "playerFy": Field(620 / 1080, kind='float', min=0.0, max=1.0),
    "targetFx": Field(910 / 1920, kind='float', min=0.0, max=1.0),
    "targetFy": Field(560 / 1080, kind='float', min=0.0, max=1.0),
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
    return validate_all(_SCHEMA, config)


def is_enabled(config):
    """True iff the overlay would emit any timer: the master enable is on AND at
    least one side is on. Drives the build-time `include_cast_timer` gate — when
    False, no cast-timer code is compiled."""
    return bool(config.get("enabled")) and (
        bool(config.get("enableP")) or bool(config.get("enableT")))


# The Extras dialog's slice of the profile document — flat: the config dict
# itself is the section. Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('cast_timer', _SCHEMA, LANE_BUILD)
