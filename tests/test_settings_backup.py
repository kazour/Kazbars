"""
Smoke test: the settings_backup pure layer round-trips and is safe.

Covers backup → restore byte-identity, *.tmp exclusion, manifest validation
(accept ours, reject foreign/non-zip), the Funcom-prefs locator under a
monkeypatched LOCALAPPDATA, and the zip-slip guard on restore. Plus one
handoff-order test for `restore_settings` itself — the live profile must
flush before anything on disk changes, and reopen afterward — with every
other dependency monkeypatched; the rest of the Tk dialog layer
(open_backup_dialog / backup_settings) is exercised manually.

Run: `pytest tests/test_settings_backup.py` (from repo root).
"""

import zipfile
from types import SimpleNamespace

from kazbars import settings_backup
from kazbars.settings_backup import (
    locate_funcom_prefs,
    read_manifest,
    restore_settings,
    restore_zip,
    write_backup_zip,
)
from kazbars.userdata import funcom_prefs_path


def _make_tree(root, files: dict[str, bytes]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


def test_backup_restore_round_trip(tmp_path) -> None:
    funcom = tmp_path / "Prefs"
    _make_tree(
        funcom,
        {
            "Prefs_3.xml": b"<Root/>",
            "acct/hotkeys.xml": b"<keys/>",
            "acct/Char1/DockAreas/dock.xml": b"<dock/>",
            "acct/Char1/preview.bin": b"\x00\x01\x02",
            "scratch.tmp": b"transient - must be skipped",
        },
    )
    # The userdata/ allowlist: profiles/, database_user.json, prefs.json.
    profiles = tmp_path / "profiles"
    _make_tree(profiles, {"Default.json": b'{"grids": []}', "Alt.json": b"{}"})
    database_user = tmp_path / "database_user.json"
    database_user.write_bytes(b'{"version": 2, "buffs": [], "deleted": []}')
    prefs = tmp_path / "prefs.json"
    prefs.write_bytes(b'{"game_path": "X"}')
    # The OTA content/ cache exists but is NOT a write_backup_zip parameter, so
    # it can never enter a backup.
    _make_tree(tmp_path / "content", {"Database.json": b"{}", ".bak/prev/Database.json": b"{}"})

    zip_path = tmp_path / "backup.zip"
    sections = write_backup_zip(
        zip_path,
        funcom_dir=funcom,
        profiles_dir=profiles,
        database_user=database_user,
        prefs_file=prefs,
        app_version="9.9.9",
    )

    assert sections["funcom"]["files"] == 4  # .tmp excluded
    assert sections["kazbars"] == {"profiles": 2, "database_user": 1, "prefs": 1}

    # content/ never leaks into the archive.
    with zipfile.ZipFile(zip_path) as zf:
        assert not any("content" in n for n in zf.namelist())

    manifest = read_manifest(zip_path)
    assert manifest["format"] == "kazbars-settings-backup"
    assert manifest["app_version"] == "9.9.9"

    # Restore WITHOUT prefs (default): everything but prefs.json lands under userdata.
    funcom_dest = tmp_path / "restored_prefs"
    userdata_dest = tmp_path / "restored_userdata"
    restored = restore_zip(zip_path, funcom_dest=funcom_dest, userdata_dest=userdata_dest)
    assert restored == {"funcom": 4, "kazbars": 3}  # 2 profiles + db_user, NOT prefs

    assert (funcom_dest / "Prefs_3.xml").read_bytes() == b"<Root/>"
    assert (funcom_dest / "acct/Char1/preview.bin").read_bytes() == b"\x00\x01\x02"
    assert not (funcom_dest / "scratch.tmp").exists()
    assert (userdata_dest / "profiles/Default.json").read_bytes() == b'{"grids": []}'
    assert (userdata_dest / "database_user.json").exists()
    # prefs.json is machine-local — left out unless explicitly opted in.
    assert not (userdata_dest / "prefs.json").exists()

    # Restore WITH prefs opted in: prefs.json comes along too.
    with_prefs = tmp_path / "restored_with_prefs"
    restored2 = restore_zip(
        zip_path, funcom_dest=tmp_path / "fp2", userdata_dest=with_prefs, include_prefs=True
    )
    assert restored2["kazbars"] == 4  # + prefs.json
    assert (with_prefs / "prefs.json").read_bytes() == b'{"game_path": "X"}'


def test_backup_omits_absent_sources(tmp_path) -> None:
    """A backup with no Funcom folder still writes the KazBars section."""
    profiles = tmp_path / "profiles"
    _make_tree(profiles, {"Only.json": b"{}"})
    zip_path = tmp_path / "kz_only.zip"
    sections = write_backup_zip(
        zip_path, funcom_dir=None, profiles_dir=profiles, app_version="1.0"
    )
    assert "funcom" not in sections
    assert sections["kazbars"] == {"profiles": 1}


def test_restore_skips_pre_p8_settings_entries(tmp_path) -> None:
    """A backup made before P8 may still carry `kazbars/settings/*` (Deeps /
    Live Tracker / Damage Numbers disk files) — restore must not resurrect
    the retired `userdata/settings/` directory."""
    z = tmp_path / "legacy.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("kazbars/profiles/Default.json", '{"grids": []}')
        zf.writestr("kazbars/settings/deeps_settings.json", '{"alarm_threshold": 2000}')
        zf.writestr("kazbars/database_user.json", '{"version": 2, "buffs": [], "deleted": []}')
    userdata_dest = tmp_path / "restored"
    restored = restore_zip(z, funcom_dest=tmp_path / "fp", userdata_dest=userdata_dest)
    assert restored["kazbars"] == 2  # profile + db_user, settings/ entry skipped
    assert (userdata_dest / "profiles/Default.json").exists()
    assert not (userdata_dest / "settings").exists()


def test_read_manifest_rejects_foreign_zip(tmp_path) -> None:
    z = tmp_path / "foreign.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("hello.txt", "not a backup")
    assert read_manifest(z) is None


def test_read_manifest_rejects_non_zip(tmp_path) -> None:
    p = tmp_path / "not.zip"
    p.write_text("garbage")
    assert read_manifest(p) is None


def test_locate_funcom_prefs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    prefs = tmp_path / "Funcom" / "Conan" / "Prefs"
    assert funcom_prefs_path() == prefs
    assert locate_funcom_prefs() is None  # path computed, but not yet on disk
    prefs.mkdir(parents=True)
    assert locate_funcom_prefs() == prefs


def test_funcom_prefs_path_without_localappdata(monkeypatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert funcom_prefs_path() is None
    assert locate_funcom_prefs() is None


def test_restore_blocks_zip_slip(tmp_path) -> None:
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("funcom/../escape.txt", "pwned")
        zf.writestr("funcom/ok.xml", "<ok/>")
    funcom_dest = tmp_path / "dest"
    restored = restore_zip(z, funcom_dest=funcom_dest, userdata_dest=tmp_path / "kz")
    assert restored["funcom"] == 1  # only the in-tree entry
    assert (funcom_dest / "ok.xml").exists()
    assert not (tmp_path / "escape.txt").exists()


def _stub_restore_settings_deps(monkeypatch, tmp_path, order, *, release_store_ok=True):
    """Monkeypatch every restore_settings dependency except profile_io's
    release_store/startup_profile (order-recorded by the caller) so the flow
    runs to completion (or aborts, per release_store_ok) with no real disk/Tk."""
    monkeypatch.setattr(settings_backup, "filedialog",
                        SimpleNamespace(askopenfilename=lambda **k: str(tmp_path / "backup.zip")))
    monkeypatch.setattr(settings_backup, "read_manifest", lambda p: {"created": "now"})
    monkeypatch.setattr(settings_backup, "funcom_prefs_path", lambda: tmp_path / "funcom")
    monkeypatch.setattr(settings_backup, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(settings_backup, "write_backup_zip", lambda *a, **k: {})
    monkeypatch.setattr(settings_backup, "locate_funcom_prefs", lambda: None)
    monkeypatch.setattr(settings_backup, "database_user_path", lambda: tmp_path / "db.json")
    monkeypatch.setattr(settings_backup, "prefs_path", lambda: tmp_path / "prefs.json")
    monkeypatch.setattr(settings_backup, "userdata_root", lambda: tmp_path)
    monkeypatch.setattr(
        settings_backup, "restore_zip",
        lambda *a, **k: order.append("restore_zip") or {"funcom": 1, "kazbars": 1})
    monkeypatch.setattr(
        settings_backup.profile_io, "release_store",
        lambda app: order.append("release_store") or release_store_ok)
    monkeypatch.setattr(
        settings_backup.profile_io, "startup_profile",
        lambda app: order.append("startup_profile"))
    monkeypatch.setattr(settings_backup, "Messagebox", SimpleNamespace(
        show_info=lambda *a, **k: None, show_error=lambda *a, **k: None))


def _restore_app(order, tmp_path):
    return SimpleNamespace(
        app_path=tmp_path, app_version="3.0.0", profiles_path=tmp_path / "profiles",
        settings=SimpleNamespace(reload=lambda: order.append("settings.reload")),
        database=SimpleNamespace(reload=lambda: order.append("database.reload")),
        db_panel=None,
    )


def test_restore_settings_flushes_before_restoring_then_reopens(monkeypatch, tmp_path) -> None:
    order = []
    _stub_restore_settings_deps(monkeypatch, tmp_path, order)
    app = _restore_app(order, tmp_path)

    restore_settings(app, SimpleNamespace(destroy=lambda: None))

    assert order == [
        "release_store", "restore_zip", "settings.reload", "database.reload", "startup_profile"]


def test_restore_settings_aborts_before_restore_zip_when_release_store_fails(
        monkeypatch, tmp_path) -> None:
    order = []
    _stub_restore_settings_deps(monkeypatch, tmp_path, order, release_store_ok=False)
    app = _restore_app(order, tmp_path)

    restore_settings(app, SimpleNamespace(destroy=lambda: None))

    assert order == ["release_store"]  # never reached restore_zip or anything after
