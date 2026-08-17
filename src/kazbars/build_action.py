"""
KazBars — Build action.

The Build & Install flow: validate prerequisites, auto-save the profile,
compile grids to a staging SWF via MTASC, install to the game folder, and
surface progress + summary via the BuildLoadingScreen. Takes the KazBarsApp
instance as first arg.
"""

import logging
import shutil
import threading
import time
import tkinter as tk
from pathlib import Path

from ttkbootstrap.dialogs import Messagebox

from . import game_folder
from .app_popups import show_close_game_required_dialog
from .build_loading import BuildLoadingScreen
from .build_utils import find_compiler
from .cast_timer import is_enabled as cast_is_enabled
from .cast_timer import validate_config as validate_cast_config
from .grid_model import get_game_resolution_or_default
from .grids_generator import MAX_TOTAL_SLOTS, unresolved_refs
from .ui_helpers import THEME_COLORS
from .ui_widgets import app_toast, confirm, flash_status_bar

logger = logging.getLogger(__name__)

# Each build phase (compile / bake / install) stays on screen at least this long so
# the loading animation reads as a deliberate beat rather than a flash now that the
# work is near-instant. Enforced on the worker thread, so it paces the display
# without ever blocking the UI or the next phase's real work.
PHASE_MIN_MS = 300


def build(app):
    """Build and install KazBars.swf to the configured game folder."""
    if app._building:
        return

    valid = (
        bool(app.game_path)
        and Path(app.game_path).is_dir()
        and (Path(app.game_path) / "Data" / "Gui" / "Default").exists()
    )

    compiler = find_compiler(app.assets_path, app.app_path)
    grids = app.grids_panel.get_profile_data()
    total_slots = app.grids_panel.get_total_slots()

    di_settings = dict(app.profile_store.get_section('damage_numbers'))
    di_enabled = bool(di_settings.get('enabled'))
    di_assets_ok = (
        (Path(app.assets_path) / "damageinfo" / "DamageInfo.swf").exists()
        and (Path(app.assets_path) / "damageinfo" / "src" / "__Packages").exists()
    )

    # Extras stand on their own: nothing downstream needs a grid, so an
    # extras-only build is legitimate. Mirrors the generator's include gates —
    # cast through is_enabled on the validated config, stopwatch/inspect off
    # their own flag. The three configs are profile sections; snapshot-copy
    # them off the live store dicts here so the worker thread never reads a
    # dict the main thread could mutate.
    cast_config = validate_cast_config(dict(app.profile_store.get_section('cast_timer')))
    stopwatch_config = dict(app.profile_store.get_section('stopwatch'))
    inspect_config = dict(app.profile_store.get_section('inspect'))
    any_extra = (
        bool(app.settings.get('build_console', False))
        or cast_is_enabled(cast_config)
        or bool(stopwatch_config.get('enabled'))
        or bool(inspect_config.get('enabled'))
        or di_enabled
    )

    validations = [
        (not valid,
         "No valid game folder configured.\n\n"
         "Set your Age of Conan folder from the bottom bar."),
        (compiler is None,
         "A required build file is missing.\n\n"
         "Re-download KazBars to restore it."),
        (not grids and not any_extra,
         "Nothing to build.\n\nAdd a grid or enable an extra first."),
        (total_slots > MAX_TOTAL_SLOTS,
         f"Total slots ({total_slots}) exceeds maximum ({MAX_TOTAL_SLOTS}).\n\n"
         "Remove some grids or reduce grid sizes."),
        (di_enabled and not di_assets_ok,
         "Damage Numbers is enabled but its files are missing.\n\n"
         "Re-download KazBars to restore them."),
    ]
    for k, (failed, msg) in enumerate(validations):
        if failed:
            if k == 0:
                game_folder.pulse_game_hint(app)
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
        if not confirm(
            f"These grids have no tracked buffs and would appear empty in-game:\n\n{names}\n\n"
            "Disable them and build anyway?",
            title="Empty Grids", action="Disable & build"
        ):
            return
        for g in grids:
            if g['id'] in empty:
                g['enabled'] = False
        # Rebuild the cards from the mutated dicts BEFORE pushing to the store:
        # _on_grids_edited flushes widget values over the dicts, so pushing
        # first would let the stale enabled-toggles clobber the disable.
        app.grids_panel.refresh_panels(expand_index=-1)
        app._on_grids_edited()

    # Block while any engine process is running, but only on the first build: the
    # client has to start with our declarations in place for the archive to
    # survive, and a patcher left open strips it on its own exit-save. After a
    # successful install, /reloadui handles the swap.
    if not app.settings.get('has_built_before'):
        from .build_executor import get_running_engine_process
        running = get_running_engine_process()
        if running:
            show_close_game_required_dialog(app, process_name=running)
            return

    # Flush the pending autosave so built == saved; the summary line names the
    # profile that was persisted.
    profile_name = None
    if app.profile_store is not None:
        try:
            if app.profile_store.flush():
                profile_name = app.profile_store.document['name']
        except Exception as e:
            logger.warning("Could not save profile before build: %s", e)

    # Lock build — disable all build triggers
    app._building = True
    app.build_btn.configure(state='disabled')
    app.unbind_all('<Control-b>')

    # Snapshot every Tk/main-thread input the worker needs, then run the heavy
    # compile + install off the UI thread so the loading animation never freezes
    # (mirrors content_update's thread + app.after(0, …) marshalling).
    ctx = {
        'grids': grids,
        'database': app.database,
        'assets_path': app.assets_path,
        'compiler': compiler,
        'app_version': app.app_version,
        'include_console': bool(app.settings.get('build_console', False)),
        'cast_config': cast_config,
        'stopwatch_config': stopwatch_config,
        'inspect_config': inspect_config,
        'panel_font_size': app.settings.get('panel_font_size'),
        'game_resolution': get_game_resolution_or_default(),
        'game_path': app.game_path,
        'di_enabled': di_enabled,
        'di_settings': di_settings,
        'profile_name': profile_name,
        # Inert refs the generator will skip — the summary reports the count
        # (the old load-time missing-buff warning retired into this line).
        'unresolved': len(unresolved_refs(grids, app.database)),
    }

    loading = BuildLoadingScreen(app)
    loading.advance_step("Compiling KazBars...")
    threading.Thread(target=_build_worker, args=(app, loading, ctx), daemon=True).start()


