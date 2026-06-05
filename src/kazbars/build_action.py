"""
KazBars — Build action.

The Build & Install flow: validate prerequisites, auto-save the profile,
compile grids to a staging SWF via MTASC, install to the game folder, and
surface progress + summary via the BuildLoadingScreen. Takes the KazBarsApp
instance as first arg.
"""

import logging
import shutil
from pathlib import Path

from ttkbootstrap.dialogs import Messagebox

from . import damageinfo_settings as dis
from . import game_folder, profile_io
from .build_loading import BuildLoadingScreen, show_close_game_required_dialog
from .build_utils import find_compiler
from .grids_generator import MAX_TOTAL_SLOTS
from .ui_helpers import THEME_COLORS
from .ui_widgets import app_toast, flash_status_bar

logger = logging.getLogger(__name__)


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
        Messagebox.show_error(
            f"These grids have no tracked buffs and would appear empty in-game:\n\n{names}\n\n"
            "Add tracked buffs (or slot assignments for static grids), or disable the grid.",
            title="Empty Grids"
        )
        return

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

    from .build_executor import compile_to_staging, install_to_client, is_aoc_running

    loading = BuildLoadingScreen(app)
    staging_dir = None
    try:
        loading.advance_step("Compiling KazBars...")
        app.update()

        staging_dir, compile_result = compile_to_staging(
            grids, app.database, app.assets_path, compiler, app.app_version,
            include_console=bool(app.settings.get('build_console', False)),
            cast_config=app.grids_panel.get_cast_timer_config(),
        )

        if not compile_result[0]:
            loading.show_summary(
                [], compile_result, profile_name=profile_name)
            app_toast(app, "Build failed", 'error', 10)
            flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])
            return

        # Damage Numbers: bake + compile the modded DamageInfo.swf into the same
        # staging dir (gated by the master enable). Both SWFs are staged before any
        # install so the deploy is all-or-nothing. When disabled, damageinfo_swf
        # stays None and install reverts any previously-installed mod to stock.
        damageinfo_swf = None
        if di_enabled:
            loading.advance_step("Baking damage numbers...")
            app.update()
            from .damageinfo_generator import build_damageinfo
            staged_di = staging_dir / "DamageInfo.swf"
            di_ok, di_msg = build_damageinfo(app.assets_path, di_settings, compiler, staged_di)
            if not di_ok:
                logger.warning("Damage Numbers build failed: %s", di_msg)
                loading.show_summary([], (False, di_msg), profile_name=profile_name)
                app_toast(app, "Damage Numbers build failed", 'error', 10)
                flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])
                return
            damageinfo_swf = staged_di

        loading.advance_step("Installing...")
        app.update()

        # TextColors.xml customizations, gated by the master enable so disabling reverts
        # them: the "Group my resource numbers" toggle (resource-loss directions) and the
        # per-source color editor. When off, install regenerates stock from the backup.
        group_resources = di_enabled and bool(di_settings.get('other_resource_loss_to_target'))
        source_colors = di_settings.get('source_colors', {}) if di_enabled else {}

        staging_swf = staging_dir / "KazBars.swf"
        ok, err = install_to_client(
            staging_swf, app.game_path, app.use_aoc_bypass,
            damageinfo_swf=damageinfo_swf,
            damageinfo_pristine=Path(app.assets_path) / "damageinfo" / "DamageInfo.swf",
            group_resources=group_resources, source_colors=source_colors)
        client_results = [(game_folder.format_game_path(app.game_path), ok, err)]

        aoc_running = app.use_aoc_bypass and is_aoc_running()

        if ok:
            if app.use_aoc_bypass and aoc_running:
                app_toast(app, "/reloadui in-game", 'success', 8)
            elif app.use_aoc_bypass:
                app_toast(app, "launch the game", 'success', 8)
            else:
                app_toast(app, "/reloadui + /reloadgrids", 'success', 8)
            flash_status_bar(app.bottom_bar)
            app.grids_panel.notify_build_done(app.use_aoc_bypass, app.current_profile)
            if not app.settings.get('has_built_before'):
                app.settings.set('has_built_before', True)
                app.settings.save()
        else:
            app_toast(app, "Build failed", 'error', 10)
            flash_status_bar(app.bottom_bar, THEME_COLORS['danger'])

        loading.show_summary(
            client_results, compile_result, profile_name=profile_name,
            aoc_installed=app.use_aoc_bypass, aoc_running=aoc_running)

    except Exception as e:
        logger.exception("Unexpected build error")
        loading.destroy()
        Messagebox.show_error(
            "Something went wrong during the build.\n\n"
            "Your game files may not have been updated.\n\n"
            f"({e})",
            title="Build Error"
        )
        app_toast(app, "Build failed", 'error', 10)
    finally:
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)
        app._building = False
        app.bind_all('<Control-b>', lambda e: build(app))
        game_folder.update_build_state(app)
