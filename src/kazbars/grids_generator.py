"""
KazBars — KazBars Code Generator
Generates KazBars.as ActionScript 2.0 source code from grid configurations.
"""

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from . import inspect_catalog, onslaught
from .build_utils import compile_as2, resolve_assets_path
from .cast_timer import is_enabled as cast_is_enabled
from .cast_timer import validate_config as validate_cast_config
from .console import ships as console_ships
from .console import validate_config as validate_console_config
from .grid_model import DEFAULT_GAME_RESOLUTION, is_band, is_plate, project_px
from .inspect import validate_config as validate_inspect_config
from .overlay import VERDANA, as2_face, font_slug
from .overlay import validate_config as validate_overlay
from .overlay_size import cast_fs, grid_metrics, panel_fs
from .prefs import ANCHOR_SIDE_DEFAULT, ANCHOR_UP_DEFAULT
from .stopwatch import validate_config as validate_stopwatch_config
from .swf_font import SwfFontError, import_game_font, splice

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

# as2c caps every class at 32 KB of bytecode. The grid configs and custom icons
# are packed into KazBarsData1..N, each built from whole units up to
# this many source chars. Measured AVM1 density is ~0.6 byte per source char
# and the pessimistic bound (no push merging) is 1.0, so 24K chars keeps at
# least 1.36x headroom under the cap. Don't raise it.
DATA_CHUNK_BUDGET = 24_000


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
    output. A marker names one flag; an unknown flag, a nested //#if, a stray
    //#end or an unclosed block is a template bug and fails the build. No
    nesting, no else."""
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


def sanitize_id(grid_id):
    """A grid id as a safe AS2 identifier: ASCII alphanumerics and `_` kept,
    every other character `_`, a leading digit prefixed with `_`, empty → `Grid`."""
    safe = "".join(c if (c.isascii() and c.isalnum()) or c == "_" else "_" for c in grid_id)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe or "Grid"


def free_id(taken, base):
    """`base`, or `base_2`, `base_3`, …: the first whose in-game archive key
    (`sanitize_id`) no id in `taken` makes (`Buffs DT` and `Buffs_DT` are one
    key), so a copied grid gets saved positions of its own."""
    keys = {sanitize_id(t) for t in taken}
    grid_id, n = base, 2
    while sanitize_id(grid_id) in keys:
        grid_id = f"{base}_{n}"
        n += 1
    return grid_id


def fact_code(btype, stack):
    """An id's facts for one grid, the value of `d.WL[gid][id]`: bits 0-1 its
    type (1 buff, 2 debuff, 3 misc; any other word is a buff), bits 2-11 its
    stack level (0: not stacking; capped at 1023), bits 12 and up its stacking
    family's index in the grid (1-based; 0 none). `stack` is (level, family
    index), or None for an id that does not stack."""
    t = {"debuff": 2, "misc": 3}.get(btype, 1)
    level, family = stack or (0, 0)
    return t | (max(0, min(level, 1023)) << 2) | (family << 12)


def grid_ships(grid):
    """A grid is baked only when enabled and tracking something: a dynamic grid
    a whitelist entry, a static one a buff in a slot inside its shape. An empty
    grid is left out as it is, never turned off."""
    if not grid.get("enabled", True):
        return False
    if grid.get("slotMode") != "static":
        return bool(grid.get("whitelist"))
    cells = grid.get("rows", 1) * grid.get("cols", 1)
    for key, value in (grid.get("slotAssignments") or {}).items():
        try:
            inside = 0 <= int(key) < cells
        except (TypeError, ValueError):
            inside = False
        if inside and value:
            return True
    return False


def _as_list(value):
    """Normalize a whitelist/slot-assignment value that may be a bare scalar
    (an imported or hand-edited profile can carry one known id instead of a
    list) into a list — the shape `_expand_primary_ids` and the unresolved-ref
    scan both need."""
    return value if isinstance(value, list) else [value]


def _pack_units(units, budget):
    """Greedy split of consecutive source units into chunks whose joined
    (newline-separated) source stays within `budget` chars; a unit bigger
    than the budget gets a chunk of its own."""
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for unit in units:
        if current and size + len(unit) > budget:
            chunks.append(current)
            current, size = [], 0
        current.append(unit)
        size += len(unit) + 1
    if current:
        chunks.append(current)
    return chunks


def _stack_bound(value, fallback):
    """Coerce a stackStart/stackEnd from an imported/hand-edited entry the way
    the other loaders coerce ints (numeric strings count, junk falls back), so
    the slice in `_expand_primary_ids` can't go negative or raise."""
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return value if value >= 1 else fallback


