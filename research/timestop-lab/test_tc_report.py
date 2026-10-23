"""tc_report.py offline: a synthetic sampler file with a stop, a moved deadline and a cloud."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import tc_report


def sample(w, ts=0, hp=80, sp=1, fx="", pj=()):
    return {"k": "s", "w": w, "p": False, "ts": ts, "tc": 11 if ts else -1,
            "a": [{"id": 10, "hp": hp, "sp": sp, "fx": fx}], "pj": list(pj)}


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
        self.assertEqual(tc_report.effects("A/1/4096/5,A/1/4096/9,B/2/1/0"),
                         {"A/1": (4096, 5), "A/1#2": (4096, 9), "B/2": (1, 0)})


if __name__ == "__main__":
    unittest.main()
