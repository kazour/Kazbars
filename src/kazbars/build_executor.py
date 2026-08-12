"""
KazBars — Build Executor
Compile KazBars.swf and install to game folders.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .build_utils import CREATE_NO_WINDOW, strip_marker_block
from .game_persistence import (
    FLAG_NAME,
    GAME_EXES,
    LEGACY_AOC_DIRS,
    PATCHER_EXE,
    discover_aoc_archive_declarations,
    ensure_flag,
    remove_flag,
    splice_declarations,
    strip_declarations,
)
from .grids_generator import build_grids

logger = logging.getLogger(__name__)


# Legacy filenames removed from Data/Gui/Default/Flash before each install.
# These are predecessor names: kzgrids.swf / KzGrids.swf were the original
# Kaz Flash Mods era; KazGrids.swf was the Kaz Grids era. The current
# KazBars.swf takes ownership and supersedes all of them.
LEGACY_FLASH_FILES = ("kzgrids.swf", "KzGrids.swf", "KazGrids.swf")

# Chat-command scripts the pre-persistence build wrote for /loadclip loading.
# The module now loads itself, so these are dead weight and get removed.
LEGACY_SCRIPTS = ("reloadgrids", "unloadgrids")

# Marker block strings used in Scripts/auto_login. Old markers are stripped
# on every install/uninstall so a single rename pass converges.
AUTO_LOAD_MARKER = "# KazBars auto-load"
LEGACY_AUTO_LOAD_MARKERS = ("# KzGrids auto-load",)

# Damage Numbers: a core game Flash file we replace with a modded build. We back the
# stock file up once so install/disable/uninstall can always revert cleanly.
DAMAGEINFO_FILE = "DamageInfo.swf"
DAMAGEINFO_BACKUP = "DamageInfo.swf.kazbars.bak"

# Returned when a running client holds DamageInfo.swf locked, so nothing was committed.
_DAMAGEINFO_LOCK_MSG = (
    "Couldn't update Damage Numbers.\n\n"
    "Close Age of Conan and build again — the game locks DamageInfo.swf while it's "
    "running. Your grids were not changed."
)


def _files_equal(a, b):
    """True only if both paths exist and have byte-identical contents."""
    try:
        a, b = Path(a), Path(b)
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _atomic_install(src, dst):
    """Copy ``src`` onto ``dst`` atomically.

    Writes a temp file beside ``dst`` then ``os.replace`` (atomic within a volume on
    Windows), so an interrupted/partial write can never leave ``dst`` truncated: on
    failure the target is untouched and the temp is cleaned up. Used for the live game
    file (DamageInfo.swf), which a running client can hold locked — a lock makes the
    replace raise before touching the target, so the caller's OSError handler fires.
    """
    dst = Path(dst)
    tmp = dst.with_name(dst.name + ".kaztmp")
    shutil.copy2(src, tmp)
    try:
        os.replace(tmp, dst)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def compile_to_staging(grids, database, assets_path, compiler, app_version,
                       include_console=False, cast_config=None, stopwatch_config=None,
                       inspect_config=None):
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
        stopwatch_config=stopwatch_config,
        inspect_config=inspect_config,
    )
    return staging_dir, result


def install_to_client(staging_swf, game_path, damageinfo_swf=None,
                      damageinfo_pristine=None):
    """Install the compiled SWF and make the game load it, permanently.

    One mode for everyone: the module declarations are spliced straight into the
    game's own MainPrefs.xml + Modules.xml and the engine's IgnorePatcher.enable
    flag lets the client launch without the patcher putting them back. That is
    what makes positions survive a relog — see ``game_persistence`` for THE STRIP
    RULE and why other mods' declarations come along for the ride.

    ``damageinfo_swf`` (a staged modded DamageInfo.swf, or None) drives the Damage
    Numbers feature: a path installs the mod (backing up the stock file once); None
    reverts to the stock file from that backup if one exists. ``damageinfo_pristine``
    is the bundled genuine stock SWF — used to seed/recognize the backup so it can
    never capture a mod. See ``_prepare_damageinfo``.

    The build never touches the skin's TextColors.xml — per-source colors *and*
    directions belong to the Damage Number Colors panel, which edits the file directly.

    Returns (success, error_message).
    """
    flash_path = Path(game_path) / "Data" / "Gui" / "Default" / "Flash"

    try:
        flash_path.mkdir(parents=True, exist_ok=True)

        cleanup_legacy_files(game_path)

        # DamageInfo.swf is a core game file a running client can hold locked. Stage the
        # change to a temp file first — the slow, failure-prone copy — then commit with
        # os.replace, the only lock-prone step. Staging runs before KazBars.swf is copied,
        # so a lock leaves the grids untouched.
        try:
            staged = _prepare_damageinfo(flash_path, damageinfo_swf, damageinfo_pristine)
        except OSError:
            return False, _DAMAGEINFO_LOCK_MSG

        if staged:
            tmp, target = staged
            try:
                os.replace(tmp, target)
            except OSError:
                tmp.unlink(missing_ok=True)
                return False, _DAMAGEINFO_LOCK_MSG

        shutil.copy2(staging_swf, flash_path / "KazBars.swf")

        splice_declarations(game_path, discover_aoc_archive_declarations(game_path))
        ensure_flag(game_path)
    except ValueError as e:
        return False, (
            f"Could not update the game's interface files\n\n{e}\n\n"
            "Run Game ▸ Repair game install to restore them from the backup."
        )
    except OSError as e:
        return False, (
            f"Could not write files\n\n{e}\n\n"
            "Check that your disk has free space and the game folder is not read-only."
        )

    return True, ""


def _prepare_damageinfo(flash_path, staged_swf, pristine_swf=None):
    """Stage the DamageInfo.swf install/revert to a temp file without committing it.

    Returns the ``(tmp, target)`` pair the caller os.replaces at commit, or ``None`` when
    there's nothing to do. Does all the lock-safe-but-slow work up front (seed the backup,
    copy to the temp) so the caller's commit phase is nothing but os.replace; raises
    OSError if that work fails, with the target untouched.

    - staged_swf given: ensure a stock backup exists, then stage the modded build.
    - staged_swf None: Damage Numbers is off — stage a restore from the backup if we made
      one (``None`` when the feature was never installed).

    The backup must always hold genuine stock so a later revert can never resurrect a
    mod. The old "copy whatever the target is, once" rule failed if the .bak was lost
    out-of-band while a modded target remained — the next build would capture the mod as
    "stock". So when no backup exists we seed it from the live target ONLY if it is
    byte-identical to our bundled pristine stock (``pristine_swf``); otherwise (modded,
    a variant, or absent) we seed from the bundled pristine itself. Either way the backup
    is real stock. ``pristine_swf`` None falls back to the legacy behavior for callers
    that don't supply it.
    """
    target = flash_path / DAMAGEINFO_FILE
    backup = flash_path / DAMAGEINFO_BACKUP
    if staged_swf:
        if not backup.exists():
            if pristine_swf and Path(pristine_swf).is_file():
                source = target if _files_equal(target, pristine_swf) else Path(pristine_swf)
                shutil.copy2(source, backup)
            elif target.exists():
                shutil.copy2(target, backup)  # legacy fallback: no pristine supplied
        src = staged_swf
    elif backup.exists():
        src = backup
    else:
        return None
    tmp = target.with_name(target.name + ".kaztmp")
    shutil.copy2(src, tmp)
    return tmp, target


def cleanup_legacy_files(game_path):
    """Clear every earlier way of loading KazBars before the fresh install.

    Two generations' worth: predecessor SWFs and module folders (Kaz Flash Mods,
    Kaz Grids), and the pre-persistence era's own two load paths — the
    ``Data/Gui/Aoc/KazBars`` fragments and the ``/loadclip`` reload scripts +
    auto_login entry. Our own Aoc folder has to go: a user who still launches
    through Aoc.exe would otherwise get KazBars declared twice, once by us
    permanently and once by its per-session merge.
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

    for script in LEGACY_SCRIPTS:
        try:
            (Path(game_path) / "Scripts" / script).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not remove %s: %s", script, e)

    clean_auto_login(game_path)


