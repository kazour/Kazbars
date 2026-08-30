"""Tests for kazbars.self_update — staging, handoff parsing, apply (no network,
no real spawn).

Fake install trees live under tmp_path; a fake opener stands in for urlopen;
`spawn_detached` is monkeypatched so nothing launches. The one real process is
the Windows-gated `wait_for_pid` check, which waits on a short-lived child.

Run: `pytest tests/test_self_update.py` (from repo root).
"""

import hashlib
import io
import json
import subprocess
import sys
import time
import zipfile

import pytest

from kazbars import self_update as S

# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, data, length=True):
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _opener(by_url, length=True):
    def open_(url):
        if url not in by_url:
            raise OSError(f"no route to {url}")
        return _Resp(by_url[url], length)
    return open_


def _zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


GOOD = {
    "KazBars/KazBars.exe": b"EXE",
    "KazBars/_internal/a.dll": b"A",
    "KazBars/_internal/sub/x.pyd": b"X",
}


def _release(zip_data=b"", with_sha=True, size=None):
    assets = [{"name": S.ZIP_ASSET, "browser_download_url": "http://x/zip",
               "size": len(zip_data) if size is None else size}]
    if with_sha:
        assets.append({"name": S.SHA_ASSET, "browser_download_url": "http://x/sha", "size": 77})
    return {"tag_name": "v9.9.9", "html_url": "http://x/rel", "assets": assets}


def _sha_line(data):
    return f"{hashlib.sha256(data).hexdigest()}  {S.ZIP_ASSET}".encode()