def _post(app, fn, *args):
    """Schedule `fn(*args)` on the Tk main loop; quietly no-op if the app is gone."""
    try:
        app.after(0, fn, *args)
    except (RuntimeError, tk.TclError):
        pass


def _hold_phase(started):
    """Keep the current build phase visible at least PHASE_MIN_MS. Runs on the worker
    thread, so the loading animation keeps ticking on the main thread — only pads when
    the phase's real work finished early, and never delays the work itself."""
    remaining = PHASE_MIN_MS / 1000 - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)


def _build_worker(app, loading, ctx):
    """Worker thread: compile → (optionally bake Damage Numbers) → install, each phase
    held for a beat. No Tk here — every UI touch hops to the main loop via `_post`."""
    from .build_executor import compile_to_staging, install_to_client, is_aoc_running
    from .game_persistence import client_supports_flag

    staging_dir = None
    try:
        started = time.monotonic()
        staging_dir, compile_result = compile_to_staging(
            ctx['grids'], ctx['database'], ctx['assets_path'], ctx['compiler'],
            ctx['app_version'],
            include_console=ctx['include_console'], cast_config=ctx['cast_config'],
            stopwatch_config=ctx['stopwatch_config'],
            inspect_config=ctx['inspect_config'],
            panel_font_size=ctx['panel_font_size'],
            game_resolution=ctx['game_resolution'],
        )
        if not compile_result[0]:
            _hold_phase(started)
            _post(app, _finish_failure, app, loading, staging_dir,
                  compile_result, ctx['profile_name'], "Build failed")
            return
        _hold_phase(started)

        # Damage Numbers: bake the modded DamageInfo.swf into the same staging dir
        # (gated by the master enable) so the deploy is all-or-nothing. When disabled,
        # damageinfo_swf stays None and install reverts any installed mod to stock.
        damageinfo_swf = None
        if ctx['di_enabled']:
            started = time.monotonic()
            _post(app, loading.advance_step, "Baking damage numbers...")
            from .damageinfo_generator import build_damageinfo
            staged_di = staging_dir / "DamageInfo.swf"
            di_ok, di_msg = build_damageinfo(
                ctx['assets_path'], ctx['di_settings'], ctx['compiler'], staged_di)
            if not di_ok:
                logger.warning("Damage Numbers build failed: %s", di_msg)
                _hold_phase(started)
                _post(app, _finish_failure, app, loading, staging_dir,
                      (False, di_msg), ctx['profile_name'], "Damage Numbers build failed")
                return
            damageinfo_swf = staged_di
            _hold_phase(started)

        started = time.monotonic()
        _post(app, loading.advance_step, "Installing...")
        ok, err = install_to_client(
            staging_dir / "KazBars.swf", ctx['game_path'],
            damageinfo_swf=damageinfo_swf,
            damageinfo_pristine=Path(ctx['assets_path']) / "damageinfo" / "DamageInfo.swf",
        )
        game_running = is_aoc_running()
        flag_supported = client_supports_flag(ctx['game_path'])
        _hold_phase(started)
        _post(app, _finish_success, app, loading, staging_dir, ctx,
              compile_result, ok, err, game_running, flag_supported)
    except Exception as e:
        logger.exception("Unexpected build error")
        _post(app, _build_error, app, loading, staging_dir, e)


