"""Guard the satellite ⇄ KazBarsApp attribute contract.

The kazbars-only satellites (profile_io, build_action, content_update, …) take
the whole ``KazBarsApp`` instance as their ``app`` argument — a deliberately
wide seam (docs/architecture.md → "kazbars-only satellites"). The cost of that
width is that nothing static ties a satellite's ``app.<attr>`` accesses to what
``KazBarsApp`` actually defines: rename an attribute in app.py and the break
surfaces at runtime, in whichever flow happens to cross it.

This test makes the seam a checked contract without narrowing it: it AST-scans
every ``src/kazbars`` module for attribute accesses on a parameter named
``app`` (reads *and* writes — a satellite inventing app state by assignment is
the same hidden coupling) and asserts each attribute is defined on
``KazBarsApp``: inherited Tk surface via ``dir()``, plus every ``self.X = …``
the class assigns (collected from app.py's AST, since instance attributes
aren't on the class object).

Deliberately out of scope: ``getattr(app, 'x', default)`` (defensive by
design) and ``self.app.X`` chains in widget classes (different convention,
noisier signal).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from kazbars.app import KazBarsApp

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / 'src' / 'kazbars'


def _self_assigned_attrs():
    """Every `self.X = …` target inside class KazBarsApp (tuple unpacks too)."""
    tree = ast.parse((SRC / 'app.py').read_text(encoding='utf-8'))
    attrs = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == 'KazBarsApp'):
            continue
        for n in ast.walk(node):
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, (ast.Tuple, ast.List)):
                        targets.extend(t.elts)
                    elif isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id == 'self':
                        attrs.add(t.attr)
    return attrs


DECLARED = set(dir(KazBarsApp)) | _self_assigned_attrs()


def _app_accesses():
    """module name -> set of attrs accessed on an `app` parameter."""
    per_module = {}
    for path in sorted(SRC.glob('*.py')):
        if path.name == 'app.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        attrs = set()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
            if 'app' not in [a.arg for a in params]:
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                        and n.value.id == 'app':
                    attrs.add(n.attr)
        if attrs:
            per_module[path.name] = attrs
    return per_module


ACCESSES = _app_accesses()


def test_app_accesses_were_collected():
    # If the satellite convention or this scanner ever drift apart, the
    # parametrized test below would pass vacuously. Pin floors well under the
    # real counts (~13 modules / ~74 attrs) so that fails loudly instead.
    total = sum(len(a) for a in ACCESSES.values())
    assert len(ACCESSES) >= 8 and total >= 40, (
        f'Only {len(ACCESSES)} modules / {total} app.<attr> accesses collected '
        '— the app-parameter convention and this scanner have likely drifted apart.'
    )


@pytest.mark.parametrize('module', sorted(ACCESSES))
def test_app_attrs_resolve(module):
    missing = sorted(ACCESSES[module] - DECLARED)
    assert not missing, (
        f'{module} accesses attributes that KazBarsApp never defines:\n  '
        + '\n  '.join(f'app.{a}' for a in missing)
        + '\nRenamed in app.py? Update the satellite. New cross-module state? '
        'Declare it in KazBarsApp.__init__ (the # State block) so the '
        'contract stays visible in one place.'
    )
