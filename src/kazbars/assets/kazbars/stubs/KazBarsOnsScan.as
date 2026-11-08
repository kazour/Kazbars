// KazBarsOnsScan.as - Finds and tracks the watched mobs of an Onslaught
// instance (Skull Gate, Kuthchemes), including ones nobody has targeted yet.
// The view (KazBarsOnslaught) makes one of these on entering an instance that
// needs it, drives slice() every frame and poll() once a second, reads the
// public fields below and drops it on leaving, after stop().
//
// No engine surface lists NPCs to Flash, so ids come from two places. Free
// sources (own and team targets, damage, the casters of effects on you) each
// give one id, probed at once; they all come from KazBarsWorld, shared with the
// other modules. A time-sliced scan covers the ids just above the highest one seen,
// because instance spawns take rising ids; measured in game, it found a mini
// 33-37 s before any target or damage event. The probe is one reused ID32
// through DynelBase (0.007 ms an id, against 0.054 for a fresh Character with
// identical names), checked against Character on the first anchor and, until
// it passes, on later ids (ten tries in all). A slice never runs past about a
// millisecond and resumes where it stopped, so the load is steady instead of a
// burst that stutters the client.
//
// A name that is watched becomes a held record: a Character whose HP signal
// and a 1 Hz poll keep pct/distance/state current. A record is the only shape
// shared with the view: id its id, nm name, k kind (b boss, s skull, g guard,
// m mini, c camp, "" ally), ch the Character, cb its signal closure, st state
// (0 alive, 1 out of view, 2 dead, 3 dropped), pct HP percent, d metres or -1,
// cp the name of the camp a skull last stood on ("" none), seen last time the
// name read, dead and drop the times of death and of the last HP loss, row the
// view's own clip, hl and sh the ids of the heal and the shield buff on it (0
// none; buffs are told by name, ids are per session), ca and cr the closures
// of its buff signals. Every engine call sits in a try.
class KazBarsOnsScan {
    public var anchor:Number;     // first id from any source, -1 until then
    public var anchorAt:Number;
    public var mobs:Array;        // held mobs, bosses first, then first-seen
    public var cands:Array;       // AoE candidates {id, nm, ch, mx, at, d}
    public var aoeAt:Number;      // when the burst's first candidate came, 0 = none
    public var ally:Object;       // the defended NPC, once found
    public var fresh:Array;       // found by scan or others, not yet announced

    private var w:KazBarsWorld;
    private var fx:KazBarsEffects;   // yours, tapped for casters
    private var W:Object;         // watched name -> kind
    private var H:Object;         // AoE helper names
    private var HL:Object;        // heal buff names
    private var SH:Object;        // shield buff names
    private var CP:Array;         // this map's skull camps {n, r2, p}, in check order
    private var allyN:String;
    private var wantAoe:Boolean;
    private var CH:Function;      // Character
    private var ID:Function;      // ID32
    private var DB:Function;      // DynelBase, if this client has it
    private var LT:Function;      // what candidates are held as
    private var rid:Object;       // the one ID32 the scan reuses
    private var reuse:Boolean;    // DynelBase on rid answered like Character
    private var tries:Number;     // self-checks run, ten at most
    private var hmin:Number;      // smallest max HP read on a helper-named spawn, unset until one reads
    private var known:Object;     // id -> 1 found, 2 dropped (may be found again, without an alert)
    private var maxId:Number;
    private var jNext:Number;     // the open job is jNext..jHi
    private var jHi:Number;
    private var downNext:Number;  // the sweep below the anchor
    private var downStop:Number;
    private var nearDue:Number;
    private var wideDue:Number;
    private var revDue:Number;
    private var mates:Array;      // the ids of the team members followed

    public function KazBarsOnsScan(world:KazBarsWorld, watch:Object, helpers:Object,
                                   allyName:String, aoe:Boolean, heal:Object, shield:Object,
                                   camps:Array) {
        w = world;
        W = watch;
        H = helpers;
        HL = heal;
        SH = shield;
        CP = [];
        var i:Number;
        for (i = 0; i < camps.length; i++) {
            CP.push({n: camps[i].n, r2: camps[i].r * camps[i].r, p: camps[i].p});
        }
        allyN = allyName;
        wantAoe = aoe;
        CH = com.GameInterface.Game.Character;
        ID = com.Utils.ID32;
        DB = _global["com"]["GameInterface"]["Game"]["DynelBase"];
        LT = (DB != undefined) ? DB : CH;
        rid = new ID(50000, 0);
        reuse = false;
        tries = 0;
        anchor = -1;
        maxId = 0;
        jNext = 1;
        jHi = 0;
        known = {};
        mobs = [];
        cands = [];
        fresh = [];
        mates = [];
        ally = null;
        aoeAt = 0;
    }

