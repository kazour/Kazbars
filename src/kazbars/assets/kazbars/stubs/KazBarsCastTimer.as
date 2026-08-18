// KazBarsCastTimer.as - Timer-only cast overlay (no bar) for player + target.
// Lifts the cast-tracking + EMA estimate logic from the old KzCastbars module,
// dropping the bar/mask/color visuals. Pure dynamic text fields (device fonts),
// so it needs no new symbols in base.swf.
//
// Positioning mirrors grids: PLAYER_X/Y + TARGET_X/Y baked into config are the
// defaults a first-ever session starts from; preview drag persists via the
// config archive (permanent since the persistence era), as does the preview
// control panel's master switch (ctv) — inactive renders nothing, live
// casts included.
//
// Driven from KazBars: create() in onLoad, connectPlayer()/setTarget()
// from the existing player/target lifecycle, previewOn()/previewOff() from the
// shared Shift+Ctrl+Alt preview, loadState()/saveState() from the module archive.
class KazBarsCastTimer implements KazBarsModule {
    private var rootClip:MovieClip;

    // Config (set by configure())
    private var ENABLE_P:Boolean;
    private var ENABLE_T:Boolean;
    private var PLAYER_X:Number;
    private var PLAYER_Y:Number;
    private var TARGET_X:Number;
    private var TARGET_Y:Number;
    private var BOLD:Boolean;
    private var SIZE:Number;
    private var DISPLAY:String;   // "elapsed" | "total" | "both"
    private var COLOR:Number;

    // Display clips
    private var m_PlayerClip:MovieClip;
    private var m_TargetClip:MovieClip;

    // Tracked characters (mirrors KazBars m_Player/m_Target so we can read progress)
    private var playerChar:Object;
    private var targetChar:Object;

    // Cast state
    private var playerData:Object;
    private var targetData:Object;
    private var driverClip:MovieClip;
    private var previewMode:Boolean;
    private var active:Boolean;

    // The shared preview skin. Stateless — it reads the clip out of each spec —
    // so one instance dresses both timers.
    private var preview:KazBarsPreview;

    public function KazBarsCastTimer(root:MovieClip) {
        rootClip = root;
        preview = new KazBarsPreview(root);
        previewMode = false;
        active = true;
        playerData = newCastData();
        targetData = newCastData();
    }

