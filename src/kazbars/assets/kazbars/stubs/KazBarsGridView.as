// KazBarsGridView.as - One grid on screen: its clip, its slots, their icons, timers and flashing. Screen grids
// (KazBarsGrids), and overhead grids (KazBarsOverhead) each own views; a view never reads the game
// itself: show(list) draws what its owner picked (KazBarsGridPick), tick(now) runs timers and flashing. A slot is made
// the first time something is drawn in it (fill() makes them all, for preview) and kept; every write is on change.
// A box (fillDir LR..BR-TL) places slot i once, by its shape; a band (fillDir "C": an overhead dynamic grid) places
// what it shows after each show(), cols to a row from the bottom, each row centred on the band, at most maxSlots,
// and its W and H follow (band()): its owner reads them after show().
//
// A slot: the authored BuffSlot / DebuffSlot / MiscSlot art scaled iconSize / 64, at depth = its index (so the preview
// overlay, attached on top, stays on top through a type swap), the baked custom icon at depth 8 beside the masked
// m_icon (Scaleform paints nothing attached inside it), the art's ring at depth 9, the text at depths 10-13 (the bar
// timer at 10, where the digits would be). Kept on
// the slot: _slotType, _buff (its entry), _lastIco (the icon shown or on its way), _lastSec (the digits shown, or the
// bar's percent), _stk, _c (timer colour), _a (alpha).
class KazBarsGridView {
    public var mc:MovieClip;
    public var cfg:Object;
    public var shown:Boolean;     // the owner's: the control panel's check, or in view
    public var stale:Boolean;     // the owner's: redraw when it shows again
    public var n:Number;          // entries drawn by the last show()
    public var W:Number;          // the footprint
    public var H:Number;
    private var d:Object;         // the baked data: CUSTOMICON, WL (this grid's ids -> fact codes, KazBarsGridPick)
    private var sl:Array;         // the slots made so far
    private var ld:Array;         // a MovieClipLoader each
    private var K:Number;         // native pixels per screen pixel, for the text
    private static var NATIVE_SIZE:Number = 64;
    private static var Q:Object;  // icon -> {t asked, l the slots waiting {v view, i index}}, every view's

    public function KazBarsGridView(parent:MovieClip, name:String, c:Object, data:Object) {
        cfg = c;
        d = data;
        shown = true;
        n = 0;
        sl = [];
        ld = [];
        K = NATIVE_SIZE / c.iconSize;
        W = c.cols * (c.iconSize + c.gap) - c.gap;
        H = c.rows * (c.iconSize + c.gap) - c.gap;
        mc = parent.createEmptyMovieClip(name, parent.getNextHighestDepth());
        mc._x = c.x;
        mc._y = c.y;
        mc._visible = false;
    }

    // l: entries in slot order (null: an empty slot); past the grid's size (a band's maxSlots) is cut.
    public function show(l:Array):Void {
        var t:Number = (cfg.maxSlots > 0) ? cfg.maxSlots : cfg.rows * cfg.cols;
        var m:Number = (l.length < t) ? l.length : t;
        var i:Number;
        n = 0;
        for (i = 0; i < m; i++) {
            if (l[i] != null) {
                draw(i, l[i]);
                n++;
            } else hide(sl[i]);
        }
        for (i = m; i < sl.length; i++) hide(sl[i]);
        if (cfg.fillDir == "C") band(n);
    }

    // A band of n shown slots (a dynamic pick has no gaps, so they are the first n): cfg.cols to a row (the row
    // cap), rows from the bottom, each row centred on the band; W is the widest row, H the rows, so the owner's
    // top-left placement keeps the bottom edge put as rows come and go.
    private function band(n:Number):Void {
        var c:Object = cfg;
        var st:Number = c.iconSize + c.gap;
        var rows:Number = Math.ceil(n / c.cols);
        W = (n > 0) ? ((n < c.cols) ? n : c.cols) * st - c.gap : 0;
        H = (n > 0) ? rows * st - c.gap : 0;
        var i:Number;
        var r:Number;
        var rw:Number;
        var s:MovieClip;
        for (i = 0; i < n; i++) {
            s = sl[i];
            r = Math.floor(i / c.cols);
            rw = n - r * c.cols;
            if (rw > c.cols) rw = c.cols;
            s._x = W / 2 + (i % c.cols - (rw - 1) / 2) * st - c.iconSize / 2;
            s._y = (rows - 1 - r) * st;
        }
    }

