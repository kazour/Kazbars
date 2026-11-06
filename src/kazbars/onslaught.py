"""KazBars — the Onslaught Tracker: its watch catalog, its instances and its
profile section (pure data, no Tk).

The in-game tracker (KazBarsOnslaught / KazBarsOnsScan stubs) watches the
Onslaught instances (Skull Gate, Kuthchemes): a board listing the bosses,
skull minis and minis in view with their health, the wave line and timer,
spawn alerts, AoE warnings and the defended ally's health. It always watches
the catalog's bosses, skulls and minis; the Kuthchemes camp beasts with
`camps`; and up to 20 names of the user's own, as minis. In game a name
matches exactly and case-sensitively, so the spelling here is the game's own.

The section (`onslaught`, BUILD lane): `enabled`, `scale` (the board's text,
`overlay_size.panel_fs`; the alerts draw 1.6 times as large), the five
displays (`showList` Mob list, `showWave` Wave timer, `showAlly` Hylda HP,
`showAlerts` Spawn alerts, `showAoe` AoE warnings), `alertSeconds` (how long a
banner stays), `camps` and `custom`. It ships when enabled with at least one
display. The board and the alerts are placed in game, in preview mode.
"""

import unicodedata
from typing import Any, NamedTuple

from .overlay_size import SCALE_DEFAULT, scale_from
from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, get_defaults, validate_all

# ============================================================================
# CATALOG
# ============================================================================
# What a watched name is, and so which board tier it lists under: boss (b),
# skull mini (s), mini (m), or camp beast (c: listed, but it never alerts).
BOSS, SKULL, MINI, CAMP = 'b', 's', 'm', 'c'

# Where a row comes from, in catalog order (the dialog names the watched mobs
# one line per group, in this order).
GROUPS = ('Skull Gate boss', 'Skull Gate skull', 'Skull Gate mini', 'Kuthchemes boss',
          'Kuthchemes skull', 'Kuthchemes mini', 'Kuthchemes camp')


class Row(NamedTuple):
    name: str
    group: str
    kind: str


# Catalog order = emission order. Sources: the bosses/minibosses roster built
# from combat logs (boss = the end-of-wave Champion, miniboss = every other
# enemy above the HP threshold), wave ranges from public guides, names and
# spawn windows measured in game.
ROWS: tuple[Row, ...] = (
    Row('Taskmaster Mijoral', 'Skull Gate boss', BOSS),  # waves 1-4
    Row('Thror Ironhand', 'Skull Gate boss', BOSS),  # waves 5-9
    Row('Vammatar the Cruel', 'Skull Gate boss', BOSS),  # waves 10-14
    Row('Louhi', 'Skull Gate boss', BOSS),  # waves 15-19
    Row('Gurnakhi Juggernaut', 'Skull Gate skull', SKULL),
    Row('Concubine of Vammatar', 'Skull Gate skull', SKULL),
    Row('Acolyte of Louhi', 'Skull Gate skull', SKULL),
    Row('Priest of the Purple Plague', 'Skull Gate skull', SKULL),
    Row('High Priest Vallittu', 'Skull Gate mini', MINI),
    Row('Gurnakhi Death Knight', 'Skull Gate mini', MINI),
    Row('Gurnakhi Slaver', 'Skull Gate mini', MINI),
    Row('Gurnakhi Warlord', 'Skull Gate mini', MINI),  # not yet confirmed in game
    Row('Kushite Chieftain', 'Kuthchemes boss', BOSS),  # waves 1-4 and 20-24
    Row('Attendant of Zug', 'Kuthchemes boss', BOSS),  # waves 5-9 and 25-29
    Row('Prince Kutamun', 'Kuthchemes boss', BOSS),  # waves 10-14 and 30-34
    # Its AoE helpers share the name; they drive the AoE warnings, not this row.
    Row('Thugra Khotan', 'Kuthchemes boss', BOSS),  # waves 15-19 and 35-39
    Row('Ancient Kuthcheman Guardian', 'Kuthchemes skull', SKULL),
    Row('Ancient Kuthcheman Witch', 'Kuthchemes skull', SKULL),
    Row('Concubine of Khotan', 'Kuthchemes skull', SKULL),
    Row('Excavator of Souls', 'Kuthchemes skull', SKULL),
    Row('Asshuri Sultan', 'Kuthchemes mini', MINI),
    Row('Templar of Set', 'Kuthchemes mini', MINI),
    Row('Herald of Khotan', 'Kuthchemes mini', MINI),
    Row('Otanes', 'Kuthchemes mini', MINI),
    Row('Myrcinus', 'Kuthchemes mini', MINI),
    Row('Shathrazan', 'Kuthchemes mini', MINI),
    Row('Kushite Firedancer', 'Kuthchemes mini', MINI),
    Row('Kuthcheman Spider Demon', 'Kuthchemes camp', CAMP),
    Row('Khorajan Sandwyrm', 'Kuthchemes camp', CAMP),
    Row('Ancient Ruins Scorpion', 'Kuthchemes camp', CAMP),
    Row('Kuthcheman Monitor Demon', 'Kuthchemes camp', CAMP),
    Row('Zug-Touched Camel Spider', 'Kuthchemes camp', CAMP),
    Row('Serpent of Khotan', 'Kuthchemes camp', CAMP),
    Row('Zug-Touched Monitor', 'Kuthchemes camp', CAMP),
    Row('Zug-Touched Scorpion', 'Kuthchemes camp', CAMP),
)
_NAMES = {r.name for r in ROWS}


