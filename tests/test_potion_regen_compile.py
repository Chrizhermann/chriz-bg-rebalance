"""Bounded opcode98 compiler parity and native-field evidence; no game runs."""
from dataclasses import replace
import os
from pathlib import Path
import sys
import unittest

from tests.test_potion_admission_manifest import compiler, fx, potion, record_for
from tests.test_potion_admission_lua_compiler import LuaCompiler, LuaError
from tests.test_potion_linked_manifest import cast
from tests.test_potion_payload_audit import container
from tests import test_potion_regen_runtime as runtime_tests
from tests import test_potion_generated_trampoline as generated

ROOT = runtime_tests.ROOT


class RegenerationCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.port = LuaCompiler()

    def both(self, items, spells=None, policy='unique'):
        before = dict(items, **(spells or {}))
        reader = None if spells is None else spells.__getitem__
        result = compiler.build_manifest(items, policy, read_resource=reader)
        self.assertEqual(result, self.port.build(items, policy, read_resource=reader))
        self.assertEqual(before, dict(items, **(spells or {})))
        return result

    def fails(self, code, effect):
        items = {'POTN42.ITM': potion([effect])}
        with self.assertRaises(compiler.ManifestError) as caught:
            compiler.build_manifest(items)
        self.assertEqual(code, caught.exception.code)
        with self.assertRaisesRegex(LuaError, code + ':'):
            self.port.build(items)

    def test_both_native_modes_are_refresh_families_under_both_policies(self):
        for policy in ('unique', 'except_genius'):
            for mode, amount in ((2, 1), (3, 3)):
                with self.subTest(policy=policy, mode=mode):
                    result = self.both({'POTN42.ITM': potion([fx(98, amount, parameter2=mode)])}, policy=policy)
                    _, record = record_for(result, 'POTN42')
                    self.assertEqual((98, amount, mode), (record['opcode'], record['amount'], record['mode']))
                    self.assertEqual({'hp': False, 'genius': False}, result['families']['POTN42'])

    def test_raw_aliases_and_native_fields_are_preserved_not_normalized_in_keys(self):
        effects = [fx(98, 65537, parameter2=65538, power=7, resist_dispel=3,
                      probability1=73, probability2=9, save_type=8, save_bonus=-2,
                      dice_number=21, dice_size=4, resource='ABCDEFGH')]
        result = self.both({'POTN42.ITM': potion(effects, school=5, secondary=9, source_flags=0x8041)})
        _, r = record_for(result, 'POTN42')
        self.assertEqual((65537, 65538, 0, 0, 4, 21),
                         (r['amount'], r['mode'], r['diceCount'], r['diceSize'], r['minLevel'], r['maxLevel']))
        self.assertEqual((7, 3, 73, 9, 8, -2, 'ABCDEFGH', 5, 9, 0x8041),
                         (r['power'], r['flags'], r['probUpper'], r['probLower'], r['saveType'],
                          r['saveBonus'], r['resource'], r['school'], r['secondary'], r['sourceFlags']))
        ordinary = self.both({'POTN42.ITM': potion([fx(98, 1, parameter2=2)])})
        alias = self.both({'POTN42.ITM': potion([fx(98, 65537, parameter2=65538)])})
        self.assertNotEqual(record_for(ordinary, 'POTN42')[0], record_for(alias, 'POTN42')[0])

    def test_native_adverse_or_zero_heal_remains_unowned_but_bad_intervals_diagnose(self):
        for raw in (0, -1, 32768, 65535, 65536):
            with self.subTest(heal=raw):
                result = self.both({'POTN42.ITM': potion([fx(98, raw, parameter2=2)])})
                self.assertFalse(result['sources']['POTN42']['abilities']['0']['effects']['0'])
                self.assertEqual({}, result['sources']['POTN42']['keys'])
            with self.subTest(interval=raw):
                self.fails('AMOUNT_CAPABILITY', fx(98, raw, parameter2=3))
        for raw in (1, 32767, 65537, -65535):
            for mode in (2, 3):
                with self.subTest(positive_alias=raw, mode=mode):
                    result = self.both({'POTN42.ITM': potion([fx(98, raw, parameter2=mode + 65536)])})
                    self.assertEqual(raw, record_for(result, 'POTN42')[1]['amount'])

    def test_unproved_modes_special_timing_and_native_countdown_width_fail_explicitly(self):
        for mode in (0, 1, 4, 5, 65536, 0xFFFFFFFF):
            self.fails('OPCODE_CAPABILITY', fx(98, 3, parameter2=mode))
        self.fails('SPECIAL_CAPABILITY', fx(98, 1, parameter2=2, special=1))
        self.fails('TIMING_CAPABILITY', replace(fx(98, 3, parameter2=3), timing=3))
        self.fails('DURATION_CAPABILITY', replace(fx(98, 1, parameter2=2), timing=10, duration=0x80000000))
        self.fails('DURATION_CAPABILITY', replace(fx(98, 3, parameter2=3), duration=0x08888889))
        self.fails('FLAGS_CAPABILITY', fx(98, 1, parameter2=2, resist_dispel=4))
        self.fails('LEVEL_CAPABILITY', fx(98, 1, parameter2=2, dice_size=65536))
        # UsesDice=false: legitimate level fields and Decode's -1 sentinel stay supported.
        for timing, duration in ((0, 0x08888888), (10, 0x7FFFFFFF)):
            r = self.both({'POTN42.ITM': potion([replace(fx(98, 1, parameter2=2,
                dice_number=99, dice_size=-1), timing=timing, duration=duration)])})
            self.assertEqual((0, 99), (record_for(r, 'POTN42')[1]['minLevel'], record_for(r, 'POTN42')[1]['maxLevel']))

    def test_direct_layout_variation_and_scs_alias_keep_unrelated_records_and_quota(self):
        heal, regen = replace(fx(17, 3), timing=1), fx(98, 3, parameter2=3)
        items = {'POTN42.ITM': container(groups=[[heal, regen, fx(139, 7), regen]], effects_first=True),
                 'DW#PTN42.ITM': potion([regen, regen, heal])}
        result = self.both(items)
        base, alias = (result['sources'][n] for n in ('POTN42', 'DW#PTN42'))
        self.assertEqual('POTN42', alias['family'])
        self.assertEqual(base['keys'], alias['keys'])
        self.assertEqual([2], list(base['abilities']['0']['quotas'].values()))
        self.assertFalse(base['abilities']['0']['effects']['0'])
        self.assertFalse(base['abilities']['0']['effects']['2'])

    def test_original_mode1_linked_graph_retains_child_source_and_header_variations(self):
        for mode in (2, 3):
            for policy in ('unique', 'except_genius'):
                child = container('SPL', groups=[[fx(139, 1), fx(98, 3, parameter2=mode)],
                                                [fx(98, 3, parameter2=mode), fx(139, 2)]], effects_first=True)
                result = self.both({'POTN42.ITM': potion([cast('REGEN')])}, {'REGEN.SPL': child}, policy)
                source = result['sources']['POTN42']
                key = next(iter(source['keys']))
                self.assertEqual((1, {'REGEN': True}),
                                 (source['records'][key]['nativeSourceType'], source['records'][key]['nativeSources']))
                self.assertEqual({key: 1}, source['abilities']['0']['quotas'])
                self.assertEqual(key, source['calls']['REGEN']['abilities']['0']['effects']['1'])
                self.assertEqual(key, source['calls']['REGEN']['abilities']['1']['effects']['0'])

    def test_hp_sensitive_mixed_family_keeps_ignore_repeat_policy(self):
        for hp in (fx(18, 10), fx(10, 2)):
            result = self.both({'POTN42.ITM': potion([hp, fx(98, 1, parameter2=2)])})
            self.assertTrue(result['families']['POTN42']['hp'])
            self.assertEqual(2, len(result['sources']['POTN42']['keys']))

    def test_compiled_raw_alias_flows_through_real_bridge_runtime_and_recovery(self):
        # Actual compiler output replaces the earlier hand-built Runtime fixture
        # registry. Native Apply remains its explicit normalized-cache double.
        f = runtime_tests.RegenerationRuntimeTests(); f.setUp()
        manifest = self.both({'POTN42.ITM': potion([fx(98, 65537, parameter2=65538)])})
        _, fields = record_for(manifest, 'POTN42')
        f.fixture.fields = fields
        f.g.reader = f.lua.execute((ROOT / 'CBRPQNative.lua').read_text())(f.g, f.fixture.table(manifest))
        f.bridge = f.fixture.module.new(f.g, f.g.reader, f.g.lifetime, f.fixture.parts,
            f.lua.eval('function(reason) if runtime then runtime.disable(reason) end end'))
        f.fixture.bridge = f.bridge; f.g.bridge = f.bridge; f.g.adapter = f.bridge
        f.bridge.prepareServices('CBRPQAliasRegen')
        f.runtime = f.lua.execute((ROOT / 'CBRPQRuntime.lua').read_text())(
            f.g.core, f.lua.execute((ROOT / 'CBRPQMessages.lua').read_text()), f.g.reader,
            f.fixture.table(manifest), f.lua.eval('function(e) errors[#errors+1]=e end'),
            f.lua.table_from({'regeneration': f.bridge, 'persistence': f.g.persistence}))
        f.g.runtime = f.runtime
        old = f.active(); before = f.image(old.pointer)
        f.natural_death(); queued = f.queue()
        self.assertTrue(f.admit(queued)); f.finish(queued)
        self.assertEqual((65537, 65538), (f.g.get(old.pointer + 0x1C, 4), f.g.get(old.pointer + 0x20, 4)))
        after = f.image(old.pointer)
        self.assertEqual(before[:0x28] + before[0x2C:], after[:0x28] + after[0x2C:])
        self.assertEqual((2, 1, 1), (f.g.get(0x200020, 2), f.g.get(0x200018, 2), f.g.get(0x200024, 2)))
        self.assertEqual((True, None), f.runtime.status())


