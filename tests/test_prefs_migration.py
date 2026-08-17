"""The PREFS_SCHEMA v1 → v2 rung: per-panel font sizes become one shared size.

v1 gave the stopwatch and the inspect panel a `fontSize` each and left the buff
console and preview control panel frozen at 12. v2 adds a flat
`panel_font_size` that all four follow, anchored on Inspect, not on `max()` —
the shared control lives in the Inspect dialog and the console and control
panel are the inspect panel's visual family, so a user who only ever enlarged
the stopwatch keeps the other two where they were.

The stopwatch/inspect/cast_timer configs later moved into the profile document
and their prefs Fields were dropped, so strict validation now erases the
sub-dicts the rung rewrites — its surviving effect is the lifted
`panel_font_size`. These tests pin both halves: the lift still lands, and the
retired keys are gone after a load.

Exercised through `settings_core.load` rather than the rung directly: the
ladder runs on the raw dict *before* `validate_all`, and that ordering is the
thing that has to hold.
"""

import json

from kazbars import settings_core
from kazbars.prefs import PREFS_SCHEMA

RETIRED_KEYS = ("stopwatch", "inspect", "cast_timer")


def _load_v1(tmp_path, **sections):
    (tmp_path / PREFS_SCHEMA.filename).write_text(
        json.dumps({'schema_version': 1, **sections}), encoding='utf-8'
    )
    return settings_core.load(PREFS_SCHEMA, tmp_path)


def test_inspect_size_lifts_onto_the_shared_size(tmp_path):
    out = _load_v1(
        tmp_path,
        stopwatch={'enabled': True, 'fontSize': 16},
        inspect={'enabled': True, 'fontSize': 12},
    )
    assert out['panel_font_size'] == 12
    for key in RETIRED_KEYS:
        assert key not in out


def test_agreeing_panels_collapse_onto_the_shared_size(tmp_path):
    out = _load_v1(
        tmp_path,
        stopwatch={'fontSize': 16},
        inspect={'fontSize': 16},
    )
    assert out['panel_font_size'] == 16


def test_neither_key_lands_on_the_default(tmp_path):
    out = _load_v1(tmp_path, game_path='C:/Games/AoC')
    assert out['panel_font_size'] == 12
    assert out['game_path'] == 'C:/Games/AoC'


def test_inspect_alone_sets_the_shared_size(tmp_path):
    out = _load_v1(tmp_path, inspect={'fontSize': 20})
    assert out['panel_font_size'] == 20


def test_stopwatch_alone_leaves_the_shared_size_at_the_default(tmp_path):
    # Anchoring on max() here would silently enlarge the console and control
    # panel for a user who only ever touched the stopwatch.
    out = _load_v1(tmp_path, stopwatch={'fontSize': 24})
    assert out['panel_font_size'] == 12


def test_retired_extras_keys_are_erased_even_at_current_version(tmp_path):
    # The extras moved into the profile document; a prefs file that still
    # carries their dicts (any 2.2.x machine) loses them to strict validation
    # — clean start, no migration into the profile.
    (tmp_path / PREFS_SCHEMA.filename).write_text(
        json.dumps({
            'schema_version': 2,
            'panel_font_size': 20,
            'stopwatch': {'enabled': True, 'fontSize': 16},
            'inspect': {'enabled': True},
            'cast_timer': {'enableP': True},
        }),
        encoding='utf-8',
    )
    out = settings_core.load(PREFS_SCHEMA, tmp_path)
    assert out['panel_font_size'] == 20
    for key in RETIRED_KEYS:
        assert key not in out


def test_save_stamps_the_current_version(tmp_path):
    settings_core.save(PREFS_SCHEMA, tmp_path, _load_v1(tmp_path, inspect={'fontSize': 20}))
    stored = json.loads((tmp_path / PREFS_SCHEMA.filename).read_text(encoding='utf-8'))
    assert stored['schema_version'] == PREFS_SCHEMA.version == 2
    # A second load must not re-run the rung against the now-shared value.
    assert settings_core.load(PREFS_SCHEMA, tmp_path)['panel_font_size'] == 20
