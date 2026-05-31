class com.Utils.Signal
{
   var m_EventList;
   function Signal()
   {
      this.m_EventList = new Array();
   }
   function Connect()
   {
      var _loc4_;
      var _loc6_;
      var _loc7_;
      var _loc5_;
      var _loc3_ = 0;
      if(arguments.length > 1 && typeof arguments[1] == "function")
      {
         _loc4_ = arguments[_loc3_++];
         _loc6_ = arguments[_loc3_++];
      }
      else
      {
         _loc4_ = null;
         _loc6_ = arguments[_loc3_++];
      }
      if(arguments.length > _loc3_)
      {
         _loc7_ = arguments[_loc3_++];
      }
      else
      {
         _loc7_ = null;
      }
      _loc5_ = new com.Utils.Slot(this,_loc4_,_loc6_,_loc7_);
      this.m_EventList.push(_loc5_);
      if(_loc4_ != null)
      {
         _loc4_.AddSlot(_loc5_);
      }
      return _loc5_;
   }
   function Disconnect(callback)
   {
      var _loc3_;
      if(arguments.length == 1)
      {
         _loc3_ = 0;
         while(_loc3_ < this.m_EventList.length)
         {
            if(this.m_EventList[_loc3_].GetCallback() == callback)
            {
               if(this.m_EventList[_loc3_].m_SignalGroup != null)
               {
                  this.m_EventList[_loc3_].m_SignalGroup.RemoveSlot(this.m_EventList[_loc3_]);
               }
               this.m_EventList.splice(_loc3_,1);
               return true;
            }
            _loc3_ = _loc3_ + 1;
         }
         trace("Signal.Disconnect() failed to remove function slot.");
         return false;
      }
      var _loc5_ = arguments[1];
      _loc3_ = 0;
      while(_loc3_ < this.m_EventList.length)
      {
         if(this.m_EventList[_loc3_].GetCallback() == callback && this.m_EventList[_loc3_].GetObject() == _loc5_)
         {
            if(this.m_EventList[_loc3_].m_SignalGroup != null)
            {
               this.m_EventList[_loc3_].m_SignalGroup.RemoveSlot(this.m_EventList[_loc3_]);
            }
            this.m_EventList.splice(_loc3_,1);
            return true;
         }
         _loc3_ = _loc3_ + 1;
      }
      trace("Signal.Disconnect() failed to remove method slot.");
      return false;
   }
   function DisconnectSlot(slot)
   {
      var _loc2_ = 0;
      while(_loc2_ < this.m_EventList.length)
      {
         if(this.m_EventList[_loc2_] == slot)
         {
            slot.m_Signal = null;
            this.m_EventList.splice(_loc2_,1);
            return true;
         }
         _loc2_ = _loc2_ + 1;
      }
      trace("Signal.DisconnectSlot() failed to remove slot.");
      return false;
   }
   function Emit()
   {
      var _loc4_;
      var _loc3_ = 0;
      while(_loc3_ < this.m_EventList.length)
      {
         this.m_EventList[_loc3_].GetCallback().apply(this.m_EventList[_loc3_].GetObject(),arguments);
         _loc3_ = _loc3_ + 1;
      }
   }
   function Empty()
   {
      return this.m_EventList.length == 0;
   }
}
