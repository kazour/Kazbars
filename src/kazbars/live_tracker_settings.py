"""
Live Tracker Settings Module for KazBars
Defines Live Tracker overlay settings, defaults, and validation.
"""

import logging
import re
from pathlib import Path
from typing import Any

from . import settings_core
from .overlay_engine import FONT_FAMILY_CHOICES, OverlayConfig
from .settings_core import Field, Schema

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULT SETTINGS
# =============================================================================

TIMERS_DEFAULTS = {
    # Overlay position and size
    "x": 0,                     # Will be centered on first run
    "y": 150,                   # Below the top edge
    "width": 269,
    "height": 104,

    # Overlay state
    "locked": False,
    "bg_opacity": 0.66,         # 0.0 transparent → 1.0 solid dark
    "font_family": "Segoe UI",  # one of overlay_engine.FONT_FAMILY_CHOICES
    "font_size": 20,            # range 12-48

    # Visibility (remember if user hid the overlay)
    "visible": True,

    # True once the user (or auto-center) has placed the overlay; gates the
    # one-time centering pass in TimerOverlay.__init__.
    "positioned": False,
}

# =============================================================================
# VALIDATION RANGES
# =============================================================================

TIMERS_RANGES: dict[str, dict[str, Any]] = {
    "x":          {"min": 0,    "max": 3840,  "step": 1},
    "y":          {"min": 0,    "max": 2160,  "step": 1},
    "width":      {"min": 150,  "max": 600,   "step": 1},
    "height":     {"min": 60,   "max": 300,   "step": 1},
    "bg_opacity": {"min": 0.0,  "max": 1.0,   "step": 0.05},
    "font_size":  {"min": 12,   "max": 48,    "step": 1},
}


# =============================================================================
# SCHEMA
# =============================================================================
# Derived from the tables above so the two can't drift; the engine owns coercion,
# fill, and atomic I/O. Overlay adapters (below) stay out of the load path.

SETTINGS_FILENAME = "live_tracker_settings.json"

_BOOL_KEYS = ("locked", "visible", "positioned")


def _build_fields() -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for key, default in TIMERS_DEFAULTS.items():
        if key in _BOOL_KEYS:
            fields[key] = Field(default, kind="bool")
        elif key == "font_family":
            fields[key] = Field(default, choices=tuple(FONT_FAMILY_CHOICES))
        elif key in TIMERS_RANGES:
            r = TIMERS_RANGES[key]
            kind = "float" if (isinstance(r.get("step"), float) or key == "bg_opacity") else "int"
            fields[key] = Field(default, min=r["min"], max=r["max"], kind=kind)
        else:
            fields[key] = Field(default)
    return fields


_SCHEMA = Schema(SETTINGS_FILENAME, 1, _build_fields())


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_default_settings():
    """Return a copy of the default timers settings."""
    return settings_core.get_defaults(_SCHEMA)


_LOG_NAME_RE = re.compile(r"^(CombatLog)-\d{4}-\d{2}-\d{2}_(\d{4})(?:\.\w+)?$")


def sanitize_log_name(name):
    """Trim a combat-log filename for display.

    'CombatLog-2026-05-16_2152.txt' -> 'CombatLog_2152' (drop the date, keep
    the time). Accepts a bare name or a full path. Anything that doesn't match
    the AoC pattern falls back to the stem (no directory, no extension).
    """
    base = Path(name).name
    m = _LOG_NAME_RE.match(base)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return Path(base).stem


def validate_setting(key, value):
    """Validate a single timer setting. Returns clamped/corrected value.
    Unknown keys pass through (validate_all_settings drops them)."""
    return settings_core.coerce(_SCHEMA, key, value)


def validate_all_settings(settings):
    """Validate all timer settings, drop unknowns, fill missing with defaults."""
    return settings_core.validate_all(_SCHEMA, settings)


# =============================================================================
# SETTINGS FILE I/O
# =============================================================================
# `SETTINGS_FILENAME` is defined up in the SCHEMA section (the Schema needs it).


def get_settings_path(settings_folder):
    """Get the full path to live_tracker_settings.json."""
    return str(Path(settings_folder) / SETTINGS_FILENAME)


def load_settings(settings_folder):
    """Load, migrate, validate, fill. Defaults on missing/corrupt — never raises."""
    return settings_core.load(_SCHEMA, settings_folder)


def overlay_config_from_timer(settings):
    """Build an `OverlayConfig` from the Live Tracker bare keys."""
    return OverlayConfig(
        x=int(settings.get("x", TIMERS_DEFAULTS["x"])),
        y=int(settings.get("y", TIMERS_DEFAULTS["y"])),
        positioned=bool(settings.get("positioned", False)),
        locked=bool(settings.get("locked", False)),
        font_family=str(settings.get("font_family", TIMERS_DEFAULTS["font_family"])),
        font_size=int(settings.get("font_size", TIMERS_DEFAULTS["font_size"])),
        bg_opacity=float(settings.get("bg_opacity", TIMERS_DEFAULTS["bg_opacity"])),
        visible=bool(settings.get("visible", TIMERS_DEFAULTS["visible"])),
    )


def overlay_config_to_timer(cfg):
    """Project an `OverlayConfig` onto the Live Tracker bare keys."""
    return {
        "x": cfg.x,
        "y": cfg.y,
        "positioned": cfg.positioned,
        "locked": cfg.locked,
        "font_family": cfg.font_family,
        "font_size": cfg.font_size,
        "bg_opacity": cfg.bg_opacity,
        "visible": cfg.visible,
    }


def save_settings(settings_folder, settings):
    """Validate and write atomically (temp + rename). Creates the folder if
    missing; returns True on success."""
    return settings_core.save(_SCHEMA, settings_folder, settings)


# =============================================================================
# COLOR CONSTANTS (used by overlay and boss_timer)
# =============================================================================

COLORS = {
    "default": "#CCCCCC",   # Gray - idle/waiting
    "warning": "#FFDD66",   # Yellow - attention needed
    "alert": "#FF7744",     # Orange/red - urgent
    "active": "#99DD66",    # Green - action in progress
    "player": "#6ea0ff",    # Blue - player names
}
