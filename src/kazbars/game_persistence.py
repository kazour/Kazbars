"""
KazBars — Game persistence.

Permanent module declarations in the game's own XMLs, plus the engine-native
patcher-bypass flag, so grid positions survive a relog for **every** user.

The chain: `Data/Gui/Default/MainPrefs.xml` declares the `KazBars` variable and
the `KazBars settings` archive, a `<Module>` block in Modules.xml loads
KazBars.swf with `GMF_CFG_STORE_USER_CONFIG`, and the client then saves the
archive (grid x/y/visibility, panel positions) to the account-global
`%LOCALAPPDATA%\\Funcom\\Conan\\Prefs\\Prefs_3.xml`.

THE STRIP RULE (live-verified): any engine process — client *or* patcher — that
starts *without* a declaration and later saves prefs **deletes** the orphaned
archive. So the declarations must be present for every launch; that is why they
live in the game's XMLs permanently instead of being merged per session, why a
game patch (which restores the stock XMLs) needs a Repair before the next
launch, and why other Aoc.exe mods' archive declarations get adopted into our
splice rather than left to be stripped.

Every write here is byte-faithful: the game's XMLs are LF-only, and the patcher
compares hashes, so files are read as bytes and rewritten as bytes — never
through universal-newline translation, which would silently convert a whole file
to CRLF. Pure file ops, no Tk.
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from .build_utils import CREATE_NO_WINDOW

logger = logging.getLogger(__name__)

# The two client executables. Both carry the IgnorePatcher.enable string, and
# either can be the target of the direct-launch desktop shortcut.
GAME_EXES = ('AgeOfConan.exe', 'AgeOfConanDX10.exe')

# The Funcom patcher. It restores the stock XMLs (undoing our splice) and saves
# Prefs_3.xml on exit, so Repair must never run while it is alive.
PATCHER_EXE = 'ConanPatcher.exe'

# Our own module folders under Data/Gui/Aoc — the current name plus every
# predecessor (Kaz Flash Mods → Kaz Grids → KazBars). The persistence era owns
# the declarations directly, so all of these are removed on install and skipped
# when adopting other mods' fragments. Windows matches them case-insensitively.
LEGACY_AOC_DIRS = ("KzGrids", "KazGrids", "Kazbars", "KazBars")

# Empty file in the game root. Engine-native: a bare-launched client respawns
# ConanPatcher.exe and exits unless this exists. The patcher never deletes it
# (foreign-file rule), so it survives patch day.
FLAG_NAME = "IgnorePatcher.enable"

# Our spliced blocks are wrapped in these so refresh and removal are exact —
# we persist across sessions, so guessing at an unmarked block is never OK.
MARKER_BEGIN = "<!-- KazBars begin -->"
MARKER_END = "<!-- KazBars end -->"

# One-time pre-splice copy of each XML, seeded the first time we touch it.
BACKUP_SUFFIX = ".kazbars.bak"

# The archive the game saves our positions into.
ARCHIVE_NAME = "KazBars settings"

# Declarations spliced into MainPrefs.xml (one line each, indentation included).
MAINPREFS_DECLARATIONS = (
    '\t<Value name="KazBars" value="true" />',
    '\t<Archive name="KazBars settings" />',
)

# The module block spliced into whichever Modules.xml is live.
MODULES_DECLARATION = (
    '\t<Module',
    '\t\tname              = "KazBars"',
    '\t\tmovie             = "KazBars.swf"',
    '\t\tflags             = "GMF_CFG_STORE_USER_CONFIG"',
    '\t\tdepth_layer       = "Top"',
    '\t\tsub_depth         = "0"',
    '\t\tvariable          = "KazBars"',
    '\t\tcriteria          = "KazBars &amp;&amp; (guimode &amp; '
    '(GUIMODEFLAGS_INPLAY | GUIMODEFLAGS_ENABLEALLGUI))"',
    '\t\tconfig_name       = "KazBars settings"',
    '\t/>',
)

# A third-party fragment line we are willing to copy into the game's own
# MainPrefs.xml: a complete, self-closing <Value>/<Archive> tag and nothing else.
# Anything unrecognized is skipped rather than trusted.
_DECLARATION_RE = re.compile(r'<(?:Value|Archive)\s+[^<>]*/>\Z')

_ARCHIVE_NAME_RE = re.compile(r'<Archive\s+name="([^"]+)"')

# A whole <Archive> element in a Prefs_3.xml-shaped file, self-closing or not,
# including its trailing newline so a re-injected block lands on its own line.
_ARCHIVE_BLOCK_RE = re.compile(
    r'^[ \t]*<Archive\s+name="([^"]+)"\s*(?:/>|>.*?^[ \t]*</Archive>)[ \t]*\r?\n?',
    re.DOTALL | re.MULTILINE,
)


# ============================================================================
# PATHS
# ============================================================================

def main_prefs_path(game_path):
    """The one MainPrefs.xml the engine reads — always the Default/ copy."""
    return Path(game_path) / "Data" / "Gui" / "Default" / "MainPrefs.xml"


def modules_target(game_path):
    """The Modules.xml our block belongs in.

    The game honors a `Customized/Modules.xml`, and some UI mods ship one. When it
    exists it may shadow the Default copy entirely, so it is the only splice that
    is guaranteed to load — and being a foreign file, the patcher leaves it alone.
    When it is absent, Default/ is the live-proven target. We never create the
    Customized file ourselves.
    """
    customized = Path(game_path) / "Data" / "Gui" / "Customized" / "Modules.xml"
    if customized.is_file():
        return customized
    return Path(game_path) / "Data" / "Gui" / "Default" / "Modules.xml"


def _modules_locations(game_path):
    """Both Modules.xml candidates. A mod installed after us can move the live
    target, so removal has to sweep the one we no longer write to as well."""
    return (
        Path(game_path) / "Data" / "Gui" / "Default" / "Modules.xml",
        Path(game_path) / "Data" / "Gui" / "Customized" / "Modules.xml",
    )


def prefs3_path():
    """Where the client saves module archives, or None if LOCALAPPDATA is unset."""
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        return None
    return Path(local) / "Funcom" / "Conan" / "Prefs" / "Prefs_3.xml"


# ============================================================================
# BYTE-FAITHFUL TEXT IO
# ============================================================================

def _read(path):
    """Decode without newline translation, so a rewrite can be byte-identical."""
    return Path(path).read_bytes().decode('utf-8')


def _read_or_none(path):
    try:
        return _read(path)
    except (OSError, UnicodeDecodeError):
        return None


def _write(path, text):
    """Atomic write that preserves the text's own line endings exactly."""
    path = Path(path)
    tmp = path.with_name(path.name + ".kaztmp")
    tmp.write_bytes(text.encode('utf-8'))
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _newline(text):
    return '\r\n' if '\r\n' in text else '\n'


