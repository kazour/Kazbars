"""Damage Numbers settings — schema, validation, and the AS2 bake-map.

The settings model is *offset-from-game-default*: each tunable stores an offset
(default ``0`` ⇒ unchanged) that the generator adds to the stock game value, then
regex-rewrites the named AS2 constant in a copy of the lean ``DamageInfo`` source
before MTASC compiles it. ``GLOBAL_SETTINGS`` is the single source of truth for both
the UI (ranges, labels, tooltips) and the bake (target file + regex pattern); it must
stay in lockstep with the constants declared in ``assets/damageinfo/src``. The
``test_damageinfo_generator`` regex-coupling test guards that lockstep.

A few keys are *absolute*, not offsets — they have no ``GAME_DEFAULTS`` entry, so
``compute_final_value`` returns the stored value directly: ``shadow_mode`` (enum) and
``ranged_keep`` (the keep-ranged-big toggle; its source constant ships at 0 = off/stock).

``enabled`` is the master gate (not baked — it decides whether the modded SWF is
built and installed at all). Pure data; no Tk. Mirrors ``deeps_settings.py``.
"""

import logging
import re
from pathlib import Path
from typing import Any

from . import settings_core
from .settings_core import Field, Schema

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
        'description': 'X offset',
        'tooltip': 'Horizontal shift for numbers that float above a target. Positive = further right.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var DIR1_X_OFFSET\s*=\s*)(-?\d+)',
    },
    'dir1_y_offset': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Y offset',
        'tooltip': 'Vertical shift for numbers above a target. Drag right to raise them.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var DIR1_Y_OFFSET\s*=\s*)(-?\d+)',
    },
    # --- Fixed columns (direction -1) + split ---
    'fixed_col_x': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'X offset',
        'tooltip': 'Column A horizontal position from screen center. Plain damage numbers go here (everything stacks here when the second column is off).',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_X\s*=\s*)(-?\d+)',
    },
    'fixed_col_y': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Y offset',
        'tooltip': 'Column A vertical position. Drag right to raise it on screen.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_Y\s*=\s*)(-?\d+)',
    },
    # "Separate resources into Column B" also drops your incoming damage/heals into the fixed
    # columns: at install it flips the self Attacks/Spells/Combos/Heals directions to -1 in
    # TextColors.xml (build_executor, independent of "Group my resource numbers"), so plain
    # damage stacks in Column A and the signed numbers (heals, mana, stamina) in Column B.
    'fixed_col_split': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Separate resources into Column B',
        'tooltip': 'Sends everything that lands on you into the fixed columns and splits it: '
                   'incoming damage in Column A; heals, stamina and mana in Column B. '
                   'Off = everything in one column.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var FIXED_COL_SPLIT\s*=\s*)(\d+)',
    },
    # Default +50 so Column B sits clear of Column A (FIXED_COL_X) when the split is on.
    'col_b_x': {
        'default': 50, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'X offset',
        'tooltip': 'Column B horizontal position. Starts +50 right of Column A so the two '
                   'columns do not overlap.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var COL_B_X\s*=\s*)(-?\d+)',
    },
    'col_b_y': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Y offset',
        'tooltip': 'Column B vertical position. Drag right to raise it.',
        'file': 'numbersTypes/MovingDamageText.as',
        'pattern': r'(static var COL_B_Y\s*=\s*)(-?\d+)',
    },
    # --- Zig-zag static (direction 0) ---
    'fixed_x_base': {
        'default': 0, 'min': -200, 'max': 200, 'step': 10, 'unit': 'px', 'relative': True,
        'description': 'X offset',
        'tooltip': 'Horizontal center of the zig-zag stack. Drag right to move it right.',
        'file': 'numbersManagers/FixedManager.as',
        'pattern': r'(static var TEXT_X_BASE\s*=\s*)(-?\d+)',
    },
    'fixed_y_base': {
        'default': 0, 'min': -300, 'max': 300, 'step': 10, 'unit': 'px', 'invert': True, 'relative': True,
        'description': 'Y offset',
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
    # Keep-ranged-big is a toggle: ON freezes ranged hits (real avatar→target distance ≥ 15 m)
    # at the size a 15 m hit gets, so they stop shrinking with distance; OFF = stock. Melee
    # (< 15 m) is never touched either way. "Real" distance is recovered in the AS2 — the SWF
    # is handed only camera-to-target distance, so it subtracts a live camera-zoom sample
    # (camera→own-avatar); see DamageNumberManager.as. Absolute key (no GAME_DEFAULTS); the
    # source constant ships at 0 (= off/stock).
    'ranged_keep': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Keep ranged numbers big',
        'tooltip': 'Stops ranged damage numbers (hits past ~15 real metres) from shrinking with '
                   'distance — they hold the size of a 15 m hit. Off = stock (they shrink). '
                   'Close-range (melee) numbers are never affected.',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var RANGED_KEEP\s*=\s*)(-?\d+)',
    },
    # Inverse of the old "show all labels": ON suppresses CRITICAL/MANA/HEALTH etc., leaving
    # only the essential Dodge/Parry/Resist labels. OFF (default) shows every label. The AS2
    # constant ESSENTIAL_LABELS_ONLY ships at 0, so a 0 (off) bakes 0 = show all.
    'essential_labels_only': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Keep only essential labels',
        'tooltip': "When on, only Dodge / Parry / Resist labels show. Off (default) shows every "
                   "label (CRITICAL / MANA / HEALTH, …).",
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var ESSENTIAL_LABELS_ONLY\s*=\s*)(\d+)',
    },
    # "Group my resource numbers": baked into OTHER_RESOURCE_LOSS_TO_TARGET (the SWF keeps
    # enemy drains over the enemy) AND patches TextColors.xml at install time so your own
    # resource losses drop into the fixed column with your gains. See build_executor._prepare_textcolors.
    'other_resource_loss_to_target': {
        'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'bool', 'unit': '',
        'description': 'Group my resource numbers',
        'tooltip': 'Sends your own mana/stamina losses to the same fixed column as your '
                   'resource gains, so you watch all your resource changes in one place. '
                   'Mana/stamina you drain from enemies still floats above them. '
                   '(Patches TextColors.xml on Build & Install.)',
        'file': 'DamageNumberManager.as',
        'pattern': r'(static var OTHER_RESOURCE_LOSS_TO_TARGET\s*=\s*)(\d+)',
    },
    # (Number/label size is intentionally NOT here — AoC's own Options ▸ Damage Number Size
    # slider already covers it live for every class. The AS2 keeps DEFAULT_TEXT_SCALE = 1 as
    # a no-op multiplier.)
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
# (compute_final_value returns the stored value): shadow_mode, ranged_keep.
GAME_DEFAULTS: dict[str, float] = {
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
    'essential_labels_only': 0,
    'other_resource_loss_to_target': 0,
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


# ============================================================
# PER-SOURCE COLORS (TextColors.xml)
# ============================================================
# Catalog of AoC's flytext sources for the color editor, grouped for the 2-column
# (self | other) panel. Names MUST match the htmlFontParser("...") calls in
# assets/damageinfo/src/__Packages/helpers/NumbersFontsCollection.as — guarded by
# test_damageinfo_settings. Colors live in TextColors.xml and apply at Build & Install
# (build_executor._prepare_textcolors) — they are NOT baked into the SWF.

# (group title, self [(name, label)], other [(name, label)]) — paired source groups.
PAIRED_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]], ...] = (
    ('Attacks', (
        ('self_attacked', 'Hit'),
        ('self_attacked_unshielded', 'Unshielded'),
        ('self_attacked_critical', 'Critical'),
        ('self_attacked_environment', 'Environment'),
        ('self_dodged', 'Dodge / miss'),
    ), (
        ('other_attacked', 'Hit'),
        ('other_attacked_unshielded', 'Unshielded'),
        ('other_attacked_critical', 'Critical'),
        ('other_attacked_environment', 'Environment'),
        ('other_dodged', 'Dodge / miss'),
    )),
    ('Spells', (
        ('self_attacked_spell', 'Spell'),
        ('self_attacked_spell_critical', 'Spell crit'),
    ), (
        ('other_attacked_spell', 'Spell'),
        ('other_attacked_spell_critical', 'Spell crit'),
    )),
    ('Combos', (
        ('self_attacked_combo', 'Combo'),
        ('self_attacked_combo_critical', 'Combo crit'),
        ('self_combo_name', 'Combo name'),
    ), (
        ('other_attacked_combo', 'Combo'),
        ('other_attacked_combo_critical', 'Combo crit'),
        ('other_combo_name', 'Combo name'),
    )),
    ('Heals', (
        ('self_healed', 'Heal'),
        ('self_healed_critical', 'Heal crit'),
    ), (
        ('other_healed', 'Heal'),
        ('other_healed_critical', 'Heal crit'),
    )),
)

