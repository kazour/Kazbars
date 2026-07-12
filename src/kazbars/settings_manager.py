"""
KazBars — Settings proxy + the atomic JSON-save helper.

Holds ``safe_save_json`` (temp-file + rename) — the atomic write that
``settings_core`` and ``profile_io`` are built on — plus a module-global
settings reference set via ``init_settings()`` so modules can call
``get_setting`` / ``set_setting`` without threading the prefs object through
every API.

The old ``SettingsManager`` class is retired: a ``settings_core.Store`` built on
``prefs.PREFS_SCHEMA`` is what ``init_settings`` now receives, and the three typed
settings files route through ``settings_core`` directly.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_save_json(path, data):
    """Write JSON atomically — temp file + rename."""
    safe_write_text(path, json.dumps(data, indent=2))


def safe_write_text(path, text):
    """Write text atomically — temp file + rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(p)


_settings = None


def init_settings(settings):
    """Store the app settings reference. Call once from KazBarsApp.__init__."""
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
