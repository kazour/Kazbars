"""Tests for `inspect_catalog` — the Inspect Panel's stat rows — and the AS2
the build bakes from them (`d.INS.groups/rows/watch`, `d.INS.pvp`).

Pins the catalog's shape (112 rows in seven groups, unique keys, an `s<id>`
key reading exactly its id), the retired keys that still migrate (append-only),
selection order, the watch list, every row's AS2 fields as a valid
object-literal fragment, the fixed PvP view, the picker's edits and the
too-tall estimate.

Run: `pytest tests/test_inspect_catalog.py` (from repo root).
"""

import re

from kazbars import inspect_catalog as cat
from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import CodeGenerator
from kazbars.inspect import validate_config


def _keys(rows):
    return [r.key for r in rows]


# --------------------------------------------------------------------------
# The catalog
# --------------------------------------------------------------------------


def test_112_rows_in_seven_groups_with_unique_well_formed_keys():
    assert len(cat.ROWS) == 112
    assert [sum(1 for r in cat.ROWS if r.group is g) for g in cat.Group] == [12, 18, 6, 18, 20, 17, 21]
    assert len({r.key for r in cat.ROWS}) == 112
    for r in cat.ROWS:
        assert re.fullmatch(r"[a-z0-9_]+", r.key), r.key
        assert r.label and '"' not in r.label, r.key


def test_s_prefixed_keys_carry_their_id_in_kind():
    for r in cat.ROWS:
        if re.fullmatch(r"s\d+", r.key):
            assert r.kind.needed_ids == (int(r.key[1:]),), r.key


def test_rows_run_in_group_order():
    idx = [r.group.index for r in cat.ROWS]
    assert idx == sorted(idx)
    assert [g.label for g in cat.Group] == ["Summary", "Vitals", "Attributes", "Offensive",
                                           "Defensive", "PvP Stats", "PvP Combat"]
    assert [g.player_gated for g in cat.Group] == [False] * 5 + [True] * 2


def test_watch_ids_cover_every_row_ascending_with_the_always_ids():
    ids = cat.watch_ids(list(cat.ROWS))
    assert ids == sorted(set(ids))
    for r in cat.ROWS:
        assert set(r.kind.needed_ids) <= set(ids), r.key
    assert set(cat.ALWAYS_IDS) <= set(ids)
    assert cat.watch_ids([]) == [1, 54, 67, 70, 804, 808, 810, 814]


def test_the_default_sheet_is_the_summary_group():
    labels = [cat.find(k).label for k in cat.default_keys()]
    assert labels == ["Health", "Armor", "Protection", "Crit Chance / Damage", "Hate",
                      "Critig Chance / Amount", "Tenacity", "Armor / Spell Pen", "Heal Rating",
                      "Combat Rating", "Bonus Spell Damage", "Ferocity"]
    assert cat.watch_ids(cat.shown(None)) == [
        1, 27, 54, 67, 70, 148, 157, 158, 162, 167, 170, 312, 334, 448, 449, 450, 451, 452, 488, 491,
        507, 710, 711, 713, 804, 808, 810, 814, 861, 866, 867, 868, 869, 870, 871, 872, 873, 875,
        876, 877, 878, 879, 902, 905, 906, 907, 908, 911, 926, 927, 928, 929, 1007, 1008, 1009,
        1010, 1403, 1000016, 1000017, 1000018]


def test_every_shipped_retired_key_still_migrates_and_targets_are_live():
    shipped = {
        "pvp_kills_deaths": ("pvp_kills", "pvp_deaths"),
        "season_kd": ("pvp_kills", "pvp_deaths"),
        "s1000025": ("pvp_tournament_wins",),
        "s1000026": ("pvp_conquest_wins",),
        "s1000027": ("pvp_conquest_losses",),
        "s311": ("pvp_hit",),
        "s1100": ("pvp_immunity",),
        "pvp_spell_dmg": ("pvp_spell_holy", "pvp_spell_unholy", "pvp_spell_cold",
                          "pvp_spell_elec", "pvp_spell_fire"),
    }
    for old, new in shipped.items():
        assert cat.ALIASES[old] == new, old
    for old, new in cat.ALIASES.items():
        assert cat.find(old) is None, old
        assert new and all(cat.find(k) for k in new), old
    assert cat.resolve("armor") == ("armor",)
    assert cat.resolve("season_kd") == ("pvp_kills", "pvp_deaths")
    assert cat.resolve("s448") == () and cat.resolve("no_such_key") == ()


