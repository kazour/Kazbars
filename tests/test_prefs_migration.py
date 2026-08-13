"""The PREFS_SCHEMA v1 → v2 rung: per-panel font sizes become one shared size.

v1 gave the stopwatch and the inspect panel a `fontSize` each and left the buff
console and preview control panel frozen at 12. v2 adds a flat
`panel_font_size` that all four follow, with the two configurable panels able to
override it (`fontSize: None` = follow).

The rung anchors on Inspect, not on `max()` — the shared control lives in the
Inspect dialog and the console and control panel are the inspect panel's visual
family, so a user who only ever enlarged the stopwatch keeps the other two where
they were. Whatever the stored values, the stopwatch and the inspect panel must
render at exactly the size they rendered at before.

Exercised through `settings_core.load` rather than the rung directly: the ladder
runs on the raw dict *before* `validate_all`, and that ordering is the thing
that has to hold.
"""

import json

from kazbars import settings_core
from kazbars.inspect import validate_config as validate_inspect
from kazbars.prefs import PREFS_SCHEMA
from kazbars.stopwatch import validate_config as validate_stopwatch


def _load_v1(tmp_path, **sections):
    (tmp_path / PREFS_SCHEMA.filename).write_text(
        json.dumps({'schema_version': 1, **sections}), encoding='utf-8'
    )
    return settings_core.load(PREFS_SCHEMA, tmp_path)


def _sizes(prefs):
    """The two overrides as every consumer sees them. An absent section stores as
    a bare `{}` (the prefs Field's default is not run through its validator), so
    the data layer is what turns it into a real config."""
    return (
        validate_stopwatch(prefs['stopwatch'])['fontSize'],
        validate_inspect(prefs['inspect'])['fontSize'],
    )


def test_disagreeing_stopwatch_keeps_its_size_as_an_override(tmp_path):
    out = _load_v1(
        tmp_path,
        stopwatch={'enabled': True, 'fontSize': 16},
        inspect={'enabled': True, 'fontSize': 12},
    )
    assert out['panel_font_size'] == 12
    assert _sizes(out) == (16, None)


def test_agreeing_panels_both_collapse_onto_the_shared_size(tmp_path):
    out = _load_v1(
        tmp_path,
        stopwatch={'fontSize': 16},
        inspect={'fontSize': 16},
    )
    assert out['panel_font_size'] == 16
    assert _sizes(out) == (None, None)


def test_neither_key_lands_on_the_default(tmp_path):
    out = _load_v1(tmp_path, game_path='C:/Games/AoC')
    assert out['panel_font_size'] == 12
    assert _sizes(out) == (None, None)
    assert out['game_path'] == 'C:/Games/AoC'


def test_inspect_alone_sets_the_shared_size(tmp_path):
    # The stopwatch was never configured, so it follows — which is the point:
    # the console and control panel move with the inspect panel, not against it.
    out = _load_v1(tmp_path, inspect={'fontSize': 20})
    assert out['panel_font_size'] == 20
    assert _sizes(out) == (None, None)


def test_stopwatch_alone_leaves_the_shared_size_at_the_default(tmp_path):
    # Anchoring on max() here would silently enlarge the console and control
    # panel for a user who only ever touched the stopwatch.
    out = _load_v1(tmp_path, stopwatch={'fontSize': 24})
    assert out['panel_font_size'] == 12
    assert _sizes(out) == (24, None)


def test_already_migrated_prefs_are_left_alone(tmp_path):
    (tmp_path / PREFS_SCHEMA.filename).write_text(
        json.dumps({
            'schema_version': 2,
            'panel_font_size': 20,
            'stopwatch': {'fontSize': 16},
            'inspect': {'fontSize': None},
        }),
        encoding='utf-8',
    )
    out = settings_core.load(PREFS_SCHEMA, tmp_path)
    assert out['panel_font_size'] == 20
    assert _sizes(out) == (16, None)


def test_save_stamps_the_current_version(tmp_path):
    settings_core.save(PREFS_SCHEMA, tmp_path, _load_v1(tmp_path, inspect={'fontSize': 20}))
    stored = json.loads((tmp_path / PREFS_SCHEMA.filename).read_text(encoding='utf-8'))
    assert stored['schema_version'] == PREFS_SCHEMA.version == 2
    # A second load must not re-run the rung against the now-shared value.
    assert settings_core.load(PREFS_SCHEMA, tmp_path)['panel_font_size'] == 20
