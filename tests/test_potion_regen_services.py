"""Read-only service planning tests; generated native code has a separate probe."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

SOURCE=Path(__file__).resolve().parents[1]/'research/prototypes/potion-admission/CBRPQRegenServices.lua'


class RegenerationServicePlanningTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.module=self.lua.execute(SOURCE.read_text())
        self.memory={}
        self.base=0x140000000
        self.reads=[]
        for rva,text in self.module.expected.items():
            for i,value in enumerate(bytes.fromhex(text)): self.memory[self.base+rva+i]=value
        self.lua.globals().read=lambda p:self.reads.append(p) or self.memory.get(p)
        self.api=self.lua.eval('{EEex_GetImageBase=function() return 0x140000000 end, EEex_ReadU8=function(p) return read(p) end}')

    def test_plan_checks_native_dependencies_without_jit_or_native_call_capabilities(self):
        plan=self.module.plan(self.api)
        self.assertEqual(plan.cacheSize,48)
        self.assertEqual(plan.requestSize,64)
        self.assertEqual(plan.heapCell,self.base+0x34B8590)
        self.assertEqual(set(self.reads),set(self.memory))
        self.assertIn('call qword ptr [rax]',plan.allocate)
        self.assertNotIn('4F7A88',plan.allocate)

    def test_patched_dependency_fails_before_a_service_plan_is_returned(self):
        location=self.base+0x407890+9
        self.memory[location]^=1
        with self.assertRaisesRegex(Exception,'unsupported/patched native dependency'):
            self.module.plan(self.api)

    def test_relocated_generation_uses_the_given_image_base(self):
        base=0x180000000
        plan=self.module.generate(base)
        self.assertEqual(plan.heapAllocIAT,base+0x58A1B0)
        self.assertIn(format(base+0x4077F0,'X'),plan.insert)
        self.assertIn(format(base+0x598B18,'X'),plan.initialize)
        self.assertNotIn(format(self.base+0x4077F0,'X'),plan.insert)

    def test_nonintegral_or_inexact_addresses_are_rejected(self):
        for base in (0,-1,1.5,9007199254740991):
            with self.subTest(base=base), self.assertRaises(Exception): self.module.generate(base)
        for address in (0,-1,1.5,9007199254740992):
            with self.subTest(address=address), self.assertRaises(Exception): self.module.luaWrapper(address)

    def test_wrapper_uses_existing_eeex_lua_c_api_labels_and_status_return(self):
        wrapper=self.module.luaWrapper(0x143600000)
        self.assertIn('#L(Hardcoded_lua_tointegerx)',wrapper)
        self.assertIn('#L(Hardcoded_lua_pushinteger)',wrapper)
        self.assertIn('mov eax, 1',wrapper)
        self.assertEqual(self.reads,[])  # Generation is inert, even read capabilities are unnecessary.


if __name__=='__main__': unittest.main()
