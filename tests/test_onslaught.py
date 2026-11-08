"""Tests for `onslaught` — the Onslaught Tracker's catalog, its profile section
(defaults, clamps, the camps, the guards and the custom names, the build gate),
its skull camps — and the `d.ONS` block the build bakes from it.

Run: `pytest tests/test_onslaught.py` (from repo root).
"""

from kazbars import onslaught as ons
from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import CodeGenerator

SHOWS = ("showList", "showAlerts", "showWave", "showAoe", "showAlly")


def _cfg(raw):
    return ons.validate_config(raw)


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------


def test_the_catalog_has_its_35_names_in_seven_groups_and_27_always_watched():
    assert len(ons.ROWS) == 35 and len({r.name for r in ons.ROWS}) == 35
    assert [r.group for r in ons.ROWS] == sorted((r.group for r in ons.ROWS), key=ons.GROUPS.index)
    assert sum(1 for r in ons.ROWS if r.kind != ons.CAMP) == 27
    assert max(len(r.name) for r in ons.ROWS) == ons.NAME_MAX
    assert next(r for r in ons.ROWS if r.name == "Louhi").kind == ons.BOSS
    guards = [r for r in ons.ROWS if r.kind == ons.GUARD]
    assert len(guards) == 2 and all(r.group.endswith(" skull") for r in guards)
    assert [(i.playfield, i.ally, i.aoe) for i in ons.INSTANCES] == [
        (20010, "Valkyrie Hylda", False), (20000, "", True)]


# --------------------------------------------------------------------------
# Section
# --------------------------------------------------------------------------


def test_defaults_from_absent_or_non_object_section():
    for raw in (None, 5, [], "x"):
        c = _cfg(raw)
        assert not c["enabled"] and c["scale"] == 100 and c["alertScale"] == 160
        assert all(c[k] for k in SHOWS)
        assert c["alertSeconds"] == 6 and not c["camps"] and c["custom"] == []
        assert c["guards"] is True


def test_clamps_scale_and_alert_time_and_coerces_truthiness():
    for raw, alert, scale in (
        ({"alertSeconds": 0, "scale": 4}, 3, 40),
        ({"alertSeconds": 99, "scale": 400}, 15, 300),
        ({"alertSeconds": "9", "scale": "120"}, 9, 120),
        ({"alertSeconds": 8.5, "scale": 120.7}, 8, 120),
        ({"alertSeconds": "x", "scale": float("nan")}, 6, 100),
        ({"scale": ""}, 6, 100),
        ({"fontSize": 30}, 6, 100),
    ):
        c = _cfg(raw)
        assert (c["alertSeconds"], c["scale"]) == (alert, scale), raw
    for raw, want in ((4, 40), (400, 300), ("120", 120), (120.7, 120), (float("nan"), 100), ("", 100),
                      (None, 100)):
        assert _cfg({"alertScale": raw})["alertScale"] == want, raw
    c = _cfg({"enabled": 1, "showList": "", "showAoe": []})
    assert c["enabled"] and not c["showList"] and not c["showAoe"] and c["showWave"]


def test_keys_an_older_build_wrote_are_dropped():
    c = _cfg({"enabled": True, "custom": ["Pict Shaman"], "showSkulls": False, "maxRows": 3,
              "fontSize": 20, "watch": ["Louhi"], "testLog": True})
    for key in ("showSkulls", "maxRows", "watch", "fontSize", "testLog"):
        assert key not in c, key
    assert c["custom"] == ["Pict Shaman"] and c["scale"] == 100
    assert "Taskmaster Mijoral" in ons.names_of(c, ons.BOSS), "a picked watch list narrows nothing"
    assert list(c) == ["enabled", "scale", "alertScale", *SHOWS, "alertSeconds", "camps", "guards", "custom"]


def test_the_catalog_is_watched_and_the_camps_only_when_asked():
    def rows(kind):
        return [r.name for r in ons.ROWS if r.kind == kind]
    plain = _cfg({})
    for kind in (ons.BOSS, ons.SKULL, ons.MINI):
        assert ons.names_of(plain, kind) == rows(kind)
    assert ons.names_of(plain, ons.CAMP) == []
    camps = _cfg({"camps": True})
    assert ons.names_of(camps, ons.CAMP) == rows(ons.CAMP)
    assert ons.names_of(camps, ons.BOSS) == rows(ons.BOSS)
    assert _cfg({"camps": 1})["camps"] and not _cfg({"camps": ""})["camps"]


