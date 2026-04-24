"""
Kaz Grids — Live Tracker Panel
Boss Timer child window: Ethram-Fal seed timer overlay and combat log monitoring.
"""

import logging
import tkinter as tk
from tkinter import ttk
from ttkbootstrap.dialogs import Messagebox
from pathlib import Path

logger = logging.getLogger(__name__)

from .live_tracker_settings import (
    load_settings, save_settings, get_default_settings, validate_all_settings,
    COLORS,
)
from .boss_timer import BossTimer
from .combat_monitor import CombatLogMonitor
from .timer_overlay import TimerOverlay
from .ui_helpers import (
    THEME_COLORS, FONT_SMALL, FONT_SMALL_BOLD, MODULE_COLORS,
    BTN_SMALL,
    PAD_TAB, PAD_XS, PAD_SMALL, PAD_LF, PAD_BUTTON_GAP, PAD_MID,
)
from .ui_widgets import create_tip_bar, create_dialog_header, add_tooltip
from .window_position import restore_window_position


class LiveTrackerPanel(tk.Toplevel):
    """
    Boss Timer child window for Kaz Grids.

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
        self.title("Ethram-Fal Seed Timer \u2014 Kaz Grids")
        self.resizable(False, False)

        restore_window_position(self, 'boss_timer', 460, 470, parent, resizable=False)

        self.settings_folder = str(settings_path)
        self.game_path_getter = game_path_getter

        # Load timer settings
        self.timer_settings = load_settings(self.settings_folder)

        # State
        self.overlay = None
        self.boss_timer = None
        self.combat_monitor = None
        self._game_loop_id = None
        self._monitoring = False

        # Build UI
        self._build_ui()

        # Create overlay (hidden until user clicks Show)
        self._create_overlay()

        # Wire components — marshal callback to main thread for tkinter safety
        def _thread_safe_update(**kwargs):
            self.after(0, lambda: self.overlay.update_display(**kwargs))

        self.boss_timer = BossTimer(update_callback=_thread_safe_update)
        self.combat_monitor = CombatLogMonitor(self.boss_timer)

        # Auto-detect log path and push idle status to overlay
        self._update_log_path()

        self.protocol("WM_DELETE_WINDOW", self._on_withdraw)

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build the panel UI."""
        create_dialog_header(self, "Ethram-Fal Seed Timer", MODULE_COLORS['grids'])
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

        self.stop_btn = ttk.Button(
            monitor_frame, text="Stop",
            command=self._stop_monitoring, width=BTN_SMALL,
            state='disabled',
            bootstyle="danger"
        )
        self.stop_btn.pack(side='left')

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
                  font=FONT_SMALL_BOLD, foreground=THEME_COLORS['muted'])
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

        self.lock_btn = ttk.Button(
            btn_row, text="Lock", command=self._toggle_lock, width=BTN_SMALL
        )
        self.lock_btn.pack(side='left', padx=(0, PAD_XS))

        self.test_btn = ttk.Button(
            btn_row, text="Test Cycle", command=self._toggle_test
        )
        self.test_btn.pack(side='left')

        ttk.Separator(overlay_frame, orient='horizontal').pack(fill='x', pady=(PAD_XS, PAD_MID))

        self.transparent_var = tk.BooleanVar(value=self.timer_settings.get('transparent_bg', False))
        self.transparent_cb = ttk.Checkbutton(
            overlay_frame, text="Transparent background",
            variable=self.transparent_var,
            command=self._toggle_transparent,
            bootstyle="success-round-toggle"
        )
        self.transparent_cb.pack(anchor='w', pady=(0, PAD_MID))
        add_tooltip(self.transparent_cb, "Make overlay background transparent (click-through when locked)")

        opacity_row = ttk.Frame(overlay_frame)
        opacity_row.pack(fill='x', pady=(0, PAD_XS))
        ttk.Label(opacity_row, text="Opacity:",
                  font=FONT_SMALL).pack(side='left')
        self.opacity_var = tk.DoubleVar(value=self.timer_settings.get('opacity', 0.9))
        self.opacity_slider = ttk.Scale(
            opacity_row, from_=0.3, to=1.0,
            variable=self.opacity_var,
            orient='horizontal', length=120,
            command=self._on_opacity_change
        )
        self.opacity_slider.pack(side='left', padx=(PAD_SMALL, 0), fill='x', expand=True)
        add_tooltip(self.opacity_slider, "Overlay window transparency (30% to 100%)")

        font_row = ttk.Frame(overlay_frame)
        font_row.pack(fill='x')
        ttk.Label(font_row, text="Font size:",
                  font=FONT_SMALL).pack(side='left')
        self.font_var = tk.IntVar(value=self.timer_settings.get('font_size', 11))
        self.font_slider = ttk.Scale(
            font_row, from_=8, to=20,
            variable=self.font_var,
            orient='horizontal', length=120,
            command=self._on_font_change
        )
        self.font_slider.pack(side='left', padx=(PAD_SMALL, 0), fill='x', expand=True)
        add_tooltip(self.font_slider, "Timer text size in the overlay (8-20 pt)")

    def _create_overlay(self):
        """Create the overlay window."""
        root = self.winfo_toplevel()
        self.overlay = TimerOverlay(
            root,
            self.timer_settings,
            on_settings_changed=self.save_settings
        )
        # Always show the overlay when the tracker panel is launched,
        # regardless of any previously-saved hidden state.
        self.overlay.show()
        self.visibility_btn.config(text="Hide")
        self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    # =========================================================================
    # MONITORING LOGIC
    # =========================================================================

    def _update_log_path(self):
        """Update combat log path from current game path."""
        game_path = self.game_path_getter()

        if not game_path:
            self.log_status_label.config(
                text="Set a game folder in the main window first",
                foreground=THEME_COLORS['warning']
            )
            return

        if not Path(game_path).exists():
            self.log_status_label.config(
                text=f"Game folder not found: {game_path}",
                foreground=THEME_COLORS['danger']
            )
            return

        latest = self.combat_monitor.set_log_folder(game_path) if self.combat_monitor else None

        if latest:
            self.log_status_label.config(
                text=f"Found: {Path(latest).name}",
                foreground=THEME_COLORS['success']
            )
        else:
            self.log_status_label.config(
                text="No combat logs found. Type /logcombat on in game.",
                foreground=THEME_COLORS['warning']
            )

        self._update_overlay_idle()

    def _update_overlay_idle(self):
        """Push monitor + combat log status to overlay when not actively tracking."""
        if not self.overlay or self._monitoring:
            return

        status_text = "Monitor: Running" if self._monitoring else "Monitor: Stopped"
        status_color = COLORS["active"] if self._monitoring else COLORS["default"]

        log_text = self.log_status_label.cget('text')
        log_fg = self.log_status_label.cget('foreground')
        log_color = COLORS["default"]
        if log_fg == THEME_COLORS.get('success'):
            log_color = COLORS["active"]
        elif log_fg == THEME_COLORS.get('warning'):
            log_color = COLORS["warning"]
        elif log_fg == THEME_COLORS.get('danger'):
            log_color = COLORS["alert"]

        self.overlay.update_display(
            status_text, "", "", status_color,
            log_text, "", "", log_color, ""
        )

    def _start_monitoring(self):
        """Start combat log monitoring."""
        self._update_log_path()

        if not self.combat_monitor.log_path:
            Messagebox.show_error(
                "No combat log found.\n\n"
                "1. Set game path in the main window\n"
                "2. In-game, type: /logcombat on",
                title="Error"
            )
            return

        if self.combat_monitor.start_monitoring():
            self._monitoring = True
            self.status_label.config(text="Running", foreground=THEME_COLORS['success'])
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.boss_timer._push_waiting_state()
            self._start_game_loop()
            if self.overlay and not self.overlay.is_visible:
                self.overlay.show()
                self.visibility_btn.config(text="Hide")
        else:
            Messagebox.show_error("Failed to start monitoring.\n\nThe combat log file may be locked or unreadable.\nTry /logcombat off, then /logcombat on.", title="Error")

    def _stop_monitoring(self):
        """Stop combat log monitoring."""
        self.combat_monitor.stop_monitoring()
        self.boss_timer.stop_cycle()
        self._monitoring = False
        self._stop_game_loop()
        self.status_label.config(text="Stopped", foreground=THEME_COLORS['muted'])
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self._update_log_path()
        self._update_overlay_idle()

    def _rescan_log(self):
        """Manually rescan for a newer combat log file."""
        if not self.combat_monitor or not self.combat_monitor.log_folder:
            self._update_log_path()
            return

        latest = self.combat_monitor.rescan_log()
        if latest:
            self.log_status_label.config(
                text=f"Found: {Path(latest).name}",
                foreground=THEME_COLORS['success']
            )
        else:
            self.log_status_label.config(
                text="No combat logs found. Type /logcombat on in game.",
                foreground=THEME_COLORS['warning']
            )
        self._update_overlay_idle()

    def _start_game_loop(self):
        """Start the 50ms update loop."""
        def loop():
            try:
                self.boss_timer.update_display()
            except Exception as e:
                logger.error("Timer loop error: %s", e)
            finally:
                self._game_loop_id = self.after(50, loop)

        self._game_loop_id = self.after(50, loop)

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
        self.lock_btn.config(text="Unlock" if self.overlay.is_locked else "Lock")

    def _toggle_transparent(self):
        self.overlay.set_transparent(self.transparent_var.get())

    def _on_opacity_change(self, value):
        self.overlay.set_opacity(float(value))

    def _on_font_change(self, value):
        self.overlay.set_font_size(int(float(value)))

    def _toggle_test(self):
        """Toggle test mode (simulate a seed cycle)."""
        if self.boss_timer.timer_active:
            self.boss_timer.stop_cycle()
            self.test_btn.config(text="Test Cycle")
            self._stop_game_loop()
        else:
            self.boss_timer.start_cycle("TestPlayer")
            self.test_btn.config(text="Stop")
            self._start_game_loop()
            if self.overlay and not self.overlay.is_visible:
                self.overlay.show()
                self.visibility_btn.config(text="Hide")

            def trigger_fixation():
                if self.boss_timer.timer_active:
                    self.boss_timer.update_fixation("FixPlayer")

            def check_reset():
                if not self.boss_timer.timer_active:
                    self.test_btn.config(text="Test Cycle")
                    self._stop_game_loop()
                else:
                    self.after(500, check_reset)

            self.after(4000, trigger_fixation)
            self.after(39500, check_reset)

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def save_settings(self):
        """Save current overlay settings to disk."""
        if self.overlay:
            settings = self.overlay.get_settings()
            if not save_settings(self.settings_folder, settings):
                logger.warning("Failed to save timer overlay settings")

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
        if self.combat_monitor:
            self._update_log_path()

    def _sync_overlay_ui(self):
        """Sync overlay control widgets to current timer_settings."""
        self.transparent_var.set(self.timer_settings.get('transparent_bg', False))
        self.opacity_var.set(self.timer_settings.get('opacity', 0.9))
        self.font_var.set(self.timer_settings.get('font_size', 11))
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
        if self.combat_monitor:
            self.combat_monitor.stop_monitoring()
        self._stop_game_loop()
        self.save_settings()
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
