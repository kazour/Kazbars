// KzGridsConsole.as - Buff ID Console for discovering and logging buff IDs
class KzGridsConsole {
    private var owner:Object;
    private var rootClip:MovieClip;
    private var consoleClip:MovieClip;
    private var playerText:TextField;
    private var targetText:TextField;
    private var playerLog:String;
    private var targetLog:String;
    private var seenPlayer:Object;
    private var seenTarget:Object;
    private var playerCount:Number;
    private var targetCount:Number;
    private var MAX_ENTRIES:Number;
    public var logPlayerEnabled:Boolean;
    public var logTargetEnabled:Boolean;

    public function KzGridsConsole(kb:Object, root:MovieClip) {
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
    }

    public function isActive():Boolean {
        return (consoleClip != null);
    }

    public function createConsole():Void {
        if (consoleClip != null) consoleClip.removeMovieClip();
        consoleClip = rootClip.createEmptyMovieClip("buffConsole", rootClip.getNextHighestDepth());
        var cw:Number = 500, ch:Number = 320, pw:Number = 240;
        consoleClip._x = (Stage.width - cw) / 2;
        consoleClip._y = 250;
        consoleClip.beginFill(0x1a1a1a, 90);
        consoleClip.lineStyle(2, 0x444444, 100);
        consoleClip.moveTo(0, 0); consoleClip.lineTo(cw, 0); consoleClip.lineTo(cw, ch); consoleClip.lineTo(0, ch); consoleClip.lineTo(0, 0);
        consoleClip.endFill();
        consoleClip.lineStyle(1, 0x444444, 100);
        consoleClip.moveTo(cw / 2, 25); consoleClip.lineTo(cw / 2, ch - 35);

        var titleFmt:TextFormat = new TextFormat();
        titleFmt.font = "Arial"; titleFmt.size = 12; titleFmt.bold = true;
        var tp:TextField = consoleClip.createTextField("tp", consoleClip.getNextHighestDepth(), 10, 5, pw, 20);
        tp.selectable = false; tp.embedFonts = false; tp.text = "PLAYER BUFFS"; tp.textColor = 0x66AAFF; tp.setTextFormat(titleFmt);
        var tt:TextField = consoleClip.createTextField("tt", consoleClip.getNextHighestDepth(), cw / 2 + 10, 5, pw, 20);
        tt.selectable = false; tt.embedFonts = false; tt.text = "TARGET BUFFS"; tt.textColor = 0xFF6666; tt.setTextFormat(titleFmt);

        var textFmt:TextFormat = new TextFormat();
        textFmt.font = "Arial"; textFmt.size = 11;

        playerText = consoleClip.createTextField("pt", consoleClip.getNextHighestDepth(), 10, 28, pw, ch - 70);
        playerText.selectable = true; playerText.multiline = true; playerText.wordWrap = true; playerText.embedFonts = false;
        playerText.textColor = 0xCCCCCC;
        playerText.text = playerLog;
        playerText.setTextFormat(textFmt);
        playerText.setNewTextFormat(textFmt);

        targetText = consoleClip.createTextField("tt2", consoleClip.getNextHighestDepth(), cw / 2 + 10, 28, pw, ch - 70);
        targetText.selectable = true; targetText.multiline = true; targetText.wordWrap = true; targetText.embedFonts = false;
        targetText.textColor = 0xCCCCCC;
        targetText.text = targetLog;
        targetText.setTextFormat(textFmt);
        targetText.setNewTextFormat(textFmt);

        // Drag handle (title bar area) - created first so checkboxes are on top
        var dragHandle:MovieClip = consoleClip.createEmptyMovieClip("dh", consoleClip.getNextHighestDepth());
        dragHandle.beginFill(0x000000, 0);
        dragHandle.moveTo(0, 0); dragHandle.lineTo(cw, 0); dragHandle.lineTo(cw, 25); dragHandle.lineTo(0, 25); dragHandle.lineTo(0, 0); dragHandle.endFill();
        dragHandle.onPress = function() { this._parent.startDrag(); };
        dragHandle.onRelease = dragHandle.onReleaseOutside = function() { this._parent.stopDrag(); };
        dragHandle.useHandCursor = true;

        var self:KzGridsConsole = this;

        // Player logging checkbox (next to PLAYER BUFFS title)
        var pcb:MovieClip = consoleClip.createEmptyMovieClip("pcb", consoleClip.getNextHighestDepth());
        pcb._x = 130; pcb._y = 7;
        var pbox:MovieClip = pcb.createEmptyMovieClip("box", 1);
        pbox.lineStyle(1, 0xFFFFFF, 100);
        pbox.beginFill(0x333333, 100);
        pbox.moveTo(0, 0); pbox.lineTo(12, 0); pbox.lineTo(12, 12); pbox.lineTo(0, 12); pbox.lineTo(0, 0);
        pbox.endFill();
        var pchk:MovieClip = pcb.createEmptyMovieClip("chk", 2);
        pchk.lineStyle(2, 0x99DD66, 100);
        pchk.moveTo(2, 6); pchk.lineTo(5, 10); pchk.lineTo(10, 2);
        pchk._visible = logPlayerEnabled;
        var phit:MovieClip = pcb.createEmptyMovieClip("hit", 0);
        phit.beginFill(0, 0);
        phit.moveTo(-4, -4); phit.lineTo(16, -4); phit.lineTo(16, 16); phit.lineTo(-4, 16); phit.lineTo(-4, -4);
        phit.endFill();
        phit.useHandCursor = true;
        phit.onPress = function() {
            self.logPlayerEnabled = !self.logPlayerEnabled;
            pchk._visible = self.logPlayerEnabled;
        };

        // Target logging checkbox (next to TARGET BUFFS title)
        var tcb:MovieClip = consoleClip.createEmptyMovieClip("tcb", consoleClip.getNextHighestDepth());
        tcb._x = cw / 2 + 130; tcb._y = 7;
        var tbox:MovieClip = tcb.createEmptyMovieClip("box", 1);
        tbox.lineStyle(1, 0xFFFFFF, 100);
        tbox.beginFill(0x333333, 100);
        tbox.moveTo(0, 0); tbox.lineTo(12, 0); tbox.lineTo(12, 12); tbox.lineTo(0, 12); tbox.lineTo(0, 0);
        tbox.endFill();
        var tchk:MovieClip = tcb.createEmptyMovieClip("chk", 2);
        tchk.lineStyle(2, 0x99DD66, 100);
        tchk.moveTo(2, 6); tchk.lineTo(5, 10); tchk.lineTo(10, 2);
        tchk._visible = logTargetEnabled;
        var thit:MovieClip = tcb.createEmptyMovieClip("hit", 0);
        thit.beginFill(0, 0);
        thit.moveTo(-4, -4); thit.lineTo(16, -4); thit.lineTo(16, 16); thit.lineTo(-4, 16); thit.lineTo(-4, -4);
        thit.endFill();
        thit.useHandCursor = true;
        thit.onPress = function() {
            self.logTargetEnabled = !self.logTargetEnabled;
            tchk._visible = self.logTargetEnabled;
        };

        // Keep Open checkbox (bottom-left)
        var kcb:MovieClip = consoleClip.createEmptyMovieClip("kcb", consoleClip.getNextHighestDepth());
        kcb._x = 20; kcb._y = ch - 24;
        var kbox:MovieClip = kcb.createEmptyMovieClip("box", 1);
        kbox.lineStyle(1, 0xFFFFFF, 100);
        kbox.beginFill(0x333333, 100);
        kbox.moveTo(0, 0); kbox.lineTo(12, 0); kbox.lineTo(12, 12); kbox.lineTo(0, 12); kbox.lineTo(0, 0);
        kbox.endFill();
        var kchk:MovieClip = kcb.createEmptyMovieClip("chk", 2);
        kchk.lineStyle(2, 0x99DD66, 100);
        kchk.moveTo(2, 6); kchk.lineTo(5, 10); kchk.lineTo(10, 2);
        kchk._visible = owner.consolePinned;
        var klbl:TextField = kcb.createTextField("lbl", kcb.getNextHighestDepth(), 16, -2, 80, 16);
        klbl.selectable = false; klbl.embedFonts = false;
        klbl.text = "Keep Open"; klbl.textColor = 0xAAAAAA;
        var kfmt:TextFormat = new TextFormat();
        kfmt.font = "Arial"; kfmt.size = 10;
        klbl.setTextFormat(kfmt);
        var khit:MovieClip = kcb.createEmptyMovieClip("hit", 0);
        khit.beginFill(0, 0);
        khit.moveTo(-4, -4); khit.lineTo(100, -4); khit.lineTo(100, 16); khit.lineTo(-4, 16); khit.lineTo(-4, -4);
        khit.endFill();
        khit.useHandCursor = true;
        khit.onPress = function() {
            self.owner.consolePinned = !self.owner.consolePinned;
            kchk._visible = self.owner.consolePinned;
        };

        // Clear button
        var clr:MovieClip = consoleClip.createEmptyMovieClip("clr", consoleClip.getNextHighestDepth());
        clr._x = cw - 80; clr._y = ch - 28;
        clr.beginFill(0x333333, 100); clr.lineStyle(1, 0x666666, 100);
        clr.moveTo(0, 0); clr.lineTo(60, 0); clr.lineTo(60, 22); clr.lineTo(0, 22); clr.lineTo(0, 0); clr.endFill();
        var clbl:TextField = clr.createTextField("l", clr.getNextHighestDepth(), 0, 3, 60, 18);
        clbl.selectable = false; clbl.embedFonts = false; clbl.text = "Clear"; clbl.textColor = 0xFFFFFF;
        var btnFmt:TextFormat = new TextFormat();
        btnFmt.font = "Arial"; btnFmt.size = 11; btnFmt.bold = true; btnFmt.align = "center"; clbl.setTextFormat(btnFmt);
        clr.onRelease = function() { self.clearLog(); }; clr.useHandCursor = true;

    }

