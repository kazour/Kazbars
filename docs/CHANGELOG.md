# Changelog

All notable changes to KazBars will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Target inspect panel** (Extras ▸ Target inspect panel…) — an optional in-game overlay that shows a combat sheet for whatever you have targeted, styled after the game's own inspect window: armor and protection with their mitigation percentages, crit and critigation, heal rating with the Celestial Gaze range it buys, bonus spell damage, combat rating — and, on player targets only, the PvP section with its own bonus spell damage and combat rating (mobs and bosses show the PvE sheet). The title line identifies the target — name, class, and level/PvP level, dropping whatever a target doesn't have. Turn it on in the new dialog and it ships with your next Build & Install; the position and font size you pick are baked in, and the whole panel scales with the font size. Dragging its name strip shows live coordinates — type them into the dialog to make a spot permanent; the − button folds the panel down to that strip, and Aoc.exe clients remember both the drag and the folded state. Off by default; when off, the built overlay carries no inspect-panel code at all.
- **Seal of Yog (Crit) and Seal of Yog (Mana)** — the Dark Templar stacking buffs join the catalog, every stack rank covered. (Already delivered to existing installs as a content update; see `database-changelog.md`.)

### Changed
- **Damage number colors now apply the moment you hit Apply — no build, no toggle.** The color editor (Extras ▸ Damage number colors…) works like the Default Buff Bars editor: pick your colors, click Apply, and type `/reloadui` in-game to see them. It edits the game's `TextColors.xml` directly instead of waiting for a Build & Install, and it no longer depends on the Damage Numbers mod being switched on — colors are the game's own feature, so they stand on their own. Edits land in your `Customized` skin folder (created for you if needed) and touch only the colors, so a game update can't wipe them and the Damage Numbers direction options never clash with your palette. "Reset to game default" pulls the original color straight from the game's stock files. Colors you set now stay put when you turn the Damage Numbers mod off or uninstall — use Reset if you want them back to stock.

### Fixed
- **Tooltips no longer get stuck on screen.** Removing a control while its tooltip was showing — deleting a grid card, for example — could leave the tooltip floating over the app. Tooltips now disappear with their control.

## [2.2.2] — 2026-06-17

### Changed
- **The build screen reads as clear steps instead of a flicker.** Now that the build is near-instant, its progress used to flash past too fast to follow. The compile and install run without freezing the loading animation, and each phase — Compiling, Baking damage numbers, Installing — holds on screen for a brief beat, so you can see what's happening.

### Fixed
- **Build & Install no longer freezes for ~15 seconds before it starts.** On some systems, clicking Build & Install would hang with nothing on screen for a beat while Windows prepared the helper processes the build needs (compiling the grids and checking whether the game is running). That preparation step now runs without the stall, so Build & Install starts near-instantly — roughly 16 seconds down to under one on affected machines.

## [2.2.1] — 2026-06-16

### Fixed
- **Frameless popups no longer trap the app after Show Desktop (Win+D).** Pressing Win+D while a borderless KazBars modal was open — the Build & Install summary, the welcome popup, About, or the "close the game first" notice — could leave the window minimized with no way back: clicking the taskbar or Alt-Tab did nothing, because these title-bar-less windows give Windows nothing to restore. They now track the main window — hiding when you minimize and returning, on top and usable, when you restore.
- **Veil of the Unliving (Zaal) now matches the in-game effect.** Corrected the buff's spell ID, so grids and profiles tracking it light up again. (Already delivered to existing installs as a content update; see `database-changelog.md`.)

## [2.2.0] — 2026-06-15

