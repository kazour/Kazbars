## What's New in v2.0.0 — KazBars rebrand

The mod everyone has always called KazBars now actually calls itself KazBars. Existing Kaz Grids users can install on top — the build pipeline auto-cleans the old files, and your settings (game folder, AoC bypass preference, window position) carry over on first launch.

### Changed
- Renamed throughout: app title, deployed `KazBars.swf`, `Aoc/KazBars/` module folder, XML element IDs, auto-load marker. Predecessor names (`kzgrids.swf`, `KzGrids.swf`, `KazGrids.swf`, `Aoc/{KzGrids,KazGrids,Kazbars}/`, `# KzGrids auto-load`) are removed automatically by the install step.
- Settings file: `kzgrids_settings.json` → `kazbars_settings.json`. Migrated automatically on first launch — no reconfiguration needed.

### Internal (no user-visible behavior change)
- Project moved to a `src/` layout; entry point is `python -m kazbars`. Build is now `pyinstaller kazbars.spec` (replaces the old `build.py` wrapper).
- Tests run via `pytest`. CI runs lint + tests on every push.

---

Buff/debuff grid overlay editor for **Age of Conan**. Design icon grids that show your active effects on top of the game, then compile and install them in one click.

## Highlights

- **Player and Target grids** — track effects on you or your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric spell IDs to readable names and classify them as Buff, Debuff, or Misc
- **Default Buff Bars editor** — edit the in-game HUD widgets (icon size, spacing, columns, friendly/hostile filter) without hand-editing XML
- **Ethram-Fal Seed Timer** — always-on-top overlay for the Viscous Seed / Lotus Fixation / Syphon cycle

## Install

1. Download `KazBars.zip` below and extract it anywhere.
2. Run `KazBars.exe`.
3. Click the `Game:` label in the bottom bar and pick your Age of Conan folder.
4. On the Grids tab, click `+ Add Grid` — a 1×10 horizontal bar is a good starting point.
5. Click `Tracked Buffs` and pick entries from the database.
6. Click `Build & Install`. Close the game for your first build; after that, rebuild anytime and type `/reloadui` in chat to apply changes.

## Upgrading from Kaz Grids

Just install KazBars — that's it. No need to uninstall the old version first; the build pipeline replaces `KazGrids.swf` with `KazBars.swf` and removes the old auto-load marker. Your existing settings and last profile carry over automatically on first launch.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
