"""Tests for kazbars.settings_core — the schema-driven settings engine.

Covers Field coercion (bool/int/float/choices/custom validate/passthrough),
validate_all (strict drop-unknown + fill-missing), get_defaults freshness, the
migration ladder (ordering + idempotent fixpoint + empty no-op), and atomic file
I/O (missing/corrupt → defaults, round-trip, no leftover .tmp, schema_version
stamp, structured-dict round-trip). The three typed settings modules
(deeps/live_tracker/damageinfo) are the integration regression gate; this is the
engine's own unit gate.

Run: `pytest tests/test_settings_core.py` (from repo root).
"""

import json
from pathlib import Path

from kazbars import settings_core
from kazbars.settings_core import Field, Migration, Schema, Store

# --------------------------------------------------------------------------- #
# A representative schema exercising every Field flavour.
# --------------------------------------------------------------------------- #


def _clamp_positions(value):
    """Structured-dict validator: keep {name: {x, y}} entries with int coords,
    clamped to a sane range. Models the Phase-2 window_positions field."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for name, pos in value.items():
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            out[name] = {
                "x": max(0, min(int(pos["x"]), 7680)),
                "y": max(0, min(int(pos["y"]), 4320)),
            }
    return out


def _schema(version=1, migrations=()):
    return Schema(
        "test_settings.json",
        version,
        {
            "flag": Field(True, kind="bool"),
            "count": Field(10, min=0, max=100, kind="int"),
            "ratio": Field(0.5, min=0.0, max=1.0, kind="float"),
            "mode": Field("a", choices=("a", "b", "c")),
            "width": Field(5, kind="int", choices=(5, 7, 11)),
            "positions": Field({}, validate=_clamp_positions),
            "label": Field("hello"),  # no spec → passthrough
        },
        migrations=migrations,
    )


# --------------------------------------------------------------------------- #
# Field coercion (via coerce — unknown keys pass through)
# --------------------------------------------------------------------------- #

class TestCoerce:
    def test_bool(self):
        s = _schema()
        assert settings_core.coerce(s, "flag", 0) is False
        assert settings_core.coerce(s, "flag", "yes") is True

    def test_int_clamp_and_round(self):
        s = _schema()
        assert settings_core.coerce(s, "count", 999) == 100
        assert settings_core.coerce(s, "count", -5) == 0
        v = settings_core.coerce(s, "count", 30.0)
        assert v == 30 and isinstance(v, int)

    def test_float_clamp(self):
        s = _schema()
        assert settings_core.coerce(s, "ratio", 5.0) == 1.0
        assert settings_core.coerce(s, "ratio", -1.0) == 0.0
        assert isinstance(settings_core.coerce(s, "ratio", 1), float)

    def test_numeric_garbage_falls_back_to_default(self):
        s = _schema()
        assert settings_core.coerce(s, "count", "junk") == 10
        assert settings_core.coerce(s, "ratio", None) == 0.5

    def test_string_choices(self):
        s = _schema()
        assert settings_core.coerce(s, "mode", "b") == "b"
        assert settings_core.coerce(s, "mode", "z") == "a"   # off-list → default
        assert settings_core.coerce(s, "mode", None) == "a"

    def test_int_choices_coerce_then_membership(self):
        s = _schema()
        assert settings_core.coerce(s, "width", "7") == 7    # coerced then matched
        assert settings_core.coerce(s, "width", 6) == 5      # off-list → default
        assert settings_core.coerce(s, "width", "junk") == 5

    def test_custom_validate_override(self):
        s = _schema()
        out = settings_core.coerce(s, "positions", {"main": {"x": 99999, "y": -3}})
        assert out == {"main": {"x": 7680, "y": 0}}
        assert settings_core.coerce(s, "positions", "not a dict") == {}

    def test_passthrough_field(self):
        s = _schema()
        assert settings_core.coerce(s, "label", "anything") == "anything"

    def test_unknown_key_passthrough(self):
        s = _schema()
        assert settings_core.coerce(s, "not_a_field", "kept") == "kept"


# --------------------------------------------------------------------------- #
# validate_all (strict drop-unknown + fill-missing)
# --------------------------------------------------------------------------- #

class TestValidateAll:
    def test_empty_returns_defaults(self):
        s = _schema()
        assert settings_core.validate_all(s, {}) == settings_core.get_defaults(s)

    def test_non_dict_returns_defaults(self):
        s = _schema()
        assert settings_core.validate_all(s, None) == settings_core.get_defaults(s)

    def test_known_kept_and_coerced(self):
        s = _schema()
        out = settings_core.validate_all(s, {"count": 999})
        assert out["count"] == 100
        assert out["mode"] == "a"  # filled

    def test_unknown_dropped_strict(self):
        s = _schema()
        out = settings_core.validate_all(s, {"bogus": 1})
        assert "bogus" not in out


# --------------------------------------------------------------------------- #
# get_defaults freshness
# --------------------------------------------------------------------------- #

class TestGetDefaults:
    def test_returns_fresh_mutable_copies(self):
        s = _schema()
        a = settings_core.get_defaults(s)
        a["positions"]["main"] = {"x": 1, "y": 2}
        b = settings_core.get_defaults(s)
        assert b["positions"] == {}            # not shared with the schema default
        assert s.fields["positions"].default == {}


# --------------------------------------------------------------------------- #
# Migration ladder
# --------------------------------------------------------------------------- #

def _trail_migrations():
    return (
        Migration(2, lambda d: {**d, "label": d.get("label", "") + "a"}),
        Migration(3, lambda d: {**d, "label": d.get("label", "") + "b"}),
    )


class TestMigrations:
    def test_empty_ladder_is_noop(self):
        s = _schema()
        raw = {"label": "x", "schema_version": 1}
        assert settings_core._migrate(s, raw) is raw

    def test_runs_rungs_in_order_from_stored_version(self):
        s = _schema(version=3, migrations=_trail_migrations())
        out = settings_core._migrate(s, {"label": "", "schema_version": 1})
        assert out["label"] == "ab"   # v2 then v3, in order

    def test_only_runs_rungs_above_stored_version(self):
        s = _schema(version=3, migrations=_trail_migrations())
        out = settings_core._migrate(s, {"label": "", "schema_version": 2})
        assert out["label"] == "b"    # v2 skipped (already applied)

    def test_idempotent_fixpoint(self):
        s = _schema(version=3, migrations=_trail_migrations())
        once = settings_core._migrate(s, {"label": "", "schema_version": 1})
        # Re-running on already-migrated data (now at current version) is a no-op.
        twice = settings_core._migrate(s, {**once, "schema_version": 3})
        assert twice["label"] == once["label"] == "ab"

    def test_load_applies_ladder(self, tmp_path):
        s = _schema(version=3, migrations=_trail_migrations())
        (tmp_path / s.filename).write_text(
            json.dumps({"label": "", "schema_version": 1}), encoding="utf-8"
        )
        loaded = settings_core.load(s, tmp_path)
        assert loaded["label"] == "ab"


# --------------------------------------------------------------------------- #
# File I/O
# --------------------------------------------------------------------------- #

class TestFileIO:
    def test_load_missing_returns_defaults(self, tmp_path):
        s = _schema()
        assert settings_core.load(s, tmp_path) == settings_core.get_defaults(s)

    def test_load_corrupt_returns_defaults(self, tmp_path):
        s = _schema()
        (tmp_path / s.filename).write_text("{not json", encoding="utf-8")
        assert settings_core.load(s, tmp_path) == settings_core.get_defaults(s)

    def test_load_non_dict_json_returns_defaults(self, tmp_path):
        s = _schema()
        (tmp_path / s.filename).write_text("[1, 2, 3]", encoding="utf-8")
        assert settings_core.load(s, tmp_path) == settings_core.get_defaults(s)

    def test_save_creates_folder(self, tmp_path):
        s = _schema()
        nested = tmp_path / "a" / "b"
        assert settings_core.save(s, nested, settings_core.get_defaults(s)) is True
        assert (nested / s.filename).exists()

    def test_round_trip(self, tmp_path):
        s = _schema()
        data = settings_core.get_defaults(s)
        data["count"] = 42
        data["mode"] = "c"
        data["positions"] = {"main": {"x": 100, "y": 200}}
        assert settings_core.save(s, tmp_path, data) is True
        assert settings_core.load(s, tmp_path) == data

    def test_save_stamps_schema_version(self, tmp_path):
        s = _schema(version=4)
        settings_core.save(s, tmp_path, settings_core.get_defaults(s))
        on_disk = json.loads((tmp_path / s.filename).read_text(encoding="utf-8"))
        assert on_disk["schema_version"] == 4

    def test_schema_version_not_leaked_into_loaded_data(self, tmp_path):
        s = _schema()
        settings_core.save(s, tmp_path, settings_core.get_defaults(s))
        assert "schema_version" not in settings_core.load(s, tmp_path)

    def test_atomic_save_leaves_no_tmp(self, tmp_path):
        s = _schema()
        settings_core.save(s, tmp_path, settings_core.get_defaults(s))
        assert list(Path(tmp_path).glob("*.tmp")) == []

    def test_save_validates_out_of_range_before_write(self, tmp_path):
        s = _schema()
        bad = settings_core.get_defaults(s)
        bad["count"] = 99999
        settings_core.save(s, tmp_path, bad)
        on_disk = json.loads((tmp_path / s.filename).read_text(encoding="utf-8"))
        assert on_disk["count"] == 100

    def test_structured_dict_round_trip(self, tmp_path):
        s = _schema()
        data = settings_core.get_defaults(s)
        data["positions"] = {"main": {"x": 12, "y": 34}, "alt": {"x": 56, "y": 78}}
        settings_core.save(s, tmp_path, data)
        assert settings_core.load(s, tmp_path)["positions"] == data["positions"]


# --------------------------------------------------------------------------- #
# Store (stateful facade)
# --------------------------------------------------------------------------- #

class TestStore:
    def test_get_set_save_reload(self, tmp_path):
        s = _schema()
        store = Store(s, tmp_path)
        assert store.get("count") == 10
        store.set("count", 42)
        assert store.save() is True

        fresh = Store(s, tmp_path)
        assert fresh.get("count") == 42

    def test_reload_picks_up_external_write(self, tmp_path):
        s = _schema()
        store = Store(s, tmp_path)
        store.set("mode", "b")
        store.save()
        # Simulate a restore overwriting the file underneath us.
        other = settings_core.get_defaults(s)
        other["mode"] = "c"
        settings_core.save(s, tmp_path, other)
        store.reload()
        assert store.get("mode") == "c"

    def test_save_with_explicit_data(self, tmp_path):
        s = _schema()
        store = Store(s, tmp_path)
        store.save({**settings_core.get_defaults(s), "count": 7})
        assert store.get("count") == 7
        assert Store(s, tmp_path).get("count") == 7
