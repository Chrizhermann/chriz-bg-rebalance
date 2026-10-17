"""Saved ownership through the installed EEex Lua serializer, offline only.

The real Lua size/write/read routines run unchanged. Native memory primitives
are bounded byte-buffer doubles; no DLL, sprite, save, or game is accessed.
Opt in with EEEX_LUA_DIR pointing at the reviewed EEex_scripts directory.
"""
from pathlib import Path
import os
import struct
import unittest

from lupa.luajit21 import LuaRuntime


MODULE = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission/CBRPQSaved.lua"
EEEX = os.environ.get("EEEX_LUA_DIR")
BASE = 0x200000000


@unittest.skipUnless(EEEX, "set EEEX_LUA_DIR for the actual EEex Lua serializer")
class PotionSavedEEexTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.memory = bytearray()
        self.lua.globals()[b"memory_write"] = self.write
        self.lua.globals()[b"memory_read"] = self.read
        self.lua.globals()[b"memory_string"] = self.read_string
        self.lua.globals()[b"saved"] = self.lua.execute(MODULE.read_bytes())
        self.lua.execute(b'''
            local formats={[8]='b',[16]='h',[32]='i',[64]='q'}
            for width,fmt in pairs(formats) do
                _G['EEex_Write'..width]=function(p,v) memory_write(p,fmt,v) end
                _G['EEex_Read'..width]=function(p) return memory_read(p,fmt) end
                local unsigned=fmt:upper()
                _G['EEex_WriteU'..width]=function(p,v) memory_write(p,unsigned,v) end
                _G['EEex_ReadU'..width]=function(p) return memory_read(p,unsigned) end
            end
            EEex_WriteString=function(p,s) memory_write(p,'bytes',s..'\0') end
            EEex_WriteLString=function(p,s,n) memory_write(p,'bytes',s:sub(1,n)) end
            EEex_ReadString=function(p) return memory_string(p) end
            EEex_Memset=function(p,v,n) memory_write(p,'bytes',string.rep(string.char(v),n)) end
            EEex_RoundUp=function(n,m) return math.ceil(n/m)*m end
            EEex_Error=error
            ignoredErrors={}
            EEex_Utility_TryIgnore=function(fn,...)
                local ok,result=pcall(fn,...)
                if not ok then ignoredErrors[#ignoredErrors+1]=tostring(result); return nil end
                return result
            end
            EEex_GetUDAux=function(sprite) return sprite.aux end
            EEex_Utility_GetOrCreateTable=function(t,k) t[k]=t[k] or {}; return t[k] end
            CGameEffectBase={sizeof=0x108}
        ''')
        source = (Path(EEEX) / "EEex_Sprite.lua").read_bytes()
        start = source.index(b"EEex_Sprite_Private_MarshalHandlers = {}")
        end = source.index(b"EEex_Sprite_Private_CustomConcentrationCheckFuncName = nil", start)
        self.lua.execute(source[start:end])
        self.lua.execute(b'''
            function body()
                return string.rep('\0',0x10)..string.char(90,0,0,0)..string.rep('\0',0x158-0x14)
            end
            function record() return {identity={},body=body()} end
            function owned() return {source='POTN36',key=string.rep('a',64)} end
            function verify(r,o) return o.source=='POTN36' and o.key==string.rep('a',64) end
            function makeState(n)
                local records,owners={},{}
                for i=1,n do
                    records[i]=record()
                    if i%2==0 then owners[records[i].identity]=owned() end
                end
                return saved.export(records,owners)
            end
            input={aux={}}
            output={aux={}}
        ''')

    def write(self, address, fmt, value):
        fmt = fmt.decode()
        data = value if fmt == "bytes" else struct.pack("<" + fmt, int(value))
        offset = int(address) - BASE
        self.assertGreaterEqual(offset, 0)
        self.assertLessEqual(offset + len(data), len(self.memory), "EEex wrote beyond calculated allocation")
        self.memory[offset:offset + len(data)] = data

    def read(self, address, fmt):
        fmt = fmt.decode()
        offset = int(address) - BASE
        self.assertGreaterEqual(offset, 0)
        self.assertLessEqual(offset + struct.calcsize(fmt), len(self.memory))
        return struct.unpack_from("<" + fmt, self.memory, offset)[0]

    def read_string(self, address):
        offset = int(address) - BASE
        self.assertGreaterEqual(offset, 0)
        end = self.memory.index(0, offset)
        return bytes(self.memory[offset:end])

    def round_trip(self, sprite=b"input", target=b"output"):
        size = self.lua.globals()[b"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize"](
            self.lua.globals()[sprite])
        self.assertEqual(0, size % 0x108)
        self.memory = bytearray([0xA5] * size)
        self.lua.globals()[b"EEex_Sprite_Hook_WriteExtraEffectListMarshal"](BASE)
        self.assertEqual(b"X-BIV1.0", self.memory[:8])
        consumed = self.lua.globals()[b"EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal"](
            self.lua.globals()[target], BASE)
        self.assertEqual(size, consumed * 0x108)
        self.lua.execute(b"assert(#ignoredErrors==0,table.concat(ignoredErrors,'; '))")
        return size

    def test_sparse_owned_occurrences_round_trip_across_number_width_boundary(self):
        self.lua.execute(b'''
            state=makeState(300)
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function() return state end,
                function(sprite,data) sprite.restored=data end)
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function() return {flag=true,n=4294967295,text='retained'} end,
                function(sprite,data) sprite.foreign=data end)
        ''')
        self.round_trip()
        self.lua.execute(b'''
            local records={}
            for i=1,300 do records[i]=record() end
            local owners=saved.restore(records,output.restored,verify)
            for i,r in ipairs(records) do assert((owners[r.identity]~=nil)==(i%2==0)) end
            assert(output.foreign.flag and output.foreign.n==4294967295 and output.foreign.text=='retained')
        ''')

    def test_missing_handler_uses_real_fallback_and_reexport_preserves_metadata(self):
        self.lua.execute(b'''
            state=makeState(4)
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function() return state end,
                function(sprite,data) sprite.restored=data end)
        ''')
        size = self.lua.globals()[b"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize"](
            self.lua.globals()[b"input"])
        self.memory = bytearray(size)
        self.lua.globals()[b"EEex_Sprite_Hook_WriteExtraEffectListMarshal"](BASE)
        self.lua.execute(b"EEex_Sprite_Private_MarshalHandlers.CBRPQ=nil")
        self.lua.globals()[b"EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal"](
            self.lua.globals()[b"output"], BASE)
        self.lua.execute(b'''
            assert(output.restored==nil and output.aux.EEex_Sprite_FallbackMarshalStorage.CBRPQ.version==1)
            final={aux={}}
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function() return nil end,
                function(sprite,data) sprite.restored=data end)
        ''')
        self.round_trip(b"output", b"final")
        self.lua.execute(b'''
            local records={record(),record(),record(),record()}
            local restored=saved.restore(records,final.restored,verify)
            assert(restored[records[1].identity]==nil and restored[records[2].identity]~=nil)
            assert(restored[records[3].identity]==nil and restored[records[4].identity]~=nil)
        ''')

    def test_mutating_exporter_after_ownership_snapshot_reproduces_wrong_relative_owner(self):
        # This is a required counterexample, not an accepted integration. A
        # post-export snapshot/guard is needed before enabling save ownership.
        self.lua.execute(b'''
            first,second=record(),record()
            input.effects={first,second}
            local ownership={[second.identity]=owned()}
            local seen={}
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function(sprite)
                seen[#seen+1]='owner'
                return saved.export(sprite.effects,ownership)
            end,function(sprite,data) sprite.restored=data end)
            EEex_Sprite_AddMarshalHandlers('MUTATOR',function(sprite)
                seen[#seen+1]='mutator'
                sprite.effects={second,first}
                return nil
            end,function() end)
            -- The official loop uses pairs; prescribe one allowed iteration
            -- order while retaining the actual exporter/size/write/read code.
            local originalPairs=pairs
            pairs=function(t)
                if t==EEex_Sprite_Private_MarshalHandlers then
                    local keys={'CBRPQ','MUTATOR'}; local i=0
                    return function() i=i+1; local k=keys[i]; if k then return k,t[k] end end
                end
                return originalPairs(t)
            end
        ''')
        self.round_trip()
        self.lua.execute(b'''
            local savedPotion,savedForeign=record(),record()
            local result=saved.restore({savedPotion,savedForeign},output.restored,verify)
            assert(result[savedPotion.identity]==nil and result[savedForeign.identity]~=nil,
                'required snapshot-order counterexample no longer reproduced')
        ''')

    def compose_exporter(self):
        factory = self.lua.execute((MODULE.parent / "CBRPQSaveExport.lua").read_bytes())
        self.lua.globals()[b"exportFactory"] = factory
        self.lua.execute(b'''
            nativeContext={identity={},version=1,onlyTiming9=false,excludeTiming2=true,normalBytes=0}
            input.effects={}
            input.owners={}
            snapshotReads,otherCalls=0,0
            invalidated={}
            composed=exportFactory(_G,saved,{
                context=function() return nativeContext end,
                records=function(sprite) snapshotReads=snapshotReads+1; return sprite.effects end,
                owners=function(sprite) return sprite.owners end,
                invalidate=function(reason) invalidated[#invalidated+1]=reason end,
            })
            EEex_Sprite_AddMarshalHandlers('CBRPQ',composed.exporter,
                function(sprite,data) sprite.restored=data end)
            EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize=composed.calculate
            EEex_Sprite_Hook_WriteExtraEffectListMarshal=composed.write
            local originalPairs=pairs
            pairs=function(t)
                if t==EEex_Sprite_Private_MarshalHandlers then
                    local keys={'CBRPQ','MUTATOR'}; local i=0
                    return function()
                        i=i+1; local k=keys[i]
                        if k and t[k] then return k,t[k] end
                    end
                end
                return originalPairs(t)
            end
        ''')

    def test_final_snapshot_after_other_exporters_corrects_identical_record_order(self):
        self.compose_exporter()
        self.lua.execute(b'''
            first,second=record(),record()
            input.effects={first,second}; input.owners={[second.identity]=owned()}
            nativeContext.normalBytes=2*0x108
            EEex_Sprite_AddMarshalHandlers('MUTATOR',function(sprite)
                otherCalls=otherCalls+1
                assert(snapshotReads==0)
                sprite.effects={second,first}
                return {untouched='preserve this handler'}
            end,function(sprite,data) sprite.other=data end)
        ''')
        self.round_trip()
        self.lua.execute(b'''
            local potion,foreign=record(),record()
            local result=saved.restore({potion,foreign},output.restored,verify)
            assert(result[potion.identity]~=nil and result[foreign.identity]==nil)
            assert(otherCalls==1 and snapshotReads==1 and output.other.untouched=='preserve this handler')
        ''')

    def test_final_metadata_grows_allocation_without_changing_native_count_and_filters_timings(self):
        self.compose_exporter()
        self.lua.execute(b'''
            function withTiming(r,timing)
                r.body=r.body:sub(1,0x24)..string.char(timing,0,0,0)..r.body:sub(0x29)
                return r
            end
            for i=1,300 do
                input.effects[i]=withTiming(record(),i%3==0 and 2 or (i%2==0 and 9 or 0))
            end
            nativeContext.normalBytes=200*0x108
            EEex_Sprite_AddMarshalHandlers('MUTATOR',function(sprite)
                otherCalls=otherCalls+1
                -- Late ownership metadata can grow, but the native normal
                -- effect count was already fixed before these exporters ran.
                for _,r in ipairs(sprite.effects) do sprite.owners[r.identity]=owned() end
                return {preserved=1234}
            end,function(sprite,data) sprite.other=data end)
        ''')
        size = self.round_trip()
        self.assertGreater(size, 0x108)
        self.lua.execute(b'''
            local records={}
            for i=1,300 do if i%3~=0 then records[#records+1]=withTiming(record(),i%2==0 and 9 or 0) end end
            local result=saved.restore(records,output.restored,verify)
            local count=0; for _ in pairs(result) do count=count+1 end
            assert(count==200 and otherCalls==1 and output.other.preserved==1234)
        ''')
        self.lua.execute(b"nativeContext.onlyTiming9=true; nativeContext.normalBytes=100*0x108; output={aux={}}")
        self.round_trip()
        self.lua.execute(b'''
            local records={}
            for i=1,100 do records[i]=withTiming(record(),9) end
            local result=saved.restore(records,output.restored,verify)
            local count=0; for _ in pairs(result) do count=count+1 end
            assert(count==100 and otherCalls==2)
        ''')

    def test_changed_native_count_repairs_both_allocation_and_footer_location(self):
        for mutation,new_count in ((b"sprite.effects[2]=record()",2), (b"sprite.effects={}",0)):
            with self.subTest(new_count=new_count):
                self.setUp()
                self.compose_exporter()
                self.lua.execute(b'''
                    input.effects={record()}; nativeContext.normalBytes=0x108
                    EEex_Sprite_AddMarshalHandlers('MUTATOR',function(sprite)
                '''+mutation+b'''
                    end,function() end)
                ''')
                added=self.lua.globals()[b"composed"][b"calculate"](self.lua.globals()[b"input"])
                extra=self.lua.globals()[b"EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize"]+8
                self.assertEqual(extra+(new_count-1)*0x108,added)
                self.memory=bytearray(0x108+added)
                self.lua.globals()[b"composed"][b"write"](BASE+0x108)
                self.assertEqual(b"X-BIV1.0",self.memory[new_count*0x108:new_count*0x108+8])
                consumed=self.lua.globals()[b"EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal"](
                    self.lua.globals()[b"output"],BASE+new_count*0x108)
                self.assertEqual(consumed*0x108,extra)

    def binary_reader(self):
        module=self.lua.execute((MODULE.parent/"CBRPQSavedBinary.lua").read_bytes())
        return module[b"read"]

    def test_bounded_binary_preparse_matches_real_serializer_without_calling_importers(self):
        self.lua.execute(b'''
            state=makeState(300); importerCalls=0
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function() return state end,
                function() importerCalls=importerCalls+1 end)
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function()
                return {[false]={nested={a=-123,b=true,c=4294967295}},[13]='other data'}
            end,function() importerCalls=importerCalls+1 end)
        ''')
        size=self.lua.globals()[b"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize"](
            self.lua.globals()[b"input"])
        self.memory=bytearray(size)
        self.lua.globals()[b"EEex_Sprite_Hook_WriteExtraEffectListMarshal"](BASE)
        data,count=self.binary_reader()(self.lua.globals()[b"EEex_ReadU8"],BASE,BASE+size,b"CBRPQ")
        self.assertEqual(size,count*0x108)
        self.lua.globals()[b"preparsed"]=data
        self.lua.execute(b'''
            assert(importerCalls==0)
            local records={}; for i=1,300 do records[i]=record() end
            local owners=saved.restore(records,preparsed,verify)
            for i,r in ipairs(records) do assert((owners[r.identity]~=nil)==(i%2==0)) end
        ''')

    def test_preparser_skips_foreign_64_bit_values_without_rounding_or_rejecting_them(self):
        raw=b"X-BIV1.0FOREIGN\0\x02v\0\x0a"+b"\xff"*8+b"\0\0"
        self.memory=bytearray(raw.ljust(0x108,b"\0"))
        data,count=self.binary_reader()(self.lua.globals()[b"EEex_ReadU8"],BASE,BASE+0x108,b"CBRPQ")
        self.assertIsNone(data)
        self.assertEqual(count,1)
        raw=raw.replace(b"FOREIGN",b"CBRPQ")
        self.memory=bytearray(raw.ljust(0x108,b"\0"))
        with self.assertRaisesRegex(Exception,"exact owner integer"):
            self.binary_reader()(self.lua.globals()[b"EEex_ReadU8"],BASE,BASE+0x108,b"CBRPQ")

    def test_preparser_requires_footer_last_and_never_reads_outside_native_interval(self):
        for raw,size,reason in (
            (b"X-BIV1.0\0",0x210,"final native input block"),
            (b"X-BIV1.0X",9,"beyond native input"),
            (b"X-BIV1.0CBRPQ\0\x02key\0\xff",21,"scalar field type"),
            (b"X-BIV1.0CBRPQ\0\0CBRPQ\0\0\0",0x108,"duplicate ownership handler")):
            with self.subTest(reason=reason):
                self.memory=bytearray(raw.ljust(size,b"\0"))
                reads=[]
                def read_byte(address):
                    reads.append(address)
                    self.assertLess(address,BASE+size)
                    return self.memory[int(address-BASE)]
                self.lua.globals()[b"bounded_read"]=read_byte
                callback=self.lua.eval(b"function(p) return bounded_read(p) end")
                with self.assertRaisesRegex(Exception,reason):
                    self.binary_reader()(callback,BASE,BASE+size,b"CBRPQ")
                self.assertTrue(reads)

    def composed_native_import(self,mutation):
        # Exact reader/save/copy modules and unchanged EEex Lua serializer.
        # Native allocation, field construction, list membership, and the
        # caller context remain explicit byte-memory/lifetime service doubles.
        from tests.test_potion_native_reader import descriptor,FIELDS
        fields=descriptor(nativeSourceType=1,nativeSource="SHARED")
        self.memory=bytearray(0x40000)
        for pointer in (BASE+0x1000,BASE+0x2000):
            for name,(offset,fmt) in FIELDS.items():
                struct.pack_into("<"+fmt,self.memory,pointer-BASE+offset,fields[name])
            struct.pack_into("<Q",self.memory,pointer-BASE,0x140590000)
            struct.pack_into("<I",self.memory,pointer-BASE+0x90,1)
            self.memory[pointer-BASE+0x94:pointer-BASE+0x9C]=b"SHARED\0\0"
            struct.pack_into("<I",self.memory,pointer-BASE+0xC8,17)
            struct.pack_into("<I",self.memory,pointer-BASE+0x11C,120)
        def literal(value):
            if isinstance(value,str): return "'"+value+"'"
            return str(value)
        self.lua.execute(("nativeFields={"+",".join(k+"="+literal(v) for k,v in fields.items())+"}").encode())
        for filename,global_name in (("CBRPQNative.lua",b"nativeFactory"),
                ("CBRPQSaveImport.lua",b"importFactory"),("CBRPQSavedBinary.lua",b"binary"),
                ("CBRPQUnmarshal.lua",b"inputFactory")):
            self.lua.globals()[global_name]=self.lua.execute((MODULE.parent/filename).read_bytes())
        self.lua.globals()[b"base"]=BASE
        self.lua.execute(b'''
            EEex_UDToPtr=function(o) return o.pointer end
            EEex_Utility_IterateCPtrList=function(list,fn)
                for _,e in ipairs(list) do if fn(e) then break end end
            end
            native=nativeFactory(_G,{sources={POTN36={keys={linked=true},records={linked=nativeFields}}}})
            potion={pointer=base+0x1000}; foreign={pointer=base+0x2000}
            input.m_timedEffectList={foreign,potion}
            native.bindLinked(potion,'POTN36','linked')
            for _,p in ipairs({potion.pointer,foreign.pointer}) do
                EEex_WriteU32(p+0x24,4096); EEex_WriteU32(p+0x28,3700)
            end
            inputState=saved.export(native.savedRecords(input),native.savedOwners())
            foreignCalls=0
            EEex_Sprite_AddMarshalHandlers('CBRPQ',function() return inputState end,function() end)
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function() return {preserved=true} end,
                function(sprite,data)
                    foreignCalls=foreignCalls+1; assert(data.preserved)
        '''+mutation+b'''
                end)
            local builtinPairs=pairs
            pairs=function(t)
                if t==EEex_Sprite_Private_MarshalHandlers then
                    local keys={'FOREIGN','CBRPQ'}; local i=0
                    return function() i=i+1; local k=keys[i]; if k then return k,t[k] end end
                end
                return builtinPairs(t)
            end
        ''')
        size=self.lua.globals()[b"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize"](
            self.lua.globals()[b"input"])
        data=BASE+0x20000
        footer=data+2*0x108
        self.lua.globals()[b"EEex_Sprite_Hook_WriteExtraEffectListMarshal"](footer)
        self.assertLess(self.memory.index(b"FOREIGN",footer-BASE),self.memory.index(b"CBRPQ",footer-BASE))
        self.lua.globals()[b"input_data"]=data
        self.lua.globals()[b"input_size"]=2*0x108+size
        self.lua.globals()[b"footer"]=footer
        self.lua.execute(b'''
            native.resetTokens()
            output.pointer=base+0xF000
            output.m_timedEffectList={}
            inputContext=inputFactory(function(list,sprite)
                assert(list==base+0xF100 and sprite==output.pointer)
                local result={}
                for i,record in ipairs(native.savedRecords(output)) do result[i]=record.identity end
                return result
            end,EEex_UDToPtr)
            inputContext.invalidate=function(reason) error('unexpected ownership failure: '..reason) end
            inputContext.enter(base+0x30000,base+0xF100,input_data,input_size,output.pointer,1)
            -- Native decoded originals are already linked before ReadExtra.
            output.m_timedEffectList={foreign,potion}
            imported=importFactory(_G,binary,saved,native,inputContext,'CBRPQ')
            EEex_Sprite_Private_MarshalHandlers.CBRPQ.importer=imported.importer
        ''')
        return self.lua.globals()[b"imported"][b"read"](self.lua.globals()[b"output"],footer)

    def test_import_restores_before_a_foreign_handler_swaps_identical_originals(self):
        count=self.composed_native_import(b"sprite.m_timedEffectList={potion,foreign}")
        self.assertGreater(count,0)
        self.lua.execute(b'''
            assert(foreignCalls==1 and #ignoredErrors==0)
            assert(native.identify(potion,'linked',false).ownerSource=='POTN36')
            assert(native.identify(foreign,nil,false)==nil)
        ''')

    def test_early_foreign_importer_copy_keeps_owner_after_removing_original(self):
        self.composed_native_import(b'''
            clone={pointer=base+0x3000}
            for i=0,0x154,4 do EEex_WriteU32(clone.pointer+i,EEex_ReadU32(potion.pointer+i)) end
            EEex_WriteU32(clone.pointer+0x114,0)
            EEex_WriteU32(clone.pointer+0x11C,3700)
            EEex_WriteU32(clone.pointer+0x150,4294967295)
            assert(native.copyLinked(clone,potion.pointer))
            native.retire(potion.pointer)
            sprite.m_timedEffectList={foreign,clone}
        ''')
        self.lua.execute(b'''
            assert(foreignCalls==1 and #ignoredErrors==0)
            assert(native.identify(clone,'linked',false).ownerSource=='POTN36')
            assert(native.identify(potion,nil,false)==nil and native.identify(foreign,nil,false)==nil)
        ''')

    def test_post_collector_ownership_failure_emits_invalid_marker_without_underallocating(self):
        for modification,reason in (
            (b"EEex_Sprite_Private_MarshalHandlers.CBRPQ=nil","exporter did not run"),
            (b"input.aux.EEex_Sprite_FallbackMarshalStorage={CBRPQ={version=1,groups={},retained='old metadata'}}",
             "duplicate ownership handler"),
            (b"input.effects={record()}; input.owners[input.effects[1].identity]={source='bad\\0source',key='x'}; nativeContext.normalBytes=0x108",
             "owning item")):
            with self.subTest(reason=reason):
                self.setUp(); self.compose_exporter(); self.lua.execute(modification)
                old_bytes=self.lua.globals()[b"nativeContext"][b"normalBytes"]
                added=self.lua.globals()[b"composed"][b"calculate"](self.lua.globals()[b"input"])
                self.memory=bytearray(old_bytes+added)
                self.lua.globals()[b"composed"][b"write"](BASE+old_bytes)
                data,count=self.binary_reader()(self.lua.globals()[b"EEex_ReadU8"],BASE+old_bytes,
                                                BASE+len(self.memory),b"CBRPQ")
                self.assertTrue(data[b"invalid"])
                self.assertGreater(count,0)
                enabled,error=self.lua.globals()[b"composed"][b"status"]()
                self.assertFalse(enabled)
                self.assertIn(reason.encode(),error)
                self.assertIn(reason.encode(),self.lua.globals()[b"invalidated"][1])
                if reason=="duplicate ownership handler":
                    self.assertTrue(any(v[b"retained"]==b"old metadata" for v in data[b"previous"].values()))

    def test_missing_or_changed_context_and_disabled_marshalling_diagnose_before_write(self):
        for modification, reason in (
                (b"nativeContext.version=0", "exact V2 Marshal context"),
                (b"nativeContext.excludeTiming2=nil", "native timing filters"),
                (b"nativeContext.normalBytes=nil", "normal-effect byte count"),
                (b"nativeContext.normalBytes=1", "normal-effect byte count"),
                (b"EEex_Debug_DisableExtraCreatureMarshalling=true", "marshalling is disabled"),
                (b"EEex_Sprite_AddMarshalHandlers('MUTATOR',function() nativeContext.identity={} end,function() end)",
                 "context changed")):
            with self.subTest(reason=reason):
                self.setUp()
                self.compose_exporter()
                self.lua.execute(modification)
                with self.assertRaisesRegex(Exception, reason):
                    self.lua.globals()[b"composed"][b"calculate"](self.lua.globals()[b"input"])
                self.assertEqual(bytearray(), self.memory)


if __name__ == "__main__":
    unittest.main()
