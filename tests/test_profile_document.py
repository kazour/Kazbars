"""Tests for `profile_document` — the profile document model and its single
validation boundary.

`validate_document` is the only gate between raw bytes and a trusted document
(library load, import, and migration share it), so this suite pins the
rejection messages (old format / too new / damaged), the strict-inside vs
preserve-unknown section policy, sparse-section semantics, and that the gate
never mutates its input.

Run: `pytest tests/test_profile_document.py` (from repo root).
"""

import pytest

from kazbars.profile_document import (
    DOC_SCHEMA_VERSION,
    LANE_BUILD,
    LANE_LIVE,
    LANE_PATCH,
    DocumentError,
    SectionRegistry,
    SectionSpec,
    mint_id,
    new_document,
    validate_document,
)
from kazbars.settings_core import Field, Schema


def _registry():
    reg = SectionRegistry()
    reg.register(SectionSpec(
        "alpha",
        Schema("", 1, {
            "count": Field(10, min=0, max=100, kind="int"),
            "mode": Field("a", choices=("a", "b")),
        }),
        LANE_BUILD,
    ))
    reg.register(SectionSpec(
        "beta",
        Schema("", 1, {
            "crit": Field("FFFFFF"),
            "size": Field(12, min=8, max=48, kind="int"),
        }),
        LANE_PATCH,
        sparse=True,
    ))
    return reg


