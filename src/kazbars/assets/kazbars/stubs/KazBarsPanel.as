// KazBarsPanel.as - Chrome-family base for the four runtime-drawn panels
// (Console, Stopwatch, Inspect, PreviewPanel). Holds the family's shared
// primitives exactly as each panel drew them: warm near-black plate with the
// 1px black-over-bronze double frame, Arial device-font TextFields, the flat
// square button, the box/tick/hit checkbox, Stage-clamped title-strip drag
// with the grey coordinate readout, and the bare - / + collapse glyph whose
// collapsed bar re-opens on a press that moved under 2px. Every dimension is
// Math.round(FS x ratio) seeded by applyBaseSize(); panels layer their own
// ratios, layout, chrome rules and persistence on top — loadState/saveState
// stay per panel because their archive keys AND their load orderings differ
// on purpose (fold-before-clamp and friends).
//
// The panel<->core contract: the core drives every panel through its typed
// lifecycle calls (configure / create* / loadState / saveState / cleanup /
// isActive / setActive / previewOn / previewOff and the per-stub feeds); the
// ONE call that flows back is KazBars.previewToggle(key, shown), routed from
// the preview panel's extra rows. AS2 note: private members are visible to
// subclasses (there is no protected), and all methods dispatch virtually —
// toggleCollapsed() here lands on each panel's own applyCollapsed().
class KazBarsPanel {
    private var rootClip:MovieClip;
    private var panelClip:MovieClip;
    private var chrome:MovieClip;
    private var dragMC:MovieClip;
    private var collapseBtn:MovieClip;
    private var coordTF:TextField;
    private var collapsed:Boolean;
    private var dragX:Number;         // panel position at press, so a collapsed
    private var dragY:Number;         // press that never moved reads as a click
    private var posX:Number;          // cached spot for panels whose clip is
    private var posY:Number;          // destroyed between shows (console, ppanel)
    private var curW:Number;          // footprint of the plate on screen —
    private var curH:Number;          // the drag clamp measures these

    // Shared ratios off the base font size (applyBaseSize). Panels with their
    // own extras derive them after the base pass; the stopwatch overwrites
    // BTN_W with its fit-three-buttons derivation the same way.
    private var FS:Number;
    private var PAD:Number;       // 0.85
    private var TITLE_H:Number;   // 1.85
    private var LINE:Number;      // 1.4   the height one line of text needs
    private var BOX:Number;       // 1.0   checkbox side
    private var BTN:Number;       // 1.1   collapse glyph box
    private var BTN_W:Number;     // 5.0
    private var BTN_H:Number;     // 1.85
    private var NAME_FS:Number;   // 1.15  title font size
    private var COLL_W:Number;    // 15.8  the family's collapsed bar
    private var COLL_H:Number;    // 2.0
    private var COLL_PAD:Number;  // 0.55
    private var LEAD:Number;      // TextFormat leading; only the stopwatch and
                                  // inspect panel set one (0.15), and makeTF
                                  // applies it only when set — the console and
                                  // control panel never carried leading
    private var TF_MULTILINE:Boolean; // inspect's makeTF flavour (multiline,
                                      // no wrap); everyone else stays plain

    public function KazBarsPanel(root:MovieClip) {
        rootClip = root;
        collapsed = false;
        dragX = 0;
        dragY = 0;
        posX = Number.NaN;   // unset until dragged or loaded from the archive
        posY = Number.NaN;
        curW = 0;
        curH = 0;
        LEAD = 0;
        TF_MULTILINE = false;
    }

    // =========================================================================
    // Geometry
    // =========================================================================

    private function applyBaseSize(size:Number):Void {
        FS = size;
        PAD = Math.round(FS * 0.85);
        TITLE_H = Math.round(FS * 1.85);
        LINE = Math.round(FS * 1.4);
        BOX = Math.round(FS);
        BTN = Math.round(FS * 1.1);
        BTN_W = Math.round(FS * 5);
        BTN_H = Math.round(FS * 1.85);
        NAME_FS = Math.round(FS * 1.15);
        COLL_W = Math.round(FS * 15.8);
        COLL_H = Math.round(FS * 2);
        COLL_PAD = Math.round(FS * 0.55);
    }

    // =========================================================================
    // Widgets
    // =========================================================================

    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        if (TF_MULTILINE) {
            tf.multiline = true;
            tf.wordWrap = false;
        }
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = bold;
        fmt.align = align;
        fmt.color = col;
        if (LEAD > 0) fmt.leading = LEAD;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // Flat square button: plate fill, 1px bronze border, orange label on hover
    // — the family's own chrome at button scale. Label size is the caller's:
    // the control panel floors at 9, the stopwatch does not.
    private function makeButton(parent:MovieClip, name:String, label:String,
                                x:Number, y:Number, labelSize:Number):MovieClip {
        var c:MovieClip = parent.createEmptyMovieClip(name, parent.getNextHighestDepth());
        c._x = x;
        c._y = y;
        c._self = this;
        c.beginFill(0x0C0A07, 90);
        rectPath(c, 0, 0, BTN_W, BTN_H);
        c.endFill();
        c.lineStyle(1, 0x4A3B22, 100);
        rectPath(c, 0, 0, BTN_W, BTN_H);
        var tf:TextField = makeTF(c, "label", 0, Math.floor((BTN_H - LINE) / 2),
                                  BTN_W, LINE, labelSize, true, 0xC8C0B0, "center");
        tf.text = label;
        c.useHandCursor = true;
        c.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        c.onRollOut = function() { this.label.textColor = 0xC8C0B0; };
        return c;
    }

