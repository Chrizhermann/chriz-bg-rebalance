"""Actual generated sprite observer trampolines; Unicorn and local ML64 only."""
from pathlib import Path
import unittest
from tests.test_potion_sprite_lifetime import LifetimeHarness,read_image,BASE
from tests import test_potion_regen_lifecycle_native as reuse
from tests import test_potion_generated_trampoline as native

@unittest.skipUnless(native.EEEX and native.LIBS and native.ML64,'optional: EEex/ML64/Unicorn')
class SpriteLifetimeNativeTests(unittest.TestCase):
 setUpClass=classmethod(reuse.RegenerationLifecycleNativeTests.setUpClass.__func__)
 tearDownClass=classmethod(reuse.RegenerationLifecycleNativeTests.tearDownClass.__func__)
 initializer=reuse.RegenerationLifecycleNativeTests.initializer
 baseline=reuse.RegenerationLifecycleNativeTests.baseline
 def test_six_sites_preserve_native_replay_state_and_borrow_only_the_sprite_pointer(self):
  h=LifetimeHarness(self.image,True);p=h.render()
  self.assertEqual(8,len(h.assemblies))
  for index,(_,d) in enumerate(p.descriptors.items(),2):
   baseline=self.baseline(h,d)
   for error in (False,True):
    with self.subTest(site=d.key,error=error):
     m=native.GeneratedMachine(h,self.directory,index,{int(d.address+d.restoreSize)},
         lua_error=error,initializer=self.initializer(d))
     self.assertEqual(baseline.snapshot(),m.snapshot())
     self.assertEqual(bytes(baseline.uc.mem_read(baseline.initial_rsp,128)),bytes(m.uc.mem_read(m.initial_rsp,128)))
     self.assertEqual(bytes(baseline.uc.mem_read(m.DATA,0x10000)),bytes(m.uc.mem_read(m.DATA,0x10000)))
     self.assertEqual([m.initial['RSI' if d.key.startswith('ready') else 'RCX']],[x[1] for x in m.lua_arguments])
     self.assertEqual(1,m.watchdog_checks)

if __name__=='__main__':unittest.main()