# Sources the game stores as single entries (no self/other split) → full-width card.
SHARED_SOURCES: tuple[tuple[str, str], ...] = (
    ('stamina_gained', 'Stamina gain'),
    ('stamina_lost', 'Stamina loss'),
    ('stamina_gained_critical', 'Stamina gain crit'),
    ('stamina_loss_critical', 'Stamina loss crit'),
    ('mana_gained', 'Mana gain'),
    ('mana_lost', 'Mana loss'),
    ('mana_gained_critical', 'Mana gain crit'),
    ('mana_loss_critical', 'Mana loss crit'),
    ('xp_gained', 'XP gain'),
    ('murder_points_gained', 'Murder points'),
    ('murder_points_gained_murderer', 'Murder points (murderer)'),
)


def _all_source_names() -> frozenset[str]:
    names: set[str] = set()
    for _title, self_rows, other_rows in PAIRED_GROUPS:
        names.update(n for n, _ in self_rows)
        names.update(n for n, _ in other_rows)
    names.update(n for n, _ in SHARED_SOURCES)
    return frozenset(names)


ALL_SOURCE_NAMES: frozenset[str] = _all_source_names()

_HEX6_RE = re.compile(r'^[0-9A-Fa-f]{6}$')


def normalize_color(value: Any) -> str | None:
    """Bare upper-case ``RRGGBB`` for a ``0x``/``#``/bare hex string, or None if invalid."""
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip('#')
    if v[:2].lower() == '0x':
        v = v[2:]
    return v.upper() if _HEX6_RE.match(v) else None


