"""Pure lifetime authority plus optional pinned native descriptor checks."""
from pathlib import Path
import unittest
from lupa.luajit21 import LuaRuntime
from tests.test_potion_regen_lifecycle import LifecycleHarness, read_image, BASE
from tests.test_potion_hook_preprocessor import EEEX
ROOT=Path(__file__).resolve().parents[1]/"research/prototypes/potion-admission"
MODULE=ROOT/'CBRPQSpriteLifetime.lua'
KEYS=('beginDefault','beginData','readyDefault','readyData','destroy','clear')

class SpriteLifetimeTests(unittest.TestCase):
 def setUp(self):
  self.lua=LuaRuntime(unpack_returned_tuples=True)
  self.module=self.lua.execute(MODULE.read_text())
  self.lua.execute("""
   memory,events,errors={}, {}, {};reads=0
   api={imageBase=0x140000000,
    readPtr=function(p) reads=reads+1; assert(memory[p],'invalid native memory'); return memory[p] end,
    onRetire=function(p,id) events[#events+1]={'retire',p,id} end,
    onContentsReset=function(p,id) events[#events+1]={'clear',p,id} end,
    onReset=function() events[#events+1]={'reset'} end,
    report=function(e) errors[#errors+1]=e end}
   function readyMemory(p) memory[p]=0x140598B68;memory[p+0x1A08]=0x14058F528 end
  """)
  self.g=self.lua.globals();self.registry=self.module.new(self.g.api)
  self.g.registry=self.registry
 def create(self,p=0x50000,kind='Data'):
  self.assertTrue(self.registry.callbacks['begin'+kind](p));self.g.readyMemory(p)
  self.assertTrue(self.registry.callbacks['ready'+kind](p));return self.registry.identity(p)
 def same(self,a,b):return self.lua.eval('function(a,b) return rawequal(a,b) end')(a,b)
 def test_birth_never_reads_uninitialized_memory_and_unknown_not_adopted(self):
  self.assertTrue(self.registry.callbacks.beginData(0x50000))
  self.assertIsNone(self.registry.identity(0x50000));self.assertIsNone(self.registry.identity(0x60000))
  self.assertEqual(0,self.g.reads)
 def test_both_constructors_publish_only_after_structural_ready(self):
  a=self.create(kind='Default');b=self.create(0x60000,'Data')
  self.assertFalse(self.same(a,b));self.assertEqual(4,self.g.reads)
 def test_destruction_retires_before_same_address_and_same_object_id_reuse(self):
  old=self.create();self.assertTrue(self.registry.callbacks.destroy(0x50000))
  self.assertIsNone(self.registry.identity(0x50000));new=self.create()
  self.assertFalse(self.same(old,new));self.assertEqual('retire',self.g.events[1][1])
 def test_destroy_notification_sees_old_identity_and_retirement_needs_no_native_read(self):
  old=self.create();self.lua.execute("api.onRetire=function(p,id) assert(rawequal(registry.identity(p),id)); memory={} end")
  reads=self.g.reads;self.assertTrue(self.registry.callbacks.destroy(0x50000))
  self.assertEqual(reads,self.g.reads);self.assertIsNone(self.registry.identity(0x50000))
 def test_clear_marshal_preserves_allocation_token_and_notifies_content_cleanup(self):
  old=self.create();self.assertTrue(self.registry.callbacks.clear(0x50000))
  self.assertTrue(self.same(old,self.registry.identity(0x50000)));self.assertEqual('clear',self.g.events[1][1])
 def test_copy_constructor_is_a_distinct_lifetime_despite_copied_resource_or_uuid(self):
  old=self.create();copy=self.create(0x60000)
  self.assertFalse(self.same(old,copy));self.registry.callbacks.clear(0x60000)
  self.assertTrue(self.same(copy,self.registry.identity(0x60000)))
 def test_reset_cleans_dependents_before_rotating_tokens_and_keeps_allocation_authority(self):
  old=self.create();self.lua.globals().old=old
  self.lua.execute("api.onReset=function() assert(rawequal(registry.identity(0x50000),old)); events[#events+1]={'reset'} end")
  self.registry.reset();self.assertFalse(self.same(old,self.registry.identity(0x50000)))
  self.assertTrue(self.registry.callbacks.destroy(0x50000));self.assertIsNone(self.registry.identity(0x50000))
 def test_unknown_destructor_clear_are_ignored_without_native_reads(self):
  self.assertFalse(self.registry.callbacks.destroy(0x50000));self.assertFalse(self.registry.callbacks.clear(0x50000))
  self.assertEqual(0,self.g.reads)
 def test_duplicate_begin_and_readiness_without_birth_halt(self):
  self.registry.callbacks.beginData(0x50000)
  self.assertFalse(self.registry.callbacks.beginData(0x50000));self.assertTrue(self.registry.status().halted)
  with self.assertRaisesRegex(Exception,'halted'):self.registry.identity(0x50000)
  other=self.module.new(self.g.api);self.assertFalse(other.callbacks.readyData(0x60000))
 def test_failed_constructor_destructs_pending_record_without_a_readiness_read(self):
  self.registry.callbacks.beginData(0x50000)
  self.assertTrue(self.registry.callbacks.destroy(0x50000));self.assertIsNone(self.registry.identity(0x50000))
  self.assertEqual(0,self.g.reads);self.create()
 def test_wrong_native_class_fails_ready_without_publishing_token(self):
  self.registry.callbacks.beginData(0x50000);self.g.readyMemory(0x50000);self.g.memory[0x50000]=0
  self.assertFalse(self.registry.callbacks.readyData(0x50000));self.assertIn('class mismatch',self.registry.status().error)
 def test_retirement_and_reset_errors_are_reported_and_cannot_silently_continue(self):
  self.create();self.lua.execute("api.onRetire=function() error('cleanup error') end")
  self.assertFalse(self.registry.callbacks.destroy(0x50000));self.assertEqual(1,len(self.g.errors))
  other=self.module.new(self.g.api);self.lua.execute("api.onReset=function() error('reset error') end")
  with self.assertRaisesRegex(Exception,'reset error'):other.reset()
  self.assertTrue(other.status().halted)

