"""Smoke tests for kazbars.build_executor — the install/uninstall orchestration.

Covers the filesystem side of the build pipeline (the riskiest untested path
per the audit), with no MTASC and no Tk: SWF + script deployment in both
standard and Aoc.exe modes, legacy-artifact cleanup, the Aoc xml.add module
files, launcher detection, uninstall, and the running-game-process argv. The
actual MTASC compile is covered separately (test_build_compile.py); the Build &
Install Tk flow is exercised manually (/smoke).

Run: `pytest tests/test_build_executor.py` (from repo root).
"""

import types

from kazbars import build_executor
from kazbars.build_executor import (
    AUTO_LOAD_MARKER,
    GAME_PROCESSES,
    LEGACY_AOC_DIRS,
    LEGACY_FLASH_FILES,
    cleanup_legacy_files,
    create_scripts,
    detect_aoc_launcher,
    get_running_game_process,
    install_to_client,
    is_aoc_running,
    uninstall_from_client,
    write_xml_add_files,
)


def _staging_swf(tmp_path):
    swf = tmp_path / "staging" / "KazBars.swf"
    swf.parent.mkdir(parents=True)
    swf.write_bytes(b"FWS\x06fake-swf-bytes")
    return swf


def _flash(game):
    return game / "Data" / "Gui" / "Default" / "Flash"


def _scripts(game):
    return game / "Scripts"


# =========================================================================== #
# install_to_client                                                           #
# =========================================================================== #

class TestInstallStandard:
    def test_copies_swf_and_writes_scripts(self, tmp_path):
        game = tmp_path / "game"
        ok, err = install_to_client(_staging_swf(tmp_path), str(game), use_aoc=False)

        assert (ok, err) == (True, "")
        assert (_flash(game) / "KazBars.swf").read_bytes().startswith(b"FWS")
        assert (_scripts(game) / "reloadgrids").exists()
        assert (_scripts(game) / "unloadgrids").exists()

    def test_writes_auto_load_marker(self, tmp_path):
        game = tmp_path / "game"
        install_to_client(_staging_swf(tmp_path), str(game), use_aoc=False)

        auto_login = (_scripts(game) / "auto_login").read_text(encoding="utf-8")
        assert AUTO_LOAD_MARKER in auto_login
        assert "/loadclip KazBars.swf" in auto_login

    def test_no_aoc_module_in_standard_mode(self, tmp_path):
        game = tmp_path / "game"
        install_to_client(_staging_swf(tmp_path), str(game), use_aoc=False)

        assert not (game / "Data" / "Gui" / "Aoc" / "KazBars").exists()


class TestInstallAoc:
    def test_writes_xml_add_and_no_auto_login_marker(self, tmp_path):
        game = tmp_path / "game"
        ok, err = install_to_client(_staging_swf(tmp_path), str(game), use_aoc=True)

        assert (ok, err) == (True, "")
        aoc_dir = game / "Data" / "Gui" / "Aoc" / "KazBars"
        assert (aoc_dir / "MainPrefs.xml.add").exists()
        assert (aoc_dir / "Modules.xml.add").exists()
        # Aoc.exe loads via xml.add — the auto_login marker must not be written.
        auto_login = _scripts(game) / "auto_login"
        if auto_login.exists():
            assert AUTO_LOAD_MARKER not in auto_login.read_text(encoding="utf-8")


# =========================================================================== #
# cleanup_legacy_files (runs inside every install)                            #
# =========================================================================== #

class TestCleanupLegacy:
    def test_removes_legacy_swfs_but_keeps_current(self, tmp_path):
        game = tmp_path / "game"
        flash = _flash(game)
        flash.mkdir(parents=True)
        for name in LEGACY_FLASH_FILES:
            (flash / name).write_text("stale", encoding="utf-8")
        (flash / "KazBars.swf").write_text("current", encoding="utf-8")

        cleanup_legacy_files(str(game))

        for name in LEGACY_FLASH_FILES:
            assert not (flash / name).exists()
        assert (flash / "KazBars.swf").exists()

    def test_removes_legacy_aoc_dirs(self, tmp_path):
        game = tmp_path / "game"
        aoc = game / "Data" / "Gui" / "Aoc"
        for name in LEGACY_AOC_DIRS:
            d = aoc / name
            d.mkdir(parents=True)
            (d / "Modules.xml.add").write_text("x", encoding="utf-8")

        cleanup_legacy_files(str(game))

        for name in LEGACY_AOC_DIRS:
            assert not (aoc / name).exists()

    def test_install_cleans_legacy_before_copy(self, tmp_path):
        game = tmp_path / "game"
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / "KzGrids.swf").write_text("stale", encoding="utf-8")

        install_to_client(_staging_swf(tmp_path), str(game), use_aoc=False)

        assert not (flash / "KzGrids.swf").exists()
        assert (flash / "KazBars.swf").exists()


# =========================================================================== #
# create_scripts                                                              #
# =========================================================================== #

