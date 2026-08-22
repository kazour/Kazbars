// KazBarsPreviewPanel.as - Preview-mode control panel: one checkbox per grid
// and one per compiled-in extra, so a single overlay can be isolated while it
// is being positioned. Rows sit under three section headers — Player Grids,
// Target Grids, Tools — and a dim footer carries the exit keybind, the
// /reloadui recipe and the version credit, so the panel also orients a user
// who has never seen preview mode before.
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
// survives the exit and the relog. A header is its group's master: one click
// checks the group, another unchecks it. The panel itself stays stateless — the
// owner persists the grid flags (g<i>_v) and each stub persists its own (swv/
// inv/ctv/cnv). Its own drag position rides in the module config archive as
// ppx/ppy, beside the other panels' keys.
class KazBarsPreviewPanel extends KazBarsPanel {
    // The one call that flows back to the core (the contract note atop
    // KazBarsPanel): owner.previewToggle(key, shown), routed from an extra
    // row's checkbox. Typed, not an interface — KazBars is generated into the
    // same compile unit, so MTASC checks the call for free.
    private var owner:KazBars;
    private var titleTF:TextField;
    // Three fixed groups [{label, rows}]; a row is {obj, key, label, checked,
    // cb} — obj set for grids, key for extras. addGrid buckets by the grid's
    // cfg.type, addExtra lands in Tools; a group nothing landed in emits no
    // header. Group order here IS the panel's section order.
    private var groups:Array;
    private var ver:String;   // app version for the footer credit (d.PF.version)

    // Layout beyond the base set, plus the row grid. Columns wrap at
    // MAX_PER_COL so a 64-grid build stays on the Stage.
    private var FS_REQ:Number;    // the size configure() was given, before any fit clamp
    private var ROW_H:Number;     // 1.667
    private var BTN_Y:Number;
    private var ROWS_Y:Number;
    private var COL_W:Number;     // 18.33
    private var HDR_GAP:Number;   // 0.4  breathing room above a mid-column header
    private var FOOT_FS:Number;   // 0.7  footer text size (floor 9 like the rest)
    private var MAX_PER_COL:Number;   // an item count, not a size — never scaled

    // layoutItems() -> show(): positioned {hdr, label, grp, row, col, y} items,
    // the column count, the tallest column's height and the measured footer
    // height — recomputed per fit-loop pass, so they live on the class.
    private var items:Array;
    private var nCols:Number;
    private var rowsH:Number;
    private var footH:Number;

    public function KazBarsPreviewPanel(kb:KazBars, root:MovieClip) {
        super(root);
        owner = kb;
        begin();
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
        ver = (cfg.version == null) ? "" : String(cfg.version);
        applySize(Number(cfg.fontSize));
        FS_REQ = FS;   // the clamped request — show()'s fit loop restarts from it
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
        HDR_GAP = Math.round(FS * 0.4);
        FOOT_FS = Math.max(9, Math.round(FS * 0.7));
        measure(1, 0, 0);
    }

    // The panel's footprint for a given layout — the one place columns, the
    // tallest column and the footer become a width and a height, so the fit
    // loop in show() and the empty seed in applySize() can't drift apart.
    private function measure(cols:Number, rowsHeight:Number, footerH:Number):Void {
        curW = PAD * 2 + cols * COL_W;
        var bottom:Number = ROWS_Y + rowsHeight;
        if (footerH > 0) bottom += Math.round(FS * 0.5) * 2 + footerH;
        curH = bottom + PAD;
    }

    private function footSepY():Number { return ROWS_Y + rowsH + Math.round(FS * 0.5); }
    private function footTextY():Number { return footSepY() + Math.round(FS * 0.5); }

    // =========================================================================
    // Row collection — begin() then one add per thing that can be hidden
    // =========================================================================

    // Rows are rebuilt from scratch every entry and each add seeds its check
    // from live state, so the panel never carries a stale flag between entries.
    public function begin():Void {
        groups = [{label: "Player Grids", rows: new Array()},
                  {label: "Target Grids", rows: new Array()},
                  {label: "Tools", rows: new Array()}];
    }

    public function addGrid(obj:Object):Void {
        var g:Object = (obj.cfg.type == "target") ? groups[1] : groups[0];
        g.rows.push({obj: obj, key: null, label: String(obj.cfg.id),
                     checked: (obj.shown == true), cb: null});
    }

