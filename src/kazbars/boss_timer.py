"""
Boss Timer Module for KazBars
Core timing logic for Ethram-Fal seed cycle phases.

Decoupled from UI - receives update_callback to push display data.
"""

import logging
import threading
import time

from .live_tracker_settings import COLORS

logger = logging.getLogger(__name__)

# =============================================================================
# ETHRAM-FAL SEED CYCLE TIMING CONSTANTS (seconds)
# =============================================================================
SEED_DURATION = 7           # How long the seed debuff lasts
FIXATION_DELAY = 4          # Seconds after seed before fixation appears
SEED_ACTIVE_END = 10        # End of seed active display phase
SILENCE_START = 14          # Wait-for-silence phase ends here (countdown from 15)
SILENCE_COUNTDOWN = 15      # Silence countdown target
BRING_SCORP_END = 18        # "Bring Scorpion to the pile" message ends here
KILL_WINDOW_START = 31      # Kill window opens
URGENCY_START = 33          # Urgency escalation starts (! marks)
KILL_WINDOW_END = 36        # Kill window urgency ramps up
CYCLE_DURATION = 39         # Full cycle duration
NEW_SEED_WARNING = 5        # Show "New Seed in X" when <= this many seconds remain

# Double-seed detection bounds
DOUBLE_SEED_MIN_GAP = 5
DOUBLE_SEED_MAX_GAP = 12
DOUBLE_SEED_END = 14        # Second seed active until this time

# First-seed-only detection threshold
FIRST_SEED_THRESHOLD = 6    # If no fixation after this many seconds, it's first-seed

# Kill window alert threshold
KILL_ALERT_THRESHOLD = 28   # Switch to alert color when elapsed >= this


