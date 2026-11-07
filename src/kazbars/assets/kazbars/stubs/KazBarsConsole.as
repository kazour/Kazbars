// KazBarsConsole.as - The Console: an in-game panel of tabs that serves every module. This class is the shell: the
// title, the tab strip, the two columns (player | target, or friendly | hostile), the Clear button, fold and drag.
// Each tab is its own class (KazBarsConTab) under its own build gate, added by the template; the strip follows the
// profile's order (d.CON.tabs). A tab feeds its columns (KazBarsConList) from the shared runtime; this class draws
// only the visible tab's, from one clock task every 250 ms while the panel is open, and only a column that changed.
//
// Chrome and palette are the family's, inherited from KazBarsPanel: warm near-black plate, double frame,
// Conan-orange title, bronze hairline rules, square corners. Every dimension is a ratio of the base font size, so
// the console folds to the same bar the inspect panel does at any size. The columns keep their player/target
// identity in the panel's perk-pair blue and red.
//
// Drag is clamped to the Stage; the position, fold state, master switch and visible tab (by its key, so a strip
// reordered in the app opens the same tab) persist in the module config archive (cnx/cny/cnc/cnv/cnt). Every build
// of the panel opens each tab (open) and every teardown closes them, so a tab's own work runs only while it is up.
class KazBarsConsole extends KazBarsPanel implements KazBarsModule {
    private var m_Body:MovieClip;
    private var strip:MovieClip;
    private var titleTF:TextField;
    private var collTF:TextField;
    private var headTF:TextField;
    private var footTF:TextField;
    private var hdrs:Array;       // the two column titles
    private var cols:Array;       // the two column fields
    private var tabs:Array;       // KazBarsConTab, in the strip's order
    private var order:Array;      // the profile's tab keys
    private var cur:Number;       // the visible tab
    private var lastHead:String;
    private var task:Object;

    private var CW:Number;        // 41.67 the expanded footprint
    private var CH:Number;        // 28.67
    private var STRIP_Y:Number;   // 2.6   the tab strip
    private var TAB_GAP:Number;   // 1.2   between strip labels
    private var RULE_Y:Number;    // 4.4   the rule under the strip
    private var HEAD_Y:Number;    // 4.85  a tab's head line, when it has one
    private var COL_W:Number;     // 19.17
    private var RULE_BOT:Number;  // 2.92  the mid rule stops above the button band
    private var LOG_BOT:Number;   // 3.33  and the columns above that

    // Every log entry spells out its own face and size: Scaleform re-parses htmlText from scratch, so
    // setNewTextFormat on the field does not reach an untagged run; it would fall back to a serif device font.
    private var ENTRY_FONT:String;

