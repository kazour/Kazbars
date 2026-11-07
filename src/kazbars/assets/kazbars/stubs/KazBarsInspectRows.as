// KazBarsInspectRows.as - The inspect panel's stat model: every id read, every
// synthesis formula, and the row-kind dispatch that turns a baked row object
// ({f: "...", s: ..., ...}) into the one line of text it renders as. Split out
// of KazBarsInspect so the panel's own class stays under the AVM1 bytecode
// cap; this class holds no UI state at all, only the poll cache and the
// formatters; KazBarsInspect drives it as `eng`, the Console's Stats tab one per side.
//
// Reading rules are measured engine behaviour, not style: gear and rating ids
// never fire SignalStatChanged and signal-time reads race the server, so the
// 250 ms GetStat poll is the data path. Every synthesis constant below is
// level-invariant (confirmed in game across the full 1-86 range), so the
// %-decodes show for every target regardless of level.
class KazBarsInspectRows {

    // Poll cache — id -> settled mode-2 value, plus the player state the
    // poll settles once a pass.
    public var curV:Object;
    public var subjPlayer:Boolean;
    public var DASH:String;
    public var twoHand:Number;   // main-hand family: -1 unknown, 0 one-handed, 1 two-handed
    // What opens and closes a "rating (effect)" line's second part, in the lines the PvP view splits into its two
    // columns (mitigation, chance, combat damage): the panel sets "\t" and "" around that view's values.
    public var L:String;
    public var R:String;

    private var SPELL_IDS:Array;

    public function KazBarsInspectRows(d:Object) {
        curV = {};
        subjPlayer = false;
        twoHand = -1;
        DASH = String.fromCharCode(8212);
        L = " (";
        R = ")";
        SPELL_IDS = d.spellIds;
    }

    public function reset():Void {
        curV = {};
        subjPlayer = false;
        twoHand = -1;
    }

    // =========================================================================
    // Stat access + sheet syntheses (field-measured at level 80, level-invariant)
    // =========================================================================

    // Keyed by the raw id: a full render asks this ~195 times, and building
    // a key string per ask was the panel's largest source of AVM1 garbage.
    public function gv(sid:Number):Number {
        var v = curV[sid];
        if (v == null || v == undefined) return 0;
        var n:Number = Number(v);
        if (isNaN(n)) return 0;
        return n;
    }

    // gv() guarded for an id field that may be the baked "no id" sentinel
    // (0) or plain missing (an omitted optional field bakes as undefined,
    // and Number(undefined) is NaN) — id 0 is a real stat, so it must never
    // reach gv() as a lookup key.
    private function gvo(x:Number):Number {
        if (!(x > 0)) return 0;
        return gv(x);
    }

    private function has(sid:Number):Boolean {
        return gv(sid) != 0;
    }

    // attribute sheet value from the x10+10 encoding; 0 = absent (mobs)
    private function attrSheet(sid:Number):Number {
        var r:Number = gv(sid);
        if (r == 0) return 0;
        return Math.round((r - 10) / 10);
    }

    // exact (unrounded) attribute share for Regen: 0 when the id is the
    // "unused" sentinel or reads 0, else (raw - 10) / 10 — measured in game.
    private function attrExact(x:Number):Number {
        return (gvo(x) == 0) ? 0 : (gv(x) - 10) / 10;
    }

    // Gates the PvP block, the Perks row, the title's class name and every
    // player-only line; both signals must agree. IsPlayer() is measured
    // truthful on players but never sampled on a mob, so it vetoes rather
    // than confirms alone. Attributes must be DECODED — raw, an NPC template
    // carrying them at base reads 10, which put a PvP block on city guards.
    public function evalPlayer(subjIsPlayer:Number):Boolean {
        var hasAttrs:Boolean = attrSheet(804) > 4 || attrSheet(808) > 4
                            || attrSheet(810) > 4 || attrSheet(814) > 4;
        if (subjIsPlayer >= 0) return (subjIsPlayer == 1) && hasAttrs;
        return hasAttrs;
    }

