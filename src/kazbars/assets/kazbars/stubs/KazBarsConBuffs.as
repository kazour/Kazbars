// KazBarsConBuffs.as - The console's Buffs tab: every effect applied to you and to your target, tracked or not: its
// name, with "tracked" after it when a grid in this build watches the id; then the buff id (the id a grid needs for a
// buff the database does not carry) and its total duration, green for a beneficial effect and red for a hostile one
// (the game's own m_Hostile), and its caster, gold for a player and red for an NPC. It taps World's one set of buff
// signals (KazBarsEffects.tap), so it adds no signal of its own. The taps are held only while the console is open: a
// closed one keeps no Effects live for it. Each id once per column, the newest 100 kept; the records already on a
// character as its tap starts (an opening, a new target) are listed too, no application of theirs being signalled.
// Of the record's other fields, m_Count, m_MaxCounters and m_ColorLine read 0 on every effect and m_BuffType and
// m_Cancelable are not on it (measured 2026-11-04).
class KazBarsConBuffs implements KazBarsConTab {
    private var con:KazBarsConsole;
    private var W:KazBarsWorld;
    private var up:Boolean;          // the console is open
    private var fP:KazBarsEffects;   // your Effects and your target's, tapped while open
    private var fT:KazBarsEffects;
    private var lP:KazBarsConList;
    private var lT:KazBarsConList;

    public function KazBarsConBuffs() {
        up = false;
        lP = new KazBarsConList(100, true);
        lT = new KazBarsConList(100, true);
    }

    public function key():String { return "buffs"; }
    public function label():String { return "Buffs"; }
    public function heads():Array { return ["PLAYER BUFFS", "TARGET BUFFS"]; }
    public function logs():Array { return [lP, lT]; }
    public function head():String { return ""; }
    public function foot():String { return "Red hostile, green friendly. Holds 100 ids a side, each once."; }

    public function follow(c:KazBarsConsole, w:KazBarsWorld):Void {
        con = c;
        W = w;
        w.onPlayer(onP, this);
        w.onTarget(onT, this);
    }

    public function onP(ch:Object, id:Number):Void { fP = see(fP, id, "conP", seenP, lP); }
    public function onT(t:Object):Void { fT = see(fT, W.tn, "conT", seenT, lT); }

    private function see(o:KazBarsEffects, n:Number, k:String, f:Function, l:KazBarsConList):KazBarsEffects {
        if (o != null) {
            if (up && o.id == n) return o;
            o.unwatch(k);
        }
        var e:KazBarsEffects = (up && n > 0) ? W.effects(n) : null;
        if (e != null) {
            e.tap(k, f, this);
            found(e, l);
        }
        return e;
    }

    // The records already on the character as the tap starts.
    private function found(e:KazBarsEffects, l:KazBarsConList):Void {
        var bl:Object = null;
        try { bl = e.ch.m_BuffList; } catch (x:Object) {}
        if (bl == null) return;
        var k:String;
        for (k in bl) {
            var b:Object = bl[k];
            if (b != null) put(l, e, b);
        }
    }

    public function seenP(e:KazBarsEffects, b:Object):Void { put(lP, e, b); }
    public function seenT(e:KazBarsEffects, b:Object):Void { put(lT, e, b); }

    // Two lines: the time and the name in label grey, the tracked mark muted; the id and total in the side's colour,
    // then the caster in its own.
    private function put(l:KazBarsConList, e:KazBarsEffects, b:Object):Void {
        if (!con.isActive() || b.m_Name == null) return;
        var id:Number = Number(b.m_BuffId);
        l.add(String(id), con.run(con.clock() + "  " + b.m_Name, "C8C0B0") + con.run(e.flt[id] ? "   tracked" : "", "A89A86") + "<br>"
                + con.run("ID " + id + total(Number(b.m_TotalTime)), (b.m_Hostile == true) ? "D68585" : "7AC142")
                + who(Number(b.m_CasterId)) + "<br><br>");
    }

    // The record's total, ms, to one decimal in seconds, minutes from a minute, hours from an hour, built from
    // integers (a fraction is single precision in this client: 13.6 prints as 13.60000038147); nothing for an effect
    // with no end (0). The unit is picked on the rounded tenths, so 59.96 s is 1.0 min, never 60.0 s.
    private function total(ms:Number):String {
        if (!(ms > 0)) return "";
        var u:String = "s";
        var n:Number = Math.round(ms / 100);
        if (n >= 600) { u = "min"; n = Math.round(ms / 6000); }
        if (n >= 600) { u = "h"; n = Math.round(ms / 360000); }
        return "   " + Math.floor(n / 10) + "." + (n % 10) + " " + u;
    }

    // The caster as a run: you, a character World can name, else its id alone; nothing for none. Gold for a player,
    // red for an NPC: an instance id at or above 1 << 24 is a player's (Funcom's ID32.IsPlayer, a field test).
    private function who(c:Number):String {
        if (!(c > 0)) return "";
        var col:String = (c >= 16777216) ? "F7A22B" : "D68585";
        if (c == W.myId) return con.run("   by you", col);
        var n:String = null;
        try { n = W.get(c, null).GetName(); } catch (x:Object) {}
        return con.run("   by " + ((n == null || n == "") ? ("#" + c) : n), col);
    }

    public function open(b:Boolean):Void {
        up = b;
        onP(W.ch, W.myId);
        onT(null);
    }

    public function shown(vis:Boolean):Void {}

    public function clear():Void {
        lP.clear();
        lT.clear();
    }

    public function stop():Void {
        open(false);
    }
}
