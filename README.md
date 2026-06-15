# KazBars

[![CI](https://github.com/kazour/Kazbars/actions/workflows/ci.yml/badge.svg)](https://github.com/kazour/Kazbars/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/kazour/Kazbars?label=release)](https://github.com/kazour/Kazbars/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Buff/debuff grid overlay editor for **Age of Conan** — design icon grids that show your active effects on top of the game, then compile and install them in one click. Most of what it builds is set up once and runs on its own after you close the app; two live combat HUDs (the Ethram-Fal seed timer and a real-time deeps meter) keep working only while KazBars is open. A handful of in-game extras round it out.

> **Upgrading from Kaz Grids?** Install over it — no uninstall needed. Your settings and game folder carry over automatically.

## Install

1. Download `KazBars.zip` from the [latest release](../../releases/latest) and extract it anywhere.
2. Run `KazBars.exe`.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project.

## Quick start

1. **Set your game folder** — click the `Game:` label in the bottom bar and pick your Age of Conan install folder.
2. **Start from the default profile** — first launch loads a ready-made set of grids (My Buffs, Raid Debuffs, Target Buffs, Target Debuffs). Build & Install it as-is, or tweak it first.
3. **Add your own grid** (optional) — in the Grids view, click `+ Add Grid`. A 1×10 horizontal bar is a good starting point.
4. **Choose buffs to track** — click `Tracked Buffs...` and pick entries from the database.
5. **Build & Install** — click the green button. If you use the Aoc.exe launcher bypass, close the game for your first build. After that, rebuild anytime and type `/reloadui` in chat to apply changes.

Up to **64 slots total** across all your grids.

## Community

Questions, bug reports, and release news live on Discord. [Join the Discord](https://discord.gg/ubK5Guryfa).

## What it does

Everything KazBars does is one of three kinds of mod, and the kind tells you the
one thing you care about: **whether you ever need the app open again.**

Almost everything is **set up once and forgotten** — you Build & Install, type
`/reloadui`, and close the app. Only the two live overlays need KazBars running
while you play.

### Set up once — Build & Install, then close the app

These compile into the game's UI or patch its skin files. After a build you type
`/reloadui` in chat and never open the editor again, unless you want to change
something.

**Grids** are the flagship — they compile into the game and draw your icons:

- **Player or Target grids** — track effects on you or your current target
- **Dynamic mode** — slots auto-fill as buffs activate; choose fill direction, sort order, and grouping
- **Static mode** — pin specific buffs to specific slots
- **Stacking** — show stack counts over icons for multi-stack effects
- **Timers and flash warnings** — optional remaining-duration text and pulse-on-low-time
- **Buff database** — a curated catalog that maps numeric spell IDs to readable names, classifies them as Buff (grey), Debuff (red), or Misc (golden), and sorts them into categories so you can find what you track
- **Buff-discovery console** — optional in-game overlay that logs effect names and their spell IDs as they land on you or your target, so you can find the numbers to add to the database

Optional extras that also compile into the overlay:

- **Cast-timer overlay** — on-screen readout of your and your target's current cast time, positioned and styled alongside your grids
- **In-game stopwatch** — a draggable Start/Pause/Reset count-up timer that works in fullscreen and never steals focus from the game. Off by default

Two extras change the game's own combat text and HUD — same Build & Install:

- **Damage Numbers** — a leaner rewrite of the game's floating combat numbers. Headline fix: ranged hits stop shrinking to nothing at distance. Also tune shadow, pop-in/fade speed, where numbers land (over the target, in fixed columns, or a zig-zag stack), and recolor each combat-number source. Off by default behind a master toggle; your stock file is backed up, so turning it off restores the original
- **Default Buff Bars editor** — edit the game's own HUD `<BuffListView />` widgets (icon size, spacing, columns, friendly/hostile filter) without hand-editing XML

### Runs while you play — keep KazBars open

These read your combat log in real time and draw always-on-top desktop overlays.
They only work while KazBars is running:

- **Ethram-Fal Live Tracker** — always-on-top overlay for the Viscous Seed / Lotus Fixation / Syphon cycle. A missed timer wipes the raid, so the whole group watches it during the pull
- **Deeps** — real-time combat overlay showing DPS out, DPS in, HPS out, HPS in, and ΔHP in. The DPS-out cell pulses red past a threshold you set; the incoming cells tint as your net HP drops

### And one housekeeping tool

- **Backup & restore** — save your full Age of Conan config plus your KazBars profiles and settings to one portable zip, and restore it after a reformat or a corrupted profile

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

See **[`docs/README.md`](docs/README.md)** for the full doc map — every doc with its audience and when to update it (changelog, architecture, flows, brand brief, visual system).

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
