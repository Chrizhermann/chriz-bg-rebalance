"""Read-only WeiDU inventory in synthetic games; no native component or game."""
from pathlib import Path
import shutil
import tempfile
import unittest

from lupa.luajit21 import LuaRuntime
from tests.test_potion_uniqueness_installer import PotionGame, potion, fx

ROOT = Path(__file__).resolve().parents[1]
LIB = "research/prototypes/potion-admission/potion_registry.tpa"
SETUP = "setup-cbr_potion_inventory.tp2"


class PotionRegistryInstallerTests(unittest.TestCase):
    def game(self, resources, policy="unique", biff_only=()):
        holder = tempfile.TemporaryDirectory(prefix="cbr-potion-registry-")
        self.addCleanup(holder.cleanup)
        game = PotionGame(Path(holder.name), resources, biff_only=biff_only)
        path = game.root / LIB
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / LIB, path)
        (game.root / "empty.lua").write_bytes(b"")
        (game.root / SETUP).write_text(
            'BACKUP ~cbr_inventory/backup~\nAUTHOR ~offline fixture~\n'
            'BEGIN ~Inventory fixture~ DESIGNATED 0\n'
            f'INCLUDE ~{LIB}~\n'
            f'LAF cbr_pq_inventory STR_VAR policy=~{policy}~ RET inventory_lua inventory_count END\n'
            'COPY ~empty.lua~ ~override/CBRPQREG.lua~\n'
            '  INSERT_BYTES 0 (STRING_LENGTH ~%inventory_lua%~)\n'
            '  WRITE_ASCIIE 0 ~%inventory_lua%~\n', encoding="ascii")
        return game

    def extract(self, game):
        result = game.run(0, target=SETUP)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = (game.override / "CBRPQREG.lua").read_bytes()
        lua = LuaRuntime(encoding=None)
        options = lua.execute(data)
        return options, data

    def test_effective_override_and_biff_inventory_preserve_every_input(self):
        resources = {"POTN36.ITM": potion((fx(90,40),)), "DW#PTN36.ITM": potion((fx(90,40),)),
                     "HEALING.ITM": potion((fx(17,8,timing=1),)),
                     "FOREIGN.ITM": potion((fx(90,2),),category=3), "KEEP.LUA": b"unchanged\n"}
        for policy in ("unique", "except_genius"):
            with self.subTest(policy=policy):
                g = self.game(resources, policy, biff_only=("POTN36.ITM", "FOREIGN.ITM"))
                options, data = self.extract(g)
                self.assertEqual(1, options[b"version"])
                self.assertEqual(policy.encode(), options[b"policy"])
                self.assertEqual({b"POTN36.ITM",b"DW#PTN36.ITM",b"HEALING.ITM"},
                                 set(options[b"names"].values()))
                after = g.snapshot()
                after.pop("CBRPQREG.LUA")
                self.assertEqual(g.before, after)
                for path, original in g.stable.items():
                    self.assertEqual(original, path.read_bytes())
                # The emitted artifact is inert data; it contains no native APIs.
                self.assertNotIn(b"EEex_", data)
                result = g.run(0, target=SETUP, uninstall=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(g.before, g.snapshot())

    def test_empty_inventory_is_valid_and_bad_policy_rolls_back(self):
        g = self.game({"WAND.ITM": potion(category=35)})
        options, _ = self.extract(g)
        self.assertEqual([], list(options[b"names"].items()))
        g = self.game({"POTN36.ITM": potion((fx(90,40),))}, "invalid")
        result = g.run(0, target=SETUP)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unknown repeat policy", result.stdout + result.stderr)
        self.assertEqual(g.before, g.snapshot())

    def test_truncated_item_is_diagnosed_before_inventory_artifact_is_written(self):
        g = self.game({"BROKEN.ITM": b"ITM V1  "})
        result = g.run(0, target=SETUP)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("too short to read its item category", result.stdout + result.stderr)
        self.assertEqual(g.before, g.snapshot())


if __name__ == "__main__":
    unittest.main()
