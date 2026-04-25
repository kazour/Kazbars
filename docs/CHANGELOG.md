# Changelog

All notable changes to Kaz Grids will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Internal: split `Modules/ui_helpers.py` (1,497 lines, 8 responsibilities) into six focused modules: `ui_helpers` (design tokens), `ui_widgets`, `ui_components`, `ui_tk_style`, `window_position`, `settings_manager`. Imports inside `Modules/` are now consistently relative. No user-facing changes.
- Internal: shrank `kzgrids.py` from 1,152 to 741 lines by extracting profile I/O → `Modules/profile_io.py`, game-folder UI → `Modules/game_folder.py`, Build & Install action → `Modules/build_action.py`, and consolidating settings plumbing + JSON helpers into `Modules/settings_manager.py`. `CustomMenuBar` moved out of `ui_components.py` into its own `Modules/custom_menu_bar.py`. Pruned the defensive PyInstaller `--hidden-import` block in `build.py` (PyInstaller discovers all modules via static analysis). No user-facing changes.
- Internal: simplified the four largest functions in `grids_panel.py` and the five largest in `database_editor.py` by extracting builder methods. `GridEditorPanel.__init__` (232 → 60 lines) and `_build_empty_state` (124 → 58 lines) now delegate to focused `_build_*` helpers; `update_labels` reuses a new `_format_buff_preview` for the truncated-name preview that was duplicated for whitelist and slot-assignment paths. `BuffEditDialog.create_widgets`/`on_ok` and `DatabaseEditorTab.create_widgets`/`refresh_list`/`import_buffs` now use `_add_grid_row`, `_build_stacking_section`, `_collect_inputs`, `_apply_stacking_fields`, `_build_filter_bar`/`_build_tree`/`_build_button_bar`, plus module-level `format_stack_indicator` and `migrate_legacy_buff_fields`. New `bind_label_hover_colors` helper in `ui_widgets.py` centralizes the Enter/Leave/FocusIn/FocusOut foreground-toggle pattern previously copy-pasted on hover-able header labels. No user-facing changes.

### Added
- Smoke tests: `tests/test_imports.py` (full import-graph check) and `tests/test_data_integrity.py` (buff-ref resolution in `Default.json` + bundled-DB sync check). Run both before every commit.

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
