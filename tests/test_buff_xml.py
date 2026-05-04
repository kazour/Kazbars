"""
Smoke test: round-trip the buff_display_editor XML helpers.

The module edits AoC HUD XML files via targeted regex (no parser). Tests
here cover: attribute extraction, surgical attribute replacement (other
bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the
filter whitespace normaliser, and the no-BuffListView guard.

Run: `pytest tests/test_buff_xml.py` (from repo root).
"""

from kazbars.buff_xml import (
    FILTER_BOTH,
    FILTER_FRIENDLY,
    FILTER_HOSTILE,
    _normalise_filter,
    _read_bufflistview,
    _write_bufflistview,
)

SAMPLE = '''\
<?xml version="1.0" encoding="UTF-8"?>
<View name="CharPortraitLeft">
    <!-- some comment -->
    <BuffListView name              = "BuffListView"
                  h_local_alignment = "CENTER"
                  layout_borders    = "Rect(15,0,0,0)"
                  icon_size         = "Point(31,31)"
                  icon_spacing      = "Point(3,3)"
                  full_size_limit   = "6"
                  max_columns       = "10"
                  filter            = "hostile"
    />
    <OtherWidget x="42" />
</View>
'''


def test_read_basic():
    attrs = _read_bufflistview(SAMPLE)
    assert attrs is not None
    assert attrs['icon_size'] == 'Point(31,31)'
    assert attrs['icon_spacing'] == 'Point(3,3)'
    assert attrs['max_columns'] == '10'
    assert attrs['filter'] == FILTER_HOSTILE
    assert attrs['enabled'] is True


def test_write_attrs_preserves_surrounding_bytes():
    """All bytes outside the BuffListView tag must be byte-identical."""
    new = _write_bufflistview(
        SAMPLE,
        {'icon_size': 'Point(40,40)', 'filter': 'friendly'},
        enabled=True,
    )
    assert new is not None
    assert '<?xml version="1.0" encoding="UTF-8"?>' in new
    assert '<!-- some comment -->' in new
    assert '<OtherWidget x="42" />' in new
    # The two changed attrs land:
    assert 'icon_size         = "Point(40,40)"' in new
    assert 'filter            = "friendly"' in new
    # Untouched attrs remain:
    assert 'icon_spacing      = "Point(3,3)"' in new
    assert 'max_columns       = "10"' in new
    assert 'full_size_limit   = "6"' in new
    assert 'layout_borders    = "Rect(15,0,0,0)"' in new


def test_write_unchanged_when_no_attrs_passed():
    """An empty attrs dict with enabled=True is a no-op."""
    new = _write_bufflistview(SAMPLE, {}, enabled=True)
    assert new == SAMPLE


def test_off_wraps_in_sentinel_and_round_trips():
    new = _write_bufflistview(SAMPLE, {}, enabled=False)
    assert new is not None
    assert '<!--KZ_OFF' in new
    assert 'KZ_OFF-->' in new
    # Re-read should report enabled=False, attrs intact.
    attrs = _read_bufflistview(new)
    assert attrs is not None
    assert attrs['enabled'] is False
    assert attrs['icon_size'] == 'Point(31,31)'
    assert attrs['filter'] == FILTER_HOSTILE


def test_on_unwraps_sentinel():
    off = _write_bufflistview(SAMPLE, {}, enabled=False)
    on = _write_bufflistview(off, {}, enabled=True)
    assert on is not None
    assert 'KZ_OFF' not in on
    # And reading should report enabled=True with original attrs.
    attrs = _read_bufflistview(on)
    assert attrs is not None
    assert attrs['enabled'] is True
    assert attrs['icon_size'] == 'Point(31,31)'


def test_off_then_edit_then_on_preserves_edits():
    """Toggling off, editing values, then toggling back on must keep edits."""
    off = _write_bufflistview(SAMPLE, {}, enabled=False)
    off_edited = _write_bufflistview(off, {'icon_size': 'Point(50,50)'}, enabled=False)
    on_edited = _write_bufflistview(off_edited, {}, enabled=True)
    assert on_edited is not None
    attrs = _read_bufflistview(on_edited)
    assert attrs is not None
    assert attrs['enabled'] is True
    assert attrs['icon_size'] == 'Point(50,50)'


def test_no_bufflistview_returns_none():
    """A file without <BuffListView /> returns None (read) and None (write)."""
    no_bv = '<View name="Other"><Widget/></View>'
    assert _read_bufflistview(no_bv) is None
    assert _write_bufflistview(no_bv, {'icon_size': 'Point(40,40)'}, enabled=True) is None


def test_filter_normalise_whitespace_roundtrip():
    """'friendly|hostile' (no spaces) and the canonical spaced form both
    map to BOTH; everything else falls through to its canonical form."""
    assert _normalise_filter('friendly|hostile') == FILTER_BOTH
    assert _normalise_filter('friendly | hostile') == FILTER_BOTH
    assert _normalise_filter('hostile|friendly') == FILTER_BOTH
    assert _normalise_filter('hostile') == FILTER_HOSTILE
    assert _normalise_filter('friendly') == FILTER_FRIENDLY
    assert _normalise_filter(None) is None


def test_filter_canonical_form_written():
    """Writing FILTER_BOTH yields the spaced canonical form on disk."""
    no_space = SAMPLE.replace('filter            = "hostile"',
                              'filter            = "friendly|hostile"')
    attrs = _read_bufflistview(no_space)
    assert attrs is not None
    assert attrs['filter'] == FILTER_BOTH
    written = _write_bufflistview(no_space, {'filter': FILTER_BOTH}, enabled=True)
    assert written is not None
    assert 'filter            = "friendly | hostile"' in written