def _finish_success(app, loading, staging_dir, ctx, compile_result, ok, err,
                    game_running, flag_supported):
    """Main thread: install-result toast + summary, then unlock + clean up."""
    try:
        if ok:
            if game_running:
                app_toast(app, "/reloadui in-game", 'success', 8)
            else:
                app_toast(app, "launch the game", 'success', 8)
            flash_status_bar(app.bottom_bar)
            app.grids_panel.notify_build_done()
            if not app.settings.get('has_built_before'):
                app.settings.set('has_built_before', True)
                app.settings.save()
        else:
            app_toast(app, "Build failed", 'error', 10)
            flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])
        # First successful build on this machine: once the summary is dismissed,
        # offer the direct-launch shortcut. Not gated on the has_built_before
        # flip — upgraders already have that set, and they are precisely the
        # audience whose launch habit has to change.
        if ok and not app.settings.get('desktop_shortcut_offered'):
            loading.on_closed = lambda: game_folder.offer_game_desktop_link(
                app, first_build=True)
        client_results = [(game_folder.format_game_path(ctx['game_path']), ok, err)]
        loading.show_summary(
            client_results, compile_result, profile_name=ctx['profile_name'],
            game_running=game_running, flag_supported=flag_supported,
            unresolved=ctx['unresolved'])
    finally:
        _unlock(app, staging_dir)


def _finish_failure(app, loading, staging_dir, result, profile_name, toast_msg):
    """Main thread: compile/bake-failure summary, then unlock + clean up."""
    try:
        loading.show_summary([], result, profile_name=profile_name)
        app_toast(app, toast_msg, 'error', 10)
        flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])
    finally:
        _unlock(app, staging_dir)


def _build_error(app, loading, staging_dir, exc):
    """Main thread: unexpected-exception path — tear down the screen, report, clean up."""
    try:
        loading.destroy()
        Messagebox.show_error(
            "Something went wrong during the build.\n\n"
            "Your game files may not have been updated.\n\n"
            f"({exc})",
            title="Build Error",
        )
        app_toast(app, "Build failed", 'error', 10)
    finally:
        _unlock(app, staging_dir)


def _unlock(app, staging_dir):
    """Drop the staging dir, release the build lock, rebind Ctrl+B, sync the button."""
    if staging_dir:
        shutil.rmtree(staging_dir, ignore_errors=True)
    app._building = False
    app.bind_all('<Control-b>', lambda e: build(app))
    game_folder.update_build_state(app)
