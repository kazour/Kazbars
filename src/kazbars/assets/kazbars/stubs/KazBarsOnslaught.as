// KazBarsOnslaught.as - Onslaught Tracker: an in-game HUD module that runs only
// inside the two Onslaught instances (Skull Gate, Kuthchemes) and does no
// per-frame work anywhere else. It finds the watched mobs as they spawn
// (KazBarsOnsScan), shows where they are and how hurt in five tiers (boss,
// skull, mini, camps, guards: the guards' tier is empty unless the build lists
// them apart), times each wave from the game's own wave widget (its progress bar
// is the fatality line), warns about Thugra Khotan's area attacks and keeps the
// defended ally's HP (Valkyrie Hylda) on screen. Which of the five displays
// exist, the watch list, the heal and shield buff names and the per-instance
// facts (playfield ids, start action, spawn window, ally, skull camps) are all
// baked into d.ONS; nothing about the game is hardcoded here.
//
// Two anchors, each placed in preview through the shared overlay in
// KazBarsPreview and remembered in the module archive (onpx onpy onax onay, the
// master switch onv and the alerts' own switch onav): the board (wave line,
// fatality, ally line, then the tiers) and the alerts (spawn alerts, the AoE
// line, low-ally alerts, at their own baked size). They are
// runtime-drawn clips with device-font text, and a HUD element: no handlers
// outside preview, so they are mouse transparent. The class extends
// KazBarsPanel for geometry, text fields and the plate alone, like the inspect
// panel.
//
// The board is laid out from a running cursor: the fixed lines (wave, fatality,
// ally, start hint), then for each tier that has a row a header and its rows in
// the scan's order. The wave line is the board's title: the wave's label, the
// elapsed clock, the phase, the remaining clock and "left", one field each on
// one bottom edge across the board's width, the clocks at the Alert size; the
// fatality line's bar is the board's thickest. A row is a name, a value flush
// right (the distance, or the camp a skull stands on, then the percent), a bar
// under both (light blue while a shield buff is on the mob) and, while a heal
// buff is on the mob, a green cross after the name. It belongs to its
// record (r.row), is made on the record's first paint and is removed when the
// scan drops the record (a won wave drops all but the camps in view) or when the
// mob has been out of view for 20 s; the scan goes on holding that record, and
// the row is made again if the mob comes back.
//
// Lifecycle: the playfield signal and one empty host clip are the only things
// alive outside an instance. The host is made in create(), in registration
// order, so the anchors keep this module's place in the z-order (under the
// console); it holds no handlers and no children until an instance is entered.
// Entering one builds the anchors and the scan and switches on a KazBarsClock
// task that runs the scan slice every frame and renders four times a second.
// The bars glide between renders (KazBarsPanel). Leaving removes all of it
// (clips are removed, never hidden: hidden clips still advance) and switches
// the task off. A new character starts over, the same one keeps the
// run (see connectPlayer). Preview swaps the anchors for placeholders painted
// by the same code; the scan keeps running underneath, only rendering pauses.
// Text is written only when it changed; writes are the expensive part.
class KazBarsOnslaught extends KazBarsPanel implements KazBarsModule {

    // Config (set by configure()). The palette is the family's: text C8C0B0,
    // gold F7A22B, dim 7F786C, red E0503C, bar bands green 7AC142 / gold / red.
    private var LIST:Boolean;
    private var ALERTS:Boolean;
    private var WAVE:Boolean;
    private var AOE:Boolean;
    private var ALLY:Boolean;
    private var ALERT_MS:Number;
    private var ALF:Number;       // the alerts' text size (the board's ALERT_FS is the wave clocks')
    private var W:Object;         // watched name -> kind
    private var H:Object;         // AoE helper names
    private var HEAL:Object;      // heal buff names -> true
    private var SHIELD:Object;    // shield buff names -> true
    private var GUARD:Boolean;    // the guards list apart (their own tier)
    private var TIERS:String;     // the tiers' kind codes, top to bottom
    private var AL:Object;        // alert tag and colour by kind code: {t, c}; a mini's is the default
    private var INST:Object;      // playfield id -> {start, spawnMs, ally, aoe, camps}
    private var PULSE:Array;      // 20 alpha steps, 70 + 30 cos
    private var P:Array;          // anchor x, y pairs: board, alerts
    private var TS:Object;        // tier style by kind code b s m c g: {fs, bold, col, bh, rh, hd}

    // Geometry beyond the base set, every value Math.round(FS x ratio). Type is
    // the base's roles: boss rows and the wave label Title, the wave clocks and
    // the alerts Alert, camp rows and tier headers Small, everything else Body
    // (see KazBarsPanel).
    private static var TT:Array = ["w", "c1", "n", "c2", "l"];   // the title's fields, left to right
    private static var GUT:Number = 4;   // a TextField's two 2 px gutters, around its textWidth
    private var NAME_W:Number;    // 16   name column
    private var VAL_W:Number;     // 9    value column
    private var FAT_H:Number;     // 0.75 the fatality line's bar, the board's thickest
    private var ALLY_H:Number;    // 0.5  the ally line's bar
    private var FAT_X:Number;     // what the fatality line takes: LINE + its bar + 2
    private var ALLY_X:Number;    // the same for the ally line
    private var PW:Number;        // NAME_W + VAL_W
    private var AH:Number;        // the wave line: lh(ALERT_FS)
    private var ALH:Number;       // an alert line: lh(ALF)
    private var AW:Number;        // alert width: the longest alert at ALF
    private var FX:Array;         // each anchor's nominal footprint from its origin:
    private var FW:Array;         // the preview overlay and the archive clamp
    private var FH:Array;

