"""
KazBars — Target inspect panel config (pure data layer).

Defaults + validation for the in-game target inspect panel: a minimal combat
sheet for the current target, rendered by the KazBars module (KazBarsInspect
stub) in the visual language of the game's default inspect window. Configured
via the Extras-menu dialog (`inspect_panel.py`); lives in the profile document
as the `inspect` section (BUILD lane, like `stopwatch` and `cast_timer`), so
the panel travels with the profile. No Tk — importable by the codegen, the
section registry, and tests.

`fontSize` is baked at build time (cast-timer precedent) and drives the whole
panel: every dimension in the stub derives from it, so the panel scales as one
piece. It is **nullable**: `None` means "follow the shared `panel_font_size`"
(which stays machine-local in prefs.json), the default for all four in-game
panels; a number is a deliberate per-panel override. The Extras dialog hosts
the shared control (as it already hosts the console's build gate), and the
build path is the only place the two are resolved into one number. `fx`/`fy`
are fractions of the game resolution (pixels exist only at dialog display and
AS2 emit via `grid_model.project_px`/`unproject_px`), baked into the generated
SWF as the first-session seed (the panel shows live coordinates while its name
strip is dragged so users can copy them here); from then on the game persists
drag position and collapsed state in the module config archive, for every user
(`game_persistence`).
"""

import logging

from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, get_defaults, nullable_int, validate_all

logger = logging.getLogger(__name__)

# Master on/off. Off by default — nothing compiles until the user turns it on,
# so the SWF carries no inspect-panel code when unused.
_SCHEMA = Schema('', 1, {
    "enabled": Field(False, kind='bool'),
    "fx": Field(40 / 1920, kind='float', min=0.0, max=1.0),
    "fy": Field(240 / 1080, kind='float', min=0.0, max=1.0),
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


# The Extras dialog's slice of the profile document — flat: the config dict
# itself is the section. Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('inspect', _SCHEMA, LANE_BUILD)
