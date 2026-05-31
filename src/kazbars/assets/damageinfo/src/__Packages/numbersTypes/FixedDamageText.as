class numbersTypes.FixedDamageText extends numbersTypes.DamageTextAbstract
{
   // Note: TYPE, _container, _currentPosition, _id, _ttl are inherited from DamageTextAbstract

   function FixedDamageText(id)
   {
      super(id);
      this.TYPE = 0;  // STATIC
   }
   
   function changeID(newValue)
   {
      this._id = newValue;
   }
   
   function generate(parentClip, xPos, yPos, htmlFont, title, text, scale)
   {
      super.generate(parentClip, xPos, yPos, htmlFont, title, text, scale);
      this._ttl *= 0.5;
      this._currentPosition = new flash.geom.Point(xPos, yPos);
   }
   
   function setPosition(position)
   {
      this._currentPosition = position;
      this._container._x = this._currentPosition.x;
      this._container._y = this._currentPosition.y;
      var _loc3_ = this._getContentByType(DamageTextContent.TYPE_TEXT);
      this._start(_loc3_);
      var _loc2_ = this._getContentByType(DamageTextContent.TYPE_TITLE);
      if(_loc2_ != null)
      {
         this._start(_loc2_, 0, -(_loc3_.content._height + 10));
      }
   }
   
   // PHASE3: Reset for object pooling
   function reset()
   {
      // Call base reset
      super.reset();
      
      // Reset FixedDamageText-specific properties
      this._currentPosition = null;
   }
}
