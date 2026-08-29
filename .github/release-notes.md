## What's New in v3.0.0

A major release: your in-game layout now survives relogs and restarts, profiles are a managed library, and a new target inspect panel joins the extras. Profiles from 2.2.2 don't carry over — read the first section before you build.

### Upgrading from 2.2.2

**Your old profiles won't appear.** The profile format changed, so profiles made with 2.2.2 or earlier are left on disk untouched but don't show in the new library. Recreate your layout with **New from template** — this is why v3.0.0 is a major version, not a patch.

**Close the game and the patcher for your first build.** Build & Install now registers KazBars with the game once; that first build needs both closed. After that, rebuild anytime and type `/reloadui` in-game.

**Dragged positions reset once.** Saved in-game spots are now tied to the grid itself instead of its place in the list, so every dragged position resets on this upgrade. Reposition once in preview mode (Ctrl+Shift+Alt) and it holds from then on.

**The Cast Timer has its own dialog now.** The strip above the grid list is gone; the timer's settings live under Extras, and it starts from defaults — set it up again there if you use it.

### Added

**Your layout survives relogs and restarts.** Drag grids and panels in preview mode and the game remembers positions, collapse states and the preview panel's checkboxes — the same way it remembers its own windows. There is one install mode for everyone; the Aoc.exe question is gone.

**Repair game install** — the patch-day fix. If the game updates, run the official patcher once, then Repair: it re-registers KazBars, restores your saved positions from a safety snapshot, and puts the Damage Numbers mod back. A startup check notices when the game stopped loading KazBars and offers the repair in one click.

**Desktop shortcut for direct launch** — after your first build, KazBars offers to create a shortcut to the game executable (DX10 or DX9), so the patcher-skipping launch is one double-click.

**Target inspect panel** — an in-game combat sheet for whatever you have targeted, styled after the game's own inspect window: armor and protection with mitigation, crit and critigation, heal rating with its Celestial Gaze range, bonus spell damage and combat rating, plus a PvP section and up to six slotted AA perks on player targets. Drag it, fold it, and the game remembers both. Off by default

**KazBars Preview panel** — preview mode's control panel now lists every grid and extra under Player Grids, Target Grids and Tools. Untick a box to hide an item while you position things; click a header to toggle the whole group. Each box is a master switch that stays put across relogs.

**Extras toggle cards** — a row above the grid list shows Cast timer, Damage numbers, Inspect panel and Stopwatch, lit green with "In next build" when on. Click a card to flip it.

**Extras-only builds** — a layout with no grids but an enabled extra now builds.

**A direction for every combat number** — each damage source gets a Rising / Dropping / Zig-zag choice beside its color swatch, with two shortcuts that move your own resource numbers or everything incoming to the fixed column at once.

**One text size for all four in-game panels** — the stopwatch, inspect panel, buff console and preview panel share a single 8–48 size. The stopwatch and inspect panel can still opt out and keep their own.

**Two new buff categories: Dungeons and World Bosses** — 36 boss debuffs move out of General, and dungeon debuffs are now named by the instance instead of the boss, so a grid reads by where you are. Spell IDs are unchanged, so existing Tracked Buffs lists still match.

**Wrack and Torment now catch the later re-issues** — the three generic Wracks gained the alias spell IDs the game uses for newer content, and three new Torment (Generic) entries (26 IDs each) cover every same-named copy outside the stacking ranks. Sodabeh's Wrack (Ardashir Fort) joins them.

**24 new crowd-control entries, cast and confirmed in game** — every class's CC list gains entries, corrected spell IDs, added ranks, and names that say what the effect actually does (fear-and-slow, silence-and-stun).

**20 more wrack and torment boss debuffs** — completing the dispel set on raid encounters that only had their ruin half tracked.

**Ruin line expanded and cleaned up** — 25 new entries confirmed in game, 14 renamed with their applying boss, 4 unconfirmed ones withdrawn, and the generic Ruins gained their later-content alias IDs.

**Seal of Yog (Crit) and Seal of Yog (Mana)** — the Dark Templar stacking buffs, every rank covered. Nature's Wrath now tracks all ten stacks, and Crushed Armor Wrack is credited to Dai Gang.

