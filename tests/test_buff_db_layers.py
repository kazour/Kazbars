"""Tests for kazbars.buff_db_layers — the three-layer buff DB merge.

Covers merge precedence (stock <- content <- user), provenance mapping,
tombstones (incl. user re-add beating its own tombstone), missing/corrupt-layer
fallbacks, load_effective/load_floor, compute_delta (add/override/tombstone/
cosmetic-no-op/primary-id-change), and the DeltaStore round-trip.

Run: `pytest tests/test_buff_db_layers.py` (from repo root).
"""

import json

from kazbars import buff_db_layers as L
from kazbars.buff_db_layers import (
    DeltaStore,
    compute_delta,
    load_effective,
    load_floor,
    merge_layers,
)


def _b(id0, name, **extra):
    return {"name": name, "ids": [id0], "category": "#X", "type": "buff", **extra}


# --------------------------------------------------------------------------- #
# merge precedence + provenance
# --------------------------------------------------------------------------- #

def test_user_overrides_content_overrides_stock():
    stock = [_b(1, "Stock1"), _b(2, "Stock2")]
    content = [_b(2, "Content2")]   # overrides stock 2
    user = [_b(1, "User1")]         # overrides stock 1
    eff, prov = merge_layers(stock, content, user, set())
    by = {b["ids"][0]: b for b in eff}
    assert by[1]["name"] == "User1"
    assert by[2]["name"] == "Content2"
    assert prov[1] == "user"
    assert prov[2] == "content"


def test_provenance_unchanged_stock():
    _eff, prov = merge_layers([_b(1, "S")], [], [], set())
    assert prov[1] == "stock"


def test_user_add_new_id():
    eff, prov = merge_layers([_b(1, "S")], [], [_b(9, "Mine")], set())
    assert {b["ids"][0] for b in eff} == {1, 9}
    assert prov[9] == "user"


def test_order_preserved_override_keeps_position():
    stock = [_b(1, "A"), _b(2, "B"), _b(3, "C")]
    user = [_b(2, "B2")]
    eff, _prov = merge_layers(stock, [], user, set())
    assert [b["ids"][0] for b in eff] == [1, 2, 3]
    assert eff[1]["name"] == "B2"


def test_buff_without_ids_skipped():
    eff, _prov = merge_layers([{"name": "noid", "ids": []}], [], [], set())
    assert eff == []


# --------------------------------------------------------------------------- #
# tombstones
# --------------------------------------------------------------------------- #

def test_tombstone_hides_stock_buff():
    eff, prov = merge_layers([_b(1, "S1"), _b(2, "S2")], [], [], {2})
    assert {b["ids"][0] for b in eff} == {1}
    assert 2 not in prov


def test_user_readd_wins_over_own_tombstone():
    eff, prov = merge_layers([_b(2, "S2")], [], [_b(2, "Mine2")], {2})
    by = {b["ids"][0]: b for b in eff}
    assert by[2]["name"] == "Mine2"
    assert prov[2] == "user"


# --------------------------------------------------------------------------- #
# load_effective / load_floor / missing + corrupt layers
# --------------------------------------------------------------------------- #

def _write(p, buffs, deleted=None):
    data = {"version": 2, "buffs": buffs}
    if deleted is not None:
        data["deleted"] = deleted
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def test_load_effective_missing_content_and_user(tmp_path):
    stock = tmp_path / "Database.json"
    _write(stock, [_b(1, "S")])
    eff, prov = load_effective(
        stock, tmp_path / "content" / "Database.json", tmp_path / "database_user.json"
    )
    assert [b["ids"][0] for b in eff] == [1]
    assert prov[1] == "stock"


def test_load_effective_full_three_layers(tmp_path):
    stock = tmp_path / "Database.json"
    _write(stock, [_b(1, "S1"), _b(2, "S2")])
    content = tmp_path / "content" / "Database.json"
    _write(content, [_b(2, "C2"), _b(3, "C3")])
    user = tmp_path / "database_user.json"
    _write(user, [_b(4, "U4")], deleted=[1])
    eff, prov = load_effective(stock, content, user)
    by = {b["ids"][0]: b for b in eff}
    assert set(by) == {2, 3, 4}            # 1 tombstoned
    assert by[2]["name"] == "C2"           # content overrides stock
    assert prov == {2: "content", 3: "content", 4: "user"}


def test_load_floor_ignores_user(tmp_path):
    stock = tmp_path / "Database.json"
    _write(stock, [_b(1, "S1")])
    floor, prov = load_floor(stock, None)
    assert [b["ids"][0] for b in floor] == [1]
    assert prov == {1: "stock"}


def test_load_floor_stock_fallback(tmp_path):
    stock = tmp_path / "Database.json"            # missing on purpose
    fallback = tmp_path / "Database.json.default"
    _write(fallback, [_b(1, "Def")])
    floor, _prov = load_floor(stock, None, stock_fallback_path=fallback)
    assert [b["ids"][0] for b in floor] == [1]


def test_read_corrupt_layer_is_empty(tmp_path):
    bad = tmp_path / "Database.json"
    bad.write_text("{not json", encoding="utf-8")
    assert L._read_buffs(bad) == []


