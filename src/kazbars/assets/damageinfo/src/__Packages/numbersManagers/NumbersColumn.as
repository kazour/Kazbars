class numbersManagers.NumbersColumn
{
   var _direction;
   var _id;
   var _target;
   var itemsCount;
   
   // PHASE1: Track when column became empty for delayed cleanup
   var _emptyTimestamp;
   
   // PHASE2: Column now stores its own elements directly
   var _elements;
   
   // CUSTOMIZATION: Store hashmap key for proper cleanup
   var _hashmapKey;
   
   static var MAX_ITEMS_COUNT = 100;
   
   function NumbersColumn(id, target, direction)
   {
      this._id = id;
      this._target = target;
      this._direction = direction;
      this.itemsCount = 0;
      this._emptyTimestamp = -1;
      
      // PHASE2: Initialize elements array
      this._elements = [];
      
      // CUSTOMIZATION: Initialize hashmap key (will be set by manager)
      this._hashmapKey = null;
   }
   
   // CUSTOMIZATION: Set the hashmap key
   function setHashmapKey(key)
   {
      this._hashmapKey = key;
   }
   
   // CUSTOMIZATION: Get the hashmap key
   function getHashmapKey()
   {
      return this._hashmapKey;
   }
   
   // PHASE2: Add element to column's own array
   function addElement(element)
   {
      this._elements.push(element);
      this.itemsCount = this._elements.length;
   }
   
   // PHASE2: Remove element from column's own array
   function removeElement(element)
   {
      var _loc2_ = 0;
      while(_loc2_ < this._elements.length)
      {
         if(this._elements[_loc2_] == element)
         {
            this._elements.splice(_loc2_, 1);
            this.itemsCount = this._elements.length;
            return true;
         }
         _loc2_ = _loc2_ + 1;
      }
      return false;
   }
   
   // PHASE2: Get element at index
   function getElementAt(index)
   {
      if(index >= 0 && index < this._elements.length)
      {
         return this._elements[index];
      }
      return null;
   }
   
   // PHASE2: Get all elements (returns reference to array, not copy)
   function getElements()
   {
      return this._elements;
   }
   
   // PHASE2: Get first element (oldest)
   function getFirstElement()
   {
      if(this._elements.length > 0)
      {
         return this._elements[this._elements.length - 1];
      }
      return null;
   }
   
   // PHASE2: Get last element (newest)
   function getLastElement()
   {
      if(this._elements.length > 0)
      {
         return this._elements[0];
      }
      return null;
   }
   
   function get id()
   {
      return this._id;
   }
   function get target()
   {
      return this._target;
   }
   function get direction()
   {
      return this._direction;
   }
   function toString()
   {
      return "Column " + this.id + " target = " + this.target + " direction = " + this.direction + " items = " + this.itemsCount;
   }
}
