"""tc_report.py offline: a synthetic sampler file with a stop, a moved deadline and a cloud."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import tc_report


def sample(w, ts=0, hp=80, sp=1, fx="", pj=(), ck=None):
    actor = {"id": 10, "hp": hp, "sp": sp, "fx": fx}
    if ck is not None:
        actor["ck"] = ck
    return {"k": "s", "w": w, "p": False, "ts": ts, "tc": 11 if ts else -1, "a": [actor], "pj": list(pj)}


class ReportTests(unittest.TestCase):
    def test_stop_effects_and_a_cloud(self):
        cloud = {"id": 5, "ty": "CProjectileArea", "x": 300, "y": 400, "ar": 1, "rm": 10, "rl": 75, "cd": 30}
        records = [
            {"k": "header", "lab": "CBR TimeClocks Lab 2730\n", "records": 9, "overflow": False, "errors": 0},
            {"k": "decode", "w": 100, "ty": "CProjectileArea", "source": 6, "by": 11, "pro": 187},
            sample(100, fx="CBRTBUF/0/4096/190"),
            {"k": "fired", "w": 101, "id": 5, "ty": "CProjectileArea", "decoded": 100},
            sample(101, fx="CBRTBUF/0/4096/190", pj=[cloud]),
            {"k": "mark", "label": "a_stop", "w": 110, "actor": 11},
            sample(110, ts=180, fx="CBRTBUF/0/4096/191", pj=[cloud]),
            sample(150, ts=100, hp=81, fx="CBRTBUF/0/4096/231", pj=[cloud]),
            sample(200, ts=0, hp=81, sp=0, fx="CBRTBUF/0/4096/280", pj=[{**cloud, "cd": 29, "x": 301}]),
            sample(290, hp=81, sp=0, pj=[{**cloud, "cd": 0, "rm": 9}]),
            {"k": "gone", "w": 300, "id": 5, "ty": "CProjectileArea"},
            sample(300, hp=81, sp=1),
        ]
        with tempfile.TemporaryDirectory(prefix="cbr-tc-report-") as directory:
            path = Path(directory) / "x.samples.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            summary = tc_report.summarize(*tc_report.load(path))
        self.assertEqual(summary["stops"], [{"start": 110, "counter": 180, "caster": 11, "last": 150, "end": 200}])
        self.assertEqual(summary["marks"], [{"label": "a_stop", "w": 110, "actor": 11}])
        actor = summary["actors"]["10"]
        self.assertEqual(actor["hp"], [[100, 80], [150, 81]])
        self.assertEqual(actor["speed"], [[100, 1], [200, 0], [300, 1]])
        buff = actor["effects"]["CBRTBUF/0"]
        self.assertEqual((buff["seen"], buff["deadline"], buff["removed"]), (100, 190, 290))
        self.assertEqual(buff["moves"], [[110, 190, 191], [150, 191, 231], [200, 231, 280]])
        cloud_summary = summary["projectiles"]["5"]
        self.assertEqual((cloud_summary["fired"], cloud_summary["gone"]), (101, 300))
        self.assertEqual(cloud_summary["moved"]["ticks"], [200, 290])
        self.assertEqual(cloud_summary["area"], [[101, 1, 10, 30], [200, 1, 10, 29], [290, 1, 9, 0]])
        self.assertEqual(summary["decodes"][0]["pro"], 187)

    def test_a_file_without_header_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="cbr-tc-report-") as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"k": "s", "w": 1}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                tc_report.load(path)

    def test_an_effect_applied_again_keeps_its_removal(self):
        records = [{"k": "header", "lab": "x", "records": 3}, sample(10, fx="SPWI213/39/4096/50"),
                   sample(52), sample(80, fx="SPWI213/39/4096/215")]
        summary = tc_report.summarize(*[records[0], records[1:]])
        effect = summary["actors"]["10"]["effects"]["SPWI213/39"]
        self.assertEqual((effect["seen"], effect["deadline"], effect["removed"], effect["again"]),
                         (10, 50, None, [[52, 80, 215]]))

    def test_repeated_effects_keep_their_own_rows(self):
        self.assertEqual(tc_report.copies("A/1/4096/5,A/1/4096/9,B/2/1/0"),
                         {"A/1": [(4096, 5), (4096, 9)], "B/2": [(1, 0)]})
        # Session d2's case A: a stop moved the first sleep, a pulse added a second, then the
        # first went and the list moved the second to the front. Its row must stay its own.
        records = [{"k": "header", "lab": "x", "records": 5}, sample(31, fx="S/39/4096/166"),
                   sample(68, fx="S/39/4096/167"), sample(290, fx="S/39/4096/389"),
                   sample(332, fx="S/39/4096/389,S/39/4096/466"), sample(410, fx="S/39/4096/466")]
        rows = tc_report.summarize(records[0], records[1:])["actors"]["10"]["effects"]
        self.assertEqual((rows["S/39"]["deadline"], rows["S/39"]["moves"][-1], rows["S/39"]["removed"]),
                         (166, [290, 167, 389], 410))
        self.assertEqual((rows["S/39#2"]["seen"], rows["S/39#2"]["deadline"], rows["S/39#2"]["moves"],
                          rows["S/39#2"]["removed"]), (332, 466, [], None))
        self.assertEqual(sum(new - old for _, old, new in rows["S/39"]["moves"]), 223)

    def test_a_copy_moves_by_at_most_the_given_ticks(self):
        self.assertEqual(tc_report.match([100, 200], [200, 104], 4), ([(1, 0), (0, 1)], [], []))
        self.assertEqual(tc_report.match([100], [104], 3), ([], [0], [0]))
        self.assertEqual(tc_report.match([100], [101], 1), ([(0, 0)], [], []))
        self.assertEqual(tc_report.match([100], [101], 0), ([], [0], [0]))

    def test_a_creature_with_sparse_passes_keeps_its_moves(self):
        # Session d2's case A: the sleeping target had a pass only every third tick (its check
        # counter `ck`), and each frozen pass moved its deadlines by the ticks since the one
        # before, the first by one. A copy that changes without a pass came anew.
        records = [{"k": "header", "lab": "x", "records": 9},
                   sample(65, ck=31, fx="S/39/4096/166"), sample(66, ck=31, fx="S/39/4096/166"),
                   sample(68, ts=180, ck=32, fx="S/39/4096/167"), sample(70, ts=176, ck=32, fx="S/39/4096/167"),
                   sample(71, ts=174, ck=33, fx="S/39/4096/170"), sample(74, ts=168, ck=34, fx="S/39/4096/173"),
                   sample(75, ts=166, ck=34, fx="S/39/4096/175"), sample(77, ts=162, ck=35, fx="S/39/4096/178")]
        rows = tc_report.summarize(records[0], records[1:])["actors"]["10"]["effects"]
        self.assertEqual(rows["S/39"]["moves"], [[68, 166, 167], [71, 167, 170], [74, 170, 173], [77, 175, 178]])
        self.assertEqual((rows["S/39"]["removed"], rows["S/39"]["again"]), (None, [[75, 75, 175]]))
        self.assertEqual(rows["S/39"]["deadline"], 166)
        self.assertNotIn("S/39#2", rows)


if __name__ == "__main__":
    unittest.main()
