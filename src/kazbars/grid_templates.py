"""KazBars — grids files: one grid or a class tab's grids, shared on their own
(pure data layer, no Tk).

A grids file (`*.kazbars-grids.yml`) is ``{format: kazbars-grids, schema,
grids, [buffs]}``: each grid exactly as the profile holds it minus its
`class` (the importing tab sets that), plus the user-DB buffs the grids
reference, so they resolve on an install that has never seen them.

  - ``build(grids, by_id, by_name, provenance)`` → the file's value.
  - ``parse(raw)`` → ``(grids, buffs)``; ``ValueError`` with a
    user-presentable message for anything else (a profile gets pointed at
    File ▸ Import profile…).
  - ``import_into(existing, grids, class_id)`` → ``(appended, renames)``: the
    grids validated, on the tab's class, each under a free id.
"""

import copy

from .grid_model import PROFILE_SECTION, validate_grid
from .grids_generator import free_id
from .profile_share import EXPORT_FORMAT, GRIDS_FORMAT, PROFILE_FORMAT, collect_for_refs

TEMPLATE_SCHEMA = 1


def build(grids, by_id, by_name, provenance):
    """The grids file for `grids`: each without its `class`, and the
    user-provenance buffs they reference — only when there are any."""
    out = {
        'format': GRIDS_FORMAT,
        'schema': TEMPLATE_SCHEMA,
        'grids': [{k: copy.deepcopy(v) for k, v in g.items() if k != 'class'} for g in grids],
    }
    harvest = PROFILE_SECTION.harvest_refs
    refs = harvest({'grids': grids}) if harvest else []
    buffs = collect_for_refs(refs, by_id, by_name, provenance)
    if buffs:
        out['buffs'] = buffs
    return out


def parse(raw):
    """A loaded grids file → ``(grids, buffs)``; raises ``ValueError``."""
    fmt = raw.get('format') if isinstance(raw, dict) else None
    if fmt in (PROFILE_FORMAT, EXPORT_FORMAT):
        raise ValueError("That file is a profile, not a grids file. "
                         "Use File ▸ Import profile… instead.")
    if fmt != GRIDS_FORMAT:
        raise ValueError("That file isn't a KazBars grids file.")
    schema = raw.get('schema', TEMPLATE_SCHEMA)
    if isinstance(schema, int) and not isinstance(schema, bool) and schema > TEMPLATE_SCHEMA:
        raise ValueError("This grids file needs a newer KazBars — update the app first.")
    grids = raw.get('grids')
    grids = [g for g in grids if isinstance(g, dict)] if isinstance(grids, list) else []
    if not grids:
        raise ValueError("That file holds no grids.")
    buffs = raw.get('buffs')
    return grids, buffs if isinstance(buffs, list) else []


def import_into(existing, grids, class_id):
    """`grids` made ready to append to `existing`: each validated, on
    `class_id` (None — the All tab — leaves it on every class), under a free
    id (`free_id`: `Buffs` → `Buffs_2` when its archive key is taken, the
    taken set growing as each lands). Returns ``(appended, renames)``,
    renames as ``[(old, new)]``."""
    taken = [g.get('id', '') for g in existing]
    appended, renames = [], []
    for raw in grids:
        grid = validate_grid(copy.deepcopy(raw))
        if class_id is None:
            grid.pop('class', None)
        else:
            grid['class'] = class_id
        old = grid['id']
        grid['id'] = free_id(taken, old)
        if grid['id'] != old:
            renames.append((old, grid['id']))
        taken.append(grid['id'])
        appended.append(grid)
    return appended, renames
