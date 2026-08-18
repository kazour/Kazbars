"""
Tests for `grids_generator.CodeGenerator` — the optional buff-discovery
console toggle (`include_console`).

When `include_console=False` the generated AS2 must contain no `console`
references and no `KazBarsConsole` references — otherwise MTASC would
fail to resolve the missing class.

When `include_console=True` the generator must emit the original console
hooks: instantiation in the constructor, the two log calls in
SlotPBuffAdd / SlotTBuffAdd, plus the preview-mode wiring.

Run: `pytest tests/test_grids_generator.py` (from repo root).
"""

from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import CodeGenerator, escape_as2_string
from kazbars.paths import KAZBARS_ASSETS


def _minimal_grid():
    return {
        "id": "TestGrid",
        "enabled": True,
        "type": "player",
        "rows": 1,
        "cols": 1,
        "iconSize": 32,
        "gap": 0,
        "fx": 0.0,
        "fy": 0.0,
        "slotMode": "dynamic",
        "showTimers": False,
        "timerFontSize": 12,
        "timerFlashThreshold": 5,
        "timerYOffset": 0,
        "stackFontSize": 10,
        "enableFlashing": False,
        "fillDirection": "LR",
        "sortOrder": "longest",
        "layout": "buffFirst",
        "whitelist": [],
    }


def _load_db():
    db = BuffDatabase()
    db_path = KAZBARS_ASSETS / "Database.json"
    if db_path.exists():
        db.load(db_path)
    else:
        db.buffs = []
        db._rebuild_indexes()
    return db


def test_escape_as2_string_escapes_quotes_newlines_backslashes():
    assert escape_as2_string("plain") == "plain"
    assert escape_as2_string('a"b') == 'a\\"b'
    assert escape_as2_string("a\\b") == "a\\\\b"
    assert escape_as2_string("a\nb") == "a\\nb"
    assert escape_as2_string("a\rb") == "a\\rb"


def test_grid_id_with_quote_is_escaped_in_output():
    grid = _minimal_grid()
    grid["id"] = 'My"Grid'
    main, data = CodeGenerator([grid], _load_db(), "0.0.0").generate()
    combined = main + data
    # The quote is escaped, keeping the AS2 string literal well-formed...
    assert 'My\\"Grid' in combined
    # ...and the raw, literal-breaking form never appears.
    assert 'My"Grid' not in combined


def test_positions_project_to_the_build_resolution():
    grid = _minimal_grid()
    grid["fx"], grid["fy"] = 0.5, 0.85
    _, data_1080 = CodeGenerator(
        [grid], _load_db(), "0.0.0", game_resolution=(1920, 1080)).generate()
    assert "x: 960," in data_1080 and "y: 918," in data_1080
    _, data_4k = CodeGenerator(
        [grid], _load_db(), "0.0.0", game_resolution=(3840, 2160)).generate()
    assert "x: 1920," in data_4k and "y: 1836," in data_4k


def test_positions_default_resolution_when_none_given():
    grid = _minimal_grid()
    grid["fx"], grid["fy"] = 1.0, 1.0
    _, data = CodeGenerator([grid], _load_db(), "0.0.0").generate()
    assert "x: 1920," in data and "y: 1080," in data  # DEFAULT_GAME_RESOLUTION


def test_grid_id_with_newline_does_not_inject():
    grid = _minimal_grid()
    grid["id"] = "X\ninjected"
    main, data = CodeGenerator([grid], _load_db(), "0.0.0").generate()
    combined = main + data
    assert "X\\ninjected" in combined  # escaped to backslash-n
    assert "X\ninjected" not in combined  # no raw newline survives


def test_console_off_emits_no_console_refs():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", include_console=False)
    main_code, _ = gen.generate()

    # The class name and identifier are namespaced in case-sensitive AS2.
    # `console` (lowercase) is the member name; `KazBarsConsole` is the class.
    assert "KazBarsConsole" not in main_code, (
        "include_console=False must not reference KazBarsConsole class — "
        "MTASC would fail to resolve it."
    )
    # The substring "console" appears in many unrelated words; restrict to
    # the meaningful tokens that would make AS2 fail.
    assert "console." not in main_code
    assert "consolePinned" not in main_code
    # Template tokens must all be substituted away.
    assert "{{CONSOLE_" not in main_code


