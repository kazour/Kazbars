# Target inspect panel — stat reference

What the inspect panel reads (the `KazBarsInspect` / `KazBarsInspectRows` stubs and the stat catalog behind them), and why every constant is the number it is. Update when the catalog, a synthesis formula, or a display gate changes — the stubs carry the rules as comments, this doc carries the reasoning and the id table behind them.

The panel is an optional in-game overlay (Extras ▸ Inspect Target…) that renders a combat sheet for the current target — the rows the user picked, or the Default Summary sheet — in the visual language of the game's own inspect window. It is off by default; when off the build emits zero references and the compiler skips the stub entirely.

| Piece | Where |
|---|---|
| Runtime (AS2: poll, layout, perks, PvP tab) | `src/kazbars/assets/kazbars/stubs/KazBarsInspect.as` (chrome/collapse primitives from `KazBarsPanel.as`; the preview overlay it is dragged by from `KazBarsPreview.as`; the target from `KazBarsWorld.as`) |
| Stat model (every id read, every synthesis, the row formatters) | `src/kazbars/assets/kazbars/stubs/KazBarsInspectRows.as` |
| Stat catalog (rows, the ids each reads, formatter fields, `ALWAYS_IDS`, `PVP_VIEW`) | `src/kazbars/inspect_catalog.py` |
| Baked tables (perk pool, names, class map) | `src/kazbars/assets/kazbars/stubs/KazBarsInspectData.as` — static `init()` |
| Config layer (pure, no Tk) | `src/kazbars/inspect.py` — `validate_config()` |
| Settings dialog | `src/kazbars/inspect_panel.py` — `open_inspect_dialog()` |
| Build gate | `src/kazbars/grids_generator.py` — `include_inspect`, emits `d.INS` (`_inspect_data_block`), `d.INS.groups` / `.rows` / `.watch` (`_inspect_rows_block`) and `d.INS.pvp` (`_pvp_view_block`) |
| Config flow | [`flows.md`](flows.md) → flow 26 · build gating → flow 1, step 10 |
| Module wiring | [`architecture.md`](architecture.md) → Build pipeline |

Nothing here is unit-testable — `tests/test_inspect.py` covers the config layer, `tests/test_inspect_catalog.py` the catalog's shape, `tests/test_grids_generator.py` the on/off codegen contract, and `tests/test_build_compile.py` a real compile of the stubs, but the numbers below only prove themselves against the live game sheet. See **Verification** at the bottom.

---

## 1. Reading rules

These are measured engine behaviour, not style choices. Changing any of them changes what the panel shows.

- **Read with `GetStat(id, 2)`.** Mode 2 is the live effective value, for every id (`readIds`). The one other read is the weapon family, off the target's inventory (`readWeapon`, §3) — not a stat.
- **Poll; do not trust signals.** A full pass over the baked ids (§2) runs every 250 ms on one `KazBarsClock` task, switched on only while there is a subject and the panel is shown. `SignalStatChanged` is not usable as the data path here: gear and rating ids never fire it at all, signal-time reads race the server, and equips with no stat lines emit nothing. The poll *is* the settle re-read, and the assign-on-change string cache in `render()` subsumes any dirty flag — most passes change nothing, and `TextField.text` writes are the expensive part.
- **The pass only pays for what is on screen.** The panel shares one AVM1 sandbox with the grids and every other module, so a pass does no work it cannot show. Collapsed the panel is a static label (§5), so a pass reads `GATE` — the teardown gate's two ids — instead of the whole list, and skips the player gate, the perk read and all value building; expanding runs one full pass immediately (`toggleCollapsed`), so the sheet is never stale. The PvP tab reads its own list (`d.INS.pvp.ids`), and only while it is the view on screen. Perks are not a buff-list walk: the subject's `KazBarsEffects` (the one the grids share) is watched by the perk ids alone, only on a player, and re-read only when its `ver` moved — so bosses, with the longest buff lists in the game, are never watched. Stat values are cached under the raw id and the player gate is settled once per pass into `subjPlayer`, because a full render asks `gv()` ~195 times. A perk buff's icon instance is read once per id per session into `iconInst` rather than per pass — it is static game data.
- **Warm up 3 passes (~750 ms)** before the panel is allowed to show. Login, zone changes and retargets all repopulate stats over roughly that window; without the warm-up a retarget flashes the previous target's values.
- **Teardown gate.** Logout and zoning collapse every id to 0 in one burst. Id 1 (max HP) and id 54 (level) reading 0 *together* is that burst, not data. On detecting it the stub drops the subject handle outright — keeping the dead handle lets the warm-up count three null passes and re-show a phantom all-dash sheet.
- **Subject resolution.** `KazBarsWorld` names the target: one `SignalOffensiveTargetChanged` (re-read once a second in case a signal was missed), delivered to `onTarget` as the `Character` plus its instance id (`w.tn`). Identity is that instance id (`subjN`); re-targeting the same entity keeps the warm cache instead of restarting the warm-up, and World telling the same target again with a fresh `Character` only swaps the handle.
- **Visibility is per subject.** A neutral player exposes most of the combat sheet; a hostile player additionally exposes the PvP cluster; mobs expose no attributes, so every attribute-fed synthesis collapses to a dash by design; bosses expose template stats plus critigation.
- **Rounding.** The game sheet *rounds* fractional internals, `GetStat` *floors* them. A ±1 disagreement with the sheet is the display surface, not a wrong formula. Health percent (id 525) is shown verbatim for the same reason — the panel never computes it.

---

## 2. The watch list

There is no fixed list. Every catalog row (`inspect_catalog.Row`) names the stat ids its `Kind` reads (`needed_ids`); the build bakes `d.INS.watch` = `watch_ids(selected rows)` — the ascending union of those ids with `ALWAYS_IDS` (1, 54, 67, 70, 804, 808, 810, 814: the teardown gate, the title and the player gate) — and the PvP view bakes its own, `d.INS.pvp.ids`. The Default sheet reads 60 ids, all 112 rows 155, the PvP view 66. They are polled every pass while the panel is open (collapsed, only `GATE` is read — §1). `curV[id]` holds the last settled value; `gv(id)` returns 0 for absent, null or NaN. The tables below are the ids the syntheses (§3) are built from and what each means; a row's other ids and its decode are in the catalog, each `Row` carrying its note and how fresh its value is.

