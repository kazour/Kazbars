"""
KazBars — Path constants.

Two concepts, kept separate:

- **PACKAGE_ROOT** — the kazbars package directory at runtime; under it sit
  the bundled read-only assets in dev. `Path(__file__).parent` gives this in
  both dev and PyInstaller frozen builds.

- **APP_PATH** — the user-writable runtime root (settings/, profiles/). In
  dev that's the repo root; in a frozen build it's the directory next to the
  .exe. KazBars stays portable on purpose (no `%APPDATA%`) so users can keep
  multiple installs side-by-side.

`ASSETS` resolves to whichever location the bundled resources actually live
in — handles both the current `kazbars.spec` layout (assets at `<exe>/assets/`)
and a future spec change that bundles them inside the package
(`<exe>/_internal/kazbars/assets/`). Dev always uses `PACKAGE_ROOT / assets`.
"""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def _resolve_assets() -> Path:
    pkg_assets = PACKAGE_ROOT / "assets"
    if pkg_assets.exists():
        return pkg_assets
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "assets"
    return pkg_assets


ASSETS = _resolve_assets()
KAZBARS_ASSETS = ASSETS / "kazbars"
COMPILER_ASSETS = ASSETS / "compiler"
COMMON_STUBS_ASSETS = ASSETS / "common_stubs"


def app_path() -> Path:
    """Return the user-writable runtime root (parent of settings/, profiles/)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # Dev: src/kazbars/paths.py → repo root is parent.parent.parent
    return PACKAGE_ROOT.parent.parent
