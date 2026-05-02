"""
Smoke test: every kazbars submodule imports cleanly.

Catches missing symbols, wrong-module references, and import cycles — every
failure mode a symbol-move refactor can introduce. Each module is its own
parametrized test case so pytest reports the failure on the offending module
rather than a single rolled-up error.

Run: `pytest tests/test_imports.py` (from repo root).
"""

import importlib
import pkgutil

import kazbars


def _all_modules() -> list[str]:
    mods = ["kazbars", "kazbars.app", "kazbars.__main__"]
    for _, name, _ in pkgutil.iter_modules(kazbars.__path__):
        if name in ("__main__", "app"):
            continue
        mods.append(f"kazbars.{name}")
    return sorted(mods)


def pytest_generate_tests(metafunc):
    if "modname" in metafunc.fixturenames:
        metafunc.parametrize("modname", _all_modules())


def test_module_imports_cleanly(modname: str) -> None:
    importlib.import_module(modname)
