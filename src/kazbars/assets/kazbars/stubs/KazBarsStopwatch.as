// KazBarsStopwatch.as - In-game count-up stopwatch panel (Start / Pause / Reset).
// Runtime-drawn chrome + dynamic text fields (Arial resolves against the faces
// embedded in base.swf), so it needs no new symbols. Clicks are ordinary
// Scaleform GUI input: fullscreen-safe, never steals game focus.
//
// Chrome, palette and geometry are the inspect panel's (KazBarsInspect.as, and
// docs/inspect-panel.md section 5): warm near-black plate, 1px black-over-bronze
// double frame, Conan-orange title, square corners, and every dimension a
// Math.round(FS * ratio) off the baked fontSize. The collapsed bar is FS*15.8 x
// FS*2 — the same bar the inspect panel folds to — so the two pair at any font
// size, not just at the default 12 the numbers used to be hard-coded for.
//
// Positioning mirrors the cast timer: X/Y are baked into config (the only
// position that survives relaunch on /loadclip default clients; the title bar
// shows live coordinates while dragging so users can copy them into the app);
// aoc.exe clients persist drag position + collapsed state via the module
// config archive (swx/swy/swc).
//
// Driven from KazBars: createPanel() in onLoad, loadState()/saveState() from
// the module archive, cleanup() on deactivate.
class KazBarsStopwatch {
    private var rootClip:MovieClip;

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;
    private var FS:Number;

    // Layout — all derived from FS in configure() (AS2 has no const)
    private var PAD:Number;       // 0.85  plate padding
    private var W:Number;         // 15.8  the inspect panel's collapsed width
    private var H:Number;         // 8.0   expanded plate
    private var H_COLLAPSED:Number; // 2.0  its collapsed bar
    private var TITLE_H:Number;   // 1.85  title band, above the rule
    private var COLL_PAD:Number;  // 0.55  collapsed-bar inset (inspect/console)
    private var BTN:Number;       // 1.1   collapse glyph box
    private var NAME_FS:Number;   // 1.15  title font
    private var TIME_FS:Number;   // 2.0   time readout font
    private var LINE_H:Number;    // 1.4x FS, the height one line of text needs
    private var NAME_H:Number;    // 1.4x NAME_FS
    private var TIME_H:Number;    // 2.7   time readout field
    private var LEAD:Number;      // 0.15  TextFormat.leading
    private var BTN_W:Number;     // derived: three buttons across the plate
    private var BTN_H:Number;     // 1.85
    private var BTN_GAP:Number;   // 0.42
    private var BTN_PAD:Number;   // 0.5   button row inset (tighter than PAD)

    // UI
    private var m_Panel:MovieClip;
    private var m_Body:MovieClip;
    private var chrome:MovieClip;
    private var dragMC:MovieClip;
    private var titleTF:TextField;
    private var collTF:TextField;
    private var coordTF:TextField;
    private var timeTF:TextField;
    private var btnStart:MovieClip;
    private var btnPause:MovieClip;
    private var collapseBtn:MovieClip;
    private var collapsed:Boolean;
    private var dragX:Number;
    private var dragY:Number;

    // Stopwatch state
    private var running:Boolean;
    private var paused:Boolean;
    private var startTime:Number;
    private var pausedAt:Number;
    private var pausedTotal:Number;
    private var lastText:String;

