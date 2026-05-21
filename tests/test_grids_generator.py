"""
Tests for `grids_generator.CodeGenerator` — the optional buff-discovery
console toggle (`include_console`).

When `include_console=False` the generated AS2 must contain no `console`
references and no `KzGridsConsole` references — otherwise MTASC would
fail to resolve the missing class.

When `include_console=True` the generator must emit the original console
hooks: instantiation in the constructor, the two log calls in
SlotPBuffAdd / SlotTBuffAdd, plus the preview-mode wiring.

Run: `pytest tests/test_grids_generator.py` (from repo root).
"""

from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import CodeGenerator
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


def test_console_off_emits_no_console_refs():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", include_console=False)
    main_code, _ = gen.generate()

    # The class name and identifier are namespaced in case-sensitive AS2.
    # `console` (lowercase) is the member name; `KzGridsConsole` is the class.
    assert "KzGridsConsole" not in main_code, (
        "include_console=False must not reference KzGridsConsole class — "
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
    assert "private var console:KzGridsConsole;" in main_code
    assert "console = new KzGridsConsole(this, rootClip);" in main_code
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
    assert "KzGridsConsole" not in main_code


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
    """No cast_config (or both sides off) must reference KzGridsCastTimer —
    MTASC would otherwise fail to resolve the class — and leave no raw tokens."""
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", cast_config=None)
    main_code, data_code = gen.generate()
    assert not gen.include_cast_timer
    assert "KzGridsCastTimer" not in main_code
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
    assert "KzGridsCastTimer" not in main_code


def test_cast_on_emits_hooks_and_data():
    gen = CodeGenerator([_minimal_grid()], _load_db(), "0.0.0", cast_config=_cast_cfg())
    main_code, data_code = gen.generate()
    assert gen.include_cast_timer

    # Instantiation + configure
    assert "private var castTimer:KzGridsCastTimer;" in main_code
    assert "castTimer = new KzGridsCastTimer(this, rootClip);" in main_code
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
