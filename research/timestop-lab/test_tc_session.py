"""tc_session.py offline: its timing rules, save folders, target matching, mod check, and the
request sequences of run, clean, quick save and late answers against a scripted console."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
os.environ.setdefault("USERPROFILE", str(Path.home()))
import lab_rc
import tc_session as ts
import test_tc_requests


class RulesTests(unittest.TestCase):
    def test_waits_reproduce_the_calibrated_captures(self):
        # timestop_01/02 and haste_01/02 of the Time Stop lab (README, 2026-10-22).
        self.assertEqual(ts.stop_wait(1507, 74), 73)
        self.assertEqual(ts.stop_wait(1815, 37), 36)
        self.assertEqual(ts.haste_wait(1496), 70)
        self.assertEqual(ts.haste_wait(2238), 78)
        for counter in range(0, 60):
            with self.subTest(counter=counter):
                start = ts.stop_wait(counter, 37) + 1
                self.assertIn((counter + start) % 15, (6, 7, 8, 9))
                self.assertLessEqual(abs(start - 37), 7)

    def test_save_folders_take_free_numbers_and_unique_names(self):
        self.assertEqual(ts.next_save_folder(["000000000-Quick-Save"], "CBTC n1 base"), "000000800-CBTC n1 base")
        self.assertEqual(ts.next_save_folder(["000000800-CBTC a", "000000801-CBTC b"], "CBTC c"),
                         "000000802-CBTC c")
        with self.assertRaisesRegex(ts.SessionError, "exists already"):
            ts.next_save_folder(["000000800-CBTC a"], "cbtc A")
        for name in ("", "../x", "a" * 41, "semi;colon"):
            with self.subTest(name=name), self.assertRaises(ts.SessionError):
                ts.next_save_folder([], name)

    def test_spots_get_their_nearest_new_creature_once(self):
        creatures = [{"id": 1, "x": 100, "y": 100}, {"id": 2, "x": 90, "y": 210}, {"id": 3, "x": 500, "y": 500}]
        matched = ts.match_spots([(100, 200), (100, 100)], creatures)
        self.assertEqual([(t["id"], t["off_spot"]) for t in matched], [(2, 14), (1, 0)])
        with self.assertRaises(ts.SessionError):
            ts.match_spots([(0, 0), (1, 1)], creatures[:1])

    def test_fixture_rows_ignore_order_and_other_actors(self):
        probe = {"actors": {"portrait0": {"timed": [{"source": "CBRTREG", "opcode": 98, "timing": 4096, "deadline": 9},
                                                    {"source": "CBRTBUF", "opcode": 0, "timing": 4096, "deadline": 5}]},
                            "portrait1": None, "id7": {"timed": [{"source": "X"}]}}}
        self.assertEqual(ts.fixture_rows(probe), {"portrait0": [("CBRTBUF", 0, 4096, 5), ("CBRTREG", 98, 4096, 9)],
                                                  "portrait1": []})


class FakeConsole:
    """Answers each request by its file name; a handler returns the first return value, or a
    whole response dict under the key "response"."""

    def __init__(self):
        self.handlers, self.sent = {}, []

    def send(self, label, code, source, timeout, delay, expect_exit=False):
        request = Path(source).stem
        self.sent.append((request, label, code))
        handler = self.handlers[request]
        value = handler(code) if callable(handler) else handler
        if isinstance(value, dict) and "response" in value:
            return {"response": value["response"]}
        return {"response": {"status": "ok", "returnValues": [value]}}


class SessionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="cbr-tc-session-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.lab, self.profile = root / "lab", root / "profile"
        (self.lab / "override").mkdir(parents=True)
        (self.profile / "save").mkdir(parents=True)
        patcher = mock.patch.multiple(lab_rc, VARIANT="timeclocks", LAB=self.lab, OVERRIDE=self.lab / "override",
                                      LAB_ID=b"CBR TimeClocks Lab 2730\n")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.console = FakeConsole()
        self.session = ts.Session("t1", "defaults", profile=self.profile)
        self.addCleanup(self.session.log_file.close)
        self.session.send = self.console.send
        self.session.sleep = lambda seconds: None
        self.session.echo = False
        self.session.subject_id, self.session.controller_id = 10, 11

    def requests(self):
        return [request for request, _, _ in self.console.sent]

    def test_run_resumes_an_autopause_until_the_world_time_advanced(self):
        times = iter([(True, 100, False), (False, 130, False), (True, 150, True), (False, 210, False),
                      (False, 260, False)])

        def pause(code):
            if '"\\112\\097\\117\\115\\101\\100"' in code:  # want = "paused"
                return {"before": {"game_time": 262}, "after": {"game_time": 261}, "toggled": True}
            was_paused, now, _ = next(times)
            return {"before": {"game_time": now}, "after": {"game_time": now}, "toggled": was_paused}
        self.console.handlers["pause"] = pause
        self.assertEqual(self.session.run(150, "case"), (100, 261))
        log = (self.lab / "cbr-timestop-output" / "tc-driver-t1.jsonl").read_text(encoding="utf-8")
        self.assertIn('"k": "autopause"', log)

    def test_run_refuses_a_world_time_that_stands_still(self):
        self.console.handlers["pause"] = {"before": {"game_time": 50}, "after": {"game_time": 50}, "toggled": False}
        with self.assertRaisesRegex(ts.SessionError, "stands still"):
            self.session.run(30, "stuck")

    def test_a_late_answer_is_collected_and_a_failure_stops(self):
        self.console.handlers["menus"] = {"response": {"status": "timeout", "claimed": False}}
        answers = iter([{"response": {"status": "timeout"}}, {"response": {"status": "ok", "returnValues": [{"top": "X"}]}}])
        self.session.collect = lambda label, timeout: next(answers)
        self.assertEqual(self.session.menus(), {"top": "X"})
        self.console.handlers["ping"] = {"response": {"status": "error", "error": "boom"}}
        with self.assertRaisesRegex(ts.SessionError, "boom"):
            self.session.rc("ping")
        with self.assertRaisesRegex(ts.SessionError, "Label"):
            self.session.rc("ping", "bad label")

    def test_mod_states_are_checked_switch_by_switch(self):
        active = {"status": "active: Time Stop ...", "installed": True, "options": dict(ts.MOD_STATES["defaults"])}
        self.session.check_mod(active)
        with self.assertRaisesRegex(ts.SessionError, "differ"):
            self.session.check_mod({**active, "options": {**active["options"], "slow": False}})
        with self.assertRaisesRegex(ts.SessionError, "not active"):
            self.session.check_mod({**active, "status": "off: EEex is not active", "installed": False})
        with self.assertRaisesRegex(ts.SessionError, "not active"):
            self.session.check_mod("not loaded")
        self.session.mod = "absent"
        self.session.check_mod("not loaded")
        with self.assertRaisesRegex(ts.SessionError, "absent"):
            self.session.check_mod(active)

    def test_clean_runs_out_effects_and_projectiles_then_lowers_hp(self):
        probes = iter([
            {"game_time": 1000, "time_stop_remaining": 40,
             "actors": {"portrait0": {"timed": [{"deadline": 1200}]}, "portrait1": {"timed": []}},
             "sampler": {"projectiles": 0, "pending": 0}},
            {"game_time": 1300, "time_stop_remaining": 0, "actors": {"portrait0": {"timed": []}},
             "sampler": {"projectiles": 1, "pending": 0}},
            {"game_time": 1450, "time_stop_remaining": 0, "actors": {"portrait0": {"timed": []}},
             "sampler": {"projectiles": 0, "pending": 0}},
        ])
        self.console.handlers["tc-probe"] = lambda code: next(probes)
        ran = []
        self.session.run = lambda ticks, label="run": ran.append(ticks) or (0, ticks)
        hp = iter([{"hp": 95, "max_hp": 98}, {"hp": 83, "max_hp": 98}])
        self.console.handlers["subject"] = lambda code: {"portrait0": next(hp)}
        self.console.handlers["queue"] = {"queued": "ApplyDamage(Myself,18,0)"}
        self.session.clean()
        self.assertEqual(ran, [215, 150, 15])  # the effect's 200 ticks + 15; the projectile; the damage
        damage = [code for request, _, code in self.console.sent if request == "queue"]
        self.assertEqual(len(damage), 1)
        self.assertIn(lab_rc.lua_string("18"), damage[0])  # 13 + 8 - 3 missing

    def test_quick_save_is_found_and_kept_with_its_probe(self):
        quick = self.profile / "save" / "000000000-Quick-Save"

        def save(code):
            quick.mkdir()
            (quick / "BALDUR.GAM").write_bytes(b"GAME")
            (quick / "BALDUR.SAV").write_bytes(b"SAV")
            return {"queued": "CBRTSQA_QUICKSAVE"}
        self.console.handlers["save"] = save
        self.console.handlers["tc-probe"] = {"game_time": 777, "time_stop_remaining": 0, "actors": {}}
        saved = self.session.quicksave("base")
        self.assertEqual(saved["folder"], "000000000-Quick-Save")
        kept = self.session.keep_save("CBTC t1 base", saved)
        self.assertEqual(kept, "000000800-CBTC t1 base")
        self.assertEqual((self.profile / "save" / kept / "BALDUR.SAV").read_bytes(), b"SAV")
        sidecar = json.loads((self.lab / "cbr-timestop-output" / "saves" / f"{kept}.json").read_text(encoding="utf-8"))
        self.assertEqual((sidecar["quick_save"], sidecar["probe"]["game_time"], sidecar["mod"]),
                         ("000000000-Quick-Save", 777, "defaults"))
        with self.assertRaisesRegex(ts.SessionError, "exists already"):
            self.session.keep_save("CBTC t1 base", saved)

    def test_a_refused_save_is_reported_not_kept(self):
        self.console.handlers.update({"save": {"queued": "CBRTSQA_QUICKSAVE"}, "menus": {"top": "WORLD"},
                                      "tc-probe": {"game_time": 1, "actors": {}}})
        saved = self.session.quicksave("in-stop")
        self.assertIsNone(saved["folder"])
        self.assertIsNone(self.session.keep_save("CBTC t1 in stop", saved))

    def test_spawned_targets_are_the_new_creatures_at_their_spots(self):
        nearby = iter([{"creatures": [{"id": 10, "x": 0, "y": 0}]},
                       {"creatures": [{"id": 10, "x": 0, "y": 0}]},
                       {"creatures": [{"id": 10, "x": 0, "y": 0}, {"id": 77, "x": 610, "y": 405, "name": "Bounty Hunter"}]}])
        self.console.handlers.update({"nearby": lambda code: next(nearby), "tc-queue": {"queued": "x"}})
        ran = []
        self.session.run = lambda ticks, label="run": ran.append(ticks) or (0, ticks)
        (target,) = self.session.spawn([(600, 400)], "areaa")
        self.assertEqual((target["id"], target["off_spot"], ran), (77, 11, [8]))
        queued = next(code for request, _, code in self.console.sent if request == "tc-queue")
        self.assertIn(lab_rc.lua_string("spawn:BOUNHA02:600:400"), queued)


class ScriptedGame:
    """Just enough game for every case: the world time moves only while unpaused, spawns appear
    where tc-queue.lua's CreateCreature puts them, and each save rewrites the quick save. Every
    tc-queue request runs through tc-queue.lua's own checks."""

    def __init__(self, test: unittest.TestCase, saves: Path):
        self.test, self.saves = test, saves
        self.time, self.paused, self.saved = 2000, True, 0
        self.objects = {10: "CBRTS Subject", 11: "Imoen"}
        self.creatures = []

    def handlers(self) -> dict:
        done = {"ok": True}
        return {"pause": self.pause, "subject": self.subject, "tc-probe": self.probe, "tc-queue": self.queue,
                "nearby": lambda code: {"creatures": list(self.creatures)}, "save": self.save,
                "queue": {"queued": "x"}, "sampler": done, "sampler-export": done, "arm": done, "stop": done,
                "export": done, "menus": {"top": "WORLD_ACTIONBAR"}}

    def pause(self, code):
        paused, before = lab_rc.lua_string("paused") in code, self.time
        if not paused and not self.paused:
            self.time += 40
        toggled, self.paused = self.paused != paused, paused
        return {"before": {"game_time": before}, "after": {"game_time": self.time}, "toggled": toggled}

    def subject(self, code):
        return {"portrait0": {"clocks": {"list": self.time - 500}, "hp": 85, "max_hp": 98, "x": 3741, "y": 2801}}

    def probe(self, code):
        return {"game_time": self.time, "time_stop_remaining": 0, "sampler": {"projectiles": 0, "pending": 0},
                "actors": {"portrait0": {"timed": []}, "portrait1": {"timed": []}}}

    def queue(self, code):
        ok, response, _, _ = test_tc_requests.run_tc_queue(code, actors=dict(self.objects))
        self.test.assertTrue(ok, response)
        for x, y in re.findall(r'CreateCreature\("BOUNHA02",\[(\d+)\.(\d+)\],0\)', response):
            ident = 100 + len(self.creatures)
            self.objects[ident] = "Bounty Hunter"
            self.creatures.append({"id": ident, "name": "Bounty Hunter", "x": int(x), "y": int(y)})
        return {"queued": response}

    def save(self, code):
        quick = self.saves / "000000000-Quick-Save"
        quick.mkdir(exist_ok=True)
        (quick / "BALDUR.GAM").write_bytes(b"GAME")
        self.saved += 1
        os.utime(quick / "BALDUR.GAM", (1_000_000 + self.saved,) * 2)
        return {"queued": "CBRTSQA_QUICKSAVE"}


