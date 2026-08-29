// KazBarsInspect.as - Target inspect panel: a combat sheet for the current
// target in the visual language of the game's default inspect window.
// Runtime-drawn chrome + dynamic text fields (Arial resolves against the faces
// embedded in base.swf), so it needs no new symbols. Plate and collapse
// primitives inherit from KazBarsPanel.
//
// Reading rules are measured engine behaviour, not style: gear and rating ids
// never fire SignalStatChanged and signal-time reads race the server, so the
// 250 ms GetStat poll is the data path; 3 clean passes settle before the panel
// shows; id 1 + id 54 collapsing together is the logout/zone teardown burst,
// not data. Every synthesis constant below is level-invariant (confirmed
// in game across the full 1-86 range), so the %-decodes show for every
// target regardless of level.
//
// The PvP section and the Perks row are baked config gates (showPvp /
// showPerks). The Perks row shows the slotted AA perk buffs detected on a
// player target's buff list as game icons, RDB-loaded through the same
// ImageLoader path the grids use; a player slots at most 6 (2 General,
// 2 Archetype, 2 Class — some Class perks cost both slots). Hovering an icon
// names it from a baked table, hit-tested off a Mouse listener rather than
// rollover handlers — see hoverTick().
//
// Positioning mirrors the grids and the cast timer, not the stopwatch: this is
// a HUD element, so it is mouse-transparent in normal play and is dragged only
// in preview mode, through the shared overlay in KazBarsPreview. X/Y, font size
// and collapsed state baked into config are the first-session defaults; drag +
// collapse persist via the archive (inx/iny/inc, master switch inv). All
// geometry derives from fontSize.
//
// Driven from KazBars: create() in onLoad, setSubject() from
// SlotTargetChanged (first statement, so clears and raw tids both arrive),
// loadState()/saveState() from the module archive, previewOn()/previewOff()
// from the shared preview, cleanup() on deactivate.
class KazBarsInspect extends KazBarsPanel implements KazBarsModule {

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;
    private var SHOW_PVP:Boolean;
    private var SHOW_PERKS:Boolean;

    // Geometry beyond the base set — every value is Math.round(FS x ratio),
    // so the panel scales as one piece.
    private var LABEL_W:Number;   // 8.6   label column
    private var COL_GAP:Number;   // 0.85  label -> value gap
    private var VALUE_W:Number;   // 12.0  value column
    private var NAME_GAP:Number;  // 0.5   name -> first section header
    private var SECT_GAP:Number;  // 0.75  space above a section header
    private var RULE_GAP:Number;  // 0.2   header baseline -> 1px rule
    private var ROWS_GAP:Number;  // 0.4   rule -> first stat row
    private var ICO:Number;       // 2.4   perk icon box
    private var ICO_GAP:Number;   // 0.35  gap between perk icons
    private var TIP_PAD:Number;   // 0.3   perk-name chip padding, and its gap
                                  //       above the icon row
    private var W:Number;         // 2xPAD + LABEL_W + COL_GAP + VALUE_W

    // UI
    private var body:MovieClip;
    private var panelVis:Boolean;     // mirrors panelClip._visible; hoverTick
                                      // asks every mouse move
    private var fullH:Number;
    private var nameTF:TextField;
    private var collTF:TextField;     // the collapsed bar's whole content
    private var pveHdrTF:TextField;
    private var pvpHdrTF:TextField;
    private var pveLabTF:TextField;
    private var pveValTF:TextField;
    private var pvpLabTF:TextField;
    private var pvpValTF:TextField;
    private var m_ruleA:Number;   // rule offsets from the last layout pass,
    private var m_ruleB:Number;   // replayed on collapse; -1 = not on screen
    private var m_ruleC:Number;   // perks-section rule, same replay contract
    private var perksHdrTF:TextField;
    private var perkSlots:Array;      // 6 boxes, each with an m_icon child
    private var perkLoaders:Array;    // one MovieClipLoader per slot
    private var perksShown:Boolean;
    private var perkRowY:Number;      // icon row top from the last layout
                                      // pass; hoverTick's hit test
    private var tipMC:MovieClip;      // perk-name chip, hidden until hovered
    private var tipTF:TextField;
    private var tipSlot:Number;       // slot the chip is drawn for, -1 = none
    private var mouseLsnr:Object;     // hover source; see hoverTick()

    // Subject / poll state
    private var m_Subject:Object;
    private var subjName:String;
    private var subjKey:String;
    private var subjIsPlayer:Number;  // 1 player, 0 not, -1 unanswered
    private var subjPlayer:Boolean;   // the isPlayer() gate, settled once a
                                      // pass — six call sites ask it
    private var aaOn:Boolean;         // +100-all-attrs AA visible on subject
    private var curPerks:Array;       // detected perks, table order, capped at 6
    private var curPerkRanks:Array;   // the same six slots as ranks, for names
    private var iconInst:Object;      // "i<buffId>" -> icon instance; static
                                      // game data, so read once not per pass
    private var pollIv:Number;
    private var curV:Object;      // stat id -> settled mode-2 value
    private var m1Str:Number;     // raw mode-1 804 / 814 — the pre-%-multiplier
    private var m1Dex:Number;     // attribute sum, CDI attr term only
    private var haveFull:Boolean;
    private var warmup:Number;
    private var previewMode:Boolean;
    private var active:Boolean;
    private var pvpShown:Boolean;

    // Render cache — assign only on change; TextField.text writes are the
    // expensive part and most 250 ms passes change nothing
    private var lastName:String;
    private var lastPve:String;
    private var lastPvp:String;
    private var lastPerks:String;

