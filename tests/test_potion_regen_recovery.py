"""Pure Lua lifecycle/transaction tests. Native allocation is explicitly mocked."""
from pathlib import Path
import unittest

from tests import test_potion_regen_cache as cache_tests

PROTOTYPE = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


class RegenerationRecoveryTests(unittest.TestCase):
    def setUp(self):
        b = cache_tests.RegenerationCacheTests()
        b.setUp()
        self.lua, self.g, self.core, self.record = b.lua, b.g, b.core, b.record
        self.lua.execute("""
            cacheIds, nodes, metas, saved, operations = {}, {}, {}, {}, {}
            nextCache,nextNode,nextSnapshot=0x5000,0xA000,1
            allocations,insertions,disposals=0,0,0
            failAllocation,failInsertion,failAfterInsertion=false,false,false
            failAllocationAt=nil
            allocationCallback=nil
            function meta(sprite)
                if not metas[sprite] then
                    metas[sprite]={pointer=sprite+0x1A08,identity={},counter=0}
                end
                return metas[sprite]
            end
            function cacheIdentity(p)
                if not cacheIds[p] then cacheIds[p]={} end
                if not nodes[p] then nodes[p]=nextNode; nextNode=nextNode+0x20 end
                return cacheIds[p]
            end
            function copy(t) local out={}; for k,v in pairs(t) do out[k]=v end; return out end
            api.recovery={
                list=function(sprite)
                    local m=meta(sprite); local entries={}
                    for _,p in ipairs(lists[sprite] or {}) do
                        entries[#entries+1]={pointer=p,identity=cacheIdentity(p),node=nodes[p]}
                    end
                    return {pointer=m.pointer,identity=m.identity,counter=m.counter,entries=entries}
                end,
                capture=function(p)
                    local s=string.rep(string.char(nextSnapshot),0x30)
                    nextSnapshot=nextSnapshot+1; saved[s]=copy(memory[p]); return s
                end,
                allocate=function(state,changes)
                    if failAllocation or allocations+1==failAllocationAt then error('native allocation unavailable') end
                    if allocationCallback then allocationCallback() end
                    local p=nextCache; nextCache=nextCache+0x100
                    memory[p]=copy(saved[state])
                    for k,v in pairs(changes) do memory[p][k]=v end
                    allocations=allocations+1; operations[#operations+1]='allocate'
                    return {pointer=p,identity=cacheIdentity(p)}
                end,
                insert=function(listPointer,listIdentity,allocation,node)
                    if failInsertion then error('native insert failed') end
                    local sprite=nil
                    for s,m in pairs(metas) do
                        if m.pointer==listPointer and m.identity==listIdentity then sprite=s end
                    end
                    assert(sprite,'wrong list lifetime')
                    local index=#lists[sprite]+1
                    if node~=0 then
                        index=nil
                        for i,p in ipairs(lists[sprite]) do if nodes[p]==node then index=i end end
                        assert(index,'retired successor node')
                    end
                    table.insert(lists[sprite],index,allocation.pointer)
                    insertions=insertions+1; operations[#operations+1]='insert'
                    if failAfterInsertion then error('native insert failed after mutation') end
                end,
                dispose=function(allocation)
                    if allocation and allocation.pointer then
                        memory[allocation.pointer]=nil; cacheIds[allocation.pointer]=nil
                        disposals=disposals+1; operations[#operations+1]='dispose'
                    end
                end,
            }
            memory[0x3000].mode=3
            now=1449
            function removeCache(p)
                for _,list in pairs(lists) do
                    for i=#list,1,-1 do if list[i]==p then table.remove(list,i) end end
                end
                module.onCacheDestroy(p)
                memory[p],cacheIds[p],nodes[p]=nil,nil,nil
            end
            function death(p)
                memory[p].remaining=0
                module.onNaturalDeath(p)
                memory[p].done=true
                module.onBeforeRemove(p)
                removeCache(p)
            end
            function finish(frame)
                meta(frame.sprite).counter=meta(frame.sprite).counter+1
                return module.onUpdateExit(frame)
            end
        """)
        factory = self.lua.execute((PROTOTYPE / "CBRPQRegenCache.lua").read_text())
        recovery = self.lua.execute((PROTOTYPE / "CBRPQRegenRecovery.lua").read_text())
        self.module = factory(self.g.api, recovery)
        self.g.module = self.module
        self.module.onAppend(0x2000, 0x3000, 0x9000)

    def frame(self, sprite=0x9000):
        return self.module.onUpdateEnter(sprite, sprite + 0x1A08)

    def updates(self, expiry=1900, record=None):
        return self.lua.table_from([self.g.update(record or self.record, expiry)])

    def commit(self, expiry=1900, record=None):
        updates = self.updates(expiry, record)
        txn = self.module.prepare(updates)
        self.core.commit(self.lua.table_from({"refresh":updates,"allow":False,"state":self.lua.table()}))
        return txn.commit()

    def commit_many(self, pairs):
        updates=self.lua.table_from([self.g.update(record,expiry) for record,expiry in pairs])
        txn=self.module.prepare(updates)
        self.g.expireCore(updates)
        return txn.commit()

    def missing(self):
        frame = self.frame()
        self.g.death(0x3000)
        return frame

    def add(self, original=0x2100, cache=0x3100, sprite=0x9000, expiry=2000):
        record = self.g.effect(original, 98, expiry, sprite)
        self.g.cache(cache, 500)
        self.g.memory[cache].mode=2
        self.g.memory[cache].interval=1
        self.g.memory[cache].phase=0
        if self.g.lists[sprite] is None: self.g.lists[sprite]=self.lua.table()
        self.lua.eval("table.insert")(self.g.lists[sprite],cache)
        self.module.onAppend(original,cache,sprite)
        return record

    def test_immediate_recovery_preserves_position_and_state(self):
        self.add()
        frame=self.missing()
        self.g.finish(frame)
        self.commit()
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000,0x3100])
        self.assertEqual(self.g.memory[0x5000].remaining,450)
        self.assertEqual(self.g.memory[0x5000].phase,2)
        self.assertEqual(self.g.memory[0x5000].unrelated,"preserve")
        self.assertEqual(self.g.memory[0x3100].remaining,500)
        self.assertEqual(self.g.allocations,1)

    def test_deferred_same_dose_and_later_deadlines_allocate_only_at_exit(self):
        self.add()
        frame=self.missing()
        self.commit(1900)
        self.commit(1900)
        self.commit(2000)
        self.assertEqual(self.g.allocations,0)
        self.g.finish(frame)
        self.assertEqual(self.g.allocations,1)
        self.assertEqual(self.g.memory[0x5000].remaining,550)
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000,0x3100])
        self.commit(2100)  # The reconstructed cache is now ordinary exact lineage.
        self.assertEqual(self.g.memory[0x5000].remaining,650)
        self.assertEqual(self.g.allocations,1)

    def test_removed_successor_uses_next_surviving_lifetime(self):
        self.add(); self.add(0x2200,0x3200)
        frame=self.missing()
        self.commit()
        self.g.removeCache(0x3100)
        self.g.finish(frame)
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000,0x3200])

    def test_all_successors_removed_uses_tail(self):
        self.add()
        frame=self.missing()
        self.commit()
        self.g.removeCache(0x3100)
        self.g.finish(frame)
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000])

    def test_original_cancellation_clears_pending_without_native_reads(self):
        frame=self.missing(); self.commit()
        reads=self.g.reads
        self.module.onOriginalDestroy(0x2000)
        self.assertEqual(self.g.reads,reads)
        self.g.finish(frame)
        self.assertEqual(self.g.allocations,0)

    def test_list_cancel_and_reset_never_reconstruct(self):
        frame=self.missing(); self.commit()
        self.module.onCancelList(0x9000)
        self.g.finish(frame)
        self.assertEqual(self.g.allocations,0)
        self.module.reset()
        self.assertFalse(self.module.onUpdateExit(frame))

    def test_canceled_cache_never_gets_natural_snapshot(self):
        frame=self.frame()
        self.g.memory[0x3000].canceled=True
        self.module.onBeforeRemove(0x3000)
        self.g.removeCache(0x3000)
        self.g.finish(frame)
        with self.assertRaisesRegex(Exception,"no recoverable natural-death"):
            self.module.prepare(self.updates())
        self.assertEqual(self.record.m_duration,1450)

    def test_outside_window_and_shortening_reject_before_core(self):
        frame=self.missing(); self.g.finish(frame)
        with self.assertRaisesRegex(Exception,"nonshortening"):
            self.module.prepare(self.updates(1450))
        self.g.now=1450
        with self.assertRaises(Exception): self.module.prepare(self.updates())
        self.assertEqual(self.record.m_duration,1450)

    def test_new_or_reused_cache_during_pass_diagnoses_at_exit(self):
        self.add()
        frame=self.missing(); self.commit()
        self.g.removeCache(0x3100)
        self.g.cache(0x3100,500)
        self.lua.eval("table.insert")(self.g.lists[0x9000],0x3100)
        # No verified native append callback: this is an unexplained mutation.
        with self.assertRaisesRegex(Exception,"new/reordered/reused"):
            self.g.finish(frame)
        self.assertEqual(self.g.allocations,0)
        self.assertEqual(self.record.m_duration,1900)  # Explicit no rollback claim.

    def test_same_list_nested_pass_rejected_different_list_nests(self):
        frame=self.frame()
        with self.assertRaisesRegex(Exception,"nested update of same list"):
            self.frame()
        self.g.lists[0xA000]=self.lua.table()
        inner=self.frame(0xA000)
        self.g.finish(inner); self.g.finish(frame)

    def test_counter_exit_and_lifetime_are_validated(self):
        frame=self.missing(); self.commit()
        with self.assertRaisesRegex(Exception,"after-counter-increment"):
            self.module.onUpdateExit(frame)
        self.g.meta(0x9000).identity=self.lua.table()
        with self.assertRaisesRegex(Exception,"after-counter-increment"):
            self.g.finish(frame)
        self.assertEqual(self.g.allocations,0)

    def test_allocation_failure_is_not_rolled_back_or_retried(self):
        frame=self.missing(); self.g.finish(frame)
        self.g.failAllocation=True
        updates=self.updates()
        txn=self.module.prepare(updates)
        self.g.expireCore(updates)
        with self.assertRaisesRegex(Exception,"allocation unavailable"): txn.commit()
        self.assertEqual(self.record.m_duration,1900)
        self.assertEqual(self.g.insertions,0)
        with self.assertRaisesRegex(Exception,"already used"): txn.commit()

    def test_insertion_failure_after_mutation_is_not_freed(self):
        frame=self.missing(); self.g.finish(frame)
        self.g.failAfterInsertion=True
        with self.assertRaisesRegex(Exception,"after mutation"): self.commit()
        self.assertEqual(self.g.insertions,1)
        self.assertEqual(self.g.disposals,0)
        self.assertEqual(self.record.m_duration,1900)

    def test_allocator_reentry_is_diagnostic(self):
        frame=self.missing(); self.g.finish(frame)
        self.lua.execute("allocationCallback=function() module.reset() end")
        with self.assertRaisesRegex(Exception,"reentered recovery lifecycle"):
            self.commit()
        self.assertEqual(self.g.insertions,0)

    def test_missing_adapter_is_explicit_factory_capability_failure(self):
        self.g.api.recovery.allocate=None
        factory=self.lua.execute((PROTOTYPE/"CBRPQRegenCache.lua").read_text())
        recovery=self.lua.execute((PROTOTYPE/"CBRPQRegenRecovery.lua").read_text())
        with self.assertRaisesRegex(Exception,"capability unavailable: allocate"):
            factory(self.g.api,recovery)

    def batch_setup(self):
        self.g.memory[0x3000].label='A'
        self.add(); self.g.memory[0x3100].label='X'
        second=self.add(0x2200,0x3200,expiry=1450)
        self.g.memory[0x3200].label='B'
        self.g.memory[0x3200].amount=5
        self.add(0x2300,0x3300); self.g.memory[0x3300].label='T'
        return second

    def labels(self):
        return [self.g.memory[p].label for p in self.g.lists[0x9000].values()]

    def test_two_missing_same_pass_stage_all_then_preserve_middle_order(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200)
        self.commit_many([(second,2000),(self.record,1900)])
        self.assertEqual(self.g.allocations,0)
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','B','T'])
        self.assertEqual(list(self.g.operations.values()),['allocate','allocate','insert','insert'])
        values={self.g.memory[p].label:self.g.memory[p] for p in self.g.lists[0x9000].values()}
        self.assertEqual(values['A'].remaining,450)
        self.assertEqual(values['B'].remaining,550)
        self.assertEqual(values['B'].amount,5)

    def test_two_missing_immediate_batch_in_reverse_request_order(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200); self.g.finish(frame)
        self.commit_many([(second,2000),(self.record,1900)])
        self.assertEqual(self.labels(),['A','X','B','T'])
        self.assertEqual(self.g.allocations,2)

    def test_two_missing_separate_commits_and_deadline_changes_share_pending_batch(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200)
        self.commit(1900); self.commit(2000,second); self.commit(2100)
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','B','T'])
        values={self.g.memory[p].label:self.g.memory[p] for p in self.g.lists[0x9000].values()}
        self.assertEqual(values['A'].remaining,650)
        self.assertEqual(values['B'].remaining,550)
        self.assertEqual(self.g.allocations,2)

    def test_different_passes_retain_first_removal_position_and_elapsed_counter(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.finish(frame)
        frame=self.frame(); self.g.death(0x3200)
        self.commit_many([(second,1900),(self.record,1900)])
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','B','T'])
        values={self.g.memory[p].label:self.g.memory[p] for p in self.g.lists[0x9000].values()}
        self.assertEqual(values['A'].remaining,449)
        self.assertEqual(values['B'].remaining,450)

    def test_middle_successor_removed_between_two_natural_deaths(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.removeCache(0x3100); self.g.death(0x3200)
        self.commit_many([(self.record,1900),(second,1900)])
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','B','T'])

    def test_cancel_one_pending_original_preserves_other_recovery(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200)
        self.commit_many([(self.record,1900),(second,1900)])
        self.module.onOriginalDestroy(0x2200)
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','T'])
        self.assertEqual(self.g.allocations,1)

    def test_second_allocation_failure_disposes_first_detached_cache_without_insertion(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200); self.g.finish(frame)
        self.g.failAllocationAt=2
        with self.assertRaisesRegex(Exception,'allocation unavailable'):
            self.commit_many([(self.record,1900),(second,1900)])
        self.assertEqual(self.labels(),['X','T'])
        self.assertEqual(self.g.allocations,1)
        self.assertEqual(self.g.disposals,1)
        self.assertEqual(self.g.insertions,0)
        self.assertEqual(self.record.m_duration,1900)
        self.assertEqual(second.m_duration,1900)

    def test_mixed_live_cache_refresh_and_missing_batch(self):
        second=self.batch_setup()
        frame=self.missing()
        self.commit_many([(self.record,1900),(second,2000)])
        self.assertEqual(self.g.memory[0x3200].remaining,1050)
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','B','T'])
        self.assertEqual(self.g.allocations,1)

    def test_separate_immediate_reconstructions_recognize_own_earlier_insertions(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.death(0x3200); self.g.finish(frame)
        self.commit(1900)
        self.commit(2000,second)
        self.assertEqual(self.labels(),['A','X','B','T'])
        self.assertEqual(self.g.allocations,2)

    def test_elapsed_boundary_advances_phase_without_backfilled_heal_operation(self):
        self.g.meta(0x9000).counter=13
        frame=self.missing(); self.g.finish(frame)
        frame=self.frame(); self.g.finish(frame)
        self.commit(1900)
        self.assertEqual(self.g.memory[0x5000].phase,0)  # saved2 + one elapsed boundary, modulo3
        self.assertEqual(self.g.memory[0x5000].remaining,449)
        self.assertEqual(list(self.g.operations.values()),['allocate','insert'])

    def test_wrong_allocator_amount_is_rejected_and_detached_memory_disposed(self):
        frame=self.missing(); self.g.finish(frame)
        self.lua.execute('''
            local original=api.recovery.allocate
            api.recovery.allocate=function(state,changes)
                local result=original(state,changes); memory[result.pointer].amount=999; return result
            end
        ''')
        with self.assertRaisesRegex(Exception,'restore exact cache fields'): self.commit()
        self.assertEqual(self.g.disposals,1)
        self.assertEqual(self.g.insertions,0)

    def test_success_return_without_native_insert_is_detected(self):
        frame=self.missing(); self.g.finish(frame)
        self.lua.execute('api.recovery.insert=function() end')
        with self.assertRaisesRegex(Exception,'insertion changed unrelated list state'): self.commit()
        self.assertEqual(self.record.m_duration,1900)
        self.assertEqual(self.g.disposals,0)  # Never guess ownership after an insertion call.

    def test_independent_lists_defer_and_restore_at_their_own_exits(self):
        other=self.add(0x2200,0x3200,0xA000,1450)
        frame=self.missing()
        inner=self.frame(0xA000); self.g.death(0x3200)
        self.commit(1900,other)
        self.g.finish(inner)
        self.assertEqual(self.g.allocations,1)
        self.assertEqual(len(self.g.lists[0x9000]),0)
        self.commit(2000)
        self.g.finish(frame)
        self.assertEqual(self.g.allocations,2)
        self.assertEqual(len(self.g.lists[0x9000]),1)
        self.assertEqual(len(self.g.lists[0xA000]),1)

    def test_observed_unowned_append_after_retired_tail_keeps_old_position(self):
        frame=self.missing(); self.commit()
        self.g.cache(0x3100,500)
        self.lua.eval('table.insert')(self.g.lists[0x9000],0x3100)
        self.assertFalse(self.module.onAppend(0xDEAD,0x3100,0x9000))  # no owned original
        self.g.finish(frame)
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000,0x3100])

    def test_observed_append_with_cache_address_reuse_has_new_logical_position(self):
        self.add()
        frame=self.missing(); self.commit()
        self.g.removeCache(0x3100)
        self.g.cache(0x3100,500)
        self.lua.eval('table.insert')(self.g.lists[0x9000],0x3100)
        self.module.onAppend(0x2100,0x3100,0x9000)
        self.g.finish(frame)
        self.assertEqual(list(self.g.lists[0x9000].values()),[0x5000,0x3100])

    def test_observed_append_between_two_removal_passes_extends_batch_order(self):
        second=self.batch_setup()
        frame=self.missing(); self.g.finish(frame)
        self.g.cache(0x3400,500); self.g.memory[0x3400].label='N'
        self.lua.eval('table.insert')(self.g.lists[0x9000],0x3400)
        self.module.onNativeAppend(0x9000,0x3400)
        frame=self.frame(); self.g.death(0x3200)
        self.commit_many([(self.record,1900),(second,2000)])
        self.g.finish(frame)
        self.assertEqual(self.labels(),['A','X','B','T','N'])

    def test_forged_append_cannot_explain_a_middle_insert_or_other_mutation(self):
        self.add()
        frame=self.missing()
        self.g.cache(0x3400,500)
        self.lua.eval('table.insert')(self.g.lists[0x9000],1,0x3400)
        with self.assertRaisesRegex(Exception,'not current native tail'):
            self.module.onNativeAppend(0x9000,0x3400)
        self.g.cache(0x3500,500)
        self.lua.eval('table.insert')(self.g.lists[0x9000],0x3500)
        with self.assertRaisesRegex(Exception,'another unknown/reordered'):
            self.module.onNativeAppend(0x9000,0x3500)
        self.assertEqual(self.g.allocations,0)


if __name__=="__main__": unittest.main()