def clean_auto_login(game_path):
    """Strip our marker block (and its predecessors') from Scripts/auto_login,
    deleting the file if that leaves it empty. Returns True if anything changed."""
    auto_login = Path(game_path) / "Scripts" / "auto_login"
    if not auto_login.exists():
        return False
    try:
        content = auto_login.read_text(encoding='utf-8')
        cleaned = strip_marker_block(content, AUTO_LOAD_MARKER)
        for legacy in LEGACY_AUTO_LOAD_MARKERS:
            cleaned = strip_marker_block(cleaned, legacy)
        if cleaned == content:
            return False
        if cleaned.strip():
            auto_login.write_text(cleaned, encoding='utf-8')
        else:
            auto_login.unlink()
        return True
    except (UnicodeDecodeError, OSError):
        logger.debug("Could not read/clean auto_login markers", exc_info=True)
        return False


def uninstall_from_client(game_path, damageinfo_pristine=None):
    """Remove KazBars files from the game folder.

    ``damageinfo_pristine`` is the bundled genuine stock DamageInfo.swf — used to
    restore stock if the one-time backup is missing but a modded file remains, so a
    "complete" uninstall never leaves a modded core game file behind.

    Returns (success, message).
    """
    removed = []
    try:
        flash = Path(game_path) / "Data" / "Gui" / "Default" / "Flash"
        swf = flash / "KazBars.swf"
        if swf.exists():
            swf.unlink()
            removed.append("KazBars.swf")

        # Damage Numbers: restore the stock DamageInfo.swf from our one-time backup; if
        # that backup is gone but a non-stock (modded) file is still present, fall back to
        # the bundled pristine so uninstall never leaves the game file modded.
        di_backup = flash / DAMAGEINFO_BACKUP
        di_target = flash / DAMAGEINFO_FILE
        if di_backup.exists():
            _atomic_install(di_backup, di_target)
            di_backup.unlink()
            removed.append("DamageInfo.swf (restored stock)")
        elif (damageinfo_pristine and Path(damageinfo_pristine).is_file()
              and di_target.exists() and not _files_equal(di_target, damageinfo_pristine)):
            _atomic_install(damageinfo_pristine, di_target)
            removed.append("DamageInfo.swf (restored stock from bundled copy)")

        # TextColors.xml is never touched: per-source colors AND directions are the user's
        # content (written by the Damage Number Colors panel, like the buff-bar edits), so
        # they survive an uninstall — as does any .kazbars.bak, their manual restore point.

        # Put the game's own XMLs back byte-for-byte and drop the bypass flag, so
        # an uninstalled game folder is indistinguishable from a never-modded one.
        removed.extend(strip_declarations(game_path))
        if remove_flag(game_path):
            removed.append(FLAG_NAME)

        aoc_dir = Path(game_path) / "Data" / "Gui" / "Aoc" / "KazBars"
        if aoc_dir.exists():
            shutil.rmtree(aoc_dir)
            removed.append("Aoc module files")

        for script in LEGACY_SCRIPTS:
            p = Path(game_path) / "Scripts" / script
            if p.exists():
                p.unlink()
                removed.append(script)

        if clean_auto_login(game_path):
            removed.append("auto_login entry")
    except OSError as e:
        return False, f"Could not remove files:\n\n{e}"

    if not removed:
        return True, "Nothing to remove — KazBars isn't installed in this game folder."
    return True, "Removed: " + ", ".join(removed)


def _first_running(names):
    """Name of the first of `names` that tasklist reports as running, or None."""
    for name in names:
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {name}', '/NH'],
                capture_output=True, text=True, timeout=5,
                creationflags=CREATE_NO_WINDOW
            )
            if name.lower() in result.stdout.lower():
                return name
        except Exception:
            continue
    return None


def get_running_game_process():
    """Return the name of a running AoC game process, or None.

    Aoc.exe (the launcher bypass loader) doesn't lock the overlay files —
    the actual game process does. Only the DX9/DX10 game exes matter here.
    """
    return _first_running(GAME_EXES)


def get_running_engine_process():
    """Return the name of any running DV-engine process — client or patcher.

    Repair has to wait for both. The patcher saves Prefs_3.xml on exit just like
    the client does, so a live patcher run would strip the archives we are about
    to re-inject (THE STRIP RULE, game_persistence).
    """
    return _first_running((*GAME_EXES, PATCHER_EXE))


def is_aoc_running():
    """Return True if any AoC game process is currently running."""
    return get_running_game_process() is not None


