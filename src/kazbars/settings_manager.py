"""
KazBars — Settings persistence.

Owns the SettingsManager class (JSON file → in-memory dict → atomic save) plus
the safe_save_json helper it's built on. Also exposes a
module-global reference set via init_settings() so modules can call
get_setting / set_setting without threading the manager through every API.
"""

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

LEGACY_SETTINGS_FILENAME = "kzgrids_settings.json"


def _safe_load_json(path, fallback=None):
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
        self._migrate_legacy_filename()
        self.data = _safe_load_json(self.filepath)

    def _migrate_legacy_filename(self):
        """One-shot copy of the pre-rename Kaz Grids settings file (kzgrids_settings.json)
        to the current filename, so users keep their game folder, window position,
        and other preferences on first launch of KazBars."""
        legacy = self.filepath.parent / LEGACY_SETTINGS_FILENAME
        if legacy.exists() and not self.filepath.exists():
            try:
                shutil.copy2(legacy, self.filepath)
                logger.info("Migrated settings from %s to %s",
                            legacy.name, self.filepath.name)
            except OSError as e:
                logger.warning("Settings migration failed: %s", e)

    def save(self):
        try:
            safe_save_json(self.filepath, self.data)
        except Exception as e:
            logger.error("Error saving settings: %s", e)

    def reload(self):
        """Re-read settings from disk, replacing in-memory state. Used after a
        restore overwrites the settings file underneath the running app."""
        self.data = _safe_load_json(self.filepath)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


_settings = None


def init_settings(settings):
    """Store the app settings reference. Call once from KazBars.__init__."""
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
