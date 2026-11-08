"""
Tests for `grids_generator.CodeGenerator` — the AS2 text a build bakes.

Covers which grids ship, one grid's unit (sizes from the overlay model, timer
style, Applied by me, its id set as `[id, fact code, …]` pairs), the fact codes
themselves (type, stack level, stacking family), the data blocks (`d.PF`,
`d.CAST`, `d.SW`, `d.INS`), the template's feature gates, the module registry
and preview-panel rows, archive keys, inert refs, and the data-class chunking.
No compiler runs here (test_build_compile does that).

Run: `pytest tests/test_grids_generator.py` (from repo root).
"""

import re

import pytest

from kazbars.buff_database import BuffDatabase
from kazbars.grid_model import create_default_grid, validate_grid
from kazbars.grids_generator import (
    DATA_CHUNK_BUDGET,
    CodeGenerator,
    _apply_feature_gates,
    _pack_units,
    escape_as2_string,
    fact_code,
    grid_ships,
    sanitize_id,
    unresolved_refs,
)
from kazbars.paths import KAZBARS_ASSETS

# Tome of Epithur (Necro): a plain buff, ids 222609 + 222610.
BUFF = 222609
# Ethereal Lash 1-4: a stacking debuff, ids 4281285, 4281287, 4281288, 4281289.
LASH = 4281285


def _grid(**kw):
    """A validated dynamic player grid tracking BUFF (so it ships)."""
    return validate_grid({**create_default_grid(grid_id="G", rows=1, cols=2),
                          "whitelist": [BUFF], **kw})


_DB = None


def _db():
    global _DB
    if _DB is None:
        _DB = BuffDatabase()
        _DB.load_layers(KAZBARS_ASSETS / "Database.json")
    return _DB


def _gen(grids=None, **kw):
    return CodeGenerator([_grid()] if grids is None else grids, _db(), "0.0.0", **kw)


def _num(text, name):
    return int(re.search(rf"\b{name}: (-?\d+)", text).group(1))


def _block(text, name):
    return next(line.strip() for line in text.splitlines()
                if line.strip().startswith(f"d.{name} = {{"))


def _codes(data, vid="G_0"):
    line = re.search(rf"var {vid}_ids:Array = \[([^\]]*)\];", data).group(1)
    nums = [int(n) for n in line.split(", ")]
    return list(zip(nums[0::2], nums[1::2]))


# --------------------------------------------------------------------------
# Escaping and positions
# --------------------------------------------------------------------------


def test_escape_as2_string_escapes_quotes_newlines_backslashes():
    assert escape_as2_string("plain") == "plain"
    assert escape_as2_string('a"b') == 'a\\"b'
    assert escape_as2_string("a\\b") == "a\\\\b"
    assert escape_as2_string("a\nb") == "a\\nb"
    assert escape_as2_string("a\rb") == "a\\rb"


def test_grid_id_with_quote_is_escaped_in_output():
    main, data = _gen([_grid(id='My"Grid')]).generate()
    assert 'My\\"Grid' in main + data
    assert 'My"Grid' not in main + data


def test_grid_id_with_newline_does_not_inject():
    main, data = _gen([_grid(id="X\ninjected")]).generate()
    assert "X\\ninjected" in main + data
    assert "X\ninjected" not in main + data


def test_positions_project_to_the_build_resolution():
    grid = _grid(fx=0.5, fy=0.85)
    _, data_1080 = _gen([grid], game_resolution=(1920, 1080)).generate()
    assert "x: 960," in data_1080 and "y: 918," in data_1080
    _, data_4k = _gen([grid], game_resolution=(3840, 2160)).generate()
    assert "x: 1920," in data_4k and "y: 1836," in data_4k


def test_positions_default_resolution_when_none_given():
    _, data = _gen([_grid(fx=1.0, fy=1.0)]).generate()
    assert "x: 1920," in data and "y: 1080," in data


# --------------------------------------------------------------------------
# Which grids ship
# --------------------------------------------------------------------------


