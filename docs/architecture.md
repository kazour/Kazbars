# Architectural Map

**Current as of:** 2026-11-06 (grid cards are never expanded — a to-scale preview, `grid_preview` + `grid_preview_canvas`, and a cog that opens `grid_settings_dialog`; the in-game side is one shared runtime — clock, world, effects — under modules on a typed lifecycle, sized from one profile-wide overlay size × a per-module `scale`; profile schema 3 with `overlay`, `console` and `onslaught` sections; AS2 compiles in-process via `as2c`).
**Purpose:** Module topology, dependencies, and coupling hotspots. Updated alongside code changes — if you edit this file, commit it with the code. Per-file line counts live in [`inventory.md`](inventory.md) (generated); role blurbs live in [`inventory-roles.md`](inventory-roles.md).

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
- `ui_widgets` is the leaf "core glue": `blend_alpha`, `add_tooltip` (+ `_InAppToolTip`), `app_toast`, `flash_status_bar`, `debounced_callback`, `refresh_tooltip` (re-arms a tooltip for a canvas whose tip follows the pointer), and the event-binding helpers (`bind_card_events`, `bind_button_press_effect`, `bind_label_hover_colors`, `bind_label_press_effect`). Imports nothing from the three siblings below — they depend on it, not the reverse, so no cycles.
- `ui_headers` builds the headers: `create_dialog_header`, `create_app_header`, `update_app_header_color`, `create_tip_bar`. Imports `blend_alpha` from `ui_widgets`.
- `ui_forms` builds the form fields + settings-panel builders: `labeled_spinbox`/`labeled_combobox`/`position_entry`, `size_slider` (the `scale` control — a percent of the overlay size, 50–200 in steps of 5, with a live pt/px hint and an optional `on_move` for live feedback during the drag), `create_rounded_rect`, `ColorSwatch` (now with `set_enabled` for master-gated forms), and the shared settings-panel group the config panels and Extras dialogs use — `create_card`, `create_status_block`, `create_slider_row`, `toggle_button_state`, `create_toggle_action_button`, `refresh_toggle_button`. Imports `add_tooltip` from `ui_widgets`.
- `ui_collapsible` holds `CollapsibleSection` (with `set_dimmed`, consumed by `buff_display_editor`). Imports `blend_alpha` from `ui_widgets`.
- `ui_components` adds stateful composites: the toast stack — pure `ToastModel` (visible cap + queue, two-tier priority, coalesce-by-key) rendered by `ToastManager` (all placement through the single `_layout()` authority, which subtracts a `set_bottom_guard(*widgets)` inset — `_bottom_inset()` sums height + `PAD_XS` over each *mapped* guard, read live in `_place`, never cached — to keep the stack clear of whatever is pinned to the parent's bottom edge, on the Grids tab the extras tiles plus the in-game status row above them; `relayout()` re-runs `_layout()` after a tab switch maps or unmaps those guards) — plus `DragReorderManager`, `create_scrollable_frame`, `scroll_widget_into_view` (scrolls a canvas the least it takes to show a widget whole), global mousewheel routing.
- `ui_tk_style` handles raw-tk widget styling + dark-titlebar monkey-patch.
- `custom_menu_bar` is the dark-themed Canvas-based menu bar (was in `ui_components`; extracted for size + single-consumer isolation).

### App state
```
settings_manager (get/set proxy + safe_save_json/safe_write_text)
  ← settings_core  ← deeps_settings, live_tracker_settings, damageinfo_settings
                   ← prefs (PREFS_SCHEMA)
                   ← profile_document (SectionSpec/SectionRegistry + validate_document)
  ← window_position
userdata (userdata/ paths + ensure_layout)  ← prefs, settings_backup, app
profile_document ← grid_model + overlay + live_tracker_settings + deeps_settings + stopwatch
                   + inspect + cast_timer + console + onslaught + damageinfo_settings + buff_xml
                   (each exports a PROFILE_SECTION; damageinfo_settings exports two —
                   `PROFILE_SECTION` (damage_numbers, BUILD) + `DAMAGE_COLORS_SECTION`
                   (damage_colors, sparse PATCH))
  ← profile_library (sole reader/writer of userdata/profiles/) ← profile_io, app
profile_store (in-memory doc + debounced autosave) ← profile_io, app
```
- `settings_core` is the schema-driven settings engine (`Field`/`Schema`/`Migration`/`Store` + functional `load`/`save`/`validate_all`); it imports only `settings_manager.safe_save_json` and stdlib. Every settings file declares a `Schema` and delegates validation + atomic I/O to it. It is **strict drop-unknown** — undeclared keys are erased on save — so any dynamic key namespace is one structured-dict `Field`, never N top-level keys.
- `userdata` resolves the `userdata/` storage root (created fresh on first launch by `ensure_layout()`; **no legacy migration** — old `settings/`/`profiles/` next to the exe are ignored) and its named subpaths. `assets/` stays read-only.
- `prefs` declares `PREFS_SCHEMA` (machine-local `prefs.json`, strict). `app.settings` is a `settings_core.Store` built on it; `init_settings(app.settings)` keeps the `get_setting`/`set_setting` proxy working, and `settings_manager` now holds only that proxy + the atomic temp+rename writers (`safe_save_json`/`safe_write_text`). The strict guard is `tests/test_prefs_schema_covers_all_proxy_keys` — it greps every proxy key and fails if one isn't a declared Field.
- `window_position` stores all window geometry under the single `window_positions` prefs dict field (keyed by window name), reached via the `get_setting`/`set_setting` proxy — not the `_settings` global, and not N top-level `window_pos_*` keys. It also owns `fit_window_height(window, width)` — the shared re-fit for fixed-width panels whose content grows at runtime (a status line wrapping to two rows): reconfigures only when `winfo_reqheight()` actually moved, and re-clamps through `clamp_to_screen` so growing can't push the window off the bottom of the screen.

**Storage layout / data lifecycle.** Three data classes by lifecycle, not by feature:
```
<install>/
  KazBars.exe
  assets/kazbars/{Database.json, Database.json.default, Default.json}  ← REFERENCE (read-only, shipped; app never writes here)
  userdata/                       ← USER + MACHINE (created fresh by ensure_layout() on first launch)
    prefs.json                    ← machine-local (window positions, game path, resolution, the `active_profile` pointer, the Grids tab's `grids_tab`, the overhead anchor `anchor_side`/`anchor_up` — this PC's field of view, so never profile data, the `last_build`/`last_patch` staleness records, UI state)
    profiles/*.json               ← profile documents (identity = in-doc id; `profile_library` is the sole reader/writer)
    profiles/*.json.bak           ← per-profile session-start snapshots
    profiles/trash/               ← deleted profiles, pruned to the 10 newest
    database_user.json            ← user buff deltas (seeded empty)
    prefs3_snapshot.xml           ← copy of the game's Prefs_3.xml, taken only while the install is healthy; Repair re-injects stripped archives from it (Flow 29)
    content/  content/.bak/       ← OTA reference content + rollback
```
The editor and OTA updater **never write `assets/`**, so a reinstall always has a clean floor and the `Database.json` ⇄ `.default` byte-identity test holds. Backup/restore (`settings_backup`) covers an explicit `userdata/` allowlist — `profiles/` (minus session `*.json.bak` snapshots and `trash/` — local recovery state), `database_user.json`, and `prefs.json` — and never `content/` (regenerable OTA cache) or `prefs3_snapshot.xml` (it mirrors game state, not the user's own data, and the Funcom prefs tree is already in the zip on its own terms); `prefs.json` rides in the zip but is machine-local, so restore leaves it out unless the user ticks the opt-in checkbox. A profile is a **document**: envelope `schema` (int, `profile_document`'s ladder key, 3 today — the 1→2 rung converted px positions to fractions, the 2→3 rung `_overlay_scale` converted per-module px/pt sizes to a percent `scale` of one `overlay.size`) + `id` (stable 8-hex — identity; filenames are cosmetic slugs) + `name` + `authored_at` ([w,h] display-only provenance) + `modules` (one section per registered `SectionSpec`: `grids`, `overlay`, `boss_timer`, `deeps`, `stopwatch`, `inspect`, `cast_timer`, `damage_numbers`, `console`, `onslaught`, `damage_colors`, `buff_bars` today — `overlay` (`{size, font}`) and the extras + `damage_numbers` sections are flat config dicts, BUILD lane, fractions from birth where positions apply, each extra carrying a `scale`; `deeps` and `boss_timer` are LIVE lane — every field retunes an open overlay immediately, including its screen `x`/`y`, which stay plain px since desktop placement isn't a game-resolution concept; `damage_colors`/`buff_bars` are **sparse** PATCH lane — `{}` default, absent field = "no opinion, follow whatever the XML already says", written only by the XML editors' own Apply, never dispatched on a profile switch). Grid and extras positions are **fractions of game resolution** (`fx`/`fy`; `playerFx`/… for the cast timer's two points; full floats): px exists only at the editors' position fields and the AS2 bake (`grid_model.unproject_px`/`project_px`), so a resolution change rewrites nothing and a shared profile lands proportionally on any screen; sizes are **percents of one base size** (`overlay.size`, with each grid, panel and the cast timer carrying its own `scale`; see `overlay_size` below), so a resolution change rescales nothing there either — the seeded template gets its `overlay.size` from `overlay.size_for_height` (≤1080 / ≤1440 / above → 12 / 16 / 24, i.e. 48 / 64 / 96 px icons at scale 100) at instantiation (`create_from_template`) and at first launch's "Use Defaults" (`_seed_overlay_size`), never on a document the user has tuned. Old-format profiles (root `grids`/`profile_schema`) are **rejected, not migrated** (clean start): the library never lists them and leaves the files untouched. The active pointer is `prefs.active_profile` (the id); there is no save prompt anywhere — `profile_store` autosaves debounced, `profile_library.write` validates every byte, and Build & Install flushes first so built == saved. The shipped `assets/kazbars/Default.json` is the document-format (schema 3) starter and is OTA-manifest-tracked (`gen_manifest.py`); templates are instantiate-only — `profile_library.create_from_template(name, authored_at)` copies one into the library under a fresh id and sets that resolution's `overlay.size`, so no template can ever be opened or overwritten in place.

### Grid editing
```
grid_model  ← grid_dialogs  ← grid_editor_panel  ← grids_panel
grid_model  ← grid_settings_dialog  ← grid_editor_panel
grid_model  ← grid_preview  ← grid_preview_canvas  ← grid_editor_panel
              grid_preview  ← grid_editor_panel, grids_panel
            (also pulls settings_manager, window_position, ui_*)
classes       ← grid_model, grid_editor_panel, grids_panel, prefs
overlay_size  ← grid_model, grid_editor_panel, grid_settings_dialog, ui_forms, grids_generator, cast_timer, stopwatch, inspect, console, onslaught (+ each Extras dialog)
overlay       ← grids_panel, grid_editor_panel, grids_generator, first_launch, profile_library, app
```
- `grid_editor_panel` owns the per-row card (`GridEditorPanel`, never expanded: the title line — name, badge, summary, the ⚙ cog, "Move…", Enabled, ▲ ▼, × — the to-scale preview and the names line). Its settings live in `grid_settings_dialog` (`open_grid_settings`, `GridSettingsDialog`: Grid / Icons / Overhead / Sorting cards, the fill / timer / sort / layout option tables, X/Y, Size slider), which hands a draft to the card (`preview_draft` live, `apply_settings` on Apply, `cancel_draft`) and never writes the config itself; `apply_settings` runs the resize rules (slot trim / restore, a dynamic grid's 1×1, the fill reset via `grid_model.valid_fills`). `grid_settings_dialog` is imported by `grid_editor_panel` only. `grids_panel` is the container (toolbar with the Overlay size/font dropdowns, the class-tab strip, scrollable list, profile load/save bridge). A grid is a floating grid (`player`/`target`, 64 slots) or an overhead grid (`friendly`/`hostile`, 16 slots; a dynamic one is a *band*) and carries an optional `class`; there is no slot total across grids, `grid_model.max_slots` is per grid.
- `grid_preview` is the pure geometry + text behind a card's preview (placements per fill direction, the to-scale `layout()`, hit test, summary / tip / names-line text); imports only `grid_model`. `grid_preview_canvas.GridPreview` is the Tk canvas that draws it and routes pointer/keys to the card's `on_pick`/`on_clear` (imports `grid_preview`, `grid_model`, `ui_helpers`, `ui_widgets`). The empty-state preset cards in `grids_panel` draw through `grid_preview.layout` too. Slot assignment is the card's own `edit_slot` (a `BuffSelectorDialog`), not a dialog class of its own.
- `classes.py` is the twelve game classes (id = `GetStat(67, 2)`, tab label, archetype) — pure data behind the tab strip, a grid's `class` and the Move/Copy menu.
- `overlay_size.py` is the **size model**, pure integer arithmetic with half-up rounding (AS2's `Math.round`): the profile has one base size (`overlay.size`, 10–24) and every module has its own `scale` (percent, 50–200), from which `panel_fs` (panels), `cast_fs` (cast timer) and `grid_metrics` (icon `4 × round(s)` px, timer and stack `round(s)` pt, a 9 pt floor and fit caps) derive every size. The generator bakes the results and the dialogs' hints read them back, so the two cannot drift; `tests/test_as2_stub_pins.py` pins the AS2 geometry that must agree with it. `overlay.py` is the `overlay` section (`{size, font}`) with the dropdown choices and `size_for_height` (the seed size per game-resolution height: ≤1080 → 12, ≤1440 → 16, else 24). `swf_font.py` is the font layer: pure byte functions that splice a baked face's tags (`assets/kazbars/fonts/<slug>.bin`) over the two Arials `base.swf` embeds, import the game's own Verdana, and swap DamageInfo's `_ConanFont` import (Damage Numbers' Style card).

### Buff database (three-layer merge, pure data layer)
```
settings_manager (safe_save_json)  ← buff_db_layers  ← buff_database  ← database_editor (UI)
                                                      ← app.py (DeltaStore + get_floor)
buff_xml  ← buff_display_editor   (UI; HUD-XML editor dialog)
```
- `buff_db_layers.py` is the pure three-layer merge: effective DB = stock floor (`assets/`, read-only) ← OTA `content/` override ← user deltas (`userdata/database_user.json`), **user always wins**, keyed on the primary spell ID `ids[0]`. `merge_layers`/`load_effective`/`load_floor` return `(buffs, provenance)` where provenance is `stock`|`content`|`user`; `compute_delta(floor, edited)` diffs the editor's effective list back into a delta (user adds/overrides + tombstoned `ids[0]`); `DeltaStore` reads/writes `database_user.json` atomically. Imports only stdlib + `settings_manager.safe_save_json`.
- `buff_database.load_layers()` merges the three layers into `self.buffs` + `self.provenance` (corrupt stock → bundled `.default` **in memory**, never writes assets), `reload()` re-merges (the OTA updater calls it), and `current_floor()` hands the editor the stock←content floor. `load(json_path)` stays for single-file/back-compat (tests).
- `database_editor` writes **only** `database_user.json` via `DeltaStore`: `save()` computes a delta vs the floor; the Source column badges each row (Built-in / Updated / Yours from provenance); Delete branches on provenance — hide-a-built-in (reversible tombstone) vs delete-your-buff. Because `assets/` is never written, the `Database.json` ⇄ `Database.json.default` byte-identity invariant gets *stronger*.
- `buff_database.py` / `buff_db_layers.py` / `buff_xml.py` import only stdlib (plus `safe_save_json` for the merge writer) — no Tk, no ttkbootstrap. Tests collect them in a minimal CI image without the UI extra (`tests/test_buff_db_layers.py`, `tests/test_buff_xml.py`, `tests/test_grids_generator.py`).

### Reference content / OTA (silent, reversible content channel)
```
update_orchestrator  ← app.py, first_launch, app_popups   (the one update routine; Tk)
  → update_check (fetch_release), self_update (stage / spawn / startup marker), content_update (check_and_apply, _post)
content_update  ← update_orchestrator, app.py (active_content_db_path, revert), profile_io
  → buff_db_layers (summarize), userdata (content_dir), ui_widgets (toast)
update_check    (GitHub release lookup, pure; content_update borrows its _parts version parser, self_update its release_tag)
self_update     ← update_orchestrator, __main__   (in-place app update, pure)
```
- **One routine, app first.** `update_orchestrator.check_on_launch` / `check_now` run `update_check.fetch_release` on a worker thread; a newer release is offered ("vX is available — click to install") and the content check is skipped — the new build ships current content. Only when the app is current (or, on launch, unreachable) does `content_update.check_and_apply` run. Click 1 → `start_install` → `self_update.stage_release` streams `KazBars.zip` into `<install>/.update/` (not %TEMP% — an exe launched from TEMP trips AV heuristics), verifies it against the `.sha256` asset, unpacks to `.update/KazBars/`, writes `pending.json`; progress/ready/failed toasts coalesce under one `app-update` key. Click 2 → `restart_to_install` runs `KazBarsApp._on_close()` (its unsaved-work guards may cancel; the staged tree waits) and, on True, `spawn_apply` launches the **staged** exe with `--apply-update --target <install> --wait-pid <pid>`. `__main__` routes that flag to `self_update.run_apply` before any logging or Tk: `wait_for_pid` (ctypes) → `wait_until_writable` on the install's exe (the real "nobody runs this install" signal) → `plan_copy` (skips `userdata/`, `logs/`, `.update/`; exe last) → `apply_tree` (phase A copies every file to a `.kbnew` sibling, phase B is one `os.replace` burst — the mixed old/new window is the burst, not the copy) → `prune_internal` (drops `_internal/` files the new build doesn't ship, never the root) → relaunch. The new app's `finish_startup` (deferred 1.5 s — the staged exe is still tearing down) reads `startup_action` (`updated` / `failed` / `retry` / `clean`), toasts, and removes `.update/`; a `retry` (apply died under the attempt cap) is respawned by `__main__` before the window exists. Every spawn goes through the single `spawn_detached` (`cwd` = install root, `CREATE_NO_WINDOW`). The asset names are a contract with `release.yml` (`tests/test_release_assets.py`); `KAZBARS_RELEASE_API_URL` points the lookup at a local fake for the manual upgrade check. `update_check` and `self_update` are Tk-free and on the mypy gate; `update_orchestrator` mirrors `content_update`'s dispatcher shape.
- `content_update.py` polls `ota/manifest.json` (raw URL on `main`) on launch; if it advertises a newer `content_version` than `prefs.json.content_version`, the app is new enough (`min_app_version`), and the auto-update toggle is on, it downloads the `Database.json` + `Default.json` payloads (URLs on the `main` ref; integrity is the sha256), verifies sha256, **atomically** swaps them into `userdata/content/` with a `.bak/` rollback (snapshot prev → `os.replace` → write the `content/manifest.json` marker LAST), re-merges the live DB (`BuffDatabase.reload()`), and shows **one** toast. Anything that fails swaps nothing; it defers if the DB editor is dirty or a build is running (and, on a fresh install, until first launch completes). Pure helpers (`parse_manifest`/`is_newer`/`app_supports`/`verify_sha256`/`apply_content`/`rollback`/`summarize_changes`) + a thin Tk dispatcher (`check_and_apply`/`revert`); mirrors `update_check`'s shape but doesn't cross-import it. **Not** on the mypy blocking gate (imports tkinter).
- **Three version markers, kept distinct:** the server `ota/manifest.json` advertises the latest; `prefs.json.content_version` (defaulting to the shipped `CONTENT_BASELINE_VERSION`) is the **authoritative comparison key**; `userdata/content/manifest.json` records what's currently applied (the step-5 commit marker). `CONTENT_BASELINE_VERSION` (`__init__.py`) is stamped == the manifest's `content_version` by `scripts/gen_manifest.py`, run **locally** in the same commit as a stock-file change (the pre-commit pytest gate blocks it otherwise), so a fresh install ships current and fires no redundant first-run update. `.github/workflows/ota-manifest.yml` only **verifies** on push-to-main touching the stock files (regenerate + fail on drift; never commits back, so branch protection can't block it). `tests/test_manifest.py` guards both (sha256 match + baseline lockstep). `min_app_version` is a **floor the generator preserves** across regenerations — never the running `__version__` (that would lock every older install out of the catalog on each patch release); it is raised only with `--min-app X.Y.Z`, when a payload genuinely needs a newer app, and the notes say why.
- User controls (Updates menu): an **"Automatically update the buff database"** toggle (default on), **"Check for updates now"** (manual — app release first, then content), **"Revert last buff-database update"** (`rollback()`). User deltas (`database_user.json`) are never touched by apply or rollback.

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
             ← build_executor  ← build_action, game_folder, app_popups
             ← game_persistence  ← build_executor, build_action, game_folder
app_popups   ← app.py, build_action, first_launch, build_loading
build_loading  ← build_action
inspect_catalog, onslaught, console, cast_timer, stopwatch, inspect (config + gate layers),
overlay, overlay_size, swf_font (size / face / SWF), prefs (anchor defaults), grid_model  ← grids_generator
```

`game_persistence` is the cluster's game-folder layer: it owns the structures that live in the *game's* install (the two XMLs, the `Data/Gui/Aoc` fragments, `IgnorePatcher.enable`, `Prefs_3.xml`) and the constants naming them (`GAME_EXES`, `PATCHER_EXE`, `LEGACY_AOC_DIRS`). `build_executor` calls it during install/uninstall and re-exports nothing; `game_folder` calls it for Repair, the health check and the desktop shortcut; `build_action` for `client_supports_flag` and `is_merged`. It imports one thing upward (`build_utils.CREATE_NO_WINDOW`) and no Tk, so it sits on the mypy blocking gate.

`app_popups` is the frameless dark popup family — the shared chrome (`make_popup_shell`/`draw_close_button`/`center_popup` + the `WIDTH`/`BG`/`BORDER_COLOR`/`SCANLINE_STEP` frame constants) plus `show_welcome_popup` (first-launch), `show_about_popup` (Help ▸ About), and `show_close_game_required_dialog` (build pre-check). `build_loading` keeps only `BuildLoadingScreen` and imports the chrome one-way (no cycle — `app_popups` imports nothing from the build cluster).

`build_utils.compile_as2` compiles AS2 in-process via `as2c` (GPL-2.0-or-later — a Python port of MTASC 1.14 that bundles its own `std`/`std8` intrinsic headers), no subprocess. `as2c` is vendored verbatim at `src/as2c/` — a second top-level package beside `kazbars` in the wheel, not an installed dependency; it is third-party code to this doc, outside the module inventory and the mypy gate, and is replaced whole rather than edited. `find_compiler` and `paths.COMPILER_ASSETS` are gone; `src/kazbars/assets/compiler/` no longer exists — `kazbars.spec` ships `as2c`'s headers via `collect_data_files("as2c")` instead. `CREATE_NO_WINDOW` still guards the remaining console-child spawns (`tasklist`, the patcher).

**AS2 class names are load-bearing.** `base.swf` bootstraps `m_Module = new KazBars(this)`, so the generated classes, the `stubs/KazBars*.as` filenames, and `KazBars.as.template` must keep the `KazBars*` names to bind against it. The generator also emits `KazBarsData1..N` — the grid configs and id facts packed under the AS2 compiler's 32 KB-per-class bytecode cap, each filled into `d` by `KazBarsData.init()`; `base.swf` never bootstraps those, but `test_as2_class_names.py` holds every generated class to the prefix. A Python-only rename silently breaks the bind — undoing one needs a Flash CS6 re-export of `base.fla`/`base.swf` with the new bootstrap. The template's gates (`//#if` blocks, flags CONSOLE, CONBUFFS, CONCASTS, CAST, INS, ONS, PLATE, SW, kept or stripped by `_apply_feature_gates`) decide which stubs compile: a stripped gate leaves the stub unreferenced and the compiler skips its class. Always in the build: the shared runtime (`KazBarsClock`, `KazBarsWorld`, `KazBarsEffects`, `KazBarsTeam`, `KazBarsCopies`), the screen grids (`KazBarsGrids`, `KazBarsGridView`, `KazBarsGridPick`), `KazBarsModule`, `KazBarsPanel`, `KazBarsPreview` and `KazBarsPreviewPanel`. Gated: the overhead grids (`KazBarsOverhead`, `KazBarsRelations`; PLATE, any baked overhead grid), `KazBarsCastTimer` with `KazBarsCastSide` (CAST), `KazBarsInspect` with `KazBarsInspectRows` and `KazBarsInspectData` (INS), `KazBarsOnslaught` with `KazBarsOnsScan` (ONS), `KazBarsStopwatch` (SW), and the console shell `KazBarsConsole` with `KazBarsConTab`/`KazBarsConList` (CONSOLE) plus one class per tab — `KazBarsConBuffs` (CONBUFFS), `KazBarsConCasts` (CONCASTS).

**One shared runtime, then modules.** The host makes one `KazBarsClock` — the single frame handler; every periodic job is a task (every N frames or N ms) that is switched on only while it has work, so idle costs nothing — and one `KazBarsWorld` that reads what the game says once and hands it to every module: the player (`onPlayer`, and `onClass` off `GetStat(67, 2)`), your target (one `SignalOffensiveTargetChanged`; `onTarget`), a refcounted table of `Character`s by instance id, the team and the damage feed (`world.tm`), and `effects(id)` — one `KazBarsEffects` per character, shared by every view that shows its buffs (owners `watch` the ids they want, and the buff signals stay connected only while an owner exists). The grids are modules like the rest. `KazBarsGridPick` picks what a grid shows from a character's effects (a dynamic grid's whitelist with its `d.WL` fact codes, a static grid's slots, one icon per caster copy via `KazBarsCopies`), `KazBarsGridView` draws it (a slot is made the first time something is drawn in it and kept; every write is on change; the bar or digit timer and the flashing run on a clock task), `KazBarsGrids` owns the screen grids and `KazBarsOverhead` a pooled view per character `KazBarsRelations` knows to be friendly or hostile. Per class: only the player's class's grids (`cls`) and the All grids are built, the All ones alone until the class reads.

Modules implement `KazBarsModule` (`stubs/KazBarsModule.as`: `create`, `previewOn`/`previewOff`, `isActive`/`setActive`, `loadState`/`saveState`, `previewKey`/`previewLabel`, `cleanup`) and the core keeps them in one `modules` array registered in z-order only (grids, overhead, inspect, cast timer, onslaught, stopwatch, console — later ones stack above); every lifecycle call is an ungated loop over it through a typed local, so a build gate carries only the field, the construction, the registration, the `configure(d.X, …)` that hands the stub its data block and the stub's own feeds. The archive is read and written in one place each — `loadAll`/`saveAll` — so the three call sites (`OnModuleActivated`, `exitPreview`, `OnModuleDeactivated`) are one line apiece. **Two classes of module, and the split is what preview is for.** HUD modules (grids, overhead grids, cast timer, inspect panel, onslaught tracker) are game-facing displays: hidden when they have nothing to show and deliberately mouse-transparent in normal play so they never eat a combat click — which is why they need preview, their only interactive moment. Each is positioned there through the shared overlay (`KazBarsPreview.attach(spec)` — static, the class holds no state: tinted rect, label and a Stage-clamped drag from the spec's bounds rect, so a top-left-anchored grid and a centre-anchored cast timer share one implementation; no coordinate readout, a spot is dragged rather than typed). The overlay is *removed* on exit, never hidden — a hidden overlay would still take the click. Tools (stopwatch, console) are opt-in utilities: always interactive, dragged by their own title strip through `KazBarsPanel`, so their `previewOn`/`previewOff` are no-ops. The **preview control panel** (`KazBarsPreviewPanel`) is never gated, so the `d.PF` block (base size, face, app version, overhead anchor) and `ppanel.configure(d.PF)` are emitted unconditionally: a mistake there breaks every build. It exists only while preview mode is on, but its checks are the master switches for what it lists: `enterPreview` calls `begin()`, one `addGrid` per screen grid (bucketed by `cfg.type` into Player Grids or Target Grids; overhead grids have no row), `previewOn()` on every module, then one feature-gated `addExtra` per extra in Tools order — cast timer, inspect, onslaught, console, stopwatch — each labelled and keyed by the module (`previewLabel()`/`previewKey()`) and seeded from its own `isActive()`, so neither the panel nor the core caches a state; a header click toggles its group; `show()` goes last so the panel lands topmost and steps its own size down until the plate fits the Stage. Preview is WYSIWYG, and unchecked means genuinely inactive, not merely hidden. A row routes through `previewToggle(key, shown)` to the module's `setActive`, and `exitPreview` persists through the same `saveAll` the deactivate path uses.

`stubs/KazBarsPanel.as` is the chrome-family base of the five runtime-drawn panels (`KazBarsConsole`, `KazBarsStopwatch`, `KazBarsInspect`, `KazBarsOnslaught`, `KazBarsPreviewPanel`): warm near-black plate, 1px black-over-bronze double frame, device-font `TextField`s in the build's face (`KazBarsPreview.FACE`, set from `d.PF.face`; the shipped Arials, the game's `_StandardFont`, or a baked face spliced over the Arials), the flat button and checkbox, Stage-clamped title-strip drag, the fold glyph. Every dimension is `Math.round(FS × ratio)` off `applyBaseSize`, with the text roles Small 0.8 / Title 1.25 / Alert 1.6 (`roleFS`), and `FS` is the panel's baked body size, `panel_fs(overlay.size, scale)` — so a panel scales as one piece and its collapsed bar (`× 15.8` by `× 2`) is the same bar in every panel at one body size. A panel is seated on the Stage as it reads now and again when the Stage resizes. Per-panel `loadState`/`saveState` are deliberately not shared (archive keys and load orderings differ): stopwatch `swx`/`swy`/`swc`/`swv`, console `cnx`/`cny`/`cnc`/`cnv`/`cnt`, inspect `inx`/`iny`/`inc`/`inp`/`inv`, onslaught `onpx`/`onpy`/`onax`/`onay`/`onv`, control panel `ppx`/`ppy`, cast timer `ctpx`/`ctpy`/`cttx`/`ctty`/`ctv`, each grid `gk_<key>_x`/`_y`/`_v` — for every user, since the persistence era declares the module permanently. The stopwatch is a count-up Start/Pause/Reset panel. The console (`KazBarsConsole`) is the shell — title, the tab strip in the profile's order (`d.CON.tabs`), two columns per tab, Clear, fold, drag; each tab is its own class implementing `KazBarsConTab` and feeds `KazBarsConList` columns from the shared runtime, drawn only while that tab is visible (Buffs taps World's one set of buff signals through `KazBarsEffects.tap`; Casts wires World's player and target itself). The onslaught tracker (`KazBarsOnslaught`, with `KazBarsOnsScan`, which finds the watched mobs as they spawn) does nothing outside the two Onslaught instances — their playfield ids and facts are baked into `d.ONS` — and is a HUD module whose two anchors (board, alerts) are placed in preview. The target inspect panel is a HUD module whose contract — the baked rows and watch list, the syntheses, the display gates, the PvP tab, the perks row, the visual constants and the in-game checklist — lives in [`inspect-panel.md`](inspect-panel.md); read that before changing any number in the stubs.

**Null-icon custom icons.** Some AoC buffs return `m_Icon.GetInstance()==0` (no game icon → the slot rendered blank). `grids_generator.CUSTOM_ICON_LINKAGE` maps such buff IDs → baked symbol linkage names in `base.swf` (`IcoSlow30/40/45/60` for the ice-gem slows), emitted into `KazBarsData.CUSTOMICON`. `KazBarsGridView` picks the icon per effect — the baked symbol from `d.CUSTOMICON`, the shared **`IcoNull`** fallback when the effect has no icon or its load failed, else the RDB image — and attaches a baked symbol as a slot sibling at **dynamic depth 8**, so no tracked buff shows a blank slot. The slot's authored art (bg/icoMask/m_icon/frame in the FLA) becomes timeline content in the negative reserved depth range at runtime, so depth 8 sits above it; the art's ring is at depth 9 and the timer/stack TextFields are pinned to fixed depths **10–13**, so they render above the icon rather than under it. A slot sits at the depth equal to its index, so the preview overlay (attached on top) stays on top through a buff-to-debuff type swap. The rounded crop is baked into the art (PNG inset ~56×56 in a 64×64 canvas), **not masked** at runtime: AoC's Scaleform renderer applies masks only to `loadClip` content (the RDB game icons), never to `attachMovie`'d content.

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
`src/kazbars/assets/damageinfo/src/__Packages`, regex-rewrites each named constant to
`default + offset`, and compiles the result into a copy of the pristine
`src/kazbars/assets/damageinfo/DamageInfo.swf` (two entry points — `MainDamageNumbers` +
`FixOnLoad`, the latter force-compiled so the container's `onLoad` survives the
inject). The AS2 is a from-scratch lean rewrite of the stock overlay: a single
`onEnterFrame` IN/LIVE/OUT loop (no TweenLite / `setInterval`), an O(1) column
hashmap, object pools, and a 3-way `SHADOW_MODE` (None / Fast offset-twin / Real
DropShadowFilter). A `font` setting (Style card, `swf_font.DN_FONTS`; Hyborian, the game's own, leaves the file alone) rewrites `DEFAULT_TEXT_SCALE` by `swf_font.dn_scale` and swaps the compiled SWF's `_ConanFont` import for the chosen face's embedded fonts. Gated by a master `enabled` flag (off by default); when off the
build leaves the stock file alone and reverts any prior mod via the one-time
`DamageInfo.swf.kazbars.bak`. The panel is **Model B** — every control stages into
`self.settings` and only Apply writes `damageinfo_settings.json` and closes; Cancel /
Escape / X discard.

A *second* game file — the skin's `TextColors.xml` — is reached by exactly one surface, the
per-source **color + direction editor** (`damageinfo_colors_panel.py` → each type's
`color="0x…"` and `direction="1|-1|0"`), which writes on its own Apply (`apply_colors`, no
build, no gate — like the Default Buff Bars editor), always to **Customized/** (created from
the stock Default/ copy when absent — the game patcher resets Default/ on update, so edits
there don't stick), with a one-time `TextColors.xml.kazbars.bak` of any pre-existing skin
file. Edits are **surgical and byte-preserving**: `set_source_color` and
`set_source_direction` (`buff_xml.py`) touch only their own attribute on the named element,
and the panel sends only the directions the user actually moved, since a direction write
*injects* the attribute when the source omits it. Directions are therefore user content —
**neither Build & Install nor Uninstall touches the file**; "Reset to game default" is the
route back to stock. Two SWF-baked toggles refine what the directions decide:
`fixed_col_split` ("Split signed numbers into Column B") splits whatever already drops into
the fixed column, and `other_resource_loss_to_target` ("Keep enemy drains overhead") holds
enemy resource drains above the enemy whatever their direction says. Two named group lists in
`buff_xml.py` (`RESOURCE_LOSS_TYPES` / `INCOMING_DAMAGE_TYPES`) back the editor's two macro
checkboxes, which stage a whole group's per-row directions at once and derive their own tick
state from those rows. The regex↔constant coupling is guarded by `tests/test_damageinfo_generator.py`
(no live compile). Isolated — `damageinfo_*` import only stdlib + `build_utils`/`paths` (generator)
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
`deeps_settings` exports a `PROFILE_SECTION` (LANE_LIVE), the same
sanctioned-infrastructure pattern `live_tracker_settings` uses; `deeps_panel`
never imports `profile_document`/`profile_store` itself — it exposes
`get_profile_data()`/`load_profile_data()` and app.py wires them through a
duck-typed `on_deeps_profile_data` hook (mirrors `on_boss_timer_profile_data`),
so cluster isolation holds.

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
src/kazbars/app.py  → profile_io, game_folder, game_resolution, build_action, buff_display_editor, first_launch, custom_menu_bar, update_orchestrator, content_update, settings_backup, stopwatch_panel, inspect_panel, cast_timer_panel, console_panel, onslaught_panel
profile_io  → profile_store (runtime document), grid_model, ui_widgets, userdata
```
These modules are consumed only by `src/kazbars/app.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KazBarsApp` instance) as first arg. That wide seam is a *checked* contract: `tests/test_app_contract.py` AST-scans every `app.<attr>` access in app-taking functions and asserts each attribute is defined on `KazBarsApp` (Tk surface + `self.X` assigns), so a rename in app.py fails CI instead of breaking a satellite at runtime. New cross-module state goes in `KazBarsApp.__init__`'s `# State` block — a satellite must not invent app attributes by assignment. `KazBarsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `content_update`, `app_popups`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup). `update_check`'s silent launch check is called directly (single fire-and-forget caller in `__init__`); the Updates-menu manual check goes through the `_check_app_updates_now` delegator; its worker threads schedule named main-thread dispatchers (`_show_update_toast`/`_show_manual_result`) guarded by `winfo_exists()`. `app_popups` also imports its pure `fetch_latest` for the About popup's manual update check.

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 33 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 31 | `ui_widgets` | Core glue (`app_toast`/`add_tooltip`/`blend_alpha` + event bindings). Still the widest UI surface even after the builders split out — most panels pull at least a toast/tooltip/binding. Keep new helpers focused. |
| 17 | `ui_headers`, `window_position` | Dialog/app headers + tip bar — pulled by every dialog/panel that draws a CRT header; `window_position` (geometry persistence + `fit_window_height`) by the same dialogs. |
| 16 | `profile_document` | The profile section contract ← `app.py` (registry wiring), `grid_model` + `overlay` + `live_tracker_settings` + `deeps_settings` + `stopwatch` + `inspect` + `cast_timer` + `console` + `onslaught` + `damageinfo_settings` (two sections — `damage_numbers` BUILD, `damage_colors` sparse PATCH) + `buff_xml` (`buff_bars`, sparse PATCH), `profile_library` (the gate), `profile_io`, and `build_signature` consumers — `build_action` (records `last_build` on success) + `grids_panel` (status row). Infrastructure on the cluster-isolation list; imports only `settings_core`. |
| 15 | `overlay_size` | The size model's pure arithmetic (`panel_fs`/`cast_fs`/`grid_metrics`, `scale_from`/`snap_scale`) ← the six modules that own a `scale` (`grid_model`, `stopwatch`, `inspect`, `cast_timer`, `console`, `onslaught`), their Extras dialogs and the grid card and Grid Settings dialog (the hints), `ui_forms` (the slider's bounds) and `grids_generator`, which bakes the results — so a rounding rule moves the baked value and its hint together. |
| 14 | `grid_model` | Grid dataclasses + the fraction↔px projection (`project_px`/`unproject_px`, `get_game_resolution_or_default`) and the overhead/band rules (`is_plate`/`is_band`/`max_slots`/`slot_count`) — pulled by every grid-editing surface plus the extras dialogs (projected-px position fields), `build_action`, `grids_generator` and `profile_io`. Pure data, stable surface. |
| 13 | `ui_tk_style` | Raw-tk styling + the dark-titlebar patch, pulled by every dialog that builds one. |
| 11 | `ui_forms` | Form fields + shared settings-panel builders (card/status-block/slider-row/toggle, `size_slider`) — every Extras dialog and the config panels, plus the Grid Settings dialog (`position_entry`, `size_slider`). |
| 11 | `settings_manager` | `get_setting`/`set_setting` proxy + the atomic temp+rename writers (`safe_save_json`/`safe_write_text`) — pulled by the settings engine, profile/delta I/O, and the panels that persist prefs or write Customized skin files. |
|  9 | `overlay` | The `overlay` section (`{size, font}`) + `SIZE_CHOICES`/`FONT_CHOICES`/`size_for_height`/`as2_face` ← `app.py` (registers the section), `grids_panel` (toolbar dropdowns), `grid_editor_panel`, `first_launch`, `profile_library` (seed size), `grids_generator` (bakes size + face), `damageinfo_generator`/`damageinfo_panel` and `swf_font` (`HYBORIAN`, `font_label`). |
|  6 | `prefs`, `ui_components` | `prefs` ← `app.py` (builds the `Store` on `PREFS_SCHEMA`), `grids_generator` (the overhead anchor defaults), `grids_panel` (build-status anchor compare), `game_resolution` (anchor bounds), `damageinfo_colors_panel` + `buff_display_editor` (both call `record_last_patch()` from their Apply — see the `last_patch` note above). `ui_components`: stateful composites (toasts, drag-reorder, scrolling). |
|  5 | `build_utils`, `console`, `onslaught`, `paths` | `build_utils`: build-cluster leaf — `compile_as2`/`CREATE_NO_WINDOW` ← `build_executor`, `game_persistence`, `grids_generator`, `damageinfo_generator`, `self_update`. `console` / `onslaught`: the pure section + gate (`ships`) layers ← `app.py` (register their `PROFILE_SECTION`s), `build_action`, `extras_shortcuts` (the cards read `ships`, not `enabled`), `grids_generator` and their own dialog (`console_panel` / `onslaught_panel`). `paths` is imported directly by `app.py`, `build_utils`, `deeps_parsers`, `userdata` and `__main__` (everyone else gets paths via the `app` object). |
|  4 | `app_popups`, `cast_timer`, `classes`, `overlay_engine`, `swf_font`, `update_check`, `live_tracker_settings` | Narrow surface — ripple is contained. `update_check` ← `update_orchestrator` (`fetch_release`), `app_popups` (About ▸ Check for updates), `content_update` (`_parts`), `self_update` (`release_tag`). `overlay_engine` feeds both overlays + both settings adapters; `app_popups` feeds `app.py`, `build_action`, `first_launch`, `build_loading` (popup chrome + the three popups). `cast_timer` is the pure config layer ← `app.py` (registers its `PROFILE_SECTION`), `grids_generator`, `cast_timer_panel`, and `build_action` (which validates the profile section before handing it to the build as `cast_config`). `classes` (the twelve class ids) ← `grid_model` (a grid's `class`), `grid_editor_panel` (the Move/Copy menu), `grids_panel` (the tab strip) and `prefs` (the `grids_tab` check). `swf_font` (pure byte surgery on SWF font tags) ← `grids_generator` (`splice`/`import_game_font`) and `damageinfo_generator` (`set_damage_font`), with `damageinfo_settings`/`damageinfo_panel` reading `DN_FONTS`/`dn_scale`. |
|  3 | `grid_preview`, `game_persistence`, `grids_generator`, `inspect`, `inspect_catalog`, `stopwatch`, `update_orchestrator` | Cluster leaves. `grid_preview` ← `grid_preview_canvas` (the card's drawing), `grid_editor_panel` (summary / names text, slot reads) and `grids_panel` (the empty-state preset cards). `update_orchestrator` ← `app.py` (launch check, `finish_startup`, Check for updates now), `first_launch` (post-dialog check), `app_popups` (About's hit → `start_install`). `game_persistence` ← `build_executor`, `build_action`, `game_folder` — the game-folder layer of the build cluster; changing a marker, a target path or a constant there is felt by all three. `grids_generator` ← `build_action`, `build_executor`, `grids_panel` (`free_id`). `stopwatch` and `inspect` are the pure config layers ← `grids_generator`, `app.py` (registers their `PROFILE_SECTION`s), and their own Extras dialog (`stopwatch_panel` / `inspect_panel`); `inspect_catalog` is the stat catalog (rows, ids, formatter fields, `PVP_VIEW`, `ALIASES`) ← `inspect` (key resolution), `inspect_panel` (the picker) and `grids_generator` (bakes `d.INS.groups/rows/watch/pvp`). |
|  2 | `build_executor`, `self_update`, `profile_io`, `profile_library`, `grid_dialogs` | Build-cluster leaf / low-blast modules. `self_update` ← `update_orchestrator` (stage / spawn / startup marker) and `__main__` (`--apply-update` dispatch, startup retry). `profile_io` ← `app.py` (delegators + startup) and `settings_backup` (`release_store` before a restore, `startup_profile` after one reopens the restored library). `profile_library` ← `app.py` (constructs the `ProfileLibrary`) and `profile_io` (`file_mtime`/`slugify`/`SEED_NAME` for listing, dedup and template naming). |
|  1 | `grids_panel`, `grid_preview_canvas`, `grid_settings_dialog`, `ui_collapsible`, `custom_menu_bar`, `profile_store`, `game_folder`, `game_resolution`, `build_action`, `build_loading`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `boss_timer`, `timer_overlay`, `combat_monitor`, `settings_backup`, `stopwatch_panel`, `inspect_panel`, `cast_timer_panel`, `console_panel`, `onslaught_panel`, `extras_shortcuts`, `foreground`, `focus_watcher` | Each consumed by exactly one parent — low blast radius by design. (`grid_preview_canvas` and `grid_settings_dialog` ← `grid_editor_panel`; `ui_collapsible` ← `buff_display_editor`; `foreground` ← `focus_watcher`; `focus_watcher` ← `app.py`; `build_loading` ← `build_action`; `profile_store` ← `profile_io`; `extras_shortcuts` ← `grids_panel` — each card's switch flips one of the six SWF-extra gates via `app.profile_store.update_section` (autosaved), while a click on the card body calls that feature's `app._open_*` opener by name (`getattr`, no import edge); the six Extras dialogs push `refresh_extras_shortcuts()` back after Apply, and `profile_io.apply_document` resyncs the cards on every profile switch.) |

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
  - Settings read/write → declare a `Schema` of `Field`s and route load/save/validate through `settings_core` (atomic, strict, migration-ready); the `settings_manager` `get_setting`/`set_setting` proxy stays for app-global prefs. A `Schema` may also validate a document slice that owns no file (declare with `filename=''`; `validate_patch()` covers sparse-override slices where absent keys mean "no opinion"). Don't re-introduce UI-layer state or hand-roll JSON I/O.
  - Root-window logic (new menu action, new app-state flow) → extract to a new `src/kazbars/<concern>.py` taking `app` as first arg, add a one-line delegator on `KazBarsApp` if it has internal callers. Don't grow `src/kazbars/app.py`.
- **Cluster isolation:** the Live Tracker cluster AND the Deeps cluster each must not be imported from outside themselves (except `app.py`), and their members must not import other panels (cluster + shared infrastructure only). The two clusters also must not cross-import each other. Shared infrastructure now includes `settings_core` (both clusters' settings modules delegate to the engine), `profile_document` (the profile section contract — cluster settings modules export a `PROFILE_SECTION` through it; it imports only `settings_core`), `overlay_engine`, `foreground`, and `focus_watcher` (both clusters reach the overlay + focus layer through these, never through each other). Enforced by `tests/test_cluster_isolation.py` (parametrised over both).
- **Toasts:** every toast goes through `app_toast(widget, message, style, duration=, key=, on_click=)` in `ui_widgets`. The walker resolves `.toast` from the widget's ancestry, so callers don't need a direct `ToastManager` reference. Omit `duration` for the per-severity default (`ToastModel.DEFAULT_DURATIONS`: info/success 4 s, warning 6 s, danger/error 8 s); pass seconds only when the message earns a longer read. At most 3 toasts show at once — extras queue FIFO, with warning/danger jumping queued info/success (a visible toast is never displaced). Hover pauses the dismiss timer; click runs `on_click` (if set) then dismisses. Pass `key=` for any emitter that can fire repeatedly in a short burst (spinbox auto-repeat is the canonical case) — same key replaces the live toast in place instead of stacking. Don't reintroduce `obj.toast.show(...)` direct calls — they bypass the walker, fragment defaults, and force a `toast=` constructor seam.
- **Type-check gate (mypy):** the gate is the **Tk-free logic core** — the modules that import neither `tkinter` nor `ttkbootstrap` — listed explicitly in `[tool.mypy] files` in `pyproject.toml`. Bare `mypy` (CI's *blocking* step) checks exactly that set, which must stay clean; a regression there fails CI. The full repo (`mypy src/kazbars`) runs **advisory-only** (`continue-on-error: true`) because ttkbootstrap's runtime `bootstyle` kwargs + dynamic widget typing emit 97 errors mypy can't resolve. When you add a module that imports neither Tk lib, add it to the `files` list to fold it into the gate; a Tk-touching module stays out (advisory-only) by design. The gate is includes-based on purpose, and `tests/test_mypy_gate.py` keeps the list in lockstep with reality: a new Tk-free module that isn't listed (or a gated module that grows a Tk import) fails pytest, so the list can't silently drift.

## Smoke tests

Plain-Python pytest cases guard the failure modes we’ve actually hit. Per-test detail lives in [`inventory-roles.md`](inventory-roles.md) — one description per test file; don’t duplicate it here. Two conventions worth knowing up front: `tests/test_imports.py` auto-discovers every `src/kazbars/*.py` module (add nothing when a new module lands), and `tests/test_docs_in_sync.py` guards `docs/inventory.md`, `docs/flows.md`, `docs/database-changelog.md`'s buff total, and the CHANGELOG's release sections (inventory completeness, exact line counts, function-anchored refs, tag↔section parity).

Run before every commit touching code or data:
```bash
pytest tests/
```

UI behavior (Tk event flow, dialog timing, subprocess integration in the build flow) is not covered by the smoke tests — rely on manual smoke-testing for those.

