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
        "x": 0,
        "y": 0,
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


def test_console_feature_compiles():
    ok, msg, _ = _compile([_grid()], include_console=True)
    assert ok, msg


def test_cast_timer_feature_compiles():
    cast = {
        "enableP": True,
        "enableT": True,
        "playerX": 900,
        "playerY": 600,
        "targetX": 900,
        "targetY": 560,
        "bold": True,
        "fontSize": 18,
        "display": "both",
        "color": "FF8800",
    }
    ok, msg, _ = _compile([_grid()], cast_config=cast)
    assert ok, msg


def test_all_features_together_compile():
    cast = {"enableP": True, "enableT": False, "playerX": 900, "playerY": 600}
    ok, msg, _ = _compile([_grid()], include_console=True, cast_config=cast)
    assert ok, msg