# ============================================================================
# SPLICE / STRIP
# ============================================================================

def _marker_span(text, path):
    """Full-line span of the marked block as (start, end), or None if unmarked.

    Raises ValueError when the markers are damaged — a lone marker, a reversed
    pair, or duplicates. The caller restores from the .kazbars.bak instead of
    regex-guessing at where our block used to end.
    """
    n_begin = text.count(MARKER_BEGIN)
    n_end = text.count(MARKER_END)
    if not n_begin and not n_end:
        return None
    start = text.find(MARKER_BEGIN)
    end = text.find(MARKER_END)
    if n_begin != 1 or n_end != 1 or end < start:
        raise ValueError(
            f"The KazBars marker block in {path.name} is damaged "
            f"({n_begin} begin / {n_end} end markers)."
        )
    line_start = text.rfind('\n', 0, start) + 1
    after = text.find('\n', end + len(MARKER_END))
    line_end = len(text) if after == -1 else after + 1
    return line_start, line_end


def _insert_point(text, path):
    """Offset of the line holding the closing </Root>, where our block goes."""
    idx = text.rfind('</Root>')
    if idx == -1:
        raise ValueError(f"{path.name} has no closing </Root> tag.")
    return text.rfind('\n', 0, idx) + 1


def _seed_backup(path, text):
    """Capture the pre-splice text as this file's restore point.

    Only ever reached for a file carrying no block of ours, so `text` IS the
    game's own unmodified file — which is why this overwrites rather than
    seeding once. After a patch the game ships new XMLs and we splice them
    fresh; keeping the pre-patch copy would make a later restore revert the
    game itself. A marker refresh never lands here, so a genuine pre-splice
    backup is never replaced by an already-spliced one.
    """
    _write(path.with_name(path.name + BACKUP_SUFFIX), text)


