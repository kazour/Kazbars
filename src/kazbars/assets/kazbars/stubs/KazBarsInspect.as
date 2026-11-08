// KazBarsInspect.as - The Inspect Panel: a combat sheet for your target in the visual language of the game's own
// inspect window. A HUD module on the shared runtime: World names the target (onTarget), the clock runs the poll (one
// 250 ms task, on only while there is a subject and the panel is shown, so idle costs nothing), and the subject's
// KazBarsEffects carries its perk buffs (watched by the perk ids alone, and only on a player). Runtime-drawn chrome
// and device-font text fields, so it needs no symbols; plate and fold come from KazBarsPanel.
//
// The sheet is the baked groups (d.INS.groups, rows, watch: the user's rows, or the Default sheet), each a header, a
// label column and a value column; every id read and every formula lives in KazBarsInspectRows (eng). This class
// drives the poll, lays the groups out and repaints only the columns whose text changed (the writes are the cost).
//
// The PvP tab: a PvP glyph in the title strip (a player target, expanded) swaps the sheet for the PvP view (d.INS.pvp:
// the game's PvP Combat tab less its taps, then the record lines), sections with column titles whose lines split at
// the rating into two columns, a negative value red as the game draws it. The view polls its own ids (pvp.ids); the
// pick is kept in the archive (inp). Its sections are groups like the sheet's, marked by their column list (c).
//
// Perks: a player target's slotted AA perks, at most six (2 General, 2 Archetype, 2 Class; some Class perks take both
// slots), as RDB icons in the game's colour-coded pairs. Hovering one names it, off a Mouse listener that is on only
// while the row is on screen (rollover handlers would put the slots in button mode and take the clicks).
//
// A HUD element: mouse-transparent in normal play but for the fold and PvP glyphs, dragged only in preview through the shared
// overlay (KazBarsPreview). X/Y and the fold state baked into config are the first session's; the archive keeps inx,
// iny, inc, inp and the master switch inv. Every size is Math.round(FS x ratio). Every engine call sits in a try.
class KazBarsInspect extends KazBarsPanel implements KazBarsModule {

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;

    // Geometry beyond the base set, each Math.round(FS x ratio).
    private var LABEL_W:Number;   // 8.6   label column (widened to the widest baked label)
    private var COL_GAP:Number;   // 0.85  label -> value gap
    private var VALUE_W:Number;   // 12.0  value column
    private var NAME_GAP:Number;  // 0.5   name -> first section header
    private var SECT_GAP:Number;  // 0.75  space above a section header
    private var RULE_GAP:Number;  // 0.2   header baseline -> 1px rule
    private var ROWS_GAP:Number;  // 0.4   rule -> first stat row
    private var ICO:Number;       // 2.4   perk icon box
    private var ICO_GAP:Number;   // 0.35  gap between perk icons
    private var TIP_PAD:Number;   // 0.3   perk-name chip padding, and its gap above the icon row
    private var COLA:Number;      // 5.5   a PvP section's first column -> its second
    private var TAB_W:Number;     // 2.4   the PvP glyph's box
    private var W:Number;         // 2 x PAD + LABEL_W + COL_GAP + VALUE_W

    // UI
    private var body:MovieClip;       // everything under the name strip: folding is one _visible
    private var panelVis:Boolean;     // mirrors panelClip._visible
    private var fullH:Number;
    private var footH:Number;         // the taller view's fullH on a player: what preview places and a load clamps
    private var nameTF:TextField;
    private var collTF:TextField;     // the collapsed bar's whole content

    // The stat model, and one section per group: index g on every array below is GROUPS[g].
    private var eng:KazBarsInspectRows;
    private var GROUPS:Array;         // [{n: name, p: player-only, c: column titles (a PvP section only)}, ...]
    private var gRows:Array;          // each group's baked rows
    private var hdrTF:Array;
    private var labTF:Array;
    private var valTF:Array;
    private var val2TF:Array;         // a PvP section's second column, null where it has one
    private var colTF:Array;          // a PvP section's column titles
    private var grpOn:Array;          // shown this pass
    private var lastVal:Array;        // the text each value column holds
    private var ruleY:Array;          // each header's rule from the last layout, -1 off
    private var m_ruleC:Number;       // the perks header's rule, the same way
    private var perksHdrTF:TextField;
    private var perkSlots:Array;      // 6 boxes, each with hold.m_icon
    private var perkLoaders:Array;    // one MovieClipLoader per slot
    private var perksShown:Boolean;
    private var perkRowY:Number;      // the icon row's top from the last layout: the hover's hit test
    private var tipMC:MovieClip;      // the perk-name chip, hidden until hovered
    private var tipTF:TextField;
    private var tipSlot:Number;       // the slot the chip is drawn for, -1 none
    private var mouseLsnr:Object;     // the hover source, while the perk row is on screen
    private var tabBtn:MovieClip;     // the PvP glyph
    private var pvpOn:Boolean;        // the PvP tab is picked

    // Runtime
    private var w:KazBarsWorld;
    private var kP:Object;            // the poll task
    private var fx:KazBarsEffects;    // the subject's effects while its perks are watched
    private var fxVer:Number;         // fx.ver the perks were last read at