### Vitals & identity

| id | meaning | notes |
|---|---|---|
| 1 | Max HP | half of the teardown gate |
| 27 | Current HP | |
| 525 | HP % | displayed verbatim — the game floors it |
| 54 | Level | other half of the teardown gate; feeds the title |
| 67 | Class id | 34 (dagger class) and 39 (Ranger) select Dex over Str for CDI — both named by the sheet's own tooltip; 34 alone gets the 5.0 crit base (Ranger sheet-verified on 2.5). Also feeds the title's class name via the measured table 18 Barbarian · 20 Guardian · 22 Conqueror · 24 Priest of Mitra · 28 Tempest of Set · 29 Bear Shaman · 31 Dark Templar · 34 Assassin · 39 Ranger · 41 Necromancer · 43 Herald of Xotli · 44 Demonologist — all twelve measured off live targets |
| 70 | PvP level | raw; sheet-exact on five characters; feeds the title only |
| 507 | Max Mana | gates the Bonus Spell Damage lines — mana-less classes sheet the whole per-school block at 0 |

### Armor & protection

| id | meaning | notes |
|---|---|---|
| 448 | Armor gear component | |
| 450 | Bonus Armor % | multiplies 448 **only** |
| 451 | Protection flat component | |
| 334 | Bonus Protection % | multiplies 451 **only** |
| 157 | Cold protection component | Intelligence-fed |
| 926 | Fire protection component | Intelligence-fed |
| 927 | Electrical protection component | Intelligence-fed |
| 928 | Holy protection component | Wisdom-fed |
| 929 | Unholy protection component | Wisdom-fed |
| 911 | All-type invulnerability component | stances and buffs; also moves as a boss mitigation-phase marker |

Armor covers physical **and** poison damage, so the panel shows no separate poison line.

### Invulnerabilities (raw %, unclamped)

| id | meaning |
|---|---|
| 902 | Physical |
| 167 | Cold |
| 905 | Fire |
| 906 | Electrical |
| 907 | Holy |
| 908 | Unholy |

Invulnerabilities are unclamped in both directions: debuffs drive displayed mitigation negative, and values above 100% convert incoming damage to healing. Both are real states the panel renders faithfully.

### Ratings & synthesis inputs