    // linear rating law: effect% = classBase + rating/36.6
    private function pctOf(r:Number):Number {
        return Math.round(r / 36.6 * 10) / 10;
    }

    // linear v/a to 50%, then 100 - 5000/(50 + v/a); a = 219.6 armor,
    // 73.7 protection. Negative stat space floors at 0%.
    private function mitCurve(v:Number, a:Number):Number {
        if (v <= 0) return 0;
        var q:Number = v / a;
        return (q <= 50) ? q : (100 - 5000 / (50 + q));
    }

    // displayed % = base mit + invul x (1 - mit), where the per-type invul
    // column = per-type id + 911 (the all-type component)
    private function sheetMit(baseMit:Number, invulId:Number):Number {
        var inv:Number = gv(invulId) + gv(911);
        return Math.round((baseMit + inv * (1 - baseMit / 100)) * 10) / 10;
    }

    // floor(comp x (1 + BonusArmor% 450)) + 2 x Str
    private function armorTotal():Number {
        return Math.floor(gv(448) * (1 + gv(450) / 100)) + 2 * attrSheet(804);
    }

    // school comp + floor(flat 451 x (1 + BonusProt% 334)) + attr/2
    // (Int for Cold/Elec/Fire, Wis for Holy/Unholy)
    private function protTotal(schoolId:Number, attrId:Number):Number {
        return gv(schoolId) + Math.floor(gv(451) * (1 + gv(334) / 100)) + Math.floor(attrSheet(attrId) / 2);
    }

    // The base armor component: comp/AA-decoded total when attributes are
    // readable, the raw gear component otherwise; the PvP gap 454 adds on top.
    private function armorVal(p:Boolean):Number {
        var base:Number = (attrSheet(804) > 0) ? armorTotal() : gv(448);
        return base + (p ? gv(454) : 0);
    }

    // The weapon type itself is unreadable, but its family is (twoHand, set
    // by the panel from the worn inventory): a two-handed weapon draws on
    // 867/869/871, a one-handed on 866/868/870. Dagger/bow/crossbow
    // (872/873) stay in both; unknown takes the largest of all eight.
    private function maxOf(ids:Array):Number {
        var best:Number = 0;
        var i:Number = 0;
        while (i < ids.length) {
            var v:Number = gv(Number(ids[i]));
            if (v > best) best = v;
            i++;
        }
        return best;
    }

    // 3 x Str (Dex for the dagger class 34 and Rangers 39 — both named by
    // the sheet's own tooltip) + untyped 875 + equipped-school CR (by weapon family; none
    // without a main-hand weapon) + every typed magic CR; the PvP tab adds
    // 225 on top.
    //
    // The attr term is the SHEET attribute. In game two of its sources are
    // known to raise the attribute without raising this rating: the
    // all-attribute AA (measured in game: 3 x 20 rating short per point
    // invested, rank unreadable on another player) and %-attribute potions
    // (the sheet's own basis is the pre-multiplier value). Reproducing
    // those exclusions needs a formula we do not have yet — guessing a rank
    // was worse than showing the straightforward number — so this line
    // reads high for a subject running either.
    private function cdiPvE():Number {
        var c:Number = gv(67);
        var att:Number = (c == 34 || c == 39) ? attrSheet(814) : attrSheet(804);
        if (att < 0) att = 0;
        var sch:Number = 0;
        if ((gv(148) & 64) != 0) {
            if (twoHand == 1) sch = maxOf([867, 869, 871, 872, 873]);
            else if (twoHand == 0) sch = maxOf([866, 868, 870, 872, 873]);
            else sch = maxOf([866, 867, 868, 869, 870, 871, 872, 873]);
        }
        return 3 * att + gv(875) + sch + gv(162) + gv(1007) + gv(1008) + gv(1009) + gv(1010);
    }