    // State
    private var me:Object;        // the client character
    private var meId:Number;      // its instance id, 0 none
    private var pfId:Number;      // current playfield, -1 unknown
    public var pf:Object;        // its INST entry inside an instance, else null
    private var hc:MovieClip;     // the host clip: anchors and driver live in it
    public var scan:KazBarsOnsScan;
    private var w:KazBarsWorld;
    private var kD:Object;        // the frame task, on inside an instance
    private var active:Boolean;
    private var alertsOn:Boolean; // the alerts anchor shown (the control panel's own row)
    private var previewMode:Boolean;
    private var hasAoe:Boolean;   // what the anchors show right now
    private var hasAlly:Boolean;
    private var allyN:String;
    private var cl:Array;         // anchor clips: 0 board, 1 alerts
    private var ln:Array;         // board line clips by role: 0 wave, 1 fatality, 2 ally, 3 start hint
    private var hd:Array;         // tier header clips, in tier order
    private var rw:Array;         // records that have a row
    private var al:Array;         // live alerts {mc, t}, newest first
    private var pu:Array;         // clips to pulse this frame
    private var a0:MovieClip;     // the AoE line, alert slot 0
    private var ph:Number;        // plate height drawn
    private var nextQ:Number;
    private var nextSec:Number;
    private var lo:Array;         // the ally's 50 and 25 alerts have fired
    private var wPrev:String;     // wave: "" nothing yet, "0" / "1" last active flag
    private var wLab:String;      // the title's label, "Wave " + the game's text, "" until a message gave one
    public var wClock:Boolean;
    public var wStart:Number;
    private var wPh:String;
    private var wCount:Number;
    private var wMax:Number;
    private var wPct:Number;      // the wave bar's fill, 0-100
    private var wFull:Number;     // when the bar filled, 0 while it is not full
    private var wParam:String;
    private var wFinal:String;    // frozen text after a stop
    private var wDone:Boolean;    // after Defeat, until a restart

    public function KazBarsOnslaught(root:MovieClip) {
        super(root);
        active = true;
        alertsOn = true;
        previewMode = false;
        pf = null;
        pfId = -1;
        meId = 0;
        cl = [];
        ln = [];
        hd = [];
        rw = [];
        al = [];
        pu = [];
        ph = 0;
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object, world:KazBarsWorld, clock:KazBarsClock):Void {
        w = world;
        glides(clock);
        kD = clock.add(tick, this, 1, false, 0);
        world.onPlayer(connectPlayer, this);
        LIST = cfg.list;
        ALERTS = cfg.alerts;
        WAVE = cfg.wave;
        AOE = cfg.aoe;
        ALLY = cfg.ally;
        ALERT_MS = cfg.alertMs;
        P = [cfg.x, cfg.y, cfg.ax, cfg.ay];
        INST = cfg.pf;
        applyBaseSize(Number(cfg.fontSize));
        NAME_W = rd(16);
        VAL_W = rd(9);
        FAT_H = rd(0.75);
        ALLY_H = rd(0.5);
        FAT_X = LINE + FAT_H + 2;
        ALLY_X = LINE + ALLY_H + 2;
        PW = NAME_W + VAL_W;
        AH = lh(ALERT_FS);
        ALF = Number(cfg.alertFontSize);
        if (isNaN(ALF) || ALF < 8) ALF = ALERT_FS;
        ALH = lh(ALF);
        // 23.125 x ALF (37 x FS at the 1.6 role) holds the longest alert there
        // can be (SKULL or GUARD + the longest watched name + a three-digit
        // distance) at every size.
        AW = Math.round(ALF * 23.125);
        // The guards' tier exists only when the build lists them apart.
        GUARD = cfg.watch.g.length > 0;
        TIERS = GUARD ? "bsmcg" : "bsmc";
        TS = {b: tier(NAME_FS, true, 0xF7A22B, 0.6, "BOSS"), s: tier(FS, false, 0xE0703C, 0.5, "SKULL"),
              m: tier(FS, false, 0xC8C0B0, 0.4, "MINI"), c: tier(SMALL_FS, false, 0x9A9284, 0.35, "CAMPS")};
        TS.g = tier(FS, false, TS.s.col, 0.5, "GUARD");   // a skull's look under its own header
        AL = {b: {t: "BOSS ", c: 0xE0503C}, s: {t: "SKULL ", c: TS.s.col}, g: {t: "GUARD ", c: TS.s.col},
              m: {t: "", c: 0xF7A22B}};
        FX = [0, -Math.round(AW / 2)];
        FW = [PW + PAD * 2, AW];
        // The board's footprint is its preview sample: wave, fatality and ally lines, four headers,
        // five rows, and the guards' header and row when they list apart.
        FH = [PAD * 2 + (WAVE ? AH + FAT_X : 0) + (ALLY ? ALLY_X : 0)
              + (LIST ? SMALL_H * 4 + TS.b.rh + TS.s.rh + TS.m.rh * 2 + TS.c.rh
                 + (GUARD ? SMALL_H + TS.g.rh : 0) : 0), ALH * 2];
        var k:String;
        var a:Array;
        var i:Number;
        W = {};
        for (k in cfg.watch) {
            a = cfg.watch[k];
            i = a.length;
            while (i--) W[a[i]] = k;
        }
        H = toSet(cfg.helpers);
        HEAL = toSet(cfg.heal);
        SHIELD = toSet(cfg.shield);
        PULSE = [];
        for (i = 0; i < 20; i++) PULSE.push(70 + 30 * Math.cos(i * Math.PI / 10));
    }

