"""Data-layer test for damageinfo_colors_panel — baseline color reading (no Tk).

The panel UI itself is Tk and verified manually; ``_read_baseline_colors`` is pure
file I/O and is the load-bearing logic (which file to read, backup-first), so it is
unit-tested here.

Run: `pytest tests/test_damageinfo_colors_panel.py` (from repo root).
"""

from kazbars.buff_xml import BACKUP_SUFFIX
from kazbars.damageinfo_colors_panel import _read_baseline_colors

SAMPLE = (
    '<TextColors>\n'
    '  <text name="self_attacked" color="0xFF0000" direction="1" />\n'
    '  <text name="other_healed" color="0x00ff00" direction="1" />\n'
    '  <text name="stamina_lost" direction="1" />\n'  # no color attr
    '</TextColors>\n'
)


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_empty_when_no_game_path():
    assert _read_baseline_colors(None) == {}
    assert _read_baseline_colors("") == {}


def test_empty_when_file_missing(tmp_path):
    assert _read_baseline_colors(str(tmp_path)) == {}


def test_reads_live_default(tmp_path):
    _write(tmp_path / "Data" / "Gui" / "Default" / "TextColors.xml", SAMPLE)
    out = _read_baseline_colors(str(tmp_path))
    # bare upper hex; the color-less entry is omitted
    assert out == {'self_attacked': 'FF0000', 'other_healed': '00FF00'}


def test_prefers_customized_over_default(tmp_path):
    _write(tmp_path / "Data" / "Gui" / "Default" / "TextColors.xml", SAMPLE)
    _write(
        tmp_path / "Data" / "Gui" / "Customized" / "TextColors.xml",
        '<TextColors>\n  <text name="self_attacked" color="0x0000FF" direction="1" />\n</TextColors>\n',
    )
    out = _read_baseline_colors(str(tmp_path))
    assert out['self_attacked'] == '0000FF'  # the file the game actually reads


def test_prefers_backup_over_live(tmp_path):
    # With a stock backup present, baseline = stock so "reset" reverts to the game default,
    # not a color we applied on a previous build.
    default = tmp_path / "Data" / "Gui" / "Default" / "TextColors.xml"
    _write(default, SAMPLE.replace('0xFF0000', '0x123456'))          # live = previously patched
    _write(default.with_name("TextColors.xml" + BACKUP_SUFFIX), SAMPLE)  # backup = stock
    out = _read_baseline_colors(str(tmp_path))
    assert out['self_attacked'] == 'FF0000'  # from the backup
