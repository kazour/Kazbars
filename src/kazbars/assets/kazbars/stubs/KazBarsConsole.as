// KazBarsConsole.as - Buff ID Console for discovering and logging buff IDs.
//
// Chrome and palette are the inspect panel's (KazBarsInspect.as, and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, bronze hairline rules, square corners. The
// two columns keep their player/target identity, retuned onto the panel's own
// perk-pair blue and red so the console reads as part of the same HUD. The
// footprint stays a fixed 500x320 — it is a transient discovery tool with no
// font-size config, so its dimensions are named constants at the values the
// panel's ratios land on at FS 12.
//
// Drag is clamped to the Stage and the position persists in the module config
// archive (cnx/cny) beside the pin and the two log toggles.
class KazBarsConsole {
    private var owner:Object;
    private var rootClip:MovieClip;
    private var consoleClip:MovieClip;
    private var chrome:MovieClip;
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
    private var posX:Number;
    private var posY:Number;
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
    private var BTN_W:Number;
    private var BTN_H:Number;

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
        logPlayerEnabled = true;
        logTargetEnabled = true;
        posX = Number.NaN;   // unset until dragged or loaded from the archive
        posY = Number.NaN;
        CW = 500;
        CH = 320;
        PAD = 10;
        TITLE_H = 25;
        HDR_Y = 33;
        BODY_Y = 56;
        COL_W = 230;
        LINE = 17;
        BOX = 12;
        BTN_W = 60;
        BTN_H = 22;
    }

    public function isActive():Boolean {
        return (consoleClip != null);
    }

    public function createConsole():Void {
        if (consoleClip != null) consoleClip.removeMovieClip();
        consoleClip = rootClip.createEmptyMovieClip("buffConsole", rootClip.getNextHighestDepth());
        // Centred on first open; after that wherever the user left it.
        consoleClip._x = isNaN(posX) ? (Stage.width - CW) / 2 : clampPos(posX, Stage.width - CW);
        consoleClip._y = isNaN(posY) ? 250 : clampPos(posY, Stage.height - CH);

        var self:KazBarsConsole = this;

        // Chrome is its own child clip, not the console's own graphics, so it
        // can be cleared and redrawn without taking the contents with it.
        chrome = consoleClip.createEmptyMovieClip("chrome", consoleClip.getNextHighestDepth());
        drawChrome();

        var titleTF:TextField = makeTF(consoleClip, "title", PAD, 4, CW - PAD * 2, LINE + 4,
                                       14, true, 0xF7A22B, "center");
        titleTF.text = "BUFF CONSOLE";

        // Live position readout — visible only while dragging, the panel's
        // convention. Shares the title band, right-aligned.
        coordTF = makeTF(consoleClip, "coords", PAD, 6, CW - PAD * 2, LINE,
                         10, false, 0x999999, "right");
        coordTF._visible = false;

        var tp:TextField = makeTF(consoleClip, "tp", PAD, HDR_Y, COL_W, LINE + 2,
                                  12, true, 0x7FB0D6, "left");
        tp.text = "PLAYER BUFFS";
        var tt:TextField = makeTF(consoleClip, "tt", CW / 2 + PAD, HDR_Y, COL_W, LINE + 2,
                                  12, true, 0xD68585, "left");
        tt.text = "TARGET BUFFS";

        playerText = makeLog("pt", PAD, playerLog);
        targetText = makeLog("tt2", CW / 2 + PAD, targetLog);

        // Drag handle over the title band - created before the checkboxes so
        // they stay on top of it.
        var dh:MovieClip = consoleClip.createEmptyMovieClip("dh", consoleClip.getNextHighestDepth());
        dh.beginFill(0, 0);
        rectPath(dh, 0, 0, CW, TITLE_H);
        dh.endFill();
        dh._self = this;
        dh.useHandCursor = true;
        dh.onPress = function() { this._self.beginDrag(this); };
        dh.onRelease = dh.onReleaseOutside = function() { this._self.endDrag(this); };

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

        var clr:MovieClip = consoleClip.createEmptyMovieClip("clr", consoleClip.getNextHighestDepth());
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
    }

    // =========================================================================
    // Chrome + widgets
    // =========================================================================

    private function drawChrome():Void {
        chrome.clear();
        chrome.beginFill(0x0C0A07, 90);
        rectPath(chrome, 0, 0, CW, CH);
        chrome.endFill();
        chrome.lineStyle(1, 0x000000, 100);
        rectPath(chrome, 0, 0, CW, CH);
        chrome.lineStyle(1, 0x4A3B22, 100);
        rectPath(chrome, 1, 1, CW - 2, CH - 2);
        // Bronze hairlines: under the title, under each column header, and one
        // down the middle — the panel's section rules doing column duty.
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
    // value green without a field per line.
    private function makeLog(id:String, x:Number, html:String):TextField {
        var tf:TextField = makeTF(consoleClip, id, x, BODY_Y, COL_W, CH - BODY_Y - 40,
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
        var c:MovieClip = consoleClip.createEmptyMovieClip(name, consoleClip.getNextHighestDepth());
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
        consoleClip.startDrag(false, 0, 0, Math.max(0, Stage.width - CW),
                              Math.max(0, Stage.height - CH));
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
        var x:Object = config.FindEntry("cnx");
        var y:Object = config.FindEntry("cny");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
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
        chrome = null; playerText = null; targetText = null; coordTF = null;
    }

    // Names come from the game, so the markup has to survive an "&" in one.
    private function esc(s:String):String {
        return s.split("&").join("&amp;").split("<").join("&lt;");
    }

    private function entry(n:String, id:Number):String {
        return esc(n) + '<br><font color="#7AC142">ID: ' + id + "</font><br><br>";
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
