// KazBarsGrids.as - The screen grids (types player and target): one KazBarsGridView each at its archived spot, fed
// from your Effects and your target's (KazBarsWorld), picked by KazBarsGridPick. One clock task every 3rd frame
// redraws a side's grids when its Effects' ver moved, then runs timers and flashing; with nothing on screen it
// switches off until an Effects change switches it on again. Overhead grids are KazBarsOverhead's.
// Per class: only your class's grids (cls) and the All ones are built, the All ones alone until the class reads
// (KazBarsWorld.onClass); a class change hides the old set (each view stays on its cfg, _v, for reuse) and builds the
// new one at its archived spots, after preview if it is on.
// Archive: gk_<key>_x, gk_<key>_y, gk_<key>_v (shown); a grid not built keeps whatever the archive holds.
class KazBarsGrids implements KazBarsModule {
    public var views:Array;       // for the control panel's rows
    private var root:MovieClip;
    private var w:KazBarsWorld;
    private var clk:KazBarsClock;
    private var d:Object;
    private var pk:KazBarsGridPick;
    private var out:Array;
    private var cfgs:Array;
    private var ids:Array;        // per side (0 player, 1 target): the whitelists' union, null with no grid of it
    private var fx:Array;         // per side: the Effects watched
    private var vr:Array;         // per side: its ver at the last redraw
    private var pv:Boolean;
    private var dc:Boolean;       // a class change waiting for preview to end
    private var cls:Number;
    private var cf:Object;        // the archive, once it arrived
    private var kD:Object;

    public function KazBarsGrids(r:MovieClip) {
        root = r;
        views = [];
        out = [];
        cfgs = [];
        ids = [null, null];
        fx = [null, null];
        vr = [-1, -1];
        pv = false;
        dc = false;
        cls = 0;
    }

    public function configure(data:Object, world:KazBarsWorld, clock:KazBarsClock):Void {
        d = data;
        w = world;
        clk = clock;
        pk = new KazBarsGridPick(d);
        kD = clk.add(draw, this, 3, false, 0);
        w.onPlayer(onPlayer, this);
        w.onTarget(onTarget, this);
        w.onClass(onClass, this);
    }

    public function create():Void {
        free();
        build();
    }

    public function onClass(c:Number):Void {
        if (c == cls) return;
        cls = c;
        if (pv) dc = true;
        else build();
    }

    // The class's views: the old set saved and hidden, the new one made or taken back from its cfg, placed from the
    // archive, its sides' Effects watched with the new whitelists.
    private function build():Void {
        if (cf != null) saveState(cf);
        var i:Number;
        var c:Object;
        for (i = 0; i < views.length; i++) views[i].mc._visible = false;
        views.length = 0;
        cfgs = KazBarsGridPick.sel(d.CFG.grids, "player", "target", cls);
        for (i = 0; i < cfgs.length; i++) {
            c = cfgs[i];
            if (c._v == null) c._v = new KazBarsGridView(root, "g_" + c.key, c, d);
            views.push(c._v);
        }
        ids = [KazBarsGridPick.union(KazBarsGridPick.sel(cfgs, "player", "", cls), d.WL),
               KazBarsGridPick.union(KazBarsGridPick.sel(cfgs, "target", "", cls), d.WL)];
        see(0, w.myId);
        see(1, w.tn);
        loadState(cf);
    }

    public function onPlayer(ch:Object, id:Number):Void { see(0, id); }
    public function onTarget(t:Object):Void { see(1, w.tn); }

    // Side x now follows character n (0: none).
    private function see(x:Number, n:Number):Void {
        var o:KazBarsEffects = fx[x];
        if (o != null && (o.id != n || ids[x] == null)) o.unwatch("grids" + x);
        var e:KazBarsEffects = (n > 0 && ids[x] != null) ? w.effects(n) : null;
        if (e != null) e.watch("grids" + x, ids[x], kD);
        fx[x] = e;
        vr[x] = -1;
        clk.go(kD);
    }

