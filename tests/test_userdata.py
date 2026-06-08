"""Tests for kazbars.userdata — the userdata/ layout + path resolution.

ensure_layout() creates the full tree and seeds an empty database_user.json +
content/ dirs, is idempotent (never clobbers existing user data), and every
named subpath resolves under userdata/. app_path is monkeypatched to a tmp dir
so the tests never touch the real repo root.

Run: `pytest tests/test_userdata.py` (from repo root).
"""

import json

from kazbars import userdata


def _patch_root(monkeypatch, tmp_path):
    """Point userdata at tmp_path/userdata instead of the real install root."""
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)


def test_ensure_layout_creates_tree_and_seeds(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    userdata.ensure_layout()
    root = tmp_path / "userdata"
    assert root.is_dir()
    assert (root / "settings").is_dir()
    assert (root / "profiles").is_dir()
    assert (root / "content").is_dir()
    assert (root / "content" / ".bak").is_dir()
    db = root / "database_user.json"
    assert db.is_file()
    assert json.loads(db.read_text(encoding="utf-8")) == {
        "version": 2,
        "buffs": [],
        "deleted": [],
    }


def test_ensure_layout_idempotent_preserves_user_db(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    userdata.ensure_layout()
    db = userdata.database_user_path()
    db.write_text(
        json.dumps({"version": 2, "buffs": [{"ids": [1]}], "deleted": [2]}),
        encoding="utf-8",
    )
    userdata.ensure_layout()  # second run is a no-op — must NOT reseed
    reloaded = json.loads(db.read_text(encoding="utf-8"))
    assert reloaded["buffs"] == [{"ids": [1]}]
    assert reloaded["deleted"] == [2]


def test_ensure_layout_does_not_raise_when_root_exists(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    userdata.ensure_layout()
    userdata.ensure_layout()  # twice in a row, no exception


def test_subpaths_resolve_under_userdata(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    root = userdata.userdata_root()
    assert root == tmp_path / "userdata"
    assert userdata.prefs_path() == root / "prefs.json"
    assert userdata.settings_dir() == root / "settings"
    assert userdata.profiles_dir() == root / "profiles"
    assert userdata.database_user_path() == root / "database_user.json"
    assert userdata.content_dir() == root / "content"
    assert userdata.content_backup_dir() == root / "content" / ".bak"
