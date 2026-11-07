// KazBarsRelations.as - The characters an overhead grid can float over, and whether each is friendly or hostile.
// KazBarsOverhead owns one and reads recs. Characters, your target, a held character's own target (follow), the team
// and the damage feed all come from KazBarsWorld.
//
// A character is known once something names it: you, your target, your group, a character your damage or heals land
// on, the caster of an effect on any held character, or the target of a character already held. The engine lists no
// one around you. At most MAX are held; a full roster evicts the dead first, then the unknown, then the farthest from
// you (out of view counts as farthest), never you, your target or a group member. One nothing named for 30 s is
// dropped unless alive, near (100 m) and of a known relation: a corpse never keeps its place.
// The evidence: you and a group member are friendly; a player is friendly unless proven hostile (an
// id at or above PLAYER is a player's, Funcom's ID32.IsPlayer); an NPC is unknown until evidence. Your damage on a
// character makes it hostile, your heal friendly. An effect on a held character whose relation is known puts its
// caster on the other side when hostile, the same side when beneficial; with the caster's relation known and the
// subject's not, the subject is marked the same way; a self-cast effect says nothing. Hostile is never overturned;
// all of it resets on a fresh SlotAlive (a new zone or character, not a resurrection). With no overhead grid built
// for your class it stays idle: no records, no evidence, no team or damage feed, no clock (need()). A record: id, ch,
// seen, vis (a name: in view), dead, d (m from you), cd (camera m, the view's), pt (its point, the view's, reused),
// plus the view's own fields. Each instance holds and taps under its own owner key (the overhead grids' and the
// Console's World tab's never release each other's).
// point(): GetScreenPosition() is a projected point that some contexts give as a fraction of the stage: a point
// outside -1.5..2.5 settles it as pixels at once, ten inside settle fractions, until then an inside one reads as one.
class KazBarsRelations {
    public static var PLAYER:Number = 16777216;   // 1 << 24: the first player instance id (ID32.IsPlayer)
    public static var MAX:Number = 32;
    public var recs:Array;
    public var byId:Object;
    public var tgt:Number;        // your target's instance id, 0 none
    public var tch:Object;        // its Character, for the preview samples
    public var norm:Number;       // screen points: -1 undecided, 0 pixels, 1 fractions
    private var normN:Number;     // fraction-looking points seen while undecided
    private var view:Object;      // KazBarsOverhead: wake(), release(rec)
    private var w:KazBarsWorld;
    private var rel:Object;       // id -> 1 friendly, 2 hostile
    private var mates:Object;     // id -> true while in your group
    private var tp:Object;        // id -> the Effects tapped for evidence (every record, and you)
    private var live:Boolean;
    private var kP:Object;
    private var key:String;       // this instance's World hold and Effects tap owner

    public function KazBarsRelations(v:Object, world:KazBarsWorld, owner:String) {
        view = v;
        w = world;
        key = owner;
        recs = [];
        byId = {};
        rel = {};
        mates = {};
        tp = {};
        tgt = 0;
        live = false;
        kP = w.clock.add(poll, this, 250, true, 125);
        w.onPlayer(start, this);
        w.onTarget(onTarget, this);
    }

    // A fresh SlotAlive (World: a new zone or character): evidence and records start over, you are the first record
    // and the target you already have the second. A resurrection keeps them.
    public function start(ch:Object, id:Number, fresh:Boolean):Void {
        if (live && !fresh) return;
        stop();
        if (!(view.cfgs.length > 0)) return;
        live = true;
        norm = -1;
        normN = 0;
        acquire(id);
        w.tm.onDamage(onDmg, this);
        w.tm.onTeam(readTeam, this);
        readTeam(w.tm.team);
        if (w.tn > 0) onTarget(w.tgt);
    }

    // Overhead, on a class change: whether any overhead grid is built.
    public function need(b:Boolean):Void {
        if (!b) stop();
        else if (!live && w.ch != null) start(w.ch, w.myId, true);
    }

    public function stop():Void {
        live = false;
        w.tm.off(this);
        var i:Number = recs.length;
        while (i--) drop(recs[i]);   // each drop lets its tap go
        byId = {};
        rel = {};
        mates = {};
        tgt = 0;
        tch = null;
        w.clock.off(kP);
    }

