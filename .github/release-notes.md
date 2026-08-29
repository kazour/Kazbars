## What's New in v3.0.1

A patch release: one build fix, plus a note for anyone still on 2.2.2.

### Changed

**Buff-database updates now need KazBars 3.0.0.** They carry the starter profile from now on, so New from template always uses the newest one. On 2.2.2 you'll see "New buffs are available — update KazBars to get them" and keep the catalog you have. Upgrading from 2.2.2 means your old profiles won't carry over — read the v3.0.0 release notes first.

### Fixed

**Big layouts build again.** Build & Install used to stop with "Class KazBarsData excess 32K bytecode limit" once your grids tracked roughly 600 or more distinct buffs between them — the starter profile plus one more grid of about 50 new buffs was enough. Any layout within the 64-slot cap now builds, however large the buff database grows. Nothing changes in-game.

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
