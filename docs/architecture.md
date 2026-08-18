# Architectural Map

**Current as of:** 2026-08-18 (P11: the build-staleness row — `profile_document.build_signature` hashes the BUILD-lane sections; a successful Build & Install records `prefs.last_build` `{profile_id, profile_name, hash, target_resolution}`; `GridsPanel.refresh_build_status` shows a quiet "In game: …" line under the extras cards that flips stale on any BUILD edit, extras toggle, profile switch, or resolution change — no modal anywhere. The two PATCH editors gained a sync hint diffing the profile's section vs `prefs.last_patch` (`_diverged()` also enables Apply, so "Apply to sync" works with zero staged edits); every grid-card widget now arms the profile autosave (`GridEditorPanel._notify_edit` → `GridsPanel._mark_modified`), and Ctrl+S / app close / Build & Install gather the panel (`_on_grids_edited`) before flushing. Before that, P9: the first PATCH-lane, sparse `PROFILE_SECTION`s — `damage_colors` (src/kazbars/damageinfo_settings.py) and `buff_bars` (src/kazbars/buff_xml.py) — hold only the fields a profile explicitly *overrides* in `TextColors.xml`/the HUD buff-bar XMLs (`{}` default, absent field = "no opinion"; never dispatched on a profile switch, only on the XML editor's own Apply). `damageinfo_colors_panel`/`buff_display_editor` track override state per row/field: an edit creates an override, Apply writes only overridden fields (was: every populated field), and the colors panel's ↺ is context-sensitive — inherited rows stage the game default (creating an override), overridden rows un-override by restoring the pre-KazBars `.kazbars.bak` snapshot. `prefs.last_patch` (new, additive) mirrors what a PATCH section actually wrote to a given game folder, written by `prefs.record_last_patch()` — a machine-local fact a later phase diffs against the active profile's own section to show unapplied changes.
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
- `ui_widgets` is the leaf "core glue": `blend_alpha`, `add_tooltip` (+ `_InAppToolTip`), `app_toast`, `flash_status_bar`, `debounced_callback`, and the event-binding helpers (`bind_card_events`, `bind_button_press_effect`, `bind_label_hover_colors`, `bind_label_press_effect`). Imports nothing from the three siblings below — they depend on it, not the reverse, so no cycles.
- `ui_headers` builds the headers: `create_dialog_header`, `create_app_header`, `update_app_header_color`, `create_tip_bar`. Imports `blend_alpha` from `ui_widgets`.
- `ui_forms` builds the form fields + settings-panel builders: `labeled_spinbox`/`labeled_combobox`/`position_entry`, `draw_grid_cells`, `create_rounded_rect`, `ColorSwatch` (now with `set_enabled` for master-gated forms), and the shared settings-panel group the config panels and Extras dialogs use — `create_card`, `create_status_block`, `create_slider_row`, `toggle_button_state`, `create_toggle_action_button`, `refresh_toggle_button`. Imports `add_tooltip` from `ui_widgets`.
- `ui_collapsible` holds `CollapsibleSection` (with `set_dimmed`). Imports `blend_alpha` from `ui_widgets`.
- `ui_components` adds stateful composites: the toast stack — pure `ToastModel` (visible cap + queue, two-tier priority, coalesce-by-key) rendered by `ToastManager` (all placement through the single `_layout()` authority) — plus `DragReorderManager`, `create_scrollable_frame`, global mousewheel routing.
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
profile_document ← grid_model + live_tracker_settings + deeps_settings + stopwatch
                   + inspect + cast_timer + damageinfo_settings + buff_xml
                   (each exports a PROFILE_SECTION; damageinfo_settings exports two —
                   `PROFILE_SECTION` (damage_numbers, BUILD) + `DAMAGE_COLORS_SECTION`
                   (damage_colors, sparse PATCH))
  ← profile_library (sole reader/writer of userdata/profiles/) ← profile_io, app
