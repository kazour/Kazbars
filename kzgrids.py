"""
Kaz Grids — Standalone Grid Editor for Age of Conan
Main application entry point.
"""

import json
import logging
import shutil
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk
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
    disable_mousewheel_on_inputs, ToastManager, CustomMenuBar,
)
from Modules.ui_tk_style import apply_dark_titlebar, enable_global_dark_titlebar
from Modules.settings_manager import init_settings
from Modules.window_position import restore_window_position, bind_window_position_save
from Modules.build_loading import BuildLoadingScreen, show_welcome_popup, show_close_game_required_dialog, show_about_popup
from Modules.live_tracker_panel import LiveTrackerPanel
from Modules.build_utils import find_compiler
from Modules.grids_generator import MAX_TOTAL_SLOTS
from Modules.database_editor import BuffDatabase, DatabaseEditorTab
from Modules.grids_panel import GridsPanel
from Modules.instructions_panel import InstructionsPanel

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
# SAFE JSON UTILITIES
# ============================================================================
def _safe_load_json(path, fallback=None):
    """Load JSON with fallback on any corruption."""
    if fallback is None:
        fallback = {}
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        return dict(fallback)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning("%s corrupt or unreadable — using defaults: %s", Path(path).name, e)
        return dict(fallback)


def _safe_save_json(path, data):
    """Write JSON atomically — temp file + rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(p)


# ============================================================================
# SETTINGS MANAGER
# ============================================================================
class SettingsManager:
    """Persistent application settings stored as JSON."""

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.data = _safe_load_json(self.filepath)

    def save(self):
        try:
            _safe_save_json(self.filepath, self.data)
        except Exception as e:
            logger.error("Error saving settings: %s", e)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


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
        self.grids_view = self.grids_panel

        # Database view
        self.db_panel = DatabaseEditorTab(
            self.content_frame,
            database=self.database,
            assets_path=self.assets_path / "kzgrids",
            on_modified=self._mark_modified,
            get_grids=lambda: self.grids_panel.grids,
            toast=self.toast,
        )
        self.database_view = self.db_panel

        # Instructions view
        self.instructions_panel = InstructionsPanel(self.content_frame)
        self.instructions_view = self.instructions_panel

        # Show default view — set initial underlines directly (canvas not mapped yet)
        self.current_view = 'grids'
        self.grids_view.pack(fill='both', expand=True)
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

        # Inline hint — visibility managed by _update_build_state
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
        self.grids_view.pack_forget()
        self.database_view.pack_forget()
        self.instructions_view.pack_forget()

        # Show selected
        views = {
            'grids': self.grids_view,
            'database': self.database_view,
            'instructions': self.instructions_view,
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
        """One-time migration: collapse old multi-client settings to single game_path."""
        legacy = self.settings.get('game_clients')
        if not legacy:
            return
        idx = int(self.settings.get('active_game_idx') or 0)
        if not (0 <= idx < len(legacy)):
            idx = 0
        try:
            self.settings.set('game_path', legacy[idx]['path'])
        except (KeyError, TypeError, IndexError):
            pass
        self.settings.data.pop('game_clients', None)
        self.settings.data.pop('active_game_idx', None)
        self.settings.save()

    def _refresh_game_path_label(self):
        """Update the game-folder label and tooltip from self.game_path."""
        if not self.game_path:
            self._game_path_label.configure(
                text="(not set)", foreground=THEME_COLORS['muted'])
            add_tooltip(self._game_path_label, "Click to choose your Age of Conan folder")
        else:
            display = self._format_game_path(self.game_path)
            exists = Path(self.game_path).is_dir()
            text = display if exists else f"{display} ⚠"
            self._game_path_label.configure(
                text=text,
                foreground=THEME_COLORS['body'] if exists else THEME_COLORS['warning'])
            tip = self.game_path if exists else f"Folder not found: {self.game_path}"
            add_tooltip(self._game_path_label, tip)
        self._update_build_state()

    @staticmethod
    def _format_game_path(path):
        """Compact display: 'F:\\...\\Age of Conan' for long paths."""
        resolved = Path(path)
        parts = resolved.parts
        if len(parts) <= 3:
            return str(resolved)
        return f"{parts[0]}\\...\\{parts[-1]}"

    def _change_game_folder(self):
        """Browse for a game folder and persist it."""
        path = filedialog.askdirectory(title="Select Age of Conan Folder")
        if not path:
            return

        if not (Path(path) / "Data" / "Gui" / "Default").exists():
            Messagebox.show_warning(
                "This doesn't look like an Age of Conan install.\n\n"
                "The expected game folders weren't found. The folder will be set anyway.",
                title="Unexpected Folder"
            )

        test_path = str(Path(path) / "Data" / "Gui" / "Default" / "Flash" / "KazGrids.swf")
        if len(test_path) > 240:
            Messagebox.show_info(
                "This path is very long — Windows may have trouble with it.\n\n"
                "Consider a shorter install path.",
                title="Long Path"
            )

        resolved = str(Path(path).resolve())
        previous = self.game_path
        self.game_path = resolved
        self._save_game_path()

        from Modules.build_executor import detect_aoc_launcher
        if detect_aoc_launcher(resolved) and resolved != previous:
            self._prompt_aoc_bypass()

        self._refresh_game_path_label()

    def _clear_game_path(self):
        """Forget the current game folder."""
        if not self.game_path:
            return
        if Messagebox.yesno(
            "Clear the configured game folder?\n\nThis won't delete any game files.",
            title="Clear Game Folder",
        ) != "Yes":
            return
        self.game_path = None
        self._save_game_path()
        self._refresh_game_path_label()

    def _show_game_context_menu(self, event):
        """Show the change/clear menu for the game-folder label."""
        self._game_context_menu.tk_popup(event.x_root, event.y_root)

    def _save_game_path(self):
        """Persist game_path to settings and notify observers."""
        if self.game_path:
            self.settings.set('game_path', self.game_path)
        else:
            self.settings.data.pop('game_path', None)
        self.settings.save()
        self.grids_panel.notify_game_path_changed()

    def _save_aoc_bypass(self, value):
        """Persist the Aoc.exe bypass preference."""
        self.use_aoc_bypass = bool(value)
        self.settings.set('use_aoc_bypass', self.use_aoc_bypass)
        self.settings.save()

    def _prompt_aoc_bypass(self):
        """Ask the user whether they use Aoc.exe (launcher bypass)."""
        result = Messagebox.yesno(
            "Aoc.exe (third-party launcher bypass) was detected in this game folder.\n\n"
            "Is Aoc.exe enabled on your PC?",
            title="Aoc.exe Detected",
        )
        self._save_aoc_bypass(result == "Yes")

    def _uninstall_game(self):
        """Remove Kaz Grids files from the configured game folder."""
        if not self.game_path:
            Messagebox.show_warning(
                "No game folder set. Configure one in the bottom bar first.",
                title="No Game Folder"
            )
            return
        if Messagebox.yesno(
            "Remove Kaz Grids files from your game folder?\n\n"
            "This deletes KazGrids.swf, auto-load entries, and reload scripts.",
            title="Uninstall from Game Folder"
        ) != "Yes":
            return
        from Modules.build_executor import uninstall_from_client
        ok, msg = uninstall_from_client(self.game_path)
        if ok:
            self.toast.show(msg, 'success', 8)
        else:
            Messagebox.show_error(msg, title="Uninstall Failed")

    def _update_build_state(self):
        """Enable/disable build button and update game hint."""
        valid = bool(self.game_path) and Path(self.game_path).is_dir()
        if not valid:
            self.build_btn.configure(state='disabled', bootstyle='success')
            self._game_hint.configure(
                text="Set your game folder to build",
                foreground=THEME_COLORS['warning'])
            self._game_hint.pack(side='left', padx=(PAD_XS, 0))
        else:
            self.build_btn.configure(state='normal', bootstyle='success')
            self._game_hint.pack_forget()

    def _pulse_game_hint(self):
        """Briefly pulse the game hint label to draw attention."""
        original = THEME_COLORS['warning']
        bright = THEME_COLORS['heading']
        self._game_hint.configure(foreground=bright)
        self.after(150, lambda: self._game_hint.configure(foreground=original))
        self.after(300, lambda: self._game_hint.configure(foreground=bright))
        self.after(450, lambda: self._game_hint.configure(foreground=original))

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
        """Start a new empty profile."""
        if not self._check_unsaved_changes():
            return
        self.grids_panel.load_profile_data([])
        self.current_profile = None
        self.reference_resolution = None
        self.modified = False
        self._update_title()

    def _open_profile(self):
        """Open a profile from file."""
        if not self._check_unsaved_changes():
            return
        path = filedialog.askopenfilename(
            title="Open Profile",
            initialdir=str(self.profiles_path),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            self._load_profile(Path(path))

    def _load_profile(self, path):
        """Load a profile from a JSON file."""
        corrupt = False
        try:
            raw = json.loads(Path(path).read_text(encoding='utf-8'))
            data = raw if isinstance(raw, dict) else {}
            if not isinstance(raw, dict):
                corrupt = True
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            corrupt = True
            data = {}

        if corrupt:
            Messagebox.show_warning(
                f"Profile appears corrupt — starting with empty grids.\n\n{Path(path).name}",
                title="Profile Warning"
            )

        grids = data.get('grids', [])
        self.grids_panel.load_profile_data(grids)

        if bt := self._boss_timer_if_alive():
            bt.load_profile_data(data.get('boss_timer', {}))

        ref = data.get('reference_resolution')
        self.reference_resolution = list(ref) if isinstance(ref, list) and len(ref) == 2 else None

        self.current_profile = str(path)
        self.modified = False
        self.settings.set('last_profile', str(path))
        self.settings.save()
        self._update_title()

    def _save_profile(self):
        """Save current profile (or Save As if no path). Returns True if saved."""
        if self.current_profile:
            return self._do_save_profile(Path(self.current_profile))
        return self._save_profile_as()

    def _save_profile_as(self):
        """Save profile to a new file. Returns True if saved, False if cancelled."""
        path = filedialog.asksaveasfilename(
            title="Save Profile As",
            defaultextension=".json",
            initialdir=str(self.profiles_path),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            return self._do_save_profile(Path(path))
        return False

    def _do_save_profile(self, path):
        """Write profile data to disk. Returns True on success, False on error."""
        try:
            data = {
                'version': APP_VERSION,
                'grids': self.grids_panel.get_profile_data(),
            }
            if self.reference_resolution:
                data['reference_resolution'] = self.reference_resolution
            if bt := self._boss_timer_if_alive():
                data['boss_timer'] = bt.get_profile_data()
            _safe_save_json(path, data)

            self.current_profile = str(path)
            self.modified = False
            self.settings.set('last_profile', str(path))
            self.settings.save()
            self._update_title()
            self.toast.show(f"Saved: {path.name}", 'success')
            self._flash_status_bar()
            return True
        except (IOError, OSError) as e:
            Messagebox.show_error(f"Failed to save profile.\n\nCheck that the file isn't read-only or in use by another program.\n\n({e})", title="Save Error")
            return False

    def _get_profile_name(self):
        """Return the current profile display name."""
        if self.current_profile:
            return Path(self.current_profile).stem
        return "Untitled"

    def _check_for_updates(self):
        """Fire-and-forget background check for a newer GitHub release."""
        import threading
        import urllib.request
        import urllib.error

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
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # ========================================================================
    # BUILD PIPELINE
    # ========================================================================
    def _build(self):
        """Build and install KazGrids.swf to the configured game folder."""
        if self._building:
            return

        valid = (
            bool(self.game_path)
            and Path(self.game_path).is_dir()
            and (Path(self.game_path) / "Data" / "Gui" / "Default").exists()
        )

        compiler = find_compiler(self.assets_path, self.app_path)
        grids = self.grids_panel.get_profile_data()
        total_slots = self.grids_panel.get_total_slots()

        validations = [
            (not valid,
             "No valid game folder configured.\n\n"
             "Set your Age of Conan folder from the bottom bar."),
            (compiler is None,
             "A required build file is missing.\n\n"
             "Re-download Kaz Grids to restore it."),
            (not grids,
             "No grids to build.\n\nAdd at least one grid first."),
            (total_slots > MAX_TOTAL_SLOTS,
             f"Total slots ({total_slots}) exceeds maximum ({MAX_TOTAL_SLOTS}).\n\n"
             "Remove some grids or reduce grid sizes."),
        ]
        for k, (failed, msg) in enumerate(validations):
            if failed:
                if k == 0:
                    self._pulse_game_hint()
                Messagebox.show_error(msg, title="Build Error")
                return

        empty = []
        for g in grids:
            if not g.get('enabled', True):
                continue
            if g.get('slotMode') == 'static':
                sa = g.get('slotAssignments', {})
                if not any(v for v in sa.values()):
                    empty.append(g['id'])
            else:
                if not g.get('whitelist'):
                    empty.append(g['id'])

        if empty:
            names = ', '.join(f"'{n}'" for n in empty)
            Messagebox.show_error(
                f"These grids have no tracked buffs and would appear empty in-game:\n\n{names}\n\n"
                "Add tracked buffs (or slot assignments for static grids), or disable the grid.",
                title="Empty Grids"
            )
            return

        # Aoc.exe users only: block while the game is running
        if self.use_aoc_bypass:
            from Modules.build_executor import get_running_game_process
            running = get_running_game_process()
            if running:
                show_close_game_required_dialog(self, process_name=running)
                return

        # Auto-save profile before building
        profile_name = None
        if self.current_profile:
            try:
                self._do_save_profile(Path(self.current_profile))
                profile_name = Path(self.current_profile).stem
            except Exception as e:
                logger.warning("Could not save profile before build: %s", e)

        # Lock build — disable all build triggers
        self._building = True
        self.build_btn.configure(state='disabled')
        self.unbind_all('<Control-b>')

        from Modules.build_executor import compile_to_staging, install_to_client, is_aoc_running

        loading = BuildLoadingScreen(self)
        staging_dir = None
        try:
            loading.advance_step("Compiling KzGrids...")
            self.update()

            staging_dir, compile_result = compile_to_staging(
                grids, self.database, self.assets_path, compiler, APP_VERSION
            )

            if not compile_result[0]:
                loading.show_summary(
                    [], compile_result, profile_name=profile_name)
                self.toast.show("Build failed", 'error', 10)
                self._flash_status_bar(THEME_COLORS['danger'])
                return

            loading.advance_step("Installing...")
            self.update()

            staging_swf = staging_dir / "KazGrids.swf"
            ok, err = install_to_client(staging_swf, self.game_path, self.use_aoc_bypass)
            client_results = [(self._format_game_path(self.game_path), ok, err)]

            aoc_running = self.use_aoc_bypass and is_aoc_running()

            if ok:
                if self.use_aoc_bypass and aoc_running:
                    self.toast.show("Built — /reloadui in-game", 'success', 8)
                elif self.use_aoc_bypass:
                    self.toast.show("Built — launch via Aoc.exe", 'success', 8)
                else:
                    self.toast.show("Built — /reloadui + /reloadgrids", 'success', 8)
                self._flash_status_bar()
                self.grids_panel.notify_build_done(self.use_aoc_bypass)
                if not self.settings.get('has_built_before'):
                    self.settings.set('has_built_before', True)
                    self.settings.save()
            else:
                self.toast.show("Build failed", 'error', 10)
                self._flash_status_bar(THEME_COLORS['danger'])

            loading.show_summary(
                client_results, compile_result, profile_name=profile_name,
                aoc_installed=self.use_aoc_bypass, aoc_running=aoc_running)

        except Exception as e:
            logger.exception("Unexpected build error")
            loading.destroy()
            Messagebox.show_error(
                "Something went wrong during the build.\n\n"
                "Your game files may not have been updated.\n\n"
                f"({e})",
                title="Build Error"
            )
            self.toast.show("Build failed", 'error', 10)
        finally:
            if staging_dir:
                shutil.rmtree(staging_dir, ignore_errors=True)
            self._building = False
            self.bind_all('<Control-b>', lambda e: self._build())
            self._update_build_state()

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
        """Show the first-launch dialog for setting up game path."""
        from Modules.first_launch import show_first_launch_dialog

        def on_game_set(path):
            self.game_path = path
            self._save_game_path()
            self._refresh_game_path_label()

        def on_aoc_bypass_set(value):
            self._save_aoc_bypass(value)

        welcome_data = {}

        def on_load_default(resolution_str):
            default_profile = self.assets_path / "kzgrids" / "Default.json"
            if not default_profile.exists():
                Messagebox.show_warning(
                    "Default.json not found in assets/kzgrids folder.",
                    title="Default Profile Missing"
                )
                return
            self._save_game_resolution(resolution_str)
            self._load_profile(default_profile)
            scaled = self._scale_grids_to_resolution(resolution_str)
            # Save a personal copy so the user has a real profile on next launch
            copy_path = self.profiles_path / "MyGrids.json"
            n = 2
            while copy_path.exists():
                copy_path = self.profiles_path / f"MyGrids ({n}).json"
                n += 1
            self._do_save_profile(copy_path)
            # Store data for welcome popup — shown after dialog closes
            grids = self.grids_panel.grids
            welcome_data['grid_count'] = len(grids)
            welcome_data['enabled_count'] = sum(1 for g in grids if g.get('enabled', True))
            welcome_data['resolution'] = resolution_str if scaled else None
            welcome_data['profile_name'] = copy_path.name

        def on_resolution_set(resolution_str):
            self._save_game_resolution(resolution_str)

        def on_dialog_closed():
            if welcome_data:
                self.after(100, lambda: show_welcome_popup(
                    self,
                    welcome_data['grid_count'],
                    welcome_data['enabled_count'],
                    resolution_str=welcome_data['resolution'],
                    profile_name=welcome_data['profile_name']))

        default_exists = (self.assets_path / "kzgrids" / "Default.json").exists()
        show_first_launch_dialog(self, APP_NAME, on_game_set, on_load_default,
                                 on_resolution_set, default_exists, on_dialog_closed,
                                 on_aoc_bypass_set=on_aoc_bypass_set)

    def _parse_resolution(self, resolution_str):
        """Parse 'WxH' string into (width, height) or None."""
        try:
            w, h = resolution_str.lower().split('x')
            return int(w), int(h)
        except (ValueError, AttributeError):
            return None

    def _save_game_resolution(self, resolution_str):
        """Save game resolution to settings."""
        parsed = self._parse_resolution(resolution_str)
        if parsed:
            self.settings.set('game_resolution', list(parsed))
            self.settings.save()

    def _scale_grids_to_resolution(self, resolution_str):
        """Scale loaded grid x/y positions from profile's reference to game resolution.
        Returns True if scaling was applied."""
        game_res = self._parse_resolution(resolution_str)
        if not game_res:
            return False

        if not self.reference_resolution or len(self.reference_resolution) != 2:
            return False

        ref_w, ref_h = self.reference_resolution
        game_w, game_h = game_res
        if ref_w == game_w and ref_h == game_h:
            return False

        from Modules.grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
        for grid in self.grids_panel.grids:
            grid['x'] = min(round(grid['x'] * game_w / ref_w), SCREEN_MAX_X)
            grid['y'] = min(round(grid['y'] * game_h / ref_h), SCREEN_MAX_Y)

        self.grids_panel.refresh_panels()
        return True

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
