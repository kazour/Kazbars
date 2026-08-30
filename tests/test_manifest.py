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

Plus the generator itself, on throwaway copies: min_app_version is a floor that
a regeneration preserves (only --min-app raises it), and a no-arg run on an
unchanged tree is a byte-for-byte no-op — the CI drift check relies on that.

Run: `pytest tests/test_manifest.py` (from repo root).
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

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
        # LF-normalized: GitHub raw serves the LF blob (git normalizes these text
        # files on commit) while the Windows working tree is CRLF. The manifest and
        # the client both key off the LF bytes, so this guards what's actually served.
        actual = hashlib.sha256((STOCK / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert info["sha256"] == actual, (
            f"{name} sha256 in ota/manifest.json drifted from the shipped stock file — "
            "re-run scripts/gen_manifest.py"
        )


def test_baseline_matches_manifest_version():
    assert CONTENT_BASELINE_VERSION == _manifest()["content_version"], (
        "CONTENT_BASELINE_VERSION and ota/manifest.json content_version drifted — "
        "they must be stamped together by scripts/gen_manifest.py"
    )


# --------------------------------------------------------------------------- #
# the generator (throwaway copies of the manifest, __init__ and stock files)
# --------------------------------------------------------------------------- #

@pytest.fixture
def gen(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gen_manifest", REPO / "scripts" / "gen_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stock = tmp_path / "stock"
    stock.mkdir()
    for name in mod.FILES:
        (stock / name).write_text('{"v": 1}', encoding="utf-8")
    init = tmp_path / "__init__.py"
    init.write_text('__version__ = "3.0.1"\nCONTENT_BASELINE_VERSION = 5\n', encoding="utf-8")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "STOCK", stock)
    monkeypatch.setattr(mod, "INIT", init)
    monkeypatch.setattr(mod, "MANIFEST", tmp_path / "ota" / "manifest.json")
    return mod


def _seed(gen, floor="3.0.0"):
    gen.MANIFEST.parent.mkdir()
    gen.MANIFEST.write_text(json.dumps({
        "schema": 1, "content_version": 5, "min_app_version": floor, "notes": "old", "files": {},
    }), encoding="utf-8")


def test_first_manifest_floors_at_the_app_version(gen):
    gen.main("first")
    m = json.loads(gen.MANIFEST.read_text(encoding="utf-8"))
    assert (m["content_version"], m["min_app_version"], m["notes"]) == (1, "3.0.1", "first")


def test_regeneration_preserves_the_floor(gen):
    _seed(gen, floor="3.0.0")
    (gen.STOCK / "Database.json").write_text('{"v": 2}', encoding="utf-8")   # content moved
    gen.main("bump")
    m = json.loads(gen.MANIFEST.read_text(encoding="utf-8"))
    assert m["content_version"] == 6
    assert m["min_app_version"] == "3.0.0"                # NOT the running 3.0.1
    assert "CONTENT_BASELINE_VERSION = 6" in gen.INIT.read_text(encoding="utf-8")


def test_min_app_raises_the_floor(gen):
    _seed(gen, floor="3.0.0")
    gen.main("needs the document format", min_app="3.1.0")
    assert json.loads(gen.MANIFEST.read_text(encoding="utf-8"))["min_app_version"] == "3.1.0"


def test_verify_run_is_a_noop(gen):
    gen.main("seed")
    before = gen.MANIFEST.read_bytes(), gen.INIT.read_bytes()
    gen.main()                                             # what ota-manifest.yml runs
    assert (gen.MANIFEST.read_bytes(), gen.INIT.read_bytes()) == before
