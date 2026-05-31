class com.GameInterface.HTMLFont
{
   var m_Bold;
   var m_Color;
   var m_Family;
   var m_FlyingDirection;
   var m_Italic;
   var m_Kerning;
   var m_Size;
   var m_Speed;
   var m_Style;
   var m_Underline;
   var m_WaitOnScreen;
   function HTMLFont()
   {
      this.m_Color = 16777215;
      this.m_Size = 1;
      this.m_Family = "Arial";
      this.m_Style = "";
      this.m_Bold = false;
      this.m_Italic = false;
      this.m_Underline = false;
      this.m_Kerning = false;
      this.m_WaitOnScreen = 1;
      this.m_FlyingDirection = 1;
      this.m_Speed = 100;
   }
   function SetColor(rgb)
   {
      this.m_Color = rgb;
   }
   function SetWaitOnScreen(numSeconds)
   {
      this.m_WaitOnScreen = numSeconds;
   }
   function SetSpeed(speed)
   {
      this.m_Speed = speed;
   }
   function SetFlyingDirection(flyingDirection)
   {
      trace("Set flying direction:" + flyingDirection);
      this.m_FlyingDirection = flyingDirection;
   }
   function SetSize(fontSize)
   {
      this.m_Size = 1;
      if(fontSize == "xx-small")
      {
         this.m_Size = 0.25;
      }
      else if(fontSize == "x-small")
      {
         this.m_Size = 0.5;
      }
      else if(fontSize == "small")
      {
         this.m_Size = 0.75;
      }
      else if(fontSize == "medium")
      {
         this.m_Size = 1;
      }
      else if(fontSize == "large")
      {
         this.m_Size = 1.25;
      }
      else if(fontSize == "x-large")
      {
         this.m_Size = 1.5;
      }
      else if(fontSize == "xx-large")
      {
         this.m_Size = 1.75;
      }
      else if(fontSize == "smaller")
      {
         this.m_Size = 0.75;
      }
      else if(fontSize == "larger")
      {
         this.m_Size = 1.25;
      }
      else if(fontSize == "inherit")
      {
         this.m_Size = 1;
      }
      else if(fontSize.indexOf("px") != -1)
      {
         this.m_Size = parseInt(fontSize.substr(0,fontSize.indexOf("px")));
         this.m_Size /= 3;
      }
   }
   function SetStyle(fontStyle)
   {
      this.m_Style = fontStyle;
      this.m_Bold = fontStyle.indexOf("bold") != -1;
      this.m_Italic = fontStyle.indexOf("italic") != -1;
      this.m_Underline = fontStyle.indexOf("underline") != -1;
      this.m_Kerning = fontStyle.indexOf("kerning") != -1;
      if(fontStyle.indexOf("normal") != -1)
      {
         this.m_Bold = false;
         this.m_Italic = false;
         this.m_Underline = false;
         this.m_Kerning = false;
      }
   }
   function SetFamily(fontFamily)
   {
      this.m_Family = fontFamily;
   }
}
