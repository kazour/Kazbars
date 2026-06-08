"""
KazBars — Live Tracker Panel
Boss Timer child window: Ethram-Fal seed timer overlay and combat log monitoring.
"""

import logging
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import ttk

logger = logging.getLogger(__name__)

from .boss_timer import BossTimer
from .combat_monitor import CombatLogMonitor
from .live_tracker_settings import (
    TIMERS_DEFAULTS,
    get_default_settings,
    load_settings,
    sanitize_log_name,
    save_settings,
    validate_all_settings,
)
from .timer_overlay import TimerOverlay
from .ui_forms import (
    create_card,
    create_slider_row,
    create_status_block,
    create_toggle_action_button,
    refresh_toggle_button,
)
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_LARGE,
    BTN_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_MID,
    PAD_SMALL,
    PAD_TAB,
    THEME_COLORS,
)
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

# Game-loop tick (ms) — drives both the schedule cadence and the reschedule.
GAME_TICK_MS = 50

# Header + panel dimensions — width matched to the Deeps panel so the two
# sibling config windows read as a set. Height is provisional: the panel
# auto-tightens to its natural reqheight after _build_ui (resizable=False
# ignores the saved height anyway), so adding controls never clips the bottom.
_HEADER_WIDTH = 440
_PANEL_DEFAULT_WIDTH = 440
_PANEL_PROVISIONAL_HEIGHT = 470

# Test-cycle timing (ms)
TEST_FIXATION_DELAY_MS = 4000
TEST_RESET_DELAY_MS = 39500
TEST_RESET_POLL_MS = 500


