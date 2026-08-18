// KazBarsModule.as - The lifecycle the core drives every optional module
// through (console, cast timer, stopwatch, inspect panel). The core holds them
// in one `modules` array and dispatches through this type alone, so a build
// that gates a module out leaves no dangling reference behind — and MTASC
// checks each stub against the contract instead of the template's call sites
// discovering a drifted name at runtime.
//
// Two classes of module implement it. HUD (cast timer, inspect panel): a
// game-facing display, hidden when it has nothing to show, mouse-transparent
// in normal play, positioned only in preview through the shared overlay in
// KazBarsPreview. Tool (stopwatch, console): an opt-in utility, always
// interactive, dragged by its own title strip through KazBarsPanel. A tool's
// previewOn/previewOff are no-ops — it is already interactive, so preview has
// nothing to add.
//
// previewKey/previewLabel are what the control panel's extra row is built
// from; the key routes back through KazBars.previewToggle(key, shown) into
// setActive.
interface KazBarsModule {
    function create():Void;
    function loadState(config:Object):Void;
    function saveState(config:Object):Void;
    function previewOn():Void;
    function previewOff():Void;
    function isActive():Boolean;
    function setActive(shown:Boolean):Void;
    function previewKey():String;
    function previewLabel():String;
    function cleanup():Void;
}