    // A character's projected point in stage pixels (s: KazBarsPanel.stage(), a fraction's frame) into o (x, y, and
    // with cd its camera distance d, else d kept), o back, or null when unreadable. o is the caller's, reused: a
    // frame of plates allocates nothing.
    public function point(ch:Object, s:Object, o:Object, cd:Boolean):Object {
        var p:Object = null;
        try { p = ch.GetScreenPosition(); } catch (e) {}
        if (p == null) return null;
        var x:Number = Number(p.x);
        var y:Number = Number(p.y);
        if (!(x == x) || !(y == y)) return null;
        var inside:Boolean = x >= -1.5 && x <= 2.5 && y >= -1.5 && y <= 2.5;
        if (norm < 0) {
            if (!inside) norm = 0;
            else if (++normN >= 10) norm = 1;
        }
        if (inside && norm != 0) {
            x = s.x + x * s.w;
            y = s.y + y * s.h;
        }
        o.x = x;
        o.y = y;
        if (cd) {
            try { o.d = ch.GetCameraDistance(); } catch (e2) {}
        }
        return o;
    }

    // How far over the point a stack's bottom edge sits: the anchor is d.PF.up x H / 1440 / cd px above the point
    // (a world distance, so it projects as 1 / cd; cd floored at 2 m; -13 by default, the head's centre a touch
    // below the point at 1440p), and the stack starts off px of nameplate room above that.
    public function lift(off:Number, cd:Number, H:Number):Number {
        return off + w.d.PF.up * H / 1440 / ((cd > 2) ? cd : 2);
    }

    // How far right of the head's centre the point sits: d.PF.side x H / 1440 / cd px (389 by default, measured
    // at 1440p over 10-20 m, whichever way the character faces); a stack is centred that far left of it.
    public function side(cd:Number, H:Number):Number {
        return w.d.PF.side * H / 1440 / ((cd > 2) ? cd : 2);
    }

    // 1 friendly, 2 hostile, 0 unknown. You and your group beat evidence; evidence beats the player default.
    public function eff(n:Number):Number {
        if (n == w.myId || mates[n]) return 1;
        if (rel[n] > 0) return rel[n];
        return (n >= PLAYER) ? 1 : 0;
    }

    // =========================================================================
    // Sources and evidence
    // =========================================================================

    public function onTarget(c:Object):Void {
        if (!live) return;
        tgt = 0;
        tch = null;
        var n:Number = w.tn;
        if (!(n > 0) || n == w.myId) return;
        tgt = n;
        tch = c;
        acquire(n);
    }

    public function readTeam(team:Array):Void {
        if (!live) return;
        mates = {};
        var i:Number;
        var n:Number;
        for (i = 0; i < team.length; i++) {
            n = Number(team[i].m_CharacterId.m_Instance);
            if (n > 0 && n != w.myId) {
                mates[n] = true;
                rel[n] = 1;
                acquire(n);
            }
        }
    }

    private function tap(n:Number):Void {
        if (tp[n] != null) return;
        var e:KazBarsEffects = w.effects(n);
        if (e == null) return;
        e.tap(key, onBuff, this);
        tp[n] = e;
    }

    // An effect applied to a held character: the side its caster is on, from the subject's relation, or the side
    // the subject is on, from the caster's. Hostile crosses sides, beneficial keeps them. A self-cast one says
    // nothing beyond naming the caster.
    public function onBuff(e:KazBarsEffects, b:Object):Void {
        if (!live) return;
        var c:Number = Number(b.m_CasterId);
        var h:Boolean = (b.m_Hostile == true);
        var s:Number = (c == e.id) ? 0 : eff(e.id);
        var k:Number = (c == e.id) ? 0 : eff(c);
        mark(c, (s > 0) ? (h ? 3 - s : s) : 0);
        if (s == 0 && k > 0) mark(e.id, h ? 3 - k : k);
    }

