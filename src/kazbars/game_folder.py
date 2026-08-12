"""
KazBars — Game folder configuration.

UI + persistence for the configured Age of Conan install folder. Includes the
"uninstall KazBars from the game" action and build-button state sync. Functions
take the KazBarsApp instance as first arg.
"""

from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox, MessageDialog

from . import game_persistence as gp
from . import userdata
from .ui_helpers import PAD_XS, THEME_COLORS
from .ui_widgets import add_tooltip, app_toast, confirm


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

    app.game_path = str(Path(path).resolve())
    save_game_path(app)
    refresh_game_path_label(app)
    check_install_health(app)


def clear_game_path(app):
    """Forget the current game folder."""
    if not app.game_path:
        return
    if not confirm(
        "Clear the configured game folder?\n\nThis won't delete any game files.",
        title="Clear Game Folder", action="Clear game folder",
    ):
        return
    app.game_path = None
    save_game_path(app)
    refresh_game_path_label(app)


def show_game_context_menu(app, event):
    """Show the change/open/clear menu for the game-folder label."""
    ok = bool(app.game_path) and Path(app.game_path).is_dir()
    app._game_context_menu.entryconfigure(
        "Open in Explorer", state='normal' if ok else 'disabled')
    app._game_context_menu.tk_popup(event.x_root, event.y_root)


def save_game_path(app):
    """Persist game_path to settings and notify observers."""
    if app.game_path:
        app.settings.set('game_path', app.game_path)
    else:
        app.settings.data.pop('game_path', None)
    app.settings.save()
    app.grids_panel.notify_game_path_changed()


def uninstall_game(app):
    """Remove KazBars files from the configured game folder."""
    if not app.game_path:
        Messagebox.show_warning(
            "No game folder set. Configure one in the bottom bar first.",
            title="No Game Folder"
        )
        return
    if not confirm(
        "Remove KazBars files from your game folder?\n\n"
        "This deletes KazBars.swf, auto-load entries, and reload scripts.",
        title="Uninstall from Game Folder", action="Remove KazBars files", danger=True
    ):
        return
    from .build_executor import uninstall_from_client
    ok, msg = uninstall_from_client(
        app.game_path,
        damageinfo_pristine=Path(app.assets_path) / "damageinfo" / "DamageInfo.swf")
    if ok:
        app_toast(app, msg, 'success', 8)
    else:
        Messagebox.show_error(msg, title="Uninstall Failed")


def repair_game_install(app):
    """Re-apply the module declarations after a game patch wiped them.

    The patcher restores the stock `MainPrefs.xml`/`Modules.xml`, which takes our
    declarations with them; the next launch would then start without them and the
    engine would strip the saved positions (THE STRIP RULE, game_persistence).
    This puts the declarations and the bypass flag back and, if the archives were
    already lost, re-injects them from the healthy snapshot the health check took.

    Refuses to run while any engine process is alive — the patcher saves
    `Prefs_3.xml` on exit too, so its shutdown would undo a fresh re-injection.
    """
    if not app.game_path or not Path(app.game_path).is_dir():
        Messagebox.show_warning(
            "No game folder set. Configure one in the bottom bar first.",
            title="No Game Folder")
        return

    from .build_executor import get_running_engine_process
    running = get_running_engine_process()
    if running:
        app_toast(app, f"Close {running} first, then repair.", 'warning', 8)
        return

    declarations = gp.discover_aoc_archive_declarations(app.game_path)
    try:
        gp.splice_declarations(app.game_path, declarations)
    except ValueError:
        # Damaged markers: the surgical path can't run, so fall back to each
        # file's one-time backup and splice onto that known-good text.
        gp.strip_declarations(app.game_path)
        try:
            gp.splice_declarations(app.game_path, declarations)
        except (ValueError, OSError) as e:
            Messagebox.show_error(
                f"Couldn't repair the game files.\n\n{e}\n\n"
                "Run Build & Install to reinstall from scratch.",
                title="Repair Failed")
            return
    except OSError as e:
        Messagebox.show_error(
            f"Couldn't write to the game folder.\n\n{e}",
            title="Repair Failed")
        return

    gp.ensure_flag(app.game_path)

    restored = _reinject_managed_archives(declarations)
    if restored:
        app_toast(app, f"Repaired — restored {', '.join(restored)}.", 'success', 8)
    else:
        app_toast(app, "Repaired — KazBars is declared again.", 'success', 8)