def test_only_grids_that_track_something_ship():
    assert grid_ships(_grid())
    assert not grid_ships(_grid(enabled=False))
    assert not grid_ships(_grid(whitelist=[]))
    static = dict(_grid(), slotMode="static", whitelist=[])
    assert not grid_ships(static)
    assert grid_ships(dict(static, slotAssignments={"1": [BUFF]}))
    assert not grid_ships(dict(static, slotAssignments={"2": [BUFF]})), "outside the 1x2 shape"
    assert not grid_ships(dict(static, slotAssignments={"0": []}))
    assert not grid_ships(dict(static, slotAssignments={"x": [BUFF]}))


def test_an_empty_grid_is_left_out_as_it_is_and_the_header_counts_what_ships():
    empty = _grid(id="Empty", whitelist=[])
    gen = _gen([_grid(), empty])
    main, data = gen.generate()
    assert "// Grids: 1" in data
    assert '"Empty"' not in data
    assert empty["enabled"] is True, "never turned off"


# --------------------------------------------------------------------------
# One grid's unit
# --------------------------------------------------------------------------


def test_the_default_size_bakes_a_44px_grid_12pt_timer_and_12pt_stack():
    _, data = _gen().generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (44, 12, 12)


def test_the_base_size_and_the_grid_scale_pick_the_tables_row_held_to_32_92_px():
    _, data = _gen([_grid(scale=150)], overlay={"size": 12}).generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (72, 20, 18)
    _, data = _gen([_grid(scale=150)], overlay={"size": 17}).generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (92, 24, 22)
    _, data = _gen([_grid(scale=50)], overlay={"size": 10}).generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (32, 10, 10)


def test_a_set_text_size_bakes_as_typed_and_auto_follows_the_rules():
    _, data = _gen([_grid(timerPt=20, stackPt=9)], overlay={"size": 17}).generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (68, 20, 9)
    _, data = _gen([_grid(scale=50, timerPt=40)], overlay={"size": 10}).generate()
    assert (_num(data, "iconSize"), _num(data, "timerFont"), _num(data, "stackFont")) == (32, 40, 10), \
        "no fit cap on a size the grid sets"
    _, data = _gen([_grid(stackPt=14)]).generate()
    assert (_num(data, "timerFont"), _num(data, "stackFont")) == (12, 14)


def test_a_base_size_that_is_not_a_choice_bakes_as_the_default():
    _, data = _gen(overlay={"size": 24, "font": "Comic Sans"}).generate()
    assert _num(data, "iconSize") == 44
    assert 'face: "Arial"' in data


def test_the_unit_keeps_its_key_order():
    _, data = _gen().generate()
    order = ["id", "key", "type", "rows", "cols", "iconSize", "gap", "x", "y", "slotMode",
             "fillDir", "sortOrder", "layout", "timerStyle", "timerFont",
             "timerFlashThreshold", "timerYOffset", "stackFont", "enableFlashing"]
    positions = [data.index(f"            {k}: ") for k in order]
    assert positions == sorted(positions)
    assert "showTimers" not in data


def test_the_timer_style_is_baked_where_show_timers_was():
    _, data = _gen([_grid(timerStyle="bar")]).generate()
    assert '            layout: "buffFirst",\n            timerStyle: "bar",\n            timerFont: ' in data


def test_applied_by_me_is_baked_last_and_only_when_true():
    _, plain = _gen().generate()
    assert "selfCastOnly" not in plain
    _, dynamic = _gen([_grid(selfCastOnly=True)]).generate()
    assert "            enableFlashing: true,\n            selfCastOnly: true\n        };" in dynamic
    static = dict(_grid(selfCastOnly=True), slotMode="static", slotAssignments={"0": [BUFF]})
    _, fixed = _gen([static]).generate()
    assert ("            enableFlashing: true,\n            selfCastOnly: true,\n"
            "            slots: {}\n        };") in fixed


def test_a_dynamic_grid_bakes_its_id_set_as_pairs_read_by_a_loop():
    _, data = _gen().generate()
    assert '\n        d.WL["G"] = {};' in data
    assert _codes(data) == [(222609, 1), (222610, 1)]
    assert 'd.WL["G"][G_0_ids[i]] = G_0_ids[i + 1];\n            i += 2;' in data
    assert "d.ISDEB" not in data and "d.BUFFTYPE" not in data and "d.STACK_LEVEL" not in data


