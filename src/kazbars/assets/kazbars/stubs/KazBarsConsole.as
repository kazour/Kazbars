// KazBarsConsole.as - Buff ID Console for discovering and logging buff IDs.
//
// Chrome and palette are the family's, inherited from KazBarsPanel (and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, bronze hairline rules, square corners. The
// two columns keep their player/target identity, retuned onto the panel's own
// perk-pair blue and red so the console reads as part of the same HUD. Every
// dimension is a ratio of a base font size, the family's arrangement, so the
// console folds to the same bar the stopwatch and inspect panel do at any size
// rather than only at the default 12. The expanded footprint follows the
// checked sides — 500x320 with both columns at FS 12, a single 280-wide column
// with one, a short toggle strip with none — and a side flip rebuilds the clip
// in place rather than reflowing every child.
//
// Drag is clamped to the Stage and the position and fold state persist in the
// module config archive (cnx/cny/cnc) beside the master switch (cnv) and the
// two log toggles.
class KazBarsConsole extends KazBarsPanel implements KazBarsModule {
    private var m_Body:MovieClip;
    private var titleTF:TextField;
    private var collTF:TextField;
    private var playerText:TextField;
    private var targetText:TextField;
    private var playerLog:String;
    private var targetLog:String;
    private var seenPlayer:Object;
    private var seenTarget:Object;
    private var playerCount:Number;
    private var targetCount:Number;
    private var MAX_ENTRIES:Number;
    private var logPlayerEnabled:Boolean;
    private var logTargetEnabled:Boolean;

    // Layout beyond the base set. CW/CH are the current build's expanded
    // footprint, picked per checked sides.
    private var CW:Number;
    private var CH:Number;
    private var CW_FULL:Number;   // 41.67 both columns
    private var CW_ONE:Number;    // 23.33 one column (or none)
    private var CH_FULL:Number;   // 26.67
    private var CH_NONE:Number;   // 8.33  no columns: title, toggles, bottom bar
    private var CB_OFF:Number;    // 9.17  header text -> its checkbox
    private var UNIT:Number;      // header + checkbox pair width
    private var HDR_Y:Number;     // 2.75
    private var BODY_Y:Number;    // 4.67
    private var COL_W:Number;     // 19.17
    // Bottom strip: the Clear button's band. The mid rule stops just above the
    // button, the logs a little higher still, so both are measured up from the
    // plate's bottom edge rather than baked as a gap.
    private var RULE_BOT:Number;  // 2.92
    private var LOG_BOT:Number;   // 3.33

    // Every log entry spells out its own face and size: Scaleform re-parses
    // htmlText from scratch, so setNewTextFormat on the field does not reach an
    // untagged run — it would fall back to the default serif device font.
    private var ENTRY_FONT:String;

    public function KazBarsConsole(root:MovieClip) {
        super(root);
        playerLog = "";
        targetLog = "";
        seenPlayer = {};
        seenTarget = {};
        playerCount = 0;
        targetCount = 0;
        MAX_ENTRIES = 100;
        logPlayerEnabled = true;
        logTargetEnabled = true;
        // Nothing has to call configure() for the console to be usable, so it
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
        applyBaseSize(Number(cfg.fontSize));
        HDR_Y = Math.round(FS * 2.75);
        BODY_Y = Math.round(FS * 4.67);
        COL_W = Math.round(FS * 19.17);
        RULE_BOT = Math.round(FS * 2.92);
        LOG_BOT = Math.round(FS * 3.33);
        CW_FULL = Math.round(FS * 41.67);
        CW_ONE = Math.round(FS * 23.33);
        CH_FULL = Math.round(FS * 26.67);
        CH_NONE = Math.round(FS * 8.33);
        CB_OFF = Math.round(FS * 9.17);
        UNIT = CB_OFF + BOX;
        CW = CW_FULL;
        CH = CH_FULL;
        curW = CW;
        curH = CH;
        ENTRY_FONT = '<font face="Arial" size="'
                   + Math.max(9, Math.round(FS * 0.9)) + '" color="';
    }

    public function isActive():Boolean {
        return (panelClip != null);
    }

    public function previewKey():String { return "console"; }
    public function previewLabel():String { return "Buff Console"; }

