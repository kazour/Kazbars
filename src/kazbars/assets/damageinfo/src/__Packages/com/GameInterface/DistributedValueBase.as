// Intrinsic class - provided by game engine at runtime
intrinsic class com.GameInterface.DistributedValueBase
{
   var SignalChanged;

   function DistributedValueBase(name);
   function QueryValue();
   function SetValue(value);
   function GetValue();
}