class Instance(NamedTuple):
    """Per-playfield facts, so the AS2 hardcodes no game ids or text. `ally` is
    an NPC the group defends (never a watched mob); `aoe` marks an instance
    whose AOE_HELPERS spawn."""
    playfield: int
    name: str
    start_hint: str
    spawn_ms: int
    ally: str
    aoe: bool


INSTANCES = (
    Instance(20010, 'Skull Gate', 'talk to Hylda', 200_000, 'Valkyrie Hylda', False),
    Instance(20000, 'Kuthchemes', 'click the banner', 200_000, '', True),
)

# Spawns with these names are AoE-warning candidates first, watched or not.
AOE_HELPERS = ('Thugra Khotan',)
# Buff names that mark a boss as being healed (a green cross on its row);
# matched by name, as buff ids are per session.
HEAL_BUFFS = ('Healing Radiance',)

# The longest catalog name: the board's name column and the alert width are
# sized to it, so a custom name may be no longer.
NAME_MAX = 27
# The most custom names a section keeps (the first ones, in the user's order).
CUSTOM_MAX = 20


def find(name: str) -> Row | None:
    return next((r for r in ROWS if r.name == name), None)


def custom_refusal(name: str, held: list[str]) -> str | None:
    """Why `name` (already trimmed) cannot join `held` as a custom name, or
    None when it can. The validator drops what this refuses and the dialog's
    Add asks it first, so the two never disagree. Beyond the caps it refuses
    what the tracker would never match as a mob (XX names, the ally) and what
    the baked string cannot carry (AVM1 strings end at a NUL)."""
    if not name:
        return "Type a mob's name first."
    if any(unicodedata.category(c) == 'Cc' for c in name):
        return "A mob's name has no tabs or control characters."
    if len(name) > NAME_MAX:
        return "Too long: the board fits names up to the catalog's longest."
    if name in _NAMES:
        return "Already watched: it is in the catalog."
    if any(i.ally == name for i in INSTANCES):
        return "That is the ally you defend: Hylda HP tracks her."
    if name.startswith('XX'):
        return "XX names are the game's hidden helpers: the tracker skips them."
    if name in held:
        return "Already in your list."
    if len(held) >= CUSTOM_MAX:
        return "The list is full: delete a name first."
    return None


# ============================================================================
# SECTION
# ============================================================================
def _validate_custom(value: Any) -> list[str]:
    """A non-list reads as empty; each string trimmed and kept when
    `custom_refusal` lets it join the ones kept before it."""
    kept: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and custom_refusal(item.strip(), kept) is None:
            kept.append(item.strip())
    return kept


_SCHEMA = Schema('', 1, {
    'enabled': Field(False, kind='bool'),
    'scale': Field(SCALE_DEFAULT, validate=scale_from),
    'showList': Field(True, kind='bool'),
    'showAlerts': Field(True, kind='bool'),
    'showWave': Field(True, kind='bool'),
    'showAoe': Field(True, kind='bool'),
    'showAlly': Field(True, kind='bool'),
    'alertSeconds': Field(6, kind='int', min=3, max=15),
    'camps': Field(False, kind='bool'),
    'custom': Field([], validate=_validate_custom),
})

_DISPLAYS = ('showList', 'showAlerts', 'showWave', 'showAoe', 'showAlly')


def get_default_config() -> dict:
    return get_defaults(_SCHEMA)


def validate_config(config: Any) -> dict:
    return validate_all(_SCHEMA, config)


def ships(config: dict) -> bool:
    """The build gate: enabled, with at least one of the five displays on."""
    return bool(config.get('enabled')) and any(config.get(k) for k in _DISPLAYS)


def names_of(config: dict, kind: str) -> list[str]:
    """The watched names of one kind: the catalog's rows of it in catalog
    order (the camps only with `camps`), then, for minis, the custom names in
    the user's order."""
    names = [] if kind == CAMP and not config.get('camps') else [r.name for r in ROWS if r.kind == kind]
    if kind == MINI:
        names += config.get('custom', [])
    return names


# Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('onslaught', _SCHEMA, LANE_BUILD)
