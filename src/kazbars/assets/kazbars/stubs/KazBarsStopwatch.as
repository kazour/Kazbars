// KazBarsStopwatch.as - In-game count-up stopwatch panel (Start / Pause / Reset).
// Runtime-drawn chrome + dynamic text fields (Arial resolves against the faces
// embedded in base.swf), so it needs no new symbols. Clicks are ordinary
// Scaleform GUI input: fullscreen-safe, never steals game focus.
//
// Chrome, palette and geometry are the family's, inherited from KazBarsPanel
// (and docs/inspect-panel.md section 5): warm near-black plate, 1px
// black-over-bronze double frame, Conan-orange title, square corners, and
// every dimension a Math.round(FS * ratio) off the baked fontSize. The
// collapsed bar is FS*15.8 x FS*2 — the same bar the inspect panel folds to —
// so the two pair at any font size, not just at the default 12.
//
// Positioning mirrors the cast timer: the baked X/Y are the defaults a
// first-ever session starts from (the title bar shows live coordinates while
// dragging so users can copy them into the app); drag position + collapsed
// state persist for every user via the module config archive (swx/swy/swc,
// and the control-panel master switch swv).
//
// Driven from KazBars: createPanel() in onLoad, loadState()/saveState() from
// the module archive, cleanup() on deactivate.
class KazBarsStopwatch extends KazBarsPanel {

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;

    // Layout beyond the base set — all derived from FS in configure()
    private var W:Number;         // 15.8  the family's collapsed width
    private var H:Number;         // 8.0   expanded plate
    private var H_COLLAPSED:Number; // 2.0  its collapsed bar
    private var TIME_FS:Number;   // 2.0   time readout font
    private var NAME_H:Number;    // 1.4x NAME_FS
    private var TIME_H:Number;    // 2.7   time readout field
    private var BTN_GAP:Number;   // 0.42
    private var BTN_PAD:Number;   // 0.5   button row inset (tighter than PAD)
    // BTN_W is derived here, never the base's 5.0: three equal buttons plus
    // their gaps must land inside the plate at every FS.

    // UI
    private var m_Body:MovieClip;
    private var titleTF:TextField;
    private var collTF:TextField;
    private var timeTF:TextField;
    private var btnStart:MovieClip;
    private var btnPause:MovieClip;

    // Stopwatch state
    private var running:Boolean;
    private var paused:Boolean;
    private var startTime:Number;
    private var pausedAt:Number;
    private var pausedTotal:Number;
    private var lastText:String;
    private var active:Boolean;

    public function KazBarsStopwatch(owner:KazBars, root:MovieClip) {
        super(root);
        active = true;
        running = false;
        paused = false;
        startTime = 0;
        pausedAt = 0;
        pausedTotal = 0;
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
        var fs:Number = Number(cfg.fontSize);
        if (isNaN(fs) || fs < 8) fs = 12;
        applyBaseSize(fs);
        LEAD = Math.round(FS * 0.15);
        W = Math.round(FS * 15.8);
        H = Math.round(FS * 8);
        H_COLLAPSED = Math.round(FS * 2);
        TIME_FS = Math.round(FS * 2);
        NAME_H = Math.round(NAME_FS * 1.4);
        TIME_H = Math.round(FS * 2.7);
        BTN_GAP = Math.round(FS * 0.42);
        BTN_PAD = Math.round(FS * 0.5);
        // Derived, never fixed: three equal buttons plus their gaps must land
        // inside the plate at every FS, so the width falls out of the others.
        BTN_W = Math.floor((W - BTN_PAD * 2 - BTN_GAP * 2) / 3);
    }

