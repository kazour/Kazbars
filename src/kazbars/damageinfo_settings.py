"""Damage Numbers settings — schema, validation, and the AS2 bake-map.

The settings model is *offset-from-game-default*: each tunable stores an offset
(default ``0`` ⇒ unchanged) that the generator adds to the stock game value, then
regex-rewrites the named AS2 constant in a copy of the lean ``DamageInfo`` source
before MTASC compiles it. ``GLOBAL_SETTINGS`` is the single source of truth for both
the UI (ranges, labels, tooltips) and the bake (target file + regex pattern); it must
stay in lockstep with the constants declared in ``assets/damageinfo/src``. The
``test_damageinfo_generator`` regex-coupling test guards that lockstep.

A few keys are *absolute*, not offsets — they have no ``GAME_DEFAULTS`` entry, so
``compute_final_value`` returns the stored value directly: ``shadow_mode`` (enum),
``shrink_start`` and ``min_scale`` (new knobs whose stock baseline is 0).

``enabled`` is the master gate (not baked — it decides whether the modded SWF is
built and installed at all). Pure data; no Tk. Mirrors ``deeps_settings.py``.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = 'damageinfo_settings.json'

# ============================================================
# BAKE-MAP / SCHEMA
# ============================================================
# Each entry: default (offset) + min/max/step (offset bounds) + unit/description/
# tooltip (UI) + file/pattern (bake target). 'type' marks bool/enum controls.
# 'invert': True reverses the slider so dragging right moves the number UP (screen Y
# grows downward) — the vertical-position sliders; horizontal ones stay normal (right =
# right). It's a UI-direction flag only; the baked value (base + offset) is unchanged.
# 'relative': True makes the readout show the signed shift from default (0 = default,
# right = +) instead of the resulting game value — for the position-card sliders, whose
# absolute AS2 coordinate is meaningless to the user. UI-only; the bake is unchanged.
# 'pattern' has two capture groups: (declaration-prefix)(numeric-value); the bake
# rewrites group 2. shadow_blur is the one exception (dual-axis — see the generator).
GLOBAL_SETTINGS: dict[str, dict[str, Any]] = {
    # --- Distance (NEW — fixes ranged numbers shrinking to nothing) ---
    'shrink_start': {
        'default': 0, 'min': 0, 'max': 40, 'step': 5, 'unit': 'm',
        'description': 'Full-size zone',
        'tooltip': 'Numbers stay full size out to this distance before they start shrinking. 0 = shrink immediately (stock).',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var SHRINK_START\s*=\s*)(-?\d+)',
    },
    'distance_falloff': {
        'default': 0, 'min': -40, 'max': 40, 'step': 5, 'unit': 'm',
        'description': 'Vanish distance',
        'tooltip': 'How far away numbers fade to nothing. Higher = numbers stay readable further out (helps ranged classes).',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var DISTANCE_FALLOFF\s*=\s*)(-?\d+)',
    },
    'min_scale': {
        'default': 0, 'min': 0, 'max': 20, 'step': 1, 'unit': '',
        'description': 'Minimum size',
        'tooltip': 'A floor on how small distant numbers get. 0 = stock (can shrink to nothing). Raise so far-off numbers stay visible.',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var MIN_SCALE\s*=\s*)(-?\d+)',
    },
    # --- Shadow ---
    'shadow_mode': {
        'default': 2, 'min': 0, 'max': 2, 'step': 1, 'type': 'enum',
        'options': ['None', 'Fast', 'Real'], 'unit': '',
        'description': 'Shadow',
        'tooltip': 'None = no shadow (fastest). Fast = a cheap offset twin. Real = a true drop shadow (best looking, costs the most).',
        'file': 'numbersTypes/DamageTextAbstract.as',
        'pattern': r'(static var SHADOW_MODE\s*=\s*)(\d+)',
    },
    'shadow_distance': {
        'default': 0, 'min': -4, 'max': 4, 'step': 1, 'unit': 'px',
        'description': 'Shadow offset',
        'tooltip': 'How far the shadow sits from the number.',
        'file': 'numbersTypes/DamageTextAbstract.as',
        'pattern': r'(DropShadowFilter\()(\d+)',
    },
    'shadow_blur': {
        'default': 0, 'min': -3, 'max': 3, 'step': 1, 'unit': 'px',
        'description': 'Shadow softness',
        'tooltip': 'How blurry the shadow is. Real shadow only.',
        'file': 'numbersTypes/DamageTextAbstract.as',
        'pattern': r'(DropShadowFilter\(\d+,\d+,\d+,\d+,)(\d+),(\d+)',
    },
    # --- Direction 1: above target ---
    'dir1_x_offset': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'X shift from head',
        'tooltip': 'Horizontal shift for numbers that float above a target. Positive = further right.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var DIR1_X_OFFSET\s*=\s*)(-?\d+)',
    },
    'dir1_y_offset': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Y shift from head',
        'tooltip': 'Vertical shift for numbers above a target. Drag right to raise them.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var DIR1_Y_OFFSET\s*=\s*)(-?\d+)',
    },
    # --- Fixed columns (direction -1) + split ---
    'fixed_col_x': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'Column A: X',
        'tooltip': 'Column A horizontal position from screen center. Plain numbers go here (or all numbers when split is off).',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_X\s*=\s*)(-?\d+)',
    },
    'fixed_col_y': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Column A: Y',
        'tooltip': 'Column A vertical position. Drag right to raise it on screen.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_Y\s*=\s*)(-?\d+)',
    },
    'fixed_col_split': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Split into two columns',
        'tooltip': 'When on, +/- numbers go to Column B and plain numbers stay in Column A.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_SPLIT\s*=\s*)(\d+)',
    },
    'col_b_x': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'Column B: X',
        'tooltip': 'Column B horizontal position (used only when split is on).',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var COL_B_X\s*=\s*)(-?\d+)',
    },
    'col_b_y': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Column B: Y',
        'tooltip': 'Column B vertical position (used only when split is on). Drag right to raise it.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var COL_B_Y\s*=\s*)(-?\d+)',
    },
    # --- Zig-zag static (direction 0) ---
    'fixed_x_base': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'Zig-zag X center',
        'tooltip': 'Horizontal center of the zig-zag stack. Drag right to move it right.',
        'file': 'numbersManagers/FixedManager.as',
        'pattern': r'(static var TEXT_X_BASE\s*=\s*)(-?\d+)',
    },
    'fixed_y_base': {
        'default': 0, 'min': -300, 'max': 300, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Zig-zag Y center',
        'tooltip': 'Vertical center of the zig-zag stack. Drag right to raise it.',
        'file': 'numbersManagers/FixedManager.as',
        'pattern': r'(static var TEXT_Y_BASE\s*=\s*)(-?\d+)',
    },
    # Spread + spacing are set together by the "spread-spacing" radio (SPREAD_SPACING_OPTIONS),
    # not by per-axis sliders — so no UI flags here; they're still baked offsets.
    'fixed_x_offset': {
        'default': 0, 'min': -150, 'max': 150, 'step': 10, 'unit': 'px',
        'description': 'Zig-zag X spread',
        'tooltip': 'How far left/right the zig-zag swings. Higher = wider.',
        'file': 'numbersManagers/FixedManager.as',
        'pattern': r'(static var TEXT_X_OFFSET\s*=\s*)(-?\d+)',
    },
    'fixed_y_spacing': {
        'default': 0, 'min': -40, 'max': 40, 'step': 10, 'unit': 'px',
        'description': 'Zig-zag spacing',
        'tooltip': 'Vertical gap between stacked numbers. Higher = more spread.',
        'file': 'numbersManagers/FixedManager.as',
        'pattern': r'(static var TEXT_Y_OFFSET\s*=\s*)(-?\d+)',
    },
    # --- Behavior ---
    'show_titles': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Show all labels',
        'tooltip': "Show labels like CRITICAL / MANA / HEALTH on every number. Off = only Dodge/Parry/Resist labels show.",
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var SHOW_ALL_TITLES\s*=\s*)(\d+)',
    },
    'other_resource_loss_to_target': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Enemy drain at target',
        'tooltip': 'When on, mana/stamina you drain from enemies appears above their head instead of in your fixed column.',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var OTHER_RESOURCE_LOSS_TO_TARGET\s*=\s*)(\d+)',
    },
    # --- Size ---
    # One slider for both number and label size — baked into the shared DEFAULT_TEXT_SCALE
    # (the AS2 uses it for both contents). 1x = current size.
    'text_scale': {
        'default': 0, 'min': -0.5, 'max': 0.5, 'step': 0.1, 'unit': 'x',
        'description': 'Numbers & labels',
        'tooltip': 'Size of the damage numbers (and their labels). 1x = current; negative = smaller, positive = bigger.',
        'file': 'numbersTypes/DamageTextAbstract.as',
        'pattern': r'(var DEFAULT_TEXT_SCALE\s*=\s*)(\d+\.?\d*)',
    },
    # --- Animation (preset-only — no slider; Default = 0.2s, Performance = 0.1s).
    #     Easing is fixed to Quad in the AS2, so there is no easing setting. ---
    'show_duration': {
        'default': 0, 'min': -0.2, 'max': 0.2, 'step': 0.05, 'unit': 's',
        'description': 'Pop-in speed',
        'tooltip': 'How long numbers take to appear. Negative = snappier, positive = slower.',
        'file': 'numbersManagers/AbstractManager.as',
        'pattern': r'(static var SHOW_DURATION\s*=\s*)(\d+\.?\d*)',
    },
    'fade_duration': {
        'default': 0, 'min': -0.2, 'max': 0.2, 'step': 0.05, 'unit': 's',
        'description': 'Fade-out speed',
        'tooltip': 'How long numbers take to fade. Negative = snappier, positive = slower.',
        'file': 'numbersManagers/AbstractManager.as',
        'pattern': r'(static var FADE_DURATION\s*=\s*)(\d+\.?\d*)',
    },
}

# Stock game value each offset is added to. Keys absent here are absolute
# (compute_final_value returns the stored value): shadow_mode, shrink_start, min_scale.
GAME_DEFAULTS: dict[str, float] = {
    'distance_falloff': 60,
    'shadow_distance': 4,
    'shadow_blur': 3,
    'dir1_x_offset': -50,  # ships -50 → +=, so 0 offset = 50px left of head (stock), + = right
    'dir1_y_offset': 0,
    'fixed_col_x': 50,
    'fixed_col_y': 100,
    'fixed_col_split': 0,
    'col_b_x': 50,
    'col_b_y': 100,
    'fixed_x_base': 0,
    'fixed_y_base': 100,
    'fixed_x_offset': 200,
    'fixed_y_spacing': 60,
    'show_titles': 0,
    'other_resource_loss_to_target': 0,
    'text_scale': 1.0,
    'show_duration': 0.2,
    'fade_duration': 0.2,
}

# Preset bundles applied on demand from the panel (a starting point, not a locked
# invariant). Each sets only the keys it names; the rest keep their current value.
# These now carry the animation timing (there is no animation slider) plus the
# shadow character that gives each preset its name.
PRESETS: dict[str, dict[str, Any]] = {
    'Default': {
        'show_duration': 0, 'fade_duration': 0,        # 0.2s in / 0.2s out
        'shadow_mode': 2, 'shadow_distance': 0, 'shadow_blur': 0,
    },
    'Performance': {
        'show_duration': -0.1, 'fade_duration': -0.1,  # 0.1s in / 0.1s out
        'shadow_mode': 1, 'shadow_distance': 0, 'shadow_blur': 0,
    },
}

# Zig-zag spread + spacing are coupled into one "spread-spacing" radio (no per-axis
# slider). Each option sets both offsets; the bake (TEXT_X_OFFSET / TEXT_Y_OFFSET) is
# unchanged. Order is the radio order.
SPREAD_SPACING_OPTIONS: tuple[tuple[str, dict[str, int]], ...] = (
    ('Compact',  {'fixed_x_offset': -100, 'fixed_y_spacing': -20}),
    ('Default',  {'fixed_x_offset': 0,    'fixed_y_spacing': 0}),
    ('Extended', {'fixed_x_offset': 100,  'fixed_y_spacing': 20}),
)

# Float-typed keys (fractional step) format as floats in the bake; everything else int.
_FLOAT_KEYS = frozenset(
    k for k, m in GLOBAL_SETTINGS.items()
    if isinstance(m['step'], float) and m['step'] != int(m['step'])
)


def _build_defaults() -> dict[str, Any]:
    d: dict[str, Any] = {k: m['default'] for k, m in GLOBAL_SETTINGS.items()}
    d['enabled'] = False  # master gate — not baked
    return d


DAMAGEINFO_DEFAULTS: dict[str, Any] = _build_defaults()


# ============================================================
# VALIDATION
# ============================================================
def get_default_settings() -> dict[str, Any]:
    """Return a fresh copy of the default Damage Numbers settings."""
    return dict(DAMAGEINFO_DEFAULTS)


def is_float_key(key: str) -> bool:
    """True if this key's baked value should be formatted as a float."""
    return key in _FLOAT_KEYS


