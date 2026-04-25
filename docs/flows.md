# Flows

## Conventions

When a flow crosses a dialog→app boundary (any modal `Toplevel` whose buttons or `WM_DELETE_WINDOW` callbacks invoke app methods), name the dialog-side dispatcher as an explicit step. Eliding it folds dialog-internal and app-internal responsibilities into one gloss and produces caller/callee confusion. Confirmed examples in this doc: Flow 4 step 3 (`AddGridWizard.on_create`), Flow 5 step 6 (`BuffSelectorDialog.on_ok`), Flow 13 step 5 (`start_empty`).

---

## 1. build and install SWF

Trigger: User clicks "Build & Install" button in the bottom bar or presses Ctrl+B

Steps:
1. `KzGridsApp._build()` — kzgrids.py:595 — one-line delegator to `build_action.build(self)`
2. `build_action.build()` — Modules/build_action.py:25 — checks `_building` re-entry guard; validates game folder, compiler path, grids list, total slot count; flags grids that would render empty (no whitelist or no static slot assignments); blocks build if Aoc.exe mode and an AoC game process is running
3. `get_profile_data()` — Modules/grids_panel.py:919 — calls `save_settings()` then returns `self.grids`
4. `save_settings()` — Modules/grids_panel.py:1002 — iterates all `GridEditorPanel` instances, calling `save_to_config()` on each
5. `save_to_config()` — Modules/grids_panel.py:394 — reads every spinbox/combobox/toggle value and writes it into the grid config dict
6. `find_compiler()` — Modules/build_utils.py:24 — checks three candidate paths for `mtasc.exe`; returns `Path` or `None`
7. `profile_io.do_save_profile()` — Modules/profile_io.py:121 — auto-saves the current profile (if one is loaded) before the build locks
8. Build is locked: `app._building = True`, build button disabled, Ctrl+B unbound
9. `compile_to_staging()` — Modules/build_executor.py:24 — creates a `tempfile.mkdtemp` staging dir and calls `build_grids()`; returns `(staging_dir, (success, message))`
10. `build_grids()` — Modules/grids_generator.py:350 — instantiates `CodeGenerator`, writes `KzGrids.as` and `KzGridsData.as` to a second temp dir, copies `base.swf`, calls `compile_as2()`
11. `CodeGenerator.generate()` — Modules/grids_generator.py:59 — returns `(KzGrids.as, KzGridsData.as)` source strings; calls `_resolve_grid()` per grid to expand primary IDs
12. `compile_as2()` — Modules/build_utils.py:36 — assembles MTASC command with classpaths, runs subprocess, returns `(bool, stderr)`
13. `install_to_client()` — Modules/build_executor.py:46 — calls `cleanup_legacy_files()`; copies SWF to `Data/Gui/Default/Flash/`; calls `write_xml_add_files()` in Aoc mode; calls `create_scripts()`
14. `create_scripts()` — Modules/build_executor.py:198 — writes `reloadgrids` and `unloadgrids`; in non-Aoc mode calls `update_script_with_marker()` to add the auto-load entry; in Aoc mode strips any old KzGrids/KazBars markers from `auto_login` instead (Aoc.exe loads via xml.add)
15. `update_script_with_marker()` — Modules/build_utils.py:79 — strips old KzGrids marker block (and any listed legacy markers) from `auto_login`, then appends fresh block
16. Toast text varies by mode: "Built — /reloadui in-game" (Aoc + game running), "Built — launch via Aoc.exe" (Aoc + not running), or "Built — /reloadui + /reloadgrids" (standard launcher)
17. `notify_build_done(use_aoc_bypass)` — Modules/grids_panel.py:857 — re-shows the in-panel tip guide with step 4 marked complete
18. `finally` block: cleans up staging dir via `shutil.rmtree`, releases `_building` flag, re-binds Ctrl+B, syncs build button state

End state: `KazGrids.swf` installed under the game folder; `Scripts/reloadgrids` and `Scripts/unloadgrids` written; in non-Aoc mode `Scripts/auto_login` updated; in Aoc mode `Data/Gui/Aoc/KazGrids/MainPrefs.xml.add` and `Modules.xml.add` written; build loading screen shows the result summary

---

## 2. load profile from file

Trigger: User selects File > Open Profile... (or presses Ctrl+O) and confirms a `.json` path

