"""
Smoke test: the settings_backup pure layer round-trips and is safe.

Covers backup → restore byte-identity, *.tmp exclusion, manifest validation
(accept ours, reject foreign/non-zip), the Funcom-prefs locator under a
monkeypatched LOCALAPPDATA, and the zip-slip guard on restore. The Tk dialog
layer (open_backup_dialog / backup_settings / restore_settings) is exercised
manually via /smoke.

Run: `pytest tests/test_settings_backup.py` (from repo root).
"""

import zipfile

from kazbars.settings_backup import (
    funcom_prefs_path,
    locate_funcom_prefs,
    read_manifest,
    restore_zip,
    write_backup_zip,
)


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
    profiles = tmp_path / "profiles"
    _make_tree(profiles, {"Default.json": b'{"grids": []}', "Alt.json": b"{}"})
    settings = tmp_path / "settings"
    _make_tree(
        settings,
        {
            "kazbars_settings.json": b'{"game_path": "X"}',
            "deeps_settings.json": b'{"alarm_threshold": 2000}',
            "live_tracker_settings.json": b'{"opacity": 0.8}',
        },
    )

    zip_path = tmp_path / "backup.zip"
    sections = write_backup_zip(
        zip_path,
        funcom_dir=funcom,
        profiles_dir=profiles,
        settings_dir=settings,
        app_version="9.9.9",
    )

    assert sections["funcom"]["files"] == 4  # .tmp excluded
    assert sections["kazbars"] == {"profiles": 2, "settings": 3}  # all 3 settings files

    manifest = read_manifest(zip_path)
    assert manifest["format"] == "kazbars-settings-backup"
    assert manifest["app_version"] == "9.9.9"

    funcom_dest = tmp_path / "restored_prefs"
    kazbars_dest = tmp_path / "restored_app"
    restored = restore_zip(zip_path, funcom_dest=funcom_dest, kazbars_dest=kazbars_dest)
    assert restored == {"funcom": 4, "kazbars": 5}  # 2 profiles + 3 settings

    assert (funcom_dest / "Prefs_3.xml").read_bytes() == b"<Root/>"
    assert (funcom_dest / "acct/Char1/preview.bin").read_bytes() == b"\x00\x01\x02"
    assert not (funcom_dest / "scratch.tmp").exists()
    assert (kazbars_dest / "profiles/Default.json").read_bytes() == b'{"grids": []}'
    assert (kazbars_dest / "settings/kazbars_settings.json").read_bytes() == b'{"game_path": "X"}'
    # Deeps + Live Tracker settings come along with the whole settings/ dir
    assert (kazbars_dest / "settings/deeps_settings.json").exists()
    assert (kazbars_dest / "settings/live_tracker_settings.json").exists()


def test_backup_omits_absent_sources(tmp_path) -> None:
    """A backup with no Funcom folder still writes the KazBars section."""
    profiles = tmp_path / "profiles"
    _make_tree(profiles, {"Only.json": b"{}"})
    zip_path = tmp_path / "kz_only.zip"
    sections = write_backup_zip(
        zip_path, funcom_dir=None, profiles_dir=profiles, settings_dir=None, app_version="1.0"
    )
    assert "funcom" not in sections
    assert sections["kazbars"] == {"profiles": 1}


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
    restored = restore_zip(z, funcom_dest=funcom_dest, kazbars_dest=tmp_path / "kz")
    assert restored["funcom"] == 1  # only the in-tree entry
    assert (funcom_dest / "ok.xml").exists()
    assert not (tmp_path / "escape.txt").exists()
