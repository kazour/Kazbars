"""Tests for kazbars.game_persistence — the permanent module declarations.

Covers the file surgery the persistence era rests on, against fake game trees
with no Tk and no game: splice/refresh/strip of the marked blocks (including
byte-exact restore, which the patcher's hash check makes visible), the
conditional Modules.xml target, the patcher-bypass flag, adoption of other
mods' archive declarations, Prefs_3.xml snapshot + re-injection, and the
desktop-shortcut spawn. The real client, patcher and shell are never involved.

Run: `pytest tests/test_game_persistence.py` (from repo root).
"""

import subprocess

import pytest

from kazbars import game_persistence
from kazbars.build_utils import CREATE_NO_WINDOW
from kazbars.game_persistence import (
    ARCHIVE_NAME,
    BACKUP_SUFFIX,
    FLAG_NAME,
    MARKER_BEGIN,
    MARKER_END,
    _scan_bytes,
    archive_names_in,
    client_supports_flag,
    create_game_desktop_link,
    discover_aoc_archive_declarations,
    ensure_flag,
    is_merged,
    main_prefs_path,
    missing_archives,
    modules_target,
    prefs3_path,
    reinject_archives,
    remove_flag,
    snapshot_prefs3,
    splice_declarations,
    strip_declarations,
)

# Shaped like the real files: XML declaration, $Change comment, LF-only line
# endings, a blank line before the closing </Root>.
STOCK_MAINPREFS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
    '<!-- $Change: 599229 $ -->\n'
    '<Root>\n'
    '  <Value name="FullScreen"        value="true" />\n'
    '  <Archive name="SelectedBundles" />\n'
    '\n'
    '</Root>\n'
)

STOCK_MODULES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
    '<!-- $Change: 599229 $ -->\n'
    '<Root>\n'
    '\t<Module name="HUDWindow" variable="hud_window"\n'
    '\t\tcriteria="hud_window"\n'
    '\t/>\n'
    '\n'
    '</Root>\n'
)

STOCK_PREFS3 = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
    '<Root>\n'
    '    <Value name="ViewDistance" value="3500.000000" />\n'
    '    <Archive name="KazBars settings">\n'
    '        <Double name="g0_x" value="623.000000" />\n'
    '        <Double name="g0_y" value="1126.000000" />\n'
    '    </Archive>\n'
    '    <Archive name="Position">\n'
    '        <Double name="px" value="10.000000" />\n'
    '    </Archive>\n'
    '    <Archive name="SelectedBundles" />\n'
    '</Root>\n'
)


