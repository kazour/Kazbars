# Architectural Map

**Current as of:** 2026-05-25 (after the overlay-consolidation pass: both overlays unified onto a shared `overlay_engine.HudOverlay` + `OverlayConfig`; one app-owned `focus_watcher.ForegroundWatcher` replaced the per-cluster focus polls; the foreground probe moved to a pure `foreground.py`; `paths.py` centralizes asset/app-path resolution. Inventory line counts + file list resynced against the tree, and the new `foreground`/`focus_watcher`/`paths` modules + `test_overlay_config`/`test_focus_watcher`/`test_foreground`/`test_timer_sizing`/`test_toggle_button_state`/`test_log_name` tests added to the inventory below.)
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

**Null-icon custom icons.** Some AoC buffs return `m_Icon.GetInstance()==0` (no game icon → the slot rendered blank). `grids_generator.CUSTOM_ICON_LINKAGE` maps such buff IDs → baked symbol linkage names in `base.swf` (`IcoSlow30/40/45/60` for the ice-gem slows), emitted into `KazBarsData.CUSTOMICON`. `KazBars_core.as.template`'s `loadIcon` routes through `attachBaked` to attach the symbol as a slot sibling at **dynamic depth 8**, with a shared **`IcoNull`** fallback for any other no-icon buff — so no tracked buff shows a blank slot. The slot's authored art (bg/icoMask/m_icon/frame, depths 1/3/5/9 in the FLA) becomes timeline content in the negative reserved depth range at runtime, so depth 8 sits above it; the timer/stack TextFields are pinned to fixed depths **10–13** (`KazBarsSlot`, not `getNextHighestDepth()`) so they render above the icon rather than under it. The flash (`animSlot`) pulses `s.cust` for baked icons, `m_icon` for RDB icons. The rounded crop is baked into the art (PNG inset ~56×56 in a 64×64 canvas), **not masked** at runtime: AoC's Scaleform renderer applies masks only to `loadClip` content (the RDB game icons), never to `attachMovie`'d content.

### Live Tracker (isolated — no other panel imports from it)
```
live_tracker_settings  ← boss_timer
                       ← timer_overlay
                       ← combat_monitor
                       ← live_tracker_panel  (orchestrator)
```

### Deeps (isolated — no other panel imports from it)
```
deeps_parsers         ← deeps_trackers       ← deeps_meter ← deeps_panel
deeps_rolling_window  ← deeps_trackers
deeps_settings                               ←              deeps_panel
                                                deeps_meter ← deeps_overlay  ← deeps_panel
                                                              (MeterSnapshot only)
```
Real-time meter showing five numbers — DPS out, DPS in, HPS out, HPS in, and
ΔHP in (HPS in − DPS in). Mirrors the Live Tracker shape (data layer →
background tail thread → transparent overlay → configuration panel) but stays
a separate cluster — `tests/test_cluster_isolation.py` enforces that neither
cluster imports the other. `deeps_parsers` is pure (no Tk, no threading); the
damage/heal regexes are byte-identical to `Deeps/rust/aoc-damage` and
`Deeps/rust/aoc-heal` (the external Rust project they were ported from). Pet
damage is the one intentional divergence: KazBars counts only the logger's own
pet (`Your`-prefixed lines), not team-mates' pets of the same kind.

### Shared overlay layer (both clusters reach through it)
```
foreground       (pure ctypes probe — app_or_game_foreground)
  ← focus_watcher (ForegroundWatcher: app-owned tick, fan-out suppression)  ← app.py
overlay_engine   (LayeredOverlay win32 blit ← HudOverlay chrome/drag/lock/visibility ← OverlayConfig)
  ← deeps_overlay, timer_overlay        (thin render_content + measure consumers)
  ← deeps_settings, live_tracker_settings  (FONT_FAMILY_CHOICES + OverlayConfig adapters)
```
Both overlays render on one `HudOverlay` over the untouched `LayeredOverlay` blit; each consumer supplies a `render_content(draw, w, h)` + a `measure()` and reads/writes a shared `OverlayConfig` (per-cluster settings adapters map disk keys, which are **not** renamed). Focus-gating is a single app-owned `ForegroundWatcher` (constructed in `KazBarsApp.__init__`, stopped in `_on_close`); overlays `register`/`unregister` and expose `set_focus_suppressed`. The foreground probe lives once in pure `foreground.py` (no Tk/PIL); only the `ForegroundWatcher` consumes it now — the Deeps meter no longer probes focus (`MeterSnapshot` dropped `aoc_in_focus`). Both overlays follow **Hide-on-Stop** (visible only while monitoring) and the timer overlay **auto-sizes** from its font (no resize handle).

