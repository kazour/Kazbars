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
from .grid_model import DEFAULT_GAME_RESOLUTION, MAX_TOTAL_SLOTS, project_px
from .inspect import validate_config as validate_inspect_config
from .prefs import validate_panel_font_size
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


def _load_template(assets_path=None):
    """Load the AS2 main-class template from external file (cached)."""
    base = resolve_assets_path(assets_path)
    template_path = base / "kazbars" / "KazBars.as.template"
    key = str(template_path)
    if key not in _template_cache:
        with open(template_path, encoding="utf-8") as f:
            _template_cache[key] = f.read()
    return _template_cache[key]


def _apply_feature_gates(template, flags):
    """Keep or strip the template's ``//#if FLAG ... //#end`` blocks: body lines
    stay verbatim when the flag is on, the whole block disappears when it is
    off, and marker lines (which may carry a trailing comment) never reach the
    output. Deliberately capped: exactly the four build-gate flags, no nesting,
    no else — a need for more is a design change, not a preprocessor patch."""
    out = []
    active = None
    keep = True
    for i, line in enumerate(template.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith("//#if"):
            if active is not None:
                raise ValueError(f"nested //#if at template line {i}")
            flag = stripped[5:].strip().split(" ", 1)[0]
            if flag not in flags:
                raise ValueError(f"unknown feature flag {flag!r} at template line {i}")
            active = flag
            keep = flags[flag]
        elif stripped.startswith("//#end"):
            if active is None:
                raise ValueError(f"stray //#end at template line {i}")
            active = None
            keep = True
        elif keep:
            out.append(line)
    if active is not None:
        raise ValueError(f"unclosed //#if {active}")
    return "\n".join(out)


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


def _as_list(value):
    """Normalize a whitelist/slot-assignment value that may be a bare scalar
    (an imported or hand-edited profile can carry one known id instead of a
    list) into a list — the shape `_expand_primary_ids` and the unresolved-ref
    scan both need."""
    return value if isinstance(value, list) else [value]


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
        inspect_config=None,
        panel_font_size=None,
        game_resolution=None,
    ):
        """Initialize the code generator with grid configs and the buff database."""
        # Filter out disabled grids
        self.grids = [g for g in grids if g.get("enabled", True)]
        self.database = database
        self.app_version = app_version
        self._assets_path = assets_path
        self._stack_labels = {}
        self.include_console = include_console
        # Grid and extras positions are stored as fractions; bake-time is the projection
        # boundary — the emitted AS2 carries px at this resolution.
        game_w, game_h = game_resolution or DEFAULT_GAME_RESOLUTION
        self.game_w = int(game_w)
        self.game_h = int(game_h)
        # Cast-timer overlay: validated config + build gate. include_cast_timer is
        # False unless the player or target timer is enabled, so the SWF carries no
        # cast-timer code when the feature is off (mirrors include_console).
        self.cast_config = validate_cast_config(cast_config)
        self.include_cast_timer = cast_is_enabled(self.cast_config)
        # In-game stopwatch: same gate pattern — off means no stopwatch code compiles.
        self.stopwatch_config = validate_stopwatch_config(stopwatch_config)
        self.include_stopwatch = self.stopwatch_config["enabled"]
        # Target inspect panel: same gate pattern again.
        self.inspect_config = validate_inspect_config(inspect_config)
        self.include_inspect = self.inspect_config["enabled"]
        # Shared text size for the four in-game panels. The console and the
        # preview control panel have no config of their own and always take it;
        # the stopwatch and inspect panel take it unless their own fontSize is
        # set. Baking is the only place the two are resolved into one number.
        self.panel_font_size = validate_panel_font_size(panel_font_size)

    def sanitize_id(self, grid_id):
        """Convert a grid ID to a safe AS2 identifier by replacing invalid characters."""
        safe = ""
        for c in grid_id:
            if (c.isascii() and c.isalnum()) or c == "_":
                safe += c
            else:
                safe += "_"
        if safe and safe[0].isdigit():
            safe = "_" + safe
        return safe or "Grid"

    def _archive_key(self, grid_id):
        """Stable per-build archive key for a grid's persisted position — a
        sanitized id, deduped against every other key already emitted this
        generate() call (two ids that sanitize the same way, e.g. "a-b" and
        "a b", still need distinct archive slots)."""
        base = self.sanitize_id(grid_id)
        key = base
        suffix = 2
        while key in self._used_keys:
            key = f"{base}_{suffix}"
            suffix += 1
        self._used_keys.add(key)
        return key

    def generate(self):
        """Generate the main KazBars.as and separate KazBarsData.as source code."""
        # Archive keys are stable across a rebuild only within one generate()
        # call — reset here so re-using a CodeGenerator instance can't leak
        # collision suffixes from a previous run into this one.
        self._used_keys: set[str] = set()
        # Main class: the whole hand-written class lives in KazBars.as.template;
        # the generator only fills feature tokens (no inline config — the class
        # calls KazBarsData.init())
        main = []
        main.append(self._header())
        main.append(self._main_class())

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

    def _expand_primary_ids(self, primary_ids):
        """Expand primary spell IDs to full ID lists (respecting stacking)."""
        ids = []
        for pid in primary_ids:
            try:
                entry = self.database.by_id.get(pid)
            except TypeError:
                # A hand-edited or imported profile can carry a malformed
                # (unhashable) ref, e.g. a nested object in place of an id —
                # inert, same as any other id the database doesn't know.
                entry = None
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
                # Inert ref (see unresolved_refs) — skipped from the emitted
                # tables; %s because a preserved legacy ref can be a name string.
                logger.warning("Primary ID %s not in database — skipped", pid)

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
                resolved_sa[k] = self._expand_primary_ids(_as_list(v)) if v else v
            resolved["slotAssignments"] = resolved_sa
        return resolved

    def _resolved_font_size(self, config):
        """The size actually baked for one panel: its own `fontSize` when it set
        one, otherwise the shared `panel_font_size`. The single place the shared
        value and a per-panel override are collapsed into one number."""
        own = config.get("fontSize")
        return self.panel_font_size if own is None else int(own)

    def _panel_font_data_block(self):
        """AS2 `d.PF = {...}` literal — the shared panel text size, for the two
        panels with no config of their own to override it from, plus the app
        version the control panel's footer credit shows. Emitted
        unconditionally: `KazBarsPreviewPanel` is not gated and compiles into
        every build."""
        return (f"\n        d.PF = {{fontSize: {self.panel_font_size}, "
                f'version: "{escape_as2_string(self.app_version)}"}};')

    def _cast_data_block(self):
        """AS2 `d.CAST = {...}` literal for the cast-timer overlay. Positions
        are stored as fractions and projected to px here (the AS2 side keys
        stay playerX/…). Color is emitted as a numeric hex literal (0xRRGGBB)
        so the stub's Number(...) coercion yields a real color, not NaN."""
        c = self.cast_config
        bp = "true" if c["enableP"] else "false"
        bt = "true" if c["enableT"] else "false"
        bd = "true" if c["bold"] else "false"
        return (
            "\n        d.CAST = {"
            f"enableP: {bp}, enableT: {bt}, "
            f"playerX: {project_px(c['playerFx'], self.game_w)}, "
            f"playerY: {project_px(c['playerFy'], self.game_h)}, "
            f"targetX: {project_px(c['targetFx'], self.game_w)}, "
            f"targetY: {project_px(c['targetFy'], self.game_h)}, "
            f"bold: {bd}, fontSize: {int(c['fontSize'])}, "
            f'display: "{c["display"]}", color: 0x{c["color"]}'
            "};"
        )

    def _stopwatch_data_block(self):
        """AS2 `d.SW = {...}` literal for the in-game stopwatch panel. The
        stored fraction position projects to px here."""
        c = self.stopwatch_config
        collapsed = "true" if c["startCollapsed"] else "false"
        return (
            f"\n        d.SW = {{x: {project_px(c['fx'], self.game_w)}, "
            f"y: {project_px(c['fy'], self.game_h)}, "
            f"fontSize: {self._resolved_font_size(c)}, collapsed: {collapsed}}};"
        )

    def _inspect_data_block(self):
        """AS2 `d.INS = {...}` literal for the target inspect panel. The
        stored fraction position projects to px here."""
        c = self.inspect_config
        collapsed = "true" if c["startCollapsed"] else "false"
        show_pvp = "true" if c["showPvp"] else "false"
        show_perks = "true" if c["showPerks"] else "false"
        return (
            f"\n        d.INS = {{x: {project_px(c['fx'], self.game_w)}, "
            f"y: {project_px(c['fy'], self.game_h)}, "
            f"fontSize: {self._resolved_font_size(c)}, collapsed: {collapsed}, "
            f"showPvp: {show_pvp}, showPerks: {show_perks}}};"
        )

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

        lines.append(self._panel_font_data_block())
        if self.include_cast_timer:
            lines.append(self._cast_data_block())
        if self.include_stopwatch:
            lines.append(self._stopwatch_data_block())
        if self.include_inspect:
            lines.append(self._inspect_data_block())

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
        key = self._archive_key(gid)
        cfg = f"{var_prefix}CFG"
        wl = f"{var_prefix}WL"
        lines = []

        lines.append(f'''
        // {gid_lit}
        var {vid}:Object = {{
            id: "{gid_lit}",
            key: "{key}",
            type: "{grid["type"]}",
            rows: {grid["rows"]},
            cols: {grid["cols"]},
            iconSize: {grid["iconSize"]},
            gap: {grid["gap"]},
            x: {project_px(grid["fx"], self.game_w)},
            y: {project_px(grid["fy"], self.game_h)},
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

    def _main_class(self):
        template = _load_template(self._assets_path)
        return _apply_feature_gates(template, {
            "CONSOLE": self.include_console,
            "CAST": self.include_cast_timer,
            "SW": self.include_stopwatch,
            "INS": self.include_inspect,
        })


def unresolved_refs(grids, database) -> list:
    """Every ref in the enabled grids' whitelists/slot assignments the database
    can't resolve — exactly what `_expand_primary_ids` will skip at emit. Pure;
    `build_action` runs it pre-build so the summary can report the count. int
    refs check `by_id`, preserved legacy strings check by name; deduped, first
    occurrence order."""
    out: list = []
    seen: set = set()
    for g in grids:
        if not g.get('enabled', True):
            continue
        refs = list(g.get('whitelist') or [])
        for val in (g.get('slotAssignments') or {}).values():
            if val:
                refs.extend(_as_list(val))
        for ref in refs:
            if isinstance(ref, bool) or ref in seen:
                continue
            if isinstance(ref, int):
                if database.by_id.get(ref):
                    continue
            elif isinstance(ref, str):
                if database.get_entry_by_name(ref):
                    continue
            else:
                continue
            seen.add(ref)
            out.append(ref)
    return out


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
    inspect_config: dict | None = None,
    panel_font_size: int | None = None,
    game_resolution: tuple[int, int] | None = None,
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
            inspect_config=inspect_config,
            panel_font_size=panel_font_size,
            game_resolution=game_resolution,
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
