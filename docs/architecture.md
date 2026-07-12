# Architectural Map

**Current as of:** 2026-07-12 (doc slimmed: retired the accumulated pass-history from this line — git history and docs/CHANGELOG.md hold it — and consolidated per-test descriptions into the File-inventory roles).
**Purpose:** Module topology, dependencies, and coupling hotspots. Updated alongside code changes — if you edit this file, commit it with the code.

## Dependency clusters

All arrows point in the "imports from" direction. Every chain terminates — **no cycles**.

### UI primitives (tokens at the root)
```
ui_helpers  ← ui_tk_style
ui_helpers  ← ui_widgets          ← ui_headers, ui_forms, ui_collapsible
                                    ← ui_components
                                    (ui_components also imports ui_tk_style)
ui_helpers  ← custom_menu_bar
```
- `ui_helpers` holds design tokens only (fonts, colors, padding, BTN_*, INPUT_WIDTH_*, canvas-geometry constants, SCANLINE_ALPHA) + `setup_custom_styles` + `style_treeview_heading` (called post-Treeview-construction because ttkbootstrap rebuilds `Treeview.Heading` lazily on first instantiation, clobbering boot-time styling). Leaf — imports nothing internal.
- `ui_widgets` is the leaf "core glue": `blend_alpha`, `add_tooltip` (+ `_InAppToolTip`), `app_toast`, `flash_status_bar`, `debounced_callback`, and the event-binding helpers (`bind_card_events`, `bind_button_press_effect`, `bind_label_hover_colors`, `bind_label_press_effect`). Imports nothing from the three siblings below — they depend on it, not the reverse, so no cycles.
- `ui_headers` builds the headers: `create_dialog_header`, `create_app_header`, `update_app_header_color`, `create_tip_bar`. Imports `blend_alpha` from `ui_widgets`.
- `ui_forms` builds the form fields + settings-panel builders: `labeled_spinbox`/`labeled_combobox`/`position_entry`, `draw_grid_cells`, `create_rounded_rect`, `ColorSwatch`, and the shared settings-panel group both config panels use — `create_card`, `create_status_block`, `create_slider_row`, `toggle_button_state`, `create_toggle_action_button`, `refresh_toggle_button`. Imports `add_tooltip` from `ui_widgets`.
- `ui_collapsible` holds `CollapsibleSection` (with `set_dimmed`). Imports `blend_alpha` from `ui_widgets`.
- `ui_components` adds stateful composites: the toast stack — pure `ToastModel` (visible cap + queue, two-tier priority, coalesce-by-key) rendered by `ToastManager` (all placement through the single `_layout()` authority) — plus `DragReorderManager`, `create_scrollable_frame`, global mousewheel routing.
- `ui_tk_style` handles raw-tk widget styling + dark-titlebar monkey-patch.
- `custom_menu_bar` is the dark-themed Canvas-based menu bar (was in `ui_components`; extracted for size + single-consumer isolation).

### App state
```
settings_manager (get/set proxy + safe_save_json)
  ← settings_core  ← deeps_settings, live_tracker_settings, damageinfo_settings
                   ← prefs (PREFS_SCHEMA)
  ← window_position
userdata (userdata/ paths + ensure_layout)  ← prefs, settings_backup, app
```
- `settings_core` is the schema-driven settings engine (`Field`/`Schema`/`Migration`/`Store` + functional `load`/`save`/`validate_all`); it imports only `settings_manager.safe_save_json` and stdlib. Every settings file declares a `Schema` and delegates validation + atomic I/O to it. It is **strict drop-unknown** — undeclared keys are erased on save — so any dynamic key namespace is one structured-dict `Field`, never N top-level keys.
- `userdata` resolves the `userdata/` storage root (created fresh on first launch by `ensure_layout()`; **no legacy migration** — old `settings/`/`profiles/` next to the exe are ignored) and its named subpaths. `assets/` stays read-only.
- `prefs` declares `PREFS_SCHEMA` (machine-local `prefs.json`, strict). `app.settings` is a `settings_core.Store` built on it; `init_settings(app.settings)` keeps the `get_setting`/`set_setting` proxy working, and `settings_manager` now holds only that proxy + `safe_save_json`. The strict guard is `tests/test_prefs_schema_covers_all_proxy_keys` — it greps every proxy key and fails if one isn't a declared Field.
- `window_position` stores all window geometry under the single `window_positions` prefs dict field (keyed by window name), reached via the `get_setting`/`set_setting` proxy — not the `_settings` global, and not N top-level `window_pos_*` keys.

**Storage layout / data lifecycle.** Three data classes by lifecycle, not by feature:
```
<install>/
  KazBars.exe
  assets/kazbars/{Database.json, Database.json.default, Default.json}  ← REFERENCE (read-only, shipped; app never writes here)
  userdata/                       ← USER + MACHINE (created fresh by ensure_layout() on first launch)
    prefs.json                    ← machine-local (window positions, game path, resolution, last/default profile, build toggles, UI state)
    settings/{deeps,live_tracker,damageinfo}_settings.json
    profiles/*.json
    database_user.json            ← user buff deltas (seeded empty; Phase 3)
    content/  content/.bak/       ← OTA reference content + rollback (Phase 4)
```
The editor and OTA updater **never write `assets/`**, so a reinstall always has a clean floor and the `Database.json` ⇄ `.default` byte-identity test holds. Backup/restore (`settings_backup`) covers an explicit `userdata/` allowlist — `profiles/`, `settings/`, `database_user.json`, and `prefs.json` — and never `content/` (regenerable OTA cache); `prefs.json` rides in the zip but is machine-local, so restore leaves it out unless the user ticks the opt-in checkbox.

### Grid editing
```
grid_model  ← grid_dialogs  ← grid_editor_panel  ← grids_panel
            (also pulls settings_manager, window_position, ui_*)
```
- `grid_editor_panel` owns the per-row collapsible card (`GridEditorPanel`) and the private `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps that drive its three comboboxes. `grids_panel` is the container (toolbar, scrollable list, profile load/save bridge).

### Buff database (three-layer merge, pure data layer)
```
settings_manager (safe_save_json)  ← buff_db_layers  ← buff_database  ← database_editor (UI)
                                                      ← app.py (DeltaStore + get_floor)
