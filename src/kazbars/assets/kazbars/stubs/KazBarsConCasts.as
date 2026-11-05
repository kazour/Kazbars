// KazBarsConCasts.as - The console's Casts tab: every cast you and your target make, logged when it ends: the time it
// began, the command's name (the start signal carries it; every command with a progress bar comes, a dismount or a
// summon included) and, on the target side, the caster (gold for a player, red for an NPC); then how long it ran and
// how it ended: finished (SignalCommandEnded, green), interrupted (SignalCommandAborted, red) or lost (you retargeted
// while it ran, muted). The start signal's bar type is not shown: it reads 0 whatever the command (measured
// 2026-11-05). It wires World's player and
// target itself, so it works with or without the Cast Timer built. A cast already under way when you target someone
// is not logged: its start was never seen. The newest 100 per column kept.
class KazBarsConCasts implements KazBarsConTab {
    private var con:KazBarsConsole;
    private var W:KazBarsWorld;
    private var pc:Object;        // your Character, and your target's
    private var tc:Object;
    private var tn:Number;        // the target's instance id the last onT saw (0 none): a retarget is a new id, not a new Character
    private var sP:Object;        // the cast under way on each side, {n name, t start, c clock text, w caster run}
    private var sT:Object;
    private var lP:KazBarsConList;
    private var lT:KazBarsConList;

    public function KazBarsConCasts() {
        lP = new KazBarsConList(100, false);
        lT = new KazBarsConList(100, false);
        tn = 0;
    }

    public function key():String { return "casts"; }
    public function label():String { return "Casts"; }
    public function heads():Array { return ["PLAYER CASTS", "TARGET CASTS"]; }
    public function logs():Array { return [lP, lT]; }
    public function head():String { return ""; }
    public function foot():String { return ""; }

    public function follow(c:KazBarsConsole, w:KazBarsWorld):Void {
        con = c;
        W = w;
        w.onPlayer(onP, this);
        w.onTarget(onT, this);
    }

    public function onP(ch:Object, id:Number):Void {
        if (ch != pc) sP = null;
        pc = wire(pc, ch, pS, pE, pA);
    }

    // A retarget while the target's cast ran ends it as lost: a new instance id (World.tn), not a new Character, since
    // World tells a renewed Character for the same target (its first read was blank) and the cast goes on.
    public function onT(t:Object):Void {
        var n:Number = (t == null) ? 0 : W.tn;
        if (n != tn) sT = end(lT, sT, "lost");
        tn = n;
        tc = wire(tc, t, tS, tE, tA);
    }

    // Moves the three cast signals from `old` to `ch`, each connected with this tab as its context. The command queue
    // is hooked again even for the same Character (KazBarsCastSide.wire): World tells the player again on every
    // start, and the client may have let the old hookup go.
    private function wire(old:Object, ch:Object, s:Function, e:Function, a:Function):Object {
        if (old != ch) {
            if (old != null) {
                try {
                    old.SignalCommandStarted.Disconnect(s, this);
                    old.SignalCommandEnded.Disconnect(e, this);
                    old.SignalCommandAborted.Disconnect(a, this);
                } catch (x:Object) {}
            }
            if (ch != null) {
                try {
                    ch.SignalCommandStarted.Connect(s, this);
                    ch.SignalCommandEnded.Connect(e, this);
                    ch.SignalCommandAborted.Connect(a, this);
                } catch (y:Object) {}
            }
        }
        if (ch != null) {
            try { if (ch.ConnectToCommandQueue) ch.ConnectToCommandQueue(); } catch (z:Object) {}
        }
        return ch;
    }

    public function pS(n:String):Void { sP = begin(n, ""); }
    public function pE():Void { sP = end(lP, sP, "finished"); }
    public function pA():Void { sP = end(lP, sP, "interrupted"); }
    public function tS(n:String):Void { sT = begin(n, who()); }
    public function tE():Void { sT = end(lT, sT, "finished"); }
    public function tA():Void { sT = end(lT, sT, "interrupted"); }

    private function begin(n:String, w:String):Object {
        if (!con.isActive()) return null;
        return {n: String(n), t: getTimer(), c: con.clock(), w: w};
    }

    // The target as the caster's run: its name, gold for a player and red for an NPC (an instance id at or above
    // 1 << 24 is a player's, Funcom's ID32.IsPlayer).
    private function who():String {
        var n:String = null;
        try { n = tc.GetName(); } catch (x:Object) {}
        if (n == null || n == "") n = "#" + W.tn;
        return con.run("   by " + n, (W.tn >= 16777216) ? "F7A22B" : "D68585");
    }

    // The cast's lines: when and what in label grey with its caster; then its length and how it ended, in the
    // ending's colour. Returns null: no cast under way on that side now.
    private function end(l:KazBarsConList, s:Object, how:String):Object {
        if (s == null || !con.isActive()) return null;
        var col:String = (how == "finished") ? "7AC142" : ((how == "interrupted") ? "D68585" : "A89A86");
        l.add("", con.run(s.c + "  " + s.n, "C8C0B0") + s.w + "<br>"
                + con.run(sec(getTimer() - s.t) + "   " + how, col) + "<br><br>");
        return null;
    }

    // Milliseconds as seconds to one decimal, built from integers (a fraction is single precision in this client).
    private function sec(ms:Number):String {
        var n:Number = Math.round(ms / 100);
        return Math.floor(n / 10) + "." + (n % 10) + " s";
    }

    public function open(up:Boolean):Void {}

    public function shown(vis:Boolean):Void {}

    public function clear():Void {
        lP.clear();
        lT.clear();
    }

    public function stop():Void {
        pc = wire(pc, null, pS, pE, pA);
        tc = wire(tc, null, tS, tE, tA);
        tn = 0;
        sP = null;
        sT = null;
    }
}
