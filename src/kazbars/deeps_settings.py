"""KazBars — Deeps settings module.

Defines defaults, validation ranges, and load/save for `deeps_settings.json`.
Mirrors the structure of `live_tracker_settings.py` so the two settings
files stay consistent in shape and behavior.

Persisted state:
  - Three user-configurable thresholds (alarm DPS, HPIS green deadband,
    DPIS yellow threshold) — set from the panel.
  - Pet-damage toggle — included by default.
  - Overlay layout choice (`horizontal` | `vertical`) — radio in panel.
  - Readout tuning (the "Readout" card) — rolling-window width, display
    smoothing strength, coarse-rounding step, and redraw cadence. These are
    presentation-only knobs; `window_seconds` is the one that changes the
    measured rate (it sizes the tracker buffers), the other three only shape
    how the already-computed number is drawn.
  - Overlay window state — position, lock state, positioned-once flag.

Not persisted: the alarm-active state (recomputed every tick from threshold
+ current DPS) or the monitoring-running state (always starts stopped; no
auto-resume per the locked decision).
"""

import logging
from pathlib import Path
from typing import Any

from . import settings_core
from .overlay_engine import FONT_FAMILY_CHOICES, OverlayConfig
from .settings_core import Field, Schema

logger = logging.getLogger(__name__)

# Re-export so existing `from .deeps_settings import FONT_FAMILY_CHOICES`
# callers don't need to change.
__all__ = [
    "DEEPS_DEFAULTS",
    "DEEPS_RANGES",
    "FONT_FAMILY_CHOICES",
    "SETTINGS_FILENAME",
    "_READOUT_PRESETS",
    "_SURVIVAL_PRESETS",
    "apply_overlay_config_to_deeps",
    "get_default_settings",
    "get_settings_path",
    "load_settings",
    "normalize_readout_preset",
    "normalize_survival_preset",
    "overlay_config_from_deeps",
    "save_settings",
    "validate_all_settings",
    "validate_setting",
]


# =========================================================================== #
# DEFAULTS                                                                    #
# =========================================================================== #

DEEPS_DEFAULTS: dict[str, Any] = {
    # Threat axis — DPS-out alarm (red pulse). Set from the panel's slider over
    # the 1000-4000/s band; the stored value is just clamped to that on display.
    "alarm_threshold": 2500.0,

    # Survival axis — the ΔHP-in / DPS-in / HPS-in tints. These four values are
    # four breakpoints on one signed net-HP/s axis (heals minus incoming damage):
    #   net > +green           → HPS-in / ΔHP-in glow green
    #   deficit < tint_start   → no tint
    #   tint_start → tint_full → linear fade DEFAULT → YELLOW_TINT
    #   tint_full → flash      → solid YELLOW_TINT
    #   >= flash              → YELLOW_TINT pulse-flashing to deeper amber
    # Driven together by `survival_preset` (Tank / Standard) via
    # `normalize_survival_preset`, never edited independently — kept as the
    # source the overlay reads. Defaults match the Standard preset.
    "survival_preset": "standard",
    "hpis_green_threshold": 50.0,
    "dpis_tint_start": 100.0,
    "dpis_tint_full": 200.0,
    "dpis_flash": 300.0,

    # Behavior toggle — pet damage included by default.
    "include_pet_damage": True,

    # Readout tuning — the "Readout" card. `window_seconds` sizes the rolling
    # buffers (one of `_WINDOW_CHOICES`) and is the one knob that changes the
    # *measured* rate (it therefore also shifts when the DPS-out alarm fires
    # and when the ΔHP-in ramp tints). `smoothing` / `round_step` / `refresh_ms`
    # are pure display presentation, bundled into named presets the user picks
    # from (`readout_preset`); the three keys are kept as the source the
    # overlay's smoother reads. `smoothing` is a 0-100 strength mapped to an
    # EMA time constant (0 = off → digits snap). `round_step` quantizes the
    # drawn value (1 = off). `refresh_ms` is how often the drawn digits are
    # allowed to change (100 = live / every UI tick).
    "window_seconds": 5,
    "readout_preset": "steady",
    "smoothing": 50,
    "round_step": 10,
    "refresh_ms": 100,

    # Overlay layout — radio in panel, "horizontal" or "vertical".
    "layout": "horizontal",

    # Overlay appearance — font + background opacity. Font family is one of
    # the curated Windows-shipping faces in `FONT_FAMILY_CHOICES`. Size is
    # the number-cell size; labels scale proportionally. `overlay_bg_opacity`
    # 0.0 keeps the bg fully transparent; values up to 1.0 draw an
    # increasingly dark backdrop behind the numbers (smooth per-pixel alpha
    # via the PIL overlay engine).
    "overlay_font_family": "Segoe UI",
    "overlay_font_size": 22,
    "overlay_bg_opacity": 0.66,

    # Overlay window state.
    "overlay_x": 0,                      # will be centered on first run
    "overlay_y": 150,
    "overlay_locked": False,
    "overlay_positioned": False,         # gates one-time centering pass

    # Overlay cell visibility — list of IDs in `deeps_overlay.ALL_CELL_IDS`.
    # Render order is fixed; the user picks WHICH cells are shown via the
    # Deeps-panel checkboxes.
    "visible_cells": ["dps", "dpis", "hps"],
}


