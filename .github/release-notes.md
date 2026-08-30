## What's New in v3.1.0

A small update: 1 added, 1 changed.

### Added

- **KazBars updates itself.** When a newer release is out, the launch notice reads "KazBars vX is available — click to install": one click downloads it in the background, a second click restarts KazBars into the new version. Your profiles, settings, custom buffs and buff-database updates stay exactly where they are — no re-download, no first-time setup, no old folder to delete. If a download fails, nothing changes and the notice opens the release page instead. Installs older than this release still need one manual update: extract the new zip over your existing KazBars folder.

### Changed

- **One check for everything.** Updates ▸ Check for updates now looks for a new KazBars release first and, when you're already current, for buff-database updates — replacing the two separate menu items. The About window's check now starts the install directly.

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

1. Download `KazBars.zip` below and extract it anywhere. Upgrading from 3.0.1 or earlier? Extract it over your existing KazBars folder instead — profiles and settings survive, and from then on KazBars offers updates itself.
2. Run `KazBars.exe` as Administrator.
3. The first-run setup window opens. Point it at your Age of Conan folder.
4. Choose **Use Defaults** — ready-made grids for common raid buffs and debuffs, sized to your screen. (Or **Start Empty** to build your own from scratch.)
5. Click `Build & Install`. Close the game and the patcher for your first build. After that, rebuild anytime and type `/reloadui` in-game.
6. Launch the game from its own executable, not the patcher — KazBars offers to create a desktop shortcut (DX10 or DX9) after your first build. Launching this way is what keeps your setup in place.

Positioning happens in-game: press Shift+Ctrl+Alt for preview mode and drag your grids and panels where you want them. The game remembers where you left them, across relogs and restarts.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then `Tracked Buffs...` to pick what each one watches.

> **SmartScreen warning**: on a first install, Windows may flag the `.exe` as unrecognized. Click **More info** → **Run anyway**. Updates KazBars installs on its own don't trigger it. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