    public function KazBarsConsole(root:MovieClip) {
        super(root);
        tabs = [];
        order = [];
        cur = 0;
        lastHead = "";
        // Nothing has to call configure() for the console to be usable, so it seeds itself at the default size.
        configure(null);
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) cfg = {};
        applyBaseSize(Number(cfg.fontSize));
        if (cfg.tabs instanceof Array) order = cfg.tabs;
        CW = Math.round(FS * 41.67);
        CH = Math.round(FS * 28.67);
        STRIP_Y = Math.round(FS * 2.6);
        TAB_GAP = Math.round(FS * 1.2);
        RULE_Y = Math.round(FS * 4.4);
        HEAD_Y = Math.round(FS * 4.85);
        COL_W = Math.round(FS * 19.17);
        RULE_BOT = Math.round(FS * 2.92);
        LOG_BOT = Math.round(FS * 3.33);
        curW = CW;
        curH = CH;
        ENTRY_FONT = '<font face="' + KazBarsPreview.FACE + '" size="' + FS + '" color="#';
    }

    // A tab the build carries (the template adds one per gate that is on).
    public function add(t:KazBarsConTab):Void {
        tabs.push(t);
    }

    // The tabs in the profile's order, each fed from the shared runtime, and the draw task.
    public function follow(w:KazBarsWorld):Void {
        var sorted:Array = [];
        for (var i:Number = 0; i < order.length; i++) {
            for (var j:Number = 0; j < tabs.length; j++) {
                if (tabs[j].key() == order[i]) sorted.push(tabs[j]);
            }
        }
        tabs = sorted;
        for (var k:Number = 0; k < tabs.length; k++) tabs[k].follow(this, w);
        ck = w.clock;
        task = ck.add(draw, this, 250, true, 0);
    }

    // One HTML run in the entry font: game text escaped, so an "&" or "<" in a name survives the markup.
    public function run(s:String, col:String):String {
        return ENTRY_FONT + col + '">' + s.split("&").join("&amp;").split("<").join("&lt;") + "</font>";
    }

    public function isActive():Boolean {
        return (panelClip != null);
    }

    // The wall clock as "hh:mm:ss", for the tabs' time stamps.
    public function clock():String {
        var d:Date = new Date();
        return two(d.getHours()) + ":" + two(d.getMinutes()) + ":" + two(d.getSeconds());
    }

    private function two(n:Number):String {
        return (n < 10 ? "0" : "") + n;
    }


    public function previewKey():String { return "console"; }
    public function previewLabel():String { return "Console"; }

    // Tool class: already interactive in normal play, dragged by its own title strip, so preview has nothing to add.
    public function previewOn():Void {}
    public function previewOff():Void {}

    // Master switch: the console's active state IS the clip's existence.
    public function setActive(shown:Boolean):Void {
        if (shown) {
            if (panelClip == null) create();
        } else {
            removeConsole();
        }
    }

    public function create():Void {
        if (panelClip != null) removeConsole();
        if (tabs.length == 0) return;
        if (cur >= tabs.length) cur = 0;
        panelClip = rootClip.createEmptyMovieClip("buffConsole", rootClip.getNextHighestDepth());
        var self:KazBarsConsole = this;

        // Chrome is its own child clip, so it can be redrawn without taking the contents with it; everything below
        // the title line is the body, so folding is one _visible toggle.
        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        m_Body = panelClip.createEmptyMovieClip("body", panelClip.getNextHighestDepth());

        strip = m_Body.createEmptyMovieClip("strip", m_Body.getNextHighestDepth());
        var x:Number = PAD;
        for (var i:Number = 0; i < tabs.length; i++) {
            var c:MovieClip = strip.createEmptyMovieClip("t" + i, strip.getNextHighestDepth());
            var tf:TextField = makeTF(c, "label", 0, 0, CW, LINE, FS, true, 0xA89A86, "left");
            tf.text = tabs[i].label();
            var w:Number = Math.ceil(tf.textWidth) + 4;
            tf._width = w;
            c.beginFill(0, 0);
            rectPath(c, 0, 0, w, LINE);
            c.endFill();
            c._x = x;
            c._y = STRIP_Y;
            c.i = i;
            c.useHandCursor = true;
            c.onRelease = function() { self.pick(this.i); };
            x += w + TAB_GAP;
        }

        headTF = makeTF(m_Body, "head", PAD, HEAD_Y, CW - PAD * 2, LINE, FS, false, 0xC8C0B0, "left");
        footTF = makeTF(m_Body, "foot", PAD, CH - PAD - BTN_H + Math.floor((BTN_H - LINE) / 2), CW - PAD * 3 - BTN_W, LINE, FS,
                        false, 0xA89A86, "left");
        hdrs = [makeTF(m_Body, "hp", PAD, 0, COL_W, LINE, FS, true, 0x7FB0D6, "left"),
                makeTF(m_Body, "ht", CW / 2 + PAD, 0, COL_W, LINE, FS, true, 0xD68585, "left")];
        cols = [makeLog("cp", PAD), makeLog("ct", CW / 2 + PAD)];

        var clr:MovieClip = makeButton(m_Body, "clr", "Clear", CW - PAD * 2 - BTN_W, CH - PAD - BTN_H);
        clr.onRelease = function() { self.tabs[self.cur].clear(); };

        // Both title fields exist at once and swap on _visible, as the inspect panel's do.
        titleTF = makeTF(panelClip, "title", PAD, Math.floor((TITLE_H - NAME_H) / 2), CW - PAD * 2 - BTN, NAME_H,
                         NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "Console";
        collTF = makeCollapsedLabel("Console");

        // Drag handle over the title line, stopping short of the collapse glyph so it keeps its own press.
        makeDragStrip("dh");
        makeCollapseBtn();
        applyCollapsed();
        for (var o:Number = 0; o < tabs.length; o++) tabs[o].open(true);
        if (!collapsed) tabs[cur].shown(true);

        // Placed last: the clamp has to measure the plate actually on screen. Centred on first open; after that
        // wherever the user left it, seated again when the stage resizes.
        if (isNaN(posX) || isNaN(posY)) {
            var s:Object = KazBarsPanel.stage();
            posX = s.x + (s.w - curW) / 2;
            posY = s.y + 250;
        }
        seat();
        stageOn(true);
    }

    // A column: the one selectable field kind in the panel (the point is copying an id out). HTML, so an entry
    // can colour its runs without a field per line. Its y and height are the visible tab's (show).
    private function makeLog(id:String, x:Number):TextField {
        var tf:TextField = makeTF(m_Body, id, x, 0, COL_W, LINE, FS, false, 0xC8C0B0, "left");
        tf.selectable = true;
        tf.multiline = true;
        tf.wordWrap = true;
        tf.html = true;
        return tf;
    }

    public function pick(i:Number):Void {
        if (i == cur || tabs[i] == null) return;
        tabs[cur].shown(false);
        cur = i;
        tabs[cur].shown(true);
        show();
    }

    // Lays the visible tab out: the strip's highlight, its head line when it has one, its column titles and
    // columns below it, both columns marked for the next draw.
    private function show():Void {
        if (panelClip == null) return;
        var t:KazBarsConTab = tabs[cur];
        for (var i:Number = 0; i < tabs.length; i++) {
            strip["t" + i].label.textColor = (i == cur) ? 0xF7A22B : 0xA89A86;
        }
        lastHead = t.head();
        headTF.text = lastHead;
        footTF.text = t.foot();
        var y:Number = HEAD_Y + (lastHead == "" ? 0 : LINE);
        var body:Number = y + LINE + Math.round(FS * 0.5);
        var h:Array = t.heads();
        var l:Array = t.logs();
        for (var k:Number = 0; k < 2; k++) {
            hdrs[k]._y = y;
            hdrs[k].text = h[k];
            cols[k]._y = body;
            cols[k]._height = CH - body - LOG_BOT;
            l[k].dirty = true;
        }
        draw();
    }

    // The clock task: the visible tab's changed columns, and its head line when it moved.
    public function draw():Void {
        if (panelClip == null || collapsed) return;
        var t:KazBarsConTab = tabs[cur];
        var l:Array = t.logs();
        for (var k:Number = 0; k < 2; k++) {
            if (l[k].dirty) {
                l[k].dirty = false;
                cols[k].htmlText = l[k].html();
            }
        }
        var hd:String = t.head();
        if (hd != lastHead) {
            if ((hd == "") != (lastHead == "")) show();
            else { lastHead = hd; headTF.text = hd; }
        }
    }

    // A fold takes the visible tab off screen (shown), an unfold puts it back: a tab draws nothing while folded.
    public function toggleCollapsed():Void {
        if (!collapsed) tabs[cur].shown(false);
        super.toggleCollapsed();
        if (!collapsed) tabs[cur].shown(true);
    }

    // Two plates, not one at two heights: the sheet, and the labelled bar the inspect panel folds to. The draw
    // task runs only while the sheet is open.
    private function applyCollapsed():Void {
        if (panelClip == null) return;
        curW = collapsed ? COLL_W : CW;
        curH = collapsed ? COLL_H : CH;
        var pad:Number = collapsed ? COLL_PAD : PAD;
        var band:Number = collapsed ? COLL_H : TITLE_H;
        m_Body._visible = !collapsed;
        titleTF._visible = !collapsed;
        collTF._visible = collapsed;
        collapseBtn.label.text = collapsed ? "+" : "-";
        seatCollapseBtn(curW - pad - BTN, band);
        dragMC.clear();
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, curW - pad - BTN, band);
        dragMC.endFill();
        drawPlate(curW, curH);
        if (!collapsed) {
            // Bronze hairlines: under the title, under the strip, and down the middle between the columns.
            hairline(PAD, TITLE_H, CW - PAD, TITLE_H);
            hairline(PAD, RULE_Y, CW - PAD, RULE_Y);
            hairline(CW / 2, RULE_Y, CW / 2, CH - RULE_BOT);
            show();
        }
        if (task == null) return;
        if (collapsed) ck.off(task);
        else ck.go(task);
    }

    // =========================================================================
    // Lifecycle
    // =========================================================================

    public function removeConsole():Void {
        keepSpot();
        stageOn(false);
        if (task != null) ck.off(task);
        if (panelClip != null) {
            if (!collapsed) tabs[cur].shown(false);
            for (var i:Number = 0; i < tabs.length; i++) tabs[i].open(false);
            panelClip.removeMovieClip();
            panelClip = null;
        }
        chrome = null; m_Body = null; dragMC = null; collapseBtn = null; strip = null;
        titleTF = null; collTF = null; headTF = null; footTF = null; hdrs = null; cols = null;
    }

    // The onLoad build ran before the archive arrived: it comes down first (its tabs closed, the one it showed
    // hidden), then the panel is rebuilt on the archived spot, fold and tab, unless the master switch was saved off.
    public function loadState(config:Object):Void {
        if (config == null) return;
        removeConsole();
        var c:Object = config.FindEntry("cnc");
        if (c !== undefined) collapsed = (c == 1);
        var t:Object = config.FindEntry("cnt");
        if (t !== undefined) {
            cur = 0;
            for (var i:Number = 0; i < tabs.length; i++) {
                if (tabs[i].key() == String(t)) cur = i;
            }
        }
        var x:Object = config.FindEntry("cnx");
        var y:Object = config.FindEntry("cny");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
        }
        var v:Object = config.FindEntry("cnv");
        if (v === undefined || v != 0) create();
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        config.ReplaceEntry("cnv", isActive() ? 1 : 0);
        config.ReplaceEntry("cnc", collapsed ? 1 : 0);
        if (tabs.length > 0) config.ReplaceEntry("cnt", tabs[cur].key());
        keepSpot();
        if (isNaN(posX) || isNaN(posY)) return;
        config.ReplaceEntry("cnx", posX);
        config.ReplaceEntry("cny", posY);
    }

    // Deactivate teardown. The clip IS the active state, so the master switch and the module lifecycle take the
    // console down the same way; the tabs' feeds stop with it.
    public function cleanup():Void {
        removeConsole();
        for (var i:Number = 0; i < tabs.length; i++) tabs[i].stop();
    }
}