def test_a_static_grid_bakes_its_slots_and_every_slot_id_in_its_set():
    grid = dict(_grid(), slotMode="static", rows=1, cols=2, whitelist=[],
                slotAssignments={"0": [BUFF], "1": LASH})
    _, data = _gen([grid]).generate()
    assert "G_0.slots[0] = [222609, 222610];" in data
    assert "G_0.slots[1] = [4281285, 4281287, 4281288, 4281289];" in data
    assert [bid for bid, _ in _codes(data)] == [222609, 222610, 4281285, 4281287, 4281288, 4281289]


# --------------------------------------------------------------------------
# Fact codes
# --------------------------------------------------------------------------


def test_fact_code_packs_type_level_and_family():
    assert fact_code("buff", None) == 1
    assert fact_code("debuff", None) == 2
    assert fact_code("misc", None) == 3
    assert fact_code("whatever", None) == 1
    assert fact_code("debuff", (3, 1)) == 2 | 3 << 2 | 1 << 12
    assert fact_code("buff", (5000, 2)) == 1 | 1023 << 2 | 2 << 12, "the level caps at 1023"
    assert fact_code("buff", (-4, 0)) == 1


def test_every_level_of_a_stacking_entry_carries_one_family_and_its_own_level():
    _, data = _gen([_grid(whitelist=[LASH])]).generate()
    got = [(bid, code >> 2 & 1023, code >> 12, code & 3) for bid, code in _codes(data)]
    assert got == [(4281285, 1, 1, 2), (4281287, 2, 1, 2), (4281288, 3, 1, 2), (4281289, 4, 1, 2)]


def test_an_id_that_does_not_stack_carries_no_level_and_no_family():
    _, data = _gen().generate()
    assert all(code >> 2 == 0 and code & 3 > 0 for _, code in _codes(data))


def test_families_are_numbered_by_their_lowest_id_in_the_grid():
    db = BuffDatabase()
    db.buffs = [
        {"name": "High", "ids": [900, 901], "type": "buff", "stacking": True},
        {"name": "Low", "ids": [100, 101], "type": "debuff", "stacking": True},
        {"name": "Plain", "ids": [500], "type": "misc"},
    ]
    db._rebuild_indexes()
    grid = _grid(whitelist=[900, 100, 500])
    _, data = CodeGenerator([grid], db, "0.0.0").generate()
    families = {bid: code >> 12 for bid, code in _codes(data)}
    assert families == {100: 1, 101: 1, 500: 0, 900: 2, 901: 2}


def test_stack_labels_are_per_grid():
    # Two grids on one stacking entry: each numbers its own families from 1.
    grids = [_grid(id="A", whitelist=[BUFF, LASH]), _grid(id="B", whitelist=[LASH])]
    _, data = _gen(grids).generate()
    assert {code >> 12 for _, code in _codes(data, "A_0")} == {0, 1}
    assert {code >> 12 for _, code in _codes(data, "B_1")} == {1}


def test_custom_icons_follow_the_grids_once_each():
    grids = [_grid(id="A", whitelist=[5077953]), _grid(id="B", whitelist=[5077953])]
    _, data = _gen(grids).generate()
    assert data.count('d.CUSTOMICON[5077953] = "IcoSlow30";') == 1
    assert data.index("d.CUSTOMICON[5077953]") > data.rindex("d.CFG.grids.push(")


# --------------------------------------------------------------------------
# Data blocks
# --------------------------------------------------------------------------


def test_the_panel_block_carries_base_size_face_version_and_anchor():
    main, data = _gen().generate()
    assert _block(data, "PF") == 'd.PF = {fontSize: 12, face: "Arial", version: "0.0.0", side: 389, up: -13};'
    assert "ppanel.configure(d.PF);" in main
    _, data = _gen(overlay={"size": 16, "font": "Verdana"}, anchor=(-40, 120)).generate()
    assert _block(data, "PF") == ('d.PF = {fontSize: 18, face: "_StandardFont", version: "0.0.0", '
                                  'side: -40, up: 120};')
    _, data = _gen(overlay={"size": 12, "font": "Roboto"}).generate()
    assert 'face: "Arial"' in _block(data, "PF"), "a baked face is spliced in as Arial"


def _cast_cfg(**kw):
    return dict({"enabled": True, "enableP": True, "enableT": True,
                 "playerFx": 900 / 1920, "playerFy": 600 / 1080,
                 "targetFx": 900 / 1920, "targetFy": 560 / 1080,
                 "bold": True, "display": "both", "color": "FF8800"}, **kw)


