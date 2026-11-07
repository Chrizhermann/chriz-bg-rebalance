"""Public setup overwrites; synthetic game data only."""
import dataclasses
import re
import struct
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import SplAbility, SplEffect, SplFile, ItmFile
from tests.test_cloud_forms import Game, ROOT
from tests.test_release_components import run_public
from tests.test_emotion_hope_courage_installer import _store, _store_entries
from tests.test_time_stop_haste_clocks_installer import ClocksGame, SOURCES


class SetupOverwriteTests(unittest.TestCase):
    def game(self, resources):
        temp = tempfile.TemporaryDirectory(prefix="cbr-setup-overwrite-")
        self.addCleanup(temp.cleanup)
        game = Game(Path(temp.name), resources, public=True)
        (game.root / "WeiDU.log").write_text("")
        return game

    def install(self, game, component):
        code, output = run_public(game, component)
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
        return output

    def test_no_sr_scs_or_version_gate_in_setup(self):
        source = (ROOT / "setup-chriz-bg-rebalance.tp2").read_text(encoding="utf-8")
        for path in re.findall(r"MOD_IS_INSTALLED\s+~([^~]+)~", source):
            self.assertTrue(path.startswith(("setup-chriz-bg-rebalance", "cbr_")), path)
        self.assertNotIn("PATCH27.BIF", source)
        self.assertNotRegex(source, r"(?m)^\s*(PATCH_FAIL|PATCH_WARN|WARN)\b")

    def test_compatible_time_stop_hook_does_not_need_patch_archive(self):
        temp = tempfile.TemporaryDirectory(prefix="cbr-clock-no-archive-")
        self.addCleanup(temp.cleanup)
        game = ClocksGame(Path(temp.name) / "game", patch27=False)
        result = game.weidu("--force-install-list")
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
        for name, source in SOURCES.items():
            self.assertEqual(source.read_bytes(), (game.override / name).read_bytes())
        for name, original in game.before.items():
            self.assertEqual(original, (game.override / name).read_bytes())

    def test_telekinetic_edited_and_missing_damage_receive_the_save(self):
        for effects in ((), (SplEffect(opcode=12, special=0, save_type=0),),
                        (SplEffect(opcode=12, special=256), SplEffect(opcode=174))):
            with self.subTest(effects=effects):
                spell = SplFile(abilities=(SplAbility(required_level=1, target=2, projectile=1, effects=effects),))
                game = self.game({"SPELL.IDS": b"2007 WIZARD_TELEKINETIC_STORM\n",
                                  "SPWI007.SPL": spell.to_bytes()})
                self.install(game, 100)
                after = SplFile.from_bytes(game.snapshot()["SPWI007.SPL"])
                damage = [fx for fx in after.abilities[0].effects if fx.opcode == 12]
                self.assertTrue(damage)
                for fx in damage:
                    self.assertEqual(0x1000001, fx.save_type & 0x1000001)
                    self.assertEqual(256, fx.special & 256)
                code, output = run_public(game, 100, uninstall=True)
                self.assertEqual(0, code, output)
                self.install(game, 100)
                self.assertEqual(after.to_bytes(), game.snapshot()["SPWI007.SPL"])

    def test_absent_or_unreadable_telekinetic_is_local(self):
        for data in (None, b"truncated"):
            resources = {"SPELL.IDS": b"2820 WIZARD_TELEKINETIC_STORM\n"}
            if data is not None:
                resources["SPWI820.SPL"] = data
            game = self.game(resources)
            self.install(game, 100)
            if data is not None:
                self.assertEqual(data, game.snapshot()["SPWI820.SPL"])

    def test_freedom_stock_is_written_without_scs_or_old_quantity_gate(self):
        changed = struct.pack("<HHHHIII", 2, 9, 3, 2, 8, 127, 1)
        for rows in ((), (("SCRL9Z", changed),), (("scrl9z", changed), ("SCRL9Z", changed))):
            game = self.game({"RIBALD.STO": _store(rows), "SCRL9Z.ITM": ItmFile(abilities=()).to_bytes()})
            self.install(game, 101)
            rows = [row for row in _store_entries(game.snapshot()["RIBALD.STO"])
                    if row[:8].rstrip(b"\0").upper() == b"SCRL9Z"]
            self.assertEqual(1, len(rows))
            self.assertEqual((0, 1, 0, 0, 1, 5, 0), struct.unpack_from("<HHHHIII", rows[0], 8))


if __name__ == "__main__":
    unittest.main()