def _splice_file(path, lines):
    """Insert or refresh our marked block in one XML. Returns True if it changed."""
    if not path.is_file():
        raise ValueError(f"{path.name} is missing from the game folder.")
    try:
        text = _read(path)
    except UnicodeDecodeError:
        # A ValueError subclass, so callers would otherwise report a decode dump
        # as "damaged markers". Say what is actually wrong.
        raise ValueError(f"{path.name} isn't readable as UTF-8 text.") from None
    nl = _newline(text)
    block = nl.join((MARKER_BEGIN, *lines, MARKER_END)) + nl

    span = _marker_span(text, path)
    if span:
        start, end = span
        updated = text[:start] + block + text[end:]
    else:
        _seed_backup(path, text)
        at = _insert_point(text, path)
        updated = text[:at] + block + text[at:]

    if updated == text:
        return False
    _write(path, updated)
    return True


def splice_declarations(game_path, extra_declarations=()):
    """Write our permanent declarations into MainPrefs.xml and the Modules target.

    Idempotent: an existing marked block is refreshed in place, so repeated builds
    converge instead of stacking. `extra_declarations` are other mods' adopted
    MainPrefs lines (see `discover_aoc_archive_declarations`). Raises ValueError if
    a marker pair is damaged or an XML is missing/shapeless.
    """
    _splice_file(main_prefs_path(game_path),
                 (*MAINPREFS_DECLARATIONS, *extra_declarations))
    _splice_file(modules_target(game_path), MODULES_DECLARATION)


def _has_marker(path):
    text = _read_or_none(path)
    return text is not None and MARKER_BEGIN in text and MARKER_END in text


def is_merged(game_path):
    """True when both live targets carry a KazBars block.

    Checks the *current* modules target, so installing a mod that introduces a
    Customized/Modules.xml correctly reads as unmerged — our Default block would
    no longer be the one the game loads.
    """
    return (_has_marker(main_prefs_path(game_path))
            and _has_marker(modules_target(game_path)))


def _strip_file(path):
    """Remove our block from one XML, or restore the file wholesale from its
    backup when the file itself is unusable.

    Unusable means the surgical path cannot run at all: unreadable or gone,
    damaged markers, or no longer XML-shaped (no `</Root>` to splice against —
    which is also what a later re-splice would choke on, so the restore is the
    only way out). A file that is simply unmarked is NOT unusable: that is a
    never-installed folder, or a freshly patched one whose new stock text must
    not be reverted to our older backup.

    The backup is dropped only once a strip or a restore actually succeeded, so
    a pass that achieved nothing leaves the user's escape hatch in place.
    Returns True if the file changed.
    """
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    text = _read_or_none(path)
    changed = False
    unusable = text is None

    if text is not None:
        try:
            span = _marker_span(text, path)
        except ValueError:
            logger.warning("Damaged markers in %s — restoring from backup", path.name)
            unusable = True
        else:
            if span:
                start, end = span
                _write(path, text[:start] + text[end:])
                changed = True
            elif '</Root>' not in text:
                logger.warning("%s is not XML-shaped — restoring from backup", path.name)
                unusable = True

    if unusable and backup.is_file():
        _write(path, _read(backup))
        changed = True

    if changed and backup.is_file():
        backup.unlink()
    return changed


def strip_declarations(game_path):
    """Remove our permanent declarations, restoring each XML byte-exactly.

    Sweeps both Modules.xml locations, not just the live one — a mod installed
    after us can shift the target and strand our old block. Returns the list of
    files actually changed, parent-qualified so the two Modules.xml are distinct.
    """
    removed = []
    for path in (main_prefs_path(game_path), *_modules_locations(game_path)):
        try:
            if _strip_file(path):
                removed.append(f"{path.parent.name}/{path.name}")
        except OSError as e:
            logger.warning("Could not clean %s: %s", path.name, e)
    return removed


