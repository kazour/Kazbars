// KazBarsCastTimer.as - The Casting Timer: a text timer (no bar) for your casts and your target's. A HUD module on the
// shared runtime: World names the player and the target, each side (KazBarsCastSide) follows one Character's cast
// signals and measures the cast and its estimate, and one clock task runs every frame while a cast is under way, so
// idle costs nothing. Device-font text fields, so it needs no symbols in base.swf.
//
// Display: "elapsed" (the time since the start), "total" (the estimate) or "both" ("1.2 / 2.5"); a total shows once
// the side has one, and follows the elapsed time when the end comes late. A side's text is written only when it
// changes. After a retarget, a cast already under way is looked for 120 ms later (a one-shot clock task, the side's
// probe).
//
// A HUD element: mouse-transparent, dragged only in preview through the shared overlay (KazBarsPreview). PLAYER_X/Y
// and TARGET_X/Y baked into config are the first session's; the archive keeps ctpx, ctpy, cttx, ctty and the master
// switch ctv (off: nothing shows, live casts included). Every engine call sits in a try.
class KazBarsCastTimer implements KazBarsModule {
    private var rootClip:MovieClip;
    private var w:KazBarsWorld;
    private var kF:Object;        // the clock task: every frame while a side casts
    private var kP:Object;        // the retarget's check: once, 120 ms after it
    private var pS:KazBarsCastSide;
    private var tS:KazBarsCastSide;

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
    private var TW:Number;        // the text box: wide enough for the longest
    private var TH:Number;        // display string at SIZE, one line box tall

    private var previewMode:Boolean;
    private var active:Boolean;

    public function KazBarsCastTimer(root:MovieClip) {
        rootClip = root;
        previewMode = false;
        active = true;
        pS = new KazBarsCastSide(this, "P");
        tS = new KazBarsCastSide(this, "T");
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object, world:KazBarsWorld, clock:KazBarsClock):Void {
        w = world;
        kF = clock.add(tick, this, 1, false, 0);
        kP = clock.add(probe, this, 120, true, 120);
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
        // The widest string the display can show is "both" with a three-digit
        // seconds on each side ("888.8 / 888.8": eight digits at 0.5566 em, two
        // points and the " / " at 0.2783 em each, 5.85 em in all; the same
        // advances in bold and regular). The box is that plus Flash's 2 px
        // gutter a side, made even so it centres on the clip's origin on whole
        // pixels, and one line box tall (the grids' rule, ceil(1.2 x size) + 4).
        TW = Math.ceil((Math.ceil(SIZE * 5.85) + 4) / 2) * 2;
        TH = Math.ceil(SIZE * 6 / 5) + 4;
        if (ENABLE_P) world.onPlayer(onPlayer, this);
        if (ENABLE_T) world.onTarget(onTarget, this);
    }

    // The host runs onLoad again on this instance after a deactivation: the old clips go first.
    public function create():Void {
        dropClips();
        if (ENABLE_P) pS.mc = makeClip("kbCastP", PLAYER_X, PLAYER_Y);
        if (ENABLE_T) tS.mc = makeClip("kbCastT", TARGET_X, TARGET_Y);
    }

    private function makeClip(name:String, px:Number, py:Number):MovieClip {
        var c:MovieClip = rootClip.createEmptyMovieClip(name, rootClip.getNextHighestDepth());
        c._x = px;
        c._y = py;
        c._visible = false;
        // Centered on the origin so text grows symmetrically.
        makeTF(c, "tmrShadow", -TW / 2 + 1, 1, TW, TH, 0x000000);
        makeTF(c, "tmr", -TW / 2, 0, TW, TH, COLOR);
        return c;
    }

    private function makeTF(c:MovieClip, id:String, x:Number, y:Number, wd:Number, ht:Number, col:Number):Void {
        var tf:TextField = c.createTextField(id, c.getNextHighestDepth(), x, y, wd, ht);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.textColor = col;
        var fmt:TextFormat = new TextFormat();
        fmt.font = KazBarsPreview.FACE;
        fmt.size = SIZE;
        fmt.bold = BOLD;
        fmt.align = "center";
        tf.setNewTextFormat(fmt);
    }

    private function dropClips():Void {
        if (pS.mc != null) pS.mc.removeMovieClip();
        if (tS.mc != null) tS.mc.removeMovieClip();
        pS.mc = null;
        tS.mc = null;
        pS.txt = "";
        tS.txt = "";
    }

    // =========================================================================
    // World's player and target
    // =========================================================================

    public function onPlayer(ch:Object, id:Number):Void {
        pS.wire(ch);
    }

    public function onTarget(t:Object):Void {
        if (t == tS.ch) return;
        tS.wire(t);
        w.clock.off(kP);
        if (t != null) w.clock.go(kP);
    }

    // Once per retarget, the delay restarted by each.
    public function probe():Void {
        w.clock.off(kP);
        tS.probe();
    }

