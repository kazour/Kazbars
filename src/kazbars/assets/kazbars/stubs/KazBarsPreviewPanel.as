// KazBarsPreviewPanel.as - Preview-mode control panel: one checkbox per grid
// and one per compiled-in extra, so a single overlay can be isolated while it
// is being positioned.
//
// Chrome and palette are the inspect panel's (KazBarsInspect.as, and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, bronze hairline rules, square corners. Like
// the console it is a transient tool with no font-size config, so its dimensions
// are named constants at the values the panel's ratios land on at FS 12. It does
// not fold — it only exists while preview mode is on, and folding a panel whose
// whole job is showing which things are hidden would hide the answer.
//
// Rows are rebuilt on every preview entry and every box starts checked: the
// checks are a positioning aid, not a setting, so none of them persist. The drag
// position does, in the module config archive (ppx/ppy) beside the other panels'
// keys.
class KazBarsPreviewPanel {
    private var owner:Object;
    private var rootClip:MovieClip;
    private var panelClip:MovieClip;
    private var chrome:MovieClip;
    private var dragMC:MovieClip;
    private var titleTF:TextField;
    private var coordTF:TextField;
    // {mc, key, label, checked, cb} — mc set for grids, key for extras.
    private var rows:Array;
    private var posX:Number;
    private var posY:Number;
    private var curW:Number;
    private var curH:Number;

    // Layout — the console's FS-12 constants, plus the row grid. Columns wrap
    // at MAX_PER_COL so a 64-grid build stays on the Stage.
    private var PAD:Number;
    private var TITLE_H:Number;
    private var LINE:Number;
    private var BOX:Number;
    private var ROW_H:Number;
    private var BTN_W:Number;
    private var BTN_H:Number;
    private var BTN_Y:Number;
    private var ROWS_Y:Number;
    private var COL_W:Number;
    private var MAX_PER_COL:Number;

    public function KazBarsPreviewPanel(kb:Object, root:MovieClip) {
        owner = kb;
        rootClip = root;
        rows = new Array();
        posX = Number.NaN;   // unset until dragged or loaded from the archive
        posY = Number.NaN;
        PAD = 10;
        TITLE_H = 22;
        LINE = 17;
        BOX = 12;
        ROW_H = 20;
        BTN_W = 60;
        BTN_H = 22;
        BTN_Y = TITLE_H + 6;
        ROWS_Y = BTN_Y + BTN_H + 10;
        COL_W = 220;
        MAX_PER_COL = 16;
        curW = PAD * 2 + COL_W;
        curH = ROWS_Y + PAD;
    }

    // =========================================================================
    // Row collection — begin() then one add per thing that can be hidden
    // =========================================================================

    // Dropping the array IS the all-checked reset: every row is rebuilt checked.
    public function begin():Void {
        rows = new Array();
    }

    public function addGrid(obj:Object):Void {
        rows.push({mc: obj.mc, key: null, label: String(obj.cfg.id), checked: true, cb: null});
    }

