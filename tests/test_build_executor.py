"""Smoke tests for kazbars.build_executor — the install/uninstall orchestration.

Covers the filesystem side of the build pipeline (the riskiest untested path
per the audit), with no MTASC and no Tk: SWF deployment, the permanent module
declarations + patcher-bypass flag that make positions persist, clearing both
predecessor eras' load paths (and leaving them alone when the splice fails),
byte-exact uninstall, and the process-probe argv — including the patcher, whose
exit-save strips archives just as a client's does. The surgery itself is
unit-tested in test_game_persistence.py; the actual MTASC compile is covered
separately (test_build_compile.py); the Build & Install Tk flow is exercised
manually.

Run: `pytest tests/test_build_executor.py` (from repo root).
"""

import types

from kazbars import build_executor
from kazbars.build_executor import (
    AUTO_LOAD_MARKER,
    DAMAGEINFO_BACKUP,
    DAMAGEINFO_FILE,
    LEGACY_FLASH_FILES,
    LEGACY_SCRIPTS,
    cleanup_legacy_files,
    get_running_engine_process,
    get_running_game_process,
    install_to_client,
    is_aoc_running,
    uninstall_from_client,
)
from kazbars.game_persistence import (
    BACKUP_SUFFIX,
    FLAG_NAME,
    GAME_EXES,
    LEGACY_AOC_DIRS,
    MARKER_BEGIN,
    PATCHER_EXE,
)

# Minimal stand-ins for the game's XMLs — the splice only needs a </Root> to
# anchor to. Written as bytes so the LF endings survive on Windows.
STOCK_XML = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n<Root>\n</Root>\n'


def _staging_swf(tmp_path):
    swf = tmp_path / "staging" / "KazBars.swf"
    swf.parent.mkdir(parents=True, exist_ok=True)
    swf.write_bytes(b"FWS\x06fake-swf-bytes")
    return swf


def _flash(game):
    return game / "Data" / "Gui" / "Default" / "Flash"


def _scripts(game):
    return game / "Scripts"


def _default(game):
    return game / "Data" / "Gui" / "Default"


def _make_game(tmp_path, name="game"):
    """A game folder with the two XMLs install now splices into."""
    game = tmp_path / name
    _default(game).mkdir(parents=True, exist_ok=True)
    (_default(game) / "MainPrefs.xml").write_bytes(STOCK_XML)
    (_default(game) / "Modules.xml").write_bytes(STOCK_XML)
    return game


def _seed_legacy_layout(game):
    """A pre-persistence install: both old load paths present at once."""
    aoc = game / "Data" / "Gui" / "Aoc" / "KazBars"
    aoc.mkdir(parents=True, exist_ok=True)
    (aoc / "MainPrefs.xml.add").write_text("x", encoding="utf-8")
    (aoc / "Modules.xml.add").write_text("x", encoding="utf-8")
    _scripts(game).mkdir(parents=True, exist_ok=True)
    for script in LEGACY_SCRIPTS:
        (_scripts(game) / script).write_text("x", encoding="utf-8")
    (_scripts(game) / "auto_login").write_text(
        f"/say hi\n\n{AUTO_LOAD_MARKER}\n/loadclip KazBars.swf\n", encoding="utf-8")
    return game


# =========================================================================== #
# install_to_client                                                           #
# =========================================================================== #