def validate_source_colors(value: Any) -> dict[str, str]:
    """Keep only known source names mapped to a valid 6-hex color (bare upper-case)."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name, color in value.items():
        if name in ALL_SOURCE_NAMES:
            norm = normalize_color(color)
            if norm is not None:
                out[name] = norm
    return out


def _build_defaults() -> dict[str, Any]:
    d: dict[str, Any] = {k: m['default'] for k, m in GLOBAL_SETTINGS.items()}
    d['enabled'] = False        # master gate — not baked
    d['source_colors'] = {}     # per-source flytext colors → TextColors.xml (not baked)
    return d


DAMAGEINFO_DEFAULTS: dict[str, Any] = _build_defaults()


# ============================================================
# VALIDATION
# ============================================================
def is_float_key(key: str) -> bool:
    """True if this key's baked value should be formatted as a float."""
    return key in _FLOAT_KEYS


def is_offset_key(key: str) -> bool:
    """True if this key stores an offset from a game default (vs an absolute value).

    Offset keys have a symmetric range whose midpoint (0) is the stock value, so the
    panel centre-notches them; absolute keys (``ranged_keep``/``shadow_mode``) start at
    their floor and get no notch.
    """
    return key in GAME_DEFAULTS


# Schema derived from GLOBAL_SETTINGS (the bake-map doubles as the validation
# table). Every offset/absolute key is a clamped numeric Field — the ``type:
# 'bool'``/``'enum'`` metadata is a UI hint only, so those validate as clamped
# ints (round + clamp), exactly as the hand-rolled validator did. ``enabled`` is
# the one real bool; ``source_colors`` carries its own structured validator.
def _build_schema_fields() -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for key, meta in GLOBAL_SETTINGS.items():
        kind = 'float' if is_float_key(key) else 'int'
        fields[key] = Field(meta['default'], min=meta['min'], max=meta['max'], kind=kind)
    fields['enabled'] = Field(False, kind='bool')
    fields['source_colors'] = Field({}, validate=validate_source_colors)
    return fields


_SCHEMA = Schema(SETTINGS_FILENAME, 1, _build_schema_fields())


def get_default_settings() -> dict[str, Any]:
    """Return a fresh copy of the default Damage Numbers settings (each call gets
    its own ``source_colors`` dict — never the module-level default)."""
    return settings_core.get_defaults(_SCHEMA)


def validate_setting(key: str, value: Any) -> Any:
    """Validate and coerce one setting to the value to store. Unknown keys pass
    through; the master ``enabled`` gate and ``source_colors`` validate bespoke."""
    return settings_core.coerce(_SCHEMA, key, value)


def validate_all_settings(settings: dict) -> dict[str, Any]:
    """Validate every known key, drop unknowns, fill missing with defaults."""
    return settings_core.validate_all(_SCHEMA, settings)


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
    return settings_core.load(_SCHEMA, settings_folder)


def save_settings(settings_folder: str | Path, settings: dict) -> bool:
    """Validate and write atomically (temp + rename). Creates the folder if missing."""
    return settings_core.save(_SCHEMA, settings_folder, settings)


# The main panel (offsets/toggles) and the colors panel (source_colors) both live
# in damageinfo_settings.json but each holds its own in-memory copy loaded at open.
# A blind save from one clobbers the other's keys. These two write only their own
# slice, re-reading the sibling's slice from disk first.
def save_source_colors(settings_folder: str | Path, colors: dict) -> bool:
    """Persist only ``source_colors``, preserving whatever else is on disk (the main
    panel may have written offsets/toggles since the colors panel loaded)."""
    current = load_settings(settings_folder)
    current['source_colors'] = validate_source_colors(colors)
    return save_settings(settings_folder, current)


def save_settings_preserving_colors(settings_folder: str | Path, settings: dict) -> bool:
    """Persist ``settings`` but keep the on-disk ``source_colors`` (the colors panel
    may have written since this panel loaded)."""
    merged = dict(settings)
    merged['source_colors'] = load_settings(settings_folder)['source_colors']
    return save_settings(settings_folder, merged)