def _write(path, text):
    """Write without newline translation — these tests assert on exact bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def _read(path):
    return path.read_bytes().decode('utf-8')


def _make_game(tmp_path, customized_modules=False):
    game = tmp_path / "game"
    default = game / "Data" / "Gui" / "Default"
    _write(default / "MainPrefs.xml", STOCK_MAINPREFS)
    _write(default / "Modules.xml", STOCK_MODULES)
    if customized_modules:
        _write(game / "Data" / "Gui" / "Customized" / "Modules.xml", STOCK_MODULES)
    return game


def _default_modules(game):
    return game / "Data" / "Gui" / "Default" / "Modules.xml"


def _customized_modules(game):
    return game / "Data" / "Gui" / "Customized" / "Modules.xml"


def _add_mod(game, name, mainprefs=None, modules=None):
    """Drop a sibling Aoc.exe mod folder with the given .xml.add fragments."""
    mod = game / "Data" / "Gui" / "Aoc" / name
    if mainprefs is not None:
        _write(mod / "MainPrefs.xml.add", mainprefs)
    if modules is not None:
        _write(mod / "Modules.xml.add", modules)
    return mod


# =========================================================================== #
# modules_target                                                              #
# =========================================================================== #

class TestModulesTarget:
    def test_defaults_to_default_dir(self, tmp_path):
        game = _make_game(tmp_path)
        assert modules_target(game) == _default_modules(game)

    def test_prefers_customized_when_present(self, tmp_path):
        game = _make_game(tmp_path, customized_modules=True)
        assert modules_target(game) == _customized_modules(game)

    def test_ignores_customized_dir_without_modules_xml(self, tmp_path):
        game = _make_game(tmp_path)
        (game / "Data" / "Gui" / "Customized").mkdir(parents=True)
        assert modules_target(game) == _default_modules(game)


# =========================================================================== #
# splice_declarations                                                         #
# =========================================================================== #

class TestSplice:
    def test_marks_both_files_before_root_close(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)

        for path in (main_prefs_path(game), _default_modules(game)):
            text = _read(path)
            assert text.count(MARKER_BEGIN) == 1
            assert text.count(MARKER_END) == 1
            assert text.index(MARKER_END) < text.index('</Root>')
        assert '<Value name="KazBars" value="true" />' in _read(main_prefs_path(game))
        assert '"KazBars settings"' in _read(_default_modules(game))
        assert 'movie             = "KazBars.swf"' in _read(_default_modules(game))
        assert is_merged(game)

    def test_is_idempotent(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        once = main_prefs_path(game).read_bytes()
        splice_declarations(game)

        assert main_prefs_path(game).read_bytes() == once

    def test_refreshes_block_in_place(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game, ('\t<Archive name="Position" />',))
        assert '<Archive name="Position" />' in _read(main_prefs_path(game))

        splice_declarations(game)
        text = _read(main_prefs_path(game))
        assert '<Archive name="Position" />' not in text
        assert text.count(MARKER_BEGIN) == 1

    def test_seeds_backup_with_pre_splice_bytes(self, tmp_path):
        game = _make_game(tmp_path)
        backup = main_prefs_path(game).with_name("MainPrefs.xml" + BACKUP_SUFFIX)

        splice_declarations(game)
        assert _read(backup) == STOCK_MAINPREFS

        # A marker refresh must never overwrite the backup with spliced text.
        splice_declarations(game, ('\t<Archive name="Position" />',))
        assert _read(backup) == STOCK_MAINPREFS

    def test_backup_follows_the_game_after_a_patch(self, tmp_path):
        game = _make_game(tmp_path)
        backup = main_prefs_path(game).with_name("MainPrefs.xml" + BACKUP_SUFFIX)
        splice_declarations(game)

        # The patcher restores its own (newer) stock file, markers and all gone.
        patched = STOCK_MAINPREFS.replace('599229', '600000')
        _write(main_prefs_path(game), patched)
        splice_declarations(game)

        # Re-seeded from what the game now ships — restoring later must not
        # revert the install to pre-patch text.
        assert _read(backup) == patched

    def test_non_utf8_file_says_so(self, tmp_path):
        game = _make_game(tmp_path)
        main_prefs_path(game).write_bytes(b'<Root>\xff\xfe</Root>\n')

        # UnicodeDecodeError is a ValueError subclass, so without handling this
        # would surface to the user as "damaged markers".
        with pytest.raises(ValueError, match="UTF-8"):
            splice_declarations(game)

    def test_preserves_lf_line_endings(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)

        raw = main_prefs_path(game).read_bytes()
        assert b'\r\n' not in raw

    def test_preserves_crlf_line_endings(self, tmp_path):
        game = _make_game(tmp_path)
        _write(main_prefs_path(game), STOCK_MAINPREFS.replace('\n', '\r\n'))
        splice_declarations(game)

        raw = main_prefs_path(game).read_bytes()
        assert raw.count(b'\n') == raw.count(b'\r\n')

    def test_damaged_marker_raises(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        text = _read(main_prefs_path(game))
        _write(main_prefs_path(game), text.replace(MARKER_END, ''))

        with pytest.raises(ValueError, match="damaged"):
            splice_declarations(game)

    def test_missing_xml_raises(self, tmp_path):
        game = _make_game(tmp_path)
        main_prefs_path(game).unlink()

        with pytest.raises(ValueError, match="missing"):
            splice_declarations(game)

    def test_shapeless_xml_raises(self, tmp_path):
        game = _make_game(tmp_path)
        _write(main_prefs_path(game), "not xml at all\n")

        with pytest.raises(ValueError, match="</Root>"):
            splice_declarations(game)

    def test_customized_target_leaves_default_untouched(self, tmp_path):
        game = _make_game(tmp_path, customized_modules=True)
        splice_declarations(game)

        assert MARKER_BEGIN in _read(_customized_modules(game))
        assert _read(_default_modules(game)) == STOCK_MODULES

    def test_is_merged_false_when_only_one_file_marked(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        _write(_default_modules(game), STOCK_MODULES)

        assert not is_merged(game)

    def test_is_merged_follows_a_newly_added_customized_target(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        assert is_merged(game)

        # A UI mod ships its own Customized/Modules.xml after we installed: our
        # Default block is no longer the one the game loads.
        _write(_customized_modules(game), STOCK_MODULES)
        assert not is_merged(game)

    def test_retarget_strips_the_stranded_default_block(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        default_backup = _default_modules(game).with_name("Modules.xml" + BACKUP_SUFFIX)
        assert default_backup.is_file()

        # A UI mod adds Customized/Modules.xml, moving the live target; the next
        # splice must sweep the stranded Default block (and its now-pointless
        # backup) or a merging engine would load the module twice.
        _write(_customized_modules(game), STOCK_MODULES)
        splice_declarations(game)

        assert MARKER_BEGIN in _read(_customized_modules(game))
        assert _read(_default_modules(game)) == STOCK_MODULES
        assert not default_backup.is_file()
        assert is_merged(game)


# =========================================================================== #
# strip_declarations                                                          #
# =========================================================================== #

class TestStrip:
    def test_restores_both_files_byte_exactly(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game, ('\t<Archive name="Position" />',))
        removed = strip_declarations(game)

        assert main_prefs_path(game).read_bytes() == STOCK_MAINPREFS.encode()
        assert _default_modules(game).read_bytes() == STOCK_MODULES.encode()
        assert removed == ["Default/MainPrefs.xml", "Default/Modules.xml"]

    def test_deletes_backups(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        strip_declarations(game)

        assert not main_prefs_path(game).with_name(
            "MainPrefs.xml" + BACKUP_SUFFIX).exists()
        assert not _default_modules(game).with_name(
            "Modules.xml" + BACKUP_SUFFIX).exists()

    def test_damaged_markers_restore_from_backup(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        text = _read(main_prefs_path(game))
        _write(main_prefs_path(game), text.replace(MARKER_BEGIN, ''))

        strip_declarations(game)
        assert main_prefs_path(game).read_bytes() == STOCK_MAINPREFS.encode()

    def test_sweeps_both_modules_locations(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)                      # lands in Default/
        _write(_customized_modules(game), STOCK_MODULES)
        splice_declarations(game)                      # now lands in Customized/

        removed = strip_declarations(game)
        assert MARKER_BEGIN not in _read(_default_modules(game))
        assert MARKER_BEGIN not in _read(_customized_modules(game))
        assert "Customized/Modules.xml" in removed

    def test_reports_nothing_when_never_installed(self, tmp_path):
        game = _make_game(tmp_path)
        assert strip_declarations(game) == []

    def test_shapeless_file_restores_from_backup(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        # Truncated past the markers and past </Root>: nothing to strip
        # surgically, and a re-splice would have nothing to anchor to either.
        _write(main_prefs_path(game), '<?xml version="1.0" ?>\n<Root>\n  <Value')

        strip_declarations(game)

        assert main_prefs_path(game).read_bytes() == STOCK_MAINPREFS.encode()
        # Repair's fallback re-splices onto the restored text.
        splice_declarations(game)
        assert MARKER_BEGIN in _read(main_prefs_path(game))

    def test_keeps_the_backup_when_nothing_was_stripped(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        backup = main_prefs_path(game).with_name("MainPrefs.xml" + BACKUP_SUFFIX)
        # Someone removed our block by hand: the file is fine, so there is
        # nothing to do — but their restore point must not be burned.
        _write(main_prefs_path(game), STOCK_MAINPREFS)

        strip_declarations(game)

        assert backup.is_file()
        assert _read(backup) == STOCK_MAINPREFS

    def test_keeps_the_backup_when_restore_is_impossible(self, tmp_path):
        game = _make_game(tmp_path)
        splice_declarations(game)
        backup = _default_modules(game).with_name("Modules.xml" + BACKUP_SUFFIX)
        backup.unlink()
        _write(_default_modules(game), 'garbage, no root tag')

        assert strip_declarations(game) == ["Default/MainPrefs.xml"]
        assert _read(_default_modules(game)) == 'garbage, no root tag'

    def test_missing_target_is_not_resurrected_from_its_backup(self, tmp_path):
        # A user can delete Customized/Modules.xml outright (e.g. removing a
        # mod that created it) after it became our live target. The old bug
        # treated "file gone" the same as "file unreadable" and restored it
        # from our orphaned .bak — resurrecting a file the user chose to
        # remove. MainPrefs.xml, still marked, must still get stripped in the
        # same pass; the old Default/Modules.xml target was already
        # self-cleaned when the second splice moved to Customized/, so it has
        # nothing left to strip.
        game = _make_game(tmp_path)
        splice_declarations(game)                      # lands in Default/
        _write(_customized_modules(game), STOCK_MODULES)
        splice_declarations(game)                      # now lands in Customized/
        customized_backup = _customized_modules(game).with_name(
            "Modules.xml" + BACKUP_SUFFIX)
        assert customized_backup.is_file()
        assert MARKER_BEGIN not in _read(_default_modules(game))
        _customized_modules(game).unlink()              # user deleted it

        removed = strip_declarations(game)

        assert not _customized_modules(game).exists()
        assert not customized_backup.exists()
        assert removed == ["Default/MainPrefs.xml"]


# =========================================================================== #
# IgnorePatcher.enable                                                        #
# =========================================================================== #

class TestFlag:
    def test_round_trip(self, tmp_path):
        game = _make_game(tmp_path)

        assert ensure_flag(game) is True
        assert (game / FLAG_NAME).is_file()
        assert (game / FLAG_NAME).read_bytes() == b''
        assert ensure_flag(game) is False

        assert remove_flag(game) is True
        assert not (game / FLAG_NAME).exists()
        assert remove_flag(game) is False


class TestClientSupportsFlag:
    def test_true_when_exe_carries_the_string(self, tmp_path):
        game = _make_game(tmp_path)
        (game / "AgeOfConanDX10.exe").write_bytes(
            b'\x00' * 512 + FLAG_NAME.encode() + b'\x00' * 512)

        assert client_supports_flag(game) is True

    def test_false_without_the_string(self, tmp_path):
        game = _make_game(tmp_path)
        (game / "AgeOfConan.exe").write_bytes(b'\x00' * 4096)
        (game / "AgeOfConanDX10.exe").write_bytes(b'\x00' * 4096)

        assert client_supports_flag(game) is False

    def test_false_when_exes_missing(self, tmp_path):
        assert client_supports_flag(_make_game(tmp_path)) is False

    def test_answer_is_memoized_per_game_folder(self, tmp_path, monkeypatch):
        game = _make_game(tmp_path)
        (game / "AgeOfConan.exe").write_bytes(b'\x00' * 16)
        (game / "AgeOfConanDX10.exe").write_bytes(FLAG_NAME.encode())
        scans = []
        real = game_persistence._scan_bytes
        monkeypatch.setattr(game_persistence, '_scan_bytes',
                            lambda p, n, **kw: scans.append(p) or real(p, n, **kw))

        assert client_supports_flag(game) is True
        first = len(scans)
        assert client_supports_flag(game) is True

        # The scan reads up to ~68 MB of executable; every build asks.
        assert first > 0
        assert len(scans) == first

    def test_finds_a_match_straddling_a_chunk_boundary(self, tmp_path):
        needle = FLAG_NAME.encode()
        blob = tmp_path / "blob.bin"
        # Split the needle across the read boundary — the overlap tail is the
        # only reason this is found at all.
        blob.write_bytes(b'\x00' * (64 - 5) + needle + b'\x00' * 64)

        assert _scan_bytes(blob, needle, chunk=64) is True
        assert _scan_bytes(blob, b'no-such-string', chunk=64) is False


# =========================================================================== #
# discover_aoc_archive_declarations                                           #
# =========================================================================== #

class TestDiscover:
    def test_adopts_sibling_archive_lines(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "RF position controller",
                 mainprefs='  <Archive name="Position" />')

        assert discover_aoc_archive_declarations(game) == (
            '\t<Archive name="Position" />',)

    def test_adopts_value_lines_too(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "Some mod",
                 mainprefs='\t<Value name="SomeMod" value="true" />\n'
                           '\t<Archive name="SomeMod settings" />\n')

        assert discover_aoc_archive_declarations(game) == (
            '\t<Value name="SomeMod" value="true" />',
            '\t<Archive name="SomeMod settings" />',
        )

    def test_skips_our_own_and_legacy_dirs(self, tmp_path):
        game = _make_game(tmp_path)
        for name in ("KazBars", "KazGrids", "KzGrids"):
            _add_mod(game, name, mainprefs='\t<Archive name="KazBars settings" />')

        assert discover_aoc_archive_declarations(game) == ()

    def test_ignores_module_fragments(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "No Itemshop popup",
                 modules='\t<Module name="NoShop" movie="NoShop.swf" />\n')

        assert discover_aoc_archive_declarations(game) == ()

    def test_dedups_identical_lines_across_mods(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "Mod A", mainprefs='  <Archive name="Position" />')
        _add_mod(game, "Mod B", mainprefs='\t<Archive name="Position" />')

        assert discover_aoc_archive_declarations(game) == (
            '\t<Archive name="Position" />',)

    def test_rejects_malformed_lines(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "Broken mod", mainprefs=(
            '<Archive name="Unclosed">\n'                  # not self-closing
            '<Module name="Sneaky" movie="x.swf" />\n'     # wrong element
            '</Root><Value name="X" value="1" />\n'        # tag soup
            'plain text\n'
            '<Archive name="Good" />\n'                    # the only keeper
        ))

        assert discover_aoc_archive_declarations(game) == (
            '\t<Archive name="Good" />',)

    def test_no_aoc_dir_is_empty(self, tmp_path):
        assert discover_aoc_archive_declarations(_make_game(tmp_path)) == ()

    def test_adopted_lines_survive_a_round_trip(self, tmp_path):
        game = _make_game(tmp_path)
        _add_mod(game, "RF position controller",
                 mainprefs='  <Archive name="Position" />')

        splice_declarations(game, discover_aoc_archive_declarations(game))
        assert '<Archive name="Position" />' in _read(main_prefs_path(game))
        # Adopted into MainPrefs only — their module must not load in a bare session.
        assert 'Position' not in _read(_default_modules(game))

        strip_declarations(game)
        assert main_prefs_path(game).read_bytes() == STOCK_MAINPREFS.encode()


class TestArchiveNamesIn:
    def test_collects_names(self):
        assert archive_names_in(STOCK_PREFS3) == {
            ARCHIVE_NAME, "Position", "SelectedBundles"}

    def test_empty_text(self):
        assert archive_names_in("") == set()


# =========================================================================== #
# Prefs_3.xml snapshot + re-injection                                         #
# =========================================================================== #

@pytest.fixture
def prefs3(tmp_path, monkeypatch):
    """Point prefs3_path() at a fake LOCALAPPDATA and return the file path."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "local"))
    path = prefs3_path()
    _write(path, STOCK_PREFS3)
    return path


