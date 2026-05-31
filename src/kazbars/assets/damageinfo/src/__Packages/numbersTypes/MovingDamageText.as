class numbersTypes.MovingDamageText extends numbersTypes.DamageTextAbstract
{
   // Note: TYPE, _container, _contents, _currentPosition, _font, _numContents, _ttl are inherited from DamageTextAbstract
   var _flyingDirection;
   var _targetCharacter;

   // CUSTOMIZATION: Direction 1 - Above target (floats above player/enemy head)
   static var DIR1_X_OFFSET = 50;   // Horizontal shift from target head
   static var DIR1_Y_OFFSET = 0;    // Vertical shift from target head

   // CUSTOMIZATION: Direction -1 - Fixed columns (at fixed screen position)
   // Column A: plain numbers (no prefix), or all numbers when split is off
   static var FIXED_COL_X = 50;            // Column A: X offset from center
   static var FIXED_COL_Y = 100;           // Column A: Y position from top
   static var FIXED_COL_SPLIT = 0;         // 0 = Column A only, 1 = Column A + B
   // Column B: prefix numbers (+/-) when split is enabled
   static var COL_B_X = 50;                // Column B: X offset from center (same default as A)
   static var COL_B_Y = 100;               // Column B: Y position from top (same default as A)

   // Speed limits
   static var TEXT_MIN_SPEED = 10;
   static var TEXT_MAX_SPEED = 300;
   var _speed = numbersTypes.MovingDamageText.TEXT_MIN_SPEED;
   var columnID = -1;
   var accelFactor = 1;
   var accelDuration = 0;

   // PHASE2.5: Creation order for oldest-first deletion
   var _creationOrder = 0;

   // CUSTOMIZATION: Prefix detection for column split
   var _hasPrefixSign = false;

   // CUSTOMIZATION: Flag for enemy resource loss direction override
   var _isOtherResourceLoss = false;

   function MovingDamageText(id)
   {
      super(id);
      this.TYPE = 1;  // MOVING
   }

   function generate(parentClip, xPos, yPos, htmlFont, title, text, scale)
   {
      // CUSTOMIZATION: Detect if number has prefix sign
      if(text != null && text.length > 0)
      {
         var firstChar = text.charAt(0);
         this._hasPrefixSign = (firstChar == "+" || firstChar == "-");
      }
      else
      {
         this._hasPrefixSign = false;
      }

      // CUSTOMIZATION: Determine effective direction (may be overridden for enemy resource loss)
      var effectiveDirection = htmlFont.m_FlyingDirection;
      if(this._isOtherResourceLoss && DamageNumberManager.OTHER_RESOURCE_LOSS_TO_TARGET == 1)
      {
         // Override: enemy resource drain goes to direction 1 (above their head)
         effectiveDirection = 1;
      }

      if(effectiveDirection > 0)
      {
         // Direction 1: Numbers float above target's head (player or enemy)
         xPos -= numbersTypes.MovingDamageText.DIR1_X_OFFSET;
         yPos += numbersTypes.MovingDamageText.DIR1_Y_OFFSET;
      }
      else if(effectiveDirection < 0)
      {
         // Direction -1: Numbers drop from fixed screen position
         if(numbersTypes.MovingDamageText.FIXED_COL_SPLIT == 1 && this._hasPrefixSign)
         {
            // Column B: prefix numbers (+/-)
            xPos += numbersTypes.MovingDamageText.COL_B_X;
            yPos = numbersTypes.MovingDamageText.COL_B_Y;
         }
         else
         {
            // Column A: plain numbers (or all numbers when split is off)
            xPos += numbersTypes.MovingDamageText.FIXED_COL_X;
            yPos = numbersTypes.MovingDamageText.FIXED_COL_Y;
         }
      }

      super.generate(parentClip, xPos, yPos, htmlFont, title, text, scale);
      this._speed = this._font.m_Speed;
      this._flyingDirection = effectiveDirection;  // Use effective direction, not font's
      this._ttl *= 0.7;
      var _loc4_ = this._getContentByType(DamageTextContent.TYPE_TEXT);
      this._start(_loc4_, 0, 0);
      var _loc6_ = this._getContentByType(DamageTextContent.TYPE_TITLE);
      if(_loc6_ != null)
      {
         this._start(this._getContentByType(DamageTextContent.TYPE_TITLE), 0, -(_loc4_.content._height + 10));
      }
      this._currentPosition = new flash.geom.Point(xPos, yPos);
   }

   // PHASE3: Reset for object pooling
   function reset()
   {
      // Call base reset
      super.reset();

      // Reset MovingDamageText-specific properties
      this._targetCharacter = null;
      this._flyingDirection = 0;
      this._speed = numbersTypes.MovingDamageText.TEXT_MIN_SPEED;
      this.columnID = -1;
      this.accelFactor = 1;
      this.accelDuration = 0;
      this._creationOrder = 0;
      this._currentPosition = null;
      this._hasPrefixSign = false;       // CUSTOMIZATION: Reset prefix flag
      this._isOtherResourceLoss = false;  // CUSTOMIZATION: Reset resource loss flag
   }

   function height()
   {
      var _loc3_ = 0;
      var _loc2_ = 0;
      while(_loc2_ < this._numContents)
      {
         _loc3_ += this._contents[_loc2_].content._y - _loc3_;
         _loc3_ += this._contents[_loc2_].content._height;
         _loc2_ = _loc2_ + 1;
      }
      return _loc3_;
   }

   function move(offset)
   {
      this._currentPosition.y += offset;
      this._container._y = this._currentPosition.y;
   }

   function set targetCharacter(value)
   {
      this._targetCharacter = value;
   }

   function get targetCharacter()
   {
      return this._targetCharacter;
   }

   function get speed()
   {
      return this._speed;
   }

   function set speed(value)
   {
      this._speed = value;
   }

   function get flyingDirection()
   {
      return this._flyingDirection;
   }

   // CUSTOMIZATION: Getter for prefix status
   function get hasPrefixSign()
   {
      return this._hasPrefixSign;
   }
}
