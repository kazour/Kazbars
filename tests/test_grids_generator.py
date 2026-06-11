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
    assert "consolePinned = false;" in main_code

    # The five inline call sites
    assert "console.logPlayer(buff.m_Name, bid)" in main_code
    assert "console.logTarget(buff.m_Name, bid)" in main_code
    assert "console.createConsole();" in main_code
    assert "console.removeConsole();" in main_code

    # Persistence keys
    assert 'config.ReplaceEntry("console_pin"' in main_code
    assert 'config.ReplaceEntry("log_p"' in main_code
    assert 'config.ReplaceEntry("log_t"' in main_code

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
        stopwatch_config={"enabled": True, "x": 750, "y": 410, "startCollapsed": True},
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

    # Data block
    assert "d.SW = {x: 750, y: 410, collapsed: true};" in data_code

    # No leftover tokens
    assert "{{SW_" not in main_code