class TestInstall:
    def test_copies_swf_and_declares_the_module(self, tmp_path):
        game = _make_game(tmp_path)
        ok, err = install_to_client(_staging_swf(tmp_path), str(game))

        assert (ok, err) == (True, "")
        assert (_flash(game) / "KazBars.swf").read_bytes().startswith(b"FWS")
        for xml in ("MainPrefs.xml", "Modules.xml"):
            assert MARKER_BEGIN in (_default(game) / xml).read_text(encoding="utf-8")
            assert (_default(game) / (xml + BACKUP_SUFFIX)).read_bytes() == STOCK_XML
        assert (game / FLAG_NAME).is_file()

    def test_writes_no_aoc_module_dir(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))

        # Our own fragments would make a live Aoc.exe declare KazBars twice.
        assert not (game / "Data" / "Gui" / "Aoc" / "KazBars").exists()

    def test_clears_the_previous_era_load_path(self, tmp_path):
        game = _make_game(tmp_path)
        _scripts(game).mkdir(parents=True)
        for script in LEGACY_SCRIPTS:
            (_scripts(game) / script).write_text("x", encoding="utf-8")
        (_scripts(game) / "auto_login").write_text(
            f"/say hi\n\n{AUTO_LOAD_MARKER}\n/loadclip KazBars.swf\n", encoding="utf-8")

        install_to_client(_staging_swf(tmp_path), str(game))

        for script in LEGACY_SCRIPTS:
            assert not (_scripts(game) / script).exists()
        auto_login = (_scripts(game) / "auto_login").read_text(encoding="utf-8")
        assert "/say hi" in auto_login
        assert AUTO_LOAD_MARKER not in auto_login

    def test_adopts_sibling_declarations_into_mainprefs_only(self, tmp_path):
        game = _make_game(tmp_path)
        mod = game / "Data" / "Gui" / "Aoc" / "RF position controller"
        mod.mkdir(parents=True)
        (mod / "MainPrefs.xml.add").write_text(
            '  <Archive name="Position" />', encoding="utf-8")
        (mod / "Modules.xml.add").write_text(
            '\t<Module name="RF" movie="RF.swf" />\n', encoding="utf-8")

        install_to_client(_staging_swf(tmp_path), str(game))

        # Their archive is declared, so a bare session can't strip it...
        assert '<Archive name="Position" />' in (
            _default(game) / "MainPrefs.xml").read_text(encoding="utf-8")
        # ...but their module is not ours to load.
        assert "RF" not in (_default(game) / "Modules.xml").read_text(encoding="utf-8")

    def test_second_install_is_idempotent(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))
        once = (_default(game) / "MainPrefs.xml").read_bytes()
        install_to_client(_staging_swf(tmp_path), str(game))

        assert (_default(game) / "MainPrefs.xml").read_bytes() == once

    def test_missing_xml_reports_a_repairable_failure(self, tmp_path):
        game = _make_game(tmp_path)
        (_default(game) / "MainPrefs.xml").unlink()

        ok, err = install_to_client(_staging_swf(tmp_path), str(game))

        assert ok is False
        # The escape that always works — pointing at Repair alone would be
        # circular when Repair is what just failed.
        assert "run the game patcher once" in err.lower()
        assert "Repair game install" in err

    def test_failed_splice_leaves_the_old_load_path_intact(self, tmp_path):
        game = _seed_legacy_layout(_make_game(tmp_path))
        (_default(game) / "MainPrefs.xml").unlink()

        ok, _ = install_to_client(_staging_swf(tmp_path), str(game))

        # Nothing declares KazBars now, so an upgrader's previous load path is
        # the only thing still working — it must survive the failure.
        assert ok is False
        assert (game / "Data" / "Gui" / "Aoc" / "KazBars" / "MainPrefs.xml.add").exists()
        assert (_scripts(game) / "reloadgrids").exists()
        assert AUTO_LOAD_MARKER in (
            _scripts(game) / "auto_login").read_text(encoding="utf-8")

    def test_damaged_markers_report_a_repairable_failure(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))
        prefs = _default(game) / "MainPrefs.xml"
        prefs.write_bytes(prefs.read_text(encoding="utf-8")
                          .replace(MARKER_BEGIN, "").encode("utf-8"))

        ok, err = install_to_client(_staging_swf(tmp_path), str(game))

        assert ok is False
        assert "Repair game install" in err


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

    def test_removes_legacy_and_own_aoc_dirs(self, tmp_path):
        game = tmp_path / "game"
        aoc = game / "Data" / "Gui" / "Aoc"
        for name in LEGACY_AOC_DIRS:
            d = aoc / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "Modules.xml.add").write_text("x", encoding="utf-8")

        cleanup_legacy_files(str(game))

        for name in LEGACY_AOC_DIRS:
            assert not (aoc / name).exists()

    def test_leaves_other_mods_alone(self, tmp_path):
        game = tmp_path / "game"
        other = game / "Data" / "Gui" / "Aoc" / "No Itemshop popup"
        other.mkdir(parents=True)
        (other / "Modules.xml.add").write_text("x", encoding="utf-8")

        cleanup_legacy_files(str(game))

        assert (other / "Modules.xml.add").exists()

    def test_install_cleans_legacy_before_copy(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / "KzGrids.swf").write_text("stale", encoding="utf-8")

        install_to_client(_staging_swf(tmp_path), str(game))

        assert not (flash / "KzGrids.swf").exists()
        assert (flash / "KazBars.swf").exists()