    // A geometry ratio of the base size (never a font: those are the base's roles).
    private function rd(k:Number):Number { return Math.round(FS * k); }

    // The names of an array as a set: name -> true.
    private function toSet(a:Array):Object {
        var o:Object = {};
        var i:Number = a.length;
        while (i--) o[a[i]] = true;
        return o;
    }

    // A tier's look: name font (a role) and weight, name colour, bar height (at least 2) and the row's height.
    private function tier(fs:Number, bold:Boolean, col:Number, bk:Number, label:String):Object {
        var bh:Number = Math.max(2, rd(bk));
        return {fs: fs, bold: bold, col: col, bh: bh, rh: lh(fs) + bh + 2, hd: label};
    }

    public function create():Void {
        cleanup();
        hc = rootClip.createEmptyMovieClip("kbOns", rootClip.getNextHighestDepth());
        sig("SignalPlayfieldChanged", "Connect", onPf);
    }

    public function cleanup():Void {
        previewMode = false;
        leave();
        sig("SignalPlayfieldChanged", "Disconnect", onPf);
        if (hc != null) {
            hc.removeMovieClip();
            hc = null;
        }
        me = null;
        meId = 0;
    }

    private function sig(name:String, op:String, fn:Function):Void {
        try { _global["com"]["GameInterface"]["ScryWidgets"][name][op](fn, this); } catch (e) {}
    }

    // =========================================================================
    // The playfield gate. SlotAlive (World's player) calls connectPlayer: a new character (login,
    // relog: another instance id) starts over, the same one keeps the run, since SlotAlive may also
    // fire on a resurrection and people die often; told by id, as the client may hand out a new
    // Character object for the same character. The playfield signal alone ends an instance, so
    // there is no disconnectPlayer.
    // =========================================================================

    public function connectPlayer(ch:Object, id:Number):Void {
        if (id != meId) {
            leave();
            meId = id;
        }
        me = ch;
        checkPf();
    }

    // The signal carries the new id; GetPlayfieldID reads 0 during the loading
    // screen (measured in game).
    public function onPf(id:Number):Void { setPf(Number(id)); }

    private function checkPf():Void {
        var id:Number = -1;
        try { if (me != null) id = Number(me.GetPlayfieldID()); } catch (e) {}
        setPf(id);
    }

    // The same playfield again keeps the run (a SlotAlive with the same
    // character lands here). The early return needs pf != null: the signal can
    // come before the first connectPlayer, when nothing has been entered yet.
    private function setPf(id:Number):Void {
        if (pf != null && id == pfId) return;
        leave();
        pfId = id;
        var p:Object = INST[id];
        if (p != undefined && active && me != null) enter(p);
    }

    private function enter(p:Object):Void {
        pf = p;
        var an:String = ALLY ? p.ally : "";
        var ao:Boolean = AOE && p.aoe;
        if (!previewMode) build(false);
        if (LIST || ALERTS || ao || an != "") {
            scan = new KazBarsOnsScan(w, W, H, an, ao, HEAL, SHIELD, p.camps);
            scan.start();
        }
        wReset();
        if (WAVE) sig("SignalScryMessage", "Connect", onScry);
        ck.go(kD);
        nextQ = 0;
        nextSec = 0;
    }

    private function leave():Void {
        if (pf != null && WAVE) sig("SignalScryMessage", "Disconnect", onScry);
        if (scan != null) {
            scan.stop();
            scan = null;
        }
        ck.off(kD);
        unbuild();
        pf = null;
        if (previewMode && active) build(true);
    }

    public function isActive():Boolean {
        return active;
    }

    // Off leaves; on starts fresh (and rebuilds the placeholders in preview).
    public function setActive(shown:Boolean):Void {
        active = shown;
        if (shown) checkPf();
        else leave();
    }

    public function alertsShown():Boolean {
        return alertsOn;
    }

    // The alerts anchor alone (its preview frame is its child): the board runs on.
    public function setAlerts(shown:Boolean):Void {
        alertsOn = shown;
        if (cl[1] != null) cl[1]._visible = shown;
    }

    public function previewKey():String { return "ons"; }
    public function previewLabel():String { return "Onslaught"; }

    // =========================================================================
    // The driver (a clock task): the scan slice every frame, then a
    // 4 Hz render with the scan's 1 Hz poll in it. With only the wave timer it
    // is a clock compare per frame, one text write a second and the bar's scale
    // four times a second (its pulse is the only thing animated per frame, for
    // 3 s once a wave).
    // =========================================================================

    public function tick():Void {
        var now:Number = ck.now;
        var s:KazBarsOnsScan = scan;
        if (s != null && s.anchor >= 0) s.slice(now);
        if (now >= nextQ) {
            nextQ = now + 250;
            if (s != null && now >= nextSec) {
                nextSec = now + 1000;
                s.poll(now);
            }
            if (!previewMode) render(now);
            if (s != null) s.fresh.length = 0;
        }
        if (al.length + pu.length > 0) animate(now);
    }

