// KazBarsStopwatch.as - In-game count-up stopwatch panel (Start / Pause / Reset).
// Runtime-drawn chrome + dynamic text fields (Arial resolves against the faces
// embedded in base.swf), so it needs no new symbols. Clicks are ordinary
// Scaleform GUI input: fullscreen-safe, never steals game focus.
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

    // Layout (AS2 has no const)
    private var W:Number;
    private var H:Number;
    private var H_COLLAPSED:Number;
    private var TITLE_H:Number;

    // UI
    private var m_Panel:MovieClip;
    private var m_Body:MovieClip;
    private var chrome:MovieClip;
    private var titleTF:TextField;
    private var coordTF:TextField;
    private var timeTF:TextField;
    private var btnStart:MovieClip;
    private var btnPause:MovieClip;
    private var collapseBtn:MovieClip;
    private var collapsed:Boolean;

    // Stopwatch state
    private var running:Boolean;
    private var paused:Boolean;
    private var startTime:Number;
    private var pausedAt:Number;
    private var pausedTotal:Number;
    private var lastText:String;

    public function KazBarsStopwatch(kb:Object, root:MovieClip) {
        rootClip = root;
        W = 190;
        H = 96;
        H_COLLAPSED = 24;
        TITLE_H = 22;
        running = false;
        paused = false;
        startTime = 0;
        pausedAt = 0;
        pausedTotal = 0;
        collapsed = false;
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
    }

    public function createPanel():Void {
        m_Panel = rootClip.createEmptyMovieClip("kbStopwatch", rootClip.getNextHighestDepth());
        m_Panel._x = START_X;
        m_Panel._y = START_Y;
        collapsed = START_COLLAPSED;

        chrome = m_Panel.createEmptyMovieClip("chrome", m_Panel.getNextHighestDepth());

        titleTF = makeTF(m_Panel, "title", 8, 4, 100, 16, 12, "left");
        titleTF.text = "Stopwatch";

        // Live position readout — visible only while dragging (the value a
        // /loadclip user copies into the app to make a spot permanent).
        coordTF = makeTF(m_Panel, "coords", W - 112, 6, 86, 14, 10, "right");
        coordTF.textColor = 0x999999;
        coordTF._visible = false;

        // Invisible drag handle over the title bar (stops short of the collapse button).
        var da:MovieClip = m_Panel.createEmptyMovieClip("drag", m_Panel.getNextHighestDepth());
        da.beginFill(0, 0);
        rectPath(da, 2, 2, W - 26, TITLE_H - 2);
        da.endFill();
        da._self = this;
        da.useHandCursor = true;
        da.onPress = function() { this._self.beginDrag(this); };
        da.onRelease = da.onReleaseOutside = function() { this._self.endDrag(this); };

        collapseBtn = makeButton(m_Panel, "btnCollapse", "-", W - 21, 3, 16, 16, 4);
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };

        m_Body = m_Panel.createEmptyMovieClip("body", m_Panel.getNextHighestDepth());

        timeTF = makeTF(m_Body, "time", 8, TITLE_H + 6, W - 16, 32, 24, "center");
        timeTF.text = lastText;

        var bw:Number = 56;
        var bh:Number = 22;
        var by:Number = 64;
        btnStart = makeButton(m_Body, "btnStart", "Start", 6, by, bw, bh, 6);
        btnPause = makeButton(m_Body, "btnPause", "Pause", 6 + bw + 5, by, bw, bh, 6);
        var btnReset:MovieClip = makeButton(m_Body, "btnReset", "Reset", 6 + (bw + 5) * 2, by, bw, bh, 6);
        btnStart.onRelease = function() { this._self.startWatch(); };
        btnPause.onRelease = function() { this._self.pauseWatch(); };
        btnReset.onRelease = function() { this._self.resetWatch(); };

        applyCollapsed();
        setTimeColor();
        updateButtons();
    }

    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number, h:Number, size:Number, align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = true;
        fmt.align = align;
        fmt.color = 0xCCCCCC;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    private function makeButton(parent:MovieClip, name:String, label:String, x:Number, y:Number, w:Number, h:Number, r:Number):MovieClip {
        var c:MovieClip = parent.createEmptyMovieClip(name, parent.getNextHighestDepth());
        c._x = x;
        c._y = y;
        c._w = w;
        c._h = h;
        c._r = r;
        c._self = this;
        var bd:MovieClip = c.createEmptyMovieClip("bd", c.getNextHighestDepth());
        bd.lineStyle(1, 0x4A4A40, 100);
        roundRectPath(bd, 0, 0, w, h, r);
        c.createEmptyMovieClip("bg", c.getNextHighestDepth());
        var tf:TextField = makeTF(c, "label", 0, 0, w, h, 11, "center");
        tf.text = label;
        tf._y = (h - tf.textHeight) / 2 - 2;
        c.useHandCursor = true;
        paintButton(c, false);
        c.onRollOver = function() { this._self.paintButton(this, true); };
        c.onRollOut = function() { this._self.paintButton(this, false); };
        return c;
    }

    public function paintButton(c:MovieClip, hover:Boolean):Void {
        c.bg.clear();
        c.bg.beginFill(hover ? 0x2A2A24 : 0x1A1A18, 90);
        roundRectPath(c.bg, 1, 1, c._w - 2, c._h - 2, c._r - 1);
        c.bg.endFill();
        c.label.textColor = hover ? 0xFFFFFF : 0xCCCCCC;
    }

    // =========================================================================
    // Chrome (redrawn on collapse/expand at the matching height)
    // =========================================================================

    private function drawChrome(h:Number):Void {
        chrome.clear();
        chrome.beginFill(0x0D0D0D, 85);
        rectPath(chrome, 0, 0, W, h);
        chrome.endFill();
        chrome.beginFill(0x1A1A18, 85);
        rectPath(chrome, 2, 2, W - 4, TITLE_H - 2);
        chrome.endFill();
        if (h > H_COLLAPSED) {
            chrome.lineStyle(1, 0x444440, 60);
            chrome.moveTo(2, TITLE_H);
            chrome.lineTo(W - 2, TITLE_H);
        }
        chrome.lineStyle(2, 0x3A3A30, 100);
        rectPath(chrome, 0, 0, W, h);
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    private function roundRectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number, r:Number):Void {
        mc.moveTo(x + r, y);
        mc.lineTo(x + w - r, y);
        mc.curveTo(x + w, y, x + w, y + r);
        mc.lineTo(x + w, y + h - r);
        mc.curveTo(x + w, y + h, x + w - r, y + h);
        mc.lineTo(x + r, y + h);
        mc.curveTo(x, y + h, x, y + h - r);
        mc.lineTo(x, y + r);
        mc.curveTo(x, y, x + r, y);
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
        if (collapsed) titleTF.text = txt;
    }

    private function formatTime(ms:Number):String {
        var total:Number = Math.floor(ms / 1000);
        var hh:Number = Math.floor(total / 3600);
        var mm:Number = Math.floor((total % 3600) / 60);
        var ss:Number = total % 60;
        return hh + ":" + ((mm < 10) ? "0" + mm : String(mm)) + ":" + ((ss < 10) ? "0" + ss : String(ss));
    }

    private function setTimeColor():Void {
        timeTF.textColor = running ? 0xFFFFFF : (paused ? 0xFFCC66 : 0xCCCCCC);
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

    private function applyCollapsed():Void {
        m_Body._visible = !collapsed;
        drawChrome(collapsed ? H_COLLAPSED : H);
        collapseBtn.label.text = collapsed ? "+" : "-";
        syncTitle();
    }

    private function syncTitle():Void {
        titleTF.text = (collapsed && (running || paused)) ? lastText : "Stopwatch";
    }

    public function beginDrag(da:MovieClip):Void {
        var hh:Number = collapsed ? H_COLLAPSED : H;
        m_Panel.startDrag(false, 0, 0, Stage.width - W, Stage.height - hh);
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsStopwatch = this;
        da.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(da:MovieClip):Void {
        m_Panel.stopDrag();
        delete da.onMouseMove;
        coordTF._visible = false;
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(m_Panel._x) + ", " + Math.round(m_Panel._y);
    }

    // =========================================================================
    // Persistence (aoc.exe clients only — default /loadclip clients have no archive)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        var x:Object = config.FindEntry("swx");
        var y:Object = config.FindEntry("swy");
        if (x !== undefined && y !== undefined) {
            m_Panel._x = clampPos(Number(x), Stage.width - W);
            m_Panel._y = clampPos(Number(y), Stage.height - H_COLLAPSED);
        }
        var c:Object = config.FindEntry("swc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
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