def test_cast_off_emits_no_cast_refs():
    gen = _gen(cast_config=None)
    main, data = gen.generate()
    assert not gen.include_cast_timer
    assert "KazBarsCastTimer" not in main and "castTimer" not in main
    assert "d.CAST" not in data
    assert not _gen(cast_config={"enabled": False, "enableP": True}).include_cast_timer
    assert not _gen(cast_config={"enabled": True}).include_cast_timer


def test_cast_on_emits_hooks_and_data():
    gen = _gen(cast_config=_cast_cfg())
    main, data = gen.generate()
    assert "castTimer = new KazBarsCastTimer(rootClip);" in main
    assert "castTimer.configure(d.CAST, world, clock);" in main
    assert "modules.push(castTimer);" in main
    assert _block(data, "CAST") == (
        "d.CAST = {enableP: true, enableT: true, playerX: 900, playerY: 600, "
        "targetX: 900, targetY: 560, bold: true, fontSize: 12, display: \"both\", "
        "color: 0xFF8800};")


def test_the_cast_timer_takes_the_panel_size():
    _, data = _gen(cast_config=_cast_cfg(scale=50), overlay={"size": 17}).generate()
    assert _num(_block(data, "CAST"), "fontSize") == 9


def test_stopwatch_off_emits_no_refs():
    gen = _gen(stopwatch_config=None)
    main, data = gen.generate()
    assert not gen.include_stopwatch
    assert "KazBarsStopwatch" not in main and "stopwatch" not in main
    assert "d.SW" not in data


def test_stopwatch_on_emits_hooks_and_data():
    gen = _gen(stopwatch_config={"enabled": True, "fx": 750 / 1920, "fy": 410 / 1080,
                                 "scale": 150})
    main, data = gen.generate()
    assert "stopwatch = new KazBarsStopwatch(rootClip);" in main
    assert "stopwatch.configure(d.SW);" in main
    assert "modules.push(stopwatch);" in main
    assert _block(data, "SW") == "d.SW = {x: 750, y: 410, fontSize: 18};"


def test_extras_positions_project_to_the_build_resolution():
    gen = _gen(stopwatch_config={"enabled": True, "fx": 0.5, "fy": 0.5},
               game_resolution=(2560, 1440))
    _, data = gen.generate()
    assert "d.SW = {x: 1280, y: 720," in data


def test_inspect_off_emits_no_refs():
    gen = _gen(inspect_config=None)
    main, data = gen.generate()
    assert not gen.include_inspect
    assert "KazBarsInspect" not in main and "inspect" not in main
    assert "d.INS" not in data


def test_inspect_on_emits_hooks_and_data():
    gen = _gen(inspect_config={"enabled": True, "fx": 40 / 1920, "fy": 240 / 1080,
                               "scale": 50})
    main, data = gen.generate()
    assert "inspect = new KazBarsInspect(rootClip);" in main
    assert "inspect.configure(d.INS, world, clock);" in main
    assert "modules.push(inspect);" in main
    assert _block(data, "INS").startswith("d.INS = {x: 40, y: 240, fontSize: 8};")


# --------------------------------------------------------------------------
# Template gates, registry, preview panel
# --------------------------------------------------------------------------


def test_feature_gates_strip_markers_and_refuse_template_bugs():
    template = "a\n//#if X  // why\nb\n//#end\nc"
    assert _apply_feature_gates(template, {"X": True}) == "a\nb\nc"
    assert _apply_feature_gates(template, {"X": False}) == "a\nc"
    for bad, flags in (("//#if Y\n//#end", {"X": True}),
                       ("//#if X\n//#if X\n//#end", {"X": True}),
                       ("//#end", {}),
                       ("//#if X\n", {"X": True})):
        with pytest.raises(ValueError):
            _apply_feature_gates(bad, flags)


def test_every_template_flag_is_one_the_generator_sets():
    template = (KAZBARS_ASSETS / "KazBars.as.template").read_text(encoding="utf-8")
    used = set(re.findall(r"^//#if (\w+)", template, re.M))
    assert used == {"CONSOLE", "CONBUFFS", "CONCASTS", "CAST", "INS", "ONS", "PLATE", "SW"}