    // Alerts fade over 600 ms after ALERT_MS; the ally and the mob rows pulse
    // while their HP fell in the last 3 s. Alpha only: the bars and plates take
    // it for certain, device-font text is unverified.
    private function animate(now:Number):Void {
        var a:Number = PULSE[Math.floor(now / 30) % 20];
        var i:Number = pu.length;
        var e:Object;
        while (i--) pu[i]._alpha = a;
        i = al.length;
        while (i--) {
            e = al[i];
            if (now - e.t >= ALERT_MS + 600) {
                e.mc.removeMovieClip();
                al.splice(i, 1);
            } else if (now - e.t > ALERT_MS) e.mc._alpha = 100 - (now - e.t - ALERT_MS) / 6;
        }
    }

    // =========================================================================
    // Anchors. build() makes the clips each display needs at their stored
    // positions, unbuild() reads the positions back and removes them. The
    // board always exists; the alerts anchor only if something can alert. In
    // preview (prev) every enabled display exists, painted with sample data.
    // =========================================================================

    private function build(prev:Boolean):Void {
        hasAoe = AOE && (prev || pf.aoe);
        hasAlly = ALLY && (prev || pf.ally != "");
        allyN = prev ? "Valkyrie Hylda" : pf.ally;
        var want:Array = [true, ALERTS || hasAoe || hasAlly];
        var i:Number;
        var c:MovieClip;
        for (i = 0; i < 2; i++) {
            if (want[i]) {
                c = hc.createEmptyMovieClip("kbOns" + i, hc.getNextHighestDepth());
                c._x = P[i * 2];
                c._y = P[i * 2 + 1];
                cl[i] = c;
            }
        }
        if (cl[1] != null) cl[1]._visible = alertsOn;
        cl[0].createEmptyMovieClip("p", 0);
        if (LIST) {
            for (i = 0; i < TIERS.length; i++) hd[i] = mkHd(TS[TIERS.charAt(i)]);
        }
        if (cl[1] != null) a0 = mkAl(0);
        if (!prev) return;

        // Sample records: hl, sh and cp are left out where they would be 0 or "".
        var mobs:Array = [
            {nm: "Louhi", k: "b", st: 0, pct: 100, d: 180, hl: 1},
            {nm: "Excavator of Souls", k: "s", st: 0, pct: 72, d: 210, cp: "South West"},
            {nm: "Gurnakhi Slaver", k: "m", st: 0, pct: 72, d: 240},
            {nm: "Asshuri Sultan", k: "m", st: 0, pct: 100, d: 95},
            {nm: "Zug-Touched Monitor", k: "c", st: 0, pct: 100, d: 141}];
        if (GUARD) mobs.push({nm: "Gurnakhi Juggernaut", k: "g", st: 0, pct: 100, d: 60, sh: 1});
        paintP({anchor: 1, ally: {st: 0, pct: 87}, mobs: mobs}, getTimer(), true);
        if (cl[1] != null) setAl(a0, "Gurnakhi Slaver - 240 m", 0xF7A22B);
        var lb:Array = ["Onslaught", "Onslaught Alerts"];
        for (i = 0; i < 2; i++) {
            if (cl[i] != null) KazBarsPreview.attach({mc: cl[i], x: FX[i], y: 0, w: FW[i], h: FH[i],
                                                      label: lb[i], color: 0xF7A22B});
        }
    }

    private function unbuild():Void {
        halt();
        var i:Number = 2;
        var c:MovieClip;
        while (i--) {
            c = cl[i];
            if (c != null) {
                P[i * 2] = c._x;
                P[i * 2 + 1] = c._y;
                c.removeMovieClip();
                cl[i] = null;
            }
        }
        i = rw.length;
        while (i--) rw[i].row = null;
        rw.length = 0;
        hd.length = 0;
        ln.length = 0;
        al.length = 0;
        pu.length = 0;
        ph = 0;
    }

    public function previewOn():Void {
        previewMode = true;
        if (active) {
            unbuild();
            build(true);
        }
    }

    public function previewOff():Void {
        previewMode = false;
        unbuild();
        if (pf != null) build(false);
    }

    // =========================================================================
    // Render. The board top to bottom from a running cursor: the wave line, the
    // fatality line, the ally, the start hint, then a header and the rows of each
    // tier that has any, boss first. Lines are pooled clips with a name and a
    // value field; a row is its record's own clip.
    // =========================================================================

    private function render(now:Number):Void {
        pu.length = 0;
        paintP(scan, now, false);
        if (cl[1] != null && alertsOn) paintA(scan, now);
    }

    // A mob out of view for 20 s has no row. The scan still holds and reads it (300 s), so
    // a mob that comes back is listed again with its live HP, and no new alert.
    private function away(r:Object, now:Number):Boolean {
        return r.st == 1 && now - r.seen > 20000;
    }

