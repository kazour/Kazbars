"""
KazBars — Standalone Grid Editor for Age of Conan.
Main application class.
"""

import logging
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import ttkbootstrap as ttkb
from ttkbootstrap.dialogs import Messagebox

from kazbars import (
    APP_NAME,
    buff_display_editor,
    build_action,
    game_folder,
    profile_io,
    update_check,
)
from kazbars import __version__ as APP_VERSION
from kazbars.buff_database import BuffDatabase
from kazbars.build_loading import show_about_popup
from kazbars.custom_menu_bar import CustomMenuBar
from kazbars.database_editor import DatabaseEditorTab
from kazbars.first_launch import run_first_launch
from kazbars.game_resolution import change_game_resolution
from kazbars.grids_panel import GridsPanel
from kazbars.instructions_panel import InstructionsPanel
from kazbars.live_tracker_panel import LiveTrackerPanel
from kazbars.paths import ASSETS, KAZBARS_ASSETS, app_path
from kazbars.settings_manager import SettingsManager, init_settings
from kazbars.ui_components import (
    ToastManager,
    disable_mousewheel_on_inputs,
)
from kazbars.ui_helpers import (
    BTN_LARGE,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
    setup_custom_styles,
)
from kazbars.ui_tk_style import apply_dark_titlebar, enable_global_dark_titlebar
from kazbars.ui_widgets import (
    add_tooltip,
    bind_button_press_effect,
    blend_alpha,
    create_app_header,
    update_app_header_color,
)
from kazbars.window_position import bind_window_position_save, restore_window_position

