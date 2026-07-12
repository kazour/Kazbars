"""Unit tests for kazbars.update_check version comparison.

`_parts` feeds the "is this release newer?" checks in both the silent launch
check and the manual About-popup check; a tag it can't parse must never make
a real update read as up-to-date.

Run: `pytest tests/test_update_check.py` (from repo root).
"""

from kazbars.update_check import _parts


class TestParts:
    def test_plain_semver(self):
        assert _parts("2.2.0") == (2, 2, 0)

    def test_numeric_not_lexicographic_ordering(self):
        assert _parts("2.10.0") > _parts("2.9.9")

    def test_prerelease_suffix_keeps_numeric_prefix(self):
        # A suffixed tag must still compare as newer than an older version,
        # not collapse to () and read as up-to-date.
        assert _parts("2.3.0-rc1") == (2, 3, 0)
        assert _parts("2.3.0-rc1") > _parts("2.2.0")

    def test_prerelease_equals_its_release_prefix(self):
        # Suffix ordering (rc1 < final) is out of scope — the prefix ties.
        assert _parts("2.3.0-rc1") == _parts("2.3.0")

    def test_garbage_tag_is_conservative(self):
        # Fully unparseable → () → compares as "no update" downstream.
        assert _parts("latest") == ()

    def test_parse_stops_at_first_bad_component(self):
        assert _parts("2.x.9") == (2,)