CAPTURE_ROOTS = [Path(p) for p in os.environ.get('CBR_POTION_REGEN_ROOTS', '').split(os.pathsep) if p]


@unittest.skipUnless(CAPTURE_ROOTS, 'optional: explicit read-only POTN42 roots')
class CapturedRegenerationCompilerTests(unittest.TestCase):
    def test_actual_potn42_only_matches_both_compilers_without_resource_writes(self):
        port = LuaCompiler()
        for root in CAPTURE_ROOTS:
            store = compiler.audit.ResourceStore(root, game=(root / 'chitin.key').is_file())
            inputs = {'POTN42.ITM': store.read('POTN42.ITM')}
            if 'DW#PTN42.ITM' in store.names(): inputs['DW#PTN42.ITM'] = store.read('DW#PTN42.ITM')
            for policy in ('unique', 'except_genius'):
                with self.subTest(root=str(root), policy=policy):
                    try:
                        result = compiler.build_manifest(inputs, policy, read_resource=store.read)
                    except compiler.ManifestError as error:
                        # Captured IRR has an independent native self206 guard.
                        # Keep that concrete unsupported graph diagnostic; this
                        # bounded98 work must not weaken/remove its protection.
                        self.assertEqual('OPCODE_CAPABILITY', error.code)
                        self.assertIn('finite opcode 206', str(error))
                        with self.assertRaisesRegex(LuaError, error.code + ':'):
                            port.build(inputs, policy, read_resource=store.read)
                        graph = compiler.audit.parse_resource('POTN42.SPL', store.read('POTN42.SPL'))
                        effects = [e for part in graph['slices'] for e in part['effects']]
                        self.assertTrue(any(e['opcode'] == 206 for e in effects))
                        regen = [e for e in effects if e['opcode'] == 98]
                        self.assertTrue(regen)
                        self.assertTrue(all(compiler._owned(e, 'captured regeneration', validate_target=False) for e in regen))
                        continue
                    self.assertEqual(result, port.build(inputs, policy, read_resource=store.read))
                    regen = [r for r in result['sources']['POTN42']['records'].values() if r['opcode'] == 98]
                    self.assertEqual(1, len(regen))
                    self.assertIn(regen[0]['mode'] % 65536, (2, 3))
                    self.assertFalse(result['families']['POTN42']['hp'])
                    for name, data in inputs.items(): self.assertEqual(data, store.read(name))


