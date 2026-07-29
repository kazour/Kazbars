# Target inspect panel — stat reference

What the `KazBarsInspect` stub reads, and why every constant in it is the number it is. Update when the watch list, a synthesis formula, or a display gate changes — the stub carries the rules as comments, this doc carries the reasoning and the id table behind them.

The panel is an optional in-game overlay (Extras ▸ Target inspect panel…) that renders a combat sheet for the current target in the visual language of the game's own inspect window. It is off by default; when off the build emits zero references and MTASC skips the stub entirely.

| Piece | Where |
|---|---|
| Runtime (AS2, the whole panel) | `src/kazbars/assets/kazbars/stubs/KazBarsInspect.as` |
| Config layer (pure, no Tk) | `src/kazbars/inspect.py` — `validate_config()` |
| Settings dialog | `src/kazbars/inspect_panel.py` — `open_inspect_dialog()` |
| Build gate | `src/kazbars/grids_generator.py` — `include_inspect`, emits the `d.INS` block |
| Config flow | [`flows.md`](flows.md) → flow 26 · build gating → flow 1, steps 9–11 |
| Module wiring | [`architecture.md`](architecture.md) → Build pipeline |

Nothing here is unit-testable — `tests/test_inspect.py` covers the config layer, `tests/test_grids_generator.py` the on/off codegen contract, and `tests/test_build_compile.py` a real MTASC compile of the stub, but the numbers below only prove themselves against the live game sheet. See **Verification** at the bottom.

---

## 1. Reading rules

These are measured engine behaviour, not style choices. Changing any of them changes what the panel shows.

- **Read with `GetStat(id, 2)`.** Mode 2 is the live effective value.
- **Poll; do not trust signals.** A full watch-list pass runs every 250 ms on a `setInterval`. `SignalStatChanged` is not usable as the data path here: gear and rating ids never fire it at all, signal-time reads race the server, and equips with no stat lines emit nothing. The poll *is* the settle re-read, and the assign-on-change string cache in `render()` subsumes any dirty flag — most passes change nothing, and `TextField.text` writes are the expensive part.
- **Warm up 3 passes (~750 ms)** before the panel is allowed to show. Login, zone changes and retargets all repopulate stats over roughly that window; without the warm-up a retarget flashes the previous target's values.
- **Teardown gate.** Logout and zoning collapse every id to 0 in one burst. Id 1 (max HP) and id 54 (level) reading 0 *together* is that burst, not data. On detecting it the stub drops the subject handle outright — keeping the dead handle lets the warm-up count three null passes and re-show a phantom all-dash sheet.
- **Subject resolution.** `Character.GetCharacter(tid)` first, falling back to `Dynel.GetDynel(tid)` so destructibles and simple dynels still read (stats yes, buffs no). This is why a minimal `Dynel` intrinsic sits in `src/kazbars/assets/common_stubs/com/GameInterface/Game/`. Identity key is `GetID().GetType() + ":" + GetInstance()`; re-targeting the same entity keeps the warm cache instead of restarting the warm-up.
- **Visibility is per subject.** A neutral player exposes most of the combat sheet; a hostile player additionally exposes the PvP cluster; mobs expose no attributes, so every attribute-fed synthesis collapses to a dash by design; bosses expose template stats plus critigation.
- **Rounding.** The game sheet *rounds* fractional internals, `GetStat` *floors* them. A ±1 disagreement with the sheet is the display surface, not a wrong formula. Health percent (id 525) is shown verbatim for the same reason — the panel never computes it.

---

## 2. The watch list

57 ids, polled every pass, in the order they appear in `watchIds`. `curV["i" + id]` holds the last settled value; `gv(id)` returns 0 for absent, null or NaN.

### Vitals & identity

