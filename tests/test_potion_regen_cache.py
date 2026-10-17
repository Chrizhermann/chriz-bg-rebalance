"""Offline LuaJIT bookkeeping tests; no EEex/game/native memory access."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "research/prototypes/potion-admission"


class RegenerationCacheTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            originals, memory, lists, writes = {}, {}, {}, {}
            reads, failWrite, failAfterWrite = 0, nil, false
            now, imageVtable = 1000, 0x140598B18
            api = {
                regenerationVtable=imageVtable,
                ptr=function(o) return o.pointer end,
                original=function(p) reads=reads+1; return originals[p] end,
                isCurrentOriginal=function(s,p,id)
                    reads=reads+1
                    return originals[p] and originals[p].identity==id
                        and originals[p].sprite==s and originals[p].current
                end,
                currentCaches=function(s) reads=reads+1; return lists[s] or {} end,
                cache=function(p) reads=reads+1; return memory[p] end,
                now=function() return now end,
                writeRemaining=function(p,value)
                    if failWrite==p and not failAfterWrite then error('mock write failed') end
                    memory[p].remaining=value
                    writes[#writes+1]={pointer=p,value=value}
                    if failWrite==p and failAfterWrite then error('mock write failed after mutation') end
                end,
            }
            function effect(p,opcode,expiry,sprite)
                originals[p]={identity={},opcode=opcode,timing=4096,expiry=expiry,
                    done=false,current=true,sprite=sprite}
                return setmetatable({pointer=p}, {
                    __index=function(_,k) if k=='m_duration' then return originals[p].expiry end end,
                    __newindex=function(_,k,v)
                        if k=='m_duration' then originals[p].expiry=v else error('unexpected native effect write') end
                    end,
                })
            end
            function cache(p,remaining)
                memory[p]={vtable=imageVtable,remaining=remaining,done=false,canceled=false,
                    phase=2,interval=3,amount=1,unrelated='preserve'}
            end
            function update(o,expiry)
                return {record=o,identity=originals[o.pointer].identity,
                    oldExpiry=originals[o.pointer].expiry,expiry=expiry}
            end
            function expireCore(updates)
                for _,u in ipairs(updates) do u.record.m_duration=u.expiry end
            end
            function count(t) local n=0; for _ in pairs(t) do n=n+1 end; return n end
        """)
        self.g = self.lua.globals()
        self.factory = self.lua.execute((PROTOTYPE / "CBRPQRegenCache.lua").read_text())
        self.module = self.factory(self.g.api)
        self.core = self.lua.execute((PROTOTYPE / "CBRPQCore.lua").read_text())
        self.record = self.g.effect(0x2000, 98, 1450, 0x9000)
        self.g.cache(0x3000, 451)
        self.g.lists[0x9000] = self.lua.table_from([0x3000])
        self.module.onAppend(0x2000, 0x3000, 0x9000)

    def updates(self, expiry=1900, record=None):
        return self.lua.table_from([self.g.update(record or self.record, expiry)])

    def core_commit(self, updates):
        return self.core.commit(self.lua.table_from({"refresh": updates, "allow": False, "state": self.lua.table()}))

    def prepare_commit(self, expiry=1900, record=None):
        updates = self.updates(expiry, record)
        txn = self.module.prepare(updates)
        self.core_commit(updates)
        count = txn.commit()
        return count

    def no_writes(self):
        self.assertEqual(self.g.count(self.g.writes), 0)

    def test_exact_delta_preserves_phase_offset_and_unrelated_cache(self):
        other = self.g.effect(0x2100, 98, 1700, 0x9000)
        self.g.cache(0x3100, 500)
        self.g.memory[0x3100].phase = 1
        self.g.lists[0x9000] = self.lua.table_from([0x3100, 0x3000])
        self.module.onAppend(0x2100, 0x3100, 0x9000)
        self.assertEqual(self.prepare_commit(), 1)
        self.assertEqual(self.record.m_duration, 1900)
        self.assertEqual(self.g.memory[0x3000].remaining, 901)  # retained +1 offset
        self.assertEqual(self.g.memory[0x3000].phase, 2)
        self.assertEqual(self.g.memory[0x3000].unrelated, "preserve")
        self.assertEqual(self.g.memory[0x3100].remaining, 500)
        self.assertEqual(self.g.memory[0x3100].phase, 1)
        self.assertEqual(other.m_duration, 1700)

    def test_duplicate_same_time_dose_does_not_add_duration_again(self):
        self.prepare_commit()
        self.prepare_commit()
        self.assertEqual(self.g.memory[0x3000].remaining, 901)

    def test_shortening_preserves_exact_countdown_delta(self):
        self.prepare_commit(1200)
        self.assertEqual(self.g.memory[0x3000].remaining, 201)

    def test_shortening_to_nonpositive_cache_is_rejected(self):
        self.g.memory[0x3000].remaining = 100
        with self.assertRaisesRegex(Exception, "replacement cache countdown"):
            self.module.prepare(self.updates(1200))
        self.no_writes()
        self.assertEqual(self.record.m_duration, 1450)

    def test_cache_signed_bounds_and_sentinel_are_not_wrapped(self):
        for value in (-2147483648, -1, 0, 2147483647, 4294967295):
            with self.subTest(value=value):
                self.g.memory[0x3000].remaining = value
                with self.assertRaises(Exception): self.module.prepare(self.updates())
                self.no_writes()

    def test_max_positive_countdown_with_zero_delta_is_valid(self):
        self.g.memory[0x3000].remaining = 2147483647
        self.prepare_commit(1450)
        self.assertEqual(self.g.memory[0x3000].remaining, 2147483647)

    def test_cache_done_cancel_or_wrong_class_reject_before_write(self):
        for field, invalid in (("done", True), ("canceled", True), ("vtable", 123)):
            with self.subTest(field=field):
                old = self.g.memory[0x3000][field]
                self.g.memory[0x3000][field] = invalid
                with self.assertRaises(Exception): self.module.prepare(self.updates())
                self.g.memory[0x3000][field] = old
                self.no_writes()

    def test_missing_or_duplicate_current_cache_diagnoses(self):
        self.g.lists[0x9000] = self.lua.table()
        with self.assertRaisesRegex(Exception, "missing current cache"):
            self.module.prepare(self.updates())
        self.g.cache(0x3100, 451)
        self.module.onCopy(0x3000, 0x3100)
        self.g.lists[0x9000] = self.lua.table_from([0x3000, 0x3100])
        with self.assertRaisesRegex(Exception, "multiple current caches"):
            self.module.prepare(self.updates())
        self.no_writes()

    def test_snapshot_copy_is_ignored_until_restored_to_live_list(self):
        self.g.cache(0x3100, 451)
        self.module.onCopy(0x3000, 0x3100)
        self.prepare_commit()
        self.assertEqual(self.g.memory[0x3100].remaining, 451)
        self.module.onCacheDestroy(0x3000)
        self.g.memory[0x3100].remaining = 901
        self.g.lists[0x9000] = self.lua.table_from([0x3100])
        self.prepare_commit(2000)
        self.assertEqual(self.g.memory[0x3100].remaining, 1001)

    def test_destroy_and_same_address_reuse_invalidates_old_transaction(self):
        updates = self.updates()
        txn = self.module.prepare(updates)
        self.module.onCacheDestroy(0x3000)
        self.g.cache(0x3000, 451)
        self.module.onAppend(0x2000, 0x3000, 0x9000)
        self.core_commit(updates)
        with self.assertRaisesRegex(Exception, "lifetimes changed"):
            txn.commit()
        self.no_writes()

    def test_original_destroy_purges_copies_without_native_reads(self):
        self.g.cache(0x3100, 451)
        self.module.onCopy(0x3000, 0x3100)
        reads = self.g.reads
        self.module.onOriginalDestroy(0x2000)
        self.module.onCacheDestroy(0x3000)
        self.module.reset()
        self.assertEqual(self.g.reads, reads)
        self.assertFalse(self.module.onCopy(0x3100, 0x3200))
        with self.assertRaisesRegex(Exception, "missing original cache lineage"):
            self.module.prepare(self.updates())

    def test_original_aba_plan_cannot_bind_replacement_same_address(self):
        updates = self.updates()
        self.module.onOriginalDestroy(0x2000)
        self.g.effect(0x2000, 98, 1450, 0x9000)
        self.module.onAppend(0x2000, 0x3000, 0x9000)
        with self.assertRaisesRegex(Exception, "planned original lifetime changed"):
            self.module.prepare(updates)
        self.no_writes()

    def test_append_rejects_unretired_original_identity_change(self):
        self.g.effect(0x2000, 98, 1450, 0x9000)
        self.g.cache(0x3100, 451)
        with self.assertRaisesRegex(Exception, "lifetime changed without destruction"):
            self.module.onAppend(0x2000, 0x3100, 0x9000)

    def test_live_pointer_reuse_is_rejected_before_losing_binding(self):
        for method, arguments in ((self.module.onAppend, (0x2000, 0x3000, 0x9000)),
                                  (self.module.onCopy, (0x3000, 0x3000))):
            with self.assertRaisesRegex(Exception, "live cache pointer reused"):
                method(*arguments)
        self.prepare_commit()
        self.assertEqual(self.g.memory[0x3000].remaining, 901)

    def test_non98_and_unowned_append_copy_are_ignored(self):
        skill = self.g.effect(0x2100, 90, 1450, 0x9000)
        self.assertFalse(self.module.onAppend(0x2100, 0x3100, 0x9000))
        self.assertFalse(self.module.onAppend(0x2200, 0x3200, 0x9000))
        self.assertFalse(self.module.onCopy(0x3200, 0x3300))
        self.assertEqual(self.prepare_commit(record=skill), 0)
        self.no_writes()

    def test_absent_original_or_wrong_list_membership_rejects(self):
        for field, invalid in (("current", False), ("done", True), ("timing", 0), ("expiry", 999)):
            with self.subTest(field=field):
                updates = self.updates()
                previous = self.g.originals[0x2000][field]
                self.g.originals[0x2000][field] = invalid
                with self.assertRaises(Exception): self.module.prepare(updates)
                self.g.originals[0x2000][field] = previous
                self.no_writes()

    def test_all_updates_preflight_before_any_mutation(self):
        other = self.g.effect(0x2100, 98, 1450, 0x9000)
        self.g.cache(0x3100, 100)
        self.module.onAppend(0x2100, 0x3100, 0x9000)
        self.g.lists[0x9000] = self.lua.table_from([0x3000, 0x3100])
        updates = self.lua.table_from([self.g.update(self.record, 1900), self.g.update(other, 1100)])
        with self.assertRaisesRegex(Exception, "replacement cache countdown"):
            self.module.prepare(updates)
        self.assertEqual(self.record.m_duration, 1450)
        self.no_writes()

    def test_commit_requires_core_expiry_commit_first(self):
        txn = self.module.prepare(self.updates())
        with self.assertRaisesRegex(Exception, "timing/expiry changed"):
            txn.commit()
        self.no_writes()

    def test_commit_rechecks_every_cache_before_first_write(self):
        other = self.g.effect(0x2100, 98, 1450, 0x9000)
        self.g.cache(0x3100, 451)
        self.module.onAppend(0x2100, 0x3100, 0x9000)
        self.g.lists[0x9000] = self.lua.table_from([0x3000, 0x3100])
        updates = self.lua.table_from([self.g.update(self.record, 1900), self.g.update(other, 1900)])
        txn = self.module.prepare(updates)
        self.core_commit(updates)
        self.g.memory[0x3100].remaining = 450
        with self.assertRaisesRegex(Exception, "countdown changed"):
            txn.commit()
        self.no_writes()
        self.assertEqual(self.record.m_duration, 1900)  # No false rollback claim.

    def test_transactions_are_single_use_and_reset_invalidates(self):
        updates = self.updates()
        txn = self.module.prepare(updates)
        self.module.reset()
        with self.assertRaisesRegex(Exception, "lifetimes changed"): txn.commit()
        with self.assertRaisesRegex(Exception, "already used"): txn.commit()

    def test_duplicate_refresh_and_invalid_pointers_are_rejected(self):
        update = self.g.update(self.record, 1900)
        with self.assertRaisesRegex(Exception, "duplicate original refresh"):
            self.module.prepare(self.lua.table_from([update, update]))
        for value in (0, -1, 1.5, 9007199254740991):
            with self.assertRaisesRegex(Exception, "invalid native pointer"):
                self.module.onAppend(0x2000, value, 0x9000)
        self.no_writes()

    def test_native_write_failure_is_visible_and_not_retried_or_rolled_back(self):
        updates = self.updates()
        txn = self.module.prepare(updates)
        self.core_commit(updates)
        self.g.failWrite, self.g.failAfterWrite = 0x3000, True
        with self.assertRaisesRegex(Exception, "mock write failed after mutation"): txn.commit()
        self.assertEqual(self.record.m_duration, 1900)
        self.assertEqual(self.g.memory[0x3000].remaining, 901)
        with self.assertRaisesRegex(Exception, "already used"): txn.commit()


if __name__ == "__main__":
    unittest.main()
