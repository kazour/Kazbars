# Buff Database — Change Log

Every change to the buff database (`src/kazbars/assets/kazbars/Database.json`) — buffs
**added, renamed, reclassified, or with corrected spell IDs**. Newest first.

## How to maintain it

**Scope:** the **shipped stock catalog** at `src/kazbars/assets/kazbars/Database.json` only.
Per-user deltas in `userdata/database_user.json` are per-machine and not logged
(`architecture.md` → "Buff database"). A stock change also needs its OTA manifest
regenerated in the same commit — `architecture.md` → "Reference content / OTA".

Add a bullet under a `## YYYY-MM-DD` heading at the top (reuse today's if it exists):

- **Added:** `Buff Name` — `<spell id>`, #Category type.
- **Renamed:** `Old Name` → `New Name` (`<spell id>`).
- **Reclassified:** `Buff Name` — debuff → misc (etc.).
- **Fixed:** `Buff Name` spell ID `<old>` → `<new>` (and any profile whitelist that referenced the old ID).

Always include the **spell ID** — it's the canonical identifier grids and profiles bind to.

**When this file passes ~20 KB,** move the oldest whole `## YYYY-MM-DD` sections into
`docs/database-changelog-<YYYY>.md` until it's back under ~14 KB, and add a row for the
new file in `docs/README.md`. Look an ID up across all of them with
`grep -n "<id>" docs/database-changelog*.md`; new entries always go in this file.

---

## 2026-08-09
**Wrack and torment lines — four more boss debuffs.** Continues the previous day's pass, same
sourcing: confirmed against observed in-game application data and cross-checked with the boss
rosters. No existing entry changed, so no profile whitelist is affected (`Default.json`
untouched).
- **Added:** `Kian Lai's Wrack 1-5 (Kian Lai)` — #General debuff, stacking (5 ranks): `4043129`, `4043131`, `4043132`, `4043133`, `4043134`. The boss's stacking armor debuff, and the wrack counterpart to `Kian Lai's Ruin (Kian Lai)`; the game data stores it under the bare name `Kian Lai`. Also applied by the encounter's second boss.
- **Added:** `Bhangi Khan Wrack 1-5` — #General debuff, stacking (5 ranks): `4549463`, `4549505`, `4549506`, `4549507`, `4549508`. Completes that boss's tracked set alongside his two ruins and his torment.
- **Added:** `Mind Wrack (Necropolis)` — `4239687`, `4502967`, #General debuff. A lightning-resistance debuff applied by an add in that instance. Distinct from `Mind Wrack (Stun)`, which is a player ability.
- **Added:** `Ghostly Torment (Necropolis)` — `4239695`, #General debuff. Applied by an add in that instance; a delayed debuff that deals area damage when it expires.

## 2026-08-08
**Wrack and torment lines — sixteen boss debuffs.** The wrack and torment counterparts to the
ruin line, confirmed against observed in-game application data and cross-checked with the boss
rosters. Several encounters that previously had only their ruin tracked now carry the full
dispel set. No existing entry changed, so no profile whitelist is affected (`Default.json`
untouched).
- **Added:** `Corrupted Claws Wrack 1-4 (Bone Golems)` — #General debuff, stacking (4 ranks): `4704444`, `4704445`, `4704446`, `4704447`. Named for the applying add; the parent encounter is not identified.
- **Added:** `Scorching Wrack 1-4 (Abyssal Convoker)` — #General debuff, stacking (4 ranks): `4935086`, `4935087`, `4935088`, `4935089`.
- **Added:** `Malicious Wrack 1-5 (Jing-Zhi)` — #General debuff, stacking (5 ranks): `4515806`, `4515807`, `4515818`, `4515819`, `4515820`. The wrack half of the pair whose ruin is `Malicious Ruin (Cavern of Malice)`.
- **Added:** `Lighter than Air Wrack (Air and Water)` — `4550619`, #General debuff.
- **Added:** `Poison Pincer Wrack (Sodabeh)` — `4838217`, #General debuff. Applied by the boss's two offspring adds.
- **Added:** `Scorching Torment (Devourer)` — `4935118`, #General debuff.
- **Added:** `Enslaving Torment (Kun Whu)` — `4049150`, #General debuff. A charm effect, dispel-classed as a torment.
- **Added:** `Slaughterer's Torment (Tetharos)` — `4490631`, #General debuff.
- **Added:** `Drowned God's Wrack (Thrice Drowned)` — `4991713`, #General debuff. A second spell ID exists for the arena variant of this encounter and is deliberately not tracked pending verification.
- **Added:** `Advisor's Wrack (Argo-satha)` — `4732523`, #General debuff.
- **Added:** `Advisor's Torment (Argo-satha)` — `4732526`, #General debuff. With `Advisor's Ruin (Argo-satha)`, this completes the boss's hard-mode proc set.
- **Added:** `Crushed Armor Wrack (Kamangir)` — `4752009`, #General debuff. A separate encounter's copy of the debuff tracked as `Crushed Armor Wrack (T4 adds)`; the two share a display name but not a spell ID.
- **Added:** `Sonic Missile Elemental Wrack (I-Po)` — `4548156`, #General debuff.
- **Added:** `Ghost Fangs Torment (Bhangi Khan)` — `4549368`, #General debuff.
- **Added:** `Wrack Armor (Ironwright)` — `4707552`, #General debuff.
- **Added:** `Tainted Claws Wrack (Craterspawn)` — `4752047`, #General debuff.

## 2026-07-27
**Ruin line — four entries withdrawn.** Removed from the catalog after observed
application data showed their source encounters are well represented yet never apply
them; two also had incorrect attribution. Held aside for in-game verification and
re-added if confirmed. No profile whitelisted any of these IDs.
- **Removed:** `Flying Daggers Ruin` — `4256152`, #General debuff.
- **Removed:** `Soul Ruin` — `4257775`, #General debuff. Its game-data note reads as an unfinished developer instruction rather than shipped behaviour.
- **Removed:** `Viscous Ruin (Rocknoses)` — `5054617`, #Raid T6 debuff. The Rocknoses apply Elemental Ruin; this spell belongs to the Ethram set.
- **Removed:** `Splinter Ruin (T4 adds)` — `4552688`, #Raid T4 debuff.

## 2026-07-26
**Ruin line — five more boss ruins.** Debuffs confirmed against observed in-game
application data, cross-checked with the boss rosters.
- **Added:** `Capture Ruin (Sethik Bloodblade)` — #General debuff: `4826763`. A 10-second root, dispel-classed as a ruin.
- **Added:** `Batswarm Ruin (I-Po)` — #General debuff: `4051322`.
- **Added:** `Fiery Ruin (Dimensionalist)` — #General debuff: `4932986`. A 15-second stun, dispel-classed as a ruin.
- **Added:** `Aptitude Ruin (Grand Vizier)` — #General debuff: `4990471`.
- **Added:** `Kian Lai's Ruin (Kian Lai)` — #General debuff: `4283403`, `4804225`, `4804226`. A received-healing debuff; the game data classes it as a spiritual ruin for dispel purposes. Distinct from the boss's stacking armor debuff, which is a wrack.
- **Added:** `Visions of Ruin (Omni-Prophet)` — #General debuff: `4991521`. Applied by the adds in that encounter.
- **Added:** `Advisor's Ruin (Argo-satha)` — #General debuff: `4732527`. The ruin member of the boss's wrack/torment/ruin proc set; the game data stores it under the bare name `Advisor`.

**Ruin line — applier attribution.** Eleven ruin debuffs gained the boss/encounter that
applies them as a name suffix, matching the catalog's existing boss-source convention.
Display only — no IDs, categories, or types changed, so no grid or profile is affected.
- **Renamed:** `Broken Armor Ruin (T4 adds)` → `Broken Armor Ruin (Sheng)` (`4552633`, `5064100`) — the applying add belongs to that boss's encounter.
- **Renamed:** `Malicious Ruin` → `Malicious Ruin (Cavern of Malice)` (`4515827`) — applied by an add in that instance.
- **Renamed:** `Petrifying Ruin` → `Petrifying Ruin (Basilisk)` (`4989883`, `5056521`).
- **Renamed:** `Netherfrost Nether Ruin` → `Netherfrost Nether Ruin (Yun Rau)` (`4226929`).
- **Renamed:** `Eldritch Ruin` → `Eldritch Ruin (Little Prince)` (`4866663`, `4866666`).
- **Renamed:** `Dulling Roar Ruin` → `Dulling Roar Ruin (Bhangi Khan)` (`4268087`).
- **Renamed:** `Demonic Ruin` → `Demonic Ruin (Enigmata of Yag)` (`4507663`) — the three appliers are the one randomised boss of that encounter.
- **Renamed:** `Underworld Ruin 1-5` → `Underworld Ruin 1-5 (Kun Whu)` (`4046208`, `4046209`, `4046210`, `4046211`, `4046215`).
- **Renamed:** `Venomous Ruin` → `Venomous Ruin (Kian Lai)` (`4283587`, `4515792`).
- **Renamed:** `Ravaging Howl Ruin` → `Ravaging Howl Ruin (Bhangi Khan)` (`4549364`).
- **Renamed:** `Mind Ruin` → `Mind Ruin (Necropolis)` (`4502966`, `4502998`, `4788836`) — applied by an add in that instance.

`Physical Ruin`, `Elemental Ruin`, and `Spiritual Ruin` keep bare names — they are generic
debuffs with hundreds of distinct appliers each, so no single source applies.

**Ruin line — catalog expansion.** Fourteen ruin debuffs added and two existing entries
corrected. No existing entry's primary ID changed, so no profile whitelist is affected
(`Default.json` untouched).
- **Added:** `Petrifying Ruin` — #General debuff: `4989883`, `5056521`.
- **Added:** `Viscous Ruin (Rocknoses)` — #Raid T6 debuff: `5054617`.
- **Added:** `Underworld Ruin 1-5` — #General debuff, stacking (5 ranks): `4046208`, `4046209`, `4046210`, `4046211`, `4046215`.
- **Added:** `Splinter Ruin (T4 adds)` — #Raid T4 debuff: `4552688`.
- **Added:** `Eldritch Ruin` — #General debuff: `4866663`, `4866666`.
- **Added:** `Mind Ruin` — #General debuff: `4502966`, `4502998`, `4788836`.
- **Added:** `Venomous Ruin` — #General debuff: `4283587`, `4515792`.
- **Added:** `Malicious Ruin` — #General debuff: `4515827`.
- **Added:** `Soul Ruin` — #General debuff: `4257775`.
- **Added:** `Dulling Roar Ruin` — #General debuff: `4268087`.
- **Added:** `Ravaging Howl Ruin` — #General debuff: `4549364`.
- **Added:** `Flying Daggers Ruin` — #General debuff: `4256152`.
- **Added:** `Netherfrost Nether Ruin` — #General debuff: `4226929`.
- **Added:** `Demonic Ruin` — #General debuff: `4507663`.
- **Added:** `Broken Armor Ruin (T4 adds)` (#Raid T4 debuff) alias spell ID `5064100` — the re-issued copy of the same esoteric ruin (entry IDs now `4552633`, `5064100`).
- **Renamed:** `Derketo's Ruin (Yothians)` → `Derketo's Ruin (Zelandra)` (`5064042`) — corrected boss attribution; spell ID unchanged.
- **Renamed:** `Hopeless Reality Ruin (Shadur)` → `Hopeless Reality Ruin (Saddur)` (`4857485`) — corrected boss-name spelling; spell ID unchanged.
- **Renamed:** `Shackles (Shadur)` → `Shackles (Saddur)` (`4857484`) — same boss, same spelling correction; spell ID unchanged.
- **Fixed:** `Symbiotic Idol of Set 1-5` → `Symbiotic Idol of Set 1-6` (Tempest of Set stacking buff). Rank 1 spell ID `3776175` → `3776171`: the old ID does not exist in the game, so rank 1 never resolved. Rank 6 `3776180` was missing and is now tracked, so the entry covers the buff's full 1-6 range (entry IDs now `3776171`, `3776176`, `3776177`, `3776178`, `3776179`, `3776180`). No profile whitelisted the old ID, so none needed updating.

Ruins filed under `#General` carry the bare debuff name — no boss/instance suffix. Source
suffixes are kept only where the entry sits in a raid-tier category.

## 2026-07-25
**Ruin line — alias spell IDs for the later re-issue of the generic Ruin family.** The three
`#General` ruin debuffs only carried their original spell IDs, so they never matched the second
set the game issued for later content. Names, categories, types, and each entry's primary ID are
unchanged, so no grid or profile whitelist is affected (`Default.json` untouched).
- **Added:** `Elemental Ruin` (#General debuff) alias spell IDs `4244576`, `4244577`, `4244578`, `4244579`, `4244580`, `4244581` (entry IDs now `3963062`, `4244576`, `4244577`, `4244578`, `4244579`, `4244580`, `4244581`).
- **Added:** `Physical Ruin` (#General debuff) alias spell IDs `4244715`, `4244716`, `4244717`, `4244718`, `4244719`, `4244720` (entry IDs now `3963059`, `4743743`, `4244715`, `4244716`, `4244717`, `4244718`, `4244719`, `4244720`).
- **Added:** `Spiritual Ruin` (#General debuff) alias spell IDs `4244721`, `4244722`, `4244723`, `4244724`, `4244725`, `4244726` (entry IDs now `3963070`, `4244721`, `4244722`, `4244723`, `4244724`, `4244725`, `4244726`).

## 2026-06-22
- **Added:** `Seal of Yog (Crit)` — Dark Templar stacking buff (10 stack ranks): `4204058`, `4204059`, `4204060`, `4204061`, `4204062`, `4204063`, `4204064`, `4204065`, `4204066`, `4204067`.
- **Added:** `Seal of Yog (Mana)` — Dark Templar stacking buff (5 stack ranks): `4203944`, `4203945`, `4203946`, `4203947`, `4203948`.

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

---

*Entries are reconstructed from `git log` on `Database.json` (this repo) and the predecessor
`KzBuilder-public` repo; spell IDs reflect the current database, which holds **403 buffs**.
Going forward, log changes here as they happen.*
