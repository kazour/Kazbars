"""Tests for scripts/cut_release.py — the release cut the train and the manual
routine both run. Throwaway copies of the three files it edits; never git.

Run: `pytest tests/test_cut_release.py` (from repo root).
"""

import importlib.util
import io
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

CHANGELOG = """# Changelog

## [Unreleased]

### Changed

- **One check for everything.** Both updates in one place.

### Fixed

- **Big layouts build again.** Splits the data.
- **Toast stays clickable.** Grab released first.

## [3.0.1] — 2026-08-30

### Fixed

- Old entry.
"""

NOTES = """## What's New in v3.0.1

Old lead.

### Fixed

**Old bullet.**

---

Buff/debuff overlay editor for **Age of Conan**.

## Install

1. Download.
"""

INIT = '"""KazBars."""\n\n__version__ = "3.0.1"\nAPP_NAME = "KazBars"\n'


@pytest.fixture
def cr(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("cut_release", REPO / "scripts" / "cut_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (tmp_path / "release-notes.md").write_text(NOTES, encoding="utf-8")
    (tmp_path / "__init__.py").write_text(INIT, encoding="utf-8")
    monkeypatch.setattr(mod, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(mod, "NOTES", tmp_path / "release-notes.md")
    monkeypatch.setattr(mod, "INIT", tmp_path / "__init__.py")
    return mod


def _read(cr, name):
    return getattr(cr, name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# the decision
# --------------------------------------------------------------------------- #

def test_patch_without_added(cr):
    assert cr.next_version((3, 0, 1), "### Fixed\n\n- x") == ((3, 0, 2), "patch")


def test_minor_with_added(cr):
    assert cr.next_version((3, 0, 1), "### Added\n\n- x")[0] == (3, 1, 0)
    assert cr.next_version((3, 0, 1), "- mentions ### Added inline")[0] == (3, 0, 2)


def test_unreleased_body_stops_at_the_next_release(cr):
    body = cr.unreleased_body(CHANGELOG)
    assert body.startswith("### Changed") and "Old entry" not in body
    assert cr.unreleased_body("# x\n\n## [Unreleased]\n\n## [1.0.0] — d\n") == ""


def test_lead_line_counts_bullets_per_section(cr):
    assert cr.lead_line(cr.unreleased_body(CHANGELOG)) == "A small update: 1 changed, 2 fixed."
    assert cr.lead_line("### Added\n\n- a\n- b") == "A small update: 2 added."
    assert cr.lead_line("just prose") == "A small update."


# --------------------------------------------------------------------------- #
# the cut
# --------------------------------------------------------------------------- #

def test_cut_rewrites_all_three_files(cr, capsys):
    assert cr.main(["--date", "2026-09-06"]) == 0
    changelog = _read(cr, "CHANGELOG")
    assert "## [Unreleased]\n\n## [3.0.2] — 2026-09-06\n\n### Changed" in changelog
    assert changelog.count("## [Unreleased]") == 1
    assert '__version__ = "3.0.2"' in _read(cr, "INIT")
    notes = _read(cr, "NOTES")
    assert notes.startswith("## What's New in v3.0.2\n\nA small update: 1 changed, 2 fixed.\n\n### Changed")
    assert "Old lead" not in notes and "Old bullet" not in notes
    assert notes.endswith("---\n\nBuff/debuff overlay editor for **Age of Conan**.\n\n## Install\n\n1. Download.\n")
    assert "Cut v3.0.2 (patch) from v3.0.1" in capsys.readouterr().out


def test_dry_run_writes_nothing(cr, capsys):
    assert cr.main(["--dry-run", "--date", "2026-09-06"]) == 0
    assert _read(cr, "CHANGELOG") == CHANGELOG
    assert _read(cr, "NOTES") == NOTES
    assert _read(cr, "INIT") == INIT
    out = capsys.readouterr().out
    assert "Would cut v3.0.2" in out and "## What's New in v3.0.2" in out


def test_added_makes_it_minor(cr):
    cr.CHANGELOG.write_text(CHANGELOG.replace("### Changed", "### Added", 1), encoding="utf-8")
    assert cr.main(["--date", "2026-09-06"]) == 0
    assert '__version__ = "3.1.0"' in _read(cr, "INIT")
    assert "## [3.1.0] — 2026-09-06" in _read(cr, "CHANGELOG")


def test_forced_version(cr):
    assert cr.main(["--version", "4.0.0", "--date", "2026-09-06"]) == 0
    assert '__version__ = "4.0.0"' in _read(cr, "INIT")
    assert "## What's New in v4.0.0" in _read(cr, "NOTES")


@pytest.mark.parametrize("bad", ["3.0.1", "2.9.9", "3.0", "v3.0.2"])
def test_forced_version_must_be_above_current_and_well_formed(cr, bad):
    with pytest.raises(SystemExit):
        cr.main(["--version", bad])
    assert _read(cr, "INIT") == INIT


def test_empty_unreleased_is_exit_3_and_idempotent(cr):
    assert cr.main(["--date", "2026-09-06"]) == 0
    assert cr.main(["--date", "2026-09-07"]) == cr.NOTHING_TO_DO
    assert '__version__ = "3.0.2"' in _read(cr, "INIT")           # unchanged by the second run
    assert _read(cr, "CHANGELOG").count("## [3.0.") == 2


def test_missing_divider_is_an_error(cr):
    cr.NOTES.write_text("## What's New\n\nno divider\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cr.main(["--date", "2026-09-06"])
    assert _read(cr, "CHANGELOG") == CHANGELOG                     # nothing written


def test_real_repo_dry_run_parses():
    """The script runs against the actual repo files without writing — exit 0
    when [Unreleased] has entries, 3 when it is empty; never 1."""
    spec = importlib.util.spec_from_file_location("cut_release_real", REPO / "scripts" / "cut_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--dry-run"]) in (0, mod.NOTHING_TO_DO)


def test_dry_run_survives_a_cp1252_console(cr, monkeypatch):
    """The manual routine runs on Windows, whose console is cp1252 by default;
    the What's New block carries ▸ and —. Printing must not crash after the
    files have been written, so the script fixes its own stdout encoding."""
    cr.CHANGELOG.write_text(CHANGELOG.replace("Both updates", "Updates ▸ Check — both"), encoding="utf-8")
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", write_through=True))
    assert cr.main(["--dry-run", "--date", "2026-09-06"]) == 0
    sys.stdout.flush()
    assert "Updates ▸ Check — both" in raw.getvalue().decode("utf-8")