# =========================================================================== #
# uninstall_from_client                                                       #
# =========================================================================== #

class TestUninstall:
    def test_removes_everything_and_lists_it(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))

        ok, msg = uninstall_from_client(str(game))

        assert ok is True
        assert "Removed:" in msg
        assert not (_flash(game) / "KazBars.swf").exists()
        assert "Default/MainPrefs.xml" in msg
        assert FLAG_NAME in msg

    def test_restores_the_game_xmls_byte_exactly(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))

        uninstall_from_client(str(game))

        for xml in ("MainPrefs.xml", "Modules.xml"):
            assert (_default(game) / xml).read_bytes() == STOCK_XML
            assert not (_default(game) / (xml + BACKUP_SUFFIX)).exists()
        assert not (game / FLAG_NAME).exists()

    def test_strips_marker_keeping_other_auto_login_lines(self, tmp_path):
        game = _make_game(tmp_path)
        install_to_client(_staging_swf(tmp_path), str(game))
        auto_login = _scripts(game) / "auto_login"
        auto_login.parent.mkdir(parents=True, exist_ok=True)
        auto_login.write_text(
            f"/say hi\n\n{AUTO_LOAD_MARKER}\n/loadclip KazBars.swf\n",
            encoding="utf-8",
        )

        uninstall_from_client(str(game))

        assert "/say hi" in auto_login.read_text(encoding="utf-8")
        assert AUTO_LOAD_MARKER not in auto_login.read_text(encoding="utf-8")

    def test_removes_a_pre_persistence_layout(self, tmp_path):
        # An upgrader who never rebuilt: uninstall still has to clear both old
        # load paths, not just the declarations this version writes.
        game = _seed_legacy_layout(_make_game(tmp_path))
        (_flash(game)).mkdir(parents=True, exist_ok=True)
        (_flash(game) / "KazBars.swf").write_bytes(b"FWS\x06old")

        ok, msg = uninstall_from_client(str(game))

        assert ok is True
        assert not (game / "Data" / "Gui" / "Aoc" / "KazBars").exists()
        for script in LEGACY_SCRIPTS:
            assert not (_scripts(game) / script).exists()
        assert AUTO_LOAD_MARKER not in (
            _scripts(game) / "auto_login").read_text(encoding="utf-8")
        assert "Aoc module files" in msg
        assert "auto_login entry" in msg

    def test_nothing_to_remove(self, tmp_path):
        ok, msg = uninstall_from_client(str(tmp_path))
        assert ok is True
        assert "isn't installed" in msg


# =========================================================================== #
# Damage Numbers install / backup-once / revert / uninstall                   #
# (guards the one path that overwrites a core game file — see the audit)      #
# =========================================================================== #

