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


def _scan_tree(tree):
    """Yield (line, has_creationflags) for every subprocess spawn call in an
    already-parsed module — `subprocess.run(...)` under any import alias
    (`import subprocess as sp`), or a bare `run(...)` from
    `from subprocess import run [as x]`."""
    module_aliases = set()
    name_to_spawner = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'subprocess':
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == 'subprocess':
            for alias in node.names:
                if alias.name in SPAWNERS:
                    name_to_spawner[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        via_module = (
            isinstance(fn, ast.Attribute) and fn.attr in SPAWNERS
            and isinstance(fn.value, ast.Name) and fn.value.id in module_aliases
        )
        via_name = isinstance(fn, ast.Name) and fn.id in name_to_spawner
        if via_module or via_name:
            yield node.lineno, any(kw.arg == 'creationflags' for kw in node.keywords)


def _spawn_sites():
    """Yield (file, line, has_creationflags) for every subprocess spawn call
    under src/kazbars/."""
    for path in sorted(SRC.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for line, has in _scan_tree(tree):
            yield path.name, line, has


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
    would pass vacuously. Three sites are known to exist."""
    assert len(list(_spawn_sites())) == 3


def test_scan_detects_aliased_module_and_from_import_spawns():
    """No file in src today uses an aliased subprocess import or a bare
    `from subprocess import ...` — this proves the scan would still catch a
    missing flag if one ever did, rather than passing vacuously."""
    src = (
        "import subprocess as sp\n"
        "from subprocess import call as spawn\n"
        "def f():\n"
        "    sp.run(['x'])\n"
        "    spawn(['y'], creationflags=1)\n"
    )
    hits = sorted(_scan_tree(ast.parse(src)))
    assert hits == [(4, False), (5, True)]