    private var watchIds:Array;
    private var gateIds:Array;
    private var SPELL_IDS:Array;
    private var CLASS_NAMES:Object;
    private var AA_BUFF_ID:Number;
    private var PERK_IDS:Object;      // "i<buffId>" -> display rank
    private var PERK_GEN_MAX:Number;  // last General rank
    private var PERK_ARCH_MAX:Number; // last Archetype rank
    private var PERK_2SLOT:Object;    // "r<rank>" -> costs both class slots
    private var PERK_NAMES:Array;     // rank -> perk name, for the hover chip
    private var PERK_EDGE:Array;      // per-slot-pair border colour
    private var PERK_FILL:Array;      // per-slot-pair plate colour
    private var DASH:String;

    public function KazBarsInspect(root:MovieClip) {
        super(root);
        m_Subject = null;
        subjName = "";
        subjKey = "";
        curV = {};
        m1Str = 0;
        m1Dex = 0;
        iconInst = {};
        subjPlayer = false;
        panelVis = false;
        perkRowY = 0;
        haveFull = false;
        warmup = 0;
        previewMode = false;
        active = true;
        pvpShown = false;
        lastName = "";
        lastPve = "";
        lastPvp = "";
        aaOn = false;
        curPerks = new Array();
        curPerkRanks = new Array();
        lastPerks = "";
        perksShown = false;
        tipSlot = -1;
        DASH = String.fromCharCode(8212);
        fullH = 0;
        subjIsPlayer = -1;
        // The baked tables — perk pool, names, class map, watch list — live in
        // KazBarsInspectData beside their measurement notes, the KazBarsData
        // arrangement; docs/inspect-panel.md is their contract.
        var d:Object = KazBarsInspectData.init();
        SPELL_IDS = d.spellIds;
        AA_BUFF_ID = Number(d.aaBuffId);
        PERK_IDS = d.perkIds;
        PERK_GEN_MAX = Number(d.perkGenMax);
        PERK_ARCH_MAX = Number(d.perkArchMax);
        PERK_2SLOT = d.perk2Slot;
        PERK_NAMES = d.perkNames;
        PERK_EDGE = d.perkEdge;
        PERK_FILL = d.perkFill;
        CLASS_NAMES = d.classNames;
        watchIds = d.watchIds;
        gateIds = d.gateIds;
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) return;
        START_X = Number(cfg.x);
        START_Y = Number(cfg.y);
        START_COLLAPSED = (cfg.collapsed == true);
        SHOW_PVP = (cfg.showPvp != false);
        SHOW_PERKS = (cfg.showPerks != false);
        // COLL_* from the base put the collapsed bar — a labelled bar, not a
        // folded sheet — beside the stopwatch's own at any size (190x24 at
        // the default FS 12).
        applyBaseSize(Number(cfg.fontSize));
        LEAD = Math.round(FS * 0.15);
        LABEL_W = Math.round(FS * 8.6);
        COL_GAP = Math.round(FS * 0.85);
        VALUE_W = Math.round(FS * 12);
        NAME_GAP = Math.round(FS * 0.5);
        SECT_GAP = Math.round(FS * 0.75);
        RULE_GAP = Math.round(FS * 0.2);
        ROWS_GAP = Math.round(FS * 0.4);
        ICO = Math.round(FS * 2.4);
        ICO_GAP = Math.round(FS * 0.35);
        TIP_PAD = Math.round(FS * 0.3);
        W = PAD * 2 + LABEL_W + COL_GAP + VALUE_W;
    }

    // The sheet's fields are multiline, no wrap — set here once so every field
    // the panel (or a base widget) builds carries the flavour.
    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = super.makeTF(parent, id, x, y, w, h, size, bold, col, align);
        tf.multiline = true;
        tf.wordWrap = false;
        return tf;
    }

    public function create():Void {
        // The host re-runs onLoad on this same instance; without this the old
        // interval and clip both leak.
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (panelClip != null) panelClip.removeMovieClip();
        panelClip = rootClip.createEmptyMovieClip("kbInspect", rootClip.getNextHighestDepth());
        panelClip._x = START_X;
        panelClip._y = START_Y;
        panelClip._visible = false;
        panelVis = false;

        collapsed = START_COLLAPSED;

        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        // Everything below the name strip, so collapsing is one _visible toggle.
        body = panelClip.createEmptyMovieClip("body", panelClip.getNextHighestDepth());

        nameTF = makeTF(panelClip, "name", PAD,
                        Math.floor((TITLE_H - Math.round(NAME_FS * 1.4)) / 2),
                        W - PAD * 2 - BTN, Math.round(NAME_FS * 1.4),
                        NAME_FS, true, 0xF7A22B, "left");
        // Collapsed, the bar carries a static label and nothing else — no
        // target name, so no reason for a pass to read one. Its own field
        // rather than a re-formatted name strip: a TextFormat swap per fold
        // would have to be re-applied to the text every time.
        collTF = makeCollapsedLabel("Inspect");
        collTF._visible = false;
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

        // Assigned once: absent data renders as the dash rather than dropping
        // a row, so layout() re-runs only on the PvP-visibility flip.
        pveLabTF.text = "Health\nArmor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nCritigation Chance\nCritigation Amount\nHeal Rating\nBonus Spell Dmg"
                      + "\nCombat Rating\nWeapon Dmg M/R\nCritical Chance\nCritical Damage"
                      + "\nTenacity\nFerocity";
        pvpLabTF.text = "Armor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nBonus Spell Dmg\nCombat Rating\nKills / Deaths";

        perksHdrTF = makeTF(body, "perksHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                            FS, true, 0xF7A22B, "left");
        perksHdrTF.autoSize = "left";
        perksHdrTF.text = "Perks";

        // Six slot boxes (the game's perk cap); an empty hairline box is the
        // row's em dash. Three levels on purpose: the box draws on the
        // unscaled slot, `hold` carries the scale, and the icon loads into
        // hold.m_icon. loadClip REPLACES its target clip and onLoadInit then
        // normalizes the arrival to 64x64 — so any scale set on the target
        // itself is overwritten, and the scale has to live on the parent.
        // Inset by 1 so the icon sits inside the border rather than over it.
        perkSlots = new Array();
        perkLoaders = new Array();
        var pi:Number = 0;
        while (pi < 6) {
            var ps:MovieClip = body.createEmptyMovieClip("perk" + pi, body.getNextHighestDepth());
            ps._x = PAD + pi * (ICO + ICO_GAP);
            var pair:Number = Math.floor(pi / 2);
            ps.beginFill(Number(PERK_FILL[pair]), 100);
            ps.lineStyle(1, Number(PERK_EDGE[pair]), 100);
            rectPath(ps, 0, 0, ICO, ICO);
            ps.endFill();
            var hold:MovieClip = ps.createEmptyMovieClip("hold", ps.getNextHighestDepth());
            hold._x = hold._y = 1;
            hold._xscale = hold._yscale = (ICO - 2) / 64 * 100;
            hold.createEmptyMovieClip("m_icon", hold.getNextHighestDepth());
            ps._ico = -1;
            ps._want = false;
            perkSlots.push(ps);
            perkLoaders.push(new MovieClipLoader());
            perkLoaders[pi].addListener(this);
            this["pcb" + pi] = mkPerkCB(pi);
            pi++;
        }
        // The clips are fresh even when the render cache is warm.
        lastPerks = "";

        // Re-seed from the cache: on a re-onLoad it is still warm, so
        // assign-on-change would write nothing and leave these blank.
        nameTF.text = lastName;
        pveValTF.text = lastPve;
        pvpValTF.text = lastPvp;

        makeCollapseBtn();

        // Perk-name chip, drawn last so it sits over the row it names. Opaque
        // where the plate is 90 — it lands on top of icons and a rule.
        tipMC = panelClip.createEmptyMovieClip("perkTip", panelClip.getNextHighestDepth());
        tipMC._visible = false;
        tipTF = makeTF(tipMC, "label", TIP_PAD, TIP_PAD, LABEL_W, Math.round(FS * 1.4),
                       FS, false, 0xC8C0B0, "left");
        tipTF.autoSize = "left";
        tipSlot = -1;
        // The hover source is a Mouse listener, NOT rollover handlers on the
        // slots: button handlers put a clip in button mode, and the row would
        // then swallow left clicks the way a whole-plate drag would. The fold
        // button and this hover are the panel's only interactive surfaces.
        // With the row baked off it is never installed at all — otherwise it
        // runs on every mouse move for a row that cannot render.
        if (SHOW_PERKS) {
            var selfM:KazBarsInspect = this;
            mouseLsnr = {onMouseMove: function() { selfM.hoverTick(); }};
            Mouse.addListener(mouseLsnr);
        }

        layout();

        var self:KazBarsInspect = this;
        pollIv = setInterval(function() { self.pollTick(); }, 250);
    }

    // =========================================================================
    // Layout / collapse
    // =========================================================================

    private function layout():Void {
        if (panelClip == null) return;
        var y:Number = TITLE_H + NAME_GAP;

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

        var rule3:Number = -1;
        perksHdrTF._visible = perksShown;
        var pi:Number = 0;
        while (pi < perkSlots.length) { perkSlots[pi]._visible = perksShown; pi++; }
        if (perksShown) {
            y += SECT_GAP;
            perksHdrTF._y = y;
            y += perksHdrTF._height + RULE_GAP;
            rule3 = y;
            y += 1 + ROWS_GAP;
            pi = 0;
            while (pi < perkSlots.length) { perkSlots[pi]._y = y; pi++; }
            perkRowY = y;   // hoverTick hit-tests against this, not the clip
            y += ICO;
        }
        fullH = y + PAD;
        m_ruleA = rule1;
        m_ruleB = rule2;
        m_ruleC = rule3;

        applyCollapsed();
    }

    public function toggleCollapsed():Void {
        super.toggleCollapsed();
        // Collapsed passes read the title ids only, so an expand has nothing
        // to paint from — take the full pass now rather than show a quarter
        // second of the sheet the panel was folded on.
        if (!collapsed && m_Subject != null) pollTick();
    }

    // The effective fold. Preview renders the sheet at full size whatever
    // the flag says: the plate IS the drag target, and the bar is too small
    // to aim at. The flag itself is untouched, so exiting preview folds it
    // back — and the top-left anchor means the position does not shift
    // either way.
    private function folded():Boolean {
        return collapsed && !previewMode;
    }

    // The two states are different plates, not one plate at two heights: the
    // sheet at W x fullH, and a labelled bar at COLL_W x COLL_H. The fold
    // button moves to whichever plate is on screen.
    private function applyCollapsed():Void {
        if (panelClip == null) return;
        hideTip();
        var eff:Boolean = folded();
        body._visible = !eff;
        nameTF._visible = !eff;
        collTF._visible = eff;
        collapseBtn.label.text = eff ? "+" : "-";
        curW = eff ? COLL_W : W;
        curH = eff ? COLL_H : fullH;
        var pad:Number = eff ? COLL_PAD : PAD;
        collapseBtn._x = curW - pad - BTN;
        collapseBtn._y = Math.floor(((eff ? COLL_H : TITLE_H) - BTN) / 2);
        drawChrome(curW, curH, eff ? -1 : m_ruleA, eff ? -1 : m_ruleB,
                   eff ? -1 : m_ruleC);
    }

    private function drawChrome(w:Number, h:Number, rule1:Number, rule2:Number,
                                rule3:Number):Void {
        drawPlate(w, h);
        // Title separator (expanded only — collapsed the bar IS the title
        // line), then the section-header rules; a negative offset means that
        // section is off screen (collapsed, or a target with no PvP block).
        if (h > COLL_H) {
            hairline(PAD, TITLE_H, W - PAD, TITLE_H);
        }
        if (rule1 >= 0) {
            hairline(PAD, rule1, W - PAD, rule1);
        }
        if (rule2 >= 0) {
            hairline(PAD, rule2, W - PAD, rule2);
        }
        if (rule3 >= 0) {
            hairline(PAD, rule3, W - PAD, rule3);
        }
    }

    // =========================================================================
    // Subject (Character first, Dynel wrapper fallback)
    // =========================================================================

    // Takes the raw tid, so clears and non-Character dynels both arrive here.
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
            m_Subject = subj;   // same entity re-targeted: keep the warm cache
            return;
        }
        m_Subject = subj;
        subjKey = k;
        subjName = safeName(subj);
        subjIsPlayer = classify(tid, subj);
        resetScan();
        updateVisibility();
    }

    // ID32 carries the engine's own classifiers. -1 means it never answered.
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
        m1Str = 0;
        m1Dex = 0;
        subjPlayer = false;
        aaOn = false;
        curPerks = new Array();
        curPerkRanks = new Array();
        lastName = "";
        lastPve = "";
        lastPvp = "";
        // Unloads the icons as well as resetting the key: a new subject with
        // no perks renders the same empty key the cache already holds, so
        // clearing the string alone would strand the old subject's icons.
        clearPerkSlots();
        // Preview keeps the plate on screen with no subject, and nothing
        // repaints until one settles: blank what the caches just forgot.
        if (previewMode) {
            nameTF.text = "";
            pveValTF.text = "";
            pvpValTF.text = "";
        }
    }

    // =========================================================================
    // Poll — the whole watch list every pass; the poll IS the settle re-read
    // =========================================================================

    public function pollTick():Void {
        if (!active) return;
        if (m_Subject == null) return;

        // Logout/zone collapses every id to 0 in one burst; id 1 and id 54
        // going together is that burst, not a stat change.
        if (haveFull && gv(1) != 0 && gv(54) != 0) {
            var t1 = null;
            var t54 = null;
            try { t1 = m_Subject.GetStat(1, 2); t54 = m_Subject.GetStat(54, 2); } catch (eT:Object) {}
            var z1:Boolean = (t1 == null || t1 == undefined || t1 == 0);
            var z54:Boolean = (t54 == null || t54 == undefined || t54 == 0);
            if (z1 && z54) {
                // Drop the dead handle: keeping it lets the warm-up count
                // three null passes and re-show a phantom all-dash sheet.
                m_Subject = null;
                subjKey = "";
                subjName = "";
                subjIsPlayer = -1;
                resetScan();
                updateVisibility();
                return;
            }
        }

        // Collapsed reads the teardown gate's two ids only; expanding runs a
        // full pass at once (toggleCollapsed), so the sheet is never stale.
        // Preview reads the full list whatever the fold state is — it shows the
        // sheet, so retargeting under the overlay has to fill it.
        var eff:Boolean = folded();
        var ids:Array = eff ? gateIds : watchIds;
        var i:Number = 0;
        while (i < ids.length) {
            var sid:Number = Number(ids[i]);
            var v = null;
            try { v = m_Subject.GetStat(sid, 2); } catch (e:Object) {}
            curV[sid] = v;
            i++;
        }
        if (!eff) {
            subjPlayer = evalPlayer();
            // Mode-1 side-reads: the CDI attr term uses the PRE-multiplier
            // attribute sum — mode 2 is post %-multiplier (a x1.05 Dex feat
            // moved m2 by 97x1.05 while m1 moved by the item's flat 97).
            var r1 = null;
            try { r1 = m_Subject.GetStat(804, 1); } catch (e1a:Object) {}
            m1Str = Number(r1);
            if (isNaN(m1Str)) m1Str = 0;
            r1 = null;
            try { r1 = m_Subject.GetStat(814, 1); } catch (e1b:Object) {}
            m1Dex = Number(r1);
            if (isNaN(m1Dex)) m1Dex = 0;
            // The buff-list pass: the AA's presence corrects the CDI attr
            // term, and any known perk buff feeds the Perks row. Both are
            // player-only — the AA rides an attribute term that is zero
            // without attributes, and the row is player-gated — so nothing
            // else walks the list. Bosses carry the longest buff lists in
            // the game and not one entry of one is ever ours.
            if (subjPlayer) {
                var aa:Boolean = false;
                var pk:Array = new Array();
                try {
                    var bl:Object = m_Subject.m_BuffList;
                    if (bl != null) {
                        for (var bk:String in bl) {
                            var bb:Object = bl[bk];
                            if (bb == null) continue;
                            if (bb.m_BuffId == AA_BUFF_ID) {
                                aa = true;
                                if (!SHOW_PERKS) break;
                            }
                            if (SHOW_PERKS) {
                                var bkey:String = "i" + bb.m_BuffId;
                                var rank = PERK_IDS[bkey];
                                if (rank != undefined) {
                                    // A buff's icon never changes, so the
                                    // engine answers this once per id per
                                    // session rather than 4x a second.
                                    var pin:Number = Number(iconInst[bkey]);
                                    if (isNaN(pin)) {
                                        pin = 0;
                                        try { pin = Number(bb.m_Icon.GetInstance()); } catch (eIc:Object) {}
                                        if (isNaN(pin)) pin = 0;
                                        if (pin > 0) iconInst[bkey] = pin;
                                    }
                                    pk.push({r: Number(rank), inst: pin});
                                }
                            }
                        }
                    }
                } catch (eBL:Object) {}
                aaOn = aa;
                if (SHOW_PERKS) {
                    var placed:Object = placePerks(pk);
                    curPerks = placed.inst;
                    curPerkRanks = placed.rank;
                }
            }
        }
        if (!haveFull) {
            // ~750 ms: login/zone/retarget repopulation settles inside it.
            warmup++;
            if (warmup < 3) return;
            haveFull = true;
        }
        render();
    }

    // =========================================================================
    // Stat access + sheet syntheses (field-measured, sheet-exact at level 80)
    // =========================================================================

    // Keyed by the raw id: a full render asks this ~195 times, and building
    // a key string per ask was the panel's largest source of AVM1 garbage.
    private function gv(sid:Number):Number {
        var v = curV[sid];
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

    // mode-1 attribute: the pre-%-multiplier additive sum, same encoding
    private function attrM1(raw:Number):Number {
        if (raw == 0) return 0;
        return Math.round((raw - 10) / 10);
    }

    // Gates the PvP block, the Perks row, the title's class name and every
    // player-only line; both signals must agree. IsPlayer() is measured
    // truthful on players but never sampled on a mob, so it vetoes rather
    // than confirms alone. Attributes must be DECODED — raw, an NPC template
    // carrying them at base reads 10, which put a PvP block on city guards.
    // Settled once a pass into subjPlayer: six call sites ask, and each ask
    // is four stat decodes.
    private function evalPlayer():Boolean {
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

    // The equipped weapon type is unreadable; characters stack their own
    // school's CR, so the largest component is it.
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

    // 3 x Str (Dex for the dagger class 34 and Rangers 39 — both named by
    // the sheet's own tooltip) + untyped 875 + equipped-school CR + every
    // typed magic CR; the PvP tab adds 225 on top. The attr term uses the
    // MODE-1 attribute (the pre-%-multiplier sum — the sheet's own basis,
    // two chars digit-exact) minus the +100-all-attrs AA (Immeasurable
    // Empowerment) when the subject's buff list shows it — the AA is
    // bugged in-game and never feeds this rating. Flat attr buffs other
    // than the AA still inflate the term.
    private function cdiPvE():Number {
        var c:Number = gv(67);
        var att:Number = (c == 34 || c == 39) ? attrM1(m1Dex) : attrM1(m1Str);
        if (aaOn) att -= 100;
        if (att < 0) att = 0;
        return 3 * att + gv(875) + gearSchoolCR() + gv(162) + gv(1007) + gv(1008) + gv(1009) + gv(1010);
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
        var s:String = gv(27) + " / " + gv(1);
        if (has(525)) s += " (" + gv(525) + "%)";
        return s;
    }

    private function mitLine(v:Number, invulId:Number, a:Number):String {
        if (v == 0) return DASH;
        return v + " (" + fmt1(sheetMit(mitCurve(v, a), invulId)) + "%)";
    }

    // zero-base linear decode (critigation, tenacity)
    private function pctLine(r:Number):String {
        if (r == 0) return DASH;
        return r + " (" + fmt1(pctOf(r)) + "%)";
    }

    // Rating share only: the sheet's per-character feat/AA base is absent from
    // stat space and not class-keyed, so inventing one would inflate this.
    private function critDmgLine():String {
        return pctLine(gv(711));
    }

    private function critChanceLine():String {
        var r:Number = gv(312);
        if (r == 0) return DASH;
        var wpnBase:Number = (gv(67) == 34) ? 5 : 2.5;
        return r + " (" + fmt1(r / 36.6 + wpnBase) + "%)";
    }

    // Rating + the Celestial Gaze range it buys (the main beneficiary):
    // 271 + HR x 0.2761 to 292 + HR x 0.2761. Player-only.
    private function healLine():String {
        if (!subjPlayer) return DASH;
        var r:Number = gv(713);
        if (r == 0) return DASH;
        return r + " (" + Math.round(271 + r * 0.2761) + "-" + Math.round(292 + r * 0.2761) + ")";
    }

    // 861 + schoolComponent + round(0.6 x mainAttr) + BaseSpellDamage% 1041.
    // Main attribute is max(Int, Wis) — priests lead on Wis, mages on Int —
    // avoiding an unmeasured class table, like the school CR above. Only the
    // highest school shows: a caster stacks exactly one. The PvP row adds the
    // per-school gap 226 on top — one value for all schools, the 458 shape.
    private function spellLine(add:Number):String {
        if (!subjPlayer) return DASH;
        // Mana-less classes (Ranger measured; Barbarian predicted) sheet the
        // whole per-school block at 0 even when 861/1041 carry residue —
        // max mana 507 is the gate.
        if (gv(507) == 0) return DASH;
        var best:Number = 0;
        var i:Number = 0;
        while (i < SPELL_IDS.length) {
            var v:Number = gv(Number(SPELL_IDS[i]));
            if (v > best) best = v;
            i++;
        }
        var attr:Number = Math.max(attrSheet(808), attrSheet(810));
        var total:Number = gv(861) + best + Math.round(attr * 0.6) + gv(1041) + add;
        if (total == 0) return DASH;
        return String(total);
    }

    // Sheet Ferocity = floor(1403/10), the x10-encoded gear component and
    // nothing else — a char with 1403=0 sheets Ferocity 0 even while the
    // old base candidate 864 reads 33 (864 is the engine's "Player Flags"
    // state id, not a rating). Effect is 0.15 x total on all five AOE
    // surfaces (sheet pair 260 -> 39.0%). Player-only.
    private function ferLine():String {
        if (!subjPlayer) return DASH;
        var t:Number = Math.floor(gv(1403) / 10);
        if (t == 0) return DASH;
        return t + " (" + fmt1(t * 0.15) + "%)";
    }

    // Weapon Damage % pair (1095 melee / 1096 ranged, x100) — the sheet's
    // Melee/Ranged values verbatim. No synthesis, no gates: stance and
    // proc swings and Reave-type feat multipliers are already inside the
    // ids. Dashed only when both are absent.
    private function wdLine():String {
        var m:Number = gv(1095);
        var r:Number = gv(1096);
        if (m == 0 && r == 0) return DASH;
        return fmt1(m / 100) + "% / " + fmt1(r / 100) + "%";
    }

    // rating + flat effect (the sheet's Effect column = the DPS add)
    private function cdiLine(add:Number):String {
        var r:Number = cdiPvE();
        if (r == 0) return DASH;
        r += add;
        return r + " (" + Math.round(r / 36.6) + ")";
    }

    // "Name Class (Level/PvPLevel)". Class only when the player gate agrees
    // AND id 67 maps (all twelve measured); the level part drops what is
    // absent, so a mob reads "Name (83)" and a PvP-level-0 player "Name (80)".
    private function titleLine():String {
        var s:String = subjName;
        if (subjPlayer) {
            var cn:String = CLASS_NAMES["c" + gv(67)];
            if (cn != undefined) s += " " + cn;
        }
        var lvl:Number = gv(54);
        if (lvl > 0) {
            var pl:Number = gv(70);
            s += " (" + lvl + ((pl > 0) ? ("/" + pl) : "") + ")";
        }
        return s;
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
        g.push(spellLine(0));
        g.push(cdiLine(0));
        g.push(wdLine());
        g.push(critChanceLine());
        g.push(critDmgLine());
        g.push(pctLine(gv(1000017)));
        g.push(ferLine());
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
        g.push(spellLine(gv(226)));
        g.push(cdiLine(gv(225)));
        g.push(gv(656) + " / " + gv(658));   // 0 / 0 is real data, not absence
        return g.join("\n");
    }

    // =========================================================================
    // Render / preview
    // =========================================================================

    private function render():Void {
        if (panelClip == null || m_Subject == null || !haveFull) {
            updateVisibility();
            return;
        }
        // Collapsed, the bar is a static label — nothing on it moves with the
        // target, so there is nothing to paint and nothing was read. In preview
        // the sheet is on screen at full size, so it paints like any other pass.
        if (folded()) {
            updateVisibility();
            return;
        }
        // Preview keeps the baked gates whatever the target allows, the same
        // ones previewOn laid out and sized the overlay to: a pass under the
        // overlay must not resize the plate the overlay is drawn over, and a
        // mob-to-player retarget mid-preview must not grow it out from under
        // a drag rect that was measured before.
        var wantPvp:Boolean = (previewMode || subjPlayer) && SHOW_PVP;
        var wantPerks:Boolean = (previewMode || subjPlayer) && SHOW_PERKS;
        if (wantPvp != pvpShown || wantPerks != perksShown) {
            pvpShown = wantPvp;
            perksShown = wantPerks;
            layout();
        }
        var t:String = titleLine();
        if (t != lastName) {
            lastName = t;
            nameTF.text = t;
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
        if (perksShown) renderPerks();
        updateVisibility();
    }

    // =========================================================================
    // Perks row — detected perk buffs as RDB icons in the game's own layout:
    // three colour-coded slot pairs, General / Archetype / Class
    // =========================================================================

    // Returns {inst, rank}, six entries each, -1 for an empty slot. Rank
    // order in (insertion sort over <= 6 live entries, rank-variant
    // duplicates collapsing to the first seen), then each perk drops into
    // its category's own pair the way the game's perk bar lays them out.
    // 0 is a real value here -- a perk whose buff carries no icon still
    // holds its slot -- so only -1 means empty. The rank rides along for the
    // hover chip: the icon instance does not identify the perk.
    private function placePerks(pk:Array):Object {
        var srt:Array = new Array();
        var i:Number = 0;
        while (i < pk.length) {
            var e:Object = pk[i];
            var j:Number = 0;
            var dup:Boolean = false;
            while (j < srt.length) {
                if (srt[j].r == e.r) { dup = true; break; }
                if (srt[j].r > e.r) break;
                j++;
            }
            if (!dup) srt.splice(j, 0, e);
            i++;
        }
        var out:Array = [-1, -1, -1, -1, -1, -1];
        var rnk:Array = [-1, -1, -1, -1, -1, -1];
        i = 0;
        while (i < srt.length) {
            var r:Number = srt[i].r;
            var b:Number = (r <= PERK_GEN_MAX) ? 0 : ((r <= PERK_ARCH_MAX) ? 2 : 4);
            // A pair holds two; anything beyond that is dropped rather than
            // spilling into the next category's colour. A two-slot perk
            // claims both boxes with the same icon, the way the game draws
            // it -- so it needs both free, or it is just the pair's second.
            if (out[b] == -1) {
                out[b] = srt[i].inst;
                rnk[b] = r;
                if (PERK_2SLOT["r" + r] != undefined && out[b + 1] == -1) {
                    out[b + 1] = srt[i].inst;
                    rnk[b + 1] = r;
                }
            } else if (out[b + 1] == -1) {
                out[b + 1] = srt[i].inst;
                rnk[b + 1] = r;
            }
            i++;
        }
        return {inst: out, rank: rnk};
    }

    // Assign-on-change like the value columns: the joined slot list is the
    // cache, and only slots whose icon actually changed reload. Ranks are in
    // the key too — two perks can share one icon, and the chip must not name
    // the one that left.
    private function renderPerks():Void {
        var key:String = curPerks.join(",") + "|" + curPerkRanks.join(",");
        if (key == lastPerks) return;
        lastPerks = key;
        hideTip();
        // Pass 1: settle every slot's target instance and drop stale art, so
        // pass 2 can see the whole row when it decides what to request.
        var i:Number = 0;
        while (i < perkSlots.length) {
            var s:MovieClip = perkSlots[i];
            var inst:Number = Number(curPerks[i]);
            if (isNaN(inst)) inst = -1;
            var rk:Number = Number(curPerkRanks[i]);
            s._rank = isNaN(rk) ? -1 : rk;
            if (s._ico != inst) {
                s._ico = inst;
                try { s.hold.m_icon.unloadMovie(); } catch (eU:Object) {}
                s._want = (inst > 0);
            }
            i++;
        }
        // Pass 2: one request per DISTINCT instance, one clip per answer.
        // RequestRDBImage answers a given id once -- a second request for an
        // id already in flight never calls back -- and a same-tick second
        // loadClip of one URL double-binds a shared movie def that the
        // retarget unload then releases twice: a client heap crash, isolated
        // in-game. So a dup slot KEEPS _want as its pending mark, and
        // onPerkIcon re-requests the id for it after the first answer lands
        // (the id is out of flight by then) -- sharers resolve as a chain of
        // single-clip loads. Dedup is only against instances requested on
        // THIS pass: a slot that kept its art issued no request, so it
        // cannot serve a partner that has just come to want the same
        // instance.
        var reqd:Array = new Array();
        i = 0;
        while (i < perkSlots.length) {
            var sl:MovieClip = perkSlots[i];
            if (sl._want) {
                var dup:Boolean = false;
                var j:Number = 0;
                while (j < reqd.length) {
                    if (reqd[j] == sl._ico) { dup = true; break; }
                    j++;
                }
                if (!dup) {
                    sl._want = false;
                    reqd.push(sl._ico);
                    try {
                        com.Utils.ImageLoader.RequestRDBImage(
                            new com.Utils.ID32(1010008, sl._ico), this, "pcb" + i);
                    } catch (eR:Object) {}
                }
            }
            i++;
        }
    }

    private function mkPerkCB(i:Number):Function {
        var self:KazBarsInspect = this;
        return function(url:String, ok:Boolean):Void { self.onPerkIcon(i, url, ok); };
    }

    private function onPerkIcon(i:Number, url:String, ok:Boolean):Void {
        var s:MovieClip = (perkSlots != null) ? MovieClip(perkSlots[i]) : null;
        if (s == null || s.hold == null) return;
        // The slot was cleared (or re-targeted) between request and answer;
        // only a positive instance was ever requested.
        if (!ok || url == null || url.length == 0 || s._ico <= 0) return;
        // One clip per answer -- NEVER loadClip one URL into two targets in
        // the same tick: the two binds share one movie def, the retarget
        // unload releases it twice, and the heap corruption crashes the
        // client an inspection later (isolated in-game via the serve-one
        // probe). The partner of a two-slot perk still holds _want, so chain
        // it: re-issue the request now that this answer took the id out of
        // flight, and its own callback paints it next.
        try { perkLoaders[i].loadClip(url, s.hold.m_icon); } catch (e:Object) {}
        var inst:Number = s._ico;
        var j:Number = 0;
        while (j < perkSlots.length) {
            var t:MovieClip = perkSlots[j];
            if (t != null && t._want && t._ico == inst) {
                t._want = false;
                try {
                    com.Utils.ImageLoader.RequestRDBImage(
                        new com.Utils.ID32(1010008, inst), this, "pcb" + j);
                } catch (eR:Object) {}
                break;
            }
            j++;
        }
    }

    // MovieClipLoader listener: standardize the loaded RDB icon to the 64x64
    // native size — the slot's m_icon container is pre-scaled to ICO/64, so
    // the icon lands exactly in the box.
    public function onLoadInit(mc:MovieClip):Void {
        if (mc == null) return;
        try {
            mc._xscale = mc._yscale = 100;
            var scale:Number = 6400 / Math.max(mc._width, mc._height);
            mc._xscale = mc._yscale = scale;
            mc.cacheAsBitmap = true;
        } catch (e:Object) {}
    }

    private function clearPerkSlots():Void {
        if (perkSlots == null) return;
        var i:Number = 0;
        while (i < perkSlots.length) {
            var s:MovieClip = perkSlots[i];
            s._ico = -1;
            s._rank = -1;
            s._want = false;
            try { s.hold.m_icon.unloadMovie(); } catch (e:Object) {}
            i++;
        }
        hideTip();
        lastPerks = "";
    }

    // Hover -> perk name. Driven by mouse movement rather than rollover
    // handlers so the row stays click-through (create()), and hit-tested
    // arithmetically in panel space: the boxes are a known pitch from PAD, so
    // no hitTest call and no dependence on where rootClip sits.
    public function hoverTick():Void {
        // Every mouse move, for the life of the module — and in combat the
        // camera drags the mouse continuously. So: cached AS state first
        // (the row is off screen for most of a session), and the native
        // _ymouse / _xmouse reads only for a pointer already in the panel.
        if (!perksShown || collapsed || previewMode || !panelVis) {
            hideTip();
            return;
        }
        if (panelClip == null || tipMC == null || perkSlots == null) return;
        var top:Number = perkRowY;
        var my:Number = panelClip._ymouse;
        if (my < top || my > top + ICO) {
            hideTip();
            return;
        }
        var pitch:Number = ICO + ICO_GAP;
        var mx:Number = panelClip._xmouse - PAD;
        var i:Number = Math.floor(mx / pitch);
        // The gaps between the boxes are not the boxes.
        if (i < 0 || i > 5 || mx - i * pitch > ICO) {
            hideTip();
            return;
        }
        showTip(i);
    }

    private function showTip(i:Number):Void {
        var r:Number = Number(perkSlots[i]._rank);
        if (isNaN(r) || r < 0 || PERK_NAMES[r] == undefined) {
            hideTip();
            return;
        }
        // Redraw only on a slot change; the pointer moves inside a box for
        // many frames, and renderPerks clears the cache when the row changes.
        if (tipSlot != i) {
            tipSlot = i;
            tipTF.text = String(PERK_NAMES[r]);
            var tw:Number = Math.round(tipTF._width) + TIP_PAD * 2;
            var th:Number = Math.round(tipTF._height) + TIP_PAD * 2;
            tipMC.clear();
            tipMC.beginFill(0x0C0A07, 100);
            rectPath(tipMC, 0, 0, tw, th);
            tipMC.endFill();
            tipMC.lineStyle(1, 0x4A3B22, 100);
            rectPath(tipMC, 0, 0, tw, th);
            // Centred over its icon, then clamped inside the plate — the
            // longest name is wider than a box and the end slots would hang
            // off the frame.
            var cx:Number = PAD + i * (ICO + ICO_GAP) + Math.round((ICO - tw) / 2);
            tipMC._x = Math.max(PAD, Math.min(cx, W - PAD - tw));
            tipMC._y = perkSlots[0]._y - th - TIP_PAD;
        }
        tipMC._visible = true;
    }

    // tipSlot >= 0 exactly when the chip is up, so an already-hidden chip
    // costs one compare rather than two property writes per mouse move.
    private function hideTip():Void {
        if (tipSlot < 0 || tipMC == null) return;
        tipSlot = -1;
        tipMC._visible = false;
    }

    public function previewKey():String { return "ins"; }
    public function previewLabel():String { return "Inspect Panel"; }

    // Master switch (preview control panel + archive): folds into the one
    // visibility gate, so live sheets and the preview sheet both obey it.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(shown:Boolean):Void {
        active = shown;
        updateVisibility();
    }

    private function updateVisibility():Void {
        if (panelClip == null) return;
        var vis:Boolean = active && (previewMode || (m_Subject != null && haveFull));
        if (vis != panelVis) {
            panelVis = vis;
            panelClip._visible = vis;
        }
        if (!vis) hideTip();
    }

    // The full-footprint sheet, live or empty: a target with a settled read
    // renders normally under the overlay (perks included, and a retarget
    // mid-preview follows), an untargeted panel shows the chrome and labels
    // with empty values. Sections follow the baked gates rather than what this
    // target happens to allow, so the footprint is the one being positioned.
    public function previewOn():Void {
        if (panelClip == null) return;
        previewMode = true;
        pvpShown = SHOW_PVP;
        perksShown = SHOW_PERKS;
        layout();
        // The gates just moved under the cache and the fields are rewritten
        // either way, so nothing may assign-on-change against a stale string.
        lastName = "";
        lastPve = "";
        lastPvp = "";
        lastPerks = "";
        if (m_Subject != null && haveFull) {
            // A full pass, not a render: entering preview folded shows a sheet
            // whose values were never read (collapsed passes take the gate ids
            // only), and waiting for the next tick is a quarter second of
            // dashes.
            pollTick();
        } else {
            nameTF.text = "";
            pveValTF.text = "";
            pvpValTF.text = "";
            clearPerkSlots();
        }
        updateVisibility();
        // Last: the overlay covers the whole plate, so it needs the height
        // layout() just settled.
        KazBarsPreview.attach({mc: panelClip, x: 0, y: 0, w: W, h: fullH,
                               label: "Inspect", color: 0xFF0066});
    }

    public function previewOff():Void {
        if (panelClip == null) return;
        previewMode = false;
        // Removed, never hidden: a hidden overlay would still take the clicks
        // this panel is supposed to let through — the fold button included.
        KazBarsPreview.detach(panelClip);
        // Force a live reassign: preview blanked the fields or showed sections
        // this target does not get.
        lastName = "";
        lastPve = "";
        lastPvp = "";
        lastPerks = "";
        if (m_Subject != null && haveFull) {
            applyCollapsed();
            render();
        } else {
            pvpShown = false;
            perksShown = false;
            layout();
            updateVisibility();
        }
    }

    // =========================================================================
    // Persistence (module config archive — permanent for every user)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || panelClip == null) return;
        var v:Object = config.FindEntry("inv");
        if (v !== undefined) setActive(v == 1);
        // Fold state first: the clamp has to measure the plate actually on
        // screen. Clamping a sheet against the collapsed bar's height let a
        // saved spot near the bottom edge hang off it.
        var c:Object = config.FindEntry("inc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
        var x:Object = config.FindEntry("inx");
        var y:Object = config.FindEntry("iny");
        if (x !== undefined && y !== undefined) {
            panelClip._x = KazBarsPanel.clampPos(Number(x), Stage.width - curW);
            panelClip._y = KazBarsPanel.clampPos(Number(y), Stage.height - curH);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null || panelClip == null) return;
        config.ReplaceEntry("inx", panelClip._x);
        config.ReplaceEntry("iny", panelClip._y);
        config.ReplaceEntry("inc", collapsed ? 1 : 0);
        config.ReplaceEntry("inv", active ? 1 : 0);
    }

    public function cleanup():Void {
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (perkLoaders != null) {
            var i:Number = 0;
            while (i < perkLoaders.length) {
                if (perkLoaders[i] != null) {
                    perkLoaders[i].removeListener(this);
                    perkLoaders[i] = null;
                }
                i++;
            }
            perkLoaders = null;
            perkSlots = null;
        }
        m_Subject = null;
        previewMode = false;
        if (panelClip != null) {
            panelClip.removeMovieClip();
            panelClip = null;
        }
    }
}
