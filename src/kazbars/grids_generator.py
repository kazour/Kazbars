"""
KazBars — KazBars Code Generator
Generates KazBars.as ActionScript 2.0 source code from grid configurations.
"""

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .build_utils import compile_as2, resolve_assets_path
from .cast_timer import is_enabled as cast_is_enabled
from .cast_timer import validate_config as validate_cast_config
from .grid_model import MAX_TOTAL_SLOTS
from .stopwatch import validate_config as validate_stopwatch_config

logger = logging.getLogger(__name__)


# AoC serves these buff IDs with a null icon; we attach a baked %-label symbol from
# base.swf instead of the (empty) game icon. Same-% gems share one symbol.
CUSTOM_ICON_LINKAGE = {
    5077953: "IcoSlow30",  # Ice Storm E
    5077873: "IcoSlow40",  # Ice Strike E
    5077888: "IcoSlow40",  # Ice Cloak E  (placeholder ID — verify in-game)
    5077955: "IcoSlow45",  # Ice Storm L
    5077874: "IcoSlow60",  # Ice Strike L
    5077889: "IcoSlow60",  # Ice Cloak L
}


_template_cache: dict[str, str] = {}


def _load_core_template(assets_path=None):
    """Load AS2 core methods template from external file (cached)."""
    base = resolve_assets_path(assets_path)
    template_path = base / "kazbars" / "KazBars_core.as.template"
    key = str(template_path)
    if key not in _template_cache:
        with open(template_path, encoding="utf-8") as f:
            _template_cache[key] = f.read()
    return _template_cache[key]


# ============================================================================
# CODE GENERATOR
# ============================================================================
def escape_as2_string(value):
    """Escape a string for safe interpolation into an AS2 double-quoted literal
    or bracket key — guards user-set grid IDs that contain quotes or newlines
    (which would otherwise break, or inject into, the generated AS2)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _stack_bound(value, fallback):
    """Coerce a stackStart/stackEnd from an imported/hand-edited entry the way
    the other loaders coerce ints (numeric strings count, junk falls back), so
    the slice in `_expand_primary_ids` can't go negative or raise."""
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return value if value >= 1 else fallback


