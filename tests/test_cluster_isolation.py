"""Static-import guard for the Live Tracker and Deeps clusters.

Two clusters in the codebase:

  - **Live Tracker** (`live_tracker_panel`, `boss_timer`, `combat_monitor`,
    `timer_overlay`, `live_tracker_settings`): the Ethram-Fal seed timer.
  - **Deeps** (`deeps_panel`, `deeps_overlay`, `deeps_meter`,
    `deeps_trackers`, `deeps_rolling_window`, `deeps_settings`,
    `deeps_parsers`): the DPS / DPIS / HPS meter.

Both clusters share the rule:
  - Only `app.py` imports cluster members from outside.
  - Cluster members import only stdlib + cluster-internal modules +
    shared infrastructure (design tokens, widget builders, settings,
    window geometry, paths).
  - The two clusters MUST NOT cross-import each other. Each owns its
    own tail thread, overlay, and panel — `architecture.md` lists this
    as the load-bearing convention that keeps them independently
    evolvable.

This module makes the rule enforceable via static AST inspection so
accidental cross-cluster imports show up in CI rather than in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent / "src" / "kazbars"

LIVE_TRACKER_CLUSTER = {
    "live_tracker_panel",
    "boss_timer",
    "combat_monitor",
    "timer_overlay",
    "live_tracker_settings",
}

DEEPS_CLUSTER = {
    "deeps_panel",
    "deeps_overlay",
    "deeps_meter",
    "deeps_trackers",
    "deeps_rolling_window",
    "deeps_settings",
    "deeps_parsers",
}

# Only this module is allowed to reach into either cluster from outside.
ALLOWED_INBOUND = {"app"}

# Shared infrastructure: design tokens, widget builders, settings, window
# geometry, paths. Any module — cluster or not — may import these. The
# isolation rule is about not depending on *other panels*, not about
# avoiding the shared base layer.
INFRASTRUCTURE = {
    "paths",
    "settings_manager",
    "window_position",
    "ui_helpers",
    "ui_widgets",
    "ui_components",
    "ui_tk_style",
    "custom_menu_bar",
    "overlay_engine",
    "foreground",
    "focus_watcher",
}


def _imported_kazbars_modules(py_path: Path) -> set[str]:
    """Return the set of `kazbars.*` (or relative) sibling modules imported.

    Walks both top-level imports and imports inside functions/methods —
    the cluster-isolation rule applies to ALL imports, not just module-level
    ones. (app.py legitimately uses local imports inside delegator methods
    to avoid load-time cycles; those still count.)
    """
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


@pytest.mark.parametrize(
    ("cluster_name", "cluster"),
    [
        ("Live Tracker", LIVE_TRACKER_CLUSTER),
        ("Deeps", DEEPS_CLUSTER),
    ],
)
def test_only_app_imports_into_cluster(cluster_name: str, cluster: set[str]) -> None:
    """No module outside the cluster (except app.py) should import a cluster member."""
    # The OTHER cluster's modules are also "outside" — we explicitly check
    # they don't reach into this one (cross-cluster isolation).
    violators: list[tuple[str, set[str]]] = []
    for py in PKG_ROOT.glob("*.py"):
        stem = py.stem
        if stem in cluster or stem in ALLOWED_INBOUND:
            continue
        imported = _imported_kazbars_modules(py)
        cluster_imports = imported & cluster
        if cluster_imports:
            violators.append((stem, cluster_imports))
    assert not violators, (
        f"Modules outside the {cluster_name} cluster (and outside app.py) "
        f"must not import cluster members. Violators: {violators}"
    )


@pytest.mark.parametrize(
    ("cluster_name", "cluster"),
    [
        ("Live Tracker", LIVE_TRACKER_CLUSTER),
        ("Deeps", DEEPS_CLUSTER),
    ],
)
def test_cluster_does_not_import_other_panels(
    cluster_name: str, cluster: set[str]
) -> None:
    """Cluster members may import each other, shared infrastructure, or stdlib —
    nothing else."""
    allowed = cluster | INFRASTRUCTURE
    violators: list[tuple[str, set[str]]] = []
    for stem in cluster:
        py = PKG_ROOT / f"{stem}.py"
        if not py.exists():
            continue
        imported = _imported_kazbars_modules(py)
        forbidden = imported - allowed
        if forbidden:
            violators.append((stem, forbidden))
    assert not violators, (
        f"{cluster_name} cluster modules must not import other panels. "
        f"Violators: {violators}"
    )


def test_clusters_do_not_cross_import() -> None:
    """Belt-and-suspenders: neither cluster imports any member of the other.

    Already covered by the two parametrised tests above (each cluster's
    `test_only_app_imports_into_cluster` rejects imports from the other
    cluster's members). This standalone test makes the cross-cluster rule
    explicit and gives a clearer failure message if it's the bit that breaks.
    """
    cross_violations: list[tuple[str, str, set[str]]] = []
    for src_name, src_cluster, dst_name, dst_cluster in (
        ("Live Tracker", LIVE_TRACKER_CLUSTER, "Deeps", DEEPS_CLUSTER),
        ("Deeps", DEEPS_CLUSTER, "Live Tracker", LIVE_TRACKER_CLUSTER),
    ):
        for stem in src_cluster:
            py = PKG_ROOT / f"{stem}.py"
            if not py.exists():
                continue
            imported = _imported_kazbars_modules(py)
            forbidden = imported & dst_cluster
            if forbidden:
                cross_violations.append((src_name + "." + stem, dst_name, forbidden))
    assert not cross_violations, (
        "Live Tracker and Deeps clusters must stay independent. "
        f"Cross-cluster imports: {cross_violations}"
    )
