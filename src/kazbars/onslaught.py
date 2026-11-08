"""KazBars — the Onslaught Tracker: its watch catalog, its instances and its
profile section (pure data, no Tk).

The in-game tracker (KazBarsOnslaught / KazBarsOnsScan stubs) watches the
Onslaught instances (Skull Gate, Kuthchemes): a board listing the bosses,
skull minis and minis in view with their health, the wave line and timer,
spawn alerts, AoE warnings and the defended ally's health. It always watches
the catalog's bosses, skulls, guards and minis; the Kuthchemes camp beasts
with `camps`; and up to 20 names of the user's own, as minis. In game a name
matches exactly and case-sensitively, so the spelling here is the game's own.
The guards list in their own tier at the bottom of the board with `guards`,
else among the skulls. A skull standing on one of its instance's camps shows
the camp's name in place of its distance; a mob carrying a SHIELD_BUFFS buff draws
its bar light blue.

The section (`onslaught`, BUILD lane): `enabled`, `scale` (the board's text,
`overlay_size.panel_fs`), `alertScale` (the alert banners' text, the same way;
160 by default, where the alerts drew at 1.6 times the board), the five
displays (`showList` Mob list, `showWave` Wave timer, `showAlly` Hylda HP,
`showAlerts` Spawn alerts, `showAoe` AoE warnings), `alertSeconds` (how long a
banner stays), `camps`, `guards` and `custom`. It ships when enabled with at least one
display. The board and the alerts are placed in game, in preview mode.
"""

import unicodedata
from typing import Any, NamedTuple

from .overlay_size import SCALE_DEFAULT, scale_from
from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, validate_all

# ============================================================================
# CATALOG
# ============================================================================
# What a watched name is, and so which board tier it lists under: boss (b),
# skull mini (s), guard (g: a skull, in a tier of its own with `guards`),
# mini (m), or camp beast (c: listed, but it never alerts).
BOSS, SKULL, GUARD, MINI, CAMP = 'b', 's', 'g', 'm', 'c'

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
    Row('Gurnakhi Juggernaut', 'Skull Gate skull', GUARD),
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
    Row('Ancient Kuthcheman Guardian', 'Kuthchemes skull', GUARD),
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
# Where a row comes from, in catalog order (the dialog names the watched mobs
# one line per group, in this order; the camps come last).
GROUPS = tuple(dict.fromkeys(r.group for r in ROWS))


class Camp(NamedTuple):
    """A spot a skull walks to before it casts: the board names it while the
    skull stands within `r` metres (3-D) of any of its `points` (x, y, z)."""
    name: str
    r: int
    points: tuple[tuple[int, int, int], ...]


class Instance(NamedTuple):
    """Per-playfield facts, so the AS2 hardcodes no game ids or text. `ally` is
    an NPC the group defends (never a watched mob); `aoe` marks an instance
    whose AOE_HELPERS spawn; `camps` in check order (the first in reach names
    the spot; coordinates measured in game)."""
    playfield: int
    start_hint: str
    spawn_ms: int
    ally: str
    aoe: bool
    camps: tuple[Camp, ...]


INSTANCES = (
    Instance(20010, 'talk to Hylda', 200_000, 'Valkyrie Hylda', False, (  # Skull Gate
        Camp('Hub', 20, ((185, 50, 76),)),
        Camp('Cave', 20, ((283, 35, 137),)),
        Camp('WCave', 19, ((181, 30, 145), (222, 25, 173))),
        Camp('Tower', 20, ((57, 33, 230),)),
        Camp('Bridge', 20, ((34, 39, 281),)),
        Camp('Altar', 20, ((104, 36, 140),)),
    )),
    Instance(20000, 'click the banner', 200_000, '', True, (  # Kuthchemes
        Camp('Respad', 10, ((283, 111, 133),)),
        Camp('South West', 5, ((128, 104, 225), (160, 106, 174))),
        Camp('South East', 5, ((293, 103, 201),)),
        Camp('Temple', 5, ((283, 104, 203), (242, 114, 268), (259, 114, 275),
                           (235, 114, 271), (264, 114, 263), (253, 114, 259))),
        Camp('East', 5, ((351, 105, 227), (360, 105, 207), (311, 106, 262))),
        Camp('South', 5, ((241, 102, 188), (218, 105, 177))),
        Camp('West', 5, ((159, 106, 174), (139, 104, 202), (123, 103, 226))),
        Camp('North', 5, ((235, 95, 329), (291, 98, 322), (335, 94, 318), (375, 94, 320))),
    )),
)

# Spawns with these names are AoE-warning candidates first, watched or not.
AOE_HELPERS = ('Thugra Khotan',)
# Buff names that mark a boss as being healed (a green cross on its row);
# matched by name, as buff ids are per session.
HEAL_BUFFS = ('Healing Radiance',)
# Buff names that shield a mob from damage (its bar drawn light blue), by name.
SHIELD_BUFFS: tuple[str, ...] = ('Ancient Ward',)


# The longest catalog name: the board's name column and the alert width are
# sized to it, so a custom name may be no longer.
NAME_MAX = 27
# The most custom names a section keeps (the first ones, in the user's order).
CUSTOM_MAX = 20
# How long a banner stays, in seconds: the range the dialog's slider offers.
ALERT_SECONDS = (3, 15)


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
    'alertScale': Field(160, validate=scale_from),
    'showList': Field(True, kind='bool'),
    'showAlerts': Field(True, kind='bool'),
    'showWave': Field(True, kind='bool'),
    'showAoe': Field(True, kind='bool'),
    'showAlly': Field(True, kind='bool'),
    'alertSeconds': Field(6, kind='int', min=ALERT_SECONDS[0], max=ALERT_SECONDS[1]),
    'camps': Field(False, kind='bool'),
    'guards': Field(True, kind='bool'),
    'custom': Field([], validate=_validate_custom),
})

_DISPLAYS = ('showList', 'showAlerts', 'showWave', 'showAoe', 'showAlly')


def validate_config(config: Any) -> dict:
    return validate_all(_SCHEMA, config)


def ships(config: dict) -> bool:
    """The build gate: enabled, with at least one of the five displays on."""
    return bool(config.get('enabled')) and any(config.get(k) for k in _DISPLAYS)


def names_of(config: dict, kind: str) -> list[str]:
    """The watched names of one kind: the catalog's rows of it in catalog
    order (the camps only with `camps`; the guards only with `guards`, else
    among the skulls), then, for minis, the custom names in the user's
    order."""
    apart = config.get('guards')

    def listed_as(row):
        return SKULL if row.kind == GUARD and not apart else row.kind

    names = [] if kind == CAMP and not config.get('camps') else [r.name for r in ROWS if listed_as(r) == kind]
    if kind == MINI:
        names += config.get('custom', [])
    return names


# Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('onslaught', _SCHEMA, LANE_BUILD)