    public function addExtra(label:String, key:String, checked:Boolean):Void {
        groups[2].rows.push({obj: null, key: key, label: label,
                             checked: (checked == true), cb: null});
    }

    // =========================================================================
    // Layout
    // =========================================================================

    // Groups into positioned items: each non-empty group is a header plus its
    // rows. A group that would straddle the column break but fits a fresh
    // column starts one; a group taller than a whole column splits and repeats
    // its header "(cont.)". Headers count against MAX_PER_COL like rows do.
    private function layoutItems():Void {
        items = new Array();
        var col:Number = 0;
        var y:Number = 0;
        var count:Number = 0;
        rowsH = 0;
        var gi:Number = 0;
        while (gi < groups.length) {
            var g:Object = groups[gi];
            if (g.rows.length > 0) {
                var size:Number = 1 + g.rows.length;
                if (count > 0 && count + size > MAX_PER_COL && size <= MAX_PER_COL) {
                    col++; y = 0; count = 0;
                }
                if (count > 0) y += HDR_GAP;
                items.push({hdr: true, label: g.label, grp: g, row: null, col: col, y: y});
                y += ROW_H; count++;
                if (y > rowsH) rowsH = y;
                var ri:Number = 0;
                while (ri < g.rows.length) {
                    if (count >= MAX_PER_COL) {
                        col++; y = 0; count = 0;
                        items.push({hdr: true, label: g.label + " (cont.)", grp: g,
                                    row: null, col: col, y: y});
                        y += ROW_H; count++;
                    }
                    items.push({hdr: false, label: null, grp: null, row: g.rows[ri],
                                col: col, y: y});
                    y += ROW_H; count++;
                    if (y > rowsH) rowsH = y;
                    ri++;
                }
            }
            gi++;
        }
        nCols = col + 1;
    }

    // One sizing pass: lay the items out, take the width, wrap the footer
    // inside it for a real measured height (never an estimate), then take the
    // height. The probe fields are built and removed in place.
    private function fitPass():Void {
        layoutItems();
        measure(nCols, rowsH, 0);
        footH = buildFooter(0);
        removeFooter();
        measure(nCols, rowsH, footH);
    }

    // =========================================================================
    // Build
    // =========================================================================

