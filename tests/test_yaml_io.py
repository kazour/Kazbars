"""yaml_io: the fixed writer layout, its quoting, and the reader."""

import math

import pytest
import yaml

from kazbars import yaml_io
from kazbars.yaml_io import YamlError, dumps, loads

SCALARS = [None, True, False, 0, -7, 2 ** 63 - 1, -(2 ** 63), 2 ** 64, 0.5, 1.0, -2.25, 1e20, 1e-7,
           -0.0, math.inf, -math.inf]

TRICKY = ["", " lead", "trail ", "no", "No", "on", "OFF", "yes", "y", "n", "null", "~", "true",
          "False", "1.10", "0x1F", "0o7", "12", "-3", "+1", ".5", ".inf", ".nan", "1e5", "a: b",
          "a:", "key #c", "#c", "- x", "-", "?", "[x]", "{x}", "a,b", "*ref", "&anchor", "!tag",
          "|", ">", "'q'", '"q"', "%d", "@x", "`x", "<<", "=", "two\nlines", "cr\rhere",
          "tab\there", "nul\0", "\x85", " ", "\ufeffx", "\x7f", "a?b", "what?", "\u2028", "\u00a0x"]

PLAIN = ["Bloodlust", "Ice Storm E", "Guard (rank 5)", "Tank cooldowns", "a:b", "a#b", "\u00dcn\u00efc\u00f6d\u00e9",
         "x-y_z/1.0", "it's", "back\\slash", 'say "hi"']


def _shapes(value):
    """`value` as a value, a key (str only), in a list and in a nested list."""
    out = [value, [value], {'k': value}, {'k': [[value], {'n': [value]}]}]
    if isinstance(value, str):
        out.append({value: 1})
    return out


@pytest.fixture(params=['libyaml', 'pure'])
def loader(request, monkeypatch):
    """Every read passes on both PyYAML loaders: the C one when the wheel
    carries it, the pure-Python one otherwise."""
    if request.param == 'pure':
        monkeypatch.delattr(yaml, 'CSafeLoader', raising=False)
    elif not hasattr(yaml, 'CSafeLoader'):
        pytest.skip('this PyYAML has no libyaml')
    return request.param


@pytest.mark.parametrize('value', SCALARS, ids=repr)
def test_every_scalar_reads_back(value, loader):
    for shaped in _shapes(value):
        assert loads(dumps(shaped)) == shaped


def test_nan_reads_back_nan(loader):
    assert dumps(math.nan) == '.nan\n'
    assert math.isnan(loads(dumps(math.nan)))


def test_floats_never_carry_an_exponent():
    assert [dumps(f).strip() for f in (1.0, 0.25, 1e-7, 1e20, -2.25)] == [
        '1.0', '0.25', '0.0000001', '100000000000000000000.0', '-2.25']


@pytest.mark.parametrize('text', TRICKY, ids=repr)
def test_tricky_strings_are_quoted_and_read_back_as_text(text, loader):
    assert dumps(text).startswith('"')
    for shaped in _shapes(text):
        assert loads(dumps(shaped)) == shaped


@pytest.mark.parametrize('text', PLAIN, ids=repr)
def test_ordinary_strings_stay_plain(text, loader):
    assert dumps(text) == text + '\n'
    for shaped in _shapes(text):
        assert loads(dumps(shaped)) == shaped


def test_quoted_escapes():
    assert dumps('a"b\\c\n\r\t\0') == '"a\\"b\\\\c\\n\\r\\t\\0"\n'
    assert dumps('\x01\x7f\x85\u2028\u2029\ufeff') == '"\\u0001\\u007f\\u0085\\u2028\\u2029\\ufeff"\n'
    assert dumps('\u00e9 \u00fc') == '\u00e9 \u00fc\n', "other non-ASCII stays verbatim"


def test_container_shapes(loader):
    for value in ([], {}, [1, 2], [1, 'a', None, 0.5, True], {'a': {'b': {'c': 1}}},
                  [{'a': 1}, {}, {'b': [1]}], [[1, 2], [], [[3]]], {'0': 1, '12': [2]},
                  {'grids': [{'id': 'x', 'slots': {'0': [1, 'Bloodlust']}}]}):
        assert loads(dumps(value)) == value
    assert dumps([]) == '[]\n' and dumps({}) == '{}\n'
    assert dumps({'a': [1, 2], 'b': []}) == 'a: [1, 2]\nb: []\n'
    assert dumps({'0': 1}) == '"0": 1\n'


def test_the_pinned_layout():
    doc = {'format': 'kazbars-profile',
           'grids': [{'id': 'Tank cooldowns',
                      'buffs': [{'name': 'Bloodlust', 'ids': [1, 2], 'stacking': True}],
                      'slots': {'0': 1}, 'none': []}],
           'fx': 0.25}
    assert dumps(doc) == (
        'format: kazbars-profile\n'
        'grids:\n'
        '  - id: Tank cooldowns\n'
        '    buffs:\n'
        '      - name: Bloodlust\n'
        '        ids: [1, 2]\n'
        '        stacking: true\n'
        '    slots:\n'
        '      "0": 1\n'
        '    none: []\n'
        'fx: 0.25\n')


def test_keys_must_be_text():
    with pytest.raises(TypeError):
        dumps({1: 'a'})


def test_crlf_reads_like_lf(loader):
    text = dumps({'a': [{'b': 1}, {'c': 'x y'}], 'd': 'two\nlines'})
    assert loads(text.replace('\n', '\r\n')) == loads(text)


def test_json_text_reads(loader):
    assert loads('{"a": [1, 2.5, "x"], "b": {"c": null, "d": true}}') == {
        'a': [1, 2.5, 'x'], 'b': {'c': None, 'd': True}}


def test_dumps_is_idempotent_through_a_read():
    value = {'id': 'g', 'list': [{'a': ['?x', 'ok', 1.0]}, [], {}], 'f': 1e-7, 'n': None}
    assert dumps(loads(dumps(value))) == dumps(value)


def test_unreadable_text_raises_yaml_error():
    with pytest.raises(YamlError):
        loads('a: [1, 2')
    assert issubclass(YamlError, ValueError)
    assert yaml_io.loads('') is None


def test_loads_is_json_shaped(loader):
    value = loads('slots:\n  1: [5]\nwhen: 2024-01-02\nids: !!set {7}\nid: 300\n')
    assert value == {'slots': {'1': [5]}, 'when': '2024-01-02', 'ids': [7], 'id': 300}
    assert loads(dumps(value)) == value


def test_non_characters_are_escaped_and_read_back(loader):
    for text in ('a\ufffeb', '\uffff', 'x\ufffe'):
        assert loads(dumps({'k': text, text: [text]})) == {'k': text, text: [text]}


def test_a_lone_surrogate_is_written_as_the_replacement_character(loader):
    lone = 'a' + chr(0xd800) + 'b'
    assert loads(dumps({'k': lone, lone: [lone]})) == {'k': 'a\ufffdb', 'a\ufffdb': ['a\ufffdb']}


def test_a_lone_surrogate_in_a_json_file_reads_as_the_replacement_character(tmp_path):
    # What loads is what `dumps` writes, so memory matches disk after a save.
    path = tmp_path / 'old.json'
    path.write_text('{"k\\ud83d": ["a\\ud83db"]}', encoding='utf-8')
    assert yaml_io.read_file(path) == {'k\ufffd': ['a\ufffdb']}
