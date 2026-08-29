"""MTASC compile-integration test for the AS2 code generator.

The strongest form of the codegen test: run the *whole* generated source
through the bundled `mtasc.exe` and assert exit-0. It is the single check that
bridges Python-side correctness to SWF-side correctness — a unit test on the
emitted strings can't catch AS2 the compiler rejects.

Crucially it pins the §6 escaping fix: a grid `id` containing a quote, a
newline, and a backslash must still produce a SWF MTASC accepts, proving
`escape_as2_string` keeps the emitted string literal well-formed.

Windows + bundled-compiler gated (mirrors test_deeps_meter's win32 guard) so
the suite stays green on a CI image or dev box without the MTASC payload. CI
runs windows-latest with the compiler bundled, so it executes there.

Run: `pytest tests/test_build_compile.py` (from repo root).
"""

import sys
import tempfile
from pathlib import Path

import pytest

from kazbars import grids_generator
from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import build_grids
from kazbars.paths import COMPILER_ASSETS, KAZBARS_ASSETS

_COMPILER = COMPILER_ASSETS / "mtasc.exe"
_BASE_SWF = KAZBARS_ASSETS / "base.swf"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not _COMPILER.exists() or not _BASE_SWF.exists(),
    reason="needs Windows + the bundled mtasc.exe and base.swf",
)


def _db():
    db = BuffDatabase()
    db.load(KAZBARS_ASSETS / "Database.json")
    return db


def _grid(grid_id="G"):
    return {
        "id": grid_id,
        "enabled": True,
        "type": "player",
        "rows": 1,
        "cols": 2,
        "iconSize": 32,
        "gap": 0,
        "fx": 0.0,
        "fy": 0.0,
        "slotMode": "dynamic",
        "showTimers": True,
        "timerFontSize": 12,
        "timerFlashThreshold": 5,
        "timerYOffset": 0,
        "stackFontSize": 10,
        "enableFlashing": True,
        "fillDirection": "LR",
        "sortOrder": "longest",
        "layout": "buffFirst",
        "whitelist": [],
    }


def _compile(grids, **kwargs):
    out = Path(tempfile.mkdtemp(prefix="kazbars_test_")) / "KazBars.swf"
    ok, msg = build_grids(
        grids, _db(),
        str(_BASE_SWF), str(KAZBARS_ASSETS / "stubs"),
        str(out), str(_COMPILER),
        "0.0.0",
        assets_path=KAZBARS_ASSETS.parent,
        **kwargs,
    )
    return ok, msg, out


def test_minimal_grid_compiles_to_swf():
    ok, msg, out = _compile([_grid()])
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_grid_id_with_quote_newline_backslash_still_compiles():
    # Without escape_as2_string this emits a broken string literal and MTASC
    # fails — so this is the regression guard for the §6 fix end-to-end.
    ok, msg, _ = _compile([_grid('My"Grid\n\\evil')])
    assert ok, msg


def test_non_ascii_grid_name_still_compiles():
    # Without the isascii() guard, sanitize_id lets non-ASCII letters (e.g.
    # CJK) through into the AS2 identifier and MTASC rejects it.
    ok, msg, _ = _compile([_grid("Grid ünïcodé 日本")])
    assert ok, msg


def test_grids_with_colliding_sanitized_ids_both_compile():
    # "a-b" and "a b" sanitize to the same identifier stem; the archive key
    # must be deduped ("a_b", "a_b_2") rather than emitted twice.
    ok, msg, _ = _compile([_grid("a-b"), _grid("a b")])
    assert ok, msg


def test_zero_grids_compiles():
    ok, msg, _ = _compile([])
    assert ok, msg


def test_zero_grids_with_an_extra_enabled_compiles():
    ok, msg, _ = _compile([], stopwatch_config={"enabled": True})
    assert ok, msg


def test_all_grids_disabled_compiles():
    ok, msg, _ = _compile([dict(_grid(), enabled=False)])
    assert ok, msg


def test_console_feature_compiles():
    ok, msg, _ = _compile([_grid()], include_console=True)
    assert ok, msg


def test_cast_timer_feature_compiles():
    cast = {
        "enabled": True,
        "enableP": True,
        "enableT": True,
        "playerFx": 900 / 1920,
        "playerFy": 600 / 1080,
        "targetFx": 900 / 1920,
        "targetFy": 560 / 1080,
        "bold": True,
        "fontSize": 18,
        "display": "both",
        "color": "FF8800",
    }
    ok, msg, _ = _compile([_grid()], cast_config=cast)
    assert ok, msg


def test_stopwatch_feature_compiles():
    sw = {"enabled": True, "fx": 850 / 1920, "fy": 300 / 1080, "startCollapsed": True}
    ok, msg, _ = _compile([_grid()], stopwatch_config=sw)
    assert ok, msg


def test_inspect_feature_compiles():
    # Doubles as the 32 KB-bytecode canary for the single-class stub: MTASC
    # hard-fails a class over the limit, so exit-0 here proves headroom.
    ins = {"enabled": True, "fx": 40 / 1920, "fy": 240 / 1080, "fontSize": 12,
           "startCollapsed": True}
    ok, msg, _ = _compile([_grid()], inspect_config=ins)
    assert ok, msg


def test_shared_panel_font_at_a_non_default_size_compiles():
    # d.PF is emitted into every build and both stubs now resolve their whole
    # layout from it, so a non-12 size has to reach MTASC intact — including the
    # log-entry font tag, whose size is spliced into an AS2 string literal.
    ok, msg, _ = _compile(
        [_grid()],
        include_console=True,
        stopwatch_config={"enabled": True, "fontSize": None},
        inspect_config={"enabled": True, "fontSize": 30},
        panel_font_size=20,
    )
    assert ok, msg


def test_all_features_together_compile():
    cast = {"enabled": True, "enableP": True, "enableT": False,
            "playerFx": 900 / 1920, "playerFy": 600 / 1080}
    sw = {"enabled": True}
    ins = {"enabled": True}
    ok, msg, _ = _compile([_grid()], include_console=True, cast_config=cast,
                          stopwatch_config=sw, inspect_config=ins)
    assert ok, msg


def _worst_case():
    # The 64-slot cap bounds grids and slots, not the buff ids a profile
    # references: eight dynamic 1x8 grids each whitelisting the whole catalog
    # is the most data the generator can be handed, with every extra on so
    # the main class is at its largest too.
    every_primary = [b["ids"][0] for b in _db().buffs]
    grids = [dict(_grid(f"All {k}"), cols=8, whitelist=every_primary) for k in range(8)]
    cast = {"enabled": True, "enableP": True, "enableT": True,
            "playerFx": 900 / 1920, "playerFy": 600 / 1080}
    return grids, dict(include_console=True, cast_config=cast,
                       stopwatch_config={"enabled": True}, inspect_config={"enabled": True})


def test_worst_case_profile_compiles():
    # Only compiles because the data is packed into KazBarsData1..N under
    # MTASC's 32 KB-per-class bytecode cap; a catalog grown by OTA moves the
    # chunk count, not the outcome.
    grids, extras = _worst_case()
    ok, msg, _ = _compile(grids, **extras)
    assert ok, msg


def test_worst_case_profile_fails_without_the_chunking(monkeypatch):
    # Negative control: lift the budget past the data's size and everything
    # lands in one class MTASC rejects — the positive case above is proving
    # the packing, not the compiler's leniency.
    monkeypatch.setattr(grids_generator, "DATA_CHUNK_BUDGET", 70_000)
    grids, extras = _worst_case()
    ok, msg, _ = _compile(grids, **extras)
    assert not ok and "32K" in msg, msg