def test_console_on_emits_console_hooks():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", include_console=True)
    main_code, _ = gen.generate()

    # Instantiation
    assert "private var console:KazBarsConsole;" in main_code
    assert "console = new KazBarsConsole(rootClip);" in main_code
    # The pin is gone — the control panel is the master switch now.
    assert "consolePinned" not in main_code

    # The two inline call sites left to the gate; every lifecycle call now
    # runs off the ungated module registry, which never names a stub.
    assert "console.logPlayer(buff.m_Name, bid)" in main_code
    assert "console.logTarget(buff.m_Name, bid)" in main_code
    assert "modules.push(console);" in main_code

    # Persistence lives wholly inside the stub, reached through saveAll/loadAll
    # (preview exit + deactivate, and activation for the load).
    assert 'config.ReplaceEntry("console_pin"' not in main_code
    assert 'config.ReplaceEntry("cnv"' not in main_code
    assert main_code.count("saveAll(config);") == 2
    assert "loadAll(config);" in main_code

    # No leftover tokens
    assert "{{CONSOLE_" not in main_code


def test_console_default_is_off():
    """Belt-and-suspenders: the default in CodeGenerator must be opt-in."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0")
    main_code, _ = gen.generate()
    assert "KazBarsConsole" not in main_code


# --------------------------------------------------------------------------
# Cast-timer overlay toggle (include_cast_timer, derived from cast_config)
# --------------------------------------------------------------------------


def _cast_cfg():
    # Fraction positions chosen to project to 900/600/560 px at the default
    # 1920×1080 build resolution.
    return {
        "enabled": True,
        "enableP": True,
        "enableT": True,
        "playerFx": 900 / 1920,
        "playerFy": 600 / 1080,
        "targetFx": 900 / 1920,
        "targetFy": 560 / 1080,
        "bold": True,
        "fontSize": 18,
        "display": "both",
        "color": "FF8800",
    }


def test_cast_off_emits_no_cast_refs():
    """No cast_config (or both sides off) must reference KazBarsCastTimer —
    MTASC would otherwise fail to resolve the class — and leave no raw tokens."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", cast_config=None)
    main_code, data_code = gen.generate()
    assert not gen.include_cast_timer
    assert "KazBarsCastTimer" not in main_code
    assert "castTimer" not in main_code
    assert "{{CAST_" not in main_code
    assert "d.CAST" not in data_code


def test_cast_disabled_config_is_off():
    """Master off (or both sides off) must not switch the feature on."""
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        cast_config={"enabled": False, "enableP": True, "enableT": True},
    )
    main_code, _ = gen.generate()
    assert not gen.include_cast_timer
    assert "KazBarsCastTimer" not in main_code

    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        cast_config={"enabled": True, "enableP": False, "enableT": False},
    )
    assert not gen.include_cast_timer


def test_cast_on_emits_hooks_and_data():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", cast_config=_cast_cfg())
    main_code, data_code = gen.generate()
    assert gen.include_cast_timer

    # Instantiation + configure
    assert "private var castTimer:KazBarsCastTimer;" in main_code
    assert "castTimer = new KazBarsCastTimer(rootClip);" in main_code
    assert "castTimer.configure(d.CAST);" in main_code

    # Registration (the lifecycle itself runs off the ungated registry) plus
    # the feeds, which are the cast timer's own and stay gated.
    assert "modules.push(castTimer);" in main_code
    assert "castTimer.connectPlayer(m_Player);" in main_code
    assert "castTimer.setTarget(m_Target);" in main_code
    assert "castTimer.disconnectPlayer();" in main_code

    # Data block — fractions project to px at the default build resolution;
    # color must be a numeric hex literal (Number() else NaN); font is fixed
    # to Arial in the stub, so only bold is emitted.
    assert "d.CAST = {" in data_code
    assert "playerX: 900, playerY: 600, targetX: 900, targetY: 560" in data_code
    assert "color: 0xFF8800" in data_code
    assert "bold: true" in data_code
    assert 'display: "both"' in data_code
    assert "font:" not in data_code

    # No leftover tokens
    assert "{{CAST_" not in main_code


# --------------------------------------------------------------------------
# In-game stopwatch toggle (include_stopwatch, derived from stopwatch_config)
# --------------------------------------------------------------------------


