## What's New in v2.1.0

Deeps readout tuning, plus a couple of reliability fixes.

### Added
- **Deeps Readout presets.** A new Readout card in the Deeps panel: pick the rolling-window width (5 / 7 / 11 / 13 s) and a Style — **Live** (every spike shows), **Steady** (calm but responsive), or **Calm** (heavy smoothing, chunky numbers). Ships on Steady. The alarm and tints still track the raw values, so only the digits ease.
- **Crash log on disk.** The app writes a rotating `logs/kazbars.log` next to the `.exe`, so a crash with no console still leaves a trail to share.

### Changed
- **Smoother Deeps alarm.** The DPS-out alarm glides through its pulse instead of stuttering, and the incoming-damage / net-HP cells ramp through amber as the deficit grows instead of snapping on at one threshold.
- **More in-app Help.** The Help view now covers Deeps, the Cast Timer, Backup & restore, the Default Buff Bars editor, the buff-discovery console, and game resolution.

### Fixed
- **Unusual grid names can't break the build.** Grid names with quotes, newlines, or backslashes are now escaped when generating the overlay code, so they can't corrupt the build.

---

Buff/debuff grid overlay editor for **Age of Conan**. Design icon grids that show your active effects on top of the game, then compile and install them in one click.

## Highlights

- **Player and Target grids** — track effects on you or your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric spell IDs to readable names and classify them as Buff, Debuff, or Misc
- **Deeps** — real-time combat overlay showing DPS out, DPS in, HPS out, HPS in, and ΔHP in; the DPS-out cell pulses red past a threshold you set
- **Damage Numbers** — a leaner rewrite of the game's floating combat numbers, so ranged hits stop shrinking at distance; tune shadow, speed, and placement, and recolor each source. Off by default; restores stock when you turn it off
- **Cast-timer overlay** — optional on-screen readout of your and your target's current cast time, styled alongside your grids
- **Default Buff Bars editor** — edit the in-game HUD widgets (icon size, spacing, columns, friendly/hostile filter) without hand-editing XML
- **Ethram-Fal Seed Timer** — always-on-top overlay for the Viscous Seed / Lotus Fixation / Syphon cycle
- **Backup & restore** — save your full Age of Conan config plus your KazBars profiles and settings to one portable zip, and restore it after a reformat

## Install

1. Download `KazBars.zip` below and extract it anywhere.
2. Run `KazBars.exe`.
3. Click the `Game:` label in the bottom bar and pick your Age of Conan folder.
4. In the Grids view, click `+ Add Grid` — a 1×10 horizontal bar is a good starting point.
5. Click `Tracked Buffs...` and pick entries from the database.
6. Click `Build & Install`. Close the game for your first build; after that, rebuild anytime and type `/reloadui` in chat to apply changes.

## Upgrading from Kaz Grids

Install over it — no uninstall needed. Your settings and game folder carry over automatically.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
