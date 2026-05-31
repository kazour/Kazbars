class com.GameInterface.DistributedValue extends com.GameInterface.DistributedValueBase
{
   function DistributedValue(name)
   {
      super(name);
   }
   static function Create(name)
   {
      return new com.GameInterface.DistributedValue(name);
   }
}
