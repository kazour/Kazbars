// KazBarsOverhead.as - Overhead grids (types friendly and hostile): per character KazBarsRelations knows to be of a
// grid's relation (you among the friendly, for a grid with showSelf), a pooled KazBarsGridView over the character, fed from its Effects
// (KazBarsWorld). No archive position and no control-panel row; preview shows one empty sample of each grid over
// your target.
//
// The client gives a projected point by the top of the head (KazBarsRelations.point), the one the game hangs its
// nameplate from. A character's views are one stack centred KazBarsRelations.side px left of the point (the head's
// centre): the lowest shown one's bottom edge
// KazBarsRelations.lift (the anchor's projected rise plus its own plateOffset px of nameplate room) above the point, each next
// shown one STACK px above the one below, in bake order (the static grids, then the bands: the generator bakes them so), so the
// static grids sit against the nameplate and the bands grow above them; an empty or hidden one takes no place. A band's
// W and H follow what it shows, so a view's content is picked before its place is computed. A view hides out of
// view, dead, past maxDistance m, wholly off the stage or on an unreadable point; past every one of its grids'
// maxDistance the point is not read at all.
// One clock task every frame while any character is held (or in preview): positions every frame, in twips; content
// at most every 6th frame, when the Effects' ver moved or the view shows again; timers every 3rd.
// Per class as the screen grids (KazBarsGridPick.sel); a class change gives every view back to its cfg's pool (_p),
// and with no overhead grid for the class KazBarsRelations idles (need).
class KazBarsOverhead implements KazBarsModule {
    public static var STACK:Number = 4;   // px between stacked views
    public var ros:KazBarsRelations;
    public var S:Object;          // the stage (KazBarsPanel.stage()), read once a frame
    public var W:Number;          // its size
    public var H:Number;
    public var pv:Boolean;
    public var smp:Array;         // preview samples, one per grid
    private var sp:Object;        // the samples' point, reused
    private var root:MovieClip;
    private var w:KazBarsWorld;
    private var clk:KazBarsClock;
    private var d:Object;
    private var pk:KazBarsGridPick;
    private var out:Array;
    public var cfgs:Array;
    private var ids:Object;       // every built overhead grid's whitelist, for the Effects filter
    private var cls:Number;
    private var clip:MovieClip;
    private var kF:Object;

    public function KazBarsOverhead(r:MovieClip) {
        root = r;
        out = [];
        cfgs = [];
        smp = [];
        sp = {x: 0, y: 0, d: 0};
        cls = 0;
        pv = false;
    }

    public function configure(data:Object, world:KazBarsWorld, clock:KazBarsClock):Void {
        d = data;
        w = world;
        clk = clock;
        pk = new KazBarsGridPick(d);
        kF = clk.add(frame, this, 1, false, 0);
        ros = new KazBarsRelations(this, w, "rel");

        onClass(0);
        w.onClass(onClass, this);
    }

    // The class's grids; every record's views go back and are taken again by sync.
    public function onClass(c:Number):Void {
        if (c == cls && c > 0) return;
        cls = c;
        var i:Number;
        var g:Object;
        for (i = 0; i < ros.recs.length; i++) {
            release(ros.recs[i]);
            ros.recs[i].rk = -1;
        }
        cfgs = KazBarsGridPick.sel(d.CFG.grids, "friendly", "hostile", c);
        ids = KazBarsGridPick.union(cfgs, d.WL);
        for (i = 0; i < cfgs.length; i++) {
            g = cfgs[i];
            g.one = true;
            g._r = (g.type == "friendly") ? 1 : 2;
            if (g._p == null) g._p = [];
        }
        ros.need(cfgs.length > 0);
        wake();
    }

    public function create():Void {
        cleanup();
        clip = root.createEmptyMovieClip("kzPlates", root.getNextHighestDepth());
    }

    public function wake():Void { clk.go(kF); }

    // =========================================================================
    // Frame
    // =========================================================================

    public function frame():Void {
        var now:Number = clk.now;
        var f:Number = clk.frame;
        readStage();
        pk.now = now;
        pk.me = w.myId;
        var i:Number;
        var r:Object;
        for (i = 0; i < ros.recs.length; i++) {
            r = ros.recs[i];
            sync(r);
            place(r, now, f % 3 == 0, f % 6 == 0);
        }
        if (pv) placeSamples();
        else if (ros.recs.length == 0) clk.off(kF);
    }

    private function readStage():Void {
        S = KazBarsPanel.stage();
        W = S.w;
        H = S.h;
    }

    // The views the record's relation calls for; its Effects watched while it has any.
    private function sync(r:Object):Void {
        var rk:Number = ros.eff(r.id);
        if (rk == r.rk) return;
        r.rk = rk;
        var i:Number;
        var v:KazBarsGridView;
        var mx:Number = 0;
        r.n = 0;
        for (i = 0; i < cfgs.length; i++) {
            v = r.vs[i];
            if (cfgs[i]._r == rk && (r.id != w.myId || cfgs[i].showSelf != false)) {
                if (v == null) r.vs[i] = take(i);
                r.n++;
                if (cfgs[i].maxDistance > mx) mx = cfgs[i].maxDistance;
            } else if (v != null) {
                give(v);
                r.vs[i] = null;
            }
        }
        r.mx = mx;
        if (r.n > 0 && r.e == null) {
            r.e = w.effects(r.id);
            if (r.e != null) r.e.watch("oh", ids);
            r.ev = -1;
        } else if (r.n == 0) unwatch(r);
    }