    private function paintP(src:Object, now:Number, prev:Boolean):Void {
        var y:Number = PAD;
        var j:Number;
        var k:Number;
        var n:Number;
        var c:MovieClip;
        var h:MovieClip;
        var r:Object;
        var s:Object;
        var m:Array;
        var t:String;
        var v:String;
        var col:Number;
        var pct:Number;
        var f:Number;             // when the wave bar filled, 0 = not full
        if (WAVE) {
            title(line(0, y, 0), prev ? "Wave 16" : wLab, prev ? ["1:08", "Spawning 27/36", "2:12"] : waveParts(now));
            y += AH;
            // The fatality line's bar is the game meter's: gold while it fills, red once
            // full, pulsing for 3 s from the moment it filled. A sample in preview.
            c = line(1, y, FAT_H);
            y += FAT_X;
            pct = prev ? 75 : wPct;
            f = prev ? 0 : wFull;
            row(c, "Fatality", 0xC8C0B0, Math.round(pct) + "%", 0xC8C0B0);
            // Emptying after it filled is a reset: it snaps, never glides back.
            fill(c.b, pct, f ? 0xE0503C : 0xF7A22B, pct < c.b._v);
            flash(c.b, f > 0 && now - f < 3000);
        }
        if (hasAlly) {
            r = src.ally;
            pct = 0;
            v = "";
            if (r == null) {
                t = allyN + ((src.anchor >= 0 && now - src.anchorAt > 30000) ? " - target " + short() + " once" : " -");
                col = 0x7F786C;
            } else if (r.st == 2) {
                t = allyN + " has fallen";
                col = 0xE0503C;
            } else {
                t = allyN;
                v = ((r.st == 1) ? "last seen  " : "") + r.pct + "%";
                col = (r.st == 1) ? 0x7F786C : band(r.pct);
                pct = r.pct;
            }
            c = line(2, y, ALLY_H);
            y += ALLY_X;
            row(c, t, col, v, col);
            fill(c.b, pct);
            flash(c, r != null && r.st == 0 && now - r.drop < 3000);
        }
        if (src != null && src.anchor < 0) {
            row(line(3, y, 0), "Onslaught - target any NPC to start", 0x7F786C, "", 0);
            y += LINE;
        } else if (ln[3] != null) row(ln[3], "", 0, "", 0);
        if (LIST && src != null) {
            m = src.mobs;
            // A dropped record's row goes with it, and a row out of view for 20 s goes too.
            j = rw.length;
            while (j--) {
                r = rw[j];
                if (r.st == 3 || away(r, now)) {
                    r.row.removeMovieClip();
                    r.row = null;
                    rw.splice(j, 1);
                }
            }
            for (k = 0; k < TIERS.length; k++) {
                t = TIERS.charAt(k);
                s = TS[t];
                h = hd[k];
                n = 0;
                for (j = 0; j < m.length; j++) {
                    r = m[j];
                    if (r.k == t && !away(r, now)) {
                        if (n == 0) {
                            if (h._y != y) h._y = y;
                            y += SMALL_H;
                        }
                        n++;
                        c = r.row;
                        if (c == null) c = mkRec(r, s);
                        if (c._y != y) c._y = y;
                        y += s.rh;
                        item(c, r, now);
                    }
                }
                if (h._visible != (n > 0)) h._visible = (n > 0);
            }
        }
        var show:Boolean = (y > PAD);
        y += PAD;
        if (y != ph) {
            ph = y;
            plate(cl[0].p, FW[0], y);
        }
        if (cl[0]._visible != show) cl[0]._visible = show;
    }

    // Spawn alerts, the ally's low-HP alerts and the AoE line.
    private function paintA(s:KazBarsOnsScan, now:Number):Void {
        var f:Array = s.fresh;
        var r:Object = s.ally;
        var i:Number;
        var n:Number;
        var d:Number = -1;
        var k:Object;
        if (ALERTS) {
            for (i = 0; i < f.length; i++) {
                k = AL[f[i].k];
                if (k == undefined) k = AL.m;
                addAl(k.t + f[i].nm + ((f[i].d >= 0) ? " - " + f[i].d + " m" : ""), k.c, now);
            }
        }
        if (hasAlly && r != null && r.st != 2) {
            // Below 50 and below 25 fire once each, and re-arm 5 points above.
            for (i = 0; i < 2; i++) {
                n = 50 - i * 25;
                if (r.pct >= n + 5) lo[i] = false;
                else if (r.pct < n && !lo[i]) {
                    lo[i] = true;
                    addAl(short() + ((i == 0) ? " 50%" : " 25%!"), 0xE0503C, now);
                }
            }
        }
        if (hasAoe) {
            f = s.cands;
            n = f.length;
            for (i = 0; i < n; i++) {
                if (f[i].d >= 0 && (d < 0 || f[i].d < d)) d = f[i].d;
            }
            setAl(a0, (n > 0) ? "AoE x" + n + ((d >= 0) ? " - nearest " + d + " m" : "") + " - " + sec(now - s.aoeAt) + " s" : "",
                  0xE0503C);
        }
    }

    // A board line: a pooled clip made on first use, put at the cursor (y written
    // only when it moved). The fatality and ally lines carry a bar bh tall under
    // their text (0: none). The wave line (0) is the board's title, AH tall:
    // the TT fields on one bottom edge, each with its own font, weight, colour
    // and alignment (mkTitle).
    private function line(i:Number, y:Number, bh:Number):MovieClip {
        var c:MovieClip = ln[i];
        if (c == null) {
            c = (i == 0) ? mkTitle() : mkRow(cl[0], PW, FS, false, LINE);
            if (bh > 0) c.b = mkBar(c, PAD, LINE - 1, PW, bh);
            ln[i] = c;
        }
        if (c._y != y) c._y = y;
        return c;
    }

