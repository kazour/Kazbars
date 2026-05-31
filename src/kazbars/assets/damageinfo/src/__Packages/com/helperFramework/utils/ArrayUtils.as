class com.helperFramework.utils.ArrayUtils
{
   function ArrayUtils()
   {
   }
   static function isInArray(value, collection, recursive)
   {
      if(recursive == undefined || recursive == null)
      {
         recursive = false;
      }
      var _loc3_ = false;
      var _loc6_ = collection.length;
      var _loc1_ = 0;
      while(_loc1_ < _loc6_)
      {
         if(recursive && collection[_loc1_] instanceof Array)
         {
            _loc3_ = com.helperFramework.utils.ArrayUtils.isInArray(value,collection[_loc1_],true);
            if(_loc3_)
            {
               return true;
            }
         }
         else if(collection[_loc1_] == value)
         {
            return true;
         }
         _loc1_ = _loc1_ + 1;
      }
      return false;
   }
   static function indexOf(value, collection, referenceIndex)
   {
      if(referenceIndex == null || referenceIndex == undefined)
      {
         referenceIndex = 0;
      }
      var _loc5_ = collection.length;
      var _loc1_ = 0;
      while(_loc1_ < _loc5_)
      {
         if(collection[_loc1_] instanceof Array)
         {
            if(collection[_loc1_][referenceIndex] == value)
            {
               return _loc1_;
            }
         }
         else if(collection[_loc1_] == value)
         {
            return _loc1_;
         }
         _loc1_ = _loc1_ + 1;
      }
      return -1;
   }
}