# =========================================================================== #
# VALIDATION RANGES                                                           #
# =========================================================================== #

DEEPS_RANGES: dict[str, dict[str, Any]] = {
    # Thresholds: positive numbers, generous upper caps so wild raid DPS
    # values are still accepted.
    "alarm_threshold":       {"min": 0.0, "max": 999_999.0, "kind": "float"},
    "hpis_green_threshold":  {"min": 0.0,  "max":  99_999.0, "kind": "float"},
    "dpis_tint_start":       {"min": 0.0,  "max":  99_999.0, "kind": "float"},
    "dpis_tint_full":        {"min": 0.0,  "max":  99_999.0, "kind": "float"},
    "dpis_flash":            {"min": 0.0,  "max":  99_999.0, "kind": "float"},

    # Display smoothing strength — 0 (off, digits snap) to 100 (max easing).
    "smoothing": {"min": 0, "max": 100, "kind": "int"},

    # Overlay font size — readable lower bound, big-monitor upper bound.
    "overlay_font_size": {"min": 12, "max": 48, "kind": "int"},

    # Overlay bg opacity — 0.0 fully transparent, 1.0 solid.
    "overlay_bg_opacity": {"min": 0.0, "max": 1.0, "kind": "float"},

    # Overlay position: 8K-safe sanity caps (same approach as
    # grids_panel.scale_to_resolution).
    "overlay_x": {"min": 0, "max": 7680, "kind": "int"},
    "overlay_y": {"min": 0, "max": 4320, "kind": "int"},
}

_BOOL_KEYS = ("include_pet_damage", "overlay_locked", "overlay_positioned")
_LAYOUT_CHOICES = ("horizontal", "vertical")
_ALL_CELL_IDS = ("dps", "dpis", "hps", "hps-out", "net")
_READOUT_PRESET_CHOICES = ("live", "steady", "calm")

# Disk/memory/overlay invariant — the three smoother knobs are derived from the
# selected preset name, not edited independently. `normalize_readout_preset`
# snaps `smoothing`/`round_step`/`refresh_ms` back to these values whenever
# settings are loaded or the user picks a preset.
_READOUT_PRESETS: dict[str, dict[str, int]] = {
    "live":   {"smoothing":  0, "round_step":  1, "refresh_ms": 100},
    "steady": {"smoothing": 50, "round_step": 10, "refresh_ms": 100},
    "calm":   {"smoothing": 90, "round_step": 50, "refresh_ms": 500},
}

