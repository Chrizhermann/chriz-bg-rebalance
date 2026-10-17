"""Whole ITM/manifest/Lua-reader/runtime checks; native services are doubled."""
from dataclasses import replace
import unittest

from tests.potion_runtime_fixture import ResourceRuntimeFixture
from tests.test_potion_admission_manifest import fx, potion


class PotionResourceRuntimeTests(unittest.TestCase):
    def safe_resources(self):
        pick, lock = fx(90, 40), fx(92, 30)
        heal, adverse = replace(fx(17, 8), timing=1), fx(19, -1)
        return {"POTN36.ITM": potion([pick, heal, adverse, lock], [lock, adverse, heal, pick]),
                "DW#PTN36.ITM": potion([lock, heal, pick, adverse])}

    def test_whole_mixed_doses_refresh_both_alias_orders_and_keep_unowned(self):
        resources = self.safe_resources()
        original = dict(resources)
        for first, second in (("POTN36", "DW#PTN36"), ("DW#PTN36", "POTN36")):
            with self.subTest(first=first):
                f = ResourceRuntimeFixture(resources)
                self.assertTrue(all(f.deliver(f.queue(first))))
                old = {p: f.bytes(p) for p in f.effects()}
                f.now += 75
                repeat = f.deliver(list(reversed(f.queue(second))))
                self.assertEqual(2, sum(repeat))  # Instant heal and adverse record still admitted.
                self.assertEqual(2, len(f.writes))
                for p, before in old.items():
                    after = f.bytes(p)
                    self.assertEqual(before[:0x28] + before[0x2C:], after[:0x28] + after[0x2C:])
                    if f.read(p + 0x10, "I") in (90, 92):
                        self.assertEqual(1000 + 75 + 600 * 15, f.read(p + 0x28, "I"))
                self.assertEqual(original, resources)

    def test_hp_family_subset_alias_first_blocks_whole_canonical_without_writes(self):
        hp, thac0 = fx(18, 110, parameter2=2), fx(54, 90, parameter2=2)
        resources = {"POTN09.ITM": potion([hp, thac0]), "DW#PTN09.ITM": potion([thac0])}
        for first, second in (("POTN09", "DW#PTN09"), ("DW#PTN09", "POTN09")):
            with self.subTest(first=first):
                f = ResourceRuntimeFixture(resources)
                self.assertTrue(all(f.deliver(f.queue(first))))
                before = {p: f.bytes(p) for p in f.effects()}
                f.now += 100
                self.assertFalse(any(f.deliver(f.queue(second))))
                self.assertEqual(before, {p: f.bytes(p) for p in f.effects()})
                self.assertEqual([], f.writes)
                for p in list(f.effects()):
                    f.remove(p)
                self.assertTrue(all(f.deliver(f.queue(second))))

    def test_selective_native_rejection_does_not_refresh_rejected_record(self):
        f = ResourceRuntimeFixture(self.safe_resources())
        f.deliver(f.queue("POTN36"))
        old = {f.read(p + 0x10, "I"): p for p in f.effects()}
        f.now += 10
        f.deliver(f.queue("DW#PTN36"), rejected_ordinals={0})  # Alias lock save failed.
        self.assertEqual(10000, f.read(old[92] + 0x28, "I"))
        self.assertEqual(10010, f.read(old[90] + 0x28, "I"))
        self.assertEqual(1, len(f.writes))

    def test_hp_alias_icons_do_not_extend_or_outlive_the_mechanical_repeat_lock(self):
        hp = replace(fx(18, 110, parameter2=2), duration=300)
        icon = replace(fx(142, 0, parameter2=9), duration=540)
        alias_icon = replace(icon, parameter2=10)
        resources = {"POTN09.ITM": potion([icon, hp]),
                     "DW#PTN09.ITM": potion([hp, alias_icon])}
        for first, second in (("POTN09", "DW#PTN09"), ("DW#PTN09", "POTN09")):
            with self.subTest(first=first):
                f = ResourceRuntimeFixture(resources)
                self.assertEqual([True, True], f.deliver(f.queue(first)))
                before = {p: f.bytes(p) for p in f.effects()}
                self.assertEqual([False, False], f.deliver(f.queue(second)))
                self.assertEqual(before, {p: f.bytes(p) for p in f.effects()})
                f.saved_active_roundtrip()
                for p in list(f.effects()):
                    if f.read(p + 0x10, "I") == 18:
                        f.remove(p)  # Native dispel/expiry service remains doubled.
                self.assertEqual([True, True], f.deliver(f.queue(second)))
                self.assertEqual([], f.writes)

    def test_saved_native_fields_recognize_safe_and_hp_packages_without_tokens(self):
        for opcode, amount, mode in ((90, 40, 0), (18, 110, 2)):
            with self.subTest(opcode=opcode):
                f = ResourceRuntimeFixture({"POTN09.ITM": potion([fx(opcode, amount, parameter2=mode)])})
                f.deliver(f.queue("POTN09"))
                f.saved_active_roundtrip()
                pointer = f.effects()[0]
                self.assertEqual(0, f.read(pointer + 0x110, "I"))
                self.assertFalse(any(f.deliver(f.queue("POTN09"))))
                self.assertEqual(1 if opcode == 90 else 0, len(f.writes))

    def test_alternative_ability_order_and_duplicate_effect_quota(self):
        same = fx(90, 20)
        resources = {"POTN36.ITM": potion([same, same, fx(92, 30)], [fx(92, 30), same, same])}
        f = ResourceRuntimeFixture(resources)
        self.assertEqual([True] * 3, f.deliver(f.queue("POTN36")))
        old = f.effects()
        self.assertEqual([False] * 3, f.deliver(f.queue("POTN36", 1)))
        self.assertEqual(old, f.effects())
        self.assertEqual(3, len({address for address, _, _ in f.writes}))

    def test_genius_exception_does_not_exempt_other_intelligence_potion(self):
        resources = {"POTN29.ITM": potion([fx(19, 4)]), "POTN37.ITM": potion([fx(19, 3)])}
        for policy in ("unique", "except_genius"):
            with self.subTest(policy=policy):
                f = ResourceRuntimeFixture(resources, policy)
                for source in ("POTN29", "POTN37"):
                    self.assertEqual([True], f.deliver(f.queue(source)))
                    self.assertEqual([source == "POTN29" and policy == "except_genius"],
                                     f.deliver(f.queue(source)))

    def test_interleaved_queued_uses_do_not_conflate_same_tick_doses(self):
        f = ResourceRuntimeFixture(self.safe_resources())
        first, second = f.queue("POTN36"), f.queue("DW#PTN36")
        f.deliver([first[0], second[0], first[3], second[2]])
        self.assertEqual(2, len(f.effects()))
        self.assertEqual(2, len(f.writes))


if __name__ == "__main__":
    unittest.main()