    // The title clip: the TT fields, each a row of the spec table below (font,
    // bold, colour, alignment) - the label (Title, gold), the elapsed clock
    // (Alert, bright), the phase (Body, centred), the remaining clock (Alert,
    // bright) and "left" (Body) - every one PW wide until title() lays it out.
    private function mkTitle():MovieClip {
        var d:Number = cl[0].getNextHighestDepth();
        var c:MovieClip = cl[0].createEmptyMovieClip("r" + d, d);
        var sp:Array = [[NAME_FS, true, 0xF7A22B, "left"], [ALERT_FS, true, 0xE8E2D6, "left"],
                        [FS, false, 0xC8C0B0, "center"], [ALERT_FS, true, 0xE8E2D6, "left"],
                        [FS, false, 0xC8C0B0, "left"]];
        var s:Array;
        var j:Number;
        for (j = 0; j < TT.length; j++) {
            s = sp[j];
            makeTF(c, TT[j], PAD, AH - lh(s[0]), PW, lh(s[0]), s[0], s[1], s[2], s[3]);
        }
        return c;
    }

    // The title's texts: the label, then p = [elapsed clock, phase, remaining
    // clock] (see waveParts), "left" only after a remaining clock. When any text
    // changed the fields are laid out again in two groups rd(0.5) apart: the
    // label and the elapsed clock from PAD, the remaining clock and "left"
    // ending at PAD + PW (where the bars end), and the phase centred in the gap
    // between them, clipped to it. An empty field takes no room and no gap.
    private function title(c:MovieClip, lab:String, p:Array):Void {
        var t:Array = [lab, p[0], p[1], p[2], (p[2] != "") ? "left" : ""];
        var f:TextField;
        var i:Number;
        var moved:Boolean = false;
        for (i = 0; i < TT.length; i++) {
            f = c[TT[i]];
            if (f.text != t[i]) {
                f.text = t[i];
                moved = true;
            }
        }
        if (!moved) return;
        var g:Number = rd(0.5);
        var x:Number = PAD;
        var r:Number = PAD + PW;
        var tw:Number;
        for (i = 0; i < 2; i++) {
            f = c[TT[i]];
            if (f._x != x) f._x = x;
            tw = fit(f);
            if (tw > 0) x += tw + g;
        }
        for (i = 4; i > 2; i--) {
            f = c[TT[i]];
            tw = fit(f);
            if (f._x != r - tw) f._x = r - tw;
            if (tw > 0) r -= tw + g;
        }
        f = c.n;
        tw = Math.max(0, r - x);
        if (f._x != x) f._x = x;
        if (f._width != tw) f._width = tw;
    }

    // The room a title field takes: its text with the gutters, none when empty.
    private function fit(f:TextField):Number { return (f.text != "") ? Math.round(f.textWidth) + GUT : 0; }

    // A tier's header, hidden until the tier has a row: its name, Small and bold, in the tier's colour.
    private function mkHd(s:Object):MovieClip {
        var d:Number = cl[0].getNextHighestDepth();
        var h:MovieClip = cl[0].createEmptyMovieClip("h" + d, d);
        var t:TextField = makeTF(h, "n", PAD, 0, NAME_W, SMALL_H, SMALL_FS, true, s.col, "left");
        t.text = s.hd;
        h._visible = false;
        return h;
    }

    // A mob's row: the name in its tier's size, the value in Body (a camp row's, in its own
    // Small: see mkRow), the bar under both and the heal cross after the name. Made on the
    // record's first paint, removed with the record or once the mob has been out of view for
    // 20 s (made again if it comes back), never hidden. The cross is placed once: a record's
    // name never changes.
    private function mkRec(r:Object, s:Object):MovieClip {
        var h:Number = lh(s.fs);
        var c:MovieClip = mkRow(cl[0], NAME_W, s.fs, s.bold, h);
        var a:Number = Math.max(2, Math.round(s.fs * 0.25));   // the cross's arm, its side is three of them
        var z:Number = a * 3;
        c.b = mkBar(c, PAD, h - 1, PW, s.bh);
        put(c.n, r.nm, s.col);
        var x:MovieClip = c.createEmptyMovieClip("x", c.getNextHighestDepth());
        solid(x, 0x1A1612, a - 1, -1, a + 2, z + 2);   // the dark outline: the plus grown by 1 px all round
        solid(x, 0x1A1612, -1, a - 1, z + 2, a + 2);
        solid(x, 0x7AC142, 0, a, z, a);
        solid(x, 0x7AC142, a, 0, a, z);
        x._x = Math.round(PAD + 2 + c.n.textWidth + rd(0.3));
        x._y = Math.round((h - z) / 2);
        x._visible = false;
        r.row = c;
        rw.push(r);
        return c;
    }

    // The name field spans the whole line when nw says so, so wave and hint texts
    // fit; real names stay inside NAME_W, short of the value field. The value
    // field is aligned right, its text ending where the bars end; it
    // shares the name's bottom edge: it is Body, a line box of its own (lh
    // of its size), and never larger than the row's font, so it always sits
    // inside the row — a camp row (Small) takes a Small value, a boss row
    // (Title) a Body one standing on the same bottom edge.
    private function mkRow(p:MovieClip, nw:Number, nfs:Number, bold:Boolean, h:Number):MovieClip {
        var d:Number = p.getNextHighestDepth();
        var c:MovieClip = p.createEmptyMovieClip("r" + d, d);
        var vf:Number = Math.min(FS, nfs);
        var vh:Number = lh(vf);
        makeTF(c, "n", PAD, 0, nw, h, nfs, bold, 0xC8C0B0, "left");
        makeTF(c, "v", PAD + NAME_W, Math.max(0, h - vh), VAL_W, vh, vf, false, 0xC8C0B0, "right");
        return c;
    }