buff_xml  ← buff_display_editor   (UI; HUD-XML editor dialog)
```
- `buff_db_layers.py` is the pure three-layer merge: effective DB = stock floor (`assets/`, read-only) ← OTA `content/` override (Phase 4) ← user deltas (`userdata/database_user.json`), **user always wins**, keyed on the primary spell ID `ids[0]`. `merge_layers`/`load_effective`/`load_floor` return `(buffs, provenance)` where provenance is `stock`|`content`|`user`; `compute_delta(floor, edited)` diffs the editor's effective list back into a delta (user adds/overrides + tombstoned `ids[0]`); `DeltaStore` reads/writes `database_user.json` atomically. Imports only stdlib + `settings_manager.safe_save_json`.
- `buff_database.load_layers()` merges the three layers into `self.buffs` + `self.provenance` (corrupt stock → bundled `.default` **in memory**, never writes assets), `reload()` re-merges (Phase 4 OTA calls it), and `current_floor()` hands the editor the stock←content floor. `load(json_path)` stays for single-file/back-compat (tests).
- `database_editor` writes **only** `database_user.json` via `DeltaStore`: `save()` computes a delta vs the floor; the Source column badges each row (Built-in / Updated / Yours from provenance); Delete branches on provenance — hide-a-built-in (reversible tombstone) vs delete-your-buff. Because `assets/` is never written, the `Database.json` ⇄ `Database.json.default` byte-identity invariant gets *stronger*.
- `buff_database.py` / `buff_db_layers.py` / `buff_xml.py` import only stdlib (plus `safe_save_json` for the merge writer) — no Tk, no ttkbootstrap. Tests collect them in a minimal CI image without the UI extra (`tests/test_buff_db_layers.py`, `tests/test_buff_xml.py`, `tests/test_grids_generator.py`).

### Reference content / OTA (silent, reversible content channel)
```
content_update  ← app.py, first_launch
  → buff_db_layers (summarize), userdata (content_dir), ui_widgets (toast)
update_check    (GitHub release check — sibling shape, NOT cross-imported)
```
- `content_update.py` polls `ota/manifest.json` (raw URL on `main`) on launch; if it advertises a newer `content_version` than `prefs.json.content_version`, the app is new enough (`min_app_version`), and the auto-update toggle is on, it downloads the `Database.json` + `Default.json` payloads (URLs on the `main` ref; integrity is the sha256), verifies sha256, **atomically** swaps them into `userdata/content/` with a `.bak/` rollback (snapshot prev → `os.replace` → write the `content/manifest.json` marker LAST), re-merges the live DB (`BuffDatabase.reload()`), and shows **one** toast. Anything that fails swaps nothing; it defers if the DB editor is dirty or a build is running (and, on a fresh install, until first launch completes). Pure helpers (`parse_manifest`/`is_newer`/`app_supports`/`verify_sha256`/`apply_content`/`rollback`/`summarize_changes`) + a thin Tk dispatcher (`check_and_apply`/`revert`); mirrors `update_check`'s shape but doesn't cross-import it. **Not** on the mypy blocking gate (imports tkinter).
- **Three version markers, kept distinct:** the server `ota/manifest.json` advertises the latest; `prefs.json.content_version` (defaulting to the shipped `CONTENT_BASELINE_VERSION`) is the **authoritative comparison key**; `userdata/content/manifest.json` records what's currently applied (the step-5 commit marker). `CONTENT_BASELINE_VERSION` (`__init__.py`) is stamped == the manifest's `content_version` by `scripts/gen_manifest.py`, run **locally** in the same commit as a stock-file change (the pre-commit pytest gate blocks it otherwise), so a fresh install ships current and fires no redundant first-run update. `.github/workflows/ota-manifest.yml` only **verifies** on push-to-main touching the stock files (regenerate + fail on drift; never commits back, so branch protection can't block it). `tests/test_manifest.py` guards both (sha256 match + baseline lockstep).
- User controls (Updates menu): an **"Automatically update the buff database"** toggle (default on), **"Check for buff-database updates now"** (manual), **"Revert last buff-database update"** (`rollback()`). User deltas (`database_user.json`) are never touched by apply or rollback.

The manifest (committed at repo root `ota/manifest.json`, payload URLs on the `main` ref — integrity is the per-payload sha256):
```jsonc
{ "schema": 1, "content_version": 7, "min_app_version": "2.1.0",
  "notes": "Added 3 raid debuffs; fixed Zaal Veil ID.",
  "files": { "Database.json": { "url": "…/main/…/Database.json", "sha256": "…" },
             "Default.json":  { "url": "…/main/…/Default.json",  "sha256": "…" } } }
```

### Build pipeline
```
build_utils  ← grids_generator
             ← build_executor  ← first_launch, build_action
app_popups   ← app.py, build_action, first_launch, build_loading
build_loading  ← build_action
```

`app_popups` is the frameless dark popup family — the shared chrome (`make_popup_shell`/`draw_close_button`/`center_popup` + the `WIDTH`/`BG`/`BORDER_COLOR`/`SCANLINE_STEP` frame constants) plus `show_welcome_popup` (first-launch), `show_about_popup` (Help ▸ About), and `show_close_game_required_dialog` (build pre-check). `build_loading` keeps only `BuildLoadingScreen` and imports the chrome one-way (no cycle — `app_popups` imports nothing from the build cluster).

**AS2 class names are load-bearing.** `base.swf` bootstraps `m_Module = new KazBars(this)`, so the generated classes, the `stubs/KazBars*.as` filenames, and `KazBars_core.as.template` must keep the `KazBars*` names (`KazBars`, `KazBarsData`, `KazBarsConsole`, `KazBarsPreview`, `KazBarsSlot`, `KazBarsCastTimer`, `KazBarsStopwatch`) to bind against it. A Python-only rename silently breaks the bind — the old `KzGrids` freeze was only lifted by recompiling `base.fla` in Flash CS6 with the new bootstrap and re-exporting `base.swf`; renaming again needs the same Flash re-export. The console (`KazBarsConsole` / `include_console`), cast-timer (`KazBarsCastTimer` / `cast_config`), and stopwatch (`KazBarsStopwatch` / the `stopwatch` prefs dict) stubs compile in only when enabled — gated in `grids_generator.py` so MTASC skips the unused stub class entirely. The stopwatch is a count-up Start/Pause/Reset panel drawn entirely at runtime (device-font TextFields resolving to the Arial faces embedded in `base.swf`, no new symbols): draggable title bar with a live-coordinate readout, collapse-to-title-bar via a − / + button, position + collapsed state persisted in the module config archive (`swx`/`swy`/`swc`) on aoc.exe clients, baked X/Y defaults for `/loadclip` clients.

**Null-icon custom icons.** Some AoC buffs return `m_Icon.GetInstance()==0` (no game icon → the slot rendered blank). `grids_generator.CUSTOM_ICON_LINKAGE` maps such buff IDs → baked symbol linkage names in `base.swf` (`IcoSlow30/40/45/60` for the ice-gem slows), emitted into `KazBarsData.CUSTOMICON`. `KazBars_core.as.template`'s `loadIcon` routes through `attachBaked` to attach the symbol as a slot sibling at **dynamic depth 8**, with a shared **`IcoNull`** fallback for any other no-icon buff — so no tracked buff shows a blank slot. The slot's authored art (bg/icoMask/m_icon/frame, depths 1/3/5/9 in the FLA) becomes timeline content in the negative reserved depth range at runtime, so depth 8 sits above it; the timer/stack TextFields are pinned to fixed depths **10–13** (`KazBarsSlot`, not `getNextHighestDepth()`) so they render above the icon rather than under it. The flash (`animSlot`) pulses `s.cust` for baked icons, `m_icon` for RDB icons. The rounded crop is baked into the art (PNG inset ~56×56 in a 64×64 canvas), **not masked** at runtime: AoC's Scaleform renderer applies masks only to `loadClip` content (the RDB game icons), never to `attachMovie`'d content.

### Damage Numbers (offset-bake mod for AoC's DamageInfo.swf)
```
damageinfo_settings  ← damageinfo_generator  ← build_action (gated)
                     ← damageinfo_panel       ← app.py (Extras menu)