    public function show():Void {
        if (panelClip != null) panelClip.removeMovieClip();
        panelClip = rootClip.createEmptyMovieClip("kbPPanel", rootClip.getNextHighestDepth());

        var self:KazBarsPreviewPanel = this;

        // This is the only panel whose footprint grows with content — one row
        // per grid, a fresh column every MAX_PER_COL — so a size that suits a
        // three-grid build walks a sixty-grid one off the screen. It steps its
        // own size down until it fits rather than the shared range being cut
        // for everyone. Rows are rebuilt on every preview entry from the
        // requested size, so this is self-correcting and can never strand a
        // user with a panel they cannot reach.
        applySize(FS_REQ);
        fitPass();
        while (FS > 8 && (curW > Stage.width || curH > Stage.height)) {
            applySize(FS - 1);
            fitPass();
        }

        // Chrome is its own child clip, the family's arrangement — it can be
        // cleared and redrawn without taking the contents with it.
        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        drawChrome(curW, curH);

        titleTF = makeTF(panelClip, "title", PAD, Math.floor((TITLE_H - (LINE + 4)) / 2),
                         curW - PAD * 2, LINE + 4, NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "KazBars Preview";

        // Full title width — there is no collapse glyph to stop short of.
        makeCoordReadout(Math.floor((TITLE_H - LINE) / 2), curW - PAD * 2, LINE);

        var btnAll:MovieClip = makeButton(panelClip, "btnAll", "All", PAD, BTN_Y,
                                          Math.max(9, Math.round(FS * 0.9)));
        btnAll.onRelease = function() { self.setAll(true); };
        var btnNone:MovieClip = makeButton(panelClip, "btnNone", "None", PAD + BTN_W + 8,
                                           BTN_Y, Math.max(9, Math.round(FS * 0.9)));
        btnNone.onRelease = function() { self.setAll(false); };

        var i:Number = 0;
        while (i < items.length) {
            var it:Object = items[i];
            var x:Number = PAD + it.col * COL_W;
            var y:Number = ROWS_Y + it.y;
            // AS2 shares one activation record across the whole while loop, so
            // the row/group has to travel on the clip rather than in the closure.
            if (it.hdr == true) {
                var hc:MovieClip = makeHeader("hdr" + i, x, y, it.label);
                hc.hit._grp = it.grp;
                hc.hit._self = this;
                hc.hit.onPress = function() { this._self.toggleGroup(this._grp); };
            } else {
                var r:Object = it.row;
                r.cb = makeRowCheckbox("row" + i, x, y, r.label, r.checked,
                                       COL_W - BOX - 14, COL_W - 8);
                r.cb.hit._row = r;
                r.cb.hit._self = this;
                r.cb.hit.onPress = function() { this._self.toggleRow(this._row); };
            }
            i++;
        }

        buildFooter(footTextY());

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
        var gi:Number = 0;
        while (gi < groups.length) {
            setGroup(groups[gi], shown);
            gi++;
        }
    }

    // Header press: everything checked unchecks the group, anything else checks
    // it — the group-scale mirror of the row checkbox.
    public function toggleGroup(g:Object):Void {
        var all:Boolean = true;
        var i:Number = 0;
        while (i < g.rows.length) {
            if (g.rows[i].checked != true) { all = false; break; }
            i++;
        }
        setGroup(g, !all);
    }

    private function setGroup(g:Object, shown:Boolean):Void {
        var i:Number = 0;
        while (i < g.rows.length) {
            var r:Object = g.rows[i];
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
        // Under the title, under the All/None pair, above the footer — the
        // panel's three structural rules. Groups separate by whitespace and
        // header style alone, keeping hairlines structural.
        hairline(PAD, TITLE_H, w - PAD, TITLE_H);
        hairline(PAD, ROWS_Y - 5, w - PAD, ROWS_Y - 5);
        if (footH > 0) hairline(PAD, footSepY(), w - PAD, footSepY());
    }

    // Section header: bold caps in the family label beige, orange on hover like
    // every other live control, hit strip across the column. No box — the
    // header is a group master, not a fourth state.
    private function makeHeader(name:String, x:Number, y:Number, label:String):MovieClip {
        var c:MovieClip = panelClip.createEmptyMovieClip(name, panelClip.getNextHighestDepth());
        c._x = x;
        c._y = y;
        var hit:MovieClip = c.createEmptyMovieClip("hit", 0);
        hit.beginFill(0, 0);
        rectPath(hit, -2, -3, COL_W - 8, LINE + 4);
        hit.endFill();
        hit.useHandCursor = true;
        var tf:TextField = makeTF(c, "lbl", 0, 0, COL_W - 8, LINE,
                                  Math.max(9, Math.round(FS * 0.75)), true,
                                  0xC8C0B0, "left");
        tf.text = label.toUpperCase();
        hit.onRollOver = function() { this._parent.lbl.textColor = 0xF7A22B; };
        hit.onRollOut = function() { this._parent.lbl.textColor = 0xC8C0B0; };
        return c;
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

    // Dim orientation lines in the coord-readout grey: the exit keybind, the
    // /reloadui recipe, the version credit. Word-wrapped to the plate, so
    // buildFooter both draws them and is how fitPass measures them — the same
    // fields both times, never a diverging estimate.
    private function footerLines():Array {
        var credit:String = (ver == "") ? "KazBars - by Kazour of Spartans"
                                        : "KazBars v" + ver + " - by Kazour of Spartans";
        return ["Exit preview: Shift+Ctrl+Alt",
                "Apply app changes: Build & Install, then /reloadui in chat",
                credit];
    }

    private function buildFooter(y:Number):Number {
        var w:Number = curW - PAD * 2;
        var lines:Array = footerLines();
        var yy:Number = y;
        var i:Number = 0;
        while (i < lines.length) {
            var tf:TextField = makeTF(panelClip, "foot" + i, PAD, yy, w, LINE,
                                      FOOT_FS, false, 0x999999, "left");
            tf.wordWrap = true;
            tf.autoSize = "left";   // width holds, height grows to the wrap
            tf.text = lines[i];
            yy += tf._height;
            i++;
        }
        return yy - y;
    }

    private function removeFooter():Void {
        var i:Number = 0;
        while (i < 3) {
            var tf:Object = panelClip["foot" + i];
            if (tf != null) tf.removeTextField();
            i++;
        }
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
        items = null;
        begin();
    }
}
