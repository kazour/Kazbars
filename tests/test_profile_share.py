"""Tests for kazbars.profile_share — the self-contained profile export files.

Covers the envelope (build/parse, bare-document acceptance, junk + newer-export
rejection), registry-hook buff harvesting (exactly the user-provenance refs,
across int-ID and legacy name forms, via grid_model's PROFILE_SECTION hook),
a self-contained round-trip into an empty DB through the document gate, and
the skip-on-collision import merge.

Run: `pytest tests/test_profile_share.py` (from repo root).
"""

import json

import pytest

from kazbars import grid_model
from kazbars import profile_share as PS
from kazbars.buff_db_layers import DeltaStore
from kazbars.profile_document import SectionRegistry, new_document, validate_document


def _b(i, name):
    return {"name": name, "ids": [i], "category": "#X", "type": "buff"}


def _registry():
    reg = SectionRegistry()
    reg.register(grid_model.PROFILE_SECTION)
    return reg


def _doc_with_grids(reg, grids):
    doc = new_document(reg, "Setup", (2560, 1440))
    doc["modules"]["grids"]["grids"] = grids
    return doc


# --------------------------------------------------------------------------- #
# Envelope: build / parse
# --------------------------------------------------------------------------- #

def test_build_parse_round_trip_through_json():
    reg = _registry()
    user = _b(9, "Mine")
    doc = _doc_with_grids(reg, [dict(grid_model.create_default_grid(), whitelist=[9])])
    env = PS.build_export(reg, doc, {9: user}, {"Mine": user}, {9: "user"})
    assert env["format"] == PS.EXPORT_FORMAT
    profile_raw, buffs = PS.parse_export(json.loads(json.dumps(env)))
    assert profile_raw == doc
    assert buffs == [user]
    assert validate_document(reg, profile_raw)["modules"]["grids"]["grids"][0]["whitelist"] == [9]


def test_build_export_deep_copies_document():
    reg = _registry()
    doc = _doc_with_grids(reg, [dict(grid_model.create_default_grid(), whitelist=[9])])
    env = PS.build_export(reg, doc, {}, {}, {})
    env["profile"]["modules"]["grids"]["grids"][0]["whitelist"].append(777)
    assert doc["modules"]["grids"]["grids"][0]["whitelist"] == [9]


def test_parse_accepts_bare_document():
    reg = _registry()
    doc = _doc_with_grids(reg, [])
    profile_raw, buffs = PS.parse_export(doc)
    assert profile_raw is doc
    assert buffs == []


def test_parse_passes_old_format_through_for_gate_rejection():
    # A pre-revamp profile file parses (it IS profile-shaped) so the document
    # gate downstream can give it the decided "older KazBars" message.
    old = {"version": "2.2.2", "profile_schema": 1, "grids": []}
    profile_raw, buffs = PS.parse_export(old)
    assert profile_raw is old and buffs == []
    with pytest.raises(ValueError, match="older KazBars"):
        validate_document(_registry(), profile_raw)


def test_parse_rejects_junk():
    for junk in (None, [1, 2], "KZBARS1:abc", {"hello": 1}):
        with pytest.raises(ValueError, match="isn't a KazBars profile"):
            PS.parse_export(junk)


def test_parse_rejects_envelope_missing_profile():
    with pytest.raises(ValueError, match="missing its profile"):
        PS.parse_export({"format": PS.EXPORT_FORMAT, "buffs": []})


def test_parse_rejects_newer_export_schema():
    env = {"format": PS.EXPORT_FORMAT, "export_schema": PS.EXPORT_SCHEMA + 1,
           "profile": {"schema": 1}}
    with pytest.raises(ValueError, match="update the app"):
        PS.parse_export(env)


def test_parse_coerces_non_list_buffs():
    env = {"format": PS.EXPORT_FORMAT, "profile": {"schema": 1}, "buffs": "nope"}
    assert PS.parse_export(env)[1] == []


# --------------------------------------------------------------------------- #
# collect_embedded_buffs (registry harvest hooks)
# --------------------------------------------------------------------------- #

