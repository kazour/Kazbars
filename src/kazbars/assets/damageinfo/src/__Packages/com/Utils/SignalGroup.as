class com.Utils.SignalGroup
{
   var m_Connections;
   function SignalGroup()
   {
      this.m_Connections = new Array();
   }
   function DisconnectAll()
   {
      var _loc2_ = 0;
      var _loc3_;
      while(_loc2_ < this.m_Connections.length)
      {
         _loc3_ = this.m_Connections[_loc2_];
         _loc3_.m_Signal.DisconnectSlot(_loc3_);
         _loc2_ = _loc2_ + 1;
      }
      this.m_Connections.splice(0);
   }
   function AddSlot(slot)
   {
      this.m_Connections.push(slot);
   }
   function RemoveSlot(slot)
   {
      var _loc2_ = 0;
      while(_loc2_ < this.m_Connections.length)
      {
         if(this.m_Connections[_loc2_] == slot)
         {
            this.m_Connections.splice(_loc2_,1);
            break;
         }
         _loc2_ = _loc2_ + 1;
      }
   }
}
