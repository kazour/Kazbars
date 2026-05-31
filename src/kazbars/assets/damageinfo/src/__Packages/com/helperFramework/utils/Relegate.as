class com.helperFramework.utils.Relegate extends Object
{
   function Relegate()
   {
      super();
   }
   static function create(scope, callback)
   {
      var args = arguments.splice(2);
      return function()
      {
         return callback.apply(scope,arguments.concat(args));
      };
   }
}
