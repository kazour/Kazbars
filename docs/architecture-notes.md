# KzGrids-Editor — architecture notes

Knowledge that emerged from Check #2 audit cycles but doesn't fit naturally in `docs/flows.md` (flow narratives) or `docs/architecture.md` (symbol map). These are observations about the **shape** of the codebase that future flow authors should be aware of.

**Source**: 3 findings surfaced by CC during the Flow 6 gloss re-audit (`out/check2-flow6-rerun.md`), 2026-04-25. Locations refreshed 2026-04-25 after the `kzgrids.py` → satellite refactor (commit c676449).

---

## Finding 1 — `profile_io.load_profile` is a profile fan-out point, not a pure loader

**Location**: `Modules/profile_io.py` — historically the issue lived inside a single `load_profile()` function at lines 60-100, with the boss-timer dispatch at lines 84-85, mirrored by `do_save_profile()` at lines 142-170 (boss-timer pull at lines 153-154).

**What the function did**: read a JSON profile, hand `data['grids']` to `grids_panel.load_profile_data()`, set `last_profile`. **In addition**, conditionally dispatched `data.get('boss_timer', {})` to the live `BossTimer` instance via `app._boss_timer_if_alive()`.

**Implication**: `load_profile` had **multi-consumer side effects**. The boss-timer dispatch was invisible whenever the live tracker was closed (which is always the case at first launch — that's why Flow 6 step 6's gloss legitimately elided this).

**Risk for future flows**: if anyone narrated a flow like "open boss timer and load its previous state from a profile", that flow would partially overlap with `load_profile` already handling half of it. The flow author needs to know that `load_profile` was not just a loader.

**Symmetric concern**: `do_save_profile` had the mirror shape — it pulled `bt.get_profile_data()` from the live tracker and wrote it into the profile JSON. Any flow touching save-while-tracker-open must account for this round-trip.

**Status (2026-04-25)**: docstrings on `load_profile` / `do_save_profile` updated to flag the boss-timer side effect; Flows 2 and 3 in `docs/flows.md` cross-reference the dispatch step inline.

**Status (2026-04-27)**: refactored. `load_profile` split into `read_profile_file` (`profile_io.py:70`, pure I/O, returns `(data, is_corrupt)`) and `apply_profile_data` (`profile_io.py:82`, dispatch step — boss-timer fan-out now lives at lines 103-104 in a function whose name and docstring announce it). All four call sites compose the two explicitly: `kzgrids.py:137` (startup auto-load), `profile_io.open_profile()`, `profile_io.load_default_profile()`, `first_launch.py:322`. The `_load_profile` delegator in `kzgrids.py` was removed. `do_save_profile` retained as orchestrator (`profile_io.py:194`) because the error-handling Messagebox + bool return would otherwise repeat at every save site; its body is now a 3-step compose of `build_profile_payload` (`profile_io.py:161`, names the boss-timer pull explicitly in its docstring), `write_profile_file` (`profile_io.py:176`, pure I/O), and `_commit_saved_profile` (`profile_io.py:182`, post-save state).

---

## Finding 2 — `_set_game_if_provided` is shared between two first-launch branches

**Location**: `Modules/first_launch.py:166` (definition), called from both:
- `load_default()` at `first_launch.py:180` — the path narrated by Flow 6
- `start_empty()` at `first_launch.py:185` — the sibling branch, currently undocumented

**What it does**: centralizes the "fire all path-related callbacks" sequence — `on_game_set`, `on_aoc_bypass_set`, `on_resolution_set` in order on the parent.

**Implication**: the **Start Empty branch also persists game path, Aoc bypass, and resolution**. Currently invisible in `docs/flows.md`. The only thing unique to "Load Defaults" is the actual default-profile load + scale + save chain.

**If a Flow 13 ("first-launch start empty") is ever added**: it shares steps 1-4 with Flow 6 verbatim, then diverges. Worth structuring the doc to share or cross-reference rather than duplicate.

**Side note**: `welcome_data` (the cross-closure dict mentioned in Flow 6 step 1) is **intentionally populated only by `on_load_default`**. The Start Empty and Skip paths leave it empty, suppressing the welcome popup. This is a subtle protocol — easy to miss when reading any individual closure.

**Status (2026-04-25)**: Flow 13 ("First Launch — Start Empty") added to `docs/flows.md`, cross-referencing Flow 6 steps 1-4 and naming the shared `_set_game_if_provided` dispatcher.

---

## Finding 3 — the dialog→app callback boundary needs a structurally explicit step

**Pattern observed**: pre-regen, Flow 6 had `show_first_launch_dialog` followed directly by `on_load_default`, with no intermediate step for the dialog-side dispatcher. The result was that `on_load_default`'s gloss had to absorb both dialog-internal AND app-internal responsibilities, which is exactly where the caller/callee confusion crept in.

**Resolution**: post-regen Flow 6 has step 4 = `load_default()` (the dialog-side dispatcher in `first_launch.py:180`) explicitly named between the dialog builder (step 2) and the app-side closure (step 5). The boundary is now diagrammatic.

**Generalization for future audits**: whenever a flow crosses the dialog→app boundary (or any equivalent process boundary — thread, subprocess, IPC), the dispatcher itself deserves an explicit step. Eliding it is what produces caller/callee confusion. This pattern likely recurs in:

- Drag-drop dialogs (any `_on_drop` handler that calls into app methods)
- Settings dialogs (any `_apply_settings` style dispatcher)
- Any `Toplevel` subclass that runs callbacks on `<Destroy>` or `protocol("WM_DELETE_WINDOW", ...)`

**Status (2026-04-25)**: convention codified in the `docs/flows.md` preamble. Confirmed compliant: Flow 4 (`on_create`), Flow 5 (`on_ok`), Flow 13 (`start_empty`). Flow 6 names the app-side closure (`on_load_default`) but elides the dialog-side dispatcher (`load_default()` at `first_launch.py:180`) — a future regen of Flow 6 should insert it as an explicit step between current steps 4 and 5.

---

## Meta-observation on flow document scope

These three findings have something in common: they describe **structural facts that no individual flow can fully capture**. They live above the flow level — at the architecture level — but are too narrow for the high-level `docs/architecture.md` symbol map. This file is the right home for them.

If the audit-codebase skill is promoted with Phase 3.6 (Check #2), this kind of file should probably become a **standard output**: a place to record findings that emerge during audit but don't fit anywhere else. Suggested name pattern: `docs/architecture-notes.md`.
