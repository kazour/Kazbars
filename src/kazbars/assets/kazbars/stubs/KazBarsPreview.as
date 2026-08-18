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
class KazBarsPreview {
    private var rootClip:MovieClip;

    public function KazBarsPreview(root:MovieClip) {
        rootClip = root;
    }

    // Grid entry points: the footprint falls out of the grid's own geometry,
    // and a one-column bar takes the narrow layout.
    public function createOverlay(obj:Object):Void {
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

    public function removeOverlay(obj:Object):Void {
        detach(obj.mc);
    }

    // spec: {mc, x, y, w, h, label, color, vertical}
    public function attach(spec:Object):Void {
        var mc:MovieClip = spec.mc;
        if (mc == null) return;
        detach(mc);
        var x:Number = Number(spec.x);
        var y:Number = Number(spec.y);
        var w:Number = Number(spec.w);
        var h:Number = Number(spec.h);

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
            // A one-column bar has the width for neither a horizontal label nor
            // "X:n Y:n" on one line: the label runs down it, the coords stack.
            var vl:TextField = makeTF(ov, "lbl", x, y, h, 22, 14, 0xFFFFFF);
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

        var self:KazBarsPreview = this;
        ov._mc = mc; ov._self = self;
        ov._x0 = x; ov._y0 = y; ov._w = w; ov._h = h;
        ov.useHandCursor = true;
        // Bounds are read at press, not at creation: the rect is the anchor's
        // distance to each edge, and the Stage can be resized between the two.
        ov.onPress = function() {
            this._mc.startDrag(false, -this._x0, -this._y0,
                               Stage.width - (this._x0 + this._w),
                               Stage.height - (this._y0 + this._h));
            this.onMouseMove = function() { this._self.updCoords(this); };
        };
        ov.onRelease = ov.onReleaseOutside = function() {
            this._mc.stopDrag();
            delete this.onMouseMove;
            this._self.updCoords(this);
        };
        mc._kbOv = ov;
        updCoords(ov);
    }

    public function detach(mc:MovieClip):Void {
        if (mc == null) return;
        if (mc._kbOv != null) {
            mc._kbOv.removeMovieClip();
            mc._kbOv = null;
        }
    }

    // Assigns text only: the format was set once at creation, so a drag does
    // not allocate a TextFormat per mouse move.
    public function updCoords(ov:MovieClip):Void {
        if (ov == null || ov._mc == null) return;
        var px:Number = Math.round(ov._mc._x);
        var py:Number = Math.round(ov._mc._y);
        if (ov._yc != null) {
            ov._xc.text = "X:" + px;
            ov._yc.text = "Y:" + py;
        } else if (ov._xc != null) {
            ov._xc.text = "X:" + px + " Y:" + py;
        }
    }

    private function makeTF(ov:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, col:Number):TextField {
        var tf:TextField = ov.createTextField(id, ov.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
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
