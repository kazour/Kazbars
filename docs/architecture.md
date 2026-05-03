# Architectural Map

**Current as of:** 2026-05-03 (after Live Tracker hardening pass: overlay rebuilt on a two-canvas docked layout — `text_canvas` on top with rows 1+2, fixed-height `cycle_timer_canvas` at the bottom hosting the cycle timer + chrome (lock indicator, resize handle), 1px separator frame between, so the cycle timer can no longer overlap message rows on resize; text rendered through canvas items with an 8-direction outline stroke when transparent_bg is on (legibility over arbitrary game scenes); minimum height scales with font via `_min_height()` so the layout never collapses; lock indicator switched from emoji to monochrome geometric circles (●/○) matching the resize-handle triangle (◢); cross-thread / cross-event-loop callbacks are named methods (`_dispatch_overlay_update` + `_apply_overlay_update` for the combat-monitor → main-loop hop, `_run_game_tick` for the 50ms loop, `_test_trigger_fixation` / `_test_check_reset` for the test cycle, `_block_close` / `_on_lock_click` / `_arm_click_through_on` for overlay events) instead of lambdas/closures; defaults route through `TIMERS_DEFAULTS` everywhere via `.get(key, TIMERS_DEFAULTS[key])`; `apply_settings` suspends per-setter notifications and now also applies width/height/visible (was: dropped silently); idempotent `set_locked(target)` replaces toggle-to-reach-state; click-through arms via `after_idle` instead of `after(100, ...)`; `update_display` short-circuits when state hasn't changed (~90% reduction in canvas churn at 50ms cadence); cycle timer uses `COLORS["default"]` (Tracker palette) instead of `THEME_COLORS['muted']`; new `MODULE_COLORS['live_tracker']` token used for the dialog header; settings file `timers_settings.json` → `live_tracker_settings.json` and window-pos key `window_pos_boss_timer` → `window_pos_live_tracker`, both with one-shot migrations; fixed: `positioned` flag was being stripped from saves on every launch since the rebrand because it wasn't in `TIMERS_DEFAULTS`, so the overlay re-centered every time.)
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
- `ui_helpers` holds design tokens only (fonts, colors, padding, BTN_*, INPUT_WIDTH_*, canvas-geometry constants, SCANLINE_ALPHA) + `setup_custom_styles`. Leaf — imports nothing internal.
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
- **Cluster isolation:** the Live Tracker cluster must not be imported from outside itself. Enforced by convention, not code.
- **Toasts:** every toast goes through `app_toast(widget, message, style, duration=, key=, on_click=)` in `ui_widgets`. The walker resolves `.toast` from the widget's ancestry, so callers don't need a direct `ToastManager` reference. Pass `key=` for any emitter that can fire repeatedly in a short burst (spinbox auto-repeat is the canonical case) — same key replaces the live toast in place instead of stacking. Don't reintroduce `obj.toast.show(...)` direct calls — they bypass the walker, fragment defaults, and force a `toast=` constructor seam.

## Smoke tests

Two plain-Python scripts guard the failure modes we've actually hit. No pytest.

- **`tests/test_imports.py`** — auto-discovers every `src/kazbars/*.py` + `kazbars` and imports each. Catches missing symbols, wrong-module references, and cycles. Add nothing — new modules are picked up automatically.
- **`tests/test_data_integrity.py`** — validates every buff reference in `assets/kazbars/Default.json` (whitelists + slot assignments) resolves to a `Database.json` entry, and that `Database.json.default` matches `Database.json` byte-for-byte.
- **`tests/test_buff_xml.py`** — round-trips the `buff_display_editor` XML helpers: attribute extraction, surgical attribute replacement (other bytes preserved verbatim), the KZ_OFF on/off comment-wrap toggle, the filter whitespace normaliser, and the no-`<BuffListView>` guard. Added with the editor itself; covers the regex contract since the module deliberately uses no XML parser.

Run before every commit touching code or data:
```bash
python tests/test_imports.py && python tests/test_data_integrity.py && python tests/test_buff_xml.py
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `src/kazbars/grids_panel.py` | 1242 | Grid list UI, grid management |
| `src/kazbars/database_editor.py` | 865 | Buff DB CRUD, search, filtering |
| `src/kazbars/grid_dialogs.py` | 841 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `src/kazbars/build_loading.py` | 797 | Build-progress screen + welcome/about popups |
| `src/kazbars/buff_display_editor.py` | 743 | Default Buff Bars dialog — edits HUD XML for 4 portraits via surgical regex; collapsible sections persist open state |
| `src/kazbars/app.py` | 584 | Entry point + `KazBarsApp` root window (widgets, menu, lifecycle) |
| `src/kazbars/ui_widgets.py` | 577 | Widget builders, tooltips, bindings, `CollapsibleSection` (with `set_dimmed`), `blend_alpha`, `flash_status_bar`, `app_toast` |
| `src/kazbars/live_tracker_panel.py` | 575 | Live Tracker Toplevel orchestrator |
| `src/kazbars/timer_overlay.py` | 542 | In-game transparent timer overlay (two-canvas docked layout, stroke rendering, click-through lock) |
| `src/kazbars/ui_components.py` | 451 | `ToastManager` (coalesce-by-key, in-place text update), `DragReorderManager`, scrollable frame |
| `src/kazbars/grids_generator.py` | 424 | AS2 code generation from grid configs |
| `src/kazbars/boss_timer.py` | 381 | Boss timer state + UI |
| `src/kazbars/instructions_panel.py` | 366 | Help/instructions view |
| `src/kazbars/first_launch.py` | 353 | First-launch dialog + post-dialog orchestrator (`run_first_launch`) |
| `src/kazbars/custom_menu_bar.py` | 359 | Canvas-based dark menu bar |
| `src/kazbars/combat_monitor.py` | 294 | Combat log parser feeding the tracker |
| `src/kazbars/build_executor.py` | 227 | MTASC compile + deploy |
| `build.py` | 225 | PyInstaller build driver |
| `src/kazbars/profile_io.py` | 219 | Profile load (read+apply split) / save (build+write+commit, `silent=` for piggyback saves) / new / open + missing-buff warning |
| `src/kazbars/game_folder.py` | 192 | Game folder UI + Aoc.exe bypass (with install/remove reconciler) + uninstall |
| `tests/test_buff_xml.py` | 175 | Round-trip smoke test for `buff_display_editor` XML helpers |
| `src/kazbars/build_action.py` | 168 | Build & Install flow |
| `src/kazbars/ui_helpers.py` | 169 | Design tokens + `setup_custom_styles` |
| `src/kazbars/live_tracker_settings.py` | 168 | Tracker persistence (with one-shot legacy filename migration) |
| `src/kazbars/grid_model.py` | 117 | Grid dataclasses + `parse_resolution` helper |
| `tests/test_data_integrity.py` | 103 | Buff-ref resolution smoke test |
| `src/kazbars/build_utils.py` | 98 | Compiler discovery + path helpers |
| `src/kazbars/window_position.py` | 91 | Window geometry save/restore |
| `src/kazbars/settings_manager.py` | 82 | `SettingsManager`, JSON helpers, settings proxy |
| `src/kazbars/update_check.py` | 69 | Background GitHub release check + named main-thread toast dispatcher |
| `src/kazbars/ui_tk_style.py` | 57 | Raw-tk widget styling + dark titlebar |
| `tests/test_imports.py` | 47 | Import-graph smoke test |
