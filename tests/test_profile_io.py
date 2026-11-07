"""Tests for `profile_io` — the one profile file and its File-menu flows.

Headless: a fake `app` (SimpleNamespace) carries what the flows touch, the
userdata root points at tmp_path, and the Tk-only pieces (dialogs, the grids
panel dispatch) are monkeypatched. Covers the startup ladder (profile.yml →
its .bak → a 3.1 library's active or newest profile → the template seed →
blank), export / import / reset, the template chain order, and the
flush-before-replace guard. The window-level flows are covered by the
panel-construction smoke and manual QA.

Run: `pytest tests/test_profile_io.py` (from repo root).
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from kazbars import content_update, grid_model, profile_io, profile_share, userdata, yaml_io
from kazbars.overlay import size_for_height
from kazbars.profile_document import SectionRegistry, new_document
from kazbars.profile_store import ProfileStore

ASSETS = Path(__file__).resolve().parent.parent / "src" / "kazbars" / "assets"


@pytest.fixture
def root(monkeypatch, tmp_path):
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)
    userdata.ensure_layout()
    monkeypatch.setattr(profile_io, "get_game_resolution_or_default", lambda: (2560, 1440))
    return userdata.userdata_root()


@pytest.fixture
def app(root, monkeypatch):
    registry = SectionRegistry()
    registry.register(grid_model.PROFILE_SECTION)
    toasts = []
    monkeypatch.setattr(profile_io, "apply_document", lambda a: None)
    monkeypatch.setattr(profile_io, "app_toast",
                        lambda a, msg, style, *rest, **k: toasts.append((msg, style)))
    return SimpleNamespace(
        registry=registry, assets_path=ASSETS, profile_store=None, toasts=toasts,
        after=lambda ms, fn: fn(), after_cancel=lambda token: None,
        _on_grids_edited=lambda: None,
        database=SimpleNamespace(buffs=[], by_id={}, by_name={}, provenance={}),
    )


def _doc(app, name="Mine", **grids):
    doc = new_document(app.registry, name, (1920, 1080))
    doc["modules"]["grids"]["grids"] = [grid_model.create_default_grid(grid_id=g) for g in grids]
    return doc


def _write_yml(path, doc):
    path.write_text(yaml_io.dumps(profile_share.build_profile_file(doc)), encoding="utf-8")


def _library(root, *docs):
    lib = root / "profiles"
    lib.mkdir(exist_ok=True)
    paths = []
    for i, doc in enumerate(docs):
        p = lib / f"{doc['name']}.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        os.utime(p, (1000 + i, 1000 + i))
        paths.append(p)
    return paths


def _tree(path):
    return {p.relative_to(path): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- #
# Template chain
# --------------------------------------------------------------------------- #

def test_template_chain_order(monkeypatch, tmp_path):
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)
    app = SimpleNamespace(assets_path=Path("A:/assets"))
    chain = profile_io.template_paths(app)
    # No OTA content/ at all yet — active_content_dir() falls back to the
    # shipped baseline, which meets itself, so the entry is still included.
    assert chain == (
        tmp_path / "userdata" / "content" / "Default.yml",
        Path("A:/assets/kazbars/Default.yml"),
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
    assert profile_io.template_paths(app) == (Path("A:/assets/kazbars/Default.yml"),)


# --------------------------------------------------------------------------- #
# Startup ladder
# --------------------------------------------------------------------------- #

def test_startup_reads_profile_yml(app, root):
    _write_yml(root / "profile.yml", _doc(app, "Mine", A=1))
    profile_io.startup_profile(app)
    assert app.profile_store.document["name"] == "Mine"
    assert app.toasts == []


def test_a_damaged_profile_loads_the_bak_and_is_kept_aside(app, root):
    (root / "profile.yml").write_text("grids: [unclosed", encoding="utf-8")
    _write_yml(root / "profile.yml.bak", _doc(app, "Yesterday"))
    profile_io.startup_profile(app)
    assert app.profile_store.document["name"] == "Yesterday"
    assert (root / "profile.damaged.yml").read_text(encoding="utf-8") == "grids: [unclosed"
    assert "name: Yesterday" in (root / "profile.yml").read_text(encoding="utf-8")
    assert "restored the copy" in app.toasts[0][0] and app.toasts[0][1] == "warning"


def test_a_damaged_profile_without_a_bak_seeds_from_the_template(app, root):
    (root / "profile.yml").write_text("format: kazbars-profile\nschema: 99\n", encoding="utf-8")
    profile_io.startup_profile(app)
    assert app.profile_store.document["name"] == "My Setup"
    assert (root / "profile.damaged.yml").exists()
    assert "no copy could be read" in app.toasts[0][0]


def test_startup_adopts_the_library_profile_prefs_point_at(app, root):
    a, b = _doc(app, "Raid"), _doc(app, "Solo")
    _library(root, a, b)  # Solo is newest
    (root / "prefs.json").write_text(json.dumps({"active_profile": a["id"]}), encoding="utf-8")
    before = _tree(root / "profiles")
    profile_io.startup_profile(app)
    assert app.profile_store.document["id"] == a["id"]
    assert (root / "profile.yml").read_text(encoding="utf-8").startswith("format: kazbars-profile\n")
    assert _tree(root / "profiles") == before, "the library is read, never written"
    assert "Adopted “Raid”" in app.toasts[0][0]


def test_startup_adopts_the_newest_library_profile_without_a_pointer(app, root):
    _library(root, _doc(app, "Old"), _doc(app, "New"))
    (root / "profiles" / "junk.json").write_text("{nope", encoding="utf-8")
    profile_io.startup_profile(app)
    assert app.profile_store.document["name"] == "New"


def test_startup_seeds_from_the_template_sized_for_the_resolution(app, root):
    profile_io.startup_profile(app)
    doc = app.profile_store.document
    assert doc["name"] == "My Setup" and doc["id"] != "00000000"
    assert doc["modules"]["overlay"]["size"] == size_for_height(1440)
    assert doc["modules"]["grids"]["grids"], "the stock grids"
    assert (root / "profile.yml").exists() and app.toasts == []


def test_startup_falls_back_to_blank_without_a_template(app, root, tmp_path):
    app.assets_path = tmp_path / "no-assets"
    profile_io.startup_profile(app)
    assert app.profile_store.document["name"] == "My Setup"
    assert app.profile_store.document["modules"]["grids"]["grids"] == []
    assert not profile_io.has_template(app)


def test_the_store_writes_profile_yml_and_its_bak(app, root):
    _write_yml(root / "profile.yml", _doc(app, "Mine"))
    scheduled = []
    app.after = lambda ms, fn: scheduled.append(fn) or len(scheduled)
    profile_io.startup_profile(app)
    app.profile_store.set_section("stopwatch", {"enabled": True})
    assert app.profile_store.flush()
    assert "stopwatch:" in (root / "profile.yml").read_text(encoding="utf-8")
    assert "stopwatch:" not in (root / "profile.yml.bak").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Export / import / reset
# --------------------------------------------------------------------------- #

def _open_store(app, doc):
    app.profile_store = ProfileStore(doc, writer=lambda d: True,
                                     schedule=lambda ms, fn: None, cancel=lambda t: None)
    return app.profile_store


def test_export_writes_the_profile_file_with_buffs_only_when_any(app, root, monkeypatch, tmp_path):
    doc = _doc(app, "Raid: best", A=1)
    doc["modules"]["grids"]["grids"][0]["whitelist"] = [9]
    _open_store(app, doc)
    out = tmp_path / "out.kazbars.yml"
    seen = {}
    monkeypatch.setattr(profile_io.filedialog, "asksaveasfilename",
                        lambda **k: seen.update(k) or str(out))
    profile_io.export_profile(app)
    assert seen["initialfile"] == "Raid best.kazbars.yml"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("format: kazbars-profile\nschema: ") and "buffs:" not in text

    user = {"name": "Mine", "ids": [9], "category": "#X", "type": "buff"}
    app.database = SimpleNamespace(buffs=[user], by_id={9: user}, by_name={"Mine": user},
                                   provenance={9: "user"})
    profile_io.export_profile(app)
    assert yaml_io.loads(out.read_text(encoding="utf-8"))["buffs"] == [user]
    assert "(+1 custom buff)" in app.toasts[-1][0]


@pytest.mark.parametrize("kind", ["yml", "envelope", "bare"])
def test_import_replaces_the_document_in_the_same_store(app, root, monkeypatch, tmp_path, kind):
    incoming = _doc(app, "Shared", B=1)
    path = tmp_path / {"yml": "x.kazbars.yml", "envelope": "x.kazbars.json", "bare": "x.json"}[kind]
    if kind == "yml":
        _write_yml(path, incoming)
    elif kind == "envelope":
        path.write_text(json.dumps({"format": "kazbars-profile-export", "export_schema": 1,
                                    "profile": incoming, "buffs": []}), encoding="utf-8")
    else:
        path.write_text(json.dumps(incoming), encoding="utf-8")
    home = _doc(app, "Home", A=1)
    store = _open_store(app, home)
    monkeypatch.setattr(profile_io.filedialog, "askopenfilename", lambda **k: str(path))
    profile_io.import_profile(app)
    assert app.profile_store is store
    assert store.document["name"] == "Shared" and store.document["id"] != incoming["id"]
    store.revert_to_session_start()
    assert store.document["name"] == "Home", "Revert brings the previous profile back"


def test_import_shows_the_reason_and_keeps_the_profile(app, root, monkeypatch, tmp_path):
    grids_file = tmp_path / "g.kazbars-grids.yml"
    grids_file.write_text("format: kazbars-grids\nschema: 1\ngrids: []\n", encoding="utf-8")
    store = _open_store(app, _doc(app, "Home"))
    errors = []
    monkeypatch.setattr(profile_io.Messagebox, "show_error", lambda msg, **k: errors.append(msg))
    for path in (grids_file, tmp_path / "missing.yml"):
        monkeypatch.setattr(profile_io.filedialog, "askopenfilename", lambda p=path, **k: str(p))
        profile_io.import_profile(app)
    assert "Use File ▸ Import grid… instead." in errors[0]
    assert errors[1] == "That file couldn't be read as a KazBars profile."
    assert store.document["name"] == "Home"


def test_import_continues_when_the_buff_merge_fails(app, root, monkeypatch, tmp_path):
    path = tmp_path / "x.kazbars.json"
    path.write_text(json.dumps({
        "format": "kazbars-profile-export", "export_schema": 1, "profile": _doc(app, "Imported"),
        "buffs": [{"name": "Custom", "ids": [999999], "category": "#X", "type": "buff"}],
    }), encoding="utf-8")
    _open_store(app, _doc(app, "Home"))

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(profile_io.filedialog, "askopenfilename", lambda **k: str(path))
    monkeypatch.setattr(profile_share, "merge_imported_buffs", _boom)
    profile_io.import_profile(app)
    assert app.profile_store.document["name"] == "Imported"
    assert "custom buffs not added" in app.toasts[0][0]


class _Dialog:
    result = None

    def __init__(self, *a, **k):
        pass

    def show(self):
        pass


def test_reset_cancelled_changes_nothing(app, root, monkeypatch):
    store = _open_store(app, _doc(app, "Home", A=1))
    monkeypatch.setattr(profile_io, "MessageDialog", type("D", (_Dialog,), {"result": "Cancel"}))
    profile_io.reset_to_defaults(app)
    assert store.document["name"] == "Home" and not store.dirty


def test_reset_puts_the_template_in_place_and_revert_undoes_it(app, root, monkeypatch):
    store = _open_store(app, _doc(app, "Home", A=1))
    monkeypatch.setattr(profile_io, "MessageDialog", type("D", (_Dialog,), {"result": "Reset"}))
    profile_io.reset_to_defaults(app)
    assert store.document["name"] == "Default"
    assert store.document["modules"]["overlay"]["size"] == size_for_height(1440)
    assert app.toasts[-1] == ("Reset to defaults", "info")
    store.revert_to_session_start()
    assert store.document["name"] == "Home"


# --------------------------------------------------------------------------- #
# Flush guard
# --------------------------------------------------------------------------- #

def test_release_store_mirrors_then_flushes_and_reports_a_failure(app):
    order = []
    doc = _doc(app)
    app.profile_store = ProfileStore(doc, writer=lambda d: order.append("flush") and None,
                                     schedule=lambda ms, fn: None, cancel=lambda t: None)
    app._on_grids_edited = lambda: order.append("mirror")
    app.profile_store.set_section("stopwatch", {"enabled": True})
    assert profile_io.release_store(app) is False
    assert order == ["mirror", "flush"]
    assert app.toasts[0][1] == "danger" and "Profile not saved" in app.toasts[0][0]


def test_a_second_damaged_file_never_overwrites_the_first(app, root):
    (root / "profile.damaged.yml").write_text("first", encoding="utf-8")
    (root / "profile.yml").write_text("second: [", encoding="utf-8")
    profile_io.startup_profile(app)
    assert (root / "profile.damaged.yml").read_text(encoding="utf-8") == "first"
    assert (root / "profile.damaged-2.yml").read_text(encoding="utf-8") == "second: ["


def test_startup_adopts_the_hinted_library_profile(app, root):
    a, b = _doc(app, "Raid"), _doc(app, "Solo")
    _library(root, a, b)
    profile_io.startup_profile(app, active_hint=a["id"])
    assert app.profile_store.document["id"] == a["id"]


def test_a_value_yaml_cannot_hold_is_a_failed_write_not_a_crash(app, root):
    doc = _doc(app)
    doc["modules"]["mystery"] = {1: "int key"}
    assert profile_io.write_profile(app, doc) is None
