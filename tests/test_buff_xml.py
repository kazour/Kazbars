"""
Smoke test: round-trip the buff_display_editor XML helpers.

The module edits AoC HUD XML files via targeted regex (no parser). Tests
here cover: attribute extraction, surgical attribute replacement (other
bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the
filter whitespace normaliser, and the no-BuffListView guard.

Run: `pytest tests/test_buff_xml.py` (from repo root).
"""

import re

from kazbars.buff_xml import (
    FILTER_BOTH,
    FILTER_FRIENDLY,
    FILTER_HOSTILE,
    INCOMING_DAMAGE_TYPES,
    RESOURCE_LOSS_TYPES,
    _normalise_filter,
    _read_bufflistview,
    _write_bufflistview,
    read_source_color,
    read_source_direction,
    set_source_color,
    set_source_direction,
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


# =========================================================================== #
# TextColors.xml — per-source flytext direction                               #
# =========================================================================== #
# Mixed attribute orders, a spaced `direction = "1"`, a multi-line element, and
# one element with no direction attribute at all (xp_gained — the injection path).
TEXTCOLORS = '''\
<?xml version="1.0" encoding="UTF-8"?>
<TextColors>
    <text name="self_attacked"          color="0xFF0000" direction="1" />
    <text name="stamina_gained"         direction="-1"   color="0x00FF00" />
    <text name="mana_gained"            color="0x0000FF" direction="-1" />
    <text name="stamina_lost"           direction="1"    color="0x888800" />
    <text name="mana_lost"              color="0x000088" direction="1" />
    <text name="stamina_loss_critical"  direction = "1" />
    <text name="xp_gained"              color="0x111111" />
    <text name="mana_loss_critical"
          color="0x440000"
          direction="1" />
</TextColors>
'''


def _direction_of(xml, name):
    m = re.search(rf'<[^>]*\bname="{name}"[^>]*>', xml)
    assert m, f"element {name} not found"
    d = re.search(r'direction\s*=\s*"(-?\d+)"', m.group(0))
    return d.group(1) if d else None


def test_read_source_direction():
    assert read_source_direction(TEXTCOLORS, 'self_attacked') == '1'
    assert read_source_direction(TEXTCOLORS, 'stamina_gained') == '-1'
    assert read_source_direction(TEXTCOLORS, 'stamina_loss_critical') == '1'  # spaced form
    assert read_source_direction(TEXTCOLORS, 'xp_gained') is None   # element has no direction
    assert read_source_direction(TEXTCOLORS, 'nonexistent') is None


def test_set_source_direction_replaces_named_only():
    new, changed = set_source_direction(TEXTCOLORS, 'self_attacked', -1)
    assert changed is True
    assert _direction_of(new, 'self_attacked') == '-1'
    assert _direction_of(new, 'stamina_lost') == '1'      # not named → untouched
    back, changed_back = set_source_direction(new, 'self_attacked', 1)
    assert changed_back is True
    assert back == TEXTCOLORS                             # byte-identical round trip


def test_set_source_direction_accepts_all_three_values():
    for value in (1, -1, 0):
        new, _ = set_source_direction(TEXTCOLORS, 'mana_lost', value)
        assert _direction_of(new, 'mana_lost') == str(value)


def test_set_source_direction_injects_when_missing():
    new, changed = set_source_direction(TEXTCOLORS, 'xp_gained', -1)
    assert changed is True
    assert '<text name="xp_gained"              color="0x111111" direction="-1" />' in new
    assert read_source_color(new, 'xp_gained') == '111111'   # color preserved


def test_set_source_direction_idempotent_and_missing_element():
    same, changed = set_source_direction(TEXTCOLORS, 'self_attacked', 1)  # already 1
    assert changed is False and same == TEXTCOLORS
    miss, c2 = set_source_direction(TEXTCOLORS, 'nope', -1)
    assert c2 is False and miss == TEXTCOLORS


def test_set_source_direction_preserves_surrounding_bytes():
    new, _ = set_source_direction(TEXTCOLORS, 'mana_loss_critical', -1)
    assert '<?xml version="1.0" encoding="UTF-8"?>' in new
    assert 'color="0x440000"' in new       # multi-line element's body intact
    assert 'color="0x888800"' in new       # sibling untouched


def test_direction_group_lists():
    # The colors panel's two macro checkboxes flip exactly these sets.
    assert RESOURCE_LOSS_TYPES
    assert all('lost' in n or 'loss' in n for n in RESOURCE_LOSS_TYPES)
    assert INCOMING_DAMAGE_TYPES
    assert all(n.startswith('self_') for n in INCOMING_DAMAGE_TYPES)


# =========================================================================== #
# TextColors.xml — per-source flytext color                                   #
# =========================================================================== #
def test_read_source_color():
    assert read_source_color(TEXTCOLORS, 'self_attacked') == 'FF0000'
    assert read_source_color(TEXTCOLORS, 'mana_gained') == '0000FF'
    assert read_source_color(TEXTCOLORS, 'stamina_loss_critical') is None  # element has no color attr
    assert read_source_color(TEXTCOLORS, 'nonexistent') is None


def test_set_source_color_writes_0x_form():
    new, changed = set_source_color(TEXTCOLORS, 'self_attacked', 'ABCDEF')
    assert changed is True
    assert 'color="0xABCDEF"' in new
    assert read_source_color(new, 'self_attacked') == 'ABCDEF'
    assert read_source_color(new, 'mana_gained') == '0000FF'  # other sources untouched


def test_set_source_color_accepts_hash_and_0x_and_uppercases():
    n1, _ = set_source_color(TEXTCOLORS, 'self_attacked', '#abcdef')
    n2, _ = set_source_color(TEXTCOLORS, 'self_attacked', '0xabcdef')
    assert read_source_color(n1, 'self_attacked') == 'ABCDEF'
    assert read_source_color(n2, 'self_attacked') == 'ABCDEF'


def test_set_source_color_idempotent_and_missing():
    same, changed = set_source_color(TEXTCOLORS, 'self_attacked', 'FF0000')  # already that
    assert changed is False and same == TEXTCOLORS
    nocolor, c2 = set_source_color(TEXTCOLORS, 'stamina_loss_critical', '123456')  # no color attr
    assert c2 is False and nocolor == TEXTCOLORS
    miss, c3 = set_source_color(TEXTCOLORS, 'nope', '123456')  # missing element
    assert c3 is False and miss == TEXTCOLORS


def test_set_source_color_preserves_direction():
    new, _ = set_source_color(TEXTCOLORS, 'stamina_lost', '00FF00')
    assert read_source_color(new, 'stamina_lost') == '00FF00'
    assert _direction_of(new, 'stamina_lost') == '1'  # direction attr untouched


