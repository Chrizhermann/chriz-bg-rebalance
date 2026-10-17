"""Synthetic graph/bounds/preservation checks; no game or install is executed."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import audit_potion_payloads as audit
from ie_formats import SplEffect, EffV2


def container(ext="ITM", groups=(), global_indices=(), *, category=9,
              effects_first=False, extra=b"trailer"):
    """Noncanonical offsets/order, casting/equipped slice before abilities."""
    records = list(global_indices) + [e for group in groups for e in group]
    asize = 56 if ext == "ITM" else 40
    aoff = 0x80 if not effects_first else 0x80 + len(records) * 48 + 7
    foff = 0x80 + len(groups) * asize + 7 if not effects_first else 0x80
    b = bytearray(max(aoff + len(groups) * asize, foff + len(records) * 48))
    b[:8] = (ext + " V1  ").encode()
    struct.pack_into("<H", b, 0x1C, category)
    struct.pack_into("<IHIHH", b, 0x64, aoff, len(groups), foff, 0, len(global_indices))
    idx = len(global_indices)
    for i, group in enumerate(groups):
        a = aoff + i * asize
        b[a] = 3
        b[a + 0xC] = 5  # Deliberately not the common potion self-target.
        struct.pack_into("<HH", b, a + 0x1E, len(group), idx)
        if ext == "ITM":
            struct.pack_into("<HH", b, a + 0x22, 7, 2)
        idx += len(group)
    for i, e in enumerate(records):
        b[foff + i * 48:foff + (i + 1) * 48] = e.to_bytes()
    return bytes(b) + extra


def run(resources, **kwargs):
    def read(name):
        try:
            return resources[name]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc
    return audit.audit(resources, read, **kwargs)


class PotionPayloadAuditTests(unittest.TestCase):
    def test_multiple_reordered_abilities_raw_bytes_and_instant_permanent_hp(self):
        fx = [SplEffect(opcode=17, parameter1=9, timing=1),
              SplEffect(opcode=19, parameter1=1, timing=1),
              SplEffect(opcode=18, parameter1=110, parameter2=2, duration=600),
              SplEffect(opcode=90, parameter1=40, duration=600, target=2,
                        probability1=75, probability2=20, save_type=8, save_bonus=-2)]
        for groups in ((fx[:2], fx[2:]), (fx[2:], fx[:2])):
            source = container(groups=groups, global_indices=(SplEffect(opcode=142, timing=2),))
            resources = {"CUSTOM.ITM": source, "SWORD.ITM": container(category=1)}
            before = dict(resources)
            report = run(resources)
            self.assertFalse(report["incomplete"])
            self.assertEqual(["CUSTOM.ITM"], [p["resource"] for p in report["potions"]])
            item = report["potions"][0]
            self.assertTrue(item["hp_review"])
            self.assertTrue(item["current_hp_operation"])
            self.assertEqual(2, item["timing_counts"]["limited_seconds"])
            slices = item["nodes"]["CUSTOM.ITM"]["slices"]
            self.assertEqual("equipped", slices[0]["kind"])
            self.assertTrue(all(s["charges"] == 7 and s["ability_target"] == 5 for s in slices[1:]))
            retained = [e["raw_hex"] for part in slices[1:] for e in part["effects"]]
            self.assertCountEqual([e.to_bytes().hex() for e in fx], retained)
            self.assertEqual(before, resources)
            notes = [n for part in slices for e in part["effects"] for n in e["review_notes"]]
            self.assertIn("permanent_stat_operation_or_persistent_modifier", notes)
            self.assertIn("current_hp_on_first_application", notes)

    def test_effect_table_before_ability_table_and_unused_trailer(self):
        b = container(groups=((SplEffect(opcode=19, duration=900),),), effects_first=True)
        node = audit.parse_resource("A.ITM", b)
        self.assertEqual(19, node["slices"][1]["effects"][0]["opcode"])
        self.assertEqual(hashlib.sha256(b).hexdigest(), node["sha256"])

    def test_linked_casting_effect_and_shared_child_all_edges_preserved(self):
        resources = {
            "A.ITM": container(groups=((SplEffect(opcode=146, resource="CHILD", timing=1),
                                        SplEffect(opcode=146, resource="CHILD", timing=4, duration=6)),)),
            "CHILD.SPL": container("SPL", groups=((SplEffect(opcode=177, resource="BOOST"),),),
                                   global_indices=(SplEffect(opcode=139, timing=1),)),
            "BOOST.EFF": EffV2(opcode=18, parameter1=110, parameter2=2, duration=300).to_bytes(),
        }
        item = run(resources)["potions"][0]
        self.assertFalse(item["incomplete"])
        self.assertEqual(3, len(item["nodes"]))
        self.assertEqual(3, len(item["edges"]))
        self.assertEqual("casting", item["nodes"]["CHILD.SPL"]["slices"][0]["kind"])
        self.assertTrue(item["hp_review"])

    def test_missing_cycle_and_corrupt_links_are_reported_together(self):
        resources = {
            "A.ITM": container(groups=((SplEffect(opcode=146, resource="LOOP"),
                                        SplEffect(opcode=177, resource="BAD"),
                                        SplEffect(opcode=146, resource="ABSENT")),)),
            "LOOP.SPL": container("SPL", groups=((SplEffect(opcode=146, resource="LOOP"),),)),
            "BAD.EFF": b"EFF V2.0",
        }
        report = run(resources)
        self.assertTrue(report["incomplete"])
        self.assertEqual({"cycle", "missing_resource", "invalid_resource"},
                         {d["code"] for d in report["potions"][0]["diagnostics"]})

    def test_depth_and_node_bounds(self):
        resources = {"A.ITM": container(groups=((SplEffect(opcode=146, resource="B"),),)),
                     "B.SPL": container("SPL", groups=((SplEffect(opcode=146, resource="C"),),)),
                     "C.SPL": container("SPL", groups=((SplEffect(opcode=19, duration=90),),))}
        for kwargs, expected in (({"max_depth": 0}, "depth_limit"), ({"max_nodes": 1}, "node_limit")):
            p = run(resources, **kwargs)["potions"][0]
            self.assertTrue(p["incomplete"])
            self.assertEqual(expected, p["diagnostics"][0]["code"])

    def test_implicit_links_extension_code_and_invalid_operand_are_visible(self):
        source = container(groups=((SplEffect(opcode=333), SplEffect(opcode=402, resource="LUAHOOK")),))
        p = run({"A.ITM": source})["potions"][0]
        self.assertEqual({"empty_or_implicit_link", "extension_opcode_uninterpreted"},
                         {d["code"] for d in p["diagnostics"]})
        bad = container(groups=((SplEffect(opcode=146, resource="../BAD"),),))
        self.assertEqual("invalid_resource", run({"A.ITM": bad})["potions"][0]["diagnostics"][0]["code"])

    def test_hp_no_current_update_flag_does_not_hide_max_hp_review(self):
        source = container(groups=((SplEffect(opcode=18, parameter1=110, parameter2=2,
                                               special=1, duration=600),),))
        p = run({"A.ITM": source})["potions"][0]
        self.assertTrue(p["hp_review"])
        notes = p["nodes"]["A.ITM"]["slices"][1]["effects"][0]["review_notes"]
        self.assertNotIn("current_hp_on_first_application", notes)

    def test_malformed_root_is_visible_and_other_potion_still_audited(self):
        b = bytearray(container(groups=((SplEffect(opcode=19),),)))
        struct.pack_into("<I", b, 0x6A, len(b) + 1)
        report = run({"BAD.ITM": bytes(b), "GOOD.ITM": container(groups=((),)), "SHORT.ITM": b"bad"})
        self.assertTrue(report["incomplete"])
        self.assertEqual(2, len(report["potions"]))
        self.assertEqual("item_read_error", report["diagnostics"][0]["code"])
        self.assertFalse(report["potions"][1]["incomplete"])

    def test_effect_overlap_rejected_and_shared_slices_allowed(self):
        b = bytearray(container(groups=((SplEffect(opcode=19),), ())))
        aoff = audit.u32(b, 0x64)
        struct.pack_into("<HH", b, aoff + 56 + 0x1E, 1, 0)
        node = audit.parse_resource("A.ITM", bytes(b))
        self.assertEqual(node["slices"][1]["effects"], node["slices"][2]["effects"])
        struct.pack_into("<I", b, 0x6A, aoff)
        with self.assertRaisesRegex(audit.AuditError, "overlaps"):
            audit.parse_resource("A.ITM", bytes(b))

    def test_ir_repurposed_genius_is_not_inferred_from_resref_or_name(self):
        resources = {"POTN29.ITM": container(groups=((SplEffect(opcode=146, resource="POTN29"),),)),
                     "POTN29.SPL": container("SPL", groups=((SplEffect(opcode=48, timing=1),
                                                  SplEffect(opcode=101, parameter2=38, duration=300)),))}
        item = run(resources)["potions"][0]
        self.assertFalse(item["hp_review"])
        self.assertFalse(item["incomplete"])
        self.assertNotIn("genius", json.dumps(item).lower())

    def test_stale_unused_operand_bytes_and_null_terminated_link(self):
        b = bytearray(container(groups=((SplEffect(opcode=19), SplEffect(opcode=146, resource="X")),)))
        foff = audit.u32(b, 0x6A)
        b[foff + 0x14:foff + 0x1C] = b"\xff\x80abcdef"
        b[foff + 48 + 0x14:foff + 48 + 0x1C] = b"X\0\xffabcde"
        report = run({"A.ITM": bytes(b), "X.SPL": container("SPL", groups=((),))})
        self.assertFalse(report["incomplete"])
        self.assertEqual("X.SPL", report["potions"][0]["edges"][0]["target"])
        raw = report["potions"][0]["nodes"]["A.ITM"]["slices"][1]["effects"][0]["raw_hex"]
        self.assertEqual(bytes(b[foff:foff + 48]).hex(), raw)

    def test_no_link_is_inferred_from_protection_or_remove_resource(self):
        b = container(groups=((SplEffect(opcode=321, resource="POTN60", timing=1),
                               SplEffect(opcode=206, resource="POTN60", duration=300)),))
        item = run({"COPY.ITM": b})["potions"][0]
        self.assertEqual([], item["edges"])
        self.assertFalse(item["incomplete"])
        self.assertEqual("POTN60", item["nodes"]["COPY.ITM"]["slices"][1]["effects"][0]["resource"])

    def test_loose_cli_produces_json_and_does_not_write_source(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            source = container(groups=((SplEffect(opcode=19, duration=900),),))
            (folder / "pOtN29.iTm").write_bytes(source)
            result = subprocess.run([sys.executable, "-B", str(ROOT / "research/scripts/audit_potion_payloads.py"),
                                     "--resources", str(folder)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("POTN29.ITM", json.loads(result.stdout)["potions"][0]["resource"])
            self.assertEqual(["pOtN29.iTm"], [p.name for p in folder.iterdir()])
            self.assertEqual(source, (folder / "pOtN29.iTm").read_bytes())

    def test_key_biff_and_override_precedence_without_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "override").mkdir()
            itm = container(groups=((SplEffect(opcode=146, resource="BOOST"),),))
            spl = container("SPL", groups=((SplEffect(opcode=18, parameter1=110, parameter2=2),),))
            blob = bytearray(struct.pack("<4s4sIII", b"BIFF", b"V1  ", 2, 0, 20))
            offset = 20 + 2 * 16
            blob += struct.pack("<IIIHH", 0, offset, len(itm), 1005, 0)
            blob += struct.pack("<IIIHH", 1, offset + len(itm), len(spl), 1006, 0)
            blob += itm + spl
            (root / "test.bif").write_bytes(blob)
            key = bytearray(struct.pack("<4s4sIIII", b"KEY ", b"V1  ", 1, 2, 24, 45))
            key += struct.pack("<IIHH", len(blob), 36, 9, 1) + b"test.bif\0"
            key += struct.pack("<8sHI", b"POTN09", 1005, 0) + struct.pack("<8sHI", b"BOOST", 1006, 1)
            (root / "chitin.key").write_bytes(key)
            baseline = audit.ResourceStore(root, game=True)
            self.assertTrue(audit.audit(baseline.names(), baseline.read)["potions"][0]["hp_review"])
            override = container("SPL", groups=((SplEffect(opcode=90, parameter1=40),),))
            (root / "override/boost.spl").write_bytes(override)
            current = audit.ResourceStore(root, game=True)
            self.assertFalse(audit.audit(current.names(), current.read)["potions"][0]["hp_review"])
            self.assertEqual(bytes(blob), (root / "test.bif").read_bytes())
            self.assertEqual(bytes(key), (root / "chitin.key").read_bytes())


if __name__ == "__main__":
    unittest.main()