    public function createPanel():Void {
        panelClip = rootClip.createEmptyMovieClip("kbStopwatch", rootClip.getNextHighestDepth());
        panelClip._x = START_X;
        panelClip._y = START_Y;
        collapsed = START_COLLAPSED;

        chrome = panelClip.createEmptyMovieClip("chrome", panelClip.getNextHighestDepth());

        titleTF = makeTF(panelClip, "title", PAD, 0, W - PAD * 2 - BTN, NAME_H,
                         NAME_FS, true, 0xF7A22B, "left");
        titleTF.text = "Stopwatch";

        // Separate collapsed label at the base font size, swapped on _visible —
        // the inspect/console convention, so the three collapsed bars match.
        collTF = makeTF(panelClip, "coll", COLL_PAD, 0, W - COLL_PAD * 2 - BTN,
                        LINE, FS, true, 0xF7A22B, "left");

        // Live position readout — visible only while dragging (a copyable
        // value for pinning a default spot in the app). Shares
        // the title band, right-aligned, so the two never sit on each other.
        coordTF = makeTF(panelClip, "coords", PAD, 0, W - PAD * 2 - BTN, LINE,
                         Math.max(9, Math.round(FS * 0.8)), false, 0x999999, "right");
        coordTF._visible = false;

        // Invisible drag handle over the title band (stops short of the
        // collapse button so it keeps its own press). Redrawn per fold state.
        makeDragStrip("drag");

        makeCollapseBtn();
        collapseBtn._x = W - PAD - BTN;

        m_Body = panelClip.createEmptyMovieClip("body", panelClip.getNextHighestDepth());

        timeTF = makeTF(m_Body, "time", PAD, TITLE_H + Math.round(FS * 0.5),
                        W - PAD * 2, TIME_H, TIME_FS, true, 0xC8C0B0, "center");
        timeTF.text = lastText;

        var by:Number = H - PAD - BTN_H;
        btnStart = makeButton(m_Body, "btnStart", "Start", BTN_PAD, by,
                              Math.round(FS * 0.9));
        btnPause = makeButton(m_Body, "btnPause", "Pause", BTN_PAD + BTN_W + BTN_GAP,
                              by, Math.round(FS * 0.9));
        var btnReset:MovieClip = makeButton(m_Body, "btnReset", "Reset",
                                            BTN_PAD + (BTN_W + BTN_GAP) * 2, by,
                                            Math.round(FS * 0.9));
        btnStart.onRelease = function() { this._self.startWatch(); };
        btnPause.onRelease = function() { this._self.pauseWatch(); };
        btnReset.onRelease = function() { this._self.resetWatch(); };

        applyCollapsed();
        setTimeColor();
        updateButtons();
        // A re-run of onLoad rebuilds the plate in whatever state the master
        // switch is in, not blindly visible.
        panelClip._visible = active;
    }

    // =========================================================================
    // Chrome (redrawn on collapse/expand at the matching height)
    // =========================================================================

    private function drawChrome(h:Number):Void {
        drawPlate(W, h);
        // Title separator — the same hairline the inspect panel rules its
        // section headers with. Collapsed there is no body to divide.
        if (h > H_COLLAPSED) {
            chrome.lineStyle(1, 0x6B5324, 100);
            chrome.moveTo(PAD, TITLE_H);
            chrome.lineTo(W - PAD, TITLE_H);
        }
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
        panelClip.onEnterFrame = function() { self.refreshTime(); };
    }

    private function stopDriver():Void {
        if (panelClip != null) panelClip.onEnterFrame = null;
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
    // Collapse
    // =========================================================================

    // One plate at two heights — folding keeps the title band and drops the
    // body, and the title swaps to the collapsed label. Everything sitting on
    // the band — label, readout, button and the drag strip — re-centres on
    // whichever height is on screen, at the state's own inset. curW/curH feed
    // the base drag clamp.
    private function applyCollapsed():Void {
        var band:Number = collapsed ? H_COLLAPSED : TITLE_H;
        var pad:Number = collapsed ? COLL_PAD : PAD;
        curW = W;
        curH = collapsed ? H_COLLAPSED : H;
        m_Body._visible = !collapsed;
        titleTF._visible = !collapsed;
        collTF._visible = collapsed;
        titleTF._y = Math.floor((TITLE_H - NAME_H) / 2);
        collTF._y = Math.floor((H_COLLAPSED - LINE) / 2);
        coordTF._x = pad;
        coordTF._y = Math.floor((band - LINE) / 2);
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

    // Master switch (preview control panel + archive): hidden is inactive, but
    // the timer keeps running underneath — re-activating shows the live count.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(shown:Boolean):Void {
        active = shown;
        if (panelClip != null) panelClip._visible = shown;
    }

    // =========================================================================
    // Persistence (module config archive — permanent for every user)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || panelClip == null) return;
        // Fold state first: the position clamp needs the height actually on
        // screen, or a saved spot near the bottom snaps up on every relog.
        var c:Object = config.FindEntry("swc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
        var v:Object = config.FindEntry("swv");
        if (v !== undefined) setActive(v == 1);
        var x:Object = config.FindEntry("swx");
        var y:Object = config.FindEntry("swy");
        if (x !== undefined && y !== undefined) {
            panelClip._x = clampPos(Number(x), Stage.width - W);
            panelClip._y = clampPos(Number(y), Stage.height - (collapsed ? H_COLLAPSED : H));
        }
    }

    public function saveState(config:Object):Void {
        if (config == null || panelClip == null) return;
        config.ReplaceEntry("swx", panelClip._x);
        config.ReplaceEntry("swy", panelClip._y);
        config.ReplaceEntry("swc", collapsed ? 1 : 0);
        config.ReplaceEntry("swv", active ? 1 : 0);
    }

    public function cleanup():Void {
        stopDriver();
        running = false;
        paused = false;
        if (panelClip != null) {
            panelClip.removeMovieClip();
            panelClip = null;
        }
    }
}
