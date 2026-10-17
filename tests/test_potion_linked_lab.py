"""Lab/linked/persistence/lifetime composition; native patching is doubled.

Uses the actual EEex Lua serializer and real local Lua modules. It deliberately
does not install hooks, allocate executable memory, or open a game/save.
"""
import unittest

from tests import test_potion_persistence as persistence_fixture

EEEX = persistence_fixture.EEEX
PROTOTYPE = persistence_fixture.PROTOTYPE


@unittest.skipUnless(EEEX, "set EEEX_LUA_DIR for the actual EEex Lua serializer")
class LinkedLabTests(unittest.TestCase):
    def setUp(self):
        self.fixture = persistence_fixture.PotionPersistenceTests()
        self.fixture.setUp()
        self.lua = self.fixture.lua
        self.lua.globals()[b"folder"] = PROTOTYPE.as_posix().encode()
        self.lua.execute(b'''
            events,notices,listeners={},{},{}
            function event(text) events[#events+1]=text end
            function report(reason) notices[#notices+1]=tostring(reason) end
            function provider(name)
                return {
                    validate=function(api,config)
                        event('validate:'..name)
                        if failedValidation==name then error('preflight '..name) end
                    end,
                    install=function(api,config)
                        event('install:'..name)
                        if failedInstall==name then error('install '..name) end
                    end,
                }
            end
            EEex_GetImageBase=function() return 0x140000000 end
            earlyMemory={}
            EEex_ReadPtr=function(pointer)
                if earlyMemory[pointer]~=nil then return earlyMemory[pointer] end
                return EEex_ReadU64(pointer)
            end
            EEex_HookIntegrityWatchdog_Load=false
            EEex_GenLuaCall=function() error('native generation is doubled in this composition test') end
            EEex_FlattenTable=function() error('native generation is doubled in this composition test') end
            EEex_PtrToUD=function(pointer,kind)
                assert(kind=='CGameSprite'); return assert(sprites[pointer])
            end
            EEex_DisableCodeProtection=function() event('protection:off') end
            EEex_EnableCodeProtection=function() event('protection:on') end
            EEex_HookBeforeRestoreWithLabels=function(address,...) event('install:descriptor:'..address) end
            EEex_GameState_AddDestroyedListener=function(fn) listeners[#listeners+1]=fn end
            local originalLifetime=dofile(folder..'/CBRPQSpriteLifetime.lua')
            -- Only native instruction preflight/patching is doubled here;
            -- the registry receives real constructor/readiness events below.
            local lifetime={new=originalLifetime.new,prepare=function()
                event('validate:sprite')
                if failedValidation=='sprite' then error('preflight sprite') end
                local descriptors={}
                for i=1,6 do descriptors[i]={address=100+i,restoreSize=5,labels={},assembly='native patch double'} end
                return {base=EEex_GetImageBase(),watchdog=false,descriptors=descriptors}
            end}
            manifest={policy='unique',families={POTN36={hp=false,genius=false}},sources={
                POTN36={family='POTN36',keys={linked=true},records={linked=fields},abilities={}}
            }}
            parts={core=dofile(folder..'/CBRPQCore.lua'),messages=dofile(folder..'/CBRPQMessages.lua'),
                native=function() return native end,runtime=dofile(folder..'/CBRPQRuntime.lua'),
                linked=dofile(folder..'/CBRPQLinked.lua'),lineage=dofile(folder..'/CBRPQLineage.lua'),
                persistence=PersistenceFactory,marshal=modules.Marshal,unmarshal=modules.Unmarshal,
                saved=modules.Saved,savedBinary=modules.SavedBinary,saveExport=modules.SaveExport,saveImport=modules.SaveImport,
                spriteLifetime=lifetime,transport=provider('transport'),hook=provider('admit'),
                castTransport=provider('cast'),marshalTransport=provider('marshal'),
                unmarshalTransport=provider('unmarshal'),copyTransport=provider('copy'),
            }
            labModule=dofile(folder..'/CBRPQLab.lua')
            function prepareLab() lab=labModule.prepare(_G,parts,manifest,report); return lab end
            function birth(sprite)
                sprite.list=sprite.pointer+0x4A00
                sprite.m_timedEffectList.pointer=sprite.list
                EEex_WriteU64(sprite.pointer,0x140598B68)
                EEex_WriteU64(sprite.pointer+0x1A08,0x14058F528)
                assert(CBRPQ_Early_beginDefault(sprite.pointer))
                assert(CBRPQ_Early_readyDefault(sprite.pointer))
            end
            function usePreparedPersistence()
                persistence=lab.linked.persistence
                birth(input); birth(output)
            end
            function assertUnbound()
                assert(EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize==originalCalculate)
                assert(EEex_Sprite_Hook_WriteExtraEffectListMarshal==originalWrite)
                assert(EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal==originalRead)
                assert(EEex_Sprite_Private_MarshalHandlers.CBRPQ==nil)
            end
            function useRegenBoundaryDouble()
                fields.opcode=98
                parts.regenAdapter={};parts.regenCache={};parts.regenRecovery={};parts.regenServices={}
                parts.regenNative={new=function(api,reader,lifetime,dependencies,onFailure)
                    assert(reader==native and type(lifetime.identity)=='function')
                    local prepared=false
                    regenFailure=onFailure
                    return {
                        callbacks={appendOwned=function() end,updateExit=function() onFailure('deferred cache failure') end},
                        validateServices=function() event('validate:regen-services') end,
                        prepareServices=function()
                            event('prepare:regen-services')
                            if failedPreparation then error('JIT failed') end
                            prepared=true
                        end,
                        status=function() return {servicesPrepared=prepared,halted=false} end,
                        prepare=function() error('not used by this boundary test') end,
                        onOriginalDestroy=function() event('regen:original-destroy') end,
                        onSpriteDestroy=function() event('regen:sprite-destroy') end,
                        reset=function() event('regen:reset') end,
                    }
                end}
                parts.regenLifecycle={prepare=function(api,config)
                    event('validate:regen-lifecycle')
                    assert(config.callbacks.appendOwned=='CBRPQ_Lab_regen_appendOwned')
                    return {watchdog=false,descriptors={{address=456,restoreSize=5,labels={},assembly='regen patch double'}}}
                end}
            end
            earlyModule=dofile(folder..'/CBRPQEarly.lua')
            EEex_Active=false; earlyMemory[EEex_GetImageBase()+0x667548]=0
            earlyBootstrap=earlyModule.prepare(_G,{spriteLifetime=lifetime},{report=report})
            earlyReceipt=earlyBootstrap.arm()
            parts.earlyReceipt=earlyReceipt
            EEex_Active=true;earlyMemory[EEex_GetImageBase()+0x667548]=base+0x20000
            earlyMemory[base+0x20000+0x1090]=0
            -- Separate the six doubled early installs from later composition.
            events={}
        ''')

    def test_prepare_validates_every_provider_without_patching_or_binding(self):
        self.lua.execute(b'''
            prepareLab(); assertUnbound()
            assert(table.concat(events,',')=='validate:transport,validate:admit,validate:cast,validate:marshal,validate:unmarshal,validate:copy')
            assert(not lab.armed and not lab.attempted and #listeners==1)
            assert(type(CBRPQ_Lab_childCreated)=='function' and type(CBRPQ_Lab_marshalEnter)=='function')
            throws(lab.linked.bind,'observers are not installed')
            assertUnbound()
        ''')

    def test_arm_binds_all_three_wrappers_only_after_every_native_observer(self):
        self.lua.execute(b'''
            prepareLab(); lab.arm()
            assert(lab.armed and lab.attempted)
            local text=table.concat(events,',')
            assert(text:find('validate:copy,install:transport,install:marshal,install:unmarshal,install:copy,install:cast,install:admit',1,true))
            assert(not text:find('install:descriptor:',1,true))
            assert(earlyBootstrap.status().attached and lab.linked.lifetime==earlyReceipt.registry)
            local p=lab.linked.persistence
            assert(EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize==p.calculate)
            assert(EEex_Sprite_Hook_WriteExtraEffectListMarshal==p.write)
            assert(EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal==p.read)
            assert(EEex_Sprite_Private_MarshalHandlers.CBRPQ.exporter==p.exporter)
            assert(EEex_Sprite_Private_MarshalHandlers.CBRPQ.importer==p.importer)
            throws(lab.arm,'already attempted')
        ''')

    def test_real_serializer_uses_lifetime_and_persistence_bound_by_lab(self):
        self.lua.execute(b'''
            prepareLab(); lab.arm(); usePreparedPersistence()
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function() return {unchanged=77} end,function() end)
            beginExport(); calculate(); finishExport()
            assert(persistence.status().enabled and not persistence.hasLive())
            assert(lab.runtime.status() and #notices==0)
            local data,count=modules.SavedBinary.read(EEex_ReadU8,footer,dataPointer+serializedBytes,'CBRPQ')
            assert(data.version==1 and count*0x108==metadataBytes)
            local fingerprint,group=next(data.groups)
            assert(fingerprint and next(data.groups,fingerprint)==nil)
            assert(group.count==2 and group.owned[2].source=='POTN36')
        ''')

    def test_late_validation_conflict_keeps_all_serializer_functions_original(self):
        self.lua.execute(b'''
            prepareLab(); failedValidation='copy'
            throws(lab.arm,'preflight copy')
            assert(not lab.attempted); assertUnbound()
            for _,event in ipairs(events) do assert(not event:find('install:',1,true)) end
        ''')

    def test_partial_patch_failure_halts_and_leaves_serializer_unbound(self):
        self.lua.execute(b'''
            prepareLab(); failedInstall='copy'
            throws(lab.arm,'restart required')
            assert(lab.attempted and not lab.armed and not lab.runtime.status())
            assertUnbound()
            throws(lab.arm,'already attempted')
            -- Lifetime cleanup must continue even after policy has halted.
            assert(native.identify(potion,'linked',false))
            CBRPQ_Lab_effectDestroy(potion.pointer)
            assert(native.identify(potion,nil,false)==nil)
        ''')

    def test_late_callback_or_serializer_replacement_prevents_first_patch(self):
        self.lua.execute(b'''
            prepareLab()
            local saved=CBRPQ_Lab_childCreated
            CBRPQ_Lab_childCreated=function() end
            throws(lab.arm,'callback changed'); assert(not lab.attempted)
            CBRPQ_Lab_childCreated=saved
            EEex_Sprite_Hook_WriteExtraEffectListMarshal=function() end
            throws(lab.arm,'function changed before binding'); assert(not lab.attempted)
            assert(EEex_Sprite_Private_MarshalHandlers.CBRPQ==nil)
            for _,event in ipairs(events) do assert(not event:find('install:',1,true)) end
        ''')

    def test_namespace_collision_does_not_publish_partial_callbacks(self):
        self.lua.execute(b'''
            local foreign=function() end; CBRPQ_Lab_childCreated=foreign
            throws(prepareLab,'namespace is already occupied')
            assert(CBRPQ_Lab_childCreated==foreign)
            assert(CBRPQ_Lab_admit==nil and CBRPQ_Lab_marshalEnter==nil and CBRPQ_Lab_reset==nil)
            assertUnbound(); assert(#listeners==0)
        ''')

    def test_failed_prepare_removes_all_owned_callbacks(self):
        self.lua.execute(b'''
            failedValidation='marshal'; throws(prepareLab,'preflight marshal')
            for key in pairs(_G) do assert(not key:find('CBRPQ_Lab_',1,true),key) end
            assertUnbound(); assert(#listeners==0)
            assert(not earlyBootstrap.status().attached)
        ''')

    def test_early_actor_keeps_its_identity_and_foreign_save_handlers_after_handoff(self):
        self.lua.execute(b'''
            birth(input);local earlyIdentity=earlyReceipt.registry.identity(input.pointer)
            prepareLab();lab.arm();persistence=lab.linked.persistence
            assert(persistence.requireSprite(input)==earlyIdentity)
            -- No owned bonus is necessary for an ordinary actor to be saved.
            input.m_timedEffectList={foreign};input.m_timedEffectList.pointer=input.list
            local calls=0
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function() calls=calls+1;return {preserved=77} end,function() end)
            beginExport();calculate();finishExport()
            assert(calls==1 and persistence.status().enabled and lab.runtime.status())
            assert(#notices==0)
        ''')

    def test_missing_early_receipt_fails_before_late_callbacks_or_patches(self):
        self.lua.execute(b'''
            parts.earlyReceipt=nil;throws(prepareLab,'completed early lifetime receipt is required')
            assertUnbound();assert(#events==0 and #listeners==0)
            for key in pairs(_G) do assert(not key:find('CBRPQ_Lab_',1,true),key) end
        ''')

    def test_existing_game_or_changed_early_callback_prevents_late_install(self):
        self.lua.execute(b'''
            prepareLab()
            earlyMemory[base+0x20000+0x1090]=base+0x25000
            throws(lab.arm,'CInfGame already exists')
            assert(not lab.attempted and not earlyBootstrap.status().attached)
            earlyMemory[base+0x20000+0x1090]=0
            CBRPQ_Early_clear=function() end
            throws(lab.arm,'published callback changed')
            assert(not lab.attempted and not earlyBootstrap.status().attached)
            assertUnbound()
            for _,event in ipairs(events) do assert(not event:find('install:',1,true)) end
        ''')

    def test_unknown_actor_is_not_adopted_and_quiescent_reset_rotates_known_tokens(self):
        self.lua.execute(b'''
            prepareLab(); lab.arm()
            persistence=lab.linked.persistence
            throws(function() persistence.requireSprite(input) end,'lifetime was not observed')
            usePreparedPersistence()
            local old=persistence.requireSprite(input)
            listeners[1]()
            assert(old~=persistence.requireSprite(input))
            assert(lab.runtime.status() and persistence.status().enabled)
        ''')

    def test_regeneration_prepares_before_first_patch_and_later_failure_disables_policy(self):
        self.lua.execute(b'''
            useRegenBoundaryDouble(); prepareLab(); lab.arm()
            local text=table.concat(events,',')
            assert(text:find('validate:regen-lifecycle,prepare:regen-services,install:transport',1,true))
            assert(lab.armed and lab.linked.regeneration.status().servicesPrepared)
            CBRPQ_Lab_regen_updateExit()
            assert(not lab.runtime.status() and not lab.linked.persistence.status().enabled)
            assert(notices[#notices]:find('deferred cache failure',1,true))
        ''')

    def test_failed_native_service_preparation_occurs_before_any_hook_patch_or_wrapper_binding(self):
        self.lua.execute(b'''
            useRegenBoundaryDouble(); prepareLab(); failedPreparation=true
            throws(lab.arm,'JIT failed');assert(lab.attempted and not lab.armed)
            assertUnbound()
            for _,event in ipairs(events) do assert(not event:find('install:',1,true)) end
            throws(lab.arm,'already attempted')
        ''')


if __name__ == '__main__':
    unittest.main()