SETTINGS_FILE = "kazbars_settings.json"

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN APPLICATION
# ============================================================================
class KazBarsApp(ttkb.Window):
    """KazBars — Standalone grid editor for Age of Conan."""

    def __init__(self):
        super().__init__(themename="darkly")
        self.withdraw()

        self.title(f"{APP_NAME} — Untitled")
        self.iconname(APP_NAME)

        # Paths — see kazbars.paths for the resolution rules.
        self.app_path = app_path()
        self.assets_path = ASSETS

        self.profiles_path = self.app_path / "profiles"
        self.profiles_path.mkdir(exist_ok=True)

        self.settings_path = self.app_path / "settings"
        self.settings_path.mkdir(exist_ok=True)

        # Settings
        self.settings = SettingsManager(self.settings_path / SETTINGS_FILE)
        init_settings(self.settings)

        # Database (with fallback recovery from bundled copy)
        self.database = BuffDatabase()
        db_path = KAZBARS_ASSETS / "Database.json"
        if not self.database.load(db_path):
            bundled = KAZBARS_ASSETS / "Database.json.default"
            if bundled.exists():
                logger.warning("Database.json corrupt — restoring from bundled copy")
                try:
                    shutil.copy2(bundled, db_path)
                    self.database.load(db_path)
                except OSError as e:
                    logger.error("Could not restore Database.json: %s", e)
            else:
                logger.warning("Database not found: %s", db_path)

        # State
        self.app_version = APP_VERSION
        self.current_profile = None
        self.reference_resolution = None
        self.modified = False
        self.current_view = 'grids'
        self._building = False
        self.boss_timer_panel = None

        # Single game folder + Aoc.exe preference (set via first-launch prompt)
        self._migrate_legacy_clients()
        self.game_path = self.settings.get('game_path') or None
        self.use_aoc_bypass = bool(self.settings.get('use_aoc_bypass', False))

        # Setup
        setup_custom_styles(self)
        apply_dark_titlebar(self)
        enable_global_dark_titlebar()
        disable_mousewheel_on_inputs(self)

        self._create_widgets()
        self._create_menu_bar()

        # Window position
        self.minsize(950, 660)
        restore_window_position(self, 'main_window', 950, 660)
        bind_window_position_save(self, 'main_window', save_size=True)

        # Protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Load last profile
        last_profile = self.settings.get('last_profile')
        if last_profile and Path(last_profile).exists():
            data, corrupt = profile_io.read_profile_file(Path(last_profile))
            profile_io.apply_profile_data(self, Path(last_profile), data, corrupt=corrupt)
        else:
            self._update_title()

        self.deiconify()

        # First launch check
        if not self.game_path:
            self.after(100, self._show_first_launch_dialog)

        update_check.check_for_updates(self, APP_VERSION)

    # ========================================================================
    # WIDGET CREATION
    # ========================================================================
    def _create_widgets(self):
        """Build the main UI: app header, nav bar, content area, bottom bar."""
        # --- App header ---
        self._header_canvas = create_app_header(self, APP_NAME, MODULE_COLORS['grids'])

        # --- Nav bar ---
        self.nav_frame = ttk.Frame(self)
        self.nav_frame.pack(fill='x')

        nav_inner = ttk.Frame(self.nav_frame)
        nav_inner.pack(fill='x', padx=PAD_TAB, pady=(PAD_SMALL, 0))

        # Nav buttons — grid layout for equal-width columns
        self.nav_colors = {
            'grids':        THEME_COLORS['accent'],    # blue
            'database':     THEME_COLORS['purple'],
            'instructions': THEME_COLORS['muted'],     # neutral
        }
        nav_views = [
            ('grids', 'Grids', "Create and configure buff tracking grids"),
            ('database', 'Database', "Buff names and IDs used by your grids"),
            ('instructions', 'Help', "How to use KazBars"),
        ]

        self.nav_buttons = {}
        for col, (view_name, label, tooltip) in enumerate(nav_views):
            nav_inner.columnconfigure(col, weight=1, uniform='nav')

            btn_frame = ttk.Frame(nav_inner)
            btn_frame.grid(row=0, column=col, sticky='ew')

            btn = ttk.Button(btn_frame, text=label, bootstyle="link",  # type: ignore[call-arg]
                             command=lambda v=view_name: self._switch_view(v))
            btn.pack(fill='x', pady=(PAD_XS, 0))

            tab_color = self.nav_colors[view_name]
            dim_color = blend_alpha(tab_color, TK_COLORS['bg'], 30)
            underline = tk.Canvas(btn_frame, height=1, highlightthickness=0,
                                  bg=dim_color)
            underline.pack(fill='x')

            self.nav_buttons[view_name] = {'button': btn, 'underline': underline,
                                           'color': tab_color, 'dim': dim_color}

            # Hover: brighten inactive tab underline
            def _on_enter(e, vn=view_name):
                if self.current_view != vn:
                    self.nav_buttons[vn]['underline'].configure(
                        bg=blend_alpha(self.nav_buttons[vn]['color'], TK_COLORS['bg'], 60))

            def _on_leave(e, vn=view_name):
                if self.current_view != vn:
                    self.nav_buttons[vn]['underline'].configure(
                        bg=self.nav_buttons[vn]['dim'])

            # Clickable + hoverable + tooltipped on entire tab area (frame + underline)
            for w in (btn, btn_frame, underline):
                w.bind('<Enter>', _on_enter)
                w.bind('<Leave>', _on_leave)
                add_tooltip(w, tooltip)
            btn_frame.bind('<Button-1>', lambda e, v=view_name: self._switch_view(v))
            underline.bind('<Button-1>', lambda e, v=view_name: self._switch_view(v))

        # Nav separator
        ttk.Separator(self.nav_frame, orient='horizontal').pack(fill='x', pady=(PAD_SMALL, 0))

        # --- Content area ---
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill='both', expand=True)
        self.toast = ToastManager(self.content_frame)

        # Grids view
        self.grids_panel = GridsPanel(
            self.content_frame,
            database=self.database,
            on_modified=self._mark_modified,
        )

        # Database view
        self.db_panel = DatabaseEditorTab(
            self.content_frame,
            database=self.database,
            assets_path=self.assets_path / "kazbars",
            on_modified=self._mark_modified,
            get_grids=lambda: self.grids_panel.grids,
        )

        # Instructions view
        self.instructions_panel = InstructionsPanel(self.content_frame)

        # Show default view — set initial underlines directly (canvas not mapped yet)
        self.grids_panel.pack(fill='both', expand=True)
        for name, widgets in self.nav_buttons.items():
            if name == self.current_view:
                widgets['underline'].configure(height=2, bg=widgets['color'])
            else:
                widgets['underline'].configure(height=1, bg=widgets['dim'])

        # --- Bottom bar ---
        # before=content_frame: tk pack assigns space in list order, so the bar
        # has to come BEFORE the expand=True content frame in the manager's
        # list, otherwise the content frame eats its space when shrinking.
        ttk.Separator(self, orient='horizontal').pack(
            fill='x', side='bottom', before=self.content_frame)
        self.bottom_bar = tk.Frame(self, bg=TK_COLORS['status_bg'])
        self.bottom_bar.pack(fill='x', side='bottom', before=self.content_frame)

        # Game folder indicator (left) — single path, right-click to change/clear
        game_frame = ttk.Frame(self.bottom_bar)
        game_frame.pack(side='left', padx=(PAD_TAB, 0), pady=PAD_SMALL)

        ttk.Label(game_frame, text="Game:", font=FONT_SMALL,
                  foreground=THEME_COLORS['muted']).pack(side='left', padx=(0, PAD_XS))

        self._game_path_label = ttk.Label(
            game_frame, text="", font=FONT_SMALL,
            foreground=THEME_COLORS['body'], cursor='hand2',
        )
        self._game_path_label.pack(side='left')
        self._game_path_label.bind('<Button-1>', self._show_game_context_menu)
        self._game_path_label.bind('<Button-3>', self._show_game_context_menu)

        self._game_context_menu = tk.Menu(self, tearoff=0)
        self._game_context_menu.add_command(
            label="Change game folder...", command=self._change_game_folder)
        self._game_context_menu.add_command(
            label="Clear", command=self._clear_game_path)

        # Inline hint — visibility managed by game_folder.update_build_state
        self._game_hint = ttk.Label(game_frame, text="Set your game folder to build",
                                    font=FONT_SMALL, foreground=THEME_COLORS['warning'])

        # Build button (right side of bottom bar)
        self.build_btn = ttk.Button(
            self.bottom_bar, text="Build & Install ▶", bootstyle="success",  # type: ignore[call-arg]
            width=BTN_LARGE, command=self._build
        )
        self.build_btn.pack(side='right', padx=(0, PAD_TAB), pady=PAD_SMALL)
        bind_button_press_effect(self.build_btn, bootstyle='success')
        add_tooltip(self.build_btn, "Build & Install (Ctrl+B)")

        ttk.Separator(self.bottom_bar, orient='vertical').pack(
            side='right', fill='y', padx=PAD_SMALL, pady=PAD_XS)

        tracker_btn = ttkb.Button(
            self.bottom_bar, text="⏱ Ethram-Fal", bootstyle="outline",
            command=self._open_boss_timer
        )
        tracker_btn.pack(side='right', pady=PAD_SMALL)
        add_tooltip(tracker_btn, "Open the Ethram-Fal Seed Timer")

        self._refresh_game_path_label()

    def _create_menu_bar(self):
        """Create the custom dark menu bar."""
        self._menubar = CustomMenuBar(self)
        self._menubar.pack(fill='x', before=self._header_canvas)

        self._build_console_var = tk.BooleanVar(value=bool(self.settings.get('build_console', False)))

        self._menubar.add_cascade(label="File", menu_def=[
            {'type': 'command', 'label': 'New Profile', 'accelerator': 'Ctrl+N',
             'command': self._new_profile},
            {'type': 'command', 'label': 'Open Profile...', 'accelerator': 'Ctrl+O',
             'command': self._open_profile},
            {'type': 'command', 'label': 'Load Default Profile',
             'command': self._load_default_profile},
            {'type': 'command', 'label': 'Save Profile', 'accelerator': 'Ctrl+S',
             'command': self._save_profile},
            {'type': 'command', 'label': 'Save Profile As...',
             'command': self._save_profile_as},
            {'type': 'separator'},
            {'type': 'command', 'label': 'Exit',
             'command': self._on_close},
        ])
        self._menubar.add_cascade(label="Game", menu_def=[
            {'type': 'command', 'label': 'Default buff bars...',
             'command': self._open_buff_display_editor},
            {'type': 'separator'},
            {'type': 'command', 'label': 'Change game folder...',
             'command': self._change_game_folder},
            {'type': 'command', 'label': 'Game resolution...',
             'command': self._change_game_resolution},
            {'type': 'command', 'label': 'Uninstall from game client...',
             'command': self._uninstall_game},
            {'type': 'separator'},
            {'type': 'checkbutton', 'label': 'Include buff-discovery console in builds',
             'variable': self._build_console_var,
             'command': self._on_toggle_build_console},
        ])
        self._menubar.add_command(label="About", command=self._show_about)

        # Keyboard shortcuts
        self.bind_all('<Control-n>', lambda e: self._new_profile())
        self.bind_all('<Control-o>', lambda e: self._open_profile())
        self.bind_all('<Control-s>', lambda e: self._save_profile())
        self.bind_all('<Control-b>', lambda e: self._build())

    # ========================================================================
    # NAV BAR
    # ========================================================================
    def _switch_view(self, view_name):
        """Switch between Grids, Database, and Instructions views."""
        self.current_view = view_name

        # Hide all views
        self.grids_panel.pack_forget()
        self.db_panel.pack_forget()
        self.instructions_panel.pack_forget()

        # Show selected
        views = {
            'grids': self.grids_panel,
            'database': self.db_panel,
            'instructions': self.instructions_panel,
        }
        views[view_name].pack(fill='both', expand=True)

        # Refresh database list when switching to it (grid usage may have changed)
        if view_name == 'database':
            self.grids_panel.save_settings()
            self.db_panel.refresh_list()

        # Animate nav underlines
        for name, widgets in self.nav_buttons.items():
            if name == view_name:
                self._animate_underline(widgets['underline'], widgets['color'])
            else:
                widgets['underline'].delete('ul')
                widgets['underline'].configure(height=1, bg=widgets['dim'])

        # Update header accent strip to match active tab color
        update_app_header_color(self._header_canvas, self.nav_colors[view_name])

    def _animate_underline(self, canvas, color, steps=5, interval=16):
        """Animate nav underline growing from center outward."""
        canvas.configure(height=2)
        bg = TK_COLORS['bg']

        def _step(i):
            try:
                w = canvas.winfo_width()
                if w <= 1:
                    canvas.configure(bg=color)
                    return
                canvas.delete('ul')
                t = i / steps
                # ease-out quad
                t = 1 - (1 - t) ** 2
                bar_w = int(w * t)
                x0 = (w - bar_w) // 2
                canvas.configure(bg=bg)
                canvas.create_rectangle(x0, 0, x0 + bar_w, 2,
                                        fill=color, outline='', tags='ul')
                if i < steps:
                    canvas.after(interval, lambda: _step(i + 1))
            except tk.TclError:
                pass

        _step(1)

    # ========================================================================
    # BOSS TIMER
    # ========================================================================
    def _boss_timer_if_alive(self):
        """Return the boss timer panel if it exists and is alive, else None."""
        if self.boss_timer_panel is None:
            return None
        try:
            if self.boss_timer_panel.winfo_exists():
                return self.boss_timer_panel
        except Exception:
            pass
        self.boss_timer_panel = None
        return None

    def _open_boss_timer(self):
        """Open the Boss Timer panel (single-instance)."""
        if bt := self._boss_timer_if_alive():
            bt.deiconify()
            bt.lift()
            bt.focus_force()
            bt.restore_overlay()
            return
        self.boss_timer_panel = LiveTrackerPanel(
            self, self.settings_path, lambda: self.game_path
        )

    # ========================================================================
    # GAME FOLDER MANAGEMENT
    # ========================================================================
    def _migrate_legacy_clients(self):
        return game_folder.migrate_legacy_clients(self)

    def _refresh_game_path_label(self):
        return game_folder.refresh_game_path_label(self)

    def _change_game_folder(self):
        return game_folder.change_game_folder(self)

    def _change_game_resolution(self):
        return change_game_resolution(self)

    def _clear_game_path(self):
        return game_folder.clear_game_path(self)

    def _show_game_context_menu(self, event):
        return game_folder.show_game_context_menu(self, event)

    def _uninstall_game(self):
        return game_folder.uninstall_game(self)

    def _open_buff_display_editor(self):
        return buff_display_editor.open_buff_display_editor(self)

    def _on_toggle_build_console(self):
        enabled = self._build_console_var.get()
        self.settings.set('build_console', enabled)
        self.settings.save()
        msg = ("Buff-discovery console will be included in next build"
               if enabled else "Buff-discovery console excluded from next build")
        self.toast.show(msg, style='info', duration=4)

    # ========================================================================
    # PROFILE SYSTEM
    # ========================================================================
    def _check_unsaved_changes(self):
        """Returns True if safe to proceed (saved or discarded). False = user cancelled."""
        profile_dirty = self.modified
        db_dirty = self.db_panel.modified
        if not profile_dirty and not db_dirty:
            return True
        if profile_dirty and db_dirty:
            message = "Save unsaved changes to the profile and database?"
        elif profile_dirty:
            message = (
                f"Save changes to \"{self._get_profile_name()}\"?\n\n"
                "Your grid layout has changed since the last save."
            )
        else:
            message = "Save unsaved changes to the buff database?"
        result = Messagebox.yesnocancel(message, title="Unsaved Changes")
        if result == "Yes":
            ok = True
            if profile_dirty:
                ok = self._save_profile() and ok
            if db_dirty:
                self.db_panel.save()
                ok = (not self.db_panel.modified) and ok
            return ok
        return result == "No"

    def _mark_modified(self):
        """Mark profile as having unsaved changes."""
        self.modified = True
        self._update_title()

    def _update_title(self):
        """Update the window title bar with profile name and modified indicator."""
        if self.current_profile:
            name = Path(self.current_profile).stem
        else:
            name = "Untitled"
        suffix = " *" if self.modified else ""
        self.title(f"{APP_NAME} — {name}{suffix}")

    def _new_profile(self):
        return profile_io.new_profile(self)

    def _open_profile(self):
        return profile_io.open_profile(self)

    def _load_default_profile(self):
        return profile_io.load_default_profile(self)

    def _save_profile(self):
        return profile_io.save_profile(self)

    def _save_profile_as(self):
        return profile_io.save_profile_as(self)

    def _get_profile_name(self):
        return profile_io.get_profile_name(self)

    # ========================================================================
    # BUILD PIPELINE
    # ========================================================================
    def _build(self):
        return build_action.build(self)

    # ========================================================================
    # EDIT MENU ACTIONS
    # ========================================================================
    def _add_grid(self):
        """Add a new grid via the grids panel wizard."""
        self._switch_view('grids')
        self.grids_panel.add_grid()

    def _clear_all_grids(self):
        """Clear all grids via the grids panel."""
        self._switch_view('grids')
        self.grids_panel.clear_all_grids()

    def _show_about(self):
        """Show the About dialog (single-instance — focus existing if alive)."""
        existing = getattr(self, '_about_popup', None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_set()
                    return
            except tk.TclError:
                pass
        self._about_popup = show_about_popup(self, APP_NAME, APP_VERSION)

    # ========================================================================
    # FIRST LAUNCH
    # ========================================================================
    def _show_first_launch_dialog(self):
        return run_first_launch(self, APP_NAME)

    # ========================================================================
    # WINDOW LIFECYCLE
    # ========================================================================
    def _on_close(self):
        """Handle window close with unsaved changes check."""
        if not self._check_unsaved_changes():
            return
        if bt := self._boss_timer_if_alive():
            bt.cleanup()
            bt.destroy()

        self.destroy()
