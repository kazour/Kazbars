// KazBarsConsole.as - Buff ID Console for discovering and logging buff IDs.
//
// Chrome and palette are the inspect panel's (KazBarsInspect.as, and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, bronze hairline rules, square corners. The
// two columns keep their player/target identity, retuned onto the panel's own
// perk-pair blue and red so the console reads as part of the same HUD. The
// expanded footprint stays a fixed 500x320 — it is a transient discovery tool
// with no font-size config, so its dimensions are named constants at the values
// the panel's ratios land on at FS 12, and it folds to the same 190x24 bar the
// stopwatch and inspect panel do.
//
// Drag is clamped to the Stage and the position and fold state persist in the
// module config archive (cnx/cny/cnc) beside the pin and the two log toggles.
class KazBarsConsole {
    private var owner:Object;
    private var rootClip:MovieClip;
    private var consoleClip:MovieClip;
    private var chrome:MovieClip;
    private var m_Body:MovieClip;
    private var dragMC:MovieClip;
    private var collapseBtn:MovieClip;
    private var titleTF:TextField;
    private var collTF:TextField;
    private var playerText:TextField;
    private var targetText:TextField;
    private var coordTF:TextField;
    private var playerLog:String;
    private var targetLog:String;
    private var seenPlayer:Object;
    private var seenTarget:Object;
    private var playerCount:Number;
    private var targetCount:Number;
    private var MAX_ENTRIES:Number;
    private var collapsed:Boolean;
    private var posX:Number;
    private var posY:Number;
    private var dragX:Number;
    private var dragY:Number;
    private var curW:Number;
    private var curH:Number;
    public var logPlayerEnabled:Boolean;
    public var logTargetEnabled:Boolean;

    // Layout — the FS-12 equivalents of the inspect panel's ratios.
    private var CW:Number;
    private var CH:Number;
    private var PAD:Number;
    private var TITLE_H:Number;
    private var HDR_Y:Number;
    private var BODY_Y:Number;
    private var COL_W:Number;
    private var LINE:Number;
    private var BOX:Number;
    private var BTN:Number;
    private var BTN_W:Number;
    private var BTN_H:Number;
    private var COLL_W:Number;
    private var COLL_H:Number;
    private var COLL_PAD:Number;

    // Every log entry spells out its own face and size: Scaleform re-parses
    // htmlText from scratch, so setNewTextFormat on the field does not reach an
    // untagged run — it would fall back to the default serif device font.
    private var ENTRY_FONT:String;

    public function KazBarsConsole(kb:Object, root:MovieClip) {
        owner = kb;
        rootClip = root;
        playerLog = "";
        targetLog = "";
        seenPlayer = {};
        seenTarget = {};
        playerCount = 0;
        targetCount = 0;
        MAX_ENTRIES = 100;
        collapsed = false;
        posX = Number.NaN;   // unset until dragged or loaded from the archive
        posY = Number.NaN;
        dragX = 0;
        dragY = 0;
        logPlayerEnabled = true;
        logTargetEnabled = true;
        CW = 500;
        CH = 320;
        PAD = 10;
        TITLE_H = 25;
        HDR_Y = 33;
        BODY_Y = 56;
        COL_W = 230;
        LINE = 17;
        BOX = 12;
        BTN = 13;
        BTN_W = 60;
        BTN_H = 22;
        COLL_W = 190;
        COLL_H = 24;
        COLL_PAD = 7;
        curW = CW;
        curH = CH;
        ENTRY_FONT = '<font face="Arial" size="11" color="';
    }

    public function isActive():Boolean {
        return (consoleClip != null);
    }

