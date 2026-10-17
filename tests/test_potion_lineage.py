"""Original mode1 lineage with real Messages/Core and native service doubles.

No game, DLL, hook installation or save execution. Native construction fields,
class/self checks and lifetime retirement are explicit reader doubles; this
checks provenance composition rather than claiming those native services run.
"""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


class PotionLineageTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        for filename, name in (("CBRPQCore.lua", "core"), ("CBRPQMessages.lua", "messagesFactory"),
                               ("CBRPQLineage.lua", "lineageFactory")):
            self.lua.globals()[name] = self.lua.execute((ROOT / filename).read_text())
        self.lua.execute('''
            function fails(fn,part)
                local ok,err=pcall(fn)
                assert(not ok,'expected rejection')
                assert(tostring(err):find(part,1,true),tostring(err))
            end
            actor={pointer=0x90000,identity={}}
            rootFields={opcode=146,mode=1,resource='CHILD'}
            nestedFields={opcode=146,mode=1,resource='LEAF'}
            rootAbility={count=1,effects={['0']=false},quotas={bonus=2},
                carriers={['0']={call='CHILD',fields=rootFields}}}
            childHeader={minimumLevel=1,count=2,effects={['0']='bonus',['1']=false},carriers={},quotas={bonus=1}}
            leafHeader={minimumLevel=1,count=1,effects={['0']='bonus'},carriers={},quotas={bonus=1}}
            manifest={sources={POTN36={family='POTN36',abilities={['0']=rootAbility},
                records={bonus={}},keys={bonus=true},calls={
                    CHILD={resource='CHILD',abilities={['0']=childHeader},quotas={bonus=1}},
                    LEAF={resource='LEAF',abilities={['0']=leafHeader},quotas={bonus=1}},
                }}}}
            messages=messagesFactory(core)
            bindings={}; tokens={}; carriers={}; bound={}; ptrCalls=0; projectileCalls=0
            directTickets={}; directEvents={}
            env={}
            function env.ptr(effect)
                ptrCalls=ptrCalls+1
                assert(type(effect)=='table' and type(effect.pointer)=='number','invalid borrowed userdata')
                return effect.pointer
            end
            function env.carrier(effect,source,expected,incoming,nativeSource)
                assert(effect.nativeSource==(nativeSource or source),'carrier source changed')
                assert(effect.resource==expected.resource and expected.opcode==146 and expected.mode==1,
                    'carrier fields changed')
                carriers[#carriers+1]={effect=effect,source=source,incoming=incoming,nativeSource=nativeSource}
            end
            function env.bindLinked(effect,source,key,nativeSource)
                assert(effect.nativeSource==nativeSource,'child source changed')
                assert(bindings[effect.pointer]==nil,'child already has a lifetime binding')
                tokens[effect.pointer]=tokens[effect.pointer] or {}
                bindings[effect.pointer]={identity=tokens[effect.pointer],source=source,key=key,nativeSource=nativeSource}
                bound[#bound+1]=bindings[effect.pointer]
            end
            function env.isSelf(effect,sprite) return effect.drinker==sprite.pointer end
            function env.isInstantProjectile(pointer)
                projectileCalls=projectileCalls+1
                return pointer==0x123400
            end
            function env.retire(pointer) bindings[pointer]=nil; tokens[pointer]=nil end
            function enterDirect(key,effect,noSave)
                assert(type(noSave)=='number' or type(noSave)=='boolean','invalid noSave')
                local skip=noSave==true or (type(noSave)=='number' and noSave~=0)
                local ticket=messages.enter(key,effect,skip)
                directTickets[key]=ticket
                assert(not ticket.unsupportedNoSave,'owned direct noSave')
                directEvents[#directEvents+1]={kind='enter',ticket=ticket,effect=effect}
            end
            function leaveDirect(key)
                assert(directTickets[key],'missing direct ticket')
                messages.leave(directTickets[key]); directTickets[key]=nil
                directEvents[#directEvents+1]={kind='leave'}
            end
            lineage=lineageFactory(messages,env,manifest,enterDirect,leaveDirect,function(sprite) return sprite.identity end)
            function effect(pointer,source,resource)
                return {pointer=pointer,nativeSource=source or 'CHILD',resource=resource,drinker=actor.pointer}
            end
            function root(message,pointer)
                local invocation={}
                local ref={source='POTN36',ability=rootAbility}
                local dose=messages.begin(invocation,'POTN36',ref,rootAbility.quotas)
                dose.objects={}
                local parent=effect(pointer or 0x1000,'POTN36','CHILD')
                local addMessage={}
                messages.queue(invocation,addMessage,parent.pointer,0)
                messages.endInvocation(invocation)
                local ticket=messages.enter(addMessage,parent.pointer,false)
                lineage.parentQueued(parent,message,actor)
                messages.leave(ticket)
                return dose,parent
            end
            ENTRY=0x100000; FRAME=ENTRY-0x70
            function start(message,pointer)
                local dose,parent=root(message or 0x2000,pointer)
                lineage.castEnter(message or 0x2000,ENTRY)
                return dose,parent
            end
            function destroyEffect(pointer)
                lineage.effectDestroy(pointer); messages.destroyEffect(pointer); env.retire(pointer)
            end
            function resetAll()
                lineage.reset(); messages.reset()
                bindings={}; tokens={}; directTickets={}
            end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_factory_is_inert_and_unknown_parent_does_not_infer_from_source(self):
        self.check('''
            assert(not lineage.hasLive() and not messages.hasLive() and #bound==0)
            lineage.parentQueued(effect(0x1000,'POTN36','CHILD'),0x2000,actor)
            lineage.parentQueued('invalid userdata',0,'invalid sprite')
            assert(not lineage.hasLive() and #carriers==0)
            local dose=start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childQueued(FRAME,0x4000,child,0)
            lineage.castLeave(0x2000)
            assert(not lineage.hasLive() and messages.hasLive())
            local ticket=messages.enter(0x4000,child.pointer,false)
            assert(ticket.dose==dose and ticket.ordinal==0)
            assert(ticket.abilityKey.source=='POTN36' and ticket.abilityKey.nativeSource=='CHILD')
            assert(ticket.abilityKey.ability==childHeader)
            messages.leave(ticket); assert(not messages.hasLive())
        ''')

    def test_dependencies_and_native_pointer_domains_are_validated_before_context(self):
        self.check('''
            fails(function() lineageFactory({},env,manifest,enterDirect,leaveDirect) end,'message lifecycle')
            fails(function() lineageFactory(messages,nil,manifest,enterDirect,leaveDirect) end,'dependencies')
            for _,bad in ipairs({0,-1,0.5,math.huge,9007199254740992,'message',{}}) do
                fails(function() lineage.castEnter(bad,ENTRY) end,'cast message pointer')
                assert(not lineage.hasLive())
            end
            fails(function() lineage.castEnter(0/0,ENTRY) end,'cast message pointer')
            for _,bad in ipairs({0,0x70,-1,0.5,math.huge,9007199254740992,'frame',{}}) do
                fails(function() lineage.castEnter(0x2000,bad) end,'cast entry frame')
                assert(not lineage.hasLive())
            end
            fails(function() lineage.castEnter(0x2000,0/0) end,'cast entry frame')
        ''')

    def test_distinct_live_messages_cannot_claim_the_same_native_entry_frame(self):
        self.check('''
            local dose=start()
            fails(function() lineage.castEnter(0x2100,ENTRY) end,'entry frame is already running')
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childQueued(FRAME,0x4000,child,0)
            lineage.castLeave(0x2000)
            -- The same numeric stack address is valid after balanced return.
            lineage.castEnter(0x2100,ENTRY); lineage.castLeave(0x2100)
            local ticket=messages.enter(0x4000,child.pointer,false)
            assert(ticket.dose==dose); messages.leave(ticket)
        ''')

    def test_unowned_ordinals_remain_native_but_are_counted_before_later_owned_child(self):
        self.check('''
            childHeader.effects={['0']=false,['1']='bonus'}
            start()
            lineage.childCreated(FRAME,effect(0x3000),0,0,actor,actor)
            lineage.childQueued(FRAME,0x4000,effect(0x3000),0)
            lineage.childProjectile(FRAME,effect(0x3000),0,0xBAD)
            assert(#bound==0 and projectileCalls==0)
            local child=effect(0x3100)
            lineage.childCreated(FRAME,child,1,0,actor,actor)
            lineage.childQueued(FRAME,0x4100,child,1)
            lineage.castLeave(0x2000)
            local ticket=messages.enter(0x4100,child.pointer,false)
            assert(ticket.dose and ticket.ordinal==1)
            messages.leave(ticket); assert(not messages.hasLive())
        ''')

    def test_actual_selected_header_keeps_reordered_duplicate_ordinals_and_one_root_quota(self):
        self.check('''
            local alternate={minimumLevel=9,count=3,
                effects={['0']=false,['1']='bonus',['2']='bonus'},carriers={},quotas={bonus=2}}
            manifest.sources.POTN36.calls.CHILD.abilities['1']=alternate
            local dose=start()
            for ordinal=0,2 do
                local child=effect(0x3000+ordinal*0x100)
                lineage.childCreated(FRAME,child,ordinal,1,actor,actor)
                lineage.childQueued(FRAME,0x4000+ordinal*0x100,child,ordinal)
            end
            lineage.castLeave(0x2000)
            for ordinal=1,2 do
                local ticket=messages.enter(0x4000+ordinal*0x100,0x3000+ordinal*0x100,false)
                assert(ticket.dose==dose and ticket.abilityKey.ability==alternate)
                assert(ticket.ordinal==ordinal and ticket.dose.state.quotas.bonus==2)
                messages.leave(ticket)
            end
            assert(#bound==2 and not messages.hasLive())
        ''')

    def test_cast_with_no_constructed_child_balances_without_inventing_a_branch(self):
        self.check('''
            start()
            -- A native no-header/no-child path still returns normally.
            lineage.castLeave(0x2000); lineage.castDestroy(0x2000)
            assert(#bound==0 and not messages.hasLive() and not lineage.hasLive())
        ''')

    def test_failed_message_allocation_keeps_pending_child_until_native_destruction(self):
        self.check('''
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childQueued(FRAME,0,child,0)
            lineage.castLeave(0x2000)
            assert(messages.hasLive()) -- zero allocation is not ownership retirement
            destroyEffect(child.pointer)
            assert(not messages.hasLive() and not lineage.hasLive())
        ''')

    def test_canceled_cast_message_does_not_create_owned_children_when_pointer_reappears(self):
        self.check('''
            root(0x2000)
            assert(lineage.hasLive())
            lineage.castDestroy(0x2000)
            assert(not lineage.hasLive())
            lineage.castEnter(0x2000,ENTRY)
            local before=ptrCalls
            lineage.childCreated(FRAME,'invalid userdata',0,0,'not sprite','not sprite')
            assert(ptrCalls==before and #bound==0)
            lineage.castLeave(0x2000)
            assert(not lineage.hasLive() and not messages.hasLive())
        ''')

    def test_queued_child_cancellation_retires_original_pending_dose(self):
        self.check('''
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childQueued(FRAME,0x4000,child,0)
            lineage.castLeave(0x2000)
            assert(messages.destroy(0x4000))
            destroyEffect(child.pointer)
            local canceled=messages.enter(0x4000,child.pointer,false)
            assert(canceled.dose==nil); messages.leave(canceled)
            assert(not messages.hasLive() and bindings[child.pointer]==nil)
        ''')

    def test_two_same_tick_doses_and_reused_cast_pointer_have_distinct_tokens(self):
        self.check('''
            local a=root(0x2000,0x1000)
            local b=root(0x2100,0x1100)
            assert(a.token~=b.token)
            for _,case in ipairs({{0x2100,0x3100,0x4100,b},{0x2000,0x3000,0x4000,a}}) do
                lineage.castEnter(case[1],ENTRY)
                local child=effect(case[2])
                lineage.childCreated(FRAME,child,0,0,actor,actor)
                lineage.childQueued(FRAME,case[3],child,0)
                lineage.castLeave(case[1]); lineage.castDestroy(case[1])
                local ticket=messages.enter(case[3],case[2],false)
                assert(ticket.dose==case[4]); messages.leave(ticket)
            end
            local fresh=root(0x2000,0x1000)
            assert(fresh.token~=a.token)
            lineage.castDestroy(0x2000)
            assert(not lineage.hasLive() and not messages.hasLive())
        ''')

    def test_nested_unowned_cast_and_direct_sentinel_hide_outer_admission_frame(self):
        self.check('''
            local dose=start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childDirectEnter(FRAME,child.pointer,0)
            assert(messages.top(child.pointer).dose==dose)
            lineage.castEnter(0x9999,ENTRY-0x1000)
            local before=ptrCalls
            lineage.childCreated(FRAME-0x1000,'not userdata',0,0,'not sprite','not sprite')
            assert(ptrCalls==before)
            lineage.childDirectEnter(FRAME-0x1000,0x9990,false)
            assert(messages.top(child.pointer)==nil and messages.top(0x9990)==nil)
            lineage.parentQueued(child,0xDEAD,actor)
            lineage.childDirectLeave(FRAME-0x1000)
            lineage.castLeave(0x9999)
            assert(messages.top(child.pointer).dose==dose)
            lineage.childDirectLeave(FRAME); lineage.castLeave(0x2000)
            assert(#bound==1 and not lineage.hasLive() and not messages.hasLive())
        ''')

    def test_direct_carrier_can_reentrantly_run_child_cast_on_same_root_dose(self):
        self.check('''
            childHeader.effects['0']=false
            childHeader.carriers['0']={call='LEAF',fields=nestedFields}
            local dose=start()
            local parent=effect(0x3000,'CHILD','LEAF')
            lineage.childCreated(FRAME,parent,0,0,actor,actor)
            assert(#bound==0 and carriers[#carriers].incoming==true)
            lineage.childDirectEnter(FRAME,parent.pointer,0)
            lineage.parentQueued(parent,0x5000,actor)
            assert(carriers[#carriers].incoming==false and carriers[#carriers].nativeSource=='CHILD')
            lineage.castEnter(0x5000,ENTRY-0x1000)
            local child=effect(0x6000,'LEAF')
            lineage.childCreated(FRAME-0x1000,child,0,0,actor,actor)
            lineage.childDirectEnter(FRAME-0x1000,child.pointer,0)
            local ticket=messages.top(child.pointer)
            assert(ticket.dose==dose and ticket.abilityKey.nativeSource=='LEAF')
            lineage.childDirectLeave(FRAME-0x1000)
            lineage.castLeave(0x5000)
            assert(messages.top(parent.pointer).dose==dose)
            lineage.childDirectLeave(FRAME); lineage.castLeave(0x2000)
            assert(not lineage.hasLive() and not messages.hasLive() and #bound==1)
        ''')

    def test_queued_nested_carrier_keeps_dose_after_outer_cast_has_returned(self):
        self.check('''
            childHeader.effects['0']=false
            childHeader.carriers['0']={call='LEAF',fields=nestedFields}
            local dose=start()
            local parent=effect(0x3000,'CHILD','LEAF')
            lineage.childCreated(FRAME,parent,0,0,actor,actor)
            lineage.childQueued(FRAME,0x4000,parent,0)
            lineage.castLeave(0x2000)
            local ticket=messages.enter(0x4000,parent.pointer,false)
            lineage.parentQueued(parent,0x5000,actor); messages.leave(ticket)
            lineage.castEnter(0x5000,ENTRY)
            local child=effect(0x6000,'LEAF')
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childQueued(FRAME,0x7000,child,0); lineage.castLeave(0x5000)
            ticket=messages.enter(0x7000,child.pointer,false)
            assert(ticket.dose==dose); messages.leave(ticket)
            assert(not lineage.hasLive() and not messages.hasLive())
        ''')

    def test_effect_retirement_allows_same_pointer_with_fresh_lifetime_at_next_ordinal(self):
        self.check('''
            childHeader.effects['1']='bonus'
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            local old=bindings[child.pointer].identity
            lineage.childQueued(FRAME,0x4000,child,0)
            messages.destroy(0x4000); destroyEffect(child.pointer)
            lineage.childCreated(FRAME,child,1,0,actor,actor)
            assert(bindings[child.pointer].identity~=old)
            lineage.childQueued(FRAME,0x4100,child,1)
            lineage.castLeave(0x2000)
            local ticket=messages.enter(0x4100,child.pointer,false)
            assert(ticket.dose and ticket.ordinal==1); messages.leave(ticket)
            assert(not messages.hasLive())
        ''')

    def test_projectile_class_is_checked_only_for_owned_original_pending_child(self):
        self.check('''
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            fails(function() lineage.childProjectile(FRAME,child,0,0xBAD) end,'instant class')
            lineage.childProjectile(FRAME,child,0,0x123400)
            assert(projectileCalls==2)
            lineage.castLeave(0x2000)
            -- Base instant delivery keeps this pointer; Messages binds its
            -- eventual message identity at Run without resref inference.
            local ticket=messages.enter(0x4000,child.pointer,false)
            assert(ticket.dose and ticket.ordinal==0); messages.leave(ticket)
        ''')

    def test_native_failed_child_admission_does_not_leave_another_pending_owner(self):
        self.check('''
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childDirectEnter(FRAME,child.pointer,0)
            -- CheckAdd/save failure does not invoke the admission callback.
            -- Its original native destructor still retires this exact child.
            destroyEffect(child.pointer)
            assert(messages.top(child.pointer)==nil)
            lineage.childDirectLeave(FRAME); lineage.castLeave(0x2000)
            assert(not messages.hasLive() and bindings[child.pointer]==nil)
        ''')

    def test_child_header_ordinal_self_and_frame_checks_precede_binding(self):
        cases = [
            ("FRAME+8,child,0,0,actor,actor", "original tracked mode1"),
            ("FRAME,child,0,1,actor,actor", "selected ability"),
            ("FRAME,child,2,0,actor,actor", "child ordinal"),
            ("FRAME,child,1,0,actor,actor", "order changed"),
            ("FRAME,child,-1,0,actor,actor", "invalid child ordinal"),
            ("FRAME,child,0.5,0,actor,actor", "invalid child ordinal"),
            ("FRAME,child,0,0,{pointer=7},actor", "not the drinker"),
            ("FRAME,child,0,0,actor,{pointer=7}", "not the drinker"),
        ]
        for arguments, reason in cases:
            with self.subTest(arguments=arguments):
                self.setUp()
                self.check("start(); child=effect(0x3000); fails(function() lineage.childCreated(" +
                           arguments + ") end,'" + reason + "'); assert(#bound==0)")

    def test_live_pointer_duplicate_and_changed_native_source_fail_before_second_binding(self):
        self.check('''
            childHeader.effects['1']='bonus'
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            fails(function() lineage.childCreated(FRAME,child,1,0,actor,actor) end,'already pending')
            assert(#bound==1)
            resetAll(); start()
            fails(function() lineage.childCreated(FRAME,effect(0x3100,'OTHER'),0,0,actor,actor) end,'source changed')
            assert(#bound==1)
        ''')

    def test_unbalanced_native_returns_and_running_cast_destruction_are_diagnosed(self):
        self.check('''
            start()
            lineage.castEnter(0x2100,ENTRY-0x1000)
            fails(function() lineage.castLeave(0x2000) end,'unbalanced')
            fails(function() lineage.castDestroy(0x2000) end,'while still executing')
            lineage.castLeave(0x2100)
            fails(function() lineage.childDirectLeave(FRAME) end,'has no entry')
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            lineage.childDirectEnter(FRAME,child.pointer,0)
            fails(function() lineage.castLeave(0x2000) end,'unbalanced')
            lineage.childDirectLeave(FRAME); lineage.castLeave(0x2000)
        ''')

    def test_owned_nosave_requires_bridge_failure_and_whole_composition_reset(self):
        self.check('''
            start()
            local child=effect(0x3000)
            lineage.childCreated(FRAME,child,0,0,actor,actor)
            fails(function() lineage.childDirectEnter(FRAME,child.pointer,1) end,'owned direct noSave')
            assert(messages.top(child.pointer)==nil)
            resetAll()
            lineage.childDirectLeave(FRAME); lineage.castLeave(0x2000)
            assert(not messages.hasLive() and not lineage.hasLive())
        ''')

    def test_reset_discards_old_cast_tags_and_old_returns_do_not_pop_new_distinct_frame(self):
        self.check('''
            local old=start()
            resetAll()
            local fresh=root(0x2100,0x1100)
            lineage.castEnter(0x2100,ENTRY-0x1000)
            lineage.castLeave(0x2000); lineage.castDestroy(0x2000)
            assert(lineage.hasLive() and fresh.token~=old.token)
            local child=effect(0x3000)
            lineage.childCreated(FRAME-0x1000,child,0,0,actor,actor)
            lineage.childQueued(FRAME-0x1000,0x4000,child,0); lineage.castLeave(0x2100)
            local ticket=messages.enter(0x4000,child.pointer,false)
            assert(ticket.dose==fresh); messages.leave(ticket)
            assert(not lineage.hasLive() and not messages.hasLive())
        ''')


if __name__ == "__main__":
    unittest.main()
