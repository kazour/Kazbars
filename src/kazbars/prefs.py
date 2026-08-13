"""KazBars — machine-local preferences: the PREFS_SCHEMA contract.

``prefs.json`` holds the machine-local settings — window positions, game folder,
resolution, last/default profile, build state, and a few UI-state keys. It is
backed by a ``settings_core.Schema`` like every other settings file, which means
it is **strict**: every key the app reads/writes through the
``get_setting``/``set_setting`` proxy (or ``app.settings``) MUST be a declared
``Field`` here, or it is erased on the next save.
``tests/test_prefs_schema_covers_all_proxy_keys.py`` greps the tree and fails CI
if a real proxy key isn't declared.

``app.settings`` is a ``settings_core.Store`` built on this schema; the
``get_setting``/``set_setting`` proxy and the ~20 ``app.settings`` call sites use
its ``get`` / ``set`` / ``save()`` / ``reload()`` / ``data`` surface directly.
``SettingsManager`` is retired.
"""

import logging
from typing import Any

from . import CONTENT_BASELINE_VERSION
from .cast_timer import validate_config as _validate_cast_timer
from .inspect import validate_config as _validate_inspect
from .settings_core import Field, Migration, Schema, nullable_int
from .stopwatch import validate_config as _validate_stopwatch
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


# The four in-game panels — stopwatch, inspect, buff console, preview control
# panel — are one visual family and share one text size. Stopwatch and Inspect
# may override it from their own dialogs; the console and control panel have no
# dialog to host an override, which is exactly the gap the shared value closes.
_PANEL_FONT_DEFAULT = 12
_PANEL_FONT_MIN = 8
_PANEL_FONT_MAX = 48

_coerce_panel_font = nullable_int(min=_PANEL_FONT_MIN, max=_PANEL_FONT_MAX)


def validate_panel_font_size(value: Any) -> int:
    """Clamp a shared panel text size to the 8–48 range; None/garbage → 12.

    `app.settings` already coerces the stored key through the same `Field`; this
    is for the consumers that take the value as an argument (the code generator
    bakes it into the SWF) and cannot assume it came from a validated Store.
    """
    size = _coerce_panel_font(value)
    return _PANEL_FONT_DEFAULT if size is None else int(size)


def _stored_font_size(section: Any) -> Any:
    """The `fontSize` a stored `stopwatch`/`inspect` sub-dict carried, or None."""
    return section.get("fontSize") if isinstance(section, dict) else None


def _upgrade_panel_font(data: dict) -> dict:
    """v1 → v2: lift the two per-panel font sizes onto the shared one.

    Anchored on Inspect rather than on `max()`: the shared control lives in the
    Inspect dialog, and the console and control panel are documented as the
    inspect panel's visual family, so a user who only ever enlarged the stopwatch
    keeps those two where they were instead of having them track the least
    related panel. Inspect defined the shared value, so it follows it from here;
    a stopwatch that disagreed keeps its number as a deliberate override.

    Runs on the raw dict before `validate_all`, so the sub-dicts are untouched.
    """
    sizes = {name: _stored_font_size(data.get(name)) for name in ("inspect", "stopwatch")}
    shared = _PANEL_FONT_DEFAULT if sizes["inspect"] is None else sizes["inspect"]
    data["panel_font_size"] = shared
    for name, size in sizes.items():
        section = data.get(name)
        if isinstance(section, dict) and (name == "inspect" or size == shared):
            data[name] = {**section, "fontSize": None}
    return data


PREFS_SCHEMA = Schema(
    PREFS_FILENAME,
    2,
    {
        # Machine-local: game install, resolution, profile pointers, build state.
        # Scalars are passthrough — their consumers already guard the value
        # (e.g. grid_model.get_game_resolution_or_default validates the list).
        "game_path": Field(None),
        "game_resolution": Field(None),
        "last_profile": Field(None),
        "default_profile": Field(None),
        "has_built_before": Field(False, kind="bool"),
        "desktop_shortcut_offered": Field(False, kind="bool"),
        "last_build_signature": Field(None),
        "build_console": Field(False, kind="bool"),
        # Shared text size for the four in-game panels (see _upgrade_panel_font).
        # Stopwatch/inspect fall back to it whenever their own fontSize is None.
        "panel_font_size": Field(
            _PANEL_FONT_DEFAULT, kind="int", min=_PANEL_FONT_MIN, max=_PANEL_FONT_MAX
        ),
        # In-game stopwatch — ONE structured dict (defaults/clamps in stopwatch.py).
        "stopwatch": Field({}, validate=_validate_stopwatch),
        # Target inspect panel — ONE structured dict (defaults/clamps in inspect.py).
        "inspect": Field({}, validate=_validate_inspect),
        # Cast timer — ONE structured dict (defaults/clamps in cast_timer.py). Machine-local
        # like the other two baked overlays: its X/Y depend on the screen, not the profile.
        "cast_timer": Field({}, validate=_validate_cast_timer),
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
    migrations=(Migration(2, _upgrade_panel_font),),
)
