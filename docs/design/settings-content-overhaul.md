# Settings, Profiles & Reference-Content Overhaul — Implementation Plan

**Status:** Ready for implementation · **Created:** 2026-06-08 · **Scope:** full system, phased

A from-scratch redesign of how KazBars stores user settings/preferences, how the buff database
and Default profile are updated, and how profiles are shared. It replaces the four hand-rolled
config layers and the assets-as-user-data anti-pattern with one schema-driven settings core, a
clean `userdata/` storage root, a GitHub-pulled reference-content channel decoupled from the app
binary, and self-contained profile sharing.

This is the agreed design + the phased build order. It is forward-looking; the living docs
(`architecture.md`, `flows.md`, `database-changelog.md`) are updated per-phase as each lands. All
`file:line` references were verified against the working tree on 2026-06-08.

> **Pre-publish clean start (locked).** KazBars has **no real end-user base** — only dev testers
> have a build, and it is distributed to no AoC community. So the app **starts clean: there is no
> legacy migration anywhere.** It does not read, move, archive, or delete any pre-existing
> `settings/`/`profiles/` next to the exe; it creates `userdata/` fresh and starts at defaults.
> No migration messages, no "import your old data" advice. Testers rebuild a profile in seconds.
>
> What is kept is everything *forward*-looking, because "everyone starts clean" expires the day we
> publish: the `settings_core` migration-ladder **machinery** (empty now, ready for the first
> post-publish schema bump), the strict-schema coverage test, the three-layer deltas-win merge,
> OTA `.bak/` rollback + Revert, atomic writes, backup/restore, and the `profile_schema` ladder.

---

## North star — the lens every phase is judged against

The one operation here that can hurt a user is the **OTA content swap** (Phase 4): automatic and,
done naively, hard to reverse. The plan is organised so it is **non-destructive and recoverable
first**, elegant second.

1. **Never lose user data going forward.** Profiles, custom buffs, window positions, and settings
   survive every OTA, restore, and crash — including unforeseen cases. (There is no upgrade path
   to survive — clean start.)
2. **Invisible when it works.** Updates are silent. The user hears from us only when something
   they'd care about changed, or when they must act.
3. **Automatic but never captive.** Anything automatic is reversible and has a visible off-switch.
4. **Fail safe and quiet.** Network down, manifest garbage, disk locked → the app runs on shipped
   stock and changes nothing.
5. **One signal per event, never modal.** A content update is a single dismissable toast.

These five are restated as testable acceptance criteria in the cross-cutting checklist and attach
to every phase.

---

## Decisions (locked)

| # | Decision | Choice |
|---|---|---|
| 1 | **Scope** | Full system, phased — settings engine + userdata reorg + OTA content + profile sharing |
| 2 | **Storage** | New `userdata/` folder, created fresh on first launch. No legacy migration (clean start) |
| 3 | **Publishing** | Push to `main` = live; `ota/manifest.json` auto-generated at build time and committed; payloads pinned to immutable commit SHAs |
| 4 | **Updates** | Auto-apply in the background (toggleable), then notify what changed (atomic, reversible) |

**Non-negotiables:**
- User's own custom buffs are stored as **deltas** in a separate file and survive every content
  update. Effective DB = (OTA content ?? shipped stock) merged with user deltas; **user deltas
  always win.**
- Profile exports are **self-contained**: any user-DB buffs a profile references travel with the
  export string.
- The buff **Database and Default profile update together** under one `content_version`, so a
  stock profile never references a buff the stock DB lacks.
- No automatic action destroys the only copy of user data in the session that creates the
  replacement. OTA keeps a `.bak/` rollback.

---

## Target architecture

**Three data classes by lifecycle (not by feature):**

| Class | Examples | Ships? | User edits? | OTA? | Backed up? |
|---|---|---|---|---|---|
| **Machine-local** | window geometry, game folder, resolution, `has_built_before`, `last_profile`, UI state (last filter, panel open/closed) | no | indirectly | no | optional |
| **User content** | profiles, deeps/live-tracker/damageinfo settings, custom buffs | no | yes | no | yes |
| **Reference content** | stock `Database.json` + `Default.json` | yes | no (read-only) | yes | re-ships |

**Storage layout:**
```
<install>/
  KazBars.exe
  assets/                         ← REFERENCE (read-only shipped stock; never written by the app)
    kazbars/Database.json         ← stock catalog (stays byte-identical to .default — invariant kept)
    kazbars/Database.json.default
    kazbars/Default.json          ← stock starter profile
  userdata/                       ← USER + MACHINE (created fresh on first launch)
    prefs.json                    ← machine-local: window positions, game path, resolution, last_profile, UI state, build toggles
    settings/{deeps,live_tracker,damageinfo}_settings.json
    profiles/*.json
    database_user.json            ← user buff DELTAS (+ tombstones)
    content/                      ← OTA-pulled reference content (client-local)
      Database.json  Default.json  manifest.json   ← local applied-version marker
      .bak/                       ← rollback snapshot (prev/ + incoming/)
```
The server-side update manifest lives in the **repo** at `ota/manifest.json` (not shipped, not in
`userdata/`). It is distinct from the client-local `userdata/content/manifest.json` above. See
Phase 4.

