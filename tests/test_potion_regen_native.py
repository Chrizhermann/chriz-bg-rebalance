"""Inert bridge + real reader/adapter/cache/recovery/lifetime, offline only.

Native memory, allocation and exposure are explicit doubles. Optional tests
preprocess genuine EEex Lua, then assemble/execute the generated service wrapper
in Unicorn with Lua/Windows services substituted. No game/DLL is executed.
"""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest

from lupa.luajit21 import LuaRuntime
from tests import test_potion_native_reader as reader_tests
from tests import test_potion_regen_adapter as adapter_tests
from tests import test_potion_hook_preprocessor as preprocess
from tests import test_potion_generated_trampoline as generated

ROOT = Path(__file__).resolve().parents[1] / 'research/prototypes/potion-admission'

BRIDGE_HARNESS = r"""
captured=nil; conversions={}; jit={}; exposures={}; serviceExecutions=0
signatures={}; spriteObjects={}; failFree=false; failExpose=false; failJIT=false
local nativeServices=api.services
EEex_GetImageBase=function() return BASE end
EEex_ReadPtr=function(p) return get(p,8) end
EEex_ReadU32=function(p) return get(p,4) end
EEex_Read32=function(p) local v=get(p,4);return v>=0x80000000 and v-0x100000000 or v end
EEex_ReadU16=function(p) return get(p,2) end
EEex_ReadU8=function(p) return assert(signatures[p] or mem[p],'invalid read '..p) end
EEex_WritePtr=function(p,v) put(p,8,v) end
EEex_Write32=function(p,v) put(p,4,v) end
EEex_Write16=function(p,v) put(p,2,v) end
EEex_Write8=function(p,v) put(p,1,v) end
EEex_UDToPtr=function(o) return o.pointer end
EEex_Utility_IterateCPtrList=function(list,cb) for _,e in ipairs(list) do cb(e) end end
EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_worldTime={m_gameTime=1449}}}}
function freshEffect(p)
 return setmetatable({pointer=p},{__index=function(_,k) if k=='m_duration' then return get(p+0x28,4) end end,
  __newindex=function(_,k,v) assert(k=='m_duration');put(p+0x28,4,v) end})
end
EEex_PtrToUD=function(p,kind)
 conversions[#conversions+1]={pointer=p,kind=kind}
 if kind=='CGameSprite' then return spriteObjects[p] end
 assert(kind=='CGameEffect');assert(mem[p]~=nil,'freed original conversion');return freshEffect(p)
end
EEex_Malloc=function(n) if nullScratch then return 0 end;return allocScratch(n) end
EEex_Free=function(p) if failFree then error('scratch free failure') end;freeScratch(p) end
EEex_JITNear=function(t)
 jit[#jit+1]=t[1];if failJIT then error('JIT failure') end;return BASE+0x3600000+#jit*0x1000
end
EEex_ExposeToLua=function(address,name)
 exposures[#exposures+1]={address=address,name=name}
 if failExpose then error('exposure failure') end
 local kind=name:match('_([^_]+)$')
 _G[name]=function(request) serviceExecutions=serviceExecutions+1;return nativeServices[kind](request) end
end
spriteObjects[SPRITE]={pointer=SPRITE,m_timedEffectList={}}
zero(SPRITE,8);put(SPRITE,8,BASE+0x598B68)
function currentEffect(p) local e=freshEffect(p);table.insert(spriteObjects[SPRITE].m_timedEffectList,e);return e end
function removeEffect(p)
 local l=spriteObjects[SPRITE].m_timedEffectList
 for i=#l,1,-1 do if l[i].pointer==p then table.remove(l,i) end end
end
function newPlan(e,expiry)
 local r=reader.identify(e,nil,false)
 return {allow=false,state={},refresh={{record=e,identity=r.identity,oldExpiry=e.m_duration,expiry=expiry}}}
end
function refresh(e,expiry)
 local p=newPlan(e,expiry);local t=bridge.prepare(p,spriteObjects[SPRITE]);core.commit(p);return t.commit()
end
function newLifetime()
 return lifetimeModule.new({imageBase=BASE,readPtr=EEex_ReadPtr,report=function(e) errors[#errors+1]=e end,
  onRetire=function(p) if bridge then bridge.onSpriteDestroy(p) end end,
  onContentsReset=function(p) if bridge then bridge.onSpriteDestroy(p) end end,
  onReset=function() if bridge then bridge.reset() end end})
end
function seedSprite() assert(lifetime.callbacks.beginData(SPRITE));assert(lifetime.callbacks.readyData(SPRITE)) end
"""


class RegenerationNativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(adapter_tests.HARNESS)
        self.lua.execute(BRIDGE_HARNESS)
        self.g = self.lua.globals()
        self.module = self.lua.execute((ROOT / 'CBRPQRegenNative.lua').read_text())
        self.services = self.lua.execute((ROOT / 'CBRPQRegenServices.lua').read_text())
        for rva, text in self.services.expected.items():
            for i, byte in enumerate(bytes.fromhex(text)):
                self.g.signatures[self.g.BASE + rva + i] = byte
        self.fields = reader_tests.descriptor(opcode=98, amount=1, mode=2,
            timing=0, duration=60, flags=0, sourceFlags=0, saveType=0,
            saveBonus=0, school=0, secondary=0, special=0, power=0)
        self.g.reader = self.lua.execute((ROOT / 'CBRPQNative.lua').read_text())(
            self.g, self.table(reader_tests.manifest({'r': self.fields}, 'POTN42')))
        self.g.lifetimeModule = self.lua.execute((ROOT / 'CBRPQSpriteLifetime.lua').read_text())
        self.g.lifetime = self.g.newLifetime()
        self.g.realAdapter = self.lua.execute((ROOT / 'CBRPQRegenAdapter.lua').read_text())
        self.parts = self.lua.table_from(dict(
            adapter=self.lua.eval('function(api,c,r) captured=api;return realAdapter(api,c,r) end'),
            cache=self.lua.execute((ROOT / 'CBRPQRegenCache.lua').read_text()),
            recovery=self.lua.execute((ROOT / 'CBRPQRegenRecovery.lua').read_text()),
            services=self.services))
        self.bridge = self.module.new(self.g, self.g.reader, self.g.lifetime, self.parts,
            self.lua.eval('function(e) errors[#errors+1]=e end'))
        self.g.bridge = self.bridge
        self.g.adapter = self.bridge # Native-service doubles route lifecycle here.
        self.g.core = self.lua.execute((ROOT / 'CBRPQCore.lua').read_text())

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k: self.table(v) for k, v in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(v) for v in value])
        return value

    def effect(self, p=0x20000, active=True):
        self.g.zero(p, 0x180)
        for name, (offset, fmt) in reader_tests.FIELDS.items():
            self.g.put(p + offset, struct.calcsize(fmt), self.fields[name] % (1 << (8 * struct.calcsize(fmt))))
        self.g.putBytes(p + 0x94, 'POTN42\0\0')
        self.g.put(p + 0x90, 4, 2)
        self.g.put(p + 0xC8, 4, 10)
        if active:
            self.g.put(p + 0x24, 4, 4096)
            self.g.put(p + 0x28, 4, 1450)
            return self.g.currentEffect(p)
        return self.g.freshEffect(p)

    def ready(self):
        self.g.seedSprite()
        self.bridge.prepareServices('CBRPQTestRegen')

    def add_cache(self, p=0x20000, cache=0x30000):
        self.g.makeCache(cache, 1)
        node = self.g.insertRaw(self.g.LIST, cache, 0)
        self.bridge.callbacks.append(self.g.LIST, cache, node, self.g.BASE + 0x1BEDE5)
        return self.bridge.callbacks.appendOwned(p, cache, self.g.SPRITE)

    def test_factory_and_validation_do_not_jit_allocate_bind_or_execute_services(self):
        self.assertEqual(0, len(self.g.jit))
        self.assertEqual(0, len(self.g.exposures))
        self.assertEqual(0, self.g.count(self.g.scratch))
        self.assertEqual(0, self.g.serviceExecutions)
        v = self.bridge.validateServices('CBRPQTestRegen')
        self.assertEqual(64, v.requestSize)
        self.assertEqual(0, len(self.g.jit))
        self.assertFalse(self.bridge.status().servicesPrepared)

    def test_preparation_captures_three_explicit_functions_and_cleans_only_own_names(self):
        self.g.Unrelated = 'preserve'
        self.assertTrue(self.bridge.prepareServices('CBRPQTestRegen'))
        self.assertEqual(6, len(self.g.jit))
        self.assertEqual(3, len(self.g.exposures))
        self.assertEqual(0, self.g.serviceExecutions)
        for name in ('allocate', 'insert', 'dispose'):
            self.assertIsNone(self.g['CBRPQTestRegen_' + name])
        self.assertEqual('preserve', self.g.Unrelated)
        with self.assertRaisesRegex(Exception, 'already attempted'):
            self.bridge.prepareServices('Other')

    def test_collision_or_signature_failure_occurs_before_allocation(self):
        self.g.CBRPQTestRegen_insert = 'foreign'
        with self.assertRaisesRegex(Exception, 'namespace occupied'):
            self.bridge.prepareServices('CBRPQTestRegen')
        self.assertEqual('foreign', self.g.CBRPQTestRegen_insert)
        self.g.CBRPQTestRegen_insert = None
        self.g.signatures[self.g.BASE + 0x407890] = 0
        with self.assertRaisesRegex(Exception, 'unsupported/patched'):
            self.bridge.prepareServices('CBRPQTestRegen')
        self.assertEqual(0, len(self.g.jit))
        self.assertFalse(self.bridge.status().servicePreparationAttempted)

    def test_jit_failure_never_publishes_partial_services_or_retries(self):
        self.g.failJIT = True
        with self.assertRaisesRegex(Exception, 'JIT failure'):
            self.bridge.prepareServices('CBRPQTestRegen')
        self.assertTrue(self.bridge.status().halted)
        self.assertFalse(self.bridge.status().servicesPrepared)
        with self.assertRaises(Exception): self.bridge.prepareServices('Other')
        self.assertEqual(1, len(self.g.jit))

    def test_partial_exposure_failure_cleans_known_functions_without_deleting_foreign_replacement(self):
        self.lua.execute('''
            local expose=EEex_ExposeToLua
            EEex_ExposeToLua=function(address,name)
                if name:match('_insert$') then
                    CBRPQTestRegen_allocate='foreign replacement'
                    error('second exposure failed')
                end
                expose(address,name)
            end
        ''')
        with self.assertRaisesRegex(Exception, 'binding was replaced'):
            self.bridge.prepareServices('CBRPQTestRegen')
        self.assertEqual('foreign replacement', self.g.CBRPQTestRegen_allocate)
        self.assertIsNone(self.g.CBRPQTestRegen_insert)
        self.assertFalse(self.bridge.status().servicesPrepared)
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertFalse(self.bridge.callbacks.updateEnter(0xDEAD, 0xBEEF, 1, 0xCAFE))

    def test_failed_exposure_does_not_leave_prior_successful_binding(self):
        self.lua.execute('''
            local expose=EEex_ExposeToLua
            EEex_ExposeToLua=function(address,name)
                if name:match('_insert$') then error('second exposure failed') end
                expose(address,name)
            end
        ''')
        with self.assertRaisesRegex(Exception, 'second exposure failed'):
            self.bridge.prepareServices('CBRPQTestRegen')
        self.assertIsNone(self.g.CBRPQTestRegen_allocate)
        self.assertFalse(self.bridge.status().servicesPrepared)

    def test_unknown_sprite_append_does_not_convert_or_read_original(self):
        self.assertFalse(self.bridge.callbacks.appendOwned(0xDEAD, 0xBEEF, self.g.SPRITE))
        self.assertEqual(0, len(self.g.conversions))
        self.assertIsNone(self.g.captured.original(0xDEAD))

    def test_first_apply_append_before_timed_list_insertion_uses_scoped_live_proof(self):
        self.ready()
        effect = self.effect(active=False)
        self.assertTrue(self.add_cache())
        self.assertEqual(1, len(self.g.conversions))
        self.assertEqual('CGameEffect', self.g.conversions[1].kind)
        # The callback scope ended: retained pointer alone is not authority.
        self.assertIsNone(self.g.captured.original(effect.pointer))
        self.g.currentEffect(effect.pointer)
        self.g.put(effect.pointer + 0x24, 4, 4096)
        self.g.put(effect.pointer + 0x28, 4, 1450)
        self.assertEqual(98, self.g.captured.original(effect.pointer).opcode)

    def test_append_failure_closes_scope_before_native_destruction_continues(self):
        self.ready(); effect=self.effect(active=False)
        self.g.put(effect.pointer+0xC8,4,77) # Violates original potion level proof.
        self.assertFalse(self.add_cache())
        self.assertTrue(self.bridge.status().halted)
        before=len(self.g.conversions)
        self.lua.execute('for i=0,0x17F do mem[0x20000+i]=nil end')
        self.assertIsNone(self.g.captured.original(effect.pointer))
        self.assertEqual(before,len(self.g.conversions))

    def test_live_refresh_uses_real_reader_tokens_and_only_changes_countdown_expiry(self):
        self.ready(); effect = self.effect(); self.assertTrue(self.add_cache())
        self.assertEqual(1, self.g.refresh(effect, 1900))
        self.assertEqual(1900, effect.m_duration)
        self.assertEqual(451, self.g.get(0x30028, 4))
        self.assertEqual(2, self.g.get(0x3001A, 2))
        self.assertEqual(0, self.g.serviceExecutions)
        self.assertTrue(self.lua.eval('function(a,b) return a==b end')(
            self.g.captured.original(effect.pointer).identity,
            self.g.reader.identify(effect, None, False).identity))

    def test_freed_effect_is_not_converted_or_dereferenced_and_reuse_has_new_token(self):
        self.ready(); effect = self.effect(); self.add_cache()
        old = self.g.captured.original(effect.pointer).identity
        self.g.removeEffect(effect.pointer)
        self.lua.execute('for i=0,0x17F do mem[0x20000+i]=nil end')
        before = len(self.g.conversions)
        self.assertIsNone(self.g.captured.original(effect.pointer))
        self.assertTrue(all(self.g.conversions[i].kind == 'CGameSprite'
                            for i in range(before + 1, len(self.g.conversions) + 1)))
        self.bridge.onOriginalDestroy(effect.pointer)
        self.g.reader.retire(effect.pointer)
        self.effect()
        self.assertIsNone(self.g.captured.original(effect.pointer))
        self.assertFalse(self.g.captured.isCurrentOriginal(self.g.SPRITE, effect.pointer, old))

    def test_current_membership_rejects_different_actor_and_different_lifetime(self):
        self.ready(); effect = self.effect(); self.add_cache()
        identity = self.g.captured.original(effect.pointer).identity
        self.assertFalse(self.g.captured.isCurrentOriginal(0xBAD, effect.pointer, identity))
        self.assertFalse(self.g.captured.isCurrentOriginal(self.g.SPRITE, effect.pointer, self.lua.table()))
        self.g.put(effect.pointer + 0x1C, 4, 99)
        self.assertIsNone(self.g.captured.original(effect.pointer))

    def test_sprite_retirement_or_reset_invalidates_association_without_effect_reads(self):
        self.ready(); effect = self.effect(); self.add_cache()
        old = self.g.lifetime.identity(self.g.SPRITE)
        self.g.lifetime.reset()
        self.assertIsNone(self.g.captured.original(effect.pointer))
        self.assertFalse(self.lua.eval('function(a,b) return a==b end')(old, self.g.lifetime.identity(self.g.SPRITE)))
        self.assertTrue(self.g.lifetime.callbacks.destroy(self.g.SPRITE))
        self.assertIsNone(self.g.captured.original(effect.pointer))

    def test_missing_cache_recovery_uses_bound_services_and_owned_scratch(self):
        self.ready(); effect = self.effect(); self.add_cache()
        self.g.enter(); self.g.death(0x30000); self.g.finish()
        self.assertEqual(1, self.g.refresh(effect, 1900))
        self.assertEqual(2, self.g.serviceExecutions) # allocate + insert; no Apply98.
        self.assertEqual(0, self.g.count(self.g.scratch))
        self.assertEqual(0, len(self.bridge.status().scratch))
        self.assertEqual(450, self.g.get(0x200028, 4))

    def test_prepare_requires_explicit_service_preparation_before_core_write(self):
        self.g.seedSprite(); effect = self.effect(); self.add_cache()
        with self.assertRaisesRegex(Exception, 'not explicitly prepared'):
            self.g.refresh(effect, 1900)
        self.assertEqual(1450, effect.m_duration)

    def test_scratch_binary_io_exact_widths_and_failed_free_retains_ownership(self):
        cap = self.g.captured
        p = cap.allocScratch(64)
        # Keep arbitrary binary strings wholly within Lua (Python text is UTF8).
        self.lua.eval('function(p) local b=string.char(0,255,0,128);captured.writeBytes(p,b);assert(captured.readBytes(p,4)==b) end')(p)
        cap.writePtr(p + 8, self.g.BASE)
        cap.writeU16(p + 16, 65535)
        cap.writeU32(p + 20, 0xFFFFFFFF)
        self.assertEqual(self.g.BASE, cap.readPtr(p + 8))
        self.assertEqual(65535, cap.readU16(p + 16))
        self.assertEqual(-1, cap.readI32(p + 20))
        with self.assertRaisesRegex(Exception, 'outside owned scratch'): cap.writeBytes(p + 63, 'xx')
        with self.assertRaisesRegex(Exception, 'unowned'): cap.freeScratch(p + 1)
        self.g.failFree = True
        with self.assertRaisesRegex(Exception, 'scratch free failure'): cap.freeScratch(p)
        self.assertEqual(p, self.bridge.status().scratch[1].pointer)
        with self.assertRaisesRegex(Exception, 'owned scratch'): self.bridge.reset()
        self.g.failFree = False; cap.freeScratch(p)
        self.assertEqual(0, len(self.bridge.status().scratch))

    def test_null_scratch_diagnoses_without_publishing_fake_ownership(self):
        self.g.nullScratch = True
        with self.assertRaisesRegex(Exception, 'invalid pointer'): self.g.captured.allocScratch(64)
        self.assertEqual(0, len(self.bridge.status().scratch))

    def test_services_reject_unowned_requests_before_entering_native_call(self):
        self.ready()
        with self.assertRaisesRegex(Exception, 'not owned 64-byte'):
            self.g.captured.services.allocate(0xBAD)
        self.assertEqual(0, self.g.serviceExecutions)


