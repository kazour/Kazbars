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

from . import buff_xml
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

# Damage Numbers: a core game Flash file we replace with a modded build. We back the
# stock file up once so install/disable/uninstall can always revert cleanly.
DAMAGEINFO_FILE = "DamageInfo.swf"
DAMAGEINFO_BACKUP = "DamageInfo.swf.kazbars.bak"

# Damage Numbers "Group my resource numbers" toggle: flips the resource-loss flytext
# directions in the skin's TextColors.xml (Customized/ if present, else Default/). The
# flip is surgical + reversible, so we restore by rewriting it back, not from a backup.
TEXTCOLORS_RELPATH = "TextColors.xml"

# Returned when a running client locks DamageInfo.swf / TextColors.xml. _LOCK_MSG is the
# clean "nothing committed" case; _PARTIAL_MSG covers the rare lock that bites between the
# two adjacent os.replace commits, leaving one game file swapped and the other not (the
# next successful build re-stages from stock and self-heals).
_DAMAGEINFO_LOCK_MSG = (
    "Couldn't update Damage Numbers.\n\n"
    "Close Age of Conan and build again — the game locks DamageInfo.swf and "
    "TextColors.xml while it's running. Your grids were not changed."
)
_DAMAGEINFO_PARTIAL_MSG = (
    "Couldn't finish updating Damage Numbers — the game locked one of its files midway.\n\n"
    "Close Age of Conan and build again to apply the rest. Your grids were not changed."
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


def install_to_client(staging_swf, game_path, use_aoc, damageinfo_swf=None,
                      damageinfo_pristine=None, group_resources=False, source_colors=None,
                      split_incoming=False):
    """Install compiled SWF + scripts to the game folder.

    ``damageinfo_swf`` (a staged modded DamageInfo.swf, or None) drives the Damage
    Numbers feature: a path installs the mod (backing up the stock file once); None
    reverts to the stock file from that backup if one exists. ``damageinfo_pristine``
    is the bundled genuine stock SWF — used to seed/recognize the backup so it can
    never capture a mod. See ``_prepare_damageinfo``.

    ``group_resources`` ("Group my resource numbers"), ``split_incoming`` ("Split into two
    columns" → incoming/self damage+heal directions), and ``source_colors`` (per-source
    color map) — all gated on the master enable by the caller — customize the skin's
    TextColors.xml, regenerated from a one-time stock backup. See ``_prepare_textcolors``.

    Returns (success, error_message).
    """
    flash_path = Path(game_path) / "Data" / "Gui" / "Default" / "Flash"
    scripts_path = Path(game_path) / "Scripts"

    try:
        flash_path.mkdir(parents=True, exist_ok=True)
        scripts_path.mkdir(parents=True, exist_ok=True)

        cleanup_legacy_files(game_path)

        # Damage Numbers touches two core game files (DamageInfo.swf + TextColors.xml) a
        # running client can hold locked. Stage both changes to temp files first — the slow,
        # failure-prone copy/compute — then commit them back-to-back with os.replace, the
        # only lock-prone step. Staging runs before KazBars.swf is copied, so a lock leaves
        # the grids untouched; committing the two adjacent shrinks the window where a lock
        # could swap one file but not the other down to a near-instant gap.
        staged_pairs = []
        try:
            di_pair = _prepare_damageinfo(flash_path, damageinfo_swf, damageinfo_pristine)
            if di_pair:
                staged_pairs.append(di_pair)
            tc_pair = _prepare_textcolors(game_path, group_resources, source_colors, split_incoming)
            if tc_pair:
                staged_pairs.append(tc_pair)
        except OSError:
            for tmp, _ in staged_pairs:
                tmp.unlink(missing_ok=True)
            return False, _DAMAGEINFO_LOCK_MSG

        committed = 0
        for tmp, target in staged_pairs:
            try:
                os.replace(tmp, target)
            except OSError:
                for tmp2, _ in staged_pairs[committed:]:
                    tmp2.unlink(missing_ok=True)
                return False, (_DAMAGEINFO_PARTIAL_MSG if committed else _DAMAGEINFO_LOCK_MSG)
            committed += 1

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


def _prepare_textcolors(game_path, group_resources, source_colors=None, split_incoming=False):
    """Stage the skin's TextColors.xml patch/restore to a temp file without committing it.

    Returns the ``(tmp, target)`` pair to os.replace, or ``None`` when nothing needs
    writing (no managed change, or the result already matches the live file). Raises
    OSError on a failed read/seed/temp-write, with the live file untouched.

    Three independent things customize TextColors.xml and must compose: the "Group my
    resource numbers" toggle (``group_resources`` → resource-loss flytext directions), the
    "Separate resources into Column B" toggle (``split_incoming`` → the incoming/self damage +
    heal directions, so everything that lands on you drops into the columns), and the per-source
    color editor (``source_colors`` → a ``{name: "RRGGBB"}`` map). Colors have no
    deterministic inverse, so instead of editing in place we keep a one-time genuine-stock
    backup (``TextColors.xml.kazbars.bak``) and **regenerate** the live file from it each
    build: stock → direction flips → color overrides. Because the base is always the stock
    backup (never the current file), any out-of-band hand-edit to the managed flytext
    entries is intentionally overwritten on every build — KazBars owns those entries while
    the feature is on. Nothing active ⇒ restore from the backup (kept across a disable,
    dropped on uninstall). Targets the file the game reads (Customized/ if present, else
    Default/).
    """
    source_colors = source_colors or {}
    _default, _customized, source = buff_xml._resolve_paths(game_path, TEXTCOLORS_RELPATH)
    if source is None:
        return None
    backup = source.with_name(source.name + buff_xml.BACKUP_SUFFIX)
    current = source.read_text(encoding="utf-8")

    if group_resources or split_incoming or source_colors:
        buff_xml._backup_once(source)  # seed genuine stock once (first edit)
        base = backup.read_text(encoding="utf-8") if backup.exists() else current
        if group_resources:
            base, _ = buff_xml.set_resource_loss_to_column(base, True)
        if split_incoming:
            base, _ = buff_xml.set_directions(base, buff_xml.INCOMING_DAMAGE_TYPES, True)
        for name, color in source_colors.items():
            base, _ = buff_xml.set_source_color(base, name, color)
        target_text = base
    elif backup.exists():
        target_text = backup.read_text(encoding="utf-8")
    else:
        return None

    if target_text == current:
        return None
    tmp = source.with_name(source.name + ".kaztmp")
    tmp.write_text(target_text, encoding="utf-8")
    return tmp, source


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

        # Damage Numbers: restore TextColors.xml from our one-time stock backup (covers
        # both the resource-direction toggle and the per-source colors) and drop the backup.
        _d, _c, tc_source = buff_xml._resolve_paths(game_path, TEXTCOLORS_RELPATH)
        if tc_source is not None:
            tc_backup = tc_source.with_name(tc_source.name + buff_xml.BACKUP_SUFFIX)
            if tc_backup.exists():
                _atomic_install(tc_backup, tc_source)
                tc_backup.unlink(missing_ok=True)
                removed.append("TextColors.xml (restored stock)")

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