def is_offset_key(key: str) -> bool:
    """True if this key stores an offset from a game default (vs an absolute value).

    Offset keys have a symmetric range whose midpoint (0) is the stock value, so the
    panel centre-notches them; absolute keys (``shrink_start``/``min_scale``/
    ``shadow_mode``) start at their floor and get no notch.
    """
    return key in GAME_DEFAULTS


def validate_setting(key: str, value: Any) -> Any:
    """Validate and coerce one setting to the value to store.

    Clamps offsets to [min, max], coerces float/int per the key's step. The master
    ``enabled`` gate is the one bool that lives outside ``GLOBAL_SETTINGS``.
    """
    if key == 'enabled':
        return bool(value)
    meta = GLOBAL_SETTINGS.get(key)
    if meta is None:
        return value
    try:
        num = float(value)
    except (ValueError, TypeError):
        return meta['default']
    num = max(meta['min'], min(num, meta['max']))
    return float(num) if is_float_key(key) else round(num)


def validate_all_settings(settings: dict) -> dict[str, Any]:
    """Validate every known key, drop unknowns, fill missing with defaults."""
    result = get_default_settings()
    for key, value in settings.items():
        if key in DAMAGEINFO_DEFAULTS:
            result[key] = validate_setting(key, value)
    return result


def compute_final_value(key: str, offset: Any) -> Any:
    """Return the absolute AS2 value to bake: game default + offset.

    Keys absent from ``GAME_DEFAULTS`` are absolute — the offset *is* the value.
    """
    base = GAME_DEFAULTS.get(key, 0)
    final = base + offset
    return float(final) if (is_float_key(key) or isinstance(base, float)) else round(final)