def test_collect_user_buffs_int_and_name_refs():
    reg = _registry()
    user_a, user_b, stock = _b(9, "MineA"), _b(8, "MineB"), _b(1, "Stock")
    by_id = {1: stock, 9: user_a, 8: user_b}
    by_name = {"Stock": stock, "MineA": user_a, "MineB": user_b}
    provenance = {1: "stock", 9: "user", 8: "user"}
    doc = _doc_with_grids(reg, [dict(
        grid_model.create_default_grid(),
        whitelist=[1, 9], slotAssignments={"0": ["MineB"], "1": 1},
    )])
    out = PS.collect_embedded_buffs(reg, doc, by_id, by_name, provenance)
    assert [b["ids"][0] for b in out] == [8, 9]   # user 9 (id) + user 8 (name); stock excluded


def test_collect_dedupes_and_ignores_unknown_and_bool_refs():
    reg = _registry()
    user = _b(9, "U")
    doc = _doc_with_grids(reg, [dict(
        grid_model.create_default_grid(),
        whitelist=[9, 9, 12345, True], slotAssignments={"0": [9]},
    )])
    out = PS.collect_embedded_buffs(reg, doc, {9: user}, {"U": user}, {9: "user"})
    assert [b["ids"][0] for b in out] == [9]


def test_collect_empty_for_sections_without_hook():
    reg = _registry()
    doc = _doc_with_grids(reg, [])
    doc["modules"]["mystery"] = {"whitelist": [9]}  # unknown section: no hook, no harvest
    assert PS.collect_embedded_buffs(reg, doc, {9: _b(9, "U")}, {}, {9: "user"}) == []


# --------------------------------------------------------------------------- #
# Self-contained round-trip + import merge
# --------------------------------------------------------------------------- #

def test_self_contained_round_trip_into_empty_db(tmp_path):
    reg = _registry()
    user = _b(9, "Mine")
    doc = _doc_with_grids(reg, [dict(grid_model.create_default_grid(), whitelist=[9])])
    env = json.loads(json.dumps(PS.build_export(reg, doc, {9: user}, {"Mine": user}, {9: "user"})))
    profile_raw, embedded = PS.parse_export(env)
    imported = validate_document(reg, profile_raw)
    assert imported["modules"]["grids"]["grids"][0]["whitelist"] == [9]
    store = DeltaStore(tmp_path / "database_user.json")
    assert PS.merge_imported_buffs(store, embedded, existing_ids=set()) == (1, 0)
    assert store.load()["buffs"] == [user]


def test_merge_skips_on_collision(tmp_path):
    store = DeltaStore(tmp_path / "database_user.json")
    added, skipped = PS.merge_imported_buffs(store, [_b(9, "Mine"), _b(10, "New")], existing_ids={9})
    assert (added, skipped) == (1, 1)
    assert [b["ids"][0] for b in store.load()["buffs"]] == [10]


def test_merge_no_write_when_nothing_added(tmp_path):
    path = tmp_path / "database_user.json"
    added, skipped = PS.merge_imported_buffs(DeltaStore(path), [_b(9, "Mine")], existing_ids={9})
    assert (added, skipped) == (0, 1)
    assert not path.exists()                            # nothing added → no write


def test_merge_skips_on_secondary_id_collision(tmp_path):
    # A shared id anywhere in the list (not just ids[0]) must skip — adding it
    # would silently re-home the existing owner of that id in by_id.
    store = DeltaStore(tmp_path / "database_user.json")
    multi = {"name": "Multi", "ids": [10, 5], "category": "#X", "type": "buff"}
    added, skipped = PS.merge_imported_buffs(store, [multi], existing_ids={5})
    assert (added, skipped) == (0, 1)


def test_merge_renames_on_name_collision(tmp_path):
    # New id but a name that already exists → keep the buff (grids reference the
    # id) but rename it unique so the DB editor stays unambiguous.
    store = DeltaStore(tmp_path / "database_user.json")
    added, skipped = PS.merge_imported_buffs(
        store, [_b(999, "Frenzy")], existing_ids={111}, existing_names={"Frenzy"})
    assert (added, skipped) == (1, 0)
    saved = store.load()["buffs"]
    assert len(saved) == 1
    assert saved[0]["ids"] == [999]                     # id preserved → grid refs resolve
    assert saved[0]["name"] == "Frenzy (imported)"      # renamed unique


def test_merge_rename_bumps_on_repeat_collision(tmp_path):
    store = DeltaStore(tmp_path / "database_user.json")
    added, _ = PS.merge_imported_buffs(
        store, [_b(999, "Frenzy")], existing_ids=set(),
        existing_names={"Frenzy", "Frenzy (imported)"})
    assert added == 1
    assert store.load()["buffs"][0]["name"] == "Frenzy (imported 2)"
