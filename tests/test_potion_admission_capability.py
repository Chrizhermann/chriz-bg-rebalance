"""Replacement-specific capability audit fixtures; no WeiDU or game execution."""
from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
import unittest

from tests.test_potion_admission_manifest import fx, potion
from tests.test_potion_payload_audit import container

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/prototypes/potion-admission"))
import audit_admission_capability as capability


class PotionAdmissionCapabilityTests(unittest.TestCase):
    def run_inventory(self, blobs, **kwargs):
        before = dict(blobs)
        def read(name):
            if name not in blobs:
                raise FileNotFoundError(name)
            return blobs[name]
        result = capability.inventory(blobs, read, **kwargs)
        self.assertEqual(before, blobs)
        return result

    def test_direct_owned_native_only_and_unsupported_are_separate(self):
        report = self.run_inventory({"POTN36.ITM": potion([fx()]),
                                     "POTN14.ITM": potion([fx(16, 0)]),
                                     "POTN47.ITM": potion([fx(98, 1)])})
        self.assertEqual({"direct_owned": 1, "native_only": 1, "unsupported": 1}, report["counts"])
        self.assertEqual("unsupported", report["global_checks"]["whole_profile"]["status"])
        self.assertEqual("passed", report["global_checks"]["locally_compilable_subset"]["status"])
        self.assertEqual([{"code": "OPCODE_CAPABILITY", "opcode": 98, "records": 1}],
                         report["missing_direct_adapters"])

    def test_ordered_scs_hp_alias_core_replay_in_both_orders(self):
        thac0 = fx(54, 90, parameter2=2)
        report = self.run_inventory({"POTN09.ITM": potion([fx(18, 110, parameter2=2), thac0]),
                                     "DW#PTN09.ITM": potion([thac0])})
        orders = report["canonical_scs_orders"]
        self.assertEqual(4, len(orders))
        for order in orders:
            self.assertEqual("passed", order["status"])
            second = [event for event in order["events"] if event["dose"] == 2]
            self.assertTrue(second)
            self.assertTrue(all(event["reason"] == "hp-repeat" and not event["allow"]
                                and event["writes"] == 0 for event in second))

    def test_safe_scs_mismatch_reported_before_claiming_order_coverage(self):
        report = self.run_inventory({"POTN36.ITM": potion([fx()]), "DW#PTN36.ITM": potion([fx(amount=41)])})
        order = report["canonical_scs_orders"][0]
        self.assertEqual("unsupported", order["status"])
        self.assertEqual("PROVENANCE", order["code"])
        self.assertNotIn("events", order)

    def test_linked_shared_graph_is_bounded_inventory_not_policy_coverage(self):
        link = fx(146, 0, resource="SHARED")
        report = self.run_inventory({"POTN09.ITM": potion([link]), "DW#PTN09.ITM": potion([link]),
                                     "SHARED.SPL": container("SPL", groups=[[fx(18, 110, parameter2=2)]])})
        self.assertEqual({"unsupported": 2}, report["counts"])
        self.assertEqual(["DW#PTN09.ITM", "POTN09.ITM"], report["shared_linked_resources"]["SHARED.SPL"])
        self.assertTrue(all(len(item["links"]) == 1 for item in report["potions"]))
        self.assertNotIn("raw_hex", str(report))
        self.assertNotIn("raw_ability_hex", str(report))

    def test_missing_and_cycle_paths_are_visible_even_when_compiler_rejects_links(self):
        link = fx(146, 0, resource="LOOP")
        report = self.run_inventory({"POTN09.ITM": potion([link, fx(146, 0, resource="MISSING")]),
                                     "LOOP.SPL": container("SPL", groups=[[link]])})
        row = report["potions"][0]
        self.assertTrue(row["graph_incomplete"])
        self.assertEqual({"cycle", "missing_resource"}, {d["code"] for d in row["graph_diagnostics"]})
        self.assertEqual(2, len(row["direct_diagnostics"]))
        limited = self.run_inventory({"POTN09.ITM": potion([link]),
                                      "LOOP.SPL": container("SPL", groups=[[fx()]])}, max_nodes=1)
        self.assertEqual("node_limit", limited["potions"][0]["graph_diagnostics"][0]["code"])

    def test_linked_registry_coverage_cannot_masquerade_as_direct_replay(self):
        link = replace(fx(146, 0, parameter2=1, resource="SHARED"), timing=1)
        report = self.run_inventory({
            "POTN36.ITM": potion([link]), "DW#PTN36.ITM": potion([link]),
            "SHARED.SPL": container("SPL", groups=[[fx()]]),
            "POTN14.ITM": potion([fx(206, 0, resource="POTN14")]),
        })
        self.assertEqual({"linked_owned": 2, "unsupported": 1}, report["counts"])
        for row in report["potions"]:
            if row["status"] == "linked_owned":
                self.assertEqual(["linked"], row["owned_transport"])
        self.assertEqual("unsupported", report["global_checks"]["whole_profile"]["status"])
        self.assertEqual({"status": "passed", "sources": 2},
                         report["global_checks"]["locally_compilable_subset"])
        self.assertEqual(4, len(report["canonical_scs_orders"]))
        for order in report["canonical_scs_orders"]:
            self.assertEqual("not_replayed", order["status"])
            self.assertEqual("LINKED_REPLAY_CAPABILITY", order["code"])
            self.assertNotIn("events", order)
        self.assertFalse(any(row["opcode"] == 146 for row in report["missing_direct_adapters"]))

    def test_mixed_owned_source_reports_both_transports_and_no_partial_replay(self):
        link = replace(fx(146, 0, parameter2=1, resource="SHARED"), timing=1)
        item = potion([fx(19, 4), link])
        report = self.run_inventory({"POTN36.ITM": item, "DW#PTN36.ITM": item,
                                    "SHARED.SPL": container("SPL", groups=[[fx()]])})
        self.assertEqual({"linked_owned": 2}, report["counts"])
        self.assertTrue(all(row["owned_transport"] == ["direct", "linked"] for row in report["potions"]))
        self.assertTrue(all(row["status"] == "not_replayed" for row in report["canonical_scs_orders"]))


if __name__ == "__main__":
    unittest.main()
