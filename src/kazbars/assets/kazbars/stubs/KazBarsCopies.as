// KazBarsCopies.as - The copies of one effect that several characters cast on one character. The client keeps one
// record per buff id, and measured in game (two clients, 2026-10-16) it behaves like this: every application, a
// second caster's included, arrives as SignalBuffAdded (Updated was never seen) with a new BuffData naming that
// caster; the first copy to end deletes the record while the other copies still run; SignalBuffRemoved carries only
// the id, so it never says whose copy ended; a copy ends m_TotalTime after its application (m_RemainingTime runs up
// to a second over); and m_RemainingTime is fixed when the client receives the record, so a record found already on
// a character only gives an upper bound on its end. So an entry keeps every copy it has seen, each with its caster
// and end time, and matches each removal to a copy:
//   add     an application: the caster's copy joins the entry, or replaces that caster's earlier copy
//   seed    an entry made from a record found already on the character: its copy's end is an upper bound, and
//           copies cast before it was found may run unseen until that end at the latest
//   remove  a removal: held GAP ms first. With an application of the id in the same instant (either order) it is
//           one replacement: of that caster's copy (a refresh: they cancel out), else of the copy ending soonest
//           other than the new one (another caster takes it over, as a shared stack does on every hit). Alone, it
//           ends, in this order, the copy whose end is within TOL of it, a found copy that may have ended by then
//           (another caster's before yours), nothing while unseen copies may still run (one of them ended), else the
//           copy whose end is nearest (an early end: a dispel)
//   sweep   a few times a second: settles held removals, drops a copy GRACE ms past its end that no removal claimed
//           (some effects end with no signal), and sets what the entry shows: your copy while you have one running,
//           else the one that ends last (cid, exp, buff)
//   each    a grid's icons for the entry: one per running copy, each with its own timer, as the game's buff bar
//           shows them (one caster's copy at a time: a caster's recast refreshes its copy)
//   reps    one entry per stacking family (each stack level is an id of its own, and a new level arrives as the old
//           one's removal plus the new one's application): the entry with no removal held, then the most recent
//           application, then the highest level. One stack or several at once shows only the new level
// An entry ends when none of its copies is running. Entry fields: cp (copies {c caster, x end time or 0 for none,
// r the record's m_RemainingTime, b BuffData, s found, a applied, v its icon's entry}), pr (held removals {t time,
// k the copy a takeover added}), rf (when an application replaced its caster's copy, for one removal to cancel), rk
// and rt (a copy another caster just added and when, for a removal right after to take over), u (until when unseen
// copies may run), n (running copies at the last sweep).
class KazBarsCopies {
    public static var GAP:Number = 300;
    public static var TOL:Number = 1000;
    public static var GRACE:Number = 1500;

    public static function seed(e:Object):Object {
        e.cp[0].s = true;
        e.u = until(e.cp[0]);
        return e;
    }

    // Copies cast before a found one end before it does: unseen ones run until its end at the latest.
    private static function until(c:Object):Number {
        return (c.x > 0) ? c.x : 1e15;
    }

    // e: a fresh entry (KazBarsEffects.entry, seeded or not) for old's id. True when its copies changed.
    public static function add(old:Object, e:Object, me:Number, now:Number):Boolean {
        var n:Object = e.cp[0];
        var cp:Array = old.cp;
        var pr:Array = old.pr;
        var ch:Boolean = true;
        var i:Number = cp.length;
        while (i--) {
            if (cp[i].c == n.c) break;
        }
        if (n.s) {
            // A found copy replaces that caster's known one only when it is another application: the record's
            // m_RemainingTime is fixed per application, so the same value is the copy already known, exact end
            // and all.
            if (!(old.u >= until(n))) old.u = until(n);
            if (i < 0) cp.push(n);
            else if (cp[i].r != n.r) cp[i] = n;
            else ch = false;
        } else {
            // A caster's own refresh explains a held removal before any takeover guess does.
            var p:Object = (pr.length > 0 && now - pr[pr.length - 1].t <= GAP) ? pr[pr.length - 1] : null;
            if (i >= 0) {
                cp[i] = n;
                if (p != null) pr.pop();
                else old.rf = now;
            } else {
                cp.push(n);
                if (p != null && p.k == null) p.k = n;
                else { old.rk = n; old.rt = now; }
            }
        }
        old.at = e.at;
        var b:Object = pick(cp, me, now);
        show(old, (b != null) ? b : n);
        return ch;
    }

    public static function remove(e:Object, now:Number):Void {
        var k:Object = (e.rk != null && now - e.rt <= GAP) ? e.rk : null;
        e.rk = null;
        if (e.rf > 0 && now - e.rf <= GAP) e.rf = 0;
        else e.pr.push({t: now, k: k});
    }

