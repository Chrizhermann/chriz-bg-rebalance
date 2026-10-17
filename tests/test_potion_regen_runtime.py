"""Real Runtime/Core/Native/Messages/regeneration composition, offline only.

Uses the bridge's explicit byte-memory/native-service fixtures. Persistence is
an explicit boundary double returning real SpriteLifetime identities. Native
delivery, first Apply98 and effect insertion are simulated; no game/DLL runs.
"""
import unittest

from tests import test_potion_regen_native as native_tests
from tests import test_potion_native_reader as reader_tests

ROOT = native_tests.ROOT


class RegenerationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_tests.RegenerationNativeBridgeTests()
        self.fixture.setUp()
        self.lua, self.g = self.fixture.lua, self.fixture.g
        # Match Linked/Lab's failure adapter: a contained native callback error
        # must disable Runtime even when recovery occurs AFTER admit returns.
        self.bridge = self.fixture.module.new(self.g, self.g.reader, self.g.lifetime,
            self.fixture.parts, self.lua.eval('''function(reason)
                errors[#errors+1]=reason
                if runtime then runtime.disable(reason) end
            end'''))
        self.fixture.bridge = self.bridge
        self.g.bridge, self.g.adapter = self.bridge, self.bridge
        self.fixture.ready()
        manifest = reader_tests.manifest({'r': self.fixture.fields}, 'POTN42')
        manifest['sources']['POTN42']['abilities'] = {
            '0': {'count': 1, 'effects': {'0': 'r'}, 'quotas': {'r': 1}},
            # Native record counts are quotas, not fixed potion layouts.
            '1': {'count': 2, 'effects': {'0': 'r', '1': 'r'}, 'quotas': {'r': 2}},
        }
        self.lua.execute('''
            persistenceCalls={}; persistenceFailure=nil; persistenceLive=false
            persistence={
                requireSprite=function(sprite)
                    return assert(lifetime.identity(reader.ptr(sprite)),'missing real sprite lifetime')
                end,
                hasLive=function() return persistenceLive end,
                reset=function() persistenceCalls[#persistenceCalls+1]='reset' end,
                invalidate=function(reason)
                    persistenceFailure=reason;persistenceCalls[#persistenceCalls+1]='invalidate'
                end,
                status=function() return persistenceFailure==nil,persistenceFailure end,
            }
            -- IR's original mode2 amount1 produces a mode2 interval1 cache.
            -- Native Apply98 itself is an explicit construction boundary double.
            function makeCache(p,remaining)
                zero(p,48);put(p,8,BASE+0x598B18);put(p+0x12,2,5)
                put(p+0x18,2,1);put(p+0x1A,2,0);put(p+0x20,2,2)
                put(p+0x24,2,1);put(p+0x28,4,remaining)
            end
            put(SPRITE+0x48,4,42)
            function nativeWords(p,n)
                local out={};for i=0,n-1 do out[#out+1]=mem[p+i] end;return out
            end
            trace={}
        ''')
        self.runtime = self.lua.execute((ROOT / 'CBRPQRuntime.lua').read_text())(
            self.g.core, self.lua.execute((ROOT / 'CBRPQMessages.lua').read_text()),
            self.g.reader, self.fixture.table(manifest),
            self.lua.eval('function(reason) errors[#errors+1]=reason end'),
            self.lua.table_from({'regeneration': self.bridge, 'persistence': self.g.persistence}))
        self.g.runtime = self.runtime
        self.next_pointer = 0x50000
        self.next_message = 0x80000
        self.next_frame = 0xB0000

    def active(self, p=0x20000, cache=0x30000):
        effect = self.fixture.effect(p)
        self.g.put(p + 0x110, 4, 42)
        self.assertTrue(self.fixture.add_cache(p, cache))
        return effect

    def queue(self, ability=0, count=1, kind='use'):
        self.next_frame += 1
        frame = self.next_frame
        self.runtime[kind + 'Begin'](frame, ability)
        queued = []
        for ordinal in range(count):
            self.next_pointer += 0x1000; self.next_message += 1
            effect = self.fixture.effect(self.next_pointer, active=False)
            self.g.put(effect.pointer + 0x110, 4, 42)
            self.runtime[kind + 'Queue'](frame, self.next_message, effect, ordinal)
            queued.append((self.next_message, effect))
        self.runtime[kind + 'End'](frame)
        self.assertTrue(self.runtime.status()[0], self.runtime.status()[1])
        return queued

    def admit(self, queued, index=0, no_save=0):
        message, effect = queued[index]
        self.runtime.messageEnter(message, effect.pointer, no_save)
        return self.runtime.admit(effect, self.g.spriteObjects[self.g.SPRITE])

    def finish(self, queued, index=0, rejected=True):
        message, effect = queued[index]
        self.runtime.messageLeave(message)
        self.runtime.destroy(message)
        if rejected: self.runtime.effectDestroy(effect.pointer)

    def image(self, pointer, size=0x180):
        return tuple(self.g.nativeWords(pointer, size).values())

    def cache_order(self):
        return list(self.g.listPointers(self.g.LIST).values())

    def natural_death(self, caches=(0x30000,), finish=True):
        self.g.enter()
        for p in caches: self.g.death(p)
        if finish: self.assertTrue(self.g.finish())

    def test_live_cache_refresh_preserves_incoming_and_original_fields_except_native_expiry(self):
        old = self.active(); old_bytes = self.image(old.pointer)
        queued = self.queue(); incoming = self.image(queued[0][1].pointer)
        self.assertTrue(self.admit(queued))
        self.assertEqual(2349, old.m_duration)
        self.assertEqual(900, self.g.get(0x30028, 4))
        self.assertEqual(0, self.g.get(0x3001A, 2))
        after = self.image(old.pointer)
        self.assertEqual(old_bytes[:0x28] + old_bytes[0x2C:], after[:0x28] + after[0x2C:])
        self.assertEqual(incoming, self.image(queued[0][1].pointer))
        self.assertEqual(0, self.g.serviceExecutions)
        self.finish(queued)
        self.assertEqual((True, None), self.runtime.status())
        self.assertFalse(self.runtime.hasDelivery())

    def test_expiry_minus_one_reconstructs_two_natural_deaths_in_original_order(self):
        first = self.active()
        second = self.active(0x21000, 0x31000)
        # An unrelated cache remains after both owned entries; order is physical.
        self.g.makeCache(0x32000, 100)
        node = self.g.insertRaw(self.g.LIST, 0x32000, 0)
        self.assertFalse(self.bridge.callbacks.append(self.g.LIST, 0x32000, node, 0x777))
        self.assertFalse(self.bridge.status().halted) # No recovery history exists yet.
        self.natural_death((0x30000, 0x31000))
        queued = self.queue(ability=1, count=2, kind='fire')
        self.assertTrue(self.admit(queued, 0)); self.finish(queued, 0)
        self.assertTrue(self.admit(queued, 1)); self.finish(queued, 1)
        self.assertEqual([0x200000, 0x200200, 0x32000], self.cache_order())
        self.assertEqual((2349, 2349), (first.m_duration, second.m_duration))
        self.assertEqual((899, 899), (self.g.get(0x200028, 4), self.g.get(0x200228, 4)))
        self.assertEqual(4, self.g.serviceExecutions)
        self.assertEqual(0, len(self.bridge.status().scratch))
        self.assertEqual((True, None), self.runtime.status())

    def test_recovery_during_native_pass_defers_services_until_matching_exit(self):
        old = self.active(); self.natural_death(finish=False)
        queued = self.queue()
        self.assertTrue(self.admit(queued)); self.finish(queued)
        self.assertEqual(2349, old.m_duration)
        self.assertEqual([], self.cache_order())
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertTrue(self.g.finish())
        self.assertEqual([0x200000], self.cache_order())
        self.assertEqual(899, self.g.get(0x200028, 4))
        self.assertEqual(2, self.g.serviceExecutions)

    def test_deferred_callback_failure_reports_and_disables_runtime_after_completed_rejection(self):
        old = self.active(); self.natural_death(finish=False)
        queued = self.queue()
        self.assertTrue(self.admit(queued)); self.finish(queued)
        self.assertEqual((True, None), self.runtime.status())
        self.g.allocateStatus = 2
        self.assertFalse(self.g.finish())
        self.assertTrue(self.bridge.status().halted)
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('allocation status 2', self.runtime.status()[1])
        self.assertEqual(2349, old.m_duration)
        self.assertEqual([], self.cache_order())
        self.assertEqual('invalidate', self.g.persistenceCalls[1])
        self.assertFalse(self.runtime.hasDelivery())

    def test_native_clear_cancels_deferred_reconstruction_without_healing_or_replay(self):
        old = self.active(); self.natural_death(finish=False)
        queued = self.queue(); self.assertTrue(self.admit(queued)); self.finish(queued)
        self.assertTrue(self.bridge.callbacks.clear(self.g.LIST))
        self.assertTrue(self.g.finish())
        self.assertEqual(2349, old.m_duration)
        self.assertEqual([], self.cache_order())
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertEqual((True, None), self.runtime.status())

    def test_prepare_failure_returns_native_allow_with_no_partial_expiry_or_cache_write(self):
        old = self.active(); queued = self.queue()
        before, cache_before = self.image(old.pointer), self.image(0x30000, 48)
        self.g.put(self.g.LIST + 0x30, 4, 0) # Concrete invalid native pool metadata.
        self.assertFalse(self.admit(queued))
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('pool block count', self.runtime.status()[1])
        self.assertEqual(before, self.image(old.pointer))
        self.assertEqual(cache_before, self.image(0x30000, 48))
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertEqual('invalidate', self.g.persistenceCalls[1])
        self.assertFalse(self.runtime.hasDelivery())

    def test_postcommit_allocation_failure_preserves_reject_and_halts_without_admitting_repeat(self):
        old = self.active(); self.natural_death(); queued = self.queue()
        self.g.allocateStatus = 2
        self.assertTrue(self.admit(queued))
        self.assertEqual(2349, old.m_duration) # Commit happened; no rollback claim.
        self.assertEqual([], self.cache_order())
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('allocation status 2', self.runtime.status()[1])
        self.assertEqual(0, len(self.bridge.status().scratch))
        self.assertFalse(self.runtime.hasDelivery())
        self.finish(queued) # Late native return and destructor stay safe.

    def test_postcommit_cache_write_failure_keeps_native_rejection_and_reports_partial_state(self):
        old = self.active(); queued = self.queue()
        self.lua.execute('''
            local write=EEex_Write32
            EEex_Write32=function(p,value)
                if p==0x30028 then error('injected cache countdown write failure') end
                return write(p,value)
            end
        ''')
        self.assertTrue(self.admit(queued))
        self.assertEqual(2349, old.m_duration)
        self.assertEqual(1, self.g.get(0x30028, 4))
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('countdown write failure', self.runtime.status()[1])
        self.assertEqual(0, self.g.serviceExecutions)

    def test_postcommit_uncertain_adoption_preserves_reject_and_retains_handles(self):
        old = self.active(); self.natural_death(); queued = self.queue()
        self.g.throwAfterInsert = True
        self.assertTrue(self.admit(queued))
        self.assertEqual(2349, old.m_duration)
        self.assertEqual([0x200000], self.cache_order())
        self.assertFalse(self.runtime.status()[0])
        self.assertTrue(self.bridge.status().pending[1].uncertain)
        self.assertEqual(0, self.bridge.cleanupDetached())
        self.assertEqual(0, self.g.serviceCalls.dispose)
        self.runtime.reset()
        self.assertIn('unresolved native allocation', self.runtime.status()[1])
        self.assertEqual(1, len(self.bridge.status().pending))

    def test_native_failed_admission_does_not_refresh_or_reconstruct(self):
        old = self.active(); self.natural_death(); queued = self.queue()
        message, effect = queued[0]
        self.runtime.messageEnter(message, effect.pointer, 0)
        # CheckAdd rejection never reaches Runtime.admit at the success hook.
        self.finish(queued)
        self.assertEqual(1450, old.m_duration)
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertEqual((True, None), self.runtime.status())

    def test_same_dose_duplicate_records_remain_native_with_separate_cache_lineage(self):
        queued = self.queue(ability=1, count=2)
        for index, (_, effect) in enumerate(queued):
            self.assertFalse(self.admit(queued, index))
            # Native resolve, Apply98 append and timed-list linking are doubles.
            self.g.put(effect.pointer + 0x24, 4, 4096)
            self.g.put(effect.pointer + 0x28, 4, 2349)
            self.assertTrue(self.fixture.add_cache(effect.pointer, 0x30000 + index * 0x1000))
            self.g.currentEffect(effect.pointer)
            self.finish(queued, index, rejected=False)
        self.assertEqual(2, len(self.g.spriteObjects[self.g.SPRITE].m_timedEffectList))
        self.assertEqual([0x30000, 0x31000], self.cache_order())
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertEqual((True, None), self.runtime.status())

    def test_effect_destruction_retires_real_reader_token_after_regeneration_cleanup_even_on_error(self):
        old = self.active(); before = self.g.reader.identify(old, None, False).identity
        self.lua.execute('''
            local cleanup=bridge.onOriginalDestroy
            bridge.onOriginalDestroy=function(p)
                trace[#trace+1]='regen';cleanup(p);error('injected destructor observer failure')
            end
            local retire=reader.retire
            reader.retire=function(p) trace[#trace+1]='reader';return retire(p) end
        ''')
        self.runtime.effectDestroy(old.pointer)
        self.assertEqual(['regen', 'reader'], list(self.g.trace.values()))
        self.assertFalse(self.runtime.status()[0])
        self.g.removeEffect(old.pointer)
        replacement = self.fixture.effect(old.pointer)
        after = self.g.reader.identify(replacement, None, False).identity
        self.assertFalse(self.lua.eval('function(a,b) return a==b end')(before, after))
        self.assertIsNone(self.g.captured.original(old.pointer))

    def test_effect_destruction_after_runtime_disable_still_retires_token(self):
        old = self.active(); before = self.g.reader.identify(old, None, False).identity
        self.runtime.disable('explicit test shutdown')
        self.runtime.effectDestroy(old.pointer)
        after = self.g.reader.identify(old, None, False).identity
        self.assertFalse(self.lua.eval('function(a,b) return a==b end')(before, after))
        self.assertIsNone(self.g.captured.original(old.pointer))

    def test_destroyed_original_cancels_pending_recovery_without_resurrection(self):
        old = self.active(); self.natural_death(finish=False)
        queued = self.queue(); self.assertTrue(self.admit(queued)); self.finish(queued)
        self.runtime.effectDestroy(old.pointer); self.g.removeEffect(old.pointer)
        self.assertTrue(self.g.finish())
        self.assertEqual([], self.cache_order())
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertEqual((True, None), self.runtime.status())

    def test_canceled_queued_message_and_original_pointer_reuse_do_not_inherit_old_dose(self):
        old = self.active(); queued = self.queue(); message, effect = queued[0]
        old_incoming = self.g.reader.identify(effect, None, True).identity
        self.runtime.destroy(message); self.runtime.effectDestroy(effect.pointer)
        reused = self.fixture.effect(effect.pointer, active=False)
        self.assertFalse(self.lua.eval('function(a,b) return a==b end')(
            old_incoming, self.g.reader.identify(reused, None, True).identity))
        self.runtime.messageEnter(message, reused.pointer, 0)
        self.assertFalse(self.runtime.admit(reused, self.g.spriteObjects[self.g.SPRITE]))
        self.runtime.messageLeave(message); self.runtime.destroy(message)
        self.assertEqual(1450, old.m_duration)
        self.assertEqual(1, self.g.get(0x30028, 4))
        self.assertEqual((True, None), self.runtime.status())

    def test_reset_clears_regeneration_before_persistence_and_native_tokens(self):
        old = self.active(); before = self.g.reader.identify(old, None, False).identity
        self.lua.execute('''
            local resetRegen=bridge.reset
            bridge.reset=function() trace[#trace+1]='regen';return resetRegen() end
            local resetPersistence=persistence.reset
            persistence.reset=function() trace[#trace+1]='persistence';return resetPersistence() end
            local resetTokens=reader.resetTokens
            reader.resetTokens=function() trace[#trace+1]='tokens';return resetTokens() end
        ''')
        self.runtime.reset()
        self.assertEqual(['regen', 'persistence', 'tokens'], list(self.g.trace.values()))
        self.assertIsNone(self.g.captured.original(old.pointer))
        self.assertFalse(self.lua.eval('function(a,b) return a==b end')(
            before, self.g.reader.identify(old, None, False).identity))
        self.assertEqual((True, None), self.runtime.status())

    def test_reset_with_outstanding_delivery_invalidates_without_forgetting_cache_ownership(self):
        old = self.active(); before = self.g.reader.identify(old, None, False).identity
        self.queue(); self.runtime.reset()
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('surviving potion delivery', self.runtime.status()[1])
        self.assertTrue(self.lua.eval('function(a,b) return a==b end')(
            before, self.g.reader.identify(old, None, False).identity))
        self.assertEqual(1450, old.m_duration)
        self.assertEqual(1, self.g.get(0x30028, 4))

    def test_native_no_save_route_diagnoses_before_any_refresh(self):
        old = self.active(); queued = self.queue()
        self.assertFalse(self.admit(queued, no_save=1))
        self.assertFalse(self.runtime.status()[0])
        self.assertIn('noSave', self.runtime.status()[1])
        self.assertEqual(1450, old.m_duration)
        self.assertEqual(0, self.g.serviceExecutions)


if __name__ == '__main__': unittest.main()