class CodeGenerator:
    """Generate AS2 source code for the KazBars buff-tracking grid system."""

    def __init__(
        self,
        grids,
        database,
        app_version,
        assets_path=None,
        include_console=False,
        cast_config=None,
        stopwatch_config=None,
    ):
        """Initialize the code generator with grid configs and the buff database."""
        # Filter out disabled grids
        self.grids = [g for g in grids if g.get("enabled", True)]
        self.database = database
        self.app_version = app_version
        self._assets_path = assets_path
        self._stack_labels = {}
        self.include_console = include_console
        # Cast-timer overlay: validated config + build gate. include_cast_timer is
        # False unless the player or target timer is enabled, so the SWF carries no
        # cast-timer code when the feature is off (mirrors include_console).
        self.cast_config = validate_cast_config(cast_config)
        self.include_cast_timer = cast_is_enabled(self.cast_config)
        # In-game stopwatch: same gate pattern — off means no stopwatch code compiles.
        self.stopwatch_config = validate_stopwatch_config(stopwatch_config)
        self.include_stopwatch = self.stopwatch_config["enabled"]

    def sanitize_id(self, grid_id):
        """Convert a grid ID to a safe AS2 identifier by replacing invalid characters."""
        safe = ""
        for c in grid_id:
            if c.isalnum() or c == "_":
                safe += c
            else:
                safe += "_"
        if safe and safe[0].isdigit():
            safe = "_" + safe
        return safe or "Grid"

    def generate(self):
        """Generate the main KazBars.as and separate KazBarsData.as source code."""
        # Main class (no inline config — calls KazBarsData.init())
        main = []
        main.append(self._header())
        main.append(self._class_start())
        main.append(self._member_variables())
        main.append(self._constructor())
        main.append(self._init_config_stub())
        main.append(self._core_methods())
        main.append(self._class_end())

        # Data class (all grid configs, whitelists, buff lookups)
        data = []
        data.append(self._header())
        data.append(self._data_class())

        return "\n".join(main), "\n".join(data)

    def _header(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        total_slots = sum(g["rows"] * g["cols"] for g in self.grids)
        return f"""// ============================================================================
// KZGRIDS - Generated by KazBars v{self.app_version}
// Generated: {timestamp}
// Total slots: {total_slots} / {MAX_TOTAL_SLOTS}
// ============================================================================
"""

    def _class_start(self):
        return "class KazBars {\n"

    def _class_end(self):
        return "}\n"

    def _member_variables(self):
        console_decl = "\n    private var console:KazBarsConsole;" if self.include_console else ""
        console_pin_decl = (
            "\n\n    // Console pin state (persisted via config archive)\n    private var consolePinned:Boolean;"
            if self.include_console
            else ""
        )
        cast_decl = (
            "\n    private var castTimer:KazBarsCastTimer;" if self.include_cast_timer else ""
        )
        sw_decl = (
            "\n    private var stopwatch:KazBarsStopwatch;" if self.include_stopwatch else ""
        )
        return f"""
    private var rootClip:MovieClip;
    private var m_Player:Object;
    private var m_Target:Object;
    private var config:Object;
    private var playerBuffs:Array;
    private var targetBuffs:Array;
    private var buffIndexCache:Object;
    private var grids:Array;
    private var timerInterval:Number;
    private var frameActive:Boolean;
    private var frameCount:Number;
    private var TCACHE:Object;
    private var previewMode:Boolean;
    private var previewArmed:Boolean;
    private var lastShiftDown:Number;
    private var lastCtrlDown:Number;
    private var lastAltDown:Number;
    private var C_BUFF:Number;
    private var C_DEBUFF:Number;
    private var C_BG:Number;
    private var CFG:Object;
    private var WL:Object;
    private var ISDEB:Object;
    private var BUFFTYPE:Object;
    private var STACK_LEVEL:Object;
    private var CUSTOMICON:Object;

    // OPTIMIZATION: Alpha flash lookup table (100 pre-calculated values)
    private var AFLASH:Array;

    // OPTIMIZATION: Reusable arrays to reduce GC
    private var _tempBuffs:Array;
    private var _tempDebuffs:Array;
    private var _tempMisc:Array;

    // HELPER CLASSES: Preview, Slot, and (optional) Console (32KB bytecode limit workaround)
    private var preview:KazBarsPreview;{console_decl}
    private var slot:KazBarsSlot;{console_pin_decl}{cast_decl}{sw_decl}

    // Key listener reference for proper cleanup
    private var keyListener:Object;
"""

    def _constructor(self):
        console_pin_init = "\n        consolePinned = false;" if self.include_console else ""
        console_init = (
            "\n        console = new KazBarsConsole(this, rootClip);"
            if self.include_console
            else ""
        )
        cast_init = (
            "\n        castTimer = new KazBarsCastTimer(this, rootClip);"
            if self.include_cast_timer
            else ""
        )
        sw_init = (
            "\n        stopwatch = new KazBarsStopwatch(this, rootClip);"
            if self.include_stopwatch
            else ""
        )
        return f"""
    public function KazBars(root:MovieClip) {{
        rootClip = root;
        playerBuffs = new Array();
        targetBuffs = new Array();
        grids = new Array();
        buffIndexCache = {{player: {{}}, target: {{}}}};
        frameActive = false;
        frameCount = 0;
        previewMode = false;
        previewArmed = true;
        lastShiftDown = 0;
        lastCtrlDown = 0;
        lastAltDown = 0;{console_pin_init}
        C_BUFF = 0x666666;
        C_DEBUFF = 0x8B0000;
        C_BG = 0x000000;
        TCACHE = {{}};
        var i:Number = 0;
        while (i <= 99) {{ TCACHE[i] = String(i); i++; }}

        // OPTIMIZATION: Pre-calculate alpha flash values (100 entries)
        // Replaces Math.sin() calls every frame with array lookup
        AFLASH = new Array();
        var j:Number = 0;
        while (j < 100) {{
            var phase:Number = (j / 100) * 6.28318;
            AFLASH[j] = 33 + (Math.sin(phase) + 1) * 33.5;
            j++;
        }}

        // OPTIMIZATION: Reusable arrays to reduce garbage collection
        _tempBuffs = new Array();
        _tempDebuffs = new Array();
        _tempMisc = new Array();

        // HELPER CLASSES: Initialize preview and slot managers (console added if enabled at build time)
        preview = new KazBarsPreview(this, rootClip);{console_init}
        slot = new KazBarsSlot(this, rootClip);{cast_init}{sw_init}

        initConfig();
    }}
"""

    def _expand_primary_ids(self, primary_ids):
        """Expand primary spell IDs to full ID lists (respecting stacking)."""
        ids = []
        for pid in primary_ids:
            entry = self.database.by_id.get(pid)
            if entry:
                entry_ids = entry.get("ids", [])
                if entry.get("stacking", False):
                    start = _stack_bound(entry.get("stackStart", 1), 1)
                    if entry.get("partialList", False):
                        for i, bid in enumerate(entry_ids):
                            self._stack_labels[bid] = start + i
                    else:
                        end = _stack_bound(entry.get("stackEnd", 0), len(entry_ids))
                        filtered = entry_ids[start - 1 : end]
                        for i, bid in enumerate(filtered):
                            self._stack_labels[bid] = start + i
                        entry_ids = filtered
                ids.extend(entry_ids)
            else:
                logger.warning("Primary ID %d not in database — skipped", pid)

        seen = set()
        result = []
        for bid in ids:
            if bid not in seen:
                seen.add(bid)
                result.append(bid)
        return sorted(result)

    def _resolve_grid(self, grid):
        resolved = dict(grid)
        whitelist = grid.get("whitelist", [])
        if whitelist:
            resolved["whitelist"] = self._expand_primary_ids(whitelist)
        slot_assignments = grid.get("slotAssignments", {})
        if slot_assignments:
            resolved_sa = {}
            for k, v in slot_assignments.items():
                if v:
                    resolved_sa[k] = self._expand_primary_ids(v)
                else:
                    resolved_sa[k] = v
            resolved["slotAssignments"] = resolved_sa
        return resolved

    def _init_config_stub(self):
        cast_cfg = "\n        castTimer.configure(d.CAST);" if self.include_cast_timer else ""
        sw_cfg = "\n        stopwatch.configure(d.SW);" if self.include_stopwatch else ""
        return f"""
    private function initConfig():Void {{
        var d:Object = KazBarsData.init();
        CFG = d.CFG;
        WL = d.WL;
        ISDEB = d.ISDEB;
        BUFFTYPE = d.BUFFTYPE;
        STACK_LEVEL = d.STACK_LEVEL;
        CUSTOMICON = d.CUSTOMICON;{cast_cfg}{sw_cfg}
    }}"""

    def _cast_data_block(self):
        """AS2 `d.CAST = {...}` literal for the cast-timer overlay. Color is
        emitted as a numeric hex literal (0xRRGGBB) so the stub's Number(...)
        coercion yields a real color, not NaN."""
        c = self.cast_config
        bp = "true" if c["enableP"] else "false"
        bt = "true" if c["enableT"] else "false"
        bd = "true" if c["bold"] else "false"
        return (
            "\n        d.CAST = {"
            f"enableP: {bp}, enableT: {bt}, "
            f"playerX: {int(c['playerX'])}, playerY: {int(c['playerY'])}, "
            f"targetX: {int(c['targetX'])}, targetY: {int(c['targetY'])}, "
            f"bold: {bd}, fontSize: {int(c['fontSize'])}, "
            f'display: "{c["display"]}", color: 0x{c["color"]}'
            "};"
        )

    def _stopwatch_data_block(self):
        """AS2 `d.SW = {...}` literal for the in-game stopwatch panel."""
        c = self.stopwatch_config
        collapsed = "true" if c["startCollapsed"] else "false"
        return f"\n        d.SW = {{x: {int(c['x'])}, y: {int(c['y'])}, collapsed: {collapsed}}};"

    def _data_class(self):
        lines = [
            """class KazBarsData {

    public static function init():Object {
        var d:Object = {};
        d.CFG = {};
        d.CFG.grids = new Array();
        d.WL = {};
        d.ISDEB = {};
        d.BUFFTYPE = {};
        d.STACK_LEVEL = {};
        d.CUSTOMICON = {};
        var i:Number;
"""
        ]

        if self.include_cast_timer:
            lines.append(self._cast_data_block())
        if self.include_stopwatch:
            lines.append(self._stopwatch_data_block())

        all_buff_ids = set()
        for idx, grid in enumerate(self.grids):
            resolved = self._resolve_grid(grid)
            lines.append(self._generate_grid_config(resolved, idx, var_prefix="d."))
            for bid in resolved.get("whitelist", []):
                all_buff_ids.add(bid)
            for slot_ids in resolved.get("slotAssignments", {}).values():
                for bid in slot_ids:
                    all_buff_ids.add(bid)

        if all_buff_ids:
            lines.append("\n        // Debuff, Type, and Stack Level lookup")
            for bid in sorted(all_buff_ids):
                is_deb = "true" if self.database.is_debuff(bid) else "false"
                buff_type = self.database.get_type(bid)
                lines.append(f"        d.ISDEB[{bid}] = {is_deb};")
                lines.append(f'        d.BUFFTYPE[{bid}] = "{buff_type}";')
                stack_level = self._stack_labels.get(bid)
                if stack_level is not None:
                    lines.append(f"        d.STACK_LEVEL[{bid}] = {stack_level};")
                if bid in CUSTOM_ICON_LINKAGE:
                    lines.append(f'        d.CUSTOMICON[{bid}] = "{CUSTOM_ICON_LINKAGE[bid]}";')

        lines.append("        return d;")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)

    def _generate_grid_config(self, grid, idx, var_prefix=""):
        gid = grid["id"]
        gid_lit = escape_as2_string(gid)
        vid = f"{self.sanitize_id(gid)}_{idx}"
        cfg = f"{var_prefix}CFG"
        wl = f"{var_prefix}WL"
        lines = []

        lines.append(f'''
        // {gid_lit}
        var {vid}:Object = {{
            id: "{gid_lit}",
            type: "{grid["type"]}",
            rows: {grid["rows"]},
            cols: {grid["cols"]},
            iconSize: {grid["iconSize"]},
            gap: {grid["gap"]},
            x: {grid["x"]},
            y: {grid["y"]},
            slotMode: "{grid["slotMode"]}",
            fillDir: "{grid["fillDirection"]}",
            sortOrder: "{grid["sortOrder"]}",
            layout: "{grid["layout"]}",
            showTimers: {"true" if grid["showTimers"] else "false"},
            timerFont: {grid.get("timerFontSize", 18)},
            timerFlashThreshold: {grid.get("timerFlashThreshold", 6)},
            timerYOffset: {grid.get("timerYOffset", 0)},
            stackFont: {grid.get("stackFontSize", 14)},
            enableFlashing: {"true" if grid.get("enableFlashing", True) else "false"}''')

        if grid["slotMode"] == "static":
            lines[-1] += ",\n            slots: {}\n        };"
            for slot_idx, buff_ids in grid.get("slotAssignments", {}).items():
                if buff_ids:
                    ids_str = ", ".join(str(bid) for bid in buff_ids)
                    lines.append(f"        {vid}.slots[{int(slot_idx)}] = [{ids_str}];")
        else:
            lines[-1] += "\n        };"

        lines.append(f"        {cfg}.grids.push({vid});")

        whitelist = grid.get("whitelist", [])
        if whitelist or grid["slotMode"] == "dynamic":
            lines.append(f'\n        {wl}["{gid_lit}"] = {{}};')
            if whitelist:
                ids_str = ", ".join(str(bid) for bid in whitelist)
                lines.append(f"        var {vid}_ids:Array = [{ids_str}];")
                lines.append(f'''        i = 0;
        while (i < {vid}_ids.length) {{
            {wl}["{gid_lit}"][{vid}_ids[i]] = true;
            i++;
        }}''')

        if grid["slotMode"] == "static":
            all_ids = set()
            for slot_ids in grid.get("slotAssignments", {}).values():
                all_ids.update(slot_ids)
            if all_ids:
                lines.append(f'\n        {wl}["{gid_lit}"] = {{}};')
                for bid in sorted(all_ids):
                    lines.append(f'        {wl}["{gid_lit}"][{bid}] = true;')

        return "\n".join(lines)

    def _core_methods(self):
        template = _load_core_template(self._assets_path)
        if self.include_console:
            tokens = {
                "{{CONSOLE_LOG_PLAYER}}": "if (console.isActive() && buff.m_Name != null) console.logPlayer(buff.m_Name, bid);",
                "{{CONSOLE_LOG_TARGET}}": "if (console.isActive() && buff.m_Name != null) console.logTarget(buff.m_Name, bid);",
                "{{CONSOLE_PREVIEW_OPEN}}": "if (!console.isActive()) console.createConsole();",
                "{{CONSOLE_EXIT_PERSIST}}": 'config.ReplaceEntry("console_pin", consolePinned ? 1 : 0);\n'
                '            config.ReplaceEntry("log_p", console.logPlayerEnabled ? 1 : 0);\n'
                '            config.ReplaceEntry("log_t", console.logTargetEnabled ? 1 : 0);',
                "{{CONSOLE_EXIT_REMOVE}}": "if (!consolePinned) console.removeConsole();",
                "{{CONSOLE_CLEANUP}}": "console.removeConsole();",
                "{{CONSOLE_LOAD_PERSIST}}": 'var cp:Object = config.FindEntry("console_pin");\n'
                "            if (cp !== undefined) consolePinned = (cp == 1);\n"
                '            var clp:Object = config.FindEntry("log_p");\n'
                "            if (clp !== undefined) console.logPlayerEnabled = (clp == 1);\n"
                '            var clt:Object = config.FindEntry("log_t");\n'
                "            if (clt !== undefined) console.logTargetEnabled = (clt == 1);\n"
                "            if (consolePinned) console.createConsole();",
                "{{CONSOLE_DEACTIVATE_PERSIST}}": 'config.ReplaceEntry("console_pin", consolePinned ? 1 : 0);\n'
                '            config.ReplaceEntry("log_p", console.logPlayerEnabled ? 1 : 0);\n'
                '            config.ReplaceEntry("log_t", console.logTargetEnabled ? 1 : 0);',
            }
        else:
            tokens = {
                "{{CONSOLE_LOG_PLAYER}}": "",
                "{{CONSOLE_LOG_TARGET}}": "",
                "{{CONSOLE_PREVIEW_OPEN}}": "",
                "{{CONSOLE_EXIT_PERSIST}}": "",
                "{{CONSOLE_EXIT_REMOVE}}": "",
                "{{CONSOLE_CLEANUP}}": "",
                "{{CONSOLE_LOAD_PERSIST}}": "",
                "{{CONSOLE_DEACTIVATE_PERSIST}}": "",
            }
        cast_token_names = (
            "{{CAST_CREATE}}",
            "{{CAST_DISCONNECT_P}}",
            "{{CAST_CONNECT_P}}",
            "{{CAST_SET_TARGET}}",
            "{{CAST_PREVIEW_ON}}",
            "{{CAST_PREVIEW_OFF}}",
            "{{CAST_LOAD}}",
            "{{CAST_SAVE}}",
            "{{CAST_CLEANUP}}",
        )
        if self.include_cast_timer:
            cast_tokens = {
                "{{CAST_CREATE}}": "castTimer.createFields();",
                "{{CAST_DISCONNECT_P}}": "castTimer.disconnectPlayer();",
                "{{CAST_CONNECT_P}}": "castTimer.connectPlayer(m_Player);",
                "{{CAST_SET_TARGET}}": "castTimer.setTarget(m_Target);",
                "{{CAST_PREVIEW_ON}}": "castTimer.previewOn();",
                "{{CAST_PREVIEW_OFF}}": "castTimer.previewOff();",
                "{{CAST_LOAD}}": "castTimer.loadPositions(config);",
                "{{CAST_SAVE}}": "castTimer.savePositions(config);",
                "{{CAST_CLEANUP}}": "castTimer.cleanup();",
            }
        else:
            cast_tokens = {name: "" for name in cast_token_names}
        tokens.update(cast_tokens)
        sw_token_names = (
            "{{SW_CREATE}}",
            "{{SW_LOAD}}",
            "{{SW_SAVE}}",
            "{{SW_CLEANUP}}",
        )
        if self.include_stopwatch:
            sw_tokens = {
                "{{SW_CREATE}}": "stopwatch.createPanel();",
                "{{SW_LOAD}}": "stopwatch.loadState(config);",
                "{{SW_SAVE}}": "stopwatch.saveState(config);",
                "{{SW_CLEANUP}}": "stopwatch.cleanup();",
            }
        else:
            sw_tokens = {name: "" for name in sw_token_names}
        tokens.update(sw_tokens)

        for token, replacement in tokens.items():
            template = template.replace(token, replacement)
        return template