def test_guards_list_apart_only_when_asked():
    guards = ["Gurnakhi Juggernaut", "Ancient Kuthcheman Guardian"]
    apart = _cfg({})
    assert ons.names_of(apart, ons.GUARD) == guards
    assert not set(guards) & set(ons.names_of(apart, ons.SKULL))
    together = _cfg({"guards": False})
    assert ons.names_of(together, ons.GUARD) == []
    assert ons.names_of(together, ons.SKULL) == [r.name for r in ons.ROWS if r.group.endswith(" skull")]
    assert ons.names_of(together, ons.SKULL)[0] == guards[0]


def test_camps_name_each_instance():
    camps = {i.playfield: i.camps for i in ons.INSTANCES}
    assert [c.name for c in camps[20010]] == ["Hub", "Cave", "WCave", "Tower", "Bridge", "Altar"]
    assert [c.name for c in camps[20000]] == [
        "Respad", "South West", "South East", "Temple", "East", "South", "West", "North"]
    assert [sum(len(c.points) for c in camps[pf]) for pf in (20010, 20000)] == [7, 22]
    for camp in (c for cs in camps.values() for c in cs):
        assert camp.r > 0 and len(camp.name) <= 10, camp
        assert all(len(p) == 3 and all(isinstance(v, int) for v in p) for p in camp.points), camp


def test_custom_names_are_trimmed_kept_in_order_and_watched_last_among_the_minis():
    c = _cfg({"custom": ["  Brythunian Thrall ", "Pict Shaman", "Brythunian Thrall", 5, None, "",
                         "   ", "Louhi", "louhi"]})
    assert c["custom"] == ["Brythunian Thrall", "Pict Shaman", "louhi"]
    assert ons.names_of(c, ons.MINI)[-3:] == ["Brythunian Thrall", "Pict Shaman", "louhi"]
    assert not set(c["custom"]) & set(ons.names_of(c, ons.BOSS) + ons.names_of(c, ons.SKULL))
    for raw in ("Pict Shaman", {}, None):
        assert _cfg({"custom": raw})["custom"] == []


def test_custom_names_stop_at_the_length_and_count_caps():
    fits, over = "x" * ons.NAME_MAX, "x" * (ons.NAME_MAX + 1)
    assert _cfg({"custom": [over, fits]})["custom"] == [fits]
    assert ons.custom_refusal("é" * ons.NAME_MAX, []) is None, "characters, not bytes"
    c = _cfg({"custom": [f"Mob {i}" for i in range(ons.CUSTOM_MAX + 3)]})
    assert len(c["custom"]) == ons.CUSTOM_MAX
    assert (c["custom"][0], c["custom"][-1]) == ("Mob 0", "Mob 19")


def test_custom_refusal_names_each_reason():
    held = ["Pict Shaman"]
    assert ons.custom_refusal("Brythunian Thrall", held) is None
    for name, why in (("", "Type"), ("Louhi", "catalog"), ("Pict Shaman", "your list"),
                      ("x" * 28, "long"), ("Pict\0Shaman", "control"), ("Pict\tShaman", "control"),
                      ("Valkyrie Hylda", "ally"), ("XXSpawner", "hidden")):
        assert why in (ons.custom_refusal(name, held) or ""), name
    full = [f"Mob {i}" for i in range(ons.CUSTOM_MAX)]
    assert "full" in ons.custom_refusal("Brythunian Thrall", full)


def test_ships_needs_enabled_and_at_least_one_display():
    def ships(enabled, on):
        return ons.ships(_cfg({"enabled": enabled, **{k: k in on for k in SHOWS}}))
    assert not ships(False, SHOWS)
    assert not ships(True, ())
    assert ships(True, SHOWS)
    assert all(ships(True, (k,)) for k in SHOWS)
    assert not ons.ships(_cfg({"enabled": True, "showSkulls": True,
                               **{k: False for k in SHOWS}})), "the old skull bar is not a display"


# --------------------------------------------------------------------------
# The bake
# --------------------------------------------------------------------------


def _build(section, **kw):
    gen = CodeGenerator([], BuffDatabase(), "0.0.0", onslaught_config=section, **kw)
    return gen.generate()


def _kinds(data):
    lines = data.split("        d.ONS.watch = {\n", 1)[1].split("\n        };", 1)[0]
    return [line.strip().rstrip(",") for line in lines.splitlines()]