def test_with_nothing_on_no_module_stub_is_named():
    main, _ = _gen().generate()
    assert main.count("modules.push(") == 1
    assert "modules.push(grids);" in main
    assert "ppanel.addExtra(" not in main
    for stub in ("KazBarsConsole", "KazBarsCastTimer", "KazBarsStopwatch", "KazBarsInspect",
                 "KazBarsOnslaught", "KazBarsOverhead", "KazBarsConBuffs", "KazBarsConCasts"):
        assert stub not in main, stub


def test_module_registry_emits_every_lifecycle_call_once():
    main, _ = _gen().generate()
    for call in ("m.create();", "m.previewOn();", "m.previewOff();",
                 "m.cleanup();", "m.loadState(config);", "m.saveState(config);"):
        assert main.count(call) == 1, call


def test_preview_keys_are_distinct():
    keys = {}
    for stub in sorted((KAZBARS_ASSETS / "stubs").glob("*.as")):
        m = re.search(r'previewKey\(\):String \{ return "(\w+)"; \}',
                      stub.read_text(encoding="utf-8"))
        if m:
            keys[stub.name] = m.group(1)
    assert set(keys) == {"KazBarsCastTimer.as", "KazBarsConsole.as", "KazBarsInspect.as",
                         "KazBarsOnslaught.as", "KazBarsStopwatch.as"}, keys
    assert len(set(keys.values())) == len(keys), keys
    assert "onsa" not in keys.values(), "the onslaught alerts' row key is no module's"


def test_preview_panel_rows_follow_the_tools_order_not_the_z_order():
    gen = _gen(cast_config=_cast_cfg(),
               stopwatch_config={"enabled": True},
               inspect_config={"enabled": True})
    main, _ = gen.generate()
    rows = [f"ppanel.addExtra({m}.previewLabel(), {m}.previewKey(), {m}.isActive());"
            for m in ("castTimer", "inspect", "stopwatch")]
    idxs = [main.index(row) for row in rows]
    assert idxs == sorted(idxs)
    assert (main.index("modules.push(grids);") < main.index("modules.push(inspect);")
            < main.index("modules.push(castTimer);") < main.index("modules.push(stopwatch);"))
    assert main.index("ppanel.addExtra(") < main.index("ppanel.show();")
    assert "if (m.previewKey() == key) m.setActive(shown);" in main


def test_the_onslaught_alerts_get_their_own_row_under_the_tracker():
    main, _ = _gen(onslaught_config={"enabled": True}).generate()
    board = "ppanel.addExtra(onslaught.previewLabel(), onslaught.previewKey(), onslaught.isActive());"
    alerts = 'ppanel.addExtra("Onslaught Alerts", "onsa", onslaught.alertsShown());'
    assert main.index(board) < main.index(alerts) < main.index("ppanel.show();")
    toggle = main.split("public function previewToggle", 1)[1]
    assert toggle.index('if (key == "onsa") {') < toggle.index("onslaught.setAlerts(shown);")         < toggle.index("while (mi < modules.length)")
    main, _ = _gen().generate()
    assert "onsa" not in main and "setAlerts" not in main


def test_stub_archive_keys_present():
    stubs = KAZBARS_ASSETS / "stubs"
    for name, key in (("KazBarsStopwatch.as", "swv"), ("KazBarsInspect.as", "inv"),
                      ("KazBarsCastTimer.as", "ctv"), ("KazBarsConsole.as", "cnv"),
                      ("KazBarsOnslaught.as", "onv"), ("KazBarsOnslaught.as", "onav")):
        src = (stubs / name).read_text(encoding="utf-8")
        assert f'FindEntry("{key}")' in src, f"{name} never reads {key}"
        assert f'ReplaceEntry("{key}"' in src, f"{name} never writes {key}"


# --------------------------------------------------------------------------
# Archive keys
# --------------------------------------------------------------------------


def test_sanitize_id_folds_non_ascii_to_a_valid_as2_identifier():
    safe = sanitize_id("Grid ünïcodé 日本")
    assert safe.isascii() and safe.isidentifier()
    assert sanitize_id("") == "Grid"
    assert sanitize_id("3x3") == "_3x3"


def test_archive_key_dedupes_grids_that_sanitize_the_same():
    _, data = _gen([_grid(id="a-b"), _grid(id="a b")]).generate()
    assert 'key: "a_b"' in data
    assert 'key: "a_b_2"' in data