def test_stopwatch_off_emits_no_refs():
    """No stopwatch_config (or enabled=False) must reference KazBarsStopwatch —
    MTASC would otherwise fail to resolve the class — and leave no raw tokens."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", stopwatch_config=None)
    main_code, data_code = gen.generate()
    assert not gen.include_stopwatch
    assert "KazBarsStopwatch" not in main_code
    assert "stopwatch" not in main_code
    assert "{{SW_" not in main_code
    assert "d.SW" not in data_code


def test_stopwatch_disabled_config_is_off():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": False, "fx": 0.1, "fy": 0.1},
    )
    main_code, _ = gen.generate()
    assert not gen.include_stopwatch
    assert "KazBarsStopwatch" not in main_code


def test_stopwatch_on_emits_hooks_and_data():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "fx": 750 / 1920, "fy": 410 / 1080,
                          "fontSize": 16, "startCollapsed": True},
    )
    main_code, data_code = gen.generate()
    assert gen.include_stopwatch

    # Instantiation + configure
    assert "private var stopwatch:KazBarsStopwatch;" in main_code
    assert "stopwatch = new KazBarsStopwatch(rootClip);" in main_code
    assert "stopwatch.configure(d.SW);" in main_code

    # Registration is the whole hook: the stopwatch has no feed of its own,
    # so the registry drives every lifecycle call.
    assert "modules.push(stopwatch);" in main_code

    # Data block — the fraction position projects to px at the default build
    # resolution; a fontSize of its own overrides the shared panel size
    assert "d.SW = {x: 750, y: 410, fontSize: 16, collapsed: true};" in data_code

    # No leftover tokens
    assert "{{SW_" not in main_code


def test_stopwatch_without_its_own_size_follows_the_shared_one():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "fx": 750 / 1920, "fy": 410 / 1080,
                          "fontSize": None},
        panel_font_size=20,
    )
    _, data_code = gen.generate()
    assert "d.SW = {x: 750, y: 410, fontSize: 20, collapsed: false};" in data_code


def test_extras_positions_project_to_the_build_resolution():
    """Same section, different target resolution → proportionally moved px
    (the whole point of storing extras positions as fractions)."""
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "fx": 0.5, "fy": 0.5},
        game_resolution=(2560, 1440),
    )
    _, data_code = gen.generate()
    assert "d.SW = {x: 1280, y: 720," in data_code


# --------------------------------------------------------------------------
# Target inspect panel toggle (include_inspect, derived from inspect_config)
# --------------------------------------------------------------------------


def test_inspect_off_emits_no_refs():
    """No inspect_config (or enabled=False) must reference KazBarsInspect —
    MTASC would otherwise fail to resolve the class — and leave no raw tokens."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", inspect_config=None)
    main_code, data_code = gen.generate()
    assert not gen.include_inspect
    assert "KazBarsInspect" not in main_code
    assert "inspect" not in main_code
    assert "{{INS_" not in main_code
    assert "d.INS" not in data_code


def test_inspect_disabled_config_is_off():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        inspect_config={"enabled": False, "fx": 0.1, "fy": 0.1},
    )
    main_code, _ = gen.generate()
    assert not gen.include_inspect
    assert "KazBarsInspect" not in main_code


def test_inspect_on_emits_hooks_and_data():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        inspect_config={"enabled": True, "fx": 40 / 1920, "fy": 240 / 1080,
                        "fontSize": 14, "startCollapsed": True, "showPvp": True,
                        "showPerks": False},
    )
    main_code, data_code = gen.generate()
    assert gen.include_inspect

    # Instantiation + configure
    assert "private var inspect:KazBarsInspect;" in main_code
    assert "inspect = new KazBarsInspect(rootClip);" in main_code
    assert "inspect.configure(d.INS);" in main_code

    # Registration (the lifecycle runs off the ungated registry) plus the
    # target feed, which is the inspect panel's own and stays gated.
    assert "modules.push(inspect);" in main_code
    assert "inspect.setSubject(tid);" in main_code

    # Data block — the fraction position projects to px at the default build
    # resolution; a fontSize of its own overrides the shared panel size
    assert ("d.INS = {x: 40, y: 240, fontSize: 14, collapsed: true, "
            "showPvp: true, showPerks: false};" in data_code)

    # No leftover tokens
    assert "{{INS_" not in main_code