    // Box + tick + hit only — the console never labels its boxes, and the
    // control panel adds its own label with the row's own width.
    private function makeCheckbox(parent:MovieClip, name:String, x:Number, y:Number,
                                  checked:Boolean, hitW:Number):MovieClip {
        var c:MovieClip = parent.createEmptyMovieClip(name, parent.getNextHighestDepth());
        c._x = x;
        c._y = y;
        var box:MovieClip = c.createEmptyMovieClip("box", 1);
        box.lineStyle(1, 0x4A3B22, 100);
        box.beginFill(0x0C0A07, 90);
        rectPath(box, 0, 0, BOX, BOX);
        box.endFill();
        // Tick drawn to the box rather than to a 12px box's coordinates: three
        // points at 1/6, 5/12 and 5/6 of the side, the shape it has always had.
        var chk:MovieClip = c.createEmptyMovieClip("chk", 2);
        chk.lineStyle(Math.max(1, Math.round(BOX / 6)), 0x7AC142, 100);
        chk.moveTo(Math.round(BOX / 6), Math.round(BOX / 2));
        chk.lineTo(Math.round(BOX * 5 / 12), Math.round(BOX * 5 / 6));
        chk.lineTo(Math.round(BOX * 5 / 6), Math.round(BOX / 6));
        chk._visible = checked;
        // Hit area is a child at depth 0 so it sits under the art but still
        // takes the press across the whole label.
        var hit:MovieClip = c.createEmptyMovieClip("hit", 0);
        hit.beginFill(0, 0);
        rectPath(hit, -4, -4, hitW, BOX + 8);
        hit.endFill();
        hit.useHandCursor = true;
        return c;
    }

    // =========================================================================
    // Chrome primitives (panels draw their section rules on top)
    // =========================================================================

    private function drawPlate(w:Number, h:Number):Void {
        chrome.clear();
        chrome.beginFill(0x0C0A07, 90);
        rectPath(chrome, 0, 0, w, h);
        chrome.endFill();
        chrome.lineStyle(1, 0x000000, 100);
        rectPath(chrome, 0, 0, w, h);
        chrome.lineStyle(1, 0x4A3B22, 100);
        rectPath(chrome, 1, 1, w - 2, h - 2);
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    // =========================================================================
    // Collapse (panels position/redraw in their own applyCollapsed override)
    // =========================================================================

    public function toggleCollapsed():Void {
        collapsed = !collapsed;
        applyCollapsed();
    }

    private function applyCollapsed():Void {
    }

    // Bare glyph, no box — the family's collapse control. Positioning is the
    // panel's (its applyCollapsed re-seats the glyph per fold state).
    private function makeCollapseBtn():Void {
        collapseBtn = panelClip.createEmptyMovieClip("btnCollapse", panelClip.getNextHighestDepth());
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        makeTF(collapseBtn, "label", 0, 0, BTN, BTN + 2,
               Math.max(9, Math.round(FS * 0.9)), true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };
    }

    // =========================================================================
    // Drag + position
    // =========================================================================

    // Invisible handle whose shape each panel draws for its own band (redrawn
    // per fold state); the name is the panel's historical instance name.
    private function makeDragStrip(name:String):Void {
        dragMC = panelClip.createEmptyMovieClip(name, panelClip.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };
    }

    public function beginDrag(dh:MovieClip):Void {
        panelClip.startDrag(false, 0, 0, Math.max(0, Stage.width - curW),
                            Math.max(0, Stage.height - curH));
        dragX = panelClip._x;
        dragY = panelClip._y;
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsPanel = this;
        dh.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(dh:MovieClip):Void {
        panelClip.stopDrag();
        delete dh.onMouseMove;
        coordTF._visible = false;
        capturePos();
        // Collapsed, the bar is small and labelled and reads as a button, so a
        // press that never moved it opens the panel again; a real drag still
        // just moves it. Expanded, a stray click on the title must not fold it.
        if (collapsed && Math.abs(panelClip._x - dragX) < 2
                      && Math.abs(panelClip._y - dragY) < 2) {
            toggleCollapsed();
        }
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(panelClip._x) + ", " + Math.round(panelClip._y);
    }

    // The clip may be destroyed between shows, so its position is read back
    // into the class before it goes; panels that persist the live clip simply
    // never read these.
    private function capturePos():Void {
        if (panelClip == null) return;
        posX = panelClip._x;
        posY = panelClip._y;
    }

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }
}
