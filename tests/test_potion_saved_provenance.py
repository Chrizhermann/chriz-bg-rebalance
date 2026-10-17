"""Pure future save-sidecar schema; no save or EEex marshalling is executed."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

MODULE = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission/CBRPQSaved.lua"


class PotionSavedProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().modulePath = MODULE.as_posix()
        self.lua.execute(r'''
            saved=dofile(modulePath)
            local function replace(s,off,value) return s:sub(1,off)..value..s:sub(off+#value+1) end
            function body(tag)
                local data=string.rep("\0",0x158)
                data=replace(data,0x10,string.char(90,0,0,0))
                data=replace(data,0x24,string.char(0,16,0,0))
                data=replace(data,0x94,(tag or "SHARED")..string.rep("\0",8-#(tag or "SHARED")))
                return data
            end
            function record(data) return {identity={},body=data or body()} end
            function verify(r,o) return o.source=="POTN36" and o.key=="SKILL" end
            function owner() return {source="POTN36",key="SKILL"} end
            function throws(fn,pattern)
                local ok,error=pcall(fn)
                assert(not ok and tostring(error):find(pattern,1,true),tostring(error))
            end
            change=replace
        ''')

    def test_identical_foreign_and_potion_effects_retain_exact_relative_ownership(self):
        self.lua.execute(r'''
            local foreign,potion,second,unrelated=record(),record(),record(),record(body("OTHER"))
            local state=saved.export({foreign,unrelated,potion,second},{[potion.identity]=owner(),[second.identity]=owner()})
            local f,p,s=record(),record(),record()
            local result=saved.restore({record(body("UUID")),f,record(body("OTHER")),p,s},state,verify)
            assert(result[f.identity]==nil and result[p.identity].source=="POTN36" and result[s.identity].key=="SKILL")
            assert(result[p.identity]~=result[s.identity])
        ''')

    def test_missing_duplicate_or_changed_bytes_fail_complete_import(self):
        self.lua.execute(r'''
            local a,b=record(),record()
            local state=saved.export({a,b},{[b.identity]=owner()})
            throws(function() saved.restore({record()},state,verify) end,"occurrences no longer match")
            throws(function() saved.restore({record(),record(),record()},state,verify) end,"occurrences no longer match")
            throws(function() saved.restore({record(),record(body("CHANGED"))},state,verify) end,"occurrences no longer match")
            throws(function() saved.restore({record(),record()},state,function() return false end) end,"current manifest")
        ''')

    def test_copied_fields_normalize_only_native_resref_transformations(self):
        self.lua.execute(r'''
            local original=body()
            for _,off in ipairs({0x30,0x70,0x78}) do original=change(original,off,"ab\0stuff") end
            local restored=original
            for _,off in ipairs({0x30,0x70,0x78}) do restored=change(restored,off,"AB\0\0\0\0\0\0") end
            restored=change(restored,0x50,"TAIL")
            restored=change(restored,0xD4,string.rep("X",0x158-0xD4))
            assert(saved.fingerprint(original)==saved.fingerprint(restored))
            assert(saved.fingerprint(original)~=saved.fingerprint(change(restored,0x94,"shared\0\0")))
        ''')

    def test_export_uses_only_supplied_serialized_subset_and_does_not_invent_existing_save_ownership(self):
        self.lua.execute(r'''
            local omitted=record()
            local state=saved.export({record(body("LOCAL"))},{[omitted.identity]=owner()})
            assert(next(state.groups)==nil)
            assert(next(saved.restore({record()},state,verify))==nil)
        ''')

    def test_malformed_metadata_and_duplicate_native_lifetimes_are_rejected(self):
        self.lua.execute(r'''
            local r=record()
            throws(function() saved.export({r,r},{}) end,"duplicate native lifetime")
            throws(function() saved.export({r},{[r.identity]={source="POT\0N",key="K"}}) end,"owning item")
            throws(function() saved.restore({r},{version=2,groups={}},verify) end,"unsupported schema")
            local state=saved.export({r},{[r.identity]=owner()})
            local _,entry=next(state.groups); entry.owned[2]=owner()
            throws(function() saved.restore({record()},state,verify) end,"invalid saved occurrence")
        ''')

    def test_occurrences_above_resource_header_limit_round_trip_within_native_marshal_bound(self):
        self.lua.execute(r'''
            local records={}; local bytes=body()
            for i=1,65536 do records[i]=record(bytes) end
            local data=saved.export(records,{[records[65536].identity]=owner()})
            local _,entry=next(data.groups); assert(entry.count==65536)
            local result=saved.restore(records,data,verify)
            assert(result[records[65536].identity].key=="SKILL" and result[records[65535].identity]==nil)
        ''')


if __name__ == "__main__":
    unittest.main()
