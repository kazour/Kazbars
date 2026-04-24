# Architectural Audit: KzGrids-Editor

**Date:** 2026-04-24  
**Scope:** Internal module dependencies and coupling analysis  
**Files analyzed:** 19 Python files

## 1. Star Topology Hypothesis Analysis

**Hypothesis:** PARTIALLY CONFIRMED

Command used: `grep -E "^from \.\|^from Modules\|^import \." /home/s/code/KzGrids-Editor/**/*.py`

### Internal Import Matrix

**Files importing from ui_helpers:** 9 files

Command used: `grep -l "from.*ui_helpers import\|from Modules.ui_helpers import" /home/s/code/KzGrids-Editor/*.py /home/s/code/KzGrids-Editor/Modules/*.py 2>/dev/null`

- kzgrids.py (lines 18-28)
- Modules/grids_panel.py (lines 18-30)
- Modules/grid_dialogs.py (lines 14-25)
- Modules/database_editor.py (lines 22-29)
- Modules/instructions_panel.py (lines 5-11)
- Modules/live_tracker_panel.py (lines 21-27)
- Modules/build_loading.py (lines 16-21)
- Modules/first_launch.py (lines 10-19)
- Modules/timer_overlay.py (line 9)

**Direct module-to-module dependencies (bypassing ui_helpers):**

Command used: `grep -E "from \.(grid_|build_|live_tracker|boss_|timer_|combat_|first_|database_|instructions_)" /home/s/code/KzGrids-Editor/Modules/*.py`

- `build_executor.py → build_utils.py` (line 12)
- `first_launch.py → build_executor.py` (line 19)  
- `grid_dialogs.py → grid_model.py` (line 26)
- `grids_generator.py → build_utils.py` (line 13)
- `grids_panel.py → grid_dialogs.py` (line 12)
- `grids_panel.py → grid_model.py` (lines 13-17)
- `live_tracker_panel.py → live_tracker_settings.py` (lines 14-17)
- `live_tracker_panel.py → boss_timer.py` (line 18)
- `live_tracker_panel.py → combat_monitor.py` (line 19)
- `live_tracker_panel.py → timer_overlay.py` (line 20)
- `boss_timer.py → live_tracker_settings.py` (line 11)
- `timer_overlay.py → live_tracker_settings.py` (line 8)

**Import style analysis:**

Relative imports (command: `grep -c "from \.*ui_helpers import" /home/s/code/KzGrids-Editor/*.py /home/s/code/KzGrids-Editor/Modules/*.py 2>/dev/null`): 6 files
- Modules/database_editor.py, grid_dialogs.py, live_tracker_panel.py, first_launch.py, timer_overlay.py, grids_panel.py

Absolute imports (command: `grep -c "from Modules.ui_helpers import" /home/s/code/KzGrids-Editor/*.py /home/s/code/KzGrids-Editor/Modules/*.py 2>/dev/null`): 3 files  
- kzgrids.py, Modules/build_loading.py, instructions_panel.py

**Topology:** Hub-and-spoke with local clusters. ui_helpers.py serves as the primary hub (9/19 files depend on it), but significant module-to-module dependencies exist in two domains:
1. **Grid editing cluster:** grids_panel ↔ grid_dialogs ↔ grid_model
2. **Live tracker cluster:** live_tracker_panel → [boss_timer, combat_monitor, timer_overlay] → live_tracker_settings
3. **Build utilities cluster:** [build_executor, grids_generator] → build_utils

## 2. Contents of ui_helpers.py by Responsibility

**File size:** 1,497 lines  
**Public symbols count:** 69 (command: `grep -E "^(def|class|[A-Z][A-Z0-9_]*\s*=)" /home/s/code/KzGrids-Editor/Modules/ui_helpers.py | wc -l`)

### Categorization Analysis

Command used: `grep -A1 "^# ===.*===.*$" /home/s/code/KzGrids-Editor/Modules/ui_helpers.py`

#### UI Constants (Lines 12-116, ~104 lines)  
**Public symbols: 38** (command: `grep -c "^FONT_" && grep -c "^PAD_\|^BTN_\|^OVERLAY_\|^MODULE_\|^GRID_TYPE_\|^SCANLINE_" && grep -c "^THEME_COLORS\|^TK_COLORS\|^_RETRO_COLORS"`)
- **Font constants:** 13 symbols (FONT_FAMILY, FONT_HEADING, etc.)
- **Layout constants:** 22 symbols (PAD_*, BTN_*, OVERLAY_*, etc.)  
- **Color dictionaries:** 3 symbols (THEME_COLORS, TK_COLORS, _RETRO_COLORS)
- **Consumed by:** All 9 files that import from ui_helpers

#### UI Helper Widgets (Lines 117-282, ~165 lines)  
**Public symbols: 5** (command: `sed -n '117,282p' ui_helpers.py | grep -c "^def "`)
- **Functions:** 5 (debounced_callback, blend_alpha, create_dialog_header, etc.)
- **Consumed by:** 7/9 files (excluding timer_overlay, build_loading)

#### Interaction Helpers (Lines 283-599, ~316 lines)  
**Public symbols: 7** (command: `sed -n '283,599p' ui_helpers.py | grep -E "^def |^class " | wc -l`)
- **Functions:** 5 (create_tip_bar, bind_card_events, add_tooltip, etc.)
- **Classes:** 2 (_InAppToolTip, CollapsibleSection)
- **Consumed by:** 6/9 files

