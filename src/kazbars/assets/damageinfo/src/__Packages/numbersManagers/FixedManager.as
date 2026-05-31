class numbersManagers.FixedManager extends numbersManagers.AbstractManager
{
   var _elements;
   var _numElements;
   static var TEXT_Y_BASE = 100;
   static var TEXT_X_OFFSET = 200;
   static var TEXT_Y_OFFSET = 60;
   static var MAX_STATIC_NUMBERS = 10;
   function FixedManager(onEmptyCallback)
   {
      super(onEmptyCallback);
      this._elements = new Array(numbersManagers.FixedManager.MAX_STATIC_NUMBERS);
      var _loc3_ = 0;
      while(_loc3_ < numbersManagers.FixedManager.MAX_STATIC_NUMBERS)
      {
         this._elements[_loc3_] = null;
         _loc3_ = _loc3_ + 1;
      }
   }
   function addElement(newElement)
   {
      var _loc5_ = -1;
      var _loc3_ = 9999999999999;
      var _loc6_ = this._elements.length;
      var _loc2_ = 0;
      while(_loc2_ < _loc6_)
      {
         if(this._elements[_loc2_] == null)
         {
            this._numElements = this._numElements + 1;
            this._elements[_loc2_] = newElement;
            return this._getPosition(_loc2_,newElement);
         }
         if(this._elements[_loc2_].id < _loc3_)
         {
            _loc3_ = this._elements[_loc2_].id;
            _loc5_ = _loc2_;
         }
         _loc2_ = _loc2_ + 1;
      }
      if(_loc5_ > -1)
      {
         if(this._elements[_loc5_] != null && this._elements[_loc5_].id == _loc3_)
         {
            this._removeElement(this._elements[_loc5_],0);
            this._elements[_loc5_] = newElement;
         }
      }
      return this._getPosition(_loc5_,newElement);
   }
   function update(dtMs, mod)
   {
      var _loc3_;
      var _loc2_ = 0;
      while(_loc2_ < numbersManagers.FixedManager.MAX_STATIC_NUMBERS)
      {
         if(!(!this._elements[_loc2_] || this._elements[_loc2_] == null || this._elements[_loc2_] == undefined))
         {
            this._animateElement(this._elements[_loc2_], dtMs);
            _loc3_ = this._checkElementLife(this._elements[_loc2_],mod);
            if(!_loc3_)
            {
               this._deleteElementAt(_loc2_);
            }
         }
         _loc2_ = _loc2_ + 1;
      }

      // Advance fade-outs, then signal empty so the shared loop can stop.
      this._updateFading(dtMs);
      if(this.numElements <= 0)
      {
         this._onEmptyCallback();
      }
   }
   function _getPosition(index, element)
   {
      var _loc1_ = element.currentPosition;
      _loc1_.y = _loc1_.y - numbersManagers.FixedManager.TEXT_Y_OFFSET * (index - 4) * element.scale / 100 + numbersManagers.FixedManager.TEXT_Y_BASE;
      if(index % 2 == 0)
      {
         _loc1_.x -= numbersManagers.FixedManager.TEXT_X_OFFSET;
      }
      else
      {
         _loc1_.x += numbersManagers.FixedManager.TEXT_X_OFFSET;
      }
      return _loc1_;
   }
   function _deleteElementAt(index)
   {
      this._numElements = this._numElements - 1;
      this._removeElement(this._elements[index],0);
      this._elements[index] = null;
   }
}