class TestSnapshot:
    def test_snapshots_a_healthy_file(self, tmp_path, prefs3):
        dest = tmp_path / "userdata" / "prefs3_snapshot.xml"

        assert snapshot_prefs3(dest) is True
        assert dest.read_bytes() == prefs3.read_bytes()

    def test_refuses_a_stripped_file(self, tmp_path, prefs3):
        _write(prefs3, STOCK_PREFS3.replace(f'<Archive name="{ARCHIVE_NAME}">',
                                            '<Archive name="Other">'))
        dest = tmp_path / "snapshot.xml"

        assert snapshot_prefs3(dest) is False
        assert not dest.exists()

    def test_refuses_when_prefs3_is_absent(self, tmp_path, prefs3):
        prefs3.unlink()
        assert snapshot_prefs3(tmp_path / "snapshot.xml") is False

    def test_no_localappdata(self, monkeypatch):
        monkeypatch.delenv('LOCALAPPDATA', raising=False)
        assert prefs3_path() is None


class TestMissingArchives:
    def test_reports_what_the_snapshot_can_supply(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)
        _write(prefs3, STOCK_PREFS3.replace('name="KazBars settings"',
                                            'name="Gone"'))

        assert missing_archives(prefs3, snapshot,
                                {ARCHIVE_NAME, "Position"}) == (ARCHIVE_NAME,)

    def test_empty_when_live_has_everything(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)

        assert missing_archives(prefs3, snapshot, {ARCHIVE_NAME, "Position"}) == ()

    def test_ignores_names_the_snapshot_lacks(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)

        assert missing_archives(prefs3, snapshot, {"Never Seen"}) == ()

    def test_empty_without_a_snapshot(self, tmp_path, prefs3):
        assert missing_archives(prefs3, tmp_path / "nope.xml", {ARCHIVE_NAME}) == ()


