"""Physical-resistance compiler fixtures; native arithmetic is a separate probe.

Successful manifests must match Python/Lua completely. Rejected inputs retain
their exact bytes and concrete capability diagnostics; no partial coverage is
claimed for adverse operands whose native WORD arithmetic can reverse polarity.
"""
from dataclasses import replace
import unittest

from lupa.luajit21 import LuaError
from tests.test_potion_admission_manifest import compiler, fx, potion, record_for
from tests.test_potion_admission_lua_compiler import LuaCompiler
from tests.test_potion_payload_audit import container


class PotionResistance878889Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()

    def compile(self, items, policy="unique", spells=None):
        original = {k: bytes(v) for k, v in items.items()}
        children = {k: bytes(v) for k, v in (spells or {}).items()}
        reader = None if spells is None else spells.__getitem__
        result = compiler.build_manifest(items, policy, read_resource=reader)
        self.assertEqual(result, self.port.build(items, policy, read_resource=reader))
        self.assertEqual(original, items)
        self.assertEqual(children, spells or {})
        return result

    def reject(self, code, items, spells=None):
        original = {k: bytes(v) for k, v in items.items()}
        children = {k: bytes(v) for k, v in (spells or {}).items()}
        reader = None if spells is None else spells.__getitem__
        with self.assertRaises(compiler.ManifestError) as caught:
            compiler.build_manifest(items, read_resource=reader)
        self.assertEqual(code, caught.exception.code)
        with self.assertRaisesRegex(LuaError, code + ":"):
            self.port.build(items, read_resource=reader)
        self.assertEqual(original, items)
        self.assertEqual(children, spells or {})
        return str(caught.exception)

    def test_reviewed_effective_positive_range_and_raw_aliases_both_policies(self):
        for opcode in (87, 88, 89):
            for amount in (-65535, -32869, 1, 20, 25, 100, 32667, 65537, 98203):
                for policy in ("unique", "except_genius"):
                    with self.subTest(opcode=opcode, amount=amount, policy=policy):
                        result = self.compile({"POTN18.ITM": potion([fx(opcode, amount)])}, policy)
                        key, record = record_for(result, "POTN18")
                        self.assertEqual({key: 1}, result["sources"]["POTN18"]["abilities"]["0"]["quotas"])
                        self.assertEqual((opcode, amount), (record["opcode"], record["amount"]))

    def test_upper_wrap_and_negative_underflow_are_explicit_diagnostics(self):
        for opcode in (87, 88, 89):
            for amount in (-1, -128, -32768, 32668, 32767, 32768, 65535, 98204, 2147483647):
                with self.subTest(opcode=opcode, amount=amount):
                    error = self.reject("AMOUNT_CAPABILITY", {"POTN18.ITM": bytearray(potion([fx(opcode, amount)]))})
                    self.assertIn("WORD", error)
                    self.assertIn("wrap", error)

    def test_zero_effective_values_remain_native_with_unrelated_targets(self):
        for opcode in (87, 88, 89):
            records = [replace(fx(opcode, amount), target=6) for amount in (0, 65536, -65536, -2147483648)]
            result = self.compile({"POTN18.ITM": potion(records)})
            source = result["sources"]["POTN18"]
            self.assertEqual({}, source["keys"])
            self.assertEqual([False] * 4, list(source["abilities"]["0"]["effects"].values()))

    def test_distinct_raw_aliases_keep_separate_fingerprints(self):
        for opcode in (87, 88, 89):
            result = self.compile({"POTN18.ITM": potion([fx(opcode, n) for n in (1, 65537, -65535)])})
            records = result["sources"]["POTN18"]["records"]
            self.assertEqual(3, len(records))
            self.assertEqual({1, 65537, -65535}, {record["amount"] for record in records.values()})

    def test_hp_companions_are_mechanical_and_family_wide(self):
        benefit = [fx(opcode, 20) for opcode in (87, 88, 89)]
        result = self.compile({"POTN09.ITM": potion([fx(18, 110, parameter2=2), *benefit]),
                               "DW#PTN09.ITM": potion(list(reversed(benefit)))})
        self.assertTrue(result["families"]["POTN09"]["hp"])
        source = result["sources"]["DW#PTN09"]
        self.assertEqual("POTN09", source["family"])
        self.assertEqual(3, len(source["keys"]))
        self.assertEqual({}, source["nonBlockingKeys"])
        for opcode in (87, 88, 89):
            self.reject("AMOUNT_CAPABILITY", {"POTN09.ITM": potion([fx(18, 110, parameter2=2), fx(opcode, -1)])})

    def test_reordered_scs_copies_duplicate_records_and_multiple_abilities(self):
        owned = [fx(87, 20), fx(88, 20), fx(89, 25), fx(87, 20)]
        native = [replace(fx(17, 5), timing=1, target=6), fx(139, 99), fx(19, -1)]
        inputs = {"POTN18.ITM": potion([*owned, *native], list(reversed(owned))),
                  "DW#PTN18.ITM": potion([*reversed(native), *reversed(owned)], owned)}
        for policy in ("unique", "except_genius"):
            result = self.compile(inputs, policy)
            source = result["sources"]["POTN18"]
            alias = result["sources"]["DW#PTN18"]
            self.assertEqual("POTN18", alias["family"])
            self.assertEqual(source["keys"], alias["keys"])
            self.assertEqual([False] * 3, [source["abilities"]["0"]["effects"][str(i)] for i in (4, 5, 6)])
            for ability in source["abilities"].values():
                self.assertEqual([1, 1, 2], sorted(ability["quotas"].values()))
            self.assertEqual(result, self.compile(inputs, policy))

    def test_linked_and_shared_payloads_keep_native_spell_identity(self):
        def cast(name):
            return replace(fx(146, 0, parameter2=1, resource=name), timing=1)

        for amount, seconds in ((20, 300), (25, 60)):
            payload = container("SPL", groups=[[replace(fx(opcode, amount), duration=seconds)
                                                 for opcode in (87, 88, 89)]])
            result = self.compile({"POTN18.ITM": potion([cast("WARD"), cast("WARD")]),
                                   "DW#PTN18.ITM": potion([cast("ALIAS"), cast("ALIAS")])},
                                  spells={"WARD.SPL": payload, "ALIAS.SPL": payload})
            for res, native in (("POTN18", "WARD"), ("DW#PTN18", "ALIAS")):
                source = result["sources"][res]
                self.assertEqual("POTN18", source["family"])
                self.assertEqual([2, 2, 2], sorted(source["abilities"]["0"]["quotas"].values()))
                for record in source["records"].values():
                    self.assertEqual((amount, seconds, 1, {native: True}),
                                     (record["amount"], record["duration"], record["nativeSourceType"], record["nativeSources"]))

    def test_remaining_linked_guard_is_not_silently_omitted(self):
        cast = replace(fx(146, 0, parameter2=1, resource="WARD"), timing=1)
        payload = container("SPL", groups=[[fx(opcode, 20) for opcode in (87, 88, 89)]
                                           + [fx(206, -1, resource="WARD")]])
        self.reject("OPCODE_CAPABILITY", {"POTN18.ITM": potion([cast])}, {"WARD.SPL": payload})

    def test_instant_permanent_and_zero_duration_preserve_all_operands(self):
        for opcode in (87, 88, 89):
            records = [replace(fx(opcode, amount), timing=timing)
                       for amount in (-1, 32668, 32768, 65537) for timing in (1, 2, 4, 7, 8, 9)]
            records += [replace(fx(opcode, -1), duration=0)]
            result = self.compile({"POTN18.ITM": potion(records)})
            self.assertEqual({}, result["sources"]["POTN18"]["keys"])

    def test_unreviewed_setter_and_percentage_modes_remain_diagnostic(self):
        for opcode in (87, 88, 89):
            for mode in (1, 2, 3, 0xFFFFFFFF):
                self.reject("MODE_CAPABILITY", {"POTN18.ITM": potion([fx(opcode, 20, parameter2=mode)])})

    def test_owned_transport_and_delay_capabilities_are_not_weakened(self):
        for opcode in (87, 88, 89):
            self.reject("TARGET_CAPABILITY", {"POTN18.ITM": potion([replace(fx(opcode, 20), target=6)])})
            self.reject("TIMING_CAPABILITY", {"POTN18.ITM": potion([replace(fx(opcode, 20), timing=3)])})
            result = self.compile({"POTN18.ITM": potion([replace(fx(opcode, 20), timing=10)])})
            self.assertEqual(10, record_for(result, "POTN18")[1]["timing"])

    def test_original_conditions_and_native_non_dice_fields_are_retained(self):
        for opcode in (87, 88, 89):
            original = fx(opcode, 65556, power=3, special=29, probability1=81, probability2=7,
                          save_type=3, save_bonus=-7, dice_number=17, dice_size=-1)
            result = self.compile({"POTN18.ITM": potion([original], school=4, secondary=9,
                                                       source_flags=0x80001234)})
            record = record_for(result, "POTN18")[1]
            expected = dict(opcode=opcode, amount=65556, power=3, special=29, probUpper=81,
                            probLower=7, saveType=3, saveBonus=-7, diceCount=0, diceSize=0,
                            maxLevel=17, minLevel=0, school=4, secondary=9, sourceFlags=0x80001234)
            self.assertEqual(expected, {field: record[field] for field in expected})


if __name__ == "__main__":
    unittest.main()