# ============================================================================
# BUILD FUNCTION
# ============================================================================
def build_grids(
    grids: list,
    database,
    base_swf: str | Path,
    stubs_path: str | Path,
    output_swf: str | Path,
    compiler_path: str | Path,
    app_version: str = "3.6.0",
    assets_path=None,
    include_console: bool = False,
    cast_config: dict | None = None,
    stopwatch_config: dict | None = None,
) -> tuple[bool, str]:
    """
    Complete build process for KazBars.swf.

    Args:
        grids: List of grid configuration dicts
        database: BuffDatabase instance
        base_swf: Path to assets/kazbars/base.swf
        stubs_path: Path to assets/kazbars/stubs/
        output_swf: Path to write final KazBars.swf
        compiler_path: Path to mtasc.exe
        app_version: Version string for header comment

    Returns:
        (success: bool, message: str)
    """
    base_swf = Path(base_swf)
    stubs_path = Path(stubs_path)
    output_swf = Path(output_swf)
    compiler_path = Path(compiler_path)

    if not base_swf.exists():
        return False, f"KazBars base.swf not found:\n{base_swf}"
    if not compiler_path.exists():
        return False, f"MTASC compiler not found:\n{compiler_path}"

    temp_dir = None
    try:
        # Step 1: Generate AS2 code (main class + data class)
        generator = CodeGenerator(
            grids,
            database,
            app_version,
            assets_path=assets_path,
            include_console=include_console,
            cast_config=cast_config,
            stopwatch_config=stopwatch_config,
        )
        main_code, data_code = generator.generate()

        # Step 2: Write to temp .as files
        temp_dir = tempfile.mkdtemp(prefix="kazbars_")
        temp_main_as = Path(temp_dir) / "KazBars.as"
        temp_data_as = Path(temp_dir) / "KazBarsData.as"
        with open(temp_main_as, "w", encoding="utf-8") as f:
            f.write(main_code)
        with open(temp_data_as, "w", encoding="utf-8") as f:
            f.write(data_code)

        # Step 3: Copy base.swf to temp
        output_swf.parent.mkdir(parents=True, exist_ok=True)
        temp_swf = Path(temp_dir) / "KazBars.swf"
        shutil.copy2(base_swf, temp_swf)

        # Step 4: Compile (both main class and data class)
        common_stubs = base_swf.parent.parent / "common_stubs"
        ok, err = compile_as2(
            compiler_path,
            [stubs_path, common_stubs, temp_dir],
            temp_swf,
            [temp_main_as, temp_data_as],
            temp_dir,
        )
        if not ok:
            return False, f"MTASC compilation failed:\n{err}"

        # Step 5: Copy to game directory
        shutil.copy2(temp_swf, output_swf)

        output_size = output_swf.stat().st_size
        return True, f"KazBars.swf built successfully ({output_size:,} bytes)"

    except Exception as e:
        logger.exception("build_grids failed")
        return False, f"Build error: {e!s}"
    finally:
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except OSError as cleanup_err:
                logger.warning("temp dir cleanup failed: %s", cleanup_err)