The catalog now holds 430 buffs. Every catalog change above already reached existing installs as a content update; the starter template and its Tracked Buffs lists are synced to match.

### Changed

**Profiles are a managed library.** The File menu lists every profile; click one to switch, or use New, New from template, Duplicate, Rename, Delete and Revert to session start. There is no Save button: every edit autosaves about a second after you stop, and Build & Install saves first so what's installed always matches.

**"In game:" status line** — under the extras cards, it turns orange when the installed build no longer matches the loaded profile: a different profile installed, an edit since the last build, or a resolution change.

**Export and Import profile replace the copy-paste share string.** Export writes one self-contained profile file with any custom buffs it references embedded, so the importer's database doesn't need to know them first. Positions travel as fractions of your screen, so a shared profile lands proportionally on any resolution.

**Profiles carry nearly everything a build depends on** — grids, Stopwatch, Inspect panel, Cast timer and Damage Numbers, plus Deeps, Ethram-Fal and any Default Buff Bars or Damage number color overrides you've made. A buff an import can't resolve shows greyed out as "unknown buff" instead of vanishing, and the build summary counts how many were excluded.

**Applying a rebuild is `/reloadui` alone.** The `/reloadgrids` and `/unloadgrids` chat scripts are gone — nothing needs them now.

**Damage number colors and directions apply the moment you hit Apply** — no build, no toggle. Reset to game default restores the stock color and direction, per row or all at once. Colors you set stay put when you turn the Damage Numbers mod off or uninstall.

**Damage Numbers no longer needs the launcher bypass.** If the game patches, run the patcher once, then Build & Install to put the mod back.

**Two Damage Numbers toggles renamed to say what they do** — "Split signed numbers into Column B" and "Keep enemy drains overhead".

**The Damage Numbers panel waits for Apply** — settings no longer save as you drag a slider; Cancel, Escape or the X discard everything.

**The Extras menu is split in two** — editors that write your game files (applied with `/reloadui`) above the separator, features that ship with your next Build & Install below it. "In-game stopwatch" is now **Stopwatch**, "Target inspect panel" is now **Inspect panel**.

**The buff-discovery console toggle lives in the Inspect panel dialog** — both in-game inspection tools switch on from one place.

**The Stopwatch, Inspect panel and Cast timer dialogs match the Damage Numbers panel** — master toggle at the top, settings in titled cards, Apply / Cancel along the bottom. Untick the master toggle and everything it governs greys out.

**The three in-game panels share one look.** Stopwatch, inspect panel and buff console use the same plate, frame, Conan-orange title bar and − / + button; all three fold to the same small bar, and clicking the bar reopens them. The console's Keep Open pin is retired — its open state, position and fold are remembered like everything else, and it narrows to one column when you untick a side.

**The in-app guide is a knowledge base.** New sections for Profiles, Updates, Launching the Game, After a Game Patch and Removing KazBars; Finding Buff IDs is the console's one home; How Extras Ship states the rules once. Sections link to each other.

**The quick-start tip guide shows once** — after your first build it retires for good.

**About shows the version it's running.** The Discord link left the dialog for now — the invite is still in the README.

### Fixed

**Changing the game resolution now resizes your grids' icons and fonts too** — an untouched grid lands on the stock size, a tuned grid keeps its tuning.

**Grid names with accented or non-Latin characters (é, ü, 日本語…) compile again.**

**Preview mode keeps every overlay on top, in bounds and readable** — a tall inspect panel can't be dragged off-screen, retargeting doesn't resize it out from under its label, a two-column grid's X/Y readout no longer clips a digit, and a buff that changes category mid-fight draws at its proper depth. The inspect panel also clears the moment you drop or swap target.

**The inspect panel shows percentages at any target level, not just 80** — in-game measurement confirmed the math holds across the full 1–86 range.

**Buff console entries render in the console's own type** — name in parchment grey, ID in green, no more serif fallback.

**Tooltips no longer get stuck on screen** when their control is removed, and changing your game folder repeatedly no longer stacks old and new paths.

