## What's New in v3.1.1

A small update: 1 changed.

### Changed

- **KazBars has its own icon.** A 3×3 buff grid with the top row lit in the app's blue, in the title bar, the taskbar, Alt-Tab and on `KazBars.exe` itself — replacing the generic placeholder and the ttkbootstrap logo.

---

Buff/debuff overlay editor for **Age of Conan**. Design icon grids or bars that show your active effects on top of the game, then compile and install them in one click.

## Highlights

**KazBars** — custom icon overlays arranged in bars or grids that show only the buffs and debuffs you choose to track.
- **Player and Target grids** — track effects on you and your current target
- **Overhead grids** — icons that float over the heads of your group, friendly players and whoever you're fighting
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Per-class grids** — give each class its own grids, so one profile covers every character you play
- **Buff database** — map numeric buff IDs to readable names and classify them as Buff, Debuff, or Misc

**Cast Timer** — an on-screen readout of your and your target's current cast time, ready to sit over the game's cast bars. Off by default

**Stopwatch** — a simple, draggable Start / Pause / Reset count-up timer. Off by default

**Inspect panel** — an in-game combat sheet for your current target, with the rows you pick from 112 stats and a PvP tab on players; drag or fold it and the game remembers. Off by default

**Console** — an in-game log of every buff and debuff on you and your target with its buff ID, plus how each cast ended. Off by default

**Onslaught tracker** — for Skull Gate and Kuthchemes: the bosses, skulls and minis in view with their health, the wave timer, Hylda's health, spawn alerts and AoE warnings. Off by default

**Damage Numbers** — a leaner, faster rewrite of the game's floating combat numbers, with new layout and behavior settings. Off by default

**Deeps by Veni** — a real-time meter that reads the combat log for your DPS out, DPS in, HPS out, HPS in, and ΔHP in

**Ethram-Fal Seed Timer** — tracks the Viscous Seed / Lotus Fixation / Syphon cycle to help the raid time scorpion kills

## Utility tools

**Default Buff Bars editor** — tune the game's own buff-bar HUD from one place: on/off, icon size, spacing, columns, friendly/hostile filter — no XML editing

**Damage number colors** — set a color and a direction for every damage source from one place, applied the moment you hit Apply, no build

**Backup & restore** — save your full Age of Conan config plus your KazBars profile and settings to one portable zip, and restore it after a reformat or on a new PC

**Repair game install** — after a game patch, run the official patcher once, then Repair re-registers KazBars, restores your saved positions from a safety snapshot and puts the Damage Numbers mod back; a startup check offers it when the game stopped loading KazBars

## Install

1. Download `KazBars.zip` below and extract it anywhere. Upgrading from 3.0.1 or earlier? Extract it over your existing KazBars folder instead — your profile and settings survive, and from then on KazBars offers updates itself.
2. Run `KazBars.exe` as Administrator.
3. The first-run setup window opens. Point it at your Age of Conan folder.
4. Choose **Use Defaults** — ready-made grids for common raid buffs and debuffs, sized to your screen. (Or **Start Empty** to build your own from scratch.)
5. Click `Build & Install`. Close the game and the patcher for your first build. After that, rebuild anytime and type `/reloadui` in-game.
6. Launch the game from its own executable, not the patcher — KazBars offers to create a desktop shortcut (DX10 or DX9) after your first build. Launching this way is what keeps your setup in place.

Positioning happens in-game: press Shift+Ctrl+Alt for preview mode and drag your grids and panels where you want them. The game remembers where you left them, across relogs and restarts.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then click a grid's preview to pick what it watches (on a static grid, click a slot).

> **SmartScreen warning**: on a first install, Windows may flag the `.exe` as unrecognized. Click **More info** → **Run anyway**. Updates KazBars installs on its own don't trigger it. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