    // Timers (digits: whole seconds; bar: the percent of the entry's total left, drawBar from the left edge) and
    // flashing (every 3rd frame). Red under the threshold either way; the bar's colour through a Color on change.
    public function tick(now:Number):Void {
        var th:Number = cfg.timerFlashThreshold * 1000;
        var i:Number;
        var s:MovieClip;
        var e:Object;
        var r:Number;
        var x:Number;
        var g:MovieClip;
        var col:Color;
        for (i = 0; i < sl.length; i++) {
            s = sl[i];
            e = s._buff;
            if (e == null || !s._visible) continue;
            r = (e.exp > 0) ? e.exp - now : 0;
            if (r < 0) r = 0;
            if (s.tmr != null) {
                x = Math.floor(r / 1000);
                if (s._lastSec != x) {
                    s._lastSec = x;
                    s.tmr.text = s.tmrShadow.text = (r > 0) ? String(x) : "";
                }
                x = (r > 0 && r <= th) ? 0xFF3333 : 0xFFFFFF;
                if (s._c != x) {
                    s._c = x;
                    s.tmr.textColor = x;
                }
            } else if (s.bar != null) {
                x = (e.tot > 0 && r > 0) ? Math.ceil(r / e.tot * 100) : 0;
                if (x > 100) x = 100;
                if (s._lastSec != x) {
                    s._lastSec = x;
                    if (x > 0) drawBar(s.bar, x);
                    s.bar._visible = x > 0;
                }
                x = (r > 0 && r <= th) ? 0xFF3333 : 0xFFFFFF;
                if (s._c != x) {
                    s._c = x;
                    col = new Color(s.bar);
                    col.setRGB(x);
                }
            }
            x = (cfg.enableFlashing && r > 0 && r <= th) ? 33 + (Math.sin(Math.floor((now % 1000) / 10) * 0.0628318) + 1) * 33.5 : 100;
            if (s._a != x) {
                s._a = x;
                g = (s.cust != null) ? s.cust : s.m_icon;
                g._alpha = x;
            }
        }
    }

    // Sub-pixel, in twips: whole pixels made a slowly moving overhead grid step 1 px every other frame.
    public function to(x:Number, y:Number):Void {
        x = Math.round(x * 20) / 20;
        y = Math.round(y * 20) / 20;
        if (mc._x != x) mc._x = x;
        if (mc._y != y) mc._y = y;
    }

    // Preview: every slot made and shown (a band's maxSlots), empty ones as bare art, a bar timer at two thirds.
    public function fill():Void {
        var i:Number;
        var s:MovieClip;
        var t:Number = (cfg.maxSlots > 0) ? cfg.maxSlots : cfg.rows * cfg.cols;
        for (i = 0; i < t; i++) {
            s = slot(i, (sl[i] != null) ? sl[i]._slotType : "BuffSlot");
            s._visible = true;
            if (s.bar != null) {
                drawBar(s.bar, 67);
                s.bar._visible = true;
            }
        }
        if (cfg.fillDir == "C") band(t);
    }

    // Back to the pool: the view hidden, every slot hidden and emptied, the clips kept.
    public function reset():Void {
        var i:Number;
        for (i = 0; i < sl.length; i++) hide(sl[i]);
        n = 0;
        shown = false;
        stale = false;
        mc._visible = false;
    }

    public function free():Void {
        var i:Number;
        for (i = 0; i < ld.length; i++) ld[i].removeListener(this);
        ld.length = 0;
        sl.length = 0;
        mc.removeMovieClip();
    }

