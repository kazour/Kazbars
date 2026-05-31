class numbersManagers.AbstractManager
{
   var _elements;
   var _numElements;
   var _onEmptyCallback;

   // Callback to release spent objects back to the manager's pool
   var _releaseCallback;

   // Elements in their fade-out phase, advanced independently of the live list
   var _fading;
   var _numFading;

   // CUSTOMIZATION: Animation timing (seconds) and easing
   static var SHOW_DURATION = 0.2;
   static var FADE_DURATION = 0.2;
   static var EASING_TYPE = 0;  // 0=Quad, 1=Cubic, 2=Quart

   // Easing functions (standard AS2 signature: t=time, b=begin, c=change, d=duration)
   static function easeQuad(t, b, c, d)
   {
      t = t / d;
      return -c * t * (t - 2) + b;
   }

   static function easeCubic(t, b, c, d)
   {
      t = t / d - 1;
      return c * (t * t * t + 1) + b;
   }

   static function easeQuart(t, b, c, d)
   {
      t = t / d - 1;
      return -c * (t * t * t * t - 1) + b;
   }

   static function getEase()
   {
      if(numbersManagers.AbstractManager.EASING_TYPE == 1) return numbersManagers.AbstractManager.easeCubic;
      if(numbersManagers.AbstractManager.EASING_TYPE == 2) return numbersManagers.AbstractManager.easeQuart;
      return numbersManagers.AbstractManager.easeQuad;
   }

   function AbstractManager(onEmptyCallback)
   {
      this._onEmptyCallback = onEmptyCallback;
      this._elements = [];
      this._numElements = 0;
      this._releaseCallback = null;
      this._fading = [];
      this._numFading = 0;
   }

   function setReleaseCallback(callback)
   {
      this._releaseCallback = callback;
   }

   function addElement(element)
   {
      this._elements[this._numElements] = element;
      this._numElements = this._numElements + 1;
   }

   // Begin the pop-in. No tween: the single onEnterFrame loop advances it via _animateElement.
   function showElement(element)
   {
      element.beginShow();
   }

   function update()
   {
      // overridden by Moving/Fixed managers; live signature is update(dtMs, mod)
   }

   // Step every fading element; release the ones whose fade has completed.
   function _updateFading(dtMs)
   {
      var _loc4_ = numbersManagers.AbstractManager.getEase();
      var _loc5_ = numbersManagers.AbstractManager.FADE_DURATION * 1000;
      var _loc2_ = this._numFading - 1;
      while(_loc2_ >= 0)
      {
         var _loc3_ = this._fading[_loc2_];
         if(_loc3_ == null || _loc3_.stepFade(dtMs, _loc4_, _loc5_))
         {
            this._deleteElement(_loc3_);
            this._numFading = this._numFading - 1;
            if(_loc2_ != this._numFading)
            {
               this._fading[_loc2_] = this._fading[this._numFading];
            }
            this._fading[this._numFading] = null;
         }
         _loc2_ = _loc2_ - 1;
      }
   }

   // Step the pop-in for an element still in its IN phase. No-op once LIVE.
   function _animateElement(element, dtMs)
   {
      if(element.phase == 0)
      {
         element.stepShow(dtMs, numbersManagers.AbstractManager.getEase(), numbersManagers.AbstractManager.SHOW_DURATION * 1000);
      }
   }

   function destroy()
   {
      var _loc2_;
      if(this._elements && this._numElements > 0)
      {
         _loc2_ = this._numElements - 1;
         while(_loc2_ >= 0)
         {
            this._deleteElement(this._elements[_loc2_]);
            _loc2_ = _loc2_ - 1;
         }
      }
      _loc2_ = this._numFading - 1;
      while(_loc2_ >= 0)
      {
         this._deleteElement(this._fading[_loc2_]);
         _loc2_ = _loc2_ - 1;
      }
      this._elements = [];
      this._numElements = 0;
      this._fading = [];
      this._numFading = 0;
   }

   function _checkElementLife(element, mod)
   {
      return element.updateLife(mod);
   }

   // Move a spent element into the fading list (no tween, no onComplete callback).
   function _removeElement(oldNumber, offsetY)
   {
      oldNumber.beginFade(offsetY);
      this._fading[this._numFading] = oldNumber;
      this._numFading = this._numFading + 1;
   }

   function _deleteElement(oldNumber)
   {
      if(oldNumber == null)
      {
         return undefined;
      }
      if(this._releaseCallback != null)
      {
         this._releaseCallback(oldNumber);
      }
      else
      {
         oldNumber.destroy();
      }
   }

   // Active count includes fading elements, so the loop runs until every fade finishes.
   function get numElements()
   {
      return this._numElements + this._numFading;
   }
}
