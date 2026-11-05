"""
KazBars — Grid Model
Constants, validation specs, and default grid configuration.
"""

import copy
import math

from .classes import id_of as class_id_of
from .overlay_size import SCALE_DEFAULT, SCALE_MAX, SCALE_MIN, grid_metrics
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


def screen_extent(grid, base):
    """The grid's size on screen in game px, (width, height): `KazBarsGridView`'s
    own W and H, `n x (icon + gap) - gap` along each axis, the icon at `base`
    (the profile's overlay size) and the grid's scale. A band's is its fullest:
    its widest row by its rows."""
    icon = grid_metrics(base, grid['scale']).icon
    gap = grid['gap']
    cols = min(grid['cols'], grid['maxSlots']) if is_band(grid) else grid['cols']
    return cols * (icon + gap) - gap, grid['rows'] * (icon + gap) - gap


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

    if rows == 1:
        fill_dir = "LR"
    elif cols == 1:
        fill_dir = "BT"
    else:
        fill_dir = "BL-TR"

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

    # `timerStyle`, else the retired `showTimers`: a false reads `off`,
    # anything else `digits`.
    if grid.get('timerStyle') not in TIMER_STYLES:
        grid['timerStyle'] = 'off' if grid.get('showTimers') is False else 'digits'

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

    # Validate grid name/id
    grid_id = str(grid.get('id', '')).strip()
    if not grid_id:
        grid['id'] = defaults['id']

    # Ensure lists/dicts
    if not isinstance(grid.get('whitelist'), list):
        grid['whitelist'] = []
    if not isinstance(grid.get('slotAssignments'), dict):
        grid['slotAssignments'] = {}

    return grid


def _clamp_int(grid, key, default, lo, hi):
    try:
        value = int(grid.get(key, default))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(lo, min(value, hi))


def _validate_overhead(grid):
    """The overhead keys, where they apply and nowhere else: an overhead grid's
    shape inside 4 x 8 with its columns giving way to its 16 slots, its height
    (`plateOffset`, px of room for the nameplate) and range (`maxDistance`, m);
    a band's `rowCap` and `maxSlots` and the shape and centred fill derived from
    them; a friendly grid's `showSelf`."""
    gtype = grid['type']
    if is_plate(gtype):
        grid['rows'] = min(grid['rows'], PLATE_MAX_ROWS)
        grid['cols'] = min(grid['cols'], PLATE_MAX_COLS)
        grid['plateOffset'] = _clamp_int(grid, 'plateOffset', PLATE_OFFSET_DEFAULT, 0, 400)
        grid['maxDistance'] = _clamp_int(grid, 'maxDistance', PLATE_DISTANCE_DEFAULT, 5, 100)
        if is_band(grid):
            cap = snap_row_cap(_clamp_int(grid, 'rowCap', grid['cols'], 1, 7))
            slots = _clamp_int(grid, 'maxSlots', grid['rows'] * grid['cols'], 1, PLATE_MAX_SLOTS)
            grid['rows'], grid['cols'] = band_shape(cap, slots)
            grid.update(rowCap=cap, maxSlots=slots, fillDirection='C')
        else:
            grid['cols'] = min(grid['cols'], PLATE_MAX_SLOTS // grid['rows'])
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
