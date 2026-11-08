// KazBarsPanel.as - Chrome-family base for the five runtime-drawn panels
// (Console, Inspect, PreviewPanel, Onslaught, Stopwatch). Holds the family's
// shared primitives exactly as each panel drew them: warm near-black plate with
// the 1px black-over-bronze double frame, Arial device-font TextFields, the
// flat square button, the box/tick/hit checkbox, Stage-clamped title-strip drag,
// and the bare - / + collapse glyph whose
// collapsed bar re-opens on a press that moved under 2px. Every dimension is
// Math.round(FS x ratio) seeded by applyBaseSize(); panels layer their own
// ratios, layout, chrome rules and persistence on top — loadState/saveState
// stay per panel because their archive keys AND their load orderings differ
// on purpose (fold-before-clamp and friends).
//
// The drag half (makeDragStrip / beginDrag / endDrag, and
// the collapsed click-to-reopen that rides on it) serves the tool class — the
// console and the control panel; the inspect panel is a HUD
// element (see KazBarsModule) and extends this base for chrome and collapse
// alone, the onslaught tracker for geometry, text fields and the plate.
//
// The panel<->core contract: the core drives every module through the typed
// KazBarsModule lifecycle (create / loadState / saveState / previewOn /
// previewOff / isActive / setActive / previewKey / previewLabel / cleanup),
// plus configure() and the per-stub feeds; the ONE call that flows back is
// KazBars.previewToggle(key, shown), routed from the preview panel's extra
// rows. AS2 note: private members are visible to subclasses (there is no
// protected), and all methods dispatch virtually — toggleCollapsed() here
// lands on each panel's own applyCollapsed().
//
// Type: ONE modular scale, ratio 1.25 off the base size FS, by role. A panel
// picks a role, never a ratio:
//   Small   0.8   SMALL_FS    footers, small caps headers, the
//                              onslaught tier headers and camp rows
//   Body    1.0   FS          labels, values, list rows, bold section headers,
//                              the collapsed-bar label, every button (bold),
//                              the collapse glyph (bold), console log entries
//   Title   1.25  NAME_FS     panel titles, the onslaught wave label and bosses
//   Alert   1.6   ALERT_FS    the onslaught wave clocks (its alerts have their own baked size)
// roleFS() rounds each, and keeps Small from falling under 9 (or over Body).
// One line-box rule: a text field is lh(size) tall, size x 1.4 rounded.
class KazBarsPanel {
    private var rootClip:MovieClip;
    private var panelClip:MovieClip;
    private var chrome:MovieClip;
    private var dragMC:MovieClip;
    private var collapseBtn:MovieClip;
    private var collapsed:Boolean;
    private var dragX:Number;         // panel position at press, so a collapsed
    private var dragY:Number;         // press that never moved reads as a click
    private var posX:Number;          // cached spot for panels whose clip is
    private var posY:Number;          // destroyed between shows (console, ppanel)
    private var seatX:Number;         // where seat() last put the plate: one
    private var seatY:Number;         // still there was not dragged since
    private var curW:Number;         // footprint of the plate on screen —
    private var curH:Number;          // the drag clamp measures these
    private var ck:KazBarsClock;      // gliding bars (glides): the clock,
    private var kG:Object;            // the easing task,
    private var gl:Array;             // the fills short of their target,
    private var gT:Number;            // and the last step's time

    // Shared sizes off the base font size (applyBaseSize). Panels with their
    // own extras derive them after the base pass.
    private var FS:Number;          // Body, the base
    private var SMALL_FS:Number;    // Small   0.8   (9 at the least, Body at the most)
    private var NAME_FS:Number;     // Title   1.25
    private var ALERT_FS:Number;    // Alert   1.6
    private var LEAD:Number;        // 0.15  TextFormat leading, every panel
    private var PAD:Number;         // 0.85
    private var TITLE_H:Number;     // NAME_H + 0.25 padding above and below it
    private var LINE:Number;        // lh(FS) the height one Body line needs
    private var SMALL_H:Number;     // lh(SMALL_FS)
    private var NAME_H:Number;      // lh(NAME_FS)
    private var BOX:Number;         // 1.0   checkbox side
    private var BTN:Number;         // 1.1   collapse glyph box width (LINE tall)
    private var BTN_W:Number;       // 5.0
    private var BTN_H:Number;       // 1.85  holds one Body line box (LINE)
    private var BTN_GAP:Number;     // 0.42  between neighbouring buttons
    private var COLL_W:Number;      // 15.8  the family's collapsed bar
    private var COLL_H:Number;      // 2.0
    private var COLL_PAD:Number;    // 0.55

    public function KazBarsPanel(root:MovieClip) {
        rootClip = root;
        collapsed = false;
        dragX = 0;
        dragY = 0;
        posX = Number.NaN;   // unset until dragged or loaded from the archive
        posY = Number.NaN;
        seatX = Number.NaN;
        seatY = Number.NaN;
        curW = 0;
        curH = 0;
    }

    // =========================================================================
    // Geometry
    // =========================================================================

