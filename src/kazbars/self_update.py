"""KazBars — in-place app self-update (pure, no Tk).

Two halves, both stdlib:

- **Staging** (inside the running app, on a worker thread): `stage_release`
  streams the release zip into `<install>/.update/`, checks it against the
  `.sha256` asset, unpacks it to `<install>/.update/KazBars/` and writes
  `pending.json`. Any failure removes `.update/` and raises `StageError` —
  nothing outside `.update/` is touched. Not %TEMP% on purpose: an exe
  launched from TEMP trips AV heuristics, so the staged exe runs from inside
  the install dir.

- **Apply** (in the *staged* exe, `KazBars.exe --apply-update`): `run_apply`
  waits for the old process to exit, proves nobody holds the install's exe,
  copies the staged tree over the install in two phases (every file to a
  `.kbnew` sibling first, then one burst of `os.replace`, exe last — so the
  mixed old/new window is the rename burst, not the copy), prunes dead files
  under `_internal/`, relaunches the install's exe and exits. `userdata/`,
  `logs/` and `.update/` are never written: an update keeps profiles, prefs
  and the OTA content where they are.

`startup_action` is the new app's first look at `.update/`: a version match
means the update landed (toast, then delete the staging dir); an `applying`
marker under the attempt cap means the apply died mid-way and is respawned;
anything else is cleaned up.
"""

import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from ctypes import wintypes
from pathlib import Path

from .build_utils import CREATE_NO_WINDOW
from .update_check import release_tag

logger = logging.getLogger(__name__)

# The release contract — tests/test_release_assets.py pins these against
# .github/workflows/release.yml.
ZIP_ASSET = "KazBars.zip"
SHA_ASSET = "KazBars.zip.sha256"
ZIP_ROOT = "KazBars"
EXE_NAME = "KazBars.exe"
INTERNAL_DIR = "_internal"

UPDATE_DIR = ".update"
PENDING_NAME = "pending.json"
# Install-root dirs the apply never writes (lower-case; compared case-folded).
SKIP_DIRS = ("userdata", "logs", UPDATE_DIR)
TMP_SUFFIX = ".kbnew"
APPLY_FLAG = "--apply-update"
MAX_APPLY_ATTEMPTS = 2
DOWNLOAD_TIMEOUT = 15
CHUNK = 256 * 1024
WAIT_SECONDS = 30

_IS_WINDOWS = sys.platform == "win32"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

if _IS_WINDOWS:
    _SYNCHRONIZE = 0x00100000
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


class StageError(Exception):
    """A staging failure with a user-facing message. Nothing was changed."""


# =========================================================================== #
# STAGING (runs inside the app)                                               #
# =========================================================================== #

def pick_assets(release):
    """(zip_url, sha_url, size) from a release document, or None when either
    asset is missing. Exact-name match — the contract, not a pattern."""
    found = {}
    for asset in release.get("assets") or ():
        name = asset.get("name")
        if name in (ZIP_ASSET, SHA_ASSET) and asset.get("browser_download_url"):
            found[name] = asset
    if ZIP_ASSET not in found or SHA_ASSET not in found:
        return None
    return (
        found[ZIP_ASSET]["browser_download_url"],
        found[SHA_ASSET]["browser_download_url"],
        int(found[ZIP_ASSET].get("size") or 0),
    )


def parse_sha256_file(text):
    """The hex digest from a `<sha256>  KazBars.zip` line (first token, 64 hex
    chars, lower-cased); None for anything else."""
    parts = text.split()
    if not parts or not _HEX64.match(parts[0]):
        return None
    return parts[0].lower()


def _urlopen(url):
    return urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT)


def _content_length(resp):
    try:
        return int(resp.headers.get("Content-Length") or 0)
    except (AttributeError, ValueError):
        return 0