@unittest.skipUnless(preprocess.EEEX, 'optional: set EEEX_LUA_DIR to pinned scripts')
class RegenerationNativePreprocessorTests(unittest.TestCase):
    def test_bridge_prepares_real_services_and_wrappers_with_actual_eeex_preprocessor(self):
        fixture = RegenerationNativeBridgeTests(); fixture.setUp()
        # Preprocess generated output in a separate real EEex Lua state. The
        # bridge's explicit JIT/Expose API remains a recording-only substitute.
        h = preprocess.PreprocessorHarness()
        h.lua.globals().EEex_DefineAssemblyLabel('Hardcoded_lua_tointegerx', 0x180010100)
        h.lua.globals().EEex_DefineAssemblyLabel('Hardcoded_lua_pushinteger', 0x180010200)
        fixture.bridge.prepareServices('CBRPQTestRegen')
        texts = []
        for _, text in fixture.g.jit.items():
            expanded, _ = h.lua.globals().EEex_PreprocessAssembly(h.lua.table_from([text]))
            self.assertNotIn('#L(', expanded)
            self.assertNotIn('call rax\n', expanded)
            texts.append(expanded)
        self.assertEqual(6, len(texts))
        self.assertTrue(all('ret' in text for text in texts))


@unittest.skipUnless(preprocess.EEEX and generated.LIBS and generated.ML64,
                     'optional: EEex, ML64 and Unicorn paths')
