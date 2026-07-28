// KazBarsInspect.as - Target inspect panel: a minimal combat sheet for the
// current target, in the visual language of the game's default inspect window
// (dark plate, orange headers with hairline rules, grey labels, green values,
// every line "Rating (Effect%)"). Runtime-drawn chrome + dynamic text fields
// (Arial resolves against the faces embedded in base.swf), no new symbols.
//
// Reading rules are measured engine behavior, not style choices:
//   - GetStat(id, 2), full watch-list pass every 250 ms via setInterval.
//     Signals are unreliable here (gear/rating ids never signal; signal-time
//     reads race the server), so the poll IS the data path and the
//     assign-on-change string cache subsumes any dirty flag.
//   - 3 clean passes (~750 ms) before the panel shows: login/zone/retarget
//     repopulation settles inside the warm-up instead of flashing garbage.
//   - id 1 AND id 54 collapsing to 0 together is the logout/zone teardown
//     burst, not data: silent rebase + hide, no phantom values.
//   - Subject resolve: Character.GetCharacter(tid), falling back to
//     Dynel.GetDynel(tid) for destructibles (stats yes, buffs no).
//   - Every engine call is try/catch-wrapped.
//
// Display laws (sheet-exact, measured at level 80):
//   - effect% = classBase + rating / 36.6 (zero base for critigation/tenacity;
//     crit weapon base 5 daggers-class / 2.5 else; CDI effect is FLAT round).
//   - mitigation: v/a up to 50%, then 100 - 5000/(50 + v/a); a = 219.6 armor,
//     73.7 protection; sheet column adds (perTypeInvul + id911) x (1 - mit).
//   - armor total = floor(448 x (1 + 450%)) + 2xStr; protection = school comp
//     + floor(451 x (1 + 334%)) + Int/2 (C/E/F) or Wis/2 (H/U).
//   - the divisors are 80-measured: any non-80 target shows raw ratings with
//     every %-decode suppressed (lvlOK gate).
//   - Bonus Spell Damage is a synthesis like protection: untyped component
//     861 + the per-school component (Cold 158 / Fire 876 / Elec 877 /
//     Holy 878 / Unholy 879 — cold is the low-range outlier exactly as it is
//     in the protection and combat-rating families) + 0.6 per point of the
//     caster's main attribute + the flat Base Spell Damage id 1041. The panel
//     shows the highest school, which is the one a caster actually stacks.
//   - players are classified by ID32.IsPlayer() on the target id AND a decoded
//     attribute spread; both must agree. Attribute *presence* is not a
//     discriminator — attributes are x10+10 encoded, so an NPC template that
//     carries them at base still reads raw 10 (decoded 0).
//
// Positioning mirrors the stopwatch: X/Y + fontSize are baked into config
// (the only position that survives relaunch on /loadclip default clients; the
// name strip shows live coordinates while dragging so users can copy them
// into the app); aoc.exe clients persist drag position and collapsed state
// via the module config archive (inx/iny/inc). The name strip carries a
// collapse button that folds the panel to just that strip. ALL geometry
// derives from fontSize, so the panel scales as one piece across rebuilds.
//
// Driven from KazBars: createPanel() in onLoad, setSubject() from
// SlotTargetChanged (first statement, so clears AND raw tids arrive here),
// loadState()/saveState() from the module archive, previewOn()/previewOff()
// from the shared Shift+Ctrl+Alt preview, cleanup() on deactivate.
class KazBarsInspect {
    private var rootClip:MovieClip;

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;
    private var FS:Number;

    // Geometry — every value = Math.round(FS x ratio), so the whole panel
    // scales as one piece with the configured font size.
    private var PAD:Number;       // 0.85  plate padding
    private var LABEL_W:Number;   // 8.6   label column
    private var COL_GAP:Number;   // 0.85  label -> value gap
    private var VALUE_W:Number;   // 12.0  value column
    private var NAME_FS:Number;   // 1.15  name header font size
    private var NAME_GAP:Number;  // 0.5   name -> first section header
    private var SECT_GAP:Number;  // 0.75  space above a section header
    private var RULE_GAP:Number;  // 0.2   header baseline -> 1px rule
    private var ROWS_GAP:Number;  // 0.4   rule -> first stat row
    private var LEAD:Number;      // 0.15  TextFormat leading
    private var BTN:Number;       // 1.1   collapse-button box
    private var W:Number;         // 2xPAD + LABEL_W + COL_GAP + VALUE_W

