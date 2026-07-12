"""Guard that docs/architecture.md's File inventory and docs/flows.md stay honest.

Mirrors the repo's other invariant tests (``test_cluster_isolation``, the
``Database.json``/``.default`` byte-parity check in ``test_data_integrity``):
it turns silent doc drift into a CI failure instead of a thing someone notices
six months later.

architecture.md inventory — three checks, in increasing tolerance for churn:

  1. No phantoms  -- every ``src/kazbars/*.py`` / ``tests/*.py`` path named in
     the inventory still exists on disk.
  2. Completeness -- every ``src/kazbars/*.py`` and ``tests/*.py`` on disk is
     listed in the inventory.
  3. Line counts  -- each documented count is within a *generous* tolerance of
     reality (``max(40, 25%)``). Deliberately loose: a routine edit must never
     trip CI, but a file that grew by a quarter (the kind of change that also
     stales its role blurb) should. Exact refresh is a manual chore; this only
     catches gross drift.

flows.md — refs are function-anchored (`` `callable()` — src/kazbars/file.py ``),
never line numbers, so they survive edits. Three checks keep them live:

  4. No line numbers -- a ``.py:N`` ref is banned doc-wide (it rots on nearly
     every edit above it; the function name is the stable anchor).
  5. Files exist     -- every ``src/kazbars/*.py`` mentioned exists on disk.
  6. Callables exist -- each step's subject callable(s) (the backticked
     ``name()`` tokens before the file ref) resolve to a def/class somewhere
     in that file's AST, so a rename fails CI instead of orphaning the doc.

docs/CHANGELOG.md — releases can't outrun the changelog:

  7. Every ``v*`` release tag has a ``## [X.Y.Z]`` section, so a release can't
     ship while its entries still sit under ``[Unreleased]`` (v2.2.2 did
     exactly that). Skips when tags are unavailable — CI checkouts are shallow
     and tagless — so the local pre-commit run is the enforcement point.

Refreshing these docs is a manual chore; this
test just makes the drift impossible to merge silently.
"""

from __future__ import annotations

import ast
import math
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCH_DOC = REPO_ROOT / 'docs' / 'architecture.md'
FLOWS_DOC = REPO_ROOT / 'docs' / 'flows.md'

# Match only File-inventory *table rows* (`| `path` | N | role |`), not prose
# mentions of the same path elsewhere in the doc — the smoke-test bullets name
# these files too, with case counts / "1080p" etc. that would be misread as a
# line count.
_ROW_RE = re.compile(
    r'^\s*\|\s*`?(src/kazbars/[A-Za-z0-9_]+\.py|tests/[A-Za-z0-9_]+\.py)`?\s*\|\s*(\d+)\s*\|'
)


def _documented_rows():
    """Map each inventory .py path to its claimed line count."""
    rows = {}
    for line in ARCH_DOC.read_text(encoding='utf-8').splitlines():
        m = _ROW_RE.match(line)
        if m:
            rows.setdefault(m.group(1), int(m.group(2)))
    return rows


def _on_disk():
    found = set()
    for sub in ('src/kazbars', 'tests'):
        for p in (REPO_ROOT / sub).glob('*.py'):
            found.add(f'{sub}/{p.name}')
    return found


def _actual_lines(rel):
    # Count '\n' bytes to match `wc -l` regardless of line endings.
    return (REPO_ROOT / rel).read_bytes().count(b'\n')


DOCUMENTED = _documented_rows()
ON_DISK = _on_disk()
_COUNTED = sorted(p for p, n in DOCUMENTED.items() if n is not None and p in ON_DISK)


def test_no_phantom_files():
    phantoms = sorted(p for p in DOCUMENTED if p not in ON_DISK)
    assert not phantoms, (
        'architecture.md inventory names files that no longer exist:\n  '
        + '\n  '.join(phantoms)
        + '\nUpdate the inventory to match the tree.'
    )


def test_inventory_is_complete():
    missing = sorted(p for p in ON_DISK if p not in DOCUMENTED)
    assert not missing, (
        "These source/test files aren't in architecture.md's inventory:\n  "
        + '\n  '.join(missing)
        + '\nAdd a row (path, line count, role).'
    )


@pytest.mark.parametrize('rel', _COUNTED)
def test_line_count_within_tolerance(rel):
    claimed = DOCUMENTED[rel]
    actual = _actual_lines(rel)
    tol = max(40, math.ceil(0.25 * claimed))
    assert abs(actual - claimed) <= tol, (
        f'{rel}: architecture.md says {claimed} lines, actual {actual} '
        f'(delta {actual - claimed:+d}, tolerance +/-{tol}). '
        'Refresh the inventory row to match the tree.'
    )


# =============================================================================
# FLOWS.MD — function-anchored refs stay resolvable
# =============================================================================