    // =========================================================================
    // Slots
    // =========================================================================

    private function draw(i:Number, e:Object):Void {
        var f:Number = d.WL[cfg.id][e.id];
        var s:MovieClip = slot(i, ((f & 3) == 3) ? "MiscSlot" : (((f & 3) == 2) ? "DebuffSlot" : "BuffSlot"));
        if (!s._visible) s._visible = true;
        s._buff = e;
        var k:Number = f >> 2 & 1023;
        var t:String = (k > 0) ? "x" + String(k) : "";

        if (s._stk != t) {
            s._stk = t;
            s.stk.text = s.stkShadow.text = t;
        }
        icon(i, s, e);
    }

    private function hide(s:MovieClip):Void {
        if (s == null || !s._visible) return;
        s._visible = false;
        s._buff = null;
        s._lastIco = null;
        s._lastSec = null;
        s._stk = null;
        s.tmr.text = s.tmrShadow.text = s.stk.text = s.stkShadow.text = "";
        if (s.bar != null) s.bar._visible = false;
        clear(s, false);
    }

    // Slot i as this type: made the first time, re-made at its own depth on a type change.
    private function slot(i:Number, type:String):MovieClip {
        var s:MovieClip = sl[i];
        if (s._slotType == type) return s;
        if (s != null) s.removeMovieClip();
        s = mc.attachMovie(type, "s" + i, i);
        if (s == null) {
            s = mc.createEmptyMovieClip("s" + i, i);
            s.createEmptyMovieClip("m_icon", 0);
        }
        s._xscale = s._yscale = (cfg.iconSize / NATIVE_SIZE) * 100;
        if (cfg.fillDir != "C") place(s, i);
        createTexts(s);
        s._slotType = type;
        s._visible = false;
        sl[i] = s;
        if (ld[i] == null) {
            ld[i] = new MovieClipLoader();
            ld[i].addListener(this);
        }
        return s;
    }

    // Where a box's slot i goes, by the fill direction (the pane's preview mirrors this; a band's is band()).
    private function place(s:MovieClip, i:Number):Void {
        var c:Object = cfg;
        var f:String = c.fillDir;
        var r:Number = Math.floor(i / c.cols);
        var k:Number = i % c.cols;
        if (c.rows == 1) {
            r = 0;
            if (f == "RL") k = c.cols - 1 - i;
        } else if (c.cols == 1) {
            k = 0;
            r = (f == "BT") ? c.rows - 1 - i : i;
        } else {
            if (f == "TR-BL" || f == "BR-TL") k = c.cols - 1 - k;
            if (f == "BL-TR" || f == "BR-TL") r = c.rows - 1 - r;
        }
        s._x = k * (c.iconSize + c.gap);
        s._y = r * (c.iconSize + c.gap);
    }

    // =========================================================================
    // Text: the stack counter and the timer. Nothing below floors or caps a size: the generator's overlay_size did.
    // =========================================================================

    // The bar at p percent, in the slot art's native px: a strip a twelfth of the icon high (2 px or more) along the
    // inside of the ring's bottom edge, its ends on the ring's inner curve, cut at p percent of the width from the
    // left. The ring (base.swf's slot art, a 5 px stroke) leaves x 7.5..56.5 inside it, its bottom at 56.4 and its
    // inner corner radius 7.25. Redrawn on a percent change only, so the corners never stretch as it shrinks.
    private function drawBar(b:MovieClip, p:Number):Void {
        var h:Number = b.bh;
        var e:Number = 7.5 + 0.49 * p;
        var y:Number;
        var w:Number;
        var i:Number;
        b.clear();
        b.beginFill(0xFFFFFF, 90);
        // Down the left end, then back up the right: five levels, each end cut by the corner it is in.
        for (i = 0; i < 10; i++) {
            y = 56.4 - h + h * ((i < 5) ? i : 9 - i) / 4;
            w = y - 49.15;
            w = (w > 0) ? 7.25 - Math.sqrt(Math.max(0, 52.5625 - w * w)) : 0;
            w = (i < 5) ? 7.5 + w : Math.max(7.5 + w, Math.min(56.5 - w, e));
            if (i == 0) b.moveTo(w, y);
            else b.lineTo(w, y);
        }
        b.endFill();
    }

