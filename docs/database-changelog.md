# Buff Database — Change Log

Every change to the buff database (`src/kazbars/assets/kazbars/Database.json`) — buffs
**added, renamed, reclassified, or with corrected spell IDs**. Newest first.

**Why this exists:** the database grows continuously and raw `Database.json` diffs are
noisy JSON. A human-readable record of *which buff changed, its spell ID, and why* is far
easier to scan than `git log`, and gives every grid/profile that references a buff a paper
trail when an ID or name moves.

## How to maintain it

**Scope:** this log tracks the **shipped stock catalog** at `src/kazbars/assets/kazbars/Database.json`
only. As of the three-layer split, the **in-app Database editor no longer writes assets** — user
adds/edits/hidden-buffs are per-machine deltas in `userdata/database_user.json` (merged over stock at
load; see `architecture.md` → "Buff database"). So entries here come from maintainer changes to the
repo's stock file (a maintainer edit); per-user deltas are not logged.

**OTA channel:** a stock-file change requires regenerating `ota/manifest.json` **locally** in the same
commit (`python scripts/gen_manifest.py "notes"`) — the pre-commit pytest gate won't let it land
otherwise. That refreshes the sha256, the `main`-ref payload URLs, and the bumped `content_version`, and
stamps the matching `CONTENT_BASELINE_VERSION`; once on `main`, existing installs pull the update on next
launch (silent, reversible — see `architecture.md` → "Reference content / OTA"). The
`.github/workflows/ota-manifest.yml` Action only **verifies** it (regenerate + fail on drift; never commits
back). Don't hand-edit the manifest; regenerate and log the stock change here.

