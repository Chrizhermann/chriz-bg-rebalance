"""Opt-in real-resource to real-Lua runtime integration for selected potions.

Set CBR_POTION_RUNTIME_ROOTS to explicit read-only game roots separated by
os.pathsep. Native construction/admission/insertion/save copy are test doubles;
this is replacement-specific compatibility evidence, never game acceptance.
No original resources, saves or installed files are written or copied to disk.
"""
from __future__ import annotations

import os
from pathlib import Path
import unittest

from tests.potion_runtime_fixture import ResourceRuntimeFixture
from tests.test_potion_admission_manifest import compiler


ROOTS = [Path(root) for root in os.environ.get("CBR_POTION_RUNTIME_ROOTS", "").split(os.pathsep) if root]
CANONICAL = ("POTN09", "POTN29", "POTN36", "POTN37", "POTN39", "POTN41")


@unittest.skipUnless(ROOTS, "set explicit CBR_POTION_RUNTIME_ROOTS for read-only captured integration")
class CapturedPotionRuntimeTests(unittest.TestCase):
    def test_canonical_and_present_scs_orders_both_policies_and_saved_fields(self):
        for root in ROOTS:
            self.assertTrue(root.is_absolute() and root.is_dir(), str(root))
            store = compiler.audit.ResourceStore(root, game=(root / "chitin.key").is_file())
            names = set(store.names())
            resources = {}
            for canonical in CANONICAL:
                name = canonical + ".ITM"
                self.assertIn(name, names, f"missing explicitly requested reference resource: {root}/{name}")
                resources[name] = store.read(name)
                alias = "DW#PTN" + canonical[4:] + ".ITM"
                if alias in names:
                    resources[alias] = store.read(alias)
            for policy in ("unique", "except_genius"):
                for canonical in CANONICAL:
                    alias = "DW#PTN" + canonical[4:]
                    pairs = [(canonical, canonical)]
                    if alias + ".ITM" in resources:
                        pairs += [(canonical, alias), (alias, canonical)]
                    for first, second in pairs:
                        for roundtrip in (False, True):
                            with self.subTest(root=str(root), policy=policy, first=first,
                                              second=second, saved_fields=roundtrip):
                                f = ResourceRuntimeFixture(resources, policy, read_resource=store.read)
                                self.assertTrue(all(f.deliver(f.queue(first))))
                                if roundtrip:
                                    f.saved_active_roundtrip()
                                before = {pointer: f.bytes(pointer) for pointer in f.effects()}
                                f.now += 30
                                queued = f.queue(second)
                                outcome = f.deliver(queued)
                                source = f.manifest["sources"][second]
                                family = f.manifest["families"][source["family"]]
                                exempt = policy == "except_genius" and family["genius"]
                                owned = source["abilities"]["0"]["effects"]
                                for ordinal, allowed in enumerate(outcome):
                                    self.assertEqual(exempt or owned[str(ordinal)] is False, allowed)
                                if family["hp"] or exempt:
                                    self.assertEqual([], f.writes)
                                else:
                                    self.assertEqual(sum(key is not False for key in owned.values()), len(f.writes))
                                # Only expiry can differ in preexisting native effects.
                                for pointer, old in before.items():
                                    new = f.bytes(pointer)
                                    self.assertEqual(old[:0x28] + old[0x2C:], new[:0x28] + new[0x2C:])
                                self.assertEqual([], f.diagnostics)
            for name, original in resources.items():
                self.assertEqual(original, store.read(name), f"reference resource changed: {root}/{name}")


if __name__ == "__main__":
    unittest.main()