    // One bold text field (a main one or its shadow) at a fixed depth. x, y, w (px) and size (pt) are ON SCREEN; the
    // slot clip is scaled by 1 / K and text is not, so the field is made K times each in the clip's native pixels, the
    // size rounded to a whole native point. Its height is one line box of the native size, ceil(1.2 n) + 4.
    private function mkTF(s:MovieClip, id:String, depth:Number, x:Number, y:Number,
                          w:Number, size:Number, col:Number, align:String):Void {
        var n:Number = Math.round(size * K);
        var tf:TextField = s.createTextField(id, depth, x * K, y * K, w * K, Math.ceil(n * 6 / 5) + 4);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.textColor = col;
        var fmt:TextFormat = new TextFormat();
        fmt.font = KazBarsPreview.FACE;
        fmt.size = n;
        fmt.bold = true;
        fmt.align = align;
        tf.setNewTextFormat(fmt);
    }

    // cfg.iconSize, cfg.stackFont and cfg.timerFont are on-screen values baked by the generator's overlay_size.grid_metrics.
    // The stack counter ("x3") sits ins px in from the icon's top and right, ins scaling with the icon (overlay_size.inset:
    // 4 at 48 px), its field wide enough for "x" and three digits; the timer digits are centred, their box ending at
    // the icon's bottom plus timerYOffset, then kept inside the icon and clear of the stack counter when its box fits
    // there; the shadow is one screen pixel. The bar timer (cfg.timerStyle "bar") is a sibling of the icon at depth
    // 10 (never inside the masked m_icon; 9 is the art's ring), drawn by drawBar; it keeps its height in native px.
    private function createTexts(s:MovieClip):Void {
        var sz:Number = cfg.iconSize;
        var ins:Number = Math.max(2, Math.round(sz / 12));

        var sp:Number = cfg.stackFont;
        var sH:Number = Math.ceil(sp * 6 / 5) + 4;
        var sW:Number = Math.ceil(sp * 2.2264) + 4;
        var sX:Number = sz - sW - ins;
        mkTF(s, "stkShadow", 12, sX + 1, ins + 1, sW, sp, 0x000000, "right");
        mkTF(s, "stk", 13, sX, ins, sW, sp, 0xFFFFFF, "right");
        if (cfg.timerStyle == "bar") {
            var b:MovieClip = s.createEmptyMovieClip("bar", 10);
            b.bh = Math.max(2, Math.round(sz / 12)) * K;
            b._visible = false;
            return;
        }
        if (cfg.timerStyle != "digits") return;

        // The widest timer is a four-digit seconds count (Arial Bold digits, 0.5566 em).
        var tp:Number = cfg.timerFont;
        var tH:Number = Math.ceil(tp * 6 / 5) + 4;
        var tW:Number = Math.max(sz, Math.ceil(tp * 2.2264) + 4);
        var tX:Number = (sz - tW) / 2;
        var tY:Number = sz - 4 - tp + cfg.timerYOffset;
        if (tH <= sz - ins - sH) tY = Math.max(Math.min(tY, sz - tH), ins + sH);
        mkTF(s, "tmrShadow", 10, tX + 1, tY + 1, tW, tp, 0x000000, "center");
        mkTF(s, "tmr", 11, tX, tY, tW, tp, 0xFFFFFF, "center");
    }

    // =========================================================================
    // Icons: the baked CUSTOMICON symbol, IcoNull when the effect has no icon or its load failed, else the RDB image.
    // A slot already showing an icon, or waiting for it, is never asked again. The client never answers a request for
    // an icon already in flight (KazBarsInspect found it), and two loads of one URL in one frame crash it, so one
    // request per icon is in flight across every view: other slots wanting it queue, and each answer asks again for
    // the next (one clip per answer). A request unanswered for 5 s counts as lost.
    // =========================================================================

