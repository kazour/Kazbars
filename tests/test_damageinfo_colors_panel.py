"""Data-layer tests for damageinfo_colors_panel.

The panel UI is Tk and verified manually; the load-bearing logic is pure file I/O:
``_read_colors``/``_read_directions`` (what seeds each row / what "reset" reads) and
``apply_colors`` (write to Customized, created from Default, colors + directions). Both
are unit-tested here. This panel is the only writer of TextColors.xml — the build and
uninstall never touch it — so the direction scenarios that used to live in
test_build_executor are covered here too.

Run: `pytest tests/test_damageinfo_colors_panel.py` (from repo root).
"""

from kazbars.damageinfo_colors_panel import _read_colors, _read_directions, apply_colors

SAMPLE = (
    '<TextColors>\n'
    '  <text name="self_attacked" color="0xFF0000" direction="1" />\n'
    '  <text name="other_healed" color="0x00ff00" direction="1" />\n'
    '  <text name="stamina_lost" direction="1" />\n'   # no color attr
    '  <text name="mana_lost" color="0x000088" />\n'   # no direction attr
    '</TextColors>\n'
)


def _gui(game, skin):
    return game / "Data" / "Gui" / skin / "TextColors.xml"


def _write(p, text=SAMPLE):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# _read_colors
# --------------------------------------------------------------------------- #
def test_read_none_and_missing(tmp_path):
    assert _read_colors(None) == {}
    assert _read_colors(tmp_path / "nope.xml") == {}


def test_read_bare_upper_hex_omits_colorless(tmp_path):
    p = _write(tmp_path / "TextColors.xml")
    out = _read_colors(p)
    # bare upper hex; the color-less entry (stamina_lost) is omitted
    assert out == {'self_attacked': 'FF0000', 'other_healed': '00FF00', 'mana_lost': '000088'}


# --------------------------------------------------------------------------- #
# _read_directions
# --------------------------------------------------------------------------- #
def test_read_directions_none_and_missing(tmp_path):
    assert _read_directions(None) == {}
    assert _read_directions(tmp_path / "nope.xml") == {}


def test_read_directions_omits_attrless(tmp_path):
    p = _write(tmp_path / "TextColors.xml")
    # mana_lost has no direction attr — left out so the panel can fall back to Default/
    assert _read_directions(p) == {
        'self_attacked': 1, 'other_healed': 1, 'stamina_lost': 1,
    }


# --------------------------------------------------------------------------- #
# apply_colors — always writes Customized, colors only
# --------------------------------------------------------------------------- #
def test_none_when_no_textcolors_anywhere(tmp_path):
    assert apply_colors(str(tmp_path), {'self_attacked': '00FF00'}) is None


def test_creates_customized_from_default_leaves_default_stock(tmp_path):
    default = _write(_gui(tmp_path, "Default"))
    written = apply_colors(str(tmp_path), {'self_attacked': '00FF00'})

    cust = _gui(tmp_path, "Customized")
    assert written == cust
    assert 'name="self_attacked" color="0x00FF00"' in cust.read_text(encoding="utf-8")
    # Default is never written — the game patcher would reset it anyway.
    assert 'name="self_attacked" color="0xFF0000"' in default.read_text(encoding="utf-8")
    # No pre-existing Customized file, so nothing to back up.
    assert not cust.with_name("TextColors.xml.kazbars.bak").exists()


def test_edits_existing_customized_and_backs_it_up_once(tmp_path):
    _write(_gui(tmp_path, "Default"))
    cust = _write(_gui(tmp_path, "Customized"))
    apply_colors(str(tmp_path), {'other_healed': '112233'})

    text = cust.read_text(encoding="utf-8")
    assert 'name="other_healed" color="0x112233"' in text
    bak = cust.with_name("TextColors.xml.kazbars.bak")
    assert 'name="other_healed" color="0x00ff00"' in bak.read_text(encoding="utf-8")  # genuine pre-edit backup


def test_preserves_directions_and_other_colors(tmp_path):
    _write(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {'self_attacked': '00FF00'})
    text = _gui(tmp_path, "Customized").read_text(encoding="utf-8")
    assert 'name="self_attacked" color="0x00FF00" direction="1"' in text  # direction untouched
    assert 'name="other_healed" color="0x00ff00"' in text                 # sibling untouched


