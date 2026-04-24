"""
Smoke test: walk the full import graph for Kaz Grids.

Auto-discovers every *.py file under Modules/ plus kzgrids. Catches missing
symbols, wrong-module references, and import cycles — every failure mode a
symbol-move refactor can introduce.

Run: python tests/test_imports.py
Exit code 0 on success, non-zero on any import error.
"""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def discover_modules():
    mods = ['kzgrids']
    for f in sorted((ROOT / 'Modules').glob('*.py')):
        if f.stem == '__init__':
            continue
        mods.append(f'Modules.{f.stem}')
    return mods


def main():
    modules = discover_modules()
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as e:
            failed.append((name, e))

    if failed:
        for name, e in failed:
            print(f"FAIL {name}: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"OK — imported {len(modules)} modules cleanly.")


if __name__ == '__main__':
    main()
