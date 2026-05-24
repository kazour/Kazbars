"""
Live Tracker Settings Module for KazBars
Defines Live Tracker overlay settings, defaults, and validation.
"""

import json
import logging
import re
from pathlib import Path

from .overlay_engine import FONT_FAMILY_CHOICES, OverlayConfig

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

TIMERS_RANGES = {
    "x":          {"min": 0,    "max": 3840,  "step": 1},
    "y":          {"min": 0,    "max": 2160,  "step": 1},
    "width":      {"min": 150,  "max": 600,   "step": 1},
    "height":     {"min": 60,   "max": 300,   "step": 1},
    "bg_opacity": {"min": 0.0,  "max": 1.0,   "step": 0.05},
    "font_size":  {"min": 12,   "max": 48,    "step": 1},
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_default_settings():
    """Return a copy of the default timers settings."""
    return dict(TIMERS_DEFAULTS)


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
    """Validate a single timer setting. Returns clamped/corrected value."""
    if key in ("locked", "visible", "positioned"):
        return bool(value)

    if key == "font_family":
        return value if value in FONT_FAMILY_CHOICES else TIMERS_DEFAULTS["font_family"]

    if key in TIMERS_RANGES:
        r = TIMERS_RANGES[key]
        try:
            # Handle float vs int based on step
            if isinstance(r.get("step"), float) or key == "bg_opacity":
                value = float(value)
            else:
                value = int(value)
            return max(r["min"], min(value, r["max"]))
        except (ValueError, TypeError):
            return TIMERS_DEFAULTS.get(key, 0)

    return value


def _migrate_legacy_keys(raw: dict) -> dict:
    """Convert pre-PIL settings (transparent_bg + opacity) to the new bg_opacity.

    Old model: window-wide `-alpha` for opacity; `transparent_bg=True` meant
    "no panel, just text + stroke". New model: bg-only `bg_opacity` controls
    the backdrop, numbers always at full alpha. Map preserves the visual
    intent so users don't see a sudden jump on upgrade.
    """
    migrated = dict(raw)
    if "transparent_bg" in migrated or "opacity" in migrated:
        was_transparent = bool(migrated.pop("transparent_bg", False))
        old_opacity = float(migrated.pop("opacity", 0.9))
        if was_transparent:
            # User was running floating-text mode; preserve clear bg.
            migrated["bg_opacity"] = 0.0
        else:
            # User had a solid panel; carry their alpha to the new bg fill.
            migrated["bg_opacity"] = max(0.0, min(old_opacity, 1.0))
    return migrated


def validate_all_settings(settings):
    """Validate all timer settings, returning cleaned dict.

    Applies legacy-key migration before validation so users coming from
    the pre-PIL overlay see a sensible default rather than the raw
    `bg_opacity=0.0` they'd get if their old keys were silently dropped.
    """
    settings = _migrate_legacy_keys(settings)
    defaults = get_default_settings()
    result = dict(defaults)

    for key, value in settings.items():
        if key in defaults:
            result[key] = validate_setting(key, value)

    return result


# =============================================================================
# SETTINGS FILE I/O
# =============================================================================

SETTINGS_FILENAME = "live_tracker_settings.json"
LEGACY_SETTINGS_FILENAME = "timers_settings.json"


def get_settings_path(settings_folder):
    """Get the full path to live_tracker_settings.json."""
    return str(Path(settings_folder) / SETTINGS_FILENAME)


def _migrate_legacy_filename(settings_folder):
    """One-shot rename of the pre-rebrand timers_settings.json so users keep
    their saved overlay position, size, and preferences."""
    legacy = Path(settings_folder) / LEGACY_SETTINGS_FILENAME
    current = Path(settings_folder) / SETTINGS_FILENAME
    if legacy.exists() and not current.exists():
        try:
            legacy.rename(current)
            logger.info("Migrated %s to %s",
                        LEGACY_SETTINGS_FILENAME, SETTINGS_FILENAME)
        except OSError as e:
            logger.warning("Live tracker settings migration failed: %s", e)


def load_settings(settings_folder):
    """
    Load timer settings from JSON file.
    Returns validated settings dict (with defaults for missing keys).
    """
    _migrate_legacy_filename(settings_folder)
    settings_path = get_settings_path(settings_folder)

    try:
        if Path(settings_path).exists():
            with open(settings_path, encoding='utf-8') as f:
                loaded = json.load(f)
            return validate_all_settings(loaded)
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Could not load live tracker settings: %s", e)

    return get_default_settings()


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
    """
    Save timer settings to JSON file.
    Creates settings folder if it doesn't exist.
    """
    try:
        Path(settings_folder).mkdir(parents=True, exist_ok=True)
        settings_path = get_settings_path(settings_folder)

        # Validate before saving
        validated = validate_all_settings(settings)

        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(validated, f, indent=2)

        return True
    except OSError:
        return False


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