def _install(tmp_path):
    """A fake install: old exe, three _internal files, user data and a log."""
    root = tmp_path / "install"
    for rel, data in {
        "KazBars.exe": b"OLD",
        "_internal/old.dll": b"dead",
        "_internal/keep.dll": b"v1",
        "_internal/sub/x.pyd": b"v1",
        "userdata/prefs.json": b'{"game_path": "C:/AoC"}',
        "userdata/profiles/raid.json": b"{}",
        "logs/kazbars.log": b"log",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def _staged(install):
    """The staged tree: new exe, changed + new DLLs, and a poisoned copy of
    userdata/ + logs/ that must never reach the install."""
    root = install / S.UPDATE_DIR / S.ZIP_ROOT
    for rel, data in {
        "KazBars.exe": b"NEW",
        "_internal/keep.dll": b"v2",
        "_internal/new.dll": b"fresh",
        "_internal/sub/x.pyd": b"v2",
        "userdata/prefs.json": b"POISON",
        "logs/kazbars.log": b"POISON",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


# --------------------------------------------------------------------------- #
# release document + sha file
# --------------------------------------------------------------------------- #

def test_pick_assets_exact_names():
    rel = _release(b"zip", size=42)
    rel["assets"].insert(0, {"name": "KazBars.zip.bak", "browser_download_url": "http://x/bak"})
    assert S.pick_assets(rel) == ("http://x/zip", "http://x/sha", 42)


def test_pick_assets_missing_sha_is_none():
    assert S.pick_assets(_release(with_sha=False)) is None
    assert S.pick_assets({"assets": []}) is None
    assert S.pick_assets({}) is None


def test_parse_sha256_file_real_format():
    line = "0" * 63 + "a" + "  KazBars.zip"
    assert len(line) == 77
    assert S.parse_sha256_file(line) == "0" * 63 + "a"
    assert S.parse_sha256_file(line + "\n") == "0" * 63 + "a"
    assert S.parse_sha256_file("A" * 64) == "a" * 64


def test_parse_sha256_file_rejects_garbage():
    assert S.parse_sha256_file("") is None
    assert S.parse_sha256_file("not a hash  KazBars.zip") is None
    assert S.parse_sha256_file("ab" * 31) is None


# --------------------------------------------------------------------------- #
# download
# --------------------------------------------------------------------------- #

def test_stream_download_hashes_and_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "CHUNK", 7)
    data = bytes(range(256)) * 3
    seen = []
    sha = S.stream_download("http://x/zip", tmp_path / "out", opener=_opener({"http://x/zip": data}),
                            progress=lambda d, t: seen.append((d, t)))
    assert (tmp_path / "out").read_bytes() == data
    assert sha == hashlib.sha256(data).hexdigest()
    dones = [d for d, _ in seen]
    assert dones == sorted(dones) and seen[-1] == (len(data), len(data))
    assert all(t == len(data) for _, t in seen)


def test_stream_download_without_content_length_uses_size(tmp_path):
    data = b"x" * 100
    seen = []
    S.stream_download("http://x/zip", tmp_path / "out", size=100,
                      opener=_opener({"http://x/zip": data}, length=False),
                      progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (100, 100)


def test_stream_download_unknown_total_reports_once_at_the_end(tmp_path):
    data = b"x" * 100
    seen = []
    S.stream_download("http://x/zip", tmp_path / "out",
                      opener=_opener({"http://x/zip": data}, length=False),
                      progress=lambda d, t: seen.append((d, t)))
    assert seen == [(100, 100)]


# --------------------------------------------------------------------------- #
# zip validation + extraction
# --------------------------------------------------------------------------- #

def _zf(entries):
    return zipfile.ZipFile(io.BytesIO(_zip_bytes(entries)))


def test_validate_zip_accepts_both_separators():
    assert len(S.validate_zip(_zf(GOOD))) == 3
    back = {name.replace("/", "\\"): data for name, data in GOOD.items()}
    assert len(S.validate_zip(_zf(back))) == 3


@pytest.mark.parametrize("bad", [
    "KazBars/../evil.exe",
    "/KazBars/KazBars.exe",
    "C:x/KazBars.exe",
    "Other/KazBars.exe",
    "KazBars.exe",
])
def test_validate_zip_rejects_slips_and_foreign_layouts(bad):
    entries = dict(GOOD)
    entries[bad] = b"?"
    with pytest.raises(S.StageError):
        S.validate_zip(_zf(entries))


def test_validate_zip_requires_the_exe():
    entries = {k: v for k, v in GOOD.items() if not k.endswith(".exe")}
    with pytest.raises(S.StageError):
        S.validate_zip(_zf(entries))


def test_extract_staged_normalises_backslash_entries(tmp_path):
    back = {name.replace("/", "\\"): data for name, data in GOOD.items()}
    zip_path = tmp_path / "k.zip"
    zip_path.write_bytes(_zip_bytes(back))
    root = S.extract_staged(zip_path, tmp_path / "up")
    assert root == tmp_path / "up" / S.ZIP_ROOT
    assert (root / "_internal" / "sub" / "x.pyd").read_bytes() == b"X"
    assert not any("\\" in p.name for p in root.rglob("*"))


# --------------------------------------------------------------------------- #
# stage_release
# --------------------------------------------------------------------------- #

def test_stage_release_success_leaves_staged_tree_and_marker(tmp_path):
    data = _zip_bytes(GOOD)
    opener = _opener({"http://x/zip": data, "http://x/sha": _sha_line(data)})
    exe = S.stage_release(tmp_path, _release(data), opener=opener)
    update_dir = tmp_path / S.UPDATE_DIR
    assert exe == update_dir / S.ZIP_ROOT / S.EXE_NAME and exe.read_bytes() == b"EXE"
    assert not (update_dir / S.ZIP_ASSET).exists()          # zip deleted after unpack
    pending = S.read_pending(update_dir)
    assert pending == {"state": "staged", "version": "9.9.9", "html_url": "http://x/rel", "attempts": 0}


def test_stage_release_sha_mismatch_leaves_nothing(tmp_path):
    data = _zip_bytes(GOOD)
    opener = _opener({"http://x/zip": data, "http://x/sha": _sha_line(b"other")})
    with pytest.raises(S.StageError):
        S.stage_release(tmp_path, _release(data), opener=opener)
    assert not (tmp_path / S.UPDATE_DIR).exists()


def test_stage_release_missing_asset_or_route(tmp_path):
    with pytest.raises(S.StageError):
        S.stage_release(tmp_path, _release(with_sha=False), opener=_opener({}))
    with pytest.raises(S.StageError):                      # OSError from the opener
        S.stage_release(tmp_path, _release(b"zip"), opener=_opener({}))
    assert not (tmp_path / S.UPDATE_DIR).exists()


def test_stage_release_low_disk(tmp_path, monkeypatch):
    class _Usage:
        free = 10
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _p: _Usage)
    with pytest.raises(S.StageError, match="disk"):
        S.stage_release(tmp_path, _release(b"zip", size=1000), opener=_opener({}))
    assert not (tmp_path / S.UPDATE_DIR).exists()


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #

def test_plan_copy_skips_user_dirs_and_puts_exe_last(tmp_path):
    install = _install(tmp_path)
    staged = _staged(install)
    pairs = S.plan_copy(staged, install)
    rels = [dst.relative_to(install).as_posix() for _, dst in pairs]
    assert rels[-1] == S.EXE_NAME
    assert not any(r.startswith(("userdata", "logs")) for r in rels)
    assert set(rels) == {"KazBars.exe", "_internal/keep.dll", "_internal/new.dll", "_internal/sub/x.pyd"}


def test_apply_tree_replaces_and_preserves(tmp_path):
    install = _install(tmp_path)
    staged = _staged(install)
    S.apply_tree(S.plan_copy(staged, install))
    assert (install / "KazBars.exe").read_bytes() == b"NEW"
    assert (install / "_internal" / "keep.dll").read_bytes() == b"v2"
    assert (install / "_internal" / "new.dll").read_bytes() == b"fresh"
    assert (install / "userdata" / "prefs.json").read_bytes() == b'{"game_path": "C:/AoC"}'
    assert (install / "logs" / "kazbars.log").read_bytes() == b"log"
    assert (install / "_internal" / "old.dll").exists()      # pruning is a separate step
    assert not list(install.rglob("*" + S.TMP_SUFFIX))
    assert (staged / "KazBars.exe").exists()                 # staging untouched


def test_apply_tree_phase_a_failure_unwinds(tmp_path, monkeypatch):
    install = _install(tmp_path)
    staged = _staged(install)
    pairs = S.plan_copy(staged, install)
    real = S.shutil.copyfile
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 3:
            raise OSError("disk full")
        return real(src, dst)
    monkeypatch.setattr(S.shutil, "copyfile", flaky)
    with pytest.raises(OSError):
        S.apply_tree(pairs)
    assert (install / "KazBars.exe").read_bytes() == b"OLD"
    assert not list(install.rglob("*" + S.TMP_SUFFIX))


def test_prune_internal_removes_only_dead_files(tmp_path):
    install = _install(tmp_path)
    staged = _staged(install)
    (install / "_internal" / "empty").mkdir()
    (install / "_internal" / "left.kbnew").write_bytes(b"")
    (install / "_internal" / "KEEP.DLL.marker").write_bytes(b"")   # not shipped → goes
    removed = S.prune_internal(staged, install)
    names = {p.name for p in removed}
    assert names == {"old.dll", "left.kbnew", "KEEP.DLL.marker"}
    assert (install / "_internal" / "keep.dll").exists()
    assert (install / "_internal" / "sub" / "x.pyd").exists()
    assert not (install / "_internal" / "empty").exists()
    assert (install / "userdata" / "prefs.json").exists()


def test_prune_internal_is_case_insensitive(tmp_path):
    install = _install(tmp_path)
    staged = _staged(install)
    (staged / "_internal" / "keep.dll").rename(staged / "_internal" / "KEEP.dll")
    S.prune_internal(staged, install)
    assert (install / "_internal" / "keep.dll").exists()


def test_prune_internal_without_staged_internal_is_a_noop(tmp_path):
    install = _install(tmp_path)
    assert S.prune_internal(tmp_path / "nowhere", install) == []
    assert (install / "_internal" / "old.dll").exists()


# --------------------------------------------------------------------------- #
# startup marker
# --------------------------------------------------------------------------- #

def _pending(tmp_path, **fields):
    update_dir = tmp_path / S.UPDATE_DIR
    update_dir.mkdir(exist_ok=True)
    if fields:
        S.write_pending(update_dir, **fields)
    return update_dir


def test_startup_action_none_without_staging_dir(tmp_path):
    assert S.startup_action(tmp_path, "3.1.0") == ("none", None)


def test_startup_action_updated_on_version_match(tmp_path):
    _pending(tmp_path, state="applied", version="3.1.0", attempts=1)
    action, pending = S.startup_action(tmp_path, "3.1.0")
    assert action == "updated" and pending["version"] == "3.1.0"
    _pending(tmp_path, state="applying")
    assert S.startup_action(tmp_path, "3.1.0")[0] == "updated"


def test_startup_action_retry_under_cap_with_staged_exe(tmp_path):
    update_dir = _pending(tmp_path, state="applying", version="3.1.0", attempts=1)
    (update_dir / S.ZIP_ROOT).mkdir()
    (update_dir / S.ZIP_ROOT / S.EXE_NAME).write_bytes(b"NEW")
    assert S.startup_action(tmp_path, "3.0.1")[0] == "retry"
    S.write_pending(update_dir, attempts=S.MAX_APPLY_ATTEMPTS)
    assert S.startup_action(tmp_path, "3.0.1")[0] == "failed"


def test_startup_action_failed_and_clean(tmp_path):
    _pending(tmp_path, state="applying", version="3.1.0", attempts=1)   # no staged exe
    assert S.startup_action(tmp_path, "3.0.1")[0] == "failed"
    _pending(tmp_path, state="failed", error="boom")
    assert S.startup_action(tmp_path, "3.0.1")[0] == "failed"
    _pending(tmp_path, state="staged", version="3.1.0")
    assert S.startup_action(tmp_path, "3.0.1")[0] == "clean"
    (tmp_path / S.UPDATE_DIR / S.PENDING_NAME).write_text("not json", encoding="utf-8")
    assert S.startup_action(tmp_path, "3.0.1") == ("clean", None)


# --------------------------------------------------------------------------- #
# handoff
# --------------------------------------------------------------------------- #

def test_parse_args():
    assert S.parse_args([]) is None
    assert S.parse_args(["--verbose"]) is None
    assert S.parse_args([S.APPLY_FLAG]) is None                       # no target
    assert S.parse_args([S.APPLY_FLAG, "--target", "C:/K", "--wait-pid", "x"]) is None
    target, pid = S.parse_args([S.APPLY_FLAG, "--target", "C:/K", "--wait-pid", "4242"])
    assert (str(target), pid) == ("C:\\K" if sys.platform == "win32" else "C:/K", 4242)
    assert S.parse_args([S.APPLY_FLAG, "--target", "C:/K"])[1] == 0


def test_spawn_apply_argv(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(S, "spawn_detached", lambda argv, cwd: seen.append((argv, cwd)))
    S.spawn_apply(tmp_path / "staged.exe", tmp_path, 77)
    argv, cwd = seen[0]
    assert argv == [tmp_path / "staged.exe", S.APPLY_FLAG, "--target", tmp_path, "--wait-pid", 77]
    assert cwd == tmp_path
    S.respawn_apply(tmp_path)
    assert seen[1][0][0] == tmp_path / S.UPDATE_DIR / S.ZIP_ROOT / S.EXE_NAME
    assert seen[1][0][-1] == 0


def test_wait_for_pid_zero_returns_at_once():
    t0 = time.monotonic()
    S.wait_for_pid(0, 5)
    assert time.monotonic() - t0 < 0.5


@pytest.mark.skipif(sys.platform != "win32", reason="OpenProcess/WaitForSingleObject")
def test_wait_for_pid_waits_for_a_real_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.4)"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    t0 = time.monotonic()
    S.wait_for_pid(child.pid, 10)
    elapsed = time.monotonic() - t0
    assert child.poll() is not None and 0.2 < elapsed < 5
    S.wait_for_pid(child.pid, 1)                                   # already gone: no wait


def test_wait_until_writable(tmp_path):
    f = tmp_path / "KazBars.exe"
    f.write_bytes(b"x")
    assert S.wait_until_writable(f, 1) is True
    assert S.wait_until_writable(tmp_path / "missing.exe", 1) is True
    assert not (tmp_path / "missing.exe").exists()                 # probe never creates it


@pytest.mark.skipif(sys.platform != "win32", reason="Windows share-mode locking")
def test_wait_until_writable_times_out_on_a_locked_file(tmp_path):
    """A running exe is held open without FILE_SHARE_WRITE — reproduce that
    share mode (Python's own open() always shares, so it can't)."""
    import ctypes
    from ctypes import wintypes
    f = tmp_path / "KazBars.exe"
    f.write_bytes(b"x")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    generic_read, share_read, open_existing = 0x80000000, 0x1, 3
    handle = k32.CreateFileW(str(f), generic_read, share_read, None, open_existing, 0x80, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    try:
        assert S.wait_until_writable(f, 0.3, interval=0.05) is False
    finally:
        k32.CloseHandle(wintypes.HANDLE(handle))
    assert S.wait_until_writable(f, 0.3, interval=0.05) is True


# --------------------------------------------------------------------------- #
# run_apply (the --apply-update entry point)
# --------------------------------------------------------------------------- #

@pytest.fixture
def quiet_apply(monkeypatch):
    monkeypatch.setattr(S, "_configure_apply_logging", lambda _t: None)
    spawned = []
    monkeypatch.setattr(S, "spawn_detached", lambda argv, cwd: spawned.append((argv, cwd)))
    return spawned


def test_run_apply_swaps_prunes_and_relaunches(tmp_path, quiet_apply):
    install = _install(tmp_path)
    _staged(install)
    update_dir = install / S.UPDATE_DIR
    S.write_pending(update_dir, state="staged", version="9.9.9", attempts=0)

    assert S.run_apply(install, 0) == 0
    assert (install / "KazBars.exe").read_bytes() == b"NEW"
    assert not (install / "_internal" / "old.dll").exists()
    assert (install / "userdata" / "profiles" / "raid.json").exists()
    pending = S.read_pending(update_dir)
    assert pending["state"] == "applied" and pending["attempts"] == 1
    assert quiet_apply == [([install / S.EXE_NAME], install)]


def test_run_apply_failure_records_and_still_relaunches(tmp_path, quiet_apply, monkeypatch):
    install = _install(tmp_path)
    _staged(install)
    update_dir = install / S.UPDATE_DIR
    S.write_pending(update_dir, state="staged", version="9.9.9", attempts=0)
    (install / "_internal" / "half.kbnew").write_bytes(b"")

    def boom(_pairs):
        raise OSError("locked")
    monkeypatch.setattr(S, "apply_tree", boom)

    assert S.run_apply(install, 0) == 1
    pending = S.read_pending(update_dir)
    assert pending["state"] == "failed" and "locked" in pending["error"]
    assert (install / "KazBars.exe").read_bytes() == b"OLD"
    assert not (install / "_internal" / "half.kbnew").exists()
    assert quiet_apply == [([install / S.EXE_NAME], install)]


def test_run_apply_gives_up_when_the_exe_stays_locked(tmp_path, quiet_apply, monkeypatch):
    install = _install(tmp_path)
    _staged(install)
    monkeypatch.setattr(S, "wait_until_writable", lambda _p, _t: False)
    assert S.run_apply(install, 0) == 1
    assert (install / "KazBars.exe").read_bytes() == b"OLD"
    assert json.loads((install / S.UPDATE_DIR / S.PENDING_NAME).read_text())["state"] == "failed"