    // =========================================================================
    // Id sources
    // =========================================================================

    public function start():Void {
        w.onTarget(onTarget, this);
        w.tm.onDamage(onDmg, this);
        w.tm.onTeam(readTeam, this);
        fx = w.effects(w.myId);
        if (fx != null) fx.tap("ons", onBuff, this);
        readTeam();
    }

    public function stop():Void {
        w.off(this);
        if (fx != null) fx.unwatch("ons");
        fx = null;
        unmate();
        var i:Number = mobs.length;
        while (i--) drop(mobs[i]);
        if (ally != null) drop(ally);
    }

    // The wave is won (the loot phase): every mob of it is dead, and the game never says so
    // for one out of view. Everything held goes but a camp still in view. The ally and the
    // candidates stay; the view takes the rows of the dropped records on its next paint. A
    // dropped record whose mob still lives is found again, without an alert.
    public function clearWave():Void {
        var r:Object;
        var i:Number = mobs.length;
        while (i--) {
            r = mobs[i];
            if (r.k != "c" || r.st != 0) {
                drop(r);
                mobs.splice(i, 1);
            }
        }
    }

    // Your own target is one you already know, so it raises no spawn alert. No
    // target is an id of 0; seen() drops it.
    public function onTarget(t:Object):Void { seen(w.tn, true); }
    public function onMate(n:Number, t:Object):Void { if (t != null) seen(Number(t.m_Instance), false); }
    public function onBuff(e:KazBarsEffects, b:Object):Void { seen(Number(b.m_CasterId), false); }
    public function onDmg(id:Number):Void { seen(id, false); }

    // Each team member but you is held and followed (World: one Character and
    // one target signal per member, whoever else reads them).
    private function readTeam():Void {
        unmate();
        var t:Array = w.tm.team;
        var i:Number;
        var n:Number;
        for (i = 0; i < t.length; i++) {
            n = Number(t[i].m_CharacterId.m_Instance);
            if (n != w.myId && w.hold(n, "ons") != null) {
                w.follow(n, onMate, this);
                mates.push(n);
            }
        }
    }

    private function unmate():Void {
        var i:Number = mates.length;
        while (i--) {
            w.unfollow(mates[i], this);
            w.release(mates[i], "ons");
        }
        mates.length = 0;
    }

    // =========================================================================
    // Probing
    // =========================================================================

    // NPC ids only: players start at 16777216. Until the self-check has passed,
    // each new id that answers with a name gets it again (the anchor had its own).
    private function seen(n:Number, own:Boolean):Void {
        if (!(n > 0 && n < 16777216)) return;
        try {
            if (anchor < 0) firstAnchor(n);
            if (known[n] != 1) {
                var nm:String = probe(n);
                if (nm) {
                    if (!reuse && tries < 10 && n != anchor) check(n);
                    hit(n, nm, !own);
                }
            }
        } catch (e) {}
    }

    private function probe(n:Number):String {
        if (reuse) {
            rid.m_Instance = n;
            return (new DB(rid)).GetName();
        }
        return (new CH(new ID(50000, n))).GetName();
    }

    // The first id anchors the frontier, and has the self-check's first try.
    private function firstAnchor(n:Number):Void {
        var now:Number = getTimer();
        anchor = maxId = n;
        anchorAt = now;
        downNext = n - 1;
        downStop = Math.max(1, n - 15000);
        nearDue = now;
        wideDue = now + 500;
        revDue = now + 5000;
        check(n);
    }