@unittest.skipUnless(generated.EEEX and generated.LIBS, 'optional: pinned exe/Unicorn paths')
class NativeRegenerationOperandEvidenceTests(unittest.TestCase):
    def test_copied_apply_low_word_aliases_and_native_negative_heal(self):
        sys.path.insert(0, str(ROOT))
        import probe_native_regeneration as probe
        import unicorn
        from unicorn import x86_const
        from tests.test_potion_transport_preprocessor import read_image
        image = bytes(read_image())
        self.assertFalse(probe.lifecycle(image)['usesDice'])
        for mode, amount, expected_interval, expected_heal in (
            (2, 1, 1, 1), (65538, 65537, 1, 1), (65538, -65535, 1, 1),
            (2, -1, 1, 65535), (3, 3, 3, 1), (65539, 65539, 3, 1),
            (3, 32767, 32767, 1), (3, 32768, 32768, 1)):
            with self.subTest(mode=mode, amount=amount):
                p = probe.RegenMachine(image, unicorn, x86_const, mode, amount & 0xFFFFFFFF)
                p.rebuild()
                cache = p.cache()
                self.assertEqual((mode % 65536, expected_interval, expected_heal),
                                 (p.get(cache + 0x20, 'H'), p.get(cache + 0x18, 'H'), p.get(cache + 0x24, 'H')))
                if mode == 2 and amount == -1:
                    for tick in range(1001, 1016): p.tick(tick)
                    self.assertEqual(-1, p.heals[-1]['amount'])
                    self.assertEqual(9, p.get(probe.native.ACTOR + 0x57C, 'h'))


if __name__ == '__main__': unittest.main()
