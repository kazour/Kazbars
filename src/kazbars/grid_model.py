"""
KazBars — Grid Model
Constants, validation specs, and default grid configuration.
"""

import copy
import math

from .classes import id_of as class_id_of
from .overlay_size import SCALE_DEFAULT, SCALE_MAX, SCALE_MIN
from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema

# ============================================================================
# CONSTANTS
# ============================================================================
# A grid's own slot limit (rows x cols): the card's cell preview and the slot
# picker stay readable. There is no total across grids — in game a slot that
# shows nothing costs nothing (slots are made lazily).
MAX_GRID_SLOTS = 64
MAX_ROWS = 64
MAX_COLS = 64
# An overhead grid is drawn once per character it floats over, so its own
# shape is capped well below a screen grid's: 16 slots, at most 4 rows of 8.
PLATE_MAX_ROWS = 4
PLATE_MAX_COLS = 8
PLATE_MAX_SLOTS = 16
PLATE_OFFSET_DEFAULT = 75
PLATE_DISTANCE_DEFAULT = 40
# A band (an overhead dynamic grid) has no shape of its own: it grows sideways
# from the head's centre, `rowCap` icons to a row (odd, so one icon and a full
# row both centre) before the next row starts above, up to `maxSlots`.
BAND_ROW_CAPS = (3, 5, 7)
BAND_ROW_CAP_DEFAULT = 5
BAND_SLOTS_DEFAULT = 10

DEFAULT_GAME_RESOLUTION = (1920, 1080)

# Declarative validation specs: key → (default, min, max). A grid has no pixel
# or point size of its own: `scale` is a percent of the profile's overlay size
# and the generator derives icon, timer and stack sizes from it
# (overlay_size.grid_metrics).
CLAMP_SPECS = {
    'rows': (1, 1, MAX_ROWS), 'cols': (10, 1, MAX_COLS),
    'scale': (SCALE_DEFAULT, SCALE_MIN, SCALE_MAX), 'gap': (-1, -5, 10),
    'timerFlashThreshold': (6, 0, 11),
    'timerYOffset': (-3, -10, 10),
}
# Fraction position specs: key → default. Positions are stored as fractions of
# the game resolution (full floats, clamped to [0.0, 1.0]); pixels exist only
# at display/emit via project_px/unproject_px, so a document is never rewritten
# by a resolution change.
FRACTION_SPECS = {
    'fx': 100 / 1920,
    'fy': 400 / 1080,
}
# Retired per-grid keys: popped on load so a hand-added one can't zombie along
# (schema-3 documents never carry them).
_RETIRED_KEYS = ('iconSize', 'timerFontSize', 'stackFontSize', 'showTimers', 'x', 'y')

# `timerStyle`: `bar` (a line inside the icon's bottom edge that shrinks as time
# runs out), `digits` (seconds left), `off`.
TIMER_STYLES = ('bar', 'digits', 'off')

# key → (default, valid_values)
ENUM_SPECS = {
    'type': ('player', ('player', 'target', 'friendly', 'hostile')),
    'slotMode': ('dynamic', ('dynamic', 'static')),
    'fillDirection': ('LR', ('LR', 'RL', 'TB', 'BT', 'BL-TR', 'BR-TL', 'TL-BR', 'TR-BL')),
    'sortOrder': ('longest', ('longest', 'shortest', 'application')),
    'layout': ('buffFirst', ('buffFirst', 'debuffFirst', 'mixed')),
    'timerStyle': ('digits', TIMER_STYLES),
}


# ============================================================================
# OVERHEAD GRIDS AND BANDS
# ============================================================================
def is_plate(grid_type):
    """`friendly` / `hostile`: an overhead grid, drawn over each known character
    of that relation instead of at a screen position."""
    return grid_type in ('friendly', 'hostile')


def is_band(grid):
    """An overhead dynamic grid: a band, centred over the head."""
    return is_plate(grid.get('type')) and grid.get('slotMode') == 'dynamic'


def snap_row_cap(v):
    """The nearest of BAND_ROW_CAPS, a tie going up (4 reads 5, 6 reads 7)."""
    return 3 if v <= 3 else 5 if v <= 5 else 7


def max_shape(grid_type):
    """The largest (rows, cols) a grid of `grid_type` may have."""
    return (PLATE_MAX_ROWS, PLATE_MAX_COLS) if is_plate(grid_type) else (MAX_ROWS, MAX_COLS)


def max_slots(grid_type):
    """The most slots a grid of `grid_type` may have: 64 on screen, 16 overhead."""
    return PLATE_MAX_SLOTS if is_plate(grid_type) else MAX_GRID_SLOTS


