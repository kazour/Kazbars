// KazBarsCastSide.as - One side of the Casting Timer (your casts, or your target's): its Character's three cast
// signals, the cast under way and its estimate, and the length of each spell this side finished (by caster and
// spell name, this session only, the 40 used last). The timer owns the text clip (mc) and draws el / tot; the side
// only measures.
//
// The estimate. Flash gets a spell name, a bar type and a 0-1 progress, no cast time. A spell's length
// is steady for a character, so a spell this caster finished before starts with that length as its total (mem).
// The progress corrects it: from the frame it first moves (t1, q1), the rate since then gives the time left, (1 - q)
// / rate, so the delay before it moves (lag) never skews it, and the live total is the time since the start plus
// that. The live total reads after 100 ms and 2 % of movement, and a spell not seen yet shows it from then; it takes
// over from mem for the rest of the cast once, after 250 ms and 10 % (so one early, rough rate cannot), the two part
// by more than 0.15 s and a tenth (pushback, a buff that cuts the cast, a feat changed). A bar whose first movement
// is down, from 0.5 or more, empties (a channel) and is read as 1 - progress; a drop below 0.5 is a stale reading
// reset and the wait for the first movement goes on, and a first jump to full is a channel's bar filling. A cast
// found under way (mid: targeted while casting) has no start or name: any drop is an emptying bar, its start is
// inferred from the rate, and it shows nothing until that reads.
//
// A finished cast is remembered unless it was mid, nameless or its progress ever went back (pushback); any other end
// is not. What is kept is the live total last read (the time to progress 1, the same measure mem is held against;
// the start-to-end-signal time when it never read). With no end signal, a cast ends itself (lost) once its progress
// has read 0 for 500 ms after moving, or has stood still for 1 s and its total (if any) ran out 1 s ago, or after
// 30 s (2 s mid) if it never moved.
class KazBarsCastSide {
    public var key:String;        // "P" or "T" (the log's)
    public var ch:Object;         // the Character whose signals are connected, else null
    public var mc:MovieClip;      // the timer's text clip for this side (null: this side is not built)
    public var txt:String;        // the text on mc now
    public var busy:Boolean;      // a cast under way
    public var nm:String;         // its spell name ("" when mid)
    public var bar:Number;        // the start signal's bar type (-1 when mid)
    public var mid:Boolean;
    public var t0:Number;         // getTimer() at the start (mid: when it was found)
    public var p0:Number;         // the progress read then
    public var dir:Number;        // 0 until the progress first moves, then 1 (fills) or -1 (empties)
    public var t1:Number;         // the first movement: when, and q there
    public var q1:Number;
    public var q:Number;          // the progress read as filling, this frame
    public var tz:Number;         // the last frame the progress read above 0, and the last it changed (pl: as read)
    private var tc:Number;
    private var pl:Number;
    public var back:Number;       // frames the progress went back
    public var mem:Number;        // the length remembered for nm at the start, ms (0: none)
    public var live:Boolean;      // the live total has taken over from mem
    private var est:Number;       // the live total last read, ms (0: none yet)
    public var el:Number;         // shown: the time since the start and the total, ms (tot 0: none yet)
    public var tot:Number;
    private var tm:KazBarsCastTimer;
    private var ky:String;        // the cast's memory key: "s" + caster + "/" + spell name ("": not kept)
    private var lens:Object;      // key -> its last finished length, ms
    private var order:Array;      // those keys, used longest ago first

    public function KazBarsCastSide(owner:KazBarsCastTimer, k:String) {
        tm = owner;
        key = k;
        txt = "";
        busy = false;
        lens = {};
        order = [];
    }

    // Moves the three signals to c (null: none), this side their context; a cast under way goes with the old one.
    // The command queue is hooked again even for the same Character: World tells the player again on every start (a
    // resurrection, a zone), and the client may have let the old hookup go.
    public function wire(c:Object):Void {
        if (c != ch) {
            if (busy) finish("gone");
            if (ch != null) {
                try {
                    ch.SignalCommandStarted.Disconnect(onStart, this);
                    ch.SignalCommandEnded.Disconnect(onEnd, this);
                    ch.SignalCommandAborted.Disconnect(onAbort, this);
                } catch (e:Object) {}
            }
            ch = c;
            if (c != null) {
                try {
                    c.SignalCommandStarted.Connect(onStart, this);
                    c.SignalCommandEnded.Connect(onEnd, this);
                    c.SignalCommandAborted.Connect(onAbort, this);
                } catch (e2:Object) {}
            }
        }
        if (c != null) {
            try { if (c.ConnectToCommandQueue) c.ConnectToCommandQueue(); } catch (e3:Object) {}
        }
    }