    // UI (7 text fields + chrome + drag strip + collapse button)
    private var m_Panel:MovieClip;
    private var bg:MovieClip;
    private var body:MovieClip;
    private var collapseBtn:MovieClip;
    private var collapsed:Boolean;
    private var titleH:Number;
    private var fullH:Number;
    private var nameTF:TextField;
    private var pveHdrTF:TextField;
    private var pvpHdrTF:TextField;
    private var pveLabTF:TextField;
    private var pveValTF:TextField;
    private var pvpLabTF:TextField;
    private var pvpValTF:TextField;
    private var dragMC:MovieClip;
    private var coordTF:TextField;
    private var curH:Number;
    // Rule offsets from the last layout pass, replayed on every collapse
    // toggle (-1 = the PvP block is hidden, so there is no second rule).
    private var m_ruleA:Number;
    private var m_ruleB:Number;

    // Subject / poll state
    private var m_Subject:Object;
    private var subjName:String;
    private var subjKey:String;
    // Engine classification of the current subject: 1 player, 0 not,
    // -1 unanswered (fall back to decoded attributes).
    private var subjIsPlayer:Number;
    private var pollIv:Number;
    private var curV:Object;      // "i<id>" -> settled mode-2 value
    private var haveFull:Boolean;
    private var warmup:Number;
    private var previewMode:Boolean;
    private var pvpShown:Boolean;

    // Render cache — assign-on-change strings (TextField.text writes are the
    // expensive part; a full 250 ms pass with nothing changed writes nothing)
    private var lastName:String;
    private var lastPve:String;
    private var lastPvp:String;

    // Watch list: every id one render pass reads (registry-confirmed set)
    private var watchIds:Array;
    // Bonus Spell Damage per-school components (untyped 861 rides the watch
    // list): the sheet's per-school figure is 861 + this school's component.
    private var SPELL_IDS:Array;
    private var DASH:String;

