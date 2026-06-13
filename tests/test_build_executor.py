"""Smoke tests for kazbars.build_executor — the install/uninstall orchestration.

Covers the filesystem side of the build pipeline (the riskiest untested path
per the audit), with no MTASC and no Tk: SWF + script deployment in both
standard and Aoc.exe modes, legacy-artifact cleanup, the Aoc xml.add module
files, launcher detection, uninstall, and the running-game-process argv. The
actual MTASC compile is covered separately (test_build_compile.py); the Build &
Install Tk flow is exercised manually.

Run: `pytest tests/test_build_executor.py` (from repo root).
"""

import re
import types

from kazbars import build_executor
from kazbars.build_executor import (
    AUTO_LOAD_MARKER,
    DAMAGEINFO_BACKUP,
    DAMAGEINFO_FILE,
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

    def _install(self, tmp_path, game, *, di, pristine, use_aoc=False):
        return install_to_client(self._kazbars(tmp_path), str(game), use_aoc=use_aoc,
                                 damageinfo_swf=di, damageinfo_pristine=pristine)

    # --- install + backup-once ------------------------------------------- #

    def test_first_install_backs_up_stock_and_writes_mod(self, tmp_path):
        game = tmp_path / "game"
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
        game = tmp_path / "game"
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED1"), pristine=pristine)
        self._install(tmp_path, game, di=self._staged_di(tmp_path, b"MODDED2"), pristine=pristine)

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"MODDED2"
        assert (flash / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"  # still genuine stock

    def test_install_with_no_existing_target_seeds_pristine_backup(self, tmp_path):
        game = tmp_path / "game"
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
        game = tmp_path / "game"
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
        game = tmp_path / "game"
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
        game = tmp_path / "game"
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")

        self._install(tmp_path, game, di=None, pristine=self._pristine(tmp_path, b"STOCK"))

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"   # untouched
        assert not (flash / DAMAGEINFO_BACKUP).exists()             # none created

    # --- uninstall ------------------------------------------------------- #

    def test_uninstall_restores_stock_and_removes_backup(self, tmp_path):
        game = tmp_path / "game"
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
        game = tmp_path / "game"
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
        game = tmp_path / "game"
        flash = _flash(game)
        flash.mkdir(parents=True)
        (flash / "KazBars.swf").write_bytes(b"x")
        (flash / DAMAGEINFO_FILE).write_bytes(b"STOCK")
        pristine = self._pristine(tmp_path, b"STOCK")

        ok, msg = uninstall_from_client(str(game), damageinfo_pristine=pristine)

        assert (flash / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        assert "DamageInfo" not in msg   # don't claim a restore we didn't do


# =========================================================================== #
# TextColors.xml — "Group my resource numbers" toggle lifecycle               #
# =========================================================================== #
_STOCK_TEXTCOLORS = (
    '<TextColors>\n'
    '  <text name="self_attacked" color="0xFF0000" direction="1" />\n'
    '  <text name="stamina_lost" direction="1" />\n'
    '  <text name="mana_lost" direction="1" />\n'
    '  <text name="stamina_loss_critical" direction="1" />\n'
    '  <text name="mana_loss_critical" direction="1" />\n'
    '  <text name="stamina_gained" direction="-1" />\n'
    '</TextColors>\n'
)

_LOSS_NAMES = ("stamina_lost", "mana_lost", "stamina_loss_critical", "mana_loss_critical")


def _gui(game, skin):
    return game / "Data" / "Gui" / skin


def _write_textcolors(game, skin, text=_STOCK_TEXTCOLORS):
    p = _gui(game, skin) / "TextColors.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _dir_of(xml, name):
    m = re.search(rf'<[^>]*\bname="{name}"[^>]*>', xml)
    return re.search(r'direction\s*=\s*"(-?\d+)"', m.group(0)).group(1)


class TestTextColors:
    @staticmethod
    def _install(tmp_path, game, *, group=False, colors=None, split=False):
        swf = tmp_path / "staging" / "KazBars.swf"
        swf.parent.mkdir(parents=True, exist_ok=True)
        swf.write_bytes(b"FWS\x06kz")
        return install_to_client(swf, str(game), use_aoc=False,
                                 damageinfo_swf=None, damageinfo_pristine=None,
                                 group_resources=group, source_colors=colors or {},
                                 split_incoming=split)

    def test_enable_patches_and_backs_up_stock(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        ok, err = self._install(tmp_path, game, group=True)

        assert (ok, err) == (True, "")
        text = tc.read_text(encoding="utf-8")
        for name in _LOSS_NAMES:
            assert f'name="{name}" direction="-1"' in text
        assert 'name="stamina_gained" direction="-1"' in text  # gain untouched
        bak = tc.with_name("TextColors.xml.kazbars.bak")
        assert 'name="stamina_lost" direction="1"' in bak.read_text(encoding="utf-8")

    def test_prefers_customized_over_default(self, tmp_path):
        game = tmp_path / "game"
        default = _write_textcolors(game, "Default")
        cust = _write_textcolors(game, "Customized")
        self._install(tmp_path, game, group=True)

        assert 'name="stamina_lost" direction="-1"' in cust.read_text(encoding="utf-8")
        # Default left exactly as stock — the game reads Customized.
        assert 'name="stamina_lost" direction="1"' in default.read_text(encoding="utf-8")

    def test_disable_restores_stock(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, group=True)
        self._install(tmp_path, game, group=False)

        text = tc.read_text(encoding="utf-8")
        for name in _LOSS_NAMES:
            assert f'name="{name}" direction="1"' in text

    def test_second_enable_keeps_genuine_stock_backup(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, group=True)
        self._install(tmp_path, game, group=True)  # idempotent re-enable

        bak = tc.with_name("TextColors.xml.kazbars.bak")
        assert 'name="stamina_lost" direction="1"' in bak.read_text(encoding="utf-8")

    def test_missing_textcolors_install_still_succeeds(self, tmp_path):
        game = tmp_path / "game"  # no TextColors.xml anywhere
        ok, err = self._install(tmp_path, game, group=True)
        assert (ok, err) == (True, "")

    def test_uninstall_restores_stock_and_removes_backup(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, group=True)

        ok, msg = uninstall_from_client(str(game))

        assert ok is True
        assert "TextColors.xml (restored stock)" in msg
        assert 'name="stamina_lost" direction="1"' in tc.read_text(encoding="utf-8")
        assert not tc.with_name("TextColors.xml.kazbars.bak").exists()

    # --- per-source colors (compose with the direction toggle) ----------- #

    def test_colors_apply_from_stock_backup(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, colors={'self_attacked': '00FF00'})

        assert 'name="self_attacked" color="0x00FF00"' in tc.read_text(encoding="utf-8")
        bak = tc.with_name("TextColors.xml.kazbars.bak")
        assert 'name="self_attacked" color="0xFF0000"' in bak.read_text(encoding="utf-8")

    def test_colors_and_direction_compose(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, group=True, colors={'self_attacked': '00FF00'})

        text = tc.read_text(encoding="utf-8")
        assert 'name="self_attacked" color="0x00FF00"' in text   # color override
        assert 'name="stamina_lost" direction="-1"' in text      # resource flip composed in

    def test_colors_regenerate_from_stock_not_compounded(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, colors={'self_attacked': '111111'})
        self._install(tmp_path, game, colors={'self_attacked': '222222'})  # each build derives from stock
        assert 'name="self_attacked" color="0x222222"' in tc.read_text(encoding="utf-8")

    def test_disable_restores_colors_from_backup(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, colors={'self_attacked': '00FF00'})
        self._install(tmp_path, game)  # nothing active → restore stock

        assert 'name="self_attacked" color="0xFF0000"' in tc.read_text(encoding="utf-8")

    def test_uninstall_restores_colors(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, colors={'self_attacked': '00FF00'})

        uninstall_from_client(str(game))

        assert 'name="self_attacked" color="0xFF0000"' in tc.read_text(encoding="utf-8")
        assert not tc.with_name("TextColors.xml.kazbars.bak").exists()

    # --- "Split into two columns" → incoming/self directions (independent) -- #

    def test_split_drops_incoming_self_types(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, split=True)
        text = tc.read_text(encoding="utf-8")
        assert _dir_of(text, 'self_attacked') == '-1'   # incoming dropped to the column
        assert _dir_of(text, 'stamina_lost') == '1'     # resources untouched (group off)

    def test_split_and_resources_are_independent(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, group=True, split=True)
        text = tc.read_text(encoding="utf-8")
        assert _dir_of(text, 'self_attacked') == '-1'   # split
        assert _dir_of(text, 'stamina_lost') == '-1'    # resources

    def test_split_disable_restores_stock(self, tmp_path):
        game = tmp_path / "game"
        tc = _write_textcolors(game, "Default")
        self._install(tmp_path, game, split=True)
        self._install(tmp_path, game)  # nothing active → restore stock
        assert _dir_of(tc.read_text(encoding="utf-8"), 'self_attacked') == '1'


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