def readout(key: str, offset: Any) -> str:
    """The slider's right-side label text.

    ``relative`` (position) sliders read as a signed shift from default — ``0`` at the
    centre, right = ``+`` — since their absolute AS2 coordinate is meaningless. Inverted
    (vertical) sliders store a right-drag as a *negative* offset, so the sign is flipped
    back to keep right positive. Every other slider shows the resulting game value.
    """
    meta = GLOBAL_SETTINGS[key]
    unit = meta['unit']
    if meta.get('relative'):
        shift = -offset if meta.get('invert') else offset
        sign = '+' if shift > 0 else ('-' if shift < 0 else '')
        return f'{sign}{abs(shift):g}{unit}'
    final = compute_final_value(key, offset)
    txt = f'{final:g}' if isinstance(final, float) else str(final)
    return f'{txt}{unit}'


def apply_preset(settings: dict, name: str) -> dict[str, Any]:
    """Overlay a preset bundle onto ``settings`` (validated), returning the result.

    Unknown preset names are a no-op (returns the validated settings unchanged).
    """
    result = validate_all_settings(settings)
    bundle = PRESETS.get(name)
    if bundle:
        for key, value in bundle.items():
            result[key] = validate_setting(key, value)
    return result


def spread_spacing_option(settings: dict) -> str:
    """Name of the ``SPREAD_SPACING_OPTIONS`` entry matching the current offsets.

    Falls back to ``'Default'`` when the stored offsets match no option (e.g. a value
    left over from before this control existed).
    """
    for name, values in SPREAD_SPACING_OPTIONS:
        if all(settings.get(k) == v for k, v in values.items()):
            return name
    return 'Default'


# ============================================================
# FILE I/O  (mirrors deeps_settings)
# ============================================================
def get_settings_path(settings_folder: str | Path) -> str:
    """Full path to damageinfo_settings.json inside ``settings_folder``."""
    return str(Path(settings_folder) / SETTINGS_FILENAME)


def load_settings(settings_folder: str | Path) -> dict[str, Any]:
    """Load + validate settings; return defaults if missing or unparseable. Never raises."""
    settings_path = get_settings_path(settings_folder)
    try:
        if Path(settings_path).exists():
            with open(settings_path, encoding='utf-8') as f:
                loaded = json.load(f)
            return validate_all_settings(loaded)
    except (json.JSONDecodeError, OSError) as e:
        logger.debug('Could not load Damage Numbers settings: %s', e)
    return get_default_settings()


def save_settings(settings_folder: str | Path, settings: dict) -> bool:
    """Validate and write settings to JSON. Creates the folder if missing. Returns success."""
    try:
        Path(settings_folder).mkdir(parents=True, exist_ok=True)
        settings_path = get_settings_path(settings_folder)
        validated = validate_all_settings(settings)
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(validated, f, indent=2)
        return True
    except OSError as e:
        logger.warning('Could not save Damage Numbers settings: %s', e)
        return False