    // =========================================================================
    // The frame task, and the sides' starts and ends
    // =========================================================================

    public function began(s:KazBarsCastSide):Void {
        w.clock.go(kF);
    }

    public function ended(s:KazBarsCastSide):Void {
        draw(s);
    }

    public function tick():Void {
        var now:Number = w.clock.now;
        pS.tick(now);
        tS.tick(now);
        draw(pS);
        draw(tS);
        if (!pS.busy && !tS.busy) w.clock.off(kF);
    }

    // A side's text and visibility: its cast's, else preview's placeholder, else hidden.
    private function draw(s:KazBarsCastSide):Void {
        var mc:MovieClip = s.mc;
        if (mc == null) return;
        var t:String = (s.busy && (s.el > 0 || s.tot > 0)) ? text(s.el, s.tot) : "";
        if (t == "" && previewMode) t = placeholder();
        if (t != s.txt) {
            s.txt = t;
            mc.tmr.text = t;
            mc.tmrShadow.text = t;
        }
        var v:Boolean = active && t != "";
        if (mc._visible != v) mc._visible = v;
    }

    private function text(el:Number, tot:Number):String {
        if (tot > 0 && el > tot) tot = el;
        if (DISPLAY == "total") return (tot > 0) ? sec(tot) : "";
        var e:String = sec(el);
        if (DISPLAY == "elapsed" || !(tot > 0)) return e;
        return e + " / " + sec(tot);
    }

    // ms as seconds with one decimal ("2.0").
    private function sec(ms:Number):String {
        var d:Number = Math.round(ms / 100);
        return Math.floor(d / 10) + "." + (d % 10);
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
        dressForDrag(pS, 0x0066FF, "Player Cast");
        dressForDrag(tS, 0xFF0066, "Target Cast");
    }

    public function previewOff():Void {
        previewMode = false;
        if (pS.mc != null) KazBarsPreview.detach(pS.mc);
        if (tS.mc != null) KazBarsPreview.detach(tS.mc);
        draw(pS);
        draw(tS);
    }

    public function previewKey():String { return "cast"; }
    public function previewLabel():String { return "Cast Timer"; }

    // The master switch (control panel and archive) outranks a live cast: off hides both clips (the drag overlay is
    // a child, so it follows); on again mid-preview dresses them for the drag again.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(shown:Boolean):Void {
        active = shown;
        if (shown && previewMode) {
            previewOn();
            return;
        }
        draw(pS);
        draw(tS);
    }

    // The footprint is the timer's own: the text box (TW x TH, anchored on its
    // centre) with the room the overlay's name needs above it and an edge
    // below, so the label clears the text and the box is the
    // same width the text has — and the clamp below uses.
    private function dressForDrag(s:KazBarsCastSide, col:Number, title:String):Void {
        if (s.mc == null) return;
        draw(s);
        var above:Number = KazBarsPreview.roomAbove();
        KazBarsPreview.attach({mc: s.mc, x: -TW / 2, y: -above, w: TW,
                               h: above + TH + KazBarsPreview.roomBelow(),
                               label: title, color: col});
    }

    // =========================================================================
    // Persistence (module config archive — permanent for every user)
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null) return;
        applyPos(pS.mc, config.FindEntry("ctpx"), config.FindEntry("ctpy"));
        applyPos(tS.mc, config.FindEntry("cttx"), config.FindEntry("ctty"));
        var v:Object = config.FindEntry("ctv");
        if (v !== undefined) setActive(v == 1);
    }

    // makeClip centers the text on the clip's own x (a box from -TW/2 to +TW/2),
    // top-anchors it on y, so the clamp floor/ceiling shift by that half-width
    // instead of reusing KazBarsPanel.clampPos's top-left-anchored assumption.
    // The same TW x TH the text box and the preview footprint have.
    private function applyPos(clip:MovieClip, x:Object, y:Object):Void {
        if (clip == null) return;
        if (x !== undefined && y !== undefined) {
            var halfW:Number = TW / 2;
            clip._x = halfW + KazBarsPanel.clampPos(Number(x) - halfW, TW, true);
            clip._y = KazBarsPanel.clampPos(Number(y), TH, false);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        if (pS.mc != null) { config.ReplaceEntry("ctpx", pS.mc._x); config.ReplaceEntry("ctpy", pS.mc._y); }
        if (tS.mc != null) { config.ReplaceEntry("cttx", tS.mc._x); config.ReplaceEntry("ctty", tS.mc._y); }
        config.ReplaceEntry("ctv", active ? 1 : 0);
    }

    // The sides let their characters go (World tells both again on the next start); World's subscriptions stay,
    // made once.
    public function cleanup():Void {
        pS.wire(null);
        tS.wire(null);
        if (kF != null) {
            w.clock.off(kF);
            w.clock.off(kP);
        }
        previewMode = false;
        dropClips();
    }
}