# Survival-tint presets — the same disk/memory/overlay invariant as the readout
# presets, applied to the four ΔHP-in tint thresholds. The user picks a preset,
# not four numbers; `normalize_survival_preset` snaps the keys to the selection.
# Tank is symmetric (the +green surplus mirrors the -tint_start deficit, ±200)
# for big-hit / big-heal play; Standard glows green on a small surplus with a
# tighter danger ramp.
_SURVIVAL_PRESET_CHOICES = ("tank", "standard")
_SURVIVAL_PRESETS: dict[str, dict[str, float]] = {
    "tank":     {"hpis_green_threshold": 200.0, "dpis_tint_start": 200.0,
                 "dpis_tint_full": 350.0, "dpis_flash": 500.0},
    "standard": {"hpis_green_threshold":  50.0, "dpis_tint_start": 100.0,
                 "dpis_tint_full": 200.0, "dpis_flash": 300.0},
}

# Readout-card discrete choices. `window_seconds` are the odd-second widths the
# user can pick; `round_step` includes 1 (= rounding off); `refresh_ms` 100 is
# live (every UI tick). Off-list values snap back to the default.
_WINDOW_CHOICES = (5, 7, 11, 13)
_ROUND_STEPS = (1, 5, 10, 25, 50, 100)
_REFRESH_CHOICES = (100, 250, 500, 1000)
_CHOICE_KEYS = {
    "window_seconds": _WINDOW_CHOICES,
    "round_step": _ROUND_STEPS,
    "refresh_ms": _REFRESH_CHOICES,
}

# `FONT_FAMILY_CHOICES` is re-exported from `overlay_engine` (the source of
# truth) so both Deeps and the Live Tracker share the same curated list.


# =========================================================================== #
# SCHEMA                                                                       #
# =========================================================================== #
# The persistence/validation contract, derived from the tables above so the two
# can't drift. Domain logic (the preset normalisers, overlay adapters) stays
# out of the load path — the engine owns only coercion + fill + atomic I/O.

SETTINGS_FILENAME = "deeps_settings.json"

_ENUM_CHOICES = {
    "layout": _LAYOUT_CHOICES,
    "overlay_font_family": tuple(FONT_FAMILY_CHOICES),
    "readout_preset": _READOUT_PRESET_CHOICES,
    "survival_preset": _SURVIVAL_PRESET_CHOICES,
}


def _validate_visible_cells(value: Any) -> list[str]:
    """Keep only valid cell IDs; preserve given order but de-dupe. Empty list is
    allowed (overlay renders nothing — recoverable via the panel checkboxes)."""
    if not isinstance(value, (list, tuple)):
        return list(DEEPS_DEFAULTS["visible_cells"])
    seen: set[str] = set()
    result: list[str] = []
    for c in value:
        if c in _ALL_CELL_IDS and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _build_fields() -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for key, default in DEEPS_DEFAULTS.items():
        if key in _BOOL_KEYS:
            fields[key] = Field(default, kind="bool")
        elif key in _ENUM_CHOICES:
            fields[key] = Field(default, choices=_ENUM_CHOICES[key])
        elif key in _CHOICE_KEYS:
            fields[key] = Field(default, kind="int", choices=tuple(_CHOICE_KEYS[key]))
        elif key == "visible_cells":
            fields[key] = Field(default, validate=_validate_visible_cells)
        elif key in DEEPS_RANGES:
            spec = DEEPS_RANGES[key]
            fields[key] = Field(default, min=spec["min"], max=spec["max"], kind=spec["kind"])
        else:
            fields[key] = Field(default)
    return fields


_SCHEMA = Schema(SETTINGS_FILENAME, 1, _build_fields())


# =========================================================================== #
# VALIDATION                                                                  #
# =========================================================================== #

def get_default_settings() -> dict:
    """Return a fresh copy of the default Deeps settings."""
    return settings_core.get_defaults(_SCHEMA)


def validate_setting(key: str, value: Any):
    """Validate and coerce a single setting. Returns the value to store.
    Unknown keys pass through (validate_all_settings is what drops them)."""
    return settings_core.coerce(_SCHEMA, key, value)


