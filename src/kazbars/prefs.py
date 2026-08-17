"""KazBars — machine-local preferences: the PREFS_SCHEMA contract.

``prefs.json`` holds the machine-local settings — window positions, game folder,
resolution, the active-profile pointer, build state, and a few UI-state keys.
It is backed by a ``settings_core.Schema`` like every other settings file, which
means it is **strict**: every key the app reads/writes through the
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
from .settings_core import Field, Migration, Schema, Store, nullable_int
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


def _validate_last_patch(value: Any) -> dict:
    """Keep ``{game_path: {section_key: {...last-applied section value...}}}``
    entries; drop anything malformed. Machine-local mirror of what a PATCH-lane
    section (``damage_colors``/``buff_bars``) last actually wrote into *this
    game folder's* XML — the active profile's own section is the loadout-level
    intent, which can drift from this once a profile switch skips re-Applying
    (PATCH lane never fires on switch). Written by the XML editors' Apply;
    consumption (a divergence badge) is a later phase."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict] = {}
    for game_path, sections in value.items():
        if not isinstance(game_path, str) or not isinstance(sections, dict):
            continue
        kept = {k: v for k, v in sections.items() if isinstance(k, str) and isinstance(v, dict)}
        if kept:
            out[game_path] = kept
    return out


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

    Runs on the raw dict before `validate_all`. The stopwatch/inspect configs
    later moved into the profile document, so the sub-dicts this rung rewrites
    are dropped as undeclared keys — its surviving effect is the lifted
    `panel_font_size`. Frozen history; the body stays as written.
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
        # The one profile pointer: the active profile's in-document id. The old
        # last_profile/default_profile path pair is gone — strict validate_all
        # erases stale keys on the next save, no migration rung needed.
        "active_profile": Field(None),
        "has_built_before": Field(False, kind="bool"),
        "desktop_shortcut_offered": Field(False, kind="bool"),
        "build_console": Field(False, kind="bool"),
        # Shared text size for the four in-game panels (see _upgrade_panel_font).
        # Stopwatch/inspect fall back to it whenever their own fontSize is None.
        # Machine-local on purpose: it tracks the monitor, not the loadout —
        # the three extras configs themselves live in the profile document.
        "panel_font_size": Field(
            _PANEL_FONT_DEFAULT, kind="int", min=_PANEL_FONT_MIN, max=_PANEL_FONT_MAX
        ),
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
        # Machine-local record of what a PATCH-lane section last wrote into a
        # given game folder's XML (see _validate_last_patch).
        "last_patch": Field({}, validate=_validate_last_patch),
    },
    migrations=(Migration(2, _upgrade_panel_font),),
)


def record_last_patch(store: Store, game_path: str, section_key: str, value: dict) -> None:
    """Update `last_patch[game_path][section_key]` and save.

    Called by the XML editors' Apply (damageinfo_colors_panel,
    buff_display_editor) so `last_patch` mirrors what actually landed on
    disk for this game folder, independent of whichever profile is active.
    """
    last_patch = dict(store.get('last_patch'))
    per_game = dict(last_patch.get(game_path, {}))
    per_game[section_key] = value
    last_patch[game_path] = per_game
    store.set('last_patch', last_patch)
    store.save()
