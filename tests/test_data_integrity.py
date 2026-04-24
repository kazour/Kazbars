"""
Smoke test: validate buff references in the default profile and the bundled
database fallback.

1. Every buff reference in assets/kzgrids/Default.json (whitelist IDs and
   slot assignments) must resolve to an entry in Database.json.
2. Database.json.default (the bundled recovery copy) must match Database.json
   byte-for-byte.

Would have caught the Veil of the Unliving (Zaal) ID mismatch (5064067 vs
4752520) and the subsequent .default drift before either shipped.

Run: python tests/test_data_integrity.py
Exit code 0 on success, non-zero if any reference is unresolvable or the
bundled DB is out of sync.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / 'assets' / 'kzgrids'


def collect_db_keys(db):
    """Extract every spell ID and every name from the buff DB."""
    entries = db if isinstance(db, list) else db.get('buffs', db.get('entries', []))
    ids = set()
    names = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        for sid in e.get('ids', []) or []:
            ids.add(int(sid))
        if e.get('name'):
            names.add(e['name'])
    return ids, names


def collect_refs(profile):
    """Yield (grid_id, kind, value) for every buff reference in the profile."""
    for g in profile.get('grids', []):
        name = g.get('id', 'Unnamed')
        for item in g.get('whitelist', []) or []:
            yield name, 'whitelist', item
        sa = g.get('slotAssignments')
        if isinstance(sa, dict):
            for k, v in sa.items():
                vs = v if isinstance(v, list) else [v]
                for x in vs:
                    yield name, f'slot[{k}]', x
        elif isinstance(sa, list):
            for i, item in enumerate(sa):
                vs = item if isinstance(item, list) else [item]
                for x in vs:
                    yield name, f'slot[{i}]', x


def main():
    db = json.loads((DB_DIR / 'Database.json').read_text(encoding='utf-8'))
    profile = json.loads((DB_DIR / 'Default.json').read_text(encoding='utf-8'))
    known_ids, known_names = collect_db_keys(db)

    missing = defaultdict(list)
    total = 0
    for grid, kind, val in collect_refs(profile):
        total += 1
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
        n = sum(len(v) for v in missing.values())
        print(f"FAIL: {n} unresolved buff ref(s) in {len(missing)} grid(s):")
        for grid, items in missing.items():
            print(f"  Grid '{grid}':")
            for kind, val in items[:10]:
                print(f"    {kind}: {val}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")
        sys.exit(1)

    live = (DB_DIR / 'Database.json').read_bytes()
    default = (DB_DIR / 'Database.json.default').read_bytes()
    if live != default:
        print("FAIL: Database.json.default is out of sync with Database.json.")
        print(f"  live={len(live)} bytes, bundled={len(default)} bytes.")
        print("  Re-copy Database.json over Database.json.default to resync.")
        sys.exit(1)

    print(f"OK — {total} buff ref(s) in Default.json resolve cleanly; bundled DB matches live.")


if __name__ == '__main__':
    main()