class TestDamageInfo:
    @staticmethod
    def _kazbars(tmp_path):
        swf = tmp_path / "staging" / "KazBars.swf"
        swf.parent.mkdir(parents=True, exist_ok=True)
        swf.write_bytes(b"FWS\x06kazbars")
        return swf

    @staticmethod
    def _staged_di(tmp_path, content):
        p = tmp_path / "staging" / "DamageInfo.swf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    @staticmethod
    def _pristine(tmp_path, content=b"STOCK"):
        p = tmp_path / "assets" / "damageinfo" / "DamageInfo.swf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def _install(self, tmp_path, game, *, di, pristine):
        return install_to_client(self._kazbars(tmp_path), str(game),
                                 damageinfo_swf=di, damageinfo_pristine=pristine)

    # --- install + backup-once ------------------------------------------- #

    def test_first_install_backs_up_stock_and_writes_mod(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        ok, err = self._install(tmp_path, game,
                                di=self._staged_di(tmp_path, b"MODDED"),
                                pristine=self._pristine(tmp_path, b"STOCK"))

        assert (ok, err) == (True, "")
        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"MODDED"
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"

    def test_second_install_does_not_overwrite_backup(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED1"), pristine=pristine)
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED2"), pristine=pristine)

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"MODDED2"
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"  # still genuine stock

    def test_install_with_no_existing_target_seeds_pristine_backup(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        # no DamageInfo.swf present at all
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED"),
                      pristine=self._pristine(tmp_path, b"STOCK"))

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"MODDED"
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"

    def test_lost_backup_with_modded_target_reseeds_stock_not_mod(self, tmp_path):
        # The core regression: .bak deleted out-of-band while a mod remains. The next
        # build must seed the backup from bundled pristine stock, never from the mod —
        # otherwise "restore stock" would resurrect the mod forever.
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        pristine = self._pristine(tmp_path, b"STOCK")
        (flash / DAMAGEINFO_FILE).write_bytes(b"OLD-MODDED")  # modded, no .bak

        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"NEW-MODDED"), pristine=pristine)
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"
        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"NEW-MODDED"

        # disabling now restores genuine stock, not the mod
        self._install(tmp_path, game, di=None, pristine=pristine)
        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"

    # --- disable (damageinfo_swf=None) ----------------------------------- #

    def test_disable_restores_stock_and_keeps_backup(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED"), pristine=pristine)

        self._install(tmp_path, game, di=None, pristine=pristine)

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        # backup retained across a disable so a later re-enable keeps genuine stock
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"

    def test_disable_with_no_backup_is_noop(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")

        self._install(tmp_path, game, di=None, pristine=self._pristine(tmp_path, b"STOCK"))

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"   # untouched
        assert not (flash / DAMAGEINFO_BACKUP).exists()             # none created

    # --- uninstall ------------------------------------------------------- #

    def test_uninstall_restores_stock_and_removes_backup(self, tmp_path):
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED"), pristine=pristine)

        ok, msg = uninstall_from_client(str(game), damageinfo_pristine=pristine)

        assert ok is True
        assert "restored stock" in msg
        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        assert not (flash / DAMAGEINFO_BACKUP).exists()

    def test_uninstall_orphaned_mod_restored_from_pristine(self, tmp_path):
        # backup lost but a modded core file remains — uninstall must not leave it modded
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / "KazBars.swf").write_bytes(b"x")
        (flash / DAMAGEINFO_FILE).write_bytes(b"ORPHAN-MOD")
        pristine = self._pristine(tmp_path, b"STOCK")

        ok, msg = uninstall_from_client(str(game), damageinfo_pristine=pristine)

        assert ok is True
        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        assert "restored stock" in msg

    def test_uninstall_leaves_genuine_stock_untouched(self, tmp_path):
        # no backup, target already byte-identical to pristine → nothing to restore
        game = _make_game(tmp_path)
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / "KazBars.swf").write_bytes(b"x")
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")

        ok, msg = uninstall_from_client(str(game), damageinfo_pristine=pristine)

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        assert "DamageInfo" not in msg   # don't claim a restore we didn't do


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
            if name == GAME_EXES[0]:
                raise OSError("tasklist unavailable")
            return types.SimpleNamespace(stdout=f"{name} running")

        monkeypatch.setattr(build_executor.subprocess, "run", fake_run)

        # First probe raises, loop continues, second matches.
        assert get_running_game_process() == GAME_EXES[1]
        assert seen == list(GAME_EXES)

    def test_engine_probe_includes_the_patcher(self, monkeypatch):
        seen = []

        def fake_run(cmd, **kwargs):
            name = cmd[2].split("eq ")[1]
            seen.append(name)
            # Only the patcher is up — the client exes are not.
            stdout = f"{name} 4321 Console" if name == PATCHER_EXE else ""
            return types.SimpleNamespace(stdout=stdout)

        monkeypatch.setattr(build_executor.subprocess, "run", fake_run)

        # The patcher saves Prefs_3.xml on exit, so it strips a fresh archive
        # just as a client would — the first build and Repair both wait for it.
        assert get_running_engine_process() == PATCHER_EXE
        assert seen == [*GAME_EXES, PATCHER_EXE]
        assert get_running_game_process() is None
