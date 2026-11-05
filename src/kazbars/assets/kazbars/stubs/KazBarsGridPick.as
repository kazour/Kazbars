// KazBarsGridPick.as - What a grid shows, from a character's entries (KazBarsEffects.a): pick(src, cfg, out) writes
// the display list into out, a reused array, for KazBarsGridView.show. The owner sets now and me (your instance id)
// before a pass; nothing here allocates per call.
//   dynamic  the grid's whitelist (d.WL[cfg.id]: id -> fact code, bits 0-1 the type 1 buff 2 debuff 3 misc, bits
//            2-11 the stack level, bits 12 and up the stacking family) and Applied by me (selfCastOnly); one entry per stacking family
//            (KazBarsCopies.reps); with cfg.one (overhead grids) one per effect name; then misc first and buffFirst /
//            debuffFirst, or all mixed, each sorted by sortOrder (no end counts as 999,999 ms), one icon per running
//            caster copy unless Applied by me (KazBarsCopies.each)
//   static   per slot the newest matching entry, the Forced Engage lock pinned (it applies with its immunity in one
//            instant, so newest can't surface it); the id -> slots map is built once per grid (cfg._m)
// sel and union pick a class's grids and their Effects filter, for KazBarsGrids and KazBarsOverhead.
class KazBarsGridPick {
    public var now:Number;
    public var me:Number;
    private var d:Object;
    private var A:Array;          // the tracked entries
    private var B:Array;          // buffs, debuffs, misc
    private var D:Array;
    private var M:Array;
    private var N:Object;         // effect name -> the pass that saw it (cfg.one)
    private var st:Number;
    private var CS:Function;      // the comparators: shortest, longest, application order
    private var CL:Function;
    private var CA:Function;

    public function KazBarsGridPick(data:Object) {
        d = data;
        now = 0;
        me = 0;
        A = [];
        B = [];
        D = [];
        M = [];
        N = {};
        st = 0;
        var p:KazBarsGridPick = this;
        CS = function(x:Object, y:Object):Number {
            return ((x.exp > 0) ? x.exp - p.now : 999999) - ((y.exp > 0) ? y.exp - p.now : 999999);
        };
        CL = function(x:Object, y:Object):Number {
            return ((y.exp > 0) ? y.exp - p.now : 999999) - ((x.exp > 0) ? x.exp - p.now : 999999);
        };
        CA = function(x:Object, y:Object):Number { return x.at - y.at; };
    }

    public function pick(src:Array, c:Object, out:Array):Void {
        out.length = 0;
        if (src == null) return;
        if (c.slotMode == "static") {
            fixed(src, c, out);
            return;
        }
        var wl:Object = d.WL[c.id];
        var i:Number;
        var e:Object;
        var k:String;
        var q:Array;
        var t:Number;
        A.length = 0;
        for (i = 0; i < src.length; i++) {
            e = src[i];
            if (wl[e.id] > 0 && mine(e, c)) A.push(e);
        }
        if (A.length == 0) return;
        KazBarsCopies.reps(A, wl);
        B.length = 0;
        D.length = 0;
        M.length = 0;
        st++;
        for (i = 0; i < A.length; i++) {
            e = A[i];
            if (c.one) {
                k = (e.buff.m_Name != null) ? String(e.buff.m_Name) : "#" + e.id;
                if (N[k] == st) continue;
                N[k] = st;
            }
            t = wl[e.id] & 3;
            q = (t == 3) ? M : ((t == 2) ? D : B);

            if (c.selfCastOnly) q.push(e);
            else KazBarsCopies.each(e, now, q);
        }
        var f:Function = (c.sortOrder == "shortest") ? CS : ((c.sortOrder == "longest") ? CL : CA);
        add(M, f, out);
        if (c.layout == "debuffFirst") {
            add(D, f, out);
            add(B, f, out);
        } else {
            add(B, f, out);
            add(D, f, out);
        }
        if (c.layout != "buffFirst" && c.layout != "debuffFirst" && out.length > 1) out.sort(f);
    }

    private function add(a:Array, f:Function, out:Array):Void {
        if (a.length > 1) a.sort(f);
        var i:Number;
        for (i = 0; i < a.length; i++) out.push(a[i]);
    }

    private function mine(e:Object, c:Object):Boolean {
        return !c.selfCastOnly || (e.cid > 0 && e.cid == me);
    }

    private function fixed(src:Array, c:Object, out:Array):Void {
        var m:Object = c._m;
        var i:Number;
        var j:Number;
        var k:String;
        var s:Array;
        var e:Object;
        var o:Object;
        var lk:Boolean;
        if (m == null) {
            m = {};
            for (k in c.slots) {
                s = c.slots[k];
                for (j = 0; j < s.length; j++) {
                    if (m[s[j]] == null) m[s[j]] = [];
                    m[s[j]].push(Number(k));
                }
            }
            c._m = m;
        }
        for (i = 0; i < c.rows * c.cols; i++) out[i] = null;
        for (i = 0; i < src.length; i++) {
            e = src[i];
            s = m[e.id];
            if (s == null || !mine(e, c)) continue;
            lk = e.id == 4325954;
            for (j = 0; j < s.length; j++) {
                o = out[s[j]];
                if (o == null || (lk ? (o.id != 4325954 || e.at > o.at) : (o.id != 4325954 && e.at > o.at))) out[s[j]] = e;
            }
        }
    }

    // The grids of type a or b class c builds: its own (cls) and the All ones; with c still 0 the All ones only.
    public static function sel(g:Array, a:String, b:String, c:Number):Array {
        var r:Array = [];
        var i:Number;
        for (i = 0; i < g.length; i++) {
            if ((g[i].type == a || g[i].type == b) && (g[i].cls == undefined || g[i].cls == c)) r.push(g[i]);
        }
        return r;
    }

    // The union of grids l's whitelists (d.WL), the Effects filter; null with no grid.
    public static function union(l:Array, wl:Object):Object {
        if (l.length == 0) return null;
        var u:Object = {};
        var i:Number;
        var k:String;
        for (i = 0; i < l.length; i++) {
            for (k in wl[l[i].id]) u[k] = true;
        }
        return u;
    }
}
