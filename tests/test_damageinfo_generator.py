"""Tests for damageinfo_generator — bake correctness + regex↔AS2 coupling.

No MTASC here (the compile is covered by a separate gated integration check). These
run anywhere: they assert every bake-map pattern still matches the shipped AS2 source
(so an AS2 constant rename fails CI, not silently in-game) and that offsets bake to the
expected final values.
"""

import re

import pytest

from kazbars import damageinfo_generator as dig
from kazbars import damageinfo_settings as dis
from kazbars.paths import ASSETS

SRC_PKG = ASSETS / "damageinfo" / "src" / "__Packages"


# --------------------------------------------------------------------------- #
# Shipped assets present
# --------------------------------------------------------------------------- #
def test_pristine_swf_and_source_present():
    assert (ASSETS / "damageinfo" / "DamageInfo.swf").exists()
    assert SRC_PKG.is_dir()


def test_entry_points_exist():
    for entry in dig.ENTRY_POINTS:
        assert (SRC_PKG / entry).exists(), entry


# --------------------------------------------------------------------------- #
# Regex ↔ AS2 constant coupling (the guard that catches a rename)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", list(dis.GLOBAL_SETTINGS))
def test_every_bake_pattern_matches_shipped_source(key):
    meta = dis.GLOBAL_SETTINGS[key]
    target = SRC_PKG / meta['file']
    assert target.exists(), f"{key}: missing target {meta['file']}"
    content = target.read_text(encoding='utf-8')
    assert re.search(meta['pattern'], content), (
        f"{key}: pattern {meta['pattern']!r} matched nothing in {meta['file']} — "
        "the AS2 constant was likely renamed."
    )


# --------------------------------------------------------------------------- #
# Bake correctness (no MTASC)
# --------------------------------------------------------------------------- #
def _bake(tmp_path, settings):
    out = tmp_path / "__Packages"
    assert dig.DamageInfoGenerator(SRC_PKG, settings).generate(out)
    return out


def _value(out, key):
    """Re-read the baked value (capture group 2) of a single key's constant."""
    meta = dis.GLOBAL_SETTINGS[key]
    content = (out / meta['file']).read_text(encoding='utf-8')
    return re.search(meta['pattern'], content).group(2)


def test_defaults_bake_to_game_defaults(tmp_path):
    out = _bake(tmp_path, dis.get_default_settings())
    assert _value(out, 'distance_falloff') == '60'
    assert _value(out, 'shrink_start') == '0'
    assert _value(out, 'min_scale') == '0'
    assert _value(out, 'shadow_mode') == '2'
    assert _value(out, 'dir1_x_offset') == '50'
    assert _value(out, 'show_duration') == '0.2'
    assert _value(out, 'title_scale') == '0.7'


def test_offset_bakes_to_final_value(tmp_path):
    s = dis.get_default_settings()
    s['distance_falloff'] = 10   # 60 + 10
    s['shrink_start'] = 15       # absolute
    s['dir1_y_offset'] = -50
    out = _bake(tmp_path, s)
    assert _value(out, 'distance_falloff') == '70'
    assert _value(out, 'shrink_start') == '15'
    assert _value(out, 'dir1_y_offset') == '-50'


def test_float_offset_formats_cleanly(tmp_path):
    s = dis.get_default_settings()
    s['show_duration'] = -0.1   # 0.2 - 0.1 = 0.1
    out = _bake(tmp_path, s)
    assert _value(out, 'show_duration') == '0.1'


def test_enum_and_bool_bake(tmp_path):
    s = dis.get_default_settings()
    s['shadow_mode'] = 0
    s['easing_type'] = 2
    s['fixed_col_split'] = 1
    s['show_titles'] = 1
    out = _bake(tmp_path, s)
    assert _value(out, 'shadow_mode') == '0'
    assert _value(out, 'easing_type') == '2'
    assert _value(out, 'fixed_col_split') == '1'
    assert _value(out, 'show_titles') == '1'


def test_shadow_blur_dual_axis(tmp_path):
    s = dis.get_default_settings()
    s['shadow_blur'] = 2      # 3 + 2 = 5 for BOTH blurX and blurY
    s['shadow_distance'] = 2  # 4 + 2 = 6 for arg 1
    out = _bake(tmp_path, s)
    content = (out / "numbersTypes" / "DamageTextAbstract.as").read_text(encoding='utf-8')
    assert "DropShadowFilter(6,45,0,100,5,5," in content


def test_generate_fails_loudly_on_drifted_source(tmp_path):
    # A renamed AS2 constant (bake pattern matches nothing) must FAIL the build, not
    # silently ship the stock value. Guards the runtime hard-fail behavior.
    import shutil
    drifted = tmp_path / "src"
    shutil.copytree(SRC_PKG, drifted)
    dnm = drifted / "DamageNumberManager.as"
    dnm.write_text(
        dnm.read_text(encoding='utf-8').replace("SHRINK_START", "SHRINK_BEGIN"),
        encoding='utf-8',
    )
    out = tmp_path / "__Packages"
    assert dig.DamageInfoGenerator(drifted, dis.get_default_settings()).generate(out) is False


def test_bake_leaves_untouched_constants_alone(tmp_path):
    # A bake of only distance_falloff must not perturb other constants in the same file.
    s = dis.get_default_settings()
    s['distance_falloff'] = 20
    out = _bake(tmp_path, s)
    assert _value(out, 'shrink_start') == '0'
    assert _value(out, 'min_scale') == '0'
    assert _value(out, 'show_titles') == '0'
