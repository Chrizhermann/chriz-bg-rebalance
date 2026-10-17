"""Effective-resource byte-copy adapter; EEex services are explicit test doubles."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime, LuaError

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "research/prototypes/potion-admission/CBRPQResources.lua"


class PotionResourceReaderTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.lua.globals()[b"module_path"] = MODULE.as_posix().encode()
        self.lua.execute(b'''
            content, lookups, reads, demands = "", {}, {}, 0
            pointer, declaredSize = 0x100000, nil
            resource = {Demand=function(self) demands=demands+1; return buffer end}
            buffer = {}
            api = {
                EEex_Resource_Fetch=function(stem,ext)
                    lookups[#lookups+1]={stem,ext}
                    resource.nSize=declaredSize or #content
                    return missing and nil or resource
                end,
                EEex_UDToPtr=function(obj) assert(obj==buffer); return pointer end,
                EEex_ReadU8=function(address)
                    local offset=address-pointer
                    assert(offset>=0 and offset<#content,"out-of-bounds byte read")
                    reads[#reads+1]={offset,1}
                    return content:byte(offset+1)
                end,
                EEex_ReadU32=function(address)
                    local offset=address-pointer
                    assert(offset>=0 and offset+4<=#content,"out-of-bounds dword read")
                    reads[#reads+1]={offset,4}
                    local a,b,c,d=content:byte(offset+1,offset+4)
                    return a+b*256+c*65536+d*16777216
                end,
            }
            factory=dofile(module_path)
            read=factory(api)
        ''')

    def test_binary_copy_retains_signatures_nuls_high_bytes_and_chunk_boundaries(self):
        for size in (0, 1, 3, 4, 7, 2047, 2048, 2049, 4099):
            for extension in (b"itm", b"spl", b"eff"):
                with self.subTest(size=size, extension=extension):
                    data = (b"EFF V2.0\0\xff" + bytes(range(256)) * 17)[:size]
                    self.lua.globals()[b"content"] = data
                    self.assertEqual(data, self.lua.globals()[b"read"](b"dw#ptn36." + extension))
                    self.lua.execute(b'assert(lookups[#lookups][1]=="DW#PTN36")')

    def test_missing_or_failed_demand_has_no_native_memory_reads(self):
        self.lua.execute(b'api.EEex_Resource_Fetch=function() return nil end; read=factory(api)')
        value, reason = self.lua.globals()[b"read"](b"POTN36.ITM")
        self.assertIsNone(value)
        self.assertIn(b"missing", reason)
        self.lua.execute(b'assert(#reads==0 and demands==0)')
        self.setUp()
        self.lua.execute(b'buffer=nil')
        value, reason = self.lua.globals()[b"read"](b"POTN36.ITM")
        self.assertIsNone(value)
        self.assertIn(b"demand failed", reason)
        self.lua.execute(b'assert(#reads==0 and demands==1)')

    def test_invalid_size_pointer_and_name_do_not_read_memory(self):
        for name in (b"../X.ITM", b"TOOLONG99.ITM", b"A/B.ITM", b"A B.ITM", b"A\0.ITM", b"A.LUA"):
            with self.subTest(name=name), self.assertRaises(LuaError):
                self.lua.globals()[b"read"](name)
        for size in (-1, 0.5, 16 * 1024 * 1024 + 1):
            self.lua.globals()[b"declaredSize"] = size
            with self.assertRaises(LuaError):
                self.lua.globals()[b"read"](b"POTN36.ITM")
        self.lua.execute(b'declaredSize=8; pointer=9007199254740990')
        with self.assertRaises(LuaError):
            self.lua.globals()[b"read"](b"POTN36.ITM")
        self.lua.execute(b'assert(#reads==0)')

    def test_each_call_uses_current_effective_resource_and_does_not_retain_buffer(self):
        self.lua.globals()[b"content"] = b"first\x00effect"
        old = self.lua.globals()[b"read"](b"POTN36.ITM")
        self.lua.execute(b'content="second"; pointer=0x200000; buffer={}')
        self.assertEqual(b"second", self.lua.globals()[b"read"](b"POTN36.ITM"))
        self.assertEqual(b"first\x00effect", old)
        self.lua.execute(b'assert(demands==2)')


if __name__ == "__main__":
    unittest.main()