def test_the_pvp_groups_follow_the_game_tabs():
    assert _keys(r for r in cat.ROWS if r.group is cat.Group.PVP_STATS) == [
        "pvp_kills", "pvp_deaths", "pvp_fatalities", "s1097", "pvp_annih_wins",
        "pvp_annih_losses", "pvp_cts_wins", "pvp_cts_losses", "pvp_conquest_wins",
        "pvp_conquest_losses", "pvp_tournament_wins", "pvp_siege_wins", "pvp_siege_losses",
        "pvp_abandoned", "s690", "pvp_kd", "pvp_minigames"]
    assert _keys(r for r in cat.ROWS if r.group is cat.Group.PVP_COMBAT) == [
        "pvp_evade", "pvp_hit", "pvp_immunity", "pvp_armor", "pvp_combat_rating",
        "pvp_prot_holy", "pvp_prot_unholy", "pvp_prot_cold", "pvp_prot_elec", "pvp_prot_fire",
        "pvp_spell_holy", "pvp_spell_unholy", "pvp_spell_cold", "pvp_spell_elec", "pvp_spell_fire",
        "pvp_tap_phys", "pvp_tap_phys_mana", "pvp_tap_phys_stam", "pvp_tap_magic",
        "pvp_tap_magic_mana", "pvp_tap_magic_stam"]


def test_the_pvp_view_is_pvp_combat_less_the_taps_then_the_record():
    want = [r.key for r in cat.ROWS
            if r.group is cat.Group.PVP_COMBAT and not r.kind.as2_fields.startswith('f: "tap"')]
    assert _keys(cat.pvp_rows()) == [*want, "pvp_kd", "pvp_minigames"]
    assert cat.find("pvp_combat_rating").label == "Combat Damage Increase"
    schools = [int(re.search(r"s: (\d+)", cat.find(k).kind.as2_fields).group(1))
               for _, k in cat.PVP_VIEW[2][2]]
    assert schools == [878, 879, 158, 877, 876]


def test_select_keeps_group_order_skips_unknown_dedups_and_keeps_the_stored_order():
    assert _keys(cat.select(["armor", "nope", "health", "ferocity", "health"])) == [
        "health", "ferocity", "armor"]
    assert _keys(cat.select(["prot_fire", "s810", "armor", "s804", "evade"])) == [
        "s810", "s804", "prot_fire", "armor", "evade"]


def test_as2_fields_spot_checks():
    assert cat.find("sum_health").as2_fields().endswith(", z: 1")
    assert "z: 1" not in cat.find("armor").as2_fields()
    assert cat.find("prot_holy").as2_fields() == 'f: "prot", s: 928, t: 810, i: 907, p: 0'
    assert cat.find("tap_magic").as2_fields() == 'f: "tap", s: 533, d: 100, t: 476'
    assert cat.find("pvp_tap_phys").as2_fields() == 'f: "tap", s: 894, d: 1, t: 477, u: 227, v: 478'
    assert cat.raw(27).as2_fields == 'f: "raw", s: 27'
    assert cat.health().as2_fields == 'f: "health"' and cat.health().needed_ids == (1, 27)
    assert cat.crit_pct().needed_ids == (312, 67, 711, 710)
    assert cat.rate_pct_pair(1000016, 1000018).as2_fields == 'f: "ratepp", s: 1000016, t: 1000018'
    assert sorted(cat.prot_max().needed_ids) == [157, 167, 334, 451, 808, 810, 905, 906, 907, 908,
                                                911, 926, 927, 928, 929]
    assert cat.minigame_wl().needed_ids == (666, 668, 1000026, 667, 669, 1000027)


def test_every_rows_fields_are_a_valid_object_literal_fragment():
    member = r'[a-z]: (?:"[a-z0-9]+"|-?\d+)'
    for r in cat.ROWS:
        assert re.fullmatch(rf'{member}(?:, {member})*', r.as2_fields()), r.key


# --------------------------------------------------------------------------
# The profile's rows
# --------------------------------------------------------------------------


def test_rows_validation():
    def rows(v):
        return validate_config({"rows": v})["rows"]
    assert validate_config({})["rows"] is None
    assert rows("armor") is None, "not a list: the Default sheet"
    assert rows([]) == [], "an empty list is legal: title only"
    assert rows(["armor", 7, "armor", "season_kd"]) == ["armor", "pvp_kills", "pvp_deaths"]
    assert rows(["s448", "nope"]) is None, "named keys and kept none: Default, not empty"
    assert rows([7, None]) == []
    assert list(validate_config({}))[-1] == "rows", "written last"


# --------------------------------------------------------------------------
# The bake
# --------------------------------------------------------------------------


def _data(rows):
    gen = CodeGenerator([], BuffDatabase(), "0.0.0",
                        inspect_config={"enabled": True, "rows": rows})
    return gen.generate()[1]


