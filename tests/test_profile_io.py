"""Tests for kazbars.profile_io's Phase-5 additions — the profile_schema ladder
and the default-profile resolution (user default → OTA → stock).

The Tk-driven load/save flows are smoke-only; this covers the pure pieces.

Run: `pytest tests/test_profile_io.py` (from repo root).
"""

from kazbars import profile_io


class _Settings:
    def __init__(self, **values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)


class _App:
    def __init__(self, settings, assets_path):
        self.settings = settings
        self.assets_path = assets_path


def test_profile_schema_version_is_int():
    assert isinstance(profile_io.PROFILE_SCHEMA_VERSION, int)


def test_migrate_profile_empty_ladder_is_identity():
    data = {"version": "2.1.0", "profile_schema": 1, "grids": [1, 2]}
    assert profile_io._migrate_profile(data) == data


def test_resolve_default_prefers_user_default(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_io, "content_dir", lambda: tmp_path / "content")
    user_default = tmp_path / "profiles" / "Mine.json"
    user_default.parent.mkdir(parents=True)
    user_default.write_text("{}", encoding="utf-8")
    app = _App(_Settings(default_profile=str(user_default)), tmp_path / "assets")
    assert profile_io.resolve_default_profile_path(app) == user_default


def test_resolve_default_falls_back_to_ota_then_stock(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setattr(profile_io, "content_dir", lambda: content)
    app = _App(_Settings(), tmp_path / "assets")   # no default_profile set

    # No user default, no OTA Default.json → shipped stock.
    assert profile_io.resolve_default_profile_path(app) == tmp_path / "assets" / "kazbars" / "Default.json"

    # OTA Default.json present → it wins over stock.
    (content / "Default.json").write_text("{}", encoding="utf-8")
    assert profile_io.resolve_default_profile_path(app) == content / "Default.json"


def test_resolve_default_ignores_missing_user_default(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setattr(profile_io, "content_dir", lambda: content)
    # default_profile points at a file that no longer exists → fall through to stock.
    app = _App(_Settings(default_profile=str(tmp_path / "gone.json")), tmp_path / "assets")
    assert profile_io.resolve_default_profile_path(app) == tmp_path / "assets" / "kazbars" / "Default.json"
