// KazBarsWorld.as - What the game says about you and the characters around you, read once and handed to every
// module (one reader per fact). The host makes one, calls start() on every SlotAlive and stop() on cleanup.
//   player   ch, myId, cls (GetStat(67, 2); an unloaded character reads 0, retried every 500 ms until it reads),
//            zone (the playfield at the last start). onPlayer subscribers get (ch, myId, fresh) on every start, fresh
//            false when it is the same character in the same zone (SlotAlive after a resurrection); onClass ones the
//            class once known and on a change (one subscribing after that is told at once).
//   target   one SignalOffensiveTargetChanged; tgt (its Character or null), tid (the id as the signal gave it), tn
//            (its instance id, 0 none). Re-read once a second in case a signal was missed, and a target whose
//            Character did not read yet read again. onTarget subscribers get tgt on a change, or once it reads.
//   tm       the team and the damage feed (KazBarsTeam), split out for the byte budget.
//   chars    get(id) is the one Character for an instance id (GetCharacter once); hold/release(id, owner) keep it;
//            one nobody holds is dropped GRACE ms after its last release or first read (the 1 s read), your target
//            never while it is; a held one or your target that reads blank is fetched again on that read (renew), so
//            holders take it through get(), and a renewed target is told to onTarget again. follow(id, fn, ctx) hands
//            fn(id, target) the target the character has now, then every change of it, one signal per character; all
//            its followers get the current one again whenever that signal is connected again (renew, start).
//   effects  effects(id) is the KazBarsEffects for a character, swept every 100 ms while any is live. The last 8
//            targets' effects stay watched (owner "rec") for 2 minutes after you switch away, so coming back finds
//            them exact; cleared on a fresh start().
// off(ctx) drops every subscription ctx made. Parts start on first use, every engine call and every subscriber call
// sits in a try.
class KazBarsWorld {
    public static var GRACE:Number = 10000;
    public var clock:KazBarsClock;
    public var d:Object;          // the baked data (d.WL: each grid's ids and their fact codes)

    public var ch:Object;
    public var myId:Number;
    public var cls:Number;
    public var tgt:Object;
    public var tid:Object;
    public var tn:Number;
    public var tm:KazBarsTeam;
    public var zone:Number;
    private var sP:Array;         // subscribers {f, c}: player, class, target
    private var sC:Array;
    private var sT:Array;
    private var chars:Object;     // id -> {c Character, o owners, n how many, t drop time, s followers, f their closure}
    private var fx:Object;        // id -> KazBarsEffects
    private var fl:Array;         // the same, for the sweep
    private var rec:Array;        // recent targets {i id, t when left}, oldest first
    private var kA:Object;        // clock tasks: start retry, class retry, the 1 s read, the sweep (the host's
    private var kC:Object;        // clock.stop() ends them on cleanup)
    private var kT:Object;
    private var kF:Object;

    public function KazBarsWorld(c:KazBarsClock, data:Object) {
        clock = c;
        d = data;
        myId = 0;
        cls = 0;
        tn = 0;
        zone = 0;
        tm = new KazBarsTeam(this);
        sP = [];
        sC = [];
        sT = [];
        chars = {};
        fx = {};
        fl = [];
        rec = [];
        kA = c.add(start, this, 1000, true, 1000);
        kC = c.add(readCls, this, 500, true, 500);
        kT = c.add(poll, this, 1000, true, 250);
        kF = c.add(sweep, this, 100, true, 50);
    }

    // =========================================================================
    // Subscribers
    // =========================================================================

    public function onPlayer(fn:Function, ctx:Object):Void { sP.push({f: fn, c: ctx}); }
    public function onTarget(fn:Function, ctx:Object):Void { sT.push({f: fn, c: ctx}); }

    public function onClass(fn:Function, ctx:Object):Void {
        sC.push({f: fn, c: ctx});
        if (cls > 0) tell([sC[sC.length - 1]], cls);
    }

    public function off(ctx:Object):Void {
        cut(sP, ctx);
        cut(sC, ctx);
        cut(sT, ctx);
        tm.off(ctx);
    }

    // Drops ctx's subscriptions from l; true when it had any.
    public function cut(l:Array, ctx:Object):Boolean {
        var n:Number = l.length;
        var i:Number = n;
        while (i--) {
            if (l[i].c == ctx) l.splice(i, 1);
        }
        return l.length < n;
    }

    public function tell(l:Array, p:Object, q:Object, r:Object, s:Object, u:Object):Void {
        var i:Number;
        for (i = 0; i < l.length; i++) {
            try { l[i].f.call(l[i].c, p, q, r, s, u); } catch (e) {}
        }
    }

