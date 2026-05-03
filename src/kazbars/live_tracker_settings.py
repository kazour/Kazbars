"""
Live Tracker Settings Module for KazBars
Defines Live Tracker overlay settings, defaults, and validation.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULT SETTINGS
# =============================================================================

TIMERS_DEFAULTS = {
    # Overlay position and size
    "x": 0,                     # Will be centered on first run
    "y": 50,                    # Near top of screen
    "width": 269,
    "height": 104,

    # Overlay state
    "locked": False,
    "transparent_bg": False,
    "opacity": 0.90,            # 0.3 - 1.0
    "font_size": 12,            # 8 - 20

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
    "x":        {"min": 0,    "max": 3840,  "step": 1},
    "y":        {"min": 0,    "max": 2160,  "step": 1},
    "width":    {"min": 150,  "max": 600,   "step": 1},
    "height":   {"min": 60,   "max": 300,   "step": 1},
    "opacity":  {"min": 0.3,  "max": 1.0,   "step": 0.05},
    "font_size": {"min": 8,   "max": 20,    "step": 1},
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_default_settings():
    """Return a copy of the default timers settings."""
    return dict(TIMERS_DEFAULTS)


def validate_setting(key, value):
    """Validate a single timer setting. Returns clamped/corrected value."""
    if key in ("locked", "transparent_bg", "visible", "positioned"):
        return bool(value)

    if key in TIMERS_RANGES:
        r = TIMERS_RANGES[key]
        try:
            # Handle float vs int based on step
            if isinstance(r.get("step"), float) or key == "opacity":
                value = float(value)
            else:
                value = int(value)
            return max(r["min"], min(value, r["max"]))
        except (ValueError, TypeError):
            return TIMERS_DEFAULTS.get(key, 0)

    return value


def validate_all_settings(settings):
    """Validate all timer settings, returning cleaned dict."""
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