    // 0: no copy is running, the entry ends; 1: unchanged; 2: what it shows, or how many copies run, changed.
    public static function sweep(e:Object, me:Number, now:Number):Number {
        var cp:Array = e.cp;
        var pr:Array = e.pr;
        while (pr.length > 0 && now - pr[0].t >= GAP) end(e, cp, pr.shift(), me);
        var i:Number = cp.length;
        while (i--) {
            if (cp[i].x > 0 && now > cp[i].x + GRACE) cp.splice(i, 1);
        }
        var b:Object = pick(cp, me, now);
        if (b == null) return 0;
        var n:Number = 0;
        for (i = 0; i < cp.length; i++) {
            if (cp[i].x == 0 || cp[i].x > now) n++;
        }
        var ch:Boolean = (n != e.n);
        e.n = n;
        return (show(e, b) || ch) ? 2 : 1;
    }

    // The entry's icons into dst: itself while one copy runs, else one per running copy (each its own icon entry,
    // made once per copy and kept on it).
    public static function each(e:Object, now:Number, dst:Array):Void {
        var cp:Array = e.cp;
        var c:Object;
        var v:Object;
        var n:Number = 0;
        var i:Number;
        for (i = 0; i < cp.length; i++) {
            if (cp[i].x == 0 || cp[i].x > now) n++;
        }
        if (n <= 1) { dst.push(e); return; }
        for (i = 0; i < cp.length; i++) {
            c = cp[i];
            if (c.x == 0 || c.x > now) {
                v = c.v;
                if (v == null) { v = {id: e.id, ico: e.ico}; c.v = v; }

                v.buff = c.b;
                v.exp = c.x;
                v.tot = c.x - c.a;
                v.cid = c.c;
                v.at = c.a;
                dst.push(v);
            }
        }
    }

    // In place, over a view's entries: wl is the grid's id set, each id's fact code (KazBarsData: bits 12 and up its
    // stacking family, 0 for none; bits 2-11 its level; one family's codes differ in the level alone, so the greater
    // code is the higher level). An entry goes when another of its family beats it: no removal held, then the later
    // application, then the higher level (a family's ids each have their own).
    public static function reps(list:Array, wl:Object):Void {
        var i:Number = list.length;
        var j:Number;
        var a:Object;
        var b:Object;
        var f:Number;
        while (i--) {
            b = list[i];
            f = wl[b.id] >> 12;
            if (!(f > 0)) continue;
            for (j = 0; j < list.length; j++) {
                a = list[j];
                if (a != b && (wl[a.id] >> 12) == f && (((a.pr.length > 0) != (b.pr.length > 0)) ? b.pr.length > 0
                        : ((a.at != b.at) ? a.at > b.at : wl[a.id] > wl[b.id]))) {
                    list.splice(i, 1);

                    break;
                }
            }
        }
    }

    // The copy the held removal r ended, by the rules above.
    private static function end(e:Object, cp:Array, r:Object, me:Number):Void {
        var t:Number = r.t;
        var k:Number = -1;
        var d:Number = 0;
        var x:Number;
        var c:Object;
        var i:Number;
        for (i = 0; i < cp.length; i++) {
            x = (cp[i].x > 0) ? Math.abs(cp[i].x - t) : 1e12;
            if (cp[i] != r.k && (k < 0 || x < d)) { k = i; d = x; }
        }
        if (k >= 0 && d > TOL && r.k == null) {
            var f:Number = -1;
            for (i = 0; i < cp.length; i++) {
                c = cp[i];
                if (c.s && (c.x == 0 || c.x >= t - TOL) && (f < 0 || (cp[f].c == me && c.c != me))) f = i;
            }
            if (f >= 0) k = f;
            else if (e.u > t) k = -1;
        }
        if (k >= 0) cp.splice(k, 1);
    }

    // The running copy to show: yours, else the one that ends last (one with no end first). Null: none runs.
    private static function pick(cp:Array, me:Number, now:Number):Object {
        var b:Object = null;
        var c:Object;
        var i:Number;
        for (i = 0; i < cp.length; i++) {
            c = cp[i];
            if (c.x == 0 || c.x > now) {
                if (me > 0 && c.c == me) return c;
                if (b == null || (b.x > 0 && (c.x == 0 || c.x > b.x))) b = c;
            }
        }
        return b;
    }

    private static function show(e:Object, b:Object):Boolean {
        var ch:Boolean = (e.cid != b.c || e.exp != b.x || e.buff != b.b);
        e.cid = b.c;
        e.exp = b.x;
        e.tot = b.x - b.a;
        e.buff = b.b;
        return ch;
    }
}
