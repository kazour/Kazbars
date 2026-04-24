# Changelog

All notable changes to Kaz Grids will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.1.0] — 2026-04-22

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

## [1.0.0] — 2026-04-18

Initial public release.