def test_colorless_source_is_a_noop(tmp_path):
    # stamina_lost has no color attr in the file; set_source_color can't inject one, so it
    # is silently skipped rather than corrupting the element.
    _write(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {'stamina_lost': 'ABCDEF'})
    text = _gui(tmp_path, "Customized").read_text(encoding="utf-8")
    assert 'name="stamina_lost" direction="1" />' in text
    assert 'ABCDEF' not in text


def test_reset_to_default_flow(tmp_path):
    # The panel's "reset to game default" reads a color from Default and stages it; Apply
    # then writes it to Customized. Simulate: user had a custom Customized, resets to stock.
    _write(_gui(tmp_path, "Default"))  # self_attacked = FF0000 (stock)
    cust = _write(_gui(tmp_path, "Customized"),
                  SAMPLE.replace('0xFF0000', '0x00FF00'))  # customized = green
    stock = _read_colors(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {'self_attacked': stock['self_attacked']})
    assert 'name="self_attacked" color="0xFF0000"' in cust.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# apply_colors — directions (ported from the old build/uninstall toggle tests)
# --------------------------------------------------------------------------- #
def _dirs(tmp_path, skin="Customized"):
    return _read_directions(_gui(tmp_path, skin))


def test_directions_none_leaves_every_direction_alone(tmp_path):
    _write(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {'self_attacked': '00FF00'})
    assert _dirs(tmp_path) == {'self_attacked': 1, 'other_healed': 1, 'stamina_lost': 1}


def test_direction_flip_creates_customized_and_leaves_default_stock(tmp_path):
    default = _write(_gui(tmp_path, "Default"))  # no Customized copy yet
    written = apply_colors(str(tmp_path), {}, {'stamina_lost': -1})

    cust = _gui(tmp_path, "Customized")
    assert written == cust
    assert 'name="stamina_lost" direction="-1"' in cust.read_text(encoding="utf-8")
    # Default is never written — the game patcher would reset it anyway.
    assert 'name="stamina_lost" direction="1"' in default.read_text(encoding="utf-8")
    assert not cust.with_name("TextColors.xml.kazbars.bak").exists()


def test_direction_flip_backs_up_pre_existing_customized_once(tmp_path):
    _write(_gui(tmp_path, "Default"))
    cust = _write(_gui(tmp_path, "Customized"))
    apply_colors(str(tmp_path), {}, {'stamina_lost': -1})
    apply_colors(str(tmp_path), {}, {'other_healed': -1})

    bak = cust.with_name("TextColors.xml.kazbars.bak")
    assert 'name="stamina_lost" direction="1"' in bak.read_text(encoding="utf-8")  # pre-edit


def test_directions_and_colors_survive_each_other(tmp_path):
    _write(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {'self_attacked': '00FF00'})          # color only
    apply_colors(str(tmp_path), {}, {'self_attacked': -1})            # direction only
    text = _gui(tmp_path, "Customized").read_text(encoding="utf-8")
    assert 'name="self_attacked" color="0x00FF00" direction="-1"' in text


def test_direction_accepts_all_three_values_and_flips_back(tmp_path):
    _write(_gui(tmp_path, "Default"))
    for value in (-1, 0, 1):
        apply_colors(str(tmp_path), {}, {'self_attacked': value})
        assert _dirs(tmp_path)['self_attacked'] == value


def test_direction_injected_when_the_source_omits_it(tmp_path):
    # mana_lost carries no direction attr in the stock file; the panel must still be able
    # to send it somewhere (set_source_direction injects, unlike the color writer).
    _write(_gui(tmp_path, "Default"))
    apply_colors(str(tmp_path), {}, {'mana_lost': -1})
    text = _gui(tmp_path, "Customized").read_text(encoding="utf-8")
    assert 'name="mana_lost" color="0x000088" direction="-1" />' in text


def test_none_when_no_textcolors_anywhere_with_directions(tmp_path):
    assert apply_colors(str(tmp_path), {}, {'self_attacked': -1}) is None
