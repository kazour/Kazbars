"""Tests for `console` — the in-game Console's profile section — and what a
build carries: the shell only with a tab, each tab under its own gate, and
`d.CON` with the size and the tabs in the user's order.

Run: `pytest tests/test_console.py` (from repo root).
"""

from kazbars.buff_database import BuffDatabase
from kazbars.console import PROFILE_SECTION, TABS, ships, validate_config
from kazbars.grids_generator import CodeGenerator


def test_the_section_reads_leniently_in_schema_order():
    assert TABS == ("buffs", "casts")
    assert validate_config(None) == {"enabled": False, "scale": 100, "tabs": ["buffs", "casts"]}
    c = validate_config({"enabled": "yes", "scale": 999, "tabs": ["casts", "nope", "buffs", 3, "casts"]})
    assert c == {"enabled": True, "scale": 300, "tabs": ["casts", "buffs"]}
    assert list(c) == ["enabled", "scale", "tabs"]
    assert validate_config({"tabs": "buffs"})["tabs"] == ["buffs", "casts"], "not a list: every tab"
    assert validate_config({"tabs": ["stats", "world"]})["tabs"] == [], "tabs this app does not build"
    assert not ships(validate_config({"enabled": True, "tabs": []}))
    assert ships(validate_config({"enabled": True}))
    assert PROFILE_SECTION.key == "console" and PROFILE_SECTION.lane == "build"


def _build(console):
    return CodeGenerator([], BuffDatabase(), "0.0.0", console_config=console).generate()


def test_a_build_carries_the_shell_and_each_chosen_tab_only_while_it_ships():
    main, data = _build({"enabled": True, "scale": 150, "tabs": ["buffs"]})
    assert "console = new KazBarsConsole(rootClip);" in main
    assert "console.add(new KazBarsConBuffs());" in main
    assert "console.follow(world);" in main and "modules.push(console);" in main
    assert "KazBarsConCasts" not in main
    assert '        d.CON = {fontSize: 18, tabs: ["buffs"]};' in data
    main, data = _build({"enabled": True, "tabs": ["casts", "buffs"]})
    assert "console.add(new KazBarsConCasts());" in main and "console.add(new KazBarsConBuffs());" in main
    assert '        d.CON = {fontSize: 12, tabs: ["casts", "buffs"]};' in data
    for off in ({"enabled": False}, {"enabled": True, "tabs": []}):
        main, data = _build(off)
        assert "KazBarsConsole" not in main and "KazBarsConBuffs" not in main, off
        assert "d.CON" not in data, off
