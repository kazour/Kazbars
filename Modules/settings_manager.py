"""
Kaz Grids — Settings proxy.

Holds a module-global reference to the app's SettingsManager, set once at
startup via init_settings(). Provides get_setting()/set_setting() as a
lightweight public API so modules don't have to pass the manager around.
"""

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
