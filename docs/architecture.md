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

**Null-icon custom icons.** Some AoC buffs return `m_Icon.GetInstance()==0` (no game icon → the slot rendered blank). `grids_generator.CUSTOM_ICON_LINKAGE` maps such buff IDs → baked symbol linkage names in `base.swf` (`IcoSlow30/40/45/60` for the ice-gem slows), emitted into `KzGridsData.CUSTOMICON`. `KzGrids_core.as.template`'s `loadIcon` routes through `attachBaked` to attach the symbol as a slot sibling at **dynamic depth 8**, with a shared **`IcoNull`** fallback for any other no-icon buff — so no tracked buff shows a blank slot. The slot's authored art (bg/icoMask/m_icon/frame, depths 1/3/5/9 in the FLA) becomes timeline content in the negative reserved depth range at runtime, so depth 8 sits above it; the timer/stack TextFields are pinned to fixed depths **10–13** (`KzGridsSlot`, not `getNextHighestDepth()`) so they render above the icon rather than under it. The flash (`animSlot`) pulses `s.cust` for baked icons, `m_icon` for RDB icons. The rounded crop is baked into the art (PNG inset ~56×56 in a 64×64 canvas), **not masked** at runtime: AoC's Scaleform renderer applies masks only to `loadClip` content (the RDB game icons), never to `attachMovie`'d content.

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
`Deeps/rust/aoc-heal` and the parity test in `tests/test_deeps_parity.py` locks
their totals against the Rust source-of-truth (`Deeps/rust/parity-dump/`). Pet
damage is the one intentional divergence: KazBars counts only the logger's own
pet (`Your`-prefixed lines), not team-mates' pets of the same kind.

### Shared overlay layer (both clusters reach through it)
```
foreground       (pure ctypes probe — app_or_game_foreground)
  ← focus_watcher (ForegroundWatcher: app-owned tick, fan-out suppression)
  ← deeps_meter
overlay_engine   (LayeredOverlay win32 blit ← HudOverlay chrome/drag/lock/visibility ← OverlayConfig)
  ← deeps_overlay, timer_overlay  (thin render_content + measure consumers)
```
Both overlays render on one `HudOverlay` over the untouched `LayeredOverlay` blit; each consumer supplies a `render_content(draw, w, h)` + a `measure()` and reads/writes a shared `OverlayConfig` (per-cluster settings adapters map disk keys, which are **not** renamed). Focus-gating is a single app-owned `ForegroundWatcher` (constructed in `KazBarsApp.__init__`, stopped in `_on_close`); overlays `register`/`unregister` and expose `set_focus_suppressed`. The foreground probe lives once in pure `foreground.py` (no Tk/PIL), shared by the watcher and the Deeps meter — `MeterSnapshot` no longer carries `aoc_in_focus`. Both overlays follow **Hide-on-Stop** (visible only while monitoring) and the timer overlay **auto-sizes** from its font (no resize handle).

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
|  4 | `ui_tk_style`, `ui_components` | Narrow surface — ripple is contained. |
|  3 | `grid_model`, `build_utils`, `build_executor`, `build_loading`, `live_tracker_settings` | Cluster leaves. |
|  2 | `grids_generator` | |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_io`, `game_folder`, `game_resolution`, `build_action`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor`, `update_check`, `settings_backup` | Each consumed by exactly one parent — low blast radius by design. |

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

## Smoke tests

Plain-Python pytest cases guard the failure modes we've actually hit.

