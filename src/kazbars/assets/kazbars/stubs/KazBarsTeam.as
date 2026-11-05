// KazBarsTeam.as - Your group and the damage feed, for every module through KazBarsWorld (world.tm); split from World
// for its byte budget. World polls it once a second, stops it on cleanup and starts it again on its start().
//   team    linked with the first onTeam and unlinked with the last: TeamInterface's join, leave and leader signals
//           plus the poll. team is the member table's rows (you included) by group index, lead the leader's id;
//           subscribers are told when membership, order or leader changed (a new one reads team itself).
//   damage  one SignalDamageInfo connection while onDamage has subscribers; they get (id, txt, pts, cl, ft).
// off(ctx) drops ctx from both. Every engine call sits in a try.
class KazBarsTeam {
    public var team:Array;
    public var lead:Number;
    private var w:KazBarsWorld;
    private var sM:Array;         // subscribers {f, c}: team, damage
    private var sD:Array;
    private var tsig:String;      // the team's ids and leader, last read
    private var lk:Boolean;       // linked: false from stop() to start()

    public function KazBarsTeam(world:KazBarsWorld) {
        w = world;
        team = [];
        lead = 0;
        sM = [];
        sD = [];
        tsig = "";
        lk = true;
    }

    public function onTeam(fn:Function, ctx:Object):Void {
        sM.push({f: fn, c: ctx});
        if (sM.length == 1 && lk) link("Connect");
        read();
    }

    public function onDamage(fn:Function, ctx:Object):Void {
        sD.push({f: fn, c: ctx});
        if (sD.length == 1 && lk) dmg("Connect");
    }

    public function off(ctx:Object):Void {
        if (w.cut(sM, ctx) && sM.length == 0) {
            if (lk) link("Disconnect");
            tsig = "";
        }
        if (w.cut(sD, ctx) && sD.length == 0 && lk) dmg("Disconnect");
    }

    public function poll():Void {
        if (sM.length > 0) read();
    }

    // Cleanup unlinks but keeps the subscribers (some subscribe once, at configure); start() links them again.
    public function stop():Void {
        if (!lk) return;
        lk = false;
        if (sM.length > 0) link("Disconnect");
        if (sD.length > 0) dmg("Disconnect");
        tsig = "";
    }

    public function start():Void {
        if (lk) return;
        lk = true;
        if (sM.length > 0) link("Connect");
        if (sD.length > 0) dmg("Connect");
    }

    private function link(op:String):Void {
        try {
            var ti:Object = _global["com"]["GameInterface"]["Game"]["TeamInterface"];
            ti.SignalClientJoinedTeam[op](read, this);
            ti.SignalCharacterJoinedTeam[op](read, this);
            ti.SignalClientLeftTeam[op](read, this);
            ti.SignalCharacterLeftTeam[op](read, this);
            ti.SignalNewTeamLeader[op](read, this);
        } catch (e) {}
    }

    public function read():Void {
        var s:String = "";
        var i:Number;
        var k:String;
        var n:Number;
        team.length = 0;
        lead = 0;
        try {
            var ti:Object = _global["com"]["GameInterface"]["Game"]["TeamInterface"];
            var tm:Object = ti["m_TeamMembers"];
            for (k in tm) {
                if (tm[k] != null && Number(tm[k].m_CharacterId.m_Instance) > 0) team.push(tm[k]);
            }
            team.sort(byGroup);
            for (i = 0; i < team.length; i++) {
                n = Number(team[i].m_CharacterId.m_Instance);
                if (lead == 0 && ti.IsTeamLeader(team[i].m_CharacterId)) lead = n;
                s += n + ",";
            }
        } catch (e) {}
        s += lead;
        if (s != tsig) {
            tsig = s;
            w.tell(sM, team);
        }
    }

    private static function byGroup(x:Object, y:Object):Number {
        return Number(x.m_GroupIndex) - Number(y.m_GroupIndex);
    }

    private function dmg(op:String):Void {
        try { _global["com"]["GlobalSignal"]["SignalDamageInfo"][op](onDmg, this); } catch (e) {}
    }

    public function onDmg(id:Number, txt:Object, x:Number, y:Number, pts:Number, dist:Number, cl:Boolean, ft:Number):Void {
        w.tell(sD, id, txt, pts, cl, ft);
    }
}
