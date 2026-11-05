"""The PREFS_SCHEMA v1 → v2 rung: per-panel font sizes become one shared size.

v1 gave the stopwatch and the inspect panel a `fontSize` each and left the buff
console and preview control panel frozen at 12. v2 added a flat
`panel_font_size` that all four followed, anchored on Inspect, not on `max()`.

Since then the stopwatch/inspect/cast_timer configs moved into the profile
document, and `panel_font_size` itself retired for the profile's overlay size,
so strict validation now erases everything the rung writes. The rung stays as
frozen history: these tests pin its body directly, and pin that a load — at
either version — leaves none of the retired keys behind. The load tests go
through `settings_core.load`: the ladder runs on the raw dict *before*
`validate_all`, and that ordering is the thing that has to hold.
"""

import json

from kazbars import settings_core
from kazbars.prefs import PREFS_SCHEMA, _upgrade_panel_font

RETIRED_KEYS = ("stopwatch", "inspect", "cast_timer", "panel_font_size", "build_console")


def _load(tmp_path, version, **keys):
    (tmp_path / PREFS_SCHEMA.filename).write_text(
        json.dumps({'schema_version': version, **keys}), encoding='utf-8'
    )
    return settings_core.load(PREFS_SCHEMA, tmp_path)


def test_the_rung_anchors_the_shared_size_on_inspect():
    out = _upgrade_panel_font({'stopwatch': {'fontSize': 16}, 'inspect': {'fontSize': 12}})
    assert out['panel_font_size'] == 12
    assert out['inspect']['fontSize'] is None
    assert out['stopwatch']['fontSize'] == 16
    assert _upgrade_panel_font({'stopwatch': {'fontSize': 16},
                                'inspect': {'fontSize': 16}})['stopwatch']['fontSize'] is None


def test_the_rung_ignores_a_lone_stopwatch():
    # Anchoring on max() would silently enlarge the console and control panel
    # for a user who only ever touched the stopwatch.
    assert _upgrade_panel_font({'stopwatch': {'fontSize': 24}})['panel_font_size'] == 12
    assert _upgrade_panel_font({})['panel_font_size'] == 12


def test_a_v1_load_keeps_live_keys_and_erases_the_retired_ones(tmp_path):
    out = _load(tmp_path, 1, game_path='C:/Games/AoC',
                stopwatch={'enabled': True, 'fontSize': 16}, inspect={'fontSize': 20})
    assert out['game_path'] == 'C:/Games/AoC'
    for key in RETIRED_KEYS:
        assert key not in out


def test_retired_keys_are_erased_even_at_current_version(tmp_path):
    # A prefs file from an app that still had them loses them to strict
    # validation — clean start, no migration into the profile.
    out = _load(tmp_path, 2, panel_font_size=20, build_console=True,
                stopwatch={'enabled': True}, cast_timer={'enableP': True})
    for key in RETIRED_KEYS:
        assert key not in out


def test_save_stamps_the_current_version(tmp_path):
    settings_core.save(PREFS_SCHEMA, tmp_path, _load(tmp_path, 1, inspect={'fontSize': 20}))
    stored = json.loads((tmp_path / PREFS_SCHEMA.filename).read_text(encoding='utf-8'))
    assert stored['schema_version'] == PREFS_SCHEMA.version == 2
    assert 'panel_font_size' not in stored
