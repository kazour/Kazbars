"""Unit tests for kazbars.update_check — version comparison + the release lookup.

`_parts` feeds the "is this release newer?" check behind the launch offer and
the About popup; a tag it can't parse must never make a real update read as
up-to-date. `fetch_release` is exercised with `urlopen` monkeypatched.

Run: `pytest tests/test_update_check.py` (from repo root).
"""

import io
import json
import urllib.error

import pytest

from kazbars import update_check as U
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


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _serve(monkeypatch, payload):
    def urlopen(_req, timeout=None):
        if isinstance(payload, Exception):
            raise payload
        return _Resp(json.dumps(payload).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)


class TestFetchRelease:
    def test_newer_tag_returns_the_document(self, monkeypatch):
        doc = {"tag_name": "v3.1.0", "html_url": "http://x/rel", "assets": [{"name": "KazBars.zip"}]}
        _serve(monkeypatch, doc)
        assert U.fetch_release("3.0.1") == ("update", doc)

    @pytest.mark.parametrize("tag", ["v3.0.1", "v2.9.9", "", "latest"])
    def test_same_older_or_unparseable_is_current(self, monkeypatch, tag):
        _serve(monkeypatch, {"tag_name": tag})
        assert U.fetch_release("3.0.1") == ("current", None)

    def test_network_failure_is_error(self, monkeypatch):
        _serve(monkeypatch, urllib.error.URLError("offline"))
        assert U.fetch_release("3.0.1") == ("error", None)

    def test_non_object_payload_is_error(self, monkeypatch):
        _serve(monkeypatch, ["not", "a", "release"])
        assert U.fetch_release("3.0.1") == ("error", None)


def test_release_tag_strips_the_v():
    assert U.release_tag({"tag_name": "v3.1.0"}) == "3.1.0"
    assert U.release_tag({}) == ""
