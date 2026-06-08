"""Tests for kazbars.content_update — the OTA content channel (no network).

Pure helpers (parse/is_newer/app_supports/verify_sha256/summarize/apply/rollback)
are tested directly; the threaded dispatcher is exercised through `_worker` with
a fake synchronous app + an injected downloader (so the full apply → re-merge →
version-persist path runs without Tk or the network). `content_dir` and
`app_toast` are monkeypatched so nothing touches the real install or a display.

Run: `pytest tests/test_content_update.py` (from repo root).
"""

import hashlib
import json

import pytest

from kazbars import content_update as C
from kazbars.buff_database import BuffDatabase


def _b(i, name, **extra):
    return {"name": name, "ids": [i], "category": "#X", "type": "buff", **extra}


def _manifest(version=2, min_app="2.0.0", files=None):
    return {
        "schema": 1,
        "content_version": version,
        "min_app_version": min_app,
        "source_commit": "abc123",
        "notes": "some notes",
        "files": files or {"Database.json": {"url": "http://x/db", "sha256": "0" * 64}},
    }


def _payloads(db=b'{"version":2,"buffs":[]}', default=b"{}"):
    return {"Database.json": db, "Default.json": default}


# --------------------------------------------------------------------------- #
# parse_manifest
# --------------------------------------------------------------------------- #

def test_parse_valid():
    m = _manifest()
    assert C.parse_manifest(json.dumps(m)) == m
    assert C.parse_manifest(json.dumps(m).encode()) == m   # bytes too


@pytest.mark.parametrize("raw", [
    "{not json",
    "[]",
    json.dumps({"content_version": "x", "min_app_version": "1", "files": {"a": {"url": "u", "sha256": "s"}}}),
    json.dumps({"min_app_version": "1", "files": {"a": {"url": "u", "sha256": "s"}}}),
    json.dumps({"content_version": 1, "files": {"a": {"url": "u", "sha256": "s"}}}),
    json.dumps({"content_version": 1, "min_app_version": "1", "files": {}}),
    json.dumps({"content_version": 1, "min_app_version": "1", "files": {"a": {"url": "u"}}}),
])
def test_parse_rejects(raw):
    assert C.parse_manifest(raw) is None


# --------------------------------------------------------------------------- #
# is_newer / app_supports / verify_sha256 / summarize_changes
# --------------------------------------------------------------------------- #

def test_is_newer():
    assert C.is_newer(_manifest(version=3), 2)
    assert not C.is_newer(_manifest(version=2), 2)
    assert not C.is_newer(_manifest(version=1), 2)


def test_app_supports_min_version_gate():
    assert C.app_supports(_manifest(min_app="2.0.0"), "2.1.0")
    assert C.app_supports(_manifest(min_app="2.1.0"), "2.1.0")
    assert not C.app_supports(_manifest(min_app="2.2.0"), "2.1.0")


def test_verify_sha256():
    data = b"hello world"
    h = hashlib.sha256(data).hexdigest()
    assert C.verify_sha256(data, h)
    assert C.verify_sha256(data, h.upper())     # case-insensitive
    assert not C.verify_sha256(data, "0" * 64)
    assert not C.verify_sha256(data, None)


def test_summarize_changes():
    old = [_b(1, "A"), _b(2, "B")]
    new = [_b(1, "A"), _b(2, "B-changed"), _b(3, "C")]
    assert C.summarize_changes(old, new) == (1, 1)   # 3 added, 2 changed


# --------------------------------------------------------------------------- #
# apply_content / rollback / self-heal
# --------------------------------------------------------------------------- #

def test_apply_first_update_then_rollback_clears(tmp_path):
    content = tmp_path / "content"
    result = C.apply_content(content, _manifest(version=5), _payloads())
    assert result["content_version"] == 5
    assert (content / "Database.json").exists()
    assert (content / "Default.json").exists()
    assert json.loads((content / "manifest.json").read_text())["content_version"] == 5
    # prev/ recorded the (absent) prior state, so revert clears content/ entirely.
    assert C.rollback(content) is True
    assert not (content / "Database.json").exists()
    assert not (content / "manifest.json").exists()
    assert C._applied_version(content) == C.CONTENT_BASELINE_VERSION


def test_apply_twice_then_revert_to_previous(tmp_path):
    content = tmp_path / "content"
    C.apply_content(content, _manifest(version=5), _payloads(db=b"V5"))
    C.apply_content(content, _manifest(version=6), _payloads(db=b"V6"))
    assert (content / "Database.json").read_bytes() == b"V6"
    assert C.rollback(content) is True
    assert (content / "Database.json").read_bytes() == b"V5"
    assert C._applied_version(content) == 5


def test_mid_swap_self_heals(tmp_path):
    content = tmp_path / "content"
    # Crash after the os.replace, before the marker write: simulate by deleting
    # the marker. Re-applying next launch completes cleanly (sha matches; cheap).
    C.apply_content(content, _manifest(version=7), _payloads(db=b"V7"))
    (content / "manifest.json").unlink()
    assert C._applied_version(content) == C.CONTENT_BASELINE_VERSION   # not yet committed
    C.apply_content(content, _manifest(version=7), _payloads(db=b"V7"))
    assert C._applied_version(content) == 7


