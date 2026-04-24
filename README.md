# Kaz Grids

Buff/debuff grid overlay editor for **Age of Conan**. Design icon grids that show your active effects on top of the game, then compile and install them in one click.

## Install

1. Download `Kaz Grids.zip` from the [latest release](../../releases/latest) and extract it anywhere.
2. Run `Kaz Grids.exe`.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. Kaz Grids is unsigned because code signing certificates aren't justified for a hobby project.

## Quick start

1. **Set your game folder** — click the `Game:` label in the bottom bar and pick your Age of Conan install folder.
2. **Create a grid** — on the Grids tab, click `+ Add Grid`. A 1×10 horizontal bar is a good starting point.
3. **Choose buffs to track** — click `Tracked Buffs` and pick entries from the database.
4. **Build & Install** — click the green button. Close the game for your first build; after that, rebuild anytime and type `/reloadui` in chat to apply changes.

Up to **64 slots total** across all your grids.

## Features

- **Player or Target grids** — track effects on you or your current target
- **Dynamic mode** — slots auto-fill as buffs activate; choose fill direction, sort order, and grouping
- **Static mode** — pin specific buffs to specific slots
- **Buff database** — map numeric spell IDs to readable names and classify them as Buff (grey), Debuff (red), or Misc (golden)
- **Stacking** — show stack counts over icons for multi-stack effects
- **Timers and flash warnings** — optional remaining-duration text and pulse-on-low-time
- **Ethram-Fal Seed Timer** — always-on-top overlay for the Viscous Seed / Lotus Fixation / Syphon cycle

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable

Kaz Grids only reads files the game writes (combat logs, UI folder). It does not read game memory or inject anything into the game process.

## License

MIT — see [LICENSE](LICENSE).