class RegenerationNativeGeneratedTests(unittest.TestCase):
    def test_actual_preprocessed_and_assembled_service_wrappers_execute_the_native_abi(self):
        # Reuse the bounded copied-instruction service machine; its Windows
        # heap/Lua services remain explicit doubles. The code supplied here is
        # the bridge's REAL prepared output after the pinned EEex preprocessor.
        sys.path.insert(0, str(ROOT))
        import probe_native_regeneration_services as services_probe
        import unicorn
        from unicorn import x86_const
        from tests.test_potion_transport_preprocessor import read_image
        fixture = RegenerationNativeBridgeTests(); fixture.setUp()
        fixture.bridge.prepareServices('CBRPQTestRegen')
        h = preprocess.PreprocessorHarness()
        h.lua.globals().EEex_DefineAssemblyLabel('Hardcoded_lua_tointegerx', services_probe.LUA_NUMBER)
        h.lua.globals().EEex_DefineAssemblyLabel('Hardcoded_lua_pushinteger', services_probe.LUA_PUSH)
        directory = Path(tempfile.mkdtemp(prefix='cbr-regen-native-bridge-'))
        code = {}
        for i, name in enumerate(('allocate', 'lua_allocate', 'insert', 'lua_insert', 'dispose', 'lua_dispose'), 1):
            text, _ = h.lua.globals().EEex_PreprocessAssembly(h.lua.table_from([fixture.g.jit[i]]))
            address = int(fixture.g.BASE + 0x3600000 + i * 0x1000)
            code[name] = address, generated.assemble(text, address, directory, name)
        text = fixture.services.generate(fixture.g.BASE).initialize
        code['initialize'] = services_probe.SERVICE, generated.assemble(
            text, services_probe.SERVICE, directory, 'initialize')
        image = bytes(read_image())

        class StrictLuaMachine(services_probe.ServiceMachine):
            def on_code(self, uc, address, size, data):
                if address in (services_probe.LUA_NUMBER, services_probe.LUA_PUSH):
                    self.assert_lua_call(address)
                    return
                super().on_code(uc, address, size, data)

            def assert_lua_call(self, address):
                if self.reg_read('RCX') != services_probe.REQUEST:
                    raise AssertionError('lua_State did not survive native service call')
                if self.reg_read('RSP') % 16 != 8:
                    raise AssertionError('unaligned Lua C API call')
                if address == services_probe.LUA_NUMBER:
                    if self.reg_read('RDX') != 1 or self.reg_read('R8') != 0:
                        raise AssertionError('incorrect lua_tointegerx ABI')
                else:
                    self.lua_status = self.reg_read('RDX')
                # Lua callees may clobber every volatile GPR; the wrapper must
                # preserve the state/request in nonvolatile RBX, not lucky RCX.
                for index, reg in enumerate(('RCX', 'RDX', 'R8', 'R9', 'R10', 'R11')):
                    self.reg_write(reg, 0x12340000 + index)
                self.ret(services_probe.REQUEST if address == services_probe.LUA_NUMBER else 0xCAFEBABE)

        for mode in (2, 3):
            with self.subTest(mode=mode):
                machine = StrictLuaMachine(image, unicorn, x86_const, code)
                machine.snapshot(mode=mode)
                self.assertEqual(1, machine.call('lua_allocate'))
                self.assertEqual(0, machine.lua_status)
                self.assertEqual(1, machine.call('lua_insert'))
                self.assertEqual(0, machine.lua_status)
                self.assertEqual(1, len(machine.entries()))
                # Native list now owns allocations. Never dispose adopted data.
                machine.run(0x1F8990, services_probe.LIST)
                self.assertFalse(machine.live)
        machine = StrictLuaMachine(image, unicorn, x86_const, code)
        machine.snapshot(); machine.call('lua_allocate')
        self.assertEqual(1, machine.call('lua_dispose'))
        self.assertEqual(0, machine.lua_status)
        self.assertFalse(machine.live)
        machine = StrictLuaMachine(image, unicorn, x86_const, code)
        machine.snapshot(); machine.fail_at = 1
        self.assertEqual(1, machine.call('lua_allocate'))
        self.assertEqual(2, machine.lua_status)
        self.assertFalse(machine.live)


if __name__ == '__main__': unittest.main()
