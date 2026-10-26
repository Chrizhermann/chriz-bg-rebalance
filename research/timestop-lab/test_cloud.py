"""Offline validation of the cloud observer (CBRTCld.lua), its record decoder (decode_cloud.py)
and the cloud fields the observer reads in the pinned executable.

Never runs the game or reads process memory. The Lua module runs in LuaJIT (lupa) against stub
host bindings over a synthetic memory held in Python; a record it exports goes through the
decoder. Set CBRTS_TEST_DEPS as for test_cor.py; CBRTS_TEST_EXE optionally selects a copy of the
exact pinned BG2:EE executable.
Run: python -B research/timestop-lab/test_cloud.py -v
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import decode_cloud  # noqa: E402

dependency_path = os.environ.get("CBRTS_TEST_DEPS")
if not dependency_path or not Path(dependency_path).is_dir():
    raise SystemExit("Set CBRTS_TEST_DEPS to the installed offline test dependencies directory")
sys.path.insert(0, dependency_path)

import capstone
from lupa.luajit21 import LuaRuntime
import pefile

HERE = Path(__file__).resolve().parent
EXE = Path(os.environ.get(
    "CBRTS_TEST_EXE",
    r"C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition\Baldur.exe",
))
EXE_SHA256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"

MEMORY = 0x100000
GAME = 0x110000
P0, P1, OTHER = 0x130000, 0x131000, 0x132000
P0_ID, P1_ID, OTHER_ID = 1001, 1002, 1003
CLOUD, CLOUD_ID = 0x140000, 5005
AREA_VTABLE, OTHER_VTABLE = 0x1405C0000, 0x1405C0100
OFFSETS = {"id": 0x48, "left": 0x3C6, "arrived": 0x3C8, "interval": 0x3CC, "countdown": 0x3CE,
           "stop": 0x9690, "stopCaster": 0x9694}


class Host:
    """Synthetic memory, object table and hit points behind the observer's host bindings."""

    def __init__(self, directory: Path):
        self.buf = bytearray(0x50000)
        self.objects = {P0_ID: P0, P1_ID: P1, OTHER_ID: OTHER}
        self.hit_points = {P0_ID: 200, P1_ID: 150, OTHER_ID: 30}
        self.world, self.paused, self.registered, self.directory = 33000, True, [], directory
        self.fail_hp = False
        for sprite, ident in ((P0, P0_ID), (P1, P1_ID), (OTHER, OTHER_ID)):
            self.put(sprite + 0x48, "I", ident)
        self.put(GAME + 0x9694, "i", -1)
        self.put(CLOUD, "Q", AREA_VTABLE)
        self.put(CLOUD + 0x48, "I", 0xFFFFFFFF)  # not yet added to the area

    def put(self, address, fmt, value):
        struct.pack_into("<" + fmt, self.buf, address - MEMORY, value)

    def get(self, address, fmt):
        return struct.unpack_from("<" + fmt, self.buf, int(address) - MEMORY)[0]

    def hp(self, ident):
        if self.fail_hp:
            raise RuntimeError('hp "read"\nfailed')
        return self.hit_points.get(int(ident))

    def cloud(self, left=10, arrived=1, interval=75, countdown=40):
        self.put(CLOUD + 0x3C6, "h", left)
        self.put(CLOUD + 0x3C8, "I", arrived)
        self.put(CLOUD + 0x3CC, "H", interval)
        self.put(CLOUD + 0x3CE, "H", countdown)

    def add_cloud(self):
        self.put(CLOUD + 0x48, "I", CLOUD_ID)
        self.objects[CLOUD_ID] = CLOUD

    def stop(self, left, caster=P1_ID):
        self.put(GAME + 0x9690, "I", left)
        self.put(GAME + 0x9694, "i", caster)

    def bindings(self, lua):
        opener = lua.eval("function(root) return function(path, mode) return io.open(root .. '/' .. path, mode) end end")
        return lua.table_from({
            "u32": lambda a: self.get(a, "I"), "r32": lambda a: self.get(a, "i"),
            "s16": lambda a: self.get(a, "h"), "u16": lambda a: self.get(a, "H"),
            "ptr": lambda a: self.get(a, "Q"),
            "object": lambda ident: self.objects.get(int(ident)),
            "hp": self.hp,
            "world": lambda: self.world, "game": lambda: GAME, "paused": lambda: self.paused,
            "areaVtable": lambda: AREA_VTABLE,
            "pointer": lambda userdata: userdata["_ptr"], "id": lambda userdata: userdata["m_id"],
            "register": self.registered.append,
            "open": opener(str(self.directory).replace("\\", "/")),
        })


