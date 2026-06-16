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

from . import damageinfo_settings as dis
from . import game_folder, profile_io
from .app_popups import show_close_game_required_dialog
from .build_loading import BuildLoadingScreen
from .build_utils import find_compiler
from .grids_generator import MAX_TOTAL_SLOTS
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

    di_settings = dis.load_settings(app.settings_path)
    di_enabled = bool(di_settings.get('enabled'))
    di_assets_ok = (
        (Path(app.assets_path) / "damageinfo" / "DamageInfo.swf").exists()
        and (Path(app.assets_path) / "damageinfo" / "src" / "__Packages").exists()
    )

    validations = [
        (not valid,
         "No valid game folder configured.\n\n"
         "Set your Age of Conan folder from the bottom bar."),
        (compiler is None,
         "A required build file is missing.\n\n"
         "Re-download KazBars to restore it."),
        (not grids,
         "No grids to build.\n\nAdd at least one grid first."),
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
        app._mark_modified()
        app.grids_panel.refresh_panels(expand_index=-1)

    # Aoc.exe users only: block while the game is running, but only on the
    # first build. After a successful install, /reloadui handles the swap.
    if app.use_aoc_bypass and not app.settings.get('has_built_before'):
        from .build_executor import get_running_game_process
        running = get_running_game_process()
        if running:
            show_close_game_required_dialog(app, process_name=running)
            return

    # Auto-save profile before building
    profile_name = None
    if app.current_profile:
        try:
            profile_io.do_save_profile(app, Path(app.current_profile), silent=True)
            profile_name = Path(app.current_profile).stem
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
        'cast_config': app.grids_panel.get_cast_timer_config(),
        'stopwatch_config': app.settings.get('stopwatch'),
        'game_path': app.game_path,
        'use_aoc': app.use_aoc_bypass,
        'di_enabled': di_enabled,
        'di_settings': di_settings,
        # TextColors.xml customizations, gated by the master enable so disabling reverts
        # them: "Group my resource numbers", "Split into two columns", per-source colors.
        'group_resources': di_enabled and bool(di_settings.get('other_resource_loss_to_target')),
        'split_incoming': di_enabled and bool(di_settings.get('fixed_col_split')),
        'source_colors': di_settings.get('source_colors', {}) if di_enabled else {},
        'profile_name': profile_name,
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

    staging_dir = None
    try:
        started = time.monotonic()
        staging_dir, compile_result = compile_to_staging(
            ctx['grids'], ctx['database'], ctx['assets_path'], ctx['compiler'],
            ctx['app_version'],
            include_console=ctx['include_console'], cast_config=ctx['cast_config'],
            stopwatch_config=ctx['stopwatch_config'],
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
            staging_dir / "KazBars.swf", ctx['game_path'], ctx['use_aoc'],
            damageinfo_swf=damageinfo_swf,
            damageinfo_pristine=Path(ctx['assets_path']) / "damageinfo" / "DamageInfo.swf",
            group_resources=ctx['group_resources'], source_colors=ctx['source_colors'],
            split_incoming=ctx['split_incoming'],
        )
        aoc_running = ctx['use_aoc'] and is_aoc_running()
        _hold_phase(started)
        _post(app, _finish_success, app, loading, staging_dir, ctx,
              compile_result, ok, err, aoc_running)
    except Exception as e:
        logger.exception("Unexpected build error")
        _post(app, _build_error, app, loading, staging_dir, e)


def _finish_success(app, loading, staging_dir, ctx, compile_result, ok, err, aoc_running):
    """Main thread: install-result toast + summary, then unlock + clean up."""
    try:
        if ok:
            if ctx['use_aoc'] and aoc_running:
                app_toast(app, "/reloadui in-game", 'success', 8)
            elif ctx['use_aoc']:
                app_toast(app, "launch the game", 'success', 8)
            else:
                app_toast(app, "/reloadui + /reloadgrids", 'success', 8)
            flash_status_bar(app.bottom_bar)
            app.grids_panel.notify_build_done(ctx['use_aoc'], app.current_profile)
            if not app.settings.get('has_built_before'):
                app.settings.set('has_built_before', True)
                app.settings.save()
        else:
            app_toast(app, "Build failed", 'error', 10)
            flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])
        client_results = [(game_folder.format_game_path(ctx['game_path']), ok, err)]
        loading.show_summary(
            client_results, compile_result, profile_name=ctx['profile_name'],
            aoc_installed=ctx['use_aoc'], aoc_running=aoc_running)
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