    // A number over anyone but you is your damage (2-8 a hit, 9 a dodge of your attack) or your heal (0-1).
    public function onDmg(n:Number, txt:Object, pts:Number, cl:Boolean, ft:Number):Void {
        if (cl || !live) return;
        if (ft >= 2 && ft <= 9) mark(n, 2);
        else if (ft == 0 || ft == 1) mark(n, 1);
    }

    // v 1 friendly, 2 hostile, 0 named only (acquired, no evidence).
    private function mark(n:Number, v:Number):Void {
        if (!(n > 0) || n == w.myId || mates[n]) return;
        if (v > 0 && rel[n] != 2) rel[n] = v;
        acquire(n);
    }

    // =========================================================================
    // Records
    // =========================================================================

    private function acquire(n:Number):Object {
        var now:Number = getTimer();
        var r:Object = byId[n];
        if (r != null) {
            r.seen = now;
            return r;
        }
        if (recs.length >= MAX && !evict()) return null;
        var ch:Object = w.hold(n, key);
        if (ch == null) return null;
        r = {id: n, ch: ch, seen: now, vis: true, dead: false, d: 0, cd: 0, pt: {x: 0, y: 0, d: 0}, vs: [], rk: 0, n: 0, mx: 0};
        byId[n] = r;
        recs.push(r);
        tap(n);
        w.follow(n, onHeld, this);   // after the record exists: it hands onHeld the current target at once
        view.wake();
        w.clock.go(kP);
        return r;
    }

    // A held character's target is known too.
    public function onHeld(h:Number, t:Object):Void {
        if (!live || t == null || byId[h] == null) return;
        var n:Number = Number(t.m_Instance);
        if (n > 0 && n != w.myId) acquire(n);
    }

    // Dead first, then unknown, then the farthest; never you, your target or a group member.
    private function evict():Boolean {
        var b:Object = null;
        var r:Object;
        var i:Number = recs.length;
        while (i--) {
            r = recs[i];
            if (r.id != tgt && r.id != w.myId && !mates[r.id]) {
                if (b == null || rank(r) < rank(b) || (rank(r) == rank(b) && dist(r) > dist(b))) b = r;
            }
        }
        if (b == null) return false;
        drop(b);
        return true;
    }

    // Who goes first from a full roster: 0 dead, 1 unknown, 2 known.
    private function rank(r:Object):Number {
        return r.dead ? 0 : ((eff(r.id) == 0) ? 1 : 2);
    }

    // Metres from you; out of view counts as the farthest.
    private function dist(r:Object):Number {
        return r.vis ? r.d : 1e9;
    }

    private function drop(r:Object):Void {
        if (tp[r.id] != null) {
            tp[r.id].unwatch(key);
            delete tp[r.id];
        }
        w.unfollow(r.id, this);
        view.release(r);
        w.release(r.id, key);

        r.ch = null;
        delete byId[r.id];
        var i:Number = recs.length;
        while (i--) {
            if (recs[i] == r) recs.splice(i, 1);
        }
    }

    // Four times a second while any is held: in view (a name), dead (stat 27 at 0), metres from you, then the 30 s TTL.
    public function poll():Void {
        var now:Number = getTimer();
        var mp:Object = null;
        try { mp = w.ch.GetPosition(); } catch (e) {}
        var i:Number = recs.length;
        var r:Object;
        var p:Object;
        var x:Number;
        var y:Number;
        var z:Number;
        while (i--) {
            r = recs[i];
            r.ch = w.get(r.id, null);     // World's, renewed when it read blank
            try {
                r.vis = Boolean(r.ch.GetName());
                if (r.vis) {
                    r.dead = !(r.ch.GetStat(27, 2) > 0);
                    p = r.ch.GetPosition();
                    x = p.x - mp.x;
                    y = p.y - mp.y;
                    z = p.z - mp.z;
                    r.d = Math.sqrt(x * x + y * y + z * z);
                    if (!r.dead && r.d <= 100 && eff(r.id) != 0) r.seen = now;
                }
            } catch (e2) { r.vis = false; }
            if (now - r.seen > 30000 && r.id != tgt && r.id != w.myId && !mates[r.id]) drop(r);
        }
        if (recs.length == 0) w.clock.off(kP);
    }
}
