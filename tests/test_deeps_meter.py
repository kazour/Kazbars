"""Smoke tests for kazbars.deeps_meter.

What we test in isolation:
  - `newest_combat_log` file selection
  - `MeterSnapshot.empty()` shape + `Status` enum
  - `DeepsMeter._process_line` correctly dispatches to all four parsers
    and respects the `include_pet_damage` toggle
  - `DeepsMeter` start/stop lifecycle without spawning real file I/O
    (uses a non-existent game folder so the worker just sits in NOT_STARTED)
  - End-to-end integration: write to a held-open file in a tmp dir, the
    meter should reach `Status.TAILING`

What we DON'T test here (covered by manual smoke or earlier suites):
  - `aoc_is_foreground()` — requires a real foreground window
  - `is_live()` — Windows API integration; covered by the integration test
    indirectly (the held-open file makes is_live return True)
  - Full rate computations — covered by tests/test_deeps_trackers.py

Run: `pytest tests/test_deeps_meter.py` (from repo root).
"""

import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from kazbars.deeps_meter import (
    DeepsMeter,
    MeterSnapshot,
    Status,
    newest_combat_log,
)

# =========================================================================== #
# newest_combat_log                                                           #
# =========================================================================== #

class TestNewestCombatLog:
    def test_empty_folder(self, tmp_path: Path) -> None:
        assert newest_combat_log(tmp_path) is None

    def test_missing_folder(self, tmp_path: Path) -> None:
        assert newest_combat_log(tmp_path / "does_not_exist") is None

    def test_single_match(self, tmp_path: Path) -> None:
        p = tmp_path / "CombatLog-2026-05-17_2057.txt"
        p.write_text("")
        assert newest_combat_log(tmp_path) == p

    def test_picks_newest_by_mtime(self, tmp_path: Path) -> None:
        older = tmp_path / "CombatLog-2026-05-01_1200.txt"
        older.write_text("")
        time.sleep(0.05)  # ensure distinct mtimes on FAT-resolution clocks
        newer = tmp_path / "CombatLog-2026-05-17_2057.txt"
        newer.write_text("")
        assert newest_combat_log(tmp_path) == newer

    def test_filters_non_matching_names(self, tmp_path: Path) -> None:
        (tmp_path / "settings.json").write_text("")
        (tmp_path / "CombatLog.bak").write_text("")  # wrong extension
        (tmp_path / "notes.txt").write_text("")
        log = tmp_path / "CombatLog-XYZ.txt"
        log.write_text("")
        assert newest_combat_log(tmp_path) == log

    def test_ignores_directories(self, tmp_path: Path) -> None:
        (tmp_path / "CombatLog-dir.txt").mkdir()
        log = tmp_path / "CombatLog-real.txt"
        log.write_text("")
        assert newest_combat_log(tmp_path) == log


# =========================================================================== #
# Status + MeterSnapshot                                                      #
# =========================================================================== #

def test_status_enum_values() -> None:
    """Sanity: the four statuses we expect are defined."""
    assert {s.value for s in Status} == {
        "not_started",
        "waiting_for_log",
        "old_log",
        "tailing",
    }


def test_meter_snapshot_empty() -> None:
    s = MeterSnapshot.empty()
    assert s.dps is None
    assert s.dpis is None
    assert s.hps is None
    assert s.hps_out is None
    assert s.status is Status.NOT_STARTED
    assert s.log_filename is None


def test_meter_snapshot_is_frozen() -> None:
    s = MeterSnapshot.empty()
    with pytest.raises((AttributeError, Exception)):
        s.dps = 999.0  # type: ignore[misc]


# =========================================================================== #
# DeepsMeter._process_line                                                    #
# =========================================================================== #

