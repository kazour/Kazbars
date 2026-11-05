"""KazBars — the Console config (pure data layer).

An in-game panel of tabs (KazBarsConsole stub): Buffs logs every buff and
debuff applied to you and your target with its buff id — the id you need to
track something the database doesn't carry — and Casts logs your and your
target's casts as they end. Configured via the Extras-menu dialog
(`console_panel.py`); lives in the profile document as the `console` section
(BUILD lane).

`enabled` is the master switch (off by default), `scale` its share of the
overlay size (`overlay_size.panel_fs`), `tabs` the tabs it holds in the user's
order — the in-game strip's order. It ships when enabled with at least one
tab, and each tab is its own class under its own build gate, so a tab left out
costs the SWF nothing. The panel opens in preview mode (Shift+Ctrl+Alt) and
keeps its spot, fold and visible tab in the module archive.
"""

from typing import Any

from .overlay_size import SCALE_DEFAULT, scale_from
from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, get_defaults, validate_all

# Every tab, in its default order.
TABS = ('buffs', 'casts')


def _validate_tabs(value: Any) -> list[str]:
    """Known tab names kept in order, repeats dropped; not a list reads as every tab."""
    if not isinstance(value, list):
        return list(TABS)
    tabs: list[str] = []
    for t in value:
        if isinstance(t, str) and t in TABS and t not in tabs:
            tabs.append(t)
    return tabs


_SCHEMA = Schema('', 1, {
    'enabled': Field(False, kind='bool'),
    'scale': Field(SCALE_DEFAULT, validate=scale_from),
    'tabs': Field(list(TABS), validate=_validate_tabs),
})


def get_default_config() -> dict:
    return get_defaults(_SCHEMA)


def validate_config(config: Any) -> dict:
    return validate_all(_SCHEMA, config)


def ships(config: dict) -> bool:
    """What the build carries: the master switch and at least one tab."""
    return bool(config.get('enabled')) and bool(config.get('tabs'))


# Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('console', _SCHEMA, LANE_BUILD)
