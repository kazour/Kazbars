# Changelog

All notable changes to KazBars will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.1.0] — 2026-05-29

### Added
- **Deeps readout tuning** — a new **Readout** card in the Deeps panel. Choose the rolling-window width (5 / 7 / 11 / 13 s) and pick a **Style** preset — **Live** (exact, every spike shows), **Steady** (calm but responsive), or **Calm** (heavy smoothing, chunky numbers, half-second redraw) — that shapes how the drawn numbers read. The alarm pulse and net-HP tints still track the raw values, so only the digits ease. Ships on **Steady**. A note flags that widening the window also makes the alarm and tints react later.
- **Crash log on disk.** The windowed build now writes a rotating `logs/kazbars.log` next to the app, so a crash with no console still leaves a retrievable trail.

### Changed
- **Deeps alarm pulse is now smooth.** The DPS-out alarm glides through its red pulse instead of stuttering, and the incoming-damage / ΔHP-in cells now ramp through amber as the deficit grows — a graduated warning that fades in and then pulses, rather than snapping on at a single threshold.
- **Expanded in-app Help.** The Help view now documents Deeps, the Cast Timer overlay, Backup & restore, the Default Buff Bars editor, the buff-discovery console toggle, and game resolution.

### Fixed
- **Grid names with quotes, newlines, or backslashes no longer break the build.** Such characters are now escaped when the grid is written into the generated overlay code, so an unusual grid name can't corrupt the SWF build.

## [2.0.0] — 2026-05-25

The **Kaz Grids → KazBars** release: the rename the community always used, plus a real combat meter, a cast-timer overlay, settings backup, and a wide polish pass.

### Added
- **Deeps — real-time damage/heal meter.** The new `⚔ Deeps` button opens a transparent, always-on-top overlay showing five rolling numbers over the game: DPS out, DPS in, HPS out, HPS in, and net HP in. The DPS-out cell pulses red past a configurable threshold; the HPS-in / DPS-in cells tint green / orange by net HP. Two layouts (row or stack), a 5-cell visibility picker, size and background-opacity sliders, and optional own-pet damage (your pet only). Auto-hides when AoC isn't focused. (Parsers ported from the Rust [Deeps](https://github.com/lostagista/clp) project.)
- **Cast timer overlay.** A new collapsible **Cast Timer** strip above the grid list drives a timer-only overlay — no bar, just floating text — showing player and/or target cast time over the game's cast bar. Per-side enable + position; shared bold / size / color and an Elapsed / Total / Both display mode. Off by default.
- **Backup & restore game settings** (Game ▸ Backup & restore game settings…). Writes one portable `.zip` of your full Funcom config (keybinds, HUD, graphics — all characters) plus your KazBars profiles and settings, so you can recover after a Windows reformat or profile corruption. Restore validates the zip, snapshots the current state first, and recreates folders on a fresh machine.
- **Custom icons for buffs the game serves with no icon.** The six ice-gem slows — and any other icon-less tracked buff — used to render as blank slots; they now show a baked icon (a shared placeholder for anything unmapped), so no tracked buff is ever blank.
- **Default Buff Bars editor** (Game ▸ Default buff bars…). Edit AoC's built-in buff-list widgets — Player/Target portraits, top bar, floating portraits — for icon size, spacing, columns, and friendly/hostile filter, without hand-editing XML. Writes only to your `Customized/` skin and backs up each file once.
- **Optional buff-discovery console.** The `Shift+Ctrl+Alt`-in-preview overlay that logs new buff IDs is now a Game-menu build toggle (off by default), so finished builds don't carry it.
- **Help section for the Ethram-Fal Live Tracker** — setup, positioning, and the ~40s Seed → Fixation → Syphon cycle.
- **Clickable overlay padlock** — click an overlay's unlock glyph to lock it in place (unlock stays in the panel, since locking enables click-through).

