"""Tests for damageinfo_settings — schema, validation, presets, I/O.

Pure-data layer (no Tk, no MTASC). Mirrors test_deeps_settings.
"""

import json
import re

import pytest

from kazbars import damageinfo_settings as dis
from kazbars.paths import ASSETS


# --------------------------------------------------------------------------- #
# Schema invariants
# --------------------------------------------------------------------------- #
def test_defaults_has_every_global_key_plus_enabled():
    d = dis.get_default_settings()
    for key in dis.GLOBAL_SETTINGS:
        assert key in d
    assert d['enabled'] is False
    # +1 non-baked key outside GLOBAL_SETTINGS: the master 'enabled' gate. (Per-source
    # colors are NOT settings — the colors panel edits TextColors.xml directly.)
    assert len(d) == len(dis.GLOBAL_SETTINGS) + 1
    assert 'source_colors' not in d


def test_default_offsets_match_schema():
    d = dis.get_default_settings()
    for key, meta in dis.GLOBAL_SETTINGS.items():
        assert d[key] == meta['default']


def test_every_global_entry_has_file_and_pattern():
    for key, meta in dis.GLOBAL_SETTINGS.items():
        assert meta['file'], key
        assert meta['pattern'], key
        assert {'min', 'max', 'step', 'default'} <= set(meta), key


def test_game_defaults_keys_are_known():
    assert set(dis.GAME_DEFAULTS) <= set(dis.GLOBAL_SETTINGS)


def test_absolute_keys_absent_from_game_defaults():
    # shadow_mode/ranged_keep are absolute (offset == value).
    for key in ('shadow_mode', 'ranged_keep'):
        assert key not in dis.GAME_DEFAULTS


def test_is_float_key():
    for key in ('show_duration', 'fade_duration'):
        assert dis.is_float_key(key)
    for key in ('dir1_x_offset', 'shadow_mode', 'fixed_col_split'):
        assert not dis.is_float_key(key)


def test_is_offset_key():
    for key in ('dir1_x_offset', 'shadow_blur', 'shadow_distance'):
        assert dis.is_offset_key(key)
    for key in ('ranged_keep', 'shadow_mode'):  # absolute → no notch
        assert not dis.is_offset_key(key)


def test_offset_sliders_are_symmetric():
    # Offset sliders centre on 0 (== the stock value) so the panel can notch the
    # midpoint. Bool/enum offset keys aren't sliders, so they're exempt.
    for key in dis.GAME_DEFAULTS:
        meta = dis.GLOBAL_SETTINGS[key]
        if meta.get('type') in ('bool', 'enum'):
            continue
        assert meta['min'] == -meta['max'], f"{key}: {meta['min']}..{meta['max']} not symmetric"


def test_xy_position_sliders_share_common_step():
    # The X/Y position sliders all snap on one common step (10px).
    xy_keys = (
        'dir1_x_offset', 'dir1_y_offset', 'fixed_col_x', 'fixed_col_y',
        'col_b_x', 'col_b_y', 'fixed_x_base', 'fixed_y_base',
    )
    for key in xy_keys:
        assert dis.GLOBAL_SETTINGS[key]['step'] == 10, key


def test_spread_spacing_options():
    names = [n for n, _ in dis.SPREAD_SPACING_OPTIONS]
    assert names == ['Compact', 'Default', 'Extended']
    by_name = dict(dis.SPREAD_SPACING_OPTIONS)
    assert by_name['Compact'] == {'fixed_x_offset': -100, 'fixed_y_spacing': -20}
    assert by_name['Default'] == {'fixed_x_offset': 0, 'fixed_y_spacing': 0}
    assert by_name['Extended'] == {'fixed_x_offset': 100, 'fixed_y_spacing': 20}