# ============================================================================
# PATCHER-BYPASS FLAG
# ============================================================================

def ensure_flag(game_path):
    """Create the empty IgnorePatcher.enable marker. Returns True if created."""
    flag = Path(game_path) / FLAG_NAME
    if flag.exists():
        return False
    flag.touch()
    return True


def remove_flag(game_path):
    """Delete the flag, restoring stock launch behavior. True if one was there."""
    flag = Path(game_path) / FLAG_NAME
    if not flag.exists():
        return False
    flag.unlink()
    return True


def _scan_bytes(path, needle, chunk=1 << 20):
    """True if `needle` appears anywhere in the file. Streams in overlapping
    chunks so a match straddling a boundary is still found without ever holding a
    multi-megabyte executable in memory."""
    overlap = len(needle) - 1
    try:
        with Path(path).open('rb') as fh:
            tail = b''
            while True:
                block = fh.read(chunk)
                if not block:
                    return False
                if needle in tail + block:
                    return True
                tail = block[-overlap:] if overlap else b''
    except OSError:
        return False


def client_supports_flag(game_path):
    """True if either client exe recognizes IgnorePatcher.enable.

    The flag is engine-native, so the string is baked into the binary. An install
    old enough to lack it still gets the declarations — only the bare-launch part
    of the story doesn't apply, and the build summary says so.
    """
    return any(_scan_bytes(Path(game_path) / name, FLAG_NAME.encode('ascii'))
               for name in GAME_EXES)


# ============================================================================
# OTHER MODS' ARCHIVES
# ============================================================================

def discover_aoc_archive_declarations(game_path):
    """Adopt other Aoc.exe mods' MainPrefs declarations into our splice.

    Without this, a bare-exe session starts without their declarations and the
    engine strips their saved archives (THE STRIP RULE) — we would be destroying a
    neighbour's settings just by launching. Duplicated declarations are harmless
    (the engine logs a "redefine variable" line and moves on).

    Only well-formed self-closing <Value>/<Archive> lines are adopted; anything
    else is skipped and logged, so a malformed third-party fragment can never ride
    into the game's own MainPrefs.xml. Their <Module> entries are deliberately NOT
    adopted — those mods simply don't load in a bare session, which costs them
    nothing, while their saved settings stay safe.
    """
    aoc_dir = Path(game_path) / "Data" / "Gui" / "Aoc"
    if not aoc_dir.is_dir():
        return ()

    skip = {name.lower() for name in LEGACY_AOC_DIRS}
    adopted = []
    seen = set()
    for fragment in sorted(aoc_dir.glob("*/MainPrefs.xml.add")):
        if fragment.parent.name.lower() in skip:
            continue
        text = _read_or_none(fragment)
        if text is None:
            logger.warning("Skipping unreadable fragment %s", fragment)
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if not _DECLARATION_RE.fullmatch(line):
                logger.warning("Skipping malformed declaration in %s: %r",
                               fragment.parent.name, line)
                continue
            if line in seen:
                continue
            seen.add(line)
            adopted.append('\t' + line)
    return tuple(adopted)


def archive_names_in(text):
    """The archive names declared anywhere in a chunk of MainPrefs-shaped XML."""
    return {m.group(1) for m in _ARCHIVE_NAME_RE.finditer(text)}


# ============================================================================
# Prefs_3.xml INSURANCE
# ============================================================================

def snapshot_prefs3(dest):
    """Copy the live Prefs_3.xml aside as repair insurance. Returns True if taken.

    Only ever snapshots a healthy file — one that still holds our archive — so a
    prefs file the engine has already stripped can never overwrite a good
    snapshot. Called when the install checks out healthy at startup, which is
    exactly when the live file is known good.
    """
    src = prefs3_path()
    if src is None or not src.is_file():
        return False
    text = _read_or_none(src)
    if text is None or ARCHIVE_NAME not in archive_names_in(text):
        return False
    try:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as e:
        logger.warning("Could not snapshot Prefs_3.xml: %s", e)
        return False
    return True