class LiveTrackerPanel(tk.Toplevel):
    """
    Boss Timer child window for KazBars.

    Integrates:
    - Ethram-Fal seed timer overlay
    - Combat log monitoring
    - Overlay controls (lock, background opacity, font family, font size)

    Usage:
        panel = LiveTrackerPanel(parent, settings_path, game_path_getter)
        # Close button withdraws; call cleanup() + destroy() on app exit.
    """

    def __init__(self, parent, settings_path, game_path_getter):
        """
        Args:
            parent: Parent Tk window
            settings_path: Path to the settings folder (Path or str)
            game_path_getter: Callable that returns the current AoC game path (str)
        """
        super().__init__(parent)
        self.title("Ethram-Fal Seed Timer - KazBars")
        self.resizable(False, False)
        self.transient(parent)

        restore_window_position(
            self, 'live_tracker', _PANEL_DEFAULT_WIDTH, _PANEL_PROVISIONAL_HEIGHT,
            parent, resizable=False, offset=(48, 40),
        )
        bind_window_position_save(self, 'live_tracker', save_size=False)

        self.settings_folder = str(settings_path)
        self.game_path_getter = game_path_getter

        # Load timer settings
        self.timer_settings = load_settings(self.settings_folder)

        # State
        self.overlay = None
        self._game_loop_id = None
        self._focus_watcher = getattr(parent, "focus_watcher", None)
        self._monitoring = False
        self._test_fix_id = None
        self._test_reset_id = None
        # Full filename of the detected combat log (None when none found) —
        # feeds the single-line _render_status. The sanitized short name goes
        # only to the overlay footer.
        self._latest_log = None

        # Wire timer + monitor first so guards aren't needed downstream.
        # _dispatch_overlay_update hops from the combat-monitor thread to the
        # Tk main loop where the overlay can be touched safely.
        self.boss_timer = BossTimer(update_callback=self._dispatch_overlay_update)
        self.combat_monitor = CombatLogMonitor(self.boss_timer)

        # Build UI, then the overlay (which configures visibility/lock buttons)
        self._build_ui()
        self._create_overlay()

        # Auto-detect log path and push idle status to overlay
        self._update_log_path()

        # Tighten the panel to the natural height of its packed content (mirrors
        # DeepsPanel). resizable=False ignores the saved height, so this is where
        # geometry is locked in; saved-position runs keep their x/y, height only.
        self.update_idletasks()
        self.geometry(f"{_PANEL_DEFAULT_WIDTH}x{self.winfo_reqheight()}")

        self.protocol("WM_DELETE_WINDOW", self._on_withdraw)

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _dispatch_overlay_update(self, phase):
        """Hand off an overlay update from any thread to the Tk main loop.
        Combat monitoring runs in a background thread; touching tk widgets
        directly from there is unsafe."""
        self.after(0, partial(self._apply_overlay_update, phase))

    def _apply_overlay_update(self, phase):
        """Apply the queued overlay update on the Tk main thread."""
        if self.overlay:
            self.overlay.update_display(phase)

    def _build_ui(self):
        """Compose the panel to mirror DeepsPanel: header → tip → status block →
        primary action → Overlay card → Appearance card. The seed-timer's own
        Test Cycle sits where Deeps puts its thresholds/cells."""
        create_dialog_header(
            self, "Ethram-Fal Seed Timer", MODULE_COLORS['live_tracker'], width=_HEADER_WIDTH
        )
        create_tip_bar(
            self,
            "Tracks the Viscous Seed cycle in real time to help coordinate scorpion kills."
        )

        body = ttk.Frame(self, padding=(PAD_TAB, PAD_LF))
        body.pack(fill='both', expand=True)

        self._build_status_block(body)
        self._build_primary_action(body)
        self._build_overlay_controls(body)
        self._build_appearance(body)

    def _build_status_block(self, parent):
        """Single 'Status' label + one colored status line above the Start
        button — the same shape DeepsPanel uses. The line folds monitoring
        state and the detected log into one message (see _render_status)."""
        self.status_label = create_status_block(
            parent, "Status", wraplength=_PANEL_DEFAULT_WIDTH - 2 * PAD_TAB,
        )

    def _build_primary_action(self, parent):
        """Big Start / Stop monitoring toggle — the headline interaction."""
        self.start_btn = create_toggle_action_button(
            parent, self._on_start_stop_click, width=BTN_LARGE,
        )
        self.start_btn.pack(anchor='w', pady=(0, PAD_MID))
        add_tooltip(self.start_btn, "Start or stop watching the combat log for the Viscous Seed cycle")

    def _build_overlay_controls(self, parent):
        """Overlay group card: lock + test-cycle buttons (mirrors Deeps' Overlay
        card, which holds lock + layout). Visibility follows Start/Stop."""
        lf = create_card(parent, "Overlay")
        lf.pack(fill='x', pady=(PAD_SMALL, PAD_MID))

        row = ttk.Frame(lf)
        row.pack(anchor='w', fill='x')

        self.lock_btn = ttk.Button(
            row, text="Lock", command=self._toggle_lock, width=BTN_SMALL,
            bootstyle="secondary",  # type: ignore[call-arg]
        )
        self.lock_btn.pack(side='left', padx=(0, PAD_TAB))
        add_tooltip(self.lock_btn, "Lock the overlay so it can't be moved (unlock here too)")

        self.test_btn = ttk.Button(
            row, text="Test Cycle", command=self._toggle_test,
            bootstyle="secondary",  # type: ignore[call-arg]
        )
        self.test_btn.pack(side='left')
        add_tooltip(self.test_btn, "Simulate a full Viscous Seed cycle (~40 s) for visual testing")

    def _build_appearance(self, parent):
        """Appearance card: size + background sliders, same order as Deeps. Font
        family is fixed to Segoe UI, so there is no font picker."""
        lf = create_card(parent, "Appearance")
        lf.pack(fill='x', pady=(PAD_SMALL, PAD_MID))

        # Size slider 12-48 pt (matches Deeps); the overlay auto-sizes to the font.
        self.font_scale, self.font_value_label = create_slider_row(
            lf, "Size:", 12, 48,
            self.timer_settings.get('font_size', TIMERS_DEFAULTS['font_size']),
            "pt", self._on_font_change, self._on_overlay_settings_changed,
        )

        # Background opacity 0-100 %: 0 = floating text, 100 = solid panel.
        self.bg_opacity_scale, self.bg_opacity_value_label = create_slider_row(
            lf, "Background:", 0, 100,
            round(self.timer_settings.get('bg_opacity', TIMERS_DEFAULTS['bg_opacity']) * 100),
            "%", self._on_bg_opacity_change, self._on_overlay_settings_changed,
        )

    def _create_overlay(self):
        """Create the overlay window (hidden until Start — Hide-on-Stop model)."""
        root = self.winfo_toplevel()
        self.overlay = TimerOverlay(
            root,
            self.timer_settings,
            on_settings_changed=self._on_overlay_settings_changed
        )
        if self._focus_watcher:
            self._focus_watcher.register(self.overlay)
        # Hidden on open — Start shows it, Stop hides it.
        self.overlay.hide(notify=False)
        self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    # =========================================================================
    # MONITORING LOGIC
    # =========================================================================

    def _update_log_path(self):
        """Point the combat monitor at the game folder, refresh the detected
        log name + the overlay's waiting-state footer, then re-render status."""
        game_path = self.game_path_getter()

        if not game_path or not Path(game_path).exists():
            self._latest_log = None
            self.boss_timer.set_waiting_footer("")
            self._render_status()
            return

        latest = self.combat_monitor.set_log_folder(game_path)
        if latest:
            # Full filename for the panel status line (matches Deeps); the
            # sanitized short name is only for the cramped overlay footer.
            self._latest_log = Path(latest).name
            self.boss_timer.set_waiting_footer(sanitize_log_name(latest))
        else:
            self._latest_log = None
            self.boss_timer.set_waiting_footer("Waiting for combat log…")
        self._render_status()

    def _render_status(self):
        """Map (game path, monitoring, detected log) to one colored status line
        — the single-line model DeepsPanel uses, with the same color semantics."""
        game = self.game_path_getter()
        if not game:
            text = "No game folder set in KazBars main window."
            color = THEME_COLORS['danger_text']
        elif not Path(game).exists():
            text = f"Game folder not found: {game}"
            color = THEME_COLORS['danger_text']
        elif not self._monitoring:
            text = "Not monitoring. Click Start to begin."
            color = THEME_COLORS['muted']
        elif self._latest_log:
            text = f"Tailing {self._latest_log}"
            color = THEME_COLORS['success']
        else:
            text = "Waiting for combat log. Type /logcombat on in game."
            color = THEME_COLORS['warning']
        self.status_label.config(text=text, foreground=color)

    def _on_start_stop_click(self):
        if self._monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self):
        """Start combat log monitoring. Logs are auto-detected, so this can
        start before AoC has created today's log (the monitor waits)."""
        self._update_log_path()

        if not self.combat_monitor.start_monitoring():
            app_toast(self, "Can't start: set a game folder in the main window first.", 'warning', 8)
            return

        self._monitoring = True
        self._render_status()
        self._refresh_monitor_button()
        self.test_btn.config(state='disabled')
        self.boss_timer.push_waiting_state()
        self._start_game_loop()
        if self.overlay:
            self.overlay.show()

    def _stop_monitoring(self):
        """Stop combat log monitoring and hide the overlay (Hide-on-Stop)."""
        self.combat_monitor.stop_monitoring()
        self.boss_timer.stop_cycle()
        self._monitoring = False
        self._stop_game_loop()
        self._refresh_monitor_button()
        self.test_btn.config(state='normal')
        if self.overlay:
            self.overlay.hide()
        self._update_log_path()  # re-renders status to the idle line

    def _refresh_monitor_button(self):
        """Sync the Start/Stop toggle label, color, and enabled-state."""
        enabled = bool(self.game_path_getter()) or self._monitoring
        refresh_toggle_button(
            self.start_btn, running=self._monitoring, enabled=enabled,
            disabled_label="Set game folder first",
        )

    def _start_game_loop(self):
        """Start the update loop."""
        self._game_loop_id = self.after(GAME_TICK_MS, self._run_game_tick)

    def _run_game_tick(self):
        """One iteration of the boss-timer update loop. Re-schedules itself."""
        try:
            self.boss_timer.update_display()
            self._sync_monitor_log()
        except Exception as e:
            logger.error("Timer loop error: %s", e)
        finally:
            self._game_loop_id = self.after(GAME_TICK_MS, self._run_game_tick)

    def _sync_monitor_log(self):
        """Reflect the monitor's current log in the status line while monitoring.
        The combat monitor switches to a newer CombatLog in its background thread
        on a new game session; without this the panel would keep showing the log
        found at Start (Deeps stays live because it reads the meter snapshot).
        Change-guarded so it only re-renders on an actual switch."""
        if not self._monitoring:
            return
        current = self.combat_monitor.current_log_path()
        name = Path(current).name if current else None
        if name == self._latest_log:
            return
        self._latest_log = name
        self.boss_timer.set_waiting_footer(sanitize_log_name(current) if current else "")
        self._render_status()

    def _stop_game_loop(self):
        """Stop the update loop."""
        if self._game_loop_id:
            self.after_cancel(self._game_loop_id)
            self._game_loop_id = None

    # =========================================================================
    # OVERLAY CONTROLS
    # =========================================================================

    def _toggle_lock(self):
        self.overlay.toggle_lock()

    def _on_bg_opacity_change(self, value):
        """Live drag: push to overlay + refresh label, no save (commit persists)."""
        pct = round(float(value))
        if self.overlay:
            self.overlay.set_bg_opacity(pct / 100.0, notify=False)
        self.bg_opacity_value_label.config(text=f"{pct}%")

    def _on_font_change(self, value):
        """Live drag: push to overlay + refresh label, no save (commit persists)."""
        v = int(float(value))
        if self.overlay:
            self.overlay.set_font_size(v, notify=False)
        self.font_value_label.config(text=f"{v}pt")

    def _toggle_test(self):
        """Toggle test mode (simulate a seed cycle). Shows the overlay for the
        test, hides it again when the test ends (Hide-on-Stop)."""
        if self.boss_timer.timer_active:
            self.boss_timer.stop_cycle()
            self.test_btn.config(text="Test Cycle")
            self._refresh_monitor_button()
            self._stop_game_loop()
            self._cancel_test_callbacks()
            if self.overlay and not self._monitoring:
                self.overlay.hide()
        else:
            self._cancel_test_callbacks()
            self.boss_timer.start_cycle("TestPlayer")
            self.test_btn.config(text="Stop Test")
            self.start_btn.config(state='disabled')
            self._start_game_loop()
            if self.overlay:
                self.overlay.show()
            self._test_fix_id = self.after(TEST_FIXATION_DELAY_MS,
                                           self._test_trigger_fixation)
            self._test_reset_id = self.after(TEST_RESET_DELAY_MS,
                                             self._test_check_reset)

    def _test_trigger_fixation(self):
        """Test-cycle: inject a fake fixation event after the configured delay."""
        self._test_fix_id = None
        if self.boss_timer.timer_active:
            self.boss_timer.update_fixation("FixPlayer")

    def _test_check_reset(self):
        """Test-cycle: poll for the boss timer returning to idle, then restore
        the panel button states."""
        if not self.boss_timer.timer_active:
            self._test_reset_id = None
            self.test_btn.config(text="Test Cycle")
            self._refresh_monitor_button()
            self._stop_game_loop()
            if self.overlay and not self._monitoring:
                self.overlay.hide()
        else:
            self._test_reset_id = self.after(TEST_RESET_POLL_MS,
                                             self._test_check_reset)

    def _cancel_test_callbacks(self):
        """Cancel any pending test-cycle after() handlers."""
        if self._test_fix_id is not None:
            self.after_cancel(self._test_fix_id)
            self._test_fix_id = None
        if self._test_reset_id is not None:
            self.after_cancel(self._test_reset_id)
            self._test_reset_id = None

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def save_settings(self):
        """Save current overlay settings to disk."""
        if self.overlay:
            settings = self.overlay.get_settings()
            if not save_settings(self.settings_folder, settings):
                logger.warning("Failed to save timer overlay settings")

    def _on_overlay_settings_changed(self):
        """Persist settings and resync the lock button when state changes from the overlay."""
        self.save_settings()
        if self.overlay:
            self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    def get_profile_data(self) -> dict:
        """Get overlay settings dict for embedding in a profile."""
        overlay = self.overlay.get_settings() if self.overlay else dict(self.timer_settings)
        return {'overlay': overlay}

    def load_profile_data(self, config: dict):
        """Load live tracker settings from a profile dict."""
        if not config:
            return
        if 'overlay' in config:
            self.timer_settings = validate_all_settings(config['overlay'])
            if self.overlay:
                self.overlay.apply_settings(self.timer_settings)
            self._sync_overlay_ui()

    def reset_to_defaults(self):
        """Reset all live tracker settings to defaults."""
        self.timer_settings = get_default_settings()
        if self.overlay:
            self.overlay.apply_settings(self.timer_settings)
        self._sync_overlay_ui()

    def refresh_log_path(self):
        """Refresh the combat log path (call when game path changes)."""
        self._update_log_path()

    def _sync_overlay_ui(self):
        """Sync overlay control widgets to current timer_settings."""
        bg_opacity = self.timer_settings.get('bg_opacity', TIMERS_DEFAULTS['bg_opacity'])
        self.bg_opacity_scale.set(round(bg_opacity * 100))
        self.bg_opacity_value_label.config(text=f"{int(bg_opacity * 100)}%")
        font_size = self.timer_settings.get('font_size', TIMERS_DEFAULTS['font_size'])
        self.font_scale.set(font_size)
        self.font_value_label.config(text=f"{font_size}pt")
        if self.overlay:
            self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    def _on_withdraw(self):
        """Hide the panel only — monitoring keeps running so the seed-timer
        overlay stays live during play. Reopen from the bottom-bar button;
        use Stop Monitoring to actually halt tracking. Mirrors Deeps.
        """
        self.withdraw()

    def restore_overlay(self):
        """Re-show the overlay on panel reopen only while monitoring is active
        (Hide-on-Stop — visibility follows Start/Stop)."""
        if self.overlay and self._monitoring:
            self.overlay.show()

    def cleanup(self):
        """Stop monitoring and save settings. Call before destroying the window."""
        self.combat_monitor.stop_monitoring()
        self._stop_game_loop()
        self._cancel_test_callbacks()
        self.save_settings()
        if self.overlay:
            if self._focus_watcher:
                self._focus_watcher.unregister(self.overlay)
            self.overlay.destroy()
            self.overlay = None