def test_five_rows_bake_to_the_pinned_text():
    expected = (
        '\n        d.INS.groups = [{n: "Vitals", p: false}, {n: "Defensive", p: false}, '
        '{n: "PvP Stats", p: true}];\n        d.INS.rows = [\n'
        '            {g: 0, l: "Max HP", f: "raw", s: 1},\n'
        '            {g: 0, l: "Health Tap Phys", f: "tap", s: 894, d: 1, t: 477, u: 227},\n'
        '            {g: 1, l: "Armor", f: "armor", p: 0},\n'
        '            {g: 1, l: "Holy Prot", f: "prot", s: 928, t: 810, i: 907, p: 0},\n'
        '            {g: 2, l: "Kills", f: "pair", s: 1382, t: 656}\n        ];\n'
        '        d.INS.watch = [1, 54, 67, 70, 227, 334, 448, 450, 451, 477, 656, 804, 808, 810, '
        '814, 894, 902, 907, 911, 928, 1382];')
    assert expected in _data(["s1", "armor", "prot_holy", "tap_phys", "pvp_kills"])


def test_an_empty_list_bakes_empty_arrays_and_the_always_ids():
    assert ('\n        d.INS.groups = [];\n        d.INS.rows = [];\n'
            '        d.INS.watch = [1, 54, 67, 70, 804, 808, 810, 814];') in _data([])


def test_no_rows_bakes_the_default_sheet():
    data = _data(None)
    assert 'd.INS.groups = [{n: "Summary", p: false}];' in data
    assert data.count(", z: 1}") == 12


def test_the_pvp_view_bakes_its_sections_columns_and_ids():
    data = _data(None)
    block = next(line for line in data.splitlines() if "d.INS.pvp = " in line)
    assert block.startswith('        d.INS.pvp = {groups: [{n: "PvP Combat Stats", c: ["Rating", "Effect"]}, '
                            '{n: "Protection", c: ["Score", "Mitigation"]}, '
                            '{n: "Bonus Spell Damage", c: ["Damage"]}, {n: "Record", c: []}], '
                            'rows: [{g: 0, l: "Evade Chance", f: "chance"')
    assert '{g: 1, l: "Electrical", f: "prot", s: 927, t: 808, i: 906, p: 1}' in block
    assert '{g: 2, l: "Holy", f: "spell", p: 1, s: 878}' in block
    assert '{g: 3, l: "Overall K/D", f: "pair", s: 656, t: 658}, {g: 3, l: "Minigame W/L", f: "wl"}]' in block
    ids = [int(i) for i in block.split("ids: [")[1].rstrip("]};").split(", ")]
    assert ids == cat.watch_ids(cat.pvp_rows())
    for i in (225, 226, 309, 311, 1100, 454, 458, 656, 658, 666, 1000027):
        assert i in ids


# --------------------------------------------------------------------------
# The picker's edits and the height estimate
# --------------------------------------------------------------------------


def test_search_matches_label_key_group_and_ids():
    kills = cat.find("pvp_kills")
    assert cat.matches(kills, "1382") and cat.matches(kills, "kil") and cat.matches(kills, "pvp stats")
    assert not cat.matches(kills, "138")
    assert cat.matches(kills, "  ")


def test_add_puts_a_row_last_in_its_section_and_move_stays_inside_it():
    assert cat.add_keys(["s1", "armor"], ["health", "sum_hate"]) == ["sum_hate", "s1", "health", "armor"]
    active = ["sum_health", "sum_armor", "s1", "health"]
    assert cat.move_keys(active, ["sum_armor"], -1) == ["sum_armor", "sum_health", "s1", "health"]
    assert cat.move_keys(active, ["sum_armor"], 1) == active, "the section's edge holds"
    assert cat.move_keys(active, ["s1"], -1) == active, "never across sections"
    block = ["s804", "s808", "s806", "s814"]
    assert cat.move_keys(block, ["s808", "s806"], -1) == ["s808", "s806", "s804", "s814"]
    assert cat.move_keys(block, ["s808", "s806"], 1) == ["s804", "s814", "s808", "s806"]


def test_the_height_estimate_matches_the_stub_layout():
    default = cat.shown(None)
    assert cat.panel_height(default, 12) == 359
    assert cat.panel_height([], 12) == 97
    assert cat.pvp_view_height(12) == 556
    assert cat.height_warning(list(cat.ROWS)[:50], 12)
    three = default[:3]
    assert cat.height_warning(three, 24) and not cat.height_warning(three, 12)
    assert not cat.height_warning(default, 12) and cat.height_warning(default, 48)