    // One line box: a field of this size is this tall. Static, so the preview
    // overlay (KazBarsPreview) and the panels share the one rule.
    public static function lh(size:Number):Number {
        return Math.round(size * 1.4);
    }

    // A role's font size at a base size: round(base x k). A role below Body
    // (k < 1) is held at 9 so it stays legible, and never above Body, so at the
    // smallest sizes it simply becomes Body.
    public static function roleFS(base:Number, k:Number):Number {
        if (k < 1) return Math.max(Math.min(9, base), Math.round(base * k));
        return Math.round(base * k);
    }

    private function applyBaseSize(size:Number):Void {
        // The family floor and default: a missing or sub-8 size seeds every
        // ratio NaN or illegibly small, so the invariant lives here, once.
        if (isNaN(size) || size < 8) size = 12;
        FS = size;
        SMALL_FS = roleFS(FS, 0.8);
        NAME_FS = roleFS(FS, 1.25);
        ALERT_FS = roleFS(FS, 1.6);
        LEAD = Math.round(FS * 0.15);
        PAD = Math.round(FS * 0.85);
        LINE = lh(FS);
        SMALL_H = lh(SMALL_FS);
        NAME_H = lh(NAME_FS);
        TITLE_H = NAME_H + Math.round(FS * 0.25) * 2;
        BOX = Math.round(FS);
        BTN = Math.round(FS * 1.1);
        BTN_W = Math.round(FS * 5);
        BTN_H = Math.round(FS * 1.85);
        BTN_GAP = Math.round(FS * 0.42);
        COLL_W = Math.round(FS * 15.8);
        COLL_H = Math.round(FS * 2);
        COLL_PAD = Math.round(FS * 0.55);
    }

    // =========================================================================
    // Widgets
    // =========================================================================

    // A field's height is the caller's: lh(size) for a line of text, or a
    // viewport (the console log) sized to the panel. The leading is the family's
    // (LEAD, set in applyBaseSize).
    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        var fmt:TextFormat = new TextFormat();
        fmt.font = KazBarsPreview.FACE;
        fmt.size = size;
        fmt.bold = bold;
        fmt.align = align;
        fmt.color = col;
        fmt.leading = LEAD;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // Flat square button: plate fill, 1px bronze border, orange label on hover
    // — the family's own chrome at button scale. The label is Body, bold, in a
    // LINE-tall box centred in the BTN_H button.
    private function makeButton(parent:MovieClip, name:String, label:String,
                                x:Number, y:Number):MovieClip {
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
                                  BTN_W, LINE, FS, true, 0xC8C0B0, "center");
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