    public function createConsole():Void {
        if (consoleClip != null) consoleClip.removeMovieClip();
        consoleClip = rootClip.createEmptyMovieClip("buffConsole", rootClip.getNextHighestDepth());

        var self:KazBarsConsole = this;

        // Chrome is its own child clip, not the console's own graphics, so it
        // can be cleared and redrawn without taking the contents with it.
        chrome = consoleClip.createEmptyMovieClip("chrome", consoleClip.getNextHighestDepth());
        // Everything below the title line, so folding is one _visible toggle.
        m_Body = consoleClip.createEmptyMovieClip("body", consoleClip.getNextHighestDepth());

        var tp:TextField = makeTF(m_Body, "tp", PAD, HDR_Y, COL_W, LINE + 2,
                                  12, true, 0x7FB0D6, "left");
        tp.text = "PLAYER BUFFS";
        var tt:TextField = makeTF(m_Body, "tt", CW / 2 + PAD, HDR_Y, COL_W, LINE + 2,
                                  12, true, 0xD68585, "left");
        tt.text = "TARGET BUFFS";

        playerText = makeLog("pt", PAD, playerLog);
        targetText = makeLog("tt2", CW / 2 + PAD, targetLog);

        var pcb:MovieClip = makeCheckbox("pcb", PAD + 130, HDR_Y + 2, null,
                                         logPlayerEnabled, 20);
        pcb.hit.onPress = function() {
            self.logPlayerEnabled = !self.logPlayerEnabled;
            this._parent.chk._visible = self.logPlayerEnabled;
        };

        var tcb:MovieClip = makeCheckbox("tcb", CW / 2 + PAD + 130, HDR_Y + 2, null,
                                         logTargetEnabled, 20);
        tcb.hit.onPress = function() {
            self.logTargetEnabled = !self.logTargetEnabled;
            this._parent.chk._visible = self.logTargetEnabled;
        };

        var kcb:MovieClip = makeCheckbox("kcb", PAD * 2, CH - 24, "Keep Open",
                                         owner.consolePinned, 104);
        kcb.hit.onPress = function() {
            self.owner.consolePinned = !self.owner.consolePinned;
            this._parent.chk._visible = self.owner.consolePinned;
        };

        var clr:MovieClip = m_Body.createEmptyMovieClip("clr", m_Body.getNextHighestDepth());
        clr._x = CW - PAD * 2 - BTN_W;
        clr._y = CH - PAD - BTN_H;
        clr.lineStyle(1, 0x4A3B22, 100);
        clr.beginFill(0x0C0A07, 90);
        rectPath(clr, 0, 0, BTN_W, BTN_H);
        clr.endFill();
        var clbl:TextField = makeTF(clr, "label", 0, Math.floor((BTN_H - LINE) / 2),
                                    BTN_W, LINE, 11, true, 0xC8C0B0, "center");
        clbl.text = "Clear";
        clr.useHandCursor = true;
        clr.onRelease = function() { self.clearLog(); };
        clr.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        clr.onRollOut = function() { this.label.textColor = 0xC8C0B0; };

        // Both title fields exist at once and swap on _visible: re-formatting one
        // field per fold would mean re-applying the TextFormat to its text every
        // time. Same reason the inspect panel carries a separate collapsed label.
        titleTF = makeTF(consoleClip, "title", PAD, 4, CW - PAD * 2 - BTN, LINE + 4,
                         14, true, 0xF7A22B, "center");
        titleTF.text = "BUFF CONSOLE";
        collTF = makeTF(consoleClip, "coll", COLL_PAD, Math.floor((COLL_H - LINE) / 2),
                        COLL_W - COLL_PAD * 2 - BTN, LINE, 12, true, 0xF7A22B, "left");
        collTF.text = "Console";

        // Live position readout — visible only while dragging, the panel's
        // convention. Shares the title line, right-aligned.
        coordTF = makeTF(consoleClip, "coords", PAD, 0, CW - PAD * 2 - BTN, LINE,
                         10, false, 0x999999, "right");
        coordTF._visible = false;

        // Drag handle over the title line, stopping short of the collapse glyph
        // so it keeps its own press. Redrawn per fold state.
        dragMC = consoleClip.createEmptyMovieClip("dh", consoleClip.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };

        // Bare glyph, no box — the family's collapse control.
        collapseBtn = consoleClip.createEmptyMovieClip("btnCollapse", consoleClip.getNextHighestDepth());
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        makeTF(collapseBtn, "label", 0, 0, BTN, BTN + 2, 11, true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };

        applyCollapsed();

        // Placed last: the clamp has to measure the plate actually on screen.
        // Centred on first open; after that wherever the user left it.
        consoleClip._x = isNaN(posX) ? (Stage.width - curW) / 2
                                     : clampPos(posX, Stage.width - curW);
        consoleClip._y = isNaN(posY) ? 250 : clampPos(posY, Stage.height - curH);
    }