    // =========================================================================
    // Player and target
    // =========================================================================

    // SlotAlive: the client character, again. Instance ids do not outlive a zone, so in a new zone (or as another
    // character) recent targets go, held characters are read again and live effects rebound to them. The same
    // character in the same zone (a resurrection) keeps them all: only your own Character, if the client handed
    // out a new one, is rebound. A failure is retried a second later.
    public function start():Void {
        clock.off(kA);
        var k:String;
        try {
            var old:Object = ch;
            if (old != null) old.SignalOffensiveTargetChanged.Disconnect(onTgt, this);
            ch = com.GameInterface.Game.Character.GetClientCharacter();
            if (ch == null) {
                myId = 0;
                clock.go(kA);
                return;
            }
            var id:Number = Number(ch.GetID().GetInstance());
            var z:Number = Number(ch.GetPlayfieldID());   // unreadable: NaN, so fresh
            var fresh:Boolean = !(z > 0 && z == zone && id == myId);
            myId = id;
            zone = z;
            if (fresh) {
                while (rec.length > 0) unrec(0);
                for (k in chars) rebind(Number(k), fetch(Number(k), null));
            } else if (ch != old) rebind(id, ch);
            readCls();
            tm.start();
            ch.SignalOffensiveTargetChanged.Connect(onTgt, this);
            tell(sP, ch, myId, fresh);
            tn = -1;
            onTgt(ch.GetOffensiveTarget());
            for (k in chars) aimNow(chars[k], Number(k), chars[k].s);
            tm.poll();
            clock.go(kT);
        } catch (e) {
            clock.go(kA);
        }
    }

    public function stop():Void {
        var i:Number;
        var k:String;
        try { ch.SignalOffensiveTargetChanged.Disconnect(onTgt, this); } catch (e) {}
        tm.stop();
        for (k in chars) unaim(chars[k]);
        for (i = 0; i < fl.length; i++) {
            fl[i].close();
            release(fl[i].id, "fx");
        }
        fl.length = 0;
        fx = {};
        rec.length = 0;
        ch = null;
    }

    public function readCls():Void {
        var c:Number = 0;
        try { c = Number(ch.GetStat(67, 2)); } catch (e) {}
        if (!(c > 0)) {
            clock.go(kC);
            return;
        }
        clock.off(kC);
        if (c != cls) {
            cls = c;
            tell(sC, c);
        }
    }

    // The old target's effects stay watched before the subscribers let go of them; the new one's are let go of
    // after the subscribers have taken them.
    public function onTgt(t:Object):Void {
        var n:Number = 0;
        try {
            if (t != null && t.GetType() != _global.Enums.TypeID.e_Type_None) n = Number(t.m_Instance);
        } catch (e) {}
        if (!(n > 0)) n = 0;
        if (n == tn) {
            if (n > 0 && tgt == null) {
                tgt = get(n, t);
                if (tgt != null) tell(sT, tgt);
            }
            return;
        }
        drop(tn);
        var x:KazBarsEffects = fx[tn];
        if (tn > 0 && x != null) {
            x.watch("rec", x.flt);
            rec.push({i: tn, t: getTimer()});
            if (rec.length > 8) unrec(0);
        }
        tn = n;
        tid = (n > 0) ? t : null;
        tgt = (n > 0) ? get(n, t) : null;
        tell(sT, tgt);
        drop(n);
    }

    // Once a second: the target the client reports wins, recent targets age out, the team is read, characters
    // nobody held for GRACE ms go.
    public function poll():Void {
        var t:Object = null;
        try { t = ch.GetOffensiveTarget(); } catch (e) {}
        onTgt(t);
        var now:Number = getTimer();
        while (rec.length > 0 && now - rec[0].t > 120000) unrec(0);
        tm.poll();
        var k:String;
        var r:Object;
        var n:Number;
        for (k in chars) {
            r = chars[k];
            n = Number(k);
            if (r.n == 0 && now > r.t && n != tn) {
                unaim(r);
                delete chars[k];
            } else if ((r.n > 0 || n == tn) && !named(r.c)) renew(r, n);
        }
    }

    // Whether a Character reads: one taken while its character was off the client (a member far away, or still
    // loading) stays blank after it comes in, and the client hands out a new one instead.
    public function named(c:Object):Boolean {
        try { return Boolean(c.GetName()); } catch (e) {}
        return false;
    }