    private function icon(i:Number, s:MovieClip, e:Object):Void {
        var sym:String = d.CUSTOMICON[e.id];
        var q:Number = e.ico;
        if (sym == null && !(q > 0)) sym = "IcoNull";

        if (sym != null) {
            baked(s, sym);
            return;
        }
        if (s._lastIco == q) return;
        s._lastIco = q;
        clear(s, false);
        if (Q == null) Q = {};
        var r:Object = Q[q];
        var now:Number = getTimer();
        if (r != null && now - r.t < 5000) {
            r.l.push({v: this, i: i});
            return;
        }
        if (r == null) Q[q] = {t: now, l: []};
        else r.t = now;
        ask(this, i, q);
    }

    private static function ask(v:KazBarsGridView, i:Number, q:Number):Void {
        try {
            com.Utils.ImageLoader.RequestRDBImage(new com.Utils.ID32(1010008, q), cb(v, i, q), "f");
        } catch (x) {
            v.loaded(i, q, null, false);
            next(q);
        }
    }

    // The next queued slot still wanting icon q is asked for (the icon is out of flight now); none left, q is done.
    public static function next(q:Number):Void {
        var r:Object = Q[q];
        if (r == null) return;
        var l:Array = r.l;
        var w:Object;
        while (l.length > 0) {
            w = l.shift();
            if (w.v.wants(w.i, q)) {
                r.t = getTimer();
                ask(w.v, w.i, q);
                return;
            }
        }
        delete Q[q];
    }

    public function wants(i:Number, q:Number):Boolean {
        var s:MovieClip = sl[i];
        return s != null && s._buff != null && s._lastIco == q;
    }

    private function baked(s:MovieClip, sym:String):Void {
        if (s._lastIco == sym && s.cust != null) return;
        s._lastIco = sym;
        clear(s, true);
        s.attachMovie(sym, "cust", 8);
    }

    // The slot's icon gone, the loaded image and the baked symbol alike; m_icon left visible or not.
    private function clear(s:MovieClip, vis:Boolean):Void {
        s._a = null;
        if (s.cust != null) s.cust.removeMovieClip();
        s.m_icon._visible = vis;
        try { s.m_icon.unloadMovie(); } catch (x) {}
    }

    // One callback per request, carrying the icon asked for: a late answer for an icon the slot has moved on from is
    // dropped, and the next slot queued for the icon is asked for. A function of its own so that only its own locals
    // are closure-captured.
    private static function cb(v:KazBarsGridView, i:Number, q:Number):Object {
        return {f: function(url:String, ok:Boolean):Void {
            v.loaded(i, q, url, ok);
            KazBarsGridView.next(q);
        }};
    }

    public function loaded(i:Number, q:Number, url:String, ok:Boolean):Void {
        var s:MovieClip = sl[i];
        if (s == null || s._buff == null || s._lastIco != q) return;
        if (ok && url != null && url.length > 0) {
            try { ld[i].loadClip(url, s.m_icon); } catch (x) {}
        } else baked(s, "IcoNull");
    }

    // The loaders' listener: the image at the art's native 64 px, cached as a bitmap.
    public function onLoadInit(m:MovieClip):Void {
        if (m == null) return;
        try {
            if (!m._parent._visible) return;
            m._xscale = m._yscale = 100;
            m._xscale = m._yscale = (NATIVE_SIZE * 100) / Math.max(m._width, m._height);
            m.cacheAsBitmap = true;
            m._visible = true;
        } catch (x) {
            m._xscale = m._yscale = 100;
            m._visible = true;
        }
    }

    public function onLoadError(m:MovieClip):Void {
        if (m._parent._buff != null) baked(m._parent, "IcoNull");
    }
}