### Added
- **Damage Numbers** (Game ▸ Damage number Mod… / Damage number Colors…) — a new panel that tunes Age of Conan's floating combat-number overlay and installs a leaner, faster rewrite of it on your next Build & Install. The headline fix: damage numbers no longer shrink to nothing at range — a **Keep ranged numbers big** toggle holds the size of *ranged* hits (past ~15 real metres) without ever touching your close-up (melee) numbers, which stay exactly as the game draws them. Also tune shadow style (None / Fast / Real), pop-in and fade speed, and where numbers land (above the target, in fixed columns, or a zig-zag stack), with Default / Performance presets. A **Group my resource numbers** toggle routes your own mana/stamina losses into the same fixed column as your resource gains — so all your resource changes read in one place — while mana/stamina you drain from enemies still floats over them. A **Separate resources into Column B** toggle drops everything that lands on you (incoming damage, heals, mana/stamina) into fixed columns and splits it — damage in one column; heals, stamina and mana in the next — for a clean, stationary readout instead of numbers flying off your head. And a **Damage number colors** editor lets you recolor every combat-number source independently — incoming vs outgoing hits, crits, spells, combos, heals, mana/stamina — laid out self on the left, your target on the right. Off by default behind a single master toggle; your stock `DamageInfo.swf` is backed up once, so turning it off or uninstalling restores the original.
- **In-game stopwatch** (Game ▸ In-game stopwatch…) — an optional Start / Pause / Reset count-up timer that lives *inside* the game as part of the KazBars overlay, so it works in fullscreen and its buttons never steal focus from the game. Turn it on in the new dialog and it ships with your next Build & Install: a compact draggable panel showing `h:mm:ss`, with a − button that collapses it to just its title bar (which then shows the running time). Dragging the title bar shows live coordinates — type them into the dialog to make a spot permanent; Aoc.exe clients remember the position and collapsed state automatically. Off by default; when off, the built overlay carries no stopwatch code at all.

### Changed
- **Deeps "Alarm & Tints" is simpler to set.** The DPS-out alarm is now a slider over a 1000–4000/s band (instead of a typed value), and the four ΔHP-in survival-tint thresholds collapse into two presets — **Standard** (DPS / healers) and **Tank** (a wider symmetric band) — with a caption that restates the breakpoints. The default survival tints changed to match the **Standard** preset; the alarm default stays 2500/s. Your saved alarm value is kept and clamped into the slider's band.
- **Buff catalog reorganized.** The shipped buff database is sorted into clearer categories — a new **#Protections** group for group damage-mitigation buffs, plus plainer names (#Resistances → #Immunities, #Global → #General, #Group HoT → #Group Heals) and the raid tiers grouped under **#Raid T3…T6**. Display grouping only — no spell IDs changed, so existing grids and profiles are unaffected. (Shipped as a content update; see `database-changelog.md`.)
- **Refreshed default profile.** The out-of-the-box grids were redesigned and renamed for clarity — **My Buffs**, **Raid Debuffs**, **Target Buffs**, **Target Debuffs** — authored against a 1440p reference that scales to any resolution.
- **Internal** (no user-facing change) — `ui_widgets.py` split into focused modules: `ui_headers.py` (dialog/app headers), `ui_forms.py` (form fields + shared settings-panel builders), and `ui_collapsible.py` (`CollapsibleSection`), leaving `ui_widgets` as the leaf core (tooltips, toasts, event bindings).

### Fixed
- **Cast Timer no longer flashes a huge bogus estimate during lag or cast interrupts.** The timer-only overlay now samples the clock and cast progress on the same engine frame instead of on a free-running interval, so a stutter can't pair a fresh clock with stale progress and spike the estimate.

## [2.1.0] — 2026-05-29

Archived — see [`CHANGELOG-archive.md`](CHANGELOG-archive.md#210--2026-05-29).

## [2.0.0] — 2026-05-25

Archived — see [`CHANGELOG-archive.md`](CHANGELOG-archive.md#200--2026-05-25).

## [1.1.0] — 2026-04-22

Archived — see [`CHANGELOG-archive.md`](CHANGELOG-archive.md#110--2026-04-22).

## [1.0.0] — 2026-04-18

Initial public release.