    // A held character or your target that reads nothing, fetched again: a new one that reads replaces it, with its
    // target signal and its Effects moved over. Holders read it back through get(); as your target, onTarget is told.
    private function renew(r:Object, n:Number):Void {
        if (n == myId) return;
        var c:Object = fetch(n, null);
        if (c == null || c == r.c || !named(c)) return;
        rebind(n, c);
        aimNow(r, n, r.s);
        if (n == tn) {
            tgt = c;
            tell(sT, c);
        }
    }

    // Character c is id n's now: its target signal and its Effects move over.
    private function rebind(n:Number, c:Object):Void {
        var r:Object = chars[n];
        if (r != null) {
            aimOp(r, "Disconnect");
            r.c = c;
            aimOp(r, "Connect");
        }
        if (fx[n] != null) fx[n].bind(c);
    }

    private function drop(n:Number):Void {
        var i:Number = rec.length;
        while (i--) {
            if (rec[i].i == n) unrec(i);
        }
    }

    private function unrec(i:Number):Void {
        var e:KazBarsEffects = fx[rec[i].i];
        rec.splice(i, 1);
        if (e != null) e.unwatch("rec");
    }

    // =========================================================================
    // Characters and effects
    // =========================================================================

    public function get(n:Number, ido:Object):Object {
        var r:Object = chars[n];
        if (r == null) {
            var c:Object = fetch(n, ido);
            if (c == null) return null;
            r = {c: c, o: {}, n: 0, t: getTimer() + GRACE};
            chars[n] = r;
        }
        return r.c;
    }

    private function fetch(n:Number, ido:Object):Object {
        if (n == myId) return ch;
        var c:Object = null;
        try {
            c = com.GameInterface.Game.Character.GetCharacter((ido != null) ? ido : new com.Utils.ID32(50000, n));
        } catch (e) {}
        return c;
    }

    public function hold(n:Number, owner:String):Object {
        var c:Object = get(n, null);
        var r:Object = chars[n];
        if (r != null && !r.o[owner]) {
            r.o[owner] = true;
            r.n++;
        }
        return c;
    }

    public function release(n:Number, owner:String):Void {
        var r:Object = chars[n];
        if (r == null || !r.o[owner]) return;
        delete r.o[owner];
        if (--r.n == 0) r.t = getTimer() + GRACE;
    }

    // A held character's own target: one signal per character while anyone follows it. A new follower is handed the
    // current one at once: the signal says nothing until it changes.
    public function follow(n:Number, fn:Function, ctx:Object):Void {
        var r:Object = chars[n];
        if (r == null) return;
        if (r.s == null) {
            r.s = [];
            r.f = aim(n);
            aimOp(r, "Connect");
        }
        r.s.push({f: fn, c: ctx});
        aimNow(r, n, [r.s[r.s.length - 1]]);
    }

    public function unfollow(n:Number, ctx:Object):Void {
        var r:Object = chars[n];
        if (r != null && r.s != null && cut(r.s, ctx) && r.s.length == 0) unaim(r);
    }

    private function unaim(r:Object):Void {
        aimOp(r, "Disconnect");
        r.s = null;
    }

    // Followers l (null: none) are handed the target character n has now.
    private function aimNow(r:Object, n:Number, l:Array):Void {
        if (l == null) return;
        var t:Object = null;
        try { t = r.c.GetOffensiveTarget(); } catch (e) {}
        tell(l, n, t);
    }

    private function aimOp(r:Object, op:String):Void {
        if (r.s != null) {
            try { r.c.SignalOffensiveTargetChanged[op](r.f); } catch (e) {}
        }
    }

    // A function of its own so that only its own locals are closure-captured.
    private function aim(n:Number):Function {
        var w:KazBarsWorld = this;
        return function(t:Object):Void { w.aimed(n, t); };
    }

    public function aimed(n:Number, t:Object):Void {
        var r:Object = chars[n];
        if (r.s != null) tell(r.s, n, t);
    }

    // Null when the character can't be read. Watch it to make it live.
    public function effects(n:Number):KazBarsEffects {
        var e:KazBarsEffects = fx[n];
        if (e != null) return e;
        var c:Object = hold(n, "fx");
        if (c == null) return null;
        e = new KazBarsEffects(this, n, c);
        fx[n] = e;
        fl.push(e);
        clock.go(kF);
        return e;
    }

    // An Effects with no owner left.
    public function gone(e:KazBarsEffects):Void {
        var i:Number = fl.length;
        while (i--) {
            if (fl[i] == e) fl.splice(i, 1);
        }
        delete fx[e.id];
        release(e.id, "fx");
        if (fl.length == 0) clock.off(kF);
    }

    public function sweep():Void {
        var now:Number = getTimer();
        var i:Number = fl.length;
        while (i--) fl[i].sweep(myId, now);
    }
}
