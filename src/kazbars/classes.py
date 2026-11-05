"""KazBars — the twelve classes, in the Grids tab's order: four archetypes of
three (pure data, no Tk).

An id is the game's class stat (`GetStat(67, 2)`), the same ids
`KazBarsInspectData` names. A grid's `class` holds one; in game a class builds
its own grids and the All grids (those with no `class`).
"""

from typing import Any, NamedTuple


class GameClass(NamedTuple):
    id: int
    short: str        # the tab label
    name: str
    archetype: int    # 0 soldier, 1 priest, 2 rogue, 3 mage


CLASSES: tuple[GameClass, ...] = (
    GameClass(20, 'Guard', 'Guardian', 0),
    GameClass(22, 'Conq', 'Conqueror', 0),
    GameClass(31, 'DT', 'Dark Templar', 0),
    GameClass(24, 'PoM', 'Priest of Mitra', 1),
    GameClass(28, 'ToS', 'Tempest of Set', 1),
    GameClass(29, 'BS', 'Bear Shaman', 1),
    GameClass(18, 'Barb', 'Barbarian', 2),
    GameClass(34, 'Sin', 'Assassin', 2),
    GameClass(39, 'Ranger', 'Ranger', 2),
    GameClass(44, 'Demo', 'Demonologist', 3),
    GameClass(41, 'Necro', 'Necromancer', 3),
    GameClass(43, 'HoX', 'Herald of Xotli', 3),
)

_BY_ID = {c.id: c for c in CLASSES}


def by_id(class_id: Any) -> GameClass | None:
    """The class with this id, if it is one of the twelve."""
    if isinstance(class_id, bool) or not isinstance(class_id, int):
        return None
    return _BY_ID.get(class_id)


def id_of(value: Any) -> int | None:
    """A stored class id (a grid's `class`, the Grids tab pref): an int naming
    one of the twelve, else None (All)."""
    found = by_id(value)
    return found.id if found else None