def test_no_section_or_a_tracker_that_shows_nothing_bakes_nothing():
    for section in (None, {"enabled": False}, {"enabled": True, **{k: False for k in SHOWS}}):
        main, data = _build(section)
        assert "d.ONS" not in data and "KazBarsOnslaught" not in main, section


def test_the_tracker_bakes_its_block_hooks_and_instances():
    main, data = _build({"enabled": True, "scale": 175})
    assert "onslaught = new KazBarsOnslaught(rootClip);" in main
    assert "onslaught.configure(d.ONS, world, clock);" in main
    assert "modules.push(onslaught);" in main
    assert ("        d.ONS = {x: 1560, y: 300, ax: 960, ay: 200, fontSize: 21, alertFontSize: 19, list: true, "
            "alerts: true, wave: true, aoe: true, ally: true, alertMs: 6000};") in data
    assert '"Zug-Touched Scorpion"' not in data, "no camps without camps"
    assert ('        d.ONS.helpers = ["Thugra Khotan"];\n        d.ONS.heal = ["Healing Radiance"];\n'
            '        d.ONS.shield = ["Ancient Ward"];\n'
            '        d.ONS.pf = {};') in data
    assert ('        d.ONS.pf[20010] = {start: "talk to Hylda", spawnMs: 200000, '
            'ally: "Valkyrie Hylda", aoe: false, camps: [{n: "Hub", r: 20, p: [185, 50, 76]}, '
            '{n: "Cave", r: 20, p: [283, 35, 137]}, {n: "WCave", r: 19, p: [181, 30, 145, 222, 25, 173]}, '
            '{n: "Tower", r: 20, p: [57, 33, 230]}, {n: "Bridge", r: 20, p: [34, 39, 281]}, '
            '{n: "Altar", r: 20, p: [104, 36, 140]}]};') in data
    assert ('        d.ONS.pf[20000] = {start: "click the banner", spawnMs: 200000, ally: "", aoe: true, '
            'camps: [{n: "Respad", r: 10, p: [283, 111, 133]}, '
            '{n: "South West", r: 5, p: [128, 104, 225, 160, 106, 174]}, ') in data
    assert data.index("d.ONS = ") < data.index("d.ONS.watch")


def test_the_watch_table_holds_only_what_a_display_reads():
    def quoted(kind, section):
        return ", ".join(f'"{n}"' for n in ons.names_of(ons.validate_config(section), kind))
    every = {"camps": True}
    b, s, g, m, c = (f"{k}: [{quoted(k, every)}]"
                     for k in (ons.BOSS, ons.SKULL, ons.GUARD, ons.MINI, ons.CAMP))
    assert g != "g: []"
    alerts = {"enabled": True, "camps": True, **{k: k == "showAlerts" for k in SHOWS}}
    assert _kinds(_build(alerts)[1]) == [b, s, g, m, "c: []"], "a camp never alerts"
    assert "camps: []}" in _build(alerts)[1], "only the list reads a skull's camp"
    listed = {"enabled": True, "camps": True, **{k: k == "showList" for k in SHOWS}}
    assert _kinds(_build(listed)[1]) == [b, s, g, m, c]
    wave = {"enabled": True, "camps": True, **{k: k == "showWave" for k in SHOWS}}
    assert _kinds(_build(wave)[1]) == ["b: []", "s: []", "g: []", "m: []", "c: []"]
    together = {**listed, "guards": False}
    assert _kinds(_build(together)[1]) == [b, f"s: [{quoted(ons.SKULL, together)}]", "g: []", m, c]
    assert '"Gurnakhi Juggernaut"' in _kinds(_build(together)[1])[1]
    for guards in (True, False):
        kinds = _kinds(_build({"enabled": True, "guards": guards})[1])
        assert sum(line.count('"') // 2 for line in kinds) == 27, guards


def test_custom_names_bake_last_among_the_minis_escaped():
    _, data = _build({"enabled": True, "custom": ['Pict "Shaman"']})
    assert _kinds(data)[3].endswith('"Kushite Firedancer", "Pict \\"Shaman\\""]')


def test_the_spots_follow_the_build_resolution():
    _, data = _build({"enabled": True}, game_resolution=(2560, 1440))
    assert "d.ONS = {x: 2080, y: 400, ax: 1280, ay: 267, fontSize: 12," in data
