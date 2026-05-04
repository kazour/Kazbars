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
