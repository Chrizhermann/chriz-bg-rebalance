"""Inert descriptor and real EEex preprocessing checks; no native DLL/game."""
from pathlib import Path
import unittest

from tests.test_potion_transport_preprocessor import TransportHarness, read_image, BASE, inspect_paths
from tests.test_potion_hook_preprocessor import EEEX, instructions

MODULE = Path(__file__).resolve().parents[1]/"research/prototypes/potion-admission/CBRPQRegenLifecycle.lua"
CALLBACKS=("updateEnter","naturalDeath","beforeRemove","updateExit","clear","removeType",
           "replace","listDestroy","cacheDestroy","copy","appendOwned","append")

class LifecycleHarness(TransportHarness):
    def __init__(self,image,watchdog=False):
        super().__init__(image,watchdog)
        for key in CALLBACKS:
            self.lua.execute(f"function CBRPQRegen_{key}(...) end")
        self.config=self.lua.table_from({"callbacks":self.lua.table_from({k:"CBRPQRegen_"+k for k in CALLBACKS})})
        self.hook=self.lua.execute(MODULE.read_text())
    def prepare(self):
        return self.hook.prepare(self.lua.globals(),self.config,self.watchdog)
    def render(self,plan=None):
        plan=plan or self.prepare()
        # Only test doubles capture JIT/code writes. Production module has no
        # install/JIT method: this composition exists solely in the test.
        self.lua.globals().regenPlan=plan
        self.lua.globals().regenWatchdog=self.watchdog
        self.lua.execute("""
            regenWatchdog.withPreservation(_G,function()
                for _,d in ipairs(regenPlan.descriptors) do
                    EEex_HookBeforeRestoreWithLabels(d.address,0,d.restoreSize,d.restoreSize,d.labels,d.assembly)
                end
            end)
        """)
        return plan

@unittest.skipUnless(EEEX,"optional: set EEEX_LUA_DIR for real offline preprocessing")
class RegenerationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.image=read_image()
    def test_preparation_validates_but_never_jits_or_writes_or_registers_callbacks(self):
        h=LifecycleHarness(self.image)
        p=h.prepare()
        self.assertEqual(17,len(p.descriptors))
        self.assertEqual([],h.assemblies)
        self.assertEqual([],h.patches)
        self.assertEqual([],h.protection)
        self.assertIsNone(h.hook.install)
    def test_every_pinned_site_context_and_vtable_drift_fails_before_generation(self):
        initial=LifecycleHarness(self.image)
        addresses=[int(g[2]) for _,g in initial.hook.guards.items()]+[int(v[1]) for _,v in initial.hook.vtables.items()]
        for rva in addresses:
            with self.subTest(rva=hex(rva)):
                h=LifecycleHarness(self.image)
                h.image[rva]^=1
                with self.assertRaisesRegex(Exception,"unsupported"): h.prepare()
                self.assertEqual([],h.assemblies)
                self.assertEqual([],h.patches)
    def test_watchdog_and_callback_capabilities_checked_before_preparation(self):
        h=LifecycleHarness(self.image,True)
        with self.assertRaisesRegex(Exception,"watchdog preservation helper"):
            h.hook.prepare(h.lua.globals(),h.config)
        h.config.callbacks.copy="MISSING"
        with self.assertRaisesRegex(Exception,"callback must exist"): h.prepare()
        self.assertEqual(2,len(h.assemblies)) # watchdog's capture-only helper generation
        self.assertEqual([],h.patches)
    def test_all_generated_paths_balance_preserve_volatile_state_and_leave_calls_in_place(self):
        h=LifecycleHarness(self.image)
        p=h.render()
        self.assertEqual(17,len(h.assemblies))
        for i,(_,d) in enumerate(p.descriptors.items()):
            with self.subTest(site=d.key):
                text,state=h.assemblies[i]
                self.assertNotIn("#",text)
                exits,calls,indirect=inspect_paths(text,int(d.stackMod),set())
                self.assertEqual({int(d.address+d.restoreSize)},exits)
                self.assertEqual(set(),indirect)
                self.assertTrue(calls)
                for reg in ("rax","rcx","rdx","r8","r9","r10","r11"):
                    self.assertIn("push "+reg,instructions(text))
                    self.assertIn("pop "+reg,instructions(text))
                self.assertIn("pushfq",instructions(text)); self.assertIn("popfq",instructions(text))
                self.assertEqual(int(d.stackMod),state["curStackTop"])
                self.assertEqual(0,state["shadowSpaceStackTop"])
                for j in range(6): self.assertIn(f"movdqu xmm{j},",text)
        # BeforeRemove ends immediately before original RemoveAt CALL; Apply98
        # is observed only AFTER the original AddTail CALL has returned.
        self.assertEqual(0xE8,self.image[0x226564])
        self.assertEqual(0xE8,self.image[0x1BEDE0])
        self.assertNotIn(BASE+0x226564,[x[0] for x in h.patches])
        self.assertNotIn(BASE+0x1BEDE0,[x[0] for x in h.patches])
    def test_watchdog_scoped_templates_restore_after_rendering(self):
        h=LifecycleHarness(self.image,True)
        before=h.lua.eval("tostring(EEex_HookIntegrityWatchdog_HookEnter)")
        h.render()
        self.assertEqual(before,h.lua.eval("tostring(EEex_HookIntegrityWatchdog_HookEnter)"))
        self.assertEqual(19,len(h.assemblies))
        self.assertEqual([],h.protection)
        self.assertTrue(h.watchdog_metadata)
        self.assertTrue(all(row[2]==0 for row in h.watchdog_metadata if len(row)==3))

if __name__=="__main__": unittest.main()