    // The point is read every frame (a plate that lags a frame jitters) while the character is within some view's
    // range; the camera distance, which only scales the lift, on the slow cadence. top is the stack so far: the top
    // edge of the last view placed with something in it (up once there is one).
    private function place(r:Object, now:Number, anim:Boolean, slow:Boolean):Void {
        if (!(r.n > 0)) return;
        var p:Object = (r.vis && !r.dead && r.d <= r.mx) ? ros.point(r.ch, S, r.pt, slow || r.cd == 0) : null;
        if (p != null) r.cd = p.d;
        var redo:Boolean = slow && r.e != null && r.e.ver != r.ev;
        if (redo) r.ev = r.e.ver;
        var i:Number;
        var v:KazBarsGridView;
        var x:Number;
        var y:Number;
        var top:Number = 0;
        var up:Boolean = false;   // top holds a view
        var ok:Boolean;
        for (i = 0; i < r.vs.length; i++) {
            v = r.vs[i];
            if (v == null) continue;
            ok = p != null && r.d <= v.cfg.maxDistance;
            if (ok) {
                if (!v.shown || redo || v.stale) {
                    v.shown = true;
                    v.stale = false;
                    pk.pick((r.e != null) ? r.e.a : null, v.cfg, out);
                    v.show(out);
                    v.mc._visible = v.n > 0;
                }
                x = p.x - ros.side(r.cd, H) - v.W / 2;
                y = (up ? top - STACK : p.y - ros.lift(v.cfg.plateOffset, r.cd, H)) - v.H;
                ok = x + v.W > S.x && x < S.x + W && y + v.H > S.y && y < S.y + H;
            }
            if (!ok) {
                if (v.shown) {
                    v.shown = false;
                    v.mc._visible = false;
                }
                if (redo) v.stale = true;
            } else {
                v.to(x, y);
                if (v.n > 0) {
                    top = y;
                    up = true;
                }
                if (anim) v.tick(now);
            }
        }
    }

    private function take(i:Number):KazBarsGridView {
        var v:KazBarsGridView = cfgs[i]._p.pop();
        if (v == null) {
            v = new KazBarsGridView(clip, "v" + clip.getNextHighestDepth(), cfgs[i], d);
            v.reset();
        }
        return v;
    }

    private function give(v:KazBarsGridView):Void {
        v.reset();
        v.cfg._p.push(v);
    }

    private function unwatch(r:Object):Void {
        if (r.e != null) r.e.unwatch("oh");
        r.e = null;
    }

    // A record leaving the roster.
    public function release(r:Object):Void {
        var i:Number;
        for (i = 0; i < r.vs.length; i++) {
            if (r.vs[i] != null) give(r.vs[i]);
        }
        r.vs.length = 0;
        r.n = 0;
        unwatch(r);
    }

    // =========================================================================
    // KazBarsModule. Preview: one empty sample of each grid, stacked over your target (the screen centre with none).
    // =========================================================================

    public function previewOn():Void {
        if (pv) return;
        pv = true;
        var i:Number;
        for (i = 0; i < cfgs.length; i++) {
            smp[i] = take(i);
            smp[i].fill();
            smp[i].mc._visible = true;
        }
        clk.go(kF);
    }

    public function previewOff():Void {
        if (!pv) return;
        pv = false;
        var i:Number;
        for (i = 0; i < smp.length; i++) give(smp[i]);
        smp.length = 0;
    }

    // The samples stacked as the views would be, over your target (the screen centre with none).
    private function placeSamples():Void {
        var x:Number = S.x + W / 2;
        var y:Number = S.y + H / 2;
        var cd:Number = 0;
        var p:Object = (ros.tch != null) ? ros.point(ros.tch, S, sp, true) : null;

        if (p != null) {
            cd = p.d;
            x = p.x - ros.side(cd, H);
            y = p.y;
        }
        var i:Number;
        var v:KazBarsGridView;
        for (i = 0; i < smp.length; i++) {
            v = smp[i];
            y -= ((i == 0) ? ros.lift(v.cfg.plateOffset, cd, H) : STACK) + v.H;
            v.to(x - v.W / 2, y);
        }
    }

    public function cleanup():Void {
        previewOff();
        ros.stop();
        clk.off(kF);
        if (clip != null) clip.removeMovieClip();   // none before the first create()
        clip = null;
        var g:Array = d.CFG.grids;
        var i:Number;
        for (i = 0; i < g.length; i++) g[i]._p = [];
    }

    public function loadState(config:Object):Void {}
    public function saveState(config:Object):Void {}
    public function isActive():Boolean { return true; }
    public function setActive(a:Boolean):Void {}
    public function previewKey():String { return ""; }
    public function previewLabel():String { return ""; }
}
