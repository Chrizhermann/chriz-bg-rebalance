"""Local pilot packaging: real WeiDU in fake games, actual Lua compiler/loader.

Only this test substitutes expected digests, using mock.patch on the builder's
fixed profile table. No production CLI/config/environment digest override exists.
Native hook installation is doubled in startup tests; no game or DLL is run.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from lupa.luajit21 import LuaRuntime, LuaError
from tests.test_potion_uniqueness_installer import PotionGame, resources, potion, fx, spell

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('potion_trial_builder', ROOT / 'tools/build_potion_trial.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fixture_profiles():
    data = {}
    profiles = {}
    for profile in ('test-one', 'test-two'):
        data[profile] = {name: (profile + ':' + name).encode() for name in builder.PINNED_BINARIES}
        profiles[profile] = {name: (hashlib.md5(raw).hexdigest(), hashlib.sha256(raw).hexdigest())
                             for name, raw in data[profile].items()}
    return profiles, data


def pilot_resources():
    result = resources()
    result['POTN39.ITM'] = potion((fx(90, 20), fx(91, 20), fx(59, 20), fx(92, 20)))
    result['DW#PTN36.ITM'] = result['POTN36.ITM']
    return result


class TrialPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cbr-potion-package-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profiles, self.binaries = fixture_profiles()

    def bundle(self, production=False):
        output = self.root / 'bundle'
        if production:
            return builder.build(output)
        with patch.object(builder, 'PINNED_PROFILES', self.profiles):
            return builder.build(output)

    def game(self, profile='test-one', data=None):
        game = PotionGame(self.root / 'game', data or pilot_resources(), biff_only=('POTN29.ITM',))
        for name, raw in self.binaries[profile].items():
            (game.root / name).write_bytes(raw)
        (game.root / '.cbr-potion-trial').write_text('synthetic fixture only')
        bundle = self.bundle()
        for path in bundle.iterdir():
            if path.is_dir():
                shutil.copytree(path, game.root / path.name)
            else:
                shutil.copyfile(path, game.root / path.name)
        return game

    def test_production_bundle_contains_no_game_resources_or_extended_modules(self):
        bundle = self.bundle(production=True)
        manifest = json.loads((bundle / 'trial-manifest.json').read_text())
        self.assertEqual(6, len(manifest['families']))
        self.assertEqual(2, len(manifest['native_fingerprints']))
        names = {p.name for p in (bundle / builder.MOD / 'lua').iterdir()}
        self.assertEqual({name + '.lua' for name, _ in builder.MODULES.values()}, names)
        self.assertFalse(any(p.suffix.upper() in ('.ITM', '.SPL', '.EFF', '.SAV', '.GAM', '.DLL') for p in bundle.rglob('*')))
        self.assertFalse(any('Early' in p.name or 'Regen' in p.name or 'Linked' in p.name for p in bundle.rglob('*')))
        for name, expected in manifest['files'].items():
            self.assertEqual(expected, hashlib.sha256((bundle / name).read_bytes()).hexdigest())
        text = (bundle / builder.SETUP).read_text()
        self.assertNotIn('DESIGNATED 330', text)
        self.assertNotIn('DESIGNATED 331', text)

    def test_destination_must_be_new_and_not_inside_game_or_checkout(self):
        existing = self.root / 'existing';existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'NEW'):
            builder.build(existing)
        (self.root / 'chitin.key').write_bytes(b'game marker')
        with self.assertRaisesRegex(ValueError, 'game directory'):
            builder.build(self.root / 'nested')
        with self.assertRaisesRegex(ValueError, 'source checkout'):
            builder.build(ROOT / 'never-created-potion-package-test')

    def test_real_installer_preserves_every_potion_and_unrelated_file(self):
        game = self.game()
        before = game.snapshot()
        result = game.run(0, target=builder.SETUP)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        after = game.snapshot()
        self.assertEqual({'M_CBRPQ.LUA'}, set(after) - set(before))
        for name, raw in before.items():
            self.assertEqual(raw, after[name], name)
        for path, raw in game.stable.items():
            self.assertEqual(raw, path.read_bytes())
        modules = game.root / 'EEex_scripts/override'
        self.assertEqual(len(builder.MODULES), len(list(modules.iterdir())))
        self.assertIn('policy="unique"', after['M_CBRPQ.LUA'].decode())

    def test_second_policy_is_refused_without_replacing_first(self):
        game = self.game()
        first = game.run(0, target=builder.SETUP)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        before = game.snapshot()
        second = game.run(1, target=builder.SETUP)
        self.assertIn('Choose one policy', second.stdout + second.stderr)
        self.assertEqual(before, game.snapshot())
        self.assertNotIn('~1~', (game.root / 'weidu.log').read_text())

    def test_other_coherent_profile_and_genius_policy_install(self):
        game = self.game('test-two')
        result = game.run(1, target=builder.SETUP)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('policy="except_genius"', (game.override / 'M_CBRPQ.lua').read_text())

    def test_mixed_profile_rolls_back_before_any_owned_file(self):
        game = self.game()
        (game.root / 'EEex.dll').write_bytes(self.binaries['test-two']['EEex.dll'])
        before = game.snapshot()
        result = game.run(0, target=builder.SETUP)
        self.assertIn('coherent pinned', result.stdout + result.stderr)
        self.assertEqual(before, game.snapshot())
        self.assertFalse((game.root / 'EEex_scripts/override').exists())

    def test_existing_owned_namespace_is_not_overwritten(self):
        game = self.game()
        target = game.root / 'EEex_scripts/CBRPQCore.lua'
        target.parent.mkdir();target.write_bytes(b'foreign prior work')
        before = game.snapshot()
        result = game.run(0, target=builder.SETUP)
        self.assertIn('namespace already exists', result.stdout + result.stderr)
        self.assertEqual(b'foreign prior work', target.read_bytes())
        self.assertEqual(before, game.snapshot())

    def test_missing_disposable_marker_refuses_exact_matching_game(self):
        game = self.game()
        (game.root / '.cbr-potion-trial').unlink()
        before = game.snapshot()
        result = game.run(0, target=builder.SETUP)
        self.assertIn('Disposable-trial marker missing', result.stdout + result.stderr)
        self.assertEqual(before, game.snapshot())


class TrialStartupTests(unittest.TestCase):
    def setUp(self):
        self.profiles, self.binary_sets = fixture_profiles()
        with patch.object(builder, 'PINNED_PROFILES', self.profiles):
            self.files = builder._render_files()
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.g = self.lua.globals()
        self.g[b'resources'] = self.lua.table_from({name.encode(): raw for name, raw in pilot_resources().items()})
        self.g[b'binaries'] = self.lua.table_from({name.encode(): raw for name, raw in self.binary_sets['test-one'].items()})
        self.lua.execute(b'''
            BASE,CHITIN=0x140000000,0x70000
            phaseGame=0;EEex_Active=true;prepared,armed,nativeReads=0,0,0
            fetched,logs,pointers={},{},{}
            print=function(s) logs[#logs+1]=s end
            EEex_GetImageBase=function() return BASE end
            EEex_ReadPtr=function(p)
                nativeReads=nativeReads+1
                if p==BASE+0x667548 then return CHITIN end
                assert(p==CHITIN+0x1090);return phaseGame
            end
            EEex_Resource_Fetch=function(name,kind)
                local key=name..'.'..kind;fetched[#fetched+1]=key
                local raw=resources[key];if not raw then return nil end
                return {nSize=#raw,Demand=function() pointers[0x100000]=raw;return 0x100000 end}
            end
            EEex_UDToPtr=function(p) return p end
            EEex_ReadU8=function(p) return assert(pointers[0x100000]):byte(p-0x100000+1) end
            EEex_ReadU32=function(p)
                local a,b,c,d=pointers[0x100000]:byte(p-0x100000+1,p-0x100000+4)
                return a+b*256+c*65536+d*16777216
            end
            io.open=function(name,mode)
                assert(mode=='rb');local raw=binaries[name];if not raw then return nil,'missing fixture' end
                return {read=function(self,what) assert(what=='*a');return raw end,close=function() end}
            end
            function substituteLab()
                CBRPQTrialModules.lab={prepare=function(api,parts,manifest,report)
                    prepared=prepared+1;captured=manifest
                    return {runtime={status=function() return true,nil end},arm=function() armed=armed+1 end}
                end}
            end
        ''')
        def do_file(name):
            if name == getattr(self, 'missing_module', None):
                return None  # EEex protected failure has no return result.
            self.lua.execute(self.files[f'{builder.MOD}/lua/{name.decode()}.lua'])
            if name == b'CBRPQLab':
                self.g[b'substituteLab']()
            return None
        self.g[b'pythonDoFile'] = do_file
        self.lua.execute(b'EEex_DoFile=function(name) pythonDoFile(name) end')

    def run_loader(self, policy='unique'):
        self.lua.execute(self.files[f'{builder.MOD}/M_CBRPQ.lua'].replace(b'%cbr_trial_policy%', policy.encode()))

    def status(self):
        return self.g[b'CBRPQTrialStatus']()

    def test_actual_wrapped_modules_and_compiler_use_effective_bytes_and_present_aliases(self):
        self.g[b'resources'][b'POTN36.ITM'] = potion((fx(92, 27), fx(90, 33)))
        self.g[b'resources'][b'DW#PTN36.ITM'] = potion((fx(90, 33), fx(92, 27)))
        self.run_loader()
        status = self.status()
        self.assertTrue(status[b'armed']);self.assertTrue(status[b'enabled'])
        self.assertEqual(7, len(status[b'sources']))
        self.assertEqual(1, self.g[b'armed'])
        records = self.g[b'captured'][b'sources'][b'POTN36'][b'records']
        self.assertEqual({27,33}, {r[b'amount'] for r in records.values()})
        self.assertNotIn(b'POTN14.ITM', self.g[b'fetched'].values())
        self.assertNotIn(b'FOREIGN.SPL', self.g[b'fetched'].values())
        status[b'sources'][1] = b'changed snapshot'
        self.assertNotEqual(b'changed snapshot', self.status()[b'sources'][1])

    def test_genius_policy_is_forwarded_without_exempting_mind_focusing(self):
        self.run_loader('except_genius')
        manifest = self.g[b'captured']
        self.assertEqual(b'except_genius', manifest[b'policy'])
        self.assertTrue(manifest[b'families'][b'POTN29'][b'genius'])
        self.assertFalse(manifest[b'families'][b'POTN37'][b'genius'])

    def test_swallowed_module_failure_stops_before_prepare(self):
        self.missing_module = b'CBRPQCore'
        with self.assertRaisesRegex(LuaError, 'did not populate'):
            self.run_loader()
        self.assertEqual(0, self.g[b'prepared']);self.assertEqual(0, self.g[b'armed'])
        self.assertEqual(b'failed', self.status()[b'phase'])

    def test_mixed_binaries_and_too_late_startup_reject_before_prepare(self):
        self.g[b'binaries'][b'EEex.dll'] = self.binary_sets['test-two']['EEex.dll']
        with self.assertRaisesRegex(LuaError, 'changed or mixed'):
            self.run_loader()
        self.assertEqual(0, self.g[b'prepared'])
        self.assertEqual(0, self.g[b'nativeReads'])
        self.setUp();self.g[b'phaseGame'] = 0x90000
        with self.assertRaisesRegex(LuaError, 'CInfGame already exists'):
            self.run_loader()
        self.assertEqual(0, self.g[b'prepared'])

    def test_regeneration98_is_explicitly_rejected_before_lab_prepare(self):
        self.g[b'resources'][b'POTN39.ITM'] = potion((fx(98, 3, 3),))
        with self.assertRaisesRegex(LuaError, 'CBR_POTION_TRIAL_SCOPE.*regeneration98'):
            self.run_loader()
        self.assertEqual(0, self.g[b'prepared']);self.assertEqual(0, self.g[b'armed'])

    def test_linked_owned_source_is_explicitly_rejected_before_lab_prepare(self):
        self.g[b'resources'][b'POTN39.ITM'] = potion((fx(146, 0, 1, resource='TRIALCH', timing=1, duration=0),))
        self.g[b'resources'][b'TRIALCH.SPL'] = spell((fx(90, 20),))
        with self.assertRaisesRegex(LuaError, 'CBR_POTION_TRIAL_SCOPE.*linked'):
            self.run_loader()
        self.assertEqual(0, self.g[b'prepared']);self.assertEqual(0, self.g[b'armed'])


if __name__ == '__main__':
    unittest.main()