def load(host, with_gate=True):
    lua = LuaRuntime(unpack_returned_tuples=True)
    if with_gate:
        lua.execute("gate_calls = {}; function CBRTC_Entry(sprite, elapsed) "
                    "gate_calls[#gate_calls + 1] = {sprite, elapsed}; return 0, 'native' end")
    lua.execute((HERE / "CBRTCld.lua").read_text(encoding="utf-8"))
    module = lua.globals().CBRTCL
    module.UseHost(host.bindings(lua))
    return lua, module


def ids(lua, *values):
    return lua.table_from(list(values))


class CloudModule(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "cbr-timestop-output").mkdir()
        self.host = Host(self.root)
        self.lua, self.cloud = load(self.host)
        self.cloud.Install()

    def tearDown(self):
        self.temp.cleanup()

    def update(self, sprite, elapsed=1):
        return self.lua.globals().CBRTC_Entry(sprite, elapsed)

    def decode_context(self, caster=P0_ID, pointer=CLOUD, sprite=True):
        context = {"projectile": self.lua.table_from({"_ptr": pointer})}
        if sprite:
            context["originatingSprite"] = self.lua.table_from({"m_id": caster})
        self.lua.globals().CBRTCL_Mutator.projectileMutator(self.lua.table_from(context))

    def arm(self, caster=P0_ID, watched=(P0_ID, P1_ID), discard=False):
        return self.cloud.Arm(caster, ids(self.lua, *watched), discard)

    def lines(self):
        return [json.loads(self.cloud.lines[i]) for i in range(1, self.cloud.n + 1)]

    def status(self):
        return self.cloud.Status()


class InstallTests(CloudModule):
    def test_install_wraps_the_gate_once_and_registers_the_mutator(self):
        self.assertEqual(list(self.host.registered), ["CBRTCL_Mutator"])
        status = self.status()
        self.assertTrue(status["installed"] and status["wrapped"])
        self.lua.execute("first_wrapper = CBRTC_Entry")
        self.cloud.Install()
        self.assertEqual(list(self.host.registered), ["CBRTCL_Mutator"])
        self.assertTrue(self.lua.eval("CBRTC_Entry == first_wrapper"))
        self.assertEqual(self.update(P0, 3), (0, "native"))
        call = self.lua.globals().gate_calls[1]
        self.assertEqual((call[1], call[2]), (P0, 3))

    def test_install_needs_the_correction(self):
        _, cloud = load(self.host, with_gate=False)
        with self.assertRaisesRegex(Exception, "Load the correction"):
            cloud.Install()

    def test_the_gate_gets_its_result_while_sampling_fails(self):
        self.arm()
        self.host.fail_hp = True
        self.assertEqual(self.update(P0), (0, "native"))
        status = self.status()
        self.assertEqual(status["errors"], 1)
        self.assertIn('hp "read"\nfailed', status["first_error"])
        self.assertEqual(status["samples"], 0)

    def test_nothing_is_read_while_no_record_runs(self):
        self.host.fail_hp = True
        self.assertEqual(self.update(P0), (0, "native"))
        self.decode_context()
        self.assertEqual((self.status()["errors"], self.status()["cloud"]["state"]), (0, "none"))
        self.arm()
        self.cloud.Stop()
        self.update(P0)
        self.decode_context()
        self.assertEqual((self.status()["errors"], self.status()["cloud"]["state"]), (0, "none"))