def normalize_readout_preset(settings: dict) -> str:
    """Snap the three smoother keys to match the persisted
    readout_preset. Returns the (possibly defaulted) preset name."""
    name = settings.get("readout_preset", DEEPS_DEFAULTS["readout_preset"])
    if name not in _READOUT_PRESETS:
        name = DEEPS_DEFAULTS["readout_preset"]
    preset = _READOUT_PRESETS[name]
    settings["readout_preset"] = name
    settings["smoothing"] = preset["smoothing"]
    settings["round_step"] = preset["round_step"]
    settings["refresh_ms"] = preset["refresh_ms"]
    return name


def normalize_survival_preset(settings: dict) -> str:
    """Snap the four survival-tint thresholds to match the persisted
    `survival_preset`. Returns the (possibly defaulted) preset name.

    Twin of `normalize_readout_preset`: the four ΔHP-in tint keys are derived
    from the preset name, never edited independently, so this re-syncs them
    whenever settings load or the user picks a preset."""
    name = settings.get("survival_preset", DEEPS_DEFAULTS["survival_preset"])
    if name not in _SURVIVAL_PRESETS:
        name = DEEPS_DEFAULTS["survival_preset"]
    preset = _SURVIVAL_PRESETS[name]
    settings["survival_preset"] = name
    settings["hpis_green_threshold"] = preset["hpis_green_threshold"]
    settings["dpis_tint_start"] = preset["dpis_tint_start"]
    settings["dpis_tint_full"] = preset["dpis_tint_full"]
    settings["dpis_flash"] = preset["dpis_flash"]
    return name


def validate_all_settings(settings: dict) -> dict:
    """Validate every known key, drop unknowns, fill missing with defaults."""
    return settings_core.validate_all(_SCHEMA, settings)


# =========================================================================== #
# Shared OverlayConfig adapters (no disk-key renames)                         #
# =========================================================================== #

def overlay_config_from_deeps(settings: dict) -> OverlayConfig:
    """Build an `OverlayConfig` from the Deeps `overlay_*` keys."""
    return OverlayConfig(
        x=int(settings.get("overlay_x", DEEPS_DEFAULTS["overlay_x"])),
        y=int(settings.get("overlay_y", DEEPS_DEFAULTS["overlay_y"])),
        positioned=bool(settings.get("overlay_positioned", False)),
        locked=bool(settings.get("overlay_locked", False)),
        font_family=str(settings.get("overlay_font_family", DEEPS_DEFAULTS["overlay_font_family"])),
        font_size=int(settings.get("overlay_font_size", DEEPS_DEFAULTS["overlay_font_size"])),
        bg_opacity=float(settings.get("overlay_bg_opacity", DEEPS_DEFAULTS["overlay_bg_opacity"])),
        visible=True,  # Deeps visibility follows Start/Stop, not a persisted flag
    )


def apply_overlay_config_to_deeps(settings: dict, cfg: OverlayConfig) -> None:
    """Write an `OverlayConfig` back into the Deeps `overlay_*` keys (in place)."""
    settings["overlay_x"] = cfg.x
    settings["overlay_y"] = cfg.y
    settings["overlay_positioned"] = cfg.positioned
    settings["overlay_locked"] = cfg.locked
    settings["overlay_font_family"] = cfg.font_family
    settings["overlay_font_size"] = cfg.font_size
    settings["overlay_bg_opacity"] = cfg.bg_opacity


# =========================================================================== #
# FILE I/O                                                                    #
# =========================================================================== #
# `SETTINGS_FILENAME` is defined up in the SCHEMA section (the Schema needs it).


def get_settings_path(settings_folder: str | Path) -> str:
    """Full path to deeps_settings.json inside `settings_folder`."""
    return str(Path(settings_folder) / SETTINGS_FILENAME)


def load_settings(settings_folder: str | Path) -> dict:
    """Load, migrate, validate, fill. Returns defaults if the file is missing or
    unparseable — never raises (the engine logs failures at debug level)."""
    return settings_core.load(_SCHEMA, settings_folder)


def save_settings(settings_folder: str | Path, settings: dict) -> bool:
    """Validate and write atomically (temp + rename). Creates the folder if
    missing; values are clamped before the write so disk never holds junk."""
    return settings_core.save(_SCHEMA, settings_folder, settings)