### kazbars-only satellites (extracted from KazBarsApp)
```
src/kazbars/app.py  → profile_io, game_folder, game_resolution, build_action, buff_display_editor, first_launch, custom_menu_bar, update_check, settings_backup
```
These modules are consumed only by `src/kazbars/app.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KazBarsApp` instance) as first arg. `KazBarsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `profile_io`, `build_loading`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup). `update_check` is the only satellite called directly (no delegator on `KazBarsApp`) since it has a single fire-and-forget caller in `__init__`; its worker thread schedules a named main-thread dispatcher (`_show_update_toast`) guarded by `winfo_exists()`.

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 15 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 12 | `ui_widgets` | Widest builder surface. Keep new helpers focused; don't expand unchecked. |
|  5 | `window_position`, `settings_manager` | Small stable APIs. |
|  4 | `ui_tk_style`, `ui_components`, `overlay_engine` | Narrow surface — ripple is contained. `overlay_engine` feeds both overlays + both settings adapters. |
|  3 | `grid_model`, `build_utils`, `build_executor`, `build_loading`, `live_tracker_settings`, `paths` | Cluster leaves. `paths` is imported directly by `app.py`, `build_utils`, `deeps_parsers` (everyone else gets paths via the `app` object). |
|  2 | `grids_generator` | |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_io`, `game_folder`, `game_resolution`, `build_action`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor`, `update_check`, `settings_backup`, `foreground`, `focus_watcher` | Each consumed by exactly one parent — low blast radius by design. (`foreground` ← `focus_watcher`; `focus_watcher` ← `app.py`.) |

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
- **Cluster isolation:** the Live Tracker cluster AND the Deeps cluster each must not be imported from outside themselves (except `app.py`), and their members must not import other panels (cluster + shared infrastructure only). The two clusters also must not cross-import each other. Shared infrastructure now includes `overlay_engine`, `foreground`, and `focus_watcher` (both clusters reach the overlay + focus layer through these, never through each other). Enforced by `tests/test_cluster_isolation.py` (parametrised over both).
- **Toasts:** every toast goes through `app_toast(widget, message, style, duration=, key=, on_click=)` in `ui_widgets`. The walker resolves `.toast` from the widget's ancestry, so callers don't need a direct `ToastManager` reference. Pass `key=` for any emitter that can fire repeatedly in a short burst (spinbox auto-repeat is the canonical case) — same key replaces the live toast in place instead of stacking. Don't reintroduce `obj.toast.show(...)` direct calls — they bypass the walker, fragment defaults, and force a `toast=` constructor seam.
- **Type-check gate (mypy):** the gate is the **Tk-free logic core** — the modules that import neither `tkinter` nor `ttkbootstrap` — listed explicitly in `[tool.mypy] files` in `pyproject.toml`. Bare `mypy` (CI's *blocking* step) checks exactly that set, which must stay clean; a regression there fails CI. The full repo (`mypy src/kazbars`) runs **advisory-only** (`continue-on-error: true`) because ttkbootstrap's runtime `bootstyle` kwargs + dynamic widget typing emit ~80 errors mypy can't resolve. When you add a module that imports neither Tk lib, add it to the `files` list to fold it into the gate; a Tk-touching module stays out (advisory-only) by design. The gate is includes-based on purpose — a new module is *not* gated until explicitly listed, so forgetting to add one fails safe (still surfaced by the advisory pass).

## Smoke tests

Plain-Python pytest cases guard the failure modes we've actually hit.

- **`tests/test_imports.py`** — auto-discovers every `src/kazbars/*.py` + `kazbars` and imports each. Catches missing symbols, wrong-module references, and cycles. Add nothing — new modules are picked up automatically.
- **`tests/test_data_integrity.py`** — validates every buff reference in `assets/kazbars/Default.json` (whitelists + slot assignments) resolves to a `Database.json` entry, and that `Database.json.default` matches `Database.json` byte-for-byte.
- **`tests/test_buff_xml.py`** — round-trips the pure XML helpers in `buff_xml.py`: attribute extraction, surgical attribute replacement (other bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the filter whitespace normaliser, and the no-`<BuffListView>` guard. Covers the regex contract since the module deliberately uses no XML parser. Imports only `kazbars.buff_xml` — no Tk required.
- **`tests/test_grids_generator.py`** — asserts `CodeGenerator(include_console=False)` produces zero `console.` / `KazBarsConsole` substrings (so MTASC won't fail to resolve a missing class) and `include_console=True` reproduces the original hooks (instantiation, log calls, preview wiring, persistence keys). Same on/off coverage for the cast-timer overlay: `cast_config=None` (and a both-sides-off config) emits zero `KazBarsCastTimer`/`castTimer`/`{{CAST_*}}`/`d.CAST` references; an enabled config emits the instantiation, configure call, lifecycle hooks, and a numeric-hex `color:` literal in `d.CAST`. Belt-and-suspenders that both default to off. Imports `BuffDatabase` from the pure `kazbars.buff_database` — no Tk required.
- **`tests/test_cast_timer.py`** — `cast_timer` config layer: default keys present and disabled, `is_enabled` true iff a side is on, unknown keys dropped / missing filled, position + font-size clamping, color/font/display sanitization, non-dict input → defaults. Pure — no Tk.
- **`tests/test_cluster_isolation.py`** — static-import guard for the Live Tracker AND Deeps clusters. Walks every `src/kazbars/*.py` via `ast.parse`. Asserts (a) no module outside a cluster (except `app.py`) imports a cluster member, (b) cluster members import only stdlib + cluster + shared infrastructure (`ui_*`, `settings_manager`, `window_position`, `paths`, `custom_menu_bar`, `overlay_engine`, `foreground`, `focus_watcher`), and (c) the two clusters never cross-import. Parametrised over both clusters.
- **`tests/test_deeps_parsers.py`** — 163 behavior-table cases ported from `Deeps/rust/aoc-damage` and `aoc-heal` test files. Covers heal-verb filter, self-damage filter, the own-pet `Your`-gate (team-mates' pets excluded), the three heal classifications, and the timestamp stripper.- **`tests/test_deeps_rolling_window.py`** — 13 cases on the rolling-window primitive (record/prune/sum_since/count_since/first_event, decay during silence, exact-boundary inclusion).
- **`tests/test_deeps_trackers.py`** — 28 cases on the four trackers + Snapshot. Warm-up boundaries, decay, reset re-anchor, pet damage feeding the outgoing window, and the per-bucket warm-up rule for heals.
- **`tests/test_deeps_settings.py`** — 84 cases on defaults, per-key validation (incl. the readout-tuning keys `window_seconds`/`smoothing`/`round_step`/`refresh_ms`), file I/O round-trip, corrupt/partial-file fallback.
- **`tests/test_deeps_meter.py`** — 36 cases on `newest_combat_log` selection, `MeterSnapshot` shape, `_process_line` dispatch (own-pet gate + pet-toggle), lifecycle (start/stop/restart), `set_window_seconds` tracker-recreation + in-flight reset, `OLD_LOG` detection on stale files, and a Windows-only end-to-end `TAILING` check using a held-open file.
- **`tests/test_deeps_overlay.py`** — 30 cases on the pure helpers (`_format_rate`, `_format_signed_int`, `_lerp_color`), the five-cell IDs and labels, and `_DisplaySmoother` (snap-when-off, EMA easing + convergence, None-reset, coarse rounding, redraw-cadence hold). Visual behaviour is covered by manual `/smoke`.
- **`tests/test_resolution_scaling.py`** — anchor-formula regression: `grid_model.scale_grid_position` predictions for 1080p → 1440p / 4K against `Default.json` (X center-anchored, Y bottom-anchored).
- **`tests/test_settings_backup.py`** — `settings_backup` pure layer: backup→restore byte-identity (incl. Deeps + Live Tracker settings), `*.tmp` exclusion, manifest accept/reject, prefs locator, zip-slip guard.
- **`tests/test_overlay_config.py`** — `OverlayConfig` dataclass + per-cluster adapters (Deeps `overlay_*` keys ↔ Live Tracker bare keys) round-trip without dropping fields.
- **`tests/test_focus_watcher.py`** — `ForegroundWatcher` tick + fan-out: registered overlays get `set_focus_suppressed` flips driven by an injected probe (no display required).
- **`tests/test_foreground.py`** — `app_or_game_foreground`: own-process gate (any KazBars window keeps the gate open), AoC match, and the show-on-probe-failure default.
- **`tests/test_timer_sizing.py`** — Live Tracker overlay font-derived auto-size (`_measure`) bounds across font sizes.
- **`tests/test_toggle_button_state.py`** — pure `toggle_button_state` label/bootstyle flip shared by both panels' single Start↔Stop toggle.
- **`tests/test_log_name.py`** — `sanitize_log_name` trims a CombatLog filename to `CombatLog_HHMM`.
- **`tests/test_boss_timer.py`** — `BossTimer` cycle/syphon/double-seed state transitions + the phase state machine at representative elapsed times (driven via `cycle_start_time`, no sleeps).
- **`tests/test_combat_monitor.py`** — `_process_line` trigger dispatch (seed/fixation/syphon → `BossTimer`), player-name extraction, latest-log discovery + folder selection on a tmp folder, and the start-without-folder guard.
- **`tests/test_build_executor.py`** — install/uninstall orchestration on a tmp game folder (no MTASC, no Tk): SWF + script deployment in standard *and* Aoc.exe modes, `cleanup_legacy_files` (legacy SWFs/Aoc dirs removed, current `KazBars.swf` kept), `create_scripts` marker handling, `write_xml_add_files`, `detect_aoc_launcher`, `uninstall_from_client` (incl. marker-strip + nothing-to-remove), and `get_running_game_process` argv/match/per-process-exception isolation (monkeypatched `tasklist`).
- **`tests/test_build_compile.py`** — MTASC compile-integration: runs the whole `build_grids` codegen through the bundled `mtasc.exe` and asserts exit-0 — the only check bridging Python-side correctness to SWF-side. Pins the AS2-escaping fix end-to-end (a grid `id` with quote/newline/backslash must still compile) and compiles the console + cast-timer feature variants. Windows + bundled-compiler gated (skips elsewhere); runs on CI (`windows-latest`).

Run before every commit touching code or data:
```bash
pytest tests/
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `src/kazbars/grids_panel.py` | 628 | `GridsPanel` container, toolbar, scrollable list, anchor-based `scale_to_resolution`, frozen `CastTimerStrip` pinned above the list. Per-row card lives in `grid_editor_panel.py` |
| `src/kazbars/grid_editor_panel.py` | 617 | `GridEditorPanel` (per-row collapsible card) + module-level `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps; X/Y bounds pulled from `game_resolution` setting; X/Y fields built via shared `ui_widgets.position_entry` |
| `src/kazbars/database_editor.py` | 750 | Buff DB UI (treeview, dialogs, category management). Pure data layer in `buff_database.py` |
| `src/kazbars/grid_dialogs.py` | 874 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `src/kazbars/build_loading.py` | 806 | Build-progress screen + welcome/about popups |
| `src/kazbars/buff_display_editor.py` | 575 | Default Buff Bars dialog (UI). Pure XML helpers in `buff_xml.py` |
| `src/kazbars/buff_xml.py` | 215 | AoC HUD XML helpers (regex-only). Pure — no Tk/ttkbootstrap, importable from CI without UI extra |
| `src/kazbars/buff_database.py` | 140 | `BuffDatabase` class — JSON load/save, in-memory indexes, search. Pure — no Tk |
| `src/kazbars/app.py` | 627 | Entry point + `KazBarsApp` root window (widgets, menu, lifecycle) |
| `src/kazbars/ui_widgets.py` | 1033 | Widget builders, tooltips, bindings, `CollapsibleSection` (with `set_dimmed`), `ColorSwatch` (rounded swatch + themed `ColorChooserDialog`) + `create_rounded_rect`, `blend_alpha`, `flash_status_bar`, `app_toast`, `labeled_spinbox`/`labeled_combobox`/`position_entry`, `draw_grid_cells` |
| `src/kazbars/live_tracker_panel.py` | 533 | Live Tracker Toplevel orchestrator |
| `src/kazbars/timer_overlay.py` | 387 | In-game transparent Live Tracker overlay — a `HudOverlay` consumer (`_render_content`: two text rows + cycle-timer dock with 8-direction stroke; `_measure`: font-derived auto-size, no resize handle) |
| `src/kazbars/ui_components.py` | 454 | `ToastManager` (coalesce-by-key, in-place text update), `DragReorderManager`, scrollable frame |
| `src/kazbars/grids_generator.py` | 579 | AS2 code generation from grid configs (optional console hooks via `include_console`; optional cast-timer overlay hooks + `d.CAST` block via `cast_config` → `include_cast_timer`). Also holds `CUSTOM_ICON_LINKAGE` (null-icon buff IDs → baked `base.swf` symbol names), emitted into `KazBarsData.CUSTOMICON` |
| `src/kazbars/boss_timer.py` | 399 | Boss timer state + UI |
| `src/kazbars/instructions_panel.py` | 403 | Help/instructions view |
| `src/kazbars/first_launch.py` | 364 | First-launch dialog + post-dialog orchestrator (`run_first_launch`) |
| `src/kazbars/custom_menu_bar.py` | 402 | Canvas-based dark menu bar (active-cascade phosphor underline; ttkb-safe Canvas spacers; supports `command`, `separator`, `checkbutton` entries) |
| `src/kazbars/combat_monitor.py` | 289 | Combat log parser feeding the tracker |
| `src/kazbars/cast_timer_strip.py` | 348 | Frozen `CastTimerStrip` card (collapsed + master-off by default) for the cast-timer overlay. Header: one master Enabled toggle + title-adjacent Player/Target status tags + muted `overlay`. Body: a single settings row (independent Player/Target X/Y + Bold/Size/Display/Color, font fixed to Arial) + right-side sample preview. Master enables both sides together (`enableP == enableT == enabled`); X/Y grey out when off. Chrome mirrors a grid card — reserved handle gutter, shared `position_entry`, rose card border |
| `src/kazbars/build_executor.py` | 240 | MTASC compile + deploy |
| `src/kazbars/profile_io.py` | 228 | Profile load (read+apply split, with auto-anchor-scale on resolution mismatch) / save (build+write+commit, `silent=` for piggyback saves) / new / open + missing-buff warning. Persists the `cast_timer` block alongside `grids` |
| `src/kazbars/game_folder.py` | 192 | Game folder UI + Aoc.exe bypass (with install/remove reconciler) + uninstall |
| `src/kazbars/game_resolution.py` | 104 | Game resolution dialog + anchor-rescale all loaded grids on apply |
| `src/kazbars/settings_backup.py` | 394 | Backup & Restore dialog + pure zip layer (`write_backup_zip`/`read_manifest`/`restore_zip`, `funcom_prefs_path`, `_funcom_summary`) — bundles `%LOCALAPPDATA%\Funcom\Conan\Prefs` + KazBars `profiles/` + the whole `settings/` dir (app + Deeps + Live Tracker) into one zip; restore snapshots first, guards zip-slip, resyncs settings. Isolated satellite, no cross-imports |
| `tests/test_buff_xml.py` | 142 | Round-trip smoke test for `buff_display_editor` XML helpers |
| `src/kazbars/build_action.py` | 170 | Build & Install flow |
| `src/kazbars/ui_helpers.py` | 200 | Design tokens + `setup_custom_styles` + `style_treeview_heading` |
| `src/kazbars/live_tracker_settings.py` | 246 | Tracker persistence (with one-shot legacy filename migration) |
| `src/kazbars/grid_model.py` | 150 | Grid dataclasses, `parse_resolution`, `get_game_resolution_or_default`, anchor-based `scale_grid_position` (X center / Y bottom anchored) |
| `tests/test_data_integrity.py` | 97 | Buff-ref resolution smoke test |
| `src/kazbars/build_utils.py` | 98 | Compiler discovery + path helpers |
| `src/kazbars/cast_timer.py` | 113 | Cast-timer overlay config (pure data): defaults, validation, `is_enabled` gate. No Tk |
| `src/kazbars/window_position.py` | 110 | Window geometry save/restore |
| `src/kazbars/settings_manager.py` | 104 | `SettingsManager` (incl. `reload()` to resync in-memory state from disk after a restore), JSON helpers, settings proxy |
| `src/kazbars/update_check.py` | 69 | Background GitHub release check + named main-thread toast dispatcher |
| `src/kazbars/ui_tk_style.py` | 67 | Raw-tk widget styling + dark titlebar |
| `src/kazbars/foreground.py` | 111 | Pure ctypes foreground probe (`app_or_game_foreground`) — no Tk/PIL. Shared by both clusters + the `ForegroundWatcher`; defaults to "show" on any probe failure |
| `src/kazbars/focus_watcher.py` | 85 | `ForegroundWatcher` — one app-owned ~250 ms tick that probes foreground once and fans `set_focus_suppressed` out to every registered overlay. Replaced the per-cluster focus polls |
| `src/kazbars/paths.py` | 47 | Path constants: `PACKAGE_ROOT`/`ASSETS`/`KAZBARS_ASSETS` (bundled read-only assets, dev + frozen) + `app_path()` (user-writable runtime root next to the .exe) |
| `tests/test_imports.py` | 33 | Import-graph smoke test |
| `tests/test_grids_generator.py` | 175 | `CodeGenerator.include_console` AND `include_cast_timer` (via `cast_config`) on/off output checks |
| `tests/test_cast_timer.py` | 97 | `cast_timer` config defaults, clamping, color/enum sanitization, `is_enabled` build gate |
| `tests/test_cluster_isolation.py` | 180 | Static-import guard for the Live Tracker AND Deeps clusters (no inbound except `app.py`; cluster imports stdlib + cluster + shared infrastructure only; no cross-import) |
| `tests/test_resolution_scaling.py` | 93 | Anchor-formula regression test (`scale_grid_position` predictions for 1080p → 1440p / 4K against `Default.json`) |
| `tests/test_settings_backup.py` | 135 | `settings_backup` pure layer — backup→restore byte-identity (incl. Deeps + Live Tracker settings), `*.tmp` exclusion, manifest accept/reject, prefs locator, zip-slip guard |
| `tests/test_overlay_config.py` | 102 | `OverlayConfig` dataclass + per-cluster adapters (Deeps `overlay_*` keys / Live Tracker bare keys) round-trip |
| `tests/test_focus_watcher.py` | 96 | `ForegroundWatcher` tick + fan-out suppression with an injected probe (no display needed) |
| `tests/test_foreground.py` | 95 | `app_or_game_foreground` probe — own-process gate, AoC match, show-on-probe-failure default |
| `tests/test_timer_sizing.py` | 41 | Live Tracker overlay font-derived auto-size (`_measure`) bounds |
| `tests/test_toggle_button_state.py` | 41 | Pure `toggle_button_state` label/bootstyle flip shared by both panels' Start↔Stop toggle |
| `tests/test_log_name.py` | 22 | `sanitize_log_name` CombatLog filename trimming (`CombatLog-2026-05-16_2152` → `CombatLog_2152`) |
| `tests/test_boss_timer.py` | 151 | `BossTimer` cycle/syphon/double-seed transitions + phase state machine (time-driven, no sleeps) |
| `tests/test_combat_monitor.py` | 123 | `_process_line` dispatch, player extraction, latest-log discovery, start-without-folder guard |
| `tests/test_build_executor.py` | 297 | Install/uninstall orchestration (both modes), legacy cleanup, `create_scripts` markers, xml.add, launcher detect, `tasklist` argv — no MTASC/Tk |
| `tests/test_build_compile.py` | 120 | MTASC compile-integration — whole codegen → bundled `mtasc.exe` exit-0 (escaping end-to-end + console/cast variants); win32 + compiler gated |
| `src/kazbars/deeps_panel.py` | 874 | `DeepsPanel` Toplevel — status row, Start/Stop, Lock + Layout, appearance (font + size/background sliders), Readout card (window width + smoothing/round/refresh), Alarm & Tints thresholds, 5-cell visibility picker, pet toggle. Owns the meter + overlay + 100 ms UI tick + alarm hysteresis state machine |
| `src/kazbars/deeps_meter.py` | 452 | `DeepsMeter` daemon thread — tail loop, log rotation detection, `is_live` probe via `CreateFile` exclusive-share, configurable rolling-window width (`set_window_seconds` recreates the trackers). Publishes `MeterSnapshot` (focus is no longer probed here — the shared `ForegroundWatcher` owns it) |
| `src/kazbars/deeps_overlay.py` | 606 | Five-cell numbers display (DPS out/in, HPS out/in, ΔHP in). Two layouts (horizontal/vertical), 8-direction stroke text, 2 Hz alarm pulse on DPS-out, net-HP tints, click-through lock. `_DisplaySmoother` eases the drawn digits (EMA + coarse rounding + redraw-cadence gate); numbers use smoothed values, colors use the raw snapshot |
| `src/kazbars/overlay_engine.py` | 830 | Shared PIL + win32 overlay engine: `LayeredOverlay` (per-pixel-alpha win32 blit) + `HudOverlay` (shared backdrop / lock chrome / drag / visibility) + `OverlayConfig` (geometry+appearance dataclass) + `load_font`/`FONT_FAMILY_CHOICES`. Both the Deeps and Live Tracker overlays are thin `render_content` + `measure` consumers |
| `src/kazbars/deeps_parsers.py` | 408 | Pure parsers (no Tk, no threading). 5 entry points: `parse_outgoing_damage`, `parse_incoming_damage`, `parse_incoming_heal`, `parse_outgoing_heal`, `parse_pet_hit` (own-pet only). Damage/heal regexes byte-identical to `Deeps/rust/aoc-damage` + `aoc-heal` |
| `src/kazbars/deeps_trackers.py` | 221 | `DamageOutTracker`, `DamageInTracker`, `HealsInTracker` (3-bucket per-bucket warm-up), `HealsOutTracker`, `TrackerSnapshot` |
| `src/kazbars/deeps_settings.py` | 280 | `deeps_settings.json` defaults, per-key validation (incl. the readout-tuning keys: `window_seconds`, `smoothing`, `round_step`, `refresh_ms`), load/save |
| `src/kazbars/deeps_rolling_window.py` | 81 | `RollingWindow` data structure — record/prune/sum_since/count_since/first_event |
| `src/kazbars/assets/deeps/pets.json` | 81 | Pet-name registry — lifted from `Deeps/rust/aoc-damage/data/pets.json` |
| `tests/test_deeps_parsers.py` | 544 | 163 behavior-table cases from Deeps's Rust tests + the own-pet gate |
| `tests/test_deeps_meter.py` | 393 | 36 cases — file selection, lifecycle, `_process_line` dispatch, configurable-window reset, held-open-file end-to-end |
| `tests/test_deeps_trackers.py` | 288 | 28 cases — warm-up, decay, reset, per-bucket warm-up for heals |
| `tests/test_deeps_settings.py` | 330 | 84 cases — defaults, validation (incl. readout-tuning keys), round-trip, corrupt-file fallback |
| `tests/test_deeps_rolling_window.py` | 169 | 13 cases — primitive smoke + decay-during-silence |
| `tests/test_deeps_overlay.py` | 198 | 30 cases — pure helpers + 5-cell IDs/labels + `_DisplaySmoother` (EMA/rounding/cadence) (visual behaviour is `/smoke`) |