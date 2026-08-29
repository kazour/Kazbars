"""Tests for the pure-file corners of kazbars.game_folder.

Only the parts that touch disk rather than Tk: the Damage Numbers ride-along
that Repair performs, which has to put the mod back after a game patch restored
the stock DamageInfo.swf. The compiler and the bake are monkeypatched — this is
about the decision and the commit, not about MTASC (test_damageinfo_generator.py
covers that). The dialog/toast orchestration around it is exercised manually.

Run: `pytest tests/test_game_folder.py` (from repo root).
"""

import types

from kazbars import build_executor, build_utils, damageinfo_generator, game_folder
from kazbars.build_executor import DAMAGEINFO_BACKUP, DAMAGEINFO_FILE
from kazbars.game_folder import _restore_damageinfo


class _FakeProfileStore:
    def __init__(self, section):
        self._section = section

    def get_section(self, _key):
        return self._section


class _App:
    """The four attributes `_restore_damageinfo` reads off KazBarsApp."""

    def __init__(self, tmp_path, game, *, enabled):
        self.profile_store = _FakeProfileStore({'enabled': enabled})
        self.assets_path = tmp_path / "assets"
        self.app_path = tmp_path / "app"
        self.game_path = str(game)


def _flash(game):
    return game / "Data" / "Gui" / "Default" / "Flash"


def _setup(tmp_path, *, enabled, monkeypatch, compiler=True, bake=(True, "")):
    game = tmp_path / "game"
    _flash(game).mkdir(parents=True)
    (_flash(game) / DAMAGEINFO_FILE).write_bytes(b"STOCK")
    app = _App(tmp_path, game, enabled=enabled)
    (app.assets_path / "damageinfo").mkdir(parents=True)
    (app.assets_path / "damageinfo" / DAMAGEINFO_FILE).write_bytes(b"STOCK")

    monkeypatch.setattr(build_utils, 'find_compiler',
                        lambda _a, _b: tmp_path / "mtasc.exe" if compiler else None)

    def fake_build(_assets, _settings, _compiler, output):
        if bake[0]:
            output.write_bytes(b"MODDED")
        return bake

    monkeypatch.setattr(damageinfo_generator, 'build_damageinfo', fake_build)
    return app, game


class TestRestoreDamageInfo:
    def test_reinstalls_the_mod_when_enabled(self, tmp_path, monkeypatch):
        app, game = _setup(tmp_path, enabled=True, monkeypatch=monkeypatch)

        assert _restore_damageinfo(app) is True
        # The patch left stock behind; Repair puts the mod back...
        assert (_flash(game) / DAMAGEINFO_FILE).read_bytes() == b"MODDED"
        # ...through the same staged path a build uses, so the stock backup
        # exists and holds genuine stock.
        assert (_flash(game) / DAMAGEINFO_BACKUP).read_bytes() == b"STOCK"

    def test_leaves_the_game_file_alone_when_disabled(self, tmp_path, monkeypatch):
        app, game = _setup(tmp_path, enabled=False, monkeypatch=monkeypatch)

        assert _restore_damageinfo(app) is True
        assert (_flash(game) / DAMAGEINFO_FILE).read_bytes() == b"STOCK"
        assert not (_flash(game) / DAMAGEINFO_BACKUP).exists()

    def test_reports_a_missing_compiler(self, tmp_path, monkeypatch):
        app, game = _setup(tmp_path, enabled=True, monkeypatch=monkeypatch,
                           compiler=False)

        # Repair still succeeds overall; the caller turns this into the
        # "run Build & Install to restore Damage Numbers" toast.
        assert _restore_damageinfo(app) is False
        assert (_flash(game) / DAMAGEINFO_FILE).read_bytes() == b"STOCK"

    def test_reports_a_failed_bake(self, tmp_path, monkeypatch):
        app, game = _setup(tmp_path, enabled=True, monkeypatch=monkeypatch,
                           bake=(False, "mtasc exploded"))

        assert _restore_damageinfo(app) is False
        assert (_flash(game) / DAMAGEINFO_FILE).read_bytes() == b"STOCK"

    def test_leaves_no_staging_behind(self, tmp_path, monkeypatch):
        app, game = _setup(tmp_path, enabled=True, monkeypatch=monkeypatch)

        _restore_damageinfo(app)

        assert not list(tmp_path.glob("kazbars_repair_*"))
        assert not list(_flash(game).glob("*.kaztmp"))


class TestUninstallEngineGuard:
    def test_blocks_before_confirm_when_engine_running(self, tmp_path, monkeypatch):
        game = tmp_path / "game"
        game.mkdir()
        app = types.SimpleNamespace(game_path=str(game))

        monkeypatch.setattr(
            build_executor, "get_running_engine_process", lambda: "AgeOfConan.exe")

        def _must_not_run(*a, **kw):
            raise AssertionError("must not run while the engine is up")

        monkeypatch.setattr(game_folder, "confirm", _must_not_run)
        monkeypatch.setattr(build_executor, "uninstall_from_client", _must_not_run)

        game_folder.uninstall_game(app)  # would raise via the stubs above if it got past the gate