    // =========================================================================
    // Line builders — "Rating (Effect%)", dash when absent
    // =========================================================================

    private function fmt1(n:Number):String {
        var r:Number = Math.round(n * 10) / 10;
        var s:String = String(r);
        if (s.indexOf(".") == -1) s += ".0";
        return s;
    }

    private function healthLine():String {
        if (!has(1) && !has(27)) return DASH;
        return gv(27) + " / " + gv(1);
    }

    // Current + its percent id as one sheet number (Health/Stamina/Mana);
    // dashed only when NEITHER id has ever answered — 0 is real data on
    // either alone, so the null/undefined/NaN test rawLine() uses decides
    // the dash, not a zero check.
    private function poolLine(cur:Number, pct:Number):String {
        var cv = curV[cur];
        var pv = curV[pct];
        var curOk:Boolean = !(cv == null || cv == undefined || isNaN(Number(cv)));
        var pctOk:Boolean = !(pv == null || pv == undefined || isNaN(Number(pv)));
        if (!curOk && !pctOk) return DASH;
        return String(gv(cur)) + " (" + String(gv(pct)) + "%)";
    }

    // Dashed only when the score AND the invulnerability are both zero: the
    // percent moves on invulnerability alone (a debuff on a 0-armor target
    // reads 0 (-10.0%)), so a score-only test hid real changes.
    private function mitLine(v:Number, invulId:Number, a:Number):String {
        if (v == 0 && gv(invulId) + gv(911) == 0) return DASH;
        return v + L + fmt1(sheetMit(mitCurve(v, a), invulId)) + "%" + R;
    }

    // zero-base linear decode (critigation, tenacity)
    private function pctLine(r:Number):String {
        if (r == 0) return DASH;
        return r + " (" + fmt1(pctOf(r)) + "%)";
    }

    // Rating share (711) + the flat sheet add (710); dash only when both are
    // absent — a flat-only bonus with no rating is still real data.
    private function critDmgLine():String {
        var r:Number = gv(711);
        var add:Number = gv(710);
        if (r == 0 && add == 0) return DASH;
        return r + " (" + fmt1(pctOf(r) + add) + "%)";
    }

    private function critChanceLine():String {
        var r:Number = gv(312);
        if (r == 0) return DASH;
        var wpnBase:Number = (gv(67) == 34) ? 5 : 2.5;
        return r + " (" + fmt1(r / 36.6 + wpnBase) + "%)";
    }

    // Tap %, rating(s) + a linear-rating share on top (both id families
    // share the same 36.6 divisor as every other rating line). sb/rb are
    // the row's optional second-percent/PvP-rating ids (0 = unused).
    // Rendered "rating (effect%)", the project-wide shape pctLine() also
    // uses. Shown as read — a tap tooltip is not guaranteed a stat
    // footprint at all — so nothing else is composed. Dashed only when
    // every term is absent.
    private function tapLine(sa:Number, sb:Number, scale:Number, ra:Number, rb:Number):String {
        var pct:Number = gvo(sa) / scale + gvo(sb);
        var rate:Number = gvo(ra) + gvo(rb);
        if (pct == 0 && rate == 0) return DASH;
        return String(rate) + " (" + fmt1(pct + rate / 36.6) + "%)";
    }

    // Evade/Immunity: the sheet's rating column is the rating id(s) plus
    // half an attribute (Dexterity on Evade, measured in game on three
    // characters), and its percent adds the x100 direct-percent id on top
    // of the usual rating/36.6. Same "rating (effect%)" shape as tapLine.
    private function chanceLine(pid:Number, scale:Number, rid:Number, aid:Number, vid:Number):String {
        var rate:Number = gvo(rid) + gvo(vid) + ((aid > 0) ? Math.floor(attrSheet(aid) / 2) : 0);
        var pct:Number = gvo(pid) / scale;
        if (rate == 0 && pct == 0) return DASH;
        return String(rate) + L + fmt1(pct + rate / 36.6) + "%" + R;
    }

