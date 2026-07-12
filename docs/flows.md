# Flows

## Conventions

Steps reference code as `` `function_name()` — src/kazbars/<module>.py `` — the backticked callable plus the file it lives in, **never** a line number. Line numbers rot on nearly every edit; function names survive refactors and are machine-checked: `tests/test_docs_in_sync.py` parses every step line, resolves each subject callable against the referenced file's AST, and fails CI on a rename or a reintroduced `:N` suffix.

When a flow crosses a dialog→app boundary (any modal `Toplevel` whose buttons or `WM_DELETE_WINDOW` callbacks invoke app methods), name the dialog-side dispatcher as an explicit step. Eliding it folds dialog-internal and app-internal responsibilities into one gloss and produces caller/callee confusion. Confirmed examples in this doc: Flow 4 step 3 (`AddGridWizard.on_create`), Flow 5 step 6 (`BuffSelectorDialog.on_ok`), Flow 13 step 5 (`start_empty`).

---

## 1. build and install SWF

Trigger: User clicks "Build & Install" button in the bottom bar or presses Ctrl+B

Steps:
1. `KazBarsApp._build()` — src/kazbars/app.py — one-line delegator to `build_action.build(self)`
2. `build_action.build()` — src/kazbars/build_action.py — checks `_building` re-entry guard; validates game folder, compiler path, grids list, total slot count; flags grids that would render empty (no whitelist or no static slot assignments); blocks build if Aoc.exe mode and an AoC game process is running
3. `get_profile_data()` — src/kazbars/grids_panel.py — calls `save_settings()` then returns `self.grids`
4. `save_settings()` — src/kazbars/grids_panel.py — iterates all `GridEditorPanel` instances, calling `save_to_config()` on each
5. `save_to_config()` — src/kazbars/grid_editor_panel.py — reads every spinbox/combobox/toggle value and writes it into the grid config dict
6. `find_compiler()` — src/kazbars/build_utils.py — checks three candidate paths for `mtasc.exe`; returns `Path` or `None`
7. `profile_io.do_save_profile(silent=True)` — src/kazbars/profile_io.py — auto-saves the current profile (if one is loaded) before the build locks. `silent=True` suppresses the post-save "Saved: …" toast + status flash so they don't pile up against the "Built — …" toast a few steps later
8. `_build_worker()` — src/kazbars/build_action.py — build locks (`app._building = True`, build button disabled, Ctrl+B unbound), snapshots the Tk-thread inputs into a `ctx` dict, and spawns this daemon worker so the compile + install run off the UI thread (mirrors `content_update`'s thread + `app.after(0, …)` marshalling — the loading animation never freezes). Steps 9–16 run on the worker; each phase label is posted back to the main loop and held at least `PHASE_MIN_MS` by `_hold_phase()` so it reads as a beat rather than a flash
9. `compile_to_staging()` — src/kazbars/build_executor.py — creates a `tempfile.mkdtemp` staging dir and calls `build_grids()`; returns `(staging_dir, (success, message))`. Forwards `include_console` (read by `build_action` from `settings['build_console']`, default `False`), `cast_config` (read by `build_action` from `grids_panel.get_cast_timer_config()`), and `stopwatch_config` (read by `build_action` from `settings['stopwatch']`, validated downstream) to `build_grids`
10. `build_grids()` — src/kazbars/grids_generator.py — instantiates `CodeGenerator(..., include_console=include_console, cast_config=cast_config)`, writes `KazBars.as` and `KazBarsData.as` to a second temp dir, copies `base.swf`, calls `compile_as2()`
11. `CodeGenerator.generate()` — src/kazbars/grids_generator.py — returns `(KazBars.as, KazBarsData.as)` source strings; calls `_resolve_grid()` per grid to expand primary IDs; emits `d.CUSTOMICON` entries for null-icon buffs. The three optional features gate their codegen here — `include_console`, `include_cast_timer` (via `cast_timer.is_enabled`), and `include_stopwatch` (via `stopwatch.validate_config`) each toggle their declarations, template placeholders, and `KazBarsData` block, so a disabled feature leaves zero references and MTASC skips its stub class entirely (per-feature detail: architecture.md → Build pipeline)
12. `compile_as2()` — src/kazbars/build_utils.py — assembles MTASC command with classpaths, runs subprocess, returns `(bool, stderr)`
13. **(Damage Numbers — only when enabled)** `damageinfo_generator.build_damageinfo()` — src/kazbars/damageinfo_generator.py — `build_action` loads `damageinfo_settings` up front (validating the assets exist in the pre-build checks); if `enabled`, after the grids compile it bakes the offset settings into the lean AS2 tree and MTASC-injects a copy of the pristine `DamageInfo.swf` to `staging/DamageInfo.swf` (`loading.advance_step("Baking damage numbers...")`). A bake/compile failure aborts before any install — both SWFs are staged before deploy, so nothing is partially installed. Disabled ⇒ `damageinfo_swf` stays `None`
14. `install_to_client(..., damageinfo_swf=..., damageinfo_pristine=..., group_resources=..., split_incoming=...)` — src/kazbars/build_executor.py — calls `cleanup_legacy_files()`; `_prepare_damageinfo()` and `_prepare_textcolors()` stage the two game-file changes to `.kaztmp` files (the slow copy/compute), then the caller commits them back-to-back with `os.replace` (the only lock-prone step) before copying `KazBars.swf` to `Data/Gui/Default/Flash/`, so a running-client file lock leaves the grids untouched. `_prepare_damageinfo()` stages the modded `DamageInfo.swf` install (capturing a one-time stock backup at `DamageInfo.swf.kazbars.bak` — seeded from the live file only when it is byte-identical to the bundled pristine stock, otherwise from the bundled pristine itself, so the backup can never capture a mod) or, when `damageinfo_swf` is `None`, a restore of stock from that backup; `_prepare_textcolors()` stages a **surgical** direction edit to the skin's `Customized/TextColors.xml` (created from the Default copy when absent): it flips the resource-loss directions per `group_resources` (the "Group my resource numbers" toggle) and the incoming/self damage+heal directions per `split_incoming` (the "Separate resources into Column B" toggle) — both AND-ed with the master enable in `build_action`, on→−1 / off→1 — touching only `direction` attributes and never colors (the color editor owns those, Flow 21); a pre-existing skin file is backed up once to `.kazbars.bak`, and with both toggles off and no Customized file there's nothing to write; calls `write_xml_add_files()` in Aoc mode; calls `create_scripts()`
15. `create_scripts()` — src/kazbars/build_executor.py — writes `reloadgrids` and `unloadgrids`; in non-Aoc mode calls `update_script_with_marker()` to add the auto-load entry; in Aoc mode strips any old KazBars/KazBars markers from `auto_login` instead (Aoc.exe loads via xml.add)
16. `update_script_with_marker()` — src/kazbars/build_utils.py — strips old KazBars marker block (and any listed legacy markers) from `auto_login`, then appends fresh block
17. Success toast (one of three, success-styled, 8 s) — src/kazbars/build_action.py — `"/reloadui in-game"` (Aoc + game running), `"launch the game"` (Aoc + not running), or `"/reloadui + /reloadgrids"` (standard launcher). The success color and the build-loading screen carry the "it worked" signal; the toast is reduced to the next-action line
18. `notify_build_done(use_aoc_bypass, app.current_profile)` — src/kazbars/grids_panel.py — re-shows the in-panel tip guide with step 4 marked complete and writes a SHA-1 signature of `{profile_path, grids}` to `settings['last_build_signature']`. The path is part of the signature so cross-profile loads can't false-match. Step 4 un-ticks again the moment any subsequent edit fires `_mark_modified` (grids_panel.py); on relaunch, `load_profile_data` recomputes the signature against the loaded profile and restores step 4 only when both profile identity and grids hash match
19. `_unlock()` — src/kazbars/build_action.py — runs on the main thread from `_finish_success` / `_finish_failure` / `_build_error`: cleans up the staging dir via `shutil.rmtree`, releases the `_building` flag, re-binds Ctrl+B, syncs build button state

End state: `KazBars.swf` installed under the game folder; `Scripts/reloadgrids` and `Scripts/unloadgrids` written; in non-Aoc mode `Scripts/auto_login` updated; in Aoc mode `Data/Gui/Aoc/KazBars/MainPrefs.xml.add` and `Modules.xml.add` written; when Damage Numbers is enabled the modded `DamageInfo.swf` is installed (stock backed up to `DamageInfo.swf.kazbars.bak`), and when disabled any prior mod is reverted from that backup; with "Group my resource numbers" / "Separate resources into Column B" on, the skin's `Customized/TextColors.xml` has the resource-loss and/or incoming/self `direction` attributes flipped in place (flipped back to stock when off), leaving any per-source colors set via Flow 21 untouched; build loading screen shows the result summary

---

## 2. load profile from file

Trigger: User selects File > Open profile... (or presses Ctrl+O) and confirms a `.json` path

Steps:
1. `KazBarsApp._open_profile()` — src/kazbars/app.py — one-line delegator to `profile_io.open_profile(self)`
2. `profile_io.open_profile()` — src/kazbars/profile_io.py — runs the unsaved-changes guard via `_check_unsaved_changes()`; opens `filedialog.askopenfilename`; composes `read_profile_file()` + `apply_profile_data()`
3. `profile_io.read_profile_file()` + `apply_profile_data()` — src/kazbars/profile_io.py — split as of 2026-04-27 to make the boss-timer fan-out visible at every call site. `read_profile_file` is pure I/O (returns `(data, is_corrupt)`); `apply_profile_data` dispatches grids, missing-buff warning, boss-timer (when alive), reference_resolution, current_profile, settings, title. See step 8 for the boss-timer dispatch detail.
4. `load_profile_data(grids, profile_path)` — src/kazbars/grids_panel.py — iterates raw grid dicts; migrates, validates, rebuilds panel list; restores `_build_done` from `settings['last_build_signature']` when both the profile path and grids hash match; returns `{grid_name: [missing_refs]}` for buffs that couldn't be resolved
5. `_migrate_grid()` — src/kazbars/grids_panel.py — normalizes legacy `int` IDs and legacy name strings in `whitelist` and `slotAssignments` to current primary spell IDs via `database.by_id` and `database.get_entry_by_name`
6. `validate_grid()` — src/kazbars/grid_model.py — fills missing keys from `create_default_grid()`; clamps every numeric field against `CLAMP_SPECS`; coerces enums in `ENUM_SPECS`; coerces booleans and lists/dicts
7. `refresh_panels()` — src/kazbars/grids_panel.py — destroys existing `GridEditorPanel` widgets; creates new ones for the validated list; shows empty state if list is empty
8. If a Boss Timer panel is alive, `LiveTrackerPanel.load_profile_data()` — src/kazbars/live_tracker_panel.py — applies the embedded `boss_timer.overlay` settings to the overlay (`apply_settings` then propagates opacity, font, transparent, lock, x/y/width/height, and visible state through `set_*(..., notify=False)` calls, with a single `_notify_settings_changed()` at the end so the parent saves once)
9. `warn_missing_buffs()` — src/kazbars/profile_io.py — if migration dropped any references, displays them (deferred 200ms when called during startup so the dialog doesn't race the welcome popup)
10. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` to `userdata/prefs.json` (`Store.save` → `settings_core.save` → atomic temp-rename in `safe_save_json`)

End state: `GridsPanel` displays validated grid cards; `app.modified` is `False`; `last_profile` updated in settings; window title reflects loaded name

---

## 3. save profile to file

Trigger: User selects File > Save profile (Ctrl+S) or File > Save profile as...

Steps:
1. `KazBarsApp._save_profile()` — src/kazbars/app.py — one-line delegator to `profile_io.save_profile(self)`
2. `profile_io.save_profile()` — src/kazbars/profile_io.py — routes to `do_save_profile(app, current_path)` if a path exists, or to `save_profile_as()` otherwise
3. `profile_io.do_save_profile(silent=False)` — src/kazbars/profile_io.py — orchestrator: `build_profile_payload()` → `write_profile_file()` → `_commit_saved_profile(silent=silent)`, with try/except for `OSError`. The `silent` flag (default `False` for direct save; `True` for the pre-build piggyback save in Flow 1) suppresses the post-commit toast + status flash. Note: the `boss_timer` key is pulled from the live tracker (when one is open) inside `build_profile_payload()` (src/kazbars/profile_io.py) — see step 7.
4. `get_profile_data()` — src/kazbars/grids_panel.py — calls `save_settings()` then returns `self.grids`
5. `save_settings()` — src/kazbars/grids_panel.py — iterates all `GridEditorPanel` instances calling `save_to_config()`
6. `save_to_config()` — src/kazbars/grid_editor_panel.py — reads all widget values into the grid config dict
7. If a Boss Timer panel is alive, `LiveTrackerPanel.get_profile_data()` — src/kazbars/live_tracker_panel.py — returns `{'overlay': {...}}` for embedding
8. `safe_save_json()` — src/kazbars/settings_manager.py — writes JSON to `path.tmp` then `Path.replace`-renames it over the target atomically
9. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` to `userdata/prefs.json`

End state: profile `.json` written atomically; `app.modified` is `False`; title bar reflects saved name; toast `Saved: <filename>` shown and status bar pulses (both suppressed when `silent=True`, e.g. the pre-build auto-save path)

---

## 4. add new grid via wizard

Trigger: User clicks "+ Add Grid" button on the grids panel toolbar (also reachable from the empty-state "Custom" preset card)

Steps:
1. `add_grid()` — src/kazbars/grids_panel.py — checks the slot budget against `MAX_TOTAL_SLOTS` (64); opens `AddGridWizard` dialog
2. `AddGridWizard.__init__()` — src/kazbars/grid_dialogs.py — builds wizard UI with name, source/mode/dimension fields and four preset shape buttons; calls `restore_window_position()`
3. `AddGridWizard.on_create()` — src/kazbars/grid_dialogs.py — validates name (non-empty, unique), enforces slot budget; calls `create_default_grid()`
4. `create_default_grid()` — src/kazbars/grid_model.py — returns a complete grid config dict populated with caller-specified `grid_type`, `rows`, `cols`, `mode`, `grid_id`; auto-coerces `1×1` to static mode and picks a sensible `fillDirection`
5. `refresh_panels()` — src/kazbars/grids_panel.py — destroys and recreates all `GridEditorPanel` cards; the newly added card is initially expanded

End state: new grid config appended to `self.grids`; new `GridEditorPanel` card visible and expanded; slot count label updated; profile marked modified

---

## 5. select tracked buffs for a dynamic grid

Trigger: User clicks "Tracked Buffs..." on a dynamic-mode `GridEditorPanel` (the same button shows "Slot Assignments" in static mode and routes to a different dialog)

Steps:
1. `_on_mode_btn_click()` — src/kazbars/grid_editor_panel.py — dispatches to `edit_whitelist()` when grid is in dynamic mode (or `edit_slots()` for static)
2. `edit_whitelist()` — src/kazbars/grid_editor_panel.py — flushes current widget state via `save_to_config()`; opens `BuffSelectorDialog`
3. `BuffSelectorDialog.__init__()` — src/kazbars/grid_dialogs.py — resolves initial `whitelist` primary IDs to entry names via `database.by_id`; restores last-used category/type filter from settings; calls `refresh_lists()`
4. `BuffDatabase.search()` — src/kazbars/buff_database.py — filters `grouped_buffs` by query/category/type; sorts by type then name
5. `BuffSelectorDialog.refresh_lists()` — src/kazbars/grid_dialogs.py — repopulates Available and Selected listboxes; per-row foreground tinted by buff type (`THEME_COLORS['type_debuff']`/`type_misc`) to mirror the Database editor; selected entries sort by type when the grid `layout` is `buffFirst` or `debuffFirst`, alphabetically when `mixed`
6. `BuffSelectorDialog.on_ok()` — src/kazbars/grid_dialogs.py — saves filter state; maps each selected name back to `entry['ids'][0]` via `database.get_entry_by_name()`; sets `self.result`
7. `update_labels()` — src/kazbars/grid_editor_panel.py — refreshes whitelist count and buff-name preview text in card header

End state: `grid_config['whitelist']` updated with new primary spell ID list; panel header shows new buff count and preview names

---

## 6. first-launch setup with defaults

Trigger: `KazBarsApp.__init__` has just created `userdata/` fresh via `ensure_layout()` and built `self.settings = Store(PREFS_SCHEMA, userdata_root())`; the new `prefs.json` has no `game_path`, so first launch is scheduled 100ms after `deiconify()`

Steps:
1. `_show_first_launch_dialog()` — src/kazbars/app.py — one-line delegator to `run_first_launch(self, APP_NAME)`
2. `run_first_launch()` — src/kazbars/first_launch.py — defines the `on_game_set`, `on_aoc_bypass_set`, `on_load_default`, `on_resolution_set`, `on_dialog_closed` closures; calls `show_first_launch_dialog()`
3. `show_first_launch_dialog()` — src/kazbars/first_launch.py — builds modal dialog with game folder entry, common-paths shortcuts, an Aoc.exe Yes/No section (revealed on demand), resolution picker, and two option cards ("Use Defaults" / "Start Empty")
4. `detect_aoc_launcher()` — src/kazbars/build_executor.py — called whenever the path entry changes; checks for `aoc.exe` or `Aoc.log` under `Data/Gui/Aoc/`; reveals the Aoc.exe radio group if found
5. `on_load_default()` — src/kazbars/first_launch.py — closure: persists game path, Aoc.exe preference, and resolution **before** loading the profile so the auto-scale inside `apply_profile_data()` reads the just-saved `game_resolution`; composes `read_profile_file()` + `apply_profile_data()` against `Default.json`; saves a personal copy as `profiles/MyGrids.json` (auto-incremented on collision); stashes data for the welcome popup
6. `profile_io.read_profile_file()` + `apply_profile_data()` — src/kazbars/profile_io.py — reads `Default.json` (pure I/O), then dispatches grids to `grids_panel.load_profile_data()`, populates `app.reference_resolution` from the JSON, **auto-scales via `grids_panel.scale_to_resolution()` if the profile's reference differs from `game_resolution`**, anchors `current_profile` to None for the bundled default
7. `GridsPanel.scale_to_resolution()` — src/kazbars/grids_panel.py — anchor-based scaling (X center-anchored, Y bottom-anchored) via `grid_model.scale_grid_position()`; clamps to `SCREEN_MAX_X`/`SCREEN_MAX_Y` (8K sanity caps) and floors at 0; calls `refresh_panels()`
8. `profile_io.do_save_profile()` — src/kazbars/profile_io.py — writes scaled profile to `profiles/MyGrids.json`
9. `on_dialog_closed()` — src/kazbars/first_launch.py — closure called when the dialog is destroyed; if the user took the defaults path, schedules `show_welcome_popup()` 100ms later

End state: `game_path`, `use_aoc_bypass`, and `game_resolution` persisted; default profile loaded, anchor-scaled to resolution, saved as `profiles/MyGrids.json`; welcome popup shown after the dialog closes

---

## 7. save buff database

Trigger: User clicks the "Save Database" button in the Database view's toolbar (no menu item, no keyboard shortcut — Ctrl+S is bound to profile save)

Steps:
1. `DatabaseEditorTab.save()` — src/kazbars/database_editor.py — computes a delta of the in-memory effective DB against the stock←content floor via `buff_db_layers.compute_delta(self._floor_buffs, self.database.buffs)`: user adds + edits-of-a-built-in (overrides) land in `buffs`; built-ins the user hid (floor buffs now missing from the effective list) become tombstoned `ids[0]` in `deleted`.
2. `DeltaStore.save(delta)` — src/kazbars/buff_db_layers.py — writes `{version: 2, buffs, deleted}` to `userdata/database_user.json` atomically via `safe_save_json`. The shipped `assets/kazbars/Database.json` is **never** written.

End state: `userdata/database_user.json` holds the user's adds/overrides/tombstones; `DatabaseEditorTab.modified` → `False`; toast summarizes (`Saved: N custom buffs, M hidden built-ins`). On next launch `load_layers` re-merges the deltas over the shipped stock so they reappear.

---

## 8. add buff to database

Trigger: User clicks "Add" in the `DatabaseEditorTab` toolbar (Database view)

Steps:
1. `DatabaseEditorTab.add_buff()` — src/kazbars/database_editor.py — builds the validator via `_make_buff_validator()` (no args for add: checks ID collision and name uniqueness against the full DB); opens `BuffEditDialog`
2. `BuffEditDialog.__init__()` — src/kazbars/database_editor.py — builds form with name, IDs (multi-line), category combobox, type radio group, and the stacking section (toggle + partial + start/end spinboxes); calls validator on submit
3. `BuffDatabase.add_buff()` — src/kazbars/buff_database.py — appends the new entry dict to `self.buffs`; calls `_rebuild_indexes()`
4. `BuffDatabase._rebuild_indexes()` — src/kazbars/buff_database.py — rebuilds `by_id`, `by_name`, `categories`, `grouped_buffs` from the full `buffs` list
5. `DatabaseEditorTab._after_db_change()` — src/kazbars/database_editor.py — post-mutation hook: marks the editor dirty, refreshes the category dropdown, and redraws the tree via `refresh_list()` (used uniformly by add/edit/delete/import/rename-category)

End state: new buff entry visible in treeview, badged "Yours" in the Source column; `by_id` and `by_name` indexes updated; toast `Added: <name>` shown; `DatabaseEditorTab.modified` set to `True`. On Save Database it is persisted as a user delta in `userdata/database_user.json` (Flow 7), never to assets.

---

## 9. uninstall from game folder

Trigger: User selects Game > Uninstall from game client... and confirms the dialog

Steps:
1. `KazBarsApp._uninstall_game()` — src/kazbars/app.py — one-line delegator to `game_folder.uninstall_game(self)`
2. `game_folder.uninstall_game()` — src/kazbars/game_folder.py — guards on `app.game_path`; confirms with the user; calls `uninstall_from_client()`
3. `uninstall_from_client()` — src/kazbars/build_executor.py — deletes `Data/Gui/Default/Flash/KazBars.swf`, the `Data/Gui/Aoc/KazBars/` directory (if present), and `Scripts/reloadgrids` + `Scripts/unloadgrids`; strips the auto-load marker block from `Scripts/auto_login`; if a `DamageInfo.swf.kazbars.bak` exists (Damage Numbers was installed), restores the stock `DamageInfo.swf` from it and removes the backup; if the backup is missing but a modded `DamageInfo.swf` remains, restores stock from the bundled pristine copy instead so uninstall never leaves a modded core file; in the skin's `TextColors.xml` it flips any resource-loss / incoming-self `direction` attributes back to stock (`1`) surgically, leaving per-source colors (user content, Flow 21) and the `.kazbars.bak` in place
4. `strip_marker_block()` — src/kazbars/build_utils.py — removes the `# KazBars auto-load` marker-delimited section (marker line through the next blank line) from the `auto_login` file content; the script is rewritten or, if empty after the strip, deleted

End state: `KazBars.swf`, the Aoc xml.add module folder, the reload scripts, and the auto-load marker block are all removed; any modded `DamageInfo.swf` and flipped `TextColors.xml` directions are reverted to stock (per-source colors kept); toast lists what was removed (or notes nothing was installed)

---

## 10. open live tracker panel

Trigger: User clicks the "⏱ Ethram-Fal" button in the bottom bar (right side, next to Build & Install)

Steps:
1. `_open_boss_timer()` — src/kazbars/app.py — checks `_boss_timer_if_alive()`; if a panel exists, deiconifies/lifts/restores the overlay; otherwise constructs a new `LiveTrackerPanel`
2. `LiveTrackerPanel.__init__()` — src/kazbars/live_tracker_panel.py — sets `transient(parent)`; restores window position under the `live_tracker` key (a sub-key of the single `window_positions` prefs dict); calls `load_settings()`; builds UI; creates overlay and **registers it with the app's `ForegroundWatcher`** (the single shared focus gate, owned by `KazBarsApp`, that hides every overlay whenever neither KazBars nor AoC is foreground); constructs `BossTimer` and `CombatLogMonitor`; auto-detects log path
3. `load_settings()` — src/kazbars/live_tracker_settings.py — delegates to the `settings_core` engine (read → migration ladder → validate → fill) against the Live Tracker `Schema`; reads `live_tracker_settings.json` from the settings folder; returns a dict validated against `TIMERS_DEFAULTS`/`TIMERS_RANGES` (defaults on missing/corrupt — never raises)
4. `BossTimer.__init__()` — src/kazbars/boss_timer.py — initializes cycle state fields and `_last_phase = None` (the source-side dedupe cache); stores `LiveTrackerPanel._dispatch_overlay_update` (src/kazbars/live_tracker_panel.py) as `_update_callback` — that method hops cross-thread updates onto the Tk main loop via `self.after(0, partial(_apply_overlay_update, phase))` (src/kazbars/live_tracker_panel.py)
5. `CombatLogMonitor.__init__()` — src/kazbars/combat_monitor.py — initializes daemon thread state; stores the `boss_timer` reference
6. `TimerOverlay.__init__()` — src/kazbars/timer_overlay.py — builds an `OverlayConfig` from settings and constructs a `HudOverlay` (shared backdrop + lock dot + drag over `LayeredOverlay`); supplies `_render_content` (two text rows + cycle-timer dock; an 8-direction stroke keeps text legible) and `_measure` (font-derived auto-size — no resize handle). Hidden on open (Hide-on-Stop) — Start shows it
7. `LiveTrackerPanel._update_log_path()` — src/kazbars/live_tracker_panel.py — calls `combat_monitor.set_log_folder()` with the current game path; sets the overlay's waiting-state footer to the sanitized log name (`CombatLog_2152`)
8. `CombatLogMonitor.set_log_folder()` — src/kazbars/combat_monitor.py — finds latest `CombatLog*.txt` in the game folder; records file end position as `last_position`

End state: `LiveTrackerPanel` window visible; `TimerOverlay` hidden until Start (focus-gated by the app-owned `ForegroundWatcher` via `foreground.app_or_game_foreground()`, shared with the Deeps overlay); `CombatLogMonitor` ready with log folder set; panel shows monitor + sanitized log status

---

## 11. start combat log monitoring

Trigger: User clicks "Start Monitoring" button in `LiveTrackerPanel`

Steps:
1. `LiveTrackerPanel._start_monitoring()` — src/kazbars/live_tracker_panel.py — re-runs `_update_log_path()`; calls `combat_monitor.start_monitoring()` (needs only a game folder — it waits for a log if AoC hasn't created today's yet, so no "no log" bail); shows the overlay; disables Test Cycle so the two modes are mutually exclusive. Reached via the single Start↔Stop toggle (`_on_start_stop_click`)
2. `CombatLogMonitor.start_monitoring()` — src/kazbars/combat_monitor.py — sets `monitoring=True`; spawns the `CombatLogMonitor` daemon thread running `_monitor_loop()`
3. `BossTimer.push_waiting_state()` — src/kazbars/boss_timer.py — builds the idle phase dict via `_phase()`, caches it on `_last_phase`, and fires `_update_callback(phase)`
4. `LiveTrackerPanel._dispatch_overlay_update()` — src/kazbars/live_tracker_panel.py — named cross-thread dispatcher; queues `partial(_apply_overlay_update, phase)` on the Tk main loop via `self.after(0, ...)`. `_apply_overlay_update()` (src/kazbars/live_tracker_panel.py) calls `self.overlay.update_display(phase)` if the overlay still exists
5. `TimerOverlay.update_display()` — src/kazbars/timer_overlay.py — accepts the phase dict; short-circuits when it equals `_display_state`; otherwise stores it and calls `self._hud.request_paint()`. The shared `HudOverlay` repaints by invoking the overlay's `_render_content()` (src/kazbars/timer_overlay.py) — two text rows + cycle-timer dock drawn with an 8-direction stroke — sized by `_measure()` (src/kazbars/timer_overlay.py). (The old per-canvas `_redraw_text_canvas`/`_redraw_cycle_timer` split is gone since the `HudOverlay` port.)
6. `LiveTrackerPanel._start_game_loop()` — src/kazbars/live_tracker_panel.py — schedules `_run_game_tick()` (src/kazbars/live_tracker_panel.py) on a `GAME_TICK_MS` (50 ms) recurring `after()` cadence; each tick calls `boss_timer.update_display()` and re-schedules itself

End state: `CombatLogMonitor` daemon thread running; 50ms UI poll active; overlay displays "Waiting for Seed..."

---

## 12. combat log trigger detected

Trigger: `CombatLogMonitor` daemon thread reads a new log line containing "Viscous Seed", "Lotus Fixation", or "Syphon hits"

Steps:
1. `CombatLogMonitor._monitor_loop()` — src/kazbars/combat_monitor.py — polls the log every 100ms; checks every ~3s for a newer log file (auto-switches, dropping the stale one); waits (scanning) if no log exists yet; handles truncation/rotation; reads bytes since `last_position`; dispatches matching lines to `_process_line()`
2. `CombatLogMonitor._process_line()` — src/kazbars/combat_monitor.py — identifies trigger type (Syphon → `start_syphon`, Viscous Seed from Ethram-Fal → `start_cycle`, Lotus Fixation from Emerald Lotus → `update_fixation`); extracts player name (or "YOU") from the line text via `_extract_player()`
3. `BossTimer.start_cycle()` — src/kazbars/boss_timer.py — calls `_reset_cycle_state()` then sets `timer_active=True`; records `cycle_start_time` and `seed_player`; detects double-seed (P4) when called 5–12s after the previous seed for the same player
4. `BossTimer.update_display()` — src/kazbars/boss_timer.py — called from the 50 ms UI loop; calls `get_current_phase()`; compares the result to the cached `_last_phase` and short-circuits if equal (skips ~19 of every 20 ticks once the integer second is steady), otherwise fires `_update_callback(phase)` with the new dict
5. Overlay dispatch and repaint are identical to Flow 11 steps 4–5, except the painted content: per-row message colors with an 8-direction outline stroke, and `COLORS["default"]` for the cycle timer

End state: overlay displays the active seed/fixation/syphon phase with elapsed timer text updated on the next 50ms poll

---

## 13. first-launch setup with empty start

Trigger: User completes the first-launch dialog by clicking "Start Empty" instead of "Use Defaults"

Steps 1–4 are identical to Flow 6 (delegator → `run_first_launch()` → `show_first_launch_dialog()` → `detect_aoc_launcher()`).

Steps:
5. `start_empty()` — src/kazbars/first_launch.py — closure: calls `_set_game_if_provided()`, then `_close()`. No `on_load_default` invocation, so no profile load and no scale.
6. `_set_game_if_provided()` — src/kazbars/first_launch.py — same dispatcher used by Flow 6's `load_default()`; persists game path via `on_game_set`, Aoc.exe preference via `on_aoc_bypass_set`, resolution via `on_resolution_set`
7. `on_dialog_closed()` — src/kazbars/first_launch.py — runs as in Flow 6 but `welcome_data` was never populated, so the welcome popup is suppressed

End state: `game_path`, `use_aoc_bypass`, and `game_resolution` persisted; no profile loaded; no welcome popup; user lands on the empty `GridsPanel` empty-state

---

## 14. change game folder (with Aoc.exe reconcile)

Trigger: User selects Game > Change game folder... from the menu, OR left/right-clicks the path label in the bottom bar and picks "Change game folder..." from the context menu

Steps:
1. `KazBarsApp._show_game_context_menu()` — src/kazbars/app.py — one-line delegator to `game_folder.show_game_context_menu(self, event)`
2. `show_game_context_menu()` — src/kazbars/game_folder.py — pops `app._game_context_menu` at the event coordinates; both `<Button-1>` and `<Button-3>` route here
3. User picks "Change game folder..." → `KazBarsApp._change_game_folder()` — src/kazbars/app.py — one-line delegator to `game_folder.change_game_folder(self)`. (When triggered via Game menu the cascade invokes the same delegator directly, skipping steps 1-2.)
4. `change_game_folder()` — src/kazbars/game_folder.py — opens `filedialog.askdirectory`; validates AoC folder structure (warns if `Data/Gui/Default` is missing); warns if the resulting `KazBars.swf` path exceeds 240 characters
5. `save_game_path()` — src/kazbars/game_folder.py — persists `game_path` to settings; calls `grids_panel.notify_game_path_changed()` so the panel can refresh
6. **Reconcile (only when `resolved != previous`)**: `detect_aoc_launcher()` — src/kazbars/build_executor.py — checks for `aoc.exe` or `Aoc.log` under `Data/Gui/Aoc/`. Two state-divergence branches fire:
   - **Aoc.exe newly present** (`has_aoc=True, use_aoc_bypass=False`) → `prompt_aoc_bypass()` — src/kazbars/game_folder.py — modal yes/no; answer is persisted via `save_aoc_bypass()`
   - **Aoc.exe newly absent** (`has_aoc=False, use_aoc_bypass=True`) → `save_aoc_bypass(app, False)` (src/kazbars/game_folder.py) and `app_toast(app, "Aoc.exe not found in this folder — bypass mode disabled.", 'info', 8)`
7. `refresh_game_path_label()` — src/kazbars/game_folder.py — updates the path label text/tooltip and calls `update_build_state()` to re-enable or disable the Build button based on the new path's existence

End state: `game_path` and (when divergence triggered it) `use_aoc_bypass` persisted; path label updated; Build button state synced

---

## 15. open Buff Display editor and apply

Trigger: User selects Extras > Default buff bars… from the menu

Steps:
1. `KazBarsApp._open_buff_display_editor()` — src/kazbars/app.py — one-line delegator to `buff_display_editor.open_buff_display_editor(self)`
2. `open_buff_display_editor()` — src/kazbars/buff_display_editor.py — pre-flight: validates `app.game_path` is set and points to a real directory; on miss, shows a `Messagebox.show_warning` (the only modal in this module — toast can't render before the dialog exists) and returns
3. `BuffDisplayDialog.__init__()` — src/kazbars/buff_display_editor.py — `withdraw → transient → grab_set`; calls `_create_widgets()`; restores window position; binds `<Escape>` → `_on_cancel`, `<Return>` → `_on_apply`, `WM_DELETE_WINDOW` → `_on_close`; schedules `_set_initial_focus()` via `after_idle` so the toggle widget is fully realized
4. `_create_widgets()` — src/kazbars/buff_display_editor.py — packs CRT-styled header, plain-language subtitle, conditional custom-UI banner; **bottom button row packs first** (`side='bottom'`) so it reserves height before body claims expansion (Cancel + Apply stay visible at any window size); **scrollable body** wraps the section iteration via `create_scrollable_frame`; reads `SETTINGS_KEY_SECTION_OPEN` for per-section open/closed state
5. For each entry in `BUFF_FILES` (Player, Target, Top, Floating): `_Section.load()` — src/kazbars/buff_display_editor.py — resolves Customized→Default→None precedence via `_resolve_paths`; reads source XML and caches it on `self._source_text` for later reuse by `write_to_disk`; calls `_read_bufflistview()` (regex match on `<BuffListView ... />`, optionally inside a `<!--KZ_OFF ... KZ_OFF-->` wrapper); sets `state` to `STATE_OK / STATE_MISSING / STATE_UNSUPPORTED`; calls `_populate_vars()` which mirrors source byte-for-byte (blank field when attr is missing or unrecognised — no stock defaults)
6. `_Section.build(parent, initial_open)` — src/kazbars/buff_display_editor.py — builds a `CollapsibleSection` per entry with `initial_open` from saved settings (default: Player open, rest collapsed); badge label packs to `cs.header_frame` side='right' so status stays visible whether expanded or collapsed; form rows or inline state message (via `_render_inline_message`) pack into `cs.content`
7. User edits a field → spinbox `command=` or `<KeyRelease>` fires `_Section._on_change()` → snapshot guard early-returns when `_snapshot()` matches `_last_snapshot` (so non-mutating keystrokes do no work); on a real change: applies disabled-style, refreshes filter hint, refreshes badge, calls dialog's `_refresh_apply_state()` which only re-configures the Apply button when its enabled-state actually flips
8. User clicks Apply → `BuffDisplayDialog._on_apply()` — src/kazbars/buff_display_editor.py — collects sections where `dirty()` is True; for each: `write_to_disk()` then `load_after_write()`
9. `_Section.write_to_disk()` — src/kazbars/buff_display_editor.py — reuses `self._source_text` cached at load time (falls back to disk read if missing); builds attrs dict from form values via the `int_specs` table (only non-blank fields land in attrs; numerics clamped to `ICON_SIZE_MIN/MAX` etc. so a typed 999 can't reach the file); calls `_write_bufflistview()`
10. `_write_bufflistview()` — src/kazbars/buff_xml.py — unwraps any `KZ_OFF` span; for each attr in attrs dict: skips when on-disk value already equals new value (keeps file byte-identical for untouched fields); else `_replace_attr()` either replaces existing value or **injects before the closing `/>`** when the attr is missing (the source XML doesn't always carry every attr — most stock files have no `filter`); re-wraps in `KZ_OFF` if `enabled=False`
11. `_backup_once()` — src/kazbars/buff_xml.py — copies the existing Customized file to `*.kazbars.bak` once (idempotent — skips if backup already exists)
12. Customized file written via `Path.write_text` (parent dirs created)
13. `_Section.load_after_write()` — src/kazbars/buff_display_editor.py — flips `source_path` to the now-existing Customized file; re-reads, refreshes `_source_text`/`_baseline`/`_last_snapshot`, and updates the badge to `[Customized]`
14. Per-result toast via `app_toast`: success → `Saved: <names>` (`'success'`, default 6 s); failure → `Couldn't write <names>. Check folder permissions and disk space.` (`'danger'`, 10 s, `key='buff_apply_failed'` so retries coalesce); OS reasons go to the logger
15. User closes dialog (X button, Escape, Cancel, or any path that hits `WM_DELETE_WINDOW`) → `BuffDisplayDialog._on_close()` — src/kazbars/buff_display_editor.py — calls `_save_section_states()` (writes a per-label `is_open` dict to `settings[SETTINGS_KEY_SECTION_OPEN]`), then `destroy()`. Apply alone does not destroy the dialog — the user keeps editing.

End state: changed sections written to `<game>/Data/Gui/Customized/Views/HUD/<file>.xml` (Player → CharPortraitLeft.xml, Target → CharPortraitRight.xml, Top → HUDView.xml, Floating → FloatingPortraitView.xml) with surgical regex edits and one-shot backups; section open/closed state persisted to `userdata/prefs.json` (the `buff_display_section_open` field); user types `/reloadui` in-game to see the changes.

---

## 16. change game resolution

Trigger: User selects Game > Game resolution... from the menu

Steps:
1. `KazBarsApp._change_game_resolution()` — src/kazbars/app.py — one-line delegator to `game_resolution.change_game_resolution(self)`
2. `change_game_resolution()` — src/kazbars/game_resolution.py — reads current `game_resolution` setting via `get_game_resolution_or_default()`; builds a modal `Toplevel` with combobox of `["1920x1080", "2560x1440", "3840x2160"]` plus the OS-detected screen res prepended if not already in the list
3. User picks a value and clicks Apply → `_apply()` closure inside the dialog
4. `parse_resolution()` — src/kazbars/grid_model.py — converts the chosen `"WxH"` string into `(w, h)`; on parse failure the dialog just closes
5. **No-op short-circuit**: if `(new_w, new_h) == (current_w, current_h)`, dialog closes without scaling or persisting
6. `GridsPanel.scale_to_resolution()` — src/kazbars/grids_panel.py — anchor-scales every loaded grid's `x`/`y` from the previous game_resolution to the new one via `scale_grid_position()`; clamps to sanity caps; calls `refresh_panels()` so editor cards rebuild with the new spinbox max as well
7. `app.reference_resolution = [new_w, new_h]` and `app.settings.set('game_resolution', [new_w, new_h])` + save — establishes the new identity so the next profile load auto-scale is a no-op
8. `app.modified = True` + `app._update_title()` — the unsaved-changes guard now treats the in-memory profile as dirty so the user is prompted to save before closing
9. `app_toast()` — src/kazbars/ui_widgets.py — success toast `"Scaled grids: {old_res} → {new_w}×{new_h}"` (or `"Resolution set to {...}"` if the scaler short-circuited)

End state: `game_resolution` persisted; all loaded grids re-anchored to the new screen size; editor X/Y spinbox max picks up the new bounds on next panel rebuild; profile marked modified so the user is prompted on close

---

## 17. open Deeps panel and start monitoring

Trigger: User clicks the `⚔ Deeps` button in the bottom bar, then clicks `Start Monitoring` in the panel that opens.

Steps:
1. `KazBarsApp._open_deeps_panel()` — src/kazbars/app.py — one-line delegator to `open_deeps_panel(self)`. Mirrors `_open_boss_timer`.
2. `open_deeps_panel(app)` — src/kazbars/deeps_panel.py — single-instance gate: if `app.deeps_panel` exists and `winfo_exists()`, deiconify + lift + focus + `restore_overlay()` and return. Otherwise construct a fresh `DeepsPanel`.
3. `DeepsPanel.__init__()` — src/kazbars/deeps_panel.py — `restore_window_position("deeps", …)`; loads `deeps_settings.json` via `load_settings()`; constructs `DeepsMeter()` (not started) and passes `include_pet_damage` + `set_window_seconds(window_seconds)` from settings into it; builds the UI from the shared `ui_forms`/`ui_headers` settings-panel builders (the card-by-card layout lives in architecture.md → `deeps_panel.py` inventory row); calls `_create_overlay()` to build the hidden `DeepsOverlay`, **register it with the app's `ForegroundWatcher`**, and push the initial thresholds via `_push_thresholds()`; renders the initial idle status line.
4. User clicks Start Monitoring → `_on_start_stop_click()` → `_start_monitoring()`:
   - `meter.set_include_pet_damage(self._pet_var.get())` — propagate the current checkbox state
   - `meter.start(game_path)` — `DeepsMeter` resets trackers, spawns the `deeps-meter` daemon thread, returns
   - `overlay.show()` — wanted-visible (the `ForegroundWatcher` still gates on focus)
   - `_refresh_start_button()` — swap to "Stop Monitoring" + danger bootstyle (via shared `refresh_toggle_button`)
   - `_begin_tick()` — schedule `self.after(100, self._tick)`
5. **Meter thread** — src/kazbars/deeps_meter.py — outer loop scans `game_folder` for the newest `CombatLog-*.txt`; `is_live(path)` probes via Windows `CreateFile(share_mode=0)` (sharing violation = AoC holds it). On live: enters the tail loop, reads lines from EOF, strips timestamp, dispatches to all five parsers (outgoing/incoming damage, incoming/outgoing heal, own-pet hit); matches go into the four trackers under the shared lock. On 100 ms tick: rebuilds `_snapshot` (the meter no longer probes focus — the shared `ForegroundWatcher` owns that).
6. **UI tick** (every 100 ms on the Tk main thread) — `DeepsPanel._tick()`:
   - `meter.snapshot()` — read latest `MeterSnapshot` under the meter's lock
   - `_render_status(snapshot)` — colored line per status (idle/waiting/old/tailing)
   - `_update_alarm_state(snapshot)` — hysteresis: on at `dps >= alarm_threshold`, off at `dps < alarm_threshold * 0.9`
   - `_update_overlay(snapshot)` — pushes alarm + a single `overlay.paint(snapshot, time.monotonic())` (no focus branch; `paint()` no-ops while the watcher has it focus-suppressed)
   - Reschedule via `after(100, self._tick)`
7. **Overlay paint** — src/kazbars/deeps_overlay.py — `paint()` first advances the `_DisplaySmoother` (EMA easing + coarse rounding + redraw-cadence gate, all from the Readout-card knobs) to turn the raw snapshot rates into eased *display* values, then renders a PIL RGBA bitmap (pushed to the win32 layered window by `overlay_engine.LayeredOverlay`) with the visible cells in the chosen layout (horizontal row or vertical stack), each a single number with an 8-direction dark stroke. The five cells are DPS out, DPS in, HPS out, HPS in, and ΔHP in. **Cell numbers come from the smoothed display values; cell colors come from the raw snapshot** so tints/alarm stay instant while digits ease. The DPS-out cell is white by default; if alarm-active, lerps to red via a 2 Hz sine wave on `now`. The HPS-in cell (and ΔHP in positive side) tints sage green when `net > hpis_green_threshold`. The DPS-in cell + ΔHP in negative side share a three-step ramp on `-net` (incoming damage minus heals): `< dpis_tint_start` no tint → fade DEFAULT→YELLOW_TINT through `dpis_tint_full` → solid YELLOW_TINT → at `dpis_flash`, pulse-flash to a deeper amber (hysteresis-tracked on the overlay, off at `dpis_flash * 0.9`). While either the DPS-out alarm or the DPIS flash is active, `DeepsOverlay` runs a self-driven ~30 Hz repaint loop (`_pulse_tick`) so the 2 Hz sine reads as a smooth glide instead of the 10 Hz data-tick stutter; the loop stops when no pulse is wanted.

End state: meter daemon thread is parsing combat log; overlay shows numbers when AoC is the foreground window; panel status row reads "Tailing CombatLog-…" in green; alarm pulses + tints animate based on live data. The panel can be closed (withdraw) without stopping monitoring — the overlay keeps updating in-game.

---

## 18. Deeps overlay auto-hide on AoC focus loss

Trigger: User alt-tabs away from AoC (to a browser, Discord, KazBars, anything else).

This is now a shared mechanism — the same `ForegroundWatcher` gates the Ethram-Fal overlay identically.

Steps:
1. **ForegroundWatcher tick** — src/kazbars/focus_watcher.py — the app-owned watcher ticks every ~250 ms on the Tk main loop, calling `foreground.app_or_game_foreground()` once. On focus change away from AoC + away from this process's own windows, the probe returns False.
2. The watcher calls `set_focus_suppressed(True)` on every registered overlay. `DeepsOverlay.set_focus_suppressed()` (src/kazbars/deeps_overlay.py) forwards to `HudOverlay`, which is state-guarded: it blanks the surface exactly once (one transparent `LayeredOverlay` blit), not every tick.
3. The Deeps meter keeps tailing; the 100 ms UI tick keeps calling `paint()`, which no-ops while suppressed (so no work + no re-blank spam).
4. User alt-tabs back to AoC → next watcher tick → `set_focus_suppressed(False)` → `HudOverlay` repaints if the overlay is wanted-visible → it reappears with the current numbers.

Subtle: clicking the overlay itself (to drag when unlocked) DOES count as "in focus" — `foreground.app_or_game_foreground()` checks `GetCurrentProcessId()` first, so any KazBars window keeps the gate open and drag-to-position never self-hides.

End state: overlay visibility tracks focus with ≤250 ms latency, for both overlays, from one probe. Lock state, position, and tracker data are preserved across hide/show — nothing is destroyed or reset.

---

## 19. backup & restore game settings

Trigger: User selects Game > Backup & restore game settings... from the menu, then clicks Back up… or Restore… in the dialog that opens.

Steps:
1. `KazBarsApp._open_backup_dialog()` — src/kazbars/app.py — one-line delegator to `open_backup_dialog(self)`. Mirrors `_open_deeps_panel`.
2. `open_backup_dialog(app)` — src/kazbars/settings_backup.py — builds a modal `Toplevel`; `locate_funcom_prefs()` resolves `%LOCALAPPDATA%\Funcom\Conan\Prefs`; `_funcom_summary()` returns the account names (the prefs dir's immediate subfolders), the character count (`Char*` subfolders across all accounts), and total size; counts `*.json` under `app.profiles_path`; renders the "What's included" lines (account names listed, KazBars data noted as profiles + settings + custom buffs), the "Close AoC first" warning, an **off-by-default "also bring back this PC's settings" checkbox** (`include_prefs_var`), and Back up… / Restore… / Close buttons.
3a. **Back up** → `backup_settings(app, dialog)` — `filedialog.asksaveasfilename` (default `KazBars_Backup_{date}.zip`) → `write_backup_zip()` archives the Funcom prefs tree under `funcom/` + the `userdata/` allowlist under `kazbars/`: `app.profiles_path` → `kazbars/profiles/`, the whole `app.settings_path` dir (`deeps`/`live_tracker`/`damageinfo` settings) → `kazbars/settings/`, `database_user_path()` → `kazbars/database_user.json`, and `prefs_path()` → `kazbars/prefs.json`. The OTA `content/` cache is not a parameter, so it never enters the zip. Skips `*.tmp`, writes `manifest.json` last → dialog closes → `app_toast()` success with the file counts.
3b. **Restore** → `restore_settings(app, dialog, include_prefs)` — `filedialog.askopenfilename` → `read_manifest()` rejects anything that isn't a KazBars backup → `confirm()` — src/kazbars/ui_widgets.py — verb-labeled Restore settings / Cancel confirm (+ AoC-closed warning, + an unsaved-DB-edits-will-be-discarded line when `db_panel.modified`) → best-effort pre-restore snapshot via `write_backup_zip()` to `app.app_path/KazBars_PreRestore_{timestamp}.zip` (outside `userdata/`, so restore can't recurse into it) → `restore_zip(funcom_dest=funcom_prefs_path(), userdata_dest=userdata_root(), include_prefs=include_prefs)` extracts each section, creating dirs and skipping zip-slip entries; the machine-local `kazbars/prefs.json` is skipped unless the checkbox opted in → `app.settings.reload()` (`Prefs.reload`) resyncs prefs from disk so a freshly-restored `prefs.json` isn't clobbered on exit → `app.database.reload()` re-merges the buff DB from the restored `database_user.json` and the DB editor refreshes (`refresh_from_database()` — src/kazbars/database_editor.py, `modified=False`) so a later Save Database can't recompute deltas from pre-restore memory and clobber the restored custom buffs → `Messagebox.show_info` reports the restored counts + snapshot path.

End state: backup writes a single portable zip (AoC prefs + the KazBars `userdata/` allowlist); restore replaces them in place after snapshotting the prior state, re-merges the buff DB from the restored `database_user.json` so custom buffs survive a later Save Database, leaving machine-local `prefs.json` untouched unless opted in, with a KazBars restart recommended to fully apply restored window/game-folder settings.

---

## 20. open Damage Numbers panel and tune settings

Trigger: User selects Extras ▸ Damage number mod… from the menu, then adjusts a control in the panel that opens.

Steps:
1. `KazBarsApp._open_damage_numbers()` — src/kazbars/app.py — one-line delegator to `open_damage_numbers_panel(self)`. Mirrors `_open_deeps_panel`.
2. `open_damage_numbers_panel(app)` — src/kazbars/damageinfo_panel.py — single-instance gate: if `app.damage_numbers_panel` exists and `winfo_exists()`, deiconify + lift + focus and return; otherwise construct a fresh `DamageNumbersPanel(app, app.settings_path)`.
3. `DamageNumbersPanel.__init__()` — src/kazbars/damageinfo_panel.py — `restore_window_position("damage_numbers", …)`; loads `damageinfo_settings.json` via `load_settings()`; builds the UI (CRT header, tip bar, master Enable checkbutton, then a scrollable body — Presets, then cards Behavior (all toggles, off by default) / Shadow / Direction 1 (Rising) / Direction -1 (Dropping) / Direction 0 (Zig-zag) — built from `damageinfo_settings.GLOBAL_SETTINGS` metadata; no number/label size slider, AoC's own Options slider covers it); `_sync_enabled_state()` greys every control when the master toggle is off; `WM_DELETE_WINDOW` → destroy.
4. User drags a slider → `_on_slider(key, raw)` quantizes to the key's step (`validate_setting`), stores the offset in `self.settings`, and updates the right-side readout to the **resulting game value** (`compute_final_value`), not the raw offset. Commit (button/key release) → `_save()` writes `damageinfo_settings.json`. Enum radios / bool checkboxes save immediately on change; `shadow_mode`/`fixed_col_split` also re-run their sub-gates (`_sync_shadow_state` greys shadow offset/blur by mode; `_sync_split_state` greys Column B when split is off).
5. Preset buttons → `_apply_preset(name)` overlays the `PRESETS` bundle (`damageinfo_settings.apply_preset`), saves, and `_refresh_all()` re-syncs every widget + readout to the new values.

End state: `damageinfo_settings.json` reflects the chosen offsets + `enabled` flag. Nothing is applied in-game yet — the values bake into a modded `DamageInfo.swf` on the next Build & Install (Flow 1, steps 13–14); with the master toggle off, the build leaves AoC's stock file in place (reverting any prior mod).

## 21. set per-source damage-number colors

Trigger: User selects Extras ▸ Damage number colors… from the menu.

Steps:
1. `KazBarsApp._open_damage_number_colors()` — src/kazbars/app.py — one-line delegator to `open_damage_number_colors_panel(self)` — src/kazbars/damageinfo_colors_panel.py — pre-flight (mirrors Flow 20): validates `app.game_path` is set and points to a real directory; on miss, shows a `Messagebox.show_warning` and returns. Otherwise constructs `DamageNumberColorsPanel(app, game_path)` (modal: `withdraw → transient → grab_set`).
2. `DamageNumberColorsPanel.__init__()` — resolves the skin's `TextColors.xml` via `buff_xml._resolve_paths` (Customized if present, else Default); `_read_colors(source)` seeds the swatches from the live file and `_read_colors(default)` captures the stock color each "reset" reverts to (both `name → RRGGBB`). Builds a 2-column body — each `damageinfo_settings.PAIRED_GROUPS` entry as a Self card (left) + Other card (right), then a full-width "Resources & misc" card from `SHARED_SOURCES`. Each row = label + `ui_forms.ColorSwatch` + a "↺" reset. A bottom row packs Cancel + Apply (Apply disabled until a pick differs from the loaded baseline); the panel snapshots that baseline after building.
3. User picks a color → `_on_color(name, hex)` records the pick and `_refresh_apply_state()` enables Apply. "↺" → `_reset_one(name)` sets the swatch to the stock Default color; "Reset all to game default" → `_reset_all()` does so for every swatch. None of these touch disk — they stage pending edits (Cancel/Escape abandons them).
4. User clicks Apply → `_on_apply()` calls the module's pure `apply_colors(game_path, picks)`: reads the file the game reads (Customized else Default), applies each pick via `buff_xml.set_source_color` (surgical, skip-when-equal, colors only), then writes to **Customized/TextColors.xml** (created from the Default copy when absent), taking a one-time `TextColors.xml.kazbars.bak` of any pre-existing skin file first. On success the panel re-baselines (Apply disables) and toasts "type /reloadui"; an `OSError` (game holding the file locked, permissions) toasts a failure and changes nothing.

End state: colors are written straight into `Customized/TextColors.xml` — no build, no master-enable gate (mirrors the Default Buff Bars editor, Flow 20). The user types `/reloadui` in-game to see them. The direction toggles (Flow 1) edit the same file surgically and independently, so a later build's flips and these colors don't overwrite each other.

---

## 22. OTA buff-database update on launch

Trigger: `KazBarsApp.__init__` calls `content_update.check_and_apply(self, APP_VERSION, prefs.content_version)` after the layered DB load (returning user); on a fresh install `first_launch.on_dialog_closed` calls it once the welcome flow finishes (so an update never races the welcome popup). Auto-runs only if the "Automatically update the buff database" toggle is on.

Steps:
1. `content_update.check_and_apply()` — src/kazbars/content_update.py — bails immediately if (auto and the toggle is off); otherwise spawns a daemon worker thread.
2. `_worker()` — fetches `ota/manifest.json` (raw URL on `main`); `parse_manifest` validates it. If `app_supports` is false (app older than `min_app_version`), schedules the once-per-session "New buffs are available — update KazBars" compat toast and stops. If not `is_newer(manifest, prefs.content_version)`, stops (manual run toasts "already up to date").
3. Downloads each SHA-pinned payload (`Database.json`, `Default.json`); a `verify_sha256` mismatch aborts and swaps nothing. Then hops to the main thread via `app.after(0, _apply_on_main, …)`.
4. `_apply_on_main()` — **apply guard:** if `db_panel.modified` or `app._building`, defer (do nothing — retry next launch). Else `apply_content(content_dir(), …)`: snapshot the current `content/` into `.bak/prev/`, `os.replace` each verified payload into `content/`, then write `content/manifest.json` LAST as the commit marker (a crash between the replace and the marker re-applies next launch — never half-applied).
5. Persists `prefs.content_version = manifest.content_version`; `BuffDatabase.reload()` re-merges (stock←content←user); `db_panel.refresh_from_database()`. A re-merge exception auto-rolls-back from `.bak/prev/` and toasts failure.
6. One `app_toast` — "Buff database updated — N added, M changed" (`summarize_changes`), click-through to a what-changed note + a Revert reminder. User deltas (`database_user.json`) are untouched throughout.

End state: `userdata/content/` holds the new stock `Database.json` + `Default.json` + the `manifest.json` marker; `prefs.content_version` advanced; the live DB reflects the merge; `.bak/prev/` holds the prior content for Revert. Any failure or defer leaves everything on the shipped stock and changes nothing.

---

## 23. check / revert buff-database updates (manual)

Trigger: Updates ▸ "Check for buff-database updates now" or Updates ▸ "Revert last buff-database update".

Steps:
- **Check now** → `KazBarsApp._check_content_updates_now()` → `content_update.check_and_apply(..., manual=True)` — the Flow 22 path, but runs regardless of the toggle and reports the outcome (applies an update, or toasts "already up to date" / "couldn't reach the update server").
- **Revert** → `KazBarsApp._revert_content_update()` → `content_update.revert(app)` — `rollback(content_dir())` restores `content/` from `.bak/prev/` (a first-ever update clears `content/` back to the stock floor); sets `prefs.content_version` to the restored marker's version (or `CONTENT_BASELINE_VERSION`); `BuffDatabase.reload()` re-merges; refreshes the DB view; toasts. User deltas untouched. With nothing to revert, toasts so.

End state: content reverted to the previous applied version (or the shipped stock); the live DB re-merged; prefs version aligned to what's on disk.

---

## 24. manage / export / import profiles

Trigger: File ▸ "Manage profiles…".

Steps:
1. `KazBarsApp._open_profile_manager()` — src/kazbars/app.py — delegator to `profile_manager.open_profile_manager(self)` (single-instance gate on `app._profile_manager`).
2. `ProfileManagerDialog` — src/kazbars/profile_manager.py — modal Toplevel listing `userdata/profiles/*.json` in a Treeview (★ marks `prefs.default_profile`); buttons Load / Rename / Duplicate / Delete / Set Default + Export / Import.
   - **Load** → `profile_io.read_profile_file` + `apply_profile_data` (the Flow 2 path) and closes.
   - **Rename / Duplicate / Delete** → file ops under `userdata/profiles/`; `_rebind_path` keeps the `current_profile` + `default_profile` pointers valid.
   - **Set Default** → `profile_io.set_default_profile` writes `prefs.default_profile` (does **not** change which profile reopens on relaunch — that stays `last_profile`).
3. **Export** → reads the selected profile; `profile_share.collect_referenced_user_buffs(data, by_id, by_name, provenance)` gathers the user-provenance buffs it references; `profile_share.encode_profile` packs `{profile, buffs}` → `KZBARS1:<gzip+base64>` onto the clipboard; one toast notes the embedded-buff count.
4. **Import** → paste a `KZBARS1:` string → `profile_share.decode_profile` (rejects corrupt/truncated) → one confirmation ("includes N custom buffs") → `write_profile_file` to `userdata/profiles/Imported Profile.json` (auto-incremented) + `profile_share.merge_imported_buffs` into `database_user.json` (skip-on-collision) → if any buff was added, `BuffDatabase.reload()` + DB-view refresh → one summary toast ("Imported '…' — N added, M already existed").

End state: profiles managed in place; an export string is self-contained (custom buffs travel with it); an import writes the profile + merges any new custom buffs without clobbering existing ones. ("Load default profile" and first-launch resolve their target via `profile_io.resolve_default_profile_path`: the user's `default_profile` if set, else the OTA `content/Default.json`, else shipped stock.)

---

## 25. configure the in-game stopwatch

Trigger: User selects Extras ▸ In-game stopwatch… from the menu.

Steps:
1. `KazBarsApp._open_stopwatch_settings()` — src/kazbars/app.py — one-line delegator to `open_stopwatch_dialog(self)`.
2. `open_stopwatch_dialog(app)` — src/kazbars/stopwatch_panel.py — single-instance gate on `app.stopwatch_dialog` (lift + focus if open); otherwise builds a modal Toplevel over the validated `stopwatch` prefs dict: CRT header, master "Include the stopwatch in builds" checkbutton, X/Y spinboxes for the baked default position, and a "Start collapsed (title bar only)" checkbutton.
3. `_apply()` — src/kazbars/stopwatch_panel.py — re-validates via `stopwatch.validate_config` (clamps X/Y, falls back to the loaded value on an emptied spinbox), writes the dict to `prefs['stopwatch']`, saves, toasts ("Build & Install to apply" when enabled / "next build removes it" when disabled), and destroys the dialog.

End state: prefs.json's `stopwatch` dict reflects the choices. Nothing is applied in-game yet — on the next Build & Install (Flow 1, steps 9–11) `include_stopwatch` compiles the `KazBarsStopwatch` stub into the module: a draggable count-up Start/Pause/Reset panel, drawn at runtime with the Arial faces embedded in `base.swf` (no new symbols), with a − / + collapse-to-title-bar button. Clicks are ordinary Scaleform GUI input (fullscreen-safe, no game-focus steal). Dragging the title bar shows live coordinates — `/loadclip` users copy them into this dialog to make a spot permanent; aoc.exe clients persist position + collapsed state automatically via the module config archive (`swx`/`swy`/`swc`).