class LifetimeHarness(LifecycleHarness):
 def __init__(self,image,watchdog=False):
  super().__init__(image,watchdog)
  for key in KEYS:self.lua.execute(f'function CBRPQLifetime_{key}(...) end')
  self.config=self.lua.table_from({'callbacks':self.lua.table_from({k:'CBRPQLifetime_'+k for k in KEYS})})
  self.hook=self.lua.execute(MODULE.read_text())

@unittest.skipUnless(EEEX,'optional: local EEex preprocessor')
class SpriteLifetimeDescriptorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.image=read_image()
 def test_prepare_is_inert_and_sites_avoid_existing_eeex_constructor_calls(self):
  h=LifetimeHarness(self.image);p=h.prepare()
  self.assertEqual(6,len(p.descriptors));self.assertEqual([],h.assemblies);self.assertEqual([],h.patches)
  sites={int(d.address)-BASE for _,d in p.descriptors.items()}
  self.assertTrue(sites.isdisjoint({0x1A34AA,0x3418A5,0x343D0F,0x343D30,0x343FA6}))
  self.assertEqual(0xE8,self.image[0x343114])
 def test_all_byte_guards_reject_conflicts_before_generation(self):
  h=LifetimeHarness(self.image)
  sites=[int(g[2]) for _,g in h.hook.guards.items()]+[0x598B68]
  for rva in sites:
   with self.subTest(rva=hex(rva)):
    h=LifetimeHarness(self.image);h.image[rva]^=1
    with self.assertRaisesRegex(Exception,'unsupported'):h.prepare()
    self.assertEqual([],h.patches)

class SpriteLifetimeAdapterCompositionTests(unittest.TestCase):
 def setUp(self):
  from tests.test_potion_regen_adapter import HARNESS
  self.lua=LuaRuntime(unpack_returned_tuples=True);self.lua.execute(HARNESS);self.g=self.lua.globals()
  lifetime=self.lua.execute(MODULE.read_text())
  self.lua.execute("""
   lifetimeAPI={imageBase=BASE,readPtr=api.readPtr,report=api.report,
    onRetire=function(p) adapter.onSpriteDestroy(p) end,
    onContentsReset=function(p) adapter.callbacks.clear(p+0x1A08) end,
    onReset=function() adapter.reset() end}
  """)
  self.registry=lifetime.new(self.g.lifetimeAPI);self.g.life=self.registry
  self.lua.execute('api.spriteIdentity=life.identity')
  factory=self.lua.execute((ROOT/'CBRPQRegenAdapter.lua').read_text())
  self.adapter=factory(self.g.api,self.lua.execute((ROOT/'CBRPQRegenCache.lua').read_text()),
                       self.lua.execute((ROOT/'CBRPQRegenRecovery.lua').read_text()))
  self.g.adapter=self.adapter;self.g.core=self.lua.execute((ROOT/'CBRPQCore.lua').read_text())
  self.registry.callbacks.beginData(self.g.SPRITE)
  self.g.put(self.g.SPRITE,8,self.g.BASE+0x598B68)
  self.assertTrue(self.registry.callbacks.readyData(self.g.SPRITE))
  self.record=self.g.add(0x20000,0x30000,1450)
 def test_loaded_effect_lineage_can_be_observed_before_data_constructor_returns(self):
  # Ready-before-Unmarshal, append during native loading, no final-ctor callback.
  self.assertEqual(1,self.g.commit(self.record,1900))
  self.assertEqual(451,self.g.get(0x30028,4));self.assertFalse(self.adapter.status().halted)
 def test_clear_marshal_cancels_pending_recovery_but_preserves_sprite_lifetime(self):
  same=self.lua.eval('function(a,b) return rawequal(a,b) end');old=self.registry.identity(self.g.SPRITE)
  self.g.enter();self.g.death(0x30000);self.g.commit(self.record,1900)
  self.assertTrue(self.registry.callbacks.clear(self.g.SPRITE))
  self.assertTrue(same(old,self.registry.identity(self.g.SPRITE)))
  self.assertTrue(self.g.finish());self.assertEqual(0,self.g.serviceCalls.allocate)
 def test_destructor_notifies_adapter_before_retiring_sprite_token(self):
  self.assertTrue(self.registry.callbacks.destroy(self.g.SPRITE))
  self.assertIsNone(self.registry.identity(self.g.SPRITE))
  with self.assertRaisesRegex(Exception,'sprite lifetime unavailable'):
   self.adapter.prepare(self.g.plan(self.record,1900),self.g.SPRITE)
  self.assertEqual(1450,self.record.m_duration)

if __name__=='__main__':unittest.main()
