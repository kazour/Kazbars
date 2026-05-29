"""Guard that docs/architecture.md's File inventory stays honest.

Mirrors the repo's other invariant tests (``test_cluster_isolation``, the
``Database.json``/``.default`` byte-parity check in ``test_data_integrity``):
it turns silent doc drift into a CI failure instead of a thing someone notices
six months later. Three checks, in increasing tolerance for churn:

  1. No phantoms  -- every ``src/kazbars/*.py`` / ``tests/*.py`` path named in
     the inventory still exists on disk.
  2. Completeness -- every ``src/kazbars/*.py`` and ``tests/*.py`` on disk is
     listed in the inventory.
  3. Line counts  -- each documented count is within a *generous* tolerance of
     reality (``max(40, 25%)``). Deliberately loose: a routine edit must never
     trip CI, but a file that grew by a quarter (the kind of change that also
     stales its role blurb) should. Exact refresh is the agent's job; this only
     catches gross drift.

The ``/sync-docs`` command and the ``doc-maintainer`` agent refresh these; this
test just makes the drift impossible to merge silently.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCH_DOC = REPO_ROOT / 'docs' / 'architecture.md'

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
        + '\nRun /sync-docs (or the doc-maintainer agent) to reconcile.'
    )


def test_inventory_is_complete():
    missing = sorted(p for p in ON_DISK if p not in DOCUMENTED)
    assert not missing, (
        "These source/test files aren't in architecture.md's inventory:\n  "
        + '\n  '.join(missing)
        + '\nAdd a row (path, line count, role) or run /sync-docs.'
    )


@pytest.mark.parametrize('rel', _COUNTED)
def test_line_count_within_tolerance(rel):
    claimed = DOCUMENTED[rel]
    actual = _actual_lines(rel)
    tol = max(40, math.ceil(0.25 * claimed))
    assert abs(actual - claimed) <= tol, (
        f'{rel}: architecture.md says {claimed} lines, actual {actual} '
        f'(delta {actual - claimed:+d}, tolerance +/-{tol}). '
        'Refresh the inventory via /sync-docs or the doc-maintainer agent.'
    )
