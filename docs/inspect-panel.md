# Target inspect panel — stat reference

What the `KazBarsInspect` stub reads, and why every constant in it is the number it is. Update when the watch list, a synthesis formula, or a display gate changes — the stub carries the rules as comments, this doc carries the reasoning and the id table behind them.

The panel is an optional in-game overlay (Extras ▸ Inspect panel…) that renders a combat sheet for the current target in the visual language of the game's own inspect window. It is off by default; when off the build emits zero references and MTASC skips the stub entirely.

| Piece | Where |
|---|---|
| Runtime (AS2, logic + chrome overrides) | `src/kazbars/assets/kazbars/stubs/KazBarsInspect.as` (chrome/collapse primitives from `KazBarsPanel.as`; the preview overlay it is dragged by from `KazBarsPreview.as`) |
| Baked tables (perk pool, names, class map, watch list) | `src/kazbars/assets/kazbars/stubs/KazBarsInspectData.as` — static `init()` |
| Config layer (pure, no Tk) | `src/kazbars/inspect.py` — `validate_config()` |
| Settings dialog | `src/kazbars/inspect_panel.py` — `open_inspect_dialog()` |
| Build gate | `src/kazbars/grids_generator.py` — `include_inspect`, emits the `d.INS` block |
| Config flow | [`flows.md`](flows.md) → flow 26 · build gating → flow 1, steps 9–11 |
| Module wiring | [`architecture.md`](architecture.md) → Build pipeline |

Nothing here is unit-testable — `tests/test_inspect.py` covers the config layer, `tests/test_grids_generator.py` the on/off codegen contract, and `tests/test_build_compile.py` a real MTASC compile of the stub, but the numbers below only prove themselves against the live game sheet. See **Verification** at the bottom.

---

## 1. Reading rules

These are measured engine behaviour, not style choices. Changing any of them changes what the panel shows.

