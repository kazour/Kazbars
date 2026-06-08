"""Tests for kazbars.profile_share — the KZBARS1 self-contained profile codec.

Covers encode/decode round-trip, corrupt/truncated rejection,
collect_referenced_user_buffs (exactly the user-provenance refs, across int-ID
and legacy name forms), a self-contained round-trip on an empty DB, and the
skip-on-collision import merge.

Run: `pytest tests/test_profile_share.py` (from repo root).
"""

import base64
import gzip
import json

import pytest

from kazbars import profile_share as PS
from kazbars.buff_db_layers import DeltaStore


def _b(i, name):
    return {"name": name, "ids": [i], "category": "#X", "type": "buff"}


# --------------------------------------------------------------------------- #
# encode / decode
# --------------------------------------------------------------------------- #

def test_encode_decode_round_trip():
    profile = {"version": "2.1.0", "profile_schema": 1, "grids": [{"whitelist": [1, 2]}]}
    buffs = [_b(9, "Mine")]
    s = PS.encode_profile(profile, buffs)
    assert s.startswith("KZBARS1:")
    p2, b2 = PS.decode_profile(s)
    assert p2 == profile
    assert b2 == buffs


def test_decode_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        PS.decode_profile("nope")
    with pytest.raises(ValueError):
        PS.decode_profile("")
    with pytest.raises(ValueError):
        PS.decode_profile(None)


def test_decode_rejects_corrupt_or_truncated():
    s = PS.encode_profile({"grids": []}, [])
    with pytest.raises(ValueError):
        PS.decode_profile(s[:-6])                  # truncated payload
    with pytest.raises(ValueError):
        PS.decode_profile("KZBARS1:not-valid-base64!!!")


def test_decode_rejects_non_dict_profile():
    bad = "KZBARS1:" + base64.b64encode(
        gzip.compress(json.dumps({"profile": [1, 2]}).encode())
    ).decode()
    with pytest.raises(ValueError):
        PS.decode_profile(bad)


# --------------------------------------------------------------------------- #
# collect_referenced_user_buffs
# --------------------------------------------------------------------------- #

def test_collect_user_buffs_int_and_name_refs():
    user_a, user_b, stock = _b(9, "MineA"), _b(8, "MineB"), _b(1, "Stock")
    by_id = {1: stock, 9: user_a, 8: user_b}
    by_name = {"Stock": stock, "MineA": user_a, "MineB": user_b}
    provenance = {1: "stock", 9: "user", 8: "user"}
    profile = {"grids": [
        {"whitelist": [1, 9], "slotAssignments": {"0": ["MineB"], "1": 1}},
    ]}
    out = PS.collect_referenced_user_buffs(profile, by_id, by_name, provenance)
    assert sorted(b["ids"][0] for b in out) == [8, 9]   # user 9 (id) + user 8 (name); stock excluded


def test_collect_excludes_non_user_refs():
    stock, user = _b(1, "S"), _b(9, "U")
    by_id, by_name = {1: stock, 9: user}, {"S": stock, "U": user}
    prov = {1: "stock", 9: "user"}
    assert PS.collect_referenced_user_buffs({"grids": [{"whitelist": [1]}]}, by_id, by_name, prov) == []


def test_collect_dedupes_and_ignores_unknown_refs():
    user = _b(9, "U")
    by_id, by_name, prov = {9: user}, {"U": user}, {9: "user"}
    profile = {"grids": [{"whitelist": [9, 9, 12345], "slotAssignments": {"0": [9]}}]}
    out = PS.collect_referenced_user_buffs(profile, by_id, by_name, prov)
    assert [b["ids"][0] for b in out] == [9]            # de-duped; unknown 12345 ignored


# --------------------------------------------------------------------------- #
# self-contained round-trip + import merge
# --------------------------------------------------------------------------- #

def test_self_contained_round_trip_into_empty_db(tmp_path):
    user = _b(9, "Mine")
    profile = {"grids": [{"whitelist": [9]}]}
    buffs = PS.collect_referenced_user_buffs(profile, {9: user}, {"Mine": user}, {9: "user"})
    p2, embedded = PS.decode_profile(PS.encode_profile(profile, buffs))
    assert embedded == [user]
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
