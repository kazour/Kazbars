"""Tests for `profile_io` — the pure pieces of the app-facing profile satellite.

Since the revamp, profile_io orchestrates `profile_library` + `profile_store`
(each with its own suite); what's testable headless here is the template
chain order — OTA content first, then the shipped stock file — and the
missing-buff message shape. The Tk-driven
flows (apply_document, switch, rename/delete dialogs) are covered by the
panel-construction smoke and manual QA.

Run: `pytest tests/test_profile_io.py` (from repo root).
"""

import json
from pathlib import Path
from types import SimpleNamespace

from kazbars import content_update, profile_io, profile_share, userdata
from kazbars.profile_document import SectionRegistry, new_document, validate_document
from kazbars.profile_library import ProfileLibrary
from kazbars.profile_store import ProfileStore


def test_template_chain_order(monkeypatch, tmp_path):
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)
    app = SimpleNamespace(assets_path=Path("A:/assets"))
    chain = profile_io.template_paths(app)
    # No OTA content/ at all yet — active_content_dir() falls back to the
    # shipped baseline, which meets itself, so the entry is still included.
    assert chain == (
        tmp_path / "userdata" / "content" / "Default.json",
        Path("A:/assets/kazbars/Default.json"),
    )


def test_template_chain_drops_a_stale_content_entry(monkeypatch, tmp_path):
    # An app upgrade can bump CONTENT_BASELINE_VERSION past whatever OTA
    # content an older app version already applied — that content/ must not
    # even be offered to the template gate until the next OTA catches it up.
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)
    content = tmp_path / "userdata" / "content"
    content.mkdir(parents=True)
    stale = content_update.CONTENT_BASELINE_VERSION - 1
    (content / "manifest.json").write_text(
        json.dumps({"content_version": stale}), encoding="utf-8")
    app = SimpleNamespace(assets_path=Path("A:/assets"))

    chain = profile_io.template_paths(app)

    assert chain == (
        Path("A:/assets/kazbars/Default.json"),
    )


def test_newest_doc_empty_library_falls_back_to_in_memory_blank(monkeypatch):
    # `ensure_nonempty` is best-effort: when the disk refused every seed write
    # the library stays empty, and startup/delete must not die on max([]).
    monkeypatch.setattr(profile_io, "get_game_resolution_or_default", lambda: (1920, 1080))
    registry = SectionRegistry()
    app = SimpleNamespace(library=SimpleNamespace(list_profiles=lambda: []),
                          registry=registry)
    doc = profile_io._newest_doc(app)
    assert doc["name"] == "My Setup"
    assert validate_document(registry, doc) == doc


def test_newest_doc_tolerates_a_vanished_path(monkeypatch, tmp_path):
    # file_mtime() returns 0.0 instead of raising when a listed file has
    # since vanished — _newest_doc must still resolve to the entry that's
    # actually still there.
    monkeypatch.setattr(profile_io, "get_game_resolution_or_default", lambda: (1920, 1080))
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    gone = tmp_path / "gone.json"   # never created — simulates a vanished-mid-race file
    doc_real = {"id": "real-id"}
    doc_gone = {"id": "gone-id"}
    app = SimpleNamespace(library=SimpleNamespace(
        list_profiles=lambda: [(gone, doc_gone), (real, doc_real)]))

    result = profile_io._newest_doc(app)

    assert result == doc_real


def test_delete_current_flushes_before_trash(monkeypatch, tmp_path):
    """A pending debounced autosave must die with the delete — an orphaned
    timer firing afterwards would re-write the trashed document under a
    fresh slug, resurrecting the profile the user just deleted."""
    registry = SectionRegistry()
    lib = ProfileLibrary(tmp_path, registry)
    doc = lib.create_blank("Doomed", (1920, 1080))
    assert doc is not None
    doomed_id = doc["id"]

    pending = []  # scheduled debounce callbacks; None = cancelled
    store = ProfileStore(
        doc, writer=lib.write,
        schedule=lambda ms, fn: pending.append(fn) or len(pending),
        cancel=lambda token: pending.__setitem__(token - 1, None),
    )
    store.set_section("stopwatch", {"enabled": True})  # arms the debounce

    class _ConfirmDelete:
        def __init__(self, *a, **k):
            self.result = "Delete"

        def show(self):
            pass

    monkeypatch.setattr(profile_io, "MessageDialog", _ConfirmDelete)
    monkeypatch.setattr(profile_io, "apply_document", lambda app: None)
    monkeypatch.setattr(profile_io, "get_game_resolution_or_default", lambda: (1920, 1080))
    app = SimpleNamespace(
        library=lib, profile_store=store, registry=registry,
        after=lambda ms, fn: 0, after_cancel=lambda token: None,
        _on_grids_edited=lambda: None,
    )

    profile_io.delete_current(app)

    # Fire whatever the outgoing store still had scheduled — the orphaned-timer
    # scenario. The deleted profile must stay deleted.
    for fn in pending:
        if fn is not None:
            fn()
    assert lib.load(doomed_id) is None
    names = [d["name"] for _, d in lib.list_profiles()]
    assert names == ["My Setup"]  # the reseed, and nothing resurrected


def _failing_store(doc):
    """A ProfileStore whose writer always reports failure — every flush()
    call returns False and leaves the store dirty (armed for RETRY_MS)."""
    return ProfileStore(
        doc, writer=lambda d: None,
        schedule=lambda ms, fn: None, cancel=lambda token: None,
    )


