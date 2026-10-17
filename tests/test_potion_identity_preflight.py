"""Real-WeiDU read-only identity checks in disposable resource fixtures."""
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_potion_uniqueness_installer import PotionGame, fx, potion, spell
from tests.ie_formats import EffV2


class PotionIdentityPreflightTests(unittest.TestCase):
    def check(self, data, action, *, biff_only=()):
        holder = tempfile.TemporaryDirectory(prefix="cbr-potion-identity-")
        self.addCleanup(holder.cleanup)
        game = PotionGame(Path(holder.name), data, biff_only=biff_only)
        source = game.root / "identity.tp2"
        source.write_text(
            "BACKUP ~identity-backup~\nAUTHOR ~synthetic~\nBEGIN ~Identity check~\n"
            "INCLUDE ~research/prototypes/potion-uniqueness/potion_identity.tpa~\n"
            "LAF cbr_pq_index_identity_references RET cbr_pqi_indexed "
            "RET_ARRAY cbr_pqi_refs cbr_pqi_immunities END\n" + action + "\n",
            encoding="ascii",
        )
        result = game.run(0, target="identity.tp2")
        self.assertEqual(game.before, game.snapshot(), result.stdout + result.stderr)
        return result.returncode, result.stdout + result.stderr

    def test_item_ward_retains_original_outer_admission(self):
        code, output = self.check(
            {"POTN36.ITM": potion((fx(90, 40),)),
             "WARD.SPL": spell((fx(318, resource="POTN36"),))},
            "LAF cbr_pq_assert_identity STR_VAR file=~POTN36.ITM~ END",
        )
        self.assertEqual(0, code, output)

    def test_private_spell_ward_is_not_silently_bypassed(self):
        code, output = self.check(
            {"CHILD.SPL": spell((fx(90, 40),)),
             "WARD.SPL": spell((fx(318, resource="CHILD"),))},
            "LAF cbr_pq_assert_identity STR_VAR file=~child.spl~ END",
            biff_only=("WARD.SPL",),
        )
        self.assertNotEqual(0, code, output)
        self.assertIn("CBR_POTION_IDENTITY:", output)
        self.assertIn("WARD.SPL", output)

    def test_external_source_removal_is_diagnosed(self):
        code, output = self.check(
            {"POTN36.ITM": potion((fx(90, 40),)),
             "REMOVE.EFF": EffV2(opcode=321, target=1, resource="POTN36").to_bytes()},
            "LAF cbr_pq_assert_identity INT_VAR allow_self_remove=1 STR_VAR file=~POTN36.ITM~ END",
        )
        self.assertNotEqual(0, code, output)
        self.assertIn("REMOVE.EFF", output)
        self.assertIn("CBR_POTION_IDENTITY:", output)

    def test_existing_self_removal_requires_explicit_allowance(self):
        data = {"POTN60.ITM": potion((fx(321, timing=1, resource="POTN60"), fx(90, 40)))}
        code, output = self.check(
            data, "LAF cbr_pq_assert_identity STR_VAR file=~POTN60.ITM~ END")
        self.assertNotEqual(0, code, output)
        code, output = self.check(
            data, "LAF cbr_pq_assert_identity INT_VAR allow_self_remove=1 STR_VAR file=~POTN60.ITM~ END")
        self.assertEqual(0, code, output)

    def test_new_control_opcode_immunity_is_diagnosed(self):
        code, output = self.check(
            {"WARD.SPL": spell((fx(101, p2=318),))},
            "LAF cbr_pq_assert_control_opcode INT_VAR opcode=318 END",
        )
        self.assertNotEqual(0, code, output)
        self.assertIn("CBR_POTION_ADMISSION:", output)
        self.assertIn("WARD.SPL", output)

    def test_only_declared_converted_family_can_adapt_cross_copy_removal(self):
        data = {"POTN60.ITM": potion((fx(90, 40),)),
                "DW#PTN60.ITM": potion((fx(321, timing=1, resource="POTN60"), fx(90, 40)))}
        action = (
            "OUTER_SPRINT $pq_family(~POTN60.ITM~) ~POTN60.ITM~\n"
            "OUTER_SPRINT $pq_family(~DW#PTN60.ITM~) ~POTN60.ITM~\n"
            "LAF cbr_pq_assert_identity INT_VAR allow_self_remove=1 "
            "STR_VAR file=~POTN60.ITM~ family=~POTN60.ITM~ END")
        code, output = self.check(data, action)
        self.assertEqual(0, code, output)
        data["EXTERNAL.SPL"] = spell((fx(321, resource="POTN60"),))
        code, output = self.check(data, action)
        self.assertNotEqual(0, code, output)
        self.assertIn("EXTERNAL.SPL", output)

    def test_valid_effect_table_before_ability_and_orphans(self):
        original = potion((fx(90, 40),))
        header = bytearray(original[:0x72])
        ability, effects = original[0x72:0xAA], original[0xAA:]
        struct.pack_into("<I", header, 0x64, 0x72 + len(effects))
        struct.pack_into("<I", header, 0x6A, 0x72)
        # An unreferenced trailing record must not create a false native ward.
        reordered = bytes(header) + effects + ability + fx(101, p2=318).to_bytes()
        code, output = self.check(
            {"POTN36.ITM": reordered},
            "LAF cbr_pq_assert_identity STR_VAR file=~POTN36.ITM~ END\n"
            "LAF cbr_pq_assert_control_opcode INT_VAR opcode=318 END",
        )
        self.assertEqual(0, code, output)


if __name__ == "__main__":
    unittest.main()