def test_spread_spacing_option_lookup():
    s = dis.get_default_settings()
    assert dis.spread_spacing_option(s) == 'Default'          # defaults are 0/0
    s['fixed_x_offset'], s['fixed_y_spacing'] = -100, -20
    assert dis.spread_spacing_option(s) == 'Compact'
    s['fixed_x_offset'], s['fixed_y_spacing'] = 100, 20
    assert dis.spread_spacing_option(s) == 'Extended'
    s['fixed_x_offset'] = 33                                  # no match → Default
    assert dis.spread_spacing_option(s) == 'Default'


def test_vertical_position_sliders_are_inverted():
    # 'invert' reverses the slider so dragging right moves the number UP. Exactly the
    # vertical-position keys carry it; horizontal/spread/spacing stay normal.
    inverted = {k for k, m in dis.GLOBAL_SETTINGS.items() if m.get('invert')}
    assert inverted == {'dir1_y_offset', 'fixed_col_y', 'col_b_y', 'fixed_y_base'}
    # Inverted sliders stay symmetric so the centre notch still marks the default.
    for k in inverted:
        m = dis.GLOBAL_SETTINGS[k]
        assert m['min'] == -m['max']


def test_relative_readout_keys():
    # The position-card px sliders read as a relative shift; only those carry 'relative'.
    relative = {k for k, m in dis.GLOBAL_SETTINGS.items() if m.get('relative')}
    assert relative == {
        'dir1_x_offset', 'dir1_y_offset', 'fixed_col_x', 'fixed_col_y',
        'col_b_x', 'col_b_y', 'fixed_x_base', 'fixed_y_base',
    }
    # Every inverted key is also relative (the inverse needn't hold — the X positions
    # are relative but not inverted).
    inverted = {k for k, m in dis.GLOBAL_SETTINGS.items() if m.get('invert')}
    assert inverted <= relative


# --------------------------------------------------------------------------- #
# readout (UI label)
# --------------------------------------------------------------------------- #
def test_readout_relative_signed_shift():
    # 0 = default (midpoint); right-drag reads '+', left reads '-'.
    assert dis.readout('dir1_x_offset', 0) == '0px'
    assert dis.readout('dir1_x_offset', 30) == '+30px'
    assert dis.readout('dir1_x_offset', -30) == '-30px'


def test_readout_inverted_keeps_right_positive():
    # Vertical sliders store a right-drag as a negative offset; the label flips the
    # sign so dragging right still reads '+'.
    assert dis.readout('fixed_col_y', 0) == '0px'
    assert dis.readout('fixed_col_y', -30) == '+30px'
    assert dis.readout('fixed_col_y', 30) == '-30px'


def test_readout_absolute_keys_show_game_value():
    # Non-position sliders keep showing the resulting game value, not a shift.
    assert dis.readout('shadow_distance', 0) == '4px'
    assert dis.readout('show_duration', 0) == '0.2s'
    assert dis.readout('show_duration', -0.1) == '0.1s'


# --------------------------------------------------------------------------- #
# validate_setting
# --------------------------------------------------------------------------- #
def test_validate_clamps_int_offset_to_range():
    assert dis.validate_setting('dir1_x_offset', 99999) == 200   # max
    assert dis.validate_setting('dir1_x_offset', -99999) == -200  # min
    assert dis.validate_setting('dir1_x_offset', 30) == 30


def test_validate_clamps_float_offset_and_keeps_float():
    v = dis.validate_setting('show_duration', 5.0)
    assert v == pytest.approx(0.2)
    assert isinstance(v, float)
    v2 = dis.validate_setting('show_duration', -5.0)
    assert v2 == pytest.approx(-0.2)


def test_validate_int_keys_return_int():
    v = dis.validate_setting('dir1_x_offset', 30.0)
    assert v == 30 and isinstance(v, int)


def test_validate_enum_clamped():
    assert dis.validate_setting('shadow_mode', 5) == 2
    assert dis.validate_setting('shadow_mode', -3) == 0


def test_validate_bool_master():
    assert dis.validate_setting('enabled', 1) is True
    assert dis.validate_setting('enabled', 0) is False
    assert dis.validate_setting('enabled', '') is False


def test_validate_garbage_falls_back_to_default():
    assert dis.validate_setting('dir1_x_offset', 'nonsense') == 0
    assert dis.validate_setting('show_duration', None) == 0


