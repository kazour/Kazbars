"""Static-import guard for the Live Tracker cluster.

The cluster (`live_tracker_panel`, `boss_timer`, `combat_monitor`,
`timer_overlay`, `live_tracker_settings`) is intentionally isolated:
- Only `app.py` imports it from outside.
- It only imports stdlib + cluster-internal modules — no other panels.

This is a convention from `docs/architecture.md`. This test makes the
convention enforceable so an accidental cross-cluster import shows up
in CI rather than slipping through review.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "src" / "kazbars"

CLUSTER = {
    "live_tracker_panel",
    "boss_timer",
    "combat_monitor",
    "timer_overlay",
    "live_tracker_settings",
}

# Only this module is allowed to reach into the cluster from outside.
ALLOWED_INBOUND = {"app"}

# Shared infrastructure: design tokens, widget builders, settings, window
# geometry, paths. Any module — cluster or not — may import these. The
# cluster's isolation rule is about not depending on *other panels*, not
# about avoiding the shared base layer.
INFRASTRUCTURE = {
    "paths",
    "settings_manager",
    "window_position",
    "ui_helpers",
    "ui_widgets",
    "ui_components",
    "ui_tk_style",
    "custom_menu_bar",
}


def _imported_kazbars_modules(py_path: Path) -> set[str]:
    """Return the set of `kazbars.*` (or relative) sibling modules imported."""
    src = py_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            # Relative: `from .X import Y` or `from .X.Y import Z`
            if level == 1 and module:
                imports.add(module.split(".")[0])
            # Absolute: `from kazbars.X import Y`
            elif module.startswith("kazbars."):
                imports.add(module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("kazbars."):
                    imports.add(alias.name.split(".")[1])
    return imports


def test_only_app_imports_into_cluster() -> None:
    """No module outside the cluster (except app.py) should import a cluster member."""
    violators: list[tuple[str, set[str]]] = []
    for py in PKG_ROOT.glob("*.py"):
        stem = py.stem
        if stem in CLUSTER or stem in ALLOWED_INBOUND:
            continue
        imported = _imported_kazbars_modules(py)
        cluster_imports = imported & CLUSTER
        if cluster_imports:
            violators.append((stem, cluster_imports))
    assert not violators, (
        "Modules outside the Live Tracker cluster (and outside app.py) must not "
        f"import cluster members. Violators: {violators}"
    )


def test_cluster_does_not_import_other_panels() -> None:
    """Cluster members may import each other or shared infrastructure only."""
    allowed = CLUSTER | INFRASTRUCTURE
    violators: list[tuple[str, set[str]]] = []
    for stem in CLUSTER:
        py = PKG_ROOT / f"{stem}.py"
        if not py.exists():
            continue
        imported = _imported_kazbars_modules(py)
        forbidden = imported - allowed
        if forbidden:
            violators.append((stem, forbidden))
    assert not violators, (
        "Live Tracker cluster modules must not import other panels. "
        f"Violators: {violators}"
    )
