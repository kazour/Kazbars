"""
KazBars — Target inspect panel config (pure data layer).

Defaults + validation for the in-game target inspect panel: a minimal combat
sheet for the current target, rendered by the KazBars module (KazBarsInspect
stub) in the visual language of the game's default inspect window. Configured
via the Extras-menu dialog (`inspect_panel.py`); lives in the profile document
as the `inspect` section (BUILD lane, like `stopwatch` and `cast_timer`), so
the panel travels with the profile. No Tk — importable by the codegen, the
section registry, and tests.

`scale` is a percent of the profile's overlay size; the build bakes the panel's
body size from the two (`overlay_size.panel_fs`) and every dimension in the stub
derives from it, so the panel scales as one piece. `fx`/`fy` are fractions of
the game resolution (pixels exist only at dialog display and AS2 emit via
`grid_model.project_px`/`unproject_px`), baked into the generated SWF as the
first-session seed; from then on the game persists drag position, collapsed
state and the PvP tab in the module config archive, for every user
(`game_persistence`).
"""

import logging

from .overlay_size import SCALE_DEFAULT, scale_from
from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, get_defaults, validate_all

logger = logging.getLogger(__name__)

# Master on/off. Off by default — nothing compiles until the user turns it on,
# so the SWF carries no inspect-panel code when unused.
_SCHEMA = Schema('', 1, {
    "enabled": Field(False, kind='bool'),
    "fx": Field(40 / 1920, kind='float', min=0.0, max=1.0),
    "fy": Field(240 / 1080, kind='float', min=0.0, max=1.0),
    "scale": Field(SCALE_DEFAULT, validate=scale_from),
    "startCollapsed": Field(False, kind='bool'),
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
