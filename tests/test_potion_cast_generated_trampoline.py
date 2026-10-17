"""Execute inert cast transport's actual EEex-generated code in Unicorn.

Real EEex macros -> local ML64 -> copied instructions. Lua/watchdog helpers are
adversarial register-clobbering doubles. No game or DLL is executed/installed.
"""
from pathlib import Path
import struct
import tempfile
import unittest

from tests.test_potion_generated_trampoline import (
    GeneratedMachine, EEEX, LIBS, ML64,
)
from tests.test_potion_cast_transport_preprocessor import (
    CastHarness, read_image, SITES, SIZES, BASE, ENTRY_INDICES, LEAVE_INDICES,
)

if EEEX and LIBS and ML64:
    import unicorn
    from unicorn import x86_const as x86


def native_replay(machine, original):
    """Execute only displaced native instructions as an independent baseline."""
    u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    u.mem_map(0x100000, 0x1000)
    u.mem_map(machine.STACK, 0x40000)
    u.mem_map(machine.DATA, 0x10000)
    u.mem_write(machine.DATA, bytes(machine.uc.mem_read(machine.DATA, 0x10000)))
    u.mem_write(machine.initial_rsp, machine.initial_stack)
    for name, value in machine.initial.items():
        constant = x86.UC_X86_REG_EFLAGS if name=="FLAGS" else getattr(x86,"UC_X86_REG_"+name)
        u.reg_write(constant,value)
    if original:
        u.mem_write(0x100000,original)
        u.emu_start(0x100000,0x100000+len(original),count=30)
    state={name:u.reg_read(x86.UC_X86_REG_EFLAGS if name=="FLAGS" else getattr(x86,"UC_X86_REG_"+name))
           for name in machine.initial}
    return state,bytes(u.mem_read(machine.initial_rsp,128))


@unittest.skipUnless(EEEX and LIBS and ML64,
                     "optional: EEEX_LUA_DIR, EEEX_POTION_PYLIBS and EEEX_POTION_ML64")
class CastGeneratedTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=Path(tempfile.mkdtemp(prefix="cbr-potion-cast-generated-"))
        cls.image=read_image()

    def execute(self,index,*,error=False,valid_guard=True):
        h=CastHarness(self.image,watchdog=True)
        h.install()
        def initialize(m):
            # Override older shared runner's site-specific alignment fixture.
            m.initial_rsp=m.STACK+0x20000+(8 if index in ENTRY_INDICES else 0)
            m.write("RSP",m.initial_rsp)
            m.uc.mem_write(m.initial_rsp,bytes(range(128)))
            m.write("RBP",m.DATA+0x100)
            m.write("RBX",m.DATA+0x400)
            m.write("RCX",m.DATA+0x500)
            m.write("RDX",m.DATA+0x400)
            m.write("R14",m.DATA+0x600)
            m.write("R13",m.DATA+0x700)
            m.write("RSI",m.DATA+0x800)
            m.write("R15",m.DATA+0xA00)
            m.write("RDI",17)
            m.write("R9",0)
            m.uc.mem_write(m.DATA+0x100+0xB8,struct.pack("<Q",BASE+(0x212E89 if valid_guard else 0x212E90)))
            m.uc.mem_write(m.DATA+0x400+0x14,struct.pack("<I",2))
            m.uc.mem_write(m.DATA+0x500,struct.pack("<Q",BASE+(0x590D90 if valid_guard else 0x590D98)))
            m.uc.mem_write(m.initial_rsp+0x50,struct.pack("<I",1337))
        destination=BASE+0x16B331 if index in LEAVE_INDICES else BASE+SITES[index]+SIZES[index]
        m=GeneratedMachine(h,self.directory,index+2,{destination},lua_error=error,initializer=initialize)
        original=b"" if index in LEAVE_INDICES else bytes(self.image[SITES[index]:SITES[index]+SIZES[index]])
        expected,stack=native_replay(m,original)
        self.assertEqual(expected,m.snapshot(),f"state changed at{SITES[index]:X}")
        self.assertEqual(stack,bytes(m.uc.mem_read(m.initial_rsp,128)))
        self.assertEqual(1,m.watchdog_checks)
        return m

    def test_every_generated_site_preserves_native_state_and_handles_lua_errors(self):
        for index in range(len(SITES)):
            for error in (False,True):
                with self.subTest(site=hex(SITES[index]),error=error):
                    m=self.execute(index,error=error)
                    self.assertTrue(m.lua_calls)

    def test_actual_argument_values_including_original_stack_and_ability_index(self):
        for index in range(len(SITES)):
            with self.subTest(site=hex(SITES[index])):
                m=self.execute(index)
                p=m.initial
                frame=p["RBP"]+0xB8
                expected=(
                    [p["RSI"],p["R14"],p["R15"]],
                    [p["RCX"],m.initial_rsp],
                    [p["RBX"]],
                    [p["RCX"]],
                    [frame,p["RBX"],17,1337,p["R14"],p["RSI"]],
                    [frame,p["RDX"],0],
                    [frame],
                    [frame,p["RDX"],0],
                    [frame],
                    [frame,p["RDX"],p["RBX"],17],
                    [frame,p["RBX"],17,p["R13"]],
                )[index]
                self.assertEqual(expected,[value for _,value in m.lua_arguments])

    def test_unrelated_caller_or_shared_destructor_class_skips_callback_only(self):
        for index in range(3,len(SITES)):
            with self.subTest(site=hex(SITES[index])):
                m=self.execute(index,valid_guard=False)
                self.assertEqual([],m.lua_calls)
                self.assertEqual([],m.lua_arguments)


if __name__=="__main__":
    unittest.main()