class CaptureTests(CloudModule):
    def test_only_the_armed_casters_area_projectile_is_followed(self):
        self.decode_context()
        self.assertEqual(self.status()["cloud"]["state"], "none")  # not armed
        self.arm()
        self.decode_context(caster=P1_ID)
        self.decode_context(sprite=False)
        self.host.put(CLOUD + 0x1000, "Q", OTHER_VTABLE)
        self.decode_context(pointer=CLOUD + 0x1000)
        self.assertEqual(self.status()["cloud"]["state"], "none")
        self.host.world = 33010
        self.decode_context()
        cloud = self.status()["cloud"]
        self.assertEqual((cloud["state"], cloud["decoded"]), ("pending", 33010))
        self.assertEqual(self.cloud.cloud.pointer, CLOUD)
        self.host.put(CLOUD + 0x2000, "Q", AREA_VTABLE)
        self.decode_context(pointer=CLOUD + 0x2000)
        self.assertEqual(self.cloud.cloud.pointer, CLOUD)  # the first one stays

    def test_the_cloud_resolves_when_added_and_ends_when_gone(self):
        self.arm()
        self.decode_context()
        self.host.cloud(left=10, arrived=0, countdown=0)
        self.update(P0)
        self.assertEqual(self.status()["cloud"]["state"], "pending")  # not in the area yet
        self.host.add_cloud()
        self.host.world += 1
        self.update(P0)
        cloud = self.status()["cloud"]
        self.assertEqual((cloud["state"], cloud["id"], cloud["resolved"]), ("live", CLOUD_ID, 33001))
        self.assertEqual(self.lines()[-1]["left"], 10)
        del self.host.objects[CLOUD_ID]
        self.host.world += 1
        self.update(P1)
        cloud = self.status()["cloud"]
        self.assertEqual((cloud["state"], cloud["gone"]), ("gone", 33002))
        self.assertEqual(self.lines()[-1]["left"], None)

    def test_an_unresolved_projectile_is_dropped(self):
        self.arm()
        self.decode_context()
        self.host.world += 16
        self.update(P0)
        self.assertEqual(self.status()["cloud"]["state"], "lost")
        self.host.add_cloud()  # too late: the pointer is no longer read
        self.update(P0)
        self.assertEqual(self.status()["cloud"]["state"], "lost")


class SampleTests(CloudModule):
    def test_only_changes_at_sampled_updates_are_kept(self):
        self.arm()
        self.update(OTHER)
        self.assertEqual(self.cloud.n, 0)
        self.update(P0)
        self.host.world += 1
        self.update(P0)
        self.update(P1)
        self.assertEqual(self.cloud.n, 1)
        self.host.hit_points[P1_ID] = 140
        self.update(P1)
        self.host.world += 1
        self.host.stop(90)
        self.update(P0)
        del self.host.hit_points[P0_ID]
        self.update(P1)
        samples = self.lines()
        self.assertEqual([s["by"] for s in samples], [P0_ID, P1_ID, P0_ID, P1_ID])
        self.assertEqual(samples[0], {"t": 33000, "by": P0_ID, "stop": 0, "caster": -1, "cloud": "none",
                                      "left": None, "arrived": None, "interval": None, "countdown": None,
                                      "hp": [200, 150]})
        self.assertEqual((samples[1]["t"], samples[1]["hp"]), (33001, [200, 140]))
        self.assertEqual((samples[2]["stop"], samples[2]["caster"]), (90, P1_ID))
        self.assertEqual(samples[3]["hp"], [None, 140])

    def test_cloud_fields_come_from_the_aiupdate_offsets(self):
        self.arm()
        self.decode_context()
        self.host.add_cloud()
        self.host.cloud(left=7, arrived=1, interval=75, countdown=12)
        self.update(P0)
        self.assertEqual({k: self.lines()[-1][k] for k in ("cloud", "left", "arrived", "interval", "countdown")},
                         {"cloud": "live", "left": 7, "arrived": 1, "interval": 75, "countdown": 12})
        self.assertEqual({k: self.cloud.offsets[k] for k in OFFSETS}, OFFSETS)

    def test_overflow_stops_the_record(self):
        self.cloud.capacity = 2
        self.arm()
        for hp in (199, 198, 197):
            self.host.hit_points[P0_ID] = hp
            self.update(P0)
        status = self.status()
        self.assertEqual((status["samples"], status["overflow"], status["on"]), (2, True, False))