def test_switch_profile_keeps_the_old_store_when_flush_fails(monkeypatch, tmp_path):
    registry = SectionRegistry()
    lib = ProfileLibrary(tmp_path, registry)
    doc_a = lib.create_blank("A", (1920, 1080))
    doc_b = lib.create_blank("B", (1920, 1080))
    assert doc_a is not None and doc_b is not None

    store = _failing_store(doc_a)
    store.set_section("stopwatch", {"enabled": True})  # dirty, so flush() must try to write

    toasts = []
    monkeypatch.setattr(
        profile_io, "app_toast", lambda app, msg, style, *a, **k: toasts.append((msg, style)))
    app = SimpleNamespace(
        library=lib, profile_store=store, registry=registry,
        after=lambda ms, fn: 0, after_cancel=lambda token: None,
        _on_grids_edited=lambda: None,
    )

    profile_io.switch_profile(app, doc_b["id"])

    # Old store kept (not replaced) — if switch_profile had gone on to call
    # make_store/apply_document, the missing app attributes those need would
    # have raised, which this test's bare SimpleNamespace implicitly guards.
    assert app.profile_store is store
    assert toasts and toasts[0][1] == "danger"
    assert "Profile not saved" in toasts[0][0]


def test_switch_profile_mirrors_grid_edits_before_flushing(monkeypatch, tmp_path):
    registry = SectionRegistry()
    lib = ProfileLibrary(tmp_path, registry)
    doc_a = lib.create_blank("A", (1920, 1080))
    doc_b = lib.create_blank("B", (1920, 1080))
    assert doc_a is not None and doc_b is not None

    order = []

    def _writer(doc):
        order.append("flush")
        return lib.write(doc)

    store = ProfileStore(
        doc_a, writer=_writer,
        schedule=lambda ms, fn: None, cancel=lambda token: None,
    )
    store.set_section("stopwatch", {"enabled": True})  # dirty, so flush() actually writes

    monkeypatch.setattr(profile_io, "apply_document", lambda app: None)
    app = SimpleNamespace(
        library=lib, profile_store=store, registry=registry,
        after=lambda ms, fn: 0, after_cancel=lambda token: None,
        _on_grids_edited=lambda: order.append("mirror"),
    )

    profile_io.switch_profile(app, doc_b["id"])

    assert order == ["mirror", "flush"]


def test_delete_current_keeps_the_profile_when_flush_fails(monkeypatch, tmp_path):
    registry = SectionRegistry()
    lib = ProfileLibrary(tmp_path, registry)
    doc = lib.create_blank("Doomed", (1920, 1080))
    assert doc is not None
    doomed_id = doc["id"]

    store = _failing_store(doc)
    store.set_section("stopwatch", {"enabled": True})  # dirty, so flush() must try to write

    class _ConfirmDelete:
        def __init__(self, *a, **k):
            self.result = "Delete"

        def show(self):
            pass

    monkeypatch.setattr(profile_io, "MessageDialog", _ConfirmDelete)
    monkeypatch.setattr(profile_io, "app_toast", lambda *a, **k: None)
    app = SimpleNamespace(
        library=lib, profile_store=store, registry=registry,
        after=lambda ms, fn: 0, after_cancel=lambda token: None,
        _on_grids_edited=lambda: None,
    )

    profile_io.delete_current(app)

    assert lib.load(doomed_id) is not None   # never trashed — flush failed first
    assert app.profile_store is store        # not replaced


def test_import_profile_continues_when_buff_merge_fails(monkeypatch, tmp_path):
    registry = SectionRegistry()
    lib = ProfileLibrary(tmp_path, registry)
    home_doc = lib.create_blank("Home", (1920, 1080))
    assert home_doc is not None

    src_doc = new_document(registry, "Imported", (1920, 1080))
    export_path = tmp_path / "export.kazbars.json"
    export_path.write_text(json.dumps({
        "format": "kazbars-profile-export",
        "export_schema": 1,
        "profile": src_doc,
        "buffs": [{"name": "Custom", "ids": [999999], "category": "#X", "type": "buff"}],
    }), encoding="utf-8")

    store = ProfileStore(
        home_doc, writer=lib.write,
        schedule=lambda ms, fn: None, cancel=lambda token: None,
    )

    def _boom(*a, **k):
        raise OSError("disk full")

    toasts = []
    monkeypatch.setattr(profile_io.filedialog, "askopenfilename", lambda **k: str(export_path))
    monkeypatch.setattr(profile_share, "merge_imported_buffs", _boom)
    monkeypatch.setattr(profile_io, "apply_document", lambda app: None)
    monkeypatch.setattr(
        profile_io, "app_toast", lambda app, msg, style, *a, **k: toasts.append((msg, style)))
    app = SimpleNamespace(
        library=lib, profile_store=store, registry=registry,
        after=lambda ms, fn: 0, after_cancel=lambda token: None,
        _on_grids_edited=lambda: None,
        database=SimpleNamespace(buffs=[], by_id={}),
    )

    profile_io.import_profile(app)

    assert app.profile_store is not store             # switched to the imported doc
    assert app.profile_store.document["name"] == "Imported"
    assert toasts and "custom buffs not added" in toasts[0][0]