def test_validate_unknown_key_passthrough():
    assert dis.validate_setting('not_a_key', 'whatever') == 'whatever'


# --------------------------------------------------------------------------- #
# validate_all_settings
# --------------------------------------------------------------------------- #
def test_validate_all_drops_unknown_and_fills_missing():
    out = dis.validate_all_settings({'dir1_x_offset': 20, 'bogus': 7})
    assert out['dir1_x_offset'] == 20
    assert 'bogus' not in out
    assert out['enabled'] is False
    assert out['shadow_mode'] == 2  # filled from default


def test_validate_all_clamps_each():
    out = dis.validate_all_settings({'dir1_x_offset': 99999, 'shadow_blur': -999})
    assert out['dir1_x_offset'] == 200
    assert out['shadow_blur'] == -3


# --------------------------------------------------------------------------- #
# compute_final_value
# --------------------------------------------------------------------------- #
def test_compute_final_offset_keys():
    assert dis.compute_final_value('shadow_distance', 0) == 4
    assert dis.compute_final_value('shadow_distance', 2) == 6
    assert dis.compute_final_value('dir1_x_offset', 0) == -50  # 50px left of head, + = right


def test_compute_final_absolute_keys():
    assert dis.compute_final_value('shadow_mode', 1) == 1
    assert dis.compute_final_value('ranged_keep', 0) == 0
    assert dis.compute_final_value('ranged_keep', 1) == 1


def test_compute_final_float_keys():
    assert dis.compute_final_value('show_duration', 0) == pytest.approx(0.2)
    assert dis.compute_final_value('show_duration', -0.1) == pytest.approx(0.1)
    assert isinstance(dis.compute_final_value('fade_duration', 0.05), float)


# --------------------------------------------------------------------------- #
# presets
# --------------------------------------------------------------------------- #
def test_apply_preset_default():
    out = dis.apply_preset(dis.get_default_settings(), 'Default')
    assert out['shadow_mode'] == 2
    # 0.2s in / 0.2s out (offset 0 over the 0.2 game default)
    assert out['show_duration'] == 0
    assert out['fade_duration'] == 0


def test_apply_preset_performance():
    out = dis.apply_preset(dis.get_default_settings(), 'Performance')
    assert out['shadow_mode'] == 1
    # 0.1s in / 0.1s out
    assert out['show_duration'] == pytest.approx(-0.1)
    assert out['fade_duration'] == pytest.approx(-0.1)


def test_only_default_and_performance_presets():
    assert set(dis.PRESETS) == {'Default', 'Performance'}


def test_apply_preset_unknown_is_noop():
    base = dis.get_default_settings()
    base['dir1_x_offset'] = 30
    out = dis.apply_preset(base, 'NopeNotReal')
    assert out['dir1_x_offset'] == 30
    assert out == dis.validate_all_settings(base)


def test_apply_preset_preserves_unrelated_keys():
    base = dis.get_default_settings()
    base['enabled'] = True
    base['dir1_x_offset'] = 40
    out = dis.apply_preset(base, 'Performance')
    assert out['enabled'] is True
    assert out['dir1_x_offset'] == 40  # not part of any preset bundle


# --------------------------------------------------------------------------- #
# file I/O
# --------------------------------------------------------------------------- #
def test_save_load_round_trip(tmp_path):
    s = dis.get_default_settings()
    s['enabled'] = True
    s['ranged_keep'] = 1  # on (default is off) — round-trips a changed bool
    s['shadow_mode'] = 1
    assert dis.save_settings(tmp_path, s)
    loaded = dis.load_settings(tmp_path)
    assert loaded['enabled'] is True
    assert loaded['ranged_keep'] == 1
    assert loaded['shadow_mode'] == 1


def test_load_missing_returns_defaults(tmp_path):
    assert dis.load_settings(tmp_path) == dis.get_default_settings()


