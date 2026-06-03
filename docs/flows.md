# Flows

## Conventions

When a flow crosses a dialog→app boundary (any modal `Toplevel` whose buttons or `WM_DELETE_WINDOW` callbacks invoke app methods), name the dialog-side dispatcher as an explicit step. Eliding it folds dialog-internal and app-internal responsibilities into one gloss and produces caller/callee confusion. Confirmed examples in this doc: Flow 4 step 3 (`AddGridWizard.on_create`), Flow 5 step 6 (`BuffSelectorDialog.on_ok`), Flow 13 step 5 (`start_empty`).

---

## 1. build and install SWF

Trigger: User clicks "Build & Install" button in the bottom bar or presses Ctrl+B

Steps:
1. `KazBarsApp._build()` — src/kazbars/app.py:571 — one-line delegator to `build_action.build(self)`
2. `build_action.build()` — src/kazbars/build_action.py:25 — checks `_building` re-entry guard; validates game folder, compiler path, grids list, total slot count; flags grids that would render empty (no whitelist or no static slot assignments); blocks build if Aoc.exe mode and an AoC game process is running
3. `get_profile_data()` — src/kazbars/grids_panel.py:399 — calls `save_settings()` then returns `self.grids`
4. `save_settings()` — src/kazbars/grids_panel.py:513 — iterates all `GridEditorPanel` instances, calling `save_to_config()` on each
5. `save_to_config()` — src/kazbars/grid_editor_panel.py:338 — reads every spinbox/combobox/toggle value and writes it into the grid config dict
6. `find_compiler()` — src/kazbars/build_utils.py:24 — checks three candidate paths for `mtasc.exe`; returns `Path` or `None`
7. `profile_io.do_save_profile(silent=True)` — src/kazbars/profile_io.py:206 — auto-saves the current profile (if one is loaded) before the build locks. `silent=True` suppresses the post-save "Saved: …" toast + status flash so they don't pile up against the "Built — …" toast a few steps later
8. Build is locked: `app._building = True`, build button disabled, Ctrl+B unbound
9. `compile_to_staging()` — src/kazbars/build_executor.py:33 — creates a `tempfile.mkdtemp` staging dir and calls `build_grids()`; returns `(staging_dir, (success, message))`. Forwards `include_console` (read by `build_action` from `settings['build_console']`, default `False`) and `cast_config` (read by `build_action` from `grids_panel.get_cast_timer_config()`) to `build_grids`
10. `build_grids()` — src/kazbars/grids_generator.py:489 — instantiates `CodeGenerator(..., include_console=include_console, cast_config=cast_config)`, writes `KazBars.as` and `KazBarsData.as` to a second temp dir, copies `base.swf`, calls `compile_as2()`
11. `CodeGenerator.generate()` — src/kazbars/grids_generator.py:87 — returns `(KazBars.as, KazBarsData.as)` source strings; calls `_resolve_grid()` per grid to expand primary IDs. `_data_class()` also emits `d.CUSTOMICON[<id>] = "<linkage>"` for any tracked buff in `CUSTOM_ICON_LINKAGE` (buffs AoC serves with no icon → a baked `base.swf` symbol; consumed by `KazBars_core` `loadIcon`/`attachBaked`). When `include_console=False`, `_member_variables()` and `_constructor()` skip the `console`/`consolePinned` declarations and instantiations, and `_core_methods()` substitutes the eight `{{CONSOLE_*}}` placeholders in `KazBars_core.as.template` with empty strings — the generated `KazBars.as` has zero references to `KazBarsConsole`, so MTASC doesn't pull the class from the stubs classpath. The cast-timer overlay works the same way: `include_cast_timer` (derived from `cast_config` via `cast_timer.is_enabled`, so False unless the master enable is on — the strip drives both sides together as `enableP == enableT == enabled`) gates the `castTimer:KazBarsCastTimer` declaration/instantiation, the nine `{{CAST_*}}` placeholders, and the `d.CAST` block in `KazBarsData` — off means zero `KazBarsCastTimer` references, so MTASC skips the class
12. `compile_as2()` — src/kazbars/build_utils.py:36 — assembles MTASC command with classpaths, runs subprocess, returns `(bool, stderr)`
13. **(Damage Numbers — only when enabled)** `damageinfo_generator.build_damageinfo()` — src/kazbars/damageinfo_generator.py — `build_action` loads `damageinfo_settings` up front (validating the assets exist in the pre-build checks); if `enabled`, after the grids compile it bakes the offset settings into the lean AS2 tree and MTASC-injects a copy of the pristine `DamageInfo.swf` to `staging/DamageInfo.swf` (`loading.advance_step("Baking damage numbers...")`). A bake/compile failure aborts before any install — both SWFs are staged before deploy, so nothing is partially installed. Disabled ⇒ `damageinfo_swf` stays `None`
14. `install_to_client(..., damageinfo_swf=..., damageinfo_pristine=...)` — src/kazbars/build_executor.py — calls `cleanup_legacy_files()`; copies `KazBars.swf` to `Data/Gui/Default/Flash/`; `_apply_damageinfo()` either atomically installs the staged modded `DamageInfo.swf` (capturing a one-time stock backup at `DamageInfo.swf.kazbars.bak` — seeded from the live file only when it is byte-identical to the bundled pristine stock, otherwise from the bundled pristine itself, so the backup can never capture a mod) or, when `damageinfo_swf` is `None`, restores stock from that backup; calls `write_xml_add_files()` in Aoc mode; calls `create_scripts()`
15. `create_scripts()` — src/kazbars/build_executor.py — writes `reloadgrids` and `unloadgrids`; in non-Aoc mode calls `update_script_with_marker()` to add the auto-load entry; in Aoc mode strips any old KazBars/KazBars markers from `auto_login` instead (Aoc.exe loads via xml.add)
16. `update_script_with_marker()` — src/kazbars/build_utils.py:79 — strips old KazBars marker block (and any listed legacy markers) from `auto_login`, then appends fresh block
17. Success toast (one of three, success-styled, 8 s) — src/kazbars/build_action.py — `"/reloadui in-game"` (Aoc + game running), `"launch the game"` (Aoc + not running), or `"/reloadui + /reloadgrids"` (standard launcher). The success color and the build-loading screen carry the "it worked" signal; the toast is reduced to the next-action line
18. `notify_build_done(use_aoc_bypass, app.current_profile)` — src/kazbars/grids_panel.py:323 — re-shows the in-panel tip guide with step 4 marked complete and writes a SHA-1 signature of `{profile_path, grids}` to `settings['last_build_signature']`. The path is part of the signature so cross-profile loads can't false-match. Step 4 un-ticks again the moment any subsequent edit fires `_mark_modified` (grids_panel.py); on relaunch, `load_profile_data` recomputes the signature against the loaded profile and restores step 4 only when both profile identity and grids hash match
19. `finally` block: cleans up staging dir via `shutil.rmtree`, releases `_building` flag, re-binds Ctrl+B, syncs build button state