    // Hate Modification: the sheet's rating column is Hate Increase minus
    // Hate Decrease (either can be absent), and its percent adds the signed
    // whole percent a stance or gear sets in 170. Measured in game on three
    // characters, including a negative total, which nothing clamps.
    private function hateLine():String {
        var rate:Number = gv(491) - gv(488);
        var mod:Number = gv(170);
        if (rate == 0 && mod == 0) return DASH;
        return String(rate) + " (" + fmt1(rate / 36.6 + mod) + "%)";
    }

    // Regen: a base id plus a k-hundredths share of up to three EXACT
    // (unrounded) attributes, floored — measured in game. k/a/b/c are 0
    // when unused; 0 is still real data, so there is no dash.
    private function regenLine(sid:Number, k:Number, a:Number, b:Number, c:Number):String {
        // k is omitted from the baked row when the line has no attribute
        // term (Health Regen), and Number(undefined) is NaN — which 0 does
        // NOT absorb through a multiply, so the guard is not optional.
        var share:Number = (k > 0) ? (k / 100) * (attrExact(a) + attrExact(b) + attrExact(c)) : 0;
        return String(Math.floor(gvo(sid) + share));
    }

    // Rating + the Celestial Gaze range it buys (the main beneficiary):
    // 271 + HR x 0.2761 to 292 + HR x 0.2761. Player-only.
    private function healLine():String {
        if (!subjPlayer) return DASH;
        var r:Number = gv(713);
        if (r == 0) return DASH;
        return r + " (" + Math.round(271 + r * 0.2761) + "-" + Math.round(292 + r * 0.2761) + ")";
    }

    // 861 + schoolComponent + round(0.6 x mainAttr) + a flat 1 (the sheet
    // adds a flat 1 regardless of Base Spell Damage %). Main attribute is
    // max(Int, Wis) — priests lead on Wis, mages on Int — avoiding an
    // unmeasured class table, like the school CR above. sid is one school's
    // component (the PvP view's per-school lines); without one the highest
    // school shows, since a caster stacks exactly one. The PvP rows add 226
    // on top — one value for all schools, the 458 shape.
    private function spellLine(add:Number, sid:Number):String {
        if (!subjPlayer) return DASH;
        // Mana-less classes (Ranger measured; Barbarian predicted) sheet the
        // whole per-school block at 0 even when 861 carries residue —
        // max mana 507 is the gate.
        if (gv(507) == 0) return DASH;
        var best:Number = (sid > 0) ? gv(sid) : maxOf(SPELL_IDS);
        var attr:Number = Math.max(attrSheet(808), attrSheet(810));
        var total:Number = gv(861) + best + Math.round(attr * 0.6) + 1 + add;
        if (total == 0) return DASH;
        return String(total);
    }

    // Armor / Spell Penetration (449 / 452) as the raw rating: no effect
    // divisor was ever measured, so the number stands alone rather than
    // carry an invented percent.
    private function penLine(sid:Number):String {
        var v:Number = gv(sid);
        if (v == 0) return DASH;
        return String(v);
    }

    // Sheet Ferocity = floor(1403/10), the x10-encoded gear component and
    // nothing else. Effect is 0.15 x total on all five AOE surfaces.
    // Player-only.
    private function ferLine():String {
        if (!subjPlayer) return DASH;
        var t:Number = Math.floor(gv(1403) / 10);
        if (t == 0) return DASH;
        return t + " (" + fmt1(t * 0.15) + "%)";
    }

    // Weapon Damage % pair (1095 melee / 1096 ranged, x100) — the sheet's
    // Melee/Ranged values verbatim. Dashed only when both are absent.
    // The sheet carries melee and ranged separately, but a character only
    // ever fights with one of them, so the larger is the one that matters.
    private function wdLine():String {
        var m:Number = gv(1095);
        var r:Number = gv(1096);
        if (m == 0 && r == 0) return DASH;
        return fmt1((m > r ? m : r) / 100) + "%";
    }

