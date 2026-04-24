## What's New in v1.1.0

### Added
- Background check for new releases on launch. Click the toast to open release notes.
- File → Uninstall from game client. Cleanly removes Kaz Grids files from the selected install.

### Changed
- Grids now reference buffs by spell ID instead of name. Renaming a buff in the database no longer breaks grids that use it. Existing profiles migrate automatically on load; any buffs that can't be resolved are listed in a dialog so you can re-add them.
- About dialog now links to the GitHub repo.

### Fixed
- Database changes are now saved when you close the app and click "Yes" on the unsaved-changes prompt. Previously only the profile was saved.
- Build now refuses to run if an enabled grid has no tracked buffs, instead of installing a silent grid.
- Invalid entries in the Add Buff ID field show a warning before saving instead of being dropped silently.
- Welcome popup no longer references a non-existent "Edit → Clear All Grids" menu path.

---

Buff/debuff grid overlay editor for **Age of Conan**. Design icon grids that show your active effects on top of the game, then compile and install them in one click.

## Highlights

- **Player and Target grids** — track effects on you or your current target
- **Dynamic or Static slots** — auto-fill as buffs activate, or pin specific buffs to specific slots
- **Buff database** — map numeric spell IDs to readable names and classify them as Buff, Debuff, or Misc
- **Ethram-Fal Seed Timer** — always-on-top overlay for the Viscous Seed / Lotus Fixation / Syphon cycle

## Install

1. Download `Kaz Grids.zip` below and extract it anywhere.
2. Run `Kaz Grids.exe`.
3. Click the `Game:` label in the bottom bar and pick your Age of Conan folder.
4. On the Grids tab, click `+ Add Grid` — a 1×10 horizontal bar is a good starting point.
5. Click `Tracked Buffs` and pick entries from the database.
6. Click `Build & Install`. Close the game for your first build; after that, rebuild anytime and type `/reloadui` in chat to apply changes.

> **SmartScreen warning**: Windows may flag the `.exe` as unrecognized on first launch. Click **More info** → **Run anyway**. Kaz Grids is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `Kaz Grids.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "Kaz Grids.zip"` in PowerShell.

## Requirements

- Windows 10 or 11
- Age of Conan installed
- No Python install needed — ships as a standalone executable
