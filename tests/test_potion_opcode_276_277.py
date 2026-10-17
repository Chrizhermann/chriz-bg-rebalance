"""Compiler preservation/policy fixtures, not native admission or live proof.

Native constructor, Apply, expiry and arithmetic evidence is independently
executed by probe_native_skill_276_277.py. Every successful fixture here checks
the complete Python/Lua manifests and leaves all original resource bytes intact.
"""
from dataclasses import replace
import unittest

from lupa.luajit21 import LuaError
from tests.test_potion_admission_manifest import compiler, fx, potion, record_for
from tests.test_potion_admission_lua_compiler import LuaCompiler
from tests.test_potion_payload_audit import container


class PotionSkill276277Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()

    def compile(self, items, policy="unique", spells=None):
        before = {k: bytes(v) for k, v in items.items()}
        spells_before = {k: bytes(v) for k, v in (spells or {}).items()}
        reader = None if spells is None else spells.__getitem__
        result = compiler.build_manifest(items, policy, read_resource=reader)
        self.assertEqual(result, self.port.build(items, policy, read_resource=reader))
        self.assertEqual(before, items)
        self.assertEqual(spells_before, spells or {})
        return result

    def reject(self, code, items):
        before = {k: bytes(v) for k, v in items.items()}
        with self.assertRaises(compiler.ManifestError) as caught:
            compiler.build_manifest(items)
        self.assertEqual(code, caught.exception.code)
        with self.assertRaisesRegex(LuaError, code + ":"):
            self.port.build(items)
        self.assertEqual(before, items)

    def test_additive_low16_polarity_preserves_raw_amounts_both_policies(self):
        # Expected native values are explicit boundary observations, including
        # negative raw dwords whose LOW16 is a positive skill bonus.
        cases = {-2147483648: False, -65535: True, -1: False, 0: False,
                 1: True, 20: True, 32767: True, 32768: False, 65535: False,
                 65536: False, 65537: True, 2147483647: False}
        for opcode in (276, 277):
            for amount, owned in cases.items():
                for policy in ("unique", "except_genius"):
                    with self.subTest(opcode=opcode, amount=amount, policy=policy):
                        result = self.compile({"POTN39.ITM": potion([fx(opcode, amount)])}, policy)
                        source = result["sources"]["POTN39"]
                        key = source["abilities"]["0"]["effects"]["0"]
                        self.assertEqual(owned, key is not False)
                        self.assertEqual({key: 1} if owned else {}, source["abilities"]["0"]["quotas"])
                        self.assertFalse(result["families"]["POTN39"]["genius"])
                        if owned:
                            self.assertEqual(amount, source["records"][key]["amount"])

    def test_different_raw_encodings_do_not_collapse_logical_fingerprints(self):
        for opcode in (276, 277):
            with self.subTest(opcode=opcode):
                result = self.compile({"POTN39.ITM": potion([fx(opcode, n) for n in (1, 65537, -65535)])})
                source = result["sources"]["POTN39"]
                self.assertEqual(3, len(source["keys"]))
                self.assertEqual({1, 65537, -65535}, {r["amount"] for r in source["records"].values()})
                self.assertEqual([1, 1, 1], sorted(source["abilities"]["0"]["quotas"].values()))

    def test_native_low8_setters_owned_only_as_positive_hp_companions(self):
        for opcode in (276, 277):
            for amount, hp_owned in ((-1, True), (0, False), (1, True), (255, True),
                                     (256, False), (32768, False), (65537, True)):
                for hp in (False, True):
                    with self.subTest(opcode=opcode, amount=amount, hp=hp):
                        records = [fx(opcode, amount, parameter2=1)]
                        if hp:
                            records.append(fx(18, 110, parameter2=2))
                        result = self.compile({"POTN09.ITM": potion(records)})
                        source = result["sources"]["POTN09"]
                        key = source["abilities"]["0"]["effects"]["0"]
                        self.assertEqual(hp and hp_owned, key is not False)
                        self.assertEqual(hp, result["families"]["POTN09"]["hp"])
                        if key:
                            self.assertEqual(amount, source["records"][key]["amount"])
                            self.assertNotIn(key, source["nonBlockingKeys"])

    def test_base_derived_percentages_do_not_become_safe_repeat_bonuses(self):
        for opcode in (276, 277):
            for amount, hp_owned in ((-1, False), (0, False), (100, False), (101, True),
                                     (150, True), (32767, True), (32768, False),
                                     (65536, False), (65686, True)):
                for hp in (False, True):
                    with self.subTest(opcode=opcode, amount=amount, hp=hp):
                        records = [fx(opcode, amount, parameter2=2)]
                        if hp:
                            records.append(fx(18, 110, parameter2=2))
                        result = self.compile({"POTN41.ITM": potion(records)})
                        source = result["sources"]["POTN41"]
                        key = source["abilities"]["0"]["effects"]["0"]
                        self.assertEqual(hp and hp_owned, key is not False)
                        if key:
                            self.assertEqual(amount, source["records"][key]["amount"])

    def test_reordered_clones_multiple_abilities_and_unrelated_records(self):
        first, second = fx(276, 20), fx(277, 35)
        unrelated = [replace(fx(17, 5), timing=1, target=6), fx(276, -1), fx(139, 99)]
        inputs = {"POTN39.ITM": potion([first, *unrelated, second], [second, first]),
                  "DW#PTN39.ITM": potion([second, first, *reversed(unrelated)], [first, second])}
        for policy in ("unique", "except_genius"):
            result = self.compile(inputs, policy)
            source = result["sources"]["POTN39"]
            alias = result["sources"]["DW#PTN39"]
            self.assertEqual("POTN39", alias["family"])
            self.assertEqual(source["keys"], alias["keys"])
            self.assertEqual([False] * 3, [source["abilities"]["0"]["effects"][str(i)] for i in (1, 2, 3)])
            self.assertEqual([5, 2], [a["count"] for a in source["abilities"].values()])
            self.assertEqual([1, 1], sorted(source["abilities"]["1"]["quotas"].values()))
            self.assertEqual(result, self.compile(inputs, policy))

    def test_same_skill_payload_in_distinct_potion_anchors_stays_distinct(self):
        result = self.compile({"POTN36.ITM": potion([fx(277, 20)]),
                               "POTN39.ITM": potion([fx(277, 20)])})
        self.assertEqual("POTN36", result["sources"]["POTN36"]["family"])
        self.assertEqual("POTN39", result["sources"]["POTN39"]["family"])

    def test_linked_aliases_keep_original_spell_sources_and_shared_counts(self):
        def cast(name):
            return replace(fx(146, 0, parameter2=1, resource=name), timing=1)

        payload = container("SPL", groups=[[fx(276, 20), fx(277, 20), fx(277, -1),
                                           replace(fx(17, 5), timing=1)]])
        items = {"POTN39.ITM": potion([cast("SKILLS"), cast("SKILLS")]),
                 "DW#PTN39.ITM": potion([cast("ALIAS"), cast("ALIAS")])}
        result = self.compile(items, spells={"SKILLS.SPL": payload, "ALIAS.SPL": payload})
        for res, child in (("POTN39", "SKILLS"), ("DW#PTN39", "ALIAS")):
            source = result["sources"][res]
            self.assertEqual("POTN39", source["family"])
            self.assertEqual([2, 2], sorted(source["abilities"]["0"]["quotas"].values()))
            self.assertEqual([False, False], [source["calls"][child]["abilities"]["0"]["effects"][str(i)]
                                             for i in (2, 3)])
            for record in source["records"].values():
                self.assertEqual(1, record["nativeSourceType"])
                self.assertEqual({child: True}, record["nativeSources"])

    def test_permanent_instant_and_zero_duration_gains_remain_native(self):
        for opcode in (276, 277):
            records = [replace(fx(opcode, 65537), timing=t) for t in (1, 2, 4, 7, 8, 9)]
            records += [replace(fx(opcode, 20), duration=0)]
            result = self.compile({"POTN39.ITM": potion(records)})
            source = result["sources"]["POTN39"]
            self.assertFalse(source["keys"])
            self.assertEqual([False] * len(records), list(source["abilities"]["0"]["effects"].values()))

    def test_unreviewed_modes_keep_a_concrete_diagnostic(self):
        for opcode in (276, 277):
            for mode in (3, 65536, 0xFFFFFFFF):
                with self.subTest(opcode=opcode, mode=mode):
                    self.reject("MODE_CAPABILITY", {"POTN39.ITM": potion([fx(opcode, 20, parameter2=mode)])})

    def test_owned_delivery_and_lifetime_guards_are_not_weakened(self):
        for opcode in (276, 277):
            self.reject("TARGET_CAPABILITY", {"POTN39.ITM": potion([replace(fx(opcode, 20), target=6)])})
            self.reject("TIMING_CAPABILITY", {"POTN39.ITM": potion([replace(fx(opcode, 20), timing=3)])})
            result = self.compile({"POTN39.ITM": potion([replace(fx(opcode, -1), target=6)])})
            self.assertFalse(result["sources"]["POTN39"]["keys"])

    def test_original_runtime_fields_and_native_non_dice_normalization(self):
        for opcode in (276, 277):
            record = fx(opcode, 65556, special=29, power=7, probability1=73, probability2=4,
                        save_type=5, save_bonus=-3, dice_number=17, dice_size=-1)
            result = self.compile({"POTN39.ITM": potion([record], school=3, secondary=7,
                                                       source_flags=0x80001234)})
            _, native = record_for(result, "POTN39")
            expected = dict(opcode=opcode, amount=65556, special=29, power=7, probUpper=73,
                            probLower=4, saveType=5, saveBonus=-3, diceCount=0, diceSize=0,
                            maxLevel=17, minLevel=0, school=3, secondary=7, sourceFlags=0x80001234)
            self.assertEqual(expected, {name: native[name] for name in expected})


if __name__ == "__main__":
    unittest.main()
