"""Offline LuaJIT lifecycle tests. No engine hooks, game process or game writes."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "research/prototypes/potion-admission"


class PotionMessageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.globals().core = self.lua.execute((PROTOTYPE / "CBRPQCore.lua").read_text())
        self.lua.globals().factory = self.lua.execute((PROTOTYPE / "CBRPQMessages.lua").read_text())
        self.lua.execute("""
            m = factory(core)
            function fails(callback, part)
                local ok, err = pcall(callback)
                assert(not ok, 'expected rejection')
                assert(tostring(err):find(part, 1, true), tostring(err))
            end
            function open(key, family, quota)
                return m.begin(key, family or 'THIEF', 'ability-0', quota or {lock=1,pick=1})
            end
        """)

    def check(self, source):
        self.lua.execute(source)

    def test_factory_has_no_autoload_or_native_dependencies(self):
        self.check("""
            assert(type(factory)=='function' and EEex_Active==nil)
            fails(function() factory({}) end, 'invalid core')
            assert(m.top('anything')==nil)
        """)

    def test_constructed_child_attaches_to_message_and_cancels_before_run(self):
        self.check("""
            local dose=open('cast')
            m.defer('cast','child',0); m.endInvocation('cast')
            m.attach('child','queued')
            fails(function() m.attach('child','again') end,'not awaiting')
            assert(m.destroy('queued') and not m.hasLive())
            local unrelated=m.enter('queued','child',false)
            assert(unrelated.dose==nil); m.leave(unrelated)
            open('next'); m.defer('next','child',0); m.attach('child','queued')
            local owned=m.enter('queued','child',false)
            assert(owned.dose~=dose)
            fails(function() m.attach('child','other') end,'not awaiting')
            m.leave(owned); m.endInvocation('next'); assert(not m.hasLive())
        """)

    def test_attachment_cannot_borrow_another_live_message_or_a_retired_effect(self):
        self.check("""
            open('cast'); m.queue('cast','busy','first',0); m.defer('cast','second',1)
            fails(function() m.attach('second','busy') end,'already live')
            assert(m.destroyEffect('second'))
            fails(function() m.attach('second','unused') end,'not awaiting')
            m.destroy('busy'); m.endInvocation('cast'); assert(not m.hasLive())
        """)

    def test_linked_branches_share_one_dose_with_separate_header_ordinals(self):
        self.check("""
            local dose=open('root','HP',{hp=1,thac=1})
            m.queue('root','parent','carrier',0); m.endInvocation('root')
            local parent=m.enter('parent','carrier',false)
            m.branch('cast-A',parent.dose,'SPL-A:0')
            m.queue('cast-A','hp-message','hp-effect',0); m.endInvocation('cast-A')
            m.branch('cast-B',parent.dose,'SPL-B:2')
            m.defer('cast-B','thac-effect',0); m.endInvocation('cast-B')
            m.leave(parent)
            local hp=m.enter('hp-message','hp-effect',false)
            assert(hp.dose==dose and hp.abilityKey=='SPL-A:0' and hp.ordinal==0)
            hp.dose.state.snapshot={}; hp.dose.state.hpBlocked=false
            m.leave(hp)
            local thac=m.enter('projectile-message','thac-effect',false)
            assert(thac.dose==dose and thac.abilityKey=='SPL-B:2' and thac.ordinal==0)
            assert(thac.dose.state.snapshot~=nil and thac.dose.state.hpBlocked==false)
            m.leave(thac); assert(not m.hasLive())
        """)

    def test_branch_cancellation_and_same_tick_second_dose_do_not_merge(self):
        self.check("""
            local a,b=open('a'),open('b')
            m.endInvocation('a'); m.endInvocation('b')
            m.branch('a-cast',a,'SPL:0'); m.branch('b-cast',b,'SPL:0')
            m.queue('a-cast','a1','ae1',0); m.queue('a-cast','a2','ae2',1)
            m.queue('b-cast','b1','be1',0)
            m.endInvocation('a-cast'); m.endInvocation('b-cast')
            assert(m.destroy('a1'))
            local fb=m.enter('b1','be1',false)
            assert(fb.dose==b and fb.dose.token~=a.token); m.leave(fb)
            local canceled=m.enter('a1','ae1',false); assert(canceled.dose==nil); m.leave(canceled)
            local fa=m.enter('a2','ae2',false); assert(fa.dose==a); m.leave(fa)
            assert(not m.hasLive())
        """)

    def test_branch_rejects_forged_cross_factory_or_previous_generation_dose(self):
        self.check("""
            local old=open('old'); m.endInvocation('old')
            fails(function() m.branch('bad',{},'SPL:0') end,'unknown or retired root dose')
            local other=factory(core)
            fails(function() other.branch('bad',old,'SPL:0') end,'unknown or retired root dose')
            m.reset()
            fails(function() m.branch('bad',old,'SPL:0') end,'unknown or retired root dose')
            local current=open('current'); m.branch('branch',current,'SPL:0')
            fails(function() m.branch('branch',current,'SPL:1') end,'already live')
            m.queue('branch','m','e',0)
            fails(function() m.queue('branch','other','other-e',0) end,'already queued')
            local frame=m.enter('m','e',false)
            assert(frame.abilityKey=='SPL:0' and frame.dose==current)
            m.leave(frame); m.endInvocation('branch'); m.endInvocation('current')
        """)

    def test_end_preserves_queued_dose_and_state_updates(self):
        self.check("""
            local dose=open('use')
            m.queue('use','msg1','eff1',0); m.queue('use','msg2','eff2',1)
            m.endInvocation('use')
            local first=m.enter('msg1','eff1',false)
            assert(m.top('eff1')==first and first.dose==dose and first.ordinal==0)
            first.dose.state={token=dose.token, marker='updated'}
            assert(m.top('eff2')==nil)
            m.leave(first)
            local second=m.enter('msg2','eff2',false)
            assert(second.dose==dose and second.dose.state.marker=='updated')
            m.leave(second)
            assert(m.top('eff2')==nil and not m.destroy('msg2'))
        """)

    def test_synchronous_dispatch_before_loop_end_and_live_key_reuse(self):
        self.check("""
            local dose=open('use')
            m.queue('use',101,201,0)
            local first=m.enter(101,201,false); m.leave(first)
            -- Allocator reuse after disposal is legal; effect ordinals are not reused.
            m.queue('use',101,201,1)
            local second=m.enter(101,201,false)
            assert(second.dose==dose and second.ordinal==1)
            m.leave(second); m.endInvocation('use')
        """)

    def test_nested_invocations_and_messages_keep_separate_doses(self):
        self.check("""
            local a=open('outer'); m.queue('outer','a','ea',0)
            local fa=m.enter('a','ea',false)
            local b=open('inner'); m.queue('inner','b','eb',0)
            m.endInvocation('inner')
            local fb=m.enter('b','eb',false)
            assert(a.token~=b.token and m.top('ea')==nil and m.top('eb')==fb)
            fails(function() m.leave(fa) end,'out of order')
            assert(m.top('eb')==fb)
            m.leave(fb); assert(m.top('ea')==fa)
            m.leave(fa); m.endInvocation('outer')
        """)

    def test_same_tick_doses_do_not_depend_on_clock_or_actor_identity(self):
        self.check("""
            local a=open('frame'); m.queue('frame','a','ea',0); m.endInvocation('frame')
            local b=open('frame'); m.queue('frame','b','eb',0); m.endInvocation('frame')
            assert(a.token~=b.token and a.state.token==a.token and b.state.token==b.token)
            local fb=m.enter('b','eb',false); m.leave(fb)
            local fa=m.enter('a','ea',false); assert(fa.dose==a); m.leave(fa)
        """)

    def test_unrelated_nested_messages_and_effects_are_sentinels(self):
        self.check("""
            open('use'); m.queue('use','a','ea',0)
            local outer=m.enter('a','ea',false)
            assert(m.top('unrelated')==nil)
            local unknown=m.enter('unrelated-message','unrelated-effect',false)
            assert(unknown.dose==nil and m.top('ea')==nil)
            m.leave(unknown); assert(m.top('ea')==outer)
            m.leave(outer); m.endInvocation('use')
        """)

    def test_no_save_true_is_unsupported_and_still_cleans_tag(self):
        self.check("""
            open('use'); m.queue('use','a','ea',0)
            local frame=m.enter('a','ea',true)
            assert(frame.dose==nil and m.top('ea')==nil)
            m.leave(frame)
            assert(not m.destroy('a'))
            m.queue('use','a','ea',1)
            local next=m.enter('a','ea',false); assert(m.top('ea')==next)
            m.leave(next); m.endInvocation('use')
        """)

    def test_unrelated_live_frame_keys_cannot_be_reused_or_retagged(self):
        self.check("""
            open('x')
            local unrelated=m.enter('unknown','ue',false)
            fails(function() m.enter('unknown','other',false) end,'message already entered')
            fails(function() m.enter('other','ue',false) end,'effect already entered')
            fails(function() m.queue('x','unknown','e',0) end,'message key already live')
            fails(function() m.queue('x','m','ue',0) end,'effect key already live')
            m.leave(unrelated)
            m.queue('x','unknown','ue',0)
            local owned=m.enter('unknown','ue',false); assert(m.top('ue')==owned)
            m.leave(owned); m.endInvocation('x')
        """)

    def test_duplicate_invocation_message_effect_and_ordinal_are_atomic(self):
        self.check("""
            local dose=open('one')
            fails(function() open('one') end,'invocation key already live')
            m.queue('one','msg','eff',0)
            fails(function() m.queue('one','msg','other',1) end,'message key already live')
            fails(function() m.queue('one','other','eff',1) end,'effect key already live')
            fails(function() m.queue('one','other','other',0) end,'ordinal already queued')
            m.queue('one','other','other',1)
            local a=m.enter('msg','eff',false); assert(a.dose==dose); m.leave(a)
            local b=m.enter('other','other',false); assert(b.ordinal==1); m.leave(b)
            m.endInvocation('one')
        """)

    def test_invalid_keys_quotas_and_ordinals_do_not_publish_state(self):
        self.check("""
            fails(function() m.begin('x','THIEF','ability',{x=0}) end,'effect quota')
            open('x')
            for _,ordinal in ipairs({-1,0.5,65535,math.huge}) do
                fails(function() m.queue('x','m','e',ordinal) end,'invalid effect ordinal')
            end
            fails(function() m.queue('x','','e',0) end,'invalid message key')
            fails(function() m.queue('x','m',0/0,0) end,'invalid effect key')
            -- Sparse/unowned positions are valid; quota totals do not cap ordinals.
            m.queue('x','m','e',65534)
            local f=m.enter('m','e',false); assert(f.ordinal==65534); m.leave(f)
            m.endInvocation('x')
            fails(function() m.queue('x','m','e',0) end,'no open invocation')
        """)

    def test_wrong_effect_and_duplicate_entry_leave_existing_tag_intact(self):
        self.check("""
            open('x'); m.queue('x','m','e',0)
            fails(function() m.enter('m','different',false) end,'identity changed')
            fails(function() m.enter('different','e',false) end,'another live message')
            local f=m.enter('m','e',false)
            fails(function() m.enter('m','e',false) end,'already entered')
            assert(m.top('e')==f); m.leave(f)
            fails(function() m.leave(f) end,'already left frame')
            m.endInvocation('x')
        """)

    def test_destroy_canceled_message_removes_keys_but_not_ordinal_history(self):
        self.check("""
            open('x'); m.queue('x','m','e',0)
            assert(m.destroy('m') and not m.destroy('m'))
            fails(function() m.queue('x','m','e',0) end,'ordinal already queued')
            m.queue('x','m','e',1)
            m.endInvocation('x')
            assert(m.destroy('m'))
            local f=m.enter('m','e',false); assert(m.top('e')==nil); m.leave(f)
        """)

    def test_destroy_running_message_invalidates_frame_until_balanced_leave(self):
        self.check("""
            open('x'); m.queue('x','m','e',0)
            local f=m.enter('m','e',false)
            assert(m.destroy('m') and m.top('e')==nil)
            fails(function() m.queue('x','m','other',1) end,'message key already live')
            m.leave(f)
            m.queue('x','m','e',1); m.endInvocation('x'); m.destroy('m')
        """)

    def test_reset_invalidates_old_tickets_without_popping_new_generation(self):
        self.check("""
            local old=open('x'); m.queue('x','m','e',0)
            local outer=m.enter('m','e',false)
            local unknown=m.enter('unknown','other',false)
            m.reset()
            assert(m.top('e')==nil and not m.destroy('m'))
            local new=open('x'); assert(new.token~=old.token)
            m.queue('x','m','e',0)
            local fresh=m.enter('m','e',false)
            assert(not m.leave(unknown) and not m.leave(outer))
            assert(m.top('e')==fresh)
            m.leave(fresh); m.endInvocation('x')
        """)

    def test_core_integration_identical_records_are_first_dose_siblings(self):
        self.check("""
            local manifest={policy='unique',sources={POTN36={family='THIEF',keys={lock=true}}},
                families={THIEF={hp=false,genius=false}}}
            local active={}
            local function deliver(msg, eff, now)
                local frame=m.enter(msg,eff,false)
                local object={m_duration=0}
                local incoming={sourceType=2,source='POTN36',key='lock',object=object,
                    timing=0,expiry=10}
                local plan=core.plan(incoming,active,manifest,now,frame.dose.state)
                local allow,state=core.commit(plan); frame.dose.state=state
                if allow then
                    object.m_duration=now+150
                    active[#active+1]={sourceType=2,source='POTN36',key='lock',object=object,
                        timing=4096,expiry=object.m_duration,done=false}
                end
                m.leave(frame)
                return allow
            end
            open('dose1','THIEF',{lock=2})
            m.queue('dose1','m1','e1',0); m.queue('dose1','m2','e2',1); m.endInvocation('dose1')
            assert(deliver('m1','e1',100) and deliver('m2','e2',100) and #active==2)
            open('dose2','THIEF',{lock=2})
            m.queue('dose2','m3','e3',0); m.queue('dose2','m4','e4',1); m.endInvocation('dose2')
            assert(not deliver('m3','e3',120) and not deliver('m4','e4',120))
            assert(#active==2 and active[1].object.m_duration==270 and active[2].object.m_duration==270)
        """)

    def test_core_integration_hp_family_decision_is_latched_per_dose(self):
        self.check("""
            local manifest={policy='unique',sources={POTN09={family='HERO',keys={hp=true,thac0=true}}},
                families={HERO={hp=true,genius=false}}}
            local active={}
            local function deliver(msg, eff, key)
                local frame=m.enter(msg,eff,false)
                local object={m_duration=250}
                local incoming={sourceType=2,source='POTN09',key=key,object=object,timing=0,expiry=10}
                local plan=core.plan(incoming,active,manifest,100,frame.dose.state)
                local allow,state=core.commit(plan); frame.dose.state=state
                if allow then active[#active+1]={sourceType=2,source='POTN09',key=key,
                    object=object,timing=4096,expiry=250,done=false} end
                m.leave(frame); return allow
            end
            open('first','HERO',{hp=1,thac0=1}); m.queue('first','m1','e1',0)
            m.queue('first','m2','e2',1); m.endInvocation('first')
            assert(deliver('m1','e1','hp') and deliver('m2','e2','thac0'))
            open('second','HERO',{hp=1,thac0=1}); m.queue('second','m3','e3',0)
            m.queue('second','m4','e4',1); m.endInvocation('second')
            assert(not deliver('m3','e3','hp') and not deliver('m4','e4','thac0'))
            assert(#active==2 and active[1].object.m_duration==250)
        """)


if __name__ == "__main__":
    unittest.main()
