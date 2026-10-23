"""Optional real-stack regressions using an explicitly supplied local capture.

CBR_DRAGON_STACK_CAPTURE names a read-only ten-file capture, never a live game.
The public installer runs only in a disposable synthetic game built from it.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.test_dragon_installer import DragonGame, PAYLOADS, SCRIPTS
from tests.test_dragon_vorpal_scripts import matches
from tests.test_dragon_wing_buffet import ROSTER, WEIDU, blocks, snapshot

CAPTURE = os.environ.get("CBR_DRAGON_STACK_CAPTURE")


@unittest.skipUnless(WEIDU.exists(), "WeiDU executable not available")
@unittest.skipUnless(CAPTURE, "set CBR_DRAGON_STACK_CAPTURE to a private resource capture")
class DragonCapturedStackTests(unittest.TestCase):
    def test_global_stack_public_install_preservation_and_uninstall(self) -> None:
        originals = Path(CAPTURE)
        before = snapshot(originals)
        with tempfile.TemporaryDirectory(prefix="cbr-dragon-stack-") as temporary:
            game = DragonGame(Path(temporary) / "game", originals=originals)
            result = game.run("--force-install-list", "110", "111")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("NOT INSTALLED", result.stdout)
            self.assertEqual(snapshot(game.override).keys() - game.before.keys(),
                             SCRIPTS | PAYLOADS)
            for script, actor, _ in ROSTER.values():
                current = blocks((game.override / (script + ".bcs")).read_bytes())
                self.assertIn(b'"GLOBALDMWW_dragon_difficulty"', b"".join(current[:4]))
                for category in range(-1, 9):
                    for slider in range(1, 6):
                        selected = [b for b in current[:4] if matches(
                            b, actor=actor, active=0, category=category, game=slider,
                            family="global")]
                        self.assertEqual(len(selected), int(category in (5, 6, 7) or
                                                           (category == 0 and slider in (4, 5))))
            # Removing 111 exposes the unchanged original SCS body behind110.
            result = game.run("--force-uninstall-list", "111")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for script in SCRIPTS:
                self.assertEqual(blocks((game.override / script).read_bytes())[4:],
                                 blocks(before[script + ".orig"]))
            result = game.run("--force-uninstall-list", "110")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(snapshot(game.override), game.before)
            for name, data in game.stable.items():
                self.assertEqual((game.root / name).read_bytes(), data, name)
        self.assertEqual(snapshot(originals), before)


if __name__ == "__main__":
    unittest.main()
