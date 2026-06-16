"""
KazBars — Shared Build Utilities
Common functions for AS2 compilation and script management.
"""

import logging
import subprocess
from pathlib import Path

from .paths import ASSETS, COMPILER_ASSETS

logger = logging.getLogger(__name__)

# KazBars is a windowed (no-console) app; spawning a console child (mtasc, tasklist)
# makes Windows stand up a console/conhost for it via the CSR subsystem, a handshake
# that can stall ~5s per spawn on some systems (the child's initial thread blocks in
# an Executive/CSR-LPC wait). CREATE_NO_WINDOW skips the console allocation entirely.
# getattr keeps the module importable off-Windows (tests); the flag is a no-op there.
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def resolve_assets_path(assets_path=None):
    """Resolve the assets directory path. Caller-supplied path wins; otherwise
    falls back to the package's bundled assets root (dev + frozen)."""
    if assets_path is not None:
        return Path(assets_path)
    return ASSETS


def find_compiler(assets_path, app_path):
    """Find MTASC compiler, checking multiple locations. Returns Path or None."""
    for path in [
        Path(assets_path) / "compiler" / "mtasc.exe",
        COMPILER_ASSETS / "mtasc.exe",
        Path(app_path) / "compiler" / "mtasc.exe",
        Path(app_path) / "mtasc.exe",
    ]:
        if path.exists():
            return path
    return None


def compile_as2(compiler_path, classpaths, base_swf, source_as, cwd, timeout=60, extra_flags=None):
    """Run MTASC compiler. Returns (success, error_message_or_empty)."""
    cmd = [str(compiler_path)]
    for cp in classpaths:
        if Path(cp).exists():
            cmd.extend(["-cp", str(cp)])
    if extra_flags:
        cmd.extend(extra_flags)
    cmd.extend(["-swf", str(base_swf), "-version", "8"])
    if isinstance(source_as, list):
        for sa in source_as:
            cmd.append(str(sa))
    else:
        cmd.append(str(source_as))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd),
                                timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, f"MTASC compilation timed out after {timeout}s"
    if result.returncode != 0:
        error = result.stderr or result.stdout or f"Unknown MTASC error (exit code {result.returncode})"
        return False, error
    return True, ""


def strip_marker_block(content, marker):
    """Remove a marker-delimited block (marker line through next blank line)."""
    if marker not in content:
        return content
    lines = content.split('\n')
    out = []
    in_block = False
    for line in lines:
        if line.strip() == marker:
            in_block = True
            continue
        if in_block:
            if line.strip() == '':
                in_block = False
            continue
        out.append(line)
    return '\n'.join(out).rstrip('\n')


def update_script_with_marker(script_path, marker, content, old_markers=None):
    """Update or create a script file with marker-delimited content block."""
    script_path = Path(script_path)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    block = f"{marker}\n{content}\n"

    if script_path.exists():
        try:
            existing = script_path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            logger.warning("%s corrupt — overwriting with new content", script_path.name)
            existing = ""
        existing = strip_marker_block(existing, marker)
        for old in (old_markers or []):
            existing = strip_marker_block(existing, old)
        new_content = f"{existing}\n\n{block}" if existing.strip() else block
    else:
        new_content = block

    script_path.write_text(new_content, encoding='utf-8')
