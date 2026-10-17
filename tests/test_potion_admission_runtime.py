"""Real Lua core/lifecycle/bridge integration, explicit native boundary doubles.

These tests drive the documented transport callbacks; they do not execute the
native hooks, resource loading, engine admission checks or item consumption.
"""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

from tests.test_potion_admission_lua import HARNESS


ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "research/prototypes/potion-admission"

BRIDGE = r'''
    local factory = dofile(modules .. "/CBRPQRuntime.lua")
    local messageFactory = dofile(modules .. "/CBRPQMessages.lua")
    for name,source in pairs(manifest.sources) do
        local effects, quotas = {}, {}
        local keys = {}
        for key in pairs(source.keys) do keys[#keys+1] = key end
        table.sort(keys)
        for i,key in ipairs(keys) do effects[tostring(i-1)],quotas[key] = key,1 end
        source.abilities = {["0"]={effects=effects,quotas=quotas,count=#keys}}
    end
    local records, pointers, nextPointer = {}, {}, 1000
    diagnostics, target = {}, {active={},id=10}
    function incoming(source, key)
        local record = record(source,key,6,0)
        nextPointer = nextPointer + 1
        records[record.object],pointers[record.object] = record,nextPointer
        record.sourceID=10
        return record.object
    end
    function active(source,key,expiry)
        local record = record(source,key,expiry or 150)
        target.active[#target.active+1]=record
        return record.object
    end
    function ordinal(source,key)
        for i,value in pairs(manifest.sources[source].abilities["0"].effects) do
            if value==key then return tonumber(i) end
        end
        error("unknown test key")
    end
    local env = {
        ptr=function(effect) return assert(pointers[effect]) end,
        source=function(effect) return records[effect].source, records[effect].sourceType end,
        identify=function(effect) return records[effect] end,
        isSelf=function(effect,sprite) return records[effect].sourceID==sprite.id end,
        active=function(sprite)
            local result={}
            for _,r in ipairs(sprite.active) do
                -- Native re-read returns the current expiry, not a cached record.
                result[#result+1]={object=r.object,sourceType=r.sourceType,source=r.source,
                    key=r.key,timing=r.timing,expiry=r.object.m_duration,done=r.done}
            end
            return result
        end,
        now=function() return 100 end,
        retire=function() end,
        isInstantProjectile=function(pointer) return pointer==9999 end,
    }
    runtime=factory(core,messageFactory,env,manifest,function(reason)
        diagnostics[#diagnostics+1]=reason
    end)
    function assertEnabled()
        local enabled,why=runtime.status()
        assert(enabled,why)
    end
    function queue(frame,msg,effect)
        local r=records[effect]
        runtime.useQueue(frame,msg,effect,ordinal(r.source,r.key))
    end
    function enter(msg,effect,noSave)
        runtime.messageEnter(msg,pointers[effect],noSave or 0)
    end
    function pointerOf(effect) return pointers[effect] end
    function gate(effect,sprite)
        writeEnabled=true
        local reject=runtime.admit(effect,sprite or target)
        writeEnabled=false
        return reject
    end
    function nativeAccept(effect)
        local r=records[effect]
        -- Only models ownership after an accepted original. Opcode behavior is
        -- covered separately by the copied-instruction native probes.
        forceExpiry(effect,190)
        target.active[#target.active+1]={object=effect,sourceType=r.sourceType,
            source=r.source,key=r.key,timing=4096,expiry=190,done=false}
    end
    function deliver(msg,effect,accepted)
        enter(msg,effect)
        local reject=false
        if accepted~=false then
            reject=gate(effect)
            if not reject then nativeAccept(effect) end
        end
        runtime.messageLeave(msg)
        runtime.destroy(msg)
        return reject
    end
'''


class PotionAdmissionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().module_path = (MODULES / "CBRPQCore.lua").as_posix()
        self.lua.globals().modules = MODULES.as_posix()
        self.lua.execute(HARNESS + BRIDGE)

    def run_lua(self, source):
        self.lua.execute(source)

    def test_safe_repeat_refreshes_originals_across_queued_messages(self):
        self.run_lua('''
            local oldPick,oldLock=active("POTN36","PICK"),active("POTN36","LOCK")
            local pick,lock=incoming("DW#PTN36","PICK"),incoming("DW#PTN36","LOCK")
            runtime.useBegin(1,0); queue(1,101,pick); queue(1,102,lock); runtime.useEnd(1)
            assert(deliver(102,lock) and deliver(101,pick))
            assert(oldPick.m_duration==190 and oldLock.m_duration==190)
            assert(#target.active==2 and #writes==2)
            assertEnabled()
        ''')

    def test_unintegrated_adapter_capabilities_are_startup_errors_not_silent_passes(self):
        self.run_lua('''
            local factory=dofile(modules.."/CBRPQRuntime.lua")
            for _,descriptor in ipairs({{nativeSourceType=1},{opcode=98}}) do
                manifest.sources.POTN36.records={PICK=descriptor}
                local ok,why=pcall(factory,core,function() error("messages created before preflight") end,
                    {},manifest,function() error("no callbacks should run") end)
                assert(not ok and tostring(why):find("integration is unavailable",1,true),tostring(why))
            end
            assert(#writes==0 and #diagnostics==0)
        ''')

    def test_first_hp_package_siblings_then_alias_repeat_do_not_heal_or_refresh(self):
        self.run_lua('''
            local hp,thac0=incoming("DW#PTN09","HP"),incoming("DW#PTN09","THAC0")
            runtime.useBegin(1,0); queue(1,101,hp); queue(1,102,thac0); runtime.useEnd(1)
            assert(not deliver(101,hp) and not deliver(102,thac0))
            local before=snapshot(target.active)
            local hp2,thac02=incoming("POTN09","HP"),incoming("POTN09","THAC0")
            runtime.useBegin(1,0); queue(1,103,hp2); queue(1,104,thac02); runtime.useEnd(1)
            assert(deliver(104,thac02) and deliver(103,hp2))
            assert(snapshot(target.active)==before and #writes==0)
            assertEnabled()
        ''')

    def test_two_uses_in_same_tick_have_distinct_tokens(self):
        self.run_lua('''
            local first,second=incoming("POTN36","PICK"),incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,first); runtime.useEnd(1)
            runtime.useBegin(1,0); queue(1,102,second); runtime.useEnd(1)
            assert(not deliver(101,first) and deliver(102,second))
            assert(#target.active==1 and #writes==1); assertEnabled()
        ''')

    def test_immunity_or_save_rejection_never_reaches_commit(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local repeatEffect=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,repeatEffect); runtime.useEnd(1)
            deliver(101,repeatEffect,false)
            assert(old.m_duration==150 and #writes==0); assertEnabled()
        ''')

    def test_disappeared_or_done_hp_package_allows_new_original(self):
        self.run_lua('''
            active("POTN09","HP"); target.active[1].done=true
            local new=incoming("POTN09","HP")
            runtime.useBegin(1,0); queue(1,101,new); runtime.useEnd(1)
            assert(not deliver(101,new)); assertEnabled()
        ''')

    def test_different_types_overlap_and_genius_exception_is_explicit(self):
        self.run_lua('''
            active("POTN37","INT")
            local genius=incoming("POTN29","INT")
            runtime.useBegin(1,0); queue(1,101,genius); runtime.useEnd(1)
            assert(not deliver(101,genius))
            manifest.policy="except_genius"
            local another=incoming("POTN29","INT")
            runtime.useBegin(1,0); queue(1,102,another); runtime.useEnd(1)
            assert(not deliver(102,another) and #target.active==3 and #writes==0)
            assertEnabled()
        ''')

    def test_unrelated_nested_message_hides_outer_admission_frame(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local outer,unrelated=incoming("POTN36","PICK"),incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,outer); runtime.useEnd(1)
            enter(101,outer); enter(102,unrelated)
            assert(not gate(unrelated) and not gate(outer) and #writes==0)
            runtime.messageLeave(102)
            assert(gate(outer) and old.m_duration==190)
            runtime.messageLeave(101); assertEnabled()
        ''')

    def test_nested_owned_delivery_disables_before_nested_mutation(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local a,b=incoming("POTN36","PICK"),incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,a); runtime.useEnd(1)
            runtime.useBegin(1,0); queue(1,102,b); runtime.useEnd(1)
            enter(101,a); enter(102,b)
            assert(not runtime.status() and #diagnostics==1)
            assert(not gate(b) and not gate(a) and old.m_duration==150 and #writes==0)
            runtime.messageLeave(102); runtime.messageLeave(101)
            assert(#diagnostics==1)
        ''')

    def test_owned_no_save_reports_unsupported_and_never_mutates_originals(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,a); runtime.useEnd(1)
            enter(101,a,1); assert(not gate(a)); runtime.messageLeave(101)
            assert(not runtime.status() and #diagnostics==1)
            assert(diagnostics[1]:find("noSave",1,true))
            assert(old.m_duration==150 and #writes==0)
        ''')

    def test_canceled_messages_never_mutate_originals(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,102,a); runtime.useEnd(1)
            runtime.destroy(102); enter(102,a); assert(not gate(a)); runtime.messageLeave(102)
            assert(old.m_duration==150 and #writes==0); assertEnabled()
        ''')

    def test_projectile_transfer_binds_original_lifetime_to_later_message(self):
        self.run_lua('''
            local oldPick,oldLock=active("POTN36","PICK"),active("POTN36","LOCK")
            local a,b=incoming("POTN36","PICK"),incoming("POTN36","LOCK")
            runtime.useBegin(1,0)
            runtime.useProjectile(1,a,ordinal("POTN36","PICK"),9999); queue(1,102,b)
            runtime.useEnd(1)
            assert(deliver(102,b) and deliver(101,a))
            assert(oldPick.m_duration==190 and oldLock.m_duration==190)
            assert(#writes==2); assertEnabled()
        ''')

    def test_canceled_projectile_effect_cannot_tag_recycled_pointer(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.fireBegin(1,0)
            runtime.fireProjectile(1,a,ordinal("POTN36","PICK"),9999); runtime.fireEnd(1)
            runtime.effectDestroy(pointerOf(a))
            enter(101,a); assert(not gate(a)); runtime.messageLeave(101)
            assert(old.m_duration==150 and #writes==0); assertEnabled()
        ''')

    def test_mutated_projectile_class_reports_before_tagging_or_writing(self):
        self.run_lua('''
            local old=active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0)
            runtime.useProjectile(1,a,ordinal("POTN36","PICK"),8888)
            assert(not runtime.status() and #diagnostics==1)
            assert(diagnostics[1]:find("instant delivery class",1,true))
            assert(old.m_duration==150 and #writes==0)
        ''')

    def test_reset_with_surviving_owned_work_reports_instead_of_silent_replay(self):
        self.run_lua('''
            active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,a); runtime.useEnd(1)
            enter(101,a); runtime.reset(); assert(not gate(a))
            runtime.messageLeave(101)
            assert(not runtime.status() and #diagnostics==1)
            assert(diagnostics[1]:find("surviving potion delivery",1,true))
            assert(#writes==0)
        ''')

    def test_normal_queue_cancellation_then_session_reset_allows_fresh_delivery(self):
        self.run_lua('''
            active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,a); runtime.useEnd(1)
            runtime.destroy(101); runtime.effectDestroy(pointerOf(a))
            runtime.reset()
            runtime.useBegin(1,0); queue(1,102,a); runtime.useEnd(1)
            assert(deliver(102,a)); assertEnabled()
        ''')

    def test_reset_with_pending_projectile_is_diagnostic(self):
        self.run_lua('''
            local a=incoming("POTN36","PICK")
            runtime.fireBegin(1,0)
            runtime.fireProjectile(1,a,ordinal("POTN36","PICK"),9999)
            runtime.fireEnd(1); runtime.reset()
            assert(not runtime.status() and #diagnostics==1 and #writes==0)
        ''')

    def test_reset_during_open_native_invocation_is_diagnostic(self):
        self.run_lua('''
            runtime.useBegin(1,0); runtime.reset()
            assert(not runtime.status() and #diagnostics==1 and #writes==0)
        ''')

    def test_wrong_target_and_manifest_drift_disable_without_a_write(self):
        self.run_lua('''
            active("POTN36","PICK")
            local a=incoming("POTN36","PICK")
            runtime.useBegin(1,0); queue(1,101,a); runtime.useEnd(1); enter(101,a)
            assert(not gate(a,{id=11,active=target.active}))
            assert(not runtime.status() and #diagnostics==1 and #writes==0)
        ''')

    def test_immediate_dispatch_before_loop_end_and_frame_namespace_isolation(self):
        self.run_lua('''
            active("POTN36","PICK")
            local a,b=incoming("POTN36","PICK"),incoming("POTN36","LOCK")
            runtime.useBegin(1,0); runtime.fireBegin(1,0)
            queue(1,101,a); assert(deliver(101,a))
            runtime.fireQueue(1,102,b,ordinal("POTN36","LOCK"))
            assert(not deliver(102,b))
            runtime.fireEnd(1); runtime.useEnd(1); assertEnabled()
        ''')

    def test_no_engine_mutation_api_is_used(self):
        self.run_lua('assert(nativeCalls==0)')


if __name__ == "__main__":
    unittest.main()
