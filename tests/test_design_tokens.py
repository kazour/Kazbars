"""Guard the design-token rule: no hardcoded theme colors outside ui_helpers.

docs/architecture.md says design tokens live in ``ui_helpers.py``
(THEME_COLORS / TK_COLORS / …) and panels must not hardcode colors. Prose
conventions teach by example — every leaked literal trains the next edit to
leak another — so this test makes the rule fail loudly instead: it AST-scans
every ``src/kazbars`` module except ``ui_helpers.py`` for ``#hex`` string
literals and rejects any that isn't explicitly accounted for.

Not violations, by design:

- **Pure black/white** (``#000000``/``#ffffff``, any case or 3-digit form) —
  these are ``blend_alpha`` math anchors (darken/lighten toward an extreme),
  not palette decisions; allowed anywhere.
- **The Live Tracker overlay palette** in ``live_tracker_settings.COLORS`` —
  in-game PIL-rendered status colors owned by the cluster, a different render
  domain from the ttk app theme. Allowlisted literal-by-literal so a *new*
  color added there still forces a conscious decision.

PIL ``(r, g, b)`` tuples and the AS2/XML ``0x…`` color machinery are out of
scope — the rule guards the Tk theme surface.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / 'src' / 'kazbars'

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{3,8}$')

# blend_alpha anchors — math, not palette.
_BLEND_ANCHORS = {'#000', '#000000', '#fff', '#ffffff'}

# file -> literals that are deliberately not app-theme tokens (lowercased).
_ALLOWLIST = {
    # In-game overlay status palette (PIL render domain, cluster-owned).
    'live_tracker_settings.py': {'#cccccc', '#ffdd66', '#ff7744', '#99dd66', '#6ea0ff'},
}


def _hex_literals(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and _HEX_RE.match(node.value)
    ]


def test_no_hardcoded_colors_outside_ui_helpers():
    violations = []
    for path in sorted(SRC.glob('*.py')):
        if path.name == 'ui_helpers.py':
            continue
        allowed = _ALLOWLIST.get(path.name, set())
        for lit in _hex_literals(path):
            if lit.lower() in _BLEND_ANCHORS or lit.lower() in allowed:
                continue
            violations.append(f'{path.name}: {lit!r}')
    assert not violations, (
        'Hardcoded color literals outside ui_helpers.py:\n  '
        + '\n  '.join(violations)
        + '\nUse (or add) a ui_helpers token — THEME_COLORS / TK_COLORS / '
        '_RETRO_COLORS — instead. If the color genuinely is not app theme '
        '(overlay render domain, settings data), allowlist it here with a reason.'
    )


def test_detector_finds_the_tokens_themselves():
    # Sanity canary: the same scanner pointed at the token home must light up.
    # If the AST walk or the regex ever break, this fails before the guard
    # above starts passing vacuously.
    assert len(_hex_literals(SRC / 'ui_helpers.py')) >= 20


def test_allowlist_entries_still_exist():
    # An allowlisted literal that vanished from its file is stale noise —
    # prune it so the allowlist stays an honest inventory of exceptions.
    stale = []
    for fname, literals in _ALLOWLIST.items():
        present = {lit.lower() for lit in _hex_literals(SRC / fname)}
        stale += [f'{fname}: {lit!r}' for lit in sorted(literals - present)]
    assert not stale, (
        'Allowlist entries no longer present in their file (remove them):\n  '
        + '\n  '.join(stale)
    )