# A numbered step whose subject ends in a file ref: `7. `do_thing()` — src/...py — …`.
# The subject is everything before the ` — path` separator; description text
# after the second ` — ` is deliberately NOT validated (it name-drops helpers
# from *other* files).
_STEP_REF_RE = re.compile(
    r'^(?P<subject>\d+\.\s+.*?) — (?P<path>src/kazbars/[A-Za-z0-9_]+\.py)(?: — |\s*$)'
)
# Backticked callables in a subject: `KazBarsApp._build()`, `profile_io.save(...)`.
_SUBJECT_CALL_RE = re.compile(r'`([A-Za-z_][A-Za-z0-9_.]*)\(')
_ANY_PATH_RE = re.compile(r'src/kazbars/[A-Za-z0-9_]+\.py')

_FLOWS_TEXT = FLOWS_DOC.read_text(encoding='utf-8')


def _flows_subject_refs():
    """(doc line, callable as written, file path) for every step subject."""
    refs = []
    for lineno, line in enumerate(_FLOWS_TEXT.splitlines(), 1):
        m = _STEP_REF_RE.match(line.strip())
        if not m:
            continue
        for name in _SUBJECT_CALL_RE.findall(m.group('subject')):
            refs.append((lineno, name, m.group('path')))
    return refs


_FLOWS_REFS = _flows_subject_refs()
_DEFINED_NAMES: dict[str, set[str]] = {}


def _defined_names(rel):
    """Every def/class name anywhere in the module (methods included)."""
    if rel not in _DEFINED_NAMES:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding='utf-8'))
        _DEFINED_NAMES[rel] = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
    return _DEFINED_NAMES[rel]


def test_flows_has_no_line_number_refs():
    stale = [
        f'line {i}: {m.group(0)}'
        for i, line in enumerate(_FLOWS_TEXT.splitlines(), 1)
        for m in re.finditer(r'[A-Za-z0-9_]+\.py:\d+', line)
    ]
    assert not stale, (
        'flows.md refs are function-anchored, never file:line (line numbers '
        'rot on every edit). Drop the :N suffix — the subject callable is the '
        'anchor:\n  ' + '\n  '.join(stale)
    )


def test_flows_referenced_files_exist():
    missing = sorted(
        {p for p in _ANY_PATH_RE.findall(_FLOWS_TEXT) if not (REPO_ROOT / p).exists()}
    )
    assert not missing, (
        'flows.md references files that no longer exist:\n  '
        + '\n  '.join(missing)
        + '\nUpdate the references to match the tree.'
    )


def test_flows_steps_were_collected():
    # If the step regex ever stops matching the doc's format, the parametrized
    # test below would silently pass on an empty list. Pin a floor well under
    # the real count (~125) so a format change fails loudly instead.
    assert len(_FLOWS_REFS) >= 50, (
        f'Only {len(_FLOWS_REFS)} step refs parsed from flows.md — the step '
        'format and _STEP_REF_RE have likely drifted apart.'
    )


@pytest.mark.parametrize(
    'lineno,name,rel',
    _FLOWS_REFS,
    ids=[f'L{lineno}-{name}' for lineno, name, _ in _FLOWS_REFS],
)
def test_flows_subject_callable_resolves(lineno, name, rel):
    leaf = name.split('.')[-1]
    assert leaf in _defined_names(rel), (
        f'flows.md line {lineno}: step references `{name}()` in {rel}, but no '
        f'def/class named "{leaf}" exists there. Renamed? Update the flow step '
        'accordingly.'
    )


# =============================================================================
# CHANGELOG.MD — every release tag has its section
# =============================================================================

CHANGELOG_DOC = REPO_ROOT / 'docs' / 'CHANGELOG.md'


def _release_versions():
    """Version strings for every v* tag, or None when tags are unavailable."""
    try:
        out = subprocess.run(
            ['git', 'tag', '--list', 'v*'],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    versions = [t.strip().removeprefix('v') for t in out.stdout.splitlines() if t.strip()]
    return versions or None


def test_every_release_tag_has_a_changelog_section():
    versions = _release_versions()
    if versions is None:
        pytest.skip(
            'git tags unavailable (shallow or tagless checkout) — '
            'the local pre-commit run enforces this check'
        )
    headings = set(
        re.findall(r'^## \[(\d+\.\d+\.\d+)\]', CHANGELOG_DOC.read_text(encoding='utf-8'), re.M)
    )
    missing = sorted(v for v in versions if v not in headings)
    assert not missing, (
        'docs/CHANGELOG.md has no section for released tag(s):\n  '
        + '\n  '.join(f'v{v}' for v in missing)
        + '\nA release shipped without its changelog entry — move what shipped '
        'out of [Unreleased] into a dated [X.Y.Z] section.'
    )