#### Raw TK Widget Styling (Lines 600-649, ~49 lines)  
**Public symbols: 5** (command: `sed -n '600,649p' ui_helpers.py | grep -c "^def "`)
- **Functions:** 5 (style_tk_listbox, style_tk_text, apply_dark_titlebar, etc.)
- **Consumed by:** 3/9 files (grid_dialogs, database_editor, instructions_panel)

#### Settings Management (Lines 650-661, ~11 lines)  
**Public symbols: 3** (part of command: `sed -n '650,761p' ui_helpers.py | grep -c "^def "`)
- **Functions:** 3 (init_settings, get_setting, set_setting)
- **Global state:** 1 module-level `_settings` variable  
- **Consumed by:** 4/9 files (kzgrids, grid_dialogs, database_editor, grids_panel)

#### Window Position Persistence (Lines 662-761, ~99 lines)  
**Public symbols: 4** (part of command: `sed -n '650,761p' ui_helpers.py | grep -c "^def "`)  
- **Functions:** 4 (clamp_to_screen, save/restore_window_position, bind_window_position_save)
- **Consumed by:** 7/9 files

#### Custom TTK Styles (Lines 762-776, ~14 lines)  
**Public symbols: 1** (command: `sed -n '762,776p' ui_helpers.py | grep -c "^def "`)
- **Functions:** 1 (setup_custom_styles)
- **Consumed by:** 1/9 files (kzgrids.py only)

#### Complex Widget Classes (Lines 777-1497, ~720 lines)  
**Public symbols: 7** (command: `sed -n '777,1497p' ui_helpers.py | grep -E "^def |^class " | wc -l`)
- **Classes:** 3 (DragReorderManager, ToastManager, CustomMenuBar)
- **Supporting functions:** 4 (create_scrollable_frame, mousewheel handlers, etc.)
- **Consumed by:** 5/9 files

### Responsibility Spread Analysis

**Qualitative impression:** ui_helpers.py violates single responsibility principle by mixing:
- Design tokens (appropriate centralization)
- Business logic (settings persistence - should be separate module)
- Complex widget implementations (should be individual modules)
- Utility functions (appropriate shared location)

## 3. PyInstaller Hidden Import Analysis

**Investigation target:** Why `--hidden-import Modules.ui_helpers` is required in build.py:92

Command used: `grep -n "hidden-import" /home/s/code/KzGrids-Editor/build.py`

**Evidence in build.py lines 81-96:**
```python
--hidden-import", "Modules.ui_helpers",
```

**Code-based justification:** NO EXPLICIT JUSTIFICATION FOUND

**Analysis of import patterns:**
1. ui_helpers.py contains no dynamic imports or `__import__()` calls (verified by reading file)
2. All imports of ui_helpers use explicit `from .ui_helpers import` or `from Modules.ui_helpers import` syntax
3. No conditional imports or plugin-style loading detected
4. No `importlib` usage found in codebase

**Hypothesis:** The hidden-import directive appears to be defensive rather than necessary. PyInstaller's static analysis should detect all ui_helpers imports since they use explicit import statements. The directive may be legacy from a previous version or added as a precautionary measure.

**Additional context:** build.py declares hidden imports for ALL 17 modules (lines 81-96), suggesting a blanket approach rather than selective inclusion based on analysis failures.

## 4. Dependency Cycles and Coupling Hotspots

**Analysis method:** Manual trace of import chains from dependency matrix above.

### Identified Issues

#### 1. No Import Cycles Detected
**Status:** NO CIRCULAR DEPENDENCIES FOUND  
All dependency chains terminate without cycles.

#### 2. High Fan-In Coupling: ui_helpers.py  
**Severity:** HIGH  
**Evidence:** 9 of 19 files (47.4%) depend on ui_helpers.py
**Files affected:** All major UI modules
**Risk:** Changes to ui_helpers require rebuilding 47.4% of the application

#### 3. Mixed Import Conventions
**Severity:** MEDIUM  
**Evidence:** Two import styles coexist without pattern:
- Relative: `from .ui_helpers import` (6 files)
- Absolute: `from Modules.ui_helpers import` (3 files: kzgrids.py, build_loading.py, instructions_panel.py)
**Risk:** Inconsistent module resolution, potential refactoring errors

#### 4. Fat Interface: ui_helpers Exports
**Severity:** MEDIUM  
**Evidence:** 69 public symbols exported from single module
**Breakdown:** Most files import 15-25 symbols each from ui_helpers
**Risk:** Interface bloat, difficult to reason about dependencies

#### 5. Business Logic in UI Module
**Severity:** MEDIUM  
**Evidence:** Settings persistence functions in ui_helpers.py (lines 650-761)
- `init_settings()`, `get_setting()`, `set_setting()`  
- Module-level `_settings` global state
**Risk:** Architectural layer violation, business logic coupled to UI concerns

### No Critical Hotspots
**Cluster isolation:** Grid editing and Live tracker clusters remain appropriately isolated. No cross-cluster dependencies detected beyond ui_helpers.

---

**Analysis complete.** No recommendations phase - observations only per requirements.