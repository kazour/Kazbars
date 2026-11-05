// KazBarsEffects.as - The tracked effects on one character, shared by every module that shows them (one reader per
// fact). KazBarsWorld makes one per character on request (effects(id)) and sweeps it on the clock. Owners say which
// buff ids they want with watch(owner, ids, task) (an Object id -> true) and let go with unwatch(owner); the union of
// their sets is the filter. The buff signals are connected while there is an owner; with none left the object
// disconnects, empties and goes back to World. Signals only record: they change the entries, bump ver and switch on
// the owners' clock tasks, which redraw when ver moved, so a burst of signals costs one redraw. tap(owner, fn, ctx)
// also hands the owner every effect applied, tracked or not, as fn(this, BuffData) (relation evidence, the console);
// a tap alone is a watch of no ids.
//
// a is the entry array, never replaced (views hold it). An entry is made by entry() (an end, a caster) and
// keeps every caster's copy (KazBarsCopies: its header has the rules). seed() reads the records already on the
// character as found ones: on the first watch, on a filter that grew (ids already held are kept exact), and fresh
// (a emptied first) when World rebinds the character after SlotAlive. Every engine call sits in a try.
class KazBarsEffects {
    public var id:Number;         // the character's instance id
    public var ch:Object;         // its Character
    public var a:Array;
    public var ver:Number;
    public var flt:Object;        // buff id -> true: the owners' union
    private var w:KazBarsWorld;
    private var own:Object;       // owner -> its id set
    private var ix:Object;        // buff id -> its entry in a
    private var live:Boolean;     // the signals are connected
    private var wk:Object;        // owner -> its clock task, switched on by a change
    private var tp:Array;         // taps {o owner, f, c}

    public function KazBarsEffects(world:KazBarsWorld, n:Number, c:Object) {
        w = world;
        id = n;
        ch = c;
        a = new Array();
        ver = 0;
        flt = {};
        own = {};
        ix = {};
        live = false;
        wk = {};
        tp = [];
    }

    public function watch(owner:String, ids:Object, k:Object):Void {
        own[owner] = ids;
        if (k != null) wk[owner] = k;
        union();
        prune();
        if (!live) {
            live = true;
            link("Connect");
        }
        seed(false);
    }

    public function unwatch(owner:String):Void {
        if (own[owner] == undefined) return;
        delete own[owner];
        delete wk[owner];
        var i:Number = tp.length;
        while (i--) {
            if (tp[i].o == owner) tp.splice(i, 1);
        }
        if (union() == 0) {
            close();
            w.gone(this);
            return;
        }
        prune();
    }

    // Entries no owner's set names any more go (a set replaced by a narrower one, an owner gone).
    private function prune():Void {
        var i:Number = a.length;
        var c:Boolean = false;
        while (i--) {
            if (!flt[a[i].id]) {
                delete ix[a[i].id];
                a.splice(i, 1);
                c = true;
            }
        }
        if (c) bump();
    }

    // A tap with no watch of its own watches no ids, which keeps the signals connected.
    public function tap(owner:String, fn:Function, ctx:Object):Void {
        if (own[owner] == undefined) watch(owner, {}, null);
        tp.push({o: owner, f: fn, c: ctx});
    }

    // A new Character for the same id (SlotAlive): reconnect and read everything again.
    public function bind(c:Object):Void {
        if (live) link("Disconnect");
        ch = c;
        if (live) link("Connect");
        seed(true);
    }

    public function close():Void {
        if (live) link("Disconnect");
        live = false;
        own = {};
        flt = {};
        wk = {};
        tp.length = 0;
        a.length = 0;
        ix = {};
        ver++;
    }

    // A change: views redraw on their next run.
    private function bump():Void {
        ver++;
        var o:String;
        for (o in wk) w.clock.go(wk[o]);
    }

    private function union():Number {
        var n:Number = 0;
        var o:String;
        var k:String;
        flt = {};
        for (o in own) {
            n++;
            for (k in own[o]) {
                if (own[o][k]) flt[k] = true;
            }
        }
        return n;
    }

    private function link(op:String):Void {
        try {
            ch.SignalBuffAdded[op](onAdd, this);
            ch.SignalBuffUpdated[op](onAdd, this);
            ch.SignalBuffRemoved[op](onRem, this);
        } catch (e) {}
    }

    public function onAdd(bid:Number):Void {
        if (!flt[bid] && tp.length == 0) return;
        var b:Object = null;
        try { b = ch.m_BuffList[bid]; } catch (e) {}
        if (b == null) return;
        var i:Number;
        for (i = 0; i < tp.length; i++) {
            try { tp[i].f.call(tp[i].c, this, b); } catch (x) {}
        }
        if (flt[bid]) put(b, false);
    }

    // A removal names no caster: the entry settles which copy ended on a later sweep.
    public function onRem(bid:Number):Void {
        var e:Object = ix[bid];
        if (e == null) return;
        KazBarsCopies.remove(e, getTimer());
        bump();
    }

    public function seed(fresh:Boolean):Void {
        if (fresh) {
            a.length = 0;
            ix = {};
        }
        var b:Object;
        var k:String;
        try {
            var bl:Object = ch.m_BuffList;
            for (k in bl) {
                b = bl[k];
                if (b != null && flt[Number(b.m_BuffId)] && ix[Number(b.m_BuffId)] == null) put(b, true);
            }
        } catch (e) {}
        bump();
    }

    // found: a record already on the character, not an application seen.
    private function put(b:Object, found:Boolean):Void {
        var e:Object = entry(b);
        if (found) KazBarsCopies.seed(e);
        var o:Object = ix[e.id];
        if (o == null) {
            ix[e.id] = e;
            a.push(e);
        } else KazBarsCopies.add(o, e, w.myId, e.at);
        bump();
    }

    // One copy of an effect. A copy ends m_TotalTime after its application; m_RemainingTime runs up to a second over.
    // What the effect is to a grid (its type, its stack level) is the grid's own fact (d.WL, KazBarsGridView.draw).
    // ico is the record's RDB icon instance (0: none), read here once, not by every view at every draw. tot is the
    // shown copy's whole run in ms (0 with no end), the bar timer's full width (KazBarsCopies keeps it with exp).
    public static function entry(b:Object):Object {
        var now:Number = getTimer();
        var bid:Number = Number(b.m_BuffId);
        var rt:Number = Number(b.m_RemainingTime);
        var tt:Number = Number(b.m_TotalTime);
        var x:Number = (rt > 0) ? now + ((tt > 0 && rt > tt) ? tt : rt) : 0;
        var c:Number = Number(b.m_CasterId);
        if (!(c > 0)) c = 0;
        var q:Number = 0;
        try { q = Number(b.m_Icon.GetInstance()); } catch (e) {}
        if (!(q > 0)) q = 0;
        return {buff: b, id: bid, ico: q, cid: c, exp: x, at: now, tot: (x > 0) ? x - now : 0,


                cp: [{c: c, x: x, r: rt, b: b, s: false, a: now}], pr: [], rf: 0, u: 0};
    }

    // On the clock: settles copies and drops entries none of whose copies runs. A held removal settling counts as a
    // change (a stacking family's representative may move with it).
    public function sweep(me:Number, now:Number):Void {
        var i:Number = a.length;
        var p:Number;
        var k:Number;
        var c:Boolean = false;
        while (i--) {
            p = a[i].pr.length;
            k = KazBarsCopies.sweep(a[i], me, now);
            if (k == 0) {
                delete ix[a[i].id];
                a.splice(i, 1);
                c = true;
            } else if (k == 2 || a[i].pr.length != p) c = true;
        }
        if (c) bump();
    }
}