    // Subject and poll state
    private var m_Subject:Object;     // the target's Character, null none
    private var subjN:Number;         // its instance id, 0 none
    private var subjName:String;
    private var subjIsPlayer:Number;  // 1 player, 0 not, -1 unanswered
    private var curPerks:Array;       // the six slots' icon instances, -1 empty
    private var curPerkRanks:Array;   // the same slots as ranks, for the names
    private var iconInst:Object;      // "i<buffId>" -> icon instance: static game data, read once
    private var haveFull:Boolean;
    private var warmup:Number;
    private var hasCdi:Boolean;       // a sheet row is the Combat Rating (the PvP view always carries it)
    private var nextWeapon:Number;    // getTimer() of the next weapon read: 3 s after a read, 0.5 s after a miss
    private var previewMode:Boolean;
    private var active:Boolean;

    // Render cache: assign only on change
    private var lastName:String;
    private var lastPerks:String;

    private var watchIds:Array;       // what an expanded pass reads (d.INS.watch)
    private var PVP_IDS:Array;        // what it reads on the PvP view (d.INS.pvp.ids)
    private var GATE:Array;           // what a folded pass reads: the teardown gate's two ids
    private var CLASS_NAMES:Object;
    private var PERK_IDS:Object;      // "i<buffId>" -> display rank
    private var PERK_FX:Object;       // buffId -> true: the Effects filter
    private var PERK_GEN_MAX:Number;  // last General rank
    private var PERK_ARCH_MAX:Number; // last Archetype rank
    private var PERK_2SLOT:Object;    // "r<rank>" -> takes both class slots
    private var PERK_NAMES:Array;     // rank -> perk name, for the chip
    private var PERK_EDGE:Array;      // per-pair border colour
    private var PERK_FILL:Array;      // per-pair plate colour

    public function KazBarsInspect(root:MovieClip) {
        super(root);
        m_Subject = null;
        subjN = 0;
        subjName = "";
        subjIsPlayer = -1;
        iconInst = {};
        panelVis = false;
        perkRowY = 0;
        haveFull = false;
        warmup = 0;
        hasCdi = false;
        nextWeapon = 0;
        previewMode = false;
        active = true;
        lastName = "";
        curPerks = [];
        curPerkRanks = [];
        lastPerks = "";
        perksShown = false;
        tipSlot = -1;
        fullH = 0;
        footH = 0;
        fxVer = -1;
        pvpOn = false;
        GATE = [1, 54];
        // The measured tables (perk pool, names, class map) live in KazBarsInspectData beside their notes; the stat
        // model and its formatters in KazBarsInspectRows.
        var d:Object = KazBarsInspectData.init();
        eng = new KazBarsInspectRows(d);
        PERK_IDS = d.perkIds;
        PERK_FX = {};
        for (var k:String in PERK_IDS) PERK_FX[k.substring(1)] = true;
        PERK_GEN_MAX = Number(d.perkGenMax);
        PERK_ARCH_MAX = Number(d.perkArchMax);
        PERK_2SLOT = d.perk2Slot;
        PERK_NAMES = d.perkNames;
        PERK_EDGE = d.perkEdge;
        PERK_FILL = d.perkFill;
        CLASS_NAMES = d.classNames;
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object, world:KazBarsWorld, clock:KazBarsClock):Void {
        w = world;
        kP = clock.add(pollTick, this, 250, true, 0);
        world.onTarget(onTarget, this);
        START_X = Number(cfg.x);
        START_Y = Number(cfg.y);
        START_COLLAPSED = (cfg.collapsed == true);
        // COLL_* from the base make the collapsed bar the family's at any size.
        applyBaseSize(Number(cfg.fontSize));
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
        COLA = Math.round(FS * 5.5);
        TAB_W = Math.round(FS * 2.4);
        W = PAD * 2 + LABEL_W + COL_GAP + VALUE_W;

        // `watch` is a method every AS2 object has, so the member is read by name.
        watchIds = cfg["watch"];
        PVP_IDS = cfg.pvp.ids;
        GROUPS = [];
        gRows = [];
        grpOn = [];
        lastVal = [];
        ruleY = [];
        hasCdi = false;
        addView(cfg.groups, cfg.rows, false);
        addView(cfg.pvp.groups, cfg.pvp.rows, true);
    }

    // A view's groups after the ones already held, each row into its group (g indexes the view's own groups).
    private function addView(gs:Array, rows:Array, pvp:Boolean):Void {
        var base:Number = GROUPS.length;
        var g:Number;
        for (g = 0; g < gs.length; g++) {
            GROUPS.push(pvp ? {n: gs[g].n, p: true, c: gs[g].c} : gs[g]);
            gRows.push([]);
            grpOn.push(false);
            lastVal.push("");
            ruleY.push(-1);
        }
        for (var i:Number = 0; i < rows.length; i++) {
            var r:Object = rows[i];
            g = Number(r.g);
            if (g >= 0 && g < gs.length) gRows[base + g].push(r);
            if (!pvp && r.f == "cdi") hasCdi = true;
        }
    }

