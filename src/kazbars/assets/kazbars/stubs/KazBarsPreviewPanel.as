// KazBarsPreviewPanel.as - Preview-mode control panel: one checkbox per grid
// and one per compiled-in extra, so a single overlay can be isolated while it
// is being positioned.
//
// Chrome and palette are the family's, inherited from KazBarsPanel (and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, bronze hairline rules, square corners. Like
// the console, every dimension is a ratio of a base font size rather than a
// baked FS-12 number. It does not fold — it only exists while preview mode is
// on, and folding a panel whose whole job is showing which things are hidden
// would hide the answer.
//
// Rows are rebuilt on every preview entry, each one seeded from what the item
// is actually doing right now, and a box IS that item's master switch: unchecked
// survives the exit and the relog. The panel itself stays stateless — the owner
// persists the grid flags (g<i>_v) and each stub persists its own (swv/inv/ctv/
// cnv). Its own drag position rides in the module config archive as ppx/ppy,
// beside the other panels' keys.
class KazBarsPreviewPanel extends KazBarsPanel {
    // The panel<->core contract: the core drives every stub through its typed
    // lifecycle calls (configure / create* / loadState / saveState / cleanup /
    // isActive / setActive / previewOn / previewOff and the per-stub feeds);
    // the ONE call that flows back is owner.previewToggle(key, shown), routed
    // from an extra row's checkbox. Typed, not an interface: KazBars is
    // generated into the same compile unit, so MTASC checks the call for free.
    private var owner:KazBars;
    private var titleTF:TextField;
    // {obj, key, label, checked, cb} — obj set for grids, key for extras.
    private var rows:Array;

    // Layout beyond the base set, plus the row grid. Columns wrap at
    // MAX_PER_COL so a 64-grid build stays on the Stage.
    private var FS_REQ:Number;    // the size configure() was given, before any fit clamp
    private var ROW_H:Number;     // 1.667
    private var BTN_Y:Number;
    private var ROWS_Y:Number;
    private var COL_W:Number;     // 18.33
    private var MAX_PER_COL:Number;   // a row count, not a size — never scaled

    public function KazBarsPreviewPanel(kb:KazBars, root:MovieClip) {
        super(root);
        owner = kb;
        rows = new Array();
        MAX_PER_COL = 16;
        // Nothing has to call configure() for the panel to be usable, so it
        // seeds itself at the default size here rather than leaving every
        // constant NaN until someone does.
        configure(null);
    }

    // =========================================================================
    // Setup
    // =========================================================================

    // Mirrors KazBarsStopwatch/KazBarsInspect, minus their bail-on-null: those
    // two are always configured before they build, this one is not.
    public function configure(cfg:Object):Void {
        if (cfg == null) cfg = {};
        FS_REQ = Number(cfg.fontSize);
        if (isNaN(FS_REQ) || FS_REQ < 8) FS_REQ = 12;
        applySize(FS_REQ);
    }

    // Split out of configure() because show() re-runs it a notch smaller when the
    // row count would walk the panel off the Stage: the requested size has to
    // survive that, so the next entry starts from it again rather than from
    // whatever the last one's grid count clamped it to.
    private function applySize(size:Number):Void {
        applyBaseSize(size);
        ROW_H = Math.round(FS * 1.667);
        BTN_Y = TITLE_H + Math.round(FS * 0.5);
        ROWS_Y = BTN_Y + BTN_H + Math.round(FS * 0.85);
        COL_W = Math.round(FS * 18.33);
        measure(1, 0);
    }

    // The panel's footprint for a given row layout — the one place cols/rows
    // become a width and a height, so the fit loop in show() and the empty seed
    // in applySize() can't drift apart.
    private function measure(cols:Number, rowsInCol:Number):Void {
        curW = PAD * 2 + cols * COL_W;
        curH = ROWS_Y + rowsInCol * ROW_H + PAD;
    }

    // =========================================================================
    // Row collection — begin() then one add per thing that can be hidden
    // =========================================================================

    // Rows are rebuilt from scratch every entry and each add seeds its check
    // from live state, so the panel never carries a stale flag between entries.
    public function begin():Void {
        rows = new Array();
    }

    public function addGrid(obj:Object):Void {
        rows.push({obj: obj, key: null, label: String(obj.cfg.id),
                   checked: (obj.shown == true), cb: null});
    }

    public function addExtra(label:String, key:String, checked:Boolean):Void {
        rows.push({obj: null, key: key, label: label, checked: (checked == true), cb: null});
    }

    // =========================================================================
    // Build
    // =========================================================================