Steps:
1. `KzGridsApp._open_profile()` — kzgrids.py:536 — one-line delegator to `profile_io.open_profile(self)`
2. `profile_io.open_profile()` — Modules/profile_io.py:33 — runs the unsaved-changes guard via `_check_unsaved_changes()`; opens `filedialog.askopenfilename`; passes chosen path to `load_profile()`
3. `profile_io.load_profile()` — Modules/profile_io.py:46 — reads and parses JSON; on corruption shows a warning and proceeds with empty grids; extracts `grids`, `boss_timer`, `reference_resolution`. Note: also dispatches `boss_timer` to the live tracker when one is open — see step 8.
4. `load_profile_data()` — Modules/grids_panel.py:963 — iterates raw grid dicts; migrates, validates, rebuilds panel list; returns `{grid_name: [missing_refs]}` for buffs that couldn't be resolved
5. `_migrate_grid()` — Modules/grids_panel.py:946 — normalizes legacy `int` IDs and legacy name strings in `whitelist` and `slotAssignments` to current primary spell IDs via `database.by_id` and `database.get_entry_by_name`
6. `validate_grid()` — Modules/grid_model.py:74 — fills missing keys from `create_default_grid()`; clamps every numeric field against `CLAMP_SPECS`; coerces enums in `ENUM_SPECS`; coerces booleans and lists/dicts
7. `refresh_panels()` — Modules/grids_panel.py:1048 — destroys existing `GridEditorPanel` widgets; creates new ones for the validated list; shows empty state if list is empty
8. If a Boss Timer panel is alive, `LiveTrackerPanel.load_profile_data()` — Modules/live_tracker_panel.py:436 — applies the embedded `boss_timer.overlay` settings to the overlay
9. `warn_missing_buffs()` — Modules/profile_io.py:82 — if migration dropped any references, displays them (deferred 200ms when called during startup so the dialog doesn't race the welcome popup)
10. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` path to `kzgrids_settings.json` via atomic temp-rename in `safe_save_json` (Modules/settings_manager.py:33)

End state: `GridsPanel` displays validated grid cards; `app.modified` is `False`; `last_profile` updated in settings; window title reflects loaded name

---

## 3. save profile to file

Trigger: User selects File > Save Profile (Ctrl+S) or File > Save Profile As...

Steps:
1. `KzGridsApp._save_profile()` — kzgrids.py:545 — one-line delegator to `profile_io.save_profile(self)`
2. `profile_io.save_profile()` — Modules/profile_io.py:101 — routes to `do_save_profile(app, current_path)` if a path exists, or to `save_profile_as()` otherwise
3. `profile_io.do_save_profile()` — Modules/profile_io.py:121 — assembles `{version, grids}` plus optional `reference_resolution` and `boss_timer` keys; calls `safe_save_json()`. Note: the `boss_timer` key is sourced from the live tracker when one is open — see step 7.
4. `get_profile_data()` — Modules/grids_panel.py:919 — calls `save_settings()` then returns `self.grids`
5. `save_settings()` — Modules/grids_panel.py:1002 — iterates all `GridEditorPanel` instances calling `save_to_config()`
6. `save_to_config()` — Modules/grids_panel.py:394 — reads all widget values into the grid config dict
7. If a Boss Timer panel is alive, `LiveTrackerPanel.get_profile_data()` — Modules/live_tracker_panel.py:431 — returns `{'overlay': {...}}` for embedding
8. `safe_save_json()` — Modules/settings_manager.py:33 — writes JSON to `path.tmp` then `Path.replace`-renames it over the target atomically
9. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` to `kzgrids_settings.json`

End state: profile `.json` written atomically; `app.modified` is `False`; title bar reflects saved name; toast `Saved: <filename>` shown; status bar pulse

---

## 4. add new grid via wizard

Trigger: User clicks "+ Add Grid" button on the grids panel toolbar (also reachable from the empty-state "Custom" preset card)

Steps:
1. `add_grid()` — Modules/grids_panel.py:1025 — checks the slot budget against `MAX_TOTAL_SLOTS` (64); opens `AddGridWizard` dialog
2. `AddGridWizard.__init__()` — Modules/grid_dialogs.py:50 — builds wizard UI with name, source/mode/dimension fields and four preset shape buttons; calls `restore_window_position()`
3. `AddGridWizard.on_create()` — Modules/grid_dialogs.py:239 — validates name (non-empty, unique, optional special-char warning), enforces slot budget; calls `create_default_grid()`
4. `create_default_grid()` — Modules/grid_model.py:37 — returns a complete grid config dict populated with caller-specified `grid_type`, `rows`, `cols`, `mode`, `grid_id`; auto-coerces `1×1` to static mode and picks a sensible `fillDirection`
5. `refresh_panels()` — Modules/grids_panel.py:1048 — destroys and recreates all `GridEditorPanel` cards; the newly added card is initially expanded

End state: new grid config appended to `self.grids`; new `GridEditorPanel` card visible and expanded; slot count label updated; profile marked modified

---

## 5. select tracked buffs for a dynamic grid

Trigger: User clicks "Tracked Buffs..." on a dynamic-mode `GridEditorPanel` (the same button shows "Slot Assignments" in static mode and routes to a different dialog)

Steps:
1. `_on_mode_btn_click()` — Modules/grids_panel.py:466 — dispatches to `edit_whitelist()` when grid is in dynamic mode (or `edit_slots()` for static)
2. `edit_whitelist()` — Modules/grids_panel.py:472 — flushes current widget state via `save_to_config()`; opens `BuffSelectorDialog`
3. `BuffSelectorDialog.__init__()` — Modules/grid_dialogs.py:285 — resolves initial `whitelist` primary IDs to entry names via `database.by_id`; restores last-used category/type filter from settings; calls `refresh_lists()`
4. `BuffDatabase.search()` — Modules/database_editor.py:81 — filters `grouped_buffs` by query/category/type; sorts by type then name
5. `BuffSelectorDialog.refresh_lists()` — Modules/grid_dialogs.py:382 — repopulates Available and Selected listboxes; selected entries sort by type when the grid `layout` is `buffFirst` or `debuffFirst`, alphabetically when `mixed`
6. `BuffSelectorDialog.on_ok()` — Modules/grid_dialogs.py:449 — saves filter state; maps each selected name back to `entry['ids'][0]` via `database.get_entry_by_name()`; sets `self.result`
7. `update_labels()` — Modules/grids_panel.py:433 — refreshes whitelist count and buff-name preview text in card header

End state: `grid_config['whitelist']` updated with new primary spell ID list; panel header shows new buff count and preview names

---

## 6. first-launch setup with defaults

Trigger: `KzGridsApp.__init__` detects no `game_path` in settings; schedules 100ms after `deiconify()`

Steps:
1. `_show_first_launch_dialog()` — kzgrids.py:589 — one-line delegator to `run_first_launch(self, APP_NAME)`
2. `run_first_launch()` — Modules/first_launch.py:292 — defines the `on_game_set`, `on_aoc_bypass_set`, `on_load_default`, `on_resolution_set`, `on_dialog_closed` closures; calls `show_first_launch_dialog()`
3. `show_first_launch_dialog()` — Modules/first_launch.py:26 — builds modal dialog with game folder entry, common-paths shortcuts, an Aoc.exe Yes/No section (revealed on demand), resolution picker, and two option cards ("Use Defaults" / "Start Empty")
4. `detect_aoc_launcher()` — Modules/build_executor.py:139 — called whenever the path entry changes; checks for `aoc.exe` or `Aoc.log` under `Data/Gui/Aoc/`; reveals the Aoc.exe radio group if found
5. `on_load_default()` — Modules/first_launch.py:313 — closure: persists game path, Aoc.exe preference, and resolution; calls `profile_io.load_profile()` with `Default.json`; calls `grids_panel.scale_to_resolution()`; saves a personal copy as `profiles/MyGrids.json` (auto-incremented on collision); stashes data for the welcome popup
6. `profile_io.load_profile()` — Modules/profile_io.py:46 — reads `assets/kzgrids/Default.json`; passes grids to `grids_panel.load_profile_data()`; populates `app.reference_resolution` from the JSON
7. `GridsPanel.scale_to_resolution()` — Modules/grids_panel.py:1007 — proportionally adjusts each grid's `x`/`y` from `app.reference_resolution` to the selected game resolution; clamps to `SCREEN_MAX_X`/`SCREEN_MAX_Y`; calls `refresh_panels()`
8. `profile_io.do_save_profile()` — Modules/profile_io.py:121 — writes scaled profile to `profiles/MyGrids.json`
9. `on_dialog_closed()` — Modules/first_launch.py:339 — closure called when the dialog is destroyed; if the user took the defaults path, schedules `show_welcome_popup()` 100ms later

End state: `game_path` and `use_aoc_bypass` persisted; default profile loaded, scaled to resolution, saved as `profiles/MyGrids.json`; welcome popup shown after the dialog closes

---

## 7. save buff database

Trigger: User clicks the "Save Database" button in the Database view's toolbar (no menu item, no keyboard shortcut — Ctrl+S is bound to profile save)

Steps:
1. `DatabaseEditorTab.save()` — Modules/database_editor.py:840 — resolves `assets_path / "Database.json"`; calls `BuffDatabase.save()`
2. `BuffDatabase.save()` — Modules/database_editor.py:153 — serializes `self.buffs` into v2 JSON format (`{version: 2, description, buffs}`); writes to file directly (not atomic)

End state: `assets/kzgrids/Database.json` updated; `DatabaseEditorTab.modified` set to `False`; toast `Database saved` shown

---

## 8. add buff to database

Trigger: User clicks "Add" in the `DatabaseEditorTab` toolbar (Database view)

Steps:
1. `DatabaseEditorTab.add_buff()` — Modules/database_editor.py:690 — creates an add-validator closure (checks ID collision and name uniqueness); opens `BuffEditDialog`
2. `BuffEditDialog.__init__()` — Modules/database_editor.py:173 — builds form with name, IDs (multi-line), category combobox, type radio group, and the stacking section (toggle + partial + start/end spinboxes); calls validator on submit
3. `BuffDatabase.add_buff()` — Modules/database_editor.py:127 — appends the new entry dict to `self.buffs`; calls `_rebuild_indexes()`
4. `BuffDatabase._rebuild_indexes()` — Modules/database_editor.py:67 — rebuilds `by_id`, `by_name`, `categories`, `grouped_buffs` from the full `buffs` list
5. `DatabaseEditorTab.update_categories()` — Modules/database_editor.py:563 — refreshes the category dropdown values
6. `DatabaseEditorTab.refresh_list()` — Modules/database_editor.py:588 — repopulates treeview rows using current search/category/type filter state; recomputes per-grid usage counts

End state: new buff entry visible in treeview; `by_id` and `by_name` indexes updated; toast `Added: <name>` shown; `DatabaseEditorTab.modified` set to `True`

---

## 9. uninstall from game folder

Trigger: User selects File > Uninstall from game client... and confirms the dialog

Steps:
1. `KzGridsApp._uninstall_game()` — kzgrids.py:481 — one-line delegator to `game_folder.uninstall_game(self)`
2. `game_folder.uninstall_game()` — Modules/game_folder.py:142 — guards on `app.game_path`; confirms with the user; calls `uninstall_from_client()`
3. `uninstall_from_client()` — Modules/build_executor.py:95 — deletes `Data/Gui/Default/Flash/KazGrids.swf`, the `Data/Gui/Aoc/KazGrids/` directory (if present), and `Scripts/reloadgrids` + `Scripts/unloadgrids`; strips the auto-load marker block from `Scripts/auto_login`
4. `strip_marker_block()` — Modules/build_utils.py:60 — removes the `# KzGrids auto-load` marker-delimited section (marker line through the next blank line) from the `auto_login` file content; the script is rewritten or, if empty after the strip, deleted

End state: `KazGrids.swf`, the Aoc xml.add module folder, the reload scripts, and the auto-load marker block are all removed; toast lists what was removed (or notes nothing was installed)

---

## 10. open live tracker panel

Trigger: User clicks the "⏱ Tracker" button in the bottom bar (right side, next to Build & Install)

Steps:
1. `_open_boss_timer()` — kzgrids.py:438 — checks `_boss_timer_if_alive()`; if a panel exists, deiconifies/lifts/restores the overlay; otherwise constructs a new `LiveTrackerPanel`
2. `LiveTrackerPanel.__init__()` — Modules/live_tracker_panel.py:44 — restores window position; calls `load_settings()`; builds UI; creates overlay; constructs `BossTimer` and `CombatLogMonitor`; auto-detects log path
3. `load_settings()` — Modules/live_tracker_settings.py:97 — reads `timers_settings.json` from the settings folder; returns dict validated against `TIMERS_DEFAULTS` and `TIMERS_RANGES`
4. `BossTimer.__init__()` — Modules/boss_timer.py:52 — initializes cycle state fields; stores the `_thread_safe_update` closure (defined in `LiveTrackerPanel`) as `_update_callback`
5. `CombatLogMonitor.__init__()` — Modules/combat_monitor.py:34 — initializes daemon thread state; stores the `boss_timer` reference
6. `TimerOverlay.__init__()` — Modules/timer_overlay.py:41 — creates always-on-top `Toplevel` with configured opacity and position; builds two-row display + cycle-timer line + lock indicator + resize handle; auto-shows on first launch regardless of saved `visible` state
7. `LiveTrackerPanel._update_log_path()` — Modules/live_tracker_panel.py:236 — calls `combat_monitor.set_log_folder()` with the current game path
8. `CombatLogMonitor.set_log_folder()` — Modules/combat_monitor.py:51 — finds latest `CombatLog*.txt` in the game folder; records file end position as `last_position`

End state: `LiveTrackerPanel` window visible; `TimerOverlay` shown; `CombatLogMonitor` ready with log file path set; overlay shows monitor + log status

---

## 11. start combat log monitoring

Trigger: User clicks "Start Monitoring" button in `LiveTrackerPanel`

Steps:
1. `LiveTrackerPanel._start_monitoring()` — Modules/live_tracker_panel.py:292 — re-runs `_update_log_path()` (which calls `combat_monitor.set_log_folder()` to refresh `log_path` and `last_position`); errors out if no log file is found
2. `CombatLogMonitor.start_monitoring()` — Modules/combat_monitor.py:137 — sets `monitoring=True`; spawns the `CombatLogMonitor` daemon thread running `_monitor_loop()`
3. `BossTimer._push_waiting_state()` — Modules/boss_timer.py:246 — fires `_update_callback` with "Waiting for Seed..." strings
4. `_thread_safe_update()` — Modules/live_tracker_panel.py:77 — closure passed as `update_callback`; marshals the call to the main thread via `self.after(0, ...)`
5. `TimerOverlay.update_display()` — Modules/timer_overlay.py:272 — applies row1/row2/cycle_timer text and color values to the label widgets
6. `LiveTrackerPanel._start_game_loop()` — Modules/live_tracker_panel.py:349 — schedules a 50ms recurring `after()` call to `boss_timer.update_display()`

End state: `CombatLogMonitor` daemon thread running; 50ms UI poll active; overlay displays "Waiting for Seed..."

---

## 12. combat log trigger detected

Trigger: `CombatLogMonitor` daemon thread reads a new log line containing "Viscous Seed", "Lotus Fixation", or "Syphon hits"

Steps:
1. `CombatLogMonitor._monitor_loop()` — Modules/combat_monitor.py:215 — polls log file every 100ms; checks every 30s for a newer log file; handles truncation/rotation; reads bytes since `last_position`; dispatches matching lines to `_process_line()`
2. `CombatLogMonitor._process_line()` — Modules/combat_monitor.py:264 — identifies trigger type (Syphon → `start_syphon`, Viscous Seed from Ethram-Fal → `start_cycle`, Lotus Fixation from Emerald Lotus → `update_fixation`); extracts player name (or "YOU") from the line text via `_extract_player()`
3. `BossTimer.start_cycle()` — Modules/boss_timer.py:81 — sets `timer_active=True`; records `cycle_start_time` and `seed_player`; detects double-seed (P4) when called 5–12s after the previous seed for the same player
4. `BossTimer.update_display()` — Modules/boss_timer.py:227 — called from the 50ms UI loop; calls `get_current_phase()`; fires `_update_callback` with the phase display dict (msg, player, timer, color per row + cycle_timer)
5. `_thread_safe_update()` — Modules/live_tracker_panel.py:77 — closure passed as `update_callback`; marshals call to main thread via `self.after(0, ...)`
6. `TimerOverlay.update_display()` — Modules/timer_overlay.py:272 — applies message/player/timer strings and per-row colors to label widgets

End state: overlay displays the active seed/fixation/syphon phase with elapsed timer text updated on the next 50ms poll

---

## 13. first-launch setup with empty start

Trigger: User completes the first-launch dialog by clicking "Start Empty" instead of "Use Defaults"

Steps 1–4 are identical to Flow 6 (delegator → `run_first_launch()` → `show_first_launch_dialog()` → `detect_aoc_launcher()`).

Steps:
5. `start_empty()` — Modules/first_launch.py:185 — closure: calls `_set_game_if_provided()`, then `_close()`. No `on_load_default` invocation, so no profile load and no scale.
6. `_set_game_if_provided()` — Modules/first_launch.py:166 — same dispatcher used by Flow 6's `load_default()`; persists game path via `on_game_set`, Aoc.exe preference via `on_aoc_bypass_set`, resolution via `on_resolution_set`
7. `on_dialog_closed()` — Modules/first_launch.py:339 — runs as in Flow 6 but `welcome_data` was never populated, so the welcome popup is suppressed

End state: `game_path`, `use_aoc_bypass`, and `game_resolution` persisted; no profile loaded; no welcome popup; user lands on the empty `GridsPanel` empty-state