- **`tests/test_imports.py`** — auto-discovers every `src/kazbars/*.py` + `kazbars` and imports each. Catches missing symbols, wrong-module references, and cycles. Add nothing — new modules are picked up automatically.
- **`tests/test_data_integrity.py`** — validates every buff reference in `assets/kazbars/Default.json` (whitelists + slot assignments) resolves to a `Database.json` entry, and that `Database.json.default` matches `Database.json` byte-for-byte.
- **`tests/test_buff_xml.py`** — round-trips the pure XML helpers in `buff_xml.py`: attribute extraction, surgical attribute replacement (other bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the filter whitespace normaliser, and the no-`<BuffListView>` guard. Covers the regex contract since the module deliberately uses no XML parser. Imports only `kazbars.buff_xml` — no Tk required.
- **`tests/test_grids_generator.py`** — asserts `CodeGenerator(include_console=False)` produces zero `console.` / `KzGridsConsole` substrings (so MTASC won't fail to resolve a missing class) and `include_console=True` reproduces the original hooks (instantiation, log calls, preview wiring, persistence keys). Same on/off coverage for the cast-timer overlay: `cast_config=None` (and a both-sides-off config) emits zero `KzGridsCastTimer`/`castTimer`/`{{CAST_*}}`/`d.CAST` references; an enabled config emits the instantiation, configure call, lifecycle hooks, and a numeric-hex `color:` literal in `d.CAST`. Belt-and-suspenders that both default to off. Imports `BuffDatabase` from the pure `kazbars.buff_database` — no Tk required.
- **`tests/test_cast_timer.py`** — `cast_timer` config layer: default keys present and disabled, `is_enabled` true iff a side is on, unknown keys dropped / missing filled, position + font-size clamping, color/font/display sanitization, non-dict input → defaults. Pure — no Tk.
- **`tests/test_cluster_isolation.py`** — static-import guard for the Live Tracker AND Deeps clusters. Walks every `src/kazbars/*.py` via `ast.parse`. Asserts (a) no module outside a cluster (except `app.py`) imports a cluster member, (b) cluster members import only stdlib + cluster + shared infrastructure (`ui_*`, `settings_manager`, `window_position`, `paths`, `custom_menu_bar`, `overlay_engine`, `foreground`, `focus_watcher`), and (c) the two clusters never cross-import. Parametrised over both clusters.
- **`tests/test_deeps_parsers.py`** — 163 behavior-table cases ported from `Deeps/rust/aoc-damage` and `aoc-heal` test files. Covers heal-verb filter, self-damage filter, the own-pet `Your`-gate (team-mates' pets excluded), the three heal classifications, and the timestamp stripper.
- **`tests/test_deeps_parity.py`** — 9 cases comparing Python parser totals against the Rust source-of-truth output on a real ~531k-line CombatLog. Ground truth lives in `tests/fixtures/deeps_parity/expected_totals.json`, regenerated by `Deeps/rust/parity-dump/`. Four categories match Rust byte-for-byte; `pet_damage` is the documented own-pet-only exception. Skips locally when the log isn't present (`DEEPS_PARITY_LOG=<path>` overrides). The load-bearing accuracy gate.
- **`tests/test_deeps_rolling_window.py`** — 13 cases on the rolling-window primitive (record/prune/sum_since/count_since/first_event, decay during silence, exact-boundary inclusion).
- **`tests/test_deeps_trackers.py`** — 28 cases on the four trackers + Snapshot. Warm-up boundaries, decay, reset re-anchor, pet damage feeding the outgoing window, and the per-bucket warm-up rule for heals.
- **`tests/test_deeps_settings.py`** — 52 cases on defaults, per-key validation, file I/O round-trip, corrupt/partial-file fallback.
- **`tests/test_deeps_meter.py`** — 32 cases on `newest_combat_log` selection, `MeterSnapshot` shape, `_process_line` dispatch (own-pet gate + pet-toggle), lifecycle (start/stop/restart), `OLD_LOG` detection on stale files, and a Windows-only end-to-end `TAILING` check using a held-open file.
- **`tests/test_deeps_overlay.py`** — 23 cases on the pure helpers (`_format_rate`, `_format_signed_int`, `_lerp_color`) plus the five-cell IDs and labels. Visual behaviour is covered by manual `/smoke`.

Run before every commit touching code or data:
```bash
pytest tests/
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `src/kazbars/grids_panel.py` | 628 | `GridsPanel` container, toolbar, scrollable list, anchor-based `scale_to_resolution`, frozen `CastTimerStrip` pinned above the list. Per-row card lives in `grid_editor_panel.py` |
| `src/kazbars/grid_editor_panel.py` | 647 | `GridEditorPanel` (per-row collapsible card) + module-level `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps; X/Y spinbox bounds pulled from `game_resolution` setting |
| `src/kazbars/database_editor.py` | 750 | Buff DB UI (treeview, dialogs, category management). Pure data layer in `buff_database.py` |
| `src/kazbars/grid_dialogs.py` | 874 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `src/kazbars/build_loading.py` | 797 | Build-progress screen + welcome/about popups |
| `src/kazbars/buff_display_editor.py` | 563 | Default Buff Bars dialog (UI). Pure XML helpers in `buff_xml.py` |
| `src/kazbars/buff_xml.py` | 215 | AoC HUD XML helpers (regex-only). Pure — no Tk/ttkbootstrap, importable from CI without UI extra |
| `src/kazbars/buff_database.py` | 140 | `BuffDatabase` class — JSON load/save, in-memory indexes, search. Pure — no Tk |
| `src/kazbars/app.py` | 611 | Entry point + `KazBarsApp` root window (widgets, menu, lifecycle) |
| `src/kazbars/ui_widgets.py` | 867 | Widget builders, tooltips, bindings, `CollapsibleSection` (with `set_dimmed`), `ColorSwatch` (rounded swatch + themed `ColorChooserDialog`) + `create_rounded_rect`, `blend_alpha`, `flash_status_bar`, `app_toast`, `labeled_spinbox`/`labeled_combobox`, `draw_grid_cells` |
| `src/kazbars/live_tracker_panel.py` | 575 | Live Tracker Toplevel orchestrator |
| `src/kazbars/timer_overlay.py` | 542 | In-game transparent timer overlay (two-canvas docked layout, stroke rendering, click-through lock) |
| `src/kazbars/ui_components.py` | 451 | `ToastManager` (coalesce-by-key, in-place text update), `DragReorderManager`, scrollable frame |
| `src/kazbars/grids_generator.py` | 579 | AS2 code generation from grid configs (optional console hooks via `include_console`; optional cast-timer overlay hooks + `d.CAST` block via `cast_config` → `include_cast_timer`). Also holds `CUSTOM_ICON_LINKAGE` (null-icon buff IDs → baked `base.swf` symbol names), emitted into `KzGridsData.CUSTOMICON` |
| `src/kazbars/boss_timer.py` | 381 | Boss timer state + UI |
| `src/kazbars/instructions_panel.py` | 403 | Help/instructions view |
| `src/kazbars/first_launch.py` | 364 | First-launch dialog + post-dialog orchestrator (`run_first_launch`) |
| `src/kazbars/custom_menu_bar.py` | 402 | Canvas-based dark menu bar (active-cascade phosphor underline; ttkb-safe Canvas spacers; supports `command`, `separator`, `checkbutton` entries) |
| `src/kazbars/combat_monitor.py` | 294 | Combat log parser feeding the tracker |
| `src/kazbars/cast_timer_strip.py` | 278 | Frozen `CastTimerStrip` card (collapsed + off by default): per-side Enable + X/Y, shared Bold/Size/Display/Color (font fixed to Arial) for the cast-timer overlay |
| `src/kazbars/build_executor.py` | 240 | MTASC compile + deploy |
| `build.py` | 225 | PyInstaller build driver |
| `src/kazbars/profile_io.py` | 228 | Profile load (read+apply split, with auto-anchor-scale on resolution mismatch) / save (build+write+commit, `silent=` for piggyback saves) / new / open + missing-buff warning. Persists the `cast_timer` block alongside `grids` |
| `src/kazbars/game_folder.py` | 192 | Game folder UI + Aoc.exe bypass (with install/remove reconciler) + uninstall |
| `src/kazbars/game_resolution.py` | 104 | Game resolution dialog + anchor-rescale all loaded grids on apply |
| `src/kazbars/settings_backup.py` | 394 | Backup & Restore dialog + pure zip layer (`write_backup_zip`/`read_manifest`/`restore_zip`, `funcom_prefs_path`, `_funcom_summary`) — bundles `%LOCALAPPDATA%\Funcom\Conan\Prefs` + KazBars `profiles/` + the whole `settings/` dir (app + Deeps + Live Tracker) into one zip; restore snapshots first, guards zip-slip, resyncs settings. Isolated satellite, no cross-imports |
| `tests/test_buff_xml.py` | 175 | Round-trip smoke test for `buff_display_editor` XML helpers |
| `src/kazbars/build_action.py` | 170 | Build & Install flow |
| `src/kazbars/ui_helpers.py` | 193 | Design tokens + `setup_custom_styles` + `style_treeview_heading` |
| `src/kazbars/live_tracker_settings.py` | 168 | Tracker persistence (with one-shot legacy filename migration) |
| `src/kazbars/grid_model.py` | 150 | Grid dataclasses, `parse_resolution`, `get_game_resolution_or_default`, anchor-based `scale_grid_position` (X center / Y bottom anchored) |
| `tests/test_data_integrity.py` | 103 | Buff-ref resolution smoke test |
| `src/kazbars/build_utils.py` | 98 | Compiler discovery + path helpers |
| `src/kazbars/cast_timer.py` | 101 | Cast-timer overlay config (pure data): defaults, validation, `is_enabled` gate. No Tk |
| `src/kazbars/window_position.py` | 91 | Window geometry save/restore |
| `src/kazbars/settings_manager.py` | 104 | `SettingsManager` (incl. `reload()` to resync in-memory state from disk after a restore), JSON helpers, settings proxy |
| `src/kazbars/update_check.py` | 69 | Background GitHub release check + named main-thread toast dispatcher |
| `src/kazbars/ui_tk_style.py` | 57 | Raw-tk widget styling + dark titlebar |
| `tests/test_imports.py` | 33 | Import-graph smoke test |
| `tests/test_grids_generator.py` | 175 | `CodeGenerator.include_console` AND `include_cast_timer` (via `cast_config`) on/off output checks |
| `tests/test_cast_timer.py` | 80 | `cast_timer` config defaults, clamping, color/enum sanitization, `is_enabled` build gate |
| `tests/test_cluster_isolation.py` | 178 | Static-import guard for the Live Tracker AND Deeps clusters (no inbound except `app.py`; cluster imports stdlib + cluster + shared infrastructure only; no cross-import) |
| `tests/test_resolution_scaling.py` | 93 | Anchor-formula regression test (`scale_grid_position` predictions for 1080p → 1440p / 4K against `Default.json`) |
| `tests/test_settings_backup.py` | 135 | `settings_backup` pure layer — backup→restore byte-identity (incl. Deeps + Live Tracker settings), `*.tmp` exclusion, manifest accept/reject, prefs locator, zip-slip guard |
| `src/kazbars/deeps_panel.py` | 801 | `DeepsPanel` Toplevel — status row, Start/Stop, Lock + Layout, appearance (font + size/background sliders), Alarm & Tints thresholds, 5-cell visibility picker, pet toggle. Owns the meter + overlay + 100 ms UI tick + alarm hysteresis state machine |
| `src/kazbars/deeps_meter.py` | 526 | `DeepsMeter` daemon thread — tail loop, log rotation detection, AoC focus polling via `CreateToolhelp32Snapshot`, `is_live` probe via `CreateFile` exclusive-share. Publishes `MeterSnapshot` |
| `src/kazbars/deeps_overlay.py` | 527 | Five-cell numbers display (DPS out/in, HPS out/in, ΔHP in). Two layouts (horizontal/vertical), 8-direction stroke text, 2 Hz alarm pulse on DPS-out, net-HP tints, click-through lock |
| `src/kazbars/overlay_engine.py` | 540 | Shared PIL + win32 layered-window engine (`LayeredOverlay`, `load_font`, `FONT_FAMILY_CHOICES`) — per-pixel-alpha overlay used by BOTH the Deeps and Live Tracker overlays |
| `src/kazbars/deeps_parsers.py` | 408 | Pure parsers (no Tk, no threading). 5 entry points: `parse_outgoing_damage`, `parse_incoming_damage`, `parse_incoming_heal`, `parse_outgoing_heal`, `parse_pet_hit` (own-pet only). Damage/heal regexes byte-identical to `Deeps/rust/aoc-damage` + `aoc-heal` |
| `src/kazbars/deeps_trackers.py` | 221 | `DamageOutTracker`, `DamageInTracker`, `HealsInTracker` (3-bucket per-bucket warm-up), `HealsOutTracker`, `TrackerSnapshot` |
| `src/kazbars/deeps_settings.py` | 211 | `deeps_settings.json` defaults, per-key validation, load/save |
| `src/kazbars/deeps_rolling_window.py` | 81 | `RollingWindow` data structure — record/prune/sum_since/count_since/first_event |
| `src/kazbars/assets/deeps/pets.json` | 81 | Pet-name registry — lifted from `Deeps/rust/aoc-damage/data/pets.json` |
| `tests/test_deeps_parsers.py` | 544 | 163 behavior-table cases from Deeps's Rust tests + the own-pet gate |
| `tests/test_deeps_meter.py` | 355 | 32 cases — file selection, lifecycle, `_process_line` dispatch, held-open-file end-to-end |
| `tests/test_deeps_trackers.py` | 288 | 28 cases — warm-up, decay, reset, per-bucket warm-up for heals |
| `tests/test_deeps_settings.py` | 270 | 52 cases — defaults, validation, round-trip, corrupt-file fallback |
| `tests/test_deeps_parity.py` | 170 | 9 cases — Python vs Rust totals over a real CombatLog (the accuracy gate) |
| `tests/test_deeps_rolling_window.py` | 169 | 13 cases — primitive smoke + decay-during-silence |
| `tests/test_deeps_overlay.py` | 143 | 23 cases — pure helpers + 5-cell IDs/labels (visual behaviour is `/smoke`) |
| `tools/deeps_parity_dump.py` | — | Python parity harness for ad-hoc inspection of any log |
| `Deeps/rust/parity-dump/` | — | Rust source-of-truth dumper, regenerates `tests/fixtures/deeps_parity/expected_totals.json` |
