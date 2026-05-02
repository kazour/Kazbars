// KzGridsSlot.as - Slot Creation & Management Helper
// Extracted to stay under MTASC 32KB per-class bytecode limit
class KzGridsSlot {
    private var rootClip:MovieClip;
    private static var NATIVE_SIZE:Number = 64;

    public function KzGridsSlot(kb:Object, root:MovieClip) {
        rootClip = root;
    }

    // Creates timer TextFields (main + shadow) on a slot
    public function createTimerTF(s:MovieClip, fs:Number, yOffset:Number):Void {
        var tmrY:Number = NATIVE_SIZE - fs - 4 + yOffset;
        // Shadow TextField (created first so it's behind)
        var tfShadow:TextField = s.createTextField("tmrShadow", s.getNextHighestDepth(), 1, tmrY + 1, NATIVE_SIZE, fs + 4);
        tfShadow.selectable = false;
        tfShadow.embedFonts = false;
        tfShadow.textColor = 0x000000;
        var fmtShadow:TextFormat = new TextFormat();
        fmtShadow.font = "Arial";
        fmtShadow.size = fs;
        fmtShadow.bold = true;
        fmtShadow.align = "center";
        tfShadow.setNewTextFormat(fmtShadow);
        // Main timer TextField
        var tf:TextField = s.createTextField("tmr", s.getNextHighestDepth(), 0, tmrY, NATIVE_SIZE, fs + 4);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.textColor = 0xFFFFFF;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = fs;
        fmt.bold = true;
        fmt.align = "center";
        tf.setNewTextFormat(fmt);
    }

    // Creates stack counter TextFields (main + shadow) on a slot
    public function createStackTF(s:MovieClip, fs:Number):Void {
        var stkSize:Number = fs;
        var stkMargin:Number = 4;
        var stkWidth:Number = stkSize * 2 + 2;
        var stkX:Number = NATIVE_SIZE - stkWidth - stkMargin;
        var stkY:Number = stkMargin;
        // Shadow TextField
        var stkShadow:TextField = s.createTextField("stkShadow", s.getNextHighestDepth(), stkX + 1, stkY + 1, stkWidth, stkSize + 2);
        stkShadow.selectable = false;
        stkShadow.embedFonts = false;
        stkShadow.textColor = 0x000000;
        var stkFmtShadow:TextFormat = new TextFormat();
        stkFmtShadow.font = "Arial";
        stkFmtShadow.size = stkSize;
        stkFmtShadow.bold = true;
        stkFmtShadow.align = "right";
        stkShadow.setNewTextFormat(stkFmtShadow);
        // Main stack counter
        var stk:TextField = s.createTextField("stk", s.getNextHighestDepth(), stkX, stkY, stkWidth, stkSize + 2);
        stk.selectable = false;
        stk.embedFonts = false;
        stk.textColor = 0xFFFFFF;
        var stkFmt:TextFormat = new TextFormat();
        stkFmt.font = "Arial";
        stkFmt.size = stkSize;
        stkFmt.bold = true;
        stkFmt.align = "right";
        stk.setNewTextFormat(stkFmt);
    }

    // Swaps slot symbol type (BuffSlot/DebuffSlot/MiscSlot)
    // Returns the new slot MovieClip (or same if no swap needed)
    public function swapType(obj:Object, s:MovieClip, si:Number, slotType:String):MovieClip {
        if (s._slotType == slotType) return s;

        var p:MovieClip = s._parent;
        var idx:Number = s._idx;
        var sz:Number = s._sz;
        var fs:Number = s._fs;
        var cfg:Object = obj.cfg;
        var oldX:Number = s._x;
        var oldY:Number = s._y;

        s.removeMovieClip();

        var newSlot:MovieClip = p.attachMovie(slotType, "s" + idx, p.getNextHighestDepth());
        if (newSlot == null) {
            newSlot = p.createEmptyMovieClip("s" + idx, p.getNextHighestDepth());
            newSlot.createEmptyMovieClip("m_icon", newSlot.getNextHighestDepth());
        }

        var scale:Number = (sz / NATIVE_SIZE) * 100;
        newSlot._xscale = newSlot._yscale = scale;
        newSlot._x = oldX;
        newSlot._y = oldY;

        if (cfg.showTimers) createTimerTF(newSlot, fs, cfg.timerYOffset);
        createStackTF(newSlot, cfg.stackFont);

        newSlot._idx = idx;
        newSlot._sz = sz;
        newSlot._fs = fs;
        newSlot._lastIco = null;
        newSlot._lastSec = null;
        newSlot._slotType = slotType;
        newSlot._buff = null;
        newSlot._visible = false;

        obj.slots[si] = newSlot;
        return newSlot;
    }
}