class TestReinject:
    def test_adds_only_missing_archives(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)
        # The engine stripped KazBars; Position survived but has since moved.
        stripped = STOCK_PREFS3.replace(
            '    <Archive name="KazBars settings">\n'
            '        <Double name="g0_x" value="623.000000" />\n'
            '        <Double name="g0_y" value="1126.000000" />\n'
            '    </Archive>\n', ''
        ).replace('value="10.000000"', 'value="99.000000"')
        _write(prefs3, stripped)

        added = reinject_archives(prefs3, snapshot, {ARCHIVE_NAME, "Position"})

        text = _read(prefs3)
        assert added == (ARCHIVE_NAME,)
        assert '<Double name="g0_x" value="623.000000" />' in text
        assert 'value="99.000000"' in text      # the live Position is untouched
        assert text.count('<Archive name="Position"') == 1
        assert text.index('</Root>') > text.index('g0_x')

    def test_no_op_when_nothing_is_missing(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)
        before = prefs3.read_bytes()

        assert reinject_archives(prefs3, snapshot, {ARCHIVE_NAME}) == ()
        assert prefs3.read_bytes() == before

    def test_no_op_without_a_snapshot(self, tmp_path, prefs3):
        before = prefs3.read_bytes()

        assert reinject_archives(prefs3, tmp_path / "nope.xml", {ARCHIVE_NAME}) == ()
        assert prefs3.read_bytes() == before

    def test_skips_names_the_snapshot_lacks(self, tmp_path, prefs3):
        snapshot = tmp_path / "snapshot.xml"
        _write(snapshot, STOCK_PREFS3)

        assert reinject_archives(prefs3, snapshot, {"Never Seen"}) == ()


