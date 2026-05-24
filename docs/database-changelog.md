# Buff Database — Change Log

Every change to the buff database (`src/kazbars/assets/kazbars/Database.json`) — buffs
**added, renamed, reclassified, or with corrected spell IDs**. Newest first.

**Why this exists:** the database grows continuously and raw `Database.json` diffs are
noisy JSON. A human-readable record of *which buff changed, its spell ID, and why* is far
easier to scan than `git log`, and gives every grid/profile that references a buff a paper
trail when an ID or name moves.

## How to maintain it

Whenever `Database.json` changes — however it was made (the in-app Database editor, a hand
edit, or a Claude session) — add a bullet under a `## YYYY-MM-DD` heading at the top
(reuse today's heading if it already exists):

- **Added:** `Buff Name` — `<spell id>`, #Category type.
- **Renamed:** `Old Name` → `New Name` (`<spell id>`).
- **Reclassified:** `Buff Name` — debuff → misc (etc.).
- **Fixed:** `Buff Name` spell ID `<old>` → `<new>` (and any profile whitelist that referenced the old ID).

Always include the **spell ID** — it's the canonical identifier grids and profiles bind to.
And keep `Database.json` **and** `Database.json.default` in sync (`test_data_integrity.py`
enforces byte-parity); if you change an existing buff's **ID**, also update any profile that
whitelists the old one (e.g. `assets/kazbars/Default.json`). See CLAUDE.md → "Common Tasks →
Add/change a buff in the database".

---

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

## 2026-04-18 — v1.0.0
- **Initial database** — the launch buff/debuff catalog (`Ethereal Lash`, `Human Prey`, `Impel`, and the rest).

---

*Entries above predate this log and were reconstructed from `git log` on `Database.json`;
spell IDs reflect the current database. The database currently holds **360 buffs**. Going
forward, log changes here as they happen.*
