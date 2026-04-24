# Architectural Map

**Current as of:** 2026-04-24
**Purpose:** Module topology, dependencies, and coupling hotspots. Updated alongside code changes — if you edit this file, commit it with the code. `CLAUDE.md` has the short version; this file has the detail that doesn't fit there.

## Dependency clusters

All arrows point in the "imports from" direction. Every chain terminates — **no cycles**.

### UI primitives (tokens at the root)
```
ui_helpers  ← ui_tk_style
ui_helpers  ← ui_widgets          ← ui_components
                                    (also imports ui_tk_style)
```
- `ui_helpers` holds design tokens only (fonts, colors, padding, BTN_*, SCANLINE_ALPHA) + `setup_custom_styles`. It is leaf — imports nothing internal.
- `ui_widgets` adds the builder layer: `blend_alpha`, `CollapsibleSection`, tooltips, dialog/app headers, event bindings, `debounced_callback`.
- `ui_components` adds stateful composites: `ToastManager`, `DragReorderManager`, `CustomMenuBar`, `create_scrollable_frame`, global mousewheel routing.
- `ui_tk_style` handles raw-tk widget styling + dark-titlebar monkey-patch.

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
             ← build_executor  ← first_launch
build_loading  (independent, just consumes UI primitives)
```

### Live Tracker (isolated — no other panel imports from it)
```
live_tracker_settings  ← boss_timer
                       ← timer_overlay
                       ← combat_monitor
                       ← live_tracker_panel  (orchestrator)
```

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 12 | `ui_helpers` | Pure tokens — high fan-in is expected and acceptable for shared constants. Keep the surface small. |
| 9 | `ui_widgets` | Widest builder surface. Keep new helpers focused; don't expand it unchecked. |
| 5 | `window_position` | Stable API — 4 functions. |
| 4 | `settings_manager` | 3 public functions. |
| 4 | `ui_tk_style` | Small, stable. |
| 4 | `ui_components` | Heavy but narrow — touching `CustomMenuBar` barely ripples. |
| 3 | `grid_model`, `build_utils`, `live_tracker_settings` | Cluster leaves — low blast radius. |

Post-split, fan-in is spread across six focused modules instead of concentrated in one 1,497-line file. A color/padding token tweak still hits many files (because tokens are *meant* to be shared), but a change to `ToastManager` or `CustomMenuBar` rebuilds only four.

## Conventions

- **Import style:** relative (`from .other import X`) inside `Modules/`; absolute (`from Modules.X import`) only from `kzgrids.py` (top-level entry).
- **Where new code goes:**
  - Design token → `ui_helpers`
  - Reusable widget builder / event binding / small helper → `ui_widgets`
  - Stateful widget class or window-scope helper → `ui_components`
  - Raw-tk (Listbox/Text/Canvas) styling → `ui_tk_style`
  - Window geometry → `window_position`
  - Settings read/write → `settings_manager` (don't re-introduce UI-layer state)
- **Cluster isolation:** the Live Tracker cluster must not be imported from outside itself. Enforced by convention, not code.

## Known trade-offs / deferred work

- **`build.py` has a defensive `--hidden-import` block** listing every `Modules/*` file. PyInstaller's static analysis should discover them (all imports are explicit), but the block stays until there's time to test removing it.
- **`ui_components.py` is 739 lines** — `CustomMenuBar` alone is ~300. Could be split further into `menu_bar.py`, but no concrete driver forces it yet.
- **`kzgrids.py` is 1,152 lines** holding both `SettingsManager` (dataclass-ish) and `KzGridsApp` (the whole root window). Candidate for a future split, not urgent.
- **Test coverage: none.** Refactors verify via `python -c "import kzgrids; from Modules import ..."` (walks the full import graph — any missing symbol / wrong module / cycle surfaces here). Runtime correctness still relies on manual smoke-testing.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `kzgrids.py` | 1152 | Entry point, `SettingsManager`, `KzGridsApp` root window |
| `build.py` | 246 | PyInstaller build driver |
| `Modules/grids_panel.py` | 1155 | Grid list UI, grid management |
| `Modules/build_loading.py` | 914 | Build-progress screen + welcome/about popups |
| `Modules/database_editor.py` | 904 | Buff DB CRUD, search, filtering |
| `Modules/grid_dialogs.py` | 742 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `Modules/ui_components.py` | 739 | `ToastManager`, `DragReorderManager`, `CustomMenuBar`, scrollable frame |
| `Modules/ui_widgets.py` | 497 | Widget builders, tooltips, bindings, `CollapsibleSection`, `blend_alpha` |
| `Modules/live_tracker_panel.py` | 489 | Live Tracker Toplevel orchestrator |
| `Modules/boss_timer.py` | 441 | Boss timer state + UI |
| `Modules/timer_overlay.py` | 440 | In-game transparent timer overlay |
| `Modules/grids_generator.py` | 424 | AS2 code generation from grid configs |
| `Modules/instructions_panel.py` | 372 | Help/instructions view |
| `Modules/combat_monitor.py` | 313 | Combat log parser feeding the tracker |
| `Modules/first_launch.py` | 284 | One-time game-folder setup flow |
| `Modules/build_executor.py` | 227 | MTASC compile + deploy |
| `Modules/live_tracker_settings.py` | 145 | Tracker persistence |
| `Modules/ui_helpers.py` | 129 | Design tokens + `setup_custom_styles` |
| `Modules/grid_model.py` | 108 | Grid dataclasses with `to_dict`/`from_dict` |
| `Modules/build_utils.py` | 98 | Compiler discovery + path helpers |
| `Modules/window_position.py` | 91 | Window geometry save/restore |
| `Modules/ui_tk_style.py` | 57 | Raw-tk widget styling + dark titlebar |
| `Modules/settings_manager.py` | 29 | Settings proxy (`init_settings`, `get/set_setting`) |