    // One filled rectangle. Each bar of a shape is its own fill: two overlapping
    // bars in one fill would leave a hole where they cross.
    private function solid(m:MovieClip, col:Number, x:Number, y:Number, w:Number, h:Number):Void {
        m.beginFill(col, 100);
        rectPath(m, x, y, w, h);
        m.endFill();
    }

    // A bar's track is drawn once; the fill (returned) is redrawn only when its
    // colour changes and otherwise just scaled, gliding.
    private function mkBar(p:MovieClip, x:Number, y:Number, w:Number, h:Number):MovieClip {
        var t:MovieClip = p.createEmptyMovieClip("t", p.getNextHighestDepth());
        solid(t, 0x26211A, x, y, w, h);
        var f:MovieClip = p.createEmptyMovieClip("f", p.getNextHighestDepth());
        f._x = x;
        f._y = y;
        f._w = w;
        f._h = h;
        return f;
    }

    // The colour is the HP band of the value shown unless the caller gives one.
    private function fill(f:MovieClip, pct:Number, col:Number, snap:Boolean):Void {
        f._k = col;
        glide(f, pct, snap);
    }

    private function shown(f:MovieClip, v:Number):Void {
        var c:Number = f._k ? f._k : band(v);
        if (f._c != c) {
            f._c = c;
            f.clear();
            solid(f, c, 0, 0, f._w, f._h);
        }
        super.shown(f, v);
    }

    private function band(pct:Number):Number {
        return (pct >= 50) ? 0x7AC142 : ((pct >= 25) ? 0xF7A22B : 0xE0503C);
    }

    private function plate(mc:MovieClip, w:Number, h:Number):Void {
        chrome = mc;
        drawPlate(w, h);
    }

    private function flash(c:MovieClip, go:Boolean):Void {
        if (go) pu.push(c);
        else if (c._alpha != 100) c._alpha = 100;
    }

    private function put(t:TextField, s:String, c:Number):Void {
        if (t.text != s) t.text = s;
        if (t.textColor != c) t.textColor = c;
    }

    private function row(c:MovieClip, a:String, ac:Number, b:String, bc:Number):Void {
        put(c.n, a, ac);
        put(c.v, b, bc);
    }

    // A mob's row text: alive in full, out of view dimmed with where it was last,
    // dead in red; the bar under it takes the HP bands, light blue instead while
    // a shield buff is on a mob in view, and the cross shows while a heal buff is.
    private function item(c:MovieClip, r:Object, now:Number):Void {
        var s:Number = r.st;
        var v:String = "dead";
        var x:Boolean = (r.hl > 0 && s == 0);
        if (s == 0) v = where(r) + "  " + r.pct + "%";
        else if (s == 1) v = "last " + where(r) + " - " + sec(now - r.seen) + " s ago";
        row(c, r.nm, (s == 0) ? TS[r.k].col : 0x7F786C, v, (s == 0) ? 0xC8C0B0 : ((s == 1) ? 0x7F786C : 0xE0503C));
        fill(c.b, r.pct, (s == 0 && r.sh > 0) ? 0x8AC6FF : undefined);
        flash(c, s == 0 && now - r.drop < 3000);
        if (c.x._visible != x) c.x._visible = x;
    }

    // Where a mob is: the camp a skull stands on, else its distance.
    private function where(r:Object):String { return r.cp ? r.cp : dm(r.d); }
    private function dm(d:Number):String { return (d >= 0) ? d + " m" : ""; }
    private function sec(ms:Number):Number { return Math.floor(ms / 1000); }
    private function short():String { return allyN.substr(allyN.lastIndexOf(" ") + 1); }

    // =========================================================================
    // Alerts: up to three lines under the AoE line, newest first, each a clip
    // with a shadow and a text field centred on the anchor.
    // =========================================================================

    private function mkAl(y:Number):MovieClip {
        var d:Number = cl[1].getNextHighestDepth();
        var m:MovieClip = cl[1].createEmptyMovieClip("a" + d, d);
        m._y = y;
        makeTF(m, "s", FX[1] + 1, 1, AW, ALH, ALF, true, 0, "center");
        makeTF(m, "t", FX[1], 0, AW, ALH, ALF, true, 0xF7A22B, "center");
        return m;
    }

    private function setAl(m:MovieClip, s:String, c:Number):Void {
        put(m.s, s, 0);
        put(m.t, s, c);
    }

    private function addAl(s:String, c:Number, now:Number):Void {
        if (al.length == 3) al.pop().mc.removeMovieClip();
        al.unshift({mc: mkAl(0), t: now});
        setAl(al[0].mc, s, c);
        var i:Number = al.length;
        while (i--) al[i].mc._y = (i + 1) * ALH;
    }

