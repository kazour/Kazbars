"""Tests for `profile_library` — the managed profiles/ directory.

Pins the single-writer contract (everything through validate_document, both
directions), skip-invalid listing (corrupt / old-format files left untouched,
never listed), id-based identity across rename (dedupe-by-id healing), trash
with prune, template instantiate-only semantics, the library-never-empty
reseed, and session .bak round-trip.

Run: `pytest tests/test_profile_library.py` (from repo root).
"""

import json
import os

import pytest

from kazbars.profile_document import (
    DocumentError,
    SectionRegistry,
    SectionSpec,
    new_document,
)
from kazbars.profile_library import SEED_NAME, TRASH_KEEP, ProfileLibrary, slugify
from kazbars.settings_core import Field, Schema


def _registry():
    reg = SectionRegistry()
    reg.register(SectionSpec(
        "alpha",
        Schema("", 1, {"count": Field(10, min=0, max=100, kind="int")}),
        "build",
    ))
    return reg


@pytest.fixture
def lib(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    return ProfileLibrary(profiles, _registry())


def _write_raw(folder, name, payload):
    path = folder / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _doc(reg, name="Setup"):
    return new_document(reg, name, (2560, 1440))


# --------------------------------------------------------------------------- #
# Listing: skip-invalid, dedupe-by-id
# --------------------------------------------------------------------------- #

def test_write_list_load_round_trip(lib):
    doc = _doc(lib.registry)
    path = lib.write(doc)
    assert path is not None and path.name == "Setup.json"
    assert [d for _, d in lib.list_profiles()] == [doc]
    assert lib.load(doc["id"]) == (path, doc)


def test_old_format_and_corrupt_files_skipped_and_untouched(lib):
    old = _write_raw(lib.profiles_dir, "MyGrids.json", {"profile_schema": 1, "grids": []})
    bad = _write_raw(lib.profiles_dir, "broken.json", {"schema": 1})  # no id
    garbage = lib.profiles_dir / "garbage.json"
    garbage.write_text("{not json", encoding="utf-8")
    before = {p.name: p.read_text(encoding="utf-8") for p in (old, bad, garbage)}
    assert lib.list_profiles() == []
    after = {p.name: p.read_text(encoding="utf-8") for p in (old, bad, garbage)}
    assert after == before  # never migrated, moved, or deleted


def test_listing_dedupes_by_id_newest_wins(lib):
    doc = _doc(lib.registry)
    stale = _write_raw(lib.profiles_dir, "Old Name.json", doc)
    fresh = lib.profiles_dir / "New Name.json"
    fresh.write_text(json.dumps(doc), encoding="utf-8")
    imported_at = stale.stat().st_mtime
    os.utime(stale, (imported_at - 100, imported_at - 100))
    entries = lib.list_profiles()
    assert len(entries) == 1
    assert entries[0][0] == fresh


def test_write_rejects_invalid_document(lib):
    with pytest.raises(DocumentError):
        lib.write({"schema": 1, "id": "nope"})


def test_write_same_id_keeps_path_new_id_gets_suffix(lib):
    doc = _doc(lib.registry)
    path = lib.write(doc)
    doc["modules"]["alpha"]["count"] = 5
    assert lib.write(doc) == path  # same id → same file
    other = _doc(lib.registry)  # same name, new id
    assert lib.write(other).name == "Setup (2).json"


# --------------------------------------------------------------------------- #
# Lifecycle: rename, duplicate, delete/trash
# --------------------------------------------------------------------------- #

def test_rename_reslugs_file_and_keeps_id(lib):
    doc = _doc(lib.registry)
    old_path = lib.write(doc)
    new_path = lib.rename(doc["id"], "Raid: PoM/Bear")
    assert new_path.name == "Raid PoMBear.json"  # illegal chars stripped
    assert not old_path.exists()
    held = lib.load(doc["id"])
    assert held is not None and held[1]["name"] == "Raid: PoM/Bear"


def test_rename_same_slug_rewrites_in_place(lib):
    doc = _doc(lib.registry, name="Setup")
    path = lib.write(doc)
    assert lib.rename(doc["id"], "Setup") == path


def test_rename_unknown_or_empty_is_none(lib):
    doc = _doc(lib.registry)
    lib.write(doc)
    assert lib.rename("deadbeef", "X") is None
    assert lib.rename(doc["id"], "   ") is None


def test_duplicate_gets_fresh_id_and_copy_name(lib):
    doc = _doc(lib.registry)
    lib.write(doc)
    dup = lib.duplicate(doc["id"])
    assert dup["id"] != doc["id"]
    assert dup["name"] == "Setup (copy)"
    dup2 = lib.duplicate(doc["id"])
    assert dup2["name"] == "Setup (copy) 2"
    assert len(lib.list_profiles()) == 3


def test_delete_moves_to_trash_and_prunes(lib):
    docs = []
    for i in range(TRASH_KEEP + 3):
        d = _doc(lib.registry, name=f"P{i:02d}")
        lib.write(d)
        docs.append(d)
    for d in docs:
        assert lib.delete(d["id"])
    assert lib.list_profiles() == []
    trashed = list(lib.trash_dir.glob("*.json"))
    assert len(trashed) == TRASH_KEEP


def test_delete_unknown_is_false(lib):
    assert lib.delete("deadbeef") is False


# --------------------------------------------------------------------------- #
# Templates + the never-empty invariant
# --------------------------------------------------------------------------- #

def test_ensure_nonempty_seeds_from_first_valid_template(lib, tmp_path):
    template = _doc(lib.registry, name="Default")
    template["modules"]["alpha"]["count"] = 77
    bad = _write_raw(tmp_path, "old-default.json", {"profile_schema": 1})
    good = _write_raw(tmp_path, "default.json", template)
    lib.template_paths = (bad, good)
    seeded = lib.ensure_nonempty((1920, 1080))
    assert seeded["name"] == SEED_NAME
    assert seeded["id"] != template["id"]  # instantiate-only: fresh id
    assert seeded["modules"]["alpha"]["count"] == 77
    assert seeded["authored_at"] == [2560, 1440]  # template's own provenance
    assert lib.ensure_nonempty((1920, 1080)) is None  # no longer empty


def test_ensure_nonempty_blank_fallback_when_no_template(lib):
    seeded = lib.ensure_nonempty((1920, 1080))
    assert seeded["name"] == SEED_NAME
    assert seeded["authored_at"] == [1920, 1080]
    assert seeded["modules"]["alpha"] == {"count": 10}


# --------------------------------------------------------------------------- #
# Session snapshots
# --------------------------------------------------------------------------- #

def test_session_bak_round_trip_and_not_listed(lib):
    doc = _doc(lib.registry)
    path = lib.write(doc)
    lib.write_session_bak(doc)
    assert (lib.profiles_dir / f"{path.name}.bak").is_file()
    assert len(lib.list_profiles()) == 1  # .bak never lists
    assert lib.read_session_bak(doc["id"]) == doc


def test_delete_removes_session_bak(lib):
    doc = _doc(lib.registry)
    path = lib.write(doc)
    lib.write_session_bak(doc)
    lib.delete(doc["id"])
    assert not (lib.profiles_dir / f"{path.name}.bak").exists()


# --------------------------------------------------------------------------- #
# Slug rules
# --------------------------------------------------------------------------- #

def test_slugify_windows_safe():
    assert slugify('Raid <PoM>: "best"?') == "Raid PoM best"
    assert slugify("   ") == "Profile"
    assert slugify("dots...") == "dots"
    assert slugify("Bear  Shaman") == "Bear Shaman"
