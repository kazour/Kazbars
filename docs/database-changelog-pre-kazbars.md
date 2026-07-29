# Buff database — pre-KazBars history

Moved out of [`database-changelog.md`](database-changelog.md) on 2026-07-30. Closed record; nothing here changes again.

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