# =========================================================================== #
# create_game_desktop_link                                                    #
# =========================================================================== #

class _FakeRun:
    """Stand-in for subprocess.run that records the call and reports success."""

    def __init__(self, returncode=0, stdout="C:\\Users\\k\\Desktop\\Age of Conan (DX10).lnk"):
        self.returncode = returncode
        self.stdout = stdout
        self.call = None

    def __call__(self, argv, **kwargs):
        self.call = (argv, kwargs)
        return subprocess.CompletedProcess(argv, self.returncode,
                                           stdout=self.stdout, stderr="")


@pytest.fixture
def game_with_exes(tmp_path):
    # An apostrophe and non-ASCII characters — fatal if these ever reached a
    # PowerShell command string instead of the environment.
    game = tmp_path / "Jörg's Ægis"
    (game / "Data" / "Gui" / "Default").mkdir(parents=True)
    for name in ("AgeOfConan.exe", "AgeOfConanDX10.exe"):
        (game / name).write_bytes(b'MZ')
    return game


class TestDesktopLink:
    def test_spawn_shape(self, game_with_exes, monkeypatch):
        fake = _FakeRun()
        monkeypatch.setattr(subprocess, 'run', fake)

        ok, msg = create_game_desktop_link(game_with_exes, 'AgeOfConanDX10.exe')

        argv, kwargs = fake.call
        assert ok is True
        assert msg.endswith("Age of Conan (DX10).lnk")
        assert isinstance(argv, list) and argv[0] == 'powershell'
        assert 'shell' not in kwargs
        assert kwargs['timeout'] == 15
        assert kwargs['creationflags'] == CREATE_NO_WINDOW

    def test_passes_paths_through_the_environment(self, game_with_exes, monkeypatch):
        fake = _FakeRun()
        monkeypatch.setattr(subprocess, 'run', fake)

        create_game_desktop_link(game_with_exes, 'AgeOfConanDX10.exe')

        argv, kwargs = fake.call
        env = kwargs['env']
        assert env['KAZBARS_LINK_TARGET'] == str(game_with_exes / 'AgeOfConanDX10.exe')
        assert env['KAZBARS_LINK_DIR'] == str(game_with_exes)
        assert env['KAZBARS_LINK_NAME'] == "Age of Conan (DX10).lnk"
        # The awkward characters live in the environment, never in the script.
        assert str(game_with_exes) not in argv[-1]

    def test_dx9_name(self, game_with_exes, monkeypatch):
        fake = _FakeRun()
        monkeypatch.setattr(subprocess, 'run', fake)

        create_game_desktop_link(game_with_exes, 'AgeOfConan.exe')

        assert fake.call[1]['env']['KAZBARS_LINK_NAME'] == "Age of Conan (DX9).lnk"

    def test_missing_exe(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, 'run', lambda *a, **k: called.append(a))

        ok, msg = create_game_desktop_link(tmp_path, 'AgeOfConanDX10.exe')

        assert ok is False
        assert "isn't in this game folder" in msg
        assert called == []

    def test_powershell_failure(self, game_with_exes, monkeypatch):
        monkeypatch.setattr(subprocess, 'run', _FakeRun(returncode=1, stdout=""))

        ok, msg = create_game_desktop_link(game_with_exes, 'AgeOfConanDX10.exe')

        assert ok is False
        assert "Could not create the shortcut" in msg

    def test_spawn_error(self, game_with_exes, monkeypatch):
        def boom(*a, **k):
            raise OSError("powershell missing")
        monkeypatch.setattr(subprocess, 'run', boom)

        ok, msg = create_game_desktop_link(game_with_exes, 'AgeOfConanDX10.exe')

        assert ok is False
        assert "powershell missing" in msg