class TestProcessLine:
    """Drive the dispatcher directly; verify the right trackers see records.

    Reaches into private state to confirm — this is an internal contract
    test, not a public API surface.
    """

    def test_outgoing_damage_recorded(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Strike hits Arbanus for 105.")
        # Window should have one event.
        assert len(m._out_tracker._window._events) == 1
        assert m._out_tracker._window._events[0] == (1.0, 105)

    def test_incoming_damage_recorded(self) -> None:
        m = DeepsMeter()
        m._process_line(2.0, "The King of Winter hits you for 1500 crushing damage.")
        assert len(m._in_tracker._window._events) == 1
        assert m._in_tracker._window._events[0] == (2.0, 1500)

    def test_heal_recorded_to_correct_bucket(self) -> None:
        m = DeepsMeter()
        m._process_line(3.0, "Your Health Potion Effect 10 heals you for 70.")
        # Potion bucket should be populated.
        assert len(m._heals_tracker._potion._events) == 1
        assert len(m._heals_tracker._spell._events) == 0

    def test_pet_damage_dropped_when_toggle_off(self) -> None:
        m = DeepsMeter()
        # Default: include_pet_damage = False
        m._process_line(4.0, "Your Cacodemon's Hellfire hits Boss for 1500.")
        assert len(m._out_tracker._window._events) == 0  # not recorded

    def test_pet_damage_recorded_when_toggle_on(self) -> None:
        m = DeepsMeter()
        m.set_include_pet_damage(True)
        m._process_line(4.0, "Your Cacodemon's Hellfire hits Boss for 1500.")
        assert len(m._out_tracker._window._events) == 1
        assert m._out_tracker._window._events[0] == (4.0, 1500)

    def test_team_mate_pet_dropped_even_when_toggle_on(self) -> None:
        """Bare (no 'Your') same-kind pet is a team-mate's — never counted."""
        m = DeepsMeter()
        m.set_include_pet_damage(True)
        m._process_line(4.0, "Cacodemon's Hellfire hits Boss for 1500.")
        assert len(m._out_tracker._window._events) == 0

    def test_non_matching_line_no_writes(self) -> None:
        m = DeepsMeter()
        m._process_line(5.0, "Some random emote chatter line.")
        assert len(m._out_tracker._window._events) == 0
        assert len(m._in_tracker._window._events) == 0

    def test_outgoing_heal_to_player_recorded(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Wave of Life (Rank 6) heals Zarse for 384.")
        assert len(m._heals_out_tracker._window._events) == 1
        assert m._heals_out_tracker._window._events[0] == (1.0, 384)

    def test_outgoing_heal_to_self_not_recorded(self) -> None:
        """`heals you for N` is HPS-in territory, not HPS-out."""
        m = DeepsMeter()
        m._process_line(1.0, "Your Wave of Life (Rank 6) heals you for 115.")
        assert len(m._heals_out_tracker._window._events) == 0
        # And it DOES go through the incoming-heal parser.
        assert len(m._heals_tracker._spell._events) == 1

    def test_outgoing_heal_to_own_pet_not_recorded(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Life of Set (Rank 6) heals Your Idol of Set for 192.")
        assert len(m._heals_out_tracker._window._events) == 0

    def test_outgoing_heal_to_others_pet_not_recorded(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Wave of Life (Rank 6) heals Zarse's Life-stealer for 384.")
        assert len(m._heals_out_tracker._window._events) == 0

    def test_known_mob_filter_rejects_bubble_boss_heal(self) -> None:
        """After you damage a mob, subsequent bubble-heal lines on it are filtered."""
        m = DeepsMeter()
        # Hit the boss → adds "Lady Zelandra" to known_mobs.
        m._process_line(1.0, "Your Storm Crown hits Lady Zelandra for 41 electrical damage.")
        assert "Lady Zelandra" in m._known_mobs
        # Bubble-heal line — should NOT be recorded.
        m._process_line(2.0, "Your Lightning Arc critically healed Lady Zelandra for 129.")
        assert len(m._heals_out_tracker._window._events) == 0

    def test_known_mob_filter_via_pet_damage(self) -> None:
        """Own-pet hits also populate known_mobs (regardless of pet-damage toggle)."""
        m = DeepsMeter()
        # Own pet hits the boss — known_mobs gains the target even though pet
        # damage isn't recorded into _out_tracker (toggle is off).
        m._process_line(1.0, "Your Cacodemon's Hellfire hits Boss for 1500.")
        assert "Boss" in m._known_mobs
        assert len(m._out_tracker._window._events) == 0  # toggle off
        # Now any heal line targeting "Boss" is filtered.
        m._process_line(2.0, "Your Some Heal heals Boss for 50.")
        assert len(m._heals_out_tracker._window._events) == 0

    def test_outgoing_heal_player_not_filtered_when_unrelated_mob_known(self) -> None:
        """Known-mob filter is name-specific — other targets pass through."""
        m = DeepsMeter()
        m._process_line(1.0, "Your Storm Crown hits Lady Zelandra for 41 electrical damage.")
        m._process_line(2.0, "Your Wave of Life (Rank 6) heals Zarse for 384.")
        assert len(m._heals_out_tracker._window._events) == 1
        assert m._heals_out_tracker._window._events[0] == (2.0, 384)

    def test_known_mobs_cleared_on_reset(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Strike hits Arbanus for 105.")
        assert "Arbanus" in m._known_mobs
        m._reset_for_log_boundary()
        assert m._known_mobs == set()


# =========================================================================== #
# Configurable rolling window                                                 #
# =========================================================================== #

class TestWindowSeconds:
    def test_default_window_is_five(self) -> None:
        m = DeepsMeter()
        assert m._window_seconds == 5.0
        assert m._out_tracker._window_seconds == 5.0

    def test_set_window_recreates_trackers_at_new_width(self) -> None:
        m = DeepsMeter()
        old = m._out_tracker
        m.set_window_seconds(13)
        assert m._window_seconds == 13.0
        assert m._out_tracker is not old  # fresh instance
        for tracker_window in (
            m._out_tracker._window_seconds,
            m._in_tracker._window_seconds,
            m._heals_out_tracker._window_seconds,
        ):
            assert tracker_window == 13.0

    def test_set_window_clears_in_flight_state(self) -> None:
        m = DeepsMeter()
        m._process_line(1.0, "Your Strike hits Arbanus for 105.")
        assert len(m._out_tracker._window._events) == 1
        assert "Arbanus" in m._known_mobs
        m.set_window_seconds(7)
        assert len(m._out_tracker._window._events) == 0
        assert m._known_mobs == set()

    def test_set_window_same_value_is_noop(self) -> None:
        m = DeepsMeter()
        old = m._out_tracker
        m.set_window_seconds(5)  # already 5.0
        assert m._out_tracker is old  # not recreated


# =========================================================================== #
# Lifecycle (no real file I/O)                                                #
# =========================================================================== #

class TestLifecycle:
    def test_initial_snapshot_is_empty(self) -> None:
        m = DeepsMeter()
        assert m.snapshot() == MeterSnapshot.empty()
        assert m.is_running() is False

    def test_start_with_missing_folder_sets_not_started(self) -> None:
        """A nonexistent game folder → status sticks at NOT_STARTED."""
        m = DeepsMeter()
        m.start("Z:/does_not_exist_98765")
        try:
            assert m.is_running() is True
            time.sleep(0.6)  # let the loop tick at least once
            s = m.snapshot()
            assert s.status is Status.NOT_STARTED
        finally:
            m.stop(timeout=1.0)

    def test_start_with_empty_folder_sets_waiting(self, tmp_path: Path) -> None:
        m = DeepsMeter()
        m.start(tmp_path)
        try:
            time.sleep(0.5)
            s = m.snapshot()
            assert s.status is Status.WAITING_FOR_LOG
        finally:
            m.stop(timeout=1.0)

    def test_stop_returns_to_empty_snapshot(self, tmp_path: Path) -> None:
        m = DeepsMeter()
        m.start(tmp_path)
        time.sleep(0.3)
        m.stop(timeout=1.0)
        assert m.is_running() is False
        assert m.snapshot() == MeterSnapshot.empty()

    def test_double_start_is_noop(self, tmp_path: Path) -> None:
        m = DeepsMeter()
        m.start(tmp_path)
        try:
            t1 = m._thread
            m.start(tmp_path)  # already running → no-op
            assert m._thread is t1  # same thread, not replaced
        finally:
            m.stop(timeout=1.0)

    def test_stop_when_not_running_is_safe(self) -> None:
        m = DeepsMeter()
        m.stop()  # never started — must not raise

    def test_log_boundary_marks_resume_from_start(self) -> None:
        """A boundary re-tail reads from the top (fresh session content);
        everything else attaches at EOF so history is never replayed."""
        m = DeepsMeter()
        assert m._resume_from_start is False
        m._reset_for_log_boundary()
        assert m._resume_from_start is True

    def test_start_clears_resume_flag(self, tmp_path: Path) -> None:
        """A restart must attach at EOF even if a boundary flag was left set."""
        m = DeepsMeter()
        m._resume_from_start = True
        m.start(tmp_path)
        try:
            assert m._resume_from_start is False
        finally:
            m.stop(timeout=1.0)

    def test_old_log_detected(self, tmp_path: Path) -> None:
        """A CombatLog file no one is writing → Status.OLD_LOG."""
        log = tmp_path / "CombatLog-stale.txt"
        log.write_text("some old content\n", encoding="utf-8")

        m = DeepsMeter()
        m.start(tmp_path)
        try:
            # Give the loop time to scan, probe is_live (fails → stale), and update state.
            time.sleep(0.5)
            s = m.snapshot()
            assert s.status is Status.OLD_LOG
            assert s.log_filename == "CombatLog-stale.txt"
        finally:
            m.stop(timeout=1.0)


# =========================================================================== #
# Integration: a held-open file should look "live" and reach TAILING          #
# =========================================================================== #

@contextmanager
def _held_open(log: Path):
    """Hold `log` open for append from another thread the way AoC would —
    Python's open() on Windows shares FILE_SHARE_READ (not exclusive), enough
    to make the exclusive-share is_live probe fail, i.e. read as "live".
    Yields the append handle; releases it and joins the thread on exit."""
    holder: dict[str, object] = {}
    done = threading.Event()

    def hold():
        # 'a' mode keeps the file open for append without truncating.
        holder["f"] = open(log, "a", encoding="utf-8")
        done.wait()
        holder["f"].close()

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1.0
    while "f" not in holder and time.monotonic() < deadline:
        time.sleep(0.02)
    assert "f" in holder, "holder thread didn't open the file in time"
    try:
        yield holder["f"]
    finally:
        done.set()
        thread.join(timeout=1.0)


def _wait_for_tailing(meter: DeepsMeter, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if meter.snapshot().status is Status.TAILING:
            return
        time.sleep(0.05)
    pytest.fail(f"Meter never reached TAILING (last status: {meter.snapshot().status})")


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="is_live() uses Windows CreateFile semantics; integration "
    "test only meaningful on Windows.",
)
def test_tailing_reached_with_held_open_file(tmp_path: Path) -> None:
    """End-to-end: Python `open()` on Windows holds the file with FILE_SHARE_READ
    (not exclusive), which is enough to make our exclusive-share probe fail —
    indistinguishable from AoC holding it. The meter should reach TAILING."""
    log = tmp_path / "CombatLog-live.txt"
    log.write_text("", encoding="utf-8")

    with _held_open(log):
        meter = DeepsMeter()
        meter.start(tmp_path)
        try:
            # The meter scans, sees the file, probes is_live (fails because
            # we hold the file → "live"), opens its own read handle, sits in
            # tail_file. Give it time to settle.
            _wait_for_tailing(meter)
            assert meter.snapshot().log_filename == "CombatLog-live.txt"
        finally:
            meter.stop(timeout=1.0)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="is_live() uses Windows CreateFile semantics; integration "
    "test only meaningful on Windows.",
)
def test_attach_skips_preexisting_content(tmp_path: Path) -> None:
    """A mid-session Start must not replay the log's existing content into the
    trackers (it would read as a huge false rate spike once warm-up clears);
    lines appended after the attach are still picked up."""
    log = tmp_path / "CombatLog-live.txt"
    log.write_text("Your Strike hits Arbanus for 105.\n" * 50, encoding="utf-8")

    with _held_open(log) as f:
        meter = DeepsMeter()
        meter.start(tmp_path)
        try:
            _wait_for_tailing(meter)

            # Give the tail loop a beat: the 50 pre-existing hits must be skipped.
            time.sleep(0.3)
            assert len(meter._out_tracker._window._events) == 0

            # A line appended after the attach IS parsed.
            f.write("Your Strike hits Arbanus for 105.\n")
            f.flush()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if len(meter._out_tracker._window._events) == 1:
                    break
                time.sleep(0.05)
            assert len(meter._out_tracker._window._events) == 1
        finally:
            meter.stop(timeout=1.0)