```
An Extras-menu config popup (`damageinfo_panel.py`) tunes AoC's floating combat-number
overlay. Each setting is an **offset from the stock game value** (default 0 ⇒
unchanged); `damageinfo_settings.GLOBAL_SETTINGS` is the bake-map (UI ranges + target
file + regex pattern) and `GAME_DEFAULTS` the baseline. On Build & Install,
`damageinfo_generator.build_damageinfo` copies the lean AS2 tree under
`assets/damageinfo/src/__Packages`, regex-rewrites each named constant to
`default + offset`, and MTASC-injects the result into a copy of the pristine
`assets/damageinfo/DamageInfo.swf` (two entry points — `MainDamageNumbers` +
`FixOnLoad`, the latter force-compiled so the container's `onLoad` survives the
inject). The AS2 is a from-scratch lean rewrite of the stock overlay: a single
`onEnterFrame` IN/LIVE/OUT loop (no TweenLite / `setInterval`), an O(1) column
hashmap, object pools, and a 3-way `SHADOW_MODE` (None / Fast offset-twin / Real
DropShadowFilter). Gated by a master `enabled` flag (off by default); when off the
build leaves the stock file alone and reverts any prior mod via the one-time
`DamageInfo.swf.kazbars.bak`. Three features reach a *second* game file — the skin's
`TextColors.xml`, always written to **Customized/** (created from the stock Default/ copy
when absent — the game patcher resets Default/ on update, so edits there don't stick): the
"Group my resource numbers" toggle (resource-loss flytext directions → fixed column, the
SWF's `OTHER_RESOURCE_LOSS_TO_TARGET` keeping enemy drains overhead), the "Separate resources
into Column B" toggle (the incoming/self damage+heal directions → fixed column, so plain
damage stacks in column A and the signed numbers (heals, mana, stamina) in column B), and the
per-source **color editor** (`damageinfo_colors_panel.py` → each type's `color="0x…"`). All
three are **surgical, byte-preserving** regex edits that touch only their own attributes, so
they compose without stepping on each other: the two direction toggles ride Build & Install
(`build_executor._prepare_textcolors`, gated on the master enable — on flips to −1, off/disable
flips back to 1, uninstall flips back too), while the color editor writes directly on its own
Apply (`apply_colors`, no build, no gate — like the Default Buff Bars editor). A pre-existing
skin file gets a one-time `TextColors.xml.kazbars.bak`; colors and directions each survive the
other's writes. The regex↔constant coupling is guarded by `tests/test_damageinfo_generator.py`
(no MTASC). Isolated — `damageinfo_*` import only stdlib + `build_utils`/`paths` (generator)
and shared UI builders (panel); no cross-import with the Deeps/Live Tracker clusters.

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
src/kazbars/app.py  → profile_io, profile_manager, game_folder, game_resolution, build_action, buff_display_editor, first_launch, custom_menu_bar, update_check, content_update, settings_backup, stopwatch_panel
profile_manager  → profile_share (pure KZBARS1 codec), profile_io, buff_db_layers
```
These modules are consumed only by `src/kazbars/app.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KazBarsApp` instance) as first arg. That wide seam is a *checked* contract: `tests/test_app_contract.py` AST-scans every `app.<attr>` access in app-taking functions and asserts each attribute is defined on `KazBarsApp` (Tk surface + `self.X` assigns), so a rename in app.py fails CI instead of breaking a satellite at runtime. New cross-module state goes in `KazBarsApp.__init__`'s `# State` block — a satellite must not invent app attributes by assignment. `KazBarsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `profile_io`, `app_popups`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup). `update_check` is the only satellite called directly (no delegator on `KazBarsApp`) since it has a single fire-and-forget caller in `__init__`; its worker thread schedules a named main-thread dispatcher (`_show_update_toast`) guarded by `winfo_exists()`. `app_popups` also imports its pure `fetch_latest` for the About popup's manual update check.

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 25 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 22 | `ui_widgets` | Core glue (`app_toast`/`add_tooltip`/`blend_alpha` + event bindings). Still the widest UI surface even after the builders split out — most panels pull at least a toast/tooltip/binding. Keep new helpers focused. |
| 10 | `ui_headers` | Dialog/app headers + tip bar — pulled by every dialog/panel that draws a CRT header. |
|  6 | `ui_forms` | Form fields + shared settings-panel builders (card/status-block/slider-row/toggle). The Deeps + Live Tracker config panels are its heaviest consumers. |
|  5 | `ui_collapsible`, `window_position`, `settings_manager` | Small stable APIs. `ui_collapsible` is just `CollapsibleSection`. |
|  4 | `ui_tk_style`, `ui_components`, `overlay_engine`, `app_popups` | Narrow surface — ripple is contained. `overlay_engine` feeds both overlays + both settings adapters; `app_popups` feeds `app.py`, `build_action`, `first_launch`, `build_loading` (popup chrome + the three popups). |
|  3 | `grid_model`, `build_utils`, `build_executor`, `live_tracker_settings`, `paths`, `stopwatch` | Cluster leaves. `paths` is imported directly by `app.py`, `build_utils`, `deeps_parsers` (everyone else gets paths via the `app` object). `stopwatch` is the pure config layer ← `grids_generator`, `prefs`, `stopwatch_panel`. |
|  2 | `grids_generator`, `update_check` | `update_check`: `app.py` (launch check) + `app_popups` (About ▸ Check for updates via `fetch_latest`). |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_io`, `game_folder`, `game_resolution`, `build_action`, `build_loading`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor`, `settings_backup`, `stopwatch_panel`, `foreground`, `focus_watcher` | Each consumed by exactly one parent — low blast radius by design. (`foreground` ← `focus_watcher`; `focus_watcher` ← `app.py`; `build_loading` ← `build_action`.) |

## Conventions

- **Import style:** relative (`from .other import X`) inside `src/kazbars/`; absolute (`from kazbars.X import`) only from `src/kazbars/app.py` (top-level entry).
- **Where new code goes:**
  - Design token → `ui_helpers` (enforced: `tests/test_design_tokens.py` rejects `#hex` literals anywhere else — pure black/white `blend_alpha` anchors excepted)
  - Core glue: tooltip / toast / `blend_alpha` / event-binding helper → `ui_widgets`
  - Dialog/app header or tip bar → `ui_headers`
  - Form field / canvas-geometry helper / shared settings-panel builder (card, status block, slider row, toggle button) → `ui_forms`
  - Collapsible section → `ui_collapsible`
  - Frameless dark popup (welcome/About-style, CRT chrome) → `app_popups`
  - Stateful widget class or window-scope helper → `ui_components`
  - Raw-tk (Listbox/Text/Canvas) styling → `ui_tk_style`
  - Window geometry → `window_position`
  - Settings read/write → declare a `Schema` of `Field`s and route load/save/validate through `settings_core` (atomic, strict, migration-ready); the `settings_manager` `get_setting`/`set_setting` proxy stays for app-global prefs until Phase 2. Don't re-introduce UI-layer state or hand-roll JSON I/O.
  - Root-window logic (new menu action, new app-state flow) → extract to a new `src/kazbars/<concern>.py` taking `app` as first arg, add a one-line delegator on `KazBarsApp` if it has internal callers. Don't grow `src/kazbars/app.py`.