def _bool(value):
    return "true" if value else "false"


class CodeGenerator:
    """Generate AS2 source code for the KazBars buff-tracking grid system."""

    def __init__(
        self,
        grids,
        database,
        app_version,
        assets_path=None,
        cast_config=None,
        stopwatch_config=None,
        inspect_config=None,
        console_config=None,
        onslaught_config=None,
        overlay=None,
        anchor=None,
        game_resolution=None,
    ):
        """Initialize the code generator with grid configs and the buff database."""
        # Bands last, stable: KazBarsOverhead stacks a character's views in bake
        # order, so its static grids sit at the bottom against the nameplate
        # and the bands above them. Screen grids keep their order.
        self.grids = sorted((g for g in grids if grid_ships(g)), key=is_band)
        self.include_overhead = any(is_plate(g["type"]) for g in self.grids)
        self.database = database
        self.app_version = app_version
        self._assets_path = assets_path
        # Grid and extras positions are stored as fractions; bake-time is the projection
        # boundary — the emitted AS2 carries px at this resolution.
        game_w, game_h = game_resolution or DEFAULT_GAME_RESOLUTION
        self.game_w = int(game_w)
        self.game_h = int(game_h)
        # The profile's base size and face: every size baked below derives from
        # the base size and the module's own scale (overlay_size).
        self.overlay = validate_overlay(overlay)
        self.base_size = self.overlay["size"]
        # The overhead anchor (this PC's prefs, never the profile's).
        self.anchor = anchor or (ANCHOR_SIDE_DEFAULT, ANCHOR_UP_DEFAULT)
        # Each extra's validated config and build gate: off means none of its
        # code compiles into the SWF.
        self.cast_config = validate_cast_config(cast_config)
        self.include_cast_timer = cast_is_enabled(self.cast_config)
        self.stopwatch_config = validate_stopwatch_config(stopwatch_config)
        self.include_stopwatch = self.stopwatch_config["enabled"]
        self.inspect_config = validate_inspect_config(inspect_config)
        self.include_inspect = self.inspect_config["enabled"]
        self.console_config = validate_console_config(console_config)
        self.include_console = console_ships(self.console_config)
        self.onslaught_config = onslaught.validate_config(onslaught_config)
        self.include_onslaught = onslaught.ships(self.onslaught_config)

    def _archive_key(self, grid_id):
        """Stable per-build archive key for a grid's persisted position — a
        sanitized id, deduped against every other key already emitted this
        generate() call (two ids that sanitize the same way, e.g. "a-b" and
        "a b", still need distinct archive slots)."""
        base = sanitize_id(grid_id)
        key = base
        suffix = 2
        while key in self._used_keys:
            key = f"{base}_{suffix}"
            suffix += 1
        self._used_keys.add(key)
        return key

    def generate_files(self):
        """Every AS2 source of a build as `(file name, source)`, main class
        first: `KazBars.as` (the hand-written template with its feature gates
        applied — the class calls `KazBarsData.init()`), `KazBarsData.as`
        (init + feature blocks, calling each chunk in turn), then
        `KazBarsData1..N.as` — the grid configs and custom icons packed under
        DATA_CHUNK_BUDGET per class so no profile hits as2c's per-class
        bytecode cap. as2c binds file name == class name."""
        # Archive keys are stable across a rebuild only within one call —
        # reset here so re-using a CodeGenerator instance can't leak collision
        # suffixes from a previous run into this one.
        self._used_keys: set[str] = set()
        header = self._header()
        chunks = _pack_units(self._data_units(), DATA_CHUNK_BUDGET)
        files = [
            ("KazBars.as", self._main_class()),
            ("KazBarsData.as", self._data_class(len(chunks))),
        ]
        for n, units in enumerate(chunks, start=1):
            files.append((f"KazBarsData{n}.as", self._data_chunk_class(n, units)))
        return [(name, f"{header}\n{src}") for name, src in files]

    def generate(self):
        """`(KazBars.as source, every data class joined)` — for callers that
        only inspect the emitted text."""
        files = self.generate_files()
        return files[0][1], "\n".join(src for _, src in files[1:])

    def _header(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""// ============================================================================
// KZGRIDS - Generated by KazBars v{self.app_version}
// Generated: {timestamp}
// Grids: {len(self.grids)}
// ============================================================================
"""

    def _expand_primary_ids(self, primary_ids, labels):
        """Refs → full id lists (stacking respected), deduped, ascending. Each
        stacking id's (level, family) goes into `labels`, the family named by
        the first id of its entry."""
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
                    family = entry_ids[0] if entry_ids else 0
                    if not entry.get("partialList", False):
                        end = _stack_bound(entry.get("stackEnd", 0), len(entry_ids))
                        entry_ids = entry_ids[start - 1 : end]
                    for i, bid in enumerate(entry_ids):
                        labels[bid] = (start + i, family)
                ids.extend(entry_ids)
            else:
                # Inert ref (see unresolved_refs) — skipped from the emitted
                # tables; %s because a preserved legacy ref can be a name string.
                logger.warning("Primary ID %s not in database — skipped", pid)
        return sorted(set(ids))

    def _fact_codes(self, ids, labels):
        """The grid's id set as (id, fact code), ascending. A stacking family's
        index is its rank by its lowest id in the grid."""
        families: dict = {}
        codes = []
        for bid in sorted(set(ids)):
            stack = None
            if bid in labels:
                level, family = labels[bid]
                stack = (level, families.setdefault(family, len(families) + 1))
            codes.append((bid, fact_code(self.database.get_type(bid), stack)))
        return codes

    def _panel_font_data_block(self):
        """AS2 `d.PF = {...}` literal — the base size itself (the preview
        control panel and the layout-preview labels are drawn at it), the face
        every text field asks for, the version the control panel's footer
        credits, and the overhead anchor (`KazBarsRelations.side` / `.lift`).
        Emitted unconditionally: `KazBarsPreviewPanel` is not gated and
        compiles into every build."""
        side, up = self.anchor
        return (f"\n        d.PF = {{fontSize: {self.base_size}, "
                f'face: "{as2_face(self.overlay["font"])}", '
                f'version: "{escape_as2_string(self.app_version)}", '
                f"side: {int(side)}, up: {int(up)}}};")

    def _cast_data_block(self):
        """AS2 `d.CAST = {...}` literal for the cast-timer overlay. Positions
        are stored as fractions and projected to px here (the AS2 side keys
        stay playerX/…). Color is emitted as a numeric hex literal (0xRRGGBB)
        so the stub's Number(...) coercion yields a real color, not NaN."""
        c = self.cast_config
        return (
            "\n        d.CAST = {"
            f"enableP: {_bool(c['enableP'])}, enableT: {_bool(c['enableT'])}, "
            f"playerX: {project_px(c['playerFx'], self.game_w)}, "
            f"playerY: {project_px(c['playerFy'], self.game_h)}, "
            f"targetX: {project_px(c['targetFx'], self.game_w)}, "
            f"targetY: {project_px(c['targetFy'], self.game_h)}, "
            f"bold: {_bool(c['bold'])}, fontSize: {cast_fs(self.base_size, c['scale'])}, "
            f'display: "{c["display"]}", color: 0x{c["color"]}'
            "};"
        )

    def _stopwatch_data_block(self):
        """AS2 `d.SW = {...}` literal for the in-game stopwatch panel. The
        stored fraction position projects to px here."""
        c = self.stopwatch_config
        return (
            f"\n        d.SW = {{x: {project_px(c['fx'], self.game_w)}, "
            f"y: {project_px(c['fy'], self.game_h)}, "
            f"fontSize: {panel_fs(self.base_size, c['scale'])}, "
            f"collapsed: {_bool(c['startCollapsed'])}}};"
        )

    def _inspect_data_block(self):
        """AS2 `d.INS = {...}` literal for the target inspect panel. The
        stored fraction position projects to px here."""
        c = self.inspect_config
        return (
            f"\n        d.INS = {{x: {project_px(c['fx'], self.game_w)}, "
            f"y: {project_px(c['fy'], self.game_h)}, "
            f"fontSize: {panel_fs(self.base_size, c['scale'])}, "
            f"collapsed: {_bool(c['startCollapsed'])}}};"
        )

    def _inspect_rows_block(self):
        """`d.INS.groups` / `.rows` / `.watch`: the groups that own a shown row
        (`{n, p}`, p the PvP player gate), the rows in the panel's order (`g`
        indexing those groups, `l` the label, then the row's own AS2 fields),
        and every id they read plus the always-polled ones."""
        selected = inspect_catalog.shown(self.inspect_config["rows"])
        groups: list = []
        for r in selected:
            if r.group not in groups:
                groups.append(r.group)
        groups_line = "        d.INS.groups = [{}];".format(", ".join(
            f'{{n: "{g.label}", p: {_bool(g.player_gated)}}}' for g in groups))
        if selected:
            entries = ",\n".join(
                f'            {{g: {groups.index(r.group)}, l: "{escape_as2_string(r.label)}", '
                f'{r.as2_fields()}}}' for r in selected)
            rows_lines = f"        d.INS.rows = [\n{entries}\n        ];"
        else:
            rows_lines = "        d.INS.rows = [];"
        watch = ", ".join(str(i) for i in inspect_catalog.watch_ids(selected))
        return f"\n{groups_line}\n{rows_lines}\n        d.INS.watch = [{watch}];"

    def _pvp_view_block(self):
        """`d.INS.pvp`, the PvP tab's fixed view: `groups` (`{n: title, c:
        [column titles]}`), `rows` (as `d.INS.rows`, `l` the view's own label)
        and `ids` (what the view reads plus the always-polled ids; not
        `watch`, a method every AS2 object has)."""
        groups = ", ".join(
            "{{n: \"{}\", c: [{}]}}".format(title, ", ".join(f'"{c}"' for c in cols))
            for title, cols, _ in inspect_catalog.PVP_VIEW)
        labels = [(g, label) for g, (_, _, lines) in enumerate(inspect_catalog.PVP_VIEW)
                  for label, _ in lines]
        rows = ", ".join(
            f'{{g: {g}, l: "{escape_as2_string(label)}", {row.as2_fields()}}}'
            for (g, label), row in zip(labels, inspect_catalog.pvp_rows()))
        ids = ", ".join(str(i) for i in inspect_catalog.watch_ids(inspect_catalog.pvp_rows()))
        return f"\n        d.INS.pvp = {{groups: [{groups}], rows: [{rows}], ids: [{ids}]}};"

    def _onslaught_data_block(self):
        """`d.ONS`: the board's and the alerts' first-load spots (fixed
        fractions — both are placed in game), the text size and displays;
        `d.ONS.watch`, one array per kind (`b`, `s`, `m`, `c`), each the watched
        names of that kind, a kind no display reads left empty (bosses, skulls
        and minis feed the list and the alerts, camps only the list); the AoE
        helpers, the heal buffs and the per-playfield facts."""
        c = self.onslaught_config

        def quoted(names):
            return ", ".join(f'"{escape_as2_string(n)}"' for n in names)

        def names(kind, wanted):
            return quoted(onslaught.names_of(c, kind)) if wanted else ""

        listed = c["showList"] or c["showAlerts"]
        lines = [
            f"        d.ONS = {{x: {project_px(1560 / 1920, self.game_w)}, "
            f"y: {project_px(300 / 1080, self.game_h)}, "
            f"ax: {project_px(960 / 1920, self.game_w)}, ay: {project_px(200 / 1080, self.game_h)}, "
            f"fontSize: {panel_fs(self.base_size, c['scale'])}, list: {_bool(c['showList'])}, "
            f"alerts: {_bool(c['showAlerts'])}, wave: {_bool(c['showWave'])}, "
            f"aoe: {_bool(c['showAoe'])}, ally: {_bool(c['showAlly'])}, "
            f"alertMs: {c['alertSeconds'] * 1000}}};",
            "        d.ONS.watch = {",
            f"            b: [{names(onslaught.BOSS, listed)}],",
            f"            s: [{names(onslaught.SKULL, listed)}],",
            f"            m: [{names(onslaught.MINI, listed)}],",
            f"            c: [{names(onslaught.CAMP, c['showList'])}]",
            "        };",
            f"        d.ONS.helpers = [{quoted(onslaught.AOE_HELPERS)}];",
            f"        d.ONS.heal = [{quoted(onslaught.HEAL_BUFFS)}];",
            "        d.ONS.pf = {};",
        ]
        lines += [f'        d.ONS.pf[{i.playfield}] = {{start: "{escape_as2_string(i.start_hint)}", '
                  f'spawnMs: {i.spawn_ms}, ally: "{escape_as2_string(i.ally)}", aoe: {_bool(i.aoe)}}};'
                  for i in onslaught.INSTANCES]
        return "\n" + "\n".join(lines)

    def _console_data_block(self):
        """`d.CON`: the console's text size and its tabs in the strip's order."""
        c = self.console_config
        tabs = ", ".join(f'"{t}"' for t in c["tabs"])
        return (f"\n        d.CON = {{fontSize: {panel_fs(self.base_size, c['scale'])}, "
                f"tabs: [{tabs}]}};")

    def _data_units(self):
        """The data-class body as self-contained source units, in emit order:
        one per grid (its config and its id set with each id's facts), then one
        per custom icon. A unit never splits across chunks, so a `while` loop
        stays whole. `_archive_key` claims keys as it goes, so one pass."""
        units = []
        icons: set[int] = set()
        for idx, grid in enumerate(self.grids):
            labels: dict = {}
            whitelist = self._expand_primary_ids(grid.get("whitelist", []), labels)
            slots = {
                k: self._expand_primary_ids(_as_list(v), labels) if v else []
                for k, v in grid.get("slotAssignments", {}).items()
            }
            if grid["slotMode"] == "static":
                ids = [bid for slot_ids in slots.values() for bid in slot_ids]
            else:
                ids = whitelist
            codes = self._fact_codes(ids, labels)
            icons.update(bid for bid, _ in codes if bid in CUSTOM_ICON_LINKAGE)
            units.append(self._generate_grid_config(grid, idx, slots, codes))
        for bid in sorted(icons):
            units.append(f'        d.CUSTOMICON[{bid}] = "{CUSTOM_ICON_LINKAGE[bid]}";')
        return units

    def _data_chunk_class(self, n, units):
        """One `KazBarsData<n>` class filling `d` with a run of units. `i` is
        declared unconditionally — as2c rejects an assignment to an
        undeclared var, an unused local is fine."""
        body = "\n".join(units)
        return f"""class KazBarsData{n} {{

    public static function fill(d:Object):Void {{
        var i:Number;
{body}
    }}
}}"""

    def _data_class(self, chunk_count):
        lines = [
            """class KazBarsData {

    public static function init():Object {
        var d:Object = {};
        d.CFG = {};
        d.CFG.grids = new Array();
        d.WL = {};
        d.CUSTOMICON = {};"""
        ]

        lines.append(self._panel_font_data_block())
        if self.include_cast_timer:
            lines.append(self._cast_data_block())
        if self.include_stopwatch:
            lines.append(self._stopwatch_data_block())
        if self.include_inspect:
            lines.append(self._inspect_data_block())
            lines.append(self._inspect_rows_block())
            lines.append(self._pvp_view_block())
        if self.include_onslaught:
            lines.append(self._onslaught_data_block())
        if self.include_console:
            lines.append(self._console_data_block())

        if chunk_count:
            lines.append("")
        for n in range(1, chunk_count + 1):
            lines.append(f"        KazBarsData{n}.fill(d);")

        lines.append("        return d;")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)

    def _generate_grid_config(self, grid, idx, slots, codes):
        """One grid's unit: its config object, its static slots, and its id set
        `d.WL[gid]` as `[id, code, …]` pairs read in by a loop. A dynamic grid
        gets its set even empty (the pick reads it), a static one only with
        ids. `iconSize`, `timerFont` and `stackFont` are the on-screen values
        `grid_metrics` derives from the base size and the grid's scale."""
        gid = grid["id"]
        gid_lit = escape_as2_string(gid)
        vid = f"{sanitize_id(gid)}_{idx}"
        key = self._archive_key(gid)
        m = grid_metrics(self.base_size, grid["scale"])
        is_static = grid["slotMode"] == "static"
        lines = []

        unit = f'''
        // {gid_lit}
        var {vid}:Object = {{
            id: "{gid_lit}",
            key: "{key}",
            type: "{grid["type"]}",
            rows: {grid["rows"]},
            cols: {grid["cols"]},
            iconSize: {m.icon},
            gap: {grid["gap"]},
            x: {project_px(grid["fx"], self.game_w)},
            y: {project_px(grid["fy"], self.game_h)},
            slotMode: "{grid["slotMode"]}",
            fillDir: "{grid["fillDirection"]}",
            sortOrder: "{grid["sortOrder"]}",
            layout: "{grid["layout"]}",
            timerStyle: "{grid["timerStyle"]}",
            timerFont: {m.timer},
            timerFlashThreshold: {grid["timerFlashThreshold"]},
            timerYOffset: {grid["timerYOffset"]},
            stackFont: {m.stack},
            enableFlashing: {_bool(grid["enableFlashing"])}'''
        # Only where they apply, so a screen grid without selfCastOnly bakes as before.
        if is_plate(grid["type"]):
            unit += (f",\n            plateOffset: {grid['plateOffset']},"
                     f"\n            maxDistance: {grid['maxDistance']}")
            # A band: rows x cols are its derived shape (cols the row cap), fillDir "C".
            if is_band(grid):
                unit += f",\n            maxSlots: {grid['maxSlots']}"
        if grid["type"] == "friendly":
            unit += f",\n            showSelf: {_bool(grid['showSelf'])}"
        if grid.get("selfCastOnly") is True:
            unit += ",\n            selfCastOnly: true"
        if "class" in grid:
            unit += f",\n            cls: {grid['class']}"

        if is_static:
            lines.append(unit + ",\n            slots: {}\n        };")
            for slot_idx, buff_ids in slots.items():
                if buff_ids:
                    ids_str = ", ".join(str(bid) for bid in buff_ids)
                    lines.append(f"        {vid}.slots[{int(slot_idx)}] = [{ids_str}];")
        else:
            lines.append(unit + "\n        };")
        lines.append(f"        d.CFG.grids.push({vid});")

        if not is_static or codes:
            lines.append(f'\n        d.WL["{gid_lit}"] = {{}};')
        if codes:
            pairs = ", ".join(f"{bid}, {code}" for bid, code in codes)
            lines.append(f"        var {vid}_ids:Array = [{pairs}];")
            lines.append(f'''        i = 0;
        while (i < {vid}_ids.length) {{
            d.WL["{gid_lit}"][{vid}_ids[i]] = {vid}_ids[i + 1];
            i += 2;
        }}''')
        return "\n".join(lines)

    def _main_class(self):
        template = _load_template(self._assets_path)
        return _apply_feature_gates(template, {
            "CONSOLE": self.include_console,
            "CONBUFFS": self.include_console and "buffs" in self.console_config["tabs"],
            "CONCASTS": self.include_console and "casts" in self.console_config["tabs"],
            "CAST": self.include_cast_timer,
            "INS": self.include_inspect,
            "ONS": self.include_onslaught,
            "PLATE": self.include_overhead,
            "SW": self.include_stopwatch,
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
def font_base(base_swf: Path, font: str) -> bytes:
    """The SWF the compiler injects into for the overlay `font`: `base.swf` as
    shipped for Arial; for the game's Verdana, `base.swf` importing it in place
    of its two Arials; for a baked face, `base.swf` with that face's outlines
    (`fonts/<slug>.bin` beside it) spliced over them. The AS2 is the same for
    every font — only `d.PF.face` names Verdana's `_StandardFont`."""
    base = base_swf.read_bytes()
    if font == VERDANA:
        return import_game_font(base)
    slug = font_slug(font)
    if slug is None:
        return base
    return splice(base, (base_swf.parent / "fonts" / f"{slug}.bin").read_bytes())


def build_grids(
    grids: list,
    database,
    base_swf: str | Path,
    stubs_path: str | Path,
    output_swf: str | Path,
    app_version: str = "3.6.0",
    assets_path=None,
    cast_config: dict | None = None,
    stopwatch_config: dict | None = None,
    inspect_config: dict | None = None,
    console_config: dict | None = None,
    onslaught_config: dict | None = None,
    overlay: dict | None = None,
    anchor: tuple[int, int] | None = None,
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
        app_version: Version string for header comment

    Returns:
        (success: bool, message: str)
    """
    base_swf = Path(base_swf)
    stubs_path = Path(stubs_path)
    output_swf = Path(output_swf)

    if not base_swf.exists():
        return False, f"KazBars base.swf not found:\n{base_swf}"

    temp_dir = None
    try:
        # Step 1: Generate AS2 code (main class + data classes)
        generator = CodeGenerator(
            grids,
            database,
            app_version,
            assets_path=assets_path,
            cast_config=cast_config,
            stopwatch_config=stopwatch_config,
            inspect_config=inspect_config,
            console_config=console_config,
            onslaught_config=onslaught_config,
            overlay=overlay,
            anchor=anchor,
            game_resolution=game_resolution,
        )
        files = generator.generate_files()

        # Step 2: Write every class to a temp .as file (the compiler binds file
        # name == class name)
        temp_dir = tempfile.mkdtemp(prefix="kazbars_")
        sources = []
        for name, src in files:
            path = Path(temp_dir) / name
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            sources.append(path)

        # Step 3: The base for the overlay font, written to temp
        output_swf.parent.mkdir(parents=True, exist_ok=True)
        temp_swf = Path(temp_dir) / "KazBars.swf"
        font = generator.overlay["font"]
        try:
            temp_swf.write_bytes(font_base(base_swf, font))
        except (OSError, SwfFontError) as e:
            return False, f"Couldn't set the overlay in {font}:\n{e}"

        # Step 4: Compile (main class + every data class)
        common_stubs = base_swf.parent.parent / "common_stubs"
        ok, err = compile_as2([stubs_path, common_stubs, temp_dir], temp_swf, sources)
        if not ok:
            return False, f"Compilation failed:\n{err}"

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