def test_archive_key_holds_when_an_earlier_grid_is_left_out():
    _, data = _gen([_grid(id="a-b", whitelist=[]), _grid(id="a b")]).generate()
    assert 'key: "a_b_2"' in data
    assert 'key: "a_b"' not in data


# --------------------------------------------------------------------------
# Inert refs
# --------------------------------------------------------------------------


def test_a_bare_scalar_slot_assignment_resolves_like_a_list():
    grid = dict(_grid(), slotMode="static", slotAssignments={"0": BUFF})
    _, data = _gen([grid]).generate()
    assert "G_0.slots[0] = [222609, 222610];" in data


def test_a_slot_past_the_shape_is_not_built():
    grid = dict(_grid(), slotMode="static", slotAssignments={"0": [BUFF], "5": [LASH]})
    _, data = _gen([grid]).generate()
    assert "G_0.slots[5]" not in data
    assert str(LASH) not in data


def test_a_dynamic_grid_ignores_its_old_slots():
    grid = dict(_grid(), slotAssignments={"0": [LASH]})
    _, data = _gen([grid]).generate()
    assert str(LASH) not in data
    assert unresolved_refs([dict(grid, slotAssignments={"0": [99999901]})], _db()) == []


def test_a_malformed_slot_value_is_skipped_not_raised():
    grid = dict(_grid(), slotMode="static",
                slotAssignments={"0": {"nested": "object"}, "1": [BUFF]})
    _, data = _gen([grid]).generate()
    assert "G_0.slots[0]" not in data
    assert "G_0.slots[1] = [222609, 222610];" in data


def test_unresolved_refs_counts_unknown_ids_and_names_once():
    grids = [
        _grid(whitelist=[BUFF, 99999901, "Ghost Buff"]),
        dict(_grid(id="G2"), slotMode="static",
             slotAssignments={"0": [99999901], "1": "Ghost Buff", "2": []}),
    ]
    assert unresolved_refs(grids, _db()) == [99999901, "Ghost Buff"]
    assert unresolved_refs([_grid(enabled=False, whitelist=[99999901])], _db()) == []
    assert unresolved_refs([_grid()], _db()) == []


def test_unknown_refs_are_skipped_at_emit_not_crashed_on():
    main, data = _gen([_grid(whitelist=[BUFF, 99999901, "Ghost Buff"])]).generate()
    assert "99999901" not in main + data
    assert "Ghost Buff" not in main + data


# ============================================================================
# DATA CLASS CHUNKING
# ============================================================================
# as2c caps every class at 32 KB of bytecode, so the grid configs and custom
# icons are packed into KazBarsData1..N under DATA_CHUNK_BUDGET chars each.
# test_build_compile pins the cap itself; these pin the packing and the shape.


def _big_setup(n_ids=1200, n_grids=12):
    """A synthetic catalog of `n_ids` seven-digit ids spread over `n_grids`
    dynamic grids, plus one static grid on a stacking entry — several chunks'
    worth of data."""
    db = BuffDatabase()
    db.buffs = [
        {"name": f"Buff {n}", "ids": [5_000_000 + n], "category": "T", "type": "buff"}
        for n in range(n_ids)
    ]
    db.buffs.append({"name": "Stacks 1-3", "ids": [6_000_001, 6_000_002, 6_000_003],
                     "category": "T", "type": "debuff", "stacking": True})
    db._rebuild_indexes()
    per = n_ids // n_grids
    grids = [
        _grid(id=f"Grid {k}", whitelist=[5_000_000 + n for n in range(k * per, (k + 1) * per)])
        for k in range(n_grids)
    ]
    grids.append(dict(_grid(id="Static"), slotMode="static", whitelist=[],
                      slotAssignments={"0": [6_000_001]}))
    return grids, db


def test_pack_units_keeps_joined_chunks_within_budget_and_oversize_alone():
    units = ["a" * 10, "b" * 10, "c" * 5, "d" * 30, "e"]
    chunks = _pack_units(units, 24)
    assert chunks == [["a" * 10, "b" * 10], ["c" * 5], ["d" * 30], ["e"]]
    assert all(len("\n".join(c)) <= 24 for c in chunks if c != ["d" * 30])
    assert _pack_units([], 24) == []