def slot_count(grid):
    """The slots a grid can show: a band's `maxSlots`, else rows x cols."""
    return grid['maxSlots'] if is_band(grid) else grid['rows'] * grid['cols']


def valid_fills(rows, cols):
    """The fill directions a box of this shape offers, and the one it falls
    back to when its own stops fitting: a row fills sideways, a column up or
    down, anything else from a corner."""
    if rows == 1:
        return ('LR', 'RL'), 'LR'
    if cols == 1:
        return ('TB', 'BT'), 'BT'
    return ('TL-BR', 'TR-BL', 'BL-TR', 'BR-TL'), 'BL-TR'


def snap_fill(rows, cols, fill):
    """A box's fill as its renderers draw it: one the shape offers is kept, an
    unfit one becomes the order `grid_preview.slot_pos` and the AS2 `place()`
    already read it as — a row left to right, a column top down, anything else
    from the top-left corner."""
    if fill in valid_fills(rows, cols)[0]:
        return fill
    return 'LR' if rows == 1 else 'TB' if cols == 1 else 'TL-BR'


def settle_box(rows, cols, fill, grid_type, dynamic, give='cols'):
    """A box grid's (rows, cols, fill) after its shape rules: each side inside
    its max, the `give` side ('rows' or 'cols', the one just edited) giving
    way to the slot limit, a dynamic grid never
    1x1 (it becomes 1x2), and a fill that no longer fits the shape falls back
    to the shape's default. The settings dialog's draft and its Apply both
    run it, so the preview shows what Apply stores."""
    max_rows, max_cols = max_shape(grid_type)
    rows, cols = max(1, min(rows, max_rows)), max(1, min(cols, max_cols))
    limit = max_slots(grid_type)
    if rows * cols > limit:
        if give == 'rows':
            rows = max(1, limit // cols)
        else:
            cols = max(1, limit // rows)
    if dynamic and rows == 1 and cols == 1:
        cols = 2
    codes, default = valid_fills(rows, cols)
    return rows, cols, fill if fill in codes else default


def ref_list(value):
    """A whitelist or slot-assignment value as a list of buff refs: a bare
    scalar (an imported or hand-edited profile can carry one known id instead
    of a list) reads as one, nothing as none, and an empty entry is no ref."""
    if isinstance(value, list):
        return [v for v in value if v]
    return [value] if value else []


def band_shape(row_cap, slots):
    """A band's derived (rows, cols): `rowCap` to a row, rows as needed."""
    return math.ceil(slots / row_cap), row_cap


# ============================================================================
# DEFAULT GRID CONFIGURATION
# ============================================================================
def create_default_grid(grid_type="player", rows=1, cols=10, mode="dynamic", grid_id=None):
    """Return a grid configuration dictionary with sensible defaults. An
    overhead dynamic grid is a band: its row cap from `cols` (snapped to 3, 5
    or 7), its max slots `rows x cols`; a screen grid's 1x1 is static."""
    plate = is_plate(grid_type)
    if rows == 1 and cols == 1 and not plate:
        mode = "static"

    fill_dir = valid_fills(rows, cols)[1]

    grid = {
        'id': grid_id or f"{grid_type.title()}Grid 1",
        'enabled': True,
        'type': grid_type,
        'rows': rows,
        'cols': cols,
        'scale': SCALE_DEFAULT,
        'gap': -1,
        'fx': (100 if grid_type == "player" else 300) / 1920,
        'fy': 400 / 1080,
        'slotMode': mode,
        'timerStyle': 'bar' if plate else 'digits',
        'timerFlashThreshold': 6,
        'timerYOffset': -3,
        'enableFlashing': True,
        'fillDirection': fill_dir,
        'sortOrder': 'longest',
        'layout': 'debuffFirst' if grid_type in ('target', 'hostile') else 'buffFirst',
        'whitelist': [],
        'slotAssignments': {}
    }
    if plate:
        grid['plateOffset'] = PLATE_OFFSET_DEFAULT
        grid['maxDistance'] = PLATE_DISTANCE_DEFAULT
        if mode == 'dynamic':
            cap = snap_row_cap(cols)
            slots = max(1, min(rows * cols, PLATE_MAX_SLOTS))
            grid['rows'], grid['cols'] = band_shape(cap, slots)
            grid.update(rowCap=cap, maxSlots=slots, fillDirection='C')
    if grid_type == 'friendly':
        grid['showSelf'] = True
    return grid


def default_grid_name(grid_type, existing_ids):
    """First free 'PlayerGrid N' / 'TargetGrid N' for the given type."""
    base = f"{grid_type.title()}Grid"
    i = 1
    while f"{base} {i}" in existing_ids:
        i += 1
    return f"{base} {i}"


def validate_grid(grid):
    """Validate and clamp a grid config on load. Returns sanitized grid."""
    defaults = create_default_grid()

    # Type-dependent defaults, as a new grid of the type gets them.
    defaults['timerStyle'] = 'bar' if is_plate(grid.get('type')) else 'digits'
    defaults['layout'] = 'debuffFirst' if grid.get('type') in ('target', 'hostile') else 'buffFirst'

    # Ensure required keys exist
    for key, val in defaults.items():
        if key not in grid:
            grid[key] = val

    # Clamp numeric ranges. Profiles are hand-editable JSON, so a junk value
    # (null, "abc", 1e999 — json parses that to inf, and int(inf) raises
    # OverflowError) falls back to the default instead of crashing the load.
    for key, (default, lo, hi) in CLAMP_SPECS.items():
        try:
            value = int(grid.get(key, default))
        except (TypeError, ValueError, OverflowError):
            value = default
        grid[key] = max(lo, min(value, hi))

    # Fraction positions: full-float clamp to the unit range (NaN → default;
    # inf lands on the clamp bound).
    for key, frac_default in FRACTION_SPECS.items():
        try:
            frac = float(grid.get(key, frac_default))
        except (TypeError, ValueError):
            frac = frac_default
        if frac != frac:
            frac = frac_default
        grid[key] = max(0.0, min(frac, 1.0))
    for key in _RETIRED_KEYS:
        grid.pop(key, None)

    # Validate enums
    for key, (enum_default, valid) in ENUM_SPECS.items():
        if grid.get(key) not in valid:
            grid[key] = enum_default

    _validate_overhead(grid)
    if not is_band(grid):
        grid['fillDirection'] = snap_fill(grid['rows'], grid['cols'], grid['fillDirection'])

    # Validate booleans
    for bool_key in ('enabled', 'enableFlashing'):
        if not isinstance(grid.get(bool_key), bool):
            grid[bool_key] = defaults[bool_key]
    # `selfCastOnly`: show an effect only while you are its caster. Written only
    # when true, so a grid that never set it reads and saves unchanged.
    if grid.get('selfCastOnly') is not True:
        grid.pop('selfCastOnly', None)
    # `class`: the class this grid is built for in game (classes.CLASSES);
    # absent is every class (All). Written only when set.
    cls = class_id_of(grid.get('class'))
    if cls is None:
        grid.pop('class', None)
    else:
        grid['class'] = cls

    # Validate grid name/id: always text (YAML reads a bare `id: 300` as a number)
    grid_id = grid.get('id')
    grid_id = '' if grid_id is None else str(grid_id)
    grid['id'] = grid_id if grid_id.strip() else defaults['id']

    # Ensure lists/dicts
    if not isinstance(grid.get('whitelist'), list):
        grid['whitelist'] = []
    # Slot keys as the editor reads them: '0', '1', … (YAML may read a bare 0
    # as a number); a key that names no slot is dropped.
    raw = grid.get('slotAssignments')
    slots: dict[str, object] = {}
    for key, value in (raw.items() if isinstance(raw, dict) else ()):
        try:
            n = -1 if isinstance(key, bool) else int(key)
        except (TypeError, ValueError, OverflowError):
            continue
        if n >= 0:
            slots.setdefault(str(n), value)
    grid['slotAssignments'] = slots

    return grid


def _clamp_int(grid, key, default, lo, hi):
    try:
        value = int(grid.get(key, default))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(lo, min(value, hi))


def _validate_overhead(grid):
    """The overhead keys, where they apply and nowhere else: an overhead box's
    shape through `settle_box` (inside 4 x 8, its columns giving way to its 16
    slots; its fill then snapped as a screen grid's), an overhead grid's height
    (`plateOffset`, px of room for the nameplate) and range (`maxDistance`, m);
    a band's `rowCap` and `maxSlots` and the shape and centred fill derived from
    them; a friendly grid's `showSelf`."""
    gtype = grid['type']
    if is_plate(gtype):
        grid['plateOffset'] = _clamp_int(grid, 'plateOffset', PLATE_OFFSET_DEFAULT, 0, 400)
        grid['maxDistance'] = _clamp_int(grid, 'maxDistance', PLATE_DISTANCE_DEFAULT, 5, 100)
        if is_band(grid):
            # A band saved without its keys reads them off its shape, clamped first.
            grid['rows'] = min(grid['rows'], PLATE_MAX_ROWS)
            grid['cols'] = min(grid['cols'], PLATE_MAX_COLS)
            cap = snap_row_cap(_clamp_int(grid, 'rowCap', grid['cols'], 1, 7))
            slots = _clamp_int(grid, 'maxSlots', grid['rows'] * grid['cols'], 1, PLATE_MAX_SLOTS)
            grid['rows'], grid['cols'] = band_shape(cap, slots)
            grid.update(rowCap=cap, maxSlots=slots, fillDirection='C')
        else:
            grid['rows'], grid['cols'], _ = settle_box(grid['rows'], grid['cols'], '', gtype, False)
            grid.pop('rowCap', None)
            grid.pop('maxSlots', None)
    else:
        for key in ('plateOffset', 'maxDistance', 'rowCap', 'maxSlots'):
            grid.pop(key, None)
    if gtype == 'friendly':
        if not isinstance(grid.get('showSelf'), bool):
            grid['showSelf'] = True
    else:
        grid.pop('showSelf', None)


def dedupe_grid_ids(grids):
    """Rename duplicate grid ids in place (suffix _2, _3, …), first wins.

    Names key the generated AS2 whitelist tables, so two grids sharing a name
    would silently share one whitelist in-game. The interactive paths (wizard,
    card rename) already block duplicates; hand-edited or shared profiles can
    still carry them, so load-time sanitation renames rather than drops.
    Returns [(old, new), …] for the caller to surface."""
    names = [g.get('id', 'Grid') for g in grids]
    # Suffix candidates must dodge not-yet-visited names too, or a rename can
    # collide with a later grid and force a second, cascading rename.
    taken = set(names)
    seen = set()
    renamed = []
    for grid, name in zip(grids, names):
        if name in seen:
            n = 2
            while f"{name}_{n}" in taken:
                n += 1
            grid['id'] = f"{name}_{n}"
            renamed.append((name, grid['id']))
            name = grid['id']
            taken.add(name)
        seen.add(name)
    return renamed


def parse_resolution(resolution_str):
    """Parse 'WxH' string into (width, height) or None."""
    try:
        w, h = resolution_str.lower().split('x')
        return int(w), int(h)
    except (ValueError, AttributeError):
        return None


def get_game_resolution_or_default():
    """Return (w, h) from settings.game_resolution, or DEFAULT_GAME_RESOLUTION
    if unset/invalid. Reads via the settings_manager module-level proxy."""
    from .settings_manager import get_setting
    res = get_setting('game_resolution')
    if isinstance(res, list) and len(res) == 2 and all(isinstance(v, int) and v > 0 for v in res):
        return tuple(res)
    return DEFAULT_GAME_RESOLUTION


def unproject_px(px, extent):
    """One pixel coordinate → fraction of `extent`, clamped to [0.0, 1.0].
    Full float precision — the fraction model rounds only in `project_px`,
    so repeated round-trips can't drift. Non-positive `extent` → 0.0."""
    if extent <= 0:
        return 0.0
    return max(0.0, min(float(px) / extent, 1.0))


def project_px(fraction, extent):
    """One stored fraction → integer pixel at `extent`, rounded and clamped to
    [0, extent] — the fraction model's single rounding point. For px already in
    [0, extent], px → unproject_px → project_px returns px exactly."""
    return max(0, min(round(float(fraction) * extent), extent))


def _validate_grids_list(value):
    """Section validator: each entry through `validate_grid`, non-dicts dropped,
    duplicate ids renamed. Buff refs are NOT resolved here — the whitelist
    passes through untouched (unresolved refs are preserved, not stripped);
    DB-aware normalization happens in grids_panel at apply time."""
    if not isinstance(value, list):
        return []
    grids = [validate_grid(copy.deepcopy(g)) for g in value if isinstance(g, dict)]
    dedupe_grid_ids(grids)
    return grids


def _harvest_grid_refs(section):
    """Every buff ref the grids section carries (whitelists + slot
    assignments, scalar or list) — the export layer resolves and filters."""
    refs = []
    for g in section.get('grids', []):
        refs.extend(g.get('whitelist', []))
        for val in g.get('slotAssignments', {}).values():
            if isinstance(val, list):
                refs.extend(val)
            elif val is not None:
                refs.append(val)
    return refs


# The grid editor's slice of the profile document: `{'grids': [...]}`.
# Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec(
    'grids',
    Schema('', 1, {'grids': Field([], validate=_validate_grids_list)}),
    LANE_BUILD,
    harvest_refs=_harvest_grid_refs,
)