    // 1px bronze rule — the family's section hairline (title separators,
    // column and section-header rules). Sets its own style so panels can mix
    // it freely with their other chrome drawing.
    private function hairline(x1:Number, y1:Number, x2:Number, y2:Number):Void {
        chrome.lineStyle(1, 0x6B5324, 100);
        chrome.moveTo(x1, y1);
        chrome.lineTo(x2, y2);
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

    // Bare glyph, no box — the family's collapse control: a bold Body "-" / "+"
    // in a BTN-wide, LINE-tall box. Positioning is the panel's (its
    // applyCollapsed re-seats the glyph per fold state, through seatCollapseBtn).
    private function makeCollapseBtn():Void {
        collapseBtn = panelClip.createEmptyMovieClip("btnCollapse", panelClip.getNextHighestDepth());
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        makeTF(collapseBtn, "label", 0, 0, BTN, LINE, FS, true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };
    }

    // The glyph at x, centred on a band of that height. The box is LINE tall,
    // so it centres by LINE — not by BTN, its width.
    private function seatCollapseBtn(x:Number, band:Number):Void {
        collapseBtn._x = x;
        collapseBtn._y = Math.floor((band - LINE) / 2);
    }

    // The family's collapsed-bar label: base font size, Conan orange, inset
    // COLL_PAD, stopping short of the glyph, centred in the bar. Returned, not
    // stored — the swap-on-_visible field is each panel's own.
    private function makeCollapsedLabel(text:String):TextField {
        var tf:TextField = makeTF(panelClip, "coll", COLL_PAD,
                                  Math.floor((COLL_H - LINE) / 2),
                                  COLL_W - COLL_PAD * 2 - BTN, LINE,
                                  FS, true, 0xF7A22B, "left");
        tf.text = text;
        return tf;
    }

    // =========================================================================
    // Gliding bars (Onslaught): a fill's _xscale eases toward its target
    // by elapsed time (time constant 150 ms), snapping within 0.2, so uneven
    // updates never show as jumps. A clock task runs only while a fill is short
    // of its target. A fill's first value snaps, as does a reset (snap). shown()
    // writes the value: a subclass whose colour follows it overrides it. f._v is
    // the shown value, f._t the target, f._g true while gliding.
    // =========================================================================

    private function glides(c:KazBarsClock):Void {
        ck = c;
        gl = [];
        kG = c.add(ease, this, 1, false, 0);
    }

    private function glide(f:MovieClip, t:Number, snap:Boolean):Void {
        if (snap || f._v == undefined || ck == null) {
            f._t = t;
            shown(f, t);
            return;
        }
        if (f._t != t && !f._g) {
            f._g = true;
            if (gl.push(f) == 1) gT = ck.now;
            ck.go(kG);
        }
        f._t = t;
        shown(f, f._v);
    }

    public function ease():Void {
        var now:Number = ck.now;
        var k:Number = 1 - Math.exp((gT - now) / 150);
        var i:Number = gl.length;
        var f:MovieClip;
        var v:Number;
        gT = now;
        while (i--) {
            f = gl[i];
            v = f._v + (f._t - f._v) * k;
            if (Math.abs(f._t - v) <= 0.2) {
                v = f._t;
                f._g = false;
                gl.splice(i, 1);
            }
            shown(f, v);
        }
        if (gl.length == 0) ck.off(kG);
    }

    // The bars are gone: nothing glides on (a removed clip's path can name a new one).
    private function halt():Void {
        gl.length = 0;
    }

    private function shown(f:MovieClip, v:Number):Void {
        if (f._v == v) return;
        f._v = v;
        f._xscale = v;
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
        // Bounds derive from fontSize, so a big enough panel inverts the rect
        // and gets yanked off-screen; floored, it pins to the top-left.
        var s:Object = stage();
        panelClip.startDrag(false, s.x, s.y, Math.max(s.x, s.x + s.w - curW),
                            Math.max(s.y, s.y + s.h - curH));
        dragX = panelClip._x;
        dragY = panelClip._y;
    }

    public function endDrag(dh:MovieClip):Void {
        panelClip.stopDrag();
        capturePos();
        // Collapsed, the bar is small and labelled and reads as a button, so a
        // press that never moved it opens the panel again; a real drag still
        // just moves it. Expanded, a stray click on the title must not fold it.
        if (collapsed && Math.abs(panelClip._x - dragX) < 2
                      && Math.abs(panelClip._y - dragY) < 2) {
            toggleCollapsed();
        }
    }

    // The clip may be destroyed between shows, so its position is read back
    // into the class before it goes; panels that persist the live clip simply
    // never read these.
    private function capturePos():Void {
        if (panelClip == null) return;
        posX = panelClip._x;
        posY = panelClip._y;
    }

    // The spot (posX, posY) is where the user left the plate; seat() puts the plate there, clamped to the stage as
    // it reads now, and the clamp never becomes the spot: at login the stage can read 1920 x 1080 before the display
    // resolution applies (a 1440p archive held the console and the inspect panel at exactly 1920 less their width),
    // and a plate seated inside it was saved there. Stage.onResize seats it again (stageOn); a plate moved since its
    // seating (a drag) makes its new place the spot (keepSpot).
    private function keepSpot():Void {
        if (panelClip != null && (panelClip._x != seatX || panelClip._y != seatY)) {
            posX = panelClip._x;
            posY = panelClip._y;
        }
    }

    private function seat():Void {
        if (panelClip == null || isNaN(posX) || isNaN(posY)) return;
        panelClip._x = clampPos(posX, curW, true);
        panelClip._y = clampPos(posY, seatH(), false);
        seatX = panelClip._x;
        seatY = panelClip._y;
    }

    // The footprint height seat() keeps on the stage.
    private function seatH():Number {
        return curH;
    }

    private function stageOn(live:Boolean):Void {
        Stage.removeListener(this);
        if (live) Stage.addListener(this);
    }

    public function onResize():Void {
        keepSpot();
        seat();
    }

    // The drawable stage {x, y, w, h}, the one rule every position and drag
    // bound answers to: Scaleform's Stage.visibleRect (the game's own clip
    // loader seats its full-screen clips at that rect's corner and size), else
    // Stage.width/height from the origin when it reads nothing. Read where it
    // is used, so a resize between two uses is seen.
    public static function stage():Object {
        var r:Object = Stage["visibleRect"];
        var w:Number = Number(r.width);
        var h:Number = Number(r.height);
        if (w > 0 && h > 0) {
            var x:Number = Number(r.x);
            var y:Number = Number(r.y);
            return {x: (x == x) ? x : 0, y: (y == y) ? y : 0, w: w, h: h};
        }
        w = Stage.width;
        h = Stage.height;
        return {x: 0, y: 0, w: (w > 0) ? w : 1024, h: (h > 0) ? h : 768};
    }

    // v, a footprint of size n's near edge along x (horiz) or y, kept on the
    // stage. A footprint larger than the stage pins to its near edge like the
    // drag floor in beginDrag, rather than seated partly off-screen. Static so
    // every module (grids, cast timer, onslaught, panels) clamps archived
    // positions with the same rule.
    public static function clampPos(v:Number, n:Number, horiz:Boolean):Number {
        var s:Object = stage();
        var lo:Number = horiz ? s.x : s.y;
        var hi:Number = lo + (horiz ? s.w : s.h) - n;
        if (isNaN(v) || v < lo || hi < lo) return lo;
        return (v > hi) ? hi : v;
    }
}
