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
    # Must match EXACTLY once: 0 = the AS2 constant was renamed; >1 = the generator's
    # re.subn would silently rewrite an unintended second site (it rewrites all matches).
    meta = dis.GLOBAL_SETTINGS[key]
    target = SRC_PKG / meta['file']
    assert target.exists(), f"{key}: missing target {meta['file']}"
    content = target.read_text(encoding='utf-8')
    n = len(re.findall(meta['pattern'], content))
    assert n == 1, (
        f"{key}: pattern {meta['pattern']!r} matched {n} sites in {meta['file']} "
        "(expected exactly 1). 0 = constant renamed; >1 = the bake would rewrite an "
        "unintended line."
    )


# The value each constant must SHIP at in the pristine (un-baked) source so that
# offset 0 == stock: GAME_DEFAULTS for offset keys, these baselines for the absolute
# keys (no GAME_DEFAULTS entry). This pins the load-bearing offset-bake invariant — the
# bake-then-read tests below can't catch a source constant drifting off its game default.
_ABSOLUTE_SHIPPED = {'shadow_mode': 2, 'shrink_start': 0, 'min_scale': 0}


@pytest.mark.parametrize("key", list(dis.GLOBAL_SETTINGS))
def test_shipped_constant_equals_game_default(key):
    meta = dis.GLOBAL_SETTINGS[key]
    content = (SRC_PKG / meta['file']).read_text(encoding='utf-8')
    shipped = re.search(meta['pattern'], content).group(2)
    expected = dis.GAME_DEFAULTS[key] if key in dis.GAME_DEFAULTS else _ABSOLUTE_SHIPPED[key]
    assert float(shipped) == float(expected), (
        f"{key}: shipped AS2 value {shipped!r} != game default {expected} — offset 0 "
        "would no longer mean 'stock'. Fix the AS2 constant or GAME_DEFAULTS."
    )


def test_shipped_shadow_blur_both_axes_are_game_default():
    # shadow_blur is dual-axis (blurX, blurY = capture groups 2 and 3); both must ship
    # at GAME_DEFAULTS['shadow_blur'] so offset 0 leaves the stock filter unchanged.
    meta = dis.GLOBAL_SETTINGS['shadow_blur']
    content = (SRC_PKG / meta['file']).read_text(encoding='utf-8')
    m = re.search(meta['pattern'], content)
    expected = str(int(dis.GAME_DEFAULTS['shadow_blur']))
    assert (m.group(2), m.group(3)) == (expected, expected)


def test_content_scale_applies_per_content_factor():
    # The pop-in/fade animation must multiply the shared scale by each content's own
    # factor, or DEFAULT_TEXT_SCALE (the "Size" slider) silently flattens out and does
    # nothing. Source-level guard for the AS2 fix.
    abstract = (SRC_PKG / "numbersTypes" / "DamageTextAbstract.as").read_text(encoding='utf-8')
    assert "this._contentScale * this._contents[_loc2_].scale" in abstract
    content = (SRC_PKG / "DamageTextContent.as").read_text(encoding='utf-8')
    assert re.search(r'function (get|set) scale', content), "DamageTextContent needs a scale accessor"


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
    assert _value(out, 'dir1_x_offset') == '-50'
    assert _value(out, 'show_duration') == '0.2'
    assert _value(out, 'text_scale') == '1'


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
    s['fixed_col_split'] = 1
    s['show_titles'] = 1
    out = _bake(tmp_path, s)
    assert _value(out, 'shadow_mode') == '0'
    assert _value(out, 'fixed_col_split') == '1'
    assert _value(out, 'show_titles') == '1'


def test_easing_type_ships_quad():
    # Easing is fixed to Quad — no setting, no bake. Guard the AS2 constant so it
    # can't silently drift to Cubic/Quart (which there'd be no UI to undo).
    content = (SRC_PKG / "numbersManagers" / "AbstractManager.as").read_text(encoding='utf-8')
    assert re.search(r'static var EASING_TYPE\s*=\s*0\b', content)


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