    public function removeConsole():Void {
        if (consoleClip != null) { consoleClip.removeMovieClip(); consoleClip = null; }
        playerText = null; targetText = null;
    }

    public function logPlayer(n:String, id:Number):Void {
        if (!logPlayerEnabled) return;
        if (seenPlayer[id] == true) return;
        seenPlayer[id] = true;
        playerCount++;
        var limit:Number = logTargetEnabled ? MAX_ENTRIES : MAX_ENTRIES * 2;
        if (playerCount > limit) return;
        playerLog = n + "\nID: " + id + "\n\n" + playerLog;
        if (playerText != null) {
            playerText.text = playerLog;
            var fmt:TextFormat = new TextFormat();
            fmt.font = "Arial"; fmt.size = 11;
            playerText.setTextFormat(fmt);
        }
    }

    public function logTarget(n:String, id:Number):Void {
        if (!logTargetEnabled) return;
        if (seenTarget[id] == true) return;
        seenTarget[id] = true;
        targetCount++;
        var limit:Number = logPlayerEnabled ? MAX_ENTRIES : MAX_ENTRIES * 2;
        if (targetCount > limit) return;
        targetLog = n + "\nID: " + id + "\n\n" + targetLog;
        if (targetText != null) {
            targetText.text = targetLog;
            var fmt:TextFormat = new TextFormat();
            fmt.font = "Arial"; fmt.size = 11;
            targetText.setTextFormat(fmt);
        }
    }

    public function clearLog():Void {
        playerLog = ""; targetLog = "";
        seenPlayer = {}; seenTarget = {};
        playerCount = 0; targetCount = 0;
        if (playerText != null) playerText.text = "";
        if (targetText != null) targetText.text = "";
    }
}
