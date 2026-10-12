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

    def native_haste(self, *companions, secondary=0):
        data = bytearray(make_spl((SplAbility(1, 1, 0, (
            SplEffect(opcode=16, target=2, duration=48), *companions,
        )),)).to_bytes())
        data[0x27] = secondary
        return bytes(data)

    def put_slow(self, game, secondary):
        # SR's Slow carries its k1#Slow secondary type; Haste spells cancel it.
        self.put(game, "SPELL.IDS", b"2355 WIZARD_HASTE\n2677 WIZARD_IMPROVED_HASTE\n2312 WIZARD_SLOW\n")
        slow = bytearray(make_spl((SplAbility(1, 1, 0, (
            SplEffect(opcode=40, target=2, duration=30),
        )),)).to_bytes())
        slow[0x27] = secondary
        self.put(game, "SPWI312.SPL", bytes(slow))

    def blun30_immunities(self, game):
        return {effect.resource for effect in read_itm(game.override / "BLUN30.ITM").global_effects
                if effect.opcode == 206}

    def add_immunities(self, game, *names):
        # The captured vanilla/CEBG +5 items carry these native Haste immunities.
        path = game.override / "BLUN30.ITM"
        old = read_itm(path)
        added = tuple(SplEffect(opcode=206, target=1, timing=2, resource=name) for name in names)
        self.put(game, path.name, dataclasses.replace(
            old, global_effects=(*old.global_effects, *added),
        ).to_bytes())

    def test_real_vanilla_innate_haste_spells_lose_their_immunity(self):
        # Shapes of the vanilla innate Haste spells: fatigue afterwards, plus
        # lighting, glow, string, icon and sounds on SPIN828 and SPRA301.
        fatigue = SplEffect(opcode=93, target=2, parameter1=4, timing=4, duration=48)
        feedback = (
            SplEffect(opcode=141, target=2, parameter2=4, timing=1),
            SplEffect(opcode=61, target=2, parameter1=2017213440, parameter2=1638400, timing=1),
            SplEffect(opcode=139, target=2, parameter1=14023, timing=1),
            SplEffect(opcode=142, target=2, parameter2=38, duration=48),
            SplEffect(opcode=174, target=2, timing=1, resource="EFF_M28"),
            SplEffect(opcode=174, target=2, timing=4, duration=48, resource="EFF_M29"),
        )
        game = self.game("vanilla")
        self.add_immunities(game, "SPRA301", "SPIN572", "SPIN828")
        self.put(game, "SPIN572.SPL", self.native_haste(fatigue))
        for name in ("SPIN828.SPL", "SPRA301.SPL"):
            self.put(game, name, self.native_haste(*feedback, fatigue, secondary=13))
        self.assertLessEqual({"SPIN572", "SPIN828", "SPRA301"}, self.blun30_immunities(game))
        self.assert_installed(game)
        self.assertFalse({"SPIN572", "SPIN828", "SPRA301"} & self.blun30_immunities(game))
        self.assert_effect_contract(game)
        self.assert_sources_unchanged(game, "SPIN572.SPL", "SPIN828.SPL", "SPRA301.SPL")

    def test_real_sr_innate_haste_loses_its_immunity(self):
        # SR's SPIN572 also cancels Slow by secondary type and guards itself.
        game = self.game("sr")
        self.add_immunities(game, "SPIN572")
        self.put_slow(game, secondary=21)
        self.put(game, "SPIN572.SPL", self.native_haste(
            SplEffect(opcode=324, target=2, parameter1=138, parameter2=110, resource="SPIN572"),
            SplEffect(opcode=221, target=2, parameter1=9, parameter2=21),
            SplEffect(opcode=93, target=2, parameter1=4, timing=4, duration=48),
            secondary=20,
        ))
        self.assertIn("SPIN572", self.blun30_immunities(game))
        self.assert_installed(game)
        self.assertNotIn("SPIN572", self.blun30_immunities(game))
        self.assert_effect_contract(game)
        self.assert_sources_unchanged(game, "SPIN572.SPL", "SPWI312.SPL", "SPELL.IDS")

    def test_haste_with_an_unrelated_removal_keeps_immunity_and_says_why(self):
        game = self.game("sr")
        self.add_immunities(game, "SPIN572")
        self.put_slow(game, secondary=21)
        # Removing spell protections (secondary type 1) is not part of Haste.
        self.put(game, "SPIN572.SPL", self.native_haste(
            SplEffect(opcode=221, target=2, parameter1=9, parameter2=1), secondary=20,
        ))
        before = read_itm(game.override / "BLUN30.ITM")
        expected = tuple(effect.to_bytes() for effect in before.global_effects
                         if effect.opcode == 206 and effect.resource == "SPIN572")
        self.assertEqual(1, len(expected))
        process, output = game.run()
        self.assertEqual(0, process.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertRegex(output, r"(?i)BLUN30 keeps its immunity to spin572\. .*\(opcode 221\)")
        after = read_itm(game.override / "BLUN30.ITM")
        self.assertEqual(expected, tuple(effect.to_bytes() for effect in after.global_effects
                                         if effect.opcode == 206 and effect.resource == "SPIN572"))
        self.assert_sources_unchanged(game, "SPIN572.SPL", "SPWI312.SPL", "SPELL.IDS")

    def test_real_troll_rider_chain_is_left_unchanged(self):
        # The reference install links an on-hit EFF to a spell whose
        # op321/op318 pairs name other resources and add delayed damage.
        game = self.game("sr")
        pairs = []
        for name in ("DWTRRG2", "DWTRRG4", "DWTRRG12", "DWTFRG2"):
            pairs += [SplEffect(opcode=321, target=2, resource=name),
                      SplEffect(opcode=318, target=2, duration=6, resource=name)]
        damage = SplEffect(opcode=12, target=2, parameter1=1, parameter2=65536, timing=4)
        self.put(game, "DWTROLAC.EFF", EffV2(
            opcode=146, target=2, parameter1=1, parameter2=1, timing=1, resource="DWTROLAC",
        ).to_bytes())
        self.put(game, "DWTROLAC.SPL", make_spl((SplAbility(0, 1, 1, (*pairs, damage)),)).to_bytes())
        self.assert_installed(game)
        self.assert_effect_contract(game)
        self.assert_sources_unchanged(game, "DWTROLAC.EFF", "DWTROLAC.SPL")

    def test_unknown_haste_type_removal_on_hit_is_reported_and_left_unsaved(self):
        game = self.game("vanilla")  # canonical Haste here has no secondary type
        path = game.override / "BLUN14.ITM"
        old = read_itm(path)
        removal = SplEffect(opcode=221, target=2, parameter1=9, parameter2=20, probability1=33)
        ability = dataclasses.replace(old.abilities[0], effects=(*old.abilities[0].effects, removal))
        self.put(game, path.name, dataclasses.replace(old, abilities=(ability,)).to_bytes())
        process, output = game.run()
        self.assertEqual(0, process.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertIn("BLUN14 removes secondary type 20 on hit", output)
        effects = read_itm(path).abilities[0].effects
        self.assertIn(removal.to_bytes(), tuple(effect.to_bytes() for effect in effects))


if __name__ == "__main__":
    unittest.main()
