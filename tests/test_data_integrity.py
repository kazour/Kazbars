"""
Smoke test: validate buff references in the default profile and the bundled
database fallback.

1. Every buff reference in the bundled `Default.json` (whitelist IDs and slot
   assignments) must resolve to an entry in `Database.json`.
2. `Database.json.default` (the bundled recovery copy) must match
   `Database.json` byte-for-byte.

Would have caught the Veil of the Unliving (Zaal) ID mismatch (5064067 vs
4752520) and the subsequent .default drift before either shipped.

Run: `pytest tests/test_data_integrity.py` (from repo root).
"""

import json
from collections import defaultdict

from kazbars.paths import KAZBARS_ASSETS


def _load_db() -> dict:
    return json.loads((KAZBARS_ASSETS / "Database.json").read_text(encoding="utf-8"))


def _load_default_profile() -> dict:
    return json.loads((KAZBARS_ASSETS / "Default.json").read_text(encoding="utf-8"))


def _collect_db_keys(db) -> tuple[set[int], set[str]]:
    entries = db if isinstance(db, list) else db.get("buffs", db.get("entries", []))
    ids: set[int] = set()
    names: set[str] = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        for sid in e.get("ids", []) or []:
            ids.add(int(sid))
        if e.get("name"):
            names.add(e["name"])
    return ids, names


def _collect_refs(profile):
    for g in profile.get("grids", []):
        name = g.get("id", "Unnamed")
        for item in g.get("whitelist", []) or []:
            yield name, "whitelist", item
        sa = g.get("slotAssignments")
        if isinstance(sa, dict):
            for k, v in sa.items():
                vs = v if isinstance(v, list) else [v]
                for x in vs:
                    yield name, f"slot[{k}]", x
        elif isinstance(sa, list):
            for i, item in enumerate(sa):
                vs = item if isinstance(item, list) else [item]
                for x in vs:
                    yield name, f"slot[{i}]", x


def test_default_profile_buff_refs_resolve() -> None:
    db = _load_db()
    profile = _load_default_profile()
    known_ids, known_names = _collect_db_keys(db)

    missing: dict[str, list] = defaultdict(list)
    for grid, kind, val in _collect_refs(profile):
        sval = str(val)
        if sval.isdigit():
            if int(sval) not in known_ids:
                missing[grid].append((kind, val))
        elif isinstance(val, str):
            if val not in known_names:
                missing[grid].append((kind, val))
        else:
            missing[grid].append((kind, f"<{type(val).__name__}> {val!r}"))

    if missing:
        lines = [f"{sum(len(v) for v in missing.values())} unresolved buff ref(s):"]
        for grid, items in missing.items():
            lines.append(f"  Grid '{grid}':")
            for kind, val in items[:10]:
                lines.append(f"    {kind}: {val}")
            if len(items) > 10:
                lines.append(f"    ... and {len(items) - 10} more")
        raise AssertionError("\n".join(lines))


def test_bundled_database_in_sync() -> None:
    live = (KAZBARS_ASSETS / "Database.json").read_bytes()
    default = (KAZBARS_ASSETS / "Database.json.default").read_bytes()
    assert live == default, (
        f"Database.json.default is out of sync with Database.json "
        f"(live={len(live)} bytes, bundled={len(default)} bytes). "
        "Re-copy Database.json over Database.json.default to resync."
    )