    // The sheet's fields are multiline, no wrap: set here once so every field the panel builds carries it.
    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = super.makeTF(parent, id, x, y, w, h, size, bold, col, align);
        tf.multiline = true;
        tf.wordWrap = false;
        return tf;
    }

    // Runs again on the same instance when the host loads again, so it removes what a previous run left.
    public function create():Void {
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (panelClip != null) panelClip.removeMovieClip();
        panelClip = rootClip.createEmptyMovieClip("kbInspect", rootClip.getNextHighestDepth());
        panelClip._x = START_X;
        panelClip._y = START_Y;
        stageOn(true);
        panelClip._visible = false;
        panelVis = false;
        collapsed = START_COLLAPSED;

        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        body = panelClip.createEmptyMovieClip("body", panelClip.getNextHighestDepth());

        // One header, label column and value column per group. Labels are written once: absent data renders as
        // the dash rather than dropping a line, so layout() runs again only when a group shows or hides.
        hdrTF = [];
        labTF = [];
        valTF = [];
        val2TF = [];
        colTF = [];
        var g:Number;
        var k:Number;
        for (g = 0; g < GROUPS.length; g++) {
            var h:TextField = makeTF(body, "hdr" + g, PAD, 0, LABEL_W, LINE, FS, true, 0xF7A22B, "left");
            h.autoSize = "left";
            h.text = String(GROUPS[g].n);
            hdrTF.push(h);
            var lab:TextField = makeTF(body, "lab" + g, PAD, 0, LABEL_W, LINE, FS, false, 0xC8C0B0, "left");
            var val:TextField = makeTF(body, "val" + g, 0, 0, VALUE_W, LINE, FS, false, 0x7AC142, "left");
            lab.autoSize = "left";
            val.autoSize = "left";
            lab.text = KazBarsInspectRows.labels(gRows[g]);
            labTF.push(lab);
            valTF.push(val);
            // A PvP section: its column titles on the header's line (dim, like the game's), a second value column.
            var cols:Array = [];
            var c:Array = GROUPS[g].c;
            for (k = 0; c != undefined && k < c.length; k++) {
                var ct:TextField = makeTF(body, "col" + g + "_" + k, 0, 0, COLA, LINE, FS, false, 0x7F786C, "left");
                ct.autoSize = "left";
                ct.text = String(c[k]);
                cols.push(ct);
            }
            colTF.push(cols);
            val2TF.push((c != undefined && c.length > 1)
                ? makeTF(body, "vb" + g, 0, 0, VALUE_W, LINE, FS, false, 0x7AC142, "left") : null);
            if (val2TF[g] != null) val2TF[g].autoSize = "left";
            // The cache outlives a reload: seed the fresh fields from it, or assign-on-change leaves them blank.
            show(g, lastVal[g]);
        }

        // The label column is as wide as the widest label baked, never narrower than the ratio: a picked row list
        // can carry names the ratio was never sized for, and an overrun paints through the value beside it.
        for (g = 0; g < labTF.length; g++) {
            if (labTF[g]._width > LABEL_W) LABEL_W = Math.ceil(labTF[g]._width);
        }
        W = PAD * 2 + LABEL_W + COL_GAP + VALUE_W;
        var vx:Number = PAD + LABEL_W + COL_GAP;
        for (g = 0; g < valTF.length; g++) {
            valTF[g]._x = vx;
            if (val2TF[g] != null) val2TF[g]._x = vx + COLA;
            for (k = 0; k < colTF[g].length; k++) colTF[g][k]._x = vx + k * COLA;
        }

        nameTF = makeTF(panelClip, "name", PAD, Math.floor((TITLE_H - NAME_H) / 2), W - PAD * 2 - BTN - TAB_W,
                        NAME_H, NAME_FS, true, 0xF7A22B, "left");
        nameTF.text = lastName;
        // Folded, the bar is a static label and nothing else, so no pass reads a name for it.
        collTF = makeCollapsedLabel("Inspect");
        collTF._visible = false;

        perksHdrTF = makeTF(body, "perksHdr", PAD, 0, LABEL_W, LINE, FS, true, 0xF7A22B, "left");
        perksHdrTF.autoSize = "left";
        perksHdrTF.text = "Perks";

        // Six slot boxes; an empty box is the row's dash. Three levels: the box draws on the slot, `hold` carries
        // the scale, the icon loads into hold.m_icon (loadClip replaces its target and onLoadInit normalizes it to
        // 64x64, so a scale on the target itself would be lost). Inset by 1 to sit inside the border.
        perkSlots = [];
        perkLoaders = [];
        for (var pi:Number = 0; pi < 6; pi++) {
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
        }
        lastPerks = "";

        makeCollapseBtn();
        // The PvP glyph, left of the fold glyph: bold Body like it, lit while the tab is picked.
        tabBtn = panelClip.createEmptyMovieClip("btnPvp", panelClip.getNextHighestDepth());
        tabBtn._self = this;
        tabBtn.useHandCursor = true;
        var tl:TextField = makeTF(tabBtn, "label", 0, 0, TAB_W, LINE, FS, true, tabCol(), "center");
        tl.text = "PvP";
        tabBtn._x = W - PAD - BTN - TAB_W;
        tabBtn._y = Math.floor((TITLE_H - LINE) / 2);
        tabBtn.onRelease = function() { this._self.togglePvp(); };
        tabBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        tabBtn.onRollOut = function() { this.label.textColor = this._self.tabCol(); };

        // The perk-name chip, drawn last so it sits over the row it names; opaque, it lands on icons and a rule.
        tipMC = panelClip.createEmptyMovieClip("perkTip", panelClip.getNextHighestDepth());
        tipMC._visible = false;
        tipTF = makeTF(tipMC, "label", TIP_PAD, TIP_PAD, LABEL_W, LINE, FS, false, 0xC8C0B0, "left");
        tipTF.autoSize = "left";
        tipSlot = -1;

        measureFoot();
        layout();
        sync();
    }

    // =========================================================================
    // Layout / collapse
    // =========================================================================

    private function layout():Void {
        if (panelClip == null) return;
        var y:Number = TITLE_H;
        var first:Boolean = true;
        for (var g:Number = 0; g < GROUPS.length; g++) {
            var vis:Boolean = grpOn[g];
            hdrTF[g]._visible = vis;
            labTF[g]._visible = vis;
            valTF[g]._visible = vis;
            if (val2TF[g] != null) val2TF[g]._visible = vis;
            var k:Number;
            for (k = 0; k < colTF[g].length; k++) colTF[g][k]._visible = vis;
            ruleY[g] = -1;
            if (!vis) continue;
            y += first ? NAME_GAP : SECT_GAP;
            first = false;
            hdrTF[g]._y = y;
            for (k = 0; k < colTF[g].length; k++) colTF[g][k]._y = y;
            y += hdrTF[g]._height + RULE_GAP;
            ruleY[g] = y;
            y += 1 + ROWS_GAP;
            labTF[g]._y = y;
            valTF[g]._y = y;
            if (val2TF[g] != null) val2TF[g]._y = y;
            y += labTF[g]._height;
        }
        m_ruleC = -1;
        perksHdrTF._visible = perksShown;
        var pi:Number;
        for (pi = 0; pi < perkSlots.length; pi++) perkSlots[pi]._visible = perksShown;
        if (perksShown) {
            y += first ? NAME_GAP : SECT_GAP;
            perksHdrTF._y = y;
            y += perksHdrTF._height + RULE_GAP;
            m_ruleC = y;
            y += 1 + ROWS_GAP;
            for (pi = 0; pi < perkSlots.length; pi++) perkSlots[pi]._y = y;
            perkRowY = y;
            y += ICO;
        }
        fullH = y + PAD;
        applyCollapsed();
    }

    // Each view laid out as a player gets it, the taller kept: the PvP glyph swaps the view in play, so a plate placed
    // on one must leave room for the other. Leaves nothing shown, as create() found it.
    private function measureFoot():Void {
        var keep:Boolean = pvpOn;
        var g:Number;
        footH = 0;
        perksShown = true;
        for (var k:Number = 0; k < 2; k++) {
            pvpOn = (k == 1);
            for (g = 0; g < GROUPS.length; g++) grpOn[g] = want(g, true);
            layout();
            if (fullH > footH) footH = fullH;
        }
        pvpOn = keep;
        for (g = 0; g < GROUPS.length; g++) grpOn[g] = false;
        perksShown = false;
    }

    public function toggleCollapsed():Void {
        super.toggleCollapsed();
        // A folded pass reads the gate ids only, so an expand has nothing to paint from: a full pass now, not a
        // quarter second of the sheet the panel was folded on.
        if (!collapsed && m_Subject != null) pollTick();
    }

    // The fold in effect. Preview shows the whole sheet whatever the flag says: the plate is the drag target and the
    // bar too small to aim at. The flag is untouched, so leaving preview folds it back, at the same top-left.
    private function folded():Boolean {
        return collapsed && !previewMode;
    }

    // Two plates, not one at two heights: the sheet at W x fullH and a labelled bar at COLL_W x COLL_H. The glyph
    // moves to whichever is on screen.
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
        seatCollapseBtn(curW - (eff ? COLL_PAD : PAD) - BTN, eff ? COLL_H : TITLE_H);
        tabBtn._visible = !eff && perksShown;
        nameTF._width = W - PAD * 2 - BTN - (tabBtn._visible ? TAB_W : 0);
        drawPlate(curW, curH);
        // The title rule and the section rules, expanded only (a group not shown has no rule).
        if (!eff) {
            hairline(PAD, TITLE_H, W - PAD, TITLE_H);
            for (var g:Number = 0; g < ruleY.length; g++) {
                if (ruleY[g] >= 0) hairline(PAD, ruleY[g], W - PAD, ruleY[g]);
            }
            if (m_ruleC >= 0) hairline(PAD, m_ruleC, W - PAD, m_ruleC);
        }
        listen();
    }

    // =========================================================================
    // Subject: World's target
    // =========================================================================

    // World tells a new target, null for none, and the same one again when it fetched a fresh Character for it.
    public function onTarget(t:Object):Void {
        var n:Number = (t != null) ? w.tn : 0;
        if (n > 0 && n == subjN) {
            m_Subject = t;
            subjName = nameOf(t);
            return;
        }
        unwatchFx();
        if (!(n > 0)) {
            forget();
            return;
        }
        m_Subject = t;
        subjN = n;
        subjName = nameOf(t);
        subjIsPlayer = -1;
        var id:Object = w.tid;
        if (id != null && id.IsPlayer != undefined) {
            try { subjIsPlayer = (id.IsPlayer() == true) ? 1 : 0; } catch (e:Object) {}
        }
        resetScan();
        watchFx();
        sync();
        updateVisibility();
    }

    // No subject: the target cleared, or the logout and zone burst let it go.
    private function forget():Void {
        unwatchFx();
        m_Subject = null;
        subjN = 0;
        subjName = "";
        subjIsPlayer = -1;
        resetScan();
        sync();
        updateVisibility();
    }

    // Perks are a player's: a mob's buff list is never walked for them, nor anyone's while the panel is off.
    private function watchFx():Void {
        if (fx != null || !active || !(subjN > 0) || subjIsPlayer == 0) return;
        fx = w.effects(subjN);
        fxVer = -1;
        if (fx != null) fx.watch("ins", PERK_FX, null);
    }

    private function unwatchFx():Void {
        if (fx != null) fx.unwatch("ins");
        fx = null;
    }

    private function nameOf(t:Object):String {
        try { return String(t.GetName()); } catch (e:Object) {}
        return "?";
    }

    // The poll runs while there is a subject to read and the panel is shown.
    private function sync():Void {
        if (kP == null) return;
        if (active && m_Subject != null && panelClip != null) w.clock.go(kP);
        else w.clock.off(kP);
    }

    private function resetScan():Void {
        haveFull = false;
        warmup = 0;
        nextWeapon = 0;
        fxVer = -1;
        eng.reset();
        curPerks = [];
        curPerkRanks = [];
        lastName = "";
        var g:Number;
        for (g = 0; g < GROUPS.length; g++) lastVal[g] = "";
        // Unloads the icons too: a new subject with no perks renders the key the cache already holds, so clearing
        // the key alone would strand the old subject's icons.
        clearPerkSlots();
        // Preview keeps the plate up with no subject and nothing repaints until one settles: blank what the cache
        // just forgot.
        if (previewMode && nameTF != null) blank();
    }

    private function blank():Void {
        nameTF.text = "";
        for (var g:Number = 0; g < GROUPS.length; g++) show(g, "");
    }

    // =========================================================================
    // Poll: the whole watch list every pass; the poll is the settle re-read
    // =========================================================================

    public function pollTick():Void {
        if (m_Subject == null) return;
        // Logout and zoning take every id to 0 in one burst; max HP and level going together is that, not a change.
        if (haveFull && eng.gv(1) != 0 && eng.gv(54) != 0) {
            var t1 = null;
            var t54 = null;
            try { t1 = m_Subject.GetStat(1, 2); t54 = m_Subject.GetStat(54, 2); } catch (eT:Object) {}
            if ((t1 == null || t1 == 0) && (t54 == null || t54 == 0)) {
                forget();
                return;
            }
        }
        // Folded, the gate's two ids; preview shows the sheet whatever the fold, so it reads the whole list. The PvP
        // view reads its own.
        var eff:Boolean = folded();
        var ids:Array = eff ? GATE : viewIds();
        readIds(ids);
        if (!eff) {
            eng.subjPlayer = eng.evalPlayer(subjIsPlayer);
            // Both lists carry the player gate, so the verdict is this pass's; when it flips the view (an expand
            // after a fold, a player's attributes decoding late), the view render() draws reads its own ids now.
            if (viewIds() != ids) {
                ids = viewIds();
                readIds(ids);
            }
            if (eng.subjPlayer && fx != null && fx.ver != fxVer) {
                fxVer = fx.ver;
                readPerks();
            }
        }
        if (!haveFull) {
            // ~750 ms: a login, zone or retarget repopulates inside it.
            warmup++;
            if (warmup < 3) return;
            haveFull = true;
        }
        // After the warm-up on purpose: before it the stat cache (148) and the target's inventory are still
        // filling, and a read then would commit a wrong family for 3 s.
        if (!eff && (hasCdi || ids == PVP_IDS)) readWeapon();
        render();
    }

    // The ids the view on screen reads: the PvP view's on a player with the tab picked, else the sheet's.
    private function viewIds():Array {
        return (pvpOn && (eng.subjPlayer || previewMode)) ? PVP_IDS : watchIds;
    }

    private function readIds(ids:Array):Void {
        for (var i:Number = 0; i < ids.length; i++) {
            var sid:Number = Number(ids[i]);
            var v = null;
            try { v = m_Subject.GetStat(sid, 2); } catch (e:Object) {}
            eng.curV[sid] = v;
        }
    }

    // The perk buffs the subject's Effects holds, placed into the six slots.
    private function readPerks():Void {
        var pk:Array = [];
        var a:Array = fx.a;
        for (var i:Number = 0; i < a.length; i++) {
            var key:String = "i" + a[i].id;
            var rank = PERK_IDS[key];
            if (rank == undefined) continue;
            var pin:Number = Number(iconInst[key]);
            if (isNaN(pin)) {
                pin = 0;
                try { pin = Number(a[i].buff.m_Icon.GetInstance()); } catch (e:Object) {}
                if (isNaN(pin)) pin = 0;
                if (pin > 0) iconInst[key] = pin;
            }
            pk.push({r: Number(rank), inst: pin});
        }
        var placed:Object = placePerks(pk);
        curPerks = placed.inst;
        curPerkRanks = placed.rank;
    }

    // One-handed or two-handed main hand, for the Combat Rating's school. A two-hander sits in position 6 and leaves
    // the off hand (8) empty while slot bitmask 148 still sets bit 8 (256). Settled full passes only.
    //  - Bit 64 of 148 clear: no main hand (or not in yet), so no family and no school term: unknown, nothing built.
    //  - Set, an inventory whose slot 6 is still empty has not filled: unknown, tried again in 500 ms (a throw too).
    //  - A loaded inventory commits the family, read again at most every 3 s.
    private function readWeapon():Void {
        if ((eng.gv(148) & 64) == 0) {
            eng.twoHand = -1;
            return;
        }
        var now:Number = getTimer();
        if (now < nextWeapon) return;
        var th:Number = -1;
        try {
            var items = (new com.GameInterface.Inventory(new com.Utils.ID32(101, subjN))).m_Items;
            var mh = (items != null) ? items[6] : null;
            if (mh != null) th = (items[8] == null && (eng.gv(148) & 256) != 0) ? 1 : 0;
        } catch (eW:Object) { th = -1; }
        eng.twoHand = th;
        nextWeapon = now + ((th >= 0) ? 3000 : 500);
    }

    // "Name Class (Level/PvPLevel)": the class only when the player gate agrees and id 67 maps (all twelve
    // measured); the level part drops what is absent, so a mob reads "Name (83)".
    private function titleLine():String {
        var s:String = subjName;
        if (eng.subjPlayer) {
            var cn:String = CLASS_NAMES["c" + eng.gv(67)];
            if (cn != undefined) s += " " + cn;
        }
        var lvl:Number = eng.gv(54);
        if (lvl > 0) {
            var pl:Number = eng.gv(70);
            s += " (" + lvl + ((pl > 0) ? ("/" + pl) : "") + ")";
        }
        return s;
    }

    // =========================================================================
    // Render / preview
    // =========================================================================

    private function render():Void {
        if (panelClip == null || m_Subject == null || !haveFull || folded()) {
            updateVisibility();
            return;
        }
        // Preview keeps every group and the perks, as previewOn laid them out for the overlay, so a pass under it
        // never resizes the plate being dragged. Live, a player-only group and the perks show on a player only.
        var player:Boolean = previewMode || eng.subjPlayer;
        var changed:Boolean = (player != perksShown);
        var g:Number;
        for (g = 0; g < GROUPS.length; g++) {
            if (want(g, player) != grpOn[g]) changed = true;
        }
        if (changed) {
            for (g = 0; g < GROUPS.length; g++) grpOn[g] = want(g, player);
            perksShown = player;
            layout();
        }
        var t:String = titleLine();
        if (t != lastName) {
            lastName = t;
            nameTF.text = t;
        }
        for (g = 0; g < GROUPS.length; g++) {
            if (!grpOn[g]) continue;
            // A PvP section's lines come split at the rating: a tab between the columns, no brackets.
            var col:Boolean = (GROUPS[g].c != undefined);
            if (col) {
                eng.L = "\t";
                eng.R = "";
            }
            var s:String = eng.values(gRows[g]);
            if (col) {
                eng.L = " (";
                eng.R = ")";
            }
            if (s != lastVal[g]) {
                lastVal[g] = s;
                show(g, s);
            }
        }
        if (perksShown) renderPerks();
        updateVisibility();
    }

    // Whether group g shows: the view's own (the PvP view on a player with the tab picked, else the sheet), and a
    // player-only group on a player only.
    private function want(g:Number, player:Boolean):Boolean {
        return ((GROUPS[g].c != undefined) == (pvpOn && player)) && (!GROUPS[g].p || player);
    }

    // A group's values: the sheet's as one column, a PvP section's split into its columns.
    private function show(g:Number, s:String):Void {
        if (GROUPS[g].c == undefined) {
            valTF[g].text = s;
            return;
        }
        var a:Array = s.split("\n");
        var c0:Array = [];
        var c1:Array = [];
        for (var i:Number = 0; i < a.length; i++) {
            var p:Array = String(a[i]).split("\t");
            c0.push(p[0]);
            c1.push((p.length > 1) ? p[1] : "");
        }
        tint(valTF[g], c0);
        if (val2TF[g] != null) tint(val2TF[g], c1);
    }

    // A column, a negative value red as the game draws it: the field's own format over the whole text, then red
    // over each line that starts with a minus.
    private function tint(tf:TextField, l:Array):Void {
        tf.text = l.join("\n");
        var f:TextFormat = tf.getNewTextFormat();
        tf.setTextFormat(f);
        f.color = 0xE0503C;
        var at:Number = 0;
        for (var i:Number = 0; i < l.length; i++) {
            var n:Number = String(l[i]).length;
            if (String(l[i]).charAt(0) == "-") tf.setTextFormat(at, at + n, f);
            at += n + 1;
        }
    }

    // The PvP glyph: the other view, read at once (the views poll different ids).
    public function togglePvp():Void {
        pvpOn = !pvpOn;
        if (m_Subject != null) pollTick();
    }

    public function tabCol():Number {
        return pvpOn ? 0xF7A22B : 0xA89A86;
    }

    // =========================================================================
    // Perks: the game's own layout, three colour-coded pairs (General, Archetype, Class)
    // =========================================================================

    // {inst, rank}, six each, -1 empty. Rank order (insertion sort over at most a few entries, a rank seen twice
    // kept once), then each perk drops into its category's pair as the game's perk bar lays them out. 0 is a real
    // instance (a perk with no icon still holds its slot); the rank rides along for the chip.
    private function placePerks(pk:Array):Object {
        var srt:Array = [];
        var i:Number;
        for (i = 0; i < pk.length; i++) {
            var e:Object = pk[i];
            var j:Number = 0;
            var dup:Boolean = false;
            while (j < srt.length) {
                if (srt[j].r == e.r) { dup = true; break; }
                if (srt[j].r > e.r) break;
                j++;
            }
            if (!dup) srt.splice(j, 0, e);
        }
        var out:Array = [-1, -1, -1, -1, -1, -1];
        var rnk:Array = [-1, -1, -1, -1, -1, -1];
        for (i = 0; i < srt.length; i++) {
            var r:Number = srt[i].r;
            var b:Number = (r <= PERK_GEN_MAX) ? 0 : ((r <= PERK_ARCH_MAX) ? 2 : 4);
            // A pair holds two; more is dropped rather than spilling into the next colour. A two-slot perk takes
            // both boxes with one icon, as the game draws it, so it needs both free, or it is the pair's second.
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
        }
        return {inst: out, rank: rnk};
    }

    // Assign-on-change like the columns: the joined slots are the cache, and only a slot whose icon changed loads
    // again. The ranks are in the key: two perks can share an icon, and the chip must not name the one that left.
    private function renderPerks():Void {
        var key:String = curPerks.join(",") + "|" + curPerkRanks.join(",");
        if (key == lastPerks) return;
        lastPerks = key;
        hideTip();
        // Pass 1: each slot's instance, stale art dropped, so pass 2 sees the whole row.
        var i:Number;
        for (i = 0; i < perkSlots.length; i++) {
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
        }
        // Pass 2: one request per distinct instance, one clip per answer. RequestRDBImage answers an id once (a
        // second request while it is in flight never calls back), and two loadClips of one URL in one tick
        // double-bind a movie def the retarget unload then frees twice: a client crash. So a slot sharing an
        // instance keeps _want, and onPerkIcon requests the id again for it once the first answer is in.
        var reqd:Array = [];
        for (i = 0; i < perkSlots.length; i++) {
            var sl:MovieClip = perkSlots[i];
            if (!sl._want) continue;
            var dup:Boolean = false;
            for (var j:Number = 0; j < reqd.length; j++) {
                if (reqd[j] == sl._ico) { dup = true; break; }
            }
            if (dup) continue;
            sl._want = false;
            reqd.push(sl._ico);
            try {
                com.Utils.ImageLoader.RequestRDBImage(new com.Utils.ID32(1010008, sl._ico), this, "pcb" + i);
            } catch (eR:Object) {}
        }
    }

    private function mkPerkCB(i:Number):Function {
        var self:KazBarsInspect = this;
        return function(url:String, ok:Boolean):Void { self.onPerkIcon(i, url, ok); };
    }

    private function onPerkIcon(i:Number, url:String, ok:Boolean):Void {
        var s:MovieClip = (perkSlots != null) ? MovieClip(perkSlots[i]) : null;
        if (s == null || s.hold == null) return;
        // Cleared or retargeted since the request; only a positive instance was ever requested.
        if (!ok || url == null || url.length == 0 || s._ico <= 0) return;
        try { perkLoaders[i].loadClip(url, s.hold.m_icon); } catch (e:Object) {}
        // A partner slot still wanting this instance (a two-slot perk) asks again now the id is out of flight.
        var inst:Number = s._ico;
        for (var j:Number = 0; j < perkSlots.length; j++) {
            var t:MovieClip = perkSlots[j];
            if (t != null && t._want && t._ico == inst) {
                t._want = false;
                try {
                    com.Utils.ImageLoader.RequestRDBImage(new com.Utils.ID32(1010008, inst), this, "pcb" + j);
                } catch (eR:Object) {}
                break;
            }
        }
    }

    // MovieClipLoader listener: the RDB icon at its 64x64 native size; the slot's hold is scaled to the box.
    public function onLoadInit(mc:MovieClip):Void {
        if (mc == null) return;
        try {
            mc._xscale = mc._yscale = 100;
            mc._xscale = mc._yscale = 6400 / Math.max(mc._width, mc._height);
            mc.cacheAsBitmap = true;
        } catch (e:Object) {}
    }

    private function clearPerkSlots():Void {
        if (perkSlots == null) return;
        for (var i:Number = 0; i < perkSlots.length; i++) {
            var s:MovieClip = perkSlots[i];
            s._ico = -1;
            s._rank = -1;
            s._want = false;
            try { s.hold.m_icon.unloadMovie(); } catch (e:Object) {}
        }
        hideTip();
        lastPerks = "";
    }

    // The hover source is on only while the perk row is on screen: in combat the camera drags the mouse all the
    // time, and a listener for a row that cannot show would run on every move.
    private function listen():Void {
        var want:Boolean = perksShown && panelVis && !folded() && !previewMode;
        if (want == (mouseLsnr != null)) return;
        if (want) {
            var self:KazBarsInspect = this;
            mouseLsnr = {onMouseMove: function() { self.hoverTick(); }};
            Mouse.addListener(mouseLsnr);
        } else {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
            hideTip();
        }
    }

    // Hover -> perk name, hit-tested arithmetically in panel space (the boxes sit a known pitch from PAD); the
    // pointer is read only once it is inside the row's band.
    public function hoverTick():Void {
        if (panelClip == null || tipMC == null || perkSlots == null) return;
        var my:Number = panelClip._ymouse;
        if (my < perkRowY || my > perkRowY + ICO) {
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
        // Drawn again only for another slot; renderPerks clears the cache when the row changes.
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
            // Centred over its icon, kept inside the plate: the longest name is wider than a box.
            var cx:Number = PAD + i * (ICO + ICO_GAP) + Math.round((ICO - tw) / 2);
            tipMC._x = Math.max(PAD, Math.min(cx, W - PAD - tw));
            tipMC._y = perkRowY - th - TIP_PAD;
        }
        tipMC._visible = true;
    }

    // tipSlot >= 0 exactly while the chip is up, so a hidden chip costs one compare.
    private function hideTip():Void {
        if (tipSlot < 0 || tipMC == null) return;
        tipSlot = -1;
        tipMC._visible = false;
    }

    public function previewKey():String { return "ins"; }
    public function previewLabel():String { return "Inspect Target"; }

    // The master switch (control panel and archive), folded into the one visibility gate.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(wantActive:Boolean):Void {
        active = wantActive;
        if (active) watchFx();
        else unwatchFx();
        sync();
        updateVisibility();
    }

    private function updateVisibility():Void {
        if (panelClip == null) return;
        var vis:Boolean = active && (previewMode || (m_Subject != null && haveFull));
        if (vis != panelVis) {
            panelVis = vis;
            panelClip._visible = vis;
        }
        listen();
    }

    // The whole footprint, live or empty: a settled target renders under the overlay (and a retarget follows), no
    // target shows the chrome and labels with empty values. The picked view's every group and the perks show,
    // whatever the target allows, and the overlay spans the taller view (footH), so the footprint being placed
    // holds either.
    public function previewOn():Void {
        if (panelClip == null) return;
        previewMode = true;
        var g:Number;
        for (g = 0; g < GROUPS.length; g++) grpOn[g] = want(g, true);
        perksShown = true;
        layout();
        // The gates moved under the cache and every field is written either way.
        lastName = "";
        for (g = 0; g < GROUPS.length; g++) lastVal[g] = "";
        lastPerks = "";
        if (m_Subject != null && haveFull) {
            // A full pass, not a render: a sheet entered folded was never read (folded passes take the gate only).
            pollTick();
        } else {
            blank();
            clearPerkSlots();
        }
        updateVisibility();
        // Last: the overlay covers the plate at the height layout() just settled.
        KazBarsPreview.attach({mc: panelClip, x: 0, y: 0, w: W, h: footH, label: "Inspect", color: 0xFF0066});
    }

    public function previewOff():Void {
        if (panelClip == null) return;
        previewMode = false;
        // Removed, never hidden: a hidden overlay still takes the clicks this panel lets through.
        KazBarsPreview.detach(panelClip);
        // Preview blanked the fields or showed sections this target does not get: write everything again.
        lastName = "";
        var g:Number;
        for (g = 0; g < GROUPS.length; g++) lastVal[g] = "";
        lastPerks = "";
        if (m_Subject != null && haveFull) {
            applyCollapsed();
            // A pass, not a render: preview read the view a player gets, and a mob's sheet has not been read since.
            pollTick();
        } else {
            for (g = 0; g < GROUPS.length; g++) grpOn[g] = want(g, false);
            perksShown = false;
            layout();
            updateVisibility();
        }
    }

    // =========================================================================
    // Persistence (the module archive)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || panelClip == null) return;
        var v:Object = config.FindEntry("inv");
        if (v !== undefined) setActive(v == 1);
        var p:Object = config.FindEntry("inp");
        if (p !== undefined) {
            pvpOn = (p == 1);
            tabBtn.label.textColor = tabCol();
        }
        // The fold first: the clamp measures the plate on screen, folded, or else the footprint preview places.
        var c:Object = config.FindEntry("inc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
        var x:Object = config.FindEntry("inx");
        var y:Object = config.FindEntry("iny");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
            seat();
        }
    }

    // The fold in effect, or else the footprint preview places.
    private function seatH():Number {
        return folded() ? curH : footH;
    }

    // The spot, not the clamp (KazBarsPanel.seat); a preview drag moved the plate, and that is the spot now.
    public function saveState(config:Object):Void {
        if (config == null || panelClip == null) return;
        keepSpot();
        config.ReplaceEntry("inx", posX);
        config.ReplaceEntry("iny", posY);
        config.ReplaceEntry("inc", collapsed ? 1 : 0);
        config.ReplaceEntry("inv", active ? 1 : 0);
        config.ReplaceEntry("inp", pvpOn ? 1 : 0);
    }

    // The subject goes (World tells the target again on the next start); World's subscription stays, made once.
    public function cleanup():Void {
        forget();
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (perkLoaders != null) {
            for (var i:Number = 0; i < perkLoaders.length; i++) perkLoaders[i].removeListener(this);
            perkLoaders = null;
            perkSlots = null;
        }
        previewMode = false;
        stageOn(false);
        if (panelClip != null) {
            panelClip.removeMovieClip();
            panelClip = null;
        }
    }
}