### Changed
- **Renamed Kaz Grids → KazBars** end to end: the Python package, `KazBars.swf`, the `Aoc/KazBars/` folder, XML IDs, and the auto-load marker. Predecessor files (`KzGrids.swf`, `Aoc/KzGrids/`, old markers) are auto-cleaned on every install, and `kzgrids_settings.json` migrates to `kazbars_settings.json` on first launch — existing users upgrade in place with no manual uninstall.
- **AS2 internals renamed to `KazBars`.** The last `KzGrids` remnant of the rebrand is gone — `base.fla` was recompiled in Flash CS6 with a `new KazBars(this)` bootstrap and re-exported, so the ActionScript classes, stubs, and template now match the `KazBars` name used everywhere else.
- **Modern Python tooling** — a `src/` layout, `pyproject.toml` as the single source of truth, a checked-in `kazbars.spec` for builds, a `pre-commit` hook (ruff lint + pytest), and CI on every push.
- **Overlay subsystem unified (Deeps + Ethram-Fal).** Both overlays now share one rendering / chrome / drag / focus engine, so they look and behave as a set. A single app-wide focus gate hides them when AoC isn't focused, and both follow "show on Start, hide on Stop." Combat-log pickup is fully automatic — no more Scan Log button; it follows the newest log and waits if today's hasn't been created yet. Overlay font is fixed to Segoe UI, the Live Tracker overlay auto-sizes, and the two settings panels now share a common layout.
- **Tuned the out-of-the-box defaults** (first-launch only — your saved settings and profiles are untouched). Deeps: alarm threshold 2500, pet damage on, a 66% backdrop, lower screen position, default cells DPS / DPS-in / HPS. Live Tracker: lower position, 66% backdrop, slightly smaller font. Grid template: larger stack-count font, slight timer nudge.
- **Live Tracker overlay polish** — a legible outline stroke over busy scenes, a docked two-row + cycle-timer layout that can't overlap on resize, profile save/restore of size and visibility, a monochrome ●/○ lock glyph, and mutual exclusion between Test Cycle and Start Monitoring. Seed-phase wording tightened ("Scorpion" everywhere, clearer kill-window timing).
- **Database editor & Tracked-Buffs polish** — rows tint by type (debuff red / misc gold) with sortable column headings; blocking warning dialogs replaced by toasts.
- **Add Grid polish** — the Player / Target source affordances carry their type color across the wizard and the empty state.
- **Top menu refresh + reorg** — a phosphor-underline active cascade and hardened dropdown rendering; File gains **Exit**, Game gains **Change game folder** and **Uninstall**.
- **Disabled grids visually mute** in the editor list, so it's clear at a glance what won't build.
- **Toast system pass** — toasts coalesce by key (no more stacks during spinbox holds), with brand, voice, and animation fixes.
- **Window minimum size** raised to 950×660 so the bottom-bar status indicators stay readable.
- **Settings file renamed** `timers_settings.json` → `live_tracker_settings.json` (auto-migrated). `pywin32` is now a real Windows dependency, so overlay click-through actually works in shipped builds.
- **Internal** (no user-facing change) — `app.py` and `ui_helpers.py` split into focused modules; pure data/XML layers extracted (`buff_database.py`, `buff_xml.py`); Deeps and Live Tracker kept as test-enforced isolated clusters; type-checker and lint cleanups.

### Fixed
- Overlays no longer flicker off on a transient focus-probe failure, double-paint each tick, or repeatedly re-blank while alt-tabbed.
- The overlay lock dot is now drawn only when unlocked — it was a dead button when locked (locking enables OS click-through).
- The preview-mode chord (`Shift+Ctrl+Alt`) no longer mis-fires after alt-tabbing out of the game and back.
- The Live Tracker overlay no longer re-centers itself on every launch (its "already positioned" flag was being dropped on save).
- Syphon's "Avoid the clouds" message no longer sticks after Stop → Start.
- Database column-heading dividers are now visible.
- The About popup is single-instance — repeat clicks lift the existing window instead of stacking new ones.

## [1.1.0] — 2026-04-22

### Added
- Background check for new releases on launch. Click the toast to open release notes.
- File → Uninstall from game client. Cleanly removes KazBars files from the selected install.

### Changed
- Grids now reference buffs by spell ID instead of name. Renaming a buff in the database no longer breaks grids that use it. Existing profiles migrate automatically on load; any buffs that can't be resolved are listed in a dialog so you can re-add them.
- About dialog now links to the GitHub repo.

### Fixed
- Database changes are now saved when you close the app and click "Yes" on the unsaved-changes prompt. Previously only the profile was saved.
- Build now refuses to run if an enabled grid has no tracked buffs, instead of installing a silent grid.
- Invalid entries in the Add Buff ID field show a warning before saving instead of being dropped silently.
- Welcome popup no longer references a non-existent "Edit → Clear All Grids" menu path.

## [1.0.0] — 2026-04-18

Initial public release.
