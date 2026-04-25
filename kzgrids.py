"""
Kaz Grids — Standalone Grid Editor for Age of Conan
Main application entry point.
"""

import json
import logging
import shutil
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from tkinter import ttk
from pathlib import Path

import ttkbootstrap as ttkb
from ttkbootstrap.dialogs import Messagebox

from Modules.ui_helpers import (
    FONT_SMALL,
    THEME_COLORS, TK_COLORS, MODULE_COLORS,
    PAD_TAB, PAD_XS, PAD_SMALL,
    BTN_LARGE,
    setup_custom_styles,
)
from Modules.ui_widgets import (
    blend_alpha, add_tooltip, bind_button_press_effect,
    create_app_header, update_app_header_color,
)
from Modules.ui_components import (
    disable_mousewheel_on_inputs, ToastManager,
)
from Modules.custom_menu_bar import CustomMenuBar
from Modules.ui_tk_style import apply_dark_titlebar, enable_global_dark_titlebar
from Modules.settings_manager import SettingsManager, init_settings
from Modules import profile_io, game_folder, build_action
from Modules.window_position import restore_window_position, bind_window_position_save
from Modules.build_loading import show_about_popup
from Modules.live_tracker_panel import LiveTrackerPanel
from Modules.database_editor import BuffDatabase, DatabaseEditorTab
from Modules.grids_panel import GridsPanel
from Modules.instructions_panel import InstructionsPanel
from Modules.first_launch import run_first_launch

APP_NAME = "Kaz Grids"
APP_VERSION = "1.1.0"
SETTINGS_FILE = "kzgrids_settings.json"

logger = logging.getLogger(__name__)