    // Tool class: already interactive in normal play, dragged by its own title
    // strip, so preview has nothing to add or take away.
    public function previewOn():Void {}
    public function previewOff():Void {}

    // Master switch: the console's active state IS the clip's existence.
    // create()/removeConsole() already carry logs, position and fold across
    // the flip, so no second flag can drift from the truth.
    public function setActive(shown:Boolean):Void {
        if (shown) {
            if (panelClip == null) create();
        } else {
            removeConsole();
        }
    }

    public function create():Void {
        if (panelClip != null) panelClip.removeMovieClip();
        panelClip = rootClip.createEmptyMovieClip("buffConsole", rootClip.getNextHighestDepth());

        var self:KazBarsConsole = this;

        // Footprint follows the checked sides: two columns, a lone column, or
        // just the toggle strip when both are off.
        var both:Boolean = logPlayerEnabled && logTargetEnabled;
        CW = both ? CW_FULL : CW_ONE;
        CH = (logPlayerEnabled || logTargetEnabled) ? CH_FULL : CH_NONE;

        // Chrome is its own child clip, not the console's own graphics, so it
        // can be cleared and redrawn without taking the contents with it.
        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());
        // Everything below the title line, so folding is one _visible toggle.
        m_Body = panelClip.createEmptyMovieClip("body", panelClip.getNextHighestDepth());

        // Header + checkbox pairs survive an unchecked side — drop the pair
        // and there is no way to bring the column back. A checked side keeps
        // the left (or only) column; an unchecked pair parks right-aligned on
        // the header line with nothing below it.
        var px:Number = (!logPlayerEnabled && logTargetEnabled) ? CW - PAD - UNIT : PAD;
        var tx:Number = both ? CW / 2 + PAD
                             : (logTargetEnabled ? PAD : CW - PAD - UNIT);
        var logW:Number = both ? COL_W : CW - PAD * 2;

        var tp:TextField = makeTF(m_Body, "tp", px, HDR_Y, CB_OFF, LINE + 2,
                                  FS, true, 0x7FB0D6, "left");
        tp.text = "PLAYER BUFFS";
        var tt:TextField = makeTF(m_Body, "tt", tx, HDR_Y, CB_OFF, LINE + 2,
                                  FS, true, 0xD68585, "left");
        tt.text = "TARGET BUFFS";

        playerText = null;
        targetText = null;
        if (logPlayerEnabled) playerText = makeLog("pt", PAD, logW, playerLog);
        if (logTargetEnabled) targetText = makeLog("tt2", both ? CW / 2 + PAD : PAD,
                                                   logW, targetLog);

        var pcb:MovieClip = makeCheckbox(m_Body, "pcb", px + CB_OFF, HDR_Y + 2,
                                         logPlayerEnabled, BOX + 8);
        pcb.hit.onPress = function() {
            self.logPlayerEnabled = !self.logPlayerEnabled;
            self.rebuild();
        };

        var tcb:MovieClip = makeCheckbox(m_Body, "tcb", tx + CB_OFF, HDR_Y + 2,
                                         logTargetEnabled, BOX + 8);
        tcb.hit.onPress = function() {
            self.logTargetEnabled = !self.logTargetEnabled;
            self.rebuild();
        };

        var clr:MovieClip = makeButton(m_Body, "clr", "Clear", CW - PAD * 2 - BTN_W,
                                       CH - PAD - BTN_H, Math.max(9, Math.round(FS * 0.9)));
        clr.onRelease = function() { self.clearLog(); };

        // Both title fields exist at once and swap on _visible: re-formatting one
        // field per fold would mean re-applying the TextFormat to its text every
        // time. Same reason the inspect panel carries a separate collapsed label.
        titleTF = makeTF(panelClip, "title", PAD, Math.floor((TITLE_H - (LINE + 4)) / 2),
                         CW - PAD * 2 - BTN, LINE + 4,
                         NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "Buff Console";
        collTF = makeCollapsedLabel("Console");

        makeCoordReadout(0, CW - PAD * 2 - BTN, LINE);

        // Drag handle over the title line, stopping short of the collapse glyph
        // so it keeps its own press. Redrawn per fold state.
        makeDragStrip("dh");

        makeCollapseBtn();

        applyCollapsed();

        // Placed last: the clamp has to measure the plate actually on screen.
        // Centred on first open; after that wherever the user left it.
        panelClip._x = isNaN(posX) ? (Stage.width - curW) / 2
                                   : clampPos(posX, Stage.width - curW);
        panelClip._y = isNaN(posY) ? 250 : clampPos(posY, Stage.height - curH);
    }

