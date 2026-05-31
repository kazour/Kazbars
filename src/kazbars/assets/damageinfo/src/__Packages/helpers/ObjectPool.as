class helpers.ObjectPool
{
   var _available;
   var _inUse;
   var _capacity;
   var _factoryFunction;
   var _resetFunction;
   
   // PHASE3: Generic object pool for memory efficiency
   function ObjectPool(initialCapacity, factoryFunction, resetFunction)
   {
      this._capacity = initialCapacity;
      this._factoryFunction = factoryFunction;
      this._resetFunction = resetFunction;
      this._available = [];
      this._inUse = [];
   }
   
   // PHASE3: Pre-populate pool with objects
   function initialize()
   {
      var _loc2_ = 0;
      while(_loc2_ < this._capacity)
      {
         if(this._factoryFunction != null)
         {
            this._available.push(this._factoryFunction());
         }
         _loc2_ = _loc2_ + 1;
      }
   }
   
   // PHASE3: Get object from pool (or create if exhausted)
   function acquire()
   {
      var _loc2_;
      
      if(this._available.length > 0)
      {
         // Get from pool
         _loc2_ = this._available.pop();
         this._inUse.push(_loc2_);
         return _loc2_;
      }
      else
      {
         // Pool exhausted - create temporary (will be GC'd, not returned to pool)
         if(this._factoryFunction != null)
         {
            _loc2_ = this._factoryFunction();
            // Don't add to _inUse - this is a temporary object
            return _loc2_;
         }
         return null;
      }
   }
   
   // PHASE5: Fixed release logic
   function release(obj)
   {
      if(obj == null)
      {
         return undefined;
      }

      // Find and remove from in-use, track if found
      var foundIndex = -1;
      var i = 0;
      while(i < this._inUse.length)
      {
         if(this._inUse[i] == obj)
         {
            foundIndex = i;
            this._inUse.splice(i, 1);
            break;
         }
         i = i + 1;
      }

      // Reset object state
      if(this._resetFunction != null)
      {
         this._resetFunction(obj);
      }

      // Only return to pool if it was tracked (not a temporary overflow object)
      if(foundIndex != -1)
      {
         this._available.push(obj);
      }
   }
   
   // PHASE3: Expand pool capacity
   function expand(additionalCapacity)
   {
      var _loc2_ = 0;
      while(_loc2_ < additionalCapacity)
      {
         if(this._factoryFunction != null)
         {
            this._available.push(this._factoryFunction());
         }
         _loc2_ = _loc2_ + 1;
      }
      this._capacity += additionalCapacity;
   }
   
   // PHASE3: Get pool statistics
   function getStats()
   {
      return {
         capacity: this._capacity,
         available: this._available.length,
         inUse: this._inUse.length,
         utilization: (this._inUse.length / this._capacity) * 100
      };
   }
   
   function get capacity()
   {
      return this._capacity;
   }
   
   function get availableCount()
   {
      return this._available.length;
   }
   
   function get inUseCount()
   {
      return this._inUse.length;
   }
}
