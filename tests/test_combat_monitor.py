"""Smoke tests for kazbars.combat_monitor.CombatLogMonitor.

Covers the log-line trigger dispatch (_process_line → BossTimer), player-name
extraction, latest-log discovery + folder selection on a real tmp folder, and
the start-without-folder guard. The daemon tail loop is exercised manually,
not here.

Run: `pytest tests/test_combat_monitor.py` (from repo root).
"""

import os
import threading
import time

from kazbars.combat_monitor import CombatLogMonitor


class _SpyTimer:
    """Records the BossTimer calls _process_line makes, without the real state
    machine — keeps the dispatch assertions precise."""

    def __init__(self):
        self.calls = []

    def start_cycle(self, player):
        self.calls.append(("start_cycle", player))

    def update_fixation(self, player):
        self.calls.append(("update_fixation", player))

    def start_syphon(self):
        self.calls.append(("start_syphon",))


def _monitor():
    return CombatLogMonitor(_SpyTimer())


# =========================================================================== #
# Trigger dispatch                                                            #
# =========================================================================== #

class TestProcessLine:
    def test_syphon_triggers_start_syphon(self):
        m = _monitor()
        m._process_line("12:00:00 Ethram-Fal's Syphon hits the ground")
        assert m.boss_timer.calls == [("start_syphon",)]

    def test_seed_on_you(self):
        m = _monitor()
        m._process_line("Ethram-Fal afflicts you with Viscous Seed.")
        assert m.boss_timer.calls == [("start_cycle", "YOU")]

    def test_seed_on_named_player(self):
        m = _monitor()
        m._process_line("Ethram-Fal afflicts Kaz with Viscous Seed.")
        assert m.boss_timer.calls == [("start_cycle", "Kaz")]

    def test_fixation_on_named_player(self):
        m = _monitor()
        m._process_line("The Emerald Lotus afflicts Tank with Lotus Fixation.")
        assert m.boss_timer.calls == [("update_fixation", "Tank")]

    def test_unrelated_line_is_ignored(self):
        m = _monitor()
        m._process_line("Kaz hits the dummy for 1234 damage.")
        assert m.boss_timer.calls == []


# =========================================================================== #
# Player extraction                                                           #
# =========================================================================== #

class TestExtractPlayer:
    def test_extracts_between_markers(self):
        m = _monitor()
        assert m._extract_player("X afflicts Bob with Y", "afflicts", "with") == "Bob"


# =========================================================================== #
# Log discovery + folder selection                                            #
# =========================================================================== #

class TestLogDiscovery:
    def test_picks_newest_combatlog(self, tmp_path):
        old = tmp_path / "CombatLog-2026-05-01_1000.txt"
        new = tmp_path / "CombatLog-2026-05-27_2200.txt"
        old.write_text("x")
        new.write_text("y")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        m = _monitor()
        m.log_folder = str(tmp_path)
        assert m._find_latest_log() == str(new)

    def test_ignores_non_combatlogs(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        (tmp_path / "CombatLog-1.txt").write_text("y")
        m = _monitor()
        m.log_folder = str(tmp_path)
        assert m._find_latest_log().endswith("CombatLog-1.txt")

    def test_none_when_empty(self, tmp_path):
        m = _monitor()
        m.log_folder = str(tmp_path)
        assert m._find_latest_log() is None

    def test_set_log_folder_seeks_to_end(self, tmp_path):
        log = tmp_path / "CombatLog-1.txt"
        log.write_text("hello")
        m = _monitor()
        assert m.set_log_folder(str(tmp_path)) == str(log)
        assert m.log_path == str(log)
        assert m.last_position == 5  # tail starts at EOF, not the file's start


# =========================================================================== #
# Start guard                                                                 #
# =========================================================================== #

class TestStartGuard:
    def test_start_without_folder_returns_false(self):
        m = _monitor()
        assert m.start_monitoring() is False
        assert m.monitoring is False


# =========================================================================== #
# Restart                                                                     #
# =========================================================================== #

class TestRestart:
    def test_quick_restart_kills_stale_worker(self, tmp_path):
        """stop_monitoring() → start_monitoring() inside the old worker's scan
        sleep must not leave two threads double-firing the boss timer
        (thread-identity guard): stop never joins, and the restart flips
        `monitoring` back to True before the stale worker wakes."""
        m = _monitor()
        m.set_log_folder(str(tmp_path))  # empty folder → worker sits in the scan sleep
        assert m.start_monitoring()
        time.sleep(0.3)
        m.stop_monitoring()              # no join — the old thread may still sleep
        assert m.start_monitoring()
        try:
            time.sleep(1.5)              # past _SCAN_SLEEP: stale worker wakes, must exit
            alive = [t for t in threading.enumerate()
                     if t.name == "CombatLogMonitor"]
            assert len(alive) == 1
        finally:
            m.stop_monitoring()
