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
    COLORS,
    TIMERS_DEFAULTS,
    get_default_settings,
    load_settings,
    save_settings,
    validate_all_settings,
)
from .settings_manager import get_setting, set_setting
from .timer_overlay import TimerOverlay
from .ui_helpers import (
    BTN_SMALL,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    MODULE_COLORS,
    PAD_BUTTON_GAP,
    PAD_LF,
    PAD_MID,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import add_tooltip, app_toast, create_dialog_header, create_tip_bar
from .window_position import restore_window_position

# Test-cycle timing (ms)
TEST_FIXATION_DELAY_MS = 4000
TEST_RESET_DELAY_MS = 39500
TEST_RESET_POLL_MS = 500


def _migrate_window_position_key():
    """One-time rename of the legacy 'window_pos_boss_timer' key to
    'window_pos_live_tracker' after the module rebrand."""
    legacy = get_setting('window_pos_boss_timer')
    current = get_setting('window_pos_live_tracker')
    if legacy and not current:
        set_setting('window_pos_live_tracker', legacy)


class LiveTrackerPanel(tk.Toplevel):
    """
    Boss Timer child window for KazBars.

    Integrates:
    - Ethram-Fal seed timer overlay
    - Combat log monitoring
    - Overlay controls (lock, transparency, opacity, font)

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
        self.title("Ethram-Fal Seed Timer \u2014 KazBars")
        self.resizable(False, False)

        _migrate_window_position_key()
        restore_window_position(self, 'live_tracker', 460, 470, parent, resizable=False)

        self.settings_folder = str(settings_path)
        self.game_path_getter = game_path_getter

        # Load timer settings
        self.timer_settings = load_settings(self.settings_folder)

        # State
        self.overlay = None
        self._game_loop_id = None
        self._monitoring = False
        self._test_fix_id = None
        self._test_reset_id = None
        self._log_state = "default"

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

        self.protocol("WM_DELETE_WINDOW", self._on_withdraw)

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _dispatch_overlay_update(self, **kwargs):
        """Hand off an overlay update from any thread to the Tk main loop.
        Combat monitoring runs in a background thread; touching tk widgets
        directly from there is unsafe."""
        self.after(0, partial(self._apply_overlay_update, kwargs))

    def _apply_overlay_update(self, kwargs):
        """Apply the queued overlay update on the Tk main thread."""
        if self.overlay:
            self.overlay.update_display(**kwargs)

    def _build_ui(self):
        """Build the panel UI."""
        create_dialog_header(self, "Ethram-Fal Seed Timer", MODULE_COLORS['live_tracker'])
        create_tip_bar(
            self,
            "Tracks the Viscous Seed cycle in real time to help coordinate scorpion kills."
        )

        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=PAD_TAB, pady=PAD_SMALL)

        center_panel = ttk.Frame(main_frame)
        center_panel.pack(anchor='center', fill='y')

        self._build_seed_timer_section(center_panel)
        self._build_overlay_controls(center_panel)

    def _build_seed_timer_section(self, parent):
        """Build seed timer monitoring controls with status display."""
        seed_frame = ttk.LabelFrame(parent, text="Combat Log Monitor")
        seed_frame.configure(padding=PAD_LF)
        seed_frame.pack(fill='x', pady=(0, PAD_LF))

        monitor_frame = ttk.Frame(seed_frame)
        monitor_frame.pack(fill='x', pady=(0, PAD_XS))

        self.start_btn = ttk.Button(
            monitor_frame, text="Start Monitoring",
            command=self._start_monitoring,
            bootstyle="success"
        )
        self.start_btn.pack(side='left', padx=(0, PAD_SMALL))
        add_tooltip(self.start_btn, "Start watching the combat log for the Viscous Seed cycle")

        self.stop_btn = ttk.Button(
            monitor_frame, text="Stop Monitoring",
            command=self._stop_monitoring,
            state='disabled'
        )
        self.stop_btn.pack(side='left')
        add_tooltip(self.stop_btn, "Stop watching the combat log")

        self.scan_btn = ttk.Button(
            monitor_frame, text="Scan Log",
            command=self._rescan_log
        )
        self.scan_btn.pack(side='left', padx=(PAD_SMALL, 0))
        add_tooltip(self.scan_btn, "Re-scan for a newer combat log file")

        ttk.Separator(seed_frame, orient='horizontal').pack(fill='x', pady=(PAD_XS, PAD_MID))

        status_frame = ttk.Frame(seed_frame)
        status_frame.pack(fill='x', pady=(0, PAD_BUTTON_GAP))
        ttk.Label(status_frame, text="Monitor:",
                  font=FONT_SMALL, foreground=THEME_COLORS['body']).pack(side='left')
        self.status_label = ttk.Label(status_frame, text="Stopped",
                  font=FONT_SMALL_BOLD, foreground=THEME_COLORS['body'])
        self.status_label.pack(side='left', padx=(PAD_XS, 0))

        self.log_status_label = ttk.Label(seed_frame, text="No game path set",
                  font=FONT_SMALL, foreground=THEME_COLORS['muted'])
        self.log_status_label.pack(anchor='w', pady=(PAD_BUTTON_GAP, 0))

    def _build_overlay_controls(self, parent):
        """Build overlay settings (show/lock/test, transparency, opacity, font)."""
        overlay_frame = ttk.LabelFrame(parent, text="Overlay")
        overlay_frame.configure(padding=PAD_LF)
        overlay_frame.pack(fill='x', pady=(0, PAD_LF))

        btn_row = ttk.Frame(overlay_frame)
        btn_row.pack(fill='x', pady=(0, PAD_MID))

        self.visibility_btn = ttk.Button(
            btn_row, text="Show", command=self._toggle_overlay, width=BTN_SMALL
        )
        self.visibility_btn.pack(side='left', padx=(0, PAD_XS))
        add_tooltip(self.visibility_btn, "Show or hide the seed timer overlay")

        self.lock_btn = ttk.Button(
            btn_row, text="Lock", command=self._toggle_lock, width=BTN_SMALL
        )
        self.lock_btn.pack(side='left', padx=(0, PAD_XS))
        add_tooltip(self.lock_btn, "Lock the overlay so it can't be moved or resized")

        self.test_btn = ttk.Button(
            btn_row, text="Test Cycle", command=self._toggle_test
        )
        self.test_btn.pack(side='left')
        add_tooltip(self.test_btn, "Simulate a full Viscous Seed cycle (~40 s) for visual testing")

        ttk.Separator(overlay_frame, orient='horizontal').pack(fill='x', pady=(PAD_XS, PAD_MID))

        self.transparent_var = tk.BooleanVar(
            value=self.timer_settings.get('transparent_bg', TIMERS_DEFAULTS['transparent_bg'])
        )
        self.transparent_cb = ttk.Checkbutton(
            overlay_frame, text="Transparent background",
            variable=self.transparent_var,
            command=self._toggle_transparent,
            bootstyle="success-round-toggle"
        )
        self.transparent_cb.pack(anchor='w', pady=(0, PAD_MID))
        add_tooltip(self.transparent_cb, "Hide the overlay's background panel; only the text remains visible")

        opacity_row = ttk.Frame(overlay_frame)
        opacity_row.pack(fill='x', pady=(0, PAD_XS))
        ttk.Label(opacity_row, text="Opacity:",
                  font=FONT_SMALL).pack(side='left')
        self.opacity_var = tk.DoubleVar(
            value=self.timer_settings.get('opacity', TIMERS_DEFAULTS['opacity'])
        )
        self.opacity_value_label = ttk.Label(
            opacity_row, text=f"{int(self.opacity_var.get() * 100)}%",
            font=FONT_SMALL, foreground=THEME_COLORS['muted'], width=4, anchor='e'
        )
        self.opacity_value_label.pack(side='right')
        self.opacity_slider = ttk.Scale(
            opacity_row, from_=0.3, to=1.0,
            variable=self.opacity_var,
            orient='horizontal', length=120,
            command=self._on_opacity_change
        )
        self.opacity_slider.pack(side='left', padx=(PAD_SMALL, PAD_XS), fill='x', expand=True)
        add_tooltip(self.opacity_slider, "Overlay opacity (30% = mostly transparent, 100% = solid)")

        font_row = ttk.Frame(overlay_frame)
        font_row.pack(fill='x')
        ttk.Label(font_row, text="Font size:",
                  font=FONT_SMALL).pack(side='left')
        self.font_var = tk.IntVar(
            value=self.timer_settings.get('font_size', TIMERS_DEFAULTS['font_size'])
        )
        self.font_value_label = ttk.Label(
            font_row, text=f"{self.font_var.get()}pt",
            font=FONT_SMALL, foreground=THEME_COLORS['muted'], width=4, anchor='e'
        )
        self.font_value_label.pack(side='right')
        self.font_slider = ttk.Scale(
            font_row, from_=8, to=20,
            variable=self.font_var,
            orient='horizontal', length=120,
            command=self._on_font_change
        )
        self.font_slider.pack(side='left', padx=(PAD_SMALL, PAD_XS), fill='x', expand=True)
        add_tooltip(self.font_slider, "Timer text size in the overlay (8-20 pt)")

    def _create_overlay(self):
        """Create the overlay window."""
        root = self.winfo_toplevel()
        self.overlay = TimerOverlay(
            root,
            self.timer_settings,
            on_settings_changed=self._on_overlay_settings_changed
        )
        # Always show the overlay when the tracker panel is launched,
        # regardless of any previously-saved hidden state. notify=False so
        # this UI nudge doesn't overwrite the persisted visibility preference.
        self.overlay.show(notify=False)
        self.visibility_btn.config(text="Hide")
        self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    # =========================================================================
    # MONITORING LOGIC
    # =========================================================================

    def _update_log_path(self):
        """Update combat log path from current game path."""
        game_path = self.game_path_getter()

        if not game_path:
            self._set_log_status("Set a game folder in the main window first", "no_path")
            return

        if not Path(game_path).exists():
            self._set_log_status(f"Game folder not found: {game_path}", "no_folder")
            return

        latest = self.combat_monitor.set_log_folder(game_path)

        if latest:
            self._set_log_status(f"Found: {Path(latest).name}", "found")
        else:
            self._set_log_status("No combat logs found. Type /logcombat on in game.", "missing")

        self._update_overlay_idle()

    _LOG_STATE_FG = {
        "found":     'success',
        "missing":   'warning',
        "no_path":   'warning',
        "no_folder": 'danger',
        "default":   'muted',
    }

    _LOG_STATE_OVERLAY = {
        "found":     "active",
        "missing":   "warning",
        "no_path":   "warning",
        "no_folder": "alert",
        "default":   "default",
    }

    def _set_log_status(self, text, state):
        """Update the log status label and remember its semantic state."""
        self._log_state = state
        fg_key = self._LOG_STATE_FG.get(state, 'muted')
        self.log_status_label.config(text=text, foreground=THEME_COLORS[fg_key])

    def _update_overlay_idle(self):
        """Push monitor + combat log status to overlay when not actively tracking."""
        if not self.overlay or self._monitoring:
            return

        log_text = self.log_status_label.cget('text')
        log_color = COLORS[self._LOG_STATE_OVERLAY.get(self._log_state, "default")]

        self.overlay.update_display(
            "Monitor: Stopped", "", "", COLORS["default"],
            log_text, "", "", log_color, ""
        )

    def _start_monitoring(self):
        """Start combat log monitoring."""
        self._update_log_path()

        if not self.combat_monitor.log_path:
            app_toast(self, "Can't start: no combat log. Set game path and run /logcombat on", 'warning', 8)
            return

        if self.combat_monitor.start_monitoring():
            self._monitoring = True
            self.status_label.config(text="Running", foreground=THEME_COLORS['success'])
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.test_btn.config(state='disabled')
            self.boss_timer.push_waiting_state()
            self._start_game_loop()
            if self.overlay and not self.overlay.is_visible:
                self.overlay.show()
                self.visibility_btn.config(text="Hide")
        else:
            app_toast(self, "Couldn't start monitoring. Try /logcombat off, then /logcombat on", 'error', 10)

    def _stop_monitoring(self):
        """Stop combat log monitoring."""
        self.combat_monitor.stop_monitoring()
        self.boss_timer.stop_cycle()
        self._monitoring = False
        self._stop_game_loop()
        self.status_label.config(text="Stopped", foreground=THEME_COLORS['body'])
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.test_btn.config(state='normal')
        self._update_log_path()
        self._update_overlay_idle()

    def _rescan_log(self):
        """Manually rescan for a newer combat log file."""
        if not self.combat_monitor.log_folder:
            self._update_log_path()
            return

        latest = self.combat_monitor.rescan_log()
        if latest:
            self._set_log_status(f"Found: {Path(latest).name}", "found")
        else:
            self._set_log_status("No combat logs found. Type /logcombat on in game.", "missing")
        self._update_overlay_idle()

    def _start_game_loop(self):
        """Start the 50ms update loop."""
        self._game_loop_id = self.after(50, self._run_game_tick)

    def _run_game_tick(self):
        """One iteration of the boss-timer update loop. Re-schedules itself."""
        try:
            self.boss_timer.update_display()
        except Exception as e:
            logger.error("Timer loop error: %s", e)
        finally:
            self._game_loop_id = self.after(50, self._run_game_tick)

    def _stop_game_loop(self):
        """Stop the update loop."""
        if self._game_loop_id:
            self.after_cancel(self._game_loop_id)
            self._game_loop_id = None

    # =========================================================================
    # OVERLAY CONTROLS
    # =========================================================================

    def _toggle_overlay(self):
        if self.overlay.is_visible:
            self.overlay.hide()
            self.visibility_btn.config(text="Show")
        else:
            self.overlay.show()
            self.visibility_btn.config(text="Hide")

    def _toggle_lock(self):
        self.overlay.toggle_lock()

    def _toggle_transparent(self):
        self.overlay.set_transparent(self.transparent_var.get())

    def _on_opacity_change(self, value):
        v = float(value)
        if self.overlay:
            self.overlay.set_opacity(v)
        self.opacity_value_label.config(text=f"{int(v * 100)}%")

    def _on_font_change(self, value):
        v = int(float(value))
        if self.overlay:
            self.overlay.set_font_size(v)
        self.font_value_label.config(text=f"{v}pt")

    def _toggle_test(self):
        """Toggle test mode (simulate a seed cycle)."""
        if self.boss_timer.timer_active:
            self.boss_timer.stop_cycle()
            self.test_btn.config(text="Test Cycle")
            self.start_btn.config(state='normal')
            self._stop_game_loop()
            self._cancel_test_callbacks()
        else:
            self._cancel_test_callbacks()
            self.boss_timer.start_cycle("TestPlayer")
            self.test_btn.config(text="Stop Test")
            self.start_btn.config(state='disabled')
            self._start_game_loop()
            if self.overlay and not self.overlay.is_visible:
                self.overlay.show()
                self.visibility_btn.config(text="Hide")
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
            self.start_btn.config(state='normal')
            self._stop_game_loop()
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
        self.transparent_var.set(
            self.timer_settings.get('transparent_bg', TIMERS_DEFAULTS['transparent_bg'])
        )
        opacity = self.timer_settings.get('opacity', TIMERS_DEFAULTS['opacity'])
        self.opacity_var.set(opacity)
        self.opacity_value_label.config(text=f"{int(opacity * 100)}%")
        font_size = self.timer_settings.get('font_size', TIMERS_DEFAULTS['font_size'])
        self.font_var.set(font_size)
        self.font_value_label.config(text=f"{font_size}pt")
        if self.overlay:
            self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")
            self.visibility_btn.config(text="Hide" if self.overlay.is_visible else "Show")

    def _on_withdraw(self):
        """Hide panel and overlay, stop monitoring."""
        if self._monitoring:
            self._stop_monitoring()
        if self.overlay:
            self.overlay.hide()
        self.withdraw()

    def restore_overlay(self):
        """Always show the overlay when the panel is re-opened."""
        if self.overlay:
            self.overlay.show()
            self.visibility_btn.config(text="Hide")

    def cleanup(self):
        """Stop monitoring and save settings. Call before destroying the window."""
        self.combat_monitor.stop_monitoring()
        self._stop_game_loop()
        self._cancel_test_callbacks()
        self.save_settings()
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
