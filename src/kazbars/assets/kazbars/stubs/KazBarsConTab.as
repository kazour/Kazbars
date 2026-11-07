// KazBarsConTab.as - One tab of the console (KazBarsConsole). Each tab is its own class under its own build gate,
// so a tab the user left out costs the SWF nothing. A tab owns two columns (KazBarsConList: player | target, or
// friendly | hostile) and feeds them from the shared runtime; the console draws only the visible tab's.
//
// key: the profile's name for the tab (`buffs`, ...), which orders the strip. label: the strip's text. heads: the
// two column titles. head: a line above the columns ("" for none), read on every draw. foot: a muted line in the
// button band, left of Clear ("" for none), read when the tab is laid out. follow: start the feeds
// (once, at load). open: the console was built (true) or taken down (false); a tab with work of its own (a poll, a
// tracker) runs it only while the console is open. shown: the tab is now on screen (the visible one, the console
// open and unfolded) or no longer is (another tab picked, a fold, a close); a tab draws its columns only while it is.
// clear: the Clear button. stop: the module's teardown.
interface KazBarsConTab {
    function key():String;
    function label():String;
    function heads():Array;
    function logs():Array;
    function head():String;
    function foot():String;
    function follow(con:KazBarsConsole, w:KazBarsWorld):Void;
    function open(up:Boolean):Void;
    function shown(vis:Boolean):Void;
    function clear():Void;
    function stop():Void;
}