def test_load_corrupt_returns_defaults(tmp_path):
    (tmp_path / dis.SETTINGS_FILENAME).write_text('{not json', encoding='utf-8')
    assert dis.load_settings(tmp_path) == dis.get_default_settings()


def test_load_partial_fills_defaults(tmp_path):
    (tmp_path / dis.SETTINGS_FILENAME).write_text(
        json.dumps({'enabled': True, 'ranged_keep': 1}), encoding='utf-8')
    loaded = dis.load_settings(tmp_path)
    assert loaded['enabled'] is True
    assert loaded['ranged_keep'] == 1
    assert loaded['shadow_mode'] == 2  # filled


def test_save_validates_out_of_range(tmp_path):
    s = dis.get_default_settings()
    s['dir1_x_offset'] = 99999  # out of range
    dis.save_settings(tmp_path, s)
    on_disk = json.loads((tmp_path / dis.SETTINGS_FILENAME).read_text(encoding='utf-8'))
    assert on_disk['dir1_x_offset'] == 200  # clamped before write


# --------------------------------------------------------------------------- #
# per-source colors (TextColors.xml) — catalog + validation
# --------------------------------------------------------------------------- #
def test_source_catalog_matches_engine():
    # The color catalog must list exactly the flytext types the SWF parses, or a swatch
    # would target a non-existent TextColors entry (or a real type would be uneditable).
    src = (ASSETS / 'damageinfo' / 'src' / '__Packages' / 'helpers'
           / 'NumbersFontsCollection.as').read_text(encoding='utf-8')
    engine = set(re.findall(r'htmlFontParser\("([^"]+)"\)', src))
    assert engine == set(dis.ALL_SOURCE_NAMES)


def test_source_catalog_no_duplicates():
    names = []
    for _title, self_rows, other_rows in dis.PAIRED_GROUPS:
        names += [n for n, _ in self_rows] + [n for n, _ in other_rows]
    names += [n for n, _ in dis.SHARED_SOURCES]
    assert len(names) == len(set(names)) == len(dis.ALL_SOURCE_NAMES)


def test_incoming_damage_types_match_self_catalog():
    # buff_xml's "Split into two columns" target list must equal the self side of the
    # color catalog's paired groups (and be valid source names), or split would flip the
    # wrong / non-existent flytext directions.
    from kazbars import buff_xml
    self_side = []
    for _title, self_rows, _other in dis.PAIRED_GROUPS:
        self_side += [n for n, _ in self_rows]
    assert set(buff_xml.INCOMING_DAMAGE_TYPES) == set(self_side)
    assert set(buff_xml.INCOMING_DAMAGE_TYPES) <= set(dis.ALL_SOURCE_NAMES)


def test_normalize_color():
    assert dis.normalize_color('#ABCDEF') == 'ABCDEF'
    assert dis.normalize_color('0xabcdef') == 'ABCDEF'
    assert dis.normalize_color('abcdef') == 'ABCDEF'
    assert dis.normalize_color('12345') is None    # too short
    assert dis.normalize_color('GGGGGG') is None   # non-hex
    assert dis.normalize_color(123) is None         # non-str


def test_source_colors_not_persisted(tmp_path):
    # Colors are no longer a setting — an unknown 'source_colors' key is dropped on write
    # (the colors panel edits TextColors.xml directly instead).
    s = dis.get_default_settings()
    s['source_colors'] = {'self_attacked': 'FF0000'}  # legacy key from an old install
    assert dis.save_settings(tmp_path, s)
    on_disk = json.loads((tmp_path / dis.SETTINGS_FILENAME).read_text(encoding='utf-8'))
    assert 'source_colors' not in on_disk
    assert 'source_colors' not in dis.load_settings(tmp_path)


def test_save_settings_validates_and_clamps(tmp_path):
    s = dis.get_default_settings()
    s['dir1_x_offset'] = 99999  # out of range
    dis.save_settings(tmp_path, s)
    on_disk = json.loads((tmp_path / dis.SETTINGS_FILENAME).read_text(encoding='utf-8'))
    assert on_disk['dir1_x_offset'] == 200  # clamped before write
