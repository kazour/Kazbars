class helpers.NumbersFontsCollection
{
   var htmlFontParser = com.GameInterface.Utils.ParseHTMLFontFinal;
   var defaultFont = null;
   var self_healed = null;
   var other_healed = null;
   var self_healed_critical = null;
   var other_healed_critical = null;
   var self_attacked = null;
   var other_attacked = null;
   var self_attacked_unshielded = null;
   var other_attacked_unshielded = null;
   var self_attacked_critical = null;
   var other_attacked_critical = null;
   var self_attacked_spell = null;
   var other_attacked_spell = null;
   var self_attacked_spell_critical = null;
   var other_attacked_spell_critical = null;
   var self_attacked_combo = null;
   var other_attacked_combo = null;
   var self_attacked_combo_critical = null;
   var other_attacked_combo_critical = null;
   var self_dodged = null;
   var other_dodged = null;
   var self_attacked_environment = null;
   var other_attacked_environment = null;
   var stamina_gained = null;
   var stamina_lost = null;
   var mana_gained = null;
   var mana_lost = null;
   var xp_gained = null;
   var murder_points_gained = null;
   var murder_points_gained_murderer = null;
   var self_combo_name = null;
   var other_combo_name = null;
   var stamina_gained_critical = null;
   var mana_gained_critical = null;
   var stamina_loss_critical = null;
   var mana_loss_critical = null;
   var NEGATIVE_VALUES = [12,14,21,22];
   
   // PHASE2: Array-based lookup tables for faster access
   var _selfFonts;
   var _otherFonts;
   
   function NumbersFontsCollection()
   {
      this.self_healed = this.htmlFontParser("self_healed");
      this.other_healed = this.htmlFontParser("other_healed");
      this.self_healed_critical = this.htmlFontParser("self_healed_critical");
      this.other_healed_critical = this.htmlFontParser("other_healed_critical");
      this.self_attacked = this.htmlFontParser("self_attacked");
      this.other_attacked = this.htmlFontParser("other_attacked");
      this.self_attacked_unshielded = this.htmlFontParser("self_attacked_unshielded");
      this.other_attacked_unshielded = this.htmlFontParser("other_attacked_unshielded");
      this.self_attacked_critical = this.htmlFontParser("self_attacked_critical");
      this.other_attacked_critical = this.htmlFontParser("other_attacked_critical");
      this.self_attacked_spell = this.htmlFontParser("self_attacked_spell");
      this.other_attacked_spell = this.htmlFontParser("other_attacked_spell");
      this.self_attacked_spell_critical = this.htmlFontParser("self_attacked_spell_critical");
      this.other_attacked_spell_critical = this.htmlFontParser("other_attacked_spell_critical");
      this.self_attacked_combo = this.htmlFontParser("self_attacked_combo");
      this.other_attacked_combo = this.htmlFontParser("other_attacked_combo");
      this.self_attacked_combo_critical = this.htmlFontParser("self_attacked_combo_critical");
      this.other_attacked_combo_critical = this.htmlFontParser("other_attacked_combo_critical");
      this.self_dodged = this.htmlFontParser("self_dodged");
      this.other_dodged = this.htmlFontParser("other_dodged");
      this.self_attacked_environment = this.htmlFontParser("self_attacked_environment");
      this.other_attacked_environment = this.htmlFontParser("other_attacked_environment");
      this.stamina_gained = this.htmlFontParser("stamina_gained");
      this.stamina_lost = this.htmlFontParser("stamina_lost");
      this.mana_gained = this.htmlFontParser("mana_gained");
      this.mana_lost = this.htmlFontParser("mana_lost");
      this.xp_gained = this.htmlFontParser("xp_gained");
      this.murder_points_gained = this.htmlFontParser("murder_points_gained");
      this.murder_points_gained_murderer = this.htmlFontParser("murder_points_gained_murderer");
      this.self_combo_name = this.htmlFontParser("self_combo_name");
      this.other_combo_name = this.htmlFontParser("other_combo_name");
      this.stamina_gained_critical = this.htmlFontParser("stamina_gained_critical");
      this.mana_gained_critical = this.htmlFontParser("mana_gained_critical");
      this.stamina_loss_critical = this.htmlFontParser("stamina_loss_critical");
      this.mana_loss_critical = this.htmlFontParser("mana_loss_critical");
      this.defaultFont = new com.GameInterface.HTMLFont();
      this.defaultFont.m_Color = 16777215;
      this.defaultFont.SetSize("medium");
      this.defaultFont.m_Style = "bold";
      this.defaultFont.m_Family = null;
      
      // PHASE2: Initialize lookup arrays (types 0-22)
      this._selfFonts = [
         this.self_healed,                    // 0
         this.self_healed_critical,           // 1
         this.self_attacked,                  // 2
         this.self_attacked_unshielded,       // 3
         this.self_attacked_critical,         // 4
         this.self_attacked_spell,            // 5
         this.self_attacked_spell_critical,   // 6
         this.self_attacked_combo,            // 7
         this.self_attacked_combo_critical,   // 8
         this.self_dodged,                    // 9
         this.self_attacked_environment,      // 10
         this.stamina_gained,                 // 11
         this.stamina_lost,                   // 12
         this.mana_gained,                    // 13
         this.mana_lost,                      // 14
         this.xp_gained,                      // 15
         this.murder_points_gained,           // 16
         this.murder_points_gained_murderer,  // 17
         this.self_combo_name,                // 18
         this.stamina_gained_critical,        // 19
         this.mana_gained_critical,           // 20
         this.stamina_loss_critical,          // 21
         this.mana_loss_critical              // 22
      ];
      
      this._otherFonts = [
         this.other_healed,                   // 0
         this.other_healed_critical,          // 1
         this.other_attacked,                 // 2
         this.other_attacked_unshielded,      // 3
         this.other_attacked_critical,        // 4
         this.other_attacked_spell,           // 5
         this.other_attacked_spell_critical,  // 6
         this.other_attacked_combo,           // 7
         this.other_attacked_combo_critical,  // 8
         this.other_dodged,                   // 9
         this.other_attacked_environment,     // 10
         this.stamina_gained,                 // 11
         this.stamina_lost,                   // 12
         this.mana_gained,                    // 13
         this.mana_lost,                      // 14
         this.xp_gained,                      // 15
         this.murder_points_gained,           // 16
         this.murder_points_gained_murderer,  // 17
         this.other_combo_name,               // 18
         this.stamina_gained_critical,        // 19
         this.mana_gained_critical,           // 20
         this.stamina_loss_critical,          // 21
         this.mana_loss_critical              // 22
      ];
   }
   
   // PHASE2: Array lookup instead of switch (O(1) vs O(n))
   function SelfFontSelect(textType)
   {
      if(textType >= 0 && textType < this._selfFonts.length)
      {
         return this._selfFonts[textType];
      }
      return this.self_attacked;  // Default fallback
   }
   
   // PHASE2: Array lookup instead of switch (O(1) vs O(n))
   function OtherFontSelect(textType)
   {
      if(textType >= 0 && textType < this._otherFonts.length)
      {
         return this._otherFonts[textType];
      }
      return this.other_attacked;  // Default fallback
   }
   
   function getHostilityType(playerIsTarget, textType)
   {
      if(playerIsTarget)
      {
         switch(textType)
         {
            case 0:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 1:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 2:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 3:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 4:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 5:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 6:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 7:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 8:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 9:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 10:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 11:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 12:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 13:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 14:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 15:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 16:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 17:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 18:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 19:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 20:
               return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
            case 21:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            case 22:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
            default:
               return numbersTypes.DamageTextAbstract.TYPE_HOSTILE;
         }
      }
      else
      {
         // When attacking others, everything is TYPE_FRIENDLY (from player's perspective)
         return numbersTypes.DamageTextAbstract.TYPE_FRIENDLY;
      }
   }
}
