"""Guard that the mypy blocking gate covers the whole Tk-free logic core.

The gate (``[tool.mypy] files`` in pyproject.toml) is includes-based on
purpose: a Tk/ttkbootstrap module must never land on the blocking step (the
runtime ``bootstyle`` kwargs emit errors mypy can't resolve). But the flip
side — a new Tk-free module that nobody adds to the list — used to "fail
safe" into the advisory pass, which is ``continue-on-error`` and therefore
invisible. This test closes that loop: it derives the Tk-free set the same
way docs/architecture.md defines it (no ``tkinter``/``ttkbootstrap`` import
anywhere in the module) and asserts the gate list matches it exactly, in
both directions, with no phantom entries.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / 'src' / 'kazbars'
TK_ROOTS = {'tkinter', 'ttkbootstrap'}


def _gate_files():
    pyproject = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    return pyproject['tool']['mypy']['files']


def _imports_tk(path):
    """True if the module imports tkinter/ttkbootstrap anywhere (lazy included)."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split('.')[0] in TK_ROOTS for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or '').split('.')[0] in TK_ROOTS:
                return True
    return False


GATED = _gate_files()
TK_FREE = {p.as_posix().replace(REPO_ROOT.as_posix() + '/', '')
           for p in SRC.glob('*.py') if not _imports_tk(p)}


def test_gate_entries_exist_on_disk():
    phantoms = sorted(f for f in GATED if not (REPO_ROOT / f).exists())
    assert not phantoms, (
        '[tool.mypy] files lists modules that no longer exist:\n  '
        + '\n  '.join(phantoms)
        + '\nRemove (or rename) the entries in pyproject.toml.'
    )


def test_every_tk_free_module_is_gated():
    ungated = sorted(TK_FREE - set(GATED))
    assert not ungated, (
        'These modules import neither tkinter nor ttkbootstrap but are not on '
        'the mypy blocking gate ([tool.mypy] files in pyproject.toml):\n  '
        + '\n  '.join(ungated)
        + '\nAdd them to the list (and fix any errors `python -m mypy` then '
        'reports) so the Tk-free core stays fully type-checked.'
    )


def test_no_gated_module_imports_tk():
    offenders = sorted(set(GATED) - TK_FREE - {f for f in GATED if not (REPO_ROOT / f).exists()})
    assert not offenders, (
        'These gated modules import tkinter/ttkbootstrap — they belong on the '
        'advisory pass, not the blocking gate:\n  '
        + '\n  '.join(offenders)
    )