    // DynelBase on the reused id must give the name Character gives on a fresh
    // one, and nothing for a free id; otherwise (or without DynelBase) every
    // probe is a fresh Character. The check is written the way the scan loop
    // is, constructors held in locals, so a client that handles that form
    // differently fails it, not the scan. An id with no name cannot pass it and
    // the first id can be one (a static object the player had targeted, measured
    // in game), which is why it runs again on later ids, ten tries in all.
    // Without DynelBase there is nothing to check, and it only counts.
    private function check(n:Number):Void {
        tries++;
        if (DB == undefined) return;
        try {
            var D:Function = DB;
            var C:Function = CH;
            var I:Function = ID;
            var r:Object = rid;
            r.m_Instance = n;
            var a:String = (new D(r)).GetName();
            var b:String = (new C(new I(50000, n))).GetName();
            r.m_Instance = 16777215;
            var c:String = (new D(r)).GetName();
            reuse = Boolean(a && a == b && !c);
        } catch (e) {}
    }

    // An id answered with a name. XX names are the game's hidden helper NPCs.
    private function hit(n:Number, nm:String, alert:Boolean):Void {
        var back:Boolean = (known[n] == 2);
        known[n] = 1;
        if (n > maxId) maxId = n;
        if (nm.substr(0, 2) == "XX") return;
        var k:String = W[nm];
        if (H[nm]) {
            if (wantAoe || k != undefined) addCand(n, nm);
        } else if (nm == allyN) {
            if (ally == null || ally.st == 2) {
                if (ally != null) drop(ally);
                ally = hold(n, nm, "");
            }
        } else if (k != undefined) {
            add(n, nm, k, alert && !back && k != "c");
        }
    }

    // A mob found already dead is a corpse (they read for 30+ s): nothing to
    // show, and a corpse stays known for good (drop() marks every other record 2,
    // to be found again). One boss per name: a same-name boss that is out of
    // view or dead goes before this one comes in (Thugra Khotan's helper spawns
    // take a new id every few seconds and each would otherwise leave a "last
    // seen" row for 20 s and a slot for five minutes). Other kinds keep their
    // duplicates, they are real. With 80 held a spawn is not held and not known
    // either: a later probe finds it, and it alerts when it gets a slot.
    private function add(n:Number, nm:String, k:String, alert:Boolean):Void {
        if (mobs.length >= 80) {
            delete known[n];
            return;
        }
        var r:Object = hold(n, nm, k);
        if (r.st == 2) {
            drop(r);
            return;
        }
        var i:Number = mobs.length;
        if (k == "b") {
            var g:Object;
            while (i--) {
                g = mobs[i];
                if (g.nm == nm && g.st != 0) {
                    drop(g);
                    mobs.splice(i, 1);
                }
            }
            i = 0;
            while (i < mobs.length && mobs[i].k == "b") i++;
        }
        mobs.splice(i, 0, r);
        if (alert) fresh.push(r);
    }

    // =========================================================================
    // The frontier scan (the hot path: registers only inside the loop)
    // =========================================================================

    // One job at a time, first due wins: the 64 ids above the highest known
    // every 250 ms (93% of spawns land there), the 535 after them every 5 s
    // (the widest gap measured was 585), the unknown ids just below it every
    // 5 s (a spawn can be named after its id was passed), and otherwise a sweep
    // down from the anchor, 64 at a time, which is how an ally or a mob that
    // spawned before the first anchor gets found. A source id far above the
    // highest raises it in hit(), so a wide gap cannot stall the frontier.
    public function slice(now:Number):Void {
        if (jNext > jHi) {
            if (now >= nearDue) {
                nearDue = now + 250;
                jNext = maxId + 1;
                jHi = maxId + 64;
            } else if (now >= wideDue) {
                wideDue = now + 5000;
                jNext = maxId + 65;
                jHi = maxId + 600;
            } else if (now >= revDue) {
                revDue = now + 5000;
                jNext = Math.max(1, maxId - 500);
                jHi = maxId;
            } else if (downNext >= downStop) {
                jHi = downNext;
                jNext = Math.max(downStop, downNext - 63);
                downNext = jNext - 1;
            } else return;
        }
        // The time is read every 16 ids, or every 4 when each costs a Character.
        var kn:Object = known;
        var D:Function = DB;
        var r:Object = rid;
        var fb:Boolean = !reuse;
        var step:Number = fb ? 4 : 16;
        var n:Number = jNext;
        var hi:Number = jHi;
        var t0:Number = getTimer();
        var lim:Number;
        var nm:String;
        try {
            do {
                lim = n + step;
                if (lim > hi + 1) lim = hi + 1;
                while (n < lim) {
                    if (kn[n] != 1) {
                        if (fb) nm = probe(n);
                        else {
                            r.m_Instance = n;
                            nm = (new D(r)).GetName();
                        }
                        if (nm) hit(n, nm, true);
                    }
                    n++;
                }
            } while (n <= hi && getTimer() - t0 < 1);
            jNext = n;
        } catch (e) {
            jNext = jHi + 1;
        }
    }

