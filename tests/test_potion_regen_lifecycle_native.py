"""Optional generated lifecycle trampolines executed in Unicorn, not the game."""
from pathlib import Path
from types import SimpleNamespace
import struct
import tempfile
import unittest

from tests.test_potion_regen_lifecycle import LifecycleHarness, read_image, BASE
from tests import test_potion_generated_trampoline as native

@unittest.skipUnless(native.EEEX and native.LIBS and native.ML64,"optional: EEex, ML64, Unicorn paths")
class RegenerationLifecycleNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image=read_image()
        cls.directory=Path(tempfile.mkdtemp(prefix="cbr-regen-lifecycle-native-"))
        cls.assembler=native.assemble
        cls.code={}
        def cached(text,address,directory,name):
            key=(text,address)
            if key not in cls.code:
                cls.code[key]=cls.assembler(text,address,directory,"code_"+str(len(cls.code)))
            return cls.code[key]
        native.assemble=cached
    @classmethod
    def tearDownClass(cls): native.assemble=cls.assembler
    def initializer(self,d,matching=True):
        def init(m):
            m.initial_rsp=m.STACK+0x20000+int(d.stackMod)
            m.write("RSP",m.initial_rsp)
            m.uc.mem_write(m.initial_rsp,bytes(range(128)))
            m.uc.mem_write(m.initial_rsp+40,struct.pack("Q",BASE+0x1BEDE5))
            for name,offset in (("RAX",0x200),("RCX",0x400),("RDX",0x600),("RBX",0x800),
                                ("RSI",0xA00),("RDI",0xC00),("RBP",0xE00)):
                m.write(name,m.DATA+offset)
            m.write("R8",3)
            m.uc.mem_write(m.DATA+0xC00,struct.pack("Q",BASE+(0x58F528 if matching else 0x598B18)))
            m.uc.mem_write(m.DATA+0x200+0x10,struct.pack("Q",m.DATA+0x800))
            m.uc.mem_write(m.DATA+0x400+8,struct.pack("Q",m.DATA+0x1000))
        return init
    def expected_args(self,d,m):
        i=m.initial
        args={
            "updateEnter":[i["RCX"],i["RDX"],3,m.initial_rsp],
            "naturalDeath":[i["RBX"]],
            "beforeRemove":[i["RSI"],i["RBX"],i["RBP"]],
            "updateExit":[i["RSI"],m.initial_rsp+56],
            "clear":[i["RCX"]],"removeType":[i["RCX"],i["RDX"]&65535],
            "replace":[i["RCX"],i["RDX"]],"listDestroy":[i["RCX"]],
            "copy":[i["RBX"],i["RDX"]],"appendOwned":[i["RDI"],i["RBX"],i["RBP"]],
            "appendNonempty":[i["RDI"],m.DATA+0x800,i["RAX"],BASE+0x1BEDE5],
            "appendEmpty":[i["RDI"],m.DATA+0x800,i["RAX"],BASE+0x1BEDE5],
        }
        return [i["RCX"]] if d.key.startswith("cacheDestroy") else args[d.key]
    def baseline(self,h,d,matching=True):
        start=int(d.address)-BASE
        code=".DB "+", ".join(str(x) for x in self.image[start:start+int(d.restoreSize)])+"\njmp "+str(int(d.address+d.restoreSize))
        simple=SimpleNamespace(assemblies=[(code,{})],addresses=h.addresses)
        return native.GeneratedMachine(simple,self.directory,0,{int(d.address+d.restoreSize)},
                                       initializer=self.initializer(d,matching))
    def test_all_seventeen_sites_preserve_native_state_and_capture_exact_arguments_even_on_lua_error(self):
        h=LifecycleHarness(self.image,True)
        p=h.render()
        for index,(_,d) in enumerate(p.descriptors.items(),2):
            baseline=self.baseline(h,d)
            for error in (False,True):
                with self.subTest(site=d.key,error=error):
                    m=native.GeneratedMachine(h,self.directory,index,{int(d.address+d.restoreSize)},
                                              lua_error=error,initializer=self.initializer(d))
                    self.assertEqual(baseline.snapshot(),m.snapshot())
                    if d.key.startswith("cacheDestroy"):
                        # Only the replayed PUSH owns a value below entry RSP.
                        # The new 32-byte native local/shadow area is uninitialized.
                        self.assertEqual(bytes(baseline.uc.mem_read(baseline.initial_rsp-8,8)),
                                         bytes(m.uc.mem_read(m.initial_rsp-8,8)))
                    self.assertEqual(bytes(baseline.uc.mem_read(baseline.initial_rsp,128)),
                                     bytes(m.uc.mem_read(m.initial_rsp,128)))
                    self.assertEqual(self.expected_args(d,m),[arg[1] for arg in m.lua_arguments])
                    self.assertEqual(1,m.watchdog_checks)
    def test_generic_append_filter_skips_other_list_classes_without_touching_native_state(self):
        h=LifecycleHarness(self.image,True)
        p=h.render()
        for index,(_,d) in enumerate(p.descriptors.items(),2):
            if not d.key.startswith("append") or d.key=="appendOwned": continue
            with self.subTest(site=d.key):
                baseline=self.baseline(h,d,False)
                m=native.GeneratedMachine(h,self.directory,index,{int(d.address+d.restoreSize)},
                                          initializer=self.initializer(d,False))
                self.assertEqual(baseline.snapshot(),m.snapshot())
                self.assertEqual([],m.lua_arguments)
                self.assertEqual(1,m.watchdog_checks)

if __name__=="__main__": unittest.main()
