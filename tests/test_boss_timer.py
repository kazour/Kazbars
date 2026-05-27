"""Smoke tests for kazbars.boss_timer.BossTimer.

Covers cycle start/stop, syphon interrupt, double-seed detection, fixation,
the idle-state footer, the update_display dedupe, and the phase state machine
at representative elapsed times. Phase timing is driven by setting
cycle_start_time relative to time.time() rather than sleeping.

Run: `pytest tests/test_boss_timer.py` (from repo root).
"""

import time

from kazbars.boss_timer import CYCLE_DURATION, BossTimer


def _timer_at(elapsed, player="Kaz"):
    """A BossTimer with an active cycle whose elapsed time is `elapsed` seconds,
    landed mid-second so int(elapsed) is stable across the call."""
    t = BossTimer()
    t.start_cycle(player)
    t.cycle_start_time = time.time() - (elapsed + 0.5)
    return t


# =========================================================================== #
# Cycle state transitions                                                     #
# =========================================================================== #

class TestCycleState:
    def test_fresh_timer_has_no_phase(self):
        assert BossTimer().get_current_phase() is None

    def test_start_cycle_activates(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        assert t.timer_active is True
        assert t.seed_player == "Kaz"
        assert t.get_current_phase() is not None

    def test_stop_cycle_resets(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        t.stop_cycle()
        assert t.timer_active is False
        assert t.cycle_start_time is None
        assert t.get_current_phase() is None

    def test_cycle_completes_after_duration(self):
        t = _timer_at(CYCLE_DURATION + 1)
        assert t.get_current_phase() is None
        assert t.timer_active is False  # reset inline once the cycle elapses


# =========================================================================== #
# Syphon interrupt                                                            #
# =========================================================================== #

class TestSyphon:
    def test_syphon_interrupts(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        t.start_syphon()
        assert t.syphon_active is True
        assert t.timer_active is False
        assert t.get_current_phase()["row1_msg"] == "Avoid the clouds"

    def test_start_cycle_clears_syphon(self):
        t = BossTimer()
        t.start_syphon()
        t.start_cycle("Kaz")
        assert t.syphon_active is False
        assert t.timer_active is True


# =========================================================================== #
# Double-seed (P4) detection                                                  #
# =========================================================================== #

class TestDoubleSeed:
    def test_detected_within_gap(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        t.cycle_start_time = time.time() - 7  # within [5, 12]
        t.start_cycle("Kaz")
        assert t.double_seed_mode is True
        assert t.second_seed_active is True

    def test_too_soon_is_new_cycle(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        t.cycle_start_time = time.time() - 2  # below the min gap
        t.start_cycle("Kaz")
        assert t.double_seed_mode is False

    def test_different_player_is_new_cycle(self):
        t = BossTimer()
        t.start_cycle("Kaz")
        t.cycle_start_time = time.time() - 7
        t.start_cycle("Other")
        assert t.double_seed_mode is False
        assert t.seed_player == "Other"


# =========================================================================== #
# Phase calculation                                                           #
# =========================================================================== #

class TestPhases:
    def test_seed_active_shows_player_and_timer(self):
        phase = _timer_at(2).get_current_phase()
        assert phase["row1_player"] == "Kaz"
        assert phase["cycle_timer"] == "2s"

    def test_fixation_adds_second_row(self):
        t = _timer_at(5)
        t.update_fixation("Tank")
        phase = t.get_current_phase()
        assert phase["row2_player"] == "Tank"
        assert "Fix" in phase["row2_msg"]

    def test_first_seed_without_fixation(self):
        # >FIRST_SEED_THRESHOLD with no fixation → first-seed branch.
        assert _timer_at(8).get_current_phase()["row1_msg"] == "First Seed - Scorpion Soon"

    def test_kill_window_after_scorpion_phase(self):
        # Fixation seen (so not first-seed); elapsed past the scorpion phase.
        t = _timer_at(20)
        t.update_fixation("Tank")
        assert t.get_current_phase()["row1_msg"] == "Kill window in"


# =========================================================================== #
# update_display dedupe + idle footer                                         #
# =========================================================================== #

class TestUpdateDisplay:
    def test_dedupes_identical_phase(self):
        calls = []
        t = BossTimer(update_callback=calls.append)
        t.start_cycle("Kaz")
        t.cycle_start_time = time.time() - 2.5
        t.update_display()
        t.update_display()  # same phase → callback fires only once
        assert len(calls) == 1

    def test_waiting_footer_pushes_when_idle(self):
        calls = []
        t = BossTimer(update_callback=calls.append)
        t.set_waiting_footer("CombatLog_2152")
        assert calls
        assert calls[-1]["row2_msg"] == "CombatLog_2152"
