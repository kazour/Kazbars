class numbersManagers.MovingManager extends numbersManagers.AbstractManager
{
   var _columns;
   var _columnsID;
   var _elements;
   var _numColumns;
   var _numElements;

   // PHASE2: Numeric constants instead of strings (faster comparison)
   static var SEARCH_FIRST = 0;  // Oldest element in column
   static var SEARCH_LAST = 1;   // Newest element in column

   var movingOffset = 1;

   // PHASE5: Array-indexed counters [FRIENDLY=0, HOSTILE=1]
   var _currentCount;
   var _maxCount;

   // PHASE1: Column cleanup delay (2 seconds = 2000ms)
   static var COLUMN_CLEANUP_DELAY = 2000;

   // PHASE2: Hashmap for O(1) column lookup
   var _columnsByKey;

   // PHASE2.5: Track creation order for O(1) limit enforcement
   var _creationOrder = 0;

   function MovingManager(onEmptyCallback)
   {
      super(onEmptyCallback);
      this._columns = [];
      this._numColumns = 0;
      this._columnsID = 0;

      // PHASE5: Initialize array-indexed counters
      this._currentCount = [0, 0];  // [friendly, hostile]
      this._maxCount = [50, 50];    // [friendly, hostile]

      // PHASE2: Initialize hashmap
      this._columnsByKey = {};
   }

   // PHASE5: Getters for backward compatibility
   function get _maxFriendlyNumbers()
   {
      return this._maxCount[0];
   }

   function get _maxHostileNumbers()
   {
      return this._maxCount[1];
   }
   
   function addElement(newElement)
   {
      // PHASE2.5: Assign creation order for tracking oldest
      newElement._creationOrder = this._creationOrder;
      this._creationOrder = this._creationOrder + 1;

      // PHASE5: Check limit using array-indexed counters
      var type = newElement.hostilityType;
      if(this._currentCount[type] >= this._maxCount[type])
      {
         this._dropOldestByHostilityType(type);
      }
      this._currentCount[type] = this._currentCount[type] + 1;
      
      // CUSTOMIZATION: Get prefix status for column distinction
      var hasPrefixSign = false;
      if(newElement.flyingDirection == -1)
      {
         hasPrefixSign = numbersTypes.MovingDamageText(newElement).hasPrefixSign;
      }
      
      // CUSTOMIZATION: Pass prefix info to column finder
      var _loc6_ = this._findCorrespondingColumn(newElement.targetCharacter, newElement.flyingDirection, hasPrefixSign);
      
      // Check if column is full
      if(_loc6_.itemsCount >= numbersManagers.NumbersColumn.MAX_ITEMS_COUNT)
      {
         // PHASE2: Remove oldest element from column
         var _loc8_ = _loc6_.getFirstElement();
         if(_loc8_ != null)
         {
            this._deleteElementDirect(_loc8_);
         }
      }
      
      // PHASE2: Speed up all elements in this column directly
      var _loc4_ = _loc6_.getElements();
      var _loc5_ = _loc4_.length;
      var _loc3_ = 0;
      while(_loc3_ < _loc5_)
      {
         this._speedUp(numbersTypes.MovingDamageText(_loc4_[_loc3_]), this.movingOffset - 1, 10);
         _loc3_ = _loc3_ + 1;
      }
      
      // PHASE2: Add element to column
      _loc6_.addElement(newElement);
      
      // Column is no longer empty, clear empty timestamp
      _loc6_._emptyTimestamp = -1;
      
      newElement.columnID = _loc6_.id;
      
      // Add to manager's main array
      this._elements[this._numElements] = newElement;
      this._numElements = this._numElements + 1;
   }
   
   // PHASE2.5: Optimized - find and remove oldest by type using creation order
   function _dropOldestByHostilityType(hostilityType)
   {
      var _loc3_ = -1;
      var _loc4_ = 999999999;
      var _loc2_ = 0;
      
      // Find element with lowest creation order (oldest) of matching type
      while(_loc2_ < this._numElements)
      {
         if(this._elements[_loc2_].hostilityType == hostilityType)
         {
            if(this._elements[_loc2_]._creationOrder < _loc4_)
            {
               _loc4_ = this._elements[_loc2_]._creationOrder;
               _loc3_ = _loc2_;
            }
         }
         _loc2_ = _loc2_ + 1;
      }
      
      if(_loc3_ != -1)
      {
         this._deleteElementAt(_loc3_);
      }
   }
   
   function _speedUp(item, speedValue, speedDuration)
   {
      item.accelFactor += speedValue;
      item.accelDuration = speedDuration;
   }
   
   function update(dtMs, mod)
   {
      var _loc3_;
      var _loc2_ = 0;
      while(_loc2_ < this._numElements)
      {
         if(this._elements[_loc2_] != null)
         {
            this._animateElement(this._elements[_loc2_], dtMs);
            _loc3_ = this._checkElementLife(this._elements[_loc2_], mod);
            if(!_loc3_)
            {
               this._deleteElementAt(_loc2_);
               _loc2_ = _loc2_ - 1;
            }
            else
            {
               this._updateElement(this._elements[_loc2_], mod);
            }
         }
         _loc2_ = _loc2_ + 1;
      }

      // Clean up columns that have been empty for COLUMN_CLEANUP_DELAY
      this._cleanupEmptyColumns();

      // Advance fade-outs, then signal empty so the shared loop can stop.
      this._updateFading(dtMs);
      if(this.numElements <= 0)
      {
         this._onEmptyCallback();
      }
   }
   
   // PHASE5: Simplified using array-indexed counters
   function setMaxNumbersByType(hostilityType, newValue)
   {
      this._maxCount[hostilityType] = newValue;

      // Drop excess if current exceeds new max
      if(this._currentCount[hostilityType] > this._maxCount[hostilityType])
      {
         var excess = this._currentCount[hostilityType] - this._maxCount[hostilityType];
         var i = 0;
         while(i < excess)
         {
            this._dropOldestByHostilityType(hostilityType);
            i = i + 1;
         }
      }
   }
   
   // PHASE5: Extract numeric ID from target (ID32 or number)
   function _getTargetID(target)
   {
      // If it's an ID32 object, use instance number
      if(target.m_Instance != undefined)
      {
         return target.m_Instance;
      }
      // Otherwise assume it's already a number
      return Number(target);
   }

   // PHASE5: Generate numeric column key (avoids string concatenation)
   // Format: targetID * 100 + (direction + 2) * 10 + signedFlag
   function _makeColumnKey(targetID, direction, hasPrefixSign)
   {
      var signedFlag = (direction == -1 && hasPrefixSign) ? 1 : 0;
      return (targetID * 100) + ((direction + 2) * 10) + signedFlag;
   }

   // CUSTOMIZATION: Modified to accept hasPrefixSign parameter
   function _findCorrespondingColumn(target, direction, hasPrefixSign)
   {
      // PHASE5: Use numeric key instead of string concatenation
      var targetID = this._getTargetID(target);
      var key = this._makeColumnKey(targetID, direction, hasPrefixSign);

      // PHASE2: O(1) lookup
      if(this._columnsByKey[key] != undefined)
      {
         return this._columnsByKey[key];
      }

      // Create new column
      var newColumn = new numbersManagers.NumbersColumn(this._columnsID, target, direction);
      this._columns[this._numColumns] = newColumn;
      this._numColumns = this._numColumns + 1;
      this._columnsID = this._columnsID + 1;

      // PHASE5: Store numeric key in column
      newColumn.setHashmapKey(key);

      // PHASE2: Add to hashmap
      this._columnsByKey[key] = newColumn;

      return newColumn;
   }
   
   // PHASE1: Clean up columns that have been empty for delay period
   function _cleanupEmptyColumns()
   {
      var _loc2_ = this._numColumns - 1;
      var _loc3_;
      var _loc4_ = getTimer();
      
      while(_loc2_ >= 0)
      {
         _loc3_ = this._columns[_loc2_];
         
         if(_loc3_.itemsCount == 0 && _loc3_._emptyTimestamp > 0)
         {
            // Check if column has been empty long enough
            if(_loc4_ - _loc3_._emptyTimestamp >= numbersManagers.MovingManager.COLUMN_CLEANUP_DELAY)
            {
               this._dropColumn(_loc3_);
            }
         }
         
         _loc2_ = _loc2_ - 1;
      }
   }
   
   function _dropColumn(column)
   {
      // CUSTOMIZATION: Use stored hashmap key for proper cleanup
      var key = column.getHashmapKey();
      if(key != null)
      {
         delete this._columnsByKey[key];
      }
      
      // Remove from array
      this._columns.splice(com.helperFramework.utils.ArrayUtils.indexOf(column, this._columns), 1);
      this._numColumns = this._numColumns - 1;
   }
   
   // PHASE2: Simplified - use hashmap lookup
   function _getColumn(columnID)
   {
      // Still need this for backward compatibility (columnID lookup)
      var _loc2_ = 0;
      while(_loc2_ < this._numColumns)
      {
         if(this._columns[_loc2_].id == columnID)
         {
            return this._columns[_loc2_];
         }
         _loc2_ = _loc2_ + 1;
      }
      return null;
   }
   
   function _updateElement(element, intervalModifyer)
   {
      if(element.accelDuration > 0)
      {
         element.move((- (element.speed * 0.01 + element.accelFactor)) * element.flyingDirection * intervalModifyer);
         element.accelDuration -= intervalModifyer;
      }
      else
      {
         element.accelFactor = 1;
         element.move((- element.speed * 0.01) * element.flyingDirection * intervalModifyer);
      }
   }
   
   // PHASE2.5: Direct deletion without index lookup (used by column overflow)
   function _deleteElementDirect(element)
   {
      var _loc2_ = 0;
      while(_loc2_ < this._numElements)
      {
         if(this._elements[_loc2_] == element)
         {
            this._deleteElementAt(_loc2_);
            return undefined;
         }
         _loc2_ = _loc2_ + 1;
      }
   }
   
   // PHASE2.5: SWAP-AND-POP deletion instead of splice (O(1) instead of O(n))
   function _deleteElementAt(index)
   {
      if(index < 0 || index >= this._numElements)
      {
         return undefined;
      }
      
      var element = this._elements[index];
      
      // Remove from column's array
      var _loc3_ = this._getColumn(numbersTypes.MovingDamageText(element).columnID);
      if(_loc3_ != null)
      {
         _loc3_.removeElement(element);
         
         // Mark column as empty if itemsCount reached 0
         if(_loc3_.itemsCount == 0)
         {
            _loc3_._emptyTimestamp = getTimer();
         }
      }
      
      // PHASE5: Update hostility counts using array
      this._currentCount[element.hostilityType] = this._currentCount[element.hostilityType] - 1;
      
      // Trigger fade-out animation and destruction
      this._removeElement(element, numbersTypes.MovingDamageText(element).flyingDirection * 15);
      
      // PHASE2.5: SWAP-AND-POP - O(1) removal instead of splice
      // Swap with last element, then pop (no array shifting!)
      this._numElements = this._numElements - 1;
      if(index != this._numElements)
      {
         // Swap: move last element to deleted position
         this._elements[index] = this._elements[this._numElements];
      }
      // Pop: remove last element (just decrement length, array auto-shrinks)
      this._elements[this._numElements] = null;
   }
}