**Uninstall checks that the game is closed before it starts**, the same way Build & Install and Repair do.

**Build & Install re-checks that KazBars is actually registered with the game** — if a patch quietly wiped it, the close-the-game prompt reappears.

**A safety backup no longer resurrects a game config file you deleted on purpose**, and cleaning up the auto-login script leaves its line endings alone.

**A buff-database content update takes effect the moment it's applied** — no restart. An app update that raises the minimum content version falls back to its own bundled catalog.

**Failed saves no longer lose your edits.** Switching profiles or closing the app when a save fails warns you and keeps you on the unsaved profile; Backup & restore saves your profile before restoring over it and stops if that save fails.

**The profile list survives files disappearing mid-listing** — an antivirus scan or sync client can't crash it.

**A malformed grid config value no longer crashes a build.**

**Toast undo undoes the right delete** when you delete several grids back-to-back, and a stopped Deeps or Ethram-Fal overlay no longer leaves a ghost on screen.

**Deeps and the Ethram-Fal tracker no longer double-count after a quick Stop → Start.**

**Importing buffs checks every ID for a collision**, not just the first, so a shared secondary ID can't silently re-home an existing entry.

**Update checks read a suffixed release tag correctly** (e.g. `3.0.0-rc1`).

**Buff-bar and damage-color edits write to the game's XML atomically** — an interrupted write can't leave the file half-written.

---

Buff/debuff overlay editor for **Age of Conan**. Design icon grids or bars that show your active effects on top of the game, then compile and install them in one click.

## Highlights

**KazBars** — custom icon overlays arranged in bars or grids that show only the buffs and debuffs you choose to track.
- **Player and Target grids** — track effects on you and your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric buff IDs to readable names and classify them as Buff, Debuff, or Misc

**Cast Timer** — an on-screen readout of your and your target's current cast time, ready to sit over the game's cast bars. Off by default

**Stopwatch** — a simple, draggable Start / Pause / Reset count-up timer. Off by default

**Inspect panel** — an in-game combat sheet for your current target: armor and protection with mitigation, crit, heal rating and spell damage, plus a PvP section and slotted perks on players; drag or fold it and the game remembers. Off by default

**Damage Numbers** — a leaner, faster rewrite of the game's floating combat numbers, with new layout and behavior settings. Off by default

**Deeps by Veni** — a real-time meter that reads the combat log for your DPS out, DPS in, HPS out, HPS in, and ΔHP in

**Ethram-Fal Seed Timer** — tracks the Viscous Seed / Lotus Fixation / Syphon cycle to help the raid time scorpion kills

## Utility tools

**Default Buff Bars editor** — tune the game's own buff-bar HUD from one place: on/off, icon size, spacing, columns, friendly/hostile filter — no XML editing

**Damage number colors** — set a color and a direction for every damage source from one place, applied the moment you hit Apply, no build

**Backup & restore** — save your full Age of Conan config plus your KazBars profiles and settings to one portable zip, and restore it after a reformat or on a new PC

**Repair game install** — after a game patch, run the official patcher once, then Repair re-registers KazBars, restores your saved positions from a safety snapshot and puts the Damage Numbers mod back; a startup check offers it when the game stopped loading KazBars

## Install

1. Download `KazBars.zip` below and extract it anywhere.
2. Run `KazBars.exe` as Administrator.
3. The first-run setup window opens. Point it at your Age of Conan folder.
4. Choose **Use Defaults** — ready-made grids for common raid buffs and debuffs, sized to your screen. (Or **Start Empty** to build your own from scratch.)
5. Click `Build & Install`. Close the game and the patcher for your first build. After that, rebuild anytime and type `/reloadui` in-game.
6. Launch the game from its own executable, not the patcher — KazBars offers to create a desktop shortcut (DX10 or DX9) after your first build. Launching this way is what keeps your setup in place.

Positioning happens in-game: press Shift+Ctrl+Alt for preview mode and drag your grids and panels where you want them. The game remembers where you left them, across relogs and restarts.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then `Tracked Buffs...` to pick what each one watches.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
