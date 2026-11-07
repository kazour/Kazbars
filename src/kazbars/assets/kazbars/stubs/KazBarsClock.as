// KazBarsClock.as - The one frame handler for the grids and the modules on the shared runtime. A task is a function
// and its context, run every N frames or every N ms; a ms task runs on the first frame at or after its due time, and
// its due times keep their phase (a late frame never shifts the next one). add() makes a task switched off; go() and
// off() switch it (`on` is a reserved word). With no task on, the handler is cleared: idle costs nothing. Every task
// runs in a try, so one task's fault never stops the others. A task: f, c (context), e (period), m (ms, else
// frames), p (phase: frames or ms before its first run), d (due time, or frames left), a (on), q (in the run list).
class KazBarsClock {
    public var now:Number;        // getTimer() at this frame
    public var frame:Number;      // frames counted, wraps at 32768
    private var mc:MovieClip;
    private var run:Array;        // tasks on, and ones switched off since the last pass (dropped by it)
    private var h:Function;

    public function KazBarsClock(parent:MovieClip) {
        now = getTimer();
        frame = 0;
        run = [];
        mc = parent.createEmptyMovieClip("kbClock", parent.getNextHighestDepth());
        var self:KazBarsClock = this;
        h = function():Void { self.tick(); };
    }

    public function add(fn:Function, ctx:Object, every:Number, ms:Boolean, phase:Number):Object {
        return {f: fn, c: ctx, e: every, m: ms, p: phase, d: 0, a: false, q: false};
    }

    public function go(k:Object):Void {
        if (k.a) return;
        k.a = true;
        k.d = k.m ? getTimer() + k.p : k.p + 1;
        if (!k.q) {
            k.q = true;
            run.push(k);
        }
        mc.onEnterFrame = h;
    }

    public function off(k:Object):Void {
        k.a = false;
    }

    // Every task off; the clip stays, so a module loaded again (onLoad) can go() on it.
    public function stop():Void {
        var i:Number = run.length;
        while (i--) run[i].a = false;
        mc.onEnterFrame = null;
    }

    private function tick():Void {
        var t:Number = getTimer();
        now = t;
        frame = (frame + 1) % 32768;
        var n:Number = run.length;
        var j:Number = 0;
        var i:Number;
        var k:Object;
        for (i = 0; i < n; i++) {
            k = run[i];
            if (!k.a) {
                k.q = false;
                continue;
            }
            run[j++] = k;
            if (k.m ? t >= k.d : --k.d <= 0) {
                if (k.m) k.d += k.e * (Math.floor((t - k.d) / k.e) + 1);
                else k.d = k.e;
                try { k.f.call(k.c); } catch (e) {}
            }
        }
        // Tasks a task switched on during this pass were pushed after n.
        for (i = n; i < run.length; i++) run[j++] = run[i];
        run.length = j;
        if (j == 0) mc.onEnterFrame = null;
    }
}
