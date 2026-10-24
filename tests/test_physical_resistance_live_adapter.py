"""Test the private tail adapter without touching a real installation."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_physical_resistance_installer import ResistanceGame, ROOT, WEIDU, tree

# The runtime component 0 deployed on 2026-10-06 (identical to v0.8.3).
DEPLOYED_RUNTIME = ROOT / 'tests/fixtures/physical_resistance/M_CBRRES-v0.8.3.lua'
CURRENT_RUNTIME = ROOT / 'chriz-bg-rebalance/lua/M_CBRRES.lua'


def stage(root: Path, runtime: Path = CURRENT_RUNTIME) -> Path:
    destination = root / 'CBR_PHYSICAL_CAP'
    shutil.copytree(ROOT / 'live-patch/CBR_PHYSICAL_CAP', destination)
    (destination / 'lib').mkdir()
    (destination / 'lua').mkdir()
    for name in ('tempus_holy_power.tpa', 'tempus_spec_apr_eeex.tpa', 'physical_resistance.tpa'):
        shutil.copy2(ROOT / 'chriz-bg-rebalance/lib' / name, destination / 'lib' / name)
    shutil.copy2(runtime, destination / 'lua/M_CBRRES.lua')
    return destination


def install(game: ResistanceGame, component: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WEIDU), 'CBR_PHYSICAL_CAP/setup-cbr_physical_cap.tp2',
         '--game', str(game.root), '--language', '0', '--use-lang', 'en_US',
         '--no-exit-pause', '--force-install-list', component],
        cwd=game.root, capture_output=True, text=True, timeout=90,
    )


def stamped(runtime: Path, state: int) -> str:
    text = runtime.read_text(encoding='ascii')
    return text.replace('%CBR_RES_CAP%', '90').replace('%CBR_RES_STATE%', str(state))


def text(payload: bytes) -> str:
    # Staged files keep the checkout's line endings; compare content only.
    return payload.decode('ascii').replace('\r\n', '\n')


class LiveAdapterTests(unittest.TestCase):
    def games(self, *names: str) -> list:
        temporary = tempfile.TemporaryDirectory(prefix='cbr-private-cap-')
        self.addCleanup(temporary.cleanup)
        return [ResistanceGame(Path(temporary.name) / name) for name in names]

    def assert_stable(self, game: ResistanceGame) -> None:
        for path, digest in game.stable.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest, str(path))

    def assert_installed(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SUCCESSFULLY INSTALLED', result.stdout)

    def test_private_tail_matches_public_component(self):
        public, private = self.games('public', 'private')
        stage(private.root)
        result = public.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_installed(install(private, '0'))
        self.assertEqual(tree(private.override), tree(public.override))
        self.assert_stable(private)

    def test_runtime_update_tail_replaces_only_the_runtime_in_place(self):
        public, private = self.games('public', 'private')
        result = public.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        # The live game: component 0 installed with the October 6 runtime.
        adapter = stage(private.root, DEPLOYED_RUNTIME)
        self.assert_installed(install(private, '0'))
        deployed = tree(private.override)
        state = int(next(
            line.split()[0] for line in deployed['SPLSTATE.IDS'].decode('ascii').splitlines()
            if line.strip().endswith('CBR_PHYSICAL_SOFTCAP')))
        self.assertEqual(text(deployed['M_CBRRES.LUA']), stamped(DEPLOYED_RUNTIME, state))

        # The update stages the new runtime and appends component 1.
        log_before = private.active_log().splitlines()
        shutil.copy2(CURRENT_RUNTIME, adapter / 'lua/M_CBRRES.lua')
        self.assert_installed(install(private, '1'))
        log_after = private.active_log().splitlines()
        # WeiDU appends one row and rewrites only the comment of this tp2's own row 0 (its
        # current component name and VERSION); every other row stays byte-identical.
        self.assertEqual(len(log_after), len(log_before) + 1)
        self.assertRegex(log_after[-1], r'(?i)setup-cbr_physical_cap\.tp2~\s+#0\s+#1\b')
        for old, new in zip(log_before, log_after):
            if old != new:
                self.assertRegex(old, r'(?i)setup-cbr_physical_cap\.tp2~\s+#0\s+#0\b')
                self.assertEqual(old.split('//')[0], new.split('//')[0])
        updated = tree(private.override)
        self.assertEqual(updated, tree(public.override))
        self.assertEqual(updated['SPLSTATE.IDS'], deployed['SPLSTATE.IDS'])
        self.assertEqual(text(updated['M_CBRRES.LUA']), stamped(CURRENT_RUNTIME, state))
        self.assertEqual(set(updated), set(deployed))
        for name in set(deployed) - {'M_CBRRES.LUA'}:
            self.assertEqual(updated[name], deployed[name], name)
        log = private.active_log()
        self.assertRegex(log, r'(?mi)setup-cbr_physical_cap\.tp2~\s+#0\s+#0\b')
        self.assertRegex(log, r'(?mi)setup-cbr_physical_cap\.tp2~\s+#0\s+#1\b')
        # WeiDU keeps the replaced runtime so uninstalling the tail restores it.
        backup = {p.name.upper(): p.read_bytes() for p in (adapter / 'backup/1').iterdir() if p.is_file()}
        self.assertEqual(backup.get('M_CBRRES.LUA'), deployed['M_CBRRES.LUA'])
        self.assertNotIn('SPLSTATE.IDS', backup)
        self.assert_stable(private)

    def test_runtime_update_requires_component_zero(self):
        (game,) = self.games('game')
        stage(game.root)
        result = install(game, '1')
        self.assertNotIn('SUCCESSFULLY INSTALLED', result.stdout)
        self.assertNotRegex(game.active_log(), r'(?mi)#0\s+#1\b')
        self.assertEqual(tree(game.override), game.before)
        self.assert_stable(game)

    def test_runtime_update_never_allocates_a_second_marker(self):
        (game,) = self.games('game')
        adapter = stage(game.root, DEPLOYED_RUNTIME)
        self.assert_installed(install(game, '0'))
        ids = game.override / 'SPLSTATE.IDS'
        ids.write_text('IDS V1.0\n0 NORMAL\n', encoding='ascii', newline='\n')
        before = tree(game.override)
        shutil.copy2(CURRENT_RUNTIME, adapter / 'lua/M_CBRRES.lua')
        result = install(game, '1')
        self.assertNotIn('SUCCESSFULLY INSTALLED', result.stdout)
        self.assertIn('CBR_PHYSICAL_SOFTCAP marker from component 0 is missing',
                      result.stdout + result.stderr)
        self.assertNotRegex(game.active_log(), r'(?mi)#0\s+#1\b')
        self.assertEqual(tree(game.override), before)
        self.assert_stable(game)


if __name__ == '__main__':
    unittest.main()
