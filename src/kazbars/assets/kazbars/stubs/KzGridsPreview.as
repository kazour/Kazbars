// KzGridsPreview.as - Preview Mode & Overlay Management
class KzGridsPreview {
    private var rootClip:MovieClip;

    public function KzGridsPreview(kb:Object, root:MovieClip) {
        rootClip = root;
    }

    public function createOverlay(obj:Object):Void {
        var mc:MovieClip = obj.mc;
        var cfg:Object = obj.cfg;
        if (mc._overlay != null) mc._overlay.removeMovieClip();
        var ov:MovieClip = mc.createEmptyMovieClip("_overlay", mc.getNextHighestDepth());
        var step:Number = cfg.iconSize + cfg.gap;
        var w:Number = cfg.cols * step - cfg.gap;
        var h:Number = cfg.rows * step - cfg.gap;
        var col:Number = (cfg.type == "player") ? 0x0066FF : 0xFF0066;
        ov.lineStyle(2, 0xFFFFFF, 80);
        ov.beginFill(col, 20);
        ov.moveTo(-2, -2); ov.lineTo(w + 2, -2); ov.lineTo(w + 2, h + 2); ov.lineTo(-2, h + 2); ov.lineTo(-2, -2);
        ov.endFill();

        var isVertical:Boolean = (cfg.cols == 1 && cfg.rows > 1);

        if (isVertical) {
            // VERTICAL BAR: Rotated text (larger and clearer)
            var lbl:TextField = ov.createTextField("lbl", ov.getNextHighestDepth(), 0, 0, h, 22);
            lbl.selectable = false;
            lbl.embedFonts = false;
            lbl.text = cfg.id;
            lbl.textColor = 0xFFFFFF;
            var fmt:TextFormat = new TextFormat();
            fmt.font = "Arial"; fmt.size = 14; fmt.bold = true; fmt.align = "center";
            lbl.setTextFormat(fmt);
            lbl._rotation = 90;
            lbl._x = (w / 2) - 9;
            lbl._y = 5;

            // Coordinates stacked vertically at bottom
            var coordsY:Number = h - 30;
            var xCoord:TextField = ov.createTextField("xc", ov.getNextHighestDepth(), 0, coordsY, w, 14);
            xCoord.selectable = false;
            xCoord.embedFonts = false;
            xCoord.text = "X:" + Math.round(mc._x);
            xCoord.textColor = 0xFFFF00;
            var xfmt:TextFormat = new TextFormat();
            xfmt.font = "Arial"; xfmt.size = 10; xfmt.bold = true; xfmt.align = "center";
            xCoord.setTextFormat(xfmt);

            var yCoord:TextField = ov.createTextField("yc", ov.getNextHighestDepth(), 0, coordsY + 12, w, 14);
            yCoord.selectable = false;
            yCoord.embedFonts = false;
            yCoord.text = "Y:" + Math.round(mc._y);
            yCoord.textColor = 0xFFFF00;
            var yfmt:TextFormat = new TextFormat();
            yfmt.font = "Arial"; yfmt.size = 10; yfmt.bold = true; yfmt.align = "center";
            yCoord.setTextFormat(yfmt);

            obj.coordsTF = xCoord;
            obj.coordsTF2 = yCoord;
        } else {
            // HORIZONTAL/GRID: Normal layout with stacked coordinates
            var lbl:TextField = ov.createTextField("lbl", ov.getNextHighestDepth(), 0, 4, w, 18);
            lbl.selectable = false;
            lbl.embedFonts = false;
            lbl.text = cfg.id;
            lbl.textColor = 0xFFFFFF;
            var fmt:TextFormat = new TextFormat();
            fmt.font = "Arial"; fmt.size = 14; fmt.bold = true; fmt.align = "center";
            lbl.setTextFormat(fmt);

            // Coordinates stacked vertically at bottom
            var xCoord:TextField = ov.createTextField("xc", ov.getNextHighestDepth(), 0, h - 28, w, 14);
            xCoord.selectable = false;
            xCoord.embedFonts = false;
            xCoord.text = "X:" + Math.round(mc._x);
            xCoord.textColor = 0xFFFF00;
            var xfmt:TextFormat = new TextFormat();
            xfmt.font = "Arial"; xfmt.size = 11; xfmt.bold = true; xfmt.align = "center";
            xCoord.setTextFormat(xfmt);

            var yCoord:TextField = ov.createTextField("yc", ov.getNextHighestDepth(), 0, h - 16, w, 14);
            yCoord.selectable = false;
            yCoord.embedFonts = false;
            yCoord.text = "Y:" + Math.round(mc._y);
            yCoord.textColor = 0xFFFF00;
            var yfmt:TextFormat = new TextFormat();
            yfmt.font = "Arial"; yfmt.size = 11; yfmt.bold = true; yfmt.align = "center";
            yCoord.setTextFormat(yfmt);

            obj.coordsTF = xCoord;
            obj.coordsTF2 = yCoord;
        }

        var self:KzGridsPreview = this;
        ov._mc = mc; ov._obj = obj; ov._self = self; ov._w = w; ov._h = h; ov.useHandCursor = true;
        ov.onPress = function() {
            var maxX:Number = Stage.width - this._w;
            var maxY:Number = Stage.height - this._h;
            this._mc.startDrag(false, 0, 0, maxX, maxY);
            this.onMouseMove = function() { this._self.updCoords(this._obj.coordsTF, this._obj.coordsTF2, this._mc); };
        };
        ov.onRelease = ov.onReleaseOutside = function() { this._mc.stopDrag(); delete this.onMouseMove; this._self.updCoords(this._obj.coordsTF, this._obj.coordsTF2, this._mc); };
        mc._overlay = ov;
    }

    public function updCoords(xTF:TextField, yTF:TextField, mc:MovieClip):Void {
        if (xTF == null || yTF == null || mc == null) return;
        xTF.text = "X:" + Math.round(mc._x);
        yTF.text = "Y:" + Math.round(mc._y);
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = 11;
        fmt.bold = true;
        fmt.align = "center";
        xTF.setTextFormat(fmt);
        yTF.setTextFormat(fmt);
    }

    public function removeOverlay(obj:Object):Void {
        if (obj.mc._overlay != null) { obj.mc._overlay.removeMovieClip(); obj.mc._overlay = null; }
        obj.coordsTF = null;
        obj.coordsTF2 = null;
    }
}
