"""Adversarial source-preservation checks in disposable, real WeiDU games.

These fixtures test the component's safety contract, not live engine acceptance.
Borrow helpers by assignment so unittest does not rediscover either source suite.
"""

from __future__ import annotations

import dataclasses
import struct
import unittest

from tests import test_flail_of_ages as baseline
from tests import test_flail_of_ages_variants as variants
from tests.ie_formats import EffV2, ItmFile, SplAbility, SplEffect, make_spl, read_itm


class FlailSafetyTests(unittest.TestCase):
    game = baseline.FlailTests.game
    assert_installed = baseline.FlailTests.assert_installed
    put = variants.FlailVariantTests.put
    with_abilities = variants.FlailVariantTests.with_abilities
    assert_item_bytes = variants.FlailVariantTests.assert_item_bytes
    assert_foreign_and_sources_unchanged = variants.FlailVariantTests.assert_foreign_and_sources_unchanged
    assert_no_helpers_created = variants.FlailVariantTests.assert_no_helpers_created

    def assert_ability_bytes(self, before, after, expected_effects):
        # Detaching or deleting another slice may change only this first-index
        # field; the ability's other fields and every retained effect stay exact.
        self.assertEqual(before.raw[:0x20], after.raw[:0x20])
        self.assertEqual(before.raw[0x22:], after.raw[0x22:])
        self.assertEqual(tuple(e.to_bytes() for e in expected_effects), tuple(e.to_bytes() for e in after.effects))

    def assert_header_bytes(self, before, after):
        # Description allocation and the equipped slice's first/count may move.
        # No other item header byte belongs to this transformation.
        expected = bytearray(before.header_raw)
        expected[0x54:0x58] = after.header_raw[0x54:0x58]
        expected[0x6E:0x72] = after.header_raw[0x6E:0x72]
        self.assertEqual(bytes(expected), after.header_raw)

    def assert_rollback(self, game, diagnostic):
        process, output = game.run()
        self.assertNotEqual(0, process.returncode, output)
        self.assertIn(diagnostic, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(game.original, {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()})
        # WeiDU can retain appended, unreferenced strings after rollback; original
        # strings and restored item strrefs, rather than TLK length, are owned.
        self.assertEqual(game.texts, baseline.strings(game.lang_tlk)[:len(game.texts)])
        self.assert_foreign_and_sources_unchanged(game)
        return output

    def test_shared_melee_and_magic_slice_keeps_magic_effects_unchanged(self):
        game = self.game("vanilla")
        slow = SplEffect(opcode=40, target=2, duration=27, probability1=71, probability2=19, save_type=0x1000004, save_bonus=5)
        damage = SplEffect(opcode=12, target=2, parameter1=23, parameter2=65536, timing=1, special=0x102)
        self.with_abilities(game, (variants.ability(1, (damage, slow), marker=3), variants.ability(3, (damage, slow), marker=7)))
        raw = bytearray(game.original["BLUN14.ITM"])
        ability_offset = struct.unpack_from("<I", raw, 0x64)[0]
        first = struct.unpack_from("<H", raw, ability_offset + 0x20)[0]
        struct.pack_into("<H", raw, ability_offset + 0x38 + 0x20, first)
        self.put(game, "BLUN14.ITM", bytes(raw))
        before = ItmFile.from_bytes(bytes(raw))
        self.assert_installed(game)
        after = read_itm(game.override / "BLUN14.ITM")
        self.assertEqual(2, len(after.abilities))
        self.assert_ability_bytes(before.abilities[0], after.abilities[0], (damage, variants.saved(slow)))
        self.assert_ability_bytes(before.abilities[1], after.abilities[1], (damage, slow))
        self.assertEqual(tuple(e.to_bytes() for e in before.global_effects), tuple(e.to_bytes() for e in after.global_effects))
        self.assert_header_bytes(before, after)
        self.assert_foreign_and_sources_unchanged(game)

    def test_plus5_equipped_shared_slice_deletion_preserves_ability_records(self):
        game = self.game("vanilla")
        haste_immunity = SplEffect(opcode=101, target=1, parameter2=16, timing=2, special=17)
        slow = SplEffect(opcode=40, target=2, duration=29, probability1=67, probability2=13, save_type=0x1000004, save_bonus=3)
        original = ItmFile.from_bytes(game.original["BLUN30.ITM"])
        fixture = dataclasses.replace(original, global_effects=(haste_immunity, slow), abilities=(variants.ability(1, (haste_immunity, slow), marker=9),))
        raw = bytearray(fixture.to_bytes())
        ability_offset = struct.unpack_from("<I", raw, 0x64)[0]
        struct.pack_into("<H", raw, ability_offset + 0x20, 0)
        self.put(game, "BLUN30.ITM", bytes(raw))
        before = ItmFile.from_bytes(bytes(raw))
        self.assert_installed(game)
        after = read_itm(game.override / "BLUN30.ITM")
        expected_slow = dataclasses.replace(slow, save_type=(slow.save_type & ~31) | 2, save_bonus=-6)
        self.assertEqual((slow.to_bytes(),), tuple(e.to_bytes() for e in after.global_effects))
        self.assertEqual(1, len(after.abilities))
        self.assert_ability_bytes(before.abilities[0], after.abilities[0], (haste_immunity, expected_slow))
        self.assert_header_bytes(before, after)
        self.assert_foreign_and_sources_unchanged(game)

    def test_valid_trailing_padding_is_preserved_byte_for_byte(self):
        game = self.game("vanilla")
        before = read_itm(game.override / "BLUN14.ITM")
        padding = b"\xDE\xAD\x00TAIL\xFE\x7F\x00\xA5"
        self.put(game, "BLUN14.ITM", game.original["BLUN14.ITM"] + padding)
        self.assert_installed(game)
        actual = (game.override / "BLUN14.ITM").read_bytes()
        expected = dataclasses.replace(before, identified_description=struct.unpack_from("<I", actual, 0x54)[0], abilities=(dataclasses.replace(before.abilities[0], effects=tuple(variants.saved(e) if e.opcode == 40 or (e.opcode == 139 and e.parameter1 == 14000) else e for e in before.abilities[0].effects)),))
        self.assertEqual(expected.to_bytes() + padding, actual)
        self.assert_foreign_and_sources_unchanged(game)

    def test_malformed_bounds_roll_back_previously_patched_tiers(self):
        for malformed in ("ability_table", "effect_table", "ability_slice", "equipped_slice"):
            with self.subTest(malformed=malformed):
                game = self.game("vanilla")
                raw = bytearray(game.original["BLUN30.ITM"])
                ability_offset = struct.unpack_from("<I", raw, 0x64)[0]
                if malformed == "ability_table":
                    struct.pack_into("<I", raw, 0x64, len(raw) + 8)
                elif malformed == "effect_table":
                    struct.pack_into("<I", raw, 0x6A, ability_offset)
                elif malformed == "ability_slice":
                    struct.pack_into("<H", raw, ability_offset + 0x20, 0xFFFF)
                else:
                    struct.pack_into("<H", raw, 0x6E, 0xFFFF)
                self.put(game, "BLUN30.ITM", bytes(raw))
                output = self.assert_rollback(game, "outside the resource")
                self.assertIn("BLUN30", output)

    def test_separate_eff_slow_feedback_and_sr_companions_gate_same_window_only(self):
        game = self.game()
        resources = {
            "FXSLOW.EFF": EffV2(opcode=40, target=2, duration=23, special=7),
            "FXMSG.EFF": EffV2(opcode=139, target=2, parameter1=14000, timing=9),
            "FXHASTE.EFF": EffV2(opcode=221, target=2, parameter1=9, parameter2=20, duration=23),
            "FXOTHER.EFF": EffV2(opcode=221, target=2, parameter1=9, parameter2=21, duration=23),
        }
        for name, effect in resources.items():
            self.put(game, name, effect.to_bytes())
        delivery = SplEffect(opcode=177, target=2, parameter2=2, timing=1, probability1=71, probability2=19, save_type=0x1000004, save_bonus=5)
        slow = dataclasses.replace(delivery, resource="FXSLOW")
        message = dataclasses.replace(delivery, resource="FXMSG", save_type=0x2000008, save_bonus=7)
        haste = dataclasses.replace(delivery, resource="FXHASTE")
        foreign_message = dataclasses.replace(message, probability1=97, probability2=83)
        foreign_secondary = dataclasses.replace(delivery, resource="FXOTHER")
        damage = SplEffect(opcode=12, target=2, parameter1=31, timing=1)
        effects = (message, damage, slow, foreign_message, haste, foreign_secondary)
        before = self.with_abilities(game, (variants.ability(1, effects),))
        self.with_abilities(game, (variants.ability(1, effects),), "FOREIGN.ITM")
        self.assert_installed(game)
        expected = dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=tuple(variants.saved(e) if i in (0, 2, 4) else e for i, e in enumerate(effects))),))
        self.assert_item_bytes(game, expected)
        self.assert_foreign_and_sources_unchanged(game, *resources)
        self.assert_no_helpers_created(game)

    def test_cyclic_foreign_helper_does_not_abort_or_change_direct_slow_patch(self):
        game = self.game("vanilla")
        for source, child in (("FXLOOPA", "FXLOOPB"), ("FXLOOPB", "FXLOOPA")):
            helper = make_spl((SplAbility(1, 1, 0, (SplEffect(opcode=146, target=2, timing=1, resource=child),)),))
            self.put(game, f"{source}.SPL", helper.to_bytes())
        slow = SplEffect(opcode=40, target=2, duration=23, probability1=71, probability2=19, save_type=0x1000004, save_bonus=5)
        foreign = SplEffect(opcode=146, target=2, resource="FXLOOPA", timing=1, probability1=71, probability2=19, save_type=8, save_bonus=3)
        before = self.with_abilities(game, (variants.ability(1, (foreign, slow)),))
        self.with_abilities(game, (variants.ability(1, (foreign,)),), "FOREIGN.ITM")
        self.assert_installed(game)
        expected = dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=(foreign, variants.saved(slow))),))
        self.assert_item_bytes(game, expected)
        self.assert_foreign_and_sources_unchanged(game, "FXLOOPA.SPL", "FXLOOPB.SPL")
        self.assert_no_helpers_created(game)

    def test_mixed_payload_rolls_back_even_when_another_tier_was_patched(self):
        game = self.game("vanilla")
        slow = SplEffect(opcode=40, target=2, duration=23)
        damage = SplEffect(opcode=12, target=2, parameter1=31, timing=1)
        helper = make_spl((SplAbility(1, 1, 0, (slow, damage)),))
        self.put(game, "FXMIXED.SPL", helper.to_bytes())
        link = SplEffect(opcode=146, target=2, timing=1, resource="FXMIXED")
        self.with_abilities(game, (variants.ability(1, (link,)),), "BLUN30C.ITM")
        output = self.assert_rollback(game, "mixes Slow with other effects")
        self.assertIn("FXMIXED", output)

    def test_aoe_or_additional_inner_save_rejects_without_mutating_originals(self):
        cases = (
            ("area_projectile", 94, 0, 0),
            ("different_inner_save", 0, 4, 0),
            ("same_inner_save_still_additional", 0, 2, -2),
        )
        for label, projectile, child_save, child_bonus in cases:
            with self.subTest(case=label):
                game = self.game("vanilla")
                slow = SplEffect(opcode=40, target=2, duration=23, save_type=child_save, save_bonus=child_bonus)
                helper = make_spl((SplAbility(1, 1, projectile, (slow,)),))
                self.put(game, "FXUNSAFE.SPL", helper.to_bytes())
                link = SplEffect(opcode=146, target=2, timing=1, resource="FXUNSAFE", save_type=0x1000004, save_bonus=7)
                self.with_abilities(game, (variants.ability(1, (link,)),))
                self.with_abilities(game, (variants.ability(1, (link,)),), "FOREIGN.ITM")
                output = self.assert_rollback(game, "mixes Slow with other effects")
                self.assertIn("FXUNSAFE", output)


if __name__ == "__main__":
    unittest.main()