- **Read with `GetStat(id, 2)`.** Mode 2 is the live effective value. One exception: the CDI attribute term additionally reads 804/814 at **mode 1** — the pre-%-multiplier attribute sum (a ×1.05 Dex feat moved mode 2 by an item's 97×1.05 while mode 1 moved by the flat 97), which is the basis the sheet's Rating-from-attribute uses. The spell-damage attribute term stays mode 2 — both verified against sheets.
- **Poll; do not trust signals.** A full watch-list pass runs every 250 ms on a `setInterval`. `SignalStatChanged` is not usable as the data path here: gear and rating ids never fire it at all, signal-time reads race the server, and equips with no stat lines emit nothing. The poll *is* the settle re-read, and the assign-on-change string cache in `render()` subsumes any dirty flag — most passes change nothing, and `TextField.text` writes are the expensive part.
- **The pass only pays for what is on screen.** The panel shares one AVM1 sandbox with the grids, the cast timer and the stopwatch, so a pass does no work it cannot show. Collapsed the panel is a static label (§5), so a pass reads `gateIds` — the teardown gate's two ids — instead of the 63, and skips the mode-1 side-reads, the buff-list walk, the player gate and all value building; expanding runs one full pass immediately, so the sheet is never stale. The buff-list walk is player-only in the same spirit — the AA correction feeds an attribute term that is zero without attributes, and the Perks row is player-gated, so bosses (the longest buff lists in the game) are never walked. Stat values are cached under the raw id and the player gate is settled once per pass into `subjPlayer`, because a full render asks `gv()` ~195 times and asks the gate six. A perk buff's icon instance is read once per id per session into `iconInst` rather than per pass — it is static game data.
- **Warm up 3 passes (~750 ms)** before the panel is allowed to show. Login, zone changes and retargets all repopulate stats over roughly that window; without the warm-up a retarget flashes the previous target's values.
- **Teardown gate.** Logout and zoning collapse every id to 0 in one burst. Id 1 (max HP) and id 54 (level) reading 0 *together* is that burst, not data. On detecting it the stub drops the subject handle outright — keeping the dead handle lets the warm-up count three null passes and re-show a phantom all-dash sheet.
- **Subject resolution.** `Character.GetCharacter(tid)` first, falling back to `Dynel.GetDynel(tid)` so destructibles and simple dynels still read (stats yes, buffs no). This is why a minimal `Dynel` intrinsic sits in `src/kazbars/assets/common_stubs/com/GameInterface/Game/`. Identity key is `GetID().GetType() + ":" + GetInstance()`; re-targeting the same entity keeps the warm cache instead of restarting the warm-up.
- **Visibility is per subject.** A neutral player exposes most of the combat sheet; a hostile player additionally exposes the PvP cluster; mobs expose no attributes, so every attribute-fed synthesis collapses to a dash by design; bosses expose template stats plus critigation.
- **Rounding.** The game sheet *rounds* fractional internals, `GetStat` *floors* them. A ±1 disagreement with the sheet is the display surface, not a wrong formula. Health percent (id 525) is shown verbatim for the same reason — the panel never computes it.

---

## 2. The watch list

63 ids, polled every pass while the panel is open, in the order they appear in `watchIds` (collapsed, only `titleIds` is read — §1). `curV[id]` holds the last settled value; `gv(id)` returns 0 for absent, null or NaN.

### Vitals & identity

| id | meaning | notes |
|---|---|---|
| 1 | Max HP | half of the teardown gate |
| 27 | Current HP | |
| 525 | HP % | displayed verbatim — the game floors it |
| 54 | Level | the level-80 gate for every percent decode; other half of the teardown gate; feeds the title |
| 67 | Class id | 34 (dagger class) and 39 (Ranger) select Dex over Str for CDI — both named by the sheet's own tooltip; 34 alone gets the 5.0 crit base (Ranger sheet-verified on 2.5). Also feeds the title's class name via the measured table 18 Barbarian · 20 Guardian · 22 Conqueror · 24 Priest of Mitra · 28 Tempest of Set · 29 Bear Shaman · 31 Dark Templar · 34 Assassin · 39 Ranger · 41 Necromancer · 43 Herald of Xotli · 44 Demonologist — all twelve measured off live targets |
| 70 | PvP level | raw; sheet-exact on five characters; feeds the title only |
| 507 | Max Mana | gates the Bonus Spell Damage lines only — mana-less classes sheet the whole per-school block at 0 |

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
| 713 | Heal Rating | gear-sourced; NPCs never carry it |
| 804 / 808 / 810 / 814 | Strength / Intelligence / Wisdom / Dexterity | ×10+10 encoded; 804/814 additionally read at mode 1 for the CDI attr term (§1, §3) |
| 1403 | Ferocity | ×10 encoded; `floor(1403/10)` **is** the sheet value — verified exact both loaded (2600 → sheet 260) and empty (0 → sheet 0, on a character whose old base-candidate id still read 33; that id, 864, is the engine's "Player Flags" state slot and feeds nothing) |
| 875 | Untyped Combat Rating | CDI input |
| 866–873 | Per-weapon-school Combat Rating | 1HE, 2HE, 1HB, 2HB, dagger, polearm, bow, crossbow |
| 162 | Cold Combat Rating | CDI input |
| 1007–1010 | Fire / Electrical / Holy / Unholy Combat Rating | CDI inputs |
| 1095 / 1096 | Weapon Damage % (Melee / Ranged), ×100 | shown verbatim as a percent pair — no synthesis, no gates; stance and proc swings and multiplicative feats (Reave-type) are already inside the values. Dashed only when both are absent |
| 861 | Untyped Magic Damage | applies to every school |
| 158 / 876 / 877 / 878 / 879 | Cold / Fire / Electrical / Holy / Unholy Magic Damage | per-school component on top of 861 |
| 1041 | Base Spell Damage % | added **flat**, not as a percent |

Cold is the low-range outlier in every school family — 157 protection, 162 combat rating, 167 invulnerability, 158 magic damage — while the other four cluster. Expect that shape when adding a school-keyed id.

### Extended block

| id | meaning |
|---|---|
| 1000016 | Critigation Chance rating |
| 1000017 | Tenacity rating |
| 1000018 | Critigation Amount rating |

Tenacity comes from PvP gear only; bosses never carry it.

### Slotted perks (buff ids, not stats)

Not part of the watch list — these come off the subject's buff list on the same pass that finds the AA. `PERK_IDS` maps **113 perks over 114 ids**, one rank each, in id order — almost all of them in the span **4279889–4282396**.

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

**4279994 is in this table *and* is `AA_BUFF_ID`** — "Immeasurable Empowerment", the +100-all-attributes passive whose CDI contribution is bugged (§3), is itself a slotted General perk. The poll sets the AA flag and records the perk from the same buff-list entry.

**Two traps.** Most perks carry the placeholder description `No description given.`, but that is a *heuristic, not a rule*: `Prelate at Arms` (4280100, "team propagated container") and `Empowered Vitality` (4280968, "Increases Con by 2-10%") are real perks with real descriptions, and a descless-only sweep silently drops them. And the id span reaches **below** 4280000 — six General perks live at 4279889–4279997. A third-party overlay filters its own perk readout with `4279999 < m_BuffId < 4290000`, which is what first located the band, but that bound misses those six at the bottom and sweeps in ~200 NPC abilities at the top; enumerating is what avoids painting boss debuffs as perks.

Excluded from the band as non-perks: the potion-effect family, `Ethereal Lash` (a stacking-debuff family), `Bestial Endurance` (inside the grey-ape NPC run), the `Stygian Halfbreed` / `Tarpani Stallion` mounts, `Perkspell Test`, and the whole 4286xxx cluster (`Alignment of the Stars`, `Shadow of the Moon`, `Arc of the Sun`, `Reading the Heavens` and their II/III variants) — that last one sits among potion effects and megalith markers, and the General pool is confirmed full at 9 without it. **Candidates, not rejects:** `Taste of Blood` (4285065) and `Smoldering Strike` (4285069), plus the 4286xxx name-twins of the Barbarian perks `At the Gates` and `What it Takes`.

### PvP

| id | meaning | notes |
|---|---|---|
| 454 | PvP armor gap | added to the PvE total; can be negative |
| 458 | PvP protection gap | one value, applies to all five schools; can be negative |
| 225 | PvP Combat Rating | added to the CDI rating on the PvP line; moves mid-combat on procs and can rest negative |
| 226 | PvP spell-damage gap | sheet label "PvP Bonus Spell Damage"; one value, applies to all schools (the 458 shape); per-item accumulator, can rest negative; added to the spell-damage total on the PvP line |
| 656 / 658 | Kills / Deaths | `0 / 0` is real data, printed rather than dashed |

---

## 3. Syntheses & constants

Every constant below is a **level-80** figure. They are believed level-proportional but that has never been verified off-80, which is the entire reason for the level gate in §4.

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

CDI rating     = 3 × (Dex for classes 34/39, Str otherwise)
                 + 875 + gearSchoolCR + 162 + 1007 + 1008 + 1009 + 1010
CDI effect     = round(rating / 36.6)
PvP CDI rating = CDI rating + 225

PvP Armor      = Armor + 454        ·  PvP Prot(school) = Prot(school) + 458
PvP Spell Dmg  = Bonus Spell Dmg total + 226
```

`gearSchoolCR` is `max(866…873)`. The equipped weapon type is **not** readable — weapon-set swaps leave the equip bits invariant — but characters stack their own school's combat rating, so the largest component is it. This is a documented heuristic, not a measurement — though the game's own CDI tooltip named the max component as the weapon school on the one character cross-checked.

**The composition is the sheet's own, verified digit-exact from the game's itemized CDI tooltip on two characters across multiple gear/buff states.** The attribute term is `3 × (mode-1 attr − 100 if Immeasurable Empowerment)`:

- **Mode 1** is the pre-%-multiplier attribute sum — attribute-percent feats/AAs (a ×1.05 Dex feat measured; the Reave weapon-damage feat is the registry precedent) scale mode 2 but not the sheet's Rating-from-attribute, and mode 1 is exactly that basis.
- The **+100-all-attributes AA passive** ("Immeasurable Empowerment", buff id 4279994) is bugged in-game: its attributes land in mode 1 yet never feed this rating, while its Wisdom *does* feed spell damage. The panel mirrors the bug by detecting the buff (confirmed visible on self-targets and other players) and subtracting the 100; an invisible list degrades to +300 high.
- Flat attribute buffs other than the AA land in mode 1 and still inflate the term — the accepted residual. The +225 PvP delta is exact regardless.

When a subject exposes no Strength (`attrSheet(804) == 0`, i.e. every mob), the armor line falls back to the raw gear component 448 rather than a total built on a missing term.

### Critical chance

```
chance% = rating(312) / 36.6 + weaponBase
weaponBase = 5.0 for class 34 (daggers) · 2.5 otherwise
```

### Critical damage

Rating share only: `pctOf(711)`. The sheet adds a per-character feat/AA base that is **absent from stat space** and is not class-keyed, so inventing a constant would inflate the line for everyone who does not have it.

### Heal Rating

```
Celestial Gaze = 271 + HR × 0.2761   …   292 + HR × 0.2761
```

Heal Rating benefits specific heals only and has no percent form, so the panel shows the Celestial Gaze range it buys — the main beneficiary. Source: the community AA-heal table (joharaoc.eu/aaheal), not a direct measurement; the healing sheet absolute is not exposed as a stat, so the rating is the only input. Player-only.

### Bonus Spell Damage

```
total = 861 + max(158, 876, 877, 878, 879) + round(0.6 × max(Int, Wis)) + 1041
```

Only the highest school shows — a caster stacks exactly one. `max(Int, Wis)` avoids an unmeasured class table (priests lead on Wisdom, mages on Intelligence), the same shape as the school-CR heuristic above. The 1041 term is added flat despite its "Base Spell Damage %" label — read as a percent of the total it lands nowhere near the sheet. Player-only, level-80-only, and **mana-gated**: a mana-less class (Ranger measured — max mana 0, sheet block all zeros despite 861/1041 residue in stat space; Barbarian predicted) dashes rather than synthesize a number the sheet contradicts.

The PvP row adds the per-school gap 226 flat on top of the same total — the composition every other PvP row uses (+454, +458, +225), and it is **sheet-verified on two characters**: a Tempest of Set with 226 = −186 read exactly `total + 226` on the school-carrying line (985) with the school-less lines ±1 (the fractional attr term's rounding surface), and a Bear Shaman with 226 = −250 sheeted −71 against a composed −72 — the sheet's PvP per-school block is absolutes, not gaps, and renders negative faithfully.

### Ferocity

```
total = floor(1403 / 10)      ·      effect% = 0.15 × total
```

Verified exact at both ends: a loaded character (1403 = 2600 → sheet 260) and an empty one (1403 = 0 → sheet Ferocity 0, even though the one-time base candidate id 864 still read 33 there — 864 is the engine's "Player Flags" state slot and feeds nothing). The 0.15 slope rests on a **single sheet pair** (260 → +39.0% on all five AOE surfaces — radius, max targets, cone angle, column distance, splash amount; the sheet shows one uniform percent). Player-only.

### Attribution

The mitigation curve and the 36.6 / 73.7 / 219.6 divisors originate in community formula work (the 2016 Age of Conan formula thread) and were re-verified digit-for-digit against the in-game sheet before shipping. The heal decode is community-table-sourced as noted. Everything else — the totals, the fold, the CDI composition, the spell-damage composition, the class-id table and the PvP gaps — was derived here against the sheet.

---

## 4. Display rules & gates

- **Dash, never drop.** Absent data renders as an em dash (`String.fromCharCode(8212)`) inside the value field. Row counts never change, so `layout()` re-runs only on a section-visibility flip (PvP block / Perks row).
- **Title line** is `Name Class (Level/PvP level)` — e.g. `Kazour Bear Shaman (80/10)`. The class name appends only when the PvP gate below agrees the subject is a player **and** id 67 maps (all twelve classes measured; an unmapped id would mean a patch moved the enum and simply omits the class); the level part drops absent components, so a mob reads `Name (83)` and a player with no PvP level `Name Class (80)`. Built per pass from polled stats and cached assign-on-change like the value columns; an overlong name + class combination clips at the name field's fixed width.
- **Level gate.** Every percent decode is suppressed unless `GetStat(54, 2) == 80`. An off-80 target shows the raw rating with no parenthetical — the constants are level-80 measurements and applying them to a level-40 target would produce a confident wrong number.
- **Line format** is `Rating (Effect%)`, matching the game's own combat-stats tab. The CDI synthesis is labeled **Combat Rating** on both sections; this doc keeps CDI as the synthesis name.
- **Section toggles are baked.** The dialog's "Show the PvP section" and "Track slotted perks" checkbuttons bake `showPvp` / `showPerks` into the config block (both default on; absent keys read as on in `configure()`, so an old baked config keeps today's footprint). Off means the section never renders, previews included — changing either takes a Build & Install like every other baked value.
- **PvP block gating.** Behind the `showPvp` gate, shown only when the engine's `ID32.IsPlayer()` **and** a decoded attribute spread both agree:

  ```
  hasAttrs = any of attrSheet(804/808/810/814) > 4
  isPlayer = (subjIsPlayer >= 0) ? (subjIsPlayer == 1 && hasAttrs) : hasAttrs
  ```

  `IsPlayer()` is measured truthful on players but has never been sampled on a mob, so it **vetoes** rather than confirms alone; `subjIsPlayer == -1` means it never answered and the attribute spread carries the decision. The attribute half must be *decoded* — testing raw presence put a PvP block on city guards, because an NPC template at base attributes reads raw 10.
- **Player-only lines** — Heal Rating, Bonus Spell Damage and Ferocity — dash on any non-player subject.
- **Perks row** (`showPerks`, player-gated like the PvP block). The poll's buff-list walk — the same pass that finds the AA — collects every id present in `PERK_IDS` ("i\<buffId\>" → display rank). The six boxes mirror the game's own perk bar: **three fixed, colour-coded pairs** — General, Archetype, Class — so a perk drops into its own pair rather than filling left to right, and a colour never lies about what it is holding. `PERK_IDS` is ordered General → the four archetypes → the twelve classes, so the two rank boundaries `PERK_GEN_MAX` (8) and `PERK_ARCH_MAX` (28) are the whole category test. A pair holds two; anything beyond is dropped rather than spilling into the next category's colour. Slot state is the icon instance with **−1 for empty** — 0 is a real value, since a perk whose buff carries no icon still holds its slot.

  **Two-slot perks** (the game calls them Major Perks). Three of every class's seven cost both class slots — 36 in all, listed in `PERK_2SLOT` and keyed by rank, which is what `placePerks()` already carries. Such a perk paints its icon across *both* class boxes, the way the game draws it, so a character running one shows six icons rather than five. It claims the pair only when both boxes are free; otherwise it takes the second like any other perk. None of General or Archetype is two-slot. The marked-up source list is `gamedata/perks.md` (local-only).

  **One request per distinct instance, one clip per answer.** `RequestRDBImage` answers a given id **once** — a second request for an id already in flight never calls back. Two boxes showing the same icon (exactly the two-slot case) therefore cannot each ask for it up front — and the single answer must not be `loadClip`-ed into both boxes in the same tick either: the two binds share one movie definition, the retarget unload releases it twice, and the resulting heap corruption crashed the client an inspection or two later (isolated in-game with a serve-one-slot probe build). `renderPerks()` runs in two passes — settle every slot's target instance and drop stale art first, then issue one request per distinct instance, deduplicating only against instances requested *on that same pass* (a slot that kept its art issued no request, so it cannot serve a partner that has just come to want the same instance); a deduplicated partner keeps its `_want` mark as *pending*. `onPerkIcon()` loads the answer into the requesting slot only, then chains the partner: the answer just took the id out of flight, so it re-issues the request for the first slot still pending on that instance, and that slot's own callback paints it a beat later. Icons are the game's own, loaded from the buff's `m_Icon.GetInstance()` via `ImageLoader.RequestRDBImage(1010008, …)` — the grids' icon path. Each slot nests three clips on purpose: the box outline draws on the unscaled slot, a `hold` child carries the scale, and the icon loads into `hold.m_icon`. `loadClip` **replaces** its target clip and `onLoadInit` then normalizes the arrival to 64×64, so any scale set on the load target itself is overwritten — the scale has to live on the parent, or icons render at 64px and overflow the box. An empty box is the row's em dash. Rank-variant duplicates of one perk collapse to the first seen; the render is assign-on-change keyed on the joined `rank:icon` string, and only slots whose icon changed reload. Presence semantics: a passive perk shows while slotted, an active one only while its buff runs, and a granted group-perk buff (the Enchanter shape) lands on the *receiver* — the row reads "perk buffs on this player", not "perks this player slotted".
- **Preview** (`previewOn()`) shows the full-footprint sheet including whichever of the PvP block and Perks row the baked gates allow — the footprint being positioned, not the one this target happens to earn — and its content is live-or-empty: a target with a settled read renders normally under the overlay, perks included, and a retarget mid-preview follows; untargeted, the chrome and labels show with empty values. It renders from an *effective* fold state (`collapsed && !previewMode`), so a folded panel shows its sheet at the bar's own top-left spot without the flag being touched; `pollTick`'s watch-list choice and `render()`'s early return use the same predicate, and entering preview takes a full pass at once, or a folded panel would show a full-size plate of dashes. `previewOff()` detaches the overlay, re-applies the real fold state and clears the render cache. Every sheet is behind the master switch (`active`, persisted as `inv`): it is `&&`-ed into `updateVisibility`'s one gate, and an inactive panel returns from `pollTick` before touching the watch list. Preview does not override it — an unchecked panel stays dark in preview too, and the control-panel row that re-checks it calls `setActive(true)`, which re-runs the gate against the `previewMode` `previewOn()` already set.

---

## 5. Visual contract

The panel mirrors the game's default inspect window: near-black warm plate, 1px black-over-bronze frame, Conan-orange headers with hairline rules, parchment-grey labels, sheet-green values. Arial only — `embedFonts = false`, resolving against the faces already embedded in `base.swf`, so the panel needs no new symbols. Colours are written inline at their draw sites — the family base's `drawChrome()`, `hairline()` and `makeTF()` in `KazBarsPanel.as` plus the stub's own fields — not held in named constants:

| Color | Value | Role |
|---|---|---|
| header | `0xF7A22B` | name strip + PvE/PvP section headers (bold) |
| label | `0xC8C0B0` | stat labels |
| value | `0x7AC142` | stat values, including the em-dash fallback |
| rule | `0x6B5324` | 1px rule under each section header — the family's `hairline()`, that colour's sole owner |
| plate | `0x0C0A07` @ alpha 90 | plate fill |
| inner frame | `0x4A3B22` | 1px inner frame |
| outer frame | `0x000000` | 1px outer frame |

The perk row is the one place the panel departs from that palette, mirroring the game's perk bar instead — each slot pair carries its own border and plate, and the pairing *is* the category legend:

| pair | slots | border (`PERK_EDGE`) | plate (`PERK_FILL`) |
|---|---|---|---|
| General | 0–1 | `0x4A7FA5` blue | `0x0F1C26` |
| Archetype | 2–3 | `0xA34A4A` red | `0x260F0F` |
| Class | 4–5 | `0x555555` grey | `0x151515` |

Every dimension is `Math.round(FS × ratio)`, so the whole panel scales as one piece from the baked size. That size is the shared `panel_font_size` (prefs.json, 8–48, default 12) unless `inspect.fontSize` carries a number of its own; the two collapse into one baked number in `grids_generator._resolved_font_size` and nowhere else. The console and the control panel always take the shared value — they have no dialog to override it from:

| Constant | Ratio | @ FS 12 | Role |
|---|---|---|---|
| `PAD` | 0.85 | 10 | plate padding, all four sides |
| `LABEL_W` | 8.6 | 103 | label column (fits "Critigation Chance") |
| `COL_GAP` | 0.85 | 10 | label column → value column |
| `VALUE_W` | 12.0 | 144 | value column (fits a boss health line) |
| `NAME_FS` | 1.15 | 14 | name header font size |
| `TITLE_H` | 1.85 | 22 | title band — name left-aligned and vertically centred in it, hairline rule under it; the stopwatch's own band ratio, so the family's expanded title bars match |
| `BTN` | 1.1 | 13 | collapse-button box; the name field stops short of it |
| `NAME_GAP` | 0.5 | 6 | title-band rule → first section header |
| `SECT_GAP` | 0.75 | 9 | space above a section header |
| `RULE_GAP` | 0.2 | 2 | section header bottom → rule top |
| `ROWS_GAP` | 0.4 | 5 | rule → first stat row |
| `ICO` | 2.4 | 29 | perk icon box (six across: `6·ICO + 5·ICO_GAP` ≤ `W − 2·PAD` at every FS — 194 of 257 at FS 12, and the margin holds at both ends of the 8–48 range) — the icon itself is inset 1px and scaled to `ICO − 2`, inside the border |
| `ICO_GAP` | 0.35 | 4 | gap between perk boxes |
| `TIP_PAD` | 0.3 | 4 | perk-name chip: padding on all four sides, and its gap above the icon row |
| `LEAD` | 0.15 | 2 | `TextFormat.leading`, applied to every field |
| `COLL_W` | 15.8 | 190 | collapsed bar width — the stopwatch derives its own `W` from the same ratio |
| `COLL_H` | 2.0 | 24 | collapsed bar height — likewise its `H_COLLAPSED` |
| `COLL_PAD` | 0.55 | 7 | collapsed bar padding |
| `W` | 2·`PAD` + `LABEL_W` + `COL_GAP` + `VALUE_W` | 277 | total footprint — derived, never fixed |

`W` measures the outer black frame; both 1px frames sit inside it. Rules run from `x = PAD` to `W − PAD` — one under the title band (expanded only; collapsed the bar *is* the title line) plus one per visible section header, so up to four (title / PvE / PvP / Perks), the section three replayed on collapse from the last layout pass. Both columns are single left-aligned multiline `TextField`s sharing one `TextFormat`, so rows stay baseline-aligned; headers are their own bold fields. The perk boxes are 1px outlines in their pair's `PERK_EDGE` colour over its `PERK_FILL` plate, drawn once at create.

Hovering a filled perk box names it: a chip in label grey (`0xC8C0B0`) on the plate colour at **alpha 100** — the one opaque surface in the panel, since it lands on top of the icons and the Perks rule — with the usual 1px inner-frame (`0x4A3B22`) border, drawn at the top depth of `m_Panel`, centred over its icon and clamped inside `[PAD, W − PAD]` so the end slots don't hang off the frame. The name comes from `PERK_NAMES`, a rank-indexed baked table (the icon instance doesn't identify the perk, and no name field is confirmed on a buff-list entry), so `placePerks` returns `{inst, rank}` and the ranks join the `renderPerks` cache key — two perks can share an icon, and the chip must not name the one that left.

**The hover source is a `Mouse` listener, not `onRollOver` on the slots.** Rollover handlers put a clip in button mode, and the perk row — 6·`ICO` + 5·`ICO_GAP`, 194px at FS 12 — would then swallow left clicks, the same reason no part of the plate takes a press but the collapse button. `hoverTick` instead hit-tests arithmetically in panel space (`m_Panel._xmouse/_ymouse` against the known `PAD` + `i`·(`ICO` + `ICO_GAP`) pitch, rejecting the gaps between boxes), so nothing in the row is interactive and the test holds wherever `rootClip` sits. The chip redraws only on a slot change, and hides on collapse, on hide, on a row change, and on `clearPerkSlots`.

This is the one thing in the panel that runs at mouse-move frequency — continuously while the camera is dragged in combat — so it is ordered to cost as little as possible when there is nothing to name: baked `showPerks` off never installs the listener at all; the rejection path tests cached AS state (`perksShown`, `collapsed`, `previewMode`, and `panelVis`, which mirrors `m_Panel._visible`) before any native mouse or clip read; the row top comes from `perkRowY`, stamped by `layout()`, rather than off the slot clip; and `hideTip()` returns on `tipSlot < 0` instead of rewriting `_visible` on every move.

**Collapsed is a different plate, not the sheet at a shorter height.** The panel folds to a bar reading just `Inspect` — `COLL_W` × `COLL_H` (190 × 24 at FS 12). The stopwatch and the console build their own plates from the same two ratios rather than from copied constants, so all three collapsed bars are identical at *every* baked font size, not only at the default 12 — and since all four panels take the shared `panel_font_size` by default, they sit together in a HUD without any per-dialog matching up. Folding hides the name strip and shows `collTF` in its place, and the collapse button moves onto whichever plate is on screen (`applyCollapsed`, which renders from the effective fold state — preview is the full sheet either way). Nothing on the bar tracks the target, which is what lets a collapsed pass read two ids (§1).

Position mirrors the grids and the cast timer, not the stopwatch: this is a HUD element, mouse-transparent in normal play, so it is repositioned only in preview mode, by the shared overlay (`KazBarsPreview.attach`) that covers the whole plate and carries the live `X:n Y:n` readout to copy back into the dialog. Baked X/Y and `startCollapsed` seed the first-ever session; from then on the game persists drag position and folded state in the module config archive under `inx` / `iny` / `inc`, for every user (the permanent declarations in `game_persistence`). `loadState` reads `inc` **first** and only then clamps `inx`/`iny` against `curW`/`curH`: clamping a sheet against the collapsed bar's height let a saved spot near the bottom edge hang off screen. In normal play the panel's only interactive surfaces are the − / + button and the perk hover — a whole-plate drag would eat combat clicks, and the collapsed bar no longer opens on a plain press (it had that only while it carried a drag strip; the + button is the expand affordance). The overlay covers both surfaces while preview is on, which is intended: preview is for placing the panel, nothing else.

The preview control panel (`stubs/KazBarsPreviewPanel.as`) joins the family on the console's ratios — same plate, double frame, orange title, bronze rules under the title band and under the All/None pair — every dimension `Math.round(FS × ratio)` off the shared `panel_font_size`, delivered by an unconditional `ppanel.configure(d.PF)`; like the console it has no override of its own, and it seeds itself at 12 from its own constructor (a null config is taken as empty rather than bailed on, so a build that never configures it still renders). It is the one panel whose footprint grows with content — one row per grid, a fresh column every `MAX_PER_COL` — so a size that suits a three-grid build walks a sixty-grid one off the screen. `show()` therefore steps its own size down until the plate fits the Stage (floor 8) rather than the shared 8–48 range being cut for everyone: `configure` keeps what it was given in `FS_REQ`, `applySize` does the ratio block, and `measure` is the one place a column/row count becomes a width and a height. Reference footprints: 68 rows across 5 columns leaves a 1080p screen at size 22 and a 1440p screen at 28; a typical 2–6 grid build is single-column and fine past 32. Rows are rebuilt on every preview entry, so the clamp is self-correcting and can never strand a user with a panel they cannot reach. It does not fold: it exists only while preview mode is on, and a panel whose whole job is showing what is hidden gains nothing by hiding itself, so the entire title band is the drag hitbox and there is no collapse glyph to leave room for. Its rows are the console's checkbox with the label width made a parameter (a grid id gets the rest of its column — 220px at FS 12 — instead of the console's fixed 80), its All/None masters are the stopwatch's button, and drag, the live coordinate readout and `clampPos` persistence (`ppx`/`ppy`) are the family's. A row is that item's master switch, not a preview-only hide: it is seeded from live state on entry and persists past the exit. The panel owns none of that state — it calls back into the owner, which routes each key to the stub's own `setActive`, and the flag persists per item rather than per panel.

---

## 6. Known-unreadable

Do not spend another session chasing these through stat space:

- **Weapon base DPS** and the **equipped weapon type** — hence the `gearSchoolCR` heuristic and the absence of a sheet-DPS line. An item-tooltip API route exists but is untested.
- **The attributes' direct "+N DPS with weapons" grant** — reads live (mode-2) attributes and moves the sheet's DPS without touching CR, but its per-point rate was never measured and attribute tooltips are unreachable for targets. Together with the unreadable weapon base DPS this is why the panel has no DPS line — the Weapon Damage % pair is the readable part of that formula and is shown instead.
- **Attribute modes beyond 1** — modes 0 and 3–7 return the raw template 10 on live players. Mode 1 is the pre-multiplier layer (§1) — it looked like a mirror of mode 2 until a %-multiplier subject split them. Flat buffs (including the bugged AA) land inside mode 1, so the AA correction still comes from the buff list, not stat space.
- **The sheet's absolutes** — armor, protection, CDI and spell damage have no id; they are synthesized (§3).
- **The critical-damage feat/AA base** (§3).
- **Absorb-shield pool amounts** and **crowd-control resistance %** (buff presence only).
- **XP and PvP XP.**
- **Hover targeting** — the panel is target-driven because that is the only signal available.

---

## 7. Deliberately not shipped

Researched and understood, but outside the current panel. Recorded so the groundwork is not repeated:

- **Debuff readout.** `GetStat(id, 0)` returns the naked base on players and the **undebuffed spawn template on NPCs**, so `m2 − m0` isolates a live debuff total in two reads — the basis for a `[base N, dbf −N]` readout of Torment / Wrack / Ruin stacks on a boss. The panel polls mode 2 only.
- **Stamina and mana pools** (504/505, 506/507, 1356/1357) and the trailing previous-health mirror (id 11).
- **Season kills/deaths** (1382/1383), which are independent counters from the overall 656/658 pair.
- **Poison invulnerability** (909) — the panel folds poison into the armor line.
- **The 902 / 903 / 904 trio.** The set is confirmed as slash/pierce/crush but the order has never been split, because all three have read tied on every subject sampled. The panel reads 902 for the armor line; if they ever diverge, that is the line to revisit.

## 8. Open questions

- **Level proportionality** of 36.6 / 73.7 / 219.6 is assumed but unverified off-80. The level gate exists so the assumption is never displayed as fact.
- **Floor vs round** on the `attr / 2` term in the protection total is indistinguishable at even attribute values; the stub floors.
- **The 1041 term** as a flat add is an inference — a character with 0.0% Base Spell Damage would discriminate it. Either reading disagrees by at most ±1, inside the sheet's own rounding law.
- **Ferocity rounding.** The 0.15 slope is a single sheet pair (260 → 39.0%); its rounding at odd totals is unmeasured.

---

## 9. Verification

There is no automated coverage of the rendered panel — the AS2/SWF runtime is not unit-testable. Verify by build and manual QA in-game:

1. **Untargeted** — the panel is invisible; in preview it shows the full footprint including whichever sections are enabled, with empty values and empty perk boxes, and drags by the overlay.
2. **Player target** — the PvP section appears; armor and the five protections match the target's sheet digit for digit, PvP values differ from PvE by the 454/458 gaps. The title reads `Name Class (80/N)` — every class maps — and drops `/N` on a PvP-level-0 character. The Perks row shows the target's perk-buff icons — verify the set against a character whose slotted perks are known (self-target first), and that a retarget swaps the icons with no leftovers.
    - **Slot pairs** — each perk sits in its own colour pair (blue General, red Archetype, dark Class); an icon in the wrong pair means a `PERK_IDS` rank has drifted across a `PERK_GEN_MAX` / `PERK_ARCH_MAX` boundary.
    - **Two-slot perks** — a character running one of the 36 two-slot class perks shows its icon in *both* dark boxes, matching the game's bar; one running two ordinary class perks shows two different icons.
    - **Icon fit** — icons sit inside their borders at every font size, not overflowing them (the failure mode is a load-target scale being overwritten by `onLoadInit`).
3. **Mob target** — no PvP section and no Perks row, no attributes, so Heal Rating, Bonus Spell Damage and Ferocity dash and the armor line falls back to the raw gear component. The title carries no class and no PvP level — `Name (83)`.
    - **Section toggles** — rebuild with "Show the PvP section" / "Track slotted perks" off and confirm the section is gone everywhere: live player targets and the preview both.
4. **City guard or other attribute-carrying NPC** — still no PvP section. This is the case the decoded-attribute gate exists for.
5. **Boss target** — template stats and critigation read, tenacity dashes; a mitigation-phase change moves the protection percentages mid-fight via id 911.
6. **Destructible target** — stats read through the `Dynel` fallback rather than dashing out entirely.
7. **Off-80 target** — raw ratings, no parenthetical percentages anywhere.
8. **Retarget rapidly** — no flash of the previous target's numbers (the warm-up), and re-targeting the same entity does not blank the sheet.
9. **Zone or log out with the panel open** — it clears rather than freezing on a stale sheet or re-showing an all-dash phantom.
10. **Collapse and re-open** — the − button folds the panel to the `Inspect` bar; it should measure the stopwatch's collapsed bar at FS 12 and carry no target name. The + button re-opens the full sheet *immediately* — no quarter-second of stale numbers, which is the collapsed pass's two-id diet showing through if it regresses. A plain press on the bar does nothing (intended: the bar is not a button any more), and clicking the name strip expanded does nothing either. Entering preview while folded must show the sheet with live values, not dashes — the same two-id diet, seen from the other side.
11. **Relog** — drag position and collapsed state survive it; the baked X/Y and `startCollapsed` are only what a first-ever session starts from.
