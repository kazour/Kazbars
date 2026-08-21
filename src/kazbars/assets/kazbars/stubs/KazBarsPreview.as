// KazBarsPreview.as - The preview skin every HUD element is positioned by:
// a tinted rect over its footprint, its name, a live coordinate readout and
// Stage-clamped drag. One shell for grids, cast timers and the inspect panel,
// so they drag alike and read alike.
//
// The caller describes its footprint relative to its OWN clip's anchor, which
// is what lets a grid (anchored top-left) and a cast timer (anchored on the
// centre of its text) share the clamp: the drag bounds are the rect, expressed
// as the distance from the anchor to each edge.
//
// The skin is removed on exit, never hidden — a HUD element is mouse
// transparent in normal play, and a hidden overlay would still take the click.
//
// Stateless, so every entry point is static: the core, the cast timer and the
// inspect panel call the class, and nothing holds an instance.
class KazBarsPreview {
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
        // over the frame and the readout. Grid slots keep a fixed depth across
        // a type swap for exactly this reason (KazBarsSlot.swapType).
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

        if (spec.vertical == true) {
            // A one-column bar is narrower than a horizontal label or a
            // one-line "X:n Y:n", and either would hang most of its length
            // out over the play area: the label runs down it, the coords
            // stack.
            var vl:TextField = makeTF(ov, "lbl", x, y, h, 22, 14, 0xFFFFFF);
            // The only field sized to something other than its text: it is
            // as long as the bar so the rotated label centres ALONG it, and
            // growing to fit would pin it to the top instead. Switching
            // autoSize off keeps whatever size the field has by then — on an
            // empty field, the gutters — so the box is set again by hand.
            vl.autoSize = "none";
            vl._width = h;
            vl._height = 22;
            vl.text = String(spec.label);
            vl._rotation = 90;
            vl._x = x + (w / 2) - 9;
            vl._y = y + 5;
            ov._xc = makeTF(ov, "xc", x, y + h - 30, w, 14, 10, 0xFFFF00);
            ov._yc = makeTF(ov, "yc", x, y + h - 18, w, 14, 10, 0xFFFF00);
        } else {
            var hl:TextField = makeTF(ov, "lbl", x, y + 4, w, 18, 14, 0xFFFFFF);
            hl.text = String(spec.label);
            ov._xc = makeTF(ov, "xc", x, y + h - 18, w, 14, 11, 0xFFFF00);
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
            var l:Number = -this._x0;
            var t:Number = -this._y0;
            this._parent.startDrag(false, l, t,
                                   Math.max(l, Stage.width - (this._x0 + this._w)),
                                   Math.max(t, Stage.height - (this._y0 + this._h)));
            this.onMouseMove = function() { KazBarsPreview.updCoords(this); };
        };
        ov.onRelease = ov.onReleaseOutside = function() {
            this._parent.stopDrag();
            delete this.onMouseMove;
            KazBarsPreview.updCoords(this);
        };
        mc._kbOv = ov;
        updCoords(ov);
    }

    public static function detach(mc:MovieClip):Void {
        if (mc == null) return;
        if (mc._kbOv != null) {
            mc._kbOv.removeMovieClip();
            mc._kbOv = null;
        }
    }

    // Assigns text only: the format was set once at creation, so a drag does
    // not allocate a TextFormat per mouse move.
    public static function updCoords(ov:MovieClip):Void {
        if (ov == null) return;
        var px:Number = Math.round(ov._parent._x);
        var py:Number = Math.round(ov._parent._y);
        if (ov._yc != null) {
            ov._xc.text = "X:" + px;
            ov._yc.text = "Y:" + py;
        } else if (ov._xc != null) {
            ov._xc.text = "X:" + px + " Y:" + py;
        }
    }

    private static function makeTF(ov:MovieClip, id:String, x:Number, y:Number, w:Number,
                                   h:Number, size:Number, col:Number):TextField {
        var tf:TextField = ov.createTextField(id, ov.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        // Centred on the footprint and free to grow past its edges: a
        // two-column grid is narrower than "X:-1234 Y:-1234", and the readout
        // is the number that gets typed back into the dialog.
        tf.autoSize = "center";
        tf.embedFonts = false;
        tf.textColor = col;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = true;
        fmt.align = "center";
        tf.setNewTextFormat(fmt);
        return tf;
    }
}
