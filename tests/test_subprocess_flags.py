"""Every subprocess spawn of a console tool must pass creationflags.

KazBars ships as a windowed (``console=False``) executable. When a windowed
process spawns a console child without ``CREATE_NO_WINDOW``, Windows allocates a
console for it, and for non-elevated users that allocation costs a ~5s CSR/conhost
stall *per spawn* (diagnosed 2026-06; not antivirus). ``build_utils`` exports the
flag; every call site must use it.

This is an AST check, not a grep: it resolves the keyword arguments of each
``subprocess.run`` / ``Popen`` / ``call`` / ``check_call`` / ``check_output`` call
under ``src/kazbars/``. See docs/architecture.md -> Build pipeline.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src' / 'kazbars'
SPAWNERS = {'run', 'Popen', 'call', 'check_call', 'check_output'}


def _spawn_sites():
    """Yield (file, line, has_creationflags) for every subprocess spawn call."""
    for path in sorted(SRC.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in SPAWNERS):
                continue
            if not (isinstance(fn.value, ast.Name) and fn.value.id == 'subprocess'):
                continue
            has = any(kw.arg == 'creationflags' for kw in node.keywords)
            yield path.name, node.lineno, has


def test_every_subprocess_spawn_passes_creationflags():
    offenders = [f'{name}:{line}' for name, line, has in _spawn_sites() if not has]
    assert not offenders, (
        'subprocess spawn without creationflags=CREATE_NO_WINDOW at: '
        + ', '.join(offenders)
        + '. Import CREATE_NO_WINDOW from build_utils and pass it, or a '
          'non-elevated user pays a ~5s console-allocation stall per spawn.'
    )


def test_the_scan_still_finds_the_known_call_sites():
    """Canary: if a refactor hides every spawn from the AST walk, the check above
    would pass vacuously. Two sites are known to exist."""
    assert len(list(_spawn_sites())) >= 2