End state: `KazBars.swf` installed under the game folder; `Scripts/reloadgrids` and `Scripts/unloadgrids` written; in non-Aoc mode `Scripts/auto_login` updated; in Aoc mode `Data/Gui/Aoc/KazBars/MainPrefs.xml.add` and `Modules.xml.add` written; when Damage Numbers is enabled the modded `DamageInfo.swf` is installed (stock backed up to `DamageInfo.swf.kazbars.bak`), and when disabled any prior mod is reverted from that backup; build loading screen shows the result summary

---

## 2. load profile from file

Trigger: User selects File > Open Profile... (or presses Ctrl+O) and confirms a `.json` path

Steps:
1. `KazBarsApp._open_profile()` — src/kazbars/app.py:553 — one-line delegator to `profile_io.open_profile(self)`
2. `profile_io.open_profile()` — src/kazbars/profile_io.py:41 — runs the unsaved-changes guard via `_check_unsaved_changes()`; opens `filedialog.askopenfilename`; composes `read_profile_file()` + `apply_profile_data()`
3. `profile_io.read_profile_file()` + `apply_profile_data()` — src/kazbars/profile_io.py:72 + 84 — split as of 2026-04-27 to make the boss-timer fan-out visible at every call site. `read_profile_file` is pure I/O (returns `(data, is_corrupt)`); `apply_profile_data` dispatches grids, missing-buff warning, boss-timer (when alive), reference_resolution, current_profile, settings, title. See step 8 for the boss-timer dispatch detail.
4. `load_profile_data(grids, profile_path)` — src/kazbars/grids_panel.py:451 — iterates raw grid dicts; migrates, validates, rebuilds panel list; restores `_build_done` from `settings['last_build_signature']` when both the profile path and grids hash match; returns `{grid_name: [missing_refs]}` for buffs that couldn't be resolved
5. `_migrate_grid()` — src/kazbars/grids_panel.py:434 — normalizes legacy `int` IDs and legacy name strings in `whitelist` and `slotAssignments` to current primary spell IDs via `database.by_id` and `database.get_entry_by_name`
6. `validate_grid()` — src/kazbars/grid_model.py:85 — fills missing keys from `create_default_grid()`; clamps every numeric field against `CLAMP_SPECS`; coerces enums in `ENUM_SPECS`; coerces booleans and lists/dicts
7. `refresh_panels()` — src/kazbars/grids_panel.py:558 — destroys existing `GridEditorPanel` widgets; creates new ones for the validated list; shows empty state if list is empty
8. If a Boss Timer panel is alive, `LiveTrackerPanel.load_profile_data()` — src/kazbars/live_tracker_panel.py:478 — applies the embedded `boss_timer.overlay` settings to the overlay (`apply_settings` then propagates opacity, font, transparent, lock, x/y/width/height, and visible state through `set_*(..., notify=False)` calls, with a single `_notify_settings_changed()` at the end so the parent saves once)
9. `warn_missing_buffs()` — src/kazbars/profile_io.py:122 — if migration dropped any references, displays them (deferred 200ms when called during startup so the dialog doesn't race the welcome popup)
10. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` path to `kazbars_settings.json` via atomic temp-rename in `safe_save_json` (src/kazbars/settings_manager.py:33)

End state: `GridsPanel` displays validated grid cards; `app.modified` is `False`; `last_profile` updated in settings; window title reflects loaded name

---

## 3. save profile to file

Trigger: User selects File > Save Profile (Ctrl+S) or File > Save Profile As...

Steps:
1. `KazBarsApp._save_profile()` — src/kazbars/app.py:559 — one-line delegator to `profile_io.save_profile(self)`
2. `profile_io.save_profile()` — src/kazbars/profile_io.py:141 — routes to `do_save_profile(app, current_path)` if a path exists, or to `save_profile_as()` otherwise
3. `profile_io.do_save_profile(silent=False)` — src/kazbars/profile_io.py:206 — orchestrator: `build_profile_payload()` → `write_profile_file()` → `_commit_saved_profile(silent=silent)`, with try/except for `OSError`. The `silent` flag (default `False` for direct save; `True` for the pre-build piggyback save in Flow 1) suppresses the post-commit toast + status flash. Note: the `boss_timer` key is pulled from the live tracker (when one is open) inside `build_profile_payload()` (src/kazbars/profile_io.py:169) — see step 7.
4. `get_profile_data()` — src/kazbars/grids_panel.py:399 — calls `save_settings()` then returns `self.grids`
5. `save_settings()` — src/kazbars/grids_panel.py:513 — iterates all `GridEditorPanel` instances calling `save_to_config()`
6. `save_to_config()` — src/kazbars/grid_editor_panel.py:338 — reads all widget values into the grid config dict
7. If a Boss Timer panel is alive, `LiveTrackerPanel.get_profile_data()` — src/kazbars/live_tracker_panel.py:473 — returns `{'overlay': {...}}` for embedding
8. `safe_save_json()` — src/kazbars/settings_manager.py:33 — writes JSON to `path.tmp` then `Path.replace`-renames it over the target atomically
9. `app.settings.set('last_profile', ...)` then `app.settings.save()` — persists `last_profile` to `kazbars_settings.json`

End state: profile `.json` written atomically; `app.modified` is `False`; title bar reflects saved name; toast `Saved: <filename>` shown and status bar pulses (both suppressed when `silent=True`, e.g. the pre-build auto-save path)

---

## 4. add new grid via wizard

Trigger: User clicks "+ Add Grid" button on the grids panel toolbar (also reachable from the empty-state "Custom" preset card)

Steps:
1. `add_grid()` — src/kazbars/grids_panel.py:535 — checks the slot budget against `MAX_TOTAL_SLOTS` (64); opens `AddGridWizard` dialog
2. `AddGridWizard.__init__()` — src/kazbars/grid_dialogs.py:80 — builds wizard UI with name, source/mode/dimension fields and four preset shape buttons; calls `restore_window_position()`
3. `AddGridWizard.on_create()` — src/kazbars/grid_dialogs.py:301 — validates name (non-empty, unique, optional special-char warning), enforces slot budget; calls `create_default_grid()`
4. `create_default_grid()` — src/kazbars/grid_model.py:48 — returns a complete grid config dict populated with caller-specified `grid_type`, `rows`, `cols`, `mode`, `grid_id`; auto-coerces `1×1` to static mode and picks a sensible `fillDirection`
5. `refresh_panels()` — src/kazbars/grids_panel.py:558 — destroys and recreates all `GridEditorPanel` cards; the newly added card is initially expanded

End state: new grid config appended to `self.grids`; new `GridEditorPanel` card visible and expanded; slot count label updated; profile marked modified

---

## 5. select tracked buffs for a dynamic grid

Trigger: User clicks "Tracked Buffs..." on a dynamic-mode `GridEditorPanel` (the same button shows "Slot Assignments" in static mode and routes to a different dialog)

Steps:
1. `_on_mode_btn_click()` — src/kazbars/grid_editor_panel.py:412 — dispatches to `edit_whitelist()` when grid is in dynamic mode (or `edit_slots()` for static)
2. `edit_whitelist()` — src/kazbars/grid_editor_panel.py:418 — flushes current widget state via `save_to_config()`; opens `BuffSelectorDialog`
3. `BuffSelectorDialog.__init__()` — src/kazbars/grid_dialogs.py:347 — resolves initial `whitelist` primary IDs to entry names via `database.by_id`; restores last-used category/type filter from settings; calls `refresh_lists()`
4. `BuffDatabase.search()` — src/kazbars/buff_database.py:64 — filters `grouped_buffs` by query/category/type; sorts by type then name
5. `BuffSelectorDialog.refresh_lists()` — src/kazbars/grid_dialogs.py:457 — repopulates Available and Selected listboxes; per-row foreground tinted by buff type (`THEME_COLORS['type_debuff']`/`type_misc`) to mirror the Database editor; selected entries sort by type when the grid `layout` is `buffFirst` or `debuffFirst`, alphabetically when `mixed`
6. `BuffSelectorDialog.on_ok()` — src/kazbars/grid_dialogs.py:544 — saves filter state; maps each selected name back to `entry['ids'][0]` via `database.get_entry_by_name()`; sets `self.result`
7. `update_labels()` — src/kazbars/grid_editor_panel.py:377 — refreshes whitelist count and buff-name preview text in card header

End state: `grid_config['whitelist']` updated with new primary spell ID list; panel header shows new buff count and preview names

---

## 6. first-launch setup with defaults

Trigger: `KazBarsApp.__init__` detects no `game_path` in settings; schedules 100ms after `deiconify()`

Steps:
1. `_show_first_launch_dialog()` — src/kazbars/app.py:604 — one-line delegator to `run_first_launch(self, APP_NAME)`
2. `run_first_launch()` — src/kazbars/first_launch.py:300 — defines the `on_game_set`, `on_aoc_bypass_set`, `on_load_default`, `on_resolution_set`, `on_dialog_closed` closures; calls `show_first_launch_dialog()`
3. `show_first_launch_dialog()` — src/kazbars/first_launch.py:34 — builds modal dialog with game folder entry, common-paths shortcuts, an Aoc.exe Yes/No section (revealed on demand), resolution picker, and two option cards ("Use Defaults" / "Start Empty")
4. `detect_aoc_launcher()` — src/kazbars/build_executor.py:151 — called whenever the path entry changes; checks for `aoc.exe` or `Aoc.log` under `Data/Gui/Aoc/`; reveals the Aoc.exe radio group if found
5. `on_load_default()` — src/kazbars/first_launch.py:321 — closure: persists game path, Aoc.exe preference, and resolution **before** loading the profile so the auto-scale inside `apply_profile_data()` reads the just-saved `game_resolution`; composes `read_profile_file()` + `apply_profile_data()` against `Default.json`; saves a personal copy as `profiles/MyGrids.json` (auto-incremented on collision); stashes data for the welcome popup
6. `profile_io.read_profile_file()` + `apply_profile_data()` — src/kazbars/profile_io.py:72 + 84 — reads `Default.json` (pure I/O), then dispatches grids to `grids_panel.load_profile_data()`, populates `app.reference_resolution` from the JSON, **auto-scales via `grids_panel.scale_to_resolution()` if the profile's reference differs from `game_resolution`**, anchors `current_profile` to None for the bundled default
7. `GridsPanel.scale_to_resolution()` — src/kazbars/grids_panel.py:518 — anchor-based scaling (X center-anchored, Y bottom-anchored) via `grid_model.scale_grid_position()`; clamps to `SCREEN_MAX_X`/`SCREEN_MAX_Y` (8K sanity caps) and floors at 0; calls `refresh_panels()`
8. `profile_io.do_save_profile()` — src/kazbars/profile_io.py:206 — writes scaled profile to `profiles/MyGrids.json`
9. `on_dialog_closed()` — src/kazbars/first_launch.py:351 — closure called when the dialog is destroyed; if the user took the defaults path, schedules `show_welcome_popup()` 100ms later

End state: `game_path`, `use_aoc_bypass`, and `game_resolution` persisted; default profile loaded, anchor-scaled to resolution, saved as `profiles/MyGrids.json`; welcome popup shown after the dialog closes

---

## 7. save buff database

Trigger: User clicks the "Save Database" button in the Database view's toolbar (no menu item, no keyboard shortcut — Ctrl+S is bound to profile save)

Steps:
1. `DatabaseEditorTab.save()` — src/kazbars/database_editor.py:701 — resolves `assets_path / "Database.json"`; calls `BuffDatabase.save()`
2. `BuffDatabase.save()` — src/kazbars/buff_database.py:132 — serializes `self.buffs` into v2 JSON format (`{version: 2, description, buffs}`); writes to file directly (not atomic)

End state: `assets/kazbars/Database.json` updated; `DatabaseEditorTab.modified` set to `False`; toast `Database saved` shown

---

## 8. add buff to database

Trigger: User clicks "Add" in the `DatabaseEditorTab` toolbar (Database view)

Steps:
1. `DatabaseEditorTab.add_buff()` — src/kazbars/database_editor.py:577 — builds the validator via `_make_buff_validator()` (no args for add: checks ID collision and name uniqueness against the full DB); opens `BuffEditDialog`
2. `BuffEditDialog.__init__()` — src/kazbars/database_editor.py:51 — builds form with name, IDs (multi-line), category combobox, type radio group, and the stacking section (toggle + partial + start/end spinboxes); calls validator on submit
3. `BuffDatabase.add_buff()` — src/kazbars/buff_database.py:106 — appends the new entry dict to `self.buffs`; calls `_rebuild_indexes()`
4. `BuffDatabase._rebuild_indexes()` — src/kazbars/buff_database.py:50 — rebuilds `by_id`, `by_name`, `categories`, `grouped_buffs` from the full `buffs` list
5. `DatabaseEditorTab._after_db_change()` — src/kazbars/database_editor.py:571 — post-mutation hook: marks the editor dirty, refreshes the category dropdown, and redraws the tree via `refresh_list()` (used uniformly by add/edit/delete/import/rename-category)

End state: new buff entry visible in treeview; `by_id` and `by_name` indexes updated; toast `Added: <name>` shown; `DatabaseEditorTab.modified` set to `True`

---

## 9. uninstall from game folder

Trigger: User selects Game > Uninstall from game client... and confirms the dialog

Steps:
1. `KazBarsApp._uninstall_game()` — src/kazbars/app.py:493 — one-line delegator to `game_folder.uninstall_game(self)`
2. `game_folder.uninstall_game()` — src/kazbars/game_folder.py:149 — guards on `app.game_path`; confirms with the user; calls `uninstall_from_client()`
3. `uninstall_from_client()` — src/kazbars/build_executor.py — deletes `Data/Gui/Default/Flash/KazBars.swf`, the `Data/Gui/Aoc/KazBars/` directory (if present), and `Scripts/reloadgrids` + `Scripts/unloadgrids`; strips the auto-load marker block from `Scripts/auto_login`; if a `DamageInfo.swf.kazbars.bak` exists (Damage Numbers was installed), restores the stock `DamageInfo.swf` from it and removes the backup; if the backup is missing but a modded `DamageInfo.swf` remains, restores stock from the bundled pristine copy instead so uninstall never leaves a modded core file
4. `strip_marker_block()` — src/kazbars/build_utils.py:60 — removes the `# KazBars auto-load` marker-delimited section (marker line through the next blank line) from the `auto_login` file content; the script is rewritten or, if empty after the strip, deleted

End state: `KazBars.swf`, the Aoc xml.add module folder, the reload scripts, and the auto-load marker block are all removed; toast lists what was removed (or notes nothing was installed)

---

## 10. open live tracker panel

Trigger: User clicks the "⏱ Ethram-Fal" button in the bottom bar (right side, next to Build & Install)

Steps:
1. `_open_boss_timer()` — src/kazbars/app.py:450 — checks `_boss_timer_if_alive()`; if a panel exists, deiconifies/lifts/restores the overlay; otherwise constructs a new `LiveTrackerPanel`
2. `LiveTrackerPanel.__init__()` — src/kazbars/live_tracker_panel.py — runs the one-shot `_migrate_window_position_key()` (renames legacy `window_pos_boss_timer` → `window_pos_live_tracker`); sets `transient(parent)`; restores window position; calls `load_settings()`; builds UI; creates overlay and **registers it with the app's `ForegroundWatcher`** (the single shared focus gate, owned by `KazBarsApp`, that hides every overlay whenever neither KazBars nor AoC is foreground); constructs `BossTimer` and `CombatLogMonitor`; auto-detects log path
3. `load_settings()` — src/kazbars/live_tracker_settings.py:169 — runs the one-shot `_migrate_legacy_filename()` (renames legacy `timers_settings.json` → `live_tracker_settings.json`); reads `live_tracker_settings.json` from the settings folder; returns dict validated against `TIMERS_DEFAULTS` and `TIMERS_RANGES`
4. `BossTimer.__init__()` — src/kazbars/boss_timer.py:53 — initializes cycle state fields and `_last_phase = None` (the source-side dedupe cache); stores `LiveTrackerPanel._dispatch_overlay_update` (src/kazbars/live_tracker_panel.py:151) as `_update_callback` — that method hops cross-thread updates onto the Tk main loop via `self.after(0, partial(_apply_overlay_update, phase))` (src/kazbars/live_tracker_panel.py:157)
5. `CombatLogMonitor.__init__()` — src/kazbars/combat_monitor.py:42 — initializes daemon thread state; stores the `boss_timer` reference
6. `TimerOverlay.__init__()` — src/kazbars/timer_overlay.py — builds an `OverlayConfig` from settings and constructs a `HudOverlay` (shared backdrop + lock dot + drag over `LayeredOverlay`); supplies `_render_content` (two text rows + cycle-timer dock; an 8-direction stroke keeps text legible) and `_measure` (font-derived auto-size — no resize handle). Hidden on open (Hide-on-Stop) — Start shows it
7. `LiveTrackerPanel._update_log_path()` — src/kazbars/live_tracker_panel.py — calls `combat_monitor.set_log_folder()` with the current game path; sets the overlay's waiting-state footer to the sanitized log name (`CombatLog_2152`)
8. `CombatLogMonitor.set_log_folder()` — src/kazbars/combat_monitor.py:59 — finds latest `CombatLog*.txt` in the game folder; records file end position as `last_position`

End state: `LiveTrackerPanel` window visible; `TimerOverlay` hidden until Start (focus-gated by the app-owned `ForegroundWatcher` via `foreground.app_or_game_foreground()`, shared with the Deeps overlay); `CombatLogMonitor` ready with log folder set; panel shows monitor + sanitized log status

---

## 11. start combat log monitoring

Trigger: User clicks "Start Monitoring" button in `LiveTrackerPanel`

Steps:
1. `LiveTrackerPanel._start_monitoring()` — src/kazbars/live_tracker_panel.py — re-runs `_update_log_path()`; calls `combat_monitor.start_monitoring()` (needs only a game folder — it waits for a log if AoC hasn't created today's yet, so no "no log" bail); shows the overlay; disables Test Cycle so the two modes are mutually exclusive. Reached via the single Start↔Stop toggle (`_on_start_stop_click`)
2. `CombatLogMonitor.start_monitoring()` — src/kazbars/combat_monitor.py:105 — sets `monitoring=True`; spawns the `CombatLogMonitor` daemon thread running `_monitor_loop()`
3. `BossTimer.push_waiting_state()` — src/kazbars/boss_timer.py:214 — builds the idle phase dict via `_phase()`, caches it on `_last_phase`, and fires `_update_callback(phase)`
4. `LiveTrackerPanel._dispatch_overlay_update()` — src/kazbars/live_tracker_panel.py:151 — named cross-thread dispatcher; queues `partial(_apply_overlay_update, phase)` on the Tk main loop via `self.after(0, ...)`. `_apply_overlay_update()` (src/kazbars/live_tracker_panel.py:157) calls `self.overlay.update_display(phase)` if the overlay still exists
5. `TimerOverlay.update_display()` — src/kazbars/timer_overlay.py:173 — accepts the phase dict; short-circuits when it equals `_display_state`; otherwise stores it and calls `self._hud.request_paint()`. The shared `HudOverlay` repaints by invoking the overlay's `_render_content()` (src/kazbars/timer_overlay.py:293) — two text rows + cycle-timer dock drawn with an 8-direction stroke — sized by `_measure()` (src/kazbars/timer_overlay.py:286). (The old per-canvas `_redraw_text_canvas`/`_redraw_cycle_timer` split is gone since the `HudOverlay` port.)
6. `LiveTrackerPanel._start_game_loop()` — src/kazbars/live_tracker_panel.py:346 — schedules `_run_game_tick()` (src/kazbars/live_tracker_panel.py:350) on a `GAME_TICK_MS` (50 ms) recurring `after()` cadence; each tick calls `boss_timer.update_display()` and re-schedules itself

End state: `CombatLogMonitor` daemon thread running; 50ms UI poll active; overlay displays "Waiting for Seed..."

---

## 12. combat log trigger detected

Trigger: `CombatLogMonitor` daemon thread reads a new log line containing "Viscous Seed", "Lotus Fixation", or "Syphon hits"

Steps:
1. `CombatLogMonitor._monitor_loop()` — src/kazbars/combat_monitor.py — polls the log every 100ms; checks every ~3s for a newer log file (auto-switches, dropping the stale one); waits (scanning) if no log exists yet; handles truncation/rotation; reads bytes since `last_position`; dispatches matching lines to `_process_line()`
2. `CombatLogMonitor._process_line()` — src/kazbars/combat_monitor.py:240 — identifies trigger type (Syphon → `start_syphon`, Viscous Seed from Ethram-Fal → `start_cycle`, Lotus Fixation from Emerald Lotus → `update_fixation`); extracts player name (or "YOU") from the line text via `_extract_player()`
3. `BossTimer.start_cycle()` — src/kazbars/boss_timer.py:90 — calls `_reset_cycle_state()` then sets `timer_active=True`; records `cycle_start_time` and `seed_player`; detects double-seed (P4) when called 5–12s after the previous seed for the same player
4. `BossTimer.update_display()` — src/kazbars/boss_timer.py:191 — called from the 50 ms UI loop; calls `get_current_phase()`; compares the result to the cached `_last_phase` and short-circuits if equal (skips ~19 of every 20 ticks once the integer second is steady), otherwise fires `_update_callback(phase)` with the new dict
5. `LiveTrackerPanel._dispatch_overlay_update()` — src/kazbars/live_tracker_panel.py:151 — named cross-thread dispatcher; queues `partial(_apply_overlay_update, phase)` on the Tk main loop via `self.after(0, ...)`. `_apply_overlay_update()` (src/kazbars/live_tracker_panel.py:157) calls `self.overlay.update_display(phase)` if the overlay still exists
6. `TimerOverlay.update_display()` — src/kazbars/timer_overlay.py:173 — dedupe (skip when `phase == _display_state`); on a real change, stores the phase and calls `self._hud.request_paint()`. The shared `HudOverlay` then repaints via `_render_content()` (src/kazbars/timer_overlay.py:293) — per-row message colors with an 8-direction outline stroke, and `COLORS["default"]` for the cycle timer

End state: overlay displays the active seed/fixation/syphon phase with elapsed timer text updated on the next 50ms poll

---

## 13. first-launch setup with empty start

Trigger: User completes the first-launch dialog by clicking "Start Empty" instead of "Use Defaults"

Steps 1–4 are identical to Flow 6 (delegator → `run_first_launch()` → `show_first_launch_dialog()` → `detect_aoc_launcher()`).

Steps:
5. `start_empty()` — src/kazbars/first_launch.py:193 — closure: calls `_set_game_if_provided()`, then `_close()`. No `on_load_default` invocation, so no profile load and no scale.
6. `_set_game_if_provided()` — src/kazbars/first_launch.py:174 — same dispatcher used by Flow 6's `load_default()`; persists game path via `on_game_set`, Aoc.exe preference via `on_aoc_bypass_set`, resolution via `on_resolution_set`
7. `on_dialog_closed()` — src/kazbars/first_launch.py:351 — runs as in Flow 6 but `welcome_data` was never populated, so the welcome popup is suppressed

End state: `game_path`, `use_aoc_bypass`, and `game_resolution` persisted; no profile loaded; no welcome popup; user lands on the empty `GridsPanel` empty-state

---

## 14. change game folder (with Aoc.exe reconcile)

Trigger: User selects Game > Change game folder... from the menu, OR left/right-clicks the path label in the bottom bar and picks "Change game folder..." from the context menu

Steps:
1. `KazBarsApp._show_game_context_menu()` — src/kazbars/app.py:490 — one-line delegator to `game_folder.show_game_context_menu(self, event)`
2. `show_game_context_menu()` — src/kazbars/game_folder.py:117 — pops `app._game_context_menu` at the event coordinates; both `<Button-1>` and `<Button-3>` route here
3. User picks "Change game folder..." → `KazBarsApp._change_game_folder()` — src/kazbars/app.py:481 — one-line delegator to `game_folder.change_game_folder(self)`. (When triggered via Game menu the cascade invokes the same delegator directly, skipping steps 1-2.)
4. `change_game_folder()` — src/kazbars/game_folder.py:63 — opens `filedialog.askdirectory`; validates AoC folder structure (warns if `Data/Gui/Default` is missing); warns if the resulting `KazBars.swf` path exceeds 240 characters
5. `save_game_path()` — src/kazbars/game_folder.py:122 — persists `game_path` to settings; calls `grids_panel.notify_game_path_changed()` so the panel can refresh
6. **Reconcile (only when `resolved != previous`)**: `detect_aoc_launcher()` — src/kazbars/build_executor.py:151 — checks for `aoc.exe` or `Aoc.log` under `Data/Gui/Aoc/`. Two state-divergence branches fire:
   - **Aoc.exe newly present** (`has_aoc=True, use_aoc_bypass=False`) → `prompt_aoc_bypass()` — src/kazbars/game_folder.py:139 — modal yes/no; answer is persisted via `save_aoc_bypass()`
   - **Aoc.exe newly absent** (`has_aoc=False, use_aoc_bypass=True`) → `save_aoc_bypass(app, False)` (src/kazbars/game_folder.py:132) and `app_toast(app, "Aoc.exe not found in this folder — bypass mode disabled.", 'info', 8)`
7. `refresh_game_path_label()` — src/kazbars/game_folder.py:36 — updates the path label text/tooltip and calls `update_build_state()` to re-enable or disable the Build button based on the new path's existence

End state: `game_path` and (when divergence triggered it) `use_aoc_bypass` persisted; path label updated; Build button state synced; if state diverged, the user has either confirmed bypass via the prompt or seen the auto-disable toast

---

## 15. open Buff Display editor and apply

Trigger: User selects Game > Default buff bars… from the menu

Steps:
1. `KazBarsApp._open_buff_display_editor()` — src/kazbars/app.py:496 — one-line delegator to `buff_display_editor.open_buff_display_editor(self)`
2. `open_buff_display_editor()` — src/kazbars/buff_display_editor.py:567 — pre-flight: validates `app.game_path` is set and points to a real directory; on miss, shows a `Messagebox.show_warning` (the only modal in this module — toast can't render before the dialog exists) and returns
3. `BuffDisplayDialog.__init__()` — src/kazbars/buff_display_editor.py:407 — `withdraw → transient → grab_set`; calls `_create_widgets()`; restores window position; binds `<Escape>` → `_on_cancel`, `<Return>` → `_on_apply`, `WM_DELETE_WINDOW` → `_on_close`; schedules `_set_initial_focus()` via `after_idle` so the toggle widget is fully realized
4. `_create_widgets()` — src/kazbars/buff_display_editor.py:455 — packs CRT-styled header, plain-language subtitle, conditional custom-UI banner; **bottom button row packs first** (`side='bottom'`) so it reserves height before body claims expansion (Cancel + Apply stay visible at any window size); **scrollable body** wraps the section iteration via `create_scrollable_frame`; reads `SETTINGS_KEY_SECTION_OPEN` for per-section open/closed state
5. For each entry in `BUFF_FILES` (Player, Target, Top, Floating): `_Section.load()` — src/kazbars/buff_display_editor.py:147 — resolves Customized→Default→None precedence via `_resolve_paths`; reads source XML and caches it on `self._source_text` for later reuse by `write_to_disk`; calls `_read_bufflistview()` (regex match on `<BuffListView ... />`, optionally inside a `<!--KZ_OFF ... KZ_OFF-->` wrapper); sets `state` to `STATE_OK / STATE_MISSING / STATE_UNSUPPORTED`; calls `_populate_vars()` which mirrors source byte-for-byte (blank field when attr is missing or unrecognised — no stock defaults)
6. `_Section.build(parent, initial_open)` — src/kazbars/buff_display_editor.py:201 — builds a `CollapsibleSection` per entry with `initial_open` from saved settings (default: Player open, rest collapsed); badge label packs to `cs.header_frame` side='right' so status stays visible whether expanded or collapsed; form rows or inline state message (via `_render_inline_message`) pack into `cs.content`
7. User edits a field → spinbox `command=` or `<KeyRelease>` fires `_Section._on_change()` → snapshot guard early-returns when `_snapshot()` matches `_last_snapshot` (so non-mutating keystrokes do no work); on a real change: applies disabled-style, refreshes filter hint, refreshes badge, calls dialog's `_refresh_apply_state()` which only re-configures the Apply button when its enabled-state actually flips
8. User clicks Apply → `BuffDisplayDialog._on_apply()` — src/kazbars/buff_display_editor.py:519 — collects sections where `dirty()` is True; for each: `write_to_disk()` then `load_after_write()`
9. `_Section.write_to_disk()` — src/kazbars/buff_display_editor.py:347 — reuses `self._source_text` cached at load time (falls back to disk read if missing); builds attrs dict from form values via the `int_specs` table (only non-blank fields land in attrs; numerics clamped to `ICON_SIZE_MIN/MAX` etc. so a typed 999 can't reach the file); calls `_write_bufflistview()`
10. `_write_bufflistview()` — src/kazbars/buff_xml.py:152 — unwraps any `KZ_OFF` span; for each attr in attrs dict: skips when on-disk value already equals new value (keeps file byte-identical for untouched fields); else `_replace_attr()` either replaces existing value or **injects before the closing `/>`** when the attr is missing (the source XML doesn't always carry every attr — most stock files have no `filter`); re-wraps in `KZ_OFF` if `enabled=False`
11. `_backup_once()` — src/kazbars/buff_xml.py:182 — copies the existing Customized file to `*.kazbars.bak` once (idempotent — skips if backup already exists)
12. Customized file written via `Path.write_text` (parent dirs created)
13. `_Section.load_after_write()` — src/kazbars/buff_display_editor.py:384 — flips `source_path` to the now-existing Customized file; re-reads, refreshes `_source_text`/`_baseline`/`_last_snapshot`, and updates the badge to `[Customized]`
14. Per-result toast via `app_toast`: success → `Saved: <names>` (`'success'`, default 6 s); failure → `Couldn't write <names>. Check folder permissions and disk space.` (`'danger'`, 10 s, `key='buff_apply_failed'` so retries coalesce); OS reasons go to the logger
15. User closes dialog (X button, Escape, Cancel, or any path that hits `WM_DELETE_WINDOW`) → `BuffDisplayDialog._on_close()` — src/kazbars/buff_display_editor.py:552 — calls `_save_section_states()` (writes a per-label `is_open` dict to `settings[SETTINGS_KEY_SECTION_OPEN]`), then `destroy()`. Apply alone does not destroy the dialog — the user keeps editing.

End state: changed sections written to `<game>/Data/Gui/Customized/Views/HUD/<file>.xml` (Player → CharPortraitLeft.xml, Target → CharPortraitRight.xml, Top → HUDView.xml, Floating → FloatingPortraitView.xml) with surgical regex edits and one-shot backups; section open/closed state persisted to `kazbars_settings.json`; user types `/reloadui` in-game to see the changes.

---

## 16. change game resolution

Trigger: User selects Game > Game resolution... from the menu

Steps:
1. `KazBarsApp._change_game_resolution()` — src/kazbars/app.py:484 — one-line delegator to `game_resolution.change_game_resolution(self)`
2. `change_game_resolution()` — src/kazbars/game_resolution.py:32 — reads current `game_resolution` setting via `get_game_resolution_or_default()`; builds a modal `Toplevel` with combobox of `["1920x1080", "2560x1440", "3840x2160"]` plus the OS-detected screen res prepended if not already in the list
3. User picks a value and clicks Apply → `_apply()` closure inside the dialog
4. `parse_resolution()` — src/kazbars/grid_model.py:122 — converts the chosen `"WxH"` string into `(w, h)`; on parse failure the dialog just closes
5. **No-op short-circuit**: if `(new_w, new_h) == (current_w, current_h)`, dialog closes without scaling or persisting
6. `GridsPanel.scale_to_resolution()` — src/kazbars/grids_panel.py:518 — anchor-scales every loaded grid's `x`/`y` from the previous game_resolution to the new one via `scale_grid_position()`; clamps to sanity caps; calls `refresh_panels()` so editor cards rebuild with the new spinbox max as well
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
3. `DeepsPanel.__init__()` — src/kazbars/deeps_panel.py — `restore_window_position("deeps", …)`; loads `deeps_settings.json` via `load_settings()`; constructs `DeepsMeter()` (not started); passes `include_pet_damage` + `set_window_seconds(window_seconds)` from settings into the meter; builds the UI via the shared `ui_forms` settings-panel builders + `ui_headers` (CRT header via `ui_headers.create_dialog_header`, status block, single Start↔Stop toggle, Overlay row with Lock + layout radio, Appearance card with size & background sliders — font is fixed to Segoe UI, no picker — Readout card with Window dropdown + a Style preset radio (Live / Steady / Calm, each bundling smoothing/round_step/refresh_ms), Overlay-cells picker, Alarm & Tints card with a DPS-out alarm **slider** (1000–4000/s band, 50/s step, live `/s` readout, built via `ui_forms.create_slider_row` with `value_width=7`) + Standard/Tank **survival-tint preset radios** + a live breakpoint caption (the four ΔHP-in tint thresholds are driven by the preset via `normalize_survival_preset`, not set individually), pet checkbox + note); calls `_create_overlay()` to build the hidden `DeepsOverlay`, **register it with the app's `ForegroundWatcher`**, and push the initial thresholds via `_push_thresholds()`; renders the initial idle status line.
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
2. `open_backup_dialog(app)` — src/kazbars/settings_backup.py — builds a modal `Toplevel`; `locate_funcom_prefs()` resolves `%LOCALAPPDATA%\Funcom\Conan\Prefs`; `_funcom_summary()` returns the account names (the prefs dir's immediate subfolders), the character count (`Char*` subfolders across all accounts), and total size; counts `*.json` under `app.profiles_path`; renders the "What's included" lines (account names listed, KazBars settings noted as app/Deeps/Live Tracker), the "Close AoC first" warning, and Back up… / Restore… / Close buttons.
3a. **Back up** → `backup_settings(app, dialog)` — `filedialog.asksaveasfilename` (default `KazBars_Backup_{date}.zip`) → `write_backup_zip()` archives the Funcom prefs tree under `funcom/` + `app.profiles_path` under `kazbars/profiles/` + the whole `app.settings_path` dir (`kazbars_settings.json` + `deeps_settings.json` + `live_tracker_settings.json`) under `kazbars/settings/`, skipping `*.tmp` and writing `manifest.json` last → dialog closes → `app_toast()` success with the file counts.
3b. **Restore** → `restore_settings(app, dialog)` — `filedialog.askopenfilename` → `read_manifest()` rejects anything that isn't a KazBars backup → `Messagebox.yesno` confirm (+ AoC-closed warning) → best-effort pre-restore snapshot via `write_backup_zip()` to `app.app_path/KazBars_PreRestore_{timestamp}.zip` → `restore_zip()` extracts each section to its destination (`funcom_prefs_path()` for `funcom/`, `app.app_path` for `kazbars/`), creating dirs as needed and skipping zip-slip entries → `app.settings.reload()` (src/kazbars/settings_manager.py) resyncs in-memory settings from disk so the restored file isn't clobbered on exit → `Messagebox.show_info` reports the restored counts + snapshot path.

End state: backup writes a single portable zip (AoC prefs + KazBars profiles/settings); restore replaces both in place after snapshotting the prior state, with a KazBars restart recommended to fully apply the restored window/game-folder settings.

---

## 20. open Damage Numbers panel and tune settings

Trigger: User selects Game ▸ Damage numbers… from the menu, then adjusts a control in the panel that opens.

Steps:
1. `KazBarsApp._open_damage_numbers()` — src/kazbars/app.py — one-line delegator to `open_damage_numbers_panel(self)`. Mirrors `_open_deeps_panel`.
2. `open_damage_numbers_panel(app)` — src/kazbars/damageinfo_panel.py — single-instance gate: if `app.damage_numbers_panel` exists and `winfo_exists()`, deiconify + lift + focus and return; otherwise construct a fresh `DamageNumbersPanel(app, app.settings_path)`.
3. `DamageNumbersPanel.__init__()` — src/kazbars/damageinfo_panel.py — `restore_window_position("damage_numbers", …)`; loads `damageinfo_settings.json` via `load_settings()`; builds the UI (CRT header, tip bar, master Enable checkbutton, then a scrollable body of cards — Presets / Distance / Shadow / Size / Animation / Above-target position / Fixed columns / Zig-zag / Behavior — built from `damageinfo_settings.GLOBAL_SETTINGS` metadata); `_sync_enabled_state()` greys every control when the master toggle is off; `WM_DELETE_WINDOW` → destroy.
4. User drags a slider → `_on_slider(key, raw)` quantizes to the key's step (`validate_setting`), stores the offset in `self.settings`, and updates the right-side readout to the **resulting game value** (`compute_final_value`), not the raw offset. Commit (button/key release) → `_save()` writes `damageinfo_settings.json`. Enum radios / bool checkboxes save immediately on change; `shadow_mode`/`fixed_col_split` also re-run their sub-gates (`_sync_shadow_state` greys shadow offset/blur by mode; `_sync_split_state` greys Column B when split is off).
5. Preset buttons → `_apply_preset(name)` overlays the `PRESETS` bundle (`damageinfo_settings.apply_preset`), saves, and `_refresh_all()` re-syncs every widget + readout to the new values.

End state: `damageinfo_settings.json` reflects the chosen offsets + `enabled` flag. Nothing is applied in-game yet — the values bake into a modded `DamageInfo.swf` on the next Build & Install (Flow 1, steps 13–14); with the master toggle off, the build leaves AoC's stock file in place (reverting any prior mod).