    // A percent id whose IDLE value is a base rather than 0 (Magic Damage
    // Modifier sits at 100 with nothing running), shown as the signed
    // deviation so "nothing" reads 0% like every other modifier.
    private function pctBaseLine(sid:Number, base:Number):String {
        var v = curV[sid];
        if (v == null || v == undefined) return DASH;
        var n:Number = Number(v);
        if (isNaN(n)) return DASH;
        return String(n - base) + "%";
    }

    // rating + the PvP add (the sheet's Effect column = the DPS add). The add
    // goes in BEFORE the zero test, like armor and protection do with 454/458:
    // a subject with no PvE rating but PvP gear still has a PvP rating to show.
    private function cdiLine(add:Number):String {
        var r:Number = cdiPvE() + add;
        if (r == 0) return DASH;
        return r + L + Math.round(r / 36.6) + R;
    }

    // Pair line (kills/deaths and similar): 0 is real data on both sides.
    private function pairLine(s:Number, t:Number):String {
        return String(gv(s)) + " / " + String(gv(t));
    }

    // Minigame wins / losses, overall: Annihilation, Capture the Skull and Conquest summed.
    private function wlLine():String {
        return (gv(666) + gv(668) + gv(1000026)) + " / " + (gv(667) + gv(669) + gv(1000027));
    }

    // The integer as read, straight from the poll cache: dash only when the
    // id never answered (null/undefined/NaN) — 0 is real data (NPC flags
    // read 0 on players).
    private function rawLine(sid:Number):String {
        var v = curV[sid];
        if (v == null || v == undefined) return DASH;
        var n:Number = Number(v);
        if (isNaN(n)) return DASH;
        return String(n);
    }

    private function x100Line(sid:Number):String {
        return fmt1(gv(sid) / 100) + "%";
    }

    // Decoded attribute sheet value; dash when the raw id sheets 0 (absent).
    private function attrLine(sid:Number):String {
        if (gv(sid) == 0) return DASH;
        return String(attrSheet(sid));
    }

    // Raw percent straight off the poll cache: dash only when the id never
    // answered — 0 is real data.
    private function pctRawLine(sid:Number):String {
        var v = curV[sid];
        if (v == null || v == undefined) return DASH;
        var n:Number = Number(v);
        if (isNaN(n)) return DASH;
        return String(n) + "%";
    }

    // =========================================================================
    // Row dispatch — a baked row object {f, s, t, i, d, p, g, l} to one line
    // Summary lines (the Default sheet). Protection: the largest of the five
    // PvE school totals (first wins a tie) with its own invulnerability.
    private function protMaxLine():String {
        var sc:Array = [928, 929, 157, 927, 926];
        var at:Array = [810, 810, 808, 808, 808];
        var iv:Array = [907, 908, 167, 906, 905];
        var best:Number = protTotal(sc[0], at[0]);
        var bi:Number = iv[0];
        var i:Number = 1;
        while (i < 5) {
            var v:Number = protTotal(sc[i], at[i]);
            if (v > best) {
                best = v;
                bi = iv[i];
            }
            i++;
        }
        return mitLine(best, bi, 73.7);
    }

    private function critPctLine():String {
        var r:Number = gv(312);
        var r2:Number = gv(711);
        var add:Number = gv(710);
        if (r == 0 && r2 == 0 && add == 0) return DASH;
        var base:Number = (gv(67) == 34) ? 5 : 2.5;
        return fmt1(((r == 0) ? 0 : r / 36.6 + base)) + "% / " + fmt1(pctOf(r2) + add) + "%";
    }