    // =========================================================================
    // Collapse / chrome / widgets
    // =========================================================================

    public function toggleCollapsed():Void {
        collapsed = !collapsed;
        applyCollapsed();
    }

    // Two plates, not one at two heights: the 500x320 sheet, and the labelled
    // bar the stopwatch and inspect panel fold to. Everything that sits on the
    // title line — title, readout, glyph, drag strip — moves onto whichever
    // plate is on screen.
    private function applyCollapsed():Void {
        if (consoleClip == null) return;
        curW = collapsed ? COLL_W : CW;
        curH = collapsed ? COLL_H : CH;
        var pad:Number = collapsed ? COLL_PAD : PAD;
        var band:Number = collapsed ? COLL_H : TITLE_H;
        m_Body._visible = !collapsed;
        titleTF._visible = !collapsed;
        collTF._visible = collapsed;
        collapseBtn.label.text = collapsed ? "+" : "-";
        collapseBtn._x = curW - pad - BTN;
        collapseBtn._y = Math.floor((band - BTN) / 2);
        coordTF._x = pad;
        coordTF._y = Math.floor((band - LINE) / 2);
        coordTF._width = curW - pad * 2 - BTN;
        dragMC.clear();
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, curW - pad - BTN, band);
        dragMC.endFill();
        drawChrome(curW, curH);
    }

    private function drawChrome(w:Number, h:Number):Void {
        chrome.clear();
        chrome.beginFill(0x0C0A07, 90);
        rectPath(chrome, 0, 0, w, h);
        chrome.endFill();
        chrome.lineStyle(1, 0x000000, 100);
        rectPath(chrome, 0, 0, w, h);
        chrome.lineStyle(1, 0x4A3B22, 100);
        rectPath(chrome, 1, 1, w - 2, h - 2);
        // Bronze hairlines: under the title, under each column header, and one
        // down the middle — the panel's section rules doing column duty.
        // Collapsed the bar is the title line, so there is nothing to divide.
        if (h > COLL_H) {
            chrome.lineStyle(1, 0x6B5324, 100);
            chrome.moveTo(PAD, TITLE_H);
            chrome.lineTo(CW - PAD, TITLE_H);
            chrome.moveTo(PAD, BODY_Y - 5);
            chrome.lineTo(PAD + COL_W, BODY_Y - 5);
            chrome.moveTo(CW / 2 + PAD, BODY_Y - 5);
            chrome.lineTo(CW / 2 + PAD + COL_W, BODY_Y - 5);
            chrome.moveTo(CW / 2, TITLE_H);
            chrome.lineTo(CW / 2, CH - 35);
        }
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

    // The one selectable field in the panel — the whole point is copying an id
    // out. HTML so each entry can put its name in label grey and its id in
    // value green without a field per line. Lives on the body clip so a fold
    // takes it with everything else.
    private function makeLog(id:String, x:Number, html:String):TextField {
        var tf:TextField = makeTF(m_Body, id, x, BODY_Y, COL_W, CH - BODY_Y - 40,
                                  11, false, 0xC8C0B0, "left");
        tf.selectable = true;
        tf.multiline = true;
        tf.wordWrap = true;
        tf.html = true;
        tf.htmlText = html;
        return tf;
    }

    // `on` would be a parse error here — AS2 reserves it for clip handlers.
    private function makeCheckbox(name:String, x:Number, y:Number, label:String,
                                  checked:Boolean, hitW:Number):MovieClip {
        var c:MovieClip = m_Body.createEmptyMovieClip(name, m_Body.getNextHighestDepth());
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
        if (label != null) {
            var lbl:TextField = makeTF(c, "lbl", BOX + 4, -3, 80, LINE,
                                       10, false, 0xC8C0B0, "left");
            lbl.text = label;
        }
        // Hit area is a child at depth 0 so it sits under the art but still
        // takes the press across the whole label.
        var hit:MovieClip = c.createEmptyMovieClip("hit", 0);
        hit.beginFill(0, 0);
        rectPath(hit, -4, -4, hitW, BOX + 8);
        hit.endFill();
        hit.useHandCursor = true;
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
        consoleClip.startDrag(false, 0, 0, Math.max(0, Stage.width - curW),
                              Math.max(0, Stage.height - curH));
        dragX = consoleClip._x;
        dragY = consoleClip._y;
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsConsole = this;
        dh.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(dh:MovieClip):Void {
        consoleClip.stopDrag();
        delete dh.onMouseMove;
        coordTF._visible = false;
        capturePos();
        // Collapsed, the bar is small and labelled and reads as a button, so a
        // press that never moved it opens the console again; a real drag still
        // just moves it. Expanded, a stray click on the title must not fold it.
        if (collapsed && Math.abs(consoleClip._x - dragX) < 2
                      && Math.abs(consoleClip._y - dragY) < 2) {
            toggleCollapsed();
        }
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(consoleClip._x) + ", " + Math.round(consoleClip._y);
    }

    // The clip is destroyed every time the console closes, so its position has
    // to be read back into the class before it goes.
    private function capturePos():Void {
        if (consoleClip == null) return;
        posX = consoleClip._x;
        posY = consoleClip._y;
    }

    public function loadState(config:Object):Void {
        if (config == null) return;
        var c:Object = config.FindEntry("cnc");
        if (c !== undefined) collapsed = (c == 1);
        var x:Object = config.FindEntry("cnx");
        var y:Object = config.FindEntry("cny");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        config.ReplaceEntry("cnc", collapsed ? 1 : 0);
        capturePos();
        if (isNaN(posX) || isNaN(posY)) return;
        config.ReplaceEntry("cnx", posX);
        config.ReplaceEntry("cny", posY);
    }

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }

    // =========================================================================
    // Logging
    // =========================================================================

    public function removeConsole():Void {
        capturePos();
        if (consoleClip != null) { consoleClip.removeMovieClip(); consoleClip = null; }
        chrome = null; m_Body = null; dragMC = null; collapseBtn = null;
        titleTF = null; collTF = null; playerText = null; targetText = null; coordTF = null;
    }

    // Names come from the game, so the markup has to survive an "&" in one.
    private function esc(s:String):String {
        return s.split("&").join("&amp;").split("<").join("&lt;");
    }

    // Both runs carry face + size, not just colour: an htmlText run without
    // them renders in the player's default serif font whatever the field's
    // TextFormat says. Name in label grey, id in value green.
    private function entry(n:String, id:Number):String {
        return ENTRY_FONT + '#C8C0B0">' + esc(n) + "</font><br>"
             + ENTRY_FONT + '#7AC142">ID: ' + id + "</font><br><br>";
    }

    public function logPlayer(n:String, id:Number):Void {
        if (!logPlayerEnabled) return;
        if (seenPlayer[id] == true) return;
        seenPlayer[id] = true;
        playerCount++;
        var limit:Number = logTargetEnabled ? MAX_ENTRIES : MAX_ENTRIES * 2;
        if (playerCount > limit) return;
        playerLog = entry(n, id) + playerLog;
        if (playerText != null) playerText.htmlText = playerLog;
    }

    public function logTarget(n:String, id:Number):Void {
        if (!logTargetEnabled) return;
        if (seenTarget[id] == true) return;
        seenTarget[id] = true;
        targetCount++;
        var limit:Number = logPlayerEnabled ? MAX_ENTRIES : MAX_ENTRIES * 2;
        if (targetCount > limit) return;
        targetLog = entry(n, id) + targetLog;
        if (targetText != null) targetText.htmlText = targetLog;
    }

    public function clearLog():Void {
        playerLog = ""; targetLog = "";
        seenPlayer = {}; seenTarget = {};
        playerCount = 0; targetCount = 0;
        if (playerText != null) playerText.htmlText = "";
        if (targetText != null) targetText.htmlText = "";
    }
}