# ============================================================================
# PATH RESOLUTION
# ============================================================================
def resolve_assets_path():
    """Return the app root — handles both frozen (PyInstaller) and dev runs."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


# ============================================================================
# MAIN APPLICATION
# ============================================================================
class KzGridsApp(ttkb.Window):
    """Kaz Grids — Standalone grid editor for Age of Conan."""

    def __init__(self):
        super().__init__(themename="darkly")
        self.withdraw()

        self.title(f"{APP_NAME} — Untitled")
        self.iconname(APP_NAME)

        # Paths
        self.app_path = resolve_assets_path()

        self.profiles_path = self.app_path / "profiles"
        self.profiles_path.mkdir(exist_ok=True)

        self.settings_path = self.app_path / "settings"
        self.settings_path.mkdir(exist_ok=True)

        self.assets_path = self.app_path / "assets"

        # Settings
        self.settings = SettingsManager(self.settings_path / SETTINGS_FILE)
        init_settings(self.settings)

        # Database (with fallback recovery from bundled copy)
        self.database = BuffDatabase()
        db_path = self.assets_path / "kzgrids" / "Database.json"
        if not self.database.load(db_path):
            bundled = self.assets_path / "kzgrids" / "Database.json.default"
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
        self.minsize(900, 500)
        restore_window_position(self, 'main_window', 900, 650)
        bind_window_position_save(self, 'main_window', save_size=True)

        # Protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Load last profile
        last_profile = self.settings.get('last_profile')
        if last_profile and Path(last_profile).exists():
            self._load_profile(Path(last_profile))
        else:
            self._update_title()

        self.deiconify()

        # First launch check
        if not self.game_path:
            self.after(100, self._show_first_launch_dialog)

        self._check_for_updates()

    # ========================================================================
    # WIDGET CREATION
    # ========================================================================
    def _create_widgets(self):
        """Build the main UI: app header, nav bar, content area, bottom bar."""
        # --- App header ---
        self._header_canvas = create_app_header(self, APP_NAME, MODULE_COLORS['grids'])

        # --- Nav bar ---
        self.nav_frame = ttk.Frame(self)
        self.nav_frame.pack(fill='x', padx=0, pady=0)

        nav_inner = ttk.Frame(self.nav_frame)
        nav_inner.pack(fill='x', padx=PAD_TAB, pady=(PAD_SMALL, 0))

        # Nav buttons — grid layout for equal-width columns
        self.nav_colors = {
            'grids':        THEME_COLORS['accent'],    # blue
            'database':     THEME_COLORS['purple'],
            'instructions': THEME_COLORS['muted'],     # neutral
        }
        nav_views = [('grids', 'Grids'), ('database', 'Database'), ('instructions', 'Help')]
        for col in range(len(nav_views)):
            nav_inner.columnconfigure(col, weight=1, uniform='nav')

        self.nav_buttons = {}
        for col, (view_name, label) in enumerate(nav_views):
            btn_frame = ttk.Frame(nav_inner)
            btn_frame.grid(row=0, column=col, sticky='ew')

            btn = ttk.Button(btn_frame, text=label, bootstyle="link",
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

            # Clickable + hoverable on entire tab area (frame + underline)
            for w in (btn, btn_frame, underline):
                w.bind('<Enter>', _on_enter)
                w.bind('<Leave>', _on_leave)
            btn_frame.bind('<Button-1>', lambda e, v=view_name: self._switch_view(v))
            underline.bind('<Button-1>', lambda e, v=view_name: self._switch_view(v))

            if view_name == 'grids':
                add_tooltip(btn, "Create and configure buff tracking grids")
            if view_name == 'database':
                add_tooltip(btn, "Buff names and IDs used by your grids")
            if view_name == 'instructions':
                add_tooltip(btn, "How to use Kaz Grids")

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
            assets_path=self.assets_path / "kzgrids",
            on_modified=self._mark_modified,
            get_grids=lambda: self.grids_panel.grids,
            toast=self.toast,
        )

        # Instructions view
        self.instructions_panel = InstructionsPanel(self.content_frame)

        # Show default view — set initial underlines directly (canvas not mapped yet)
        self.grids_panel.pack(fill='both', expand=True)
        for name, widgets in self.nav_buttons.items():
            if name == 'grids':
                widgets['underline'].configure(height=2, bg=widgets['color'])
            else:
                widgets['underline'].configure(height=1, bg=widgets['dim'])

        # --- Bottom bar ---
        ttk.Separator(self, orient='horizontal').pack(fill='x', side='bottom')
        self.bottom_bar = tk.Frame(self, bg=TK_COLORS['status_bg'])
        self.bottom_bar.pack(fill='x', side='bottom')

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
            label="Change game folder…", command=self._change_game_folder)
        self._game_context_menu.add_command(
            label="Clear", command=self._clear_game_path)

        # Inline hint — visibility managed by game_folder.update_build_state
        self._game_hint = ttk.Label(game_frame, text="Set your game folder to build",
                                     font=FONT_SMALL, foreground=THEME_COLORS['warning'])

        # Build button (right side of bottom bar)
        self.build_btn = ttk.Button(
            self.bottom_bar, text="Build & Install \u25B6", bootstyle="success",
            width=BTN_LARGE, command=self._build
        )
        self.build_btn.pack(side='right', padx=(0, PAD_TAB), pady=PAD_SMALL)
        bind_button_press_effect(self.build_btn, bootstyle='success')
        add_tooltip(self.build_btn, "Build & Install (Ctrl+B)")

        ttk.Separator(self.bottom_bar, orient='vertical').pack(
            side='right', fill='y', padx=PAD_SMALL, pady=PAD_XS)

        tracker_btn = ttkb.Button(
            self.bottom_bar, text="\u23F1 Tracker", bootstyle="outline",
            command=self._open_boss_timer
        )
        tracker_btn.pack(side='right', pady=PAD_SMALL)
        add_tooltip(tracker_btn, "Open the live combat log tracker")

        self._refresh_game_path_label()


    def _create_menu_bar(self):
        """Create the custom dark menu bar."""
        self._menubar = CustomMenuBar(self)
        self._menubar.pack(fill='x', before=self._header_canvas)

        self.bind_all('<Alt_L>', lambda e: self._menubar.activate())
        self.bind_all('<Alt_R>', lambda e: self._menubar.activate())

        # File menu (the only menu)
        self._menubar.add_cascade(label="File", menu_def=[
            {'type': 'command', 'label': 'New Profile', 'accelerator': 'Ctrl+N',
             'command': self._new_profile},
            {'type': 'command', 'label': 'Open Profile...', 'accelerator': 'Ctrl+O',
             'command': self._open_profile},
            {'type': 'command', 'label': 'Save Profile', 'accelerator': 'Ctrl+S',
             'command': self._save_profile},
            {'type': 'command', 'label': 'Save Profile As...',
             'command': self._save_profile_as},
            {'type': 'separator'},
            {'type': 'command', 'label': 'Uninstall from game client...',
             'command': self._uninstall_game},
            {'type': 'separator'},
            {'type': 'command', 'label': 'About Kaz Grids',
             'command': self._show_about},
        ])

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

    def _flash_status_bar(self, color=None, steps=8, interval=30):
        """Brief color pulse on the bottom bar — subtle success feedback."""
        color = color or THEME_COLORS['success']
        bg = TK_COLORS['status_bg']

        def _step(i):
            try:
                t = i / steps
                blended = blend_alpha(color, bg, int(40 * (1 - t)))
                self.bottom_bar.configure(bg=blended)
                if i < steps:
                    self.bottom_bar.after(interval, lambda: _step(i + 1))
                else:
                    self.bottom_bar.configure(bg=bg)
            except tk.TclError:
                pass

        _step(0)

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

    def _clear_game_path(self):
        return game_folder.clear_game_path(self)

    def _show_game_context_menu(self, event):
        return game_folder.show_game_context_menu(self, event)

    def _uninstall_game(self):
        return game_folder.uninstall_game(self)

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

    def _load_profile(self, path):
        return profile_io.load_profile(self, path)

    def _save_profile(self):
        return profile_io.save_profile(self)

    def _save_profile_as(self):
        return profile_io.save_profile_as(self)

    def _get_profile_name(self):
        return profile_io.get_profile_name(self)

    def _check_for_updates(self):
        """Fire-and-forget background check for a newer GitHub release."""
        def _worker():
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/kazour/Kaz-Grids/releases/latest",
                    headers={'Accept': 'application/vnd.github+json'}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                tag = (data.get('tag_name') or '').lstrip('v')
                if not tag or tag == APP_VERSION:
                    return

                def _parts(v):
                    try:
                        return tuple(int(p) for p in v.split('.'))
                    except ValueError:
                        return ()
                if _parts(tag) <= _parts(APP_VERSION):
                    return
                url = data.get('html_url', 'https://github.com/kazour/Kaz-Grids/releases/latest')
                self.after(0, lambda: self.toast.show(
                    f"Update available: v{tag} \u2014 click for release notes", 'info', 12,
                    on_click=lambda: webbrowser.open(url)
                ))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, tk.TclError):
                pass

        threading.Thread(target=_worker, daemon=True).start()

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
        """Show the About dialog."""
        show_about_popup(self, APP_NAME, APP_VERSION)

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



# ============================================================================
# ENTRY POINT
# ============================================================================
def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    app = KzGridsApp()
    app.mainloop()


if __name__ == '__main__':
    main()