    // =========================================================================
    // Held mobs
    // =========================================================================

    private function hold(n:Number, nm:String, k:String):Object {
        var now:Number = getTimer();
        var r:Object = {id: n, nm: nm, k: k, ch: new CH(new ID(50000, n)), cb: null, st: 0, pct: 100,
                        d: -1, cp: "", seen: now, dead: 0, drop: 0, row: null, hl: 0, sh: 0};
        r.cb = statSlot(r);
        r.ca = buffSlot(r, true);
        r.cr = buffSlot(r, false);
        try {
            r.ch.SignalStatChanged.Connect(r.cb);
            r.ch.SignalBuffAdded.Connect(r.ca);
            r.ch.SignalBuffRemoved.Connect(r.cr);
            read(r, now, w.ch.GetPosition());
            // A heal or a shield that is up already. The buff list of an NPC is
            // unverified: every level is guarded.
            var bl:Object = r.ch.m_BuffList;
            var q:String;
            var bn:String;
            for (q in bl) {
                bn = bl[q].m_Name;
                if (HL[bn]) r.hl = Number(q);
                if (SH[bn]) r.sh = Number(q);
            }
        } catch (e) {}
        return r;
    }

    // A function of its own so that only its own locals are closure-captured.
    private function statSlot(r:Object):Function {
        var self:KazBarsOnsScan = this;
        return function(stat:Number):Void { if (stat == 27) self.onHp(r); };
    }

    private function buffSlot(r:Object, up:Boolean):Function {
        var self:KazBarsOnsScan = this;
        return function(id:Number):Void { self.onMobBuff(r, id, up); };
    }

    // A heal or a shield buff on a held mob, told by its name. Added: look the
    // buff up by its id. Removed: only that buff's own id clears it, so other
    // buffs coming and going change nothing.
    public function onMobBuff(r:Object, id:Number, up:Boolean):Void {
        if (up) {
            var b:Object = r.ch.m_BuffList[id];
            if (b == undefined) return;
            var nm:String = b.m_Name;
            if (HL[nm]) r.hl = id;
            if (SH[nm]) r.sh = id;
        } else {
            if (id == r.hl) r.hl = 0;
            if (id == r.sh) r.sh = 0;
        }
    }

    // The signal reports a death 0.6-0.9 s before the poll would see it. The
    // name is read first, as read() does: a mob leaving view may have its stats
    // cleared, and an empty name is out of view, not dead. Dead stays dead.
    public function onHp(r:Object):Void {
        try {
            if (r.ch.GetName()) setHp(r, getTimer());
            else if (r.st < 2) r.st = 1;
        } catch (e) {}
    }

    // HP percent is stat 525; where that reads 0 on a live mob, current / max.
    // Dead (stat 27 at 0) stays dead and keeps its first time of death.
    private function setHp(r:Object, now:Number):Void {
        var ch:Object = r.ch;
        var hp:Number = ch.GetStat(27, 2);
        if (hp <= 0) {
            if (r.st != 2) r.dead = now;
            r.st = 2;
            r.pct = 0;
            return;
        }
        r.st = 0;
        var p:Number = Math.round(ch.GetStat(525, 2));
        if (!(p > 0)) {
            var m:Number = ch.GetStat(1, 2);
            p = (m > 0) ? Math.round(hp * 100 / m) : 0;
        }
        if (p < r.pct) r.drop = now;
        r.pct = p;
    }

    // An empty name is out of view, not dead: keep the last pct, distance and camp.
    private function read(r:Object, now:Number, mp:Object):Void {
        var ch:Object = r.ch;
        if (!ch.GetName()) {
            r.st = 1;
            return;
        }
        setHp(r, now);
        if (r.st == 0) {
            r.seen = now;
            var p:Object = ch.GetPosition();
            r.d = dist(mp, p);
            if (r.k == "s") r.cp = campAt(p);
        }
    }