@unittest.skipIf(test_tc_requests.lupa is None, "lupa with LuaJIT 2.1 is not installed")
class DryRunTests(unittest.TestCase):
    """Every case against a scripted game, under the longest tag: each console label is usable
    and tc-queue.lua accepts every step list the cases queue (session n1 stopped on a label)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="cbr-tc-dry-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        lab, profile = root / "lab", root / "profile"
        (lab / "override").mkdir(parents=True)
        (lab / "override" / "CBRTSRCK.SPL").write_bytes(b"")  # areag needs SR's Cloudkill staged
        (profile / "save").mkdir(parents=True)
        patcher = mock.patch.multiple(lab_rc, VARIANT="timeclocks", LAB=lab, OVERRIDE=lab / "override",
                                      LAB_ID=b"CBR TimeClocks Lab 2730\n")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.console, self.game = FakeConsole(), ScriptedGame(self, profile / "save")
        self.console.handlers.update(self.game.handlers())
        self.session = ts.Session("longtag8", "defaults", profile=profile)
        self.addCleanup(self.session.log_file.close)
        self.session.send, self.session.sleep, self.session.echo = self.console.send, lambda seconds: None, False
        self.session.subject_id, self.session.controller_id = 10, 11

    def test_every_case_runs_against_a_scripted_game(self):
        for name in [name for name in ts.CASES if name != "load"] + ["load"]:
            with self.subTest(case=name):
                if name == "load":  # the copy the save case kept
                    self.session.loaded = "000000800-CBTC longtag8 after stop"
                self.session.position = (3741, 2801)
                self.assertEqual(ts.CASES[name](self.session, name)["capture"], f"longtag8_{name}")
        queued = sum(1 for request, _, _ in self.console.sent if request == "tc-queue")
        self.assertGreater(queued, 20)
        self.assertEqual(len(self.game.creatures), 11)  # A 2, B 1, C 2, C2 1, D 2, E 1, F 1, G 1


class ArgumentTests(unittest.TestCase):
    def test_cases_and_starts_are_checked_before_anything_runs(self):
        for argv in (["t1", "--mod", "defaults", "--save", "x", "--cases", "nope"],
                     ["t1", "--mod", "defaults", "--fresh", "base", "--cases", "load"],
                     ["t1", "--mod", "defaults", "--save", "x", "--cases", "base,base"],
                     ["t1", "--mod", "maybe", "--save", "x"],
                     ["t1", "--mod", "defaults"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), \
                    mock.patch("sys.stderr", new=open(os.devnull, "w", encoding="utf-8")) as err:
                try:
                    ts.main(argv)
                finally:
                    err.close()


if __name__ == "__main__":
    unittest.main()
