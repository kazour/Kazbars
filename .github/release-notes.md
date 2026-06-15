## What's New in v2.2.0

New **Damage Numbers** overlay, an in-game stopwatch, and a simpler Deeps alarm.

### Added
- **Damage Numbers.** A leaner rewrite of Age of Conan's floating combat numbers, installed on your next Build & Install (Game ▸ Damage number Mod… / Damage number Colors…). The headline fix: ranged hits stop shrinking to nothing at distance — a **Keep ranged numbers big** toggle holds the size of ranged damage past about 15 metres without touching your melee numbers. You can also set the shadow style, the pop-in and fade speed, and where numbers land (above the target, in fixed columns, or a zig-zag stack), with **Default** and **Performance** presets. Two toggles group or split your resource numbers so your own mana/stamina reads in one steady place, and a **Damage number colors** editor recolors every source — incoming and outgoing hits, crits, spells, combos, heals, mana/stamina — for you and your target separately. Off by default behind one master toggle; your stock `DamageInfo.swf` is backed up once, so turning it off restores the original.
- **In-game stopwatch.** An optional Start / Pause / Reset count-up timer that lives inside the game overlay (Game ▸ In-game stopwatch…), so it works in fullscreen and never steals focus from the game. A compact draggable panel showing `h:mm:ss`; the `−` button collapses it to its title bar, which then shows the running time. Off by default.

### Changed
- **Deeps "Alarm & Tints" is simpler.** The DPS-out alarm is now a slider over a 1000–4000/s band instead of a typed value, and the survival tints collapse into two presets — **Standard** (DPS / healers) and **Tank** (a wider band). Your saved alarm value is kept and clamped into the slider's band.
- **Buff catalog reorganized.** Clearer categories with a new **#Protections** group, plainer names (#Resistances → #Immunities, #Global → #General, #Group HoT → #Group Heals), and the raid tiers grouped under **#Raid T3…T6**.
- **Refreshed default profile.** The out-of-the-box grids are redesigned with clear names: My Buffs, Raid Debuffs, Target Buffs, Target Debuffs.

### Fixed
- **Cast Timer no longer flashes a bogus estimate** during lag or cast interrupts. It now reads the clock and cast progress on the same frame, so a stutter can't spike the number.

---

Buff/debuff grid overlay editor for **Age of Conan**. Design icon grids that show your active effects on top of the game, then compile and install them in one click.

## Highlights

- **Player and Target grids** — track effects on you or your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric spell IDs to readable names and classify them as Buff, Debuff, or Misc
- **Deeps** — real-time combat overlay showing DPS out, DPS in, HPS out, HPS in, and ΔHP in; the DPS-out cell pulses red past a threshold you set
- **Damage Numbers** — a leaner rewrite of the game's floating combat numbers, so ranged hits stop shrinking at distance; tune shadow, speed, and placement, and recolor each source. Off by default; restores stock when you turn it off
- **Cast-timer overlay** — optional on-screen readout of your and your target's current cast time, styled alongside your grids
- **In-game stopwatch** — a draggable Start / Pause / Reset count-up timer that works in fullscreen and never steals focus. Off by default
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
