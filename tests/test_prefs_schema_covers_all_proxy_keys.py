"""Strict-schema safety net: every prefs key the app reads/writes through the
settings proxy MUST be a declared PREFS_SCHEMA Field.

prefs.json is validated in strict mode (settings_core drops undeclared keys), so
a key written via the proxy but missing from PREFS_SCHEMA would be silently
erased on the next save. This test greps the source for every proxy access and
asserts each resolved key is declared — the guard the overhaul plan calls for.

It recognises three proxy forms (the only ones that touch the global prefs):
  - ``get_setting('key')`` / ``set_setting('key', …)`` — the module proxy.
  - ``app.settings.get/set('key')`` / ``app.settings.data.pop('key', …)``.
  - ``self.settings.get/set('key')`` — **only in app.py**, where ``self`` is the
    app (elsewhere ``self.settings`` is a panel's own local settings dict).

String-literal keys are read directly; a key passed as an ``UPPER_CASE`` constant
(e.g. ``SETTINGS_KEY_SECTION_OPEN``) is resolved to its string value from source.
A constant that can't be resolved fails loudly rather than slipping through.

Run: `pytest tests/test_prefs_schema_covers_all_proxy_keys.py` (from repo root).
"""

import re
from pathlib import Path

from kazbars.prefs import PREFS_SCHEMA

PKG = Path(__file__).resolve().parent.parent / "src" / "kazbars"

_LITERAL = re.compile(r"""(?:get_setting|set_setting)\(\s*['"](\w+)['"]""")
_CONST = re.compile(r"""(?:get_setting|set_setting)\(\s*([A-Z_][A-Z0-9_]*)\b""")
_APP = re.compile(r"""app\.settings\.(?:get|set)\(\s*['"](\w+)['"]""")
_APP_POP = re.compile(r"""app\.settings\.data\.pop\(\s*['"](\w+)['"]""")
_SELF = re.compile(r"""self\.settings\.(?:get|set)\(\s*['"](\w+)['"]""")


def _resolve_const(name, sources):
    pat = re.compile(rf"^{re.escape(name)}\s*=\s*['\"](\w+)['\"]", re.M)
    for src in sources:
        m = pat.search(src)
        if m:
            return m.group(1)
    return None


def _collect_used_keys():
    files = {p: p.read_text(encoding="utf-8") for p in PKG.glob("*.py")}
    sources = list(files.values())
    used: set[str] = set()
    unresolved: list[str] = []
    for path, src in files.items():
        used |= set(_LITERAL.findall(src))
        used |= set(_APP.findall(src))
        used |= set(_APP_POP.findall(src))
        if path.name == "app.py":
            used |= set(_SELF.findall(src))
        for const in _CONST.findall(src):
            val = _resolve_const(const, sources)
            if val is None:
                unresolved.append(f"{path.name}:{const}")
            else:
                used.add(val)
    return used, unresolved


def test_no_unresolvable_constant_keys():
    """Every constant-named proxy key must resolve to a literal string, or the
    coverage check below can't verify it."""
    _used, unresolved = _collect_used_keys()
    assert not unresolved, (
        "get/set_setting is called with a constant whose string value couldn't be "
        f"resolved from source: {unresolved}. Add handling so its key can be checked."
    )


def test_prefs_schema_covers_all_proxy_keys():
    used, _unresolved = _collect_used_keys()
    declared = set(PREFS_SCHEMA.fields)
    missing = used - declared
    assert not missing, (
        "These keys are read/written via the settings proxy but are NOT declared in "
        f"PREFS_SCHEMA, so strict validation would erase them on the next save: "
        f"{sorted(missing)}. Add a Field for each in prefs.py."
    )