    // The first camp with a point within its reach (3-D, squared), or "".
    private function campAt(p:Object):String {
        var i:Number;
        var j:Number;
        var c:Object;
        var a:Array;
        var x:Number;
        var y:Number;
        var z:Number;
        for (i = 0; i < CP.length; i++) {
            c = CP[i];
            a = c.p;
            for (j = 0; j < a.length; j += 3) {
                x = p.x - a[j];
                y = p.y - a[j + 1];
                z = p.z - a[j + 2];
                if (x * x + y * y + z * z <= c.r2) return c.n;
            }
        }
        return "";
    }

    private function dist(a:Object, b:Object):Number {
        var x:Number = a.x - b.x;
        var y:Number = a.y - b.y;
        var z:Number = a.z - b.z;
        return Math.round(Math.sqrt(x * x + y * y + z * z));
    }

    private function drop(r:Object):Void {
        r.ch.SignalStatChanged.Disconnect(r.cb);
        r.ch.SignalBuffAdded.Disconnect(r.ca);
        r.ch.SignalBuffRemoved.Disconnect(r.cr);
        r.ch = null;
        r.hl = 0;
        r.sh = 0;
        if (r.st != 2) known[r.id] = 2;
        r.st = 3;
    }

    // =========================================================================
    // AoE candidates. Kuthchemes' ghost boss spawns helpers that share Thugra
    // Khotan's name, and the champion himself spawns under it when the wave's
    // phase turns Boss. A spawn with a helper name is a candidate. The helpers
    // all have the same max HP within an instance and the champion has about
    // twice that (1.8-2.1 times, measured), so a candidate whose max HP is at
    // least 1.5 times the smallest seen on any helper-named spawn is the
    // champion, and is promoted at once. The figure is read again every poll:
    // a spawn can still show the helper's for a moment, and a champion seen
    // before any helper only stands out once one arrives. HP lost says nothing,
    // helpers lose some within seconds. They are gone by 31 s (measured), so a
    // candidate still there at 32 s is the champion too.
    // =========================================================================

    private function addCand(n:Number, nm:String):Void {
        var now:Number = getTimer();
        var c:Object = {id: n, nm: nm, ch: new LT(new ID(50000, n)), at: now};
        if (isChamp(c)) {
            promote(c);
            return;
        }
        if (cands.length == 0) aoeAt = now;
        c.d = dist(w.ch.GetPosition(), c.ch.GetPosition());
        cands.push(c);
    }

    // Reads the candidate's max HP, keeps the smallest figure seen, and says
    // whether this one is the champion's. A figure that did not read (0, or no
    // number) says nothing, and is kept as read for the log.
    private function isChamp(c:Object):Boolean {
        var m:Number = c.ch.GetStat(1, 2);
        c.mx = m;
        if (!(m > 0)) return false;
        if (!hmin || m < hmin) hmin = m;
        return m >= hmin * 1.5;
    }

    // A champion is held like any other watched name (an unwatched one gets no row).
    private function promote(c:Object):Void {
        if (W[c.nm] != undefined) add(c.id, c.nm, W[c.nm], true);
    }

    // =========================================================================
    // The 1 Hz poll
    // =========================================================================

    public function poll(now:Number):Void {
        try {
            var mp:Object = w.ch.GetPosition();
            var r:Object;
            var i:Number = mobs.length;
            while (i--) {
                r = mobs[i];
                // A corpse goes after 10 s; out of view, a mob's fate is
                // unknowable (measured), so after 300 s it stops holding a slot.
                if (r.st == 2 ? now - r.dead > 10000 : r.st == 1 && now - r.seen > 300000) {
                    drop(r);
                    mobs.splice(i, 1);
                } else if (r.st != 2) read(r, now, mp);
            }
            if (ally != null && ally.st != 2) read(ally, now, mp);
            var c:Object;
            i = cands.length;
            while (i--) {
                c = cands[i];
                if (!c.ch.GetName()) cands.splice(i, 1);
                else if (isChamp(c) || now - c.at >= 32000) {
                    cands.splice(i, 1);
                    promote(c);
                } else c.d = dist(mp, c.ch.GetPosition());
            }
            if (cands.length == 0) aoeAt = 0;
        } catch (e) {}
    }
}
