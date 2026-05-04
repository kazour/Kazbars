# Architectural Map

**Current as of:** 2026-05-04 (after the audit-cleanup pass: pure data layer extracted (`buff_database.py` + `buff_xml.py`) so `tests/test_buff_xml.py` and `tests/test_grids_generator.py` collect without `ttkbootstrap`; `GridEditorPanel` extracted to its own module with the private `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps; new `labeled_spinbox`, `labeled_combobox`, `draw_grid_cells` helpers in `ui_widgets` consolidating the three labeled-widget patterns from `grids_panel`; `combat_monitor` lock now actually covers `log_path`/`last_position`/`file_handle` writes; `pywinstyles` declared in deps; `update_check` URLs rebranded; `MAX_TOTAL_SLOTS` deduped; `CodeGenerator.app_version` made required; `build_grids` exception path now logs traceback. New `tests/test_cluster_isolation.py` makes the Live Tracker isolation rule load-bearing rather than aspirational.)
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
- `ui_helpers` holds design tokens only (fonts, colors, padding, BTN_*, INPUT_WIDTH_*, canvas-geometry constants, SCANLINE_ALPHA) + `setup_custom_styles` + `style_treeview_heading` (called post-Treeview-construction because ttkbootstrap rebuilds `Treeview.Heading` lazily on first instantiation, clobbering boot-time styling). Leaf — imports nothing internal.
- `ui_widgets` adds the builder layer: `blend_alpha`, `CollapsibleSection`, tooltips, dialog/app headers, event bindings, `debounced_callback`.
- `ui_components` adds stateful composites: `ToastManager` (coalesce-by-key for spammy emitters; single trailing `update_idletasks` in `_reposition`), `DragReorderManager`, `create_scrollable_frame`, global mousewheel routing.
- `ui_tk_style` handles raw-tk widget styling + dark-titlebar monkey-patch.
- `custom_menu_bar` is the dark-themed Canvas-based menu bar (was in `ui_components`; extracted for size + single-consumer isolation).

### App state
```
settings_manager  ← window_position
```
Window-position helpers reach settings via the public `get_setting`/`set_setting` API, not the `_settings` global directly.

### Grid editing
```
grid_model  ← grid_dialogs  ← grid_editor_panel  ← grids_panel
            (also pulls settings_manager, window_position, ui_*)
```
- `grid_editor_panel` owns the per-row collapsible card (`GridEditorPanel`) and the private `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps that drive its three comboboxes. `grids_panel` is the container (toolbar, scrollable list, profile load/save bridge).

### Buff database (pure data layer)
```
buff_database  ← database_editor   (UI; dialogs, treeview)
buff_xml       ← buff_display_editor   (UI; HUD-XML editor dialog)
```
- `buff_database.py` and `buff_xml.py` import only stdlib — no Tk, no ttkbootstrap. Tests can collect them in a minimal CI image without the UI extra (`tests/test_buff_xml.py`, `tests/test_grids_generator.py`).

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

### kazbars-only satellites (extracted from KazBarsApp)
```
src/kazbars/app.py  → profile_io, game_folder, build_action, buff_display_editor, first_launch, custom_menu_bar, update_check
```
These modules are consumed only by `src/kazbars/app.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KazBarsApp` instance) as first arg. `KazBarsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `profile_io`, `build_loading`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup). `update_check` is the only satellite called directly (no delegator on `KazBarsApp`) since it has a single fire-and-forget caller in `__init__`; its worker thread schedules a named main-thread dispatcher (`_show_update_toast`) guarded by `winfo_exists()`.

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 15 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 12 | `ui_widgets` | Widest builder surface. Keep new helpers focused; don't expand unchecked. |
|  5 | `window_position`, `settings_manager` | Small stable APIs. |
|  4 | `ui_tk_style`, `ui_components` | Narrow surface — ripple is contained. |
|  3 | `grid_model`, `build_utils`, `build_executor`, `build_loading`, `live_tracker_settings` | Cluster leaves. |
|  2 | `grids_generator` | |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_io`, `game_folder`, `build_action`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor`, `update_check` | Each consumed by exactly one parent — low blast radius by design. |

## Conventions

- **Import style:** relative (`from .other import X`) inside `src/kazbars/`; absolute (`from kazbars.X import`) only from `src/kazbars/app.py` (top-level entry).
- **Where new code goes:**
  - Design token → `ui_helpers`
  - Reusable widget builder / event binding / small helper → `ui_widgets`
  - Stateful widget class or window-scope helper → `ui_components`
  - Raw-tk (Listbox/Text/Canvas) styling → `ui_tk_style`
  - Window geometry → `window_position`
  - Settings read/write → `settings_manager` (don't re-introduce UI-layer state)
  - Root-window logic (new menu action, new app-state flow) → extract to a new `src/kazbars/<concern>.py` taking `app` as first arg, add a one-line delegator on `KazBarsApp` if it has internal callers. Don't grow `src/kazbars/app.py`.
- **Cluster isolation:** the Live Tracker cluster must not be imported from outside itself (except `app.py`), and its members must not import other panels (cluster + shared infrastructure only). Enforced by `tests/test_cluster_isolation.py`.
- **Toasts:** every toast goes through `app_toast(widget, message, style, duration=, key=, on_click=)` in `ui_widgets`. The walker resolves `.toast` from the widget's ancestry, so callers don't need a direct `ToastManager` reference. Pass `key=` for any emitter that can fire repeatedly in a short burst (spinbox auto-repeat is the canonical case) — same key replaces the live toast in place instead of stacking. Don't reintroduce `obj.toast.show(...)` direct calls — they bypass the walker, fragment defaults, and force a `toast=` constructor seam.

## Smoke tests

Plain-Python pytest cases guard the failure modes we've actually hit.

- **`tests/test_imports.py`** — auto-discovers every `src/kazbars/*.py` + `kazbars` and imports each. Catches missing symbols, wrong-module references, and cycles. Add nothing — new modules are picked up automatically.
- **`tests/test_data_integrity.py`** — validates every buff reference in `assets/kazbars/Default.json` (whitelists + slot assignments) resolves to a `Database.json` entry, and that `Database.json.default` matches `Database.json` byte-for-byte.
- **`tests/test_buff_xml.py`** — round-trips the pure XML helpers in `buff_xml.py`: attribute extraction, surgical attribute replacement (other bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the filter whitespace normaliser, and the no-`<BuffListView>` guard. Covers the regex contract since the module deliberately uses no XML parser. Imports only `kazbars.buff_xml` — no Tk required.
- **`tests/test_grids_generator.py`** — asserts `CodeGenerator(include_console=False)` produces zero `console.` / `KzGridsConsole` substrings (so MTASC won't fail to resolve a missing class) and `include_console=True` reproduces the original hooks (instantiation, log calls, preview wiring, persistence keys). Belt-and-suspenders test that the default is `False`. Imports `BuffDatabase` from the pure `kazbars.buff_database` — no Tk required.
- **`tests/test_cluster_isolation.py`** — static-import guard for the Live Tracker cluster. Walks every `src/kazbars/*.py` via `ast.parse`. Asserts (a) no module outside the cluster (except `app.py`) imports a cluster member, and (b) cluster members import only stdlib + cluster + shared infrastructure (`ui_*`, `settings_manager`, `window_position`, `paths`, `custom_menu_bar`). Makes the cluster isolation rule load-bearing.

Run before every commit touching code or data:
```bash
pytest tests/
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `src/kazbars/grids_panel.py` | 617 | `GridsPanel` container, toolbar, scrollable list. Per-row card lives in `grid_editor_panel.py` |
| `src/kazbars/grid_editor_panel.py` | 646 | `GridEditorPanel` (per-row collapsible card) + module-level `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps |
| `src/kazbars/database_editor.py` | 750 | Buff DB UI (treeview, dialogs, category management). Pure data layer in `buff_database.py` |
| `src/kazbars/grid_dialogs.py` | 874 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `src/kazbars/build_loading.py` | 797 | Build-progress screen + welcome/about popups |
| `src/kazbars/buff_display_editor.py` | 563 | Default Buff Bars dialog (UI). Pure XML helpers in `buff_xml.py` |
| `src/kazbars/buff_xml.py` | 215 | AoC HUD XML helpers (regex-only). Pure — no Tk/ttkbootstrap, importable from CI without UI extra |
| `src/kazbars/buff_database.py` | 140 | `BuffDatabase` class — JSON load/save, in-memory indexes, search. Pure — no Tk |
| `src/kazbars/app.py` | 585 | Entry point + `KazBarsApp` root window (widgets, menu, lifecycle) |
| `src/kazbars/ui_widgets.py` | 675 | Widget builders, tooltips, bindings, `CollapsibleSection` (with `set_dimmed`), `blend_alpha`, `flash_status_bar`, `app_toast`, `labeled_spinbox`/`labeled_combobox`, `draw_grid_cells` |
| `src/kazbars/live_tracker_panel.py` | 575 | Live Tracker Toplevel orchestrator |
| `src/kazbars/timer_overlay.py` | 542 | In-game transparent timer overlay (two-canvas docked layout, stroke rendering, click-through lock) |
| `src/kazbars/ui_components.py` | 451 | `ToastManager` (coalesce-by-key, in-place text update), `DragReorderManager`, scrollable frame |
| `src/kazbars/grids_generator.py` | 472 | AS2 code generation from grid configs (with optional console hooks via `include_console` flag) |
| `src/kazbars/boss_timer.py` | 381 | Boss timer state + UI |
| `src/kazbars/instructions_panel.py` | 403 | Help/instructions view |
| `src/kazbars/first_launch.py` | 361 | First-launch dialog + post-dialog orchestrator (`run_first_launch`) |
| `src/kazbars/custom_menu_bar.py` | 402 | Canvas-based dark menu bar (active-cascade phosphor underline; ttkb-safe Canvas spacers; supports `command`, `separator`, `checkbutton` entries) |
| `src/kazbars/combat_monitor.py` | 294 | Combat log parser feeding the tracker |
| `src/kazbars/build_executor.py` | 238 | MTASC compile + deploy |
| `build.py` | 225 | PyInstaller build driver |
| `src/kazbars/profile_io.py` | 219 | Profile load (read+apply split) / save (build+write+commit, `silent=` for piggyback saves) / new / open + missing-buff warning |
| `src/kazbars/game_folder.py` | 192 | Game folder UI + Aoc.exe bypass (with install/remove reconciler) + uninstall |
| `tests/test_buff_xml.py` | 175 | Round-trip smoke test for `buff_display_editor` XML helpers |
| `src/kazbars/build_action.py` | 169 | Build & Install flow |
| `src/kazbars/ui_helpers.py` | 193 | Design tokens + `setup_custom_styles` + `style_treeview_heading` |
| `src/kazbars/live_tracker_settings.py` | 168 | Tracker persistence (with one-shot legacy filename migration) |
| `src/kazbars/grid_model.py` | 117 | Grid dataclasses + `parse_resolution` helper |
| `tests/test_data_integrity.py` | 103 | Buff-ref resolution smoke test |
| `src/kazbars/build_utils.py` | 98 | Compiler discovery + path helpers |
| `src/kazbars/window_position.py` | 91 | Window geometry save/restore |
| `src/kazbars/settings_manager.py` | 82 | `SettingsManager`, JSON helpers, settings proxy |
| `src/kazbars/update_check.py` | 69 | Background GitHub release check + named main-thread toast dispatcher |
| `src/kazbars/ui_tk_style.py` | 57 | Raw-tk widget styling + dark titlebar |
| `tests/test_imports.py` | 33 | Import-graph smoke test |
| `tests/test_grids_generator.py` | 103 | `CodeGenerator.include_console` on/off output checks |
| `tests/test_cluster_isolation.py` | 101 | Static-import guard for the Live Tracker cluster (no inbound except `app.py`; cluster imports stdlib + cluster + shared infrastructure only) |
