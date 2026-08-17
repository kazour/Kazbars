"""
KazBars — Game folder configuration.

UI + persistence for the configured Age of Conan install folder. Includes the
"uninstall KazBars from the game" action and build-button state sync. Functions
take the KazBarsApp instance as first arg.
"""

import logging
import tempfile
from pathlib import Path
from tkinter import filedialog

from ttkbootstrap.dialogs import Messagebox, MessageDialog

from . import game_persistence as gp
from . import userdata
from .ui_helpers import PAD_XS, THEME_COLORS
from .ui_widgets import add_tooltip, app_toast, confirm

logger = logging.getLogger(__name__)


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
        # The file itself is unusable, so the surgical path can't run: fall back
        # to each file's backup and splice onto that known-good text.
        gp.strip_declarations(app.game_path)
        try:
            gp.splice_declarations(app.game_path, declarations)
        except (ValueError, OSError) as e:
            Messagebox.show_error(
                f"Couldn't repair the game files.\n\n{e}\n\n"
                "Run the game patcher once to restore them, then "
                "Game ▸ Repair game install.",
                title="Repair Failed")
            return
    except OSError as e:
        Messagebox.show_error(
            f"Couldn't write to the game folder.\n\n{e}",
            title="Repair Failed")
        return

    flag_ok = True
    try:
        gp.ensure_flag(app.game_path)
    except OSError as e:
        flag_ok = False
        logger.warning("Could not create %s: %s", gp.FLAG_NAME, e)

    # An upgrader reaches Repair from the startup toast with their pre-persistence
    # load path still live (auto_login entry or Aoc fragments). Leaving it would
    # load the overlay twice, so clear it now that the new one is in place.
    from .build_executor import cleanup_legacy_files
    cleanup_legacy_files(app.game_path)

    restored = _reinject_managed_archives(declarations)
    damageinfo_ok = _restore_damageinfo(app)

    if not flag_ok:
        app_toast(app, f"Repaired, but {gp.FLAG_NAME} couldn't be written.",
                  'warning', 10)
    elif not damageinfo_ok:
        app_toast(app, "Repaired — run Build & Install to restore Damage Numbers.",
                  'warning', 10)
    elif restored:
        app_toast(app, f"Repaired — restored {', '.join(restored)}.", 'success', 8)
    else:
        app_toast(app, "Repaired — KazBars is declared again.", 'success', 8)


def _restore_damageinfo(app):
    """Re-install the Damage Numbers mod, which the patcher overwrote too.

    The same patch that restores the interface XMLs restores the stock
    DamageInfo.swf, so a Repair that skipped this would put the grids back and
    silently leave the numbers vanilla. Rebakes from the current settings through
    the compiler and commits down `build_executor`'s staged path, exactly as a
    build does.

    Returns False only when the mod is enabled and could not be restored — the
    caller says so, but Repair still counts as done: the declarations are what
    it exists for, and a rebuild fixes the rest.
    """
    from .build_executor import commit_damageinfo
    from .build_utils import find_compiler
    from .damageinfo_generator import build_damageinfo

    settings = dict(app.profile_store.get_section('damage_numbers'))
    if not settings.get('enabled'):
        return True

    compiler = find_compiler(app.assets_path, app.app_path)
    if compiler is None:
        logger.warning("Damage Numbers not restored: no compiler found")
        return False

    flash = Path(app.game_path) / "Data" / "Gui" / "Default" / "Flash"
    pristine = Path(app.assets_path) / "damageinfo" / "DamageInfo.swf"
    with tempfile.TemporaryDirectory(prefix="kazbars_repair_") as staging:
        staged = Path(staging) / "DamageInfo.swf"
        ok, msg = build_damageinfo(app.assets_path, settings, compiler, staged)
        if not ok:
            logger.warning("Damage Numbers not restored: %s", msg)
            return False
        return commit_damageinfo(flash, staged, pristine)


def _managed_archive_names(declarations):
    """Our archive plus every one we adopted a declaration for — we are the
    reason a bare session preserves theirs, so they are ours to restore too."""
    return {gp.ARCHIVE_NAME} | gp.archive_names_in('\n'.join(declarations))


def _prefs3_pair():
    """(live Prefs_3.xml, our snapshot) when both are usable, else None."""
    live = gp.prefs3_path()
    snapshot = userdata.prefs3_snapshot_path()
    if live is None or not snapshot.is_file():
        return None
    return live, snapshot


def _missing_managed_archives(declarations):
    """Managed archives the engine has stripped that our snapshot can supply."""
    pair = _prefs3_pair()
    if pair is None:
        return ()
    return gp.missing_archives(*pair, _managed_archive_names(declarations))


def _reinject_managed_archives(declarations):
    """Put back any archive the engine stripped, from our snapshot."""
    pair = _prefs3_pair()
    if pair is None:
        return ()
    return gp.reinject_archives(*pair, _managed_archive_names(declarations))


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
        _refresh_repair_insurance(app)
    else:
        app_toast(
            app,
            "The game no longer loads KazBars — click to repair.",
            'warning', 12, key='install_health',
            on_click=lambda: repair_game_install(app))


def _refresh_repair_insurance(app):
    """Healthy install: restore anything the engine stripped, then re-snapshot.

    A user who recovers by rebuilding rather than by Repair arrives here with the
    declarations back but the positions already gone, so the re-injection has to
    live on this path too — otherwise a stripped archive would sit unused in the
    snapshot forever. Order matters: re-inject first, so the snapshot taken
    afterwards is the complete one.

    Every write here is best-effort. A read-only game folder must not stop the
    app from starting — this runs during startup.
    """
    declarations = gp.discover_aoc_archive_declarations(app.game_path)
    if _missing_managed_archives(declarations):
        from .build_executor import get_running_engine_process
        running = get_running_engine_process()
        if running:
            # Its exit-save would strip the re-injection straight back out, and
            # the live file is incomplete — so don't snapshot over a good one.
            app_toast(app, f"Close {running} to restore your saved positions.",
                      'warning', 10, key='install_health')
            return
        restored = _reinject_managed_archives(declarations)
        if restored:
            app_toast(app, f"Restored saved positions: {', '.join(restored)}.",
                      'success', 8, key='install_health')

    try:
        gp.snapshot_prefs3(userdata.prefs3_snapshot_path())
        gp.ensure_flag(app.game_path)
    except OSError as e:
        logger.warning("Could not refresh repair insurance: %s", e)


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