def test_read_user_delta_missing(tmp_path):
    buffs, deleted = L._read_user_delta(tmp_path / "nope.json")
    assert buffs == [] and deleted == set()


# --------------------------------------------------------------------------- #
# compute_delta
# --------------------------------------------------------------------------- #

def test_compute_delta_user_add():
    d = compute_delta([_b(1, "S1")], [_b(1, "S1"), _b(9, "Mine")])
    assert d["deleted"] == []
    assert [b["ids"][0] for b in d["buffs"]] == [9]


def test_compute_delta_override():
    d = compute_delta([_b(1, "S1")], [_b(1, "S1-edited")])
    assert [b["name"] for b in d["buffs"]] == ["S1-edited"]
    assert d["deleted"] == []


def test_compute_delta_unchanged_stock_not_in_delta():
    floor = [_b(1, "S1"), _b(2, "S2")]
    edited = [dict(_b(1, "S1")), dict(_b(2, "S2"))]   # value-equal copies
    d = compute_delta(floor, edited)
    assert d["buffs"] == []
    assert d["deleted"] == []


def test_compute_delta_tombstone():
    d = compute_delta([_b(1, "S1"), _b(2, "S2")], [_b(1, "S1")])
    assert d["deleted"] == [2]
    assert d["buffs"] == []


def test_compute_delta_ignores_cosmetic_optional_defaults():
    floor = [_b(1, "S1", stackEnd=0, partialList=False)]
    edited = [_b(1, "S1")]                            # same minus default-valued keys
    d = compute_delta(floor, edited)
    assert d["buffs"] == []


def test_compute_delta_primary_id_change_is_add_plus_tombstone():
    d = compute_delta([_b(1, "S1")], [_b(100, "S1")])
    assert d["deleted"] == [1]                        # old primary id tombstoned
    assert [b["ids"][0] for b in d["buffs"]] == [100]  # new id is a user add


# --------------------------------------------------------------------------- #
# DeltaStore
# --------------------------------------------------------------------------- #

def test_delta_store_round_trip(tmp_path):
    store = DeltaStore(tmp_path / "database_user.json")
    store.save({"version": 2, "buffs": [_b(9, "Mine")], "deleted": [3, 1, 2]})
    loaded = store.load()
    assert loaded["buffs"] == [_b(9, "Mine")]
    assert loaded["deleted"] == [1, 2, 3]            # sorted


def test_delta_store_load_missing(tmp_path):
    assert DeltaStore(tmp_path / "nope.json").load() == {
        "version": 2,
        "buffs": [],
        "deleted": [],
    }


def test_delta_store_save_atomic_no_tmp(tmp_path):
    DeltaStore(tmp_path / "database_user.json").save({"buffs": [], "deleted": []})
    assert list(tmp_path.glob("*.tmp")) == []


# --------------------------------------------------------------------------- #
# malformed-entry filtering (hand-editable files must never crash the merge)
# --------------------------------------------------------------------------- #

def test_is_valid_buff():
    assert L.is_valid_buff(_b(1, "Ok"))
    assert not L.is_valid_buff("not-a-dict")
    assert not L.is_valid_buff({"ids": [1]})                 # no name
    assert not L.is_valid_buff({"name": "", "ids": [1]})     # empty name
    assert not L.is_valid_buff({"name": "X"})                # no ids
    assert not L.is_valid_buff({"name": "X", "ids": []})     # empty ids
    assert not L.is_valid_buff({"name": "X", "ids": ["1"]})  # non-int id
    assert not L.is_valid_buff({"name": "X", "ids": [True]})  # bool: True == 1 would alias buff 1


def test_read_buffs_drops_malformed_entries(tmp_path):
    p = tmp_path / "Database.json"
    p.write_text(json.dumps({"version": 2, "buffs": [
        _b(1, "Good"), "junk", {"ids": [2]}, {"name": "NoIds"},
    ]}), encoding="utf-8")
    assert [b["name"] for b in L._read_buffs(p)] == ["Good"]


def test_read_user_delta_drops_malformed_buffs_and_tombstones(tmp_path):
    p = tmp_path / "database_user.json"
    p.write_text(json.dumps({
        "version": 2,
        "buffs": [_b(1, "Mine"), {"no": "name"}, "junk"],
        # [9] would be unhashable in a set; true would tombstone buff 1 (True == 1)
        "deleted": [7, "8", [9], None, True],
    }), encoding="utf-8")
    buffs, deleted = L._read_user_delta(p)
    assert [b["name"] for b in buffs] == ["Mine"]
    assert deleted == {7}


def test_delta_store_save_preserves_malformed_entries(tmp_path):
    # A hand-edit typo (string ids, string tombstone) is invisible to the
    # editor; a recompute-from-memory save must leave it in the file for the
    # user to fix, not erase it.
    p = tmp_path / "database_user.json"
    typo = {"name": "Typo", "ids": ["123"]}
    p.write_text(json.dumps({
        "version": 2,
        "buffs": [_b(1, "Mine"), typo],
        "deleted": [7, "8"],
    }), encoding="utf-8")
    store = DeltaStore(p)
    store.save({"buffs": [_b(2, "New")], "deleted": [7]})
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["buffs"] == [_b(2, "New"), typo]
    assert on_disk["deleted"] == [7, "8"]