def _reinject_managed_archives(declarations):
    """Put back any archive the engine stripped, from our snapshot. Covers the
    mods we adopted declarations for too — we are the reason they survive."""
    live = gp.prefs3_path()
    snapshot = userdata.prefs3_snapshot_path()
    if live is None or not snapshot.is_file():
        return ()
    names = {gp.ARCHIVE_NAME} | gp.archive_names_in('\n'.join(declarations))
    return gp.reinject_archives(live, snapshot, names)


def check_install_health(app):
    """Verify the game still loads KazBars, and keep the repair snapshot fresh.

    Runs at startup and whenever the game folder changes. Healthy means our
    markers are present at the *current* targets — which is why installing a UI
    mod that introduces a `Customized/Modules.xml` reads as unhealthy: our Default
    block is no longer the one the game loads, and Repair moves it.
    """
    if getattr(app, '_building', False) or not app.game_path:
        return
    if not app.settings.get('has_built_before'):
        return
    game = Path(app.game_path)
    if not (game / "Data" / "Gui" / "Default" / "Flash" / "KazBars.swf").is_file():
        return

    if gp.is_merged(app.game_path):
        gp.snapshot_prefs3(userdata.prefs3_snapshot_path())
        gp.ensure_flag(app.game_path)
    else:
        app_toast(
            app,
            "The game no longer loads KazBars — click to repair.",
            'warning', 12, key='install_health',
            on_click=lambda: repair_game_install(app))


def offer_game_desktop_link(app, first_build=False):
    """Offer a desktop shortcut that launches the game directly.

    The persistence era changes how the game should be started: the Funcom
    patcher restores the stock XMLs, so going through it costs the user their
    declarations until the next Repair. A shortcut straight to a client exe makes
    the right way the easy way. Offered once automatically after a successful
    build; the Game menu re-offers it whenever the user asks.
    """
    if not app.game_path or not Path(app.game_path).is_dir():
        if not first_build:
            Messagebox.show_warning(
                "No game folder set. Configure one in the bottom bar first.",
                title="No Game Folder")
        return

    available = [name for name in gp.GAME_EXES
                 if (Path(app.game_path) / name).is_file()]
    if not available:
        if not first_build:
            Messagebox.show_warning(
                "No Age of Conan executable found in the game folder.",
                title="Nothing to Link")
        return

    # Mark it offered on *show*, not on accept — declining is an answer, and
    # re-asking after every build would be nagging.
    app.settings.set('desktop_shortcut_offered', True)
    app.settings.save()

    labels = {'AgeOfConanDX10.exe': "Create DX10 shortcut",
              'AgeOfConan.exe': "Create DX9 shortcut"}
    # Decline leftmost, DX10 rightmost as the primary: it's the modern client and
    # what most players run. GAME_EXES order already puts DX9 before DX10.
    buttons = ['Not now:secondary'] + [
        f"{labels[name]}:{'primary' if name == 'AgeOfConanDX10.exe' else 'secondary'}"
        for name in available
    ]

    dialog = MessageDialog(
        "Start the game from a desktop shortcut to keep your grid positions.\n\n"
        "Launching through the Funcom patcher resets the interface files "
        "KazBars installs — you'd need Game ▸ Repair game install each time.",
        title="Create a Desktop Shortcut", parent=app, buttons=buttons)
    dialog.show()

    chosen = next((name for name in available if labels[name] == dialog.result), None)
    if chosen is None:
        return

    ok, msg = gp.create_game_desktop_link(app.game_path, chosen)
    if ok:
        app_toast(app, f"Shortcut created: {labels[chosen]}", 'success', 8)
    else:
        Messagebox.show_error(msg, title="Shortcut Failed")


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