class ArmExportTests(CloudModule):
    def test_arm_preconditions(self):
        lua, fresh = load(self.host)
        with self.assertRaisesRegex(Exception, "Install the cloud observer first"):
            fresh.Arm(P0_ID, ids(lua, P0_ID), False)
        cases = [("Pause the lab", {"paused": False}, (P0_ID, (P0_ID,))),
                 ("Caster object ID required", {}, (0, (P0_ID,))),
                 ("Sample at least one creature", {}, (P0_ID, ())),
                 ("Distinct object IDs only", {}, (P0_ID, (P0_ID, P0_ID)))]
        for message, state, (caster, watched) in cases:
            with self.subTest(message=message):
                self.host.paused = state.get("paused", True)
                with self.assertRaisesRegex(Exception, message):
                    self.arm(caster, watched)
        self.host.paused = True
        self.arm()
        with self.assertRaisesRegex(Exception, "Already recording"):
            self.arm()
        self.cloud.Stop()
        with self.assertRaisesRegex(Exception, "Export the previous record first"):
            self.arm()
        self.assertTrue(self.arm(discard=True)["on"])

    def test_export_writes_a_record_the_decoder_reads(self):
        self.arm()
        self.update(P0)
        self.decode_context()
        self.host.add_cloud()
        for tick in range(6):
            self.host.world += 1
            self.host.cloud(left=10 - (tick > 2), countdown=(2 - tick) % 76)
            self.update(P0)
        del self.host.objects[CLOUD_ID]
        self.host.world += 1
        self.update(P0)
        with self.assertRaisesRegex(Exception, "Stop recording before the export"):
            self.cloud.Export("k7_test")
        self.cloud.Stop()
        self.host.paused = False
        with self.assertRaisesRegex(Exception, "Pause the lab"):
            self.cloud.Export("k7_test")
        self.host.paused = True
        with self.assertRaisesRegex(Exception, "simple unique record name"):
            self.cloud.Export("../k7")
        result = self.cloud.Export("k7_test")
        self.assertEqual((result["path"], result["samples"], result["cloud"]),
                         ("cbr-timestop-output/k7_test.jsonl", 8, "gone"))
        self.assertFalse(self.status()["unexported"])
        text = (self.root / "cbr-timestop-output" / "k7_test.jsonl").read_text(encoding="utf-8")
        header, samples = decode_cloud.read_record(text)
        self.assertEqual((header["caster"], header["watch"], header["errors"], header["first_error"]),
                         (P0_ID, [P0_ID, P1_ID], 0, None))
        self.assertEqual(header["cloud"], {"state": "gone", "id": CLOUD_ID, "decoded": 33000, "resolved": 33001,
                                           "gone": 33007})
        summary = decode_cloud.decode_record(header, samples)
        self.assertEqual((summary["cloud"]["arrived"], summary["cloud"]["gone"]), (33001, 33007))
        self.assertEqual([e["t"] for e in summary["cloud"]["explosions"]], [33004])
        with self.assertRaisesRegex(Exception, "Record already exists"):
            self.cloud.Export("k7_test")

    def test_an_error_message_is_escaped_in_the_header(self):
        self.arm()
        self.host.fail_hp = True
        self.update(P0)
        self.cloud.Stop()
        self.cloud.Export("k7_error")
        header, _ = decode_cloud.read_record(
            (self.root / "cbr-timestop-output" / "k7_error.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(header["errors"], 1)
        self.assertIn('hp "read"\nfailed', header["first_error"])


def simulate(stop=None, run_in_stop=False, end=1000, hit=7, before_caster=False):
    """Samples as CBRTCld keeps them, one sampled update per tick: a cloud decoded at 101, added
    at 102 and arrived at 105, then an explosion check whenever its countdown is 0 (reload to 75,
    one less explosion, both creatures hit), else one countdown step; it ends with its tenth
    explosion. stop = (first, ticks) runs a stop that freezes the cloud unless run_in_stop; with
    before_caster the cloud's update in the stop's first tick comes before the caster's."""
    samples, key = [], None
    hp, state, left, arrived, countdown = [200, 150], "none", None, None, None
    for t in range(100, end):
        stop_left = stop[0] + stop[1] - t if stop and stop[0] <= t < stop[0] + stop[1] else 0
        if t == 101:
            state = "pending"
        elif t == 102:
            state, left, arrived, countdown = "live", 10, 0, 0
        elif state == "live" and (stop_left == 0 or run_in_stop or (before_caster and t == stop[0])):
            arrived = 1 if t >= 105 else 0
            if arrived and countdown == 0:
                countdown, left, hp = 75, left - 1, [h - hit for h in hp]
                if left == 0:
                    state, left, arrived, countdown = "gone", None, None, None
            elif arrived:
                countdown -= 1
        sample = {"t": t, "by": P0_ID, "stop": stop_left, "caster": P1_ID if stop else -1, "cloud": state,
                  "left": left, "arrived": arrived, "interval": 75 if state == "live" else None,
                  "countdown": countdown, "hp": list(hp)}
        new = json.dumps({k: v for k, v in sample.items() if k not in ("t", "by")})
        if new != key:
            samples.append(sample)
            key = new
    header = {"schema": 1, "name": "sim", "caster": P0_ID, "watch": [P0_ID, P1_ID],
              "cloud": {"state": state, "id": CLOUD_ID, "decoded": 101, "resolved": 102, "gone": None},
              "samples": len(samples), "overflow": False, "errors": 0, "first_error": None}
    return header, samples


def record_text(header, samples):
    return "\n".join([json.dumps(header)] + [json.dumps(s) for s in samples]) + "\n"


class DecoderTests(unittest.TestCase):
    def test_a_frozen_cloud_keeps_its_lifetime_and_hits_nothing_in_the_stop(self):
        free = decode_cloud.decode_record(*simulate())
        stopped = decode_cloud.decode_record(*simulate(stop=(250, 90)))
        for summary in (free, stopped):
            self.assertEqual(summary["issues"], [])
            self.assertEqual(summary["cloud"]["explosion_count"], 10)
            self.assertEqual([e["active_gap"] for e in summary["cloud"]["explosions"][1:]], [76] * 9)
        lifetimes = ("lifetime", "updates", "skipped_ticks", "stop_ticks", "lifetime_outside_stops")
        self.assertEqual([free["cloud"][k] for k in lifetimes], [684, 684, 0, 0, 684])
        self.assertEqual([stopped["cloud"][k] for k in lifetimes], [774, 684, 90, 90, 684])
        self.assertEqual(stopped["verdict"], {"stops": 1, "cloud_changes_in_stop": 0, "hits_in_stop": 0,
                                              "frozen": True})
        window = stopped["stops"][0]
        self.assertEqual((window["first"], window["last"], window["ticks"], window["caster"]), (250, 339, 90, P1_ID))
        self.assertEqual((window["left"], window["countdown"]), ([8, 8], [7, 7]))
        self.assertIsNone(window["at_start"])
        self.assertEqual([c["field"] for c in window["at_end"]["cloud"]], ["countdown"])
        self.assertEqual([d["t"] for d in stopped["hp"][str(P1_ID)]["drops"]][2:4], [347, 423])
        self.assertEqual(free["verdict"], {"stops": 0, "cloud_changes_in_stop": 0, "hits_in_stop": 0,
                                           "frozen": False})

    def test_a_cloud_updated_before_the_caster_runs_in_the_stops_first_tick(self):
        summary = decode_cloud.decode_record(*simulate(stop=(250, 90), before_caster=True))
        lifetimes = ("lifetime", "updates", "skipped_ticks", "stop_ticks", "lifetime_outside_stops")
        self.assertEqual([summary["cloud"][k] for k in lifetimes], [773, 684, 89, 90, 683])
        self.assertEqual(summary["verdict"]["cloud_changes_in_stop"], 0)
        self.assertEqual([c["field"] for c in summary["stops"][0]["at_start"]["cloud"]], ["countdown"])
        self.assertEqual([e["active_gap"] for e in summary["cloud"]["explosions"][1:]], [76] * 9)

    def test_a_heal_in_the_stop_is_no_hit(self):
        header, samples = simulate(stop=(250, 90))
        index = next(i for i, s in enumerate(samples) if s["stop"] == 50)
        for sample in samples[index:]:
            sample["hp"][0] += 5
        summary = decode_cloud.decode_record(header, samples)
        self.assertEqual(summary["stops"][0]["hp_inside"], [{"id": P0_ID, "from": 186, "to": 191, "t": 290}])
        self.assertEqual(summary["verdict"]["hits_in_stop"], 0)
        self.assertEqual(summary["hp"][str(P0_ID)]["rises"], [{"t": 290, "from": 186, "to": 191}])

    def test_a_stop_before_the_arrival_is_outside_the_lifetime(self):
        summary = decode_cloud.decode_record(*simulate(stop=(103, 10)))
        lifetimes = ("arrived", "lifetime", "updates", "skipped_ticks", "stop_ticks")
        self.assertEqual([summary["cloud"][k] for k in lifetimes], [113, 684, 684, 0, 0])

    def test_a_cloud_running_in_the_stop_is_caught(self):
        summary = decode_cloud.decode_record(*simulate(stop=(250, 90), run_in_stop=True))
        self.assertFalse(summary["verdict"]["frozen"])
        self.assertEqual(summary["verdict"]["hits_in_stop"], 4)  # at 257 and 333, both creatures
        fields = {c["field"] for c in summary["stops"][0]["cloud_inside"]}
        self.assertEqual(fields, {"countdown", "left"})
        lifetimes = ("lifetime", "updates", "skipped_ticks", "stop_ticks", "lifetime_outside_stops")
        self.assertEqual([summary["cloud"][k] for k in lifetimes], [684, 684, 0, 90, 594])
        self.assertEqual([e["active_gap"] for e in summary["cloud"]["explosions"][1:]], [76] * 9)

    def test_changes_at_the_stops_edges_are_kept_apart(self):
        header, samples = simulate(stop=(257, 90))  # begins on the tick of the third explosion
        summary = decode_cloud.decode_record(header, samples)
        self.assertEqual(summary["verdict"]["cloud_changes_in_stop"], 0)
        header, samples = simulate(stop=(250, 90), run_in_stop=True)
        index = next(i for i, s in enumerate(samples) if s["stop"] == 90)
        samples[index]["hp"] = [1, 1]  # the change into the stop's first sample
        summary = decode_cloud.decode_record(header, samples)
        self.assertEqual(summary["stops"][0]["at_start"]["hp"][0]["to"], 1)

    def test_an_incomplete_record_is_reported(self):
        header, samples = simulate(end=400)
        summary = decode_cloud.decode_record(header, samples)
        self.assertIn("no cloud followed", summary["issues"][0])
        header, samples = simulate(stop=(250, 900), end=600)
        header["overflow"], header["errors"], header["first_error"] = True, 2, "x"
        issues = decode_cloud.decode_record(header, samples)["issues"]
        self.assertEqual(len(issues), 4)
        self.assertTrue(any("ends inside a stop" in issue for issue in issues))

    def test_invalid_records_are_refused(self):
        header, samples = simulate()
        good = record_text(header, samples)
        self.assertEqual(decode_cloud.read_record(good)[0]["samples"], len(samples))
        broken = [record_text({**header, "schema": 2}, samples),
                  record_text({**header, "samples": len(samples) + 1}, samples),
                  record_text(header, [dict(samples[0], hp=[1])] + samples[1:]),
                  record_text(header, [{k: v for k, v in samples[0].items() if k != "by"}] + samples[1:]),
                  record_text(header, [dict(samples[0], cloud="flying")] + samples[1:]), ""]
        for text in broken:
            with self.subTest(text=text[:40]):
                with self.assertRaises(ValueError):
                    decode_cloud.read_record(text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r.jsonl"
            path.write_text(broken[0], encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(decode_cloud.main([str(path), "--json", str(Path(directory) / "s.json")]), 2)
            self.assertIn("not a schema 1 CBRTCld record", error.getvalue())
            path.write_text(good, encoding="utf-8")
            self.assertEqual(decode_cloud.main([str(path), "--json", str(Path(directory) / "s.json")]), 0)
            header, samples = simulate(end=400)
            path.write_text(record_text(header, samples), encoding="utf-8")
            self.assertEqual(decode_cloud.main([str(path), "--json", str(Path(directory) / "s.json")]), 1)


class PinnedCloudFieldsTests(unittest.TestCase):
    """The fields CBRTCld reads and the stop gate, as the pinned executable's cloud AIUpdate uses
    them; the range test cloud.lua's reach guard copies."""

    AREA_UPDATE, AREA_UPDATE_END, TRAVEL_UPDATE, GET_ALL_IN_RANGE = 0x2284B0, 0x22864C, 0x228650, 0x17F700

    @classmethod
    def setUpClass(cls):
        data = EXE.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXE_SHA256:
            raise unittest.SkipTest("CBRTS_TEST_EXE is not the pinned 2.7.3.0 executable")
        cls.pe = pefile.PE(data=data, fast_load=True)
        cls.base = cls.pe.OPTIONAL_HEADER.ImageBase
        cls.decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def listing(self, start, end):
        return [f"{i.mnemonic} {i.op_str}" for i in self.decoder.disasm(self.pe.get_data(start, end - start),
                                                                          self.base + start)]

    def assertInOrder(self, needles, listing):
        position = 0
        for needle in needles:
            found = [i for i in range(position, len(listing)) if listing[i] == needle]
            self.assertTrue(found, f"{needle!r} not found after instruction {position}")
            position = found[0] + 1

    def test_the_cloud_update_stops_for_everyone_but_the_caster(self):
        listing = self.listing(self.AREA_UPDATE, self.AREA_UPDATE_END)
        self.assertInOrder([
            "cmp dword ptr [rbx + 0x3c8], 0",           # arrived; else the travel update
            "cmp dword ptr [rcx + 0x9690], 0",          # a Time Stop runs
            "mov eax, dword ptr [rbx + 0x48]",          # its own object ID
            "cmp dword ptr [rcx + 0x9694], eax",        # is the stop's caster, or it returns
            "movzx eax, word ptr [rbx + 0x3ce]",        # countdown 0:
            "movzx eax, word ptr [rbx + 0x3cc]",        #   reload from the interval
            "mov word ptr [rbx + 0x3ce], ax",
            "movzx ecx, word ptr [rbx + 0x3c6]",        #   one less on a nonzero check
            "dec cx",
            "mov word ptr [rbx + 0x3c6], cx",
            "dec ax",                                   # else one countdown step
            "mov word ptr [rbx + 0x3ce], ax",
        ], listing)
        travel = self.listing(self.TRAVEL_UPDATE, self.TRAVEL_UPDATE + 0x48)
        self.assertInOrder(["cmp dword ptr [rcx + 0x9690], 0", "mov eax, dword ptr [rdi + 0x48]",
                            "cmp dword ptr [rcx + 0x9694], eax"], travel)

    def test_the_module_reads_those_offsets(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute((HERE / "CBRTCld.lua").read_text(encoding="utf-8"))
        offsets = lua.globals().CBRTCL.offsets
        self.assertEqual({k: offsets[k] for k in OFFSETS}, OFFSETS)

    def test_range_queries_scale_the_vertical_offset_by_four_thirds(self):
        listing = self.listing(self.GET_ALL_IN_RANGE, self.GET_ALL_IN_RANGE + 0xE0)
        self.assertInOrder(["mov r10d, dword ptr [rdx + 4]", "mov eax, 0x55555556", "shl r10d, 2", "imul r10d",
                            "imul edx, edx", "imul r8d, r8d", "imul r9d, r9d", "add r8d, edx", "cmp r8d, r9d"],
                           listing)
        request = (HERE / "rc" / "cloud.lua").read_text(encoding="utf-8")
        self.assertIn("((object.m_pos.y - y) * 4 / 3) ^ 2", request)


if __name__ == "__main__":
    unittest.main()