class BossTimer:
    """
    Tracks the 39-second Ethram-Fal seed cycle and calculates phase display data.

    Usage:
        timer = BossTimer(update_callback=overlay.update_display)
        timer.start_cycle("PlayerName")
        # Call update_display() every 50ms in a game loop
    """

    def __init__(self, update_callback=None):
        """
        Initialize the boss timer.

        Args:
            update_callback: Function to call with display data. Signature:
                callback(row1_msg, row1_player, row1_timer, row1_color,
                        row2_msg, row2_player, row2_timer, row2_color, cycle_timer)
        """
        self._update_callback = update_callback
        self._lock = threading.Lock()

        # Core state
        self.timer_active = False
        self.cycle_start_time = None
        self.seed_player = None
        self.fixation_player = None
        self.seed_detected = False
        self.fixation_detected = False

        # Special mechanics
        self.syphon_active = False
        self.double_seed_mode = False
        self.second_seed_active = False

    def start_cycle(self, player_name):
        """
        Start a new seed cycle for the given player.
        Detects double-seed (P4) if called 5-12s after previous seed.
        """
        current_time = time.time()

        with self._lock:
            self.syphon_active = False

            # Check for double seed (P4 mechanic)
            if (self.timer_active and
                self.cycle_start_time is not None and
                self.seed_player == player_name):

                elapsed = current_time - self.cycle_start_time
                if DOUBLE_SEED_MIN_GAP <= elapsed <= DOUBLE_SEED_MAX_GAP:
                    self.double_seed_mode = True
                    self.second_seed_active = True
                    return

            # New cycle - reset state
            self.timer_active = True
            self.cycle_start_time = current_time
            self.seed_player = player_name
            self.fixation_player = None
            self.seed_detected = True
            self.fixation_detected = False
            self.second_seed_active = False
            self.double_seed_mode = False

    def stop_cycle(self):
        """Stop the current cycle and reset to waiting state."""
        with self._lock:
            self.timer_active = False
            self.cycle_start_time = None
            self.seed_player = None
            self.fixation_player = None
            self.seed_detected = False
            self.fixation_detected = False
            self.second_seed_active = False
            self.double_seed_mode = False
            self.syphon_active = False

        self.push_waiting_state()

    def start_syphon(self):
        """Boss is using syphon attack - interrupt timer."""
        with self._lock:
            self.syphon_active = True
            self.timer_active = False
            self.cycle_start_time = None

    def update_fixation(self, player_name):
        """Record the fixation target."""
        with self._lock:
            self.fixation_detected = True
            self.fixation_player = player_name

    def get_current_phase(self):
        """
        Calculate and return current phase display data.

        Returns:
            dict with keys: row1_msg, row1_player, row1_timer, row1_color,
                           row2_msg, row2_player, row2_timer, row2_color, cycle_timer
            None if no active display needed
        """
        with self._lock:
            # Syphon phase overrides everything
            if self.syphon_active:
                return {
                    'row1_msg': "Avoid the clouds", 'row1_player': "",
                    'row1_timer': "", 'row1_color': COLORS["alert"],
                    'row2_msg': "", 'row2_player': "",
                    'row2_timer': "", 'row2_color': COLORS["default"],
                    'cycle_timer': ""
                }

            if not self.timer_active or self.cycle_start_time is None:
                return None

            elapsed = time.time() - self.cycle_start_time

            # Cycle complete — reset inline under the same lock to prevent
            # start_cycle() from sneaking in between lock release and stop_cycle()
            if elapsed >= CYCLE_DURATION:
                self.timer_active = False
                self.cycle_start_time = None
                self.seed_player = None
                self.fixation_player = None
                self.seed_detected = False
                self.fixation_detected = False
                self.second_seed_active = False
                self.double_seed_mode = False
                cycle_completed = True
            else:
                cycle_completed = False
                elapsed_int = int(elapsed)
                timer_text = f"{elapsed_int}s"

                is_first_seed = elapsed_int > FIRST_SEED_THRESHOLD and not self.fixation_detected
                is_double_seed = self.double_seed_mode
                second_seed_active = self.second_seed_active

                seed_detected = self.seed_detected
                fixation_detected = self.fixation_detected
                seed_player = self.seed_player
                fixation_player = self.fixation_player

        if cycle_completed:
            self.push_waiting_state()
            return None

        # Determine which phase we're in
        if is_double_seed:
            return self._get_double_seed_phase(
                elapsed_int, timer_text, seed_player, fixation_player,
                fixation_detected, second_seed_active
            )

        if is_first_seed:
            return self._get_first_seed_phase(
                elapsed_int, timer_text, seed_detected, seed_player
            )

        if elapsed_int < BRING_SCORP_END + 1:
            return self._get_seed_fixation_phase(
                elapsed_int, timer_text, seed_detected, fixation_detected,
                seed_player, fixation_player
            )

        return self._get_dps_kill_phase(elapsed_int, timer_text)

    def update_display(self):
        """
        Get current phase and push to callback.
        Call this every 50ms in the game loop.
        """
        phase = self.get_current_phase()
        if phase and self._update_callback:
            self._update_callback(
                row1_msg=phase.get('row1_msg', ''),
                row1_player=phase.get('row1_player', ''),
                row1_timer=phase.get('row1_timer', ''),
                row1_color=phase.get('row1_color', COLORS["default"]),
                row2_msg=phase.get('row2_msg', ''),
                row2_player=phase.get('row2_player', ''),
                row2_timer=phase.get('row2_timer', ''),
                row2_color=phase.get('row2_color', COLORS["default"]),
                cycle_timer=phase.get('cycle_timer', '')
            )

    def push_waiting_state(self):
        """Push the idle/waiting display state."""
        if self._update_callback:
            self._update_callback(
                row1_msg="Waiting for Seed...", row1_player="", row1_timer="",
                row1_color=COLORS["default"], row2_msg="", row2_player="",
                row2_timer="", row2_color=COLORS["default"], cycle_timer=""
            )

    # =========================================================================
    # HELPER: Build phase display dict
    # =========================================================================

    @staticmethod
    def _phase(row1_msg, row1_color, timer_text,
               row1_player="", row1_timer="",
               row2_msg="", row2_player="", row2_timer="",
               row2_color=None):
        """Build a phase display dict with sensible defaults."""
        return {
            'row1_msg': row1_msg, 'row1_player': row1_player,
            'row1_timer': row1_timer, 'row1_color': row1_color,
            'row2_msg': row2_msg, 'row2_player': row2_player,
            'row2_timer': row2_timer,
            'row2_color': row2_color or COLORS["default"],
            'cycle_timer': timer_text
        }

    # =========================================================================
    # PHASE CALCULATION METHODS
    # =========================================================================

    def _get_first_seed_phase(self, elapsed, timer_text, seed_detected, seed_player):
        """First seed without fixation (scorpion soon)."""
        if elapsed <= SEED_DURATION:
            seed_remaining = max(0, SEED_DURATION - elapsed)
            row1_msg = "Seed: " if seed_detected and seed_player else "Seed"
            row1_player = seed_player if seed_detected and seed_player else ""
            row1_timer = f"{int(seed_remaining)}s" if seed_remaining > 0 else "Done"
            return self._phase(row1_msg, COLORS["alert"], timer_text,
                               row1_player=row1_player, row1_timer=row1_timer)

        return self._phase("First Seed - Scorpion Soon", COLORS["warning"], timer_text)

    def _get_seed_fixation_phase(self, elapsed, timer_text, seed_detected,
                                  fixation_detected, seed_player, fixation_player):
        """Normal seed + fixation cycle phases."""
        if elapsed <= SEED_ACTIVE_END:
            return self._phase_seed_active(
                elapsed, timer_text, seed_player, fixation_detected, fixation_player)

        if elapsed <= SILENCE_START:
            return self._phase_wait_silence(elapsed, timer_text, fixation_player)

        return self._phase_dps_scorpion(timer_text)

    def _phase_seed_active(self, elapsed, timer_text, seed_player,
                           fixation_detected, fixation_player):
        """Seed active phase (0-10s)."""
        seed_remaining = max(0, SEED_DURATION - elapsed)
        row1_msg = "Seed: " if seed_player else "Seed"
        row1_player = seed_player if seed_player else ""
        row1_timer = f"{int(seed_remaining)}s" if seed_remaining > 0 else "Done"

        if fixation_detected:
            fixation_elapsed = elapsed - FIXATION_DELAY
            fixation_remaining = max(0, SEED_DURATION - fixation_elapsed)
            return self._phase(row1_msg, COLORS["alert"], timer_text,
                               row1_player=row1_player, row1_timer=row1_timer,
                               row2_msg="Fix: ",
                               row2_player=fixation_player or "",
                               row2_timer=f"{int(fixation_remaining)}s",
                               row2_color=COLORS["active"])

        return self._phase(row1_msg, COLORS["alert"], timer_text,
                           row1_player=row1_player, row1_timer=row1_timer)

    def _phase_wait_silence(self, elapsed, timer_text, fixation_player):
        """Wait for silence phase (11-14s)."""
        silence_remaining = SILENCE_COUNTDOWN - elapsed
        return self._phase("Wait for Silence", COLORS["active"], timer_text,
                           row1_timer=f"{int(silence_remaining)}s",
                           row2_msg="Fix: ",
                           row2_player=fixation_player or "",
                           row2_timer="Done", row2_color=COLORS["active"])

    def _phase_dps_scorpion(self, timer_text):
        """Silence done, DPS scorpion phase (15-16s)."""
        return self._phase("Wait for Silence", COLORS["active"], timer_text,
                           row1_timer="Done",
                           row2_msg="Bring Scorpion to the pile", row2_color=COLORS["warning"])

    def _get_dps_kill_phase(self, elapsed, timer_text):
        """DPS window and kill scorpion phases."""
        kill_window_in = max(0, KILL_WINDOW_START - elapsed)
        new_seed_in = max(0, CYCLE_DURATION - elapsed)

        if elapsed < KILL_WINDOW_START:
            color = COLORS["alert"] if elapsed >= KILL_ALERT_THRESHOLD else COLORS["warning"]
            return self._phase("Kill window in", color, timer_text,
                               row1_timer=f"{int(kill_window_in)}s",
                               row2_msg="Dps Scorpion to 5%", row2_color=COLORS["warning"])

        if elapsed < KILL_WINDOW_END:
            urgency = "!" * max(0, elapsed - URGENCY_START) if elapsed > URGENCY_START else ""
            row1_timer = f"{int(new_seed_in)}s" if elapsed > URGENCY_START else ""
            return self._phase(f"Kill Scorpion{urgency}", COLORS["alert"], timer_text,
                               row1_timer=row1_timer)

        # Final burn - new seed imminent
        urgency = "!" * (elapsed - URGENCY_START)
        return self._phase(f"Kill Scorpion{urgency}", COLORS["alert"], timer_text,
                           row1_timer=f"{int(new_seed_in)}s",
                           row2_msg=f"New Seed in {int(new_seed_in)}",
                           row2_color=COLORS["warning"])

    def _get_double_seed_phase(self, elapsed, timer_text, seed_player, fixation_player,
                                fixation_detected, second_seed_active):
        """P4 double seed mechanic phases."""
        if elapsed <= SEED_DURATION:
            return self._phase_double_first_seed(
                elapsed, timer_text, seed_player, fixation_player, fixation_detected)

        if elapsed <= DOUBLE_SEED_END:
            return self._phase_double_second_seed(
                elapsed, timer_text, seed_player, fixation_player, fixation_detected)

        return self._phase_double_kite(elapsed, timer_text)

    def _phase_double_first_seed(self, elapsed, timer_text, seed_player,
                                  fixation_player, fixation_detected):
        """P4 first seed phase (0-7s)."""
        seed_remaining = max(0, SEED_DURATION - elapsed)
        row1_msg = "Seed: " if seed_player else "Seed"
        row1_player = seed_player if seed_player else ""

        if fixation_detected and elapsed >= FIXATION_DELAY:
            fixation_elapsed = elapsed - FIXATION_DELAY
            fixation_remaining = max(0, SEED_DURATION - fixation_elapsed)
            return self._phase(row1_msg, COLORS["alert"], timer_text,
                               row1_player=row1_player,
                               row1_timer=f"{int(seed_remaining)}s",
                               row2_msg="Fix: ",
                               row2_player=fixation_player or "",
                               row2_timer=f"{int(fixation_remaining)}s",
                               row2_color=COLORS["active"])

        return self._phase(row1_msg, COLORS["alert"], timer_text,
                           row1_player=row1_player,
                           row1_timer=f"{int(seed_remaining)}s",
                           row2_msg="P4 - Double Seed",
                           row2_color=COLORS["warning"])

    def _phase_double_second_seed(self, elapsed, timer_text, seed_player,
                                   fixation_player, fixation_detected):
        """P4 second seed phase (8-14s)."""
        seed2_remaining = max(0, DOUBLE_SEED_END - elapsed)
        row1_msg = "Seed 2: " if seed_player else "Seed 2"
        row1_player = seed_player if seed_player else ""

        if fixation_detected:
            fixation_elapsed = elapsed - FIXATION_DELAY
            fixation_remaining = max(0, SEED_DURATION - fixation_elapsed)
            fix_timer = f"{int(fixation_remaining)}s" if fixation_remaining > 0 else "Done"
            return self._phase(row1_msg, COLORS["alert"], timer_text,
                               row1_player=row1_player,
                               row1_timer=f"{int(seed2_remaining)}s",
                               row2_msg="Fix: ",
                               row2_player=fixation_player or "",
                               row2_timer=fix_timer,
                               row2_color=COLORS["active"])

        return self._phase(row1_msg, COLORS["alert"], timer_text,
                           row1_player=row1_player,
                           row1_timer=f"{int(seed2_remaining)}s")

    def _phase_double_kite(self, elapsed, timer_text):
        """P4 kite phase (15s+)."""
        new_seed_in = max(0, CYCLE_DURATION - elapsed)

        if new_seed_in <= NEW_SEED_WARNING:
            return self._phase("Kite Scorpions", COLORS["warning"], timer_text,
                               row2_msg=f"New Seed in {int(new_seed_in)}",
                               row2_color=COLORS["alert"])

        return self._phase("Kite Scorpions", COLORS["warning"], timer_text)