| id | meaning | notes |
|---|---|---|
| 1 | Max HP | half of the teardown gate |
| 27 | Current HP | |
| 525 | HP % | displayed verbatim — the game floors it |
| 54 | Level | the level-80 gate for every percent decode; other half of the teardown gate |
| 67 | Class id | 34 is the dagger class — selects Dex over Str for CDI and the 5.0 crit base |

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
| 804 / 808 / 810 / 814 | Strength / Intelligence / Wisdom / Dexterity | ×10+10 encoded |
| 875 | Untyped Combat Rating | CDI input |
| 866–873 | Per-weapon-school Combat Rating | 1HE, 2HE, 1HB, 2HB, dagger, polearm, bow, crossbow |
| 162 | Cold Combat Rating | CDI input |
| 1007–1010 | Fire / Electrical / Holy / Unholy Combat Rating | CDI inputs |
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

### PvP

| id | meaning | notes |
|---|---|---|
| 454 | PvP armor gap | added to the PvE total; can be negative |
| 458 | PvP protection gap | one value, applies to all five schools; can be negative |
| 225 | PvP Combat Rating | added to the CDI rating on the PvP line; moves mid-combat on procs and can rest negative |
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

CDI rating     = 3 × (Dex if class 34 else Str)
                 + 875 + gearSchoolCR + 162 + 1007 + 1008 + 1009 + 1010
CDI effect     = round(rating / 36.6)
PvP CDI rating = CDI rating + 225

