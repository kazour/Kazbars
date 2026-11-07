"""grid_templates: build, parse and import of grids files."""

import pytest

from kazbars import grid_templates as GT
from kazbars import yaml_io
from kazbars.grid_model import create_default_grid
from kazbars.profile_share import EXPORT_FORMAT, PROFILE_FORMAT


def _b(i, name):
    return {"name": name, "ids": [i], "category": "#X", "type": "buff"}


def _grid(grid_id, cls=None, **extra):
    g = create_default_grid('player', 1, 5, 'dynamic', grid_id)
    if cls:
        g['class'] = cls
    g.update(extra)
    return g


def test_build_strips_class_and_embeds_only_user_buffs():
    user, stock = _b(9, "Mine"), _b(1, "Stock")
    grids = [_grid('A', 31, whitelist=[1, 9]), _grid('B', slotAssignments={'0': ['Mine']})]
    value = GT.build(grids, {1: stock, 9: user}, {"Mine": user, "Stock": stock},
                     {1: 'stock', 9: 'user'})
    assert list(value)[:3] == ['format', 'schema', 'grids']
    assert value['format'] == 'kazbars-grids' and value['schema'] == 1
    assert all('class' not in g for g in value['grids'])
    assert grids[0]['class'] == 31, "the profile's grid is untouched"
    assert value['buffs'] == [user]
    assert yaml_io.dumps(value).startswith('format: kazbars-grids\nschema: 1\ngrids:\n')


def test_build_leaves_out_the_cards_private_keys():
    value = GT.build([_grid('A', whitelist=[1], _orphanedAssignments=[9])], {}, {}, {})
    assert '_orphanedAssignments' not in value['grids'][0]


def test_build_omits_buffs_when_none():
    assert 'buffs' not in GT.build([_grid('A', whitelist=[1])], {}, {}, {})


def test_parse_round_trips_a_built_file():
    user = _b(9, "Mine")
    value = GT.build([_grid('A', whitelist=[9])], {9: user}, {}, {9: 'user'})
    grids, buffs = GT.parse(yaml_io.loads(yaml_io.dumps(value)))
    assert [g['id'] for g in grids] == ['A'] and buffs == [user]


@pytest.mark.parametrize('raw,message', [
    (None, "isn't a KazBars grids file"),
    ([1], "isn't a KazBars grids file"),
    ({'grids': []}, "isn't a KazBars grids file"),
    ({'format': 'other'}, "isn't a KazBars grids file"),
    ({'format': PROFILE_FORMAT, 'schema': 3}, "is a profile, not a grids file. Use File ▸ Import profile"),
    ({'format': EXPORT_FORMAT, 'profile': {}}, "is a profile, not a grids file"),
    ({'format': 'kazbars-grids', 'schema': 2, 'grids': [{}]}, "needs a newer KazBars"),
    ({'format': 'kazbars-grids', 'grids': []}, "holds no grids"),
    ({'format': 'kazbars-grids', 'grids': [1, 'x']}, "holds no grids"),
    ({'format': 'kazbars-grids', 'grids': 'x'}, "holds no grids"),
])
def test_parse_messages(raw, message):
    with pytest.raises(ValueError, match=message):
        GT.parse(raw)


def test_parse_reads_an_absent_schema_as_one_and_drops_junk_buffs():
    grids, buffs = GT.parse({'format': 'kazbars-grids', 'grids': [{'id': 'A'}, 3], 'buffs': 'x'})
    assert grids == [{'id': 'A'}] and buffs == []


def test_import_renames_on_an_archive_key_collision():
    existing = [_grid('Buffs DT')]
    appended, renames = GT.import_into(existing, [_grid('Buffs_DT'), _grid('Other')], 31)
    assert [g['id'] for g in appended] == ['Buffs_DT_2', 'Other']
    assert renames == [('Buffs_DT', 'Buffs_DT_2')]
    assert existing == [_grid('Buffs DT')], "the tab's own grids are untouched"


def test_import_keeps_taken_growing_across_the_batch():
    appended, renames = GT.import_into([], [_grid('A'), _grid('A'), _grid('A')], None)
    assert [g['id'] for g in appended] == ['A', 'A_2', 'A_3']
    assert renames == [('A', 'A_2'), ('A', 'A_3')]


def test_import_sets_or_clears_the_class():
    appended, _ = GT.import_into([], [_grid('A', 30)], 31)
    assert appended[0]['class'] == 31
    appended, _ = GT.import_into([], [_grid('A', 30)], None)
    assert 'class' not in appended[0]


def test_import_validates_each_grid():
    raw = {'id': 'Junk', 'rows': 'abc', 'cols': 3, 'type': 'nope', 'enabled': 'yes'}
    appended, _ = GT.import_into([], [raw], None)
    g = appended[0]
    assert g['type'] == 'player' and isinstance(g['rows'], int) and g['enabled'] is True
    assert raw == {'id': 'Junk', 'rows': 'abc', 'cols': 3, 'type': 'nope', 'enabled': 'yes'}