    public function draw():Void {
        var now:Number = clk.now;
        var c0:Boolean = moved(0);
        var c1:Boolean = moved(1);
        var up:Boolean = false;
        var i:Number;
        var v:KazBarsGridView;
        var x:Number;
        pk.now = now;
        pk.me = w.myId;
        for (i = 0; i < views.length; i++) {
            v = views[i];
            x = (v.cfg.type == "player") ? 0 : 1;
            if (!pv && ((x == 0) ? c0 : c1)) {
                pk.pick((fx[x] != null) ? fx[x].a : null, v.cfg, out);
                v.show(out);
                v.mc._visible = v.shown && v.n > 0;
            }
            if (v.mc._visible) {
                v.tick(now);
                up = true;
            }
        }
        if (!up && !pv) clk.off(kD);
    }

    private function moved(x:Number):Boolean {
        var n:Number = (fx[x] != null) ? fx[x].ver : -2;
        if (n == vr[x]) return false;
        vr[x] = n;
        return true;
    }

    // Every view made, built for this class or not.
    private function free():Void {
        var g:Array = d.CFG.grids;
        var i:Number;
        for (i = 0; i < g.length; i++) {
            if (g[i]._v == null) continue;
            KazBarsPreview.detach(g[i]._v.mc);
            g[i]._v.free();
            g[i]._v = null;
        }
        views.length = 0;
    }

    // =========================================================================
    // KazBarsModule
    // =========================================================================

    public function cleanup():Void {
        pv = false;
        free();
        clk.off(kD);
        if (fx[0] != null) fx[0].unwatch("grids0");
        if (fx[1] != null) fx[1].unwatch("grids1");
        fx = [null, null];
    }

    public function previewOn():Void {
        pv = true;
        var i:Number;
        for (i = 0; i < views.length; i++) {
            views[i].fill();
            views[i].mc._visible = views[i].shown;
            KazBarsPreview.createOverlay(views[i]);
        }
        clk.go(kD);
    }

    public function previewOff():Void {
        pv = false;
        var i:Number;
        for (i = 0; i < views.length; i++) KazBarsPreview.detach(views[i].mc);
        vr = [-1, -1];
        clk.go(kD);
        if (dc) {
            dc = false;
            build();
        }
    }

    public function loadState(config:Object):Void {
        vr = [-1, -1];
        clk.go(kD);
        if (config == null) return;
        cf = config;
        var i:Number;
        var v:KazBarsGridView;
        var k:String;
        var x:Object;
        var y:Object;
        for (i = 0; i < views.length; i++) {
            v = views[i];
            k = "gk_" + v.cfg.key;
            x = config.FindEntry(k + "_x");
            y = config.FindEntry(k + "_y");
            if (x !== undefined && y !== undefined) {
                v.mc._x = KazBarsPanel.clampPos(Number(x), v.W, true);
                v.mc._y = KazBarsPanel.clampPos(Number(y), v.H, false);
            }
            // Hidden at once: a grid may already be up from before the archive arrived.
            x = config.FindEntry(k + "_v");
            if (x !== undefined) {
                v.shown = (x == 1);
                if (!v.shown) v.mc._visible = false;
            }
        }
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        var i:Number;
        var v:KazBarsGridView;
        for (i = 0; i < views.length; i++) {
            v = views[i];
            config.ReplaceEntry("gk_" + v.cfg.key + "_x", v.mc._x);
            config.ReplaceEntry("gk_" + v.cfg.key + "_y", v.mc._y);
            config.ReplaceEntry("gk_" + v.cfg.key + "_v", v.shown ? 1 : 0);
        }
    }

    public function isActive():Boolean { return true; }
    public function setActive(a:Boolean):Void {}
    public function previewKey():String { return ""; }
    public function previewLabel():String { return ""; }
}
