"""scripts/convert_profiles.py: JSON profile files → YAML profile files."""

import importlib.util
import json
from pathlib import Path

import pytest

from kazbars import grid_model, yaml_io
from kazbars.profile_document import SectionRegistry, new_document
from kazbars.profile_share import EXPORT_FORMAT, parse_profile_file

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def conv():
    spec = importlib.util.spec_from_file_location(
        'convert_profiles', REPO / 'scripts' / 'convert_profiles.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc():
    reg = SectionRegistry()
    reg.register(grid_model.PROFILE_SECTION)
    doc = new_document(reg, 'Raid: "best"', (2560, 1440))
    doc['id'] = '1a2b3c4d'
    doc['modules']['grids']['grids'] = [dict(grid_model.create_default_grid(), whitelist=[9, 'Ice Storm'])]
    return doc


def test_an_export_converts_with_its_buffs(conv, tmp_path, capsys):
    buff = {'name': 'Mine', 'ids': [9], 'category': '#X', 'type': 'buff'}
    src = tmp_path / 'Raid.kazbars.json'
    src.write_text(json.dumps({'format': EXPORT_FORMAT, 'export_schema': 1, 'profile': _doc(),
                               'buffs': [buff]}), encoding='utf-8')
    assert conv.main([str(src), '--check']) == 0
    out = tmp_path / 'Raid.kazbars.yml'
    text = out.read_text(encoding='utf-8')
    assert text.startswith('format: kazbars-profile\nschema: ')
    assert parse_profile_file(yaml_io.loads(text)) == (_doc(), [buff])
    assert 'round trip equal' in capsys.readouterr().out


def test_a_folder_of_bare_documents_converts_under_out(conv, tmp_path):
    lib = tmp_path / 'profiles'
    lib.mkdir()
    (lib / 'My Setup.json').write_text(json.dumps(_doc()), encoding='utf-8')
    (lib / 'Other.json').write_text(json.dumps(_doc()), encoding='utf-8')
    out = tmp_path / 'yml'
    assert conv.main([str(lib), '--out', str(out), '--check']) == 0
    assert sorted(p.name for p in out.iterdir()) == ['My Setup.yml', 'Other.yml']
    value = yaml_io.loads((out / 'Other.yml').read_text(encoding='utf-8'))
    assert 'buffs' not in value and parse_profile_file(value) == (_doc(), [])


def test_unreadable_input_exits_non_zero(conv, tmp_path, capsys):
    bad = tmp_path / 'bad.json'
    bad.write_text('{nope', encoding='utf-8')
    junk = tmp_path / 'junk.json'
    junk.write_text('{"hello": 1}', encoding='utf-8')
    assert conv.main([str(bad), str(junk)]) == 1
    assert not (tmp_path / 'bad.yml').exists() and not (tmp_path / 'junk.yml').exists()
    assert capsys.readouterr().out.count('not converted') == 2


def test_a_check_mismatch_exits_non_zero(conv, tmp_path, monkeypatch):
    src = tmp_path / 'x.json'
    src.write_text(json.dumps(_doc()), encoding='utf-8')
    monkeypatch.setattr(conv.yaml_io, 'loads', lambda text: {'other': 1})
    assert conv.main([str(src), '--check']) == 1
