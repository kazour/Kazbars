class com.Utils.Slot
{
   var m_Callback;
   var m_Object;
   var m_Signal;
   var m_SignalGroup;
   function Slot(signal, group, callback, object)
   {
      this.m_Signal = signal;
      this.m_SignalGroup = group;
      if(object != null)
      {
         this.m_Object = new com.Utils.WeakPtr(object);
         this.m_Object.OnObjectDied = mx.utils.Delegate.create(this,this.DisconnectSelf);
      }
      else
      {
         this.m_Object = null;
      }
      this.m_Callback = callback;
   }
   function GetCallback()
   {
      return this.m_Callback;
   }
   function GetObject()
   {
      if(this.m_Object != null)
      {
         return this.m_Object.Get();
      }
      return null;
   }
   function DisconnectSelf()
   {
      this.m_Signal.DisconnectSlot(this);
   }
}
