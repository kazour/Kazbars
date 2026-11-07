// KazBarsConList.as - One console column (a list, not a debug log): its lines as HTML runs, newest first, at most
// `cap`; past that the oldest rolls off, so the newest are never lost. A unique column (Buffs) takes each key once
// while it holds it. `dirty` tells the console the column needs drawing, and the console clears it once drawn: a
// hidden tab costs one insert per event, never a text rebuild.
class KazBarsConList {
    public var dirty:Boolean;
    private var lines:Array;
    private var keys:Array;
    private var seen:Object;
    private var cap:Number;

    public function KazBarsConList(n:Number, unique:Boolean) {
        cap = n;
        if (unique) seen = {};
        clear();
    }

    public function add(key:String, html:String):Void {
        if (seen != null) {
            if (seen[key] == true) return;
            seen[key] = true;
        }
        lines.unshift(html);
        keys.unshift(key);
        if (lines.length > cap) {
            lines.pop();
            var k:String = String(keys.pop());
            if (seen != null) delete seen[k];
        }
        dirty = true;
    }

    public function html():String {
        return lines.join("");
    }

    public function clear():Void {
        lines = [];
        keys = [];
        if (seen != null) seen = {};
        dirty = true;
    }
}
