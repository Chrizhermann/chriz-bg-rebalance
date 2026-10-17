"""Actual lifetime registry/generator; explicit native-memory/patch doubles."""
from pathlib import Path
import unittest
from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1] / 'research/prototypes/potion-admission'


class EarlyStartupTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.g.Early = self.lua.execute((ROOT / 'CBRPQEarly.lua').read_text())
        self.g.Lifetime = self.lua.execute((ROOT / 'CBRPQSpriteLifetime.lua').read_text())
        self.lua.execute('''
            BASE,CHITIN,SPRITE=0x140000000,0x70000,0x80000
            memory,bytes,events,errors,patches,reads={},{},{},{},{},{}
            protections,generations=0,0
            memory[BASE+0x667548]=0
            for _,guard in ipairs(Lifetime.guards) do
                for n=1,#guard[3],2 do bytes[BASE+guard[2]+(n-1)/2]=tonumber(guard[3]:sub(n,n+1),16) end
            end
            local value=BASE+0x1A4630
            for n=0,7 do bytes[BASE+0x598B68+n]=value%256;value=math.floor(value/256) end
            api={EEex_HookIntegrityWatchdog_Load=false,
                EEex_GetImageBase=function() return BASE end,
                EEex_ReadPtr=function(p)
                    reads[#reads+1]=p
                    assert(memory[p]~=nil,'unexpected native pointer read')
                    return memory[p]
                end,
                EEex_ReadU8=function(p) assert(bytes[p]~=nil,'unexpected code read');return bytes[p] end,
                EEex_GenLuaCall=function(name,args) generations=generations+1;return {'call '..name} end,
                EEex_FlattenTable=function(parts) return parts end,
                EEex_DisableCodeProtection=function() protections=protections+1 end,
                EEex_EnableCodeProtection=function() protections=protections-1 end,
                EEex_HookBeforeRestoreWithLabels=function(address,...)
                    assert(api.CBRPQEarlyReceipt==nil,'receipt published before all hooks')
                    patches[#patches+1]=address
                    if failHook==#patches then error('injected native patch failure') end
                    if rejectHook==#patches then return false end
                end}
            config={report=function(reason) errors[#errors+1]=reason end}
            parts={spriteLifetime=Lifetime}
            sinks={
                onRetire=function(p,id) events[#events+1]={'retire',p,id} end,
                onContentsReset=function(p,id) events[#events+1]={'clear',p,id} end,
                onReset=function() events[#events+1]={'reset'} end,
                report=function(reason) errors[#errors+1]=reason end}
            function make() bootstrap=Early.prepare(api,parts,config);return bootstrap end
            function arm() receipt=bootstrap.arm();return receipt end
            function late() api.EEex_Active=true;memory[BASE+0x667548]=CHITIN;memory[CHITIN+0x1090]=0 end
            function born(p,kind)
                assert(api['CBRPQ_Early_begin'..kind](p))
                memory[p]=BASE+0x598B68;memory[p+0x1A08]=BASE+0x58F528
                assert(api['CBRPQ_Early_ready'..kind](p))
                return receipt.registry.identity(p)
            end
        ''')
        self.bootstrap = self.g.make()

    def arm(self):
        return self.g.arm()

    def same(self, a, b):
        return self.lua.eval('function(a,b) return rawequal(a,b) end')(a, b)

    def test_prepare_is_inert_and_does_not_publish_or_read_game(self):
        self.assertEqual(0, len(self.g.reads))
        self.assertEqual(0, len(self.g.patches))
        self.assertEqual(0, self.g.generations)
        self.assertIsNone(self.g.api.CBRPQ_Early_beginDefault)
        self.assertIsNone(self.g.api.CBRPQEarlyReceipt)

    def test_arm_installs_six_actual_descriptors_before_one_receipt(self):
        receipt = self.arm()
        self.assertTrue(self.same(receipt, self.g.api.CBRPQEarlyReceipt))
        self.assertEqual(6, len(self.g.patches))
        self.assertEqual(6, self.g.generations)
        self.assertEqual(0, self.g.protections)
        self.assertTrue(self.bootstrap.status().complete)
        self.assertEqual({self.g.BASE + 0x667548}, set(self.g.reads.values()))
        with self.assertRaisesRegex(Exception, 'already attempted'):
            self.bootstrap.arm()

    def test_active_or_actual_chitin_prevents_any_publication_or_patch(self):
        self.g.api.EEex_Active = True
        with self.assertRaisesRegex(Exception, 'startup already completed'):
            self.arm()
        self.g.api.EEex_Active = False
        self.g.memory[self.g.BASE + 0x667548] = self.g.CHITIN
        with self.assertRaisesRegex(Exception, 'CBaldurChitin already exists'):
            self.arm()
        self.assertEqual(0, len(self.g.patches))
        self.assertIsNone(self.g.api.CBRPQ_Early_destroy)

    def test_sdl_pointer_is_not_used_as_authority(self):
        self.g.memory[self.g.BASE + 0x667558] = self.g.CHITIN
        self.arm()
        self.assertNotIn(self.g.BASE + 0x667558, self.g.reads.values())

    def test_all_native_guards_fail_before_callback_publication(self):
        self.g.bytes[self.g.BASE + 0x34310E] = 0
        with self.assertRaisesRegex(Exception, 'unsupported/patched site readyData'):
            self.arm()
        self.assertEqual(0, len(self.g.patches))
        self.assertEqual(0, self.g.generations)
        self.assertIsNone(self.g.api.CBRPQ_Early_beginData)

    def test_provider_change_after_prepare_is_rejected_before_reads(self):
        self.lua.execute('api.EEex_ReadPtr=function() return 0 end')
        with self.assertRaisesRegex(Exception, 'provider changed'):
            self.arm()
        self.assertEqual(0, len(self.g.patches))
        self.assertEqual(0, len(self.g.reads))

    def test_foreign_namespace_is_preserved(self):
        self.lua.execute('foreign=function() end; api.CBRPQ_Early_clear=foreign')
        with self.assertRaisesRegex(Exception, 'namespace is occupied'):
            self.arm()
        self.assertTrue(self.same(self.g.foreign, self.g.api.CBRPQ_Early_clear))
        self.assertEqual(0, len(self.g.patches))

    def test_partial_native_failure_keeps_callbacks_but_never_a_receipt(self):
        self.g.failHook = 3
        with self.assertRaisesRegex(Exception, 'injected native patch failure'):
            self.arm()
        self.assertEqual(3, len(self.g.patches))
        self.assertEqual(0, self.g.protections)
        self.assertIsNone(self.g.api.CBRPQEarlyReceipt)
        self.assertIsNotNone(self.g.api.CBRPQ_Early_beginData)
        self.assertTrue(self.bootstrap.status().halted)
        with self.assertRaisesRegex(Exception, 'restart required'):
            self.arm()

    def test_receipt_and_completion_identity_are_immutable(self):
        self.arm()
        with self.assertRaisesRegex(Exception, 'receipt is immutable'):
            self.lua.execute('receipt.registry={}')
        with self.assertRaisesRegex(Exception, 'immutable completion identity'):
            self.lua.execute('receipt.completionIdentity.changed=true')
        self.lua.execute('rawset(receipt,"registry",{})');self.g.late()
        with self.assertRaisesRegex(Exception, 'was modified'):
            self.g.receipt.validateLate()

    def test_native_provider_false_result_does_not_publish_completion(self):
        self.g.rejectHook = 6
        with self.assertRaisesRegex(Exception, 'installation rejected clear'):
            self.arm()
        self.assertEqual(6, len(self.g.patches))
        self.assertEqual(0, self.g.protections)
        self.assertIsNone(self.g.api.CBRPQEarlyReceipt)

    def test_code_protection_failure_remains_restart_only_without_receipt(self):
        self.lua.execute('api.EEex_EnableCodeProtection=function() error("protect failed") end')
        self.bootstrap = self.g.make()
        with self.assertRaisesRegex(Exception, 'protect failed'):
            self.arm()
        self.assertEqual(6, len(self.g.patches))
        self.assertTrue(self.bootstrap.status().halted)
        self.assertIsNone(self.g.api.CBRPQEarlyReceipt)

    def test_late_requires_exact_pre_game_phase(self):
        receipt = self.arm()
        with self.assertRaisesRegex(Exception, 'startup has not completed'):
            receipt.validateLate()
        self.g.api.EEex_Active = True
        with self.assertRaisesRegex(Exception, 'CBaldurChitin is unavailable'):
            receipt.validateLate()
        self.g.late();self.assertTrue(receipt.validateLate())
        self.g.memory[self.g.CHITIN + 0x1090] = 0x90000
        with self.assertRaisesRegex(Exception, 'CInfGame already exists'):
            receipt.attach(self.g.sinks)
        self.assertFalse(self.bootstrap.status().attached)

    def test_default_sprite_before_attachment_uses_same_token_and_no_adoption(self):
        receipt = self.arm();old = self.g.born(self.g.SPRITE, 'Default')
        self.assertTrue(self.g.api.CBRPQ_Early_clear(self.g.SPRITE))
        self.assertEqual(0, len(self.g.events))
        self.g.late();registry = receipt.attach(self.g.sinks)
        self.assertTrue(self.same(registry, receipt.registry))
        self.assertTrue(self.same(old, registry.identity(self.g.SPRITE)))
        self.assertIsNone(registry.identity(0xA0000))
        self.assertTrue(self.g.api.CBRPQ_Early_clear(self.g.SPRITE))
        self.assertTrue(self.g.api.CBRPQ_Early_destroy(self.g.SPRITE))
        self.assertEqual(['clear', 'retire'], [e[1] for e in self.g.events.values()])
        self.assertIsNone(registry.identity(self.g.SPRITE))

    def test_pre_attachment_destruction_and_address_reuse_do_not_resurrect(self):
        receipt = self.arm();old = self.g.born(self.g.SPRITE, 'Data')
        self.g.api.CBRPQ_Early_destroy(self.g.SPRITE)
        new = self.g.born(self.g.SPRITE, 'Default')
        self.assertFalse(self.same(old, new));self.g.late()
        receipt.attach(self.g.sinks)
        self.assertTrue(self.same(new, receipt.registry.identity(self.g.SPRITE)))

    def test_pre_attachment_lifecycle_failure_prevents_late_handoff(self):
        receipt = self.arm();self.g.born(self.g.SPRITE, 'Default')
        self.assertFalse(self.g.api.CBRPQ_Early_beginData(self.g.SPRITE))
        self.g.late()
        with self.assertRaisesRegex(Exception, 'lifetime observer is halted'):
            receipt.attach(self.g.sinks)
        self.assertEqual(1, len(self.g.errors));self.assertFalse(self.bootstrap.status().attached)

    def test_late_rejects_replaced_receipt_callback_and_registry_method(self):
        receipt = self.arm();self.g.late()
        self.lua.execute('api.CBRPQEarlyReceipt={}')
        with self.assertRaisesRegex(Exception, 'unavailable or replaced'):
            receipt.validateLate()
        self.g.api.CBRPQEarlyReceipt = receipt
        self.lua.execute('original=api.CBRPQ_Early_clear;api.CBRPQ_Early_clear=function() end')
        with self.assertRaisesRegex(Exception, 'published callback changed'):
            receipt.validateLate()
        self.g.api.CBRPQ_Early_clear = self.g.original
        self.lua.execute('receipt.registry.identity=function() return {} end')
        with self.assertRaisesRegex(Exception, 'lifetime method changed'):
            receipt.validateLate()

    def test_attach_once_captures_sinks_and_reset_cleans_before_new_epoch(self):
        receipt = self.arm();old = self.g.born(self.g.SPRITE, 'Default');self.g.old = old
        self.lua.execute('sinks.onReset=function() assert(rawequal(receipt.registry.identity(SPRITE),old));events[#events+1]={"reset"} end')
        self.g.late();receipt.attach(self.g.sinks)
        self.lua.execute('sinks.onReset=function() error("later caller mutation") end')
        receipt.registry.reset()
        self.assertFalse(self.same(old, receipt.registry.identity(self.g.SPRITE)))
        self.assertEqual('reset', self.g.events[1][1])
        with self.assertRaisesRegex(Exception, 'already been attached'):
            receipt.attach(self.g.sinks)

    def test_attached_sink_failure_halts_registry_without_freed_pointer_read(self):
        receipt = self.arm();self.g.born(self.g.SPRITE, 'Default');self.g.late()
        self.lua.execute('sinks.onRetire=function() error("dependent cleanup failed") end')
        receipt.attach(self.g.sinks);read_count = len(self.g.reads)
        self.assertFalse(self.g.api.CBRPQ_Early_destroy(self.g.SPRITE))
        self.assertEqual(read_count, len(self.g.reads))
        self.assertTrue(receipt.registry.status().halted)

    def test_watchdog_validates_and_wraps_entire_native_install(self):
        self.lua.execute('''
            api.EEex_HookIntegrityWatchdog_Load=true
            watchdogEvents={}
            parts.watchdog={
                validate=function() watchdogEvents[#watchdogEvents+1]='validate' end,
                withPreservation=function(api,fn)
                    watchdogEvents[#watchdogEvents+1]='enter';fn();watchdogEvents[#watchdogEvents+1]='leave'
                end}
        ''')
        self.bootstrap = self.g.make();self.arm()
        self.assertEqual(['validate','enter','leave'], list(self.g.watchdogEvents.values()))


if __name__ == '__main__':
    unittest.main()