class TestCreateScripts:
    def test_reload_unload_content(self, tmp_path):
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        create_scripts(scripts, use_aoc=False)

        assert (scripts / "reloadgrids").read_text(encoding="utf-8") == (
            "/unloadclip KazBars.swf\n/delay 100\n/loadclip KazBars.swf"
        )
        assert (scripts / "unloadgrids").read_text(encoding="utf-8") == (
            "/unloadclip KazBars.swf"
        )

    def test_standard_appends_marker_preserving_existing(self, tmp_path):
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        (scripts / "auto_login").write_text("/say hello\n", encoding="utf-8")

        create_scripts(scripts, use_aoc=False)

        content = (scripts / "auto_login").read_text(encoding="utf-8")
        assert "/say hello" in content
        assert AUTO_LOAD_MARKER in content

    def test_aoc_strips_marker_but_keeps_other_lines(self, tmp_path):
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        (scripts / "auto_login").write_text(
            f"/say hi\n\n{AUTO_LOAD_MARKER}\n/loadclip KazBars.swf\n",
            encoding="utf-8",
        )

        create_scripts(scripts, use_aoc=True)

        content = (scripts / "auto_login").read_text(encoding="utf-8")
        assert "/say hi" in content
        assert AUTO_LOAD_MARKER not in content


# =========================================================================== #
# write_xml_add_files                                                         #
# =========================================================================== #

def test_write_xml_add_files(tmp_path):
    aoc_dir = tmp_path / "Aoc" / "KazBars"
    write_xml_add_files(aoc_dir)

    prefs = (aoc_dir / "MainPrefs.xml.add").read_text(encoding="utf-8")
    modules = (aoc_dir / "Modules.xml.add").read_text(encoding="utf-8")
    assert 'name="KazBars"' in prefs
    assert 'movie             = "KazBars.swf"' in modules
    assert 'variable          = "KazBars"' in modules


# =========================================================================== #
# detect_aoc_launcher                                                         #
# =========================================================================== #

class TestDetectAocLauncher:
    def test_true_on_aoc_exe(self, tmp_path):
        aoc = tmp_path / "Data" / "Gui" / "Aoc"
        aoc.mkdir(parents=True)
        (aoc / "aoc.exe").write_text("x", encoding="utf-8")
        assert detect_aoc_launcher(str(tmp_path)) is True

    def test_true_on_aoc_log(self, tmp_path):
        aoc = tmp_path / "Data" / "Gui" / "Aoc"
        aoc.mkdir(parents=True)
        (aoc / "Aoc.log").write_text("x", encoding="utf-8")
        assert detect_aoc_launcher(str(tmp_path)) is True

    def test_false_when_absent(self, tmp_path):
        assert detect_aoc_launcher(str(tmp_path)) is False


# =========================================================================== #
# uninstall_from_client                                                       #
# =========================================================================== #

class TestUninstall:
    def test_removes_everything_and_lists_it(self, tmp_path):
        game = tmp_path / "game"
        install_to_client(_staging_swf(tmp_path), str(game), use_aoc=True)

        ok, msg = uninstall_from_client(str(game))

        assert ok is True
        assert "Removed:" in msg
        assert not (_flash(game) / "KazBars.swf").exists()
        assert not (game / "Data" / "Gui" / "Aoc" / "KazBars").exists()
        assert not (_scripts(game) / "reloadgrids").exists()

    def test_strips_marker_keeping_other_auto_login_lines(self, tmp_path):
        game = tmp_path / "game"
        install_to_client(_staging_swf(tmp_path), str(game), use_aoc=False)
        auto_login = _scripts(game) / "auto_login"
        auto_login.write_text(
            f"/say hi\n\n{AUTO_LOAD_MARKER}\n/loadclip KazBars.swf\n",
            encoding="utf-8",
        )

        uninstall_from_client(str(game))

        assert "/say hi" in auto_login.read_text(encoding="utf-8")
        assert AUTO_LOAD_MARKER not in auto_login.read_text(encoding="utf-8")

    def test_nothing_to_remove(self, tmp_path):
        ok, msg = uninstall_from_client(str(tmp_path))
        assert ok is True
        assert "isn't installed" in msg


# =========================================================================== #
# get_running_game_process — argv + match/exception handling                  #
# =========================================================================== #

class TestRunningGameProcess:
    def test_argv_and_match(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            # tasklist echoes the image name in its output when present.
            name = cmd[2].split("eq ")[1]
            stdout = f"{name} 1234 Console" if name == "AgeOfConan.exe" else ""
            return types.SimpleNamespace(stdout=stdout)

        monkeypatch.setattr(build_executor.subprocess, "run", fake_run)

        assert get_running_game_process() == "AgeOfConan.exe"
        # List-form argv, no shell, bounded timeout — the safe-subprocess contract.
        cmd, kwargs = calls[0]
        assert cmd[0] == "tasklist"
        assert "shell" not in kwargs
        assert kwargs["timeout"] == 5

    def test_none_when_no_match(self, monkeypatch):
        monkeypatch.setattr(
            build_executor.subprocess, "run",
            lambda cmd, **kw: types.SimpleNamespace(stdout=""),
        )
        assert get_running_game_process() is None
        assert is_aoc_running() is False

    def test_exception_is_isolated_per_process(self, monkeypatch):
        seen = []

        def fake_run(cmd, **kwargs):
            name = cmd[2].split("eq ")[1]
            seen.append(name)
            if name == GAME_PROCESSES[0]:
                raise OSError("tasklist unavailable")
            return types.SimpleNamespace(stdout=f"{name} running")

        monkeypatch.setattr(build_executor.subprocess, "run", fake_run)

        # First probe raises, loop continues, second matches.
        assert get_running_game_process() == GAME_PROCESSES[1]
        assert seen == list(GAME_PROCESSES)
