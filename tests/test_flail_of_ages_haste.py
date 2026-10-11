"""Haste capability/preservation regressions in disposable synthetic games.

Reuse fixture helpers, not their TestCase inheritance, so baseline tests are
not discovered a second time. No live game or captured resource is modified.
"""

from __future__ import annotations

import dataclasses
import unittest

from tests import test_flail_of_ages as baseline
from tests.ie_formats import EffV2, SplAbility, SplEffect, make_spl, read_itm


class FlailHasteTests(unittest.TestCase):
    game = baseline.FlailTests.game
    assert_installed = baseline.FlailTests.assert_installed
    assert_effect_contract = baseline.FlailTests.assert_effect_contract

    def put(self, game, name, data):
        game.original[name] = data
        (game.override / name).write_bytes(data)

    def add_movement_immunity(self, game):
        path = game.override / "BLUN30.ITM"
        old = read_itm(path)
        immunity = SplEffect(
            opcode=101, target=1, parameter2=176, timing=2,
            power=7, probability1=97, probability2=3, special=0xA5,
        )
        self.put(game, path.name, dataclasses.replace(
            old, global_effects=(*old.global_effects, immunity),
        ).to_bytes())
        return immunity

    def assert_sources_unchanged(self, game, *names):
        for name in ("FOREIGN.ITM", "BLUN14A.ITM", *names):
            self.assertEqual(game.original[name], (game.override / name).read_bytes(), name)
        for path, data in game.stable.items():
            self.assertEqual(data, path.read_bytes(), str(path))

    def assert_noncanonical_immunity_preserved(self, game):
        before = read_itm(game.override / "BLUN30.ITM")
        expected = tuple(
            effect.to_bytes() for effect in before.global_effects
            if effect.opcode == 206 and effect.resource == "NOTHASTE"
        )
        self.assertEqual(1, len(expected), "fixture must contain the tested immunity")
        self.assert_installed(game)
        after = read_itm(game.override / "BLUN30.ITM")
        actual = tuple(
            effect.to_bytes() for effect in after.global_effects
            if effect.opcode == 206 and effect.resource == "NOTHASTE"
        )
        self.assertEqual(expected, actual)
        self.assert_effect_contract(game)
        self.assert_sources_unchanged(game, "NOTHASTE.SPL")

    def test_noncanonical_spell_with_orphan_haste_record_keeps_immunity(self):
        game = self.game("vanilla")
        visual = SplEffect(opcode=215, target=2, resource="FXVISUAL", timing=1)
        spell = make_spl((SplAbility(1, 1, 0, (visual,)),)).to_bytes()
        # The extra full record is not referenced by casting or ability slices.
        # It must not turn this visual-only spell into a Haste-identity match.
        # Using an allowed visual also ensures the separate mixed-payload
        # rejection cannot accidentally hide an orphan-record scanning bug.
        orphan = SplEffect(opcode=16, target=2, duration=60).to_bytes()
        self.put(game, "NOTHASTE.SPL", spell + orphan)
        self.assert_noncanonical_immunity_preserved(game)

    def test_noncanonical_mixed_damage_and_haste_spell_keeps_immunity(self):
        game = self.game("vanilla")
        damage = SplEffect(
            opcode=12, target=2, parameter1=23, parameter2=65536,
            timing=1, save_type=1, save_bonus=-3,
        )
        haste = SplEffect(opcode=16, target=2, duration=37)
        self.put(game, "NOTHASTE.SPL", make_spl((
            SplAbility(1, 1, 0, (damage, haste)),
        )).to_bytes())
        # Removing this immunity would expose its wearer to foreign damage,
        # not merely make the flail's Free Action compatible with Haste.
        self.assert_noncanonical_immunity_preserved(game)

    def test_nested_canonical_haste_movement_conflict_diagnoses_and_rolls_back(self):
        game = self.game("vanilla")
        self.add_movement_immunity(game)
        movement = EffV2(opcode=176, target=2, parameter1=6, duration=60)
        self.put(game, "FHMOVE.EFF", movement.to_bytes())
        helper = make_spl((SplAbility(1, 1, 0, (
            SplEffect(opcode=177, target=2, parameter2=2, timing=1, resource="FHMOVE"),
        )),))
        self.put(game, "FHMID.SPL", helper.to_bytes())
        canonical = make_spl((SplAbility(1, 1, 0, (
            SplEffect(opcode=146, target=2, timing=1, resource="FHMID"),
        )),))
        # SPELL.IDS in Game relocates WIZARD_HASTE to this resource. Neither
        # canonical Haste nor Improved Haste contains a direct opcode 176.
        self.put(game, "SPWI355.SPL", canonical.to_bytes())
        expected = {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()}
        process, output = game.run()
        self.assertNotEqual(0, process.returncode, output)
        self.assertIn("movement-rate immunity blocks revised Haste", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(expected, {
            p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()
        })
        # WeiDU may retain newly allocated, now-unused strings after rollback;
        # every pre-existing string and item reference must remain intact.
        self.assertEqual(game.texts, baseline.strings(game.lang_tlk)[:len(game.texts)])
        self.assert_sources_unchanged(game, "SPWI355.SPL", "FHMID.SPL", "FHMOVE.EFF")

    def test_native_haste_secondary_type_does_not_imply_movement_conflict(self):
        game = self.game("vanilla")
        immunity = self.add_movement_immunity(game)
        native = bytearray(make_spl((SplAbility(1, 1, 0, (
            SplEffect(opcode=16, target=2, duration=60),
        )),)).to_bytes())
        native[0x27] = 20
        self.put(game, "SPWI355.SPL", bytes(native))
        self.assert_installed(game)
        after = read_itm(game.override / "BLUN30.ITM")
        self.assertIn(immunity.to_bytes(), tuple(effect.to_bytes() for effect in after.global_effects))
        self.assert_effect_contract(game)
        self.assert_sources_unchanged(game, "SPWI355.SPL")


if __name__ == "__main__":
    unittest.main()