def test_inspect_without_its_own_size_follows_the_shared_one():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        inspect_config={"enabled": True, "fx": 40 / 1920, "fy": 240 / 1080,
                        "fontSize": None},
        panel_font_size=20,
    )
    _, data_code = gen.generate()
    assert ("d.INS = {x: 40, y: 240, fontSize: 20, collapsed: false, "
            "showPvp: true, showPerks: true};" in data_code)


# --------------------------------------------------------------------------
# Preview-mode control panel (KazBarsPreviewPanel — unconditional; the extra
# rows and their dispatch arms are gated per extra)
# --------------------------------------------------------------------------


def _all_extras_gen():
    return CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        include_console=True,
        cast_config=_cast_cfg(),
        stopwatch_config={"enabled": True, "fx": 750 / 1920, "fy": 410 / 1080},
        inspect_config={"enabled": True, "fx": 40 / 1920, "fy": 240 / 1080},
    )


def test_preview_panel_always_emitted():
    """The panel compiles into every build, extras or not."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0")
    main_code, _ = gen.generate()

    assert "private var ppanel:KazBarsPreviewPanel;" in main_code
    assert "ppanel = new KazBarsPreviewPanel(this, rootClip);" in main_code

    # Rows are collected on every preview entry, panel shown last (topmost).
    assert "ppanel.begin();" in main_code
    assert "ppanel.addGrid(obj);" in main_code
    assert "ppanel.show();" in main_code
    assert "public function previewToggle(key:String, shown:Boolean):Void {" in main_code

    # Teardown from both paths (exitPreview + cleanup); the panel's own
    # persistence is written once, inside saveAll, which both persist paths
    # (exitPreview + OnModuleDeactivated) call.
    assert main_code.count("ppanel.destroy();") == 2
    assert main_code.count("ppanel.saveState(config);") == 1
    assert main_code.count("saveAll(config);") == 2
    assert "ppanel.loadState(config);" in main_code

    assert "{{PP_" not in main_code


def test_shared_panel_font_is_always_emitted_and_configured():
    """`d.PF` is unconditional — the control panel compiles into every build, so
    a mistake here breaks every build rather than only console-enabled ones. Its
    identifiers must also stay clear of the bare 'stopwatch'/'inspect' substrings
    the off-path tests assert against the whole generated class."""
    main_code, data_code = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0").generate()
    assert "d.PF = {fontSize: 12};" in data_code
    assert "ppanel.configure(d.PF);" in main_code
    assert "console.configure(d.PF);" not in main_code

    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0",
                        include_console=True, panel_font_size=20)
    main_code, data_code = gen.generate()
    assert "d.PF = {fontSize: 20};" in data_code
    assert "console.configure(d.PF);" in main_code


def test_shared_panel_font_is_clamped():
    def size_of(value):
        return CodeGenerator([_minimal_grid()], _load_db(), "0.0.0",
                             panel_font_size=value).panel_font_size

    assert size_of(None) == 12
    assert size_of("garbage") == 12
    assert size_of(2) == 8
    assert size_of(99) == 48


def test_preview_panel_no_extras_has_no_extra_rows():
    """With nothing compiled in, the registry is empty, so the rows loop and the
    dispatcher loop both run over nothing. They are ungated — the check that
    nothing was left dangling is that no stub is registered or named."""
    main_code, _ = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0").generate()
    assert "modules.push(" not in main_code
    for stub in ("KazBarsConsole", "KazBarsCastTimer", "KazBarsStopwatch",
                 "KazBarsInspect"):
        assert stub not in main_code


def test_preview_panel_rows_and_dispatch_all_extras():
    main_code, _ = _all_extras_gen().generate()

    # One row per registered module, each seeded from that module's live state
    # and labelled by it — the panel never caches a flag of its own, and the
    # core never spells out a row.
    assert ("ppanel.addExtra(m.previewLabel(), m.previewKey(), m.isActive());"
            in main_code)

    # Registration order IS row order, and rows are added before the panel is
    # built (which is what puts it topmost).
    assert (main_code.index("modules.push(stopwatch);")
            < main_code.index("modules.push(inspect);")
            < main_code.index("modules.push(castTimer);")
            < main_code.index("modules.push(console);"))
    assert main_code.index("ppanel.addExtra(") < main_code.index("ppanel.show();")

    # One dispatcher for every row, matched on the module's own key.
    assert 'if (m.previewKey() == key) m.setActive(shown);' in main_code

    # Nothing is restored on the way out of preview any more — a check is the
    # setting, and the pin it replaced is gone.
    assert "setShown" not in main_code
    assert "consolePinned" not in main_code

    assert "{{PP_" not in main_code
    assert "{{SW_" not in main_code


def test_preview_panel_row_gated_per_extra():
    """A row only appears for an extra that is actually compiled in."""
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "fx": 750 / 1920, "fy": 410 / 1080},
    )
    main_code, _ = gen.generate()
    assert main_code.count("modules.push(") == 1
    assert "modules.push(stopwatch);" in main_code


def test_grid_shown_is_master_switch():
    """A grid row flips a persisted `shown` flag the normal-mode writers honor,
    and preview shows what normal mode would (no blanket force-show)."""
    main_code, _ = _all_extras_gen().generate()

    assert "dirty: true, shown: true" in main_code
    assert 'config.FindEntry("g" + i + "_v")' in main_code
    # Written once, in saveAll, keyed like the positions beside it — both
    # persist paths reach it from there.
    assert main_code.count(
        'config.ReplaceEntry("g" + i + "_v", grids[i].shown ? 1 : 0);') == 1

    assert "obj.mc._visible = obj.shown;" in main_code
    assert "obj.mc._visible = obj.shown && disp.length > 0;" in main_code
    assert "obj.mc._visible = obj.shown && hasAny;" in main_code


def test_console_master_switch_defaults_active():
    """A fresh archive opens the console at login; the archived master switch
    (cnv) is honoured inside the stub's loadState on activation."""
    main_code, _ = _all_extras_gen().generate()

    assert main_code.index("m.create();") < main_code.index(
        "SignalClientCharacterAlive")
    assert main_code.index("m.create();") < main_code.index("loadAll(config);")
    assert "console_pin" not in main_code


def test_stub_archive_keys_present():
    """The per-stub master switches live inside the stubs, where generator
    output can't show them."""
    stubs = KAZBARS_ASSETS / "stubs"
    pairs = (
        ("KazBarsStopwatch.as", "swv"),
        ("KazBarsInspect.as", "inv"),
        ("KazBarsCastTimer.as", "ctv"),
        ("KazBarsConsole.as", "cnv"),
    )
    for name, key in pairs:
        src = (stubs / name).read_text(encoding="utf-8")
        assert f'FindEntry("{key}")' in src, f"{name} never reads {key}"
        assert f'ReplaceEntry("{key}"' in src, f"{name} never writes {key}"


# --------------------------------------------------------------------------
# Inert refs: unresolved_refs (the build-summary count) + emit-time skip
# --------------------------------------------------------------------------


def _known_primary_id(db):
    return db.buffs[0]["ids"][0]


def test_unresolved_refs_counts_unknown_ids_and_names_once():
    from kazbars.grids_generator import unresolved_refs
    db = _load_db()
    known = _known_primary_id(db)
    grids = [
        dict(_minimal_grid(), whitelist=[known, 99999901, "Ghost Buff"]),
        dict(_minimal_grid(), id="G2", slotMode="static",
             slotAssignments={"0": [99999901], "1": "Ghost Buff", "2": []}),
    ]
    # Deduped across grids and across whitelist/slot forms, resolvable skipped.
    assert unresolved_refs(grids, db) == [99999901, "Ghost Buff"]


def test_unresolved_refs_ignores_disabled_grids():
    from kazbars.grids_generator import unresolved_refs
    grids = [dict(_minimal_grid(), enabled=False, whitelist=[99999901])]
    assert unresolved_refs(grids, _load_db()) == []


def test_unresolved_refs_empty_when_everything_resolves():
    from kazbars.grids_generator import unresolved_refs
    db = _load_db()
    grids = [dict(_minimal_grid(), whitelist=[_known_primary_id(db)])]
    assert unresolved_refs(grids, db) == []


def test_unknown_refs_are_skipped_at_emit_not_crashed_on():
    """An inert int or legacy-name ref must vanish from the emitted tables —
    and never raise — exactly what unresolved_refs predicted for the summary."""
    db = _load_db()
    grid = dict(_minimal_grid(), whitelist=[_known_primary_id(db), 99999901, "Ghost Buff"])
    main_code, data_code = CodeGenerator([grid], db, "0.0.0").generate()
    assert "99999901" not in main_code + data_code
    assert "Ghost Buff" not in main_code + data_code
