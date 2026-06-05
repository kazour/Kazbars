class numbersTypes.DamageTextAbstract
{
   var _container;
   var _contents;
   var _currentPosition;
   var _font;
   var _id;
   var _numContents;
   var _scale;
   var _ttl;
   static var TYPE_HOSTILE = 1;
   static var TYPE_FRIENDLY = 0;
   // One size factor for both number and label, applied via the contentScale setter so
   // it survives the pop-in/fade. Ships at 1 (== game default) so a 0 offset leaves them
   // at their current on-screen size; the panel "Size" slider bakes an offset on top.
   var DEFAULT_TEXT_SCALE = 1;

   // Vertical gap (px) between a number and its shown label, added on top of half of
   // each one's height. 0 = the label tucks right against the number.
   static var TITLE_GAP = 0;

   var _contentScale = 100;

   // Shared DropShadowFilter — distance (arg 1) and blur (args 5,6) are bake targets.
   static var SHADOW_FILTER = new flash.filters.DropShadowFilter(4,45,0,100,3,3,40,3,false,false,false);

   // CUSTOMIZATION: Shadow rendering mode. 0=None, 1=Fast (offset dark twin), 2=Real (DropShadowFilter)
   static var SHADOW_MODE = 2;

   // Properties needed for pooling
   var hostilityType;
   var TYPE;

   // Animation phase: 0=IN (pop-in), 1=LIVE, 2=OUT (fade). Stepped by the single onEnterFrame loop.
   var _phase = 1;
   var _animMs = 0;
   var _fadeFromAlpha = 0;
   var _fadeFromY = 0;
   var _fadeFromScale = 0;
   var _fadeOffsetY = 0;

   function DamageTextAbstract(id)
   {
      this._id = id;
      this._contents = [];
      this._numContents = 0;
      this.hostilityType = 0;
   }

   function generate(parentClip, xPos, yPos, htmlFont, title, text, scale)
   {
      if(text == null && title != null)
      {
         text = title;
         title = null;
      }
      this._container = parentClip;
      this._font = htmlFont;
      this._scale = scale;
      this._ttl = this._font.m_WaitOnScreen * 60;
      this._container._x = xPos;
      this._addContent(this._generateContent(DamageTextContent.TYPE_TITLE, title, this.DEFAULT_TEXT_SCALE));
      this._addContent(this._generateContent(DamageTextContent.TYPE_TEXT, text, this.DEFAULT_TEXT_SCALE));

      // Real shadow is a per-clip filter; Fast shadow is a twin built in _generateContent; None adds nothing.
      if(numbersTypes.DamageTextAbstract.SHADOW_MODE == 2)
      {
         this._container.filters = [numbersTypes.DamageTextAbstract.SHADOW_FILTER];
      }
   }

   // Reset object state for pooling (instead of destroy)
   function reset()
   {
      var _loc2_;
      var _loc3_ = this._numContents - 1;
      while(_loc3_ >= 0)
      {
         _loc2_ = this._contents[_loc3_];
         if(_loc2_ != null)
         {
            _loc2_.content.removeMovieClip();  // removes any Fast-shadow child with it
            _loc2_ = null;
         }
         _loc3_ = _loc3_ - 1;
      }
      this._contents = [];
      this._numContents = 0;

      this._font = null;
      this._scale = 0;
      this._ttl = 0;
      this._contentScale = 100;
      this._currentPosition = null;
      this.hostilityType = 0;
      this._phase = 1;
      this._animMs = 0;

      this._container = null;
   }

   function destroy()
   {
      this.reset();
   }

   function set contentScale(value)
   {
      this._contentScale = value;
      var _loc2_ = 0;
      while(_loc2_ < this._numContents)
      {
         // Keep each content's own size factor on top of the shared animated scale —
         // without it the pop-in flattens it out and DEFAULT_TEXT_SCALE (the "Size"
         // slider) does nothing.
         this._contents[_loc2_]._xscale = this._contents[_loc2_]._yscale = this._contentScale * this._contents[_loc2_].scale;
         _loc2_ = _loc2_ + 1;
      }
   }

   function updateLife(intervalModifyer)
   {
      this._ttl -= intervalModifyer;
      if(this._ttl <= 0)
      {
         return false;
      }
      return true;
   }

   // ---- Single-loop animation phases (replace TweenLite) -------------------

   // Pop-in: alpha 0->100, contentScale scale*0.5 -> scale, over SHOW_DURATION.
   function beginShow()
   {
      this._phase = 0;
      this._animMs = 0;
      this._container._alpha = 0;
      this.contentScale = this._scale * 0.5;
   }

   function stepShow(dtMs, easeFn, durMs)
   {
      this._animMs += dtMs;
      if(durMs <= 0 || this._animMs >= durMs)
      {
         this._container._alpha = 100;
         this.contentScale = this._scale;
         this._phase = 1;
         return undefined;
      }
      this._container._alpha = easeFn(this._animMs, 0, 100, durMs);
      this.contentScale = easeFn(this._animMs, this._scale * 0.5, this._scale * 0.5, durMs);
   }

   // Fade-out: alpha -> 30, y drifts by -offsetY, contentScale -> scale*0.7, over FADE_DURATION.
   function beginFade(offsetY)
   {
      this._phase = 2;
      this._animMs = 0;
      this._fadeFromAlpha = this._container._alpha;
      this._fadeFromY = this._container._y;
      this._fadeFromScale = this._contentScale;
      this._fadeOffsetY = offsetY;
   }

   // Returns true when the fade has completed.
   function stepFade(dtMs, easeFn, durMs)
   {
      this._animMs += dtMs;
      if(durMs <= 0)
      {
         return true;
      }
      if(this._animMs >= durMs)
      {
         this._container._alpha = 30;
         this._container._y = this._fadeFromY - this._fadeOffsetY;
         this.contentScale = this._scale * 0.7;
         return true;
      }
      this._container._alpha = easeFn(this._animMs, this._fadeFromAlpha, 30 - this._fadeFromAlpha, durMs);
      this._container._y = easeFn(this._animMs, this._fadeFromY, - this._fadeOffsetY, durMs);
      this.contentScale = easeFn(this._animMs, this._fadeFromScale, this._scale * 0.7 - this._fadeFromScale, durMs);
      return false;
   }

   // -------------------------------------------------------------------------

   function _addContent(newContent)
   {
      if(newContent == null)
      {
         return undefined;
      }
      this._contents[this._numContents] = newContent;
      this._numContents = this._numContents + 1;
   }

   function _getContentByType(type)
   {
      var _loc2_ = 0;
      while(_loc2_ < this._numContents)
      {
         if(this._contents[_loc2_].type == type)
         {
            return this._contents[_loc2_];
         }
         _loc2_ = _loc2_ + 1;
      }
      return null;
   }

   function _generateContent(type, content, scaleOffset)
   {
      if(content == undefined || content == null || content == "")
      {
         return null;
      }
      var _loc2_ = new DamageTextContent(type, this._container.attachMovie("DamageText", "damageText" + this._numContents, this._container.getNextHighestDepth()));
      var _loc3_ = new TextFormat();
      _loc3_.color = this._font.m_Color;
      _loc3_.bold = this._font.m_Bold;
      _loc3_.italic = this._font.m_Italic;
      _loc3_.underline = this._font.m_Underline;
      _loc3_.kerning = this._font.m_Kerning;
      _loc2_.label.autoSize = true;
      _loc2_.label.setNewTextFormat(_loc3_);
      _loc2_.label.text = content;
      _loc2_.scale = scaleOffset;
      _loc2_._xscale = _loc2_._yscale = this._scale * scaleOffset;
      _loc2_.label._x = (- _loc2_.label._width) * 0.5;
      _loc2_.label._y = (- _loc2_.label._height) * 0.5;

      // Fast shadow: a dark twin attached just below the label, inside the content clip,
      // so it scales/positions/fades with the number for free (no per-frame filter cost).
      if(numbersTypes.DamageTextAbstract.SHADOW_MODE == 1)
      {
         var _loc4_ = numbersTypes.DamageTextAbstract.SHADOW_FILTER.distance * 0.707;
         var _loc5_ = _loc2_.content.attachMovie("DamageText", "kzShadow", _loc2_.label.getDepth() - 1);
         var _loc6_ = new TextFormat();
         _loc6_.color = 0;
         _loc6_.bold = this._font.m_Bold;
         _loc6_.italic = this._font.m_Italic;
         _loc6_.underline = this._font.m_Underline;
         _loc6_.kerning = this._font.m_Kerning;
         _loc5_.label.autoSize = true;
         _loc5_.label.setNewTextFormat(_loc6_);
         _loc5_.label.text = content;
         _loc5_.label._x = (- _loc5_.label._width) * 0.5;
         _loc5_.label._y = (- _loc5_.label._height) * 0.5;
         _loc5_._x = _loc4_;
         _loc5_._y = _loc4_;
      }
      return _loc2_;
   }

   function _start(target, offsetX, offsetY)
   {
      if(!target)
      {
         return undefined;
      }
      if(!offsetX || offsetX == null || offsetX == undefined)
      {
         offsetX = 0;
      }
      if(!offsetY || offsetY == null || offsetY == undefined)
      {
         offsetY = 0;
      }
      target._x = offsetX;
      target._y = offsetY;
   }

   function get contentScale()
   {
      return this._contentScale;
   }

   function get phase()
   {
      return this._phase;
   }

   function get id()
   {
      return this._id;
   }

   function get ttl()
   {
      return this._ttl;
   }

   function get container()
   {
      return this._container;
   }

   function get scale()
   {
      return this._scale;
   }

   function get currentPosition()
   {
      return this._currentPosition;
   }
}
