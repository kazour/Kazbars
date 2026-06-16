## What's New in v2.2.2

A patch release: a faster, smoother Build & Install.

### Fixed

**Build & Install no longer freezes before it starts.** On some systems, clicking Build & Install hung for about 15 seconds with nothing on screen before the build got going. That's fixed — it now starts near-instantly.

### Changed

**The build screen reads as clear steps.** With the build now near-instant, its progress used to flash past too fast to follow. Each phase — Compiling, Baking damage numbers, Installing — now holds on screen for a brief beat, so you can see what's happening.

---

Buff/debuff overlay editor for **Age of Conan**. Design icon grids or bars that show your active effects on top of the game, then compile and install them in one click.

## Highlights

**KazBars** — custom icon overlays arranged in bars or grids that show only the buffs and debuffs you choose to track.
- **Player and Target grids** — track effects on you and your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric buff IDs to readable names and classify them as Buff, Debuff, or Misc

**Cast Timer** — an on-screen readout of your and your target's current cast time, ready to sit over the game's cast bars. Off by default

**Stopwatch** — a simple, draggable Start / Pause / Reset count-up timer. Off by default

**Damage Numbers** — a leaner, faster rewrite of the game's floating combat numbers with new layout and behavior settings. Needs the Aoc.exe launcher bypass: it replaces a stock `.swf` file that the game's patcher restores otherwise. Rebuild after each patcher run if you don't have launcher bypass. Off by default

**Deeps by Veni** — a real-time meter that reads the combat log for your DPS out, DPS in, HPS out, HPS in, and ΔHP in

**Ethram-Fal Seed Timer** — tracks the Viscous Seed / Lotus Fixation / Syphon cycle to help the raid time scorpion kills

## Utility tools

**Default Buff Bars editor** — tune the game's own buff-bar HUD from one place: on/off, icon size, spacing, columns, friendly/hostile filter — no XML editing

**Damage number colors** — recolor every damage source from one place

**Backup & restore** — save your full Age of Conan config plus your KazBars profiles and settings to one portable zip, and restore it after a reformat or on a new PC

## Install

1. Download `KazBars.zip` below and extract it anywhere.
2. Run `KazBars.exe` as Administrator.
3. The first-run setup window opens. Point it at your Age of Conan folder.
4. If it detects the Aoc.exe launcher bypass in that folder, say whether you use it.
5. Choose **Use Defaults** — ready-made grids for common raid buffs and debuffs, sized to your screen. (Or **Start Empty** to build your own from scratch.)
6. Click `Build & Install`. Close the game for your first build; after that, rebuild anytime and apply from chat — `/reloadui` if you use Aoc.exe, or `/reloadui` then `/reloadgrids` on the standard launcher.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then `Tracked Buffs...` to pick what each one watches.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
