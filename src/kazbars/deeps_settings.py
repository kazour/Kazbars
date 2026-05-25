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

import json
import logging
from pathlib import Path

from .overlay_engine import FONT_FAMILY_CHOICES, OverlayConfig

logger = logging.getLogger(__name__)

# Re-export so existing `from .deeps_settings import FONT_FAMILY_CHOICES`
# callers don't need to change.
__all__ = [
    "DEEPS_DEFAULTS",
    "DEEPS_RANGES",
    "FONT_FAMILY_CHOICES",
    "SETTINGS_FILENAME",
    "apply_overlay_config_to_deeps",
    "get_default_settings",
    "get_settings_path",
    "load_settings",
    "overlay_config_from_deeps",
    "save_settings",
    "validate_all_settings",
    "validate_setting",
]


# =========================================================================== #
# DEFAULTS                                                                    #
# =========================================================================== #

DEEPS_DEFAULTS = {
    # Thresholds — set from the panel by the user.
    "alarm_threshold": 2500.0,           # red-flash alarm activates at this 5s DPS
    "hpis_green_threshold": 50.0,        # HPS cell tints green when net > +N/s
    "dpis_yellow_threshold": 300.0,      # DPIS cell tints yellow when -net > +N/s

    # Behavior toggle — pet damage included by default.
    "include_pet_damage": True,

    # Readout tuning — the "Readout" card. `window_seconds` sizes the rolling
    # buffers (one of `_WINDOW_CHOICES`); the other three are pure display
    # presentation. `smoothing` is a 0-100 strength mapped to an EMA time
    # constant (0 = off → digits snap). `round_step` quantizes the drawn value
    # (1 = off). `refresh_ms` is how often the drawn digits are allowed to
    # change (100 = live / every UI tick).
    "window_seconds": 5,
    "smoothing": 50,
    "round_step": 5,
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

DEEPS_RANGES = {
    # Thresholds: positive numbers, generous upper caps so wild raid DPS
    # values are still accepted.
    "alarm_threshold":       {"min": 0.0, "max": 999_999.0, "kind": "float"},
    "hpis_green_threshold":  {"min": 0.0,  "max":  99_999.0, "kind": "float"},
    "dpis_yellow_threshold": {"min": 0.0,  "max":  99_999.0, "kind": "float"},

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
# VALIDATION                                                                  #
# =========================================================================== #

def get_default_settings() -> dict:
    """Return a fresh copy of the default Deeps settings."""
    return dict(DEEPS_DEFAULTS)


def validate_setting(key: str, value: object):
    """Validate and coerce a single setting. Returns the value to store."""
    if key in _BOOL_KEYS:
        return bool(value)

    if key == "layout":
        return value if value in _LAYOUT_CHOICES else DEEPS_DEFAULTS["layout"]

    if key == "overlay_font_family":
        return value if value in FONT_FAMILY_CHOICES else DEEPS_DEFAULTS["overlay_font_family"]

    if key in _CHOICE_KEYS:
        try:
            coerced = int(value)
        except (ValueError, TypeError):
            return DEEPS_DEFAULTS[key]
        return coerced if coerced in _CHOICE_KEYS[key] else DEEPS_DEFAULTS[key]

    if key == "visible_cells":
        # Keep only valid cell IDs; preserve given order but de-dupe. Empty
        # list is allowed (overlay just renders nothing — recoverable via
        # the panel checkboxes).
        if not isinstance(value, (list, tuple)):
            return list(DEEPS_DEFAULTS["visible_cells"])
        seen: set[str] = set()
        result: list[str] = []
        for c in value:
            if c in _ALL_CELL_IDS and c not in seen:
                seen.add(c)
                result.append(c)
        return result

    if key in DEEPS_RANGES:
        spec = DEEPS_RANGES[key]
        try:
            coerced = float(value) if spec["kind"] == "float" else int(value)
        except (ValueError, TypeError):
            return DEEPS_DEFAULTS[key]
        return max(spec["min"], min(coerced, spec["max"]))

    return value


def validate_all_settings(settings: dict) -> dict:
    """Validate every known key, drop unknowns, fill missing with defaults."""
    result = get_default_settings()
    for key, value in settings.items():
        if key in DEEPS_DEFAULTS:
            result[key] = validate_setting(key, value)
    return result


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

SETTINGS_FILENAME = "deeps_settings.json"


def get_settings_path(settings_folder: str | Path) -> str:
    """Full path to deeps_settings.json inside `settings_folder`."""
    return str(Path(settings_folder) / SETTINGS_FILENAME)


def load_settings(settings_folder: str | Path) -> dict:
    """Load settings from JSON, validate, fill missing with defaults.

    Returns the default settings if the file doesn't exist or can't be parsed.
    Never raises — failures are logged at debug level and defaults are used.
    """
    settings_path = get_settings_path(settings_folder)
    try:
        if Path(settings_path).exists():
            with open(settings_path, encoding="utf-8") as f:
                loaded = json.load(f)
            return validate_all_settings(loaded)
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Could not load Deeps settings: %s", e)
    return get_default_settings()


def save_settings(settings_folder: str | Path, settings: dict) -> bool:
    """Validate and write settings to JSON. Returns True on success.

    Creates the settings folder if missing. Validation happens before write,
    so the file is never left in a corrupt or out-of-range state.
    """
    try:
        Path(settings_folder).mkdir(parents=True, exist_ok=True)
        settings_path = get_settings_path(settings_folder)
        validated = validate_all_settings(settings)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(validated, f, indent=2)
        return True
    except OSError as e:
        logger.warning("Could not save Deeps settings: %s", e)
        return False
