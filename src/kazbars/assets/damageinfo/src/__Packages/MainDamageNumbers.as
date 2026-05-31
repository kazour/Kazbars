class MainDamageNumbers
{
   static var _flash;
   static var _manager;
   function MainDamageNumbers()
   {
   }
   static function main(swfRoot)
   {
      MainDamageNumbers._flash = swfRoot;
      MainDamageNumbers._manager = new DamageNumberManager(MainDamageNumbers._flash.attachMovie("NumbersContainer","numbersContainer",MainDamageNumbers._flash.getNextHighestDepth()));
   }
}
