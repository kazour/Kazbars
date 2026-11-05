// KazBarsPreview.as - The preview skin every HUD element is positioned by:
// a tinted rect over its footprint, its name and Stage-clamped drag (no
// coordinate readout: nothing types a position in). One shell for grids, cast timers, the inspect panel and
// the onslaught tracker, so they drag alike and read alike.
//
// The caller describes its footprint relative to its OWN clip's anchor, which
// is what lets a grid (anchored top-left) and a cast timer (anchored on the
// centre of its text) share the clamp: the drag bounds are the rect, expressed
// as the distance from the anchor to each edge.
//
// The skin is removed on exit, never hidden — a HUD element is mouse
// transparent in normal play, and a hidden overlay would still take the click.
//
// Stateless, so every entry point is static: the core, the cast timer, the
// inspect panel and the onslaught tracker call the class, and nothing holds an
// instance.
//
// Its labels are set from the shared panel size (d.PF.fontSize), the one
// KazBarsPreviewPanel is configured with, on the panels' scale (see
// KazBarsPanel): the name is the Title role, its field lh() of its size tall.
class KazBarsPreview {
    private static var PF:Number = 12;   // until the control panel hands over the real one

    // KazBarsPreviewPanel.configure() calls this with the shared panel size.
    public static function setFontSize(pf:Number):Void {
        PF = pf;
    }

    // The face every KazBars text field asks for: "Arial" (embedded in the SWF) or
    // the game's own "_StandardFont". KazBarsPreviewPanel.configure() sets it from
    // d.PF before any other module makes a field.
    public static var FACE:String = "Arial";

    public static function setFace(face:String):Void {
        FACE = face;
    }

    private static function nameFS():Number {
        return KazBarsPanel.roleFS(PF, 1.25);
    }

    // The label's gap to the footprint's edge.
    private static function edge():Number {
        return Math.round(PF / 3);
    }

    // What a footprint that FRAMES an element needs above and below it, for the
    // name to sit clear of it (the cast timer's, whose footprint is the text
    // plus these).
    public static function roomAbove():Number {
        return edge() * 2 + KazBarsPanel.lh(nameFS());
    }

    public static function roomBelow():Number {
        return edge();
    }

    // Grid entry point: the footprint falls out of the grid's own geometry,
    // and a one-column bar takes the narrow layout.
    public static function createOverlay(obj:Object):Void {
        var cfg:Object = obj.cfg;
        var step:Number = cfg.iconSize + cfg.gap;
        attach({mc: obj.mc,
                x: 0, y: 0,
                w: cfg.cols * step - cfg.gap,
                h: cfg.rows * step - cfg.gap,
                label: cfg.id,
                color: (cfg.type == "player") ? 0x0066FF : 0xFF0066,
                vertical: (cfg.cols == 1 && cfg.rows > 1)});
    }

    // spec: {mc, x, y, w, h, label, color, vertical}
    public static function attach(spec:Object):Void {
        var mc:MovieClip = spec.mc;
        if (mc == null) return;
        detach(mc);
        var x:Number = Number(spec.x);
        var y:Number = Number(spec.y);
        var w:Number = Number(spec.w);
        var h:Number = Number(spec.h);

        // Topmost by depth, and it has to stay that way: anything the element
        // adds to its own clip at getNextHighestDepth() AFTER this point draws
        // over the frame. Grid slots keep a fixed depth across
        // a type swap for exactly this reason (KazBarsGridView.slot).
        var ov:MovieClip = mc.createEmptyMovieClip("_kbOv", mc.getNextHighestDepth());
        ov.lineStyle(2, 0xFFFFFF, 80);
        ov.beginFill(Number(spec.color), 20);
        // Outset by 2, so the frame reads as a border around the footprint
        // rather than a line drawn through its outermost pixels.
        ov.moveTo(x - 2, y - 2);
        ov.lineTo(x + w + 2, y - 2);
        ov.lineTo(x + w + 2, y + h + 2);
        ov.lineTo(x - 2, y + h + 2);
        ov.lineTo(x - 2, y - 2);
        ov.endFill();

        // The name on the Title role, a line box (lh) tall, an edge below the
        // footprint's top.
        var nfs:Number = nameFS();
        var nh:Number = KazBarsPanel.lh(nfs);
        var m:Number = edge();
        if (spec.vertical == true) {
            // A one-column bar is narrower than a horizontal label, which would
            // hang most of its length out over the play area: the label runs
            // down it.
            var vl:TextField = makeTF(ov, "lbl", x, y, h, nh, nfs, 0xFFFFFF);
            // The only field sized to something other than its text: it is
            // as long as the bar so the rotated label centres ALONG it, and
            // growing to fit would pin it to the top instead. Switching
            // autoSize off keeps whatever size the field has by then — on an
            // empty field, the gutters — so the box is set again by hand.
            vl.autoSize = "none";
            vl._width = h;
            vl._height = nh;
            vl.text = String(spec.label);
            vl._rotation = 90;
            vl._x = x + (w / 2) - Math.round(PF * 0.75);
            vl._y = y + m;
        } else {
            var hl:TextField = makeTF(ov, "lbl", x, y + m, w, nh, nfs, 0xFFFFFF);
            hl.text = String(spec.label);
        }

        ov._x0 = x; ov._y0 = y; ov._w = w; ov._h = h;
        ov.useHandCursor = true;
        // Bounds are read at press, not at creation: the rect is the anchor's
        // distance to each edge, and the Stage can be resized between the two.
        ov.onPress = function() {
            // Floored against the near edge: an element taller or wider than
            // the Stage would otherwise hand startDrag a rect whose far edge
            // sits behind its near one, and the drag throws the element off
            // screen with no overlay left on screen to bring it back.
            var s:Object = KazBarsPanel.stage();
            var l:Number = s.x - this._x0;
            var t:Number = s.y - this._y0;
            this._parent.startDrag(false, l, t,
                                   Math.max(l, s.x + s.w - (this._x0 + this._w)),
                                   Math.max(t, s.y + s.h - (this._y0 + this._h)));
        };
        ov.onRelease = ov.onReleaseOutside = function() { this._parent.stopDrag(); };
        mc._kbOv = ov;
    }

    public static function detach(mc:MovieClip):Void {
        if (mc == null) return;
        if (mc._kbOv != null) {
            mc._kbOv.removeMovieClip();
            mc._kbOv = null;
        }
    }

    private static function makeTF(ov:MovieClip, id:String, x:Number, y:Number, w:Number,
                                   h:Number, size:Number, col:Number):TextField {
        var tf:TextField = ov.createTextField(id, ov.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        // Centred on the footprint and free to grow past its edges: a
        // two-column grid is narrower than most names.
        tf.autoSize = "center";
        tf.embedFonts = false;
        tf.textColor = col;
        var fmt:TextFormat = new TextFormat();
        fmt.font = KazBarsPreview.FACE;
        fmt.size = size;
        fmt.bold = true;
        fmt.align = "center";
        tf.setNewTextFormat(fmt);
        return tf;
    }
}