def _archive_blocks(text):
    """Map archive name → its whole <Archive> element, trailing newline included."""
    return {m.group(1): m.group(0) for m in _ARCHIVE_BLOCK_RE.finditer(text)}


def missing_archives(live, snapshot, names):
    """Of `names`, the archives the live prefs file lacks and the snapshot holds.

    Asks "is anything worth restoring?" without restoring it, so a caller can
    check first and hold off while an engine process is alive — its exit-save
    would strip the re-injection straight back out.
    """
    live_text = _read_or_none(Path(live))
    snap_text = _read_or_none(Path(snapshot))
    if live_text is None or snap_text is None:
        return ()
    present = archive_names_in(live_text)
    blocks = _archive_blocks(snap_text)
    return tuple(sorted(n for n in names if n not in present and n in blocks))


def reinject_archives(live, snapshot, names):
    """Put archives the engine stripped back into Prefs_3.xml from a snapshot.

    Only ever ADDS a block whose name is missing from the live file, so a stale
    snapshot can never overwrite positions the user has moved since. Returns the
    names re-injected.
    """
    live, snapshot = Path(live), Path(snapshot)
    missing = missing_archives(live, snapshot, names)
    if not missing:
        return ()

    live_text = _read_or_none(live)
    snap_text = _read_or_none(snapshot)
    if live_text is None or snap_text is None:
        return ()
    blocks = _archive_blocks(snap_text)

    try:
        at = _insert_point(live_text, live)
    except ValueError:
        return ()
    addition = ''.join(blocks[name] for name in missing)
    try:
        _write(live, live_text[:at] + addition + live_text[at:])
    except OSError as e:
        logger.warning("Could not re-inject archives: %s", e)
        return ()
    return tuple(missing)


# ============================================================================
# DESKTOP SHORTCUT
# ============================================================================

# Values reach PowerShell through the environment, never the command string, so
# a game path with quotes, apostrophes or non-ASCII characters needs no escaping
# and cannot be read as script.
_SHORTCUT_PS = (
    "$ws = New-Object -ComObject WScript.Shell; "
    "$path = Join-Path ([Environment]::GetFolderPath('Desktop')) $env:KAZBARS_LINK_NAME; "
    "$lnk = $ws.CreateShortcut($path); "
    "$lnk.TargetPath = $env:KAZBARS_LINK_TARGET; "
    "$lnk.Arguments = '-novideo'; "
    "$lnk.WorkingDirectory = $env:KAZBARS_LINK_DIR; "
    "$lnk.Save(); "
    "Write-Output $path"
)

SHORTCUT_NAMES = {
    'AgeOfConanDX10.exe': "Age of Conan (DX10).lnk",
    'AgeOfConan.exe': "Age of Conan (DX9).lnk",
}


def create_game_desktop_link(game_path, exe_name):
    """Create a desktop shortcut that launches the game executable directly.

    Direct launch is what the persistence era wants: the Funcom patcher restores
    the stock XMLs, so going through it costs the user their declarations until
    the next Repair. `-novideo` skips the intro movies. The desktop folder is
    resolved by the shell, so a OneDrive-redirected Desktop still works.

    Returns (success, message).
    """
    target = Path(game_path) / exe_name
    if not target.is_file():
        return False, f"{exe_name} isn't in this game folder."

    env = dict(os.environ)
    env['KAZBARS_LINK_TARGET'] = str(target)
    env['KAZBARS_LINK_DIR'] = str(Path(game_path))
    env['KAZBARS_LINK_NAME'] = SHORTCUT_NAMES.get(exe_name, "Age of Conan.lnk")

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', _SHORTCUT_PS],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW, env=env,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Desktop shortcut failed: %s", e)
        return False, f"Could not create the shortcut.\n\n{e}"

    created = result.stdout.strip().splitlines()
    if result.returncode != 0 or not created:
        detail = (result.stderr or result.stdout).strip()
        return False, f"Could not create the shortcut.\n\n{detail}"
    return True, created[-1]