    public function KazBarsInspect(kb:Object, root:MovieClip) {
        rootClip = root;
        m_Subject = null;
        subjName = "";
        subjKey = "";
        curV = {};
        haveFull = false;
        warmup = 0;
        previewMode = false;
        pvpShown = false;
        lastName = "";
        lastPve = "";
        lastPvp = "";
        curH = 0;
        DASH = String.fromCharCode(8212);
        collapsed = false;
        titleH = 0;
        fullH = 0;
        subjIsPlayer = -1;
        // Cold is the low-range outlier in every school family (157 prot,
        // 162 CR, 158 magic damage); the other four cluster at 876-879.
        SPELL_IDS = [158, 876, 877, 878, 879];
        watchIds = [
            1, 27, 525, 54, 67,
            448, 450, 451, 334, 157, 926, 927, 928, 929, 911,
            902, 167, 905, 906, 907, 908,
            312, 711, 713, 804, 808, 810, 814,
            875, 866, 867, 868, 869, 870, 871, 872, 873,
            162, 1007, 1008, 1009, 1010,
            861, 158, 876, 877, 878, 879, 1041,
            1000016, 1000017, 1000018,
            454, 458, 225, 656, 658
        ];
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) return;
        START_X = Number(cfg.x);
        START_Y = Number(cfg.y);
        START_COLLAPSED = (cfg.collapsed == true);
        FS = Number(cfg.fontSize);
        if (isNaN(FS) || FS < 8) FS = 12;
        PAD = Math.round(FS * 0.85);
        LABEL_W = Math.round(FS * 8.6);
        COL_GAP = Math.round(FS * 0.85);
        VALUE_W = Math.round(FS * 12);
        NAME_FS = Math.round(FS * 1.15);
        NAME_GAP = Math.round(FS * 0.5);
        SECT_GAP = Math.round(FS * 0.75);
        RULE_GAP = Math.round(FS * 0.2);
        ROWS_GAP = Math.round(FS * 0.4);
        LEAD = Math.round(FS * 0.15);
        BTN = Math.round(FS * 1.1);
        W = PAD * 2 + LABEL_W + COL_GAP + VALUE_W;
    }

    public function createPanel():Void {
        // Double-init protection (the host re-runs onLoad on the same
        // instance): clear the old interval and clip or both leak.
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        if (m_Panel != null) m_Panel.removeMovieClip();
        m_Panel = rootClip.createEmptyMovieClip("kbInspect", rootClip.getNextHighestDepth());
        m_Panel._x = START_X;
        m_Panel._y = START_Y;
        m_Panel._visible = false;

        collapsed = START_COLLAPSED;

        bg = m_Panel.createEmptyMovieClip("chrome", m_Panel.getNextHighestDepth());
        // Everything below the name strip lives in one clip, so collapsing is
        // a single _visible toggle instead of six.
        body = m_Panel.createEmptyMovieClip("body", m_Panel.getNextHighestDepth());

        nameTF = makeTF(m_Panel, "name", PAD, PAD, W - PAD * 2 - BTN, Math.round(NAME_FS * 1.4),
                        NAME_FS, true, 0xF7A22B, "center");
        pveHdrTF = makeTF(body, "pveHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                          FS, true, 0xF7A22B, "left");
        pveHdrTF.autoSize = "left";
        pveHdrTF.text = "PvE";
        pvpHdrTF = makeTF(body, "pvpHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                          FS, true, 0xF7A22B, "left");
        pvpHdrTF.autoSize = "left";
        pvpHdrTF.text = "PvP";

        pveLabTF = makeTF(body, "pveLab", PAD, 0, LABEL_W, 10, FS, false, 0xC8C0B0, "left");
        pveValTF = makeTF(body, "pveVal", PAD + LABEL_W + COL_GAP, 0, VALUE_W, 10,
                          FS, false, 0x7AC142, "left");
        pvpLabTF = makeTF(body, "pvpLab", PAD, 0, LABEL_W, 10, FS, false, 0xC8C0B0, "left");
        pvpValTF = makeTF(body, "pvpVal", PAD + LABEL_W + COL_GAP, 0, VALUE_W, 10,
                          FS, false, 0x7AC142, "left");
        pveLabTF.autoSize = "left";
        pveValTF.autoSize = "left";
        pvpLabTF.autoSize = "left";
        pvpValTF.autoSize = "left";

        // Label text is constant (15 PvE lines, 8 PvP) — assigned exactly once;
        // missing data renders as the dash so line counts never change and
        // layout() only ever re-runs on the PvP-visibility flip.
        pveLabTF.text = "Health\nArmor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nCritigation Chance\nCritigation Amount\nHeal Rating\nBonus Spell Dmg"
                      + "\nCDI\nCritical Chance\nCritical Damage\nTenacity";
        pvpLabTF.text = "Armor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nCDI\nKills / Deaths";

        // Re-seed the changing fields from the render cache. The host re-runs
        // onLoad on this same instance and setSubject's same-entity path keeps
        // the cache warm, so assign-on-change would write nothing and leave
        // these blank under a full label column.
        nameTF.text = lastName;
        pveValTF.text = lastPve;
        pvpValTF.text = lastPvp;

        // Live position readout — left of the centered name, visible only
        // while dragging (the value a /loadclip user copies into the app to
        // make a spot permanent).
        coordTF = makeTF(m_Panel, "coords", PAD, PAD, LABEL_W, Math.round(FS * 1.3),
                         Math.max(9, Math.round(FS * 0.8)), false, 0x999999, "left");
        coordTF._visible = false;

        // Drag handle = the name strip only (whole-plate drag would eat
        // combat clicks over the stat rows), stopping short of the collapse
        // button so the button still receives its own press.
        dragMC = m_Panel.createEmptyMovieClip("drag", m_Panel.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };

        collapseBtn = m_Panel.createEmptyMovieClip("btnCollapse", m_Panel.getNextHighestDepth());
        collapseBtn._x = W - PAD - BTN;
        collapseBtn._y = PAD;
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        var btf:TextField = makeTF(collapseBtn, "label", 0, 0, BTN, BTN + 2,
                                   Math.max(9, Math.round(FS * 0.9)), true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };

        layout();

        var self:KazBarsInspect = this;
        pollIv = setInterval(function() { self.pollTick(); }, 250);
    }

    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.multiline = true;
        tf.wordWrap = false;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = bold;
        fmt.align = align;
        fmt.color = col;
        fmt.leading = LEAD;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // =========================================================================
    // Layout — runs at createPanel and on the PvP-visibility flip only.
    // Column text fields keep constant line counts, so their heights are
    // stable; total height is read off the fields, never predicted.
    // =========================================================================

    private function layout():Void {
        if (m_Panel == null) return;
        titleH = PAD + nameTF._height + PAD;
        var y:Number = PAD + nameTF._height + NAME_GAP;

        pveHdrTF._y = y;
        y += pveHdrTF._height + RULE_GAP;
        var rule1:Number = y;
        y += 1 + ROWS_GAP;
        pveLabTF._y = y;
        pveValTF._y = y;
        y += pveLabTF._height;

        var rule2:Number = -1;
        pvpHdrTF._visible = pvpShown;
        pvpLabTF._visible = pvpShown;
        pvpValTF._visible = pvpShown;
        if (pvpShown) {
            y += SECT_GAP;
            pvpHdrTF._y = y;
            y += pvpHdrTF._height + RULE_GAP;
            rule2 = y;
            y += 1 + ROWS_GAP;
            pvpLabTF._y = y;
            pvpValTF._y = y;
            y += pvpLabTF._height;
        }
        fullH = y + PAD;
        m_ruleA = rule1;
        m_ruleB = rule2;

        // Name-strip drag hitbox: full width minus the collapse button, so the
        // button keeps its own press.
        dragMC.clear();
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, W - PAD - BTN, titleH);
        dragMC.endFill();

        applyCollapsed();
    }

    // Collapse folds the panel to its name strip; the stat body is one clip,
    // so this is a visibility toggle plus a chrome redraw at the right height.
    public function toggleCollapsed():Void {
        collapsed = !collapsed;
        applyCollapsed();
    }

    private function applyCollapsed():Void {
        if (m_Panel == null) return;
        body._visible = !collapsed;
        collapseBtn.label.text = collapsed ? "+" : "-";
        curH = collapsed ? titleH : fullH;
        drawChrome(curH, collapsed ? -1 : m_ruleA, collapsed ? -1 : m_ruleB);
    }

    private function drawChrome(h:Number, rule1:Number, rule2:Number):Void {
        bg.clear();
        // Plate fill + the two 1px frames (outer black, inner bronze).
        bg.beginFill(0x0C0A07, 90);
        rectPath(bg, 0, 0, W, h);
        bg.endFill();
        bg.lineStyle(1, 0x000000, 100);
        rectPath(bg, 0, 0, W, h);
        bg.lineStyle(1, 0x4A3B22, 100);
        rectPath(bg, 1, 1, W - 2, h - 2);
        // Hairline rule under each section header, full content width.
        // A negative offset means that section is not on screen (collapsed
        // panel, or a target with no PvP block).
        bg.lineStyle(1, 0x6B5324, 100);
        if (rule1 >= 0) {
            bg.moveTo(PAD, rule1);
            bg.lineTo(W - PAD, rule1);
        }
        if (rule2 >= 0) {
            bg.moveTo(PAD, rule2);
            bg.lineTo(W - PAD, rule2);
        }
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    // =========================================================================
    // Subject plumbing (Character first, Dynel wrapper fallback)
    // =========================================================================

    // Receives the RAW tid from SlotTargetChanged (before the host's null
    // branch), so target clears and non-Character dynels both arrive here.
    public function setSubject(tid:Object):Void {
        var isNull:Boolean = (tid == null);
        try {
            if (!isNull && tid.GetType != undefined && tid.GetType() == _global.Enums.TypeID.e_Type_None) isNull = true;
        } catch (e:Object) { isNull = true; }
        if (isNull) {
            m_Subject = null;
            subjIsPlayer = -1;
            resetScan();
            updateVisibility();
            return;
        }
        var subj:Object = resolveTarget(tid);
        if (subj == null) {
            m_Subject = null;
            subjIsPlayer = -1;
            resetScan();
            updateVisibility();
            return;
        }
        var k:String = keyOf(subj);
        if (m_Subject != null && k == subjKey) {
            // Same entity re-targeted — keep the warm cache, no flicker.
            m_Subject = subj;
            return;
        }
        m_Subject = subj;
        subjKey = k;
        subjName = safeName(subj);
        subjIsPlayer = classify(tid, subj);
        resetScan();
        updateVisibility();
    }

    // ID32 carries the engine's own classifiers (IsPlayer / IsNpc / ...).
    // Returns 1 player, 0 not, -1 unanswered — the caller then falls back to
    // decoded attributes.
    private function classify(tid:Object, subj:Object):Number {
        var id:Object = tid;
        if (id == null || id.IsPlayer == undefined) {
            id = null;
            try { id = subj.GetID(); } catch (e:Object) { id = null; }
        }
        if (id != null && id.IsPlayer != undefined) {
            try { return (id.IsPlayer() == true) ? 1 : 0; } catch (e2:Object) {}
        }
        return -1;
    }

    private function resolveTarget(tid:Object):Object {
        if (tid == null) return null;
        var ch:Object = null;
        try {
            ch = com.GameInterface.Game.Character.GetCharacter(tid);
        } catch (e:Object) { ch = null; }
        if (ch == null || ch.GetStat == undefined) {
            try {
                var dy:Object = com.GameInterface.Game.Dynel.GetDynel(tid);
                if (dy != null && dy.GetStat != undefined) return dy;
            } catch (e2:Object) {}
            if (ch != null && ch.GetStat == undefined) return null;
        }
        return ch;
    }

    private function keyOf(obj:Object):String {
        try {
            var id:Object = obj.GetID();
            return String(id.GetType()) + ":" + String(id.GetInstance());
        } catch (e:Object) {}
        return "n:" + safeName(obj);
    }

    private function safeName(obj:Object):String {
        try { return String(obj.GetName()); } catch (e:Object) { return "?"; }
    }

    private function resetScan():Void {
        haveFull = false;
        warmup = 0;
        curV = {};
        lastName = "";
        lastPve = "";
        lastPvp = "";
    }

    // =========================================================================
    // Poll — the whole watch list every pass; the poll IS the settle re-read
    // =========================================================================

    public function pollTick():Void {
        if (m_Subject == null) return;

        // Teardown gate: logout/zone collapses every id to 0 in one burst.
        // id1 AND id54 dropping from nonzero to 0 together is that burst,
        // not stat change — rebase silently and hide, no phantom values.
        if (haveFull && gv(1) != 0 && gv(54) != 0) {
            var t1 = null;
            var t54 = null;
            try { t1 = m_Subject.GetStat(1, 2); t54 = m_Subject.GetStat(54, 2); } catch (eT:Object) {}
            var z1:Boolean = (t1 == null || t1 == undefined || t1 == 0);
            var z54:Boolean = (t54 == null || t54 == undefined || t54 == 0);
            if (z1 && z54) {
                // Drop the dead handle too: a retarget arrives via setSubject
                // anyway, and keeping it would let the warm-up count three
                // null passes and re-show a phantom all-dash sheet.
                m_Subject = null;
                subjKey = "";
                subjName = "";
                subjIsPlayer = -1;
                resetScan();
                updateVisibility();
                return;
            }
        }

        var i:Number = 0;
        while (i < watchIds.length) {
            var sid:Number = Number(watchIds[i]);
            var v = null;
            try { v = m_Subject.GetStat(sid, 2); } catch (e:Object) {}
            curV["i" + sid] = v;
            i++;
        }
        if (!haveFull) {
            // 3 clean passes (~750 ms) before the first show — login/zone/
            // retarget repopulation settles without flashing garbage.
            warmup++;
            if (warmup < 3) return;
            haveFull = true;
        }
        if (previewMode) return;
        render();
    }

    // =========================================================================
    // Stat access + sheet syntheses (field-measured, sheet-exact-verified)
    // =========================================================================

    private function gv(sid:Number):Number {
        var v = curV["i" + sid];
        if (v == null || v == undefined) return 0;
        var n:Number = Number(v);
        if (isNaN(n)) return 0;
        return n;
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

    // Gates the whole PvP block, and both available signals must agree.
    //
    // ID32.IsPlayer() is the engine's own classifier and is measured truthful
    // on players, but it has never been sampled on a mob — so it is trusted to
    // veto, not to confirm alone. The second signal is the DECODED attribute
    // spread: raw values are useless here because the x10+10 encoding means an
    // NPC template carrying the ids at base still reads raw 10 (a city guard
    // does exactly that, which is what put a PvP block on guards). Decoded, a
    // character carries hundreds of points and those templates sit at 0-1.
    private function isPlayer():Boolean {
        var hasAttrs:Boolean = attrSheet(804) > 4 || attrSheet(808) > 4
                            || attrSheet(810) > 4 || attrSheet(814) > 4;
        if (subjIsPlayer >= 0) return (subjIsPlayer == 1) && hasAttrs;
        return hasAttrs;
    }

    // The 36.6 / 73.7 / 219.6 constants are level-80 measurements; any other
    // level shows raw ratings with every %-decode suppressed.
    private function lvlOK():Boolean {
        return gv(54) == 80;
    }

    // linear rating law: effect% = classBase + rating/36.6 at 80
    private function pctOf(r:Number):Number {
        return Math.round(r / 36.6 * 10) / 10;
    }

    // mitigation curve: linear v/a up to 50%, then 100 - 5000/(50 + v/a);
    // a = 219.6 armor, 73.7 protection; negative stat space floors at 0%
    private function mitCurve(v:Number, a:Number):Number {
        if (v <= 0) return 0;
        var q:Number = v / a;
        return (q <= 50) ? q : (100 - 5000 / (50 + q));
    }

    // the sheet's displayed % = base mit + invul x (1 - mit), where the
    // per-type invul column = per-type id + 911 (the all-type component)
    private function sheetMit(baseMit:Number, invulId:Number):Number {
        var inv:Number = gv(invulId) + gv(911);
        return Math.round((baseMit + inv * (1 - baseMit / 100)) * 10) / 10;
    }

    // sheet armor total = floor(comp x (1 + BonusArmor% 450)) + 2 x Str
    private function armorTotal():Number {
        return Math.floor(gv(448) * (1 + gv(450) / 100)) + 2 * attrSheet(804);
    }

    // per-school protection total = school comp + floor(flat 451 x
    // (1 + BonusProt% 334)) + attr/2 (Int for C/E/F, Wis for H/U)
    private function protTotal(schoolId:Number, attrId:Number):Number {
        return gv(schoolId) + Math.floor(gv(451) * (1 + gv(334) / 100)) + Math.floor(attrSheet(attrId) / 2);
    }

    // equipped-school gear CR (weapon type unreadable): largest school
    // component — chars stack the CR of their own weapon school
    private function gearSchoolCR():Number {
        var ids:Array = [866, 867, 868, 869, 870, 871, 872, 873];
        var best:Number = 0;
        var i:Number = 0;
        while (i < ids.length) {
            var v:Number = gv(Number(ids[i]));
            if (v > best) best = v;
            i++;
        }
        return best;
    }

    // Combat Damage Increase rating: 3 x Str (Dex for the dagger class 34)
    // + untyped 875 + equipped-school CR + all typed magic CRs; the PvP tab
    // adds 225 on top. Effect = round(rating/36.6), flat.
    private function cdiPvE():Number {
        var att:Number = (gv(67) == 34) ? attrSheet(814) : attrSheet(804);
        return 3 * att + gv(875) + gearSchoolCR() + gv(162) + gv(1007) + gv(1008) + gv(1009) + gv(1010);
    }

    // =========================================================================
    // Line builders — every line renders like the character sheet:
    // "Rating (Effect%)", dash when data is absent, effect dropped off-80
    // =========================================================================

    private function fmt1(n:Number):String {
        var r:Number = Math.round(n * 10) / 10;
        var s:String = String(r);
        if (s.indexOf(".") == -1) s += ".0";
        return s;
    }

    private function healthLine():String {
        if (!has(1) && !has(27)) return DASH;
        var s:String = gv(27) + " / " + gv(1);
        if (has(525)) s += " (" + gv(525) + "%)";
        return s;
    }

    // rating + folded mitigation % (a = 219.6 armor / 73.7 protection)
    private function mitLine(v:Number, invulId:Number, a:Number):String {
        if (v == 0) return DASH;
        if (!lvlOK()) return String(v);
        return v + " (" + fmt1(sheetMit(mitCurve(v, a), invulId)) + "%)";
    }

    // zero-base linear decode (critigation, tenacity)
    private function pctLine(r:Number):String {
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        return r + " (" + fmt1(pctOf(r)) + "%)";
    }

    // Crit bonus damage: the rating share only. A per-character feat/AA base
    // rides on top of it on the sheet, but it is not readable from stat space
    // and is NOT class-keyed (measured feat bases exist outside class 34), so
    // inventing one would silently inflate the number.
    private function critDmgLine():String {
        return pctLine(gv(711));
    }

    private function critChanceLine():String {
        var r:Number = gv(312);
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        var wpnBase:Number = (gv(67) == 34) ? 5 : 2.5;
        return r + " (" + fmt1(r / 36.6 + wpnBase) + "%)";
    }

    // Heal Rating + the Celestial Gaze heal range (the main HR beneficiary):
    // low = 271 + HR x 0.2761, high = 292 + HR x 0.2761 (community table,
    // all five points exact). Player-only — mobs/bosses never heal-rate.
    private function healLine():String {
        if (!isPlayer()) return DASH;
        var r:Number = gv(713);
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        return r + " (" + Math.round(271 + r * 0.2761) + "-" + Math.round(292 + r * 0.2761) + ")";
    }

    // Bonus Spell Damage. The gear half is confirmed: untyped component 861
    // plus the highest per-school component (Highspawn's 861 read 381, the
    // registry's exact HoX baseline; Bazour's holy component read 57 against a
    // measured 56). But the sheet adds a flat per-character term on top of
    // that — 856/998/866/749/824 across five measured casters, ~115 on a
    // melee priest — and the sheet absolute is proven absent from GetStat
    // space, so that term is derived, not readable.
    //
    // Bonus Spell Damage, sheet-exact on two fully-probed casters:
    //
    //   861 + schoolComponent + round(0.6 x mainAttr) + BaseSpellDamage% 1041
    //
    // Demo Sadyra: 716 + 72 + round(0.6 x 1442 Int) + 1 = 1654, sheet 1654.
    // ToS Khaenofset: 339 + 62 + round(0.6 x 1371 Wis) + 1 = 1224... 1225
    // with the 1041 term, sheet 1225. Main attribute is max(Int, Wis) —
    // priests lead on Wis, mages on Int — which avoids an unmeasured class
    // table, the same shape as the equipped-school CR heuristic. The sheet
    // absolute is proven absent from stat space, so this synthesis is the
    // only route to it, exactly as with armor and protection.
    //
    // The 0.6 per point is level-80-measured like every other constant here,
    // so an off-80 target shows the dash rather than a number built on an
    // unverified coefficient.
    private function spellLine():String {
        var best:Number = 0;
        var i:Number = 0;
        while (i < SPELL_IDS.length) {
            var v:Number = gv(Number(SPELL_IDS[i]));
            if (v > best) best = v;
            i++;
        }
        if (!isPlayer() || !lvlOK()) return DASH;
        var attr:Number = Math.max(attrSheet(808), attrSheet(810));
        var total:Number = gv(861) + best + Math.round(attr * 0.6) + gv(1041);
        if (total == 0) return DASH;
        return String(total);
    }

    // CDI rating + flat effect (the sheet's own Effect column = the DPS add)
    private function cdiLine(add:Number):String {
        var r:Number = cdiPvE();
        if (r == 0) return DASH;
        r += add;
        if (!lvlOK()) return String(r);
        return r + " (" + Math.round(r / 36.6) + ")";
    }

    private function pveValues():String {
        var armorVal:Number = (attrSheet(804) > 0) ? armorTotal() : gv(448);
        var g:Array = new Array();
        g.push(healthLine());
        g.push(mitLine(armorVal, 902, 219.6));
        g.push(mitLine(protTotal(928, 810), 907, 73.7));
        g.push(mitLine(protTotal(929, 810), 908, 73.7));
        g.push(mitLine(protTotal(157, 808), 167, 73.7));
        g.push(mitLine(protTotal(927, 808), 906, 73.7));
        g.push(mitLine(protTotal(926, 808), 905, 73.7));
        g.push(pctLine(gv(1000016)));
        g.push(pctLine(gv(1000018)));
        g.push(healLine());
        g.push(spellLine());
        g.push(cdiLine(0));
        g.push(critChanceLine());
        g.push(critDmgLine());
        g.push(pctLine(gv(1000017)));
        return g.join("\n");
    }

    private function pvpValues():String {
        var armorVal:Number = (attrSheet(804) > 0) ? armorTotal() : gv(448);
        var g:Array = new Array();
        g.push(mitLine(armorVal + gv(454), 902, 219.6));
        g.push(mitLine(protTotal(928, 810) + gv(458), 907, 73.7));
        g.push(mitLine(protTotal(929, 810) + gv(458), 908, 73.7));
        g.push(mitLine(protTotal(157, 808) + gv(458), 167, 73.7));
        g.push(mitLine(protTotal(927, 808) + gv(458), 906, 73.7));
        g.push(mitLine(protTotal(926, 808) + gv(458), 905, 73.7));
        g.push(cdiLine(gv(225)));
        // K/D zeros are legitimate data, never the dash.
        g.push(gv(656) + " / " + gv(658));
        return g.join("\n");
    }

    // =========================================================================
    // Render — assign-on-change; layout() re-runs only on the PvP flip
    // =========================================================================

    private function render():Void {
        if (m_Panel == null || m_Subject == null || !haveFull) {
            updateVisibility();
            return;
        }
        var pv:Boolean = isPlayer();
        if (pv != pvpShown) {
            pvpShown = pv;
            layout();
        }
        if (subjName != lastName) {
            lastName = subjName;
            nameTF.text = subjName;
        }
        var s:String = pveValues();
        if (s != lastPve) {
            lastPve = s;
            pveValTF.text = s;
        }
        if (pvpShown) {
            var p:String = pvpValues();
            if (p != lastPvp) {
                lastPvp = p;
                pvpValTF.text = p;
            }
        }
        updateVisibility();
    }

    private function updateVisibility():Void {
        if (m_Panel == null) return;
        m_Panel._visible = previewMode || (m_Subject != null && haveFull);
    }

    // =========================================================================
    // Preview (shared Shift+Ctrl+Alt) — canned full-footprint sheet so the
    // panel can be positioned without a target
    // =========================================================================

    public function previewOn():Void {
        if (m_Panel == null) return;
        previewMode = true;
        if (!pvpShown) {
            pvpShown = true;
            layout();
        }
        nameTF.text = "Preview";
        pveValTF.text = "11527 / 23093 (49%)\n12492 (55.7%)\n3233 (23.4%)\n3228 (23.2%)"
                      + "\n3090 (22.6%)\n3090 (22.6%)\n3090 (22.6%)\n2196 (60.0%)\n2202 (60.2%)"
                      + "\n2196 (877-898)\n1726\n3312 (90)\n467 (15.3%)\n431 (11.8%)\n2112 (57.7%)";
        pvpValTF.text = "8230 (38.1%)\n3090 (42.5%)\n3090 (42.5%)\n3090 (42.5%)\n3090 (42.5%)"
                      + "\n3090 (42.5%)\n5269 (144)\n18304 / 16264";
        updateVisibility();
    }

    public function previewOff():Void {
        if (m_Panel == null) return;
        previewMode = false;
        // Force a live reassign — the canned sheet overwrote the cache targets.
        lastName = "";
        lastPve = "";
        lastPvp = "";
        if (m_Subject != null && haveFull) {
            render();
        } else {
            if (pvpShown) {
                pvpShown = false;
                layout();
            }
            updateVisibility();
        }
    }

    // =========================================================================
    // Drag (name strip only) + live coordinate readout
    // =========================================================================

    public function beginDrag(da:MovieClip):Void {
        // Both bounds derive from fontSize, so a large enough panel overflows the
        // stage and the rect inverts (bottom < top) — which yanks the panel
        // off-screen on the first press. Floor them: a panel bigger than the
        // stage pins to the top-left corner instead.
        m_Panel.startDrag(false, 0, 0, Math.max(0, Stage.width - W),
                          Math.max(0, Stage.height - curH));
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsInspect = this;
        da.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(da:MovieClip):Void {
        m_Panel.stopDrag();
        delete da.onMouseMove;
        coordTF._visible = false;
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(m_Panel._x) + ", " + Math.round(m_Panel._y);
    }

    // =========================================================================
    // Persistence (aoc.exe clients only — default /loadclip clients have no archive)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        var x:Object = config.FindEntry("inx");
        var y:Object = config.FindEntry("iny");
        if (x !== undefined && y !== undefined) {
            m_Panel._x = clampPos(Number(x), Stage.width - W);
            m_Panel._y = clampPos(Number(y), Stage.height - titleH);
        }
        var c:Object = config.FindEntry("inc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
    }

    public function saveState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        config.ReplaceEntry("inx", m_Panel._x);
        config.ReplaceEntry("iny", m_Panel._y);
        config.ReplaceEntry("inc", collapsed ? 1 : 0);
    }

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }

    public function cleanup():Void {
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        m_Subject = null;
        previewMode = false;
        if (m_Panel != null) {
            m_Panel.removeMovieClip();
            m_Panel = null;
        }
    }
}
