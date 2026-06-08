"""
KazBars — Game folder configuration.

UI + persistence for the configured Age of Conan install folder. Includes the
Aoc.exe launcher-bypass prompt, the "uninstall KazBars from the game" action,
and build-button state sync. Functions take the KazBarsApp instance as first arg.
"""

from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox

from .ui_helpers import PAD_XS, THEME_COLORS
from .ui_widgets import add_tooltip, app_toast


def refresh_game_path_label(app):
    """Update the game-folder label and tooltip from app.game_path."""
    if not app.game_path:
        app._game_path_label.configure(
            text="(not set)", foreground=THEME_COLORS['muted'])
        add_tooltip(app._game_path_label, "Click to choose your Age of Conan folder")
    else:
        display = format_game_path(app.game_path)
        exists = Path(app.game_path).is_dir()
        text = display if exists else f"{display} ⚠"
        app._game_path_label.configure(
            text=text,
            foreground=THEME_COLORS['body'] if exists else THEME_COLORS['warning'])
        tip = app.game_path if exists else f"Folder not found: {app.game_path}"
        add_tooltip(app._game_path_label, tip)
    update_build_state(app)


def format_game_path(path):
    """Compact display: 'F:\\...\\Age of Conan' for long paths."""
    resolved = Path(path)
    parts = resolved.parts
    if len(parts) <= 3:
        return str(resolved)
    return f"{parts[0]}\\...\\{parts[-1]}"


def change_game_folder(app):
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

    test_path = str(Path(path) / "Data" / "Gui" / "Default" / "Flash" / "KazBars.swf")
    if len(test_path) > 240:
        Messagebox.show_info(
            "This path is very long — Windows may have trouble with it.\n\n"
            "Consider a shorter install path.",
            title="Long Path"
        )

    resolved = str(Path(path).resolve())
    previous = app.game_path
    app.game_path = resolved
    save_game_path(app)

    from .build_executor import detect_aoc_launcher
    if resolved != previous:
        has_aoc = detect_aoc_launcher(resolved)
        if has_aoc and not app.use_aoc_bypass:
            prompt_aoc_bypass(app)
        elif not has_aoc and app.use_aoc_bypass:
            save_aoc_bypass(app, False)
            app_toast(app,
                      "Aoc.exe not found in this folder — bypass mode disabled.",
                      'info', 8)

    refresh_game_path_label(app)


def clear_game_path(app):
    """Forget the current game folder."""
    if not app.game_path:
        return
    if Messagebox.yesno(
        "Clear the configured game folder?\n\nThis won't delete any game files.",
        title="Clear Game Folder",
    ) != "Yes":
        return
    app.game_path = None
    save_game_path(app)
    refresh_game_path_label(app)


def show_game_context_menu(app, event):
    """Show the change/clear menu for the game-folder label."""
    app._game_context_menu.tk_popup(event.x_root, event.y_root)


def save_game_path(app):
    """Persist game_path to settings and notify observers."""
    if app.game_path:
        app.settings.set('game_path', app.game_path)
    else:
        app.settings.data.pop('game_path', None)
    app.settings.save()
    app.grids_panel.notify_game_path_changed()


def save_aoc_bypass(app, value):
    """Persist the Aoc.exe bypass preference."""
    app.use_aoc_bypass = bool(value)
    app.settings.set('use_aoc_bypass', app.use_aoc_bypass)
    app.settings.save()


def prompt_aoc_bypass(app):
    """Ask the user whether they use Aoc.exe (launcher bypass)."""
    result = Messagebox.yesno(
        "Aoc.exe (third-party launcher bypass) was detected in this game folder.\n\n"
        "Is Aoc.exe enabled on your PC?",
        title="Aoc.exe Detected",
    )
    save_aoc_bypass(app, result == "Yes")


def uninstall_game(app):
    """Remove KazBars files from the configured game folder."""
    if not app.game_path:
        Messagebox.show_warning(
            "No game folder set. Configure one in the bottom bar first.",
            title="No Game Folder"
        )
        return
    if Messagebox.yesno(
        "Remove KazBars files from your game folder?\n\n"
        "This deletes KazBars.swf, auto-load entries, and reload scripts.",
        title="Uninstall from Game Folder"
    ) != "Yes":
        return
    from .build_executor import uninstall_from_client
    ok, msg = uninstall_from_client(
        app.game_path,
        damageinfo_pristine=Path(app.assets_path) / "damageinfo" / "DamageInfo.swf")
    if ok:
        app_toast(app, msg, 'success', 8)
    else:
        Messagebox.show_error(msg, title="Uninstall Failed")


def update_build_state(app):
    """Enable/disable build button and update game hint."""
    valid = bool(app.game_path) and Path(app.game_path).is_dir()
    if not valid:
        app.build_btn.configure(state='disabled', bootstyle='success')
        app._game_hint.configure(
            text="Set your game folder to build",
            foreground=THEME_COLORS['warning'])
        app._game_hint.pack(side='left', padx=(PAD_XS, 0))
    else:
        app.build_btn.configure(state='normal', bootstyle='success')
        app._game_hint.pack_forget()


def pulse_game_hint(app):
    """Briefly pulse the game hint label to draw attention."""
    original = THEME_COLORS['warning']
    bright = THEME_COLORS['heading']
    app._game_hint.configure(foreground=bright)
    app.after(150, lambda: app._game_hint.configure(foreground=original))
    app.after(300, lambda: app._game_hint.configure(foreground=bright))
    app.after(450, lambda: app._game_hint.configure(foreground=original))
