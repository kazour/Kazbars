"""Unit tests for kazbars.settings_manager atomic write helpers.

`safe_write_text` / `safe_save_json` (temp file + rename) back every
settings, profile, and customized-skin write — a crash mid-write must never
leave a torn file behind.

Run: `pytest tests/test_settings_manager.py` (from repo root).
"""

import json

from kazbars.settings_manager import safe_save_json, safe_write_text


class TestSafeWriteText:
    def test_round_trip_creates_parents(self, tmp_path):
        target = tmp_path / "sub" / "TextColors.xml"
        safe_write_text(target, "<Colors/>")
        assert target.read_text(encoding="utf-8") == "<Colors/>"

    def test_overwrite_leaves_no_tmp_behind(self, tmp_path):
        target = tmp_path / "file.xml"
        safe_write_text(target, "one")
        safe_write_text(target, "two")
        assert target.read_text(encoding="utf-8") == "two"
        assert list(tmp_path.iterdir()) == [target]


class TestSafeSaveJson:
    def test_round_trip(self, tmp_path):
        target = tmp_path / "prefs.json"
        safe_save_json(target, {"a": 1})
        assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