def _doc(**overrides):
    base = {
        "schema": DOC_SCHEMA_VERSION,
        "id": "a3f81c2e",
        "name": "PoM Raid",
        "authored_at": [2560, 1440],
        "modules": {"alpha": {"count": 42}, "beta": {"size": 20}},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Registry + spec contract
# --------------------------------------------------------------------------- #

def test_duplicate_section_key_raises():
    reg = _registry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register(SectionSpec("alpha", Schema("", 1, {}), LANE_LIVE))


def test_unknown_lane_raises():
    with pytest.raises(ValueError, match="unknown lane"):
        SectionSpec("x", Schema("", 1, {}), "bake")


def test_for_lane_filters():
    reg = _registry()
    assert [s.key for s in reg.for_lane(LANE_BUILD)] == ["alpha"]
    assert [s.key for s in reg.for_lane(LANE_PATCH)] == ["beta"]
    assert reg.for_lane(LANE_LIVE) == ()


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #

def test_mint_id_is_8_hex():
    for _ in range(20):
        assert len(mint_id()) == 8
        assert int(mint_id(), 16) >= 0


def test_new_document_fills_all_sections():
    doc = new_document(_registry(), "  My Setup  ", (1920, 1080))
    assert doc["schema"] == DOC_SCHEMA_VERSION
    assert doc["name"] == "My Setup"
    assert doc["authored_at"] == [1920, 1080]
    assert doc["modules"]["alpha"] == {"count": 10, "mode": "a"}
    assert doc["modules"]["beta"] == {}  # sparse: default is no overrides
    assert validate_document(_registry(), doc) == doc


def test_new_document_empty_name_defaults():
    assert new_document(_registry(), "   ", (1920, 1080))["name"] == "Profile"


# --------------------------------------------------------------------------- #
# The boundary — rejections
# --------------------------------------------------------------------------- #

def test_non_dict_rejected():
    with pytest.raises(DocumentError, match="Not a KazBars profile"):
        validate_document(_registry(), "KZBARS1:abc")


def test_old_format_rejected_by_profile_schema_key():
    old = {"version": "2.2.2", "profile_schema": 1, "grids": []}
    with pytest.raises(DocumentError, match="older KazBars"):
        validate_document(_registry(), old)


def test_old_format_rejected_by_root_grids_key():
    with pytest.raises(DocumentError, match="older KazBars"):
        validate_document(_registry(), {"grids": []})


def test_missing_schema_rejected():
    with pytest.raises(DocumentError, match="Not a KazBars profile"):
        validate_document(_registry(), {"id": "a3f81c2e", "modules": {}})


def test_bool_schema_rejected():
    with pytest.raises(DocumentError, match="Not a KazBars profile"):
        validate_document(_registry(), _doc(schema=True))


def test_newer_schema_refused_untouched():
    with pytest.raises(DocumentError, match="update the app"):
        validate_document(_registry(), _doc(schema=DOC_SCHEMA_VERSION + 1))


def test_bad_id_rejected():
    for bad in (None, "", "xyz", "A3F81C2E", "a3f81c2e9"):
        with pytest.raises(DocumentError, match="damaged"):
            validate_document(_registry(), _doc(id=bad))


# --------------------------------------------------------------------------- #
# The boundary — section policy
# --------------------------------------------------------------------------- #

def test_known_section_strict_coerce_fill_drop():
    doc = _doc(modules={"alpha": {"count": 999, "mode": "z", "bogus": 1}})
    out = validate_document(_registry(), doc)
    assert out["modules"]["alpha"] == {"count": 100, "mode": "a"}  # clamped, filled, dropped


def test_missing_known_section_gets_defaults():
    out = validate_document(_registry(), _doc(modules={}))
    assert out["modules"]["alpha"] == {"count": 10, "mode": "a"}
    assert out["modules"]["beta"] == {}


def test_sparse_section_keeps_only_present_keys():
    out = validate_document(_registry(), _doc(modules={"beta": {"size": 999, "junk": 1}}))
    assert out["modules"]["beta"] == {"size": 48}


def test_unknown_section_preserved_verbatim():
    payload = {"future_thing": [1, {"deep": True}]}
    out = validate_document(_registry(), _doc(modules={"gamma": payload}))
    assert out["modules"]["gamma"] == payload
    assert out["modules"]["gamma"] is not payload  # deep-copied, not aliased


def test_envelope_coercion_defaults():
    out = validate_document(_registry(), _doc(name="  ", authored_at=[0, -5]))
    assert out["name"] == "Profile"
    assert out["authored_at"] == [1920, 1080]


def test_input_never_mutated():
    raw = _doc(modules={"alpha": {"count": 999}, "gamma": {"x": 1}})
    snapshot = {
        "schema": raw["schema"], "id": raw["id"], "name": raw["name"],
        "authored_at": list(raw["authored_at"]),
        "modules": {"alpha": {"count": 999}, "gamma": {"x": 1}},
    }
    validate_document(_registry(), raw)
    assert raw == snapshot


# --------------------------------------------------------------------------- #
# build_signature — the last_build identity
# --------------------------------------------------------------------------- #
def _sig_registry():
    from kazbars import grid_model, live_tracker_settings, stopwatch
    from kazbars.profile_document import SectionRegistry
    reg = SectionRegistry()
    reg.register(grid_model.PROFILE_SECTION)          # BUILD
    reg.register(live_tracker_settings.PROFILE_SECTION)  # LIVE
    reg.register(stopwatch.PROFILE_SECTION)           # BUILD
    return reg


def _sig_doc(reg):
    from kazbars.profile_document import new_document
    return new_document(reg, 'Sig', [1920, 1080])


def test_build_signature_is_stable_and_key_order_free():
    from kazbars.profile_document import build_signature
    reg = _sig_registry()
    doc = _sig_doc(reg)
    first = build_signature(reg, doc)
    assert first == build_signature(reg, doc)  # deterministic
    # Same content, different key insertion order → same canonical hash.
    sw = doc['modules']['stopwatch']
    doc['modules']['stopwatch'] = dict(reversed(list(sw.items())))
    assert build_signature(reg, doc) == first


def test_build_signature_changes_on_build_edits_only():
    from kazbars.profile_document import build_signature
    reg = _sig_registry()
    doc = _sig_doc(reg)
    base = build_signature(reg, doc)
    # LIVE section change: invisible to the build → hash unchanged.
    doc['modules']['boss_timer']['overlay']['font_size'] = 33
    assert build_signature(reg, doc) == base
    # BUILD section change flips it.
    doc['modules']['stopwatch']['enabled'] = True
    assert build_signature(reg, doc) != base
    # Envelope-only changes (name/rename) don't count either.
    doc['modules']['stopwatch']['enabled'] = False
    doc['name'] = 'Renamed'
    assert build_signature(reg, doc) == base


def test_build_signature_missing_section_hashes_as_defaults():
    from kazbars.profile_document import build_signature
    reg = _sig_registry()
    doc = _sig_doc(reg)
    base = build_signature(reg, doc)
    del doc['modules']['stopwatch']  # gate would refill with defaults
    assert build_signature(reg, doc) == base