| id | meaning | notes |
|---|---|---|
| 312 | Critical Rating | |
| 711 | Critical Damage Rating | |
| 710 | Critical Damage flat add | the sheet's +% on top of the rating share (§3); read from one stat, measured on one character |
| 148 | Equipped-slot bitmask | bit 64 clear = no main-hand weapon (or not loaded yet), bit 256 stays set with a two-hander; with the inventory read it gives the weapon family (§3) |
| 170 / 488 / 491 | Hate modifier (signed percent) / Hate Decrease rating / Hate Increase rating | the Hate lines (§3) |
| 449 / 452 | Armor / Spell Penetration rating | shown raw — no effect divisor was ever measured |
| 713 | Heal Rating | gear-sourced; NPCs never carry it |
| 804 / 808 / 810 / 814 | Strength / Intelligence / Wisdom / Dexterity | ×10+10 encoded (§3) |
| 1403 | Ferocity | ×10 encoded; `floor(1403/10)` **is** the sheet value — verified exact both loaded (2600 → sheet 260) and empty (0 → sheet 0, on a character whose old base-candidate id still read 33; that id, 864, is the engine's "Player Flags" state slot and feeds nothing) |
| 875 | Untyped Combat Rating | CDI input |
| 866–873 | Per-weapon-school Combat Rating | 1HE, 2HE, 1HB, 2HB, dagger, polearm, bow, crossbow |
| 162 | Cold Combat Rating | CDI input |
| 1007–1010 | Fire / Electrical / Holy / Unholy Combat Rating | CDI inputs |
| 1095 / 1096 | Weapon Damage % (Melee / Ranged), ×100 | the larger of the two is shown as one percent (a character fights with one of them) — no other synthesis, no gates; stance and proc swings and multiplicative feats (Reave-type) are already inside the values. Dashed only when both are absent |
| 861 | Untyped Magic Damage | applies to every school |
| 158 / 876 / 877 / 878 / 879 | Cold / Fire / Electrical / Holy / Unholy Magic Damage | per-school component on top of 861 |
| 1041 | Base Spell Damage % | its own raw row; the spell total adds a flat 1 instead (§3) |

Cold is the low-range outlier in every school family — 157 protection, 162 combat rating, 167 invulnerability, 158 magic damage — while the other four cluster. Expect that shape when adding a school-keyed id.

### Extended block

| id | meaning |
|---|---|
| 1000016 | Critigation Chance rating |
| 1000017 | Tenacity rating |
| 1000018 | Critigation Amount rating |

Tenacity comes from PvP gear only; bosses never carry it.

### Slotted perks (buff ids, not stats)

Not stat ids — these come off the subject's `KazBarsEffects`, watched by the perk ids alone (`PERK_FX`), on the same pass that reads the perk row. `PERK_IDS` maps **113 perks over 114 ids**, one rank each, in id order — almost all of them in the span **4279889–4282396**.

**The pool shape is the proof.** A character slots 6 of them (2 General + 2 Archetype + 2 Class, some Class perks taking both Class slots), and the pools are exactly **9 General, 5 per archetype, 7 per class** — 9 + 4×5 + 12×7 = 113. Every block below fills its quota exactly, which is what resolves the only genuinely ambiguous case: the descless run 4281420–4281429 holds eight names, so Guardian stops at 4281426 and `Void of Madness` (4281429) is the Dark Templar's seventh. Both halves are now confirmed in game.

| block | ids | count |
|---|---|---|
| General | 4279889 · 4279980 · 4279994–97 · 4280003–05 | 9 |
| Priest archetype | 4280100–01 · 4280167 · 4280208–09 | 5 |
| Soldier archetype | 4280766 · 4280968 · 4280978 · 4280980–81 | 5 |
| Rogue archetype | 4281007–11 | 5 |
| Mage archetype | 4281107–11 | 5 |
| Herald of Xotli | 4281211–17 | 7 |
| Guardian | 4281420–26 | 7 |
| Dark Templar | 4281429 · 4281445–47 · 4281451–53 | 7 |
| Conqueror | 4281564–68 · 4281571–72 | 7 |
| Priest of Mitra | 4281728–34 | 7 |
| Bear Shaman | 4281884–90 | 7 |
| Tempest of Set | 4281940–46 | 7 |
| Assassin | 4282096 · 4282100 · 4282105 · 4282107–10 | 7 |
| Barbarian | 4282139–40 · 4282142 · 4282156 · 4282159–61 | 7 |
| Demonologist | 4282300–06 | 7 |
| Necromancer | 4282307–13 | 7 |
| Ranger | 4282381–84 · 4282387 · 4282396 · **4483617** | 7 |

**107 of the 113 are read off the live in-game perk UI** — General, all four archetypes, and every one of the twelve classes. (Four of those 107 were confirmed by name rather than by id: Necromancer's 4282307–09, pinned as the only gap between Demonologist's confirmed 4282306 and Necromancer's confirmed 4282310, and Assassin's `Master Assassin` 4282096, the only descless entry left in its run.) The six that remain unread are the plain descless members of the Dark Templar run, 4281445–47 and 4281451–53 — the same shape that has been verified correct in all eleven other blocks, and its one genuinely ambiguous member, `Void of Madness` 4281429, is confirmed.

**A block is not guaranteed to be contiguous, or even in the band.** The Ranger's seventh perk, `Point Blank Shot`, was added by a later patch and sits at **4483617** — 200k ids away, with only its own `Hunting Hawk` proc records nearby. Filling that slot from the block alone picked up `Taking the Shot` (4282385), which the in-game UI does not list; it now rides along as an *alias of the same rank*, so whichever id the game actually applies paints one icon and never two. That is the failure mode to watch for whenever this table is extended: a plausible in-band name silently standing in for a real perk that lives elsewhere. Across the twelve class blocks it happened exactly once. Assassin — the other block with internal gaps, and the obvious next suspect once Ranger fell — came back correct, so the gapped shape proved a weak signal rather than a predictor. Nothing else in the id space is a reliable warning either; only reading the live perk UI settles it.

**Names ride the rank, not the id.** `PERK_NAMES` is a 113-entry rank-indexed table feeding the hover chip (§5); it is baked because the icon instance the row carries doesn't identify the perk and no name field is confirmed on a buff-list entry. The alias pair collapses cleanly — rank 112 holds both 4282385 and 4483617, and its name is the real perk, `Point Blank Shot`. Extending the id table means extending this one at the same rank.

**4279994 is in this table** — "Immeasurable Empowerment", the +100-all-attributes passive (§3), is itself a slotted General perk, so it paints an icon like the rest.

**Two traps.** Most perks carry the placeholder description `No description given.`, but that is a *heuristic, not a rule*: `Prelate at Arms` (4280100, "team propagated container") and `Empowered Vitality` (4280968, "Increases Con by 2-10%") are real perks with real descriptions, and a descless-only sweep silently drops them. And the id span reaches **below** 4280000 — six General perks live at 4279889–4279997. A third-party overlay filters its own perk readout with `4279999 < m_BuffId < 4290000`, which is what first located the band, but that bound misses those six at the bottom and sweeps in ~200 NPC abilities at the top; enumerating is what avoids painting boss debuffs as perks.

Excluded from the band as non-perks: the potion-effect family, `Ethereal Lash` (a stacking-debuff family), `Bestial Endurance` (inside the grey-ape NPC run), the `Stygian Halfbreed` / `Tarpani Stallion` mounts, `Perkspell Test`, and the whole 4286xxx cluster (`Alignment of the Stars`, `Shadow of the Moon`, `Arc of the Sun`, `Reading the Heavens` and their II/III variants) — that last one sits among potion effects and megalith markers, and the General pool is confirmed full at 9 without it. **Candidates, not rejects:** `Taste of Blood` (4285065) and `Smoldering Strike` (4285069), plus the 4286xxx name-twins of the Barbarian perks `At the Gates` and `What it Takes`.

### PvP

| id | meaning | notes |
|---|---|---|
| 454 | PvP armor gap | added to the PvE total; can be negative |
| 458 | PvP protection gap | one value, applies to all five schools; can be negative |
| 225 | PvP Combat Rating | added to the CDI rating on the PvP line; moves mid-combat on procs and can rest negative |
| 226 | PvP spell-damage gap | sheet label "PvP Bonus Spell Damage"; one value, applies to all schools (the 458 shape); per-item accumulator, can rest negative; added to the spell-damage total on the PvP line |
| 656 / 658 | Overall Kills / Deaths | the PvP Stats rows pair them with the season ids (1382 / 1383) and the PvP tab's Record line shows overall K/D from these; `0 / 0` is real data, printed rather than dashed |

---

## 3. Syntheses & constants

Every constant below was first measured at **level 80** and has since been confirmed level-invariant across the game's full 1–86 range by in-game verification — no level scaling applies, and no level gate exists in §4.

### Attribute decode

```
attrSheet(id) = round((GetStat(id, 2) − 10) / 10)      // 0 = absent
```

Attributes are ×10+10 encoded. This matters twice: the syntheses need the decoded value, and *raw presence is not a discriminator* — an NPC template carrying attributes at base still reads raw 10, which decodes to 0.

### The linear rating law

```
effect% = classBase + rating / 36.6
```

Every rating-column stat fits this. Critigation chance, critigation amount and tenacity have a zero base, so `pctOf()` is the whole decode for them. Combat Damage Increase is flat rather than a percent: `round(rating / 36.6)`.

### Mitigation curve

```
mit(v, a):  v ≤ 0  → 0                     // negative stat space floors at 0%
            q = v / a
            q ≤ 50 → q
            else   → 100 − 5000 / (50 + q)

a = 219.6 (armor)   ·   73.7 (protection)
```

Piecewise, with the knee at 50%. Diminishing returns live in item budgets, not in this conversion.

### Invulnerability fold

```
displayed% = mit + (perTypeInvul + id911) × (1 − mit / 100)
```

The sheet's per-type invulnerability column is the per-type id **plus** the all-type component 911 — reading the per-type id alone under-reports any stance or buff.

### Sheet totals

```
Armor          = floor(448 × (1 + 450/100)) + 2 × Str
Prot(school)   = schoolComp + floor(451 × (1 + 334/100)) + floor(attr / 2)
                 attr = Int for Cold/Fire/Elec · Wis for Holy/Unholy

CDI rating     = 3 × (Dex for classes 34/39, Str otherwise; floored at 0)
                 + 875 + schoolCR + 162 + 1007 + 1008 + 1009 + 1010
CDI effect     = round(rating / 36.6)
PvP CDI rating = CDI rating + 225

PvP Armor      = Armor + 454        ·  PvP Prot(school) = Prot(school) + 458
PvP Spell Dmg  = Bonus Spell Dmg total + 226
```

`schoolCR` is the largest combat rating in the equipped weapon's family: **none** without a main-hand weapon (bit 64 of id 148 clear), `max(867, 869, 871, 872, 873)` for a two-hander, `max(866, 868, 870, 872, 873)` for a one-hander (the dagger/bow/crossbow ids 872 and 873 sit in both), and `max(866…873)` while the family is unknown. The weapon type itself is **not** readable — weapon-set swaps leave the equip bits invariant — but its family is: `readWeapon` reads the target's inventory (`Inventory(ID32(101, instance)).m_Items`), slot 6 the main hand and slot 8 the off hand, and a main hand with an empty off hand while bit 256 of 148 is still set is a two-hander. It runs on settled full passes only, after the warm-up (before it id 148 and the inventory are still filling, and a read would commit a wrong family), again every 3 s once read and every 0.5 s while the inventory has not loaded. Characters stack their own school's combat rating, so the largest component in the family is it — a documented heuristic, not a measurement, though the game's own CDI tooltip named the max component as the weapon school on the one character cross-checked.

**The composition is the sheet's own, verified digit-exact from the game's itemized CDI tooltip on two characters across multiple gear/buff states.** The attribute term is the sheet attribute (`attrSheet`, mode 2). Two sources raise it without raising this rating — the **+100-all-attributes AA passive** ("Immeasurable Empowerment", buff id 4279994: bugged in-game, its attributes never feed the rating though its Wisdom does feed spell damage) and %-attribute potions (the sheet's own basis is the pre-multiplier value) — and the stub does not correct for either, since reproducing the exclusions needs a formula we do not have and guessing a rank was worse than the straightforward number; the line reads high on a subject running one. The +225 PvP delta is exact regardless.

When a subject exposes no Strength (`attrSheet(804) == 0`, i.e. every mob), the armor line falls back to the raw gear component 448 rather than a total built on a missing term.

### Critical chance

```
chance% = rating(312) / 36.6 + weaponBase
weaponBase = 5.0 for class 34 (daggers) · 2.5 otherwise
```

### Critical damage

Rating share plus the flat add: `pctOf(711) + 710`, shown `rating (effect%)` and dashed only when both are absent (a flat-only bonus with no rating is still real data). Id 710 is the sheet's +% on top of the rating share, read from one stat and measured on one character; the sheet's feat/AA base beyond it is **absent from stat space** and not class-keyed, so inventing a constant would inflate the line for everyone who does not have it.

### Heal Rating

```
Celestial Gaze = 271 + HR × 0.2761   …   292 + HR × 0.2761
```

Heal Rating benefits specific heals only and has no percent form, so the panel shows the Celestial Gaze range it buys — the main beneficiary. Source: the community AA-heal table (joharaoc.eu/aaheal), not a direct measurement; the healing sheet absolute is not exposed as a stat, so the rating is the only input. Player-only.

### Bonus Spell Damage

```
total = 861 + school + round(0.6 × max(Int, Wis)) + 1        // + 226 on the PvP rows
school = max(158, 876, 877, 878, 879) · or one named school's id (the PvP per-school rows)
```

Without a named school only the highest shows — a caster stacks exactly one. `max(Int, Wis)` avoids an unmeasured class table (priests lead on Wisdom, mages on Intelligence), the same shape as the school-CR heuristic above. The sheet adds a flat 1 regardless of Base Spell Damage % (id 1041, which has a raw row of its own): read as a percent of the total it lands nowhere near the sheet. Player-only and **mana-gated**: a mana-less class (Ranger measured — max mana 0, sheet block all zeros despite 861/1041 residue in stat space; Barbarian predicted) dashes rather than synthesize a number the sheet contradicts.

The PvP rows add the per-school gap 226 flat on top of the same total — one line per school, as the game's PvP Combat tab has them — the composition every other PvP row uses (+454, +458, +225), and it is **sheet-verified on two characters**: a Tempest of Set with 226 = −186 read exactly `total + 226` on the school-carrying line (985) with the school-less lines ±1 (the fractional attr term's rounding surface), and a Bear Shaman with 226 = −250 sheeted −71 against a composed −72 — the sheet's PvP per-school block is absolutes, not gaps, and renders negative faithfully.

### Ferocity

```
total = floor(1403 / 10)      ·      effect% = 0.15 × total
```

Verified exact at both ends: a loaded character (1403 = 2600 → sheet 260) and an empty one (1403 = 0 → sheet Ferocity 0, even though the one-time base candidate id 864 still read 33 there — 864 is the engine's "Player Flags" state slot and feeds nothing). The 0.15 slope rests on a **single sheet pair** (260 → +39.0% on all five AOE surfaces — radius, max targets, cone angle, column distance, splash amount; the sheet shows one uniform percent). Player-only.

### Other row kinds

The catalog's remaining lines are small compositions over the same law (`KazBarsInspectRows`; each prints `rating (effect)` and dashes only when every term is absent, `0` being real data on pairs and pools):

```
Hate          rate = 491 − 488 ;  effect% = rate / 36.6 + 170          // signed, nothing clamps it
Chance        rate = ratingId + pvpRating + floor(attrSheet(attr) / 2) ;  effect% = pct / scale + rate / 36.6
              (Evade, Hit Bonus, Immunity, Offhand, Fatality; scale 100 for the ×100 percent ids)
Tap           rate = ratingId + pvpRating ;  effect% = a / scale + b + rate / 36.6      // a, b the buff-percent ids
Regen         floor(base + (k / 100) × (exact attr₁ + attr₂ + attr₃))                   // exact = (raw − 10) / 10, unrounded
Protection    (Summary) the highest of the five PvE school totals, first wins a tie, with its own invulnerability
Pool          current (percent%)  — Health, Stamina, Mana, dashed only when neither id has ever answered
```

### Attribution

The mitigation curve and the 36.6 / 73.7 / 219.6 divisors originate in community formula work (the 2016 Age of Conan formula thread) and were re-verified digit-for-digit against the in-game sheet before shipping. The heal decode is community-table-sourced as noted. Everything else — the totals, the fold, the CDI composition, the spell-damage composition, the class-id table and the PvP gaps — was derived here against the sheet.

---

## 4. Display rules & gates

- **Dash, never drop.** Absent data renders as an em dash (`String.fromCharCode(8212)`) inside the value field. Row counts never change, so `layout()` re-runs only when a group or the Perks row shows or hides. The Default (Summary) lines differ in look, not count: a would-be dash renders as the zero the character sheet shows (`z: 1` — `0 / 0`, `0 (0.0%)`, `0.0%`; the player-only lines `0` on a player and a dash on anything else).
- **Title line** is `Name Class (Level/PvP level)` — e.g. `Kazour Bear Shaman (80/10)`. The class name appends only when the player gate below agrees the subject is a player **and** id 67 maps (all twelve classes measured; an unmapped id would mean a patch moved the enum and simply omits the class); the level part drops absent components, so a mob reads `Name (83)` and a player with no PvP level `Name Class (80)`. Built per pass from polled stats and cached assign-on-change like the value columns; an overlong name + class combination clips at the name field's fixed width.
- **Line format** is `Rating (Effect%)`, matching the game's own combat-stats tab. The CDI synthesis is labeled **Combat Rating** on the sheet and **Combat Damage Increase** in the PvP view; this doc keeps CDI as the synthesis name.
- **The rows are the user's.** `inspect.rows` picks catalog rows by key (§2): absent (Default) is the Summary group, twelve lines, and a list shows exactly those rows, section by section in the catalog's `Group` order (Summary, Vitals, Attributes, Offensive, Defensive, PvP Stats, PvP Combat), each section in the user's order. A group with no picked row has no header; an empty list leaves the title line and the Perks row only. The rows, labels and group headers are baked (`d.INS.groups` / `.rows`), so changing the pick takes a Build & Install like every other baked value. The label column is as wide as the widest baked label, never narrower than its ratio (§5).
- **Player gate.** The PvP tab, the Perks row, the title's class name, the player-only lines and any PvP Stats / PvP Combat group the user picked show only when the engine's `ID32.IsPlayer()` **and** a decoded attribute spread both agree:

  ```
  hasAttrs = any of attrSheet(804/808/810/814) > 4
  isPlayer = (subjIsPlayer >= 0) ? (subjIsPlayer == 1 && hasAttrs) : hasAttrs
  ```

  `IsPlayer()` is measured truthful on players but has never been sampled on a mob, so it **vetoes** rather than confirms alone; `subjIsPlayer == -1` means it never answered and the attribute spread carries the decision. The attribute half must be *decoded* — testing raw presence put a PvP block on city guards, because an NPC template at base attributes reads raw 10.
- **The PvP tab.** A PvP glyph in the title strip (an expanded panel on a player) swaps the sheet for a fixed view, `d.INS.pvp`, whatever rows the user picked (`inspect_catalog.PVP_VIEW`, the game's PvP Combat tab less its taps, then two record lines): **PvP Combat Stats** (columns Rating / Effect — Evade Chance, Hit Bonus Chance, Immunity Chance, Armor, Combat Damage Increase), **Protection** (Score / Mitigation, the five schools), **Bonus Spell Damage** (Damage, the five schools) and **Record** (Overall K/D, Minigame W/L). A line splits at its rating into its two columns, a negative value is drawn red (`0xE0503C`) as the game does, and the view polls its own ids (`d.INS.pvp.ids`, §2). The pick is kept in the archive (`inp`); on a target that is not a player the sheet stays up whatever the pick (`want(g, player)`). The PvP rows add their gaps: +454 armor, +458 protection, +225 combat rating, +226 spell damage (§3).
- **Player-only lines** — Heal Rating, Bonus Spell Damage and Ferocity — dash on any non-player subject.
- **Perks row** (a player's, always, below whichever view is up). `readPerks` collects every id in the subject's watched `KazBarsEffects` that is in `PERK_IDS` ("i\<buffId\>" → display rank). The six boxes mirror the game's own perk bar: **three fixed, colour-coded pairs** — General, Archetype, Class — so a perk drops into its own pair rather than filling left to right, and a colour never lies about what it is holding. `PERK_IDS` is ordered General → the four archetypes → the twelve classes, so the two rank boundaries `PERK_GEN_MAX` (8) and `PERK_ARCH_MAX` (28) are the whole category test. A pair holds two; anything beyond is dropped rather than spilling into the next category's colour. Slot state is the icon instance with **−1 for empty** — 0 is a real value, since a perk whose buff carries no icon still holds its slot.

  **Two-slot perks** (the game calls them Major Perks). Three of every class's seven cost both class slots — 36 in all, listed in `PERK_2SLOT` and keyed by rank, which is what `placePerks()` already carries. Such a perk paints its icon across *both* class boxes, the way the game draws it, so a character running one shows six icons rather than five. It claims the pair only when both boxes are free; otherwise it takes the second like any other perk. None of General or Archetype is two-slot. The marked-up source list is `gamedata/perks.md` (local-only).

  **One request per distinct instance, one clip per answer.** `RequestRDBImage` answers a given id **once** — a second request for an id already in flight never calls back. Two boxes showing the same icon (exactly the two-slot case) therefore cannot each ask for it up front — and the single answer must not be `loadClip`-ed into both boxes in the same tick either: the two binds share one movie definition, the retarget unload releases it twice, and the resulting heap corruption crashed the client an inspection or two later (isolated in-game with a serve-one-slot probe build). `renderPerks()` runs in two passes — settle every slot's target instance and drop stale art first, then issue one request per distinct instance, deduplicating only against instances requested *on that same pass* (a slot that kept its art issued no request, so it cannot serve a partner that has just come to want the same instance); a deduplicated partner keeps its `_want` mark as *pending*. `onPerkIcon()` loads the answer into the requesting slot only, then chains the partner: the answer just took the id out of flight, so it re-issues the request for the first slot still pending on that instance, and that slot's own callback paints it a beat later. Icons are the game's own, loaded from the buff's `m_Icon.GetInstance()` via `ImageLoader.RequestRDBImage(1010008, …)` — the grids' icon path. Each slot nests three clips on purpose: the box outline draws on the unscaled slot, a `hold` child carries the scale, and the icon loads into `hold.m_icon`. `loadClip` **replaces** its target clip and `onLoadInit` then normalizes the arrival to 64×64, so any scale set on the load target itself is overwritten — the scale has to live on the parent, or icons render at 64px and overflow the box. An empty box is the row's em dash. Rank-variant duplicates of one perk collapse to the first seen; the render is assign-on-change keyed on the joined `rank:icon` string, and only slots whose icon changed reload. Presence semantics: a passive perk shows while slotted, an active one only while its buff runs, and a granted group-perk buff (the Enchanter shape) lands on the *receiver* — the row reads "perk buffs on this player", not "perks this player slotted".
- **Preview** (`previewOn()`) shows every group of the view in play and the Perks row, as `previewOn` laid them out for the overlay — which spans the taller of the two views (`footH`) — the footprint being positioned, not the one this target happens to earn — and its content is live-or-empty: a target with a settled read renders normally under the overlay, perks included, and a retarget mid-preview follows; untargeted, the chrome and labels show with empty values — and a target lost or swapped mid-preview blanks them the same way (`resetScan` clears the name and the value columns while preview is on; nothing repaints until the next subject settles). It renders from an *effective* fold state (`folded()`, i.e. `collapsed && !previewMode`), so a folded panel shows its sheet at the bar's own top-left spot without the flag being touched; `pollTick`'s id-list choice and `render()`'s early return use the same predicate, and entering preview takes a full pass at once, or a folded panel would show a full-size plate of dashes. `previewOff()` detaches the overlay, re-applies the real fold state and clears the render cache. Every sheet is behind the master switch (`active`, persisted as `inv`): it is `&&`-ed into `updateVisibility`'s one gate, and an inactive panel returns from `pollTick` before touching the watch list. Preview does not override it — an unchecked panel stays dark in preview too, and the control-panel row that re-checks it calls `setActive(true)`, which re-runs the gate against the `previewMode` `previewOn()` already set.

---

## 5. Visual contract

The panel mirrors the game's default inspect window: near-black warm plate, 1px black-over-bronze frame, Conan-orange headers with hairline rules, parchment-grey labels, sheet-green values. Device-font fields (`embedFonts = false`) in the build's face — Arial from `base.swf`, the game's own `_StandardFont`, or a baked face spliced over the Arials (`KazBarsPreview.FACE`, set from `d.PF.face`) — so the panel needs no new symbols. Colours are written inline at their draw sites — the family base's `drawPlate()`, `hairline()` and `makeTF()` in `KazBarsPanel.as` plus the stub's own fields — not held in named constants:

| Color | Value | Role |
|---|---|---|
| header | `0xF7A22B` | name strip + group headers (bold) |
| label | `0xC8C0B0` | stat labels |
| value | `0x7AC142` | stat values, including the em-dash fallback |
| rule | `0x6B5324` | 1px rule under each section header — the family's `hairline()`, that colour's sole owner |
| plate | `0x0C0A07` @ alpha 90 | plate fill |
| inner frame | `0x4A3B22` | 1px inner frame |
| outer frame | `0x000000` | 1px outer frame |
| column title | `0x7F786C` | a PvP section's column titles (dim) |
| PvP glyph | `0xA89A86` / `0xF7A22B` | off / picked or hovered |
| negative value | `0xE0503C` | a PvP-view value that starts with a minus |

The perk row is the one place the panel departs from that palette, mirroring the game's perk bar instead — each slot pair carries its own border and plate, and the pairing *is* the category legend:

| pair | slots | border (`PERK_EDGE`) | plate (`PERK_FILL`) |
|---|---|---|---|
| General | 0–1 | `0x4A7FA5` blue | `0x0F1C26` |
| Archetype | 2–3 | `0xA34A4A` red | `0x260F0F` |
| Class | 4–5 | `0x555555` grey | `0x151515` |

Every dimension is `Math.round(FS × ratio)`, so the whole panel scales as one piece from the baked body size `FS = panel_fs(overlay.size, inspect.scale)` (`max(8, round(size × scale / 100))`, `overlay_size.py`). The family's ratios come from `KazBarsPanel.applyBaseSize` (text roles Small 0.8, Title 1.25, Alert 1.6 through `roleFS`); the panel's own are:

| Constant | Ratio | @ FS 12 | Role |
|---|---|---|---|
| `PAD` | 0.85 | 10 | plate padding, all four sides |
| `LABEL_W` | 8.6 | 103 | label column — widened at create to the widest baked label, never narrower than the ratio (a picked row can carry a name the ratio was never sized for) |
| `COL_GAP` | 0.85 | 10 | label column → value column |
| `VALUE_W` | 12.0 | 144 | value column (fits a boss health line) |
| `NAME_FS` | 1.25 | 15 | name header font size (the Title role) |
| `TITLE_H` | `lh(NAME_FS)` + 2 × `round(0.25 FS)` | 27 | title band — name left-aligned and vertically centred in it, hairline rule under it; the family's band, so every expanded title bar matches |
| `BTN` | 1.1 | 13 | collapse-button box; the name field stops short of it |
| `NAME_GAP` | 0.5 | 6 | title-band rule → first section header |
| `SECT_GAP` | 0.75 | 9 | space above a section header |
| `RULE_GAP` | 0.2 | 2 | section header bottom → rule top |
| `ROWS_GAP` | 0.4 | 5 | rule → first stat row |
| `ICO` | 2.4 | 29 | perk icon box (six across: `6·ICO + 5·ICO_GAP` ≤ `W − 2·PAD` at every FS — 194 of 257 at FS 12, and the margin holds at both ends of the 8–48 range) — the icon itself is inset 1px and scaled to `ICO − 2`, inside the border |
| `ICO_GAP` | 0.35 | 4 | gap between perk boxes |
| `COLA` | 5.5 | 66 | a PvP section's first value column → its second (its column titles sit on the same pitch) |
| `TAB_W` | 2.4 | 29 | the PvP glyph's box; the name field stops short of it on a player |
| `TIP_PAD` | 0.3 | 4 | perk-name chip: padding on all four sides, and its gap above the icon row |
| `LEAD` | 0.15 | 2 | `TextFormat.leading`, applied to every field |
| `COLL_W` | 15.8 | 190 | collapsed bar width — the stopwatch derives its own `W` from the same ratio |
| `COLL_H` | 2.0 | 24 | collapsed bar height — likewise its `H_COLLAPSED` |
| `COLL_PAD` | 0.55 | 7 | collapsed bar padding |
| `W` | 2·`PAD` + `LABEL_W` + `COL_GAP` + `VALUE_W` | 277 | total footprint — derived, never fixed |

`W` measures the outer black frame; both 1px frames sit inside it. Rules run from `x = PAD` to `W − PAD` — one under the title band (expanded only; collapsed the bar *is* the title line), one under each visible group header and one under the Perks header, replayed on collapse from the last layout pass. Every group has a header field, a label column and a value column (a PvP section a second value column and its column titles), each a single left-aligned multiline `TextField` sharing one `TextFormat`, so rows stay baseline-aligned. The perk boxes are 1px outlines in their pair's `PERK_EDGE` colour over its `PERK_FILL` plate, drawn once at create.

Hovering a filled perk box names it: a chip in label grey (`0xC8C0B0`) on the plate colour at **alpha 100** — the one opaque surface in the panel, since it lands on top of the icons and the Perks rule — with the usual 1px inner-frame (`0x4A3B22`) border, drawn at the top depth of the panel clip, centred over its icon and clamped inside `[PAD, W − PAD]` so the end slots don't hang off the frame. The name comes from `PERK_NAMES`, a rank-indexed baked table (the icon instance doesn't identify the perk, and no name field is confirmed on an effect entry), so `placePerks` returns `{inst, rank}` and the ranks join the `renderPerks` cache key — two perks can share an icon, and the chip must not name the one that left.

**The hover source is a `Mouse` listener, not `onRollOver` on the slots.** Rollover handlers put a clip in button mode, and the perk row — 6·`ICO` + 5·`ICO_GAP`, 194px at FS 12 — would then swallow left clicks, the same reason no part of the plate takes a press but the fold and PvP glyphs. `hoverTick` instead hit-tests arithmetically in panel space (`panelClip._xmouse/_ymouse` against the known `PAD` + `i`·(`ICO` + `ICO_GAP`) pitch, rejecting the gaps between boxes), so nothing in the row is interactive and the test holds wherever `rootClip` sits. The chip redraws only on a slot change, and hides on collapse, on hide, on a row change, and on `clearPerkSlots`.

This is the one thing in the panel that runs at mouse-move frequency — continuously while the camera is dragged in combat — so it is ordered to cost as little as possible when there is nothing to name: the listener exists only while the perk row is on screen (`listen()`: row shown, panel visible, not folded, not in preview), the row top comes from `perkRowY`, stamped by `layout()`, rather than off the slot clip, the pointer's x is read only once its y is inside the row's band, and `hideTip()` returns on `tipSlot < 0` instead of rewriting `_visible` on every move.

**Collapsed is a different plate, not the sheet at a shorter height.** The panel folds to a bar reading just `Inspect` — `COLL_W` × `COLL_H` (190 × 24 at FS 12). The stopwatch and the console build their own plates from the same two ratios rather than from copied constants, so all the collapsed bars are identical at *every* baked body size, not only at the default 12 — and every panel's body size is the one overlay size times its own Size, so equal Sizes sit together in a HUD without any per-dialog matching up. Folding hides the name strip and shows `collTF` in its place, and the collapse button moves onto whichever plate is on screen (`applyCollapsed`, which renders from the effective fold state — preview is the full sheet either way). Nothing on the bar tracks the target, which is what lets a collapsed pass read two ids (§1).

Position mirrors the grids and the cast timer, not the stopwatch: this is a HUD element, mouse-transparent in normal play, so it is repositioned only in preview mode, by the shared overlay (`KazBarsPreview.attach`) that covers the whole plate and lets the user drag it (there is no coordinate readout; the dialog's X/Y only seed a first session). Baked X/Y and `startCollapsed` seed the first-ever session; from then on the game persists drag position and folded state in the module config archive under `inx` / `iny` / `inc`, with the picked tab (`inp`) and the master switch (`inv`), for every user (the permanent declarations in `game_persistence`). `loadState` reads `inc` **first** and only then seats `inx`/`iny` (`seat`, clamped against the plate on screen — the bar when folded, else the taller view's footprint `footH`): clamping a sheet against the collapsed bar's height let a saved spot near the bottom edge hang off screen; the spot is seated again when the Stage resizes. In normal play the panel's only interactive surfaces are the − / + button, the PvP glyph and the perk hover — a whole-plate drag would eat combat clicks, and the collapsed bar no longer opens on a plain press (it had that only while it carried a drag strip; the + button is the expand affordance). The overlay covers both surfaces while preview is on, which is intended: preview is for placing the panel, nothing else.

The preview control panel (`stubs/KazBarsPreviewPanel.as`) joins the family — same plate, double frame, orange title ("KazBars Preview"), bronze rules under the title band, under the All/None pair and above the footer (none between groups) — every dimension `Math.round(FS × ratio)` off the overlay base size itself (`d.PF.fontSize`, delivered by an unconditional `ppanel.configure(d.PF)`, which also hands `KazBarsPreview` its size and face); it has no `scale` of its own and seeds itself at 12 from its own constructor (a null config is taken as empty rather than bailed on, so a build that never configures it still renders). Its rows sit under three clickable section headers — Player Grids, Target Grids, Tools (`makeHeader`: bold Small role in `0xC8C0B0`, orange `0xF7A22B` on hover; a click toggles the whole group via `toggleGroup`, an empty group emits no header), and a dim word-wrapped three-line footer (`buildFooter`: Small role, `0x999999` — exit keybind, Build & Install + `/reloadui` recipe, version credit from `d.PF.version`) sits under its own hairline. It is the one panel whose footprint grows with content — one row per screen grid, groups packed into columns whole at `MAX_PER_COL` (16) items (headers count, a mid-column header gets `HDR_GAP = round(FS × 0.4)` above it, an oversized group splits under a "(cont.)" header), the footer measured for real inside the fit loop (`fitPass`) — so `show()` steps its own size down until the plate fits the Stage (floor 8) rather than the shared range being cut for everyone: `configure` keeps what it was given in `FS_REQ`, `applySize` does the ratio block, and `measure` is the one place a column/row count becomes a width and a height. Rows are rebuilt on every preview entry, so the clamp is self-correcting and can never strand a user with a panel they cannot reach. It does not fold: it exists only while preview mode is on, and a panel whose whole job is showing what is hidden gains nothing by hiding itself, so the entire title band is the drag hitbox and there is no collapse glyph to leave room for; drag and `clampPos` persistence (`ppx`/`ppy`) are the family's. A row is that item's master switch, not a preview-only hide: it is seeded from live state on entry and persists past the exit. The panel owns none of that state — it calls back into the owner, which routes each key to the module's own `setActive`, and the flag persists per item rather than per panel.

---

## 6. Known-unreadable

Do not spend another session chasing these through stat space:

- **Weapon base DPS** and the **equipped weapon type** (its family is readable, §3) — hence the school-CR heuristic and the absence of a sheet-DPS line. An item-tooltip API route exists but is untested.
- **The attributes' direct "+N DPS with weapons" grant** — reads live (mode-2) attributes and moves the sheet's DPS without touching CR, but its per-point rate was never measured and attribute tooltips are unreachable for targets. Together with the unreadable weapon base DPS this is why the panel has no DPS line — the Weapon Damage % pair is the readable part of that formula and is shown instead.
- **Attribute modes other than 2** — modes 0 and 3–7 return the raw template 10 on live players. Mode 1 is the pre-multiplier layer — it looked like a mirror of mode 2 until a %-multiplier subject split them — and the panel does not read it (§3).
- **The sheet's absolutes** — armor, protection, CDI and spell damage have no id; they are synthesized (§3).
- **The critical-damage feat/AA base** beyond the flat id 710 (§3).
- **Absorb-shield pool amounts** and **crowd-control resistance %** (buff presence only).
- **XP and PvP XP.**
- **Hover targeting** — the panel is target-driven because that is the only signal available.

---

## 7. Deliberately not shipped

Researched and understood, but outside the current panel. Recorded so the groundwork is not repeated:

- **Debuff readout.** `GetStat(id, 0)` returns the naked base on players and the **undebuffed spawn template on NPCs**, so `m2 − m0` isolates a live debuff total in two reads — the basis for a `[base N, dbf −N]` readout of Torment / Wrack / Ruin stacks on a boss. The panel polls mode 2 only.
- **The trailing previous-health mirror** (id 11).
- **Poison invulnerability** (909) — the panel folds poison into the armor line.
- **The 902 / 903 / 904 trio.** The set is confirmed as slash/pierce/crush but the order has never been split, because all three have read tied on every subject sampled. The panel reads 902 for the armor line; if they ever diverge, that is the line to revisit.

## 8. Open questions

- **Floor vs round** on the `attr / 2` term in the protection total is indistinguishable at even attribute values; the stub floors.
- **Tournament season wins.** The season id (1389) follows the sheet's layout; no season win has been measured yet.
- **Ferocity rounding.** The 0.15 slope is a single sheet pair (260 → 39.0%); its rounding at odd totals is unmeasured.

---

## 9. Verification

There is no automated coverage of the rendered panel — the AS2/SWF runtime is not unit-testable. Verify by build and manual QA in-game:

1. **Untargeted** — the panel is invisible; in preview it shows the full footprint (the taller of the two views, the picked groups and the Perks row), with empty values and empty perk boxes, and drags by the overlay.
2. **Player target** — the PvP glyph appears in the title strip and swaps the sheet for the PvP view (and back); armor and the five protections match the target's sheet digit for digit, PvP values differ from PvE by the 454/458 gaps. The title reads `Name Class (80/N)` — every class maps — and drops `/N` on a PvP-level-0 character. The Perks row shows the target's perk-buff icons — verify the set against a character whose slotted perks are known (self-target first), and that a retarget swaps the icons with no leftovers.
    - **Slot pairs** — each perk sits in its own colour pair (blue General, red Archetype, dark Class); an icon in the wrong pair means a `PERK_IDS` rank has drifted across a `PERK_GEN_MAX` / `PERK_ARCH_MAX` boundary.
    - **Two-slot perks** — a character running one of the 36 two-slot class perks shows its icon in *both* dark boxes, matching the game's bar; one running two ordinary class perks shows two different icons.
    - **Icon fit** — icons sit inside their borders at every font size, not overflowing them (the failure mode is a load-target scale being overwritten by `onLoadInit`).
3. **Mob target** — no PvP glyph and no Perks row, no attributes, so Heal Rating, Bonus Spell Damage and Ferocity dash and the armor line falls back to the raw gear component. The title carries no class and no PvP level — `Name (83)`. With the PvP tab picked, the sheet still shows.
    - **Row picks** — build with a Custom list (say only Defensive rows, plus a PvP Stats row) and confirm only those groups draw, in the order picked, and that the PvP Stats row shows on a player and not on a mob.
4. **City guard or other attribute-carrying NPC** — still no PvP glyph and no Perks row. This is the case the decoded-attribute gate exists for.
5. **Boss target** — template stats and critigation read, tenacity dashes; a mitigation-phase change moves the protection percentages mid-fight via id 911.
6. **Weapon family** — Combat Rating on a player with a two-hander, with a one-hander, and with no main hand: the school term follows the family (§3), and it settles within a few seconds of targeting.
7. **Off-80 target** — percentages render identically to a level-80 target (36.6/73.7/219.6 confirmed level-invariant across 1–86); no raw-only fallback.
8. **Retarget rapidly** — no flash of the previous target's numbers (the warm-up), and re-targeting the same entity does not blank the sheet.
9. **Zone or log out with the panel open** — it clears rather than freezing on a stale sheet or re-showing an all-dash phantom.
10. **Collapse and re-open** — the − button folds the panel to the `Inspect` bar; it should measure the stopwatch's collapsed bar at FS 12 and carry no target name. The + button re-opens the full sheet *immediately* — no quarter-second of stale numbers, which is the collapsed pass's two-id diet showing through if it regresses. A plain press on the bar does nothing (intended: the bar is not a button any more), and clicking the name strip expanded does nothing either. Entering preview while folded must show the sheet with live values, not dashes — the same two-id diet, seen from the other side.
11. **Relog** — drag position, collapsed state and the picked tab survive it; the baked X/Y and `startCollapsed` are only what a first-ever session starts from.
12. **Drop the target while preview is on** — the sheet blanks (name and both value columns) instead of keeping the last target’s numbers under the overlay; retargeting refills it after the warm-up. Same check with a one-column grid on screen: its rotated name must still read along the bar.