    private function hatePctLine():String {
        var rate:Number = gv(491) - gv(488);
        var mod:Number = gv(170);
        if (rate == 0 && mod == 0) return DASH;
        return fmt1(rate / 36.6 + mod) + "%";
    }

    private function ratePctLine(sid:Number):String {
        var r:Number = gv(sid);
        if (r == 0) return DASH;
        return fmt1(pctOf(r)) + "%";
    }

    private function ratePairLine(sa:Number, sb:Number):String {
        var a:Number = gv(sa);
        var b:Number = gv(sb);
        if (a == 0 && b == 0) return DASH;
        return fmt1(pctOf(a)) + "% / " + fmt1(pctOf(b)) + "%";
    }

    // =========================================================================

    // Default-sheet lines (z: 1) show a zero like the character sheet where
    // the plain line would show the dash.
    public function value(r:Object):String {
        var s:String = line(r);
        if (r.z == 1 && s == DASH) return zeroOf(String(r.f));
        return s;
    }

    private function zeroOf(f:String):String {
        switch (f) {
            case "health":
                return "0 / 0";
            case "armor":
            case "protmax":
                return "0 (0.0%)";
            case "critp":
            case "ratepp":
                return "0.0% / 0.0%";
            case "hatep":
            case "ratep":
                return "0.0%";
            case "cdi":
                return "0 (0)";
            case "heal":
            case "spell":
            case "fer":
                return subjPlayer ? "0" : DASH;
            default:
                return DASH;
        }
    }

    private function line(r:Object):String {
        switch (String(r.f)) {
            case "health":
                return healthLine();
            case "pool":
                return poolLine(Number(r.s), Number(r.t));
            case "armor":
                return mitLine(armorVal(r.p), 902, 219.6);
            case "prot":
                var pv:Number = protTotal(Number(r.s), Number(r.t)) + (r.p ? gv(458) : 0);
                return mitLine(pv, Number(r.i), 73.7);
            case "rate":
                return pctLine(gv(Number(r.s)));
            case "tap":
                return tapLine(Number(r.s), Number(r.u), Number(r.d), Number(r.t), Number(r.v));
            case "chance":
                return chanceLine(Number(r.s), Number(r.d), Number(r.t), Number(r.a), Number(r.v));
            case "pctb":
                return pctBaseLine(Number(r.s), Number(r.d));
            case "hate":
                return hateLine();
            case "protmax":
                return protMaxLine();
            case "critp":
                return critPctLine();
            case "hatep":
                return hatePctLine();
            case "ratep":
                return ratePctLine(Number(r.s));
            case "ratepp":
                return ratePairLine(Number(r.s), Number(r.t));
            case "regen":
                return regenLine(Number(r.s), Number(r.k), Number(r.a), Number(r.b), Number(r.c));
            case "heal":
                return healLine();
            case "spell":
                return spellLine(r.p ? gv(226) : 0, Number(r.s));
            case "cdi":
                return cdiLine(r.p ? gv(225) : 0);
            case "wd":
                return wdLine();
            case "critc":
                return critChanceLine();
            case "critd":
                return critDmgLine();
            case "pen":
                return penLine(Number(r.s));
            case "fer":
                return ferLine();
            case "pair":
                return pairLine(Number(r.s), Number(r.t));
            case "wl":
                return wlLine();
            case "raw":
                return rawLine(Number(r.s));
            case "x100":
                return x100Line(Number(r.s));
            case "attr":
                return attrLine(Number(r.s));
            case "pct":
                return pctRawLine(Number(r.s));
            default:
                return DASH;
        }
    }

    public function values(list:Array):String {
        var g:Array = new Array();
        var i:Number = 0;
        while (i < list.length) {
            g.push(value(list[i]));
            i++;
        }
        return g.join("\n");
    }

    public static function labels(list:Array):String {
        var g:Array = new Array();
        var i:Number = 0;
        while (i < list.length) {
            g.push(String(list[i].l));
            i++;
        }
        return g.join("\n");
    }
}