- **Cluster isolation:** the Live Tracker cluster AND the Deeps cluster each must not be imported from outside themselves (except `app.py`), and their members must not import other panels (cluster + shared infrastructure only). The two clusters also must not cross-import each other. Shared infrastructure now includes `settings_core` (both clusters' settings modules delegate to the engine), `overlay_engine`, `foreground`, and `focus_watcher` (both clusters reach the overlay + focus layer through these, never through each other). Enforced by `tests/test_cluster_isolation.py` (parametrised over both).
- **Toasts:** every toast goes through `app_toast(widget, message, style, duration=, key=, on_click=)` in `ui_widgets`. The walker resolves `.toast` from the widget's ancestry, so callers don't need a direct `ToastManager` reference. Omit `duration` for the per-severity default (`ToastModel.DEFAULT_DURATIONS`: info/success 4 s, warning 6 s, danger/error 8 s); pass seconds only when the message earns a longer read. At most 3 toasts show at once — extras queue FIFO, with warning/danger jumping queued info/success (a visible toast is never displaced). Hover pauses the dismiss timer; click runs `on_click` (if set) then dismisses. Pass `key=` for any emitter that can fire repeatedly in a short burst (spinbox auto-repeat is the canonical case) — same key replaces the live toast in place instead of stacking. Don't reintroduce `obj.toast.show(...)` direct calls — they bypass the walker, fragment defaults, and force a `toast=` constructor seam.
- **Type-check gate (mypy):** the gate is the **Tk-free logic core** — the modules that import neither `tkinter` nor `ttkbootstrap` — listed explicitly in `[tool.mypy] files` in `pyproject.toml`. Bare `mypy` (CI's *blocking* step) checks exactly that set, which must stay clean; a regression there fails CI. The full repo (`mypy src/kazbars`) runs **advisory-only** (`continue-on-error: true`) because ttkbootstrap's runtime `bootstyle` kwargs + dynamic widget typing emit ~80 errors mypy can't resolve. When you add a module that imports neither Tk lib, add it to the `files` list to fold it into the gate; a Tk-touching module stays out (advisory-only) by design. The gate is includes-based on purpose, and `tests/test_mypy_gate.py` keeps the list in lockstep with reality: a new Tk-free module that isn't listed (or a gated module that grows a Tk import) fails pytest, so the list can't silently drift.

## Smoke tests

Plain-Python pytest cases guard the failure modes we’ve actually hit. Per-test detail lives in the **File inventory** below — one description per test file; don’t duplicate it here. Two conventions worth knowing up front: `tests/test_imports.py` auto-discovers every `src/kazbars/*.py` module (add nothing when a new module lands), and `tests/test_docs_in_sync.py` guards this doc, `docs/flows.md`, and the CHANGELOG's release sections (inventory completeness, line-count tolerance, function-anchored refs, tag↔section parity).

Run before every commit touching code or data:
```bash
pytest tests/
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

## File inventory (current)

| File | Lines | Role |
|---|---:|---|
| `src/kazbars/grids_panel.py` | 628 | `GridsPanel` container, toolbar, scrollable list, anchor-based `scale_to_resolution`, frozen `CastTimerStrip` pinned above the list. Per-row card lives in `grid_editor_panel.py` |
| `src/kazbars/grid_editor_panel.py` | 619 | `GridEditorPanel` (per-row collapsible card) + module-level `_FILL_*`/`_LAYOUT_*`/`_SORT_*` option maps; X/Y bounds pulled from `game_resolution` setting; X/Y fields built via shared `ui_forms.position_entry` |
| `src/kazbars/database_editor.py` | 807 | Buff DB UI (treeview, dialogs, category management). Edits write user deltas to `userdata/database_user.json` via `DeltaStore` (never `assets/`); `save()` diffs the effective list against the floor (`get_floor`); a Source column badges provenance (Built-in/Updated/Yours); Delete hides built-ins (tombstone) or deletes user buffs. Pure data layer in `buff_database.py`/`buff_db_layers.py` |
| `src/kazbars/grid_dialogs.py` | 874 | Add/Edit/Duplicate/BuffSelector/SlotAssignment dialogs |
| `src/kazbars/build_loading.py` | 495 | `BuildLoadingScreen` — frameless build progress (animated ring, step dots) → results-summary phases. Imports the popup chrome + frame constants from `app_popups` (incl. `keep_modal_restorable`) |
| `src/kazbars/app_popups.py` | 489 | Frameless dark popup family: shared chrome (`make_popup_shell`/`draw_close_button`/`center_popup`/`keep_modal_restorable` (Win+D-survivable modals) + `WIDTH`/`BG`/`BORDER_COLOR`/`SCANLINE_STEP`), `show_welcome_popup`, `show_about_popup` (Discord/GitHub links + animated mini-grid), `show_close_game_required_dialog` |
| `src/kazbars/buff_display_editor.py` | 575 | Default Buff Bars dialog (UI). Pure XML helpers in `buff_xml.py` |
| `src/kazbars/buff_xml.py` | 313 | AoC HUD XML helpers (regex-only): `<BuffListView>` reads/writes + `set_directions` (flip flytext directions for a group; `RESOURCE_LOSS_TYPES` and `INCOMING_DAMAGE_TYPES`) + `read_source_color`/`set_source_color` (per-source flytext `color="0x…"`, for the Damage Numbers color editor). Pure — no Tk/ttkbootstrap, importable from CI without UI extra |
| `src/kazbars/buff_database.py` | 171 | `BuffDatabase` class — in-memory indexes + search, plus `load_layers()` (three-layer merge → `self.buffs` + `self.provenance`, corrupt-stock fallback to bundled `.default` in memory), `reload()`, and `current_floor()`. `load(json_path)` kept for single-file/back-compat. Pure — no Tk |
| `src/kazbars/buff_db_layers.py` | 252 | Pure three-layer buff merge: `merge_layers`/`load_effective`/`load_floor` (stock ← content ← user deltas, user wins, keyed on `ids[0]`, with `provenance`), `compute_delta` (effective → adds/overrides + tombstones), `is_valid_buff`/`_keep_valid` malformed-entry gate, `DeltaStore` (atomic `database_user.json` I/O; saves preserve entries the load filter rejected). Imports only stdlib + `safe_save_json` |
| `src/kazbars/app.py` | 701 | Entry point + `KazBarsApp` root window (widgets, menu, lifecycle); `__init__` calls `ensure_layout()`, points `profiles_path`/`settings_path` at `userdata/`, builds `self.settings = Store(PREFS_SCHEMA, userdata_root())`, loads the buff DB via `database.load_layers(stock, content, user)` (DB editor wired with a `DeltaStore` + `get_floor`), and kicks the OTA check (`content_update.check_and_apply`, deferred to first-launch completion on a fresh install); Game menu carries the auto-update toggle + check-now/revert + the In-game stopwatch dialog; File menu carries "Manage profiles…" |
| `src/kazbars/__main__.py` | 43 | Process entry point — logging setup + `KazBarsApp().mainloop()`; invoked by `python -m kazbars` |
| `src/kazbars/__init__.py` | 11 | Package version + `APP_NAME` + `CONTENT_BASELINE_VERSION` (the shipped OTA content version, stamped by `gen_manifest`); `__version__` is the hatchling dynamic-version source |
| `src/kazbars/ui_widgets.py` | 283 | Leaf "core glue": `blend_alpha`, `add_tooltip` (+ `_InAppToolTip`), `app_toast`, `flash_status_bar`, `debounced_callback`, and the event-binding helpers (`bind_card_events`/`bind_button_press_effect`/`bind_label_hover_colors`/`bind_label_press_effect`). Imports nothing from `ui_headers`/`ui_forms`/`ui_collapsible` — they depend on it |
| `src/kazbars/ui_headers.py` | 197 | Dialog/app headers: `create_dialog_header`, `create_app_header`, `update_app_header_color`, `create_tip_bar`. Imports `blend_alpha` from `ui_widgets` |
| `src/kazbars/ui_forms.py` | 437 | Form fields + shared settings-panel builders: `labeled_spinbox`/`labeled_combobox`/`position_entry`, `draw_grid_cells`, `create_rounded_rect`, `ColorSwatch` (rounded swatch + themed `ColorChooserDialog`), and the group both config panels share — `create_card`, `create_status_block`, `create_slider_row` (optional `value_width` for the readout label, `notch` for a centered default tick on symmetric sliders, `label_width` to align descriptor columns, and `label_sink` so a master gate can grey the row's descriptor + value labels alongside its control), `toggle_button_state`, `create_toggle_action_button`, `refresh_toggle_button`. Imports `add_tooltip` from `ui_widgets` |
| `src/kazbars/ui_collapsible.py` | 232 | `CollapsibleSection` (with `set_dimmed`). Imports `blend_alpha` from `ui_widgets` |
| `src/kazbars/live_tracker_panel.py` | 520 | Live Tracker Toplevel orchestrator |
| `src/kazbars/timer_overlay.py` | 379 | In-game transparent Live Tracker overlay — a `HudOverlay` consumer (`_render_content`: two text rows + cycle-timer dock with 8-direction stroke; `_measure`: font-derived auto-size, no resize handle) |
| `src/kazbars/ui_components.py` | 587 | Toast stack — pure `ToastModel` (cap 3 + queue, two-tier priority, coalesce-by-key) + `ToastManager` Tk renderer (single `_layout()` authority, hover-pause, click-dismiss) — plus `DragReorderManager`, scrollable frame |
| `src/kazbars/grids_generator.py` | 633 | AS2 code generation from grid configs (optional console hooks via `include_console`; optional cast-timer overlay hooks + `d.CAST` block via `cast_config` → `include_cast_timer`; optional stopwatch hooks + `d.SW` block via `stopwatch_config` → `include_stopwatch`). Also holds `CUSTOM_ICON_LINKAGE` (null-icon buff IDs → baked `base.swf` symbol names), emitted into `KazBarsData.CUSTOMICON` |
| `src/kazbars/boss_timer.py` | 399 | Boss timer state + UI |
| `src/kazbars/instructions_panel.py` | 759 | Help/instructions view — two-pane knowledge base: categorized nav + live search over a `SECTIONS` data model, content rendered per selection |
| `src/kazbars/first_launch.py` | 368 | First-launch dialog + post-dialog orchestrator (`run_first_launch`); fires the deferred OTA content check on completion |
| `src/kazbars/custom_menu_bar.py` | 430 | Canvas-based dark menu bar (active-cascade phosphor underline; ttkb-safe Canvas spacers; supports `command`, `separator`, `checkbutton` entries; keyboard access via F10 + arrows/Return/Escape — root key bindings installed once and gated, never unbound) |
| `src/kazbars/combat_monitor.py` | 292 | Combat log parser feeding the tracker |
| `src/kazbars/cast_timer_strip.py` | 344 | Frozen `CastTimerStrip` card (collapsed + master-off by default) for the cast-timer overlay. Header: one master Enabled toggle + title-adjacent Player/Target status tags + muted `overlay`. Body: a single settings row (independent Player/Target X/Y + Bold/Size/Display/Color, font fixed to Arial) + right-side sample preview. Master enables both sides together (`enableP == enableT == enabled`); X/Y grey out when off. Chrome mirrors a grid card — reserved handle gutter, shared `position_entry`, rose card border |
| `src/kazbars/build_executor.py` | 389 | MTASC compile + deploy; Damage Numbers backup/restore (bundled pristine as the stock source of truth, install via stage-to-temp then back-to-back `os.replace` commit) + `_prepare_textcolors` (surgical, invertible direction flips in the skin's Customized/TextColors.xml — resource-loss + incoming/self, on→−1 / off→1, created from Default/ when absent; colors are never touched here; uninstall flips directions back and leaves colors + `.bak`) |
| `src/kazbars/profile_io.py` | 270 | Profile load (read+apply split, with auto-anchor-scale on resolution mismatch) / save (build+write+commit, `silent=` for piggyback saves) / new / open + missing-buff warning. Persists `cast_timer` + the integer `profile_schema` (migration ladder, empty now) alongside `grids`. `resolve_default_profile_path` (user `default_profile` → OTA `content/Default.json` → stock); both shipped defaults force Save As; `set_default_profile` writes the prefs pointer |
| `src/kazbars/profile_share.py` | 115 | Pure `KZBARS1:` codec — `encode_profile`/`decode_profile` (gzip+base64), `collect_referenced_user_buffs` (the user-provenance buffs a profile references, across int-ID + name forms) + `merge_imported_buffs` (skip-on-collision into `database_user.json`), so an export is self-contained. Imports stdlib + `buff_db_layers` only |
| `src/kazbars/profile_manager.py` | 290 | Profile Manager dialog (Tk) — list / load / rename / duplicate / delete / set-default over `userdata/profiles/`, plus `KZBARS1:` export-to-clipboard + import (one confirmation → write + `merge_imported_buffs` → re-merge DB → one toast). Pure codec in `profile_share` |
| `src/kazbars/game_folder.py` | 176 | Game folder UI + Aoc.exe bypass (with install/remove reconciler) + uninstall |
| `src/kazbars/game_resolution.py` | 104 | Game resolution dialog + anchor-rescale all loaded grids on apply |
| `src/kazbars/settings_backup.py` | 464 | Backup & Restore dialog + pure zip layer (`write_backup_zip`/`read_manifest`/`restore_zip`, `funcom_prefs_path`, `_funcom_summary`) — bundles `%LOCALAPPDATA%\Funcom\Conan\Prefs` + the `userdata/` allowlist (`profiles/`, `settings/`, `database_user.json`, `prefs.json`) into one zip; the OTA `content/` cache is never a parameter so it can't leak. Restore snapshots first (outside `userdata/`), guards zip-slip, resyncs prefs; machine-local `prefs.json` is restored only when the dialog checkbox opts in. Isolated satellite, no cross-imports |
| `tests/test_buff_xml.py` | 274 | Round-trip smoke test for the `buff_xml` helpers: `<BuffListView>` attrs + TextColors `set_directions`/`set_resource_loss_to_column` flips + `read_source_color`/`set_source_color` (0x form, idempotent, missing-element, direction-preserving) |
| `src/kazbars/build_action.py` | 293 | Build & Install flow (compile + install on a worker thread) |
| `src/kazbars/ui_helpers.py` | 203 | Design tokens + `setup_custom_styles` + `style_treeview_heading` |
| `src/kazbars/live_tracker_settings.py` | 183 | Tracker persistence — `TIMERS_DEFAULTS`/`TIMERS_RANGES` re-expressed as a `settings_core.Schema`; validation + atomic I/O delegate to the engine. (The pre-rebrand `timers_settings.json` filename + `transparent_bg`/`opacity` key migrations were dropped — clean start, no legacy installs.) |
| `src/kazbars/grid_model.py` | 187 | Grid dataclasses, `parse_resolution`, `get_game_resolution_or_default`, anchor-based `scale_grid_position` (X center / Y bottom anchored), `dedupe_grid_ids` load-time rename of duplicate grid names |
| `tests/test_data_integrity.py` | 97 | Buff-ref resolution smoke test (assets stock pair byte-identity + `Default.json` whitelist resolution — strengthened now the app never writes assets) |
| `tests/test_buff_db_layers.py` | 264 | Three-layer merge unit gate — precedence (stock←content←user) + provenance, tombstones (incl. user re-add beating its own tombstone), missing/corrupt-layer fallbacks, `load_effective`/`load_floor`, `compute_delta` (add/override/tombstone/cosmetic-no-op/primary-ID-change), `DeltaStore` round-trip |
| `tests/test_content_update.py` | 254 | OTA channel (no network) — manifest parse/reject, `is_newer` + `min_app_version` gate, `verify_sha256`, `apply_content`/`rollback` (first-update clears, revert-to-previous, mid-swap self-heal, user deltas untouched), `summarize_changes`, and the dispatcher via `_worker` with a fake synchronous app + injected downloader (apply→re-merge→persist, not-newer skip, sha-mismatch abort, toggle-off + edit/build apply-guard defers) |
| `tests/test_manifest.py` | 54 | OTA drift guard — `ota/manifest.json` well-formed, its per-payload sha256 matches the committed stock files, and `CONTENT_BASELINE_VERSION` == the manifest's `content_version` (stamped together by `gen_manifest`) |
| `tests/test_profile_share.py` | 121 | `KZBARS1` codec — encode/decode round-trip, corrupt/truncated rejection, `collect_referenced_user_buffs` (exactly user-provenance refs across int-ID + name forms, de-duped), self-contained round-trip into an empty DB, skip-on-collision import merge |
| `tests/test_profile_io.py` | 64 | `profile_io` pure pieces — `PROFILE_SCHEMA_VERSION` + the (empty) `_migrate_profile` ladder, and `resolve_default_profile_path` precedence (user `default_profile` → OTA `content/Default.json` → stock, ignoring a missing user default) |
| `src/kazbars/build_utils.py` | 98 | Compiler discovery + path helpers |
| `src/kazbars/cast_timer.py` | 89 | Cast-timer overlay config (pure data): a `settings_core.Schema` of defaults/validators, `validate_config`/`get_default_config` over `validate_all`, `is_enabled` gate. No Tk |
| `src/kazbars/stopwatch.py` | 47 | In-game stopwatch config (pure data): a `settings_core.Schema` validated via `validate_all`; its `enabled` flag is the `include_stopwatch` build gate. No Tk |
| `src/kazbars/stopwatch_panel.py` | 132 | In-Game Stopwatch dialog (Extras ▸ In-game stopwatch…) — build-gate toggle, baked default X/Y, start-collapsed; single-instance via `app.stopwatch_dialog`; persists the `stopwatch` prefs dict |
| `src/kazbars/damageinfo_settings.py` | 432 | Damage Numbers config (pure data; validation + atomic I/O delegate to `settings_core` — `GLOBAL_SETTINGS` doubles as the Schema's source): `GLOBAL_SETTINGS` bake-map (symmetric offset ranges + `invert`/`relative` UI flags for the position sliders + target file + regex), `GAME_DEFAULTS`, `PRESETS` (Default/Performance — carry the animation timing), `SPREAD_SPACING_OPTIONS` (one radio → both zig-zag offsets) + `spread_spacing_option`, the per-source color catalog (`PAIRED_GROUPS`/`SHARED_SOURCES`/`ALL_SOURCE_NAMES`) + `normalize_color` (the color editor's UI catalog — colors themselves are NOT settings), validate/`compute_final_value`/`readout`/`apply_preset`, `is_offset_key`, load/save. No Tk |
| `src/kazbars/damageinfo_generator.py` | 134 | Bakes setting offsets into the lean AS2 tree and MTASC-injects the pristine `DamageInfo.swf` (`build_damageinfo` via `build_utils.compile_as2`). No Tk |
| `src/kazbars/damageinfo_panel.py` | 410 | `DamageNumbersPanel` Toplevel (Extras ▸ Damage number mod…) — master enable gate, presets, then cards Behavior (all toggles, off by default) / Shadow / Direction 1 (Rising) / Direction -1 (Dropping) / Direction 0 (Zig-zag); offset sliders (centre-notched; vertical ones reversed) + the coupled `Spread-spacing` radio in a scrollable body, with the Column B rows hidden until the split toggle is on; persists to `damageinfo_settings.json`. No number/label size slider (AoC's own Options slider covers it). The per-source color editor is its own Extras-menu entry (Damage number colors…), not a child of this panel |
| `src/kazbars/damageinfo_colors_panel.py` | 239 | `DamageNumberColorsPanel` — modal Apply/Cancel color editor (Extras ▸ Damage number colors…, mirrors the Default Buff Bars dialog): all 35 sources in a 2-column self/other card layout + a shared resources/misc card, each row a `ui_forms.ColorSwatch` + reset; seeds swatches from the skin's live TextColors.xml, "reset" reads the stock color from Default/. Apply writes colors directly via the module's pure `apply_colors` (surgical `color="0x…"` edits → Customized/, created from Default/; one-time `.bak`; no build, no master-enable gate). Opener validates the game folder |
| `src/kazbars/window_position.py` | 116 | Window geometry save/restore — all windows keyed under the single `window_positions` prefs dict field (`save_window_position`/`restore_window_position`/`bind_window_position_save`; `clamp_to_screen` is multi-monitor aware) |
| `src/kazbars/settings_core.py` | 251 | Schema-driven settings engine (pure, no Tk): `Field`/`Schema`/`Migration` + a stateful `Store` + the functional `coerce`/`validate_all`/`get_defaults`/`load`/`save`. One load/migrate/validate/fill/atomic-save path behind every settings file. **Strict drop-unknown** — every persisted key must be a declared `Field` or it's erased on save, so dynamic key namespaces are declared as one structured-dict `Field` with a custom `validate=`. Migration ladder ships empty (clean start), machinery live for the first post-publish bump. Backs `deeps_settings`/`live_tracker_settings`/`damageinfo_settings` (and `prefs.json` in Phase 2). Imports only stdlib + `settings_manager.safe_save_json` |
| `src/kazbars/settings_manager.py` | 51 | The `get_setting`/`set_setting` module proxy + `safe_save_json` (atomic temp+rename — what `settings_core` and `profile_io` build on). `SettingsManager` is retired; `init_settings` now receives a `settings_core.Store` |
| `src/kazbars/userdata.py` | 86 | `userdata/` storage root: path resolution (`userdata_root`/`prefs_path`/`settings_dir`/`profiles_dir`/`database_user_path`/`content_dir`/`content_backup_dir`) + `ensure_layout()` — creates the tree and seeds an empty `database_user.json` + `content/` dirs on first launch. Idempotent; the whole startup-data step (no archive, no migrate). Pure, no Tk |
| `src/kazbars/prefs.py` | 100 | Machine-local prefs: `PREFS_SCHEMA` (strict `settings_core.Schema` for `prefs.json`, with the structured `window_positions` + `buff_display_section_open` + `stopwatch` dict fields, plus the OTA `content_version`/`auto_update_content`). `app.settings` is a `settings_core.Store` on this schema; the `get_setting`/`set_setting` proxy + ~20 `app.settings` call sites use its `get`/`set`/`save()`/`reload()`/`data` surface directly. Pure, no Tk |
| `src/kazbars/update_check.py` | 69 | Background GitHub release check + named main-thread toast dispatcher |
| `src/kazbars/content_update.py` | 352 | OTA reference-content channel: pure helpers (`parse_manifest`/`is_newer`/`app_supports`/`verify_sha256`/`apply_content`/`rollback`/`summarize_changes`) + a Tk dispatcher (`check_and_apply`/`revert`). Polls `ota/manifest.json`, SHA-verifies, atomically swaps `userdata/content/` with `.bak/` rollback, re-merges live, one toast; defers on edit/build/first-launch. NOT on the mypy gate (imports tkinter) |
| `src/kazbars/ui_tk_style.py` | 67 | Raw-tk widget styling + dark titlebar |
| `src/kazbars/foreground.py` | 111 | Pure ctypes foreground probe (`app_or_game_foreground`) — no Tk/PIL. Shared by both clusters + the `ForegroundWatcher`; defaults to "show" on any probe failure |
| `src/kazbars/focus_watcher.py` | 85 | `ForegroundWatcher` — one app-owned ~250 ms tick that probes foreground once and fans `set_focus_suppressed` out to every registered overlay. Replaced the per-cluster focus polls |
| `src/kazbars/paths.py` | 47 | Path constants: `PACKAGE_ROOT`/`ASSETS`/`KAZBARS_ASSETS` (bundled read-only assets, dev + frozen) + `app_path()` (user-writable runtime root next to the .exe) |
| `tests/test_imports.py` | 33 | Import-graph smoke test |
| `tests/test_docs_in_sync.py` | 257 | architecture.md inventory guard (no phantom rows, every `*.py` listed, line counts within `max(40, 25%)` tolerance) + flows.md ref guard (no `file:line` refs, referenced files exist, step subject callables resolve in the referenced file's AST) + CHANGELOG release guard (every `v*` tag has a `## [X.Y.Z]` section; CI checks out full history, so it bites there and in pre-commit) |
| `tests/test_mypy_gate.py` | 74 | mypy-gate loop closer — the Tk-free module set (AST-derived) must equal `[tool.mypy] files` in both directions, no phantom entries |
| `tests/test_app_contract.py` | 104 | satellite ⇄ `KazBarsApp` attribute contract — every `app.<attr>` access in app-taking functions must be defined on `KazBarsApp` (Tk `dir()` + `self.X` assigns), with a floor canary against vacuous passes; `getattr(app, …, default)` + `self.app.X` chains deliberately out of scope |
| `tests/test_design_tokens.py` | 91 | design-token guard — no `#hex` literal outside `ui_helpers.py` (pure black/white blend anchors allowed; Live Tracker overlay palette allowlisted per-literal; stale-allowlist + detector canaries) |
| `tests/test_panels_construct.py` | 168 | Panel-construction smoke — boots a real `KazBarsApp` (tmp userdata, network no-opped, prefs pre-seeded) and opens all 8 satellite panels via their app-side openers, closing each via `WM_DELETE_WINDOW`; AST canary self-enrolls new `_open_*`/`_show_*` openers (or an explicit DEFERRED entry). Windows-gated |
| `tests/test_grids_generator.py` | 256 | `CodeGenerator.include_console`, `include_cast_timer` (via `cast_config`), AND `include_stopwatch` (via `stopwatch_config`) on/off output checks |
| `tests/test_cast_timer.py` | 97 | `cast_timer` config defaults, clamping, color/enum sanitization, `is_enabled` build gate |
| `tests/test_stopwatch.py` | 52 | `stopwatch` config defaults, X/Y clamping, bad-value fallback, sanitized shape |
| `tests/test_cluster_isolation.py` | 180 | Static-import guard for the Live Tracker AND Deeps clusters (no inbound except `app.py`; cluster imports stdlib + cluster + shared infrastructure only; no cross-import) |
| `tests/test_resolution_scaling.py` | 93 | Anchor-formula regression test (`scale_grid_position` predictions for 1080p → 1440p / 4K against `Default.json`) |
| `tests/test_grid_model.py` | 62 | `validate_grid` load-time sanitation — junk values fall back to defaults (no raise), numeric-string coercion, out-of-range clamps; `dedupe_grid_ids` duplicate-name renames |
| `tests/test_settings_backup.py` | 159 | `settings_backup` pure layer — backup→restore over the `userdata/` allowlist (profiles/settings/`database_user.json`/`prefs.json`), `content/` never archived, `prefs.json` restored only when opted in, `*.tmp` exclusion, manifest accept/reject, prefs locator, zip-slip guard |
| `tests/test_settings_core.py` | 297 | `settings_core` engine unit gate — Field coercion (bool/int/float/choices/custom-validate/passthrough), strict drop-unknown + fill-missing, `get_defaults` freshness, migration ladder (ordering + idempotent fixpoint + empty no-op), atomic I/O (missing/corrupt → defaults, round-trip, no leftover `.tmp`, `schema_version` stamp, structured-dict round-trip), and the `Store` facade |
| `tests/test_userdata.py` | 68 | `userdata` layout — `ensure_layout()` creates the tree + seeds an empty `database_user.json`, is idempotent (never reseeds existing data), and every named subpath resolves under `userdata/` (`app_path` monkeypatched to tmp) |
| `tests/test_prefs_schema_covers_all_proxy_keys.py` | 83 | Strict-schema safety net — greps every `get_setting`/`set_setting`/`app.settings`/`self.settings`(app.py) proxy key in the tree (resolving `UPPER_CASE` constants) and asserts each is a declared `PREFS_SCHEMA` Field, so strict validation can't silently erase a real setting |
| `tests/test_overlay_config.py` | 102 | `OverlayConfig` dataclass + per-cluster adapters (Deeps `overlay_*` keys / Live Tracker bare keys) round-trip |
| `tests/test_focus_watcher.py` | 96 | `ForegroundWatcher` tick + fan-out suppression with an injected probe (no display needed) |
| `tests/test_foreground.py` | 95 | `app_or_game_foreground` probe — own-process gate, AoC match, show-on-probe-failure default |
| `tests/test_timer_sizing.py` | 41 | Live Tracker overlay font-derived auto-size (`_measure`) bounds |
| `tests/test_toast_model.py` | 131 | Pure `ToastModel` core — duration defaults, coalesce (live/queued/exiting), cap + FIFO promotion, two-tier priority, non-overlapping slot offsets |
| `tests/test_toggle_button_state.py` | 41 | Pure `toggle_button_state` label/bootstyle flip shared by both panels' Start↔Stop toggle |
| `tests/test_log_name.py` | 22 | `sanitize_log_name` CombatLog filename trimming (`CombatLog-2026-05-16_2152` → `CombatLog_2152`) |
| `tests/test_boss_timer.py` | 151 | `BossTimer` cycle/syphon/double-seed transitions + phase state machine (time-driven, no sleeps) |
| `tests/test_combat_monitor.py` | 123 | `_process_line` dispatch, player extraction, latest-log discovery, start-without-folder guard |
| `tests/test_build_executor.py` | 635 | Install/uninstall orchestration (both modes), legacy cleanup, `create_scripts` markers, xml.add, launcher detect, `tasklist` argv, Damage Numbers backup-once/install/revert/uninstall + orphan-mod recovery, TextColors resource+incoming direction flips (surgical, always-Customized/create-from-Default, on/off, colors-survive-a-build, uninstall flips back keeping colors + `.bak`) — no MTASC/Tk |
| `tests/test_build_compile.py` | 128 | MTASC compile-integration — whole codegen → bundled `mtasc.exe` exit-0 (escaping end-to-end + console/cast/stopwatch variants); the only check bridging Python-side correctness to the SWF side; win32 + compiler gated |
| `src/kazbars/deeps_panel.py` | 929 | `DeepsPanel` Toplevel — status row, Start/Stop, Lock + Layout, appearance (size/background sliders, font fixed to Segoe UI), Readout card (window width + a Style preset radio — Live/Steady/Calm — bundling smoothing/round/refresh), Alarm & Tints card (DPS-out alarm slider over the 1000–4000/s band + Tank/Standard survival-tint preset radios + a live breakpoint caption), 5-cell visibility picker, pet toggle. Owns the meter + overlay + 100 ms UI tick + alarm hysteresis state machine |
| `src/kazbars/deeps_meter.py` | 452 | `DeepsMeter` daemon thread — tail loop, log rotation detection, `is_live` probe via `CreateFile` exclusive-share, configurable rolling-window width (`set_window_seconds` recreates the trackers). Publishes `MeterSnapshot` (focus is no longer probed here — the shared `ForegroundWatcher` owns it) |
| `src/kazbars/deeps_overlay.py` | 749 | Five-cell numbers display (DPS out/in, HPS out/in, ΔHP in). Two layouts (horizontal/vertical), 8-direction stroke text, 2 Hz alarm pulse on DPS-out, net-HP tints, click-through lock. `_DisplaySmoother` eases the drawn digits (EMA + coarse rounding + redraw-cadence gate); numbers use smoothed values, colors use the raw snapshot |
| `src/kazbars/overlay_engine.py` | 830 | Shared PIL + win32 overlay engine: `LayeredOverlay` (per-pixel-alpha win32 blit) + `HudOverlay` (shared backdrop / lock chrome / drag / visibility) + `OverlayConfig` (geometry+appearance dataclass) + `load_font`/`FONT_FAMILY_CHOICES`. Both the Deeps and Live Tracker overlays are thin `render_content` + `measure` consumers |
| `src/kazbars/deeps_parsers.py` | 408 | Pure parsers (no Tk, no threading). 5 entry points: `parse_outgoing_damage`, `parse_incoming_damage`, `parse_incoming_heal`, `parse_outgoing_heal`, `parse_pet_hit` (own-pet only). Damage/heal regexes byte-identical to `Deeps/rust/aoc-damage` + `aoc-heal` |
| `src/kazbars/deeps_trackers.py` | 182 | `DamageOutTracker`, `DamageInTracker`, `HealsInTracker` (3-bucket per-bucket warm-up), `HealsOutTracker` |
| `src/kazbars/deeps_settings.py` | 354 | `deeps_settings.json` defaults + ranges re-expressed as a `settings_core.Schema` (validation + atomic I/O delegate to the engine). Keeps the readout-tuning keys (`window_seconds`, `smoothing`, `round_step`, `refresh_ms`, `survival_preset`). `survival_preset` (Tank/Standard) drives the four ΔHP-in tint thresholds via `normalize_survival_preset` + the `_SURVIVAL_PRESETS` table (panel-invoked domain logic, kept out of the load path), twin of the readout-preset machinery |
| `src/kazbars/deeps_rolling_window.py` | 81 | `RollingWindow` data structure — record/prune/sum_since/count_since/first_event |
| `src/kazbars/assets/deeps/pets.json` | 81 | Pet-name registry — lifted from `Deeps/rust/aoc-damage/data/pets.json` |
| `tests/test_deeps_parsers.py` | 544 | 163 behavior-table cases from Deeps's Rust tests + the own-pet gate |
| `tests/test_deeps_meter.py` | 451 | 39 cases — file selection, lifecycle, `_process_line` dispatch, configurable-window reset, attach-at-EOF vs boundary resume, held-open-file end-to-end |
| `tests/test_deeps_trackers.py` | 288 | 28 cases — warm-up, decay, reset, per-bucket warm-up for heals |
| `tests/test_deeps_settings.py` | 517 | 110 cases — defaults, validation (incl. readout-tuning keys + `survival_preset`), `normalize_survival_preset`, round-trip, corrupt-file fallback |
| `tests/test_deeps_rolling_window.py` | 169 | 13 cases — primitive smoke + decay-during-silence |
| `tests/test_deeps_overlay.py` | 376 | 30 cases — pure helpers + 5-cell IDs/labels + `_DisplaySmoother` (EMA/rounding/cadence) (visual behaviour is manual QA) |
| `tests/test_damageinfo_settings.py` | 373 | Damage Numbers config — defaults/schema invariants, symmetric offset ranges + common X/Y step + `is_offset_key` + `invert`/`relative` sets, offset clamping, enum/bool coercion, `compute_final_value`, `readout`, `apply_preset`, round-trip/fallback, per-source color catalog↔engine parity + `normalize_color` (colors are not persisted settings — a legacy `source_colors` key is dropped on save) |
| `tests/test_damageinfo_colors_panel.py` | 78 | Data-layer test for the colors panel: `_read_colors` (none/missing → {}, bare-upper hex, omits colorless) + `apply_colors` (none when no TextColors anywhere, create-Customized-from-Default leaving Default stock, edit-existing-Customized + one-time `.bak`, directions/siblings preserved, colorless source is a no-op, reset-to-Default flow). UI is manual-QA-only |
| `tests/test_damageinfo_generator.py` | 183 | Regex↔AS2 coupling guard (every bake pattern matches the shipped source **exactly once**) + shipped-constant == GAME_DEFAULTS (the offset-0-is-stock invariant) + bake correctness (offset→final, dual-axis shadow blur, enum/bool) + per-content-scale guard (Size survives the pop-in) + easing-ships-Quad guard + hard-fail on drifted source; no MTASC |