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
        "x": 0,
        "y": 0,
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
    assert "console = new KazBarsConsole(this, rootClip);" in main_code
    # The pin is gone — the control panel is the master switch now.
    assert "consolePinned" not in main_code

    # The five inline call sites
    assert "console.logPlayer(buff.m_Name, bid)" in main_code
    assert "console.logTarget(buff.m_Name, bid)" in main_code
    assert "console.createConsole();" in main_code
    assert "console.removeConsole();" in main_code

    # Persistence keys — master switch + the two log toggles here, position
    # inside the stub. cnv saves from both persist paths.
    assert 'config.ReplaceEntry("console_pin"' not in main_code
    assert main_code.count('config.ReplaceEntry("cnv"') == 2
    assert 'config.ReplaceEntry("log_p"' in main_code
    assert 'config.ReplaceEntry("log_t"' in main_code
    assert "console.saveState(config);" in main_code
    # Loaded before the re-create, so the console rebuilds where it was left.
    assert main_code.index("console.loadState(config);") < main_code.index(
        "else console.createConsole();")

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
    return {
        "enableP": True,
        "enableT": True,
        "playerX": 900,
        "playerY": 600,
        "targetX": 900,
        "targetY": 560,
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
    """A cast_config with both timers off must not switch the feature on."""
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0", cast_config={"enableP": False, "enableT": False}
    )
    main_code, _ = gen.generate()
    assert not gen.include_cast_timer
    assert "KazBarsCastTimer" not in main_code


def test_cast_on_emits_hooks_and_data():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", cast_config=_cast_cfg())
    main_code, data_code = gen.generate()
    assert gen.include_cast_timer

    # Instantiation + configure
    assert "private var castTimer:KazBarsCastTimer;" in main_code
    assert "castTimer = new KazBarsCastTimer(this, rootClip);" in main_code
    assert "castTimer.configure(d.CAST);" in main_code

    # Lifecycle hooks
    assert "castTimer.createFields();" in main_code
    assert "castTimer.connectPlayer(m_Player);" in main_code
    assert "castTimer.setTarget(m_Target);" in main_code
    assert "castTimer.previewOn();" in main_code
    assert "castTimer.savePositions(config);" in main_code
    assert "castTimer.cleanup();" in main_code

    # Data block — color must be a numeric hex literal (Number() else NaN);
    # font is fixed to Arial in the stub, so only bold is emitted.
    assert "d.CAST = {" in data_code
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
        stopwatch_config={"enabled": False, "x": 100, "y": 100},
    )
    main_code, _ = gen.generate()
    assert not gen.include_stopwatch
    assert "KazBarsStopwatch" not in main_code


def test_stopwatch_on_emits_hooks_and_data():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "x": 750, "y": 410, "fontSize": 16,
                          "startCollapsed": True},
    )
    main_code, data_code = gen.generate()
    assert gen.include_stopwatch

    # Instantiation + configure
    assert "private var stopwatch:KazBarsStopwatch;" in main_code
    assert "stopwatch = new KazBarsStopwatch(this, rootClip);" in main_code
    assert "stopwatch.configure(d.SW);" in main_code

    # Lifecycle hooks
    assert "stopwatch.createPanel();" in main_code
    assert "stopwatch.loadState(config);" in main_code
    assert "stopwatch.saveState(config);" in main_code
    assert "stopwatch.cleanup();" in main_code

    # Data block — a number of its own overrides the shared panel size
    assert "d.SW = {x: 750, y: 410, fontSize: 16, collapsed: true};" in data_code

    # No leftover tokens
    assert "{{SW_" not in main_code


def test_stopwatch_without_its_own_size_follows_the_shared_one():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        stopwatch_config={"enabled": True, "x": 750, "y": 410, "fontSize": None},
        panel_font_size=20,
    )
    _, data_code = gen.generate()
    assert "d.SW = {x: 750, y: 410, fontSize: 20, collapsed: false};" in data_code


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
        inspect_config={"enabled": False, "x": 100, "y": 100},
    )
    main_code, _ = gen.generate()
    assert not gen.include_inspect
    assert "KazBarsInspect" not in main_code


def test_inspect_on_emits_hooks_and_data():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        inspect_config={"enabled": True, "x": 40, "y": 240, "fontSize": 14,
                        "startCollapsed": True, "showPvp": True,
                        "showPerks": False},
    )
    main_code, data_code = gen.generate()
    assert gen.include_inspect

    # Instantiation + configure
    assert "private var inspect:KazBarsInspect;" in main_code
    assert "inspect = new KazBarsInspect(this, rootClip);" in main_code
    assert "inspect.configure(d.INS);" in main_code

    # Lifecycle hooks
    assert "inspect.createPanel();" in main_code
    assert "inspect.setSubject(tid);" in main_code
    assert "inspect.previewOn();" in main_code
    assert "inspect.previewOff();" in main_code
    assert "inspect.loadState(config);" in main_code
    assert "inspect.cleanup();" in main_code
    # Save fires from BOTH persist paths (exitPreview + OnModuleDeactivated)
    assert main_code.count("inspect.saveState(config);") == 2

    # Data block — a number of its own overrides the shared panel size
    assert ("d.INS = {x: 40, y: 240, fontSize: 14, collapsed: true, "
            "showPvp: true, showPerks: false};" in data_code)

    # No leftover tokens
    assert "{{INS_" not in main_code


def test_inspect_without_its_own_size_follows_the_shared_one():
    gen = CodeGenerator(
        [_minimal_grid()], _load_db(), "0.0.0",
        inspect_config={"enabled": True, "x": 40, "y": 240, "fontSize": None},
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
        stopwatch_config={"enabled": True, "x": 750, "y": 410},
        inspect_config={"enabled": True, "x": 40, "y": 240},
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

    # Teardown from both paths (exitPreview + cleanup), save from both
    # persist paths (exitPreview + OnModuleDeactivated).
    assert main_code.count("ppanel.destroy();") == 2
    assert main_code.count("ppanel.saveState(config);") == 2
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
    """With nothing compiled in, the panel lists grids only and the dispatcher
    body is empty — an addExtra or setActive here would name a missing class."""
    main_code, _ = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0").generate()
    assert "ppanel.addExtra(" not in main_code
    assert "setActive" not in main_code


def test_preview_panel_rows_and_dispatch_all_extras():
    main_code, _ = _all_extras_gen().generate()

    # Each row seeds its check from the item's live state — the panel never
    # caches a flag of its own.
    assert 'ppanel.addExtra("Stopwatch", "sw", stopwatch.isActive());' in main_code
    assert 'ppanel.addExtra("Inspect panel", "ins", inspect.isActive());' in main_code
    assert 'ppanel.addExtra("Cast timer", "cast", castTimer.isActive());' in main_code
    assert 'ppanel.addExtra("Console", "console", console.isActive());' in main_code

    # Rows are added before the panel is built, in menu order.
    assert (main_code.index('ppanel.addExtra("Stopwatch"')
            < main_code.index('ppanel.addExtra("Inspect panel"')
            < main_code.index('ppanel.addExtra("Cast timer"')
            < main_code.index('ppanel.addExtra("Console"')
            < main_code.index("ppanel.show();"))

    # One dispatch arm per extra.
    assert 'if (key == "sw") stopwatch.setActive(shown);' in main_code
    assert 'if (key == "ins") inspect.setActive(shown);' in main_code
    assert 'if (key == "cast") castTimer.setActive(shown);' in main_code
    assert 'if (key == "console") console.setActive(shown);' in main_code

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
        stopwatch_config={"enabled": True, "x": 750, "y": 410},
    )
    main_code, _ = gen.generate()
    assert 'ppanel.addExtra("Stopwatch", "sw", stopwatch.isActive());' in main_code
    assert 'ppanel.addExtra("Inspect panel", "ins", inspect.isActive());' not in main_code
    assert 'ppanel.addExtra("Cast timer", "cast", castTimer.isActive());' not in main_code
    assert 'ppanel.addExtra("Console", "console", console.isActive());' not in main_code


def test_grid_shown_is_master_switch():
    """A grid row flips a persisted `shown` flag the normal-mode writers honor,
    and preview shows what normal mode would (no blanket force-show)."""
    main_code, _ = _all_extras_gen().generate()

    assert "dirty: true, shown: true" in main_code
    assert 'config.FindEntry("g" + i + "_v")' in main_code
    # Saved from both persist paths, keyed like the positions beside them.
    assert 'config.ReplaceEntry("g" + j + "_v", grids[j].shown ? 1 : 0);' in main_code
    assert 'config.ReplaceEntry("g" + i + "_v", grids[i].shown ? 1 : 0);' in main_code

    assert "obj.mc._visible = obj.shown;" in main_code
    assert "obj.mc._visible = obj.shown && disp.length > 0;" in main_code
    assert "obj.mc._visible = obj.shown && hasAny;" in main_code


def test_console_master_switch_defaults_active():
    """Fresh archive (and every /loadclip client) opens the console at login;
    an archived cnv == 0 closes it again on activation."""
    main_code, _ = _all_extras_gen().generate()

    assert main_code.index("console.createConsole();") < main_code.index(
        "SignalClientCharacterAlive")
    assert 'if (cnv !== undefined && cnv == 0) console.removeConsole();' in main_code
    assert "console_pin" not in main_code


def test_stub_archive_keys_present():
    """The per-stub master switches live inside the stubs, where generator
    output can't show them."""
    stubs = KAZBARS_ASSETS / "stubs"
    pairs = (
        ("KazBarsStopwatch.as", "swv"),
        ("KazBarsInspect.as", "inv"),
        ("KazBarsCastTimer.as", "ctv"),
    )
    for name, key in pairs:
        src = (stubs / name).read_text(encoding="utf-8")
        assert f'FindEntry("{key}")' in src, f"{name} never reads {key}"
        assert f'ReplaceEntry("{key}"' in src, f"{name} never writes {key}"
