"""Persistence composition with the actual EEex Lua collector/writer/reader.

Native memory, field-copy/list construction and sprite lifetime events remain
explicit doubles. This does not execute a game/DLL or claim full native saves.
"""
from pathlib import Path
import struct
import unittest

from tests import test_potion_saved_eeex as eeex_fixture
from tests.test_potion_native_reader import descriptor, FIELDS

BASE, EEEX = eeex_fixture.BASE, eeex_fixture.EEEX
PROTOTYPE = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


@unittest.skipUnless(EEEX, "set EEEX_LUA_DIR for the actual EEex Lua serializer")
class PotionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = eeex_fixture.PotionSavedEEexTests()
        self.fixture.setUp()
        self.lua = self.fixture.lua
        self.fixture.memory = bytearray(0x80000)
        fields = descriptor(nativeSourceType=1, nativeSource="SHARED")
        for pointer in (BASE + 0x1000, BASE + 0x2000):
            for name, (offset, fmt) in FIELDS.items():
                struct.pack_into("<" + fmt, self.fixture.memory, pointer - BASE + offset, fields[name])
            struct.pack_into("<Q", self.fixture.memory, pointer - BASE, 0x140590000)
            struct.pack_into("<I", self.fixture.memory, pointer - BASE + 0x90, 1)
            self.fixture.memory[pointer-BASE+0x94:pointer-BASE+0x9C] = b"SHARED\0\0"
            struct.pack_into("<I", self.fixture.memory, pointer-BASE+0xC8, 17)
            struct.pack_into("<I", self.fixture.memory, pointer-BASE+0x11C, 120)

        def literal(value):
            return "'" + value + "'" if isinstance(value, str) else str(value)

        self.lua.execute(("fields={" + ",".join(k+"="+literal(v) for k,v in fields.items()) + "}").encode())
        self.lua.globals()[b"modules"] = self.lua.table()
        for name in ("Marshal", "Unmarshal", "Saved", "SavedBinary", "SaveExport", "SaveImport"):
            self.lua.globals()[b"modules"][name.encode()] = self.lua.execute(
                (PROTOTYPE / ("CBRPQ"+name+".lua")).read_bytes())
        for name in ("Native", "Persistence"):
            self.lua.globals()[(name+"Factory").encode()] = self.lua.execute(
                (PROTOTYPE / ("CBRPQ"+name+".lua")).read_bytes())
        self.lua.globals()[b"base"] = BASE
        self.lua.execute(b'''
            EEex_UDToPtr=function(object) return object.pointer end
            EEex_Utility_IterateCPtrList=function(list,fn)
                for _,effect in ipairs(list) do if fn(effect) then break end end
            end
            native=NativeFactory(_G,{sources={POTN36={keys={linked=true},records={linked=fields}}}})
            potion={pointer=base+0x1000}; foreign={pointer=base+0x2000}
            input.pointer=base+0xF000; input.list=base+0xF100
            output.pointer=base+0x10000; output.list=base+0x10100
            input.m_timedEffectList={foreign,potion}; output.m_timedEffectList={}
            native.bindLinked(potion,'POTN36','linked')
            for _,effect in ipairs(input.m_timedEffectList) do
                EEex_WriteU32(effect.pointer+0x24,4096); EEex_WriteU32(effect.pointer+0x28,3700)
            end
            sprites={[input.pointer]=input,[output.pointer]=output}
            lifetimes={[input.pointer]={},[output.pointer]={}}
            invalidations,reports={},{}; timedListReads=0
            adapter={
                timedListPointer=function(sprite) timedListReads=timedListReads+1; return sprite.list end,
                spriteFromPointer=function(pointer) return assert(sprites[pointer]) end,
                spriteIdentity=function(pointer) return lifetimes[pointer] end,
                hasDelivery=function() return false end,
                onInvalidate=function(reason) invalidations[#invalidations+1]=reason end,
                report=function(reason) reports[#reports+1]=reason end,
            }
            originalCalculate=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize
            originalWrite=EEex_Sprite_Hook_WriteExtraEffectListMarshal
            originalRead=EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal
            persistence=PersistenceFactory(_G,modules,native,adapter,'CBRPQ')
            function throws(fn,pattern)
                local ok,why=pcall(fn)
                assert(not ok and tostring(why):find(pattern,1,true),tostring(why))
            end
            function bind()
                local plan=persistence.bindings()
                assert(#plan.replacements==3 and plan.registry==EEex_Sprite_Private_MarshalHandlers)
                -- Test-only atomic publication in this isolated Lua state.
                EEex_Sprite_AddMarshalHandlers(plan.handlerName,plan.exporter,plan.importer)
                for _,binding in ipairs(plan.replacements) do _G[binding.name]=binding.replacement end
            end
            foreignCalls=0
            function addForeign(exporter,importer)
                EEex_Sprite_AddMarshalHandlers('FOREIGN',exporter or function() return {preserved=1234} end,
                    importer or function(sprite,data) assert(data.preserved==1234); foreignCalls=foreignCalls+1 end)
                -- Force a permitted stock pairs order: the foreign importer
                -- runs BEFORE ours. Its copying must see restored provenance.
                local originalPairs=pairs
                pairs=function(t)
                    if t==EEex_Sprite_Private_MarshalHandlers then
                        local keys={'FOREIGN','CBRPQ'}; local i=0
                        return function() i=i+1; local k=keys[i]; if k then return k,t[k] end end
                    end
                    return originalPairs(t)
                end
            end
            function beginExport()
                assert(persistence.marshalEnter(base+0x30000,input.list,1,0,1))
                assert(persistence.marshalCounted(base+0x30000,input.list,#input.m_timedEffectList*0x108))
            end
            function calculate()
                oldCount=#input.m_timedEffectList
                extra=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(input)
                serializedBytes=oldCount*0x108+extra
                metadataBytes=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize+8
                dataPointer=base+0x40000
                footer=dataPointer+#input.m_timedEffectList*0x108
                return serializedBytes
            end
            function finishExport()
                EEex_Sprite_Hook_WriteExtraEffectListMarshal(dataPointer+oldCount*0x108)
                assert(persistence.marshalLeave(base+0x30000))
                assert(not persistence.hasLive())
            end
            function copyFields(destination,source)
                for offset=0,0x154,4 do
                    EEex_WriteU32(destination.pointer+offset,EEex_ReadU32(source.pointer+offset))
                end
            end
            function prepareLoad(expectEnabled)
                assert(persistence.reset()==(expectEnabled~=false))
                assert(persistence.unmarshalEnter(base+0x31000,output.list,dataPointer,serializedBytes,output.pointer,1))
                loadedForeign={pointer=base+0x4000}; loadedPotion={pointer=base+0x5000}
                copyFields(loadedForeign,foreign); copyFields(loadedPotion,potion)
                -- Source-proven V2 field projection, not execution of native Unmarshal.
                for _,effect in ipairs({loadedForeign,loadedPotion}) do
                    EEex_WriteU32(effect.pointer+0x110,0)
                    EEex_WriteU32(effect.pointer+0x11C,3700)
                    EEex_WriteU32(effect.pointer+0x150,4294967295)
                end
                output.m_timedEffectList={loadedForeign,loadedPotion}
            end
            function readLoad()
                return EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(output,footer)
            end
            function finishLoad()
                assert(persistence.unmarshalLeave(base+0x31000))
                assert(not persistence.hasLive())
            end
        ''')

    def export(self):
        self.lua.execute(b"bind(); beginExport(); calculate(); finishExport()")
        footer = self.lua.globals()[b"footer"]
        self.assertEqual(b"X-BIV1.0", self.fixture.memory[int(footer-BASE):int(footer-BASE+8)])

    def corrupt_schema(self):
        offset = int(self.lua.globals()[b"footer"] - BASE)
        pos = self.fixture.memory.index(b"version\0", offset) + len(b"version\0")
        self.assertIn(self.fixture.memory[pos], (3, 4))
        self.fixture.memory[pos+1] = 99

    def test_factory_is_inert_and_binding_plan_requires_all_three_unchanged_functions(self):
        self.lua.execute(b'''
            assert(not persistence.hasLive() and persistence.status().enabled)
            assert(EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize==originalCalculate)
            assert(EEex_Sprite_Hook_WriteExtraEffectListMarshal==originalWrite)
            assert(EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal==originalRead)
            assert(EEex_Sprite_Private_MarshalHandlers.CBRPQ==nil)
            local plan=persistence.bindings()
            assert(plan.replacements[1].original==originalCalculate)
            assert(plan.replacements[2].original==originalWrite)
            assert(plan.replacements[3].original==originalRead)
            EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal=function() end
            throws(persistence.bindings,'function changed before binding')
        ''')

    def test_missing_lifetime_service_or_existing_handler_is_a_concrete_startup_error(self):
        self.lua.execute(b'''
            local identity=adapter.spriteIdentity; adapter.spriteIdentity=nil
            throws(function() PersistenceFactory(_G,modules,native,adapter) end,'spriteIdentity')
            adapter.spriteIdentity=identity
            EEex_Sprite_Private_MarshalHandlers.CBRPQ={}
            throws(function() PersistenceFactory(_G,modules,native,adapter) end,'namespace already registered')
        ''')

    def test_actual_serializer_roundtrip_preserves_owner_among_identical_foreign_records(self):
        self.lua.execute(b"addForeign()")
        self.export()
        self.lua.execute(b'''
            prepareLoad()
            assert(native.identify(loadedPotion,nil,false)==nil)
            assert(readLoad()*0x108==metadataBytes)
            assert(native.identify(loadedPotion,'linked',false).ownerSource=='POTN36')
            assert(native.identify(loadedForeign,nil,false)==nil)
            assert(foreignCalls==1 and #ignoredErrors==0)
            assert(persistence.status().enabled)
            finishLoad()
        ''')

    def test_foreign_importer_copies_then_destroys_owner_before_our_registered_importer(self):
        self.lua.execute(b'''
            addForeign(nil,function(sprite,data)
                foreignCalls=foreignCalls+1; assert(data.preserved==1234)
                assert(native.identify(loadedPotion,'linked',false))
                cloned={pointer=base+0x6000}; copyFields(cloned,loadedPotion)
                EEex_WriteU32(cloned.pointer+0x114,0)
                EEex_WriteU32(cloned.pointer+0x11C,3700)
                EEex_WriteU32(cloned.pointer+0x150,4294967295)
                assert(persistence.effectCopy(cloned,loadedPotion.pointer))
                assert(persistence.effectDestroy(loadedPotion.pointer))
                sprite.m_timedEffectList={cloned,loadedForeign}
                assert(native.identify(loadedPotion,nil,false)==nil)
            end)
        ''')
        self.export()
        self.lua.execute(b'''
            prepareLoad(); readLoad(); finishLoad()
            assert(native.identify(cloned,'linked',false).ownerSource=='POTN36')
            assert(native.identify(loadedForeign,nil,false)==nil)
            assert(foreignCalls==1 and #ignoredErrors==0 and persistence.status().enabled)
        ''')

    def test_invalid_schema_disables_before_foreign_import_but_preserves_native_return(self):
        self.lua.execute(b'''
            addForeign(nil,function(sprite,data)
                foreignCalls=foreignCalls+1
                assert(not persistence.status().enabled and persistence.hasLive())
                assert(native.identify(loadedPotion,nil,false)==nil)
                throws(persistence.reset,'in-flight native persistence')
            end)
        ''')
        self.export()
        self.corrupt_schema()
        self.lua.execute(b'''
            prepareLoad(); assert(readLoad()*0x108==metadataBytes)
            assert(persistence.hasLive() and #invalidations==1 and #ignoredErrors==0)
            finishLoad()
            assert(not persistence.reset() and not persistence.status().enabled)
            assert(foreignCalls==1)
        ''')

    def test_disabled_before_import_never_binds_valid_metadata_but_foreign_import_still_runs(self):
        self.lua.execute(b'''
            addForeign(nil,function()
                foreignCalls=foreignCalls+1
                assert(not persistence.status().enabled and persistence.hasLive())
                assert(native.identify(loadedPotion,nil,false)==nil)
            end)
        ''')
        self.export()
        self.lua.execute(b'''
            persistence.invalidate('earlier ownership failure')
            prepareLoad(false); assert(readLoad()*0x108==metadataBytes); finishLoad()
            assert(foreignCalls==1 and #invalidations==1 and #ignoredErrors==0)
            assert(native.identify(loadedPotion,nil,false)==nil)
        ''')
    def test_invalidated_export_keeps_foreign_metadata_and_writes_explicit_invalid_marker(self):
        self.lua.execute(b'''
            addForeign(function()
                persistence.invalidate('owned lifetime mismatch')
                assert(persistence.hasLive())
                return {preserved=1234}
            end)
            bind(); beginExport(); calculate()
            assert(persistence.hasLive() and not persistence.status().enabled)
            throws(persistence.reset,'in-flight native persistence')
            finishExport()
            local result,blocks=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.invalid and blocks*0x108==metadataBytes)
            assert(#invalidations==1 and #reports==1 and #ignoredErrors==0)
            -- Native context can be entered and left even after ownership halted.
            beginExport(); calculate(); finishExport()
            result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.invalid and not persistence.status().enabled)
        ''')

    def test_foreign_export_list_growth_uses_real_allocation_and_footer_delta(self):
        self.lua.execute(b'''
            addForeign(function(sprite)
                sprite.m_timedEffectList[#sprite.m_timedEffectList+1]={pointer=base+0x7000}
                copyFields(sprite.m_timedEffectList[3],foreign)
                return {preserved=1234}
            end)
            bind(); beginExport(); calculate()
            assert(oldCount==2 and #input.m_timedEffectList==3)
            assert(serializedBytes==3*0x108+metadataBytes)
            finishExport()
            assert(EEex_ReadString(footer)=='X-BIV1.0FOREIGN')
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            local _,group=next(result.groups)
            assert(group.count==3 and group.owned[2].source=='POTN36')
        ''')

    def test_corrupt_binary_disables_without_retrying_foreign_reader_and_keeps_context(self):
        self.lua.execute(b"addForeign()")
        self.export()
        self.fixture.memory[int(self.lua.globals()[b"footer"] - BASE)] = 0
        self.lua.execute(b'''
            prepareLoad()
            throws(readLoad,'signature')
            assert(foreignCalls==0 and not persistence.status().enabled and persistence.hasLive())
            assert(native.identify(loadedPotion,nil,false)==nil)
            finishLoad()
        ''')

    def test_stock_tryignore_does_not_hide_changed_ownership_handler(self):
        self.lua.execute(b'''
            addForeign(nil,function()
                foreignCalls=foreignCalls+1
                EEex_Sprite_Private_MarshalHandlers.CBRPQ.importer=function(sprite,data)
                    data.version=99; persistence.importer(sprite,data)
                end
            end)
        ''')
        self.export()
        self.lua.execute(b'''
            prepareLoad()
            throws(readLoad,'handler failed, disappeared, or changed')
            assert(not persistence.status().enabled and #ignoredErrors==1 and foreignCalls==1)
            assert(persistence.hasLive()); finishLoad()
        ''')

    def test_nested_projectile_sentinel_does_not_borrow_sprite_baseline(self):
        self.export()
        self.lua.execute(b'''
            prepareLoad()
            assert(persistence.unmarshalEnter(base+0x32000,base+0x32010,0,0,0,1))
            assert(persistence.hasLive())
            assert(persistence.unmarshalLeave(base+0x32000))
            readLoad(); finishLoad()
            assert(persistence.status().enabled)
        ''')

    def test_sprite_pointer_reuse_before_metadata_read_is_rejected_before_foreign_callbacks(self):
        self.lua.execute(b"addForeign()")
        self.export()
        self.lua.execute(b'''
            prepareLoad(); lifetimes[output.pointer]={}
            throws(readLoad,'sprite lifetime changed')
            assert(foreignCalls==0 and persistence.hasLive() and not persistence.status().enabled)
            finishLoad()
        ''')

    def test_require_sprite_refuses_unobserved_allocation_without_native_field_reads(self):
        self.lua.execute(b'''
            local token=persistence.requireSprite(input)
            assert(token==lifetimes[input.pointer])
            lifetimes[input.pointer]=nil
            local before=timedListReads
            throws(function() persistence.requireSprite(input) end,'lifetime was not observed')
            assert(persistence.status().enabled) -- pure preflight, caller contains errors
            bind(); beginExport()
            throws(calculate,'lifetime was not observed')
            assert(timedListReads==before,'dereferenced retired sprite timed-list field')
            assert(not persistence.status().enabled)
            assert(persistence.marshalLeave(base+0x30000))
        ''')

    def test_only_exact_inflight_sprite_lifecycle_changes_invalidate(self):
        self.export()
        self.lua.execute(b'''
            prepareLoad()
            assert(persistence.onSpriteRetire(input.pointer,lifetimes[input.pointer]))
            assert(persistence.onContentsReset(output.pointer,{}))
            assert(persistence.status().enabled)
            assert(not persistence.onContentsReset(output.pointer,lifetimes[output.pointer]))
            assert(not persistence.status().enabled and persistence.hasLive())
            readLoad(); finishLoad()
            assert(native.identify(loadedPotion,nil,false)==nil)
        ''')

    def test_exporter_target_reset_recovers_invalid_marker_before_native_sizing(self):
        self.lua.execute(b'''
            addForeign(function(sprite)
                assert(not persistence.onContentsReset(sprite.pointer,lifetimes[sprite.pointer]))
                return {preserved=1234}
            end)
            bind(); beginExport(); calculate(); finishExport()
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.invalid and not persistence.status().enabled)
        ''')

    def test_effect_pointer_reuse_does_not_inherit_owner_after_failure(self):
        self.lua.execute(b'''
            local old=native.identify(potion,'linked',false).identity
            persistence.invalidate('halt during native operation')
            assert(persistence.effectDestroy(potion.pointer))
            assert(native.identify(potion,nil,false)==nil)
            local records=native.savedRecords(input)
            assert(records[2].identity~=old)
            assert(not persistence.status().enabled)
        ''')

    def test_pending_native_delivery_exports_invalid_marker_without_aborting_foreign_save(self):
        self.lua.execute(b'''
            addForeign(); adapter.hasDelivery=function() return true end
            bind(); beginExport(); calculate(); finishExport()
            assert(not persistence.status().enabled)
            assert(persistence.status().failure:find('delivery survives the save boundary',1,true))
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.invalid and #ignoredErrors==0)
        ''')

    def test_bad_copy_disables_and_does_not_publish_destination_ownership(self):
        self.lua.execute(b'''
            cloned={pointer=base+0x6000}; copyFields(cloned,potion)
            EEex_WriteU32(cloned.pointer+0x1C,41)
            assert(not persistence.effectCopy(cloned,potion.pointer))
            assert(not persistence.status().enabled and native.identify(cloned,nil,false)==nil)
            assert(persistence.effectDestroy(potion.pointer))
            assert(native.identify(potion,nil,false)==nil)
        ''')

    def test_failed_invalidation_notification_does_not_discard_inflight_export(self):
        self.lua.execute(b'''
            adapter.onInvalidate=function() error('runtime notification failed') end
            bind(); beginExport(); persistence.invalidate('bad ownership')
            calculate(); finishExport()
            local status=persistence.status()
            assert(not status.enabled and status.notificationFailure:find('notification failed',1,true))
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.invalid)
        ''')

    def test_unbalanced_returns_disable_but_allow_actual_ordered_cleanup(self):
        self.lua.execute(b'''
            assert(persistence.marshalEnter(100,input.list,0,0,0))
            assert(persistence.marshalEnter(200,input.list,0,0,0))
            assert(not persistence.marshalLeave(100))
            assert(persistence.hasLive() and not persistence.status().enabled)
            assert(persistence.marshalLeave(200))
            assert(persistence.marshalLeave(100))
            assert(not persistence.hasLive() and not persistence.reset())
        ''')

    def test_failed_writer_retains_pending_allocation_and_refuses_reset(self):
        # Inject before factory construction so the real serializer's primitive
        # failure is observed through SaveExport.write's original function.
        self.lua.execute(b'''
            local actualWrite=EEex_WriteLString
            EEex_WriteLString=function() error('bounded writer primitive failed') end
            bind(); beginExport(); calculate()
            throws(finishExport,'bounded writer primitive failed')
            assert(persistence.status().writePending and not persistence.status().enabled)
            assert(persistence.marshalLeave(base+0x30000))
            assert(persistence.hasLive())
            throws(persistence.reset,'in-flight native persistence')
            EEex_WriteLString=actualWrite
        ''')

    def test_late_invalidation_changes_exactly_one_serialized_byte_and_preserves_canaries(self):
        self.lua.execute(b'''
            addForeign(); bind(); beginExport(); calculate()
            -- Obtain a reference serialization with the same real writer and
            -- exact table identities. Restore only its four global scratch
            -- slots in this isolated test; production never does this.
            local names={'EEex_Sprite_Private_CurrentSpriteMarshalHandlerData',
                'EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableSize',
                'EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta',
                'EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize'}
            local scratch={}; for _,name in ipairs(names) do scratch[name]=_G[name] end
            originalWrite(base+0x60000)
            for _,name in ipairs(names) do _G[name]=scratch[name] end
            beforeCollection=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData
            beforeMeta=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta
            beforeSize=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize
            beforeExact=EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(beforeCollection)
            foreignData=nil; ownData=nil
            for _,value in pairs(beforeCollection) do
                if beforeMeta[value].handlerName=='FOREIGN' then foreignData=value else ownData=value end
            end
            beforeGroups=ownData.groups
            assert(ownData.version==1)
            persistence.invalidate('failure after sizing')
            persistence.invalidate('repeated report')
            assert(ownData.version==0 and ownData.groups==beforeGroups)
            assert(EEex_Sprite_Private_CurrentSpriteMarshalHandlerData==beforeCollection)
            assert(EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta==beforeMeta)
            assert(EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize==beforeSize)
            assert(EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(beforeCollection)==beforeExact)
            assert(foreignData.preserved==1234 and persistence.status().invalidationError==nil)
        ''')
        footer = int(self.lua.globals()[b"footer"] - BASE)
        size = int(self.lua.globals()[b"metadataBytes"])
        self.fixture.memory[footer-32:footer] = b"\xA5" * 32
        self.fixture.memory[footer+size:footer+size+32] = b"\x5A" * 32
        expected = bytes(self.fixture.memory[0x60000:0x60000+size])
        self.lua.execute(b"finishExport(); assert(not persistence.reset())")
        actual = bytes(self.fixture.memory[footer:footer+size])
        changes = [(left,right) for left,right in zip(expected,actual) if left != right]
        self.assertEqual([(1,0)], changes)
        self.assertEqual(b"\xA5" * 32, self.fixture.memory[footer-32:footer])
        self.assertEqual(b"\x5A" * 32, self.fixture.memory[footer+size:footer+size+32])
        self.lua.execute(b'''
            local data,count=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(data.version==0 and count*0x108==metadataBytes)
            -- A fresh enabled composition must reject this saved ownership;
            -- testing only the already-disabled old instance would miss a bug.
            EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize=originalCalculate
            EEex_Sprite_Hook_WriteExtraEffectListMarshal=originalWrite
            EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal=originalRead
            EEex_Sprite_Private_MarshalHandlers.CBRPQ=nil
            native=NativeFactory(_G,{sources={POTN36={keys={linked=true},records={linked=fields}}}})
            persistence=PersistenceFactory(_G,modules,native,adapter,'CBRPQ')
            bind(); prepareLoad(); assert(persistence.status().enabled)
            assert(readLoad()*0x108==metadataBytes)
            assert(not persistence.status().enabled and native.identify(loadedPotion,nil,false)==nil)
            assert(foreignCalls==1 and #ignoredErrors==0)
            assert(persistence.status().failure:find('unsupported schema',1,true))
            finishLoad(); assert(not persistence.reset())
        ''')

    def test_recovered_invalid_placeholder_remains_fixed_size_when_invalidated_later(self):
        self.lua.execute(b'''
            addForeign()
            input.aux.EEex_Sprite_FallbackMarshalStorage={CBRPQ={version=1,groups={}}}
            bind(); beginExport(); calculate()
            local collection=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData
            local metadata=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta
            local exact=EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(collection)
            local allocated=EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize
            local recovered
            for _,value in pairs(collection) do
                if metadata[value].handlerName=='CBRPQ' then recovered=value end
            end
            assert(recovered.invalid and recovered.version==1 and #recovered.previous==2)
            local previous=recovered.previous
            persistence.invalidate('later lifecycle failure')
            assert(recovered.version==0 and recovered.previous==previous)
            assert(EEex_Sprite_Private_CurrentSpriteMarshalHandlerData==collection)
            assert(EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(collection)==exact)
            assert(EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize==allocated)
            finishExport()
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.version==0 and result.invalid and #result.previous==2)
        ''')

    def test_sprite_lifetime_mismatch_after_sizing_is_not_repaired_by_version_zero(self):
        self.lua.execute(b'''
            bind(); beginExport(); calculate()
            local old=lifetimes[input.pointer]
            assert(not persistence.onSpriteRetire(input.pointer,old))
            lifetimes[input.pointer]={}
            local reads=timedListReads
            throws(finishExport,'sprite lifetime changed')
            assert(timedListReads==reads and persistence.status().writePending)
            assert(persistence.marshalLeave(base+0x30000))
            throws(persistence.reset,'in-flight native persistence')
        ''')
        footer = int(self.lua.globals()[b"footer"] - BASE)
        self.assertEqual(b"\0" * 8, self.fixture.memory[footer:footer+8])

    def test_reentrant_invalidation_after_writer_started_is_diagnosed_without_claimed_repair(self):
        self.lua.execute(b'''
            bind(); beginExport(); calculate()
            local writeSignature=EEex_WriteLString
            EEex_WriteLString=function(...)
                writeSignature(...)
                persistence.invalidate('reentrant replaced writer')
            end
            throws(finishExport,'after writer began; output is not repaired')
            assert(persistence.status().invalidationError:find('after writer began',1,true))
            assert(persistence.status().writePending and not persistence.status().enabled)
            -- This intentionally unsupported writer already emitted bytes. Its
            -- still-version1 block is the negative control, NOT accepted output.
            local result=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(result.version==1)
            assert(persistence.marshalLeave(base+0x30000))
            throws(persistence.reset,'in-flight native persistence')
            EEex_WriteLString=writeSignature
        ''')

    def test_changed_pending_collection_prevents_invalidation_and_writer_without_extra_bytes(self):
        self.lua.execute(b'''
            bind(); beginExport(); calculate()
            EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize=
                EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize+1
            persistence.invalidate('late failure')
            assert(persistence.status().invalidationError:find('allocation/collection changed',1,true))
            throws(finishExport,'pending ownership invalidation failed')
            assert(persistence.status().writePending)
            assert(persistence.marshalLeave(base+0x30000))
        ''')
        footer = int(self.lua.globals()[b"footer"] - BASE)
        self.assertEqual(b"\0" * 8, self.fixture.memory[footer:footer+8])


if __name__ == "__main__":
    unittest.main()
