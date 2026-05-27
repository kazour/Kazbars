"""
KazBars — Grid Model
Constants, validation specs, and default grid configuration.
"""

# ============================================================================
# CONSTANTS
# ============================================================================
MAX_TOTAL_SLOTS = 64
MAX_ROWS = 64
MAX_COLS = 64
SCREEN_MAX_X = 7680
SCREEN_MAX_Y = 4320

# Anchor coefficients for resolution scaling. 0 = top-left anchored
# (offset from origin stays constant), 0.5 = center anchored, 1.0 =
# bottom-right anchored (offset from far edge stays constant). Tuned
# to match AoC's fixed-pixel HUD: action bars don't grow with resolution,
# so grids that flank them must hold a constant offset from screen
# center (X) and screen bottom (Y).
ANCHOR_COEFF_X = 0.5
ANCHOR_COEFF_Y = 1.0

DEFAULT_GAME_RESOLUTION = (1920, 1080)

# Declarative validation specs: key → (default, min, max)
CLAMP_SPECS = {
    'rows': (1, 1, MAX_ROWS), 'cols': (10, 1, MAX_COLS),
    'iconSize': (56, 8, 128), 'gap': (-1, -5, 10),
    'x': (100, 0, SCREEN_MAX_X), 'y': (400, 0, SCREEN_MAX_Y),
    'timerFontSize': (18, 8, 48), 'timerFlashThreshold': (6, 0, 11),
    'timerYOffset': (-3, -10, 10),
    'stackFontSize': (16, 8, 24),
}
# key → (default, valid_values)
ENUM_SPECS = {
    'type': ('player', ('player', 'target')),
    'slotMode': ('dynamic', ('dynamic', 'static')),
    'fillDirection': ('LR', ('LR', 'RL', 'TB', 'BT', 'BL-TR', 'BR-TL', 'TL-BR', 'TR-BL')),
    'sortOrder': ('longest', ('longest', 'shortest', 'application')),
    'layout': ('buffFirst', ('buffFirst', 'debuffFirst', 'mixed')),
}


# ============================================================================
# DEFAULT GRID CONFIGURATION
# ============================================================================
def create_default_grid(grid_type="player", rows=1, cols=10, mode="dynamic", grid_id=None):
    """Return a grid configuration dictionary with sensible defaults."""
    if rows == 1 and cols == 1:
        mode = "static"

    if rows == 1:
        fill_dir = "LR"
    elif cols == 1:
        fill_dir = "BT"
    else:
        fill_dir = "BL-TR"

    return {
        'id': grid_id or f"{grid_type.title()}Grid1",
        'enabled': True,
        'type': grid_type,
        'rows': rows,
        'cols': cols,
        'iconSize': 56,
        'gap': -1,
        'x': 100 if grid_type == "player" else 300,
        'y': 400,
        'slotMode': mode,
        'showTimers': True,
        'timerFontSize': 18,
        'timerFlashThreshold': 6,
        'timerYOffset': -3,
        'stackFontSize': 16,
        'enableFlashing': True,
        'fillDirection': fill_dir,
        'sortOrder': 'longest',
        'layout': 'buffFirst' if grid_type == "player" else 'debuffFirst',
        'whitelist': [],
        'slotAssignments': {}
    }


def validate_grid(grid):
    """Validate and clamp a grid config on load. Returns sanitized grid."""
    defaults = create_default_grid()

    # Ensure required keys exist
    for key, val in defaults.items():
        if key not in grid:
            grid[key] = val

    # Clamp numeric ranges
    for key, (default, lo, hi) in CLAMP_SPECS.items():
        grid[key] = max(lo, min(int(grid.get(key, default)), hi))

    # Validate enums
    for key, (enum_default, valid) in ENUM_SPECS.items():
        if grid.get(key) not in valid:
            grid[key] = enum_default

    # Validate booleans
    for bool_key in ('enabled', 'showTimers', 'enableFlashing'):
        if not isinstance(grid.get(bool_key), bool):
            grid[bool_key] = defaults[bool_key]

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


def scale_grid_position(x, y, ref_w, ref_h, game_w, game_h):
    """Apply anchor-based scaling to one (x, y): X anchored to horizontal
    center, Y anchored to screen bottom. Clamps to SCREEN_MAX bounds and
    floors at 0. Pure function — testable without Tk."""
    dw = game_w - ref_w
    dh = game_h - ref_h
    return (
        max(0, min(round(x + ANCHOR_COEFF_X * dw), SCREEN_MAX_X)),
        max(0, min(round(y + ANCHOR_COEFF_Y * dh), SCREEN_MAX_Y)),
    )