def test_generate_files_splits_a_large_profile_into_consecutive_data_classes():
    grids, db = _big_setup()
    gen = CodeGenerator(grids, db, "0.0.0")
    files = gen.generate_files()
    n = len(files) - 2
    assert n >= 2
    assert [name for name, _ in files] == (
        ["KazBars.as", "KazBarsData.as"] + [f"KazBarsData{k}.as" for k in range(1, n + 1)])
    assert re.findall(r"KazBarsData(\d+)\.fill\(d\);", files[1][1]) == [
        str(k) for k in range(1, n + 1)]
    longest = max(len(u) for u in gen._data_units())
    for name, src in files[2:]:
        assert f"class {name[:-3]} {{" in src
        body = src.split("        var i:Number;\n", 1)[1].rsplit("\n    }\n}", 1)[0]
        assert len(body) <= max(DATA_CHUNK_BUDGET, longest)


def test_chunked_data_keeps_grid_order_and_each_grid_its_own_set():
    grids, db = _big_setup()
    _, data = CodeGenerator(grids, db, "0.0.0").generate()
    assert re.findall(r"d\.CFG\.grids\.push\((\w+)\);", data) == (
        [f"Grid_{k}_{k}" for k in range(12)] + ["Static_12"])
    assert "Static_12.slots[0] = [6000001, 6000002, 6000003];" in data
    levels = [(bid, code >> 2 & 1023) for bid, code in _codes(data, "Static_12")]
    assert levels == [(6000001, 1), (6000002, 2), (6000003, 3)]
    assert sum(len(_codes(data, f"Grid_{k}_{k}")) for k in range(12)) == 1200
    assert data.count("class KazBarsData") == data.count(".fill(d);") + 1


def test_generate_files_is_three_files_for_a_small_profile_and_two_for_none():
    small = _gen().generate_files()
    assert [name for name, _ in small] == ["KazBars.as", "KazBarsData.as", "KazBarsData1.as"]
    assert "KazBarsData1.fill(d);" in small[1][1]
    empty = _gen([]).generate_files()
    assert [name for name, _ in empty] == ["KazBars.as", "KazBarsData.as"]
    assert ".fill(" not in empty[1][1]
    assert "return d;" in empty[1][1]


# --------------------------------------------------------------------------
# Overhead grids and bands
# --------------------------------------------------------------------------


def test_a_band_bakes_its_derived_shape_centred_fill_and_slots_last():
    grids = [
        _grid(id="Band", type="hostile", rowCap=3, maxSlots=7),
        dict(_grid(id="Box", type="hostile", rows=1, cols=2, slotMode="static", whitelist=[]),
             slotAssignments={"0": BUFF}),
        _grid(id="Screen"),
    ]
    main, data = _gen(grids).generate()
    assert ('            id: "Band",\n            key: "Band",\n            type: "hostile",\n'
            '            rows: 3,\n            cols: 3,') in data
    assert '            fillDir: "C",' in data
    assert "            maxDistance: 40,\n            maxSlots: 7\n        };" in data
    assert data.index("// Box\n") < data.index("// Screen\n") < data.index("// Band\n")
    assert "maxSlots: 2" not in data, "a box bakes no maxSlots"


def test_an_overhead_grid_turns_the_gate_on_and_bakes_its_keys():
    plate = _grid(id="P", type="hostile", rows=1, cols=4, plateOffset=90, maxDistance=30)
    main, data = _gen([_grid(), plate]).generate()
    assert "overhead = new KazBarsOverhead(rootClip);" in main
    assert "overhead.configure(d, world, clock);" in main
    assert "modules.push(overhead);" in main
    assert ("            enableFlashing: true,\n            plateOffset: 90,\n"
            "            maxDistance: 30,\n            maxSlots: 4\n        };") in data
    assert "showSelf" not in data


def test_a_friendly_grid_bakes_over_me():
    plate = _grid(id="F", type="friendly", rows=1, cols=4, maxDistance=30, showSelf=False)
    _, data = _gen([plate]).generate()
    assert "            maxDistance: 30,\n            maxSlots: 4,\n            showSelf: false\n        };" in data


def test_a_build_without_overhead_grids_never_names_the_classes():
    main, data = _gen().generate()
    assert "KazBarsOverhead" not in main
    assert "plateOffset" not in data
