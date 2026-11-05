"""Compile-integration test for the AS2 code generator.

The strongest form of the codegen test: run the *whole* generated source
through the AS2 compiler and assert success. It is the single check that
bridges Python-side correctness to SWF-side correctness — a unit test on the
emitted strings can't catch AS2 the compiler rejects — and the gate on the
compiler's 32 KB-per-class bytecode cap (no class may come near it).

Compiling costs about a second, so every build here is made once per module
(`builds`) and every test reads one: the worst case (every module on, every
grid whitelisting the whole catalog, grid ids that need escaping, sanitize the
same way or are not ASCII) and the empty build (no grid, nothing on). The one
extra compile is the chunking's negative control.

Run: `pytest tests/test_build_compile.py` (from repo root).
"""

import tempfile
import warnings
from pathlib import Path

import pytest

from as2c.swf import TAG_DO_INIT_ACTION, Movie
from kazbars import grids_generator
from kazbars.buff_database import BuffDatabase
from kazbars.grid_model import create_default_grid, validate_grid
from kazbars.grids_generator import build_grids
from kazbars.paths import KAZBARS_ASSETS

_BASE_SWF = KAZBARS_ASSETS / "base.swf"
# The compiler's per-class cap is 32 KB; a class past the warning line is a
# sign the next feature needs a split.
CLASS_CAP = 32_000
CLASS_WARN = 30_000


def _db():
    db = BuffDatabase()
    db.load(KAZBARS_ASSETS / "Database.json")
    return db


def _grid(grid_id, **kw):
    return validate_grid({**create_default_grid(grid_id=grid_id, rows=1, cols=2), **kw})


def _compile(grids, **kwargs):
    out = Path(tempfile.mkdtemp(prefix="kazbars_test_")) / "KazBars.swf"
    ok, msg = build_grids(
        grids, _db(),
        str(_BASE_SWF), str(KAZBARS_ASSETS / "stubs"),
        str(out),
        "0.0.0",
        assets_path=KAZBARS_ASSETS.parent,
        **kwargs,
    )
    return ok, msg, out


def _worst_case():
    """The most the generator can be handed: eight dynamic grids each
    whitelisting the whole catalog (the per-grid slot cap bounds slots, not the
    ids a grid references), a static grid, ids that need escaping or collide
    once sanitized, and every module on."""
    every_primary = [b["ids"][0] for b in _db().buffs]
    grids = [_grid(f"All {k}", cols=8, whitelist=every_primary) for k in range(8)]
    grids += [
        _grid("Static", slotMode="static", slotAssignments={"0": [222609], "1": 4281285}),
        _grid('My"Grid\n\\evil', whitelist=[222609]),
        _grid("Grid ünïcodé 日本", whitelist=[222609]),
        _grid("a-b", whitelist=[222609], timerStyle="bar"),
        _grid("a b", whitelist=[222609], selfCastOnly=True),
    ]
    extras = dict(
        cast_config={"enabled": True, "enableP": True, "enableT": True, "scale": 200},
        stopwatch_config={"enabled": True, "scale": 200},
        inspect_config={"enabled": True, "scale": 200},
        overlay={"size": 24, "font": "Arial"},
    )
    return grids, extras


@pytest.fixture(scope="module")
def builds():
    out = {}
    grids, extras = _worst_case()
    out["full"] = _compile(grids, **extras)
    out["empty"] = _compile([])
    return out


def _class_sizes(swf_path):
    """Every compiled class's DoInitAction bytecode size, by class name."""
    movie = Movie.load(swf_path)
    names = {cid: name for name, cid in movie.class_exports().items()}
    return {names.get(t.sprite_id(), f"#{t.sprite_id()}"): len(t.actions())
            for t in movie.find_tags(TAG_DO_INIT_ACTION)}


@pytest.mark.parametrize("name", ["full", "empty"])
def test_the_build_compiles(builds, name):
    ok, msg, out = builds[name]
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_every_module_class_is_in_the_full_build(builds):
    sizes = _class_sizes(builds["full"][2])
    for cls in ("KazBars", "KazBarsData", "KazBarsData1", "KazBarsGrids", "KazBarsGridView",
                "KazBarsWorld", "KazBarsClock", "KazBarsCastTimer", "KazBarsStopwatch",
                "KazBarsInspect", "KazBarsPreviewPanel"):
        assert cls in sizes, cls
    for cls in ("KazBarsConsole", "KazBarsOnslaught", "KazBarsOverhead"):
        assert cls not in sizes, f"{cls} is gated off"


def test_the_empty_build_carries_no_module_but_the_grids_and_the_panel(builds):
    sizes = _class_sizes(builds["empty"][2])
    for cls in ("KazBarsCastTimer", "KazBarsStopwatch", "KazBarsInspect", "KazBarsConsole",
                "KazBarsOnslaught", "KazBarsOverhead"):
        assert cls not in sizes, cls
    assert "KazBarsPreviewPanel" in sizes and "KazBarsGrids" in sizes


@pytest.mark.parametrize("name", ["full", "empty"])
def test_every_class_stays_under_the_bytecode_cap(builds, name):
    sizes = _class_sizes(builds[name][2])
    over = {cls: n for cls, n in sizes.items() if n >= CLASS_CAP}
    assert not over, over
    near = {cls: n for cls, n in sizes.items() if n >= CLASS_WARN}
    if near:
        warnings.warn(f"classes within {CLASS_CAP - CLASS_WARN} B of the cap: {near}", stacklevel=1)


def test_the_worst_case_fails_without_the_chunking(monkeypatch):
    # Negative control: lift the budget to four grids a class and the data
    # lands in classes the compiler rejects — the full build above is proving
    # the packing, not the compiler's leniency.
    monkeypatch.setattr(grids_generator, "DATA_CHUNK_BUDGET", 70_000)
    grids, extras = _worst_case()
    ok, msg, _ = _compile(grids, **extras)
    assert not ok and "32K" in msg, msg