    public function KazBarsStopwatch(kb:Object, root:MovieClip) {
        rootClip = root;
        running = false;
        paused = false;
        startTime = 0;
        pausedAt = 0;
        pausedTotal = 0;
        collapsed = false;
        dragX = 0;
        dragY = 0;
        lastText = "0:00:00";
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) return;
        START_X = Number(cfg.x);
        START_Y = Number(cfg.y);
        START_COLLAPSED = (cfg.collapsed == true);
        FS = Number(cfg.fontSize);
        if (isNaN(FS) || FS < 8) FS = 12;
        PAD = Math.round(FS * 0.85);
        W = Math.round(FS * 15.8);
        H = Math.round(FS * 8);
        H_COLLAPSED = Math.round(FS * 2);
        TITLE_H = Math.round(FS * 1.85);
        COLL_PAD = Math.round(FS * 0.55);
        BTN = Math.round(FS * 1.1);
        NAME_FS = Math.round(FS * 1.15);
        TIME_FS = Math.round(FS * 2);
        LINE_H = Math.round(FS * 1.4);
        NAME_H = Math.round(NAME_FS * 1.4);
        TIME_H = Math.round(FS * 2.7);
        LEAD = Math.round(FS * 0.15);
        BTN_H = Math.round(FS * 1.85);
        BTN_GAP = Math.round(FS * 0.42);
        BTN_PAD = Math.round(FS * 0.5);
        // Derived, never fixed: three equal buttons plus their gaps must land
        // inside the plate at every FS, so the width falls out of the others.
        BTN_W = Math.floor((W - BTN_PAD * 2 - BTN_GAP * 2) / 3);
    }

    public function createPanel():Void {
        m_Panel = rootClip.createEmptyMovieClip("kbStopwatch", rootClip.getNextHighestDepth());
        m_Panel._x = START_X;
        m_Panel._y = START_Y;
        collapsed = START_COLLAPSED;

        chrome = m_Panel.createEmptyMovieClip("chrome", m_Panel.getNextHighestDepth());

        titleTF = makeTF(m_Panel, "title", PAD, 0, W - PAD * 2 - BTN, NAME_H,
                         NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "Stopwatch";

        // Separate collapsed label at the base font size, swapped on _visible —
        // the inspect/console convention, so the three collapsed bars match.
        collTF = makeTF(m_Panel, "coll", COLL_PAD, 0, W - COLL_PAD * 2 - BTN,
                        LINE_H, FS, true, 0xF7A22B, "left");

        // Live position readout — visible only while dragging (the value a
        // /loadclip user copies into the app to make a spot permanent). Shares
        // the title band, right-aligned, so the two never sit on each other.
        coordTF = makeTF(m_Panel, "coords", PAD, 0, W - PAD * 2 - BTN, LINE_H,
                         Math.max(9, Math.round(FS * 0.8)), false, 0x999999, "right");
        coordTF._visible = false;

        // Invisible drag handle over the title band (stops short of the
        // collapse button so it keeps its own press). Redrawn per fold state.
        dragMC = m_Panel.createEmptyMovieClip("drag", m_Panel.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };

        // Bare glyph, no box — the inspect panel's collapse control.
        collapseBtn = m_Panel.createEmptyMovieClip("btnCollapse", m_Panel.getNextHighestDepth());
        collapseBtn._x = W - PAD - BTN;
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        makeTF(collapseBtn, "label", 0, 0, BTN, BTN + 2,
               Math.max(9, Math.round(FS * 0.9)), true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };

        m_Body = m_Panel.createEmptyMovieClip("body", m_Panel.getNextHighestDepth());

        timeTF = makeTF(m_Body, "time", PAD, TITLE_H + Math.round(FS * 0.5),
                        W - PAD * 2, TIME_H, TIME_FS, true, 0xC8C0B0, "center");
        timeTF.text = lastText;

        var by:Number = H - PAD - BTN_H;
        btnStart = makeButton(m_Body, "btnStart", "Start", BTN_PAD, by);
        btnPause = makeButton(m_Body, "btnPause", "Pause", BTN_PAD + BTN_W + BTN_GAP, by);
        var btnReset:MovieClip = makeButton(m_Body, "btnReset", "Reset",
                                            BTN_PAD + (BTN_W + BTN_GAP) * 2, by);
        btnStart.onRelease = function() { this._self.startWatch(); };
        btnPause.onRelease = function() { this._self.pauseWatch(); };
        btnReset.onRelease = function() { this._self.resetWatch(); };

        applyCollapsed();
        setTimeColor();
        updateButtons();
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
        fmt.leading = LEAD;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // Flat square button: plate fill, 1px bronze border, orange label on hover
    // — the panel's own chrome at button scale. Drawn once; only the label
    // colour and the disabled alpha ever change.
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
        var tf:TextField = makeTF(c, "label", 0, Math.floor((BTN_H - LINE_H) / 2),
                                  BTN_W, LINE_H, Math.round(FS * 0.9), true, 0xC8C0B0, "center");
        tf.text = label;
        c.useHandCursor = true;
        c.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        c.onRollOut = function() { this.label.textColor = 0xC8C0B0; };
        return c;
    }

    // =========================================================================
    // Chrome (redrawn on collapse/expand at the matching height)
    // =========================================================================

    private function drawChrome(h:Number):Void {
        chrome.clear();
        chrome.beginFill(0x0C0A07, 90);
        rectPath(chrome, 0, 0, W, h);
        chrome.endFill();
        chrome.lineStyle(1, 0x000000, 100);
        rectPath(chrome, 0, 0, W, h);
        chrome.lineStyle(1, 0x4A3B22, 100);
        rectPath(chrome, 1, 1, W - 2, h - 2);
        // Title separator — the same hairline the inspect panel rules its
        // section headers with. Collapsed there is no body to divide.
        if (h > H_COLLAPSED) {
            chrome.lineStyle(1, 0x6B5324, 100);
            chrome.moveTo(PAD, TITLE_H);
            chrome.lineTo(W - PAD, TITLE_H);
        }
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    // =========================================================================
    // Stopwatch
    // =========================================================================

    public function startWatch():Void {
        if (running) return;
        if (paused) {
            pausedTotal += getTimer() - pausedAt;
            paused = false;
        } else {
            startTime = getTimer();
            pausedTotal = 0;
        }
        running = true;
        startDriver();
        refreshTime();
        setTimeColor();
        syncTitle();
        updateButtons();
    }

    public function pauseWatch():Void {
        if (!running) return;
        running = false;
        paused = true;
        pausedAt = getTimer();
        stopDriver();
        refreshTime();
        setTimeColor();
        syncTitle();
        updateButtons();
    }

    public function resetWatch():Void {
        running = false;
        paused = false;
        startTime = 0;
        pausedAt = 0;
        pausedTotal = 0;
        stopDriver();
        lastText = "0:00:00";
        timeTF.text = lastText;
        setTimeColor();
        syncTitle();
        updateButtons();
    }

    private function elapsedMs():Number {
        if (paused) return Math.max(0, pausedAt - startTime - pausedTotal);
        if (running) return Math.max(0, getTimer() - startTime - pausedTotal);
        return 0;
    }

    private function startDriver():Void {
        var self:KazBarsStopwatch = this;
        m_Panel.onEnterFrame = function() { self.refreshTime(); };
    }

    private function stopDriver():Void {
        if (m_Panel != null) m_Panel.onEnterFrame = null;
    }

    public function refreshTime():Void {
        var txt:String = formatTime(elapsedMs());
        if (txt == lastText) return;
        lastText = txt;
        timeTF.text = txt;
        if (collapsed) collTF.text = txt;
    }

    private function formatTime(ms:Number):String {
        var total:Number = Math.floor(ms / 1000);
        var hh:Number = Math.floor(total / 3600);
        var mm:Number = Math.floor((total % 3600) / 60);
        var ss:Number = total % 60;
        return hh + ":" + ((mm < 10) ? "0" + mm : String(mm)) + ":" + ((ss < 10) ? "0" + ss : String(ss));
    }

    // Running / paused / stopped mapped onto the panel's value, header and
    // label colours, so the state reads without adding a fourth hue.
    private function setTimeColor():Void {
        timeTF.textColor = running ? 0x7AC142 : (paused ? 0xF7A22B : 0xC8C0B0);
    }

    private function updateButtons():Void {
        btnStart._alpha = running ? 50 : 100;
        btnPause._alpha = running ? 100 : 50;
    }

    // =========================================================================
    // Collapse / drag
    // =========================================================================

    public function toggleCollapsed():Void {
        collapsed = !collapsed;
        applyCollapsed();
    }

    // One plate at two heights — folding keeps the title band and drops the
    // body, and the title swaps to the collapsed label. Everything sitting on
    // the band — label, readout, button and the drag strip — re-centres on
    // whichever height is on screen, at the state's own inset.
    private function applyCollapsed():Void {
        var band:Number = collapsed ? H_COLLAPSED : TITLE_H;
        var pad:Number = collapsed ? COLL_PAD : PAD;
        m_Body._visible = !collapsed;
        titleTF._visible = !collapsed;
        collTF._visible = collapsed;
        titleTF._y = Math.floor((TITLE_H - NAME_H) / 2);
        collTF._y = Math.floor((H_COLLAPSED - LINE_H) / 2);
        coordTF._x = pad;
        coordTF._y = Math.floor((band - LINE_H) / 2);
        coordTF._width = W - pad * 2 - BTN;
        collapseBtn._x = W - pad - BTN;
        collapseBtn._y = Math.floor((band - BTN) / 2);
        dragMC.clear();
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, W - pad - BTN, band);
        dragMC.endFill();
        drawChrome(collapsed ? H_COLLAPSED : H);
        collapseBtn.label.text = collapsed ? "+" : "-";
        syncTitle();
    }

    private function syncTitle():Void {
        collTF.text = (running || paused) ? lastText : "Stopwatch";
    }

    public function beginDrag(da:MovieClip):Void {
        var hh:Number = collapsed ? H_COLLAPSED : H;
        m_Panel.startDrag(false, 0, 0, Math.max(0, Stage.width - W),
                          Math.max(0, Stage.height - hh));
        dragX = m_Panel._x;
        dragY = m_Panel._y;
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsStopwatch = this;
        da.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(da:MovieClip):Void {
        m_Panel.stopDrag();
        delete da.onMouseMove;
        coordTF._visible = false;
        // Collapsed, the bar is small and labelled and reads as a button, so a
        // press that never moved it opens the panel; a real drag still just
        // moves it. Expanded, a stray click on the title must not fold it away.
        if (collapsed && Math.abs(m_Panel._x - dragX) < 2
                      && Math.abs(m_Panel._y - dragY) < 2) {
            toggleCollapsed();
        }
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(m_Panel._x) + ", " + Math.round(m_Panel._y);
    }

    // Preview-mode control panel only: a hard hide of the whole plate, restored
    // on the way out of preview. The timer keeps running underneath.
    public function setShown(shown:Boolean):Void {
        if (m_Panel != null) m_Panel._visible = shown;
    }

    // =========================================================================
    // Persistence (aoc.exe clients only — default /loadclip clients have no archive)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        // Fold state first: the position clamp needs the height actually on
        // screen, or a saved spot near the bottom snaps up on every relog.
        var c:Object = config.FindEntry("swc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
        var x:Object = config.FindEntry("swx");
        var y:Object = config.FindEntry("swy");
        if (x !== undefined && y !== undefined) {
            m_Panel._x = clampPos(Number(x), Stage.width - W);
            m_Panel._y = clampPos(Number(y), Stage.height - (collapsed ? H_COLLAPSED : H));
        }
    }

    public function saveState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        config.ReplaceEntry("swx", m_Panel._x);
        config.ReplaceEntry("swy", m_Panel._y);
        config.ReplaceEntry("swc", collapsed ? 1 : 0);
    }

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }

    public function cleanup():Void {
        stopDriver();
        running = false;
        paused = false;
        if (m_Panel != null) {
            m_Panel.removeMovieClip();
            m_Panel = null;
        }
    }
}
