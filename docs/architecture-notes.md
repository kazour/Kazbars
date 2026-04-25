# KzGrids-Editor — architecture notes

Knowledge that emerged from Check #2 audit cycles but doesn't fit naturally in `docs/flows.md` (flow narratives) or `docs/architecture.md` (symbol map). These are observations about the **shape** of the codebase that future flow authors should be aware of.

**Source**: 3 findings surfaced by CC during the Flow 6 gloss re-audit (`out/check2-flow6-rerun.md`), 2026-04-25. Locations refreshed 2026-04-25 after the `kzgrids.py` → satellite refactor (commit c676449).

---

## Finding 1 — `profile_io.load_profile` is a profile fan-out point, not a pure loader

**Location**: `Modules/profile_io.py:46-79`, specifically lines 69-70 (the boss-timer dispatch). `kzgrids.py:520` keeps a one-line `_load_profile` delegator for back-compat with internal callers.

**What the function does**: reads a JSON profile, hands `data['grids']` to `grids_panel.load_profile_data()`, sets `last_profile`. **In addition**, conditionally dispatches `data.get('boss_timer', {})` to the live `BossTimer` instance via `app._boss_timer_if_alive()`.

**Implication**: `load_profile` has **multi-consumer side effects**. The boss-timer dispatch is invisible whenever the live tracker is closed (which is always the case at first launch — that's why Flow 6 step 6's gloss legitimately elides this).

**Risk for future flows**: if anyone narrates a flow like "open boss timer and load its previous state from a profile", that flow will partially overlap with `load_profile` already handling half of it. The flow author needs to know that `load_profile` is not just a loader.

**Symmetric concern (confirmed)**: `do_save_profile` has the mirror shape — at `Modules/profile_io.py:130-131` it pulls `bt.get_profile_data()` from the live tracker and writes it into the profile JSON. Any flow touching save-while-tracker-open must account for this round-trip.

**Status (2026-04-25)**: docstrings on `load_profile` / `do_save_profile` updated to flag the boss-timer side effect; Flows 2 and 3 in `docs/flows.md` cross-reference the dispatch step inline.

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
