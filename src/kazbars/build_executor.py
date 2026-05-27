"""
KazBars — Build Executor
Compile KazBars.swf and install to game folders.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from .build_utils import strip_marker_block, update_script_with_marker
from .grids_generator import build_grids

logger = logging.getLogger(__name__)


# Legacy filenames removed from Data/Gui/Default/Flash before each install.
# These are predecessor names: kzgrids.swf / KzGrids.swf were the original
# Kaz Flash Mods era; KazGrids.swf was the Kaz Grids era. The current
# KazBars.swf takes ownership and supersedes all of them.
LEGACY_FLASH_FILES = ("kzgrids.swf", "KzGrids.swf", "KazGrids.swf")

# Predecessor Aoc/* module folders to remove on install (case-insensitive on Windows).
LEGACY_AOC_DIRS = ("KzGrids", "KazGrids", "Kazbars")

# Marker block strings used in Scripts/auto_login. Old markers are stripped
# on every install/uninstall so a single rename pass converges.
AUTO_LOAD_MARKER = "# KazBars auto-load"
LEGACY_AUTO_LOAD_MARKERS = ("# KzGrids auto-load",)


def compile_to_staging(grids, database, assets_path, compiler, app_version,
                       include_console=False, cast_config=None):
    """Compile KazBars.swf to a temp staging dir.

    Returns (staging_dir, result) where result is (success_bool, message).
    Caller must clean up staging_dir.
    """
    base_swf = assets_path / "kazbars" / "base.swf"
    stubs_path = assets_path / "kazbars" / "stubs"

    staging_dir = Path(tempfile.mkdtemp(prefix="kazbars_"))
    output_swf = staging_dir / "KazBars.swf"

    result = build_grids(
        grids, database,
        str(base_swf), str(stubs_path),
        str(output_swf), str(compiler),
        app_version,
        assets_path=assets_path,
        include_console=include_console,
        cast_config=cast_config,
    )
    return staging_dir, result


def install_to_client(staging_swf, game_path, use_aoc):
    """Install compiled SWF + scripts to the game folder.

    Returns (success, error_message).
    """
    flash_path = Path(game_path) / "Data" / "Gui" / "Default" / "Flash"
    scripts_path = Path(game_path) / "Scripts"

    try:
        flash_path.mkdir(parents=True, exist_ok=True)
        scripts_path.mkdir(parents=True, exist_ok=True)

        cleanup_legacy_files(game_path)

        shutil.copy2(staging_swf, flash_path / "KazBars.swf")

        if use_aoc:
            aoc_dir = Path(game_path) / "Data" / "Gui" / "Aoc" / "KazBars"
            write_xml_add_files(aoc_dir)

        create_scripts(scripts_path, use_aoc=use_aoc)
    except OSError as e:
        return False, (
            f"Could not write files\n\n{e}\n\n"
            "Check that your disk has free space and the game folder is not read-only."
        )

    return True, ""


def cleanup_legacy_files(game_path):
    """Remove leftover SWFs and Aoc-module folders from predecessor versions
    (Kaz Flash Mods, Kaz Grids, the original KazBars mod) before the fresh install.
    """
    flash = Path(game_path) / "Data" / "Gui" / "Default" / "Flash"
    for stale in LEGACY_FLASH_FILES:
        try:
            (flash / stale).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not remove %s: %s", stale, e)

    for stale_dir in LEGACY_AOC_DIRS:
        legacy_aoc = Path(game_path) / "Data" / "Gui" / "Aoc" / stale_dir
        if legacy_aoc.is_dir():
            shutil.rmtree(legacy_aoc, ignore_errors=True)


def uninstall_from_client(game_path):
    """Remove KazBars files from the game folder.

    Returns (success, message).
    """
    removed = []
    try:
        swf = Path(game_path) / "Data" / "Gui" / "Default" / "Flash" / "KazBars.swf"
        if swf.exists():
            swf.unlink()
            removed.append("KazBars.swf")

        aoc_dir = Path(game_path) / "Data" / "Gui" / "Aoc" / "KazBars"
        if aoc_dir.exists():
            shutil.rmtree(aoc_dir)
            removed.append("Aoc module files")

        for script in ("reloadgrids", "unloadgrids"):
            p = Path(game_path) / "Scripts" / script
            if p.exists():
                p.unlink()
                removed.append(script)

        auto_login = Path(game_path) / "Scripts" / "auto_login"
        if auto_login.exists():
            try:
                content = auto_login.read_text(encoding='utf-8')
                new_content = strip_marker_block(content, AUTO_LOAD_MARKER)
                for legacy in LEGACY_AUTO_LOAD_MARKERS:
                    new_content = strip_marker_block(new_content, legacy)
                if new_content != content:
                    if new_content.strip():
                        auto_login.write_text(new_content, encoding='utf-8')
                    else:
                        auto_login.unlink()
                    removed.append("auto_login entry")
            except (UnicodeDecodeError, OSError):
                logger.debug("Could not read/clean auto_login markers", exc_info=True)
    except OSError as e:
        return False, f"Could not remove files:\n\n{e}"

    if not removed:
        return True, "Nothing to remove — KazBars isn't installed in this game folder."
    return True, "Removed: " + ", ".join(removed)


def detect_aoc_launcher(game_path):
    """Return True if this folder shows the launcher-bypass fingerprint
    (aoc.exe or Aoc.log under Data/Gui/Aoc)."""
    aoc_dir = Path(game_path) / "Data" / "Gui" / "Aoc"
    return (aoc_dir / "aoc.exe").exists() or (aoc_dir / "Aoc.log").exists()


GAME_PROCESSES = ('AgeOfConan.exe', 'AgeOfConanDX10.exe')


def get_running_game_process():
    """Return the name of a running AoC game process, or None.

    Aoc.exe (the launcher bypass loader) doesn't lock the overlay files —
    the actual game process does. Only the DX9/DX10 game exes matter here.
    """
    for name in GAME_PROCESSES:
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {name}', '/NH'],
                capture_output=True, text=True, timeout=5
            )
            if name.lower() in result.stdout.lower():
                return name
        except Exception:
            continue
    return None


def is_aoc_running():
    """Return True if any AoC game process is currently running."""
    return get_running_game_process() is not None


def write_xml_add_files(aoc_dir):
    """Write MainPrefs.xml.add and Modules.xml.add for Aoc.exe module system."""
    aoc_dir.mkdir(parents=True, exist_ok=True)

    prefs = (
        '\t<Value name="KazBars" value="true" />\n'
        '\t<Archive name="KazBars settings" />\n'
    )
    modules = (
        '\t<Module\n'
        '\t\tname              = "KazBars"\n'
        '\t\tmovie             = "KazBars.swf"\n'
        '\t\tflags             = "GMF_CFG_STORE_USER_CONFIG"\n'
        '\t\tdepth_layer       = "Top"\n'
        '\t\tsub_depth         = "0"\n'
        '\t\tvariable          = "KazBars"\n'
        '\t\tcriteria          = "KazBars &amp;&amp; (guimode &amp; (GUIMODEFLAGS_INPLAY | GUIMODEFLAGS_ENABLEALLGUI))"\n'
        '\t\tconfig_name       = "KazBars settings"\n'
        '\t/>\n'
    )

    (aoc_dir / "MainPrefs.xml.add").write_text(prefs, encoding='utf-8')
    (aoc_dir / "Modules.xml.add").write_text(modules, encoding='utf-8')


def create_scripts(scripts_path, use_aoc=False):
    """Write Scripts/reloadgrids, Scripts/unloadgrids and update Scripts/auto_login."""
    reload_content = "/unloadclip KazBars.swf\n/delay 100\n/loadclip KazBars.swf"
    unload_content = "/unloadclip KazBars.swf"
    reload_script = scripts_path / "reloadgrids"
    unload_script = scripts_path / "unloadgrids"
    auto_login_script = scripts_path / "auto_login"

    reload_script.write_text(reload_content, encoding='utf-8')
    unload_script.write_text(unload_content, encoding='utf-8')

    if use_aoc:
        # Aoc.exe handles loading via xml.add — strip any KazBars/legacy markers
        if auto_login_script.exists():
            try:
                content = auto_login_script.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                logger.warning("auto_login corrupt — overwriting")
                content = ""
            content = strip_marker_block(content, AUTO_LOAD_MARKER)
            for legacy in LEGACY_AUTO_LOAD_MARKERS:
                content = strip_marker_block(content, legacy)
            if content.strip():
                auto_login_script.write_text(content, encoding='utf-8')
            else:
                auto_login_script.unlink(missing_ok=True)
    else:
        update_script_with_marker(
            auto_login_script, AUTO_LOAD_MARKER, reload_content,
            old_markers=list(LEGACY_AUTO_LOAD_MARKERS),
        )