    public function show():Void {
        if (panelClip != null) panelClip.removeMovieClip();
        panelClip = rootClip.createEmptyMovieClip("kbPPanel", rootClip.getNextHighestDepth());

        var self:KazBarsPreviewPanel = this;

        var cols:Number = Math.max(1, Math.ceil(rows.length / MAX_PER_COL));
        var firstCol:Number = Math.min(rows.length, MAX_PER_COL);

        // This is the only panel whose footprint grows with content — one row
        // per grid, a fresh column every MAX_PER_COL — so a size that suits a
        // three-grid build walks a sixty-grid one off the screen. It steps its
        // own size down until it fits rather than the shared range being cut
        // for everyone. Rows are rebuilt on every preview entry from the
        // requested size, so this is self-correcting and can never strand a
        // user with a panel they cannot reach.
        applySize(FS_REQ);
        measure(cols, firstCol);
        while (FS > 8 && (curW > Stage.width || curH > Stage.height)) {
            applySize(FS - 1);
            measure(cols, firstCol);
        }

        // Chrome is its own child clip, the family's arrangement — it can be
        // cleared and redrawn without taking the contents with it.
        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        drawChrome(curW, curH);

        titleTF = makeTF(panelClip, "title", PAD, Math.floor((TITLE_H - (LINE + 4)) / 2),
                         curW - PAD * 2, LINE + 4, NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "Control Panel";

        // Live position readout — visible only while dragging, the panel's
        // convention. Shares the title line, right-aligned.
        coordTF = makeTF(panelClip, "coords", PAD, Math.floor((TITLE_H - LINE) / 2),
                         curW - PAD * 2, LINE,
                         Math.max(9, Math.round(FS * 0.8)), false, 0x999999, "right");
        coordTF._visible = false;

        var btnAll:MovieClip = makeButton(panelClip, "btnAll", "All", PAD, BTN_Y,
                                          Math.max(9, Math.round(FS * 0.9)));
        btnAll.onRelease = function() { self.setAll(true); };
        var btnNone:MovieClip = makeButton(panelClip, "btnNone", "None", PAD + BTN_W + 8,
                                           BTN_Y, Math.max(9, Math.round(FS * 0.9)));
        btnNone.onRelease = function() { self.setAll(false); };

        var i:Number = 0;
        while (i < rows.length) {
            var r:Object = rows[i];
            var c:Number = Math.floor(i / MAX_PER_COL);
            r.cb = makeRowCheckbox("row" + i, PAD + c * COL_W,
                                   ROWS_Y + (i % MAX_PER_COL) * ROW_H,
                                   r.label, r.checked, COL_W - BOX - 14, COL_W - 8);
            // AS2 shares one activation record across the whole while loop, so
            // the row has to travel on the clip rather than in the closure.
            r.cb.hit._row = r;
            r.cb.hit._self = this;
            r.cb.hit.onPress = function() { this._self.toggleRow(this._row); };
            i++;
        }

        // The whole title band drags — there is no collapse glyph to leave room
        // for, and nothing else lives up there.
        makeDragStrip("dh");
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, curW, TITLE_H);
        dragMC.endFill();

        // Placed last: the clamp has to measure the plate actually on screen.
        // First open sits clear of the console's own default y.
        panelClip._x = isNaN(posX) ? (Stage.width - curW) / 2
                                   : clampPos(posX, Stage.width - curW);
        panelClip._y = isNaN(posY) ? 100 : clampPos(posY, Stage.height - curH);
    }

    // =========================================================================
    // Checks
    // =========================================================================

    public function setAll(shown:Boolean):Void {
        var i:Number = 0;
        while (i < rows.length) {
            var r:Object = rows[i];
            r.checked = shown;
            r.cb.chk._visible = shown;
            applyRow(r);
            i++;
        }
    }

    public function toggleRow(r:Object):Void {
        r.checked = !r.checked;
        r.cb.chk._visible = r.checked;
        applyRow(r);
    }

    // The one dispatch point: a grid is its clip, an extra is a key the owner
    // knows how to route to whichever stub it belongs to.
    private function applyRow(r:Object):Void {
        if (r.obj != null) { r.obj.shown = r.checked; r.obj.mc._visible = r.checked; }
        else owner.previewToggle(r.key, r.checked);
    }

    // =========================================================================
    // Chrome / widgets
    // =========================================================================

    private function drawChrome(w:Number, h:Number):Void {
        drawPlate(w, h);
        // Bronze hairlines under the title and under the All/None pair — the
        // panel's section rules separating the header, the masters, the rows.
        chrome.lineStyle(1, 0x6B5324, 100);
        chrome.moveTo(PAD, TITLE_H);
        chrome.lineTo(w - PAD, TITLE_H);
        chrome.moveTo(PAD, ROWS_Y - 5);
        chrome.lineTo(w - PAD, ROWS_Y - 5);
    }

    // Base box/tick/hit plus this panel's label: its width is a parameter, not
    // the console's fixed 80 — a grid id gets the rest of its column. Its own
    // name because MTASC will not override the base makeCheckbox with a
    // different signature.
    private function makeRowCheckbox(name:String, x:Number, y:Number, label:String,
                                     checked:Boolean, labelW:Number, hitW:Number):MovieClip {
        var c:MovieClip = makeCheckbox(panelClip, name, x, y, checked, hitW);
        var lbl:TextField = makeTF(c, "lbl", BOX + 6, -3, labelW, LINE,
                                   Math.max(9, Math.round(FS * 0.8)), false,
                                   0xC8C0B0, "left");
        lbl.text = label;
        return c;
    }

    // =========================================================================
    // Persistence
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null) return;
        var x:Object = config.FindEntry("ppx");
        var y:Object = config.FindEntry("ppy");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        capturePos();
        if (isNaN(posX) || isNaN(posY)) return;
        config.ReplaceEntry("ppx", posX);
        config.ReplaceEntry("ppy", posY);
    }

    // Preview is over: the clip goes, and the rows go with it so no stale grid
    // object reference outlives the grids it points at.
    public function destroy():Void {
        capturePos();
        if (panelClip != null) { panelClip.removeMovieClip(); panelClip = null; }
        chrome = null; dragMC = null; titleTF = null; coordTF = null;
        rows = new Array();
    }
}
