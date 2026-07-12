# KazBars

[![CI](https://github.com/kazour/Kazbars/actions/workflows/ci.yml/badge.svg)](https://github.com/kazour/Kazbars/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/kazour/Kazbars?label=release)](https://github.com/kazour/Kazbars/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Buff/debuff overlay editor for **Age of Conan** — design icon grids and bars that show your active effects on top of the game, then compile and install them in one click. It also ships live combat HUDs and a handful of in-game extras: a cast timer, a stopwatch, leaner damage numbers, a real-time deeps meter, and the Ethram-Fal seed timer.

Most of what KazBars builds is set up once and runs on its own after you close the app. Only the two live combat overlays — the deeps meter and the Ethram-Fal seed timer — keep working while KazBars is open.

> **Upgrading from Kaz Grids?** Install over it — no uninstall needed. Your settings and game folder carry over automatically.

## Features

**KazBars** — custom icon overlays arranged in bars or grids that show only the buffs and debuffs you choose to track.

- **Player and Target grids** — track effects on you and your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric buff IDs to readable names and classify them as Buff, Debuff, or Misc

**Cast Timer** — an on-screen readout of your and your target's current cast time, ready to sit over the game's cast bars. Off by default

**Stopwatch** — a draggable Start / Pause / Reset count-up timer that works in fullscreen and never steals focus from the game. Off by default

**Damage Numbers** — a leaner, faster rewrite of the game's floating combat numbers, with new layout and behavior settings. Needs the Aoc.exe launcher bypass: it replaces a stock `.swf` the game's patcher restores otherwise, so rebuild after each patcher run if you don't have the bypass. Off by default

**Deeps by Veni** — a real-time meter that reads your combat log for DPS out, DPS in, HPS out, HPS in, and ΔHP in.

**Ethram-Fal Seed Timer** — tracks the Viscous Seed / Lotus Fixation / Syphon cycle so the raid can time scorpion kills.

## Utility tools

**Default Buff Bars editor** — tune the game's own buff-bar HUD from one place: on/off, icon size, spacing, columns, friendly/hostile filter — no XML editing.

**Damage number colors** — recolor every damage source from one place.

**Backup & restore** — save your full Age of Conan config plus your KazBars profiles and settings to one portable zip, and restore it after a reformat or on a new PC.

## Install

1. Download `KazBars.zip` from the [latest release](../../releases/latest) and extract it anywhere.

2. Run `KazBars.exe` as Administrator.

3. The first-run setup window opens. Point it at your Age of Conan folder.

4. If it detects the Aoc.exe launcher bypass in that folder, say whether you use it.

5. Choose **Use Defaults** — ready-made grids for common raid buffs and debuffs, sized to your screen. (Or **Start Empty** to build your own from scratch.)

6. Click `Build & Install`. Close the game for your first build; after that, rebuild anytime and apply from chat — `/reloadui` if you use Aoc.exe, or `/reloadui` then `/reloadgrids` on the standard launcher.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then `Tracked Buffs...` to pick what each one watches. Up to **64 slots total** across all your grids.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project.

## Community

Questions, bug reports, and release news live on Discord. [Join the Discord](https://discord.gg/ubK5Guryfa).

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable

KazBars only reads files the game writes (combat logs, UI folder). It does not read game memory or inject anything into the game process.

## Building from source

Developer setup. End users should download a release.

```powershell
# 1. Clone
git clone https://github.com/kazour/Kazbars.git
cd Kazbars

# 2. Install + enable git hooks (uv recommended; pip works too)
uv sync --extra dev --extra build
# or:  pip install -e ".[dev,build]"
uv run pre-commit install   # one-time per clone (pip users: drop "uv run"); runs ruff lint + pytest on every commit

# 3. Run from source
uv run python -m kazbars

# 4. Tests
uv run pytest

# 5. Lint  (formatting is intentionally not enforced — see .pre-commit-config.yaml)
uv run ruff check src tests

# 6. Build a distributable .exe
uv run pyinstaller kazbars.spec
# Output: dist/KazBars/KazBars.exe + bundled assets
```

The PyInstaller build is reproducible from the checked-in [`kazbars.spec`](kazbars.spec) and the committed [`uv.lock`](uv.lock) (CI installs with `uv sync --locked`). CI builds the same artifact on every tagged release via [`.github/workflows/release.yml`](.github/workflows/release.yml).

## Documentation

See **[`docs/README.md`](docs/README.md)** for the full doc map — every doc with its audience and when to update it (changelog, architecture, flows, database changelog).

The project follows a `src/` layout — entry point is `python -m kazbars`, which loads `KazBarsApp` from [`src/kazbars/app.py`](src/kazbars/app.py).

## Releasing

Releases are tag-driven. Bump `__version__` in [`src/kazbars/__init__.py`](src/kazbars/__init__.py), update [`docs/CHANGELOG.md`](docs/CHANGELOG.md) and [`.github/release-notes.md`](.github/release-notes.md), then:

```bash
git tag v2.0.0
git push origin v2.0.0
```

The release workflow builds `KazBars.zip` + SHA256 checksum and publishes them as a GitHub release.

## License

MIT — see [LICENSE](LICENSE).
