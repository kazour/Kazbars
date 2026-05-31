class DamageTextContent
{
   var _content;
   var _label;
   var _type;
   static var TYPE_TITLE = "title";
   static var TYPE_TEXT = "text";
   function DamageTextContent(type, content)
   {
      this._type = type;
      this._content = content;
      this._label = this._content.label;
   }
   function get type()
   {
      return this._type;
   }
   function get label()
   {
      return this._label;
   }
   function get _xscale()
   {
      return this._content._xscale;
   }
   function get _yscale()
   {
      return this._content._yscale;
   }
   function set _xscale(value)
   {
      this._content._xscale = value;
   }
   function set _yscale(value)
   {
      this._content._yscale = value;
   }
   function get _x()
   {
      return this._content._x;
   }
   function get _y()
   {
      return this._content._y;
   }
   function set _x(value)
   {
      this._content._x = value;
   }
   function set _y(value)
   {
      this._content._y = value;
   }
   function get _alpha()
   {
      return this._content._alpha;
   }
   function set _alpha(value)
   {
      this._content._alpha = value;
   }
   function get content()
   {
      return this._content;
   }
}
