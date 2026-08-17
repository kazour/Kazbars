"""Tests for `profile_io` — the pure pieces of the app-facing profile satellite.

Since the revamp, profile_io orchestrates `profile_library` + `profile_store`
(each with its own suite); what's testable headless here is the template
chain order — OTA content first, then the interim new-format template, then
the shipped stock file — and the missing-buff message shape. The Tk-driven
flows (apply_document, switch, rename/delete dialogs) are covered by the
panel-construction smoke and manual QA.

Run: `pytest tests/test_profile_io.py` (from repo root).
"""

from pathlib import Path
from types import SimpleNamespace

from kazbars import profile_io, userdata


def test_template_chain_order(monkeypatch, tmp_path):
    monkeypatch.setattr(userdata, "app_path", lambda: tmp_path)
    app = SimpleNamespace(assets_path=Path("A:/assets"))
    chain = profile_io.template_paths(app)
    assert chain == (
        tmp_path / "userdata" / "content" / "Default.json",
        Path("A:/assets/kazbars/templates/Default.json"),
        Path("A:/assets/kazbars/Default.json"),
    )
