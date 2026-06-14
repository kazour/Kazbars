"""Drift guard for ota/manifest.json + CONTENT_BASELINE_VERSION.

Two invariants, mirroring test_data_integrity's byte-level guard:
  1. the committed manifest's sha256 for each payload matches the committed
     shipped stock file — payload URLs ride the `main` ref (not a commit SHA), so
     the sha256 is what guarantees integrity: the client rejects any payload whose
     hash doesn't match; and
  2. CONTENT_BASELINE_VERSION == the manifest's content_version — the two are
     stamped together by scripts/gen_manifest.py, so a drift would make a fresh
     install either re-download content it shipped with (baseline < manifest) or
     silently miss updates (baseline > manifest).

Run: `pytest tests/test_manifest.py` (from repo root).
"""

import hashlib
import json
from pathlib import Path

from kazbars import CONTENT_BASELINE_VERSION

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "ota" / "manifest.json"
STOCK = REPO / "src" / "kazbars" / "assets" / "kazbars"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_wellformed():
    assert MANIFEST.exists(), "ota/manifest.json missing — run scripts/gen_manifest.py"
    m = _manifest()
    assert isinstance(m["content_version"], int)
    assert isinstance(m["min_app_version"], str)
    assert set(m["files"]) == {"Database.json", "Default.json"}
    for info in m["files"].values():
        assert info["url"].startswith("https://raw.githubusercontent.com/")
        assert "/main/" in info["url"], "payload URLs ride the main ref, not a commit SHA"
        assert len(info["sha256"]) == 64


def test_manifest_sha256_matches_stock_files():
    for name, info in _manifest()["files"].items():
        actual = hashlib.sha256((STOCK / name).read_bytes()).hexdigest()
        assert info["sha256"] == actual, (
            f"{name} sha256 in ota/manifest.json drifted from the shipped stock file — "
            "re-run scripts/gen_manifest.py"
        )


def test_baseline_matches_manifest_version():
    assert CONTENT_BASELINE_VERSION == _manifest()["content_version"], (
        "CONTENT_BASELINE_VERSION and ota/manifest.json content_version drifted — "
        "they must be stamped together by scripts/gen_manifest.py"
    )