def stream_download(url, dest, *, size=0, progress=None, opener=None):
    """Stream `url` to `dest` in CHUNK pieces, hashing in the same pass; returns
    the sha256 hex. `progress(done, total)` fires on every whole-percent change
    (total from Content-Length, else `size`; unknown ⇒ one final call)."""
    opener = opener or _urlopen
    digest = hashlib.sha256()
    done = 0
    last_pct = -1
    with opener(url) as resp, open(dest, "wb") as out:
        total = _content_length(resp) or size
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress and total:
                pct = min(done * 100 // total, 100)
                if pct != last_pct:
                    last_pct = pct
                    progress(done, total)
    if progress and not total:
        progress(done, done)
    return digest.hexdigest()


def validate_zip(zf):
    """Zip-slip guard + shape check. Every entry must sit under `KazBars/`
    (separators normalised — older Compress-Archive builds emitted `\\`), no
    absolute, drive-relative or `..` paths, and the exe must be present.
    Returns the entries to extract."""
    infos = []
    seen_exe = False
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        first = name.split("/", 1)[0]
        if (not name or name.startswith("/") or ":" in first
                or ".." in name.split("/")):
            raise StageError("The update package is malformed")
        if not name.startswith(ZIP_ROOT + "/"):
            raise StageError("The update package has an unexpected layout")
        if name == f"{ZIP_ROOT}/{EXE_NAME}":
            seen_exe = True
        infos.append(info)
    if not seen_exe:
        raise StageError("The update package has no KazBars.exe")
    return infos


def extract_staged(zip_path, update_dir):
    """Unpack a validated zip to `<update_dir>/KazBars/`; returns that root."""
    update_dir = Path(update_dir)
    with zipfile.ZipFile(zip_path) as zf:
        for info in validate_zip(zf):
            name = info.filename.replace("\\", "/")
            target = update_dir / name
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
    return update_dir / ZIP_ROOT


def stage_release(install_dir, release, *, progress=None, opener=None):
    """Download, verify and unpack `release` into `<install>/.update/`; returns
    the staged exe path. Raises StageError with `.update/` removed."""
    install_dir = Path(install_dir)
    update_dir = install_dir / UPDATE_DIR
    assets = pick_assets(release)
    if assets is None:
        raise StageError("This release has no download package")
    zip_url, sha_url, size = assets
    try:
        discard_staging(install_dir)
        update_dir.mkdir(parents=True)
        if size and shutil.disk_usage(install_dir).free < size * 4:
            raise StageError("Not enough free disk space for the update")
        zip_path = update_dir / ZIP_ASSET
        actual = stream_download(zip_url, zip_path, size=size, progress=progress, opener=opener)
        with (opener or _urlopen)(sha_url) as resp:
            expected = parse_sha256_file(resp.read(4096).decode("ascii", "replace"))
        if expected is None or expected != actual:
            raise StageError("The update download didn't verify")
        staged_root = extract_staged(zip_path, update_dir)
        zip_path.unlink()
        write_pending(update_dir, state="staged", version=release_tag(release),
                      html_url=release.get("html_url") or "", attempts=0)
        return staged_root / EXE_NAME
    except StageError:
        discard_staging(install_dir)
        raise
    except (OSError, zipfile.BadZipFile, ValueError) as e:
        logger.warning("update staging failed: %s", e)
        discard_staging(install_dir)
        raise StageError("Couldn't download the update") from e


def discard_staging(install_dir):
    shutil.rmtree(Path(install_dir) / UPDATE_DIR, ignore_errors=True)


def read_pending(update_dir):
    try:
        data = json.loads((Path(update_dir) / PENDING_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_pending(update_dir, **fields):
    data = read_pending(update_dir) or {}
    data.update(fields)
    (Path(update_dir) / PENDING_NAME).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def startup_action(install_dir, running_version):
    """What the freshly started app should do about `.update/`:
    'none' (no staging dir), 'updated' (an apply ran and we are the version it
    installed), 'retry' (an apply died mid-way, under the attempt cap, staged
    exe still there), 'failed' (an apply gave up), 'clean' (anything else)."""
    update_dir = Path(install_dir) / UPDATE_DIR
    if not update_dir.exists():
        return "none", None
    pending = read_pending(update_dir)
    if not pending:
        return "clean", None
    state = pending.get("state")
    if state in ("applying", "applied") and pending.get("version") == running_version:
        return "updated", pending
    if state == "failed":
        return "failed", pending
    if state == "applying":
        attempts = int(pending.get("attempts") or 0)
        if attempts < MAX_APPLY_ATTEMPTS and (update_dir / ZIP_ROOT / EXE_NAME).exists():
            return "retry", pending
        return "failed", pending
    return "clean", pending


# =========================================================================== #
# HANDOFF                                                                     #
# =========================================================================== #

def parse_args(argv):
    """`--apply-update --target <dir> --wait-pid <pid>` → (Path, int); anything
    else → None (normal launch). Hand-rolled: argparse exits through a stderr
    a windowed exe doesn't have."""
    if APPLY_FLAG not in argv:
        return None
    target = wait_pid = None
    it = iter(argv)
    for arg in it:
        if arg == "--target":
            target = next(it, None)
        elif arg == "--wait-pid":
            wait_pid = next(it, None)
    if not target:
        return None
    try:
        pid = int(wait_pid or 0)
    except ValueError:
        return None
    return Path(target), pid


def spawn_detached(argv, cwd):
    """The one spawn. `cwd` is always the install root so no process ever holds
    a directory handle inside `.update/` (which would block its removal)."""
    subprocess.Popen([str(a) for a in argv], cwd=str(cwd), close_fds=True,
                     creationflags=CREATE_NO_WINDOW)


def spawn_apply(staged_exe, target, pid):
    spawn_detached([staged_exe, APPLY_FLAG, "--target", target, "--wait-pid", pid], cwd=target)


def respawn_apply(install_dir):
    """Startup retry of a died apply — nothing to wait for, so pid 0."""
    install_dir = Path(install_dir)
    spawn_apply(install_dir / UPDATE_DIR / ZIP_ROOT / EXE_NAME, install_dir, 0)


# =========================================================================== #
# APPLY (runs in the staged exe)                                              #
# =========================================================================== #

def wait_for_pid(pid, timeout_s):
    """Block until process `pid` exits or `timeout_s` passes. pid 0, a pid that
    can't be opened (already gone) and a non-Windows host return at once."""
    if not pid or not _IS_WINDOWS:
        return
    handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        _kernel32.WaitForSingleObject(handle, int(timeout_s * 1000))
    finally:
        _kernel32.CloseHandle(handle)


def wait_until_writable(path, timeout_s, interval=0.25):
    """True once `path` opens for append. The install's exe unlocks only when no
    process runs from it — the PID wait alone can't prove that (PID reuse, a
    second instance, AV still scanning)."""
    path = Path(path)
    if not path.exists():
        return True
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with open(path, "ab"):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)


def plan_copy(staged_root, target):
    """(src, dst) for every staged file, skipping SKIP_DIRS at the install root;
    the exe last so its replacement commits the update."""
    staged_root = Path(staged_root)
    target = Path(target)
    pairs = []
    exe = None
    for src in sorted(staged_root.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(staged_root)
        if rel.parts[0].lower() in SKIP_DIRS:
            continue
        pair = (src, target / rel)
        if rel == Path(EXE_NAME):
            exe = pair
        else:
            pairs.append(pair)
    if exe:
        pairs.append(exe)
    return pairs


def _replace_retry(src, dst, attempts=5, delay=0.2):
    """os.replace with a short retry — Defender / the indexer briefly oplock
    freshly written files."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _unlink_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def apply_tree(pairs):
    """Phase A copies every file to a `.kbnew` sibling — the install stays
    bootable and a failure here unwinds to nothing. Phase B renames them into
    place in one burst."""
    temps = []
    try:
        for src, dst in pairs:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + TMP_SUFFIX)
            shutil.copyfile(src, tmp)
            temps.append((tmp, dst))
    except OSError:
        for tmp, _ in temps:
            _unlink_quiet(tmp)
        raise
    for tmp, dst in temps:
        _replace_retry(tmp, dst)


def prune_internal(staged_root, target):
    """Delete files under `<target>/_internal` the staged build doesn't ship
    (dead DLLs from older builds, leftover temps), then empty dirs. Never
    reaches outside `_internal`; failures are logged, not raised."""
    staged_int = Path(staged_root) / INTERNAL_DIR
    target_int = Path(target) / INTERNAL_DIR
    if not staged_int.is_dir() or not target_int.is_dir():
        return []
    keep = {os.path.normcase(str(p.relative_to(staged_int)))
            for p in staged_int.rglob("*") if p.is_file()}
    removed = []
    for p in sorted(target_int.rglob("*"), reverse=True):
        try:
            if p.is_file():
                if os.path.normcase(str(p.relative_to(target_int))) not in keep:
                    p.unlink()
                    removed.append(p)
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError as e:
            logger.warning("prune skipped %s: %s", p, e)
    return removed


def _unlink_temps(target):
    for p in Path(target).rglob("*" + TMP_SUFFIX):
        if p.relative_to(target).parts[0].lower() not in SKIP_DIRS:
            _unlink_quiet(p)


def _configure_apply_logging(target):
    """The apply runs from the staged exe, so `app_path()` would point at the
    staging dir — log into the install's own logs/ explicitly."""
    log_dir = Path(target) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            handlers=[logging.FileHandler(log_dir / "update.log", mode="w", encoding="utf-8")],
            force=True,
        )
    except OSError:
        pass


def run_apply(target, wait_pid):
    """The `--apply-update` entry point. Records every outcome in pending.json
    and relaunches the install's exe whatever happened — the user is never
    left without an app."""
    target = Path(target)
    update_dir = target / UPDATE_DIR
    staged_root = update_dir / ZIP_ROOT
    exe = target / EXE_NAME
    _configure_apply_logging(target)
    pending = read_pending(update_dir) or {}
    attempts = int(pending.get("attempts") or 0) + 1
    write_pending(update_dir, state="applying", attempts=attempts)
    try:
        logger.info("apply attempt %d: %s -> %s (waiting on pid %s)",
                    attempts, staged_root, target, wait_pid)
        wait_for_pid(wait_pid, WAIT_SECONDS)
        if not wait_until_writable(exe, WAIT_SECONDS):
            raise OSError(f"{exe} is still in use")
        pairs = plan_copy(staged_root, target)
        apply_tree(pairs)
        removed = prune_internal(staged_root, target)
        write_pending(update_dir, state="applied")
        logger.info("applied %d files, pruned %d", len(pairs), len(removed))
        rc = 0
    except Exception as e:
        logger.exception("apply failed")
        write_pending(update_dir, state="failed", error=str(e))
        _unlink_temps(target)
        rc = 1
    if exe.exists():
        spawn_detached([exe], cwd=target)
    return rc