profile_store (in-memory doc + debounced autosave) ← profile_io, app
```
- `settings_core` is the schema-driven settings engine (`Field`/`Schema`/`Migration`/`Store` + functional `load`/`save`/`validate_all`); it imports only `settings_manager.safe_save_json` and stdlib. Every settings file declares a `Schema` and delegates validation + atomic I/O to it. It is **strict drop-unknown** — undeclared keys are erased on save — so any dynamic key namespace is one structured-dict `Field`, never N top-level keys.
- `userdata` resolves the `userdata/` storage root (created fresh on first launch by `ensure_layout()`; **no legacy migration** — old `settings/`/`profiles/` next to the exe are ignored) and its named subpaths. `assets/` stays read-only.
- `prefs` declares `PREFS_SCHEMA` (machine-local `prefs.json`, strict). `app.settings` is a `settings_core.Store` built on it; `init_settings(app.settings)` keeps the `get_setting`/`set_setting` proxy working, and `settings_manager` now holds only that proxy + the atomic temp+rename writers (`safe_save_json`/`safe_write_text`). The strict guard is `tests/test_prefs_schema_covers_all_proxy_keys` — it greps every proxy key and fails if one isn't a declared Field.
- `window_position` stores all window geometry under the single `window_positions` prefs dict field (keyed by window name), reached via the `get_setting`/`set_setting` proxy — not the `_settings` global, and not N top-level `window_pos_*` keys.

**Storage layout / data lifecycle.** Three data classes by lifecycle, not by feature:
```
<install>/
  KazBars.exe
  assets/kazbars/{Database.json, Database.json.default, Default.json}  ← REFERENCE (read-only, shipped; app never writes here)
  userdata/                       ← USER + MACHINE (created fresh by ensure_layout() on first launch)
    prefs.json                    ← machine-local (window positions, game path, resolution, the `active_profile` pointer, build toggles incl. `build_console`, the flat `panel_font_size` the four in-game panels share, the `last_build`/`last_patch` staleness records, UI state)
    profiles/*.json               ← profile documents (identity = in-doc id; `profile_library` is the sole reader/writer once the revamp cutover lands)
    profiles/*.json.bak           ← per-profile session-start snapshots (revamp)
    profiles/trash/               ← deleted profiles, pruned to the 10 newest (revamp)
    database_user.json            ← user buff deltas (seeded empty; Phase 3)
    prefs3_snapshot.xml           ← copy of the game's Prefs_3.xml, taken only while the install is healthy; Repair re-injects stripped archives from it (Flow 29)
    content/  content/.bak/       ← OTA reference content + rollback (Phase 4)
```
The editor and OTA updater **never write `assets/`**, so a reinstall always has a clean floor and the `Database.json` ⇄ `.default` byte-identity test holds. Backup/restore (`settings_backup`) covers an explicit `userdata/` allowlist — `profiles/` (minus session `*.json.bak` snapshots and `trash/` — local recovery state), `database_user.json`, and `prefs.json` — and never `content/` (regenerable OTA cache) or `prefs3_snapshot.xml` (it mirrors game state, not the user's own data, and the Funcom prefs tree is already in the zip on its own terms); `prefs.json` rides in the zip but is machine-local, so restore leaves it out unless the user ticks the opt-in checkbox. A profile is a **document**: envelope `schema` (int, `profile_document`'s ladder key — the 1→2 rung converted px positions to fractions) + `id` (stable 8-hex — identity; filenames are cosmetic slugs) + `name` + `authored_at` ([w,h] display-only provenance) + `modules` (one section per registered `SectionSpec`: `grids`, `boss_timer`, `deeps`, `stopwatch`, `inspect`, `cast_timer`, `damage_numbers`, `damage_colors`, `buff_bars` today — the extras + `damage_numbers` sections are flat config dicts, BUILD lane, fractions from birth where positions apply; `deeps` and `boss_timer` are LIVE lane — every field retunes an open overlay immediately, including its screen `x`/`y`, which stay plain px since desktop placement isn't a game-resolution concept; `damage_colors`/`buff_bars` are **sparse** PATCH lane — `{}` default, absent field = "no opinion, follow whatever the XML already says", written only by the XML editors' own Apply, never dispatched on a profile switch). Grid and extras positions are **fractions of game resolution** (`fx`/`fy`; `playerFx`/… for the cast timer's two points; full floats): px exists only at the editors' position fields and the AS2 bake (`grid_model.unproject_px`/`project_px`), so a resolution change rewrites nothing and a shared profile lands proportionally on any screen; sizes stay px on purpose (icon art has a native size). Old-format profiles (root `grids`/`profile_schema`) are **rejected, not migrated** (clean start): the library never lists them and leaves the files untouched. The active pointer is `prefs.active_profile` (the id); there is no save prompt anywhere — `profile_store` autosaves debounced, `profile_library.write` validates every byte, and Build & Install flushes first so built == saved. The shipped `assets/kazbars/Default.json` stays byte-identical in the **old** format until the release-day flip (it is OTA-manifest-tracked); the revamp's template is `assets/kazbars/templates/Default.json`, invisible to `gen_manifest.py`, and templates are instantiate-only — `profile_library.create_from_template` copies one into the library under a fresh id, so no template can ever be opened or overwritten in place.

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
             ← build_executor  ← build_action, game_folder, app_popups
             ← game_persistence  ← build_executor, build_action, game_folder
app_popups   ← app.py, build_action, first_launch, build_loading
build_loading  ← build_action
```

`game_persistence` is the cluster's game-folder layer: it owns the structures that live in the *game's* install (the two XMLs, the `Data/Gui/Aoc` fragments, `IgnorePatcher.enable`, `Prefs_3.xml`) and the constants naming them (`GAME_EXES`, `PATCHER_EXE`, `LEGACY_AOC_DIRS`). `build_executor` calls it during install/uninstall and re-exports nothing; `game_folder` calls it for Repair, the health check and the desktop shortcut; `build_action` only for `client_supports_flag`. It imports one thing upward (`build_utils.CREATE_NO_WINDOW`) and no Tk, so it sits on the mypy blocking gate.

`app_popups` is the frameless dark popup family — the shared chrome (`make_popup_shell`/`draw_close_button`/`center_popup` + the `WIDTH`/`BG`/`BORDER_COLOR`/`SCANLINE_STEP` frame constants) plus `show_welcome_popup` (first-launch), `show_about_popup` (Help ▸ About), and `show_close_game_required_dialog` (build pre-check). `build_loading` keeps only `BuildLoadingScreen` and imports the chrome one-way (no cycle — `app_popups` imports nothing from the build cluster).

**AS2 class names are load-bearing.** `base.swf` bootstraps `m_Module = new KazBars(this)`, so the generated classes, the `stubs/KazBars*.as` filenames, and `KazBars.as.template` must keep the `KazBars*` names (`KazBars`, `KazBarsData`, `KazBarsConsole`, `KazBarsPreview`, `KazBarsSlot`, `KazBarsPreviewPanel`, `KazBarsCastTimer`, `KazBarsStopwatch`, `KazBarsInspect`) to bind against it. A Python-only rename silently breaks the bind — the old `KzGrids` freeze was only lifted by recompiling `base.fla` in Flash CS6 with the new bootstrap and re-exporting `base.swf`; renaming again needs the same Flash re-export. The console (`KazBarsConsole` / `include_console`, off the flat `build_console` pref), cast-timer (`KazBarsCastTimer` / `cast_config`, read by `build_action` from the profile's `cast_timer` section), stopwatch (`KazBarsStopwatch` / the `stopwatch` section), and target-inspect (`KazBarsInspect` / the `inspect` section) stubs compile in only when enabled — gated in `grids_generator.py` so MTASC skips the unused stub class entirely. The **preview control panel** (`KazBarsPreviewPanel`) is not gated — like `KazBarsPreview`/`KazBarsSlot` it compiles into every build, which is why the `d.PF` block carrying the shared `panel_font_size` and its `ppanel.configure(d.PF)` are emitted unconditionally: a mistake there breaks every build, not only console-enabled ones. It takes the shared size with no override of its own (no dialog to host one), and is the one panel whose footprint grows with content — one row per grid, a fresh column every `MAX_PER_COL` — so `show()` steps its own size down (floor 8) until the plate fits the Stage rather than the 8–48 range being cut for everyone. `configure` keeps the requested size in `FS_REQ` and `applySize` does the ratio block, so each entry re-measures from what was baked instead of from the last entry's clamp; rows are rebuilt every entry, so it is self-correcting and cannot strand a panel the user can't reach. The panel itself exists only while preview mode is on, but its checks are the master switches for everything it lists and outlive it: `enterPreview` calls `begin()` (dropping the row array), then one `addGrid` per grid and a build-gated `addExtra` per compiled-in extra — each seeded from what that item is doing right now (`stopwatch.isActive()` and friends), so the panel caches no state of its own — then `show()` last so it lands topmost. Preview is WYSIWYG: entry no longer force-shows anything, and a hidden item stays hidden with its row unchecked. Unchecked means genuinely inactive, not merely hidden: a grid row flips a `shown` flag that the normal-mode writers (`updateDynamic`/`updateStatic`) fold into their own emptiness test, an unchecked cast timer renders nothing even mid-cast, and an unchecked inspect panel stops its 250 ms poll outright. Extra rows route through the generated `previewToggle(key, shown)` dispatcher into each stub's `setActive`. `exitPreview` restores nothing — it persists instead: `g<i>_v` beside each grid's position, `cnv` read straight off `console.isActive()`, and the other three flags riding along inside each stub's existing save call. Drag position persists under archive keys `ppx`/`ppy`, and so do the checks (`swv`/`inv`/`ctv`/`cnv`, absent ⇒ active). The stopwatch is a count-up Start/Pause/Reset panel drawn entirely at runtime (device-font TextFields resolving to the Arial faces embedded in `base.swf`, no new symbols), in the inspect panel's chrome and palette (warm near-black plate, 1px black-over-bronze double frame, orange title, square corners; time green running / orange paused / grey stopped): draggable title bar with a live-coordinate readout, collapse-to-title-bar via a bare − / + glyph that a non-moving press on the collapsed bar also re-opens, position + collapsed state persisted in the module config archive (`swx`/`swy`/`swc`) — for every user since the persistence era declares the module permanently (fold flag read first so the clamp measures the plate on screen); the baked X/Y are the defaults a first-ever session starts from. Every dimension is `Math.round(fontSize × ratio)` off the baked size, so the panel scales as one piece and its collapsed bar (`× 15.8` by `× 2`) is the inspect panel's collapsed bar at every size, not just at the default 12. That size is the shared `panel_font_size` unless `stopwatch.fontSize` carries a number of its own (8–48); the two are resolved into one baked number in `grids_generator._resolved_font_size` and nowhere else. The console shares the same plate, frame and rules — chrome on its own child clip, orange centred title, player/target columns retuned onto the inspect panel's perk-pair blue/red, `htmlText` log bodies (name in label-grey, `ID: nnnn` in value-green) — at an expanded 500×320, Stage-clamped drag with a coordinate readout. Its dimensions are `Math.round(FS × ratio)` off a base font size the same way the stopwatch's are, and that size is the shared `panel_font_size` with no override of its own — the console has no dialog to host one, which is the gap the shared value closes. `configure(d.PF)` delivers it under `include_console`; the stub also self-configures at 12 from its constructor and treats a null config as empty rather than bailing on null, so a build that never configures it still renders. It folds like the stopwatch and inspect panel: everything below the title line lives on an `m_Body` child clip toggled by `_visible`, a bare − / + glyph on the title line drives `toggleCollapsed()` → `applyCollapsed()`, and `curW`/`curH` swap to a `COLL_W`×`COLL_H` labelled bar built from the family's own `× 15.8` by `× 2` ratios — 190×24 at font size 12, and the same bar as the other two at every size, not only at the default. Collapsed, the glyph, coordinate readout and drag hitbox re-seat on the active plate, the chrome is redrawn at the new size with the section rules suppressed, the centred `BUFF CONSOLE` title swaps on `_visible` for a left-aligned `Console` label (two fields rather than re-formatting one per fold), and a press that moves the bar under 2px (`dragX`/`dragY`) re-opens it. Position **and** fold state persist under archive keys `cnx`/`cny`/`cnc` alongside the master switch (`cnv`) and the log toggles. The console has no separate active flag — open **is** active, so `cnv` is written straight off `isActive()` and the control panel's row calls `createConsole()`/`removeConsole()`, which already carry the logs, position and fold across the flip. `onLoad` opens it unconditionally (the login default); `OnModuleActivated` then reconciles, closing it again on `cnv == 0` and otherwise rebuilding it after `loadState`, so the plate lands on the archived spot and fold rather than back in the middle of the screen. Every log entry spells out its own `<font face="Arial" size="…" color="…">` on **both** runs (name and `ID: nnnn`), the size derived from the console's base font size like every other text run (11 at 12): Scaleform re-parses `htmlText` from scratch, so the field's `setNewTextFormat` never reaches an untagged run and it falls back to the default serif device font. The target inspect panel (`stubs/KazBarsInspect.as`) is a runtime-drawn combat sheet for the current target in the visual language of the game's default inspect window: a 250 ms `GetStat` poll over a 63-id watch list (3 clean warm-up passes before showing; the id 1 + id 54 collapse is treated as logout/zone teardown, not data), subject resolved via `Character.GetCharacter` with a `Dynel.GetDynel` fallback for destructibles (a minimal intrinsic stub added to the `src/kazbars/assets/common_stubs/com/GameInterface/Game/` tree alongside `Character`/`CharacterBase`), sheet-exact armor/protection/mitigation/crit/critigation/CDI/bonus-spell-damage synthesis, and — on player targets only, gated on the engine's own `ID32.IsPlayer()` **and** a decoded attribute spread, both of which must agree (the classifier is measured truthful on players but never sampled on mobs, so it vetoes rather than confirms alone) — a PvP section plus a Perks row that renders the target's slotted-AA perk buffs as RDB-loaded game icons, each section behind its own baked config toggle (`showPvp` / `showPerks`). Attribute *presence* is not a discriminator: attributes are x10+10 encoded, so an NPC template carrying them at base still reads raw 10 — which is exactly what put a PvP block on city guards. Every dimension derives from the baked size — the shared `panel_font_size` unless `inspect.fontSize` sets its own; position and collapse work exactly as the stopwatch's (baked X/Y + `startCollapsed` defaults, name-strip drag with live coordinates and a − / + collapse button, archive keys `inx`/`iny`/`inc`, `loadState` reading the fold flag before clamping so the clamp measures the plate on screen). The watch list, the sheet syntheses and their level-80 constants, the display gates, and the in-game verification checklist are documented in [`inspect-panel.md`](inspect-panel.md) — read that before changing any number in the stub.

**Null-icon custom icons.** Some AoC buffs return `m_Icon.GetInstance()==0` (no game icon → the slot rendered blank). `grids_generator.CUSTOM_ICON_LINKAGE` maps such buff IDs → baked symbol linkage names in `base.swf` (`IcoSlow30/40/45/60` for the ice-gem slows), emitted into `KazBarsData.CUSTOMICON`. `KazBars.as.template`'s `loadIcon` routes through `attachBaked` to attach the symbol as a slot sibling at **dynamic depth 8**, with a shared **`IcoNull`** fallback for any other no-icon buff — so no tracked buff shows a blank slot. The slot's authored art (bg/icoMask/m_icon/frame, depths 1/3/5/9 in the FLA) becomes timeline content in the negative reserved depth range at runtime, so depth 8 sits above it; the timer/stack TextFields are pinned to fixed depths **10–13** (`KazBarsSlot`, not `getNextHighestDepth()`) so they render above the icon rather than under it. The flash (`animSlot`) pulses `s.cust` for baked icons, `m_icon` for RDB icons. The rounded crop is baked into the art (PNG inset ~56×56 in a 64×64 canvas), **not masked** at runtime: AoC's Scaleform renderer applies masks only to `loadClip` content (the RDB game icons), never to `attachMovie`'d content.

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
`default + offset`, and MTASC-injects the result into a copy of the pristine
`src/kazbars/assets/damageinfo/DamageInfo.swf` (two entry points — `MainDamageNumbers` +
`FixOnLoad`, the latter force-compiled so the container's `onLoad` survives the
inject). The AS2 is a from-scratch lean rewrite of the stock overlay: a single
`onEnterFrame` IN/LIVE/OUT loop (no TweenLite / `setInterval`), an O(1) column
hashmap, object pools, and a 3-way `SHADOW_MODE` (None / Fast offset-twin / Real
DropShadowFilter). Gated by a master `enabled` flag (off by default); when off the
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
src/kazbars/app.py  → profile_io, game_folder, game_resolution, build_action, buff_display_editor, first_launch, custom_menu_bar, update_check, content_update, settings_backup, stopwatch_panel, inspect_panel, cast_timer_panel
profile_io  → profile_store (runtime document), grid_model, ui_widgets, userdata
```
These modules are consumed only by `src/kazbars/app.py` by design — they hold logic that belongs to the root window but would otherwise bloat the entry-point file. Each takes `app` (the `KazBarsApp` instance) as first arg. That wide seam is a *checked* contract: `tests/test_app_contract.py` AST-scans every `app.<attr>` access in app-taking functions and asserts each attribute is defined on `KazBarsApp` (Tk surface + `self.X` assigns), so a rename in app.py fails CI instead of breaking a satellite at runtime. New cross-module state goes in `KazBarsApp.__init__`'s `# State` block — a satellite must not invent app attributes by assignment. `KazBarsApp` keeps thin delegator methods so internal call sites (menus, dialog callbacks) don't need rewriting when new functions get added. `first_launch` is the only satellite that crosses cluster boundaries — its `run_first_launch(app, app_name)` orchestrator imports `game_folder`, `profile_io`, `app_popups`, and `grid_model` to drive the dialog's post-close actions (default profile load, scaling, welcome popup). `update_check`'s silent launch check is called directly (single fire-and-forget caller in `__init__`); the Updates-menu manual check goes through the `_check_app_updates_now` delegator; its worker threads schedule named main-thread dispatchers (`_show_update_toast`/`_show_manual_result`) guarded by `winfo_exists()`. `app_popups` also imports its pure `fetch_latest` for the About popup's manual update check.

## Fan-in (modules that would churn many files if touched)

| Fan-in | Module | Notes |
|---:|---|---|
| 25 | `ui_helpers` | Pure tokens — high fan-in is expected for shared constants. Keep the surface small. |
| 22 | `ui_widgets` | Core glue (`app_toast`/`add_tooltip`/`blend_alpha` + event bindings). Still the widest UI surface even after the builders split out — most panels pull at least a toast/tooltip/binding. Keep new helpers focused. |
| 12 | `grid_model` | Grid dataclasses + the fraction↔px projection (`project_px`/`unproject_px`, `get_game_resolution_or_default`) — pulled by every grid-editing surface plus the three extras dialogs (projected-px position fields). Pure data, stable surface. |
| 13 | `profile_document` | The profile section contract ← `app.py` (registry wiring), `grid_model` + `live_tracker_settings` + `deeps_settings` + `stopwatch` + `inspect` + `cast_timer` + `damageinfo_settings` (two sections — `damage_numbers` BUILD, `damage_colors` sparse PATCH) + `buff_xml` (`buff_bars`, sparse PATCH), `profile_library` (the gate), `profile_io`, and `build_signature` consumers — `build_action` (records `last_build` on success) + `grids_panel` (status row). Infrastructure on the cluster-isolation list; imports only `settings_core`. |
| 10 | `ui_headers` | Dialog/app headers + tip bar — pulled by every dialog/panel that draws a CRT header. |
| 10 | `settings_manager` | `get_setting`/`set_setting` proxy + the atomic temp+rename writers (`safe_save_json`/`safe_write_text`) — pulled by the settings engine, profile/delta I/O, and the panels that persist prefs or write Customized skin files. |
|  6 | `ui_forms` | Form fields + shared settings-panel builders (card/status-block/slider-row/toggle). The Deeps + Live Tracker config panels are its heaviest consumers. |
|  5 | `ui_collapsible`, `window_position` | Small stable APIs. `ui_collapsible` is just `CollapsibleSection`. |
|  4 | `ui_tk_style`, `ui_components`, `overlay_engine`, `app_popups`, `cast_timer` | Narrow surface — ripple is contained. `overlay_engine` feeds both overlays + both settings adapters; `app_popups` feeds `app.py`, `build_action`, `first_launch`, `build_loading` (popup chrome + the three popups). `cast_timer` is the pure config layer ← `app.py` (registers its `PROFILE_SECTION`), `grids_generator`, `cast_timer_panel`, and `build_action` (which validates the profile section before handing it to the build as `cast_config`). |
|  4 | `prefs` | `app.py` (builds the `Store` on `PREFS_SCHEMA`) + `grids_generator` (`validate_panel_font_size` only — the shared panel size is a prefs-level contract, and the generator is what bakes it) + `damageinfo_colors_panel` + `buff_display_editor` (both call `record_last_patch()` from their Apply — see the `last_patch` note above). |
|  3 | `build_utils`, `build_executor`, `game_persistence`, `live_tracker_settings`, `paths`, `stopwatch`, `inspect` | Cluster leaves. `paths` is imported directly by `app.py`, `build_utils`, `deeps_parsers` (everyone else gets paths via the `app` object). `game_persistence` ← `build_executor`, `build_action`, `game_folder` — the game-folder layer of the build cluster; changing a marker, a target path or a constant there is felt by all three. `stopwatch` and `inspect` are the pure config layers ← `grids_generator`, `app.py` (registers their `PROFILE_SECTION`s), and their own Extras dialog (`stopwatch_panel` / `inspect_panel`). Both their `fontSize` fields are nullable — `None` defers to `prefs`'s flat `panel_font_size`, which `grids_generator` resolves and bakes. |
|  2 | `grids_generator`, `update_check` | `update_check`: `app.py` (launch check) + `app_popups` (About ▸ Check for updates via `fetch_latest`). |
|  2 | `profile_io` | ← `app.py` (delegators + startup) and `first_launch` (re-dispatch of the seeded profile). |
|  1 | `grids_panel`, `custom_menu_bar`, `profile_library`, `profile_store`, `game_folder`, `game_resolution`, `build_action`, `build_loading`, `database_editor`, `instructions_panel`, `first_launch`, `live_tracker_panel`, `grid_dialogs`, `boss_timer`, `timer_overlay`, `combat_monitor`, `settings_backup`, `stopwatch_panel`, `inspect_panel`, `cast_timer_panel`, `extras_shortcuts`, `foreground`, `focus_watcher` | Each consumed by exactly one parent — low blast radius by design. (`foreground` ← `focus_watcher`; `focus_watcher` ← `app.py`; `build_loading` ← `build_action`; `profile_library` ← `app.py`; `profile_store` ← `profile_io`; `extras_shortcuts` ← `grids_panel` — flips the four SWF-extra gates, all four via `app.profile_store.update_section` (autosaved); the four Extras dialogs push `refresh_extras_shortcuts()` back after Apply, and `profile_io.apply_document` resyncs the cards on every profile switch.) |

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

