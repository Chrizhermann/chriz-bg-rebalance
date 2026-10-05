"""Test the private tail adapter without touching a real installation."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_physical_resistance_installer import ResistanceGame, ROOT, WEIDU, tree


def stage(root: Path) -> Path:
    destination = root / 'CBR_PHYSICAL_CAP'
    shutil.copytree(ROOT / 'live-patch/CBR_PHYSICAL_CAP', destination)
    (destination / 'lib').mkdir()
    (destination / 'lua').mkdir()
    for name in ('tempus_holy_power.tpa', 'tempus_spec_apr_eeex.tpa', 'physical_resistance.tpa'):
        shutil.copy2(ROOT / 'chriz-bg-rebalance/lib' / name, destination / 'lib' / name)
    shutil.copy2(ROOT / 'chriz-bg-rebalance/lua/M_CBRRES.lua', destination / 'lua/M_CBRRES.lua')
    return destination


class LiveAdapterTests(unittest.TestCase):
    def test_private_tail_matches_public_component(self):
        with tempfile.TemporaryDirectory(prefix='cbr-private-cap-') as temporary:
            root = Path(temporary)
            public = ResistanceGame(root / 'public')
            private = ResistanceGame(root / 'private')
            stage(private.root)
            result = public.install()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(WEIDU), 'CBR_PHYSICAL_CAP/setup-cbr_physical_cap.tp2',
                 '--game', str(private.root), '--language', '0', '--use-lang', 'en_US',
                 '--no-exit-pause', '--force-install-list', '0'],
                cwd=private.root, capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SUCCESSFULLY INSTALLED', result.stdout)
            self.assertEqual(tree(private.override), tree(public.override))
            for path, digest in private.stable.items():
                import hashlib
                self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)


if __name__ == '__main__':
    unittest.main()