**The rule that makes it safe:** the editor and the OTA updater **never write to `assets/`**.
Stock stays pristine, so an app reinstall always has a clean floor and the `Database.json` ⇄
`Database.json.default` byte-identity test (`test_data_integrity.py`) gets *stronger*, not harder.

**Backup scope is an allowlist, not the whole root.** Backup/restore covers `profiles/`,
`settings/`, `database_user.json`, and `prefs.json`. It **excludes** `content/` (regenerable OTA
cache) and `content/.bak/` (rollback snapshots) — otherwise every backup balloons with the OTA
cache and could carry stale content to another machine. `prefs.json` **is written into the backup
zip** but is **machine-local → off by default on restore** (opt-in checkbox), so a cross-PC
restore doesn't drag a dead game path / window geometry along.

**Build reads the in-memory DB.** `build_action.build` → `compile_to_staging` → `build_grids`
passes `app.database` ([build_action.py:124](../../src/kazbars/build_action.py#L124)), not the DB
file on disk. So once `app.database.buffs` holds the merged effective DB, the build is
automatically correct — no build-pipeline changes are needed for the merge/OTA work.

**Only two writers to `assets/` exist** — `DatabaseEditorTab.save()`
([database_editor.py:702](../../src/kazbars/database_editor.py#L702)) and the corruption-recovery
copy in `app.__init__` ([app.py:100](../../src/kazbars/app.py#L100)). Everything else only reads
assets. Both writers are removed/redirected in Phase 3; there is no third writer to chase.

---

## Phase ordering

`1 → 2 → 3 → 4 → 5`. Each phase is independently shippable and leaves `pytest` green and the app
working. Phase 2 precedes 3/4 (OTA `content/` and `database_user.json` live under `userdata/`).
Phase 3 precedes 4 (OTA correctness depends on the three-layer merge + provenance). Phase 5 depends
on 2 (and on Phase 3's user-DB concept for self-contained export).

> There is no migration phase. Under clean start there is no legacy tree to relocate or archive, so
> forward data-safety is carried entirely by atomic writes (Phase 1), the backup/restore allowlist
> (Phase 2/3), and the OTA `.bak/` rollback (Phase 4).

---

## Phase 1 — Schema-driven settings engine (pure core)

**Goal:** One `settings_core` engine (Schema + Field + migration ladder + atomic
load/migrate/validate/fill/save) that `deeps_settings`, `live_tracker_settings`,
`damageinfo_settings` delegate to with **no behavior change**, shaped from the start to back
`prefs.json` safely in Phase 2.

**New module:** `src/kazbars/settings_core.py` (pure, no Tk). Public surface:
- `Field(default, *, validate=None, min=None, max=None, kind=None, choices=None, **ui_metadata)` —
  dataclass; `ui_metadata` carries the `unit`/`description`/`tooltip`/`step`/`type`/`options`/
  `invert`/`relative` keys `damageinfo` already uses, so panels keep reading them. `validate(value)
  -> value` overrides generic coercion for bespoke fields (`source_colors`, `visible_cells`, the
  window-positions dict).
- `Schema(filename, version, fields, migrations=[])`.
- `Migration` rungs — ordered, keyed off the stored integer `schema_version`. The ladder ships
  **empty** (clean start) but the machinery is live for the first post-publish schema bump.
- `Store(schema, folder)` — `load()` (read → run ladder → validate → fill), `save(data)` (validate
  → write `schema_version` → atomic via `settings_manager.safe_save_json`), `get`/`set`.
- `validate_all(schema, raw, *, mode='strict')` / `get_defaults(schema)`.

**The strict-validation contract (the core safety rule):** `validate_all` runs in `mode='strict'`
for all files — it drops keys the Schema doesn't declare (today's behavior in
`validate_all_settings`). This means **every persisted key must be a declared `Field`, or it is
erased on the next save.** Two consequences the implementation must honor:
- **Dynamic key namespaces are declared as one structured field.** `prefs.json`'s per-window
  positions are a single `window_positions` dict field, *not* N top-level `window_pos_*` keys (a
  fixed Schema can't enumerate them, so strict mode would erase them). See Phase 2.
- **The field list is derived from the code, not hand-typed.** Ship a Phase-1 acceptance test
  `test_prefs_schema_covers_all_proxy_keys` that greps every
  `get_setting`/`set_setting`/`settings.get`/`settings.set` key in the tree and asserts each is a
  declared `PREFS_SCHEMA` field. This is what prevents a silently-dropped setting.

**Retrofit the three typed files** (`deeps_settings.py`, `live_tracker_settings.py`,
`damageinfo_settings.py`): re-express `*_DEFAULTS`/`*_RANGES`/`validate_setting` as a `Schema`, with
each module keeping its existing public surface as thin wrappers so callers/tests don't change.
- Preserve the **actual** public names, verified per module via `__all__` + a grep of importers:
  `DEEPS_DEFAULTS`, `DEEPS_RANGES`, `GLOBAL_SETTINGS`, `GAME_DEFAULTS`, `PRESETS`,
  `SETTINGS_FILENAME`, `TIMERS_DEFAULTS`, `validate_all_settings`, `validate_setting`,
  `load_settings`, `save_settings`, `get_default_settings`, `get_settings_path`, the
  `FONT_FAMILY_CHOICES` re-export, and the deeps `normalize_*_preset` / `overlay_config_*` adapters.
  `damageinfo` has no `__all__`; importers reach it as `dis.<name>`. `DAMAGEINFO_DEFAULTS`
  ([damageinfo_settings.py:379](../../src/kazbars/damageinfo_settings.py#L379)) is internal-only —
  no other module imports it — so it needs no preserved wrapper.
- Leave domain logic untouched and out of the load path: `damageinfo`'s
  `compute_final_value`/`readout`/`apply_preset` and deeps' `normalize_readout_preset`/
  `normalize_survival_preset` are panel-invoked; the engine owns only persistence + validation.
- `live_tracker`'s `_migrate_legacy_keys` and its `timers_settings.json` → `live_tracker_settings.json`
  rename are **not ported** — they serve only pre-existing installs. The ladder starts empty.

**Free win:** the three files currently `json.dump` non-atomically. Routing every write through
`Store.save` → `safe_save_json` makes all settings writes atomic (temp + rename) at no extra cost.

**mypy:** add `settings_core.py` to `[tool.mypy] files`. Also add `damageinfo_settings.py` — it is
Tk-free but is currently missing from the blocking gate that already lists `deeps_settings` and
`live_tracker_settings`. It has never had to pass the blocking gate, so budget a fix pass for any
latent type errors in the same change.

**Cluster isolation:** `settings_core` becomes shared infra imported by the cluster settings
modules → add `"settings_core"` to `INFRASTRUCTURE` in `tests/test_cluster_isolation.py`
(`settings_manager` is already there; `settings_core` imports only it + stdlib).

**Tests:** `tests/test_settings_core.py` — Field validation, fill-missing/drop-unknown, ladder
ordering + idempotent fixpoint, atomic save leaves no `.tmp`, corrupt→defaults, structured-dict
round-trip. `tests/test_prefs_schema_covers_all_proxy_keys.py` (above). Existing
`test_deeps_settings`/`test_damageinfo_settings` are the regression gate — must pass unchanged.

**Smoke:** all three config panels still load, edit, and persist.

**Docs:** architecture.md inventory row + Conventions note (settings read/write routes through
`settings_core`; the strict/structured-field rule).

---

## Phase 2 — `userdata/` storage root (fresh, no migration)

**Goal:** All user data lives under one `userdata/` root, created fresh on first launch;
`assets/` becomes read-only. There is no migration — a fresh install (and every tester) starts at
defaults; old folders next to the exe are ignored (never read, moved, or deleted).

**New module:** `src/kazbars/userdata.py` (path resolution + layout; no Tk):
- `userdata_root()` = `app_path()/"userdata"`; named subpaths `prefs_path()`, `settings_dir()`,
  `profiles_dir()`, `database_user_path()`, `content_dir()`, `content_backup_dir()`.
- `ensure_layout()` — creates the tree and seeds an empty `database_user.json` and `content/` +
  `content/.bak/` if absent. Idempotent; this is the only startup data step (no archive, no
  migrate).

**Delete the three legacy one-shot migrations** (no beneficiary under clean start, and each is
otherwise a dead code path): `SettingsManager._migrate_legacy_filename`,
`game_folder.migrate_legacy_clients` + its call site at [app.py:126](../../src/kazbars/app.py#L126),
and `live_tracker_panel._migrate_window_position_key` + its call site at
[live_tracker_panel.py:99](../../src/kazbars/live_tracker_panel.py#L99).

**`PREFS_SCHEMA`** — prefs is backed by a `settings_core.Schema` like every other file. Per the
strict-validation contract, the field list below was reconciled against a full grep of proxy keys
and must be re-grepped at implementation time. Fields:
- `game_path`, `use_aoc_bypass`, `game_resolution`, `last_profile`, `default_profile`,
  `has_built_before`, `last_build_signature`, `build_console` (machine-local).
- `window_positions` — **one dict field** `{ "<window_name>": {x,y[,width,height]} }`, with a
  `validate=` that clamps/sanity-checks each entry. Replaces the dynamic `window_pos_*` keys.
- `buff_selector_category`, `buff_selector_type`, and the section-open map under the **actual**
  constant `SETTINGS_KEY_SECTION_OPEN = 'buff_display_section_open'`
  ([buff_display_editor.py:71](../../src/kazbars/buff_display_editor.py#L71)) — note the singular
  `section`. These UI-state keys are written via the global proxy
  ([grid_dialogs.py:381](../../src/kazbars/grid_dialogs.py#L381),
  [buff_display_editor.py:563](../../src/kazbars/buff_display_editor.py#L563)).
- `content_version` and the auto-update toggle land in Phase 4 (declare them as fields when added).
  `content_version` **defaults to the shipped `CONTENT_BASELINE_VERSION`, not `0`** (Phase 4), so a
  fresh install already knows it is current and the first-run OTA is a silent no-op unless the
  server has moved past the build.

**The `Prefs` facade** — `app.settings` is used as more than `get`/`set`: a direct `.data.pop(...)`
in `save_game_path` ([game_folder.py:127](../../src/kazbars/game_folder.py#L127)), a `.reload()`
([settings_backup.py:387](../../src/kazbars/settings_backup.py#L387)), and ~20 `.get/.set/.save()`
sites. Rather than touch every call site, wrap the prefs `Store` in a thin `Prefs` adapter exposing
the exact SettingsManager surface — no-arg `save()`, `reload()`, `get`, `set`, and a `data` mapping
view supporting `pop`. `init_settings(prefs)` keeps the module proxy working unchanged.
`SettingsManager` is retired; `safe_save_json` stays in `settings_manager.py` (the engine + profile
I/O use it), as do `init_settings`/`get_setting`/`set_setting`. (Tightening `.data.pop` into a real
`delete()` method is a later cleanup, not this phase.)

**`window_position.py`** — unchanged public API (`save_window_position`, `restore_window_position`,
`bind_window_position_save`); internally it reads/writes a sub-key of the `window_positions` dict
via the proxy instead of a top-level `window_pos_<name>` key. (The live-tracker window-pos migration
helper is deleted above; no rename rung is needed under clean start.)

**`settings_backup.py`** — source from / restore to `userdata/` using the allowlist (`profiles/`,
`settings/`, `database_user.json`; never `content/` or `content/.bak/`). `prefs.json` is written
into the backup zip but is **off by default on restore** via a dialog checkbox — a restore-side
gate, not an archive-side exclusion, so a same-PC restore keeps window positions + game folder.
Update the "what's included" copy. Keep pre-restore snapshots **outside** `userdata/` (as today, at
`app_path/KazBars_PreRestore_*.zip`) so restore can't recurse into them.

**`app.py __init__`** — call `ensure_layout()` before constructing `Prefs`; point
`profiles_path`/`settings_path` at `userdata.*`; build `self.settings = Prefs(...)`;
`init_settings(self.settings)`. The layout step is the whole startup-data story — no archive, no
migrate.

**Tests:** `tests/test_userdata.py` — `ensure_layout` creates the full tree + seeds an empty
`database_user.json` and `content/`+`.bak/`; idempotent second run is a no-op; every named subpath
resolves under `userdata/`. Update `test_settings_backup.py` (round-trip over the `userdata/`
allowlist; `content/`+`.bak/` excluded; `prefs.json` opt-in). Add `userdata.py` to mypy `files`.

**Smoke:** fresh install creates `userdata/` with defaults and fires first-launch; setting the
game folder + moving windows persists to `userdata/prefs.json`; an install that already has
pre-overhaul `profiles/`+`settings/` next to the exe starts clean (old folders left untouched and
unread); backup/restore round-trips and the backup zip does not contain `content/`.

**Docs:** architecture.md "Storage layout / data lifecycle" subsection + inventory rows
(`userdata.py`, `Prefs`); flows.md first-launch + backup flows; CLAUDE.md "When something breaks"
(stale `userdata/prefs.json` → delete to retrigger first-launch).

---

## Phase 3 — Three-layer buff DB merge with user deltas (+ provenance)

**Goal:** Effective DB = stock floor (assets) ← OTA override (`content/`) ← user deltas
(`database_user.json`), user always wins. Editor writes only `database_user.json`. Provenance is
tracked so the UI can tell the user *why* a buff behaves the way it does.

**New module:** `src/kazbars/buff_db_layers.py` (pure, no Tk):
- `load_effective(stock_path, content_path, user_delta_path) -> (buffs, provenance)` — merge up to
  three v2 files by buff identity (add / override / tombstone). `provenance` maps each effective
  buff to `stock | content | user` so the editor can badge it.
- `DeltaStore` — load/save `database_user.json` as `{version:2, buffs:[...], deleted:[...]}`,
  atomic via `safe_save_json`.
- `compute_delta(floor_buffs, edited_buffs) -> delta`.

**Identity key = `ids[0]`** (the AoC-canonical primary spell ID; `name` is display-only). Confirmed
against ref resolution: `_migrate_whitelist` normalizes every whitelist/slot ref — int ID or name
string — to `entry['ids'][0]` on load
([grids_panel.py:419](../../src/kazbars/grids_panel.py#L419)), and shipped `Default.json`
whitelists are primary IDs. Edge case for `compute_delta`/tombstones: the editor's
`update_buff`/`remove_buff` match on full-ID-**set** equality
([buff_database.py:111](../../src/kazbars/buff_database.py#L111)); keying the delta on `ids[0]`
diverges only if a user changes a buff's *primary* ID — define that as "treat as a new user buff +
tombstone the old," and test it.

**Modify:**
- `buff_database.py` — add `load_layers(stock, content, user)` (sets `self.buffs` to the merge,
  stores `self.provenance`, rebuilds indexes) and `reload()` (re-runs the merge; Phase 4 calls it
  after OTA). Keep `load(json_path)` for back-compat/tests.
- `app.py` — replace the single-file DB load + corruption-recovery copy with `load_layers(...)`;
  the recovery path stops **writing** assets (recovers `Database.json.default` into memory only).
- `database_editor.py` — `save()` stops writing `assets/kazbars/Database.json`; it computes deltas
  vs the stock+content floor and writes `database_user.json` via `DeltaStore`. The `assets_path`
  constructor arg becomes a delta-store path/callback. Deleting a stock/content buff = tombstone
  (reversible); deleting a user buff = drop the delta. **Provenance UI:** a small tag (Built-in /
  Updated / Yours) in the list, with delete copy that matches — *"Hide this built-in buff"*
  (tombstone) vs *"Delete your buff"* — so the three-layer model is legible.
- `build_action.build` — no change (passes `app.database`, now merged).
- `settings_backup.py` — add `database_user.json` to the backup/restore allowlist, so the
  data-class table's "custom buffs are backed up" is actually true.

There is **no seed migration** — under clean start no one has pre-overhaul custom buffs to recover,
so there is no diff-seed from an edited `assets/Database.json`, no guard flag, and no notice.

**Tests:** `tests/test_buff_db_layers.py` (precedence, add/override/tombstone, provenance mapping,
missing-layer fallbacks, `DeltaStore` round-trip, `compute_delta`, primary-ID-change edge).
Preserve `test_data_integrity.py` (still points at the assets stock pair + `Default.json` whitelist
resolution). Update `test_settings_backup.py` for the new allowlist member. Add `buff_db_layers.py`
to mypy `files`.

**Smoke:** add a custom buff → persists to `database_user.json` (not assets), shows the "Yours"
badge; survives a simulated content update; build uses it; survives a dist delete + relaunch; a
backup zip contains `database_user.json`; hiding a built-in buff tombstones it and un-hiding
restores it.

**Docs:** architecture.md buff-database cluster (three-layer merge + provenance) + inventory row;
flows.md save-database + add-buff + hide-built-in flows; database-changelog.md (stock/delta split);
CLAUDE.md invariant bullet.

---

## Phase 4 — OTA reference content (silent, reversible, never captive, never mid-edit)

**Goal:** On launch, poll the manifest; if a newer `content_version` exists, `app_version ≥
min_app_version`, and the user hasn't turned auto-update off, download Database.json + Default.json
(pinned SHAs), verify sha256, atomically swap into `userdata/content/` with `.bak/` rollback,
re-merge the DB live, then notify with **one** toast. Failure swaps nothing. Never applies while the
DB editor has unsaved edits, a build is running, or first launch is in progress — defers to next
launch.

### Three version markers — keep them distinct
- **`ota/manifest.json` (repo, server side)** — the published pointer. Its `content_version` is the
  latest available.
- **`prefs.json.content_version` (client)** — the **authoritative comparison key**: `is_newer`
  compares the manifest's `content_version` against this. Defaults to `CONTENT_BASELINE_VERSION`.
- **`userdata/content/manifest.json` (client)** — the on-disk record of what's currently in
  `content/` (payload provenance + step-5 commit marker), *not* the comparison source.

### Shipped baseline — no redundant first-run update
The build bakes its content version into the app as **`CONTENT_BASELINE_VERSION`** (a constant next
to `__version__` in `src/kazbars/__init__.py`, written by `gen_manifest` at build time).
`PREFS_SCHEMA.content_version` defaults to that baseline, so a fresh install already knows it ships
current: on first launch `is_newer(manifest, baseline)` is false unless the server has genuinely
moved past the build, and the OTA is a silent no-op (no download, no toast). Without this a virgin
user re-downloads content they shipped with and sees a confusing "buff database updated" toast
seconds after install.

### New module
`src/kazbars/content_update.py` — pure core + a thin Tk dispatcher, mirroring `update_check.py`'s
background-thread + named main-thread-dispatcher shape (reuse `update_check._parts` for
`min_app_version`). Because it imports `tkinter` for the toast dispatcher, it is **not** on the
blocking mypy gate (`update_check` is likewise absent); keep it advisory-only, or split a pure no-Tk
core and gate only that. Public surface:
- `check_and_apply(app, app_version, current_content_version)` — fire-and-forget; bails early if the
  toggle is off.
- Pure helpers: `parse_manifest`, `is_newer`, `verify_sha256`, `apply_content`, `rollback`,
  `summarize_changes`.

### User-facing controls (the "never captive" part)
- Settings toggle **"Automatically update the buff database (recommended)"** — a `prefs.json` field,
  default on.
- Menu action **"Check for updates now"** — manual trigger; reports "already up to date".
- Menu action **"Revert last buff-database update"** — calls `rollback()`.
- The applied `content_version` is persisted to `prefs.json` (the authoritative comparison key).

### manifest.json schema
```jsonc
{
  "schema": 1,                         // manifest format version (≠ content_version)
  "content_version": 7,                // monotonic int; client compares > prefs.json.content_version
  "min_app_version": "2.1.0",          // client skips if app_version < this (reuse update_check._parts)
  "source_commit": "a1b2c3d…",         // provenance
  "notes": "Added 3 raid debuffs; fixed Zaal Veil ID.",
  "files": {
    "Database.json": { "url": "https://raw.githubusercontent.com/kazour/Kazbars/<PINNED_SHA>/src/kazbars/assets/kazbars/Database.json", "sha256": "…" },
    "Default.json":  { "url": "https://raw.githubusercontent.com/kazour/Kazbars/<PINNED_SHA>/src/kazbars/assets/kazbars/Default.json",  "sha256": "…" }
  }
}
```
The manifest is committed at the repo root as **`ota/manifest.json`** and polled at the stable raw
URL `https://raw.githubusercontent.com/kazour/Kazbars/main/ota/manifest.json` — it lives on `main`,
not under the runtime `userdata/content/`. Every payload URL is pinned to an immutable commit SHA so
a payload can't shift under a published manifest. `min_app_version` enforces the DB+Default
move-together guarantee at the app-compat boundary. (Repo `kazour/Kazbars` is public — matches the
existing `update_check` endpoints.)

### The compat gate is a feature, not a silent skip
When `min_app_version` is newer than the running app, surface **once** *"New buffs are available —
update KazBars to get them,"* routed through the existing `update_check` notifier idiom — otherwise
users silently never get content and can't tell why.

### Build-time manifest generation
New repo-tooling script `scripts/gen_manifest.py` (not shipped; create the `scripts/` dir). It:
reads the two stock files; computes sha256; resolves the commit SHA (`git rev-parse HEAD`); bumps
`content_version` (previous + 1); fills `min_app_version` from `__version__`; writes the committed
`ota/manifest.json` (repo root); and **stamps the same `content_version` into the app as
`CONTENT_BASELINE_VERSION`** via a surgical edit of `src/kazbars/__init__.py` next to `__version__`
(hatchling reads `__version__` from there — leave that line intact). Run it via a GitHub Action on
push-to-`main` that touches the stock files (regenerates + commits the manifest and the stamped
constant in the same push, pinning payload URLs to that commit). This is a new workflow alongside
`ci.yml` + `release.yml`.

Drift guard — `tests/test_manifest.py` asserts:
1. the committed manifest's sha256 matches the committed stock files (like `test_data_integrity`); and
2. **`CONTENT_BASELINE_VERSION` == `ota/manifest.json`'s `content_version`** — the two are stamped
   together, so a drift would make a fresh install either re-download content it shipped with
   (baseline < manifest) or silently miss updates (baseline > manifest), defeating the
   silent-first-run guarantee.

### Apply / rollback / failure handling
Atomic apply in `userdata/content/`:
1. Download both payloads to `content/.bak/incoming/`. Any download fail → abort, swap nothing.
2. Verify sha256 against the manifest. Mismatch → abort, delete temp, swap nothing.
3. Snapshot current `content/` (Database.json + Default.json + manifest.json) into
   `content/.bak/prev/` (first-ever update: record empty / snapshot the assets floor).
4. `os.replace` each verified file into `content/` (atomic per file; both small).
5. **Write `content/manifest.json` LAST** as the commit marker — the applied version only advances
   once both payloads are in place. A crash between 4 and 5 → next launch re-applies (sha256
   matches, cheap) — never a half-applied state.
6. **Apply guard:** if `app.db_panel.modified` (DatabaseEditorTab.modified) or `app._building`
   ([app.py:113](../../src/kazbars/app.py#L113)), skip the live swap and leave it for next launch —
   don't yank the DB out from under an editing user. The first-launch case has no existing flag:
   **gate the whole `check_and_apply(...)` call on first launch being complete** (see Modify below)
   rather than testing a flag mid-swap.
7. `BuffDatabase.reload()` re-merges; `db_panel.refresh_list()`; Grids re-resolve. No restart.
8. **One** toast: *"Buff database updated — N added, M changed"* (`summarize_changes` diffs old vs
   new), click-through to a short what-changed list; offers Revert. No modal, no per-buff noise.

`rollback()` restores from `.bak/prev/` on demand (the menu action) and on a post-swap `reload()`
exception (auto-rollback + notify failure). User deltas are never touched by apply or rollback.

**Modify:** `app.py __init__` — after the layered DB load, call `content_update.check_and_apply(...)`
(which respects the toggle + guards). **On a fresh install, defer that call until first launch
completes** (invoke it from the first-launch completion path, not inline in `__init__`) so the OTA
never races the welcome dialog. With the shipped baseline, a fresh install won't fire an OTA at all
unless the server moved past the build, so this only matters for the rare
first-launch-coincides-with-a-server-bump case. `update_check.py` stays as-is; `content_update.py`
is its sibling (copy the idiom, don't cross-import).

**Tests:** `tests/test_content_update.py` (manifest parse/reject, `is_newer` + `min_app_version`
gate, toggle-off short-circuit, edit/build apply-guard defers, `verify_sha256`, `apply_content`
happy + each failure point, mid-swap interruption self-heals, `rollback`, deltas untouched,
`summarize_changes`). `tests/test_manifest.py` (both drift assertions above). No network in tests —
inject a fake downloader.

**Smoke:** fake manifest + payloads (local URLs / temp HTTP) → auto-apply → single toast → DB tab
shows new entries → build works → Revert restores the prior set → kill mid-apply → relaunch
self-heals → toggle off suppresses updates → "Check now" works manually → fresh install with
baseline == server fires no OTA.

**Docs:** architecture.md "Reference content / OTA" cluster + inventory row + manifest schema;
flows.md content-auto-update + revert + check-now flows; database-changelog.md (OTA channel +
manifest/baseline bump on maintainer edits); CLAUDE.md ("push to main = live, manifest +
`CONTENT_BASELINE_VERSION` auto-generated, payloads pinned to SHA", the toggle, the apply-guard, the
rollback guarantee).

---

## Phase 5 — Profile Manager UI + self-contained export/import strings

**Goal:** A Profile Manager dialog (list / rename / duplicate / delete / set-default) replacing raw
OS file pickers, plus portable `KZBARS1:<gzip+base64>` export/import strings that embed any user-DB
buffs the profile references — with a calm, one-confirmation import.

**New modules:**
- `src/kazbars/profile_share.py` (pure codec): `encode_profile(profile, embedded_buffs)`,
  `decode_profile(string) -> (profile, embedded_buffs)`, `collect_referenced_user_buffs(profile,
  effective_db, provenance)` — walks whitelist + slotAssignments and keeps only buffs whose
  provenance is `user`. Run it on the post-load in-memory profile whose refs are already normalized
  to `ids[0]` (via `_migrate_whitelist`), so a name-referenced custom buff is never missed and the
  export stays truly self-contained.
- `src/kazbars/profile_manager.py` (Tk dialog): `open_profile_manager(app)` — lists
  `userdata/profiles/*.json` with rename/duplicate/delete/set-default + Export (to clipboard) /
  Import.

**Import UX (one confirmation):** paste → *"This profile includes N custom buffs — import?"* →
write profile + merge embedded buffs into `database_user.json` (skip-on-collision) → **one** toast:
*"Imported '<name>'. 2 buffs added, 1 already existed."*

**Profile schema versioning:** the profile `version` field is the app semver stamped at save time
([profile_io.py:174](../../src/kazbars/profile_io.py#L174); shipped `Default.json` has `"version":
"2.0.0"`) and cannot drive a numeric ladder. Add a separate integer **`profile_schema`** field and a
profile migration ladder keyed off it; keep stamping app `version` for display/debugging. Normalize
refs to `ids[0]` on read via `_migrate_whitelist` so collect/embed is reliable.

**Default-profile refresh (both points):** `first_launch.py` "Use Defaults" **and** the File-menu
**"Load Default Profile"** ([profile_io.py:57](../../src/kazbars/profile_io.py#L57)) both prefer
`content_dir()/Default.json` (OTA) when present, else stock.

**Launch precedence:** `default_profile` is the first-launch / "reset to" anchor; `last_profile` is
what reopens on relaunch (today's behavior at [app.py:148](../../src/kazbars/app.py#L148)). Relaunch
loads `last_profile`; `default_profile` is used only by first-launch and explicit "load default".
Set-default does not change which profile reopens.

**Modify:** `app.py` File menu — add "Manage Profiles…" + delegator. `profile_io.py` — reuse
read/apply/save; wire the `profile_schema` ladder; "set default" writes `default_profile` to
`prefs.json`. `first_launch.py` — OTA-aware default as above.

**Tests:** `tests/test_profile_share.py` (encode/decode round-trip, corrupt/truncated rejection,
`collect_referenced_user_buffs` picks exactly user-provenance refs across both ref forms,
self-contained round-trip on an empty DB, import merge without clobber); `tests/test_profile_io.py`
for the `profile_schema` ladder. Tk dialogs are smoke-only. Add `profile_share.py` to mypy `files`.

**Smoke:** profile using a custom buff → export → import into a fresh `userdata/` → grids resolve +
custom buff appears with one confirmation + one toast; rename/duplicate/delete/set-default work;
set-default does not change relaunch; "Load Default Profile" pulls the OTA Default when present.

**Docs:** architecture.md `profile_share`/`profile_manager` rows + satellites cluster; flows.md
manage/export/import + load-default flows; CLAUDE.md (`KZBARS1:` format, `profile_schema` ladder,
self-contained guarantee, launch precedence).

---

## Cross-cutting checklist (every phase)

- **UX acceptance criteria (testable, attached to every phase):**
  1. *No user-visible data loss going forward* — user deltas survive every OTA; atomic writes
     everywhere; the layered smoke tests pass.
  2. *Fully usable with the network blocked* — OTA failure changes nothing; the app runs on shipped
     stock.
  3. *Every automatic action is reversible or non-destructive* — OTA has `.bak/` + a Revert action.
  4. *At most one notification per background event; none modal.*
  5. *No background swap during an edit, a build, or first launch.*
- **Cluster isolation** (`tests/test_cluster_isolation.py`): add a new shared module to
  `INFRASTRUCTURE` only if a Deeps/Live-Tracker cluster member imports it. Required for
  `settings_core` (Phase 1). `userdata`/`buff_db_layers`/`content_update`/`profile_share` are not
  imported by cluster members — verify before each lands.
- **mypy gate:** add each new **Tk-free** module to `[tool.mypy] files` — `settings_core`,
  `userdata`, `buff_db_layers`, `profile_share` — plus the long-missing `damageinfo_settings`
  (budget a fix pass for latent errors). **`content_update` is excluded** (imports `tkinter`, like
  `update_check`) → advisory-only, or gate only a split pure-core submodule. `profile_manager` is Tk
  → not gated.
- **Style:** single-quote strings, 4-space indent, no `ruff format`, relative imports inside
  `src/kazbars/` (absolute only from `app.py`). Run `pytest` after every code edit; UI changes need
  `/smoke`.
- **Invariants:** AS2 `KazBars*` names untouched (Python-only work); `Database.json` ⇄ `.default`
  byte-identity preserved (and strengthened — the app no longer writes assets); `Default.json`
  whitelist resolves.

---

## Resolved questions (Q1–Q6)

The six framing questions, settled. Distinct from the locked **Decisions** table (1–4) above; every
in-text "Q*n*" points here.

- **Q1 — Buff identity key.** The buff's primary game ID (`ids[0]`). IDs are AoC-canonical and never
  change; `name` is display-only. Used for merge override-matching and tombstones. Whitelist refs
  normalize to `entry['ids'][0]` on load (both int-ID and name-string forms; Phase 5 collect handles
  both).
- **Q2 — Manifest hosting.** `ota/manifest.json` committed at the repo root on `main`, polled at the
  raw URL `…/kazour/Kazbars/main/ota/manifest.json` — a distinct path from the client's runtime
  `userdata/content/` (Phase 4). Payload URLs pinned to immutable commit SHAs.
- **Q3 — Stock floor.** Always three layers. Shipped stock stays the floor under the OTA override and
  user deltas; clearing `content/` cleanly recovers the shipped list. OTA never fully shadows assets.
- **Q4 — `Default.json` refresh.** Only on first-launch and explicit "Load Default Profile" — both
  wired to prefer OTA content (Phase 5). Saved user profiles are never silently mutated.
- **Q5 — Legacy folders.** Superseded by clean start: there is no migration. The app never reads,
  moves, archives, or deletes any pre-existing `settings/`/`profiles/`; it starts fresh under
  `userdata/`. Old folders sit on disk, inert and ignored.
- **Q6 — `prefs.json` schema.** Uses the `settings_core` Schema like every other file, with the
  dynamic `window_pos_*` namespace declared as one `window_positions` dict field — a fixed Schema
  can't enumerate per-window keys, so under strict drop-unknown they'd be erased once positions
  accumulate. UI-state keys (`buff_selector_*`, `buff_display_section_open`) are likewise declared
  fields.