    // =========================================================================
    // Wave timer: the game's wave widget, read from the scry messages, plus a
    // clock. It starts when the widget goes active and stops when it goes back
    // inactive whatever its text. The wave's number is not counted: the game's
    // own meter shows the message's text field beside its wave header, and any
    // message that carries one sets the label (shown as it came; measured in
    // game, a run can start at any wave). A stop's text is built, and no label is
    // taken while it shows, so it names the wave that ended. The fatality
    // line's bar is the game meter's: currentCount over maxCount of the latest
    // message (measured in game, 0 to the total while spawning, held through the
    // enemies and the boss, 0 again at the loot), clamped. Full is red and
    // pulses from the message that filled it. A Defeat freezes the line until
    // the meter goes active again with another phase: that is a restart in the
    // same instance, and the wave state resets, the clock starts and the scan
    // purges as at a won wave.
    // =========================================================================

    // The wave state of a fresh instance (and of a restart).
    private function wReset():Void {
        wPrev = "";
        wLab = "";
        wPct = 0;
        wFull = 0;
        wClock = false;
        wFinal = "";
        wDone = false;
        lo = [false, false];
    }

    // "0", not "": the restart's own active message starts the clock ("" is
    // entering mid-wave, which has none).
    private function restart():Void {
        wReset();
        wPrev = "0";
        if (scan != null) scan.clearWave();
    }

    private function onScry(m:Object):Void {
        var t:String = m.messageText;
        if (m.messageType != "FormatScryProgress" || t.substr(0, 16) != "OnslaughtStatus_") return;
        var phase:String = t.substr(16);
        var a:Boolean = (m.active == "1");
        if (wDone) {
            if (!a || phase == "Defeat") return;
            restart();
        }
        var now:Number = getTimer();
        var cn:Number = Number(m.currentCount);
        var mx:Number = Number(m.maxCount);
        var e:String;
        if (a) {
            if (wPrev == "0") {
                wClock = true;
                wStart = now;
                wFinal = "";
            }
            wPh = phase;
            wCount = cn;
            wMax = mx;
            wParam = m.messageTextParam;
        } else if (wPrev == "1") {
            e = wClock ? mmss(now - wStart) : "";
            if (phase == "Defeat") {
                wDone = true;
                wFinal = "Defeat" + ((e != "") ? " at " + e : "");
            } else {
                wFinal = "cleared" + ((e != "") ? " in " + e : "") + " - " + pf.start;
                if (scan != null) scan.clearWave();   // the wave is won: what the game never reported dead goes now
            }
            wClock = false;
        }
        wPrev = a ? "1" : "0";
        if (m.text && wFinal == "") wLab = "Wave " + m.text;
        wPct = (mx > 0 && cn > 0) ? Math.min(100, cn * 100 / mx) : 0;
        if (wPct < 100) wFull = 0;
        else if (!wFull) wFull = now;
    }

    // The title's texts after its label (wLab): [elapsed clock, phase, remaining
    // clock], "" where there is none. A stop's text, built before its own
    // message's text is taken, goes with the label of the wave that ended.
    private function waveParts(now:Number):Array {
        if (wFinal != "") return ["", wFinal, ""];
        if (wPrev != "1") return ["", "start: " + pf.start, ""];
        var s:String = wClock ? mmss(now - wStart) : "";
        if (wPh == "Spawning") {
            return [s, "Spawning " + wCount + "/" + wMax,
                    wClock ? mmss(Math.max(0, pf.spawnMs - (now - wStart))) : ""];
        }
        return [s, (wPh.substr(0, 16) == "EnemiesRemaining") ? "Enemies left " + (wParam ? wParam : 1) : wPh, ""];
    }

    private function mmss(ms:Number):String {
        var s:Number = sec(ms);
        return Math.floor(s / 60) + ((s % 60 < 10) ? ":0" : ":") + (s % 60);
    }

    // =========================================================================
    // Persistence (module config archive). The anchor positions are read from
    // the clips when they exist (preview exit saves before previewOff), else
    // from the stored numbers.
    // =========================================================================

    public function loadState(config:Object):Void {
        if (config == null) return;
        var i:Number;
        var k:String;
        var x:Object;
        var y:Object;
        for (i = 0; i < 2; i++) {
            k = "on" + "pa".charAt(i);
            x = config.FindEntry(k + "x");
            y = config.FindEntry(k + "y");
            if (x !== undefined && y !== undefined) {
                // The alerts anchor is its text's centre, so its footprint
                // starts left of the origin (FX), as the cast timer's does.
                P[i * 2] = KazBarsPanel.clampPos(Number(x) + FX[i], FW[i], true) - FX[i];
                P[i * 2 + 1] = KazBarsPanel.clampPos(Number(y), FH[i], false);
                if (cl[i] != null) {
                    cl[i]._x = P[i * 2];
                    cl[i]._y = P[i * 2 + 1];
                }
            }
        }
        x = config.FindEntry("onav");
        if (x !== undefined) setAlerts(x == 1);
        x = config.FindEntry("onv");
        if (x !== undefined) setActive(x == 1);
    }

    public function saveState(config:Object):Void {
        if (config == null) return;
        var i:Number;
        var k:String;
        var c:MovieClip;
        for (i = 0; i < 2; i++) {
            k = "on" + "pa".charAt(i);
            c = cl[i];
            config.ReplaceEntry(k + "x", (c != null) ? c._x : P[i * 2]);
            config.ReplaceEntry(k + "y", (c != null) ? c._y : P[i * 2 + 1]);
        }
        config.ReplaceEntry("onv", active ? 1 : 0);
        config.ReplaceEntry("onav", alertsOn ? 1 : 0);
    }
}
