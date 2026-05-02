// Stub for AoC's Character class
class com.GameInterface.Game.Character {
    public var m_BuffList:Object;
    public var SignalBuffAdded:Object;
    public var SignalBuffUpdated:Object;
    public var SignalBuffRemoved:Object;
    public var SignalOffensiveTargetChanged:Object;

    public static function GetClientCharacter():com.GameInterface.Game.Character { return null; }
    public static function GetCharacter(id:Object):com.GameInterface.Game.Character { return null; }
    public function GetOffensiveTarget():Object { return null; }
}
