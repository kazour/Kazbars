class DamageNumberManager
{
   var _collection;
   var _container;
   var _fixeds;
   var _friendlyCountMonitor;
   var _hostileCountMonitor;
   var _movings;
   var _numbersScale;
   var _numbersScaleMonitor;
   var _signalGroup;
   var _elementsUID = 0;
   var _running = false;
   var _lastTime = 0;
   // CUSTOMIZATION: live camera-zoom estimate (camera->own-avatar), sampled from self-events.
   var _cameraZoom;
   
   // PHASE2: Type 9 is the only type that keeps title text (Dodge/Parry/Resist labels)
   static var KEEP_TITLE_TYPE = 9;

   // CUSTOMIZATION: Show title labels for all types (0 = only type 9, 1 = all types)
   static var SHOW_ALL_TITLES = 0;

   // CUSTOMIZATION: Enemy resource loss direction override
   // When enabled, mana/stamina you drain FROM enemies appears above their head (dir 1)
   // instead of at your fixed column position
   static var OTHER_RESOURCE_LOSS_TO_TARGET = 0;  // 0 = off, 1 = show at enemy position

   // CUSTOMIZATION: Distance-to-scale. Melee hits (real avatar->target distance below
   // RANGED_CUTOFF metres) always use AoC's untouched stock size curve. When RANGED_KEEP is
   // on, ranged hits are frozen at the cutoff-distance size so they stop shrinking with
   // distance. "Real" distance = camera->target (the only distance the game hands us) minus
   // the camera zoom, which we sample live from numbers over our own avatar (see
   // SlotCreateDamageNumber), seeded with CAMERA_ZOOM_SEED.
   static var DISTANCE_FALLOFF = 60;   // stock size curve base/vanish (fixed -- keeps melee exactly stock)
   static var RANGED_CUTOFF = 15;      // real metres; at/above this a hit counts as ranged
   static var RANGED_KEEP = 0;         // 0/1 toggle: freeze ranged hits at the cutoff-distance size
   static var CAMERA_ZOOM_SEED = 10;   // initial camera-zoom estimate until the first self-event

   // PHASE3: Object pools for memory efficiency
   var _movieClipPool;
   var _movingTextPool;
   var _fixedTextPool;
   static var POOL_BUFFER = 20;  // Fixed buffer above limit
   
   // PHASE2.5: Creation order counter
   var _creationCounter = 0;

   // CUSTOMIZATION: Client character ID for resource loss detection
   // We capture this from defenderIsClient=true events since GetClientCharacter() returns different format
   var _clientCharacterID = -1;
   var _clientCharIDCaptured = false;
   
   function DamageNumberManager(container)
   {
      this._container = container;
      this._fixeds = new numbersManagers.FixedManager(com.helperFramework.utils.Relegate.create(this, this._onListEmpty));
      this._movings = new numbersManagers.MovingManager(com.helperFramework.utils.Relegate.create(this, this._onListEmpty));
      this._container.onLoad = com.helperFramework.utils.Relegate.create(this, this._init);
      this._container.onUnload = com.helperFramework.utils.Relegate.create(this, this._destroy);
   }
   
   function _init()
   {
      this._collection = new helpers.NumbersFontsCollection();
      this._cameraZoom = DamageNumberManager.CAMERA_ZOOM_SEED;
      this._signalGroup = new com.Utils.SignalGroup();
      com.GlobalSignal.SignalDamageInfo.Connect(this._signalGroup, com.helperFramework.utils.Relegate.create(this, this.SlotCreateDamageNumber));
      com.GlobalSignal.SignalDestroyDamageInfo.Connect(this._signalGroup, this.SlotClearAllNumbers);
      
      this._numbersScaleMonitor = com.GameInterface.DistributedValue.Create("DamageNumberSize");
      this._numbersScaleMonitor.SignalChanged.Connect(this._signalGroup, com.helperFramework.utils.Relegate.create(this, this._onNumbersSizeChange));
      this._onNumbersSizeChange();
      
      this._friendlyCountMonitor = com.GameInterface.DistributedValue.Create("DamageNumberFriendlyCount");
      this._friendlyCountMonitor.SignalChanged.Connect(this._signalGroup, com.helperFramework.utils.Relegate.create(this, this._onMaxFriendlyNumbersChange));
      this._onMaxFriendlyNumbersChange();
      
      this._hostileCountMonitor = com.GameInterface.DistributedValue.Create("DamageNumberHostileCount");
      this._hostileCountMonitor.SignalChanged.Connect(this._signalGroup, com.helperFramework.utils.Relegate.create(this, this._onMaxHostileNumbersChange));
      this._onMaxHostileNumbersChange();
      
      // PHASE3: Initialize object pools AFTER settings are read
      this._initializePools();
      
      // PHASE3: Set release callbacks for managers
      this._fixeds.setReleaseCallback(com.helperFramework.utils.Relegate.create(this, this.releaseToPool));
      this._movings.setReleaseCallback(com.helperFramework.utils.Relegate.create(this, this.releaseToPool));

      // CUSTOMIZATION: Client character ID will be captured from first defenderIsClient=true event
   }
   
   // PHASE3: Create and populate object pools based on settings
   function _initializePools()
   {
      var maxNeeded = Math.max(this._movings._maxHostileNumbers, this._movings._maxFriendlyNumbers);
      var poolSize = maxNeeded + DamageNumberManager.POOL_BUFFER;
      
      // MovieClip pool for containers
      this._movieClipPool = new helpers.ObjectPool(
         poolSize,
         com.helperFramework.utils.Relegate.create(this, this._createMovieClip),
         com.helperFramework.utils.Relegate.create(this, this._resetMovieClip)
      );
      this._movieClipPool.initialize();
      
      // MovingDamageText object pool
      this._movingTextPool = new helpers.ObjectPool(
         poolSize,
         com.helperFramework.utils.Relegate.create(this, this._createMovingText),
         null  // Reset handled by object itself via reset() method
      );
      this._movingTextPool.initialize();
      
      // FixedDamageText pool (fewer needed - max 10 static numbers)
      this._fixedTextPool = new helpers.ObjectPool(
         numbersManagers.FixedManager.MAX_STATIC_NUMBERS + 5,
         com.helperFramework.utils.Relegate.create(this, this._createFixedText),
         null  // Reset handled by object itself via reset() method
      );
      this._fixedTextPool.initialize();
      
      trace("DamageInfo: Pools initialized - Moving/MovieClip: " + poolSize + ", Fixed: " + (numbersManagers.FixedManager.MAX_STATIC_NUMBERS + 5));
   }
   
   // PHASE3: Factory function for MovieClips
   function _createMovieClip()
   {
      return this._container.createEmptyMovieClip("_DamageText" + this._container.UID() + this._container.getNextHighestDepth(), this._container.getNextHighestDepth());
   }
   
   // PHASE3: Reset function for MovieClips
   function _resetMovieClip(clip)
   {
      // Reset properties
      clip._alpha = 0;
      clip._x = 0;
      clip._y = 0;
      clip._xscale = 100;
      clip._yscale = 100;
      
      // Remove all attached movies (content clips)
      for(var i = 0; i < 10; i++)  // Max 2 contents (title + text)
      {
         var childClip = clip["damageText" + i];
         if(childClip != undefined)
         {
            childClip.removeMovieClip();
         }
      }
   }
   
   // PHASE3: Factory function for MovingDamageText
   function _createMovingText()
   {
      return new numbersTypes.MovingDamageText(this._elementsUID++);
   }
   
   // PHASE3: Factory function for FixedDamageText
   function _createFixedText()
   {
      return new numbersTypes.FixedDamageText(this._elementsUID++);
   }
   
   // PHASE3: Check if pools need expansion when settings change
   function _checkPoolSize()
   {
      if(this._movieClipPool == null)
      {
         return undefined;  // Pools not initialized yet
      }
      
      var maxNeeded = Math.max(this._movings._maxHostileNumbers, this._movings._maxFriendlyNumbers);
      var newSize = maxNeeded + DamageNumberManager.POOL_BUFFER;
      
      if(newSize > this._movieClipPool.capacity)
      {
         var expansion = newSize - this._movieClipPool.capacity;
         this._movieClipPool.expand(expansion);
         this._movingTextPool.expand(expansion);
         trace("DamageInfo: Pools expanded by " + expansion + " to " + newSize);
         // Don't expand fixed pool - it's based on MAX_STATIC_NUMBERS, not limits
      }
   }
   
   function _onNumbersSizeChange()
   {
      // PHASE5: Validate input from DistributedValue
      var value = this._numbersScaleMonitor.GetValue();
      if(value == null || value == undefined || isNaN(Number(value)))
      {
         value = 1;  // Default scale
      }
      value = Math.max(0.5, Math.min(Number(value), 3));  // Clamp 0.5-3

      this._numbersScale = value;
      this._movings.movingOffset = this._numbersScale;
   }

   function _onMaxHostileNumbersChange()
   {
      // PHASE5: Validate input from DistributedValue
      var value = this._hostileCountMonitor.GetValue();
      if(value == null || value == undefined || isNaN(Number(value)))
      {
         value = 50;  // Default
      }
      value = Math.max(1, Math.min(Number(value), 200));  // Clamp 1-200

      this._movings.setMaxNumbersByType(numbersTypes.DamageTextAbstract.TYPE_HOSTILE, value);
      this._checkPoolSize();  // PHASE3: Expand pool if needed
   }

   function _onMaxFriendlyNumbersChange()
   {
      // PHASE5: Validate input from DistributedValue
      var value = this._friendlyCountMonitor.GetValue();
      if(value == null || value == undefined || isNaN(Number(value)))
      {
         value = 50;  // Default
      }
      value = Math.max(1, Math.min(Number(value), 200));  // Clamp 1-200

      this._movings.setMaxNumbersByType(numbersTypes.DamageTextAbstract.TYPE_FRIENDLY, value);
      this._checkPoolSize();  // PHASE3: Expand pool if needed
   }
   
   function SlotClearAllNumbers()
   {
      this._clear();
   }
   
   function SlotCreateDamageNumber(characterID, textContent, x, y, points, distance, defenderIsClient, flyingTextType)
   {
      if(textContent == null)
      {
         textContent = "";
      }
      
      var _loc5_ = "";
      
      // CUSTOMIZATION: Keep title text based on SHOW_ALL_TITLES setting
      // When SHOW_ALL_TITLES = 1, show labels like "CRITICAL", "MANA", etc. for all types
      // When SHOW_ALL_TITLES = 0, only type 9 (Dodge/Parry/Resist) shows labels
      if(points != 0)
      {
         if((DamageNumberManager.SHOW_ALL_TITLES == 1 || flyingTextType == DamageNumberManager.KEEP_TITLE_TYPE) && textContent.length > 0)
         {
            _loc5_ = textContent;
         }

         textContent = String(Math.abs(points));
         if(this._isNumberSigned(flyingTextType))
         {
            if(points >= 0)
            {
               textContent = "+" + textContent;
            }
            else
            {
               textContent = "-" + textContent;
            }
         }
      }
      else
      {
         // points == 0: Show title only (no number)
         if(DamageNumberManager.SHOW_ALL_TITLES == 1 || flyingTextType == DamageNumberManager.KEEP_TITLE_TYPE)
         {
            _loc5_ = textContent;
            textContent = "";  // Clear to avoid showing title twice
         }
      }
      
      if(com.helperFramework.utils.ArrayUtils.isInArray(flyingTextType, this._collection.NEGATIVE_VALUES))
      {
         textContent = "-" + textContent;
      }
      
      var _loc4_ = null;
      if(defenderIsClient)
      {
         _loc4_ = this._collection.SelfFontSelect(flyingTextType);
      }
      else
      {
         _loc4_ = this._collection.OtherFontSelect(flyingTextType);
      }
      
      if(_loc4_ == null)
      {
         trace("DamageInfo: Fatal error: no font was found");
         return undefined;
      }
      
      // CUSTOMIZATION: distance-to-scale (single "keep ranged numbers big" knob).
      // Sample camera zoom from numbers over our own avatar (there distance == camera->self);
      // skip resource-loss types, which the game flags defenderIsClient even when they land
      // on an enemy (so their distance is camera->enemy, not the zoom).
      if(defenderIsClient && !this._isResourceLossType(flyingTextType))
      {
         this._cameraZoom = distance;
      }
      var realDist = distance - this._cameraZoom;  // ~ avatar->target, in real metres
      // Stock size curve (the melee path, untouched): full near, linear to nothing at DISTANCE_FALLOFF.
      var sizeBase = Math.max(0, DamageNumberManager.DISTANCE_FALLOFF - distance);
      if(realDist >= DamageNumberManager.RANGED_CUTOFF && DamageNumberManager.RANGED_KEEP > 0)
      {
         // Ranged + toggle on: freeze the size at what a hit at the cutoff distance gets,
         // so ranged numbers stop shrinking past ~15 real metres.
         var cutoffDist = this._cameraZoom + DamageNumberManager.RANGED_CUTOFF;
         sizeBase = Math.max(0, DamageNumberManager.DISTANCE_FALLOFF - cutoffDist);
      }
      var _loc7_ = sizeBase * this._numbersScale * 0.5;
      
      // PHASE3: Acquire MovieClip from pool instead of creating
      var _loc8_ = this._movieClipPool.acquire();
      
      // PHASE3: Acquire DamageText object from appropriate pool
      // Use numeric literal (0) instead of helpers.DamageNumberType.STATIC for reliable comparison
      var _loc3_;
      if(_loc4_.m_FlyingDirection == 0)
      {
         _loc3_ = this._fixedTextPool.acquire();
         _loc3_.changeID(this._elementsUID);  // Reuse existing object with new ID
      }
      else
      {
         _loc3_ = this._movingTextPool.acquire();
         _loc3_._id = this._elementsUID;  // Reuse existing object with new ID
         numbersTypes.MovingDamageText(_loc3_).targetCharacter = characterID;

         // PHASE2.5: Assign creation order
         numbersTypes.MovingDamageText(_loc3_)._creationOrder = this._creationCounter;
         this._creationCounter = this._creationCounter + 1;

         // CUSTOMIZATION: Flag enemy resource loss for direction override
         // Capture player's character ID from the first defenderIsClient=true event
         // (defenderIsClient is true for ALL resource events, but characterID differs)
         var eventCharID = this._getCharacterID(characterID);
         if(!this._clientCharIDCaptured && defenderIsClient && eventCharID != -1)
         {
            this._clientCharacterID = eventCharID;
            this._clientCharIDCaptured = true;
         }

         // Now check if this is enemy resource loss
         if(this._isResourceLossType(flyingTextType) && this._clientCharIDCaptured)
         {
            var isEnemyResourceLoss = (eventCharID != this._clientCharacterID && eventCharID != -1);
            if(isEnemyResourceLoss)
            {
               numbersTypes.MovingDamageText(_loc3_)._isOtherResourceLoss = true;
            }
         }
      }

      this._elementsUID = this._elementsUID + 1;
      _loc3_.hostilityType = this._collection.getHostilityType(defenderIsClient, flyingTextType);

      // Generate the damage text
      _loc3_.generate(_loc8_, x, y, _loc4_, _loc5_, textContent, _loc7_);
      
      this._addElement(_loc3_);
   }
   
   function _addElement(newNumber)
   {
      // Use numeric literals: 0 = STATIC, 1 = MOVING
      var _loc3_;
      if(newNumber.TYPE == 0)
      {
         _loc3_ = this._fixeds.addElement(numbersTypes.FixedDamageText(newNumber));
         numbersTypes.FixedDamageText(newNumber).setPosition(_loc3_);
         this._fixeds.showElement(newNumber);
      }
      else if(newNumber.TYPE == 1)
      {
         this._movings.addElement(numbersTypes.MovingDamageText(newNumber));
         this._movings.showElement(newNumber);
      }
      
      if(!this._running && (this._movings.numElements > 0 || this._fixeds.numElements > 0))
      {
         this._startLoop();
      }
   }

   // Single timing source: one onEnterFrame on the container clip (replaces setInterval + TweenLite).
   function _startLoop()
   {
      this._running = true;
      this._lastTime = getTimer();
      this._container.onEnterFrame = com.helperFramework.utils.Relegate.create(this, this._update);
   }

   function _stopLoop()
   {
      this._running = false;
      delete this._container.onEnterFrame;
   }

   function _update()
   {
      var _loc3_ = getTimer();
      var _loc2_ = _loc3_ - this._lastTime;  // elapsed ms (drives pop-in/fade easing)
      this._lastTime = _loc3_;
      if(_loc2_ < 0)
      {
         _loc2_ = 0;
      }
      else if(_loc2_ > 100)
      {
         _loc2_ = 100;  // cap catch-up after an alt-tab/stall so numbers don't teleport or mass-expire in one frame
      }
      var _loc4_ = _loc2_ / 15;  // frame-equivalent modifier (drives ttl + movement, as the old 15ms tick did)

      if(this._movings.numElements > 0)
      {
         this._movings.update(_loc2_, _loc4_);
      }
      if(this._fixeds.numElements > 0)
      {
         this._fixeds.update(_loc2_, _loc4_);
      }

      // Self-defending stop: halt the loop whenever both lists are empty (incl. fading),
      // independent of the per-manager empty callback timing.
      if(this._movings.numElements <= 0 && this._fixeds.numElements <= 0)
      {
         this._stopLoop();
      }
   }

   function _onListEmpty()
   {
      if(this._movings.numElements <= 0 && this._fixeds.numElements <= 0)
      {
         this._stopLoop();
      }
   }

   function _clear()
   {
      this._movings.destroy();
      this._fixeds.destroy();
      this._stopLoop();
   }
   
   function _isNumberSigned(textType)
   {
      switch(textType)
      {
         case 0:
         case 1:
         case 11:
         case 13:
         case 15:
         case 16:
         case 17:
            return true;
         default:
            return false;
      }
   }

   // CUSTOMIZATION: Check if type is resource loss (mana/stamina drain)
   // Types: 12 = stamina_lost, 14 = mana_lost, 21 = stamina_loss_critical, 22 = mana_loss_critical
   function _isResourceLossType(textType)
   {
      return textType == 12 || textType == 14 || textType == 21 || textType == 22;
   }

   // CUSTOMIZATION: Extract numeric ID from character/ID32 object
   function _getCharacterID(target)
   {
      if(target == null || target == undefined)
      {
         return -1;
      }
      // ID32 object has m_Instance property
      if(target.m_Instance != undefined)
      {
         return target.m_Instance;
      }
      // ID32 object has GetInstance method
      if(typeof(target.GetInstance) == "function")
      {
         return target.GetInstance();
      }
      // Character object might have GetID method
      if(typeof(target.GetID) == "function")
      {
         return target.GetID();
      }
      // Try numeric conversion
      var num = Number(target);
      if(!isNaN(num))
      {
         return num;
      }
      return -1;
   }

   // PHASE3: Release object back to pool
   function releaseToPool(damageText)
   {
      if(damageText == null)
      {
         return undefined;
      }
      
      // Store container reference before reset
      var container = damageText.container;
      
      // Reset the damage text object (clears its state)
      damageText.reset();
      
      // Release to appropriate pool (0 = STATIC, 1 = MOVING)
      if(damageText.TYPE == 1)
      {
         this._movingTextPool.release(damageText);
      }
      else if(damageText.TYPE == 0)
      {
         this._fixedTextPool.release(damageText);
      }
      
      // Release MovieClip to pool
      if(container != null)
      {
         this._movieClipPool.release(container);
      }
   }
   
   function get container()
   {
      return this._container;
   }
   
   function _destroy()
   {
      this._signalGroup.DisconnectAll();
      this._clear();
   }
}