    public function addExtra(label:String, key:String):Void {
        rows.push({mc: null, key: key, label: label, checked: true, cb: null});
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
        curW = PAD * 2 + cols * COL_W;
        curH = ROWS_Y + firstCol * ROW_H + PAD;

        // Chrome is its own child clip, the family's arrangement — it can be
        // cleared and redrawn without taking the contents with it.
        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        drawChrome(curW, curH);

        titleTF = makeTF(panelClip, "title", PAD, Math.floor((TITLE_H - (LINE + 4)) / 2),
                         curW - PAD * 2, LINE + 4, 14, true, 0xF7A22B, "left");
        titleTF.text = "Control Panel";

        // Live position readout — visible only while dragging, the panel's
        // convention. Shares the title line, right-aligned.
        coordTF = makeTF(panelClip, "coords", PAD, Math.floor((TITLE_H - LINE) / 2),
                         curW - PAD * 2, LINE, 10, false, 0x999999, "right");
        coordTF._visible = false;

        var btnAll:MovieClip = makeButton(panelClip, "btnAll", "All", PAD, BTN_Y);
        btnAll.onRelease = function() { self.setAll(true); };
        var btnNone:MovieClip = makeButton(panelClip, "btnNone", "None", PAD + BTN_W + 8, BTN_Y);
        btnNone.onRelease = function() { self.setAll(false); };

        var i:Number = 0;
        while (i < rows.length) {
            var r:Object = rows[i];
            var c:Number = Math.floor(i / MAX_PER_COL);
            r.cb = makeCheckbox("row" + i, PAD + c * COL_W,
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
        dragMC = panelClip.createEmptyMovieClip("dh", panelClip.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, curW, TITLE_H);
        dragMC.endFill();
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };

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
        if (r.mc != null) r.mc._visible = r.checked;
        else owner.previewToggle(r.key, r.checked);
    }

    // =========================================================================
    // Chrome / widgets
    // =========================================================================

    private function drawChrome(w:Number, h:Number):Void {
        chrome.clear();
        chrome.beginFill(0x0C0A07, 90);
        rectPath(chrome, 0, 0, w, h);
        chrome.endFill();
        chrome.lineStyle(1, 0x000000, 100);
        rectPath(chrome, 0, 0, w, h);
        chrome.lineStyle(1, 0x4A3B22, 100);
        rectPath(chrome, 1, 1, w - 2, h - 2);
        // Bronze hairlines under the title and under the All/None pair — the
        // panel's section rules separating the header, the masters, the rows.
        chrome.lineStyle(1, 0x6B5324, 100);
        chrome.moveTo(PAD, TITLE_H);
        chrome.lineTo(w - PAD, TITLE_H);
        chrome.moveTo(PAD, ROWS_Y - 5);
        chrome.lineTo(w - PAD, ROWS_Y - 5);
    }

    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = bold;
        fmt.align = align;
        fmt.color = col;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // `on` would be a parse error here — AS2 reserves it for clip handlers.
    // Label width is a parameter, not the console's fixed 80: a grid id gets
    // the rest of its column.
    private function makeCheckbox(name:String, x:Number, y:Number, label:String,
                                  checked:Boolean, labelW:Number, hitW:Number):MovieClip {
        var c:MovieClip = panelClip.createEmptyMovieClip(name, panelClip.getNextHighestDepth());
        c._x = x;
        c._y = y;
        var box:MovieClip = c.createEmptyMovieClip("box", 1);
        box.lineStyle(1, 0x4A3B22, 100);
        box.beginFill(0x0C0A07, 90);
        rectPath(box, 0, 0, BOX, BOX);
        box.endFill();
        var chk:MovieClip = c.createEmptyMovieClip("chk", 2);
        chk.lineStyle(2, 0x7AC142, 100);
        chk.moveTo(2, 6);
        chk.lineTo(5, 10);
        chk.lineTo(10, 2);
        chk._visible = checked;
        var lbl:TextField = makeTF(c, "lbl", BOX + 6, -3, labelW, LINE,
                                   10, false, 0xC8C0B0, "left");
        lbl.text = label;
        // Hit area is a child at depth 0 so it sits under the art but still
        // takes the press across the whole label.
        var hit:MovieClip = c.createEmptyMovieClip("hit", 0);
        hit.beginFill(0, 0);
        rectPath(hit, -4, -4, hitW, BOX + 8);
        hit.endFill();
        hit.useHandCursor = true;
        return c;
    }

    // Flat square button: plate fill, 1px bronze border, orange label on hover
    // — the panel's own chrome at button scale.
    private function makeButton(parent:MovieClip, name:String, label:String,
                                x:Number, y:Number):MovieClip {
        var c:MovieClip = parent.createEmptyMovieClip(name, parent.getNextHighestDepth());
        c._x = x;
        c._y = y;
        c.beginFill(0x0C0A07, 90);
        rectPath(c, 0, 0, BTN_W, BTN_H);
        c.endFill();
        c.lineStyle(1, 0x4A3B22, 100);
        rectPath(c, 0, 0, BTN_W, BTN_H);
        var tf:TextField = makeTF(c, "label", 0, Math.floor((BTN_H - LINE) / 2),
                                  BTN_W, LINE, 11, true, 0xC8C0B0, "center");
        tf.text = label;
        c.useHandCursor = true;
        c.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        c.onRollOut = function() { this.label.textColor = 0xC8C0B0; };
        return c;
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    // =========================================================================
    // Drag + persistence
    // =========================================================================

    public function beginDrag(dh:MovieClip):Void {
        panelClip.startDrag(false, 0, 0, Math.max(0, Stage.width - curW),
                            Math.max(0, Stage.height - curH));
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsPreviewPanel = this;
        dh.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(dh:MovieClip):Void {
        panelClip.stopDrag();
        delete dh.onMouseMove;
        coordTF._visible = false;
        capturePos();
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(panelClip._x) + ", " + Math.round(panelClip._y);
    }

    // The clip is destroyed every time preview ends, so its position has to be
    // read back into the class before it goes.
    private function capturePos():Void {
        if (panelClip == null) return;
        posX = panelClip._x;
        posY = panelClip._y;
    }

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

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }

    // Preview is over: the clip goes, and the rows go with it so no stale grid
    // clip reference outlives the grids it points at.
    public function destroy():Void {
        capturePos();
        if (panelClip != null) { panelClip.removeMovieClip(); panelClip = null; }
        chrome = null; dragMC = null; titleTF = null; coordTF = null;
        rows = new Array();
    }
}