    public function onStart(n:String, b:Number):Void { begin(n, b, false); }
    public function onEnd():Void { finish("done"); }
    public function onAbort():Void { finish("abort"); }

    // The timer's check after a retarget: a cast already under way is followed from here.
    public function probe():Void {
        if (busy || ch == null) return;
        var p:Number = read();
        if (p > 0 && p < 1) begin(null, -1, true);
    }

    public function begin(n:String, b:Number, m:Boolean):Void {
        if (busy) finish("over");
        busy = true;
        nm = (n == null) ? "" : String(n);
        bar = Number(b);
        mid = m;
        t0 = getTimer();
        p0 = read();
        dir = 0;
        t1 = 0;
        q1 = 0;
        q = 0;
        tz = t0;
        tc = t0;
        pl = p0;
        back = 0;
        live = false;
        est = 0;
        ky = "";
        if (nm != "") {
            var who:String = "";
            try { who = String(ch.GetName()); } catch (e:Object) {}
            ky = "s" + who + "/" + nm;
        }
        mem = (ky == "") ? 0 : Number(lens[ky]);
        if (isNaN(mem)) mem = 0;
        el = 0;
        tot = mem;
        tm.began(this);
    }

    // One frame of the cast (the timer's clock task): the progress read, the estimate moved.
    public function tick(now:Number):Void {
        if (!busy) return;
        var p:Number = read();
        if (p > 0) tz = now;
        if (p - pl > 0.001 || pl - p > 0.001) tc = now;
        pl = p;
        // A far caster's progress can stand still above 0: el and tot are the last frame's.
        if ((dir != 0) ? (now - tz >= 500 || (now - tc >= 1000 && (!(tot > 0) || el >= tot + 1000)))
                       : now - t0 >= (mid ? 2000 : 30000)) {
            finish("lost");
            return;
        }
        if (dir == 0) {
            if (p - p0 > 0.001) {
                if (p >= 0.999) p0 = p;
                else dir = 1;
            } else if (p0 - p > 0.001) {
                if (p >= 0.5 || mid) dir = -1;
                else p0 = p;
            }
            if (dir != 0) {
                t1 = now;
                q1 = (dir > 0) ? p : 1 - p;
                q = q1;
            }
        } else if (dir < 0 || p > 0) {
            // A filling bar reads 0 once its command is gone: that is the end, not a step back.
            var nq:Number = (dir > 0) ? p : 1 - p;
            if (nq < q - 0.001) back++;
            q = nq;
        }
        var e:Number = now - t0;
        var lv:Number = 0;
        if (dir != 0 && now - t1 >= 100 && q - q1 >= 0.02) {
            var r:Number = (q - q1) / (now - t1);
            if (mid) {
                e = q / r;
                lv = 1 / r;
            } else lv = e + (1 - q) / r;
        }
        if (mid) {
            el = (lv > 0) ? e : 0;
            tot = lv;
            return;
        }
        el = e;
        if (lv > 0) est = lv;
        if (lv > 0 && mem > 0 && !live && now - t1 >= 250 && q - q1 >= 0.1) {
            var d:Number = lv - mem;
            if (d < 0) d = -d;
            if (d > 150 + mem / 10) live = true;
        }
        tot = (mem > 0 && !live) ? mem : lv;
    }

    // The cast is over: done (its end signal), abort (interrupted), lost (no end signal), over (a new start came
    // first), gone (the side moved to another character).
    public function finish(how:String):Void {
        if (!busy) return;
        busy = false;
        if (how == "done" && !mid && back == 0 && ky != "") remember((est > 0) ? est : getTimer() - t0);
        tm.ended(this);
    }

    // The key moves to the back of order: the 40 used last are kept.
    private function remember(ms:Number):Void {
        var i:Number = order.length;
        while (i--) {
            if (order[i] == ky) {
                order.splice(i, 1);
                break;
            }
        }
        order.push(ky);
        if (order.length > 40) delete lens[order.shift()];
        lens[ky] = ms;
    }

    private function read():Number {
        var p:Number = 0;
        try { p = Number(ch.GetCommandProgress()); } catch (e:Object) {}
        if (isNaN(p) || p < 0) return 0;
        return (p > 1) ? 1 : p;
    }
}