    private function newCastData():Object {
        return {casting:false, startTime:0, initialProgress:0, smoothedEstimate:0,
                lastEstimateTime:0, lockCount:0, estimateLocked:false, midCast:false};
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) return;
        ENABLE_P = (cfg.enableP == true);
        ENABLE_T = (cfg.enableT == true);
        PLAYER_X = Number(cfg.playerX);
        PLAYER_Y = Number(cfg.playerY);
        TARGET_X = Number(cfg.targetX);
        TARGET_Y = Number(cfg.targetY);
        BOLD = (cfg.bold == true);
        SIZE = Number(cfg.fontSize);
        DISPLAY = cfg.display;
        COLOR = Number(cfg.color);
    }

    public function create():Void {
        if (ENABLE_P) m_PlayerClip = makeClip("kbCastP", PLAYER_X, PLAYER_Y);
        if (ENABLE_T) m_TargetClip = makeClip("kbCastT", TARGET_X, TARGET_Y);
        // Frame-coherent update driver. Its own onEnterFrame reads getTimer() and
        // GetCommandProgress() on the same engine tick, so the EMA estimate can't
        // see a fresh clock against a stale progress -- the desync a free-running
        // setInterval produced, which spiked the estimate during lag/interrupts.
        driverClip = rootClip.createEmptyMovieClip("kbCastDrv", rootClip.getNextHighestDepth());
    }

    private function makeClip(name:String, px:Number, py:Number):MovieClip {
        var c:MovieClip = rootClip.createEmptyMovieClip(name, rootClip.getNextHighestDepth());
        c._x = px;
        c._y = py;
        c._visible = false;
        var W:Number = 200;  // wide box, centered on origin so text grows symmetrically
        var h:Number = SIZE + 8;
        makeTF(c, "tmrShadow", -W / 2 + 1, 1, W, h, 0x000000);
        makeTF(c, "tmr", -W / 2, 0, W, h, COLOR);
        return c;
    }

    private function makeTF(c:MovieClip, id:String, x:Number, y:Number, w:Number, h:Number, col:Number):Void {
        var tf:TextField = c.createTextField(id, c.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.textColor = col;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = SIZE;
        fmt.bold = BOLD;
        fmt.align = "center";
        tf.setNewTextFormat(fmt);
    }

    // =========================================================================
    // Signal wiring (called from KazBars player/target lifecycle)
    // =========================================================================

    public function connectPlayer(ch:Object):Void {
        disconnectPlayer();
        playerChar = ch;
        resetSide(playerData, m_PlayerClip);
        if (ch == null || !ENABLE_P) return;
        try {
            ch.SignalCommandStarted.Connect(slotPCastStart, this);
            ch.SignalCommandEnded.Connect(slotPCastEnd, this);
            ch.SignalCommandAborted.Connect(slotPCastEnd, this);
            if (ch.ConnectToCommandQueue) ch.ConnectToCommandQueue();
        } catch (e:Object) {}
    }

    public function disconnectPlayer():Void {
        if (playerChar != null && ENABLE_P) {
            try {
                playerChar.SignalCommandStarted.Disconnect(slotPCastStart, this);
                playerChar.SignalCommandEnded.Disconnect(slotPCastEnd, this);
                playerChar.SignalCommandAborted.Disconnect(slotPCastEnd, this);
            } catch (e:Object) {}
        }
        playerChar = null;
    }

    public function setTarget(ch:Object):Void {
        if (targetChar != null && ENABLE_T) {
            try {
                targetChar.SignalCommandStarted.Disconnect(slotTCastStart, this);
                targetChar.SignalCommandEnded.Disconnect(slotTCastEnd, this);
                targetChar.SignalCommandAborted.Disconnect(slotTCastEnd, this);
            } catch (e:Object) {}
        }
        targetChar = ch;
        resetSide(targetData, m_TargetClip);
        if (ch == null || !ENABLE_T) return;
        try {
            ch.SignalCommandStarted.Connect(slotTCastStart, this);
            ch.SignalCommandEnded.Connect(slotTCastEnd, this);
            ch.SignalCommandAborted.Connect(slotTCastEnd, this);
            if (ch.ConnectToCommandQueue) ch.ConnectToCommandQueue();
        } catch (e:Object) {}
        // Mid-cast: timer should appear even if we target someone already casting.
        var self:KazBarsCastTimer = this;
        setTimeout(function() { self.checkTargetMidCast(); }, 120);
    }

    private function checkTargetMidCast():Void {
        if (targetChar == null || targetData.casting) return;
        var p:Number;
        try { p = targetChar.GetCommandProgress(); } catch (e:Object) { return; }
        if (p > 0 && p < 1) startCast(targetData, m_TargetClip, false, true);
    }

    private function resetSide(data:Object, clip:MovieClip):Void {
        data.casting = false;
        if (clip != null && !previewMode) { clip._visible = false; setText(clip, ""); }
    }

    private function slotPCastStart(spellName:String):Void { startCast(playerData, m_PlayerClip, true, false); }
    private function slotPCastEnd():Void { endCast(playerData, m_PlayerClip); }
    private function slotTCastStart(spellName:String):Void { startCast(targetData, m_TargetClip, false, false); }
    private function slotTCastEnd():Void { endCast(targetData, m_TargetClip); }

    // =========================================================================
    // Cast tracking
    // =========================================================================

    private function startCast(data:Object, clip:MovieClip, isPlayer:Boolean, midCast:Boolean):Void {
        if (clip == null) return;
        data.casting = true;
        data.startTime = getTimer();
        data.initialProgress = 0;
        data.smoothedEstimate = 0;
        data.lastEstimateTime = 0;
        data.lockCount = 0;
        data.estimateLocked = false;
        data.midCast = midCast;
        var ch:Object = isPlayer ? playerChar : targetChar;
        if (ch != null) {
            try { data.initialProgress = clamp01(ch.GetCommandProgress()); } catch (e:Object) {}
        }
        clip._visible = active;
        setText(clip, "");
        startDriver();
        update();
    }

    private function endCast(data:Object, clip:MovieClip):Void {
        data.casting = false;
        if (clip != null) {
            if (previewMode) setText(clip, placeholder());
            else { clip._visible = false; setText(clip, ""); }
        }
        if (!playerData.casting && !targetData.casting) stopDriver();
    }

    private function startDriver():Void {
        if (driverClip == null) return;
        var self:KazBarsCastTimer = this;
        driverClip.onEnterFrame = function() { self.update(); };
    }

    private function stopDriver():Void {
        if (driverClip != null) driverClip.onEnterFrame = null;
    }

    private function update():Void {
        if (!playerData.casting && !targetData.casting) { stopDriver(); return; }
        var now:Number = getTimer();
        if (playerData.casting && playerChar != null && m_PlayerClip != null) {
            setText(m_PlayerClip, render(playerData, clamp01(safeProgress(playerChar)), now));
        }
        if (targetData.casting && targetChar != null && m_TargetClip != null) {
            setText(m_TargetClip, render(targetData, clamp01(safeProgress(targetChar)), now));
        }
    }

    private function safeProgress(ch:Object):Number {
        var p:Number;
        try { p = ch.GetCommandProgress(); } catch (e:Object) { return 0; }
        return p;
    }

    // Returns the timer text for the active display mode, refreshing the EMA estimate.
    private function render(data:Object, progress:Number, now:Number):String {
        var elapsedMs:Number = Math.max(0, now - data.startTime);
        refreshEstimate(data, progress, elapsedMs, now);

        var est:Number = data.smoothedEstimate;
        var elapsedSec:Number;
        if (data.midCast && est > 0) {
            elapsedSec = progress * est;
        } else {
            elapsedSec = elapsedMs / 1000;
            // Elapsed is wall-clock truth; clipping it down to a low estimate is
            // what stalled a real 2.0s cast at "1.9". Let it reach the true time
            // and pull the shown total up to match (keeps "both" consistent). The
            // +1s tolerance still bounds a stuck cast whose end signal was missed.
            if (est > 0) {
                if (elapsedSec > est + 1) elapsedSec = est + 1;
                if (elapsedSec > est) est = Math.round(elapsedSec * 10) / 10;
            }
        }

        if (DISPLAY == "total") return (est > 0) ? formatTime(est) : "";
        var e:String = formatTime(Math.round(elapsedSec * 10) / 10);
        if (DISPLAY == "elapsed") return e;
        // "both"
        return (est > 0) ? (e + " / " + formatTime(est)) : e;
    }

    // EMA-smoothed estimate with convergence lock (ported from KzCastbars).
    private function refreshEstimate(data:Object, progress:Number, elapsedMs:Number, now:Number):Void {
        if (data.estimateLocked || (now - data.lastEstimateTime) <= 80) return;
        data.lastEstimateTime = now;
        var pd:Number = progress - data.initialProgress;
        if (elapsedMs > 50 && pd > 0.005 && progress < 0.85) {
            var raw:Number = Math.round(10 * elapsedMs / pd / 1000) / 10;
            if (data.smoothedEstimate == 0) data.smoothedEstimate = raw;
            else data.smoothedEstimate = Math.round((data.smoothedEstimate * 0.7 + raw * 0.3) * 10) / 10;
            var diff:Number = raw - data.smoothedEstimate;
            if (diff < 0) diff = -diff;
            if (diff <= 0.15) data.lockCount = data.lockCount + 1;
            else data.lockCount = 0;
            if (data.lockCount >= 3) data.estimateLocked = true;
        }
    }

    private function formatTime(seconds:Number):String {
        var s:String = String(seconds);
        if (s.indexOf(".") == -1) s = s + ".0";
        return s;
    }

    private function setText(clip:MovieClip, txt:String):Void {
        if (clip == null) return;
        if (clip.tmr != null) clip.tmr.text = txt;
        if (clip.tmrShadow != null) clip.tmrShadow.text = txt;
    }

    private function placeholder():String {
        if (DISPLAY == "total") return "2.5";
        if (DISPLAY == "elapsed") return "1.2";
        return "1.2 / 2.5";
    }

    // =========================================================================
    // Preview drag (the shared HUD overlay, same skin the grids wear)
    // =========================================================================

    public function previewOn():Void {
        previewMode = true;
        if (!active) return;
        dressForDrag(m_PlayerClip, 0x0066FF, "Player Cast");
        dressForDrag(m_TargetClip, 0xFF0066, "Target Cast");
    }

    public function previewOff():Void {
        previewMode = false;
        // An inactive timer must not survive preview exit on the strength of a
        // live cast — the master switch outranks the cast state.
        hidePreview(m_PlayerClip, playerData.casting && active);
        hidePreview(m_TargetClip, targetData.casting && active);
    }

    // The control panel's row for this module: the key routes the check back
    // through KazBars.previewToggle into setActive below.
    public function previewKey():String { return "cast"; }
    public function previewLabel():String { return "Cast timer"; }

    // Master switch (preview control panel + archive). Hiding is a hard hide of
    // both clips (the drag overlay is a child, so it follows); re-activating
    // mid-preview rebuilds the placeholders, mid-cast re-shows the live timer.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(shown:Boolean):Void {
        active = shown;
        if (shown) {
            if (previewMode) { previewOn(); return; }
            if (playerData.casting && m_PlayerClip != null) m_PlayerClip._visible = true;
            if (targetData.casting && m_TargetClip != null) m_TargetClip._visible = true;
        } else {
            if (m_PlayerClip != null) m_PlayerClip._visible = false;
            if (m_TargetClip != null) m_TargetClip._visible = false;
        }
    }

    // The footprint is the timer's own: the text is anchored on its centre, the
    // title sits above it and the coordinate row below, so the box runs from 32
    // above the anchor to 28 below the text.
    private function dressForDrag(clip:MovieClip, col:Number, title:String):Void {
        if (clip == null) return;
        clip._visible = true;
        setText(clip, placeholder());
        preview.attach({mc: clip, x: -48, y: -32, w: 96, h: SIZE + 60,
                        label: title, color: col});
    }

    private function hidePreview(clip:MovieClip, stillCasting:Boolean):Void {
        if (clip == null) return;
        preview.detach(clip);
        if (!stillCasting) { clip._visible = false; setText(clip, ""); }
    }

    // =========================================================================
    // Persistence (module config archive — permanent for every user)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null) return;
        applyPos(m_PlayerClip, config.FindEntry("ctpx"), config.FindEntry("ctpy"));
        applyPos(m_TargetClip, config.FindEntry("cttx"), config.FindEntry("ctty"));
        var v:Object = config.FindEntry("ctv");
        if (v !== undefined) setActive(v == 1);
    }

    private function applyPos(clip:MovieClip, x:Object, y:Object):Void {
        if (clip == null) return;
        if (x !== undefined && y !== undefined) { clip._x = Number(x); clip._y = Number(y); }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        if (m_PlayerClip != null) { config.ReplaceEntry("ctpx", m_PlayerClip._x); config.ReplaceEntry("ctpy", m_PlayerClip._y); }
        if (m_TargetClip != null) { config.ReplaceEntry("cttx", m_TargetClip._x); config.ReplaceEntry("ctty", m_TargetClip._y); }
        config.ReplaceEntry("ctv", active ? 1 : 0);
    }

    public function cleanup():Void {
        stopDriver();
        disconnectPlayer();
        setTarget(null);
        previewMode = false;
        if (m_PlayerClip != null) { m_PlayerClip.removeMovieClip(); m_PlayerClip = null; }
        if (m_TargetClip != null) { m_TargetClip.removeMovieClip(); m_TargetClip = null; }
        if (driverClip != null) { driverClip.removeMovieClip(); driverClip = null; }
    }

    private function clamp01(v:Number):Number {
        if (isNaN(v)) return 0;
        if (v < 0) return 0;
        if (v > 1) return 1;
        return v;
    }
}