PvP Armor      = Armor + 454        ·  PvP Prot(school) = Prot(school) + 458
```

`gearSchoolCR` is `max(866…873)`. The equipped weapon type is **not** readable — weapon-set swaps leave the equip bits invariant — but characters stack their own school's combat rating, so the largest component is it. This is a documented heuristic, not a measurement.

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

Only the highest school shows — a caster stacks exactly one. `max(Int, Wis)` avoids an unmeasured class table (priests lead on Wisdom, mages on Intelligence), the same shape as the school-CR heuristic above. The 1041 term is added flat despite its "Base Spell Damage %" label — read as a percent of the total it lands nowhere near the sheet. Player-only and level-80-only.

### Attribution

The mitigation curve and the 36.6 / 73.7 / 219.6 divisors originate in community formula work (the 2016 Age of Conan formula thread) and were re-verified digit-for-digit against the in-game sheet before shipping. The heal decode is community-table-sourced as noted. Everything else — the totals, the fold, the CDI composition, the spell-damage composition — was derived here against the sheet.

---

## 4. Display rules & gates

- **Dash, never drop.** Absent data renders as an em dash (`String.fromCharCode(8212)`) inside the value field. Row counts never change, so `layout()` re-runs only on the PvP-visibility flip.
- **Level gate.** Every percent decode is suppressed unless `GetStat(54, 2) == 80`. An off-80 target shows the raw rating with no parenthetical — the constants are level-80 measurements and applying them to a level-40 target would produce a confident wrong number.
- **Line format** is `Rating (Effect%)`, matching the game's own combat-stats tab.
- **PvP block gating.** Shown only when the engine's `ID32.IsPlayer()` **and** a decoded attribute spread both agree:

  ```
  hasAttrs = any of attrSheet(804/808/810/814) > 4
  isPlayer = (subjIsPlayer >= 0) ? (subjIsPlayer == 1 && hasAttrs) : hasAttrs
  ```

  `IsPlayer()` is measured truthful on players but has never been sampled on a mob, so it **vetoes** rather than confirms alone; `subjIsPlayer == -1` means it never answered and the attribute spread carries the decision. The attribute half must be *decoded* — testing raw presence put a PvP block on city guards, because an NPC template at base attributes reads raw 10.
- **Player-only lines** — Heal Rating and Bonus Spell Damage — dash on any non-player subject.
- **Preview** (`previewOn()`) paints a canned full-footprint sheet including the PvP block, so the panel can be positioned without a target. `previewOff()` clears the render cache, since the canned values bypassed it.

---

## 5. Visual contract

The panel mirrors the game's default inspect window: near-black warm plate, 1px black-over-bronze frame, Conan-orange headers with hairline rules, parchment-grey labels, sheet-green values. Arial only — `embedFonts = false`, resolving against the faces already embedded in `base.swf`, so the panel needs no new symbols.

| Constant | Value | Role |
|---|---|---|
| `COL_HEADER` | `0xF7A22B` | name strip + PvE/PvP section headers (bold) |
| `COL_LABEL` | `0xC8C0B0` | stat labels |
| `COL_VALUE` | `0x7AC142` | stat values, including the em-dash fallback |
| `COL_RULE` | `0x6B5324` | 1px rule under each section header |
| `COL_BG` | `0x0C0A07` @ alpha 90 | plate fill |
| `COL_FRAME_IN` | `0x4A3B22` | 1px inner frame |
| `COL_FRAME_OUT` | `0x000000` | 1px outer frame |
| `COL_COORD` | `0x999999` | drag coordinate readout |

Every dimension is `Math.round(FS × ratio)`, so the whole panel scales as one piece from the baked `fontSize`:

| Constant | Ratio | @ FS 12 | Role |
|---|---|---|---|
| `PAD` | 0.85 | 10 | plate padding, all four sides |
| `LABEL_W` | 8.6 | 103 | label column (fits "Critigation Chance") |
| `COL_GAP` | 0.85 | 10 | label column → value column |
| `VALUE_W` | 12.0 | 144 | value column (fits a boss health line) |
| `NAME_FS` | 1.15 | 14 | name header font size |
| `BTN` | 1.1 | 13 | collapse-button box; name field and drag hitbox both stop short of it |
| `NAME_GAP` | 0.5 | 6 | name strip → first section header |
| `SECT_GAP` | 0.75 | 9 | space above a section header |
| `RULE_GAP` | 0.2 | 2 | section header bottom → rule top |
| `ROWS_GAP` | 0.4 | 5 | rule → first stat row |
| `LEAD` | 0.15 | 2 | `TextFormat.leading`, applied to every field |
| `W` | 2·`PAD` + `LABEL_W` + `COL_GAP` + `VALUE_W` | 277 | total footprint — derived, never fixed |

`W` measures the outer black frame; both 1px frames sit inside it. Rules run from `x = PAD` to `W − PAD`. Both columns are single left-aligned multiline `TextField`s sharing one `TextFormat`, so rows stay baseline-aligned; headers are their own bold fields.

Position and collapse mirror the stopwatch: baked X/Y and `startCollapsed` defaults are the only position that survives relaunch on `/loadclip` clients; dragging the name strip shows live coordinates to copy back into the dialog; aoc.exe clients persist drag position and folded state in the module config archive under `inx` / `iny` / `inc`. The drag hitbox is the name strip only — a whole-plate drag would eat combat clicks.

---

## 6. Known-unreadable

Do not spend another session chasing these through stat space:

- **Weapon base DPS** and the **equipped weapon type** — hence the `gearSchoolCR` heuristic and the absence of a sheet-DPS line. An item-tooltip API route exists but is untested.
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

---

## 9. Verification

There is no automated coverage of the rendered panel — the AS2/SWF runtime is not unit-testable. Verify by build and manual QA in-game:

1. **Untargeted** — the panel is invisible; preview from the dialog paints the full footprint including the PvP block, and drag/collapse work against it.
2. **Player target** — the PvP section appears; armor and the five protections match the target's sheet digit for digit, PvP values differ from PvE by the 454/458 gaps.
3. **Mob target** — no PvP section, no attributes, so Heal Rating and Bonus Spell Damage dash and the armor line falls back to the raw gear component.
4. **City guard or other attribute-carrying NPC** — still no PvP section. This is the case the decoded-attribute gate exists for.
5. **Boss target** — template stats and critigation read, tenacity dashes; a mitigation-phase change moves the protection percentages mid-fight via id 911.
6. **Destructible target** — stats read through the `Dynel` fallback rather than dashing out entirely.
7. **Off-80 target** — raw ratings, no parenthetical percentages anywhere.
8. **Retarget rapidly** — no flash of the previous target's numbers (the warm-up), and re-targeting the same entity does not blank the sheet.
9. **Zone or log out with the panel open** — it clears rather than freezing on a stale sheet or re-showing an all-dash phantom.
10. **aoc.exe client** — drag position and collapsed state survive a relaunch; on `/loadclip` clients the baked X/Y and `startCollapsed` are what persist.