Whenever the stock `Database.json` changes, add a bullet under a `## YYYY-MM-DD` heading at the top
(reuse today's heading if it already exists):

- **Added:** `Buff Name` — `<spell id>`, #Category type.
- **Renamed:** `Old Name` → `New Name` (`<spell id>`).
- **Reclassified:** `Buff Name` — debuff → misc (etc.).
- **Fixed:** `Buff Name` spell ID `<old>` → `<new>` (and any profile whitelist that referenced the old ID).

Always include the **spell ID** — it's the canonical identifier grids and profiles bind to.
And keep `Database.json` **and** `Database.json.default` in sync (`test_data_integrity.py`
enforces byte-parity); if you change an existing buff's **ID**, also update any profile that
whitelists the old one (e.g. `assets/kazbars/Default.json`).

---

## 2026-06-15
- **Fixed:** `Veil of the Unliving (Zaal)` (#Raid T3.5 debuff) spell ID `4752520` → `5064067`; updated the matching `Default.json` whitelist + resynced the bundled `.default`.
- **Added:** `Spellweaving 1-6` stacking buffs (6 stack ranks each, type `buff`) for the four caster classes — each routed to its class category so the stack counter shows ranks 1–6:
  - `Priest of Mitra` — `3761196`, `3761198`, `3761224`, `3761231`, `3761232`, `3761233`.
  - `Necromancer` — `3663272`, `3663273`, `3663274`, `3663275`, `3663276`, `3663277`.
  - `Tempest of Set` — `3761193`, `3761197`, `3761199`, `3761200`, `3761201`, `3761202`.
  - `Demonologist` — `3663649`, `3663648`, `3663647`, `3663646`, `3663645`, `3663643`.
- **Renamed:** spelled out the `SW ` (Spellweaving) abbreviation in 9 buff names — display only, IDs unchanged:
  - `SW Arcane Renewal` → `Spellweaving Arcane Renewal` (`3762921`), `SW Arcane Surge` → `Spellweaving Arcane Surge` (`3762648`).
  - `SW Parasite Host` → `Spellweaving Parasite Host` (`3663577`), `SW Death God` → `Spellweaving Death God` (`3762722`).
  - `SW Benevolence of Mitra` → `Spellweaving Benevolence of Mitra` (`3763853`), `SW Mitra's Thunder` → `Spellweaving Mitra's Thunder` (`3763855`), `SW Mitra's Grace` → `Spellweaving Mitra's Grace` (`3763852`).
  - `SW Set's Rebuke` → `Spellweaving Set's Rebuke` (`3764133`), `SW Power Surge` → `Spellweaving Power Surge` (`3764495`).

## 2026-06-14
**Category reorganization** for the first public release — display grouping only. No buff IDs, names, or types changed, so no grid/profile whitelist is affected (`Default.json` untouched).
- **New category `#Protections`** — 15 group damage-mitigation buffs reclassified out of `#Group Buffs`: `Fierce Aegis (Poison)` `5017458`, `Rune of Resilience (BS)` `146124`, `Rune of Resistance (BS)` `146103`, `Mystic Suppression (Demo)` `145782`, `Arcane Abatement (HoX)` `145790`, `Quell the Ether (Necro)` `145626`, `Holy Cleansing (PoM)` `3202863`, `Radiant Aegis (Unholy)` `5017456`, `Damnation of Set (ToS)` `146099`, `Glorification of Set (ToS)` `146122`, `Litany of Protection (PoM)` `4922964`, `Spirit of Yggdrasil (BS)` `4239993`, `Emissary of Elysium (PoM)` `4244612`, `Eyes of Set (ToS)` `4471707`, `Vitalizing Aegis (Fire)` `5017457`.
- **Renamed category:** `#Resistances` → `#Immunities` (21 buffs) — contents are CC-immunity / diminishing-returns flags, not gear resistances.
- **Renamed category:** `#Global` → `#General` (20 buffs).
- **Renamed category:** `#Group HoT` → `#Group Heals` (9 buffs).
- **Renamed category:** `#T3` → `#Raid T3` (8), `#T3.5` → `#Raid T3.5` (13), `#T4` → `#Raid T4` (25), `#T5` → `#Raid T5` (17), `#T6` → `#Raid T6` (20) — the five raid tiers now cluster under `#Raid`.

## 2026-06-07
- **Added:** `Spiritual Wrack` (#Global debuff) alias spell ID `4887864` (entry IDs now `3963068`, `4882958`, `4887864`).

## 2026-05-25
- **Fixed:** `Affliction (Ethram)` (#T6 debuff) spell ID `5054120` → `5054121`; updated the matching `Default.json` whitelist + resynced the bundled fallback.

## 2026-05-24
- **Added:** `Focus of the Masochis (Honorguard)` — `5014793`, #T5 debuff.

## 2026-05-23
- **Added:** `Ice Cloak E (Slow)` — `5077888`, #Crowd Control misc. Part of the custom-icon pass for icon-less buffs (baked `IcoSlow*` symbols + the shared `IcoNull` fallback).

## 2026-05-22
- **Added:** `Ice Strike E (Slow)` — `5077873`, #Crowd Control misc.

## 2026-05-08
- **Added:** `Irritating (Strom)` — `4857492`, #T4 debuff.
- **Added:** `Vivifier Wrack (Entity)` — `4924714`, #T4 debuff.
- **Added:** `Poison Blades (Fizzle)` — `3727070`, #Crowd Control misc.
- **Reclassified:** one debuff → misc.

## 2026-05-04
- **Added:** `Tactic: Provoke (Strom)` `4857489`, `Tactic: Defense (Strom)` `4857488`, `Tactic: Frenzy (Strom)` `4857490` — all #T4 buffs.
- **Added:** `Hopeless Reality Ruin (Shadur)` — `4857485`, #T4 debuff.
- **Renamed:** `Predatory Torment (T4 adds)` → `Predatory Torment (Mithrelle)` (`4857503`); reclassified debuff → buff.

## 2026-05-02
- **Renamed:** `Hands of Corruption` → `Hands of Corruption (Entity)` (`4924718`); reclassified debuff → misc.
- **Renamed:** `Shackles (Basilisk)` → `Shackles (Shadur)` (`4857484`).
- **Added:** `Watchful Eye of Yun (LuZhi)` — `4857536`, #T4.

## 2026-04-27
- **Renamed:** `Concentrated Lotus Miasma (Levi-Ethram)` → `Concentrated Lotus Miasma (Zelandra)` (`5052368`); reclassified debuff → misc.

## 2026-04-24
- **Added:** `Zaal's Wrack (Zaal)` — `4836737`, #T3.5 debuff. Aligned `Veil of the Unliving (Zaal)` ID across profile + database.

## 2026-04-22 — v1.1.0
- **Added:** `Sickness (Zodiac)`, `Withering (Zodiac)`, `Mortal Affliction (Emperor)`, `Targetted Strikes (Sheng)`, `Acid Bite (Basilisk)` (#T4 debuffs); `Aflame Cleanse (Sheng)` (#T4 misc); `Wail of Chaos (Cetriss)` (#T6 misc).
- **Renamed** (added boss-source suffixes): `Acid Decay` → `(Basilisk)`, `Aflame` → `(Sheng)`, `Broken Armor Ruin` → `(T4 adds)`, `Crushed Armor Wrack` → `(T4 adds)`, `Open Wound Wrack` → `(T4 adds)`, `Petrify` → `(Basilisk)`, `Predatory Torment` → `(T4 adds)`, `Shackles` → `(Basilisk)`, `Tainted Blood` → `(Basilisk)`, `Pollen Cloud` → `(Imp)`.

## 2026-04-18 — v1.0.0 (first KazBars-repo release)
- **Database carried over from Kaz Grids v3.x** — the KazBars repo started fresh here with the existing catalog (`Ethereal Lash`, `Human Prey`, `Impel`, and the rest). Earlier per-change history is in the *Pre-KazBars era* below.

---

## Pre-KazBars era — Kaz Flash Modz / Kaz Grids v3.x

*Earlier history of the same database, reconstructed from the predecessor repo
(`KzBuilder-public` → `assets/kzgrids/Database.json`, author `kazour`). These edits predate
this repo's v1.0.0; the catalog carried over into KazBars on the rebrand. The v3.x schema
differed (name-based storage, `#BossTx` categories), so these are version-level summaries.*

### 2026-03-22 — v3.6.x (buff dialog & sort fixes) · 328 buffs
- **Category overhaul:** introduced `#Resistances`, `#Group Buffs`, `#Crowd Control`; dropped class-name categories (`Guardian`, `Herald of Xotli`, `-Tank General`, …). Reclassifications (debuff → buff/misc) + renames (`Incinerate 1-5` → `Incinerate T3 1-5`, `Fatality (Group)` → `Fatality`, `Forced Engage (res)` → `Forced Engage`). (+13)

### 2026-03-16 — v3.6.0 (Timers v3 & UI Overhaul) · 315 buffs
- Added `(Group)` suffixes (`Battle Cry`, `Call to Arms`, `Exploit`, `Holy Cleansing`, `Wave of Life`, …); `Vengeance (debuff)/(buff)` → `Vengeance 1-3` / `Vengeance 1-10`; `Guard V` → `Guard`; removed `Master at Arms`. (+22)

### 2026-03-10 — v3.5.2 (Castbar Estimation & Database Improvements) · 293 buffs
- Category cleanup: `#BossT3/T3.5/T4/T5` → `#T3/T3.5/T4/T5` (dropped the "Boss" prefix). **+74 buffs.**

### 2026-03-06 — v3.5.0 (Grid Templates & Name-Based Buff Storage) · 219 buffs
- Disambiguated duplicate names for name-based storage: `Forced Engage` / `Vengeance` / `Marked Target` → `(debuff)` / `(buff)`; `Stunned` → `(Bear Shaman)` / `(Guardian)` / `(HoX)`.

### 2026-02-27 — Kaz Flash Modz v3.3.4 (first tracked database) · 219 buffs
- Initial database in the predecessor repo.

---

*Entries are reconstructed from `git log` on `Database.json` (this repo) and the predecessor
`KzBuilder-public` repo; spell IDs reflect the current database, which holds **360 buffs**.
Going forward, log changes here as they happen.*
