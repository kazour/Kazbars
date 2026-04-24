"""
Kaz Grids — Settings persistence.

Owns the SettingsManager class (JSON file → in-memory dict → atomic save) plus
the safe_load_json / safe_save_json helpers it's built on. Also exposes a
module-global reference set via init_settings() so modules can call
get_setting / set_setting without threading the manager through every API.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_load_json(path, fallback=None):
    """Load JSON with fallback on any corruption."""
    if fallback is None:
        fallback = {}
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        return dict(fallback)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning("%s corrupt or unreadable — using defaults: %s", Path(path).name, e)
        return dict(fallback)


def safe_save_json(path, data):
    """Write JSON atomically — temp file + rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(p)


class SettingsManager:
    """Persistent application settings stored as JSON."""

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.data = safe_load_json(self.filepath)

    def save(self):
        try:
            safe_save_json(self.filepath, self.data)
        except Exception as e:
            logger.error("Error saving settings: %s", e)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


_settings = None


def init_settings(settings):
    """Store the app settings reference. Call once from KzGrids.__init__."""
    global _settings
    _settings = settings


def get_setting(key, default=None):
    """Read a single setting value. For use by dialogs that need to persist UI state."""
    if _settings:
        return _settings.get(key, default)
    return default


def set_setting(key, value):
    """Write a single setting value and save."""
    if _settings:
        _settings.set(key, value)
        _settings.save()