def test_apply_and_rollback_never_touch_user_deltas(tmp_path):
    content = tmp_path / "content"
    user = tmp_path / "database_user.json"
    seed = b'{"version":2,"buffs":[{"ids":[1]}],"deleted":[]}'
    user.write_bytes(seed)
    C.apply_content(content, _manifest(version=5), _payloads())
    C.rollback(content)
    assert user.read_bytes() == seed


def test_rollback_no_prev_returns_false(tmp_path):
    assert C.rollback(tmp_path / "content") is False


# --------------------------------------------------------------------------- #
# dispatcher (fake synchronous app + injected downloader)
# --------------------------------------------------------------------------- #

class _Settings(dict):
    def set(self, key, value):
        self[key] = value

    def save(self):
        pass


class _FakeApp:
    def __init__(self, settings, database):
        self.settings = settings
        self.database = database
        self.db_panel = None
        self._building = False

    def after(self, _delay, fn, *args):
        fn(*args)            # run main-thread hops synchronously

    def winfo_exists(self):
        return True


def test_toggle_off_short_circuits():
    calls = []
    app = _FakeApp(_Settings(auto_update_content=False), BuffDatabase())
    C.check_and_apply(app, "2.1.0", 1, downloader=lambda url, **k: calls.append(url))
    assert calls == []        # returns before starting the worker thread


def test_apply_guard_defers_while_editing(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "content_dir", lambda: tmp_path / "content")
    monkeypatch.setattr(C, "app_toast", lambda *a, **k: None)
    app = _FakeApp(_Settings(content_version=1), BuffDatabase())
    app.db_panel = type("P", (), {"modified": True})()
    C._apply_on_main(app, _manifest(version=5), _payloads())
    assert not (tmp_path / "content" / "Database.json").exists()   # nothing applied


def test_apply_guard_defers_while_building(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "content_dir", lambda: tmp_path / "content")
    monkeypatch.setattr(C, "app_toast", lambda *a, **k: None)
    app = _FakeApp(_Settings(content_version=1), BuffDatabase())
    app._building = True
    C._apply_on_main(app, _manifest(version=5), _payloads())
    assert not (tmp_path / "content" / "Database.json").exists()


def _stock(tmp_path, buffs):
    p = tmp_path / "Database.json"
    p.write_text(json.dumps({"version": 2, "buffs": buffs}), encoding="utf-8")
    return p


def test_worker_applies_remerges_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "content_dir", lambda: tmp_path / "content")
    monkeypatch.setattr(C, "app_toast", lambda *a, **k: None)
    stock = _stock(tmp_path, [_b(1, "S")])
    content = tmp_path / "content"
    user = tmp_path / "database_user.json"

    db = BuffDatabase()
    db.load_layers(stock, content / "Database.json", user)
    assert len(db.buffs) == 1

    app = _FakeApp(_Settings(content_version=1, auto_update_content=True), db)

    new_db = json.dumps({"version": 2, "buffs": [_b(1, "S"), _b(2, "New")]}).encode()
    default_payload = b"{}"
    manifest = _manifest(version=5, files={
        "Database.json": {"url": "http://x/db", "sha256": hashlib.sha256(new_db).hexdigest()},
        "Default.json": {"url": "http://x/def", "sha256": hashlib.sha256(default_payload).hexdigest()},
    })
    by_url = {C.MANIFEST_URL: json.dumps(manifest).encode(),
              "http://x/db": new_db, "http://x/def": default_payload}

    C._worker(app, "2.1.0", 1, manual=False, downloader=lambda url, **k: by_url[url])

    assert C._applied_version(content) == 5
    assert app.settings["content_version"] == 5
    assert len(app.database.buffs) == 2          # re-merged over the new content
    assert app.database.provenance[2] == "content"


def test_worker_skips_when_not_newer(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "content_dir", lambda: tmp_path / "content")
    monkeypatch.setattr(C, "app_toast", lambda *a, **k: None)
    app = _FakeApp(_Settings(content_version=5), BuffDatabase())
    manifest = _manifest(version=5)
    C._worker(app, "2.1.0", 5, manual=False,
              downloader=lambda url, **k: json.dumps(manifest).encode())
    assert not (tmp_path / "content" / "Database.json").exists()


def test_worker_sha_mismatch_aborts(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "content_dir", lambda: tmp_path / "content")
    monkeypatch.setattr(C, "app_toast", lambda *a, **k: None)
    app = _FakeApp(_Settings(content_version=1), BuffDatabase())
    manifest = _manifest(version=9, files={
        "Database.json": {"url": "http://x/db", "sha256": "0" * 64},   # won't match
    })
    by_url = {C.MANIFEST_URL: json.dumps(manifest).encode(), "http://x/db": b"corrupt-bytes"}
    C._worker(app, "2.1.0", 1, manual=False, downloader=lambda url, **k: by_url[url])
    assert not (tmp_path / "content" / "Database.json").exists()       # aborted, swapped nothing
    assert app.settings.get("content_version") == 1
