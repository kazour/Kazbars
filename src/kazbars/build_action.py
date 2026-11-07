"""
KazBars — Build action.

The Build & Install flow: validate prerequisites, auto-save the profile,
compile grids to a staging SWF, install to the game folder, and
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

from . import game_folder, onslaught
from .app_popups import show_close_game_required_dialog
from .build_loading import BuildLoadingScreen
from .cast_timer import is_enabled as cast_is_enabled
from .cast_timer import validate_config as validate_cast_config
from .console import ships as console_ships
from .grid_model import get_game_resolution_or_default, max_slots, slot_count
from .grids_generator import grid_ships, unresolved_refs
from .profile_document import build_signature
from .ui_helpers import THEME_COLORS
from .ui_widgets import app_toast, flash_status_bar

logger = logging.getLogger(__name__)

# Each build phase (compile / bake / install) stays on screen at least this long so
# the loading animation reads as a deliberate beat rather than a flash now that the
# work is near-instant. Enforced on the worker thread, so it paces the display
# without ever blocking the UI or the next phase's real work.
PHASE_MIN_MS = 300


def _declarations_gate(app):
    """Block while any engine process is running, but only when our
    declarations aren't already merged into the live game files: the client
    has to start with them in place for the archive to survive, and a
    patcher left open strips them on its own exit-save. Once merged,
    install_to_client is an idempotent no-op and /reloadui handles the swap —
    so this fires on the first build ever, and again on an upgrade whose
    client never got spliced (e.g. a game patch wiped the declarations).
    Returns False (after showing the dialog) when the build must stop."""
    from .game_persistence import is_merged
    if not is_merged(app.game_path):
        from .build_executor import get_running_engine_process
        running = get_running_engine_process()
        if running:
            show_close_game_required_dialog(app, process_name=running)
            return False
    return True


def build(app):
    """Build and install KazBars.swf to the configured game folder."""
    if app._building:
        return

    valid = bool(app.game_path) and game_folder.is_game_folder(app.game_path)

    grids = app.grids_panel.get_profile_data()
    # A hand-edited grid past its limit blocks the build only if it would be baked.
    oversized = next((g for g in grids
                      if grid_ships(g) and slot_count(g) > max_slots(g['type'])), None)
    oversized_msg = '' if oversized is None else (
        f"Grid '{oversized['id']}' has {slot_count(oversized)} slots; "
        f"a grid holds at most {max_slots(oversized['type'])}.\n\nReduce its rows or columns.")

    di_settings = dict(app.profile_store.get_section('damage_numbers'))
    di_enabled = bool(di_settings.get('enabled'))
    di_assets_ok = (
        (Path(app.assets_path) / "damageinfo" / "DamageInfo.swf").exists()
        and (Path(app.assets_path) / "damageinfo" / "src" / "__Packages").exists()
    )

    # Extras stand on their own: nothing downstream needs a grid, so an
    # extras-only build is legitimate. Mirrors the generator's include gates —
    # cast through is_enabled on the validated config, stopwatch/inspect off
    # their own flag, the console and the onslaught tracker off their ships().
    # Each config is a profile section; snapshot-copy them off the live store
    # dicts here so the worker thread never reads a dict the main thread
    # could mutate.
    cast_config = validate_cast_config(dict(app.profile_store.get_section('cast_timer')))
    stopwatch_config = dict(app.profile_store.get_section('stopwatch'))
    inspect_config = dict(app.profile_store.get_section('inspect'))
    console_config = dict(app.profile_store.get_section('console'))
    onslaught_config = dict(app.profile_store.get_section('onslaught'))
    any_extra = (
        cast_is_enabled(cast_config)
        or bool(stopwatch_config.get('enabled'))
        or bool(inspect_config.get('enabled'))
        or console_ships(console_config)
        or onslaught.ships(onslaught_config)
        or di_enabled
    )

    validations = [
        (not valid,
         "No valid game folder configured.\n\n"
         "Set your Age of Conan folder from the bottom bar."),
        (not grids and not any_extra,
         "Nothing to build.\n\nAdd a grid or enable an extra first."),
        (oversized is not None, oversized_msg),
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

    if not _declarations_gate(app):
        return

    # Mirror the grid cards into the store, then flush, so built == saved and
    # the build signature hashes what actually gets baked; the summary line
    # names the profile.
    profile_name = None
    if app.profile_store is not None:
        app._on_grids_edited()
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
        'app_version': app.app_version,
        'cast_config': cast_config,
        'stopwatch_config': stopwatch_config,
        'inspect_config': inspect_config,
        'console_config': console_config,
        'onslaught_config': onslaught_config,
        'overlay': dict(app.profile_store.get_section('overlay')),
        'anchor': (app.settings.get('anchor_side'), app.settings.get('anchor_up')),
        'game_resolution': get_game_resolution_or_default(),
        'game_path': app.game_path,
        'di_enabled': di_enabled,
        'di_settings': di_settings,
        'profile_name': profile_name,
        # Inert refs the generator will skip — the summary reports the count
        # (the old load-time missing-buff warning retired into this line).
        'unresolved': len(unresolved_refs(grids, app.database)),
        # Identity of what this build bakes, for the last_build pref (written
        # only on a successful install) and the grids panel's status row.
        'build_profile_id': app.profile_store.document['id'],
        'build_profile_name': app.profile_store.document['name'],
        'build_signature': build_signature(app.registry, app.profile_store.document),
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
            ctx['grids'], ctx['database'], ctx['assets_path'], ctx['app_version'],
            cast_config=ctx['cast_config'],
            stopwatch_config=ctx['stopwatch_config'],
            inspect_config=ctx['inspect_config'],
            console_config=ctx['console_config'],
            onslaught_config=ctx['onslaught_config'],
            overlay=ctx['overlay'],
            anchor=ctx['anchor'],
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
            di_ok, di_msg = build_damageinfo(ctx['assets_path'], ctx['di_settings'], staged_di)
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
            # Record what this install baked — the status row compares the live
            # document against it. Written only on success: a failed install
            # leaves the previous build (and its record) in place.
            app.settings.set('last_build', {
                'profile_id': ctx['build_profile_id'],
                'profile_name': ctx['build_profile_name'],
                'hash': ctx['build_signature'],
                'target_resolution': list(ctx['game_resolution']),
                'anchor': list(ctx['anchor']),
            })
            if not app.settings.get('has_built_before'):
                app.settings.set('has_built_before', True)
            app.settings.save()
            app.grids_panel.notify_build_done()
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
