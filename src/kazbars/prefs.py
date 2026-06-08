"""KazBars — machine-local preferences: PREFS_SCHEMA + the Prefs facade.

``prefs.json`` holds the machine-local settings — window positions, game folder,
resolution, last/default profile, build state, and a few UI-state keys. It is
backed by a ``settings_core.Schema`` like every other settings file, which means
it is **strict**: every key the app reads/writes through the
``get_setting``/``set_setting`` proxy (or ``app.settings``) MUST be a declared
``Field`` here, or it is erased on the next save.
``tests/test_prefs_schema_covers_all_proxy_keys.py`` greps the tree and fails CI
if a real proxy key isn't declared.

``Prefs`` wraps a ``settings_core.Store`` and re-exposes the exact surface the
old ``SettingsManager`` had (``get`` / ``set`` / no-arg ``save()`` / ``reload()``
+ a writable ``data`` mapping that supports ``pop``), so the proxy and the ~20
``app.settings`` call sites keep working unchanged. ``SettingsManager`` is
retired.
"""

import logging
from pathlib import Path
from typing import Any

from . import CONTENT_BASELINE_VERSION, settings_core
from .settings_core import Field, Schema
from .userdata import PREFS_FILENAME

logger = logging.getLogger(__name__)

# Window positions can sit on a secondary monitor (negative or large coords), so
# we reject only absurd/corrupt values here — the real screen-clamp happens in
# window_position.clamp_to_screen on restore. Signed 16-bit bounds comfortably
# cover any realistic multi-monitor desktop.
_COORD_MIN = -32768
_COORD_MAX = 32767


def _clamp_coord(value: Any) -> int:
    return max(_COORD_MIN, min(int(value), _COORD_MAX))


def _validate_window_positions(value: Any) -> dict:
    """Keep ``{name: {x, y[, width, height]}}`` entries with int coords; drop
    anything malformed. Replaces the dynamic ``window_pos_*`` top-level keys,
    which a fixed strict Schema would erase once positions accumulate."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict] = {}
    for name, pos in value.items():
        if not isinstance(name, str) or not isinstance(pos, dict):
            continue
        try:
            entry = {"x": _clamp_coord(pos["x"]), "y": _clamp_coord(pos["y"])}
        except (KeyError, TypeError, ValueError):
            continue
        for dim in ("width", "height"):
            if dim in pos:
                try:
                    entry[dim] = max(1, int(pos[dim]))
                except (TypeError, ValueError):
                    pass
        out[name] = entry
    return out


def _validate_section_open(value: Any) -> dict:
    """Keep ``{section_label: bool}`` entries; drop non-string keys."""
    if not isinstance(value, dict):
        return {}
    return {k: bool(v) for k, v in value.items() if isinstance(k, str)}


PREFS_SCHEMA = Schema(
    PREFS_FILENAME,
    1,
    {
        # Machine-local: game install, resolution, profile pointers, build state.
        # Scalars are passthrough — their consumers already guard the value
        # (e.g. grid_model.get_game_resolution_or_default validates the list).
        "game_path": Field(None),
        "use_aoc_bypass": Field(False, kind="bool"),
        "game_resolution": Field(None),
        "last_profile": Field(None),
        "default_profile": Field(None),
        "has_built_before": Field(False, kind="bool"),
        "last_build_signature": Field(None),
        "build_console": Field(False, kind="bool"),
        # OTA reference content (Phase 4). content_version is the authoritative
        # comparison key (vs the server manifest); it defaults to the shipped
        # baseline so a fresh install knows it's current and fires no first-run OTA.
        "content_version": Field(CONTENT_BASELINE_VERSION, kind="int"),
        "auto_update_content": Field(True, kind="bool"),
        # Per-window geometry — ONE structured dict (see _validate_window_positions).
        "window_positions": Field({}, validate=_validate_window_positions),
        # UI state.
        "buff_selector_category": Field("All"),
        "buff_selector_type": Field("All"),
        "buff_display_section_open": Field({}, validate=_validate_section_open),
    },
)


class Prefs:
    """SettingsManager-compatible facade over a ``settings_core.Store`` for
    ``prefs.json``. ``get``/``set``/``save()``/``reload()`` + a writable ``data``
    mapping (supports ``pop``) keep the proxy and the app.settings call sites
    unchanged."""

    def __init__(self, folder: str | Path) -> None:
        self._store = settings_core.Store(PREFS_SCHEMA, folder)

    @property
    def data(self) -> dict:
        return self._store.data

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store.set(key, value)

    def save(self) -> bool:
        return self._store.save()

    def reload(self) -> None:
        self._store.reload()
