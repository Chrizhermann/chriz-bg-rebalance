"""Read-only compiler fixtures, not engine admission or live-game acceptance."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from lupa import LuaRuntime
from tests.ie_formats import ItmAbility, ItmFile, SplEffect, EffV2
from tests.test_potion_payload_audit import container

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "research/prototypes/potion-admission/build_manifest.py"
spec = importlib.util.spec_from_file_location("potion_manifest", COMPILER)
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


def fx(opcode=90, amount=40, **kwargs):
    return SplEffect(opcode=opcode, parameter1=amount, target=1, timing=0,
                     duration=600, **kwargs)


def potion(*groups, category=9, globals=(), school=0, secondary=0, source_flags=0,
           ability_target=5, projectile=0):
    header = bytearray(0x72)
    struct.pack_into("<H", header, 0x1C, category)
    ability = bytearray(0x38)
    ability[0], ability[0xC] = 3, ability_target
    ability[0x17], ability[0x19] = school, secondary
    struct.pack_into("<I", ability, 0x26, source_flags)
    struct.pack_into("<H", ability, 0x2A, projectile)
    struct.pack_into("<HH", ability, 0x22, 7, 2)
    return ItmFile(tuple(ItmAbility(tuple(group), raw=bytes(ability)) for group in groups),
                   global_effects=tuple(globals), header_raw=bytes(header)).to_bytes()


def record_for(manifest, res, ordinal=0, ability=0):
    source = manifest["sources"][res]
    key = source["abilities"][str(ability)]["effects"][str(ordinal)]
    return key, source["records"][key]


class PotionAdmissionManifestTests(unittest.TestCase):
    def fail_code(self, code, inputs):
        before = {key: bytes(value) for key, value in inputs.items()}
        with self.assertRaises(compiler.ManifestError) as raised:
            compiler.build_manifest(inputs)
        self.assertEqual(code, raised.exception.code)
        self.assertEqual(before, inputs)
        return str(raised.exception)

    def test_both_policies_actual_genius_and_repurposed_potn29(self):
        genuine = {"POTN29.ITM": potion([fx(19, 4)]), "GENCOPY.ITM": potion([fx(19, 4)])}
        for policy in ("unique", "except_genius"):
            with self.subTest(policy=policy):
                result = compiler.build_manifest(genuine, policy)
                self.assertEqual(policy, result["policy"])
                self.assertEqual({"hp": False, "genius": True}, result["families"]["POTN29"])
                self.assertEqual("POTN29", result["sources"]["GENCOPY"]["family"])
        result = compiler.build_manifest({"POTN29.ITM": potion([fx(48, 0), fx(54, 1)])}, "except_genius")
        self.assertFalse(result["families"]["POTN29"]["genius"])
        self.assertIs(False, result["sources"]["POTN29"]["abilities"]["0"]["effects"]["0"])
        self.assertTrue(result["sources"]["POTN29"]["keys"])

    def test_unrelated_native_records_keep_order_counts_and_input_bytes(self):
        effects = [fx(), replace(fx(17, 9), timing=1), replace(fx(19, 1), timing=1),
                   fx(19, -1), fx(139, 999), fx(92, 40)]
        inputs = {"POTN36.ITM": bytearray(potion(effects, globals=[fx(142, 9)]))}
        before = bytes(inputs["POTN36.ITM"])
        result = compiler.build_manifest(inputs)
        ability = result["sources"]["POTN36"]["abilities"]["0"]
        self.assertEqual(6, ability["count"])
        self.assertEqual([False] * 4, [ability["effects"][str(i)] for i in range(1, 5)])
        self.assertEqual(2, len(ability["quotas"]))
        self.assertEqual(before, bytes(inputs["POTN36.ITM"]))

    def test_reordered_aliases_and_presentation_differences_share_family(self):
        result = compiler.build_manifest({
            "POTN36.ITM": potion([fx(), fx(92)]),
            "COPY.ITM": potion([fx(174, 0), fx(92), fx(139, 4), fx()]),
        })
        base, alias = (result["sources"][name] for name in ("POTN36", "COPY"))
        self.assertEqual("POTN36", alias["family"])
        self.assertEqual(base["keys"], alias["keys"])
        self.assertEqual(base["records"], alias["records"])
        self.assertEqual(4, alias["abilities"]["0"]["count"])

    def test_explicit_scs_pattern_needs_payload_evidence_and_propagates_hp(self):
        hp, thac0 = fx(18, 110, parameter2=2), fx(54, 90, parameter2=2)
        result = compiler.build_manifest({"POTN09.ITM": potion([hp, thac0]),
                                          "DW#PTN09.ITM": potion([thac0])})
        self.assertEqual("POTN09", result["sources"]["DW#PTN09"]["family"])
        self.assertTrue(result["families"]["POTN09"]["hp"])
        self.fail_code("PROVENANCE", {"DW#PTN09.ITM": potion([thac0])})
        self.fail_code("PROVENANCE", {"POTN09.ITM": potion([hp, thac0]),
                                      "DW#PTN09.ITM": potion([fx(19, 4)])})
        self.fail_code("PAYLOAD_CAPABILITY", {"POTN36.ITM": potion([fx(), fx(92)]),
                                              "DW#PTN36.ITM": potion([fx()])})

    def test_distinct_canonical_types_stay_distinct_despite_identical_fields(self):
        data = potion([fx(18, 110, parameter2=2), fx(54, 90, parameter2=2)])
        result = compiler.build_manifest({"POTN09.ITM": data, "POTN41.ITM": data})
        self.assertEqual({"POTN09", "POTN41"}, set(result["families"]))
        self.assertNotEqual(result["sources"]["POTN09"]["family"], result["sources"]["POTN41"]["family"])
        self.fail_code("IDENTITY_AMBIGUITY", {"POTN09.ITM": data, "POTN41.ITM": data, "COPY.ITM": data})

    def test_multiability_duplicate_quotas_and_reordered_alternative_layout(self):
        result = compiler.build_manifest({
            "POTN36.ITM": potion([fx(), fx(), fx(92)], [fx(92), fx(), fx()]),
            "COPY.ITM": potion([fx(92), fx(), fx()]),
        })
        source = result["sources"]["POTN36"]
        self.assertEqual({"0", "1"}, set(source["abilities"]))
        key, _ = record_for(result, "POTN36")
        for ability in source["abilities"].values():
            self.assertEqual(2, ability["quotas"][key])
            self.assertEqual(3, ability["count"])
        self.assertEqual("POTN36", result["sources"]["COPY"]["family"])

    def test_native_record_schema_uses_constructor_level_fields_and_original_metadata(self):
        effect = replace(fx(), power=7, resource="Native", dice_number=30, dice_size=2,
                         save_type=0x1000004, save_bonus=-8, special=9, resist_dispel=3,
                         probability1=80, probability2=20, timing=10, duration=901)
        result = compiler.build_manifest({"POTN36.ITM": potion([effect], school=5, secondary=6,
                                                               source_flags=0x80000002)})
        _, record = record_for(result, "POTN36")
        self.assertEqual(dict(opcode=90, target=1, power=7, amount=40, mode=0, resource="NATIVE",
                              diceCount=0, diceSize=0, minLevel=2, maxLevel=30,
                              saveType=0x1000004, saveBonus=-8, special=9, flags=3,
                              school=5, secondary=6, sourceFlags=0x80000002,
                              probUpper=80, probLower=20, timing=10, duration=901), record)

    def test_hp_special_original_retained_and_normalized_collision_rejected(self):
        hp = fx(18, 110, parameter2=2, special=1)
        result = compiler.build_manifest({"POTN09.ITM": potion([hp])})
        _, record = record_for(result, "POTN09")
        self.assertEqual(1, record["special"])
        self.assertEqual((0, 0, 0, 0), tuple(record[f] for f in ("diceCount", "diceSize", "minLevel", "maxLevel")))
        self.fail_code("SPECIAL_AMBIGUITY", {"POTN09.ITM": potion([hp, replace(hp, special=0)])})
        self.fail_code("HP_DICE_CAPABILITY", {"POTN09.ITM": potion([replace(hp, dice_number=1)])})

    def test_unusual_flags_and_normalized_level_values_have_explicit_diagnostics(self):
        self.fail_code("FLAGS_CAPABILITY", {"POTN36.ITM": potion([fx(resist_dispel=9)])})
        self.fail_code("LEVEL_CAPABILITY", {"POTN36.ITM": potion([fx(dice_size=65536)])})

    def test_exact_decode_sentinel_normalizes_predicted_fields_without_mutating_inputs(self):
        for opcode in (18, 19, 90, 142):
            with self.subTest(opcode=opcode):
                sentinel = fx(opcode, 10, dice_size=-1)
                zero = replace(sentinel, dice_size=0)
                # Portrait142 ownership comes only from a real HP package.
                prefix = [fx(18, 10)] if opcode == 142 else []
                data = {"POTN09.ITM": potion(prefix + [sentinel]),
                        "COPY.ITM": potion(prefix + [zero])}
                before = dict(data)
                result = compiler.build_manifest(data)
                key, record = record_for(result, "POTN09", len(prefix))
                other_key, other_record = record_for(result, "COPY", len(prefix))
                self.assertEqual((key, record), (other_key, other_record))
                self.assertEqual((0, 0), (record["minLevel"], record["diceSize"]))
                self.assertEqual("POTN09", result["sources"]["COPY"]["family"])
                self.assertEqual(before, data)
        # Native-identical records are still separate dose quotas.
        result = compiler.build_manifest({"A.ITM": potion([fx(dice_size=-1), fx(dice_size=0)])})
        source = result["sources"]["A"]
        self.assertEqual(1, len(source["keys"]))
        self.assertEqual([2], list(source["abilities"]["0"]["quotas"].values()))

    def test_decode_sentinel_does_not_relax_neighboring_levels_or_other_dice_fields(self):
        for amount in (0, 1, 65535):
            result = compiler.build_manifest({"A.ITM": potion([fx(dice_size=amount)])})
            self.assertEqual(amount, record_for(result, "A")[1]["minLevel"])
        for amount in (65536, 0x7FFFFFFF, -2147483648, -2):
            self.fail_code("LEVEL_CAPABILITY", {"A.ITM": potion([fx(dice_size=amount)])})
        # Only raw+20 has the sentinel rewrite; raw+1C is preserved exactly.
        result = compiler.build_manifest({"A.ITM": potion([fx(dice_number=-1, dice_size=-1)])})
        self.assertEqual(0xFFFFFFFF, record_for(result, "A")[1]["maxLevel"])
        for count, size in ((1, -1), (-1, 0), (-1, -1), (0, -2), (0, 1)):
            self.fail_code("HP_DICE_CAPABILITY", {"A.ITM": potion([fx(18, 10, dice_number=count, dice_size=size)])})

    def test_original_lifetime_ambiguity_rejected_with_ability_context(self):
        diagnostic = self.fail_code("DURATION_AMBIGUITY", {"POTN36.ITM": potion([fx()], [replace(fx(), duration=601)])})
        self.assertIn("ability:0", diagnostic)
        self.assertIn("ability:1", diagnostic)
        self.fail_code("DURATION_AMBIGUITY", {"POTN36.ITM": potion([fx()]),
                                              "COPY.ITM": potion([replace(fx(), duration=601)])})
        result = compiler.build_manifest({"POTN36.ITM": potion([fx()]),
                                          "POTN39.ITM": potion([replace(fx(), duration=601)])})
        self.assertEqual(2, len(result["families"]))

    def test_specialist_adjustment_collision_including_signed_boundary(self):
        for first, second in ((0, -2), (-2147483648, 2147483646)):
            with self.subTest(first=first):
                self.fail_code("SPECIALIST_AMBIGUITY", {"POTN36.ITM": potion(
                    [fx(save_bonus=first), fx(save_bonus=second)], school=1)})
        result = compiler.build_manifest({"POTN36.ITM": potion([fx(save_bonus=0), fx(save_bonus=-2)])})
        self.assertEqual(2, len(result["sources"]["POTN36"]["keys"]))

    def test_probability_is_part_of_native_fingerprint(self):
        result = compiler.build_manifest({"POTN36.ITM": potion(
            [fx(probability1=75, probability2=20), fx(probability1=100, probability2=0)])})
        self.assertEqual(2, len(result["sources"]["POTN36"]["keys"]))

    def test_direct_only_and_transport_limits_are_explicit(self):
        for opcode in (146, 177, 232, 326):
            with self.subTest(opcode=opcode):
                self.fail_code("LINK_CAPABILITY", {"A.ITM": potion([replace(fx(opcode), timing=1, resource="PAYLOAD")])})
        self.fail_code("TARGET_CAPABILITY", {"A.ITM": potion([replace(fx(), target=2)])})
        for opcode in (98, 200):
            self.fail_code("OPCODE_CAPABILITY", {"A.ITM": potion([fx(opcode, 1)])})
        self.fail_code("EQUIPPED_CAPABILITY", {"A.ITM": potion([], globals=[fx()])})
        self.fail_code("TIMING_CAPABILITY", {"A.ITM": potion([replace(fx(), timing=3)])})

    def test_transport_bounds_apply_only_to_owned_records_in_mixed_original_order(self):
        for target in (0, 2, 3, 6, 9):
            with self.subTest(target=target):
                effects = [replace(fx(139, 99), target=target), fx(90, 40),
                           replace(fx(12, 7), target=target),
                           replace(fx(94, 500), target=target, timing=1)]
                original = potion(effects, ability_target=2, projectile=55)
                result = compiler.build_manifest({"A.ITM": original})
                ability = result["sources"]["A"]["abilities"]["0"]
                self.assertEqual([False, True, False, False],
                                 [ability["effects"][str(i)] is not False for i in range(4)])
                self.assertEqual(4, ability["count"])
                self.assertEqual(original, potion(effects, ability_target=2, projectile=55))
        self.fail_code("OPCODE_CAPABILITY", {"A.ITM": potion([replace(fx(98, 3), target=2)])})

    def test_narrow_thac0_and_stat_modes_native_unique_and_adverse_preserved(self):
        effects = [fx(54, 1), fx(54, 90, parameter2=2), fx(54, -1),
                   fx(54, 110, parameter2=2), fx(19, 20, parameter2=1),
                   fx(15, -2), fx(16, 0), fx(48, 0)]
        result = compiler.build_manifest({"A.ITM": potion(effects)})
        owned = result["sources"]["A"]["abilities"]["0"]["effects"]
        self.assertEqual([True, True] + [False] * 6, [owned[str(i)] is not False for i in range(8)])
        self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(19, 120, parameter2=3)])})

    def test_ac_cumulative_modes_use_signed_low16_without_rewriting_native_fields(self):
        for mode in (0, 1, 2, 4, 8):
            for amount in (1, 10, 65537, -65535):
                with self.subTest(mode=mode, amount=amount):
                    result = compiler.build_manifest({"A.ITM": potion([fx(0, amount, parameter2=mode)])})
                    _, record = record_for(result, "A")
                    self.assertEqual((amount, mode), (record["amount"], record["mode"]))
            for amount in (0, -1, 65535, 32768):
                with self.subTest(mode=mode, amount=amount):
                    result = compiler.build_manifest({"A.ITM": potion([fx(0, amount, parameter2=mode)])})
                    self.assertEqual({}, result["sources"]["A"]["keys"])

    def test_ac_minimum_is_native_for_safe_potions_but_owned_in_hp_package(self):
        for amount in (-2, 0, 2, 12):
            effect = fx(0, amount, parameter2=16)
            safe = compiler.build_manifest({"A.ITM": potion([effect])})
            self.assertEqual({}, safe["sources"]["A"]["keys"])
            hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 10), effect]),
                                          "DW#PTN09.ITM": potion([effect])})
            self.assertTrue(hp["sources"]["DW#PTN09"]["keys"])
            self.assertTrue(hp["families"]["POTN09"]["hp"])

    def test_apr_encoding_requires_native_mapping_and_keeps_original_amount(self):
        for amount in (*range(1, 11), 65537, -65535):
            with self.subTest(amount=amount):
                result = compiler.build_manifest({"A.ITM": potion([fx(1, amount)])})
                _, record = record_for(result, "A")
                self.assertEqual(amount, record["amount"])
        for amount in (-10, -6, -1, 0, 11, 32767, 32768, 65535):
            with self.subTest(amount=amount):
                result = compiler.build_manifest({"A.ITM": potion([fx(1, amount)])})
                self.assertEqual({}, result["sources"]["A"]["keys"])

    def test_unreviewed_ac_and_apr_modes_still_diagnose_independent_of_sign(self):
        for opcode, modes in ((0, (3, 5, 6, 15, 17)), (1, (1, 2, 3, 16))):
            for amount in (-1, 0, 1, 6, 65535):
                for mode in modes:
                    with self.subTest(opcode=opcode, amount=amount, mode=mode):
                        self.fail_code("MODE_CAPABILITY", {
                            "A.ITM": potion([fx(opcode, amount, parameter2=mode)])})

    def test_reviewed_additive_stats_preserve_native_metadata_and_adverse_records(self):
        opcodes = (6, 10, 15, 21, 22, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37,
                   44, 49, 59, 73, 91, 275)
        for opcode in opcodes:
            with self.subTest(opcode=opcode):
                effects = [fx(opcode, 7, dice_size=2, dice_number=30), fx(opcode, -2)]
                result = compiler.build_manifest({"A.ITM": potion(effects)})
                source = result["sources"]["A"]
                self.assertEqual(1, len(source["keys"]))
                self.assertIs(False, source["abilities"]["0"]["effects"]["1"])
                _, record = record_for(result, "A")
                self.assertEqual((0, 0, 2, 30), tuple(record[key] for key in
                                                    ("diceCount", "diceSize", "minLevel", "maxLevel")))
                self.assertEqual(opcode == 10, result["families"]["A"]["hp"])

    def test_newly_supported_stats_do_not_guess_unreviewed_modes(self):
        for opcode, mode in ((44, 3), (15, 3), (10, 3), (91, 3), (275, 3)):
            with self.subTest(opcode=opcode, mode=mode):
                self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(opcode, 120, parameter2=mode)])})
        for opcode in (276, 277):
            # Native-reviewed skills now use signed LOW16 nominal polarity;
            # retain raw operands and adverse/zero records without ownership.
            data = potion([fx(opcode, amount) for amount in (-65535, -1, 0, 1)])
            result = compiler.build_manifest({"A.ITM": data})
            source = result["sources"]["A"]
            self.assertEqual([True, False, False, True],
                             [source["abilities"]["0"]["effects"][str(i)] is not False for i in range(4)])
            self.assertEqual({-65535, 1}, {r["amount"] for r in source["records"].values()})

    def test_additive_native_signed16_polarity_keeps_raw_fingerprints(self):
        opcodes = (6, 10, 15, 19, 21, 22, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37,
                   44, 49, 54, 59, 73, 90, 91, 92, 275)
        for opcode in opcodes:
            for mode in ((0, 3) if opcode in range(33, 38) else (0,)):
                with self.subTest(opcode=opcode, mode=mode):
                    amounts = (1, 65537, -65535, 32768, 65535, 65536, -2147483648)
                    data = potion([fx(opcode, value, parameter2=mode) for value in amounts])
                    result = compiler.build_manifest({"A.ITM": data})
                    source = result["sources"]["A"]
                    selected = source["abilities"]["0"]["effects"]
                    self.assertEqual([True] * 3 + [False] * 4,
                                     [selected[str(i)] is not False for i in range(len(amounts))])
                    self.assertEqual({1, 65537, -65535}, {r["amount"] for r in source["records"].values()})
                    self.assertEqual(3, len(source["keys"]))  # No raw-operand canonicalization.
                    self.assertEqual(opcode == 10, result["families"]["A"]["hp"])

    def test_hp_percentages_use_each_native_operand_width(self):
        for opcode in (6, 10, 15, 19, 44, 49, 92, 275):
            for amount, owned in ((150, True), (65686, True), (-65386, True),
                                  (65535, False), (32768, False), (65536, False)):
                with self.subTest(opcode=opcode, amount=amount):
                    result = compiler.build_manifest({"POTN09.ITM": potion(
                        [fx(18, 10), fx(opcode, amount, parameter2=2)])})
                    ordinal = result["sources"]["POTN09"]["abilities"]["0"]["effects"]["1"]
                    self.assertEqual(owned, ordinal is not False)
                    if owned:
                        self.assertEqual(amount, record_for(result, "POTN09", 1)[1]["amount"])
        # 90/91 use full signed32; the same negative dword is not +150 percent.
        for opcode in (90, 91):
            result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(opcode, -65386, parameter2=2)])})
            self.assertIs(False, result["sources"]["A"]["abilities"]["0"]["effects"]["1"])

    def test_skill_full32_percent_products_diagnose_overflow_before_ownership(self):
        for opcode, low, high in ((90, -8421504, 8421504), (91, -65535, 65536)):
            for amount in (low, high):
                result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(opcode, amount, parameter2=2)])})
                selected = result["sources"]["A"]["abilities"]["0"]["effects"]["1"]
                self.assertEqual(amount > 100, selected is not False)
            for amount in (low - 1, high + 1, 2147483647, -2147483648):
                self.fail_code("AMOUNT_CAPABILITY", {"A.ITM": potion([fx(18, 10), fx(opcode, amount, parameter2=2)])})
        # A native-only base-derived setter needs no ownership/polarity decision.
        result = compiler.build_manifest({"A.ITM": potion([fx(90, 2147483647, parameter2=2)])})
        self.assertFalse(result["sources"]["A"]["keys"])
        self.fail_code("AMOUNT_CAPABILITY", {"A.ITM": potion([fx(91, 65537, parameter2=2)])})

    def test_hide_setter_uses_unsigned_byte_while_other_setters_keep_signed32(self):
        for opcode in (6, 10, 15, 19, 44, 49, 90, 91, 92, 275):
            for amount in (-1, 0, 256, 65537):
                with self.subTest(opcode=opcode, amount=amount):
                    result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(opcode, amount, parameter2=1)])})
                    owned = amount % 256 > 0 if opcode == 275 else amount > 0
                    self.assertEqual(owned, result["sources"]["A"]["abilities"]["0"]["effects"]["1"] is not False)
                    if owned:
                        self.assertEqual(amount, record_for(result, "A", 1)[1]["amount"])

    def test_thac0_clamped_hp_setters_and_percentage_baseline_ambiguity(self):
        for amount in (-65535, -1, 0, 20, 65535, 65536):
            result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(54, amount, parameter2=1)])})
            self.assertEqual(amount, record_for(result, "A", 1)[1]["amount"])
            safe = compiler.build_manifest({"A.ITM": potion([fx(54, amount, parameter2=1)])})
            self.assertFalse(safe["sources"]["A"]["keys"])
        for amount, owned in ((0, True), (90, True), (100, True), (150, False),
                              (65536, True), (65626, True), (-65446, True)):
            result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(54, amount, parameter2=2)])})
            self.assertEqual(owned, result["sources"]["A"]["abilities"]["0"]["effects"]["1"] is not False)
        for amount in (-1, -100, 65535, 32768):
            self.fail_code("BASELINE_CAPABILITY", {"A.ITM": potion([fx(18, 10), fx(54, amount, parameter2=2)])})
            safe = compiler.build_manifest({"A.ITM": potion([fx(54, amount, parameter2=2)])})
            self.assertFalse(safe["sources"]["A"]["keys"])

    def test_mind_focusing_is_distinct_from_genius_and_scs_copy_reorders(self):
        result = compiler.build_manifest({"POTN29.ITM": potion([fx(19, 4)]),
                                          "POTN37.ITM": potion([fx(15, 3), fx(19, 3)]),
                                          "DW#PTN37.ITM": potion([fx(139, 8), fx(19, 3), fx(15, 3)])},
                                         "except_genius")
        self.assertTrue(result["families"]["POTN29"]["genius"])
        self.assertFalse(result["families"]["POTN37"]["genius"])
        self.assertEqual("POTN37", result["sources"]["DW#PTN37"]["family"])
        self.assertEqual(2, len(result["sources"]["DW#PTN37"]["keys"]))

    def test_family_source_removal_diagnosed_but_foreign_removal_preserved(self):
        remove = replace(fx(321, 0, resource="POTN60"), timing=1, duration=0)
        self.fail_code("REMOVAL_CAPABILITY", {"POTN60.ITM": potion([remove, fx(6, 4)])})
        result = compiler.build_manifest({"POTN60.ITM": potion([replace(remove, resource="FOREIGN"), fx(6, 4)])})
        self.assertIs(False, result["sources"]["POTN60"]["abilities"]["0"]["effects"]["0"])

    def test_hp_post_family_classification_cannot_skip_native_unique_companions(self):
        hp = fx(18, 110, parameter2=2)
        for companion in (fx(16, 0), fx(48, 0)):
            with self.subTest(opcode=companion.opcode):
                self.fail_code("HP_COMPANION_CAPABILITY", {"POTN09.ITM": potion([hp, companion])})
                # Alias has no HP opcode. The resolved family must still reject
                # leaving its timed companion outside repeat suppression.
                self.fail_code("HP_COMPANION_CAPABILITY", {"POTN09.ITM": potion([hp]),
                                                          "DW#PTN09.ITM": potion([companion])})

    def test_hp_package_owns_stable_sets_percentages_and_state_after_family_resolution(self):
        hp = fx(18, 120, parameter2=2)
        companions = [fx(19, 20, parameter2=1), fx(54, 10, parameter2=1),
                      fx(90, 120, parameter2=2), fx(92, 120, parameter2=2),
                      fx(275, 120, parameter2=2), fx(328, 1, parameter2=68, special=1)]
        result = compiler.build_manifest({"POTN41.ITM": potion([hp] + companions),
                                          "DW#PTN41.ITM": potion(list(reversed(companions)))})
        self.assertEqual(7, len(result["sources"]["POTN41"]["keys"]))
        self.assertEqual(6, len(result["sources"]["DW#PTN41"]["keys"]))
        self.assertTrue(result["families"]["POTN41"]["hp"])
        safe = compiler.build_manifest({"A.ITM": potion(companions)})
        self.assertFalse(safe["sources"]["A"]["keys"])
        self.fail_code("PROVENANCE", {"POTN41.ITM": potion([hp, fx(90, 120, parameter2=2)]),
                                      "DW#PTN41.ITM": potion([fx(90, 130, parameter2=2)])})

    def test_find_traps_percentage_is_owned_even_without_hp(self):
        result = compiler.build_manifest({"A.ITM": potion([fx(91, 120, parameter2=2)])})
        self.assertEqual(1, len(result["sources"]["A"]["keys"]))
        self.fail_code("STATE_CAPABILITY", {"A.ITM": potion([fx(328, 1, parameter2=2, special=0)])})

    def test_state_companion_uses_native_index_bounds_not_reference_state_number(self):
        for state in (0, 1, 69, 127, 255, 256):
            with self.subTest(state=state):
                marker = fx(328, 42, parameter2=state, special=7)
                safe = compiler.build_manifest({"A.ITM": potion([marker])})
                self.assertFalse(safe["sources"]["A"]["keys"])
                hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 110, parameter2=2), marker])})
                self.assertEqual(2 if state < 256 else 1, len(hp["sources"]["POTN09"]["keys"]))

    def test_hp_portrait_is_owned_nonblocking_and_alias_presentation_may_differ(self):
        hp = replace(fx(18, 110, parameter2=2), duration=300)
        icon = replace(fx(142, 7, parameter2=22), duration=540)
        different = replace(icon, parameter2=16)
        inputs = {"POTN09.ITM": potion([hp, icon, fx(139, 55)]),
                  "DW#PTN09.ITM": potion([different, hp])}
        result = compiler.build_manifest(inputs)
        for source, ordinal, expected in (("POTN09", 1, 22), ("DW#PTN09", 0, 16)):
            key, record = record_for(result, source, ordinal)
            self.assertEqual({key: True}, result["sources"][source]["nonBlockingKeys"])
            self.assertEqual((142, expected, 540), (record["opcode"], record["mode"], record["duration"]))
            self.assertEqual(2, len(result["sources"][source]["keys"]))
        safe = compiler.build_manifest({"A.ITM": potion([icon])})
        self.assertEqual({}, safe["sources"]["A"]["nonBlockingKeys"])
        self.assertEqual({}, safe["sources"]["A"]["keys"])

    def test_native_permanent_or_adverse_hp_changes_do_not_own_poison_presentation(self):
        icon = fx(142, 0, parameter2=6)
        for change in (replace(fx(10, -1), timing=1), fx(10, -1), fx(18, -5),
                       replace(fx(10, 1), timing=1), replace(fx(18, 5), timing=1)):
            with self.subTest(opcode=change.opcode, amount=change.parameter1, timing=change.timing):
                result = compiler.build_manifest({"POTN48.ITM": potion([fx(25, 6, parameter2=3), change, icon])})
                self.assertFalse(result["families"]["POTN48"]["hp"])
                self.assertFalse(result["sources"]["POTN48"]["keys"])
                self.assertEqual({}, result["sources"]["POTN48"]["nonBlockingKeys"])

    def test_hp_colors_are_nonblocking_with_preserved_range_and_alias_presentation(self):
        hp = replace(fx(18, 10), duration=300)
        color = replace(fx(7, 72, parameter2=255), duration=540)
        inputs = {"POTN09.ITM": potion([color, hp]),
                  "DW#PTN09.ITM": potion([hp, replace(color, parameter1=53, parameter2=6)])}
        result = compiler.build_manifest(inputs)
        for source, ordinal, values in (("POTN09", 0, (72, 255)), ("DW#PTN09", 1, (53, 6))):
            key, record = record_for(result, source, ordinal)
            self.assertEqual(values, (record["amount"], record["mode"]))
            self.assertEqual(540, record["duration"])
            self.assertEqual({key: True}, result["sources"][source]["nonBlockingKeys"])
        safe = compiler.build_manifest({"A.ITM": potion([color, fx(90, 40)])})
        self.assertIs(False, safe["sources"]["A"]["abilities"]["0"]["effects"]["0"])
        self.assertEqual({}, safe["sources"]["A"]["nonBlockingKeys"])

    def test_spell_level_immunity_is_boolean_and_hp_companion_with_real_index_bound(self):
        for level in (0, 1, 5, 9, 10, 0x7FFFFFFF):
            effect = fx(102, level)
            safe = compiler.build_manifest({"A.ITM": potion([effect])})
            self.assertEqual({}, safe["sources"]["A"]["keys"])
            hp = compiler.build_manifest({"A.ITM": potion([fx(18, 10), effect])})
            self.assertEqual(2 if level <= 9 else 1, len(hp["sources"]["A"]["keys"]))
            self.assertEqual({}, hp["sources"]["A"]["nonBlockingKeys"])
        self.fail_code("LEVEL_CAPABILITY", {"A.ITM": potion([fx(102, -1)])})

    def test_boolean_immunity_patterns_stay_native_and_hp_companions_remain_explicit(self):
        for opcode, amount, mode in ((101, 0, 5), (101, 0, 24), (169, 0, 22),
                                    (267, 8364, 5), (296, 0, 5)):
            with self.subTest(opcode=opcode, mode=mode):
                effect = fx(opcode, amount, parameter2=mode, resource="TESTVFX", special=7)
                data = potion([effect, fx(90, 40), effect])
                result = compiler.build_manifest({"A.ITM": data})
                source = result["sources"]["A"]
                self.assertEqual(1, len(source["keys"]))
                self.assertIs(False, source["abilities"]["0"]["effects"]["0"])
                self.assertIs(False, source["abilities"]["0"]["effects"]["2"])
                self.assertEqual(data, potion([effect, fx(90, 40), effect]))
                self.fail_code("HP_COMPANION_CAPABILITY", {"A.ITM": potion([fx(18, 10), effect])})
        # Decrementing or removal effects do not inherit this classification.
        for opcode in (201, 202, 221, 337):
            self.fail_code("OPCODE_CAPABILITY", {"A.ITM": potion([fx(opcode, 5)])})

    def test_mr_additive_and_hp_setter_preserve_fields_with_overflow_diagnostic(self):
        for amount in (-2147450880, -1, 0, 1, 50, 65537, 2147450880):
            with self.subTest(amount=amount):
                result = compiler.build_manifest({"POTN34.ITM": potion([fx(166, amount)])})
                self.assertEqual(amount > 0, bool(result["sources"]["POTN34"]["keys"]))
                if amount > 0:
                    self.assertEqual(amount, record_for(result, "POTN34")[1]["amount"])
        for amount in (-2147483648, 2147483647):
            self.fail_code("AMOUNT_CAPABILITY", {"A.ITM": potion([fx(166, amount)])})
        setter = fx(166, 50, parameter2=1)
        result = compiler.build_manifest({"A.ITM": potion([setter])})
        self.assertFalse(result["sources"]["A"]["keys"])
        result = compiler.build_manifest({"A.ITM": potion([setter, fx(18, 10)])})
        self.assertEqual(2, len(result["sources"]["A"]["keys"]))
        self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(166, 150, parameter2=2)])})

    def test_projectile_immunity_is_native_boolean_and_hp_mechanical_companion(self):
        for mode in (0, 1, 64, 65535, 65536, 0xFFFFFFFF):
            with self.subTest(mode=mode):
                effect = fx(83, -7, parameter2=mode, special=9)
                data = {"A.ITM": potion([effect, fx(), effect])}
                before = dict(data)
                result = compiler.build_manifest(data)
                source = result["sources"]["A"]
                self.assertEqual(1, len(source["keys"]))
                self.assertIs(False, source["abilities"]["0"]["effects"]["0"])
                self.assertIs(False, source["abilities"]["0"]["effects"]["2"])
                self.assertEqual(before, data)
                hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 10), effect, effect]),
                                               "DW#PTN09.ITM": potion([effect, effect])})
                for res, ordinal in (("POTN09", 1), ("DW#PTN09", 0)):
                    source = hp["sources"][res]
                    self.assertEqual(mode <= 65535, source["abilities"]["0"]["effects"][str(ordinal)] is not False)
                    self.assertFalse(source["nonBlockingKeys"])
                    if mode <= 65535:
                        key, record = record_for(hp, res, ordinal)
                        self.assertEqual((-7, mode, 9), (record["amount"], record["mode"], record["special"]))
                        self.assertEqual(2, source["abilities"]["0"]["quotas"][key])

    def test_fire_resistance_setter_uses_native_width_without_changing_raw_fields(self):
        for amount in (-2147483648, -65535, -129, -1, 0, 1, 100, 127, 128,
                       32767, 32768, 65535, 65536, 65537, 2147483647):
            with self.subTest(amount=amount):
                effect = fx(30, amount, parameter2=1)
                safe = compiler.build_manifest({"A.ITM": potion([effect, effect])})
                self.assertFalse(safe["sources"]["A"]["keys"])
                data = {"POTN09.ITM": potion([fx(18, 10), effect])}
                before = dict(data)
                hp = compiler.build_manifest(data)
                owned = 0 < (amount + 32768) % 65536 - 32768
                self.assertEqual(owned, hp["sources"]["POTN09"]["abilities"]["0"]["effects"]["1"] is not False)
                if owned:
                    self.assertEqual(amount, record_for(hp, "POTN09", 1)[1]["amount"])
                self.assertEqual(before, data)
        self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(30, 150, parameter2=2)])})

    def test_weapon_immunity_keeps_native_predicates_and_hp_boundary(self):
        for mode in (*range(13), 0xFFFFFFFF):
            for amount in (-1, 0, 3):
                with self.subTest(mode=mode, amount=amount):
                    ward = replace(fx(120, amount, parameter2=mode, special=17), target=2)
                    data = {"A.ITM": potion([ward, fx(), ward], [fx(), ward], ability_target=3)}
                    before = dict(data)
                    result = compiler.build_manifest(data)
                    source = result["sources"]["A"]
                    self.assertEqual(1, len(source["keys"]))
                    self.assertEqual(3, source["abilities"]["0"]["count"])
                    self.assertIs(False, source["abilities"]["0"]["effects"]["0"])
                    self.assertIs(False, source["abilities"]["0"]["effects"]["2"])
                    self.assertIs(False, source["abilities"]["1"]["effects"]["1"])
                    self.assertEqual(before, data)
                    self.fail_code("HP_COMPANION_CAPABILITY", {
                        "POTN09.ITM": potion([fx(18, 10), ward]),
                        "DW#PTN09.ITM": potion([ward]),
                    })

    def test_slashing_additive_preserves_raw_operands_order_aliases_and_other_effects(self):
        for amount in (1, 20, 25, 32667, 65537, -65535, -2147483647):
            with self.subTest(amount=amount):
                benefit = replace(fx(86, amount, special=7, resist_dispel=3),
                                  timing=10, duration=900, probability1=81, probability2=7)
                unrelated = [replace(fx(86, -1), timing=1), fx(19, -1), fx(139, 42)]
                data = {"POTN18.ITM": potion([benefit, *unrelated, benefit]),
                        "DW#PTN18.ITM": potion([*reversed(unrelated), benefit, benefit])}
                before = dict(data)
                result = compiler.build_manifest(data)
                key, record = record_for(result, "POTN18")
                self.assertEqual((amount, 0, 7, 3, 10, 900, 81, 7), tuple(record[k] for k in
                    ("amount", "mode", "special", "flags", "timing", "duration", "probUpper", "probLower")))
                for name in ("POTN18", "DW#PTN18"):
                    source = result["sources"][name]
                    self.assertEqual("POTN18", source["family"])
                    self.assertEqual({key: True}, source["keys"])
                    self.assertEqual({key: 2}, source["abilities"]["0"]["quotas"])
                    self.assertEqual(5, source["abilities"]["0"]["count"])
                self.assertEqual(before, data)
        # Equal effective LOW16 does not erase intentionally different raw fields.
        result = compiler.build_manifest({"A.ITM": potion([fx(86, 1), fx(86, 65537)])})
        self.assertEqual(2, len(result["sources"]["A"]["keys"]))
        hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 10), fx(86, 20)]),
                                      "DW#PTN09.ITM": potion([fx(86, 20)])})
        self.assertTrue(hp["families"]["POTN09"]["hp"])
        self.assertEqual("POTN09", hp["sources"]["DW#PTN09"]["family"])
        self.assertEqual(86, record_for(hp, "DW#PTN09")[1]["opcode"])

    def test_slashing_wrap_boundaries_diagnose_instead_of_claiming_adverse_or_positive(self):
        for amount in (0, 65536, -2147483648):
            result = compiler.build_manifest({"A.ITM": potion([fx(86, amount)])})
            self.assertFalse(result["sources"]["A"]["keys"])
        for amount in (-1, -32768, 32668, 32767, 32768, 65535, 2147483647):
            with self.subTest(amount=amount):
                self.fail_code("AMOUNT_CAPABILITY", {"A.ITM": potion([fx(86, amount)])})
                # The guard is only for finite owned classification; native
                # instant/permanent effects retain their existing behavior.
                result = compiler.build_manifest({"A.ITM": potion([
                    replace(fx(86, amount), timing=1), replace(fx(86, amount), duration=0)])})
                self.assertFalse(result["sources"]["A"]["keys"])
        for mode in (1, 2, 3, 0xFFFFFFFF):
            self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(86, 20, parameter2=mode)])})

    def test_slashing_linked_payload_keeps_original_spell_identity_and_shared_bytes(self):
        children = {"RESIST.SPL": container("SPL", groups=[[fx(86, 25), fx(19, -1)]])}
        link = replace(fx(146, 0, parameter2=1, resource="RESIST"), timing=1)
        data = {"POTN18.ITM": potion([link]), "DW#PTN18.ITM": potion([link])}
        before = dict(data, **children)
        result = compiler.build_manifest(data, read_resource=children.__getitem__)
        for name in ("POTN18", "DW#PTN18"):
            source = result["sources"][name]
            call = source["calls"]["RESIST"]["abilities"]["0"]
            self.assertIs(False, call["effects"]["1"])
            record = source["records"][call["effects"]["0"]]
            self.assertEqual((86, 25, 1, {"RESIST": True}),
                (record["opcode"], record["amount"], record["nativeSourceType"], record["nativeSources"]))
        self.assertEqual(before, dict(data, **children))

    def test_shared_linked_weapon_ward_stays_native_without_owning_shared_resource(self):
        ward = replace(fx(120, 0, parameter2=2, special=9), target=2)
        children = {"WARD.SPL": container("SPL", groups=[[ward, replace(fx(17, 9), timing=1)]])}
        link = replace(fx(146, 0, parameter2=1, resource="WARD"), timing=1)
        data = {"POTN11.ITM": potion([link]), "POTN36.ITM": potion([fx(), link])}
        before = dict(data, **children)
        result = compiler.build_manifest(data, read_resource=children.__getitem__)
        self.assertFalse(result["sources"]["POTN11"]["keys"])
        self.assertEqual(1, len(result["sources"]["POTN36"]["keys"]))
        self.assertNotIn("calls", result["sources"]["POTN36"])
        self.assertEqual(before, dict(data, **children))

    def test_shared_linked_fire_setter_is_native_but_hp_link_has_explicit_provenance(self):
        children = {"SPIN713.SPL": container("SPL", groups=[[fx(30, 100, parameter2=1),
                     replace(fx(141, 0), timing=1), replace(fx(61, 0), timing=1)]])}
        link = replace(fx(146, 0, parameter2=1, resource="SPIN713"), timing=1)
        data = {"WAND16.ITM": potion([link]), "POTN36.ITM": potion([fx(), link])}
        before = dict(data, **children)
        result = compiler.build_manifest(data, read_resource=children.__getitem__)
        self.assertFalse(result["sources"]["WAND16"]["keys"])
        self.assertEqual(1, len(result["sources"]["POTN36"]["keys"]))
        self.assertEqual(before, dict(data, **children))
        hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 10), link])},
                                     read_resource=children.__getitem__)
        source = hp["sources"]["POTN09"]
        self.assertTrue(hp["families"]["POTN09"]["hp"])
        call = source["calls"]["SPIN713"]
        record = source["records"][call["abilities"]["0"]["effects"]["0"]]
        self.assertEqual((record["opcode"], record["nativeSourceType"], record["nativeSources"]),
                         (30, 1, {"SPIN713": True}))

    def test_consumed_bounce_pool_is_not_misclassified_as_boolean_protection(self):
        for count in (-1, 0, 1, 6):
            for duplicate in (False, True):
                with self.subTest(count=count, duplicate=duplicate):
                    effect = fx(200, count, parameter2=1, resource="BTEST1B")
                    self.fail_code("OPCODE_CAPABILITY", {
                        "BTEST1.ITM": potion([effect] * (2 if duplicate else 1))})

    def test_native_states_setters_and_morale_cure_preserve_mixed_records(self):
        unrelated = [fx(63, 7, parameter2=3, special=9), fx(76, -1),
                     fx(106, 14, parameter2=1), fx(282, 1, parameter2=4),
                     replace(fx(23, -1, parameter2=0xFFFFFFFF), timing=3),
                     replace(fx(17, 100, parameter2=2), timing=1)]
        for target in (1, 2, 6, 9):
            with self.subTest(target=target):
                native = [replace(e, target=target) for e in unrelated]
                data = potion(native[:3] + [fx(90, 40)] + native[3:], ability_target=2, projectile=55)
                result = compiler.build_manifest({"A.ITM": data})
                source = result["sources"]["A"]
                self.assertEqual(1, len(source["keys"]))
                self.assertEqual([False, False, False, True, False, False, False],
                    [source["abilities"]["0"]["effects"][str(i)] is not False for i in range(7)])
                self.assertEqual(data, potion(native[:3] + [fx(90, 40)] + native[3:], ability_target=2, projectile=55))

    def test_movement_fixed_setters_remain_native_with_hp_and_cumulative_diagnostics(self):
        for mode in (1, 2):
            for amount in (-65535, -1, 0, 1, 100, 150, 256, 65535, 65536):
                with self.subTest(mode=mode, amount=amount):
                    setter = fx(126, amount, parameter2=mode)
                    data = {"POTN45.ITM": potion([replace(setter, target=9), fx(), setter])}
                    before = dict(data)
                    result = compiler.build_manifest(data)
                    source = result["sources"]["POTN45"]
                    self.assertEqual(1, len(source["keys"]))
                    self.assertIs(False, source["abilities"]["0"]["effects"]["0"])
                    self.assertIs(False, source["abilities"]["0"]["effects"]["2"])
                    self.assertEqual(before, data)
                    self.fail_code("HP_COMPANION_CAPABILITY", {"POTN09.ITM": potion([fx(18, 10), setter])})
        for mode in (0, 5):
            self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(126, 1, parameter2=mode)])})
        for mode in (3, 4, 6, 0xFFFFFFFF):
            result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), fx(126, 100, parameter2=mode)])})
            self.assertEqual(1, len(result["sources"]["A"]["keys"]))

    def test_proficiency_setters_are_native_or_hp_package_with_true_slot_bounds(self):
        for index in (0, 88, 89, 92, 99, 131, 134, 135, 65535, 65536, 0xFFFFFFFF):
            for amount in (-1, 0, 1, 2147483647):
                with self.subTest(index=index, amount=amount):
                    setter = fx(233, amount, parameter2=index, special=9)
                    safe = compiler.build_manifest({"POTN45.ITM": potion([setter])})
                    self.assertFalse(safe["sources"]["POTN45"]["keys"])
                    data = {"POTN09.ITM": potion([fx(18, 10), setter]),
                            "DW#PTN09.ITM": potion([setter])}
                    before = dict(data)
                    hp = compiler.build_manifest(data)
                    owned = 89 <= index <= 134
                    self.assertEqual(owned, bool(hp["sources"]["DW#PTN09"]["keys"]))
                    self.assertFalse(hp["sources"]["DW#PTN09"]["nonBlockingKeys"])
                    if owned:
                        record = record_for(hp, "DW#PTN09")[1]
                        self.assertEqual((amount, index, 9), (record["amount"], record["mode"], record["special"]))
                    self.assertEqual(before, data)
        for index in (89, 92, 99, 131, 134):
            self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(233, 1, parameter2=0x10000+index)])})

    def test_hp_state_setters_are_owned_after_family_resolution_but_cure_and_adverse_stay_native(self):
        hp = fx(18, 10)
        companions = [fx(63, 0), fx(106, -1, parameter2=1), fx(282, -1, parameter2=4)]
        data = {"POTN09.ITM": potion([hp, fx(76, 0), fx(23, 0)] + companions),
                "DW#PTN09.ITM": potion(list(reversed(companions)))}
        before = dict(data)
        result = compiler.build_manifest(data)
        self.assertTrue(result["families"]["POTN09"]["hp"])
        self.assertEqual(4, len(result["sources"]["POTN09"]["keys"]))
        self.assertEqual(3, len(result["sources"]["DW#PTN09"]["keys"]))
        self.assertEqual({}, result["sources"]["POTN09"]["nonBlockingKeys"])
        self.assertEqual(-1, record_for(result, "POTN09", 4)[1]["amount"])
        for ordinal in (1, 2):
            self.assertIs(False, result["sources"]["POTN09"]["abilities"]["0"]["effects"][str(ordinal)])
        self.assertEqual(before, data)
        for source in result["sources"].values():
            for record in source["records"].values():
                self.assertNotIn("nativeSourceType", record)
                self.assertNotIn("nativeSource", record)

    def test_scripting_state_bounds_and_unreviewed_morale_modes_remain_concrete(self):
        for state in (0, 4, 8, 44, 45, 0xFFFFFFFF):
            for amount in (-1, 0, 1, 2147483647):
                with self.subTest(state=state, amount=amount):
                    effect = fx(282, amount, parameter2=state)
                    result = compiler.build_manifest({"A.ITM": potion([fx(18, 10), effect])})
                    source = result["sources"]["A"]
                    self.assertEqual(state < 45, source["abilities"]["0"]["effects"]["1"] is not False)
                    if state < 45:
                        record = record_for(result, "A", 1)[1]
                        self.assertEqual((amount, state), (record["amount"], record["mode"]))
        for mode in (0, 2, 3):
            self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(106, 1, parameter2=mode)])})
        for mode in (0, 1, 2):
            for special in (1, 9):
                self.fail_code("MORALE_CAPABILITY", {"A.ITM": potion([fx(23, 1, parameter2=mode, special=special)])})

    def test_ordinary_invisibility_is_native_or_hp_owned_but_copy_modes_diagnose(self):
        for amount, special in ((0, 0), (-1, 9), (2147483647, 1)):
            effect = fx(20, amount, special=special)
            safe = compiler.build_manifest({"A.ITM": potion([effect])})
            self.assertFalse(safe["sources"]["A"]["keys"])
            hp = compiler.build_manifest({"POTN09.ITM": potion([fx(18, 10), effect]),
                                           "DW#PTN09.ITM": potion([effect])})
            self.assertEqual(2, len(hp["sources"]["POTN09"]["keys"]))
            self.assertEqual(1, len(hp["sources"]["DW#PTN09"]["keys"]))
            record = record_for(hp, "POTN09", 1)[1]
            self.assertEqual((20, amount, special), (record["opcode"], record["amount"], record["special"]))
            self.assertFalse(hp["sources"]["POTN09"]["nonBlockingKeys"])
        for mode in (1, 2, 0xFFFFFFFF):
            self.fail_code("MODE_CAPABILITY", {"A.ITM": potion([fx(20, 0, parameter2=mode)])})

    def test_reviewed_stat_setters_preserve_safe_native_and_own_complete_con_package(self):
        for opcode in (6, 15, 44, 49):
            result = compiler.build_manifest({"A.ITM": potion([fx(opcode, 21, parameter2=1),
                                                               fx(opcode, 150, parameter2=2)])})
            self.assertFalse(result["sources"]["A"]["keys"])
        result = compiler.build_manifest({"POTN10.ITM": potion([fx(10, 18, parameter2=1),
                                                                fx(44, 21, parameter2=1)])})
        self.assertTrue(result["families"]["POTN10"]["hp"])
        self.assertEqual(2, len(result["sources"]["POTN10"]["keys"]))
        for opcode in range(33, 38):
            result = compiler.build_manifest({"A.ITM": potion([fx(opcode, 2, parameter2=3)])})
            self.assertEqual(1, len(result["sources"]["A"]["keys"]))

    def test_shared_unowned_linked_cure_and_native_setter_stay_native(self):
        children = {"CURE.SPL": container("SPL", groups=[[replace(fx(11, 0), timing=1),
                                                          replace(fx(50, 9), timing=3)]]),
                    "SETTER.SPL": container("SPL", groups=[[fx(44, 21, parameter2=1), fx(142, 8)]])}
        link = lambda name: replace(fx(146, 0, resource=name), timing=1, duration=0)
        inputs = {"POTN04.ITM": potion([link("SETTER")]), "POTN56.ITM": potion([link("SETTER")]),
                  "POTN36.ITM": potion([fx(), link("CURE")]), "DW#PTN36.ITM": potion([link("CURE"), fx()])}
        before = dict(inputs, **children)
        result = compiler.build_manifest(inputs, read_resource=children.__getitem__)
        self.assertFalse(result["sources"]["POTN04"]["keys"])
        self.assertEqual(1, len(result["sources"]["DW#PTN36"]["keys"]))
        self.assertIs(False, result["sources"]["DW#PTN36"]["abilities"]["0"]["effects"]["0"])
        self.assertEqual(before, dict(inputs, **children))

    def test_linked_resource_guards_keep_native_conditions_in_entire_unowned_graph(self):
        for amount, mode in ((0, 0), (145, 111), (-1, 0xFFFFFFFF)):
            with self.subTest(amount=amount, mode=mode):
                guard = replace(fx(318, amount, parameter2=mode, resource="REGEN", special=9),
                                target=2, duration=6)
                removal = replace(fx(321, 0, resource="REGEN"), target=2, duration=0)
                damage = replace(fx(12, 7), target=2, timing=1)
                children = {"TROLL.SPL": container("SPL", groups=[[removal, guard, damage, guard]])}
                link = replace(fx(146, 0, resource="TROLL"), timing=1)
                inputs = {"POTN13.ITM": potion([link]), "POTN26.ITM": potion([link]),
                          "POTN36.ITM": potion([fx(), link]),
                          "DW#PTN36.ITM": potion([link, fx()])}
                before = dict(inputs, **children)
                result = compiler.build_manifest(inputs, read_resource=children.__getitem__)
                self.assertFalse(result["sources"]["POTN13"]["keys"])
                self.assertFalse(result["sources"]["POTN26"]["keys"])
                self.assertEqual(1, len(result["sources"]["POTN36"]["keys"]))
                self.assertIs(False, result["sources"]["DW#PTN36"]["abilities"]["0"]["effects"]["0"])
                self.assertEqual(before, dict(inputs, **children))

    def test_linked_resource_guard_does_not_hide_owned_child_or_hp_package(self):
        guard = fx(318, 0, resource="REGEN")
        link = replace(fx(146, 0, resource="TROLL"), timing=1)
        for child_effects, parent_effects, code in (
            ([guard, fx()], [link], "LINK_OWNED_CAPABILITY"),
            ([fx(), guard], [link], "LINK_OWNED_CAPABILITY"),
            ([guard], [fx(18, 10), link], "HP_COMPANION_CAPABILITY"),
            ([replace(guard, timing=3)], [link], "TIMING_CAPABILITY"),
            ([replace(guard, resource="")], [link], "OPCODE_CAPABILITY"),
        ):
            with self.subTest(code=code):
                children = {"TROLL.SPL": container("SPL", groups=[child_effects])}
                with self.assertRaises(compiler.ManifestError) as raised:
                    compiler.build_manifest({"A.ITM": potion(parent_effects)}, read_resource=children.__getitem__)
                self.assertEqual(code, raised.exception.code)
        # Direct protection (including the real145/111 HP case) has no new adapter.
        self.fail_code("OPCODE_CAPABILITY", {"POTN10.ITM": potion([
            fx(10, 18, parameter2=1), fx(318, 145, parameter2=111, resource="DW#HDANI")])})

    def test_linked_resource_guard_for_owned_canonical_or_alias_requires_explicit_policy(self):
        for protected in ("POTN36", "DW#PTN36"):
            with self.subTest(protected=protected):
                children = {"GUARD.SPL": container("SPL", groups=[[fx(318, 0, resource=protected)]])}
                link = replace(fx(146, 0, resource="GUARD"), timing=1)
                inputs = {"POTN36.ITM": potion([fx(), link]),
                          "DW#PTN36.ITM": potion([link, fx()])}
                before = dict(inputs, **children)
                with self.assertRaises(compiler.ManifestError) as raised:
                    compiler.build_manifest(inputs, read_resource=children.__getitem__)
                self.assertEqual("RESOURCE_GUARD_CAPABILITY", raised.exception.code)
                self.assertEqual(before, dict(inputs, **children))

    def test_linked_bonus_requires_child_provenance_and_177_uses_carrier_timing(self):
        children = {"BONUS.SPL": container("SPL", groups=[[fx()]]),
                    "BONUS.EFF": EffV2(opcode=90, target=1, parameter1=40, timing=1, duration=0).to_bytes()}
        for carrier in (fx(146, 0, resource="BONUS"), fx(177, 0, parameter2=2, resource="BONUS")):
            with self.subTest(opcode=carrier.opcode):
                with self.assertRaises(compiler.ManifestError) as raised:
                    compiler.build_manifest({"A.ITM": potion([carrier])}, read_resource=children.__getitem__)
                self.assertEqual("LINK_OWNED_CAPABILITY", raised.exception.code)
        children["BONUS.EFF"] = EffV2(opcode=90, target=1, parameter1=40, timing=0, duration=600).to_bytes()
        permanent = replace(fx(177, 0, parameter2=2, resource="BONUS"), timing=1, duration=0)
        result = compiler.build_manifest({"A.ITM": potion([permanent])}, read_resource=children.__getitem__)
        self.assertFalse(result["sources"]["A"]["keys"])

    def test_link_proof_diagnoses_missing_cycle_and_hp_companion_after_family_resolution(self):
        link = fx(146, 0, resource="CHILD")
        for children, code in (({}, "LINK_RESOURCE"),
                               ({"CHILD.SPL": container("SPL", groups=[[link]])}, "LINK_CYCLE")):
            with self.assertRaises(compiler.ManifestError) as raised:
                compiler.build_manifest({"A.ITM": potion([link])}, read_resource=children.__getitem__)
            self.assertEqual(code, raised.exception.code)
        children = {"CHILD.SPL": container("SPL", groups=[[fx(44, 21, parameter2=1)]])}
        with self.assertRaises(compiler.ManifestError) as raised:
            compiler.build_manifest({"POTN09.ITM": potion([fx(18, 110, parameter2=2), link])},
                                    read_resource=children.__getitem__)
        self.assertEqual("LINK_OWNED_CAPABILITY", raised.exception.code)

        children["CHILD.SPL"] = container("SPL", groups=[[fx(10, 18, parameter2=1)]])
        with self.assertRaises(compiler.ManifestError) as raised:
            compiler.build_manifest({"A.ITM": potion([link])}, read_resource=children.__getitem__)
        self.assertEqual("LINK_OWNED_CAPABILITY", raised.exception.code)

    def test_self_ability_projectile1_preserves_target2_native_record(self):
        thac0 = replace(fx(54, 90, parameter2=2), target=2)
        inputs = {"POTN09.ITM": potion([fx(18, 110, parameter2=2), thac0], projectile=1)}
        before = dict(inputs)
        result = compiler.build_manifest(inputs)
        self.assertEqual(2, record_for(result, "POTN09", ordinal=1)[1]["target"])
        self.assertEqual(before, inputs)
        for target, projectile in ((5, 0), (5, 2), (1, 1)):
            with self.subTest(target=target, projectile=projectile):
                self.fail_code("TARGET_CAPABILITY", {"A.ITM": potion([thac0],
                                                                      ability_target=target, projectile=projectile)})
        self.fail_code("TARGET_CAPABILITY", {"A.ITM": potion([replace(thac0, target=3)], projectile=1)})

    def test_duration_clamp_and_tick_mode(self):
        self.fail_code("DURATION_CAPABILITY", {"A.ITM": potion([replace(fx(), duration=0x08888889)])})
        for timing, duration in ((0, 0x08888888), (10, 0xFFFFFFFF)):
            result = compiler.build_manifest({"A.ITM": potion([replace(fx(), timing=timing, duration=duration)])})
            self.assertEqual(duration, record_for(result, "A")[1]["duration"])

    def test_unknown_identical_copies_require_identity_provenance(self):
        data = potion([fx()])
        text = self.fail_code("IDENTITY_AMBIGUITY", {"MODA.ITM": data, "MODB.ITM": data})
        self.assertIn("MODA", text)
        self.assertIn("MODB", text)
        result = compiler.build_manifest({"MODA.ITM": data, "MODB.ITM": potion([fx(92)])})
        self.assertEqual({"MODA", "MODB"}, set(result["families"]))

    def test_malformed_input_and_nonpotion_selection(self):
        self.fail_code("FORMAT", {"BAD.ITM": b"ITM V1  "})
        bad = bytearray(potion([fx()]))
        struct.pack_into("<I", bad, 0x6A, len(bad) + 100)
        self.fail_code("FORMAT", {"BAD.ITM": bad})
        self.fail_code("INPUT", {"POTN36.ITM": potion([fx()]), "potn36.itm": potion([fx()])})
        result = compiler.build_manifest({"SWORD.ITM": potion([replace(fx(), target=2)], category=1)})
        self.assertEqual({}, result["sources"])

    def test_repeat_compile_deterministic_and_lua_roundtrip(self):
        inputs = {"POTN36.ITM": potion([fx(), fx(139, 8)]), "POTN29.ITM": potion([fx(19, 4)])}
        before = dict(inputs)
        first = compiler.build_manifest(inputs, "except_genius")
        second = compiler.build_manifest(dict(reversed(list(inputs.items()))), "except_genius")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(before, inputs)
        lua = LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(compiler.lua_manifest(first))
        self.assertEqual("except_genius", result["policy"])
        self.assertTrue(result["families"]["POTN29"]["genius"])
        self.assertIs(False, result["sources"]["POTN36"]["abilities"]["0"]["effects"]["1"])
        escaped = 'quote" slash\\ newline\n nul\0 then123 unicode\u00e9'
        self.assertEqual(escaped, lua.execute(compiler.lua_manifest({"text": escaped}))["text"])

    def test_cli_reads_only_explicit_loose_inputs_and_prints_manifest(self):
        with tempfile.TemporaryDirectory(prefix="cbr-manifest-fixture-") as temp:
            root = Path(temp)
            (root / "POTN36.ITM").write_bytes(potion([fx()]))
            (root / "foreign.bin").write_bytes(b"unchanged")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            for output_format in ("json", "lua"):
                result = subprocess.run([sys.executable, "-B", str(COMPILER), "--resources", str(root),
                                         "--format", output_format], capture_output=True, text=True, check=False)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stderr)
                parsed = json.loads(result.stdout) if output_format == "json" else LuaRuntime().execute(result.stdout)
                self.assertEqual("POTN36", parsed["sources"]["POTN36"]["family"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


if __name__ == "__main__":
    unittest.main()
