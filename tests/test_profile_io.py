"""Tests for `profile_io` — the pure pieces of the app-facing profile satellite.

Since the revamp, profile_io orchestrates `profile_library` + `profile_store`
(each with its own suite); what's testable headless here is the template
chain order — OTA content first, then the interim new-format template, then
the shipped stock file — and the missing-buff message shape. The Tk-driven
flows (apply_document, switch, rename/delete dialogs) are covered by the
panel-construction smoke and manual QA.

Run: `pytest tests/test_profile_io.py` (from repo root).
"""

import json
from pathlib import Path
from types import SimpleNamespace

from kazbars import content_update, profile_io, userdata
from kazbars.profile_document import SectionRegistry, validate_document
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
        Path("A:/assets/kazbars/templates/Default.json"),
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
        Path("A:/assets/kazbars/templates/Default.json"),
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