    // =========================================================================
    // Collapse / chrome / widgets
    // =========================================================================

    // A side flip changes the whole footprint, so the console rebuilds in
    // place — logs live in the class strings and the position is captured
    // and re-clamped, so nothing is lost.
    private function rebuild():Void {
        capturePos();
        create();
    }

    // Two plates, not one at two heights: the 500x320 sheet, and the labelled
    // bar the stopwatch and inspect panel fold to. Everything that sits on the
    // title line — title, readout, glyph, drag strip — moves onto whichever
    // plate is on screen.
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
        drawPlate(w, h);
        // Bronze hairlines: under the title, under each column that is on
        // screen, and one down the middle when both are — the panel's section
        // rules doing column duty. An unchecked side's parked pair gets no
        // rule (nothing below it), and collapsed the bar is the title line,
        // so there is nothing to divide.
        if (h > COLL_H) {
            var both:Boolean = logPlayerEnabled && logTargetEnabled;
            hairline(PAD, TITLE_H, CW - PAD, TITLE_H);
            if (logPlayerEnabled || logTargetEnabled) {
                hairline(PAD, BODY_Y - 5, PAD + (both ? COL_W : CW - PAD * 2), BODY_Y - 5);
            }
            if (both) {
                hairline(CW / 2 + PAD, BODY_Y - 5, CW / 2 + PAD + COL_W, BODY_Y - 5);
                hairline(CW / 2, TITLE_H, CW / 2, CH - RULE_BOT);
            }
        }
    }

    // The one selectable field in the panel — the whole point is copying an id
    // out. HTML so each entry can put its name in label grey and its id in
    // value green without a field per line. Lives on the body clip so a fold
    // takes it with everything else.
    private function makeLog(id:String, x:Number, w:Number, html:String):TextField {
        var tf:TextField = makeTF(m_Body, id, x, BODY_Y, w, CH - BODY_Y - LOG_BOT,
                                  Math.max(9, Math.round(FS * 0.9)), false,
                                  0xC8C0B0, "left");
        tf.selectable = true;
        tf.multiline = true;
        tf.wordWrap = true;
        tf.html = true;
        tf.htmlText = html;
        return tf;
    }

    // =========================================================================
    // Logging
    // =========================================================================

    public function removeConsole():Void {
        capturePos();
        if (panelClip != null) { panelClip.removeMovieClip(); panelClip = null; }
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

    // =========================================================================
    // Persistence (module config archive — permanent for every user)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null) return;
        var p:Object = config.FindEntry("log_p");
        if (p !== undefined) logPlayerEnabled = (p == 1);
        var t:Object = config.FindEntry("log_t");
        if (t !== undefined) logTargetEnabled = (t == 1);
        var c:Object = config.FindEntry("cnc");
        if (c !== undefined) collapsed = (c == 1);
        var x:Object = config.FindEntry("cnx");
        var y:Object = config.FindEntry("cny");
        if (x !== undefined && y !== undefined) {
            posX = Number(x);
            posY = Number(y);
        }
        // The onLoad build ran before the archive arrived: rebuild on the
        // archived spot, fold and sides — or take the panel down when the
        // master switch was saved off.
        var v:Object = config.FindEntry("cnv");
        if (v !== undefined && v == 0) removeConsole();
        else create();
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        config.ReplaceEntry("cnv", isActive() ? 1 : 0);
        config.ReplaceEntry("log_p", logPlayerEnabled ? 1 : 0);
        config.ReplaceEntry("log_t", logTargetEnabled ? 1 : 0);
        config.ReplaceEntry("cnc", collapsed ? 1 : 0);
        capturePos();
        if (isNaN(posX) || isNaN(posY)) return;
        config.ReplaceEntry("cnx", posX);
        config.ReplaceEntry("cny", posY);
    }

    // Deactivate teardown. The clip IS the active state, so the master
    // switch and the module lifecycle take the console down the same way.
    public function cleanup():Void {
        removeConsole();
    }
}
