"""Tests for the document schema 1 → 2 rung: grid positions move from absolute
pixels (anchored to `authored_at`) to fractions of the game resolution.

The rung is frozen history inside `profile_document` (deliberately inline, no
grid_model dependency), runs inside `validate_document`, and must never mutate
the caller's raw dict. Pixel↔fraction math itself is pinned in
test_grid_model; emit-time projection in test_grids_generator.

Run: `pytest tests/test_projection.py` (from repo root).
"""

import copy

from kazbars import grid_model
from kazbars.profile_document import (
    DOC_SCHEMA_VERSION,
    SectionRegistry,
    validate_document,
)


def _registry():
    reg = SectionRegistry()
    reg.register(grid_model.PROFILE_SECTION)
    return reg


def _schema1_doc(**overrides):
    base = {
        "schema": 1,
        "id": "a3f81c2e",
        "name": "Old Setup",
        "authored_at": [2560, 1440],
        "modules": {"grids": {"grids": [
            {"id": "G1", "x": 1280, "y": 1224, "whitelist": [1]},
            {"id": "G2", "x": 640, "y": 720},
        ]}},
    }
    base.update(overrides)
    return base


def test_rung_converts_px_to_fractions_via_authored_at():
    out = validate_document(_registry(), _schema1_doc())
    assert out["schema"] == DOC_SCHEMA_VERSION
    g1, g2 = out["modules"]["grids"]["grids"]
    assert (g1["fx"], g1["fy"]) == (0.5, 0.85)
    assert (g2["fx"], g2["fy"]) == (0.25, 0.5)
    assert "x" not in g1 and "y" not in g1
    assert g1["whitelist"] == [1]  # payload beyond positions survives


def test_rung_falls_back_to_default_resolution():
    out = validate_document(_registry(), _schema1_doc(authored_at="junk"))
    g1 = out["modules"]["grids"]["grids"][0]
    assert g1["fx"] == 1280 / 1920
    assert g1["fy"] == 1.0  # 1224/1080 overshoots → clamped


def test_rung_coerces_junk_px_to_grid_defaults():
    doc = _schema1_doc()
    doc["modules"]["grids"]["grids"][0].update(x="abc", y=None)
    g1 = validate_document(_registry(), doc)["modules"]["grids"]["grids"][0]
    assert g1["fx"] == 100 / 2560
    assert g1["fy"] == 400 / 1440


def test_rung_survives_non_dict_modules():
    # The boundary promises DocumentError or a valid doc — never a raw
    # AttributeError (profile_library skips on DocumentError alone, so an
    # escape here breaks list_profiles / startup / import).
    for bad in (None, [], "hello", 42):
        out = validate_document(_registry(), _schema1_doc(modules=bad))
        assert out["schema"] == DOC_SCHEMA_VERSION
        assert out["modules"]["grids"] == grid_model.PROFILE_SECTION.defaults()


def test_rung_never_mutates_input():
    raw = _schema1_doc()
    snapshot = copy.deepcopy(raw)
    validate_document(_registry(), raw)
    assert raw == snapshot


def test_current_schema_docs_skip_the_rung():
    doc = _schema1_doc(schema=DOC_SCHEMA_VERSION)
    doc["modules"]["grids"]["grids"] = [{"id": "G1", "fx": 0.25, "fy": 0.75}]
    g1 = validate_document(_registry(), doc)["modules"]["grids"]["grids"][0]
    assert (g1["fx"], g1["fy"]) == (0.25, 0.75)
