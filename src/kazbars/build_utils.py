"""
KazBars — Shared Build Utilities
Common functions for AS2 compilation and script management.
"""

import logging
import subprocess
from pathlib import Path

from as2c.compile import compile_swf
from as2c.diagnostics import CompileError

from .paths import ASSETS

logger = logging.getLogger(__name__)

# KazBars is a windowed (no-console) app; spawning a console child (tasklist)
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


def compile_as2(classpaths, base_swf, sources):
    """Compile `sources` (and every class they reach) into `base_swf` in place, mtasc
    `-swf -version 8` semantics via as2c. Returns (success, error_message_or_empty)."""
    try:
        compile_swf(base_swf, [str(cp) for cp in classpaths if Path(cp).exists()],
                    [str(s) for s in sources])
    except CompileError as e:
        return False, str(e)
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


