# Architectural Map

**Current as of:** 2026-04-25
**Purpose:** Module topology, dependencies, and coupling hotspots. Updated alongside code changes — if you edit this file, commit it with the code. `CLAUDE.md` has the short version; this file has the detail that doesn't fit there.

## Dependency clusters

All arrows point in the "imports from" direction. Every chain terminates — **no cycles**.

### UI primitives (tokens at the root)
```
ui_helpers  ← ui_tk_style
ui_helpers  ← ui_widgets          ← ui_components
                                    (also imports ui_tk_style)
ui_helpers  ← custom_menu_bar
```
- `ui_helpers` holds design tokens only (fonts, colors, padding, BTN_*, SCANLINE_ALPHA) + `setup_custom_styles`. Leaf — imports nothing internal.
- `ui_widgets` adds the builder layer: `blend_alpha`, `CollapsibleSection`, tooltips, dialog/app headers, event bindings, `debounced_callback`.
- `ui_components` adds stateful composites: `ToastManager`, `DragReorderManager`, `create_scrollable_frame`, global mousewheel routing.
- `ui_tk_style` handles raw-tk widget styling + dark-titlebar monkey-patch.
- `custom_menu_bar` is the dark-themed Canvas-based menu bar (was in `ui_components`; extracted for size + single-consumer isolation).

### App state
```
settings_manager  ← window_position
```
Window-position helpers reach settings via the public `get_setting`/`set_setting` API, not the `_settings` global directly.

### Grid editing
```
grid_model  ← grid_dialogs  ← grids_panel
            (also pulls settings_manager, window_position, ui_*)
```

### Build pipeline
```
build_utils  ← grids_generator
             ← build_executor  ← first_launch, build_action
build_loading  ← build_action, first_launch
```

### Live Tracker (isolated — no other panel imports from it)
```
live_tracker_settings  ← boss_timer
                       ← timer_overlay
                       ← combat_monitor
                       ← live_tracker_panel  (orchestrator)
```

### kzgrids-only satellites (extracted from KzGridsApp)
```
kzgrids.py  → profile_io, game_folder, build_action, first_launch, custom_menu_bar
```
These modules are consumed only by `kzgrids.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KzGridsApp` instance) as first arg. `KzGridsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `profile_io`, `build_loading`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup).

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 15 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 10 | `ui_widgets` | Widest builder surface. Keep new helpers focused; don't expand unchecked. |
|  5 | `window_position`, `settings_manager` | Small stable APIs. |
|  4 | `ui_tk_style`, `ui_components` | Narrow surface — ripple is contained. |
|  3 | `grid_model`, `build_utils`, `build_executor`, `build_loading`, `live_tracker_settings` | Cluster leaves. |
|  2 | `grids_generator` | |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_io`, `game_folder`, `build_action`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor` | Each consumed by exactly one parent — low blast radius by design. |

## Conventions

- **Import style:** relative (`from .other import X`) inside `Modules/`; absolute (`from Modules.X import`) only from `kzgrids.py` (top-level entry).
- **Where new code goes:**
  - Design token → `ui_helpers`
  - Reusable widget builder / event binding / small helper → `ui_widgets`
  - Stateful widget class or window-scope helper → `ui_components`
  - Raw-tk (Listbox/Text/Canvas) styling → `ui_tk_style`
  - Window geometry → `window_position`
  - Settings read/write → `settings_manager` (don't re-introduce UI-layer state)
  - Root-window logic (new menu action, new app-state flow) → extract to a new `Modules/<concern>.py` taking `app` as first arg, add a one-line delegator on `KzGridsApp` if it has internal callers. Don't grow `kzgrids.py`.
- **Cluster isolation:** the Live Tracker cluster must not be imported from outside itself. Enforced by convention, not code.

## Smoke tests

Two plain-Python scripts guard the failure modes we've actually hit. No pytest.

- **`tests/test_imports.py`** — auto-discovers every `Modules/*.py` + `kzgrids` and imports each. Catches missing symbols, wrong-module references, and cycles. Add nothing — new modules are picked up automatically.
- **`tests/test_data_integrity.py`** — validates every buff reference in `assets/kzgrids/Default.json` (whitelists + slot assignments) resolves to a `Database.json` entry, and that `Database.json.default` matches `Database.json` byte-for-byte.

Run before every commit touching code or data:
```bash
python tests/test_imports.py && python tests/test_data_integrity.py
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `Modules/grids_panel.py` | 1136 | Grid list UI, grid management |
| `Modules/build_loading.py` | 914 | Build-progress screen + welcome/about popups |
| `Modules/database_editor.py` | 891 | Buff DB CRUD, search, filtering |
| `Modules/grid_dialogs.py` | 742 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `kzgrids.py` | 621 | Entry point + `KzGridsApp` root window (widgets, menu, lifecycle) |
| `Modules/ui_widgets.py` | 510 | Widget builders, tooltips, bindings, `CollapsibleSection`, `blend_alpha` |
| `Modules/live_tracker_panel.py` | 489 | Live Tracker Toplevel orchestrator |
| `Modules/boss_timer.py` | 441 | Boss timer state + UI |
| `Modules/timer_overlay.py` | 440 | In-game transparent timer overlay |
| `Modules/ui_components.py` | 426 | `ToastManager`, `DragReorderManager`, scrollable frame |
| `Modules/grids_generator.py` | 424 | AS2 code generation from grid configs |
| `Modules/instructions_panel.py` | 372 | Help/instructions view |
| `Modules/first_launch.py` | 352 | First-launch dialog + post-dialog orchestrator (`run_first_launch`) |
| `Modules/custom_menu_bar.py` | 325 | Canvas-based dark menu bar |
| `Modules/combat_monitor.py` | 313 | Combat log parser feeding the tracker |
| `Modules/build_executor.py` | 227 | MTASC compile + deploy |
| `build.py` | 225 | PyInstaller build driver |
| `Modules/game_folder.py` | 185 | Game folder UI + Aoc.exe bypass + uninstall |
| `Modules/build_action.py` | 166 | Build & Install flow |
| `Modules/profile_io.py` | 154 | Profile load/save/new/open + missing-buff warning |
| `Modules/live_tracker_settings.py` | 145 | Tracker persistence |
| `Modules/ui_helpers.py` | 129 | Design tokens + `setup_custom_styles` |
| `Modules/grid_model.py` | 117 | Grid dataclasses + `parse_resolution` helper |
| `tests/test_data_integrity.py` | 103 | Buff-ref resolution smoke test |
| `Modules/build_utils.py` | 98 | Compiler discovery + path helpers |
| `Modules/window_position.py` | 91 | Window geometry save/restore |
| `Modules/settings_manager.py` | 82 | `SettingsManager`, JSON helpers, settings proxy |
| `Modules/ui_tk_style.py` | 57 | Raw-tk widget styling + dark titlebar |
| `tests/test_imports.py` | 47 | Import-graph smoke test |
