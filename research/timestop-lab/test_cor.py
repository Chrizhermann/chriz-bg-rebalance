"""Offline validation of the full-scope clock correction (CBRTCor.lua).

Never runs the game or reads process memory. The Lua core runs in LuaJIT (lupa) over a synthetic
process image held in Python. A scenario driver feeds it creatures' ProcessEffectList calls,
pauses, Time Stop, rest and inactive spans around Python models of the four periodic workers;
one group checks those models against the pinned executable's own workers. The assembly gates
run in Unicorn with the Lua call replaced by a stub. Set CBRTS_TEST_DEPS as for test_observer.py;
CBRTS_TEST_EXE optionally selects a copy of the exact pinned BG2:EE executable.
Run: python -B research/timestop-lab/test_cor.py -v
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
from periodic_model import FAMILIES, native_seed, s32, u32, worker_step  # noqa: E402
import decode_cor  # noqa: E402

dependency_path = os.environ.get("CBRTS_TEST_DEPS")
if not dependency_path or not Path(dependency_path).is_dir():
    raise SystemExit("Set CBRTS_TEST_DEPS to the installed offline test dependencies directory")
sys.path.insert(0, dependency_path)

import capstone
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
import keystone
from lupa.luajit21 import LuaRuntime
import pefile
import unicorn
from unicorn import x86_const as x86


HERE = Path(__file__).resolve().parent
EXE = Path(os.environ.get(
    "CBRTS_TEST_EXE",
    r"C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition\Baldur.exe",
))
EXE_SHA256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
REG_NAMES = ("rax", "rcx", "rdx", "rbx", "rbp", "rsi", "rdi",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "rsp")
REGS = {name: getattr(x86, "UC_X86_REG_" + name.upper()) for name in REG_NAMES}
XMMS = [getattr(x86, f"UC_X86_REG_XMM{index}") for index in range(6)]

BASE = 0x140000000
GLOBAL = BASE + 0x667548
CHITIN, GAME = 0x310000, 0x320000
ACTOR, OTHER, EFFECTS, NODES, WORKERS = 0x400000, 0x480000, 0x500000, 0x540000, 0x580000
TIMED, EQUIPPED = 0x3000, 0x3060  # synthetic list offsets; Enable() finds the real ones
LIST_COUNTER, ACTOR_ID, OTHER_ID = 0x1A40, 0x1234, 0x2345
FAMILY_BY_VTABLE = {BASE + family["vtable"]: name for name, family in FAMILIES.items()}
NATIVE, SUPPRESS, RESTART, DELIVER = 0, 1, 2, 3


class Memory:
    """A sparse synthetic process image, shared by the Lua core and the Python models."""

    def __init__(self):
        self.regions = []
        self.writes = []

    def map(self, start, size):
        self.regions.append((start, bytearray(size)))

    def find(self, address, size):
        for start, data in self.regions:
            if start <= address and address + size <= start + len(data):
                return data, address - start
        raise IndexError(f"unmapped access {address:#x}+{size}")

    def put(self, address, format_, *values):
        data, offset = self.find(address, struct.calcsize("<" + format_))
        struct.pack_into("<" + format_, data, offset, *values)

    def get(self, address, format_):
        data, offset = self.find(address, struct.calcsize("<" + format_))
        return struct.unpack_from("<" + format_, data, offset)[0]

    def bindings(self, lua):
        def write(format_):
            def store(address, value):
                address, value = int(address), int(value)
                self.writes.append((address, struct.calcsize("<" + format_)))
                self.put(address, format_, value)  # struct rejects a value out of the field's range
            return store
        return lua.table_from({
            "r32": lambda address: self.get(int(address), "i"),
            "u32": lambda address: self.get(int(address), "I"),
            "s16": lambda address: self.get(int(address), "h"),
            "ptr": lambda address: self.get(int(address), "Q"),
            "w32": write("i"), "wu32": write("I"), "w16": write("H"),
        })


def load_cor(memory=None):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((HERE / "CBRTCor.lua").read_text(encoding="utf-8"))
    cor = lua.globals().CBRTC
    if memory is not None:
        cor.UseMemory(memory.bindings(lua))
        cor.Bind(BASE, TIMED, EQUIPPED)
    return lua, cor


def lua_sites(module):
    out = []
    for index in range(1, len(module.sites) + 1):
        site = dict(module.sites[index].items())
        if "args" in site:
            site["args"] = [site["args"][i] for i in range(1, len(site["args"]) + 1)]
        out.append(site)
    return out


class Image:
    """A synthetic process image with one or two creatures and their effect lists."""

    def __init__(self, world=33000):
        self.mem = Memory()
        for start, size in ((GLOBAL & ~0xFFF, 0x1000), (CHITIN, 0x2000), (GAME, 0xA000),
                            (ACTOR, 0x6000), (OTHER, 0x6000), (EFFECTS, 0x40000),
                            (NODES, 0x40000), (WORKERS, 0x40000)):
            self.mem.map(start, size)
        self.mem.put(GLOBAL, "Q", CHITIN)
        self.mem.put(CHITIN + 0x1090, "Q", GAME)
        self.mem.put(GAME + 0x9694, "I", 0x7777)  # the caster, someone else
        for actor, ident in ((ACTOR, ACTOR_ID), (OTHER, OTHER_ID)):
            self.mem.put(actor + 0x48, "I", ident)
            self.mem.put(actor + LIST_COUNTER, "I", 1675)
        self.lists = {}
        self.next_node = NODES
        self.world(world)

    def world(self, value):
        self.mem.put(GAME + 0x3FA0, "I", u32(value))

    def stop(self, active):
        self.mem.put(GAME + 0x9690, "I", 90 if active else 0)

    def effect(self, address, *, opcode=0, timing=0x1000, deadline=0, origin=0):
        self.mem.put(address + 0x10, "I", opcode)
        self.mem.put(address + 0x24, "II", timing, u32(deadline))
        self.mem.put(address + 0x6C, "I", u32(origin))
        return address

    def link(self, effects, actor=ACTOR, offset=TIMED):
        """CPtrList: m_pNodeHead +8; CNode pNext +0, data +0x10."""
        nodes = []
        for effect in effects:
            nodes.append(self.next_node)
            self.next_node += 0x20
        for index, (node, effect) in enumerate(zip(nodes, effects)):
            self.mem.put(node, "QQQ", nodes[index + 1] if index + 1 < len(nodes) else 0,
                         nodes[index - 1] if index else 0, effect)
        self.mem.put(actor + offset + 8, "Q", nodes[0] if nodes else 0)

    def deadline(self, effect):
        return self.mem.get(effect + 0x28, "I")

    def origin(self, effect):
        return self.mem.get(effect + 0x6C, "I")

    def worker(self, address, family, *, period=2, phase=0, counter=0, remaining=180, mode=3,
               amount22=0, amount24=1):
        self.mem.put(address, "QII", BASE + FAMILIES[family]["vtable"], 0, 0)
        self.mem.put(address + 0x18, "HHI", period & 0xFFFF, phase, u32(counter))
        self.mem.put(address + 0x20, "HHH", mode, amount22, amount24)
        self.mem.put(address + 0x28, "i", remaining)
        return address

    def read_worker(self, address):
        period, phase, counter = struct.unpack("<HHI", bytes(self.mem.find(address + 0x18, 8)[0][
            self.mem.find(address + 0x18, 8)[1]:self.mem.find(address + 0x18, 8)[1] + 8]))
        mode, amount22, amount24 = (self.mem.get(address + 0x20, "H"), self.mem.get(address + 0x22, "H"),
                                    self.mem.get(address + 0x24, "H"))
        return {"period": period, "phase": phase, "counter": counter, "mode": mode, "amount22": amount22,
                "amount24": amount24, "remaining": self.mem.get(address + 0x28, "i"),
                "done": self.mem.get(address + 8, "I")}

    def write_worker(self, address, fields):
        self.mem.put(address + 8, "I", fields["done"])
        self.mem.put(address + 0x18, "HHI", fields["period"], fields["phase"], u32(fields["counter"]))
        self.mem.put(address + 0x28, "i", fields["remaining"])

    def counter(self, address):
        return self.mem.get(address + 0x1C, "i")


class CoreTests(unittest.TestCase):
    """The gate targets one at a time against a synthetic image."""

    def setUp(self):
        self.image = Image()
        self.lua, self.cor = load_cor(self.image.mem)

    def actor(self, sprite=ACTOR):
        state = self.cor.ActorState(sprite)
        return dict(state.items()) if state is not None else None

    def stats(self):
        return dict(self.cor.stats.items())

    def at(self, world):
        self.image.world(world)

    def test_frozen_moves_deadlines_delayed_starts_and_periodic_origins_once_per_world_tick(self):
        image = self.image
        timed = [image.effect(EFFECTS + 0x000, timing=0x1000, deadline=34000),
                 image.effect(EFFECTS + 0x200, timing=6, deadline=33500),  # delayed start
                 image.effect(EFFECTS + 0x400, timing=7, deadline=33600),
                 image.effect(EFFECTS + 0x600, timing=8, deadline=33700),
                 image.effect(EFFECTS + 0x800, timing=1, deadline=12),  # permanent: untouched
                 image.effect(EFFECTS + 0xA00, opcode=98, deadline=34100, origin=33000),
                 image.effect(EFFECTS + 0xC00, opcode=272, timing=6, deadline=33900, origin=32990),
                 image.effect(EFFECTS + 0xE00, opcode=12, deadline=34200, origin=33001),
                 image.effect(EFFECTS + 0x1000, deadline=0xFFFFFFFF)]  # endless: never wraps
        equipped = [image.effect(EFFECTS + 0x1200, opcode=25, timing=2, deadline=5, origin=1000),
                    image.effect(EFFECTS + 0x1400, opcode=78, timing=2, origin=1001),
                    image.effect(EFFECTS + 0x1600, opcode=12, timing=2, deadline=7, origin=1002)]
        image.link(timed)
        image.link(equipped, offset=EQUIPPED)
        before = {effect: (image.deadline(effect), image.origin(effect)) for effect in timed + equipped}
        moved_deadline = {timed[0], timed[1], timed[2], timed[3], timed[5], timed[6], timed[7]}
        moved_origin = {timed[5], timed[6], equipped[0], equipped[1]}
        for world, shifts in ((34001, 1), (34001, 1), (34000, 1), (34002, 2)):
            with self.subTest(world=world):
                self.at(world)
                self.cor.Frozen(ACTOR)
                for effect in timed + equipped:
                    deadline, origin = before[effect]
                    self.assertEqual(image.deadline(effect), u32(deadline + shifts * (effect in moved_deadline)))
                    self.assertEqual(image.origin(effect), u32(origin + shifts * (effect in moved_origin)))
        self.assertEqual(self.actor()["frozen"], 2)
        self.assertEqual(self.stats()["frozen_ticks"], 2)
        self.assertEqual(self.stats()["deadline_shifts"], 14)
        self.assertEqual(self.stats()["origin_shifts"], 8)

    def test_a_slowed_frozen_creature_counts_the_tick_it_skipped(self):
        self.image.link([self.image.effect(EFFECTS, deadline=34000)])
        self.at(33100)
        self.cor.Frozen(ACTOR)
        self.cor.Entry(ACTOR, 1)  # the pass was frozen
        self.at(33102)
        self.cor.Frozen(ACTOR)
        self.assertEqual((self.actor()["frozen"], self.image.deadline(EFFECTS)), (3, 34003))
        # Without a frozen pass before it, a gap counts one tick: the stop may have begun in it.
        self.at(33110)
        self.cor.Entry(ACTOR, 1)
        self.at(33112)
        self.cor.Frozen(ACTOR)
        self.assertEqual(self.actor()["frozen"], 4)
        # A gap longer than MAXGAP is not a slowed creature: one tick.
        self.cor.Entry(ACTOR, 1)
        self.at(33112 + 15)
        self.cor.Frozen(ACTOR)
        self.assertEqual(self.actor()["frozen"], 5)

    def test_frozen_walk_is_bounded_on_a_corrupt_cyclic_list(self):
        image = self.image
        image.effect(EFFECTS, deadline=40000)
        image.mem.put(NODES, "QQQ", NODES, 0, EFFECTS)  # a node pointing at itself
        image.mem.put(ACTOR + TIMED + 8, "Q", NODES)
        self.cor.Frozen(ACTOR)
        self.assertEqual(image.deadline(EFFECTS), 40000 + 4096)

    def test_entry_decides_once_per_pass_for_every_worker(self):
        cor, image = self.cor, self.image
        image.mem.put(ACTOR + LIST_COUNTER, "I", 1675)
        self.at(33000)
        cor.Entry(ACTOR, 1)
        self.assertEqual(self.actor()["kappa"], 1675 - 33000)
        self.assertEqual((self.actor()["last_t"], self.actor()["next_t"]), (33000, 33001))
        self.assertEqual(cor.current.mode, DELIVER)
        cor.Entry(ACTOR, 1)  # a second hasted update
        self.assertEqual(cor.current.mode, SUPPRESS)
        self.at(32999)  # paused: world time stepped back
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.current.mode, SUPPRESS)
        self.at(33000)  # the repeated tick after the pause
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.current.mode, SUPPRESS)
        self.at(33002)  # slowed: one tick skipped
        cor.Entry(ACTOR, 1)
        self.assertEqual((cor.current.mode, cor.current.pLast, cor.current.pNext), (DELIVER, 33000, 33001))
        self.at(33002 + 15)  # an area left alone for 15 ticks: its list counter did not move
        image.mem.put(ACTOR + LIST_COUNTER, "I", 1679)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.current.mode, RESTART)
        self.assertEqual((self.actor()["last_t"], self.actor()["next_t"]), (33017, 33018))
        self.assertEqual(self.actor()["kappa"], 1679 - 33017)  # continues from the native counter
        self.assertEqual(self.stats()["restarts"], 1)
        worker = image.worker(WORKERS, "regeneration")
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)
        self.assertEqual(image.counter(worker), 1679)

    def test_time_compression_passes_natively_and_counts_as_delivered(self):
        cor = self.cor
        self.at(33000)
        cor.Entry(ACTOR, 1)
        self.at(33000 + 7200)  # AdvanceCurrentTime moved world time before CompressTime runs
        cor.Entry(ACTOR, 7200)
        self.assertEqual(cor.current.mode, NATIVE)
        self.assertEqual(cor.Dispatch(ACTOR, WORKERS, 7200), -1)
        self.assertEqual((self.actor()["last_t"], self.actor()["next_t"]), (40200, 40201))
        self.at(40201)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.current.mode, DELIVER)
        self.assertEqual(self.stats()["compressed"], 1)
        # An elapsed of 0 changes nothing.
        cor.Entry(ACTOR, 0)
        self.assertEqual((cor.current.mode, self.actor()["last_t"]), (NATIVE, 40201))

    def test_time_compression_during_a_stop_freezes_the_span(self):
        cor, image = self.cor, self.image
        image.link([image.effect(EFFECTS, deadline=34000), image.effect(EFFECTS + 0x200, opcode=98,
                                                                        deadline=34100, origin=33000)])
        image.stop(True)
        self.at(33000)
        cor.Frozen(ACTOR)
        cor.Entry(ACTOR, 1)
        self.at(33000 + 900)
        cor.Entry(ACTOR, 900)
        self.assertEqual((image.deadline(EFFECTS), image.deadline(EFFECTS + 0x200), image.origin(EFFECTS + 0x200)),
                         (34901, 35001, 33901))
        self.assertEqual(self.actor()["frozen"], 901)
        self.assertEqual(cor.current.mode, NATIVE)
        self.assertEqual(self.stats()["compressed_frozen"], 1)
        # The caster and an immune creature are not frozen.
        for setup in (lambda: image.mem.put(GAME + 0x9694, "I", ACTOR_ID),
                      lambda: image.mem.put(ACTOR + 0x20A0, "I", 1),
                      lambda: (image.mem.put(ACTOR + 0x4EA4, "I", 1), image.mem.put(ACTOR + 0x13F8, "I", 1))):
            with self.subTest(setup=setup):
                image.mem.put(GAME + 0x9694, "I", 0x7777)
                image.mem.put(ACTOR + 0x20A0, "I", 0)
                image.mem.put(ACTOR + 0x4EA4, "I", 0)
                setup()
                frozen = self.actor()["frozen"]
                self.at(self.image.mem.get(GAME + 0x3FA0, "I") + 900)
                cor.Entry(ACTOR, 900)
                self.assertEqual(self.actor()["frozen"], frozen)

    def test_first_sight_in_a_frozen_pass_counts_that_tick_as_delivered(self):
        cor = self.cor
        self.at(33000)
        cor.Frozen(ACTOR)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.current.mode, SUPPRESS)
        self.assertEqual(self.actor()["last_t"], 33000 - 1)

    def test_dispatch_runs_once_per_active_tick_on_the_creature_grid(self):
        cor, image = self.cor, self.image
        worker = image.worker(WORKERS, "regeneration", remaining=100)
        self.at(33000)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)
        self.assertEqual(image.counter(worker), 1675)
        cor.Entry(ACTOR, 1)  # second hasted update: a no-op call
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 0)
        self.assertEqual(image.counter(worker), 0)
        self.at(33001)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)
        self.assertEqual(image.counter(worker), 1676)
        # Another creature's dispatch without its own entry stays native.
        self.assertEqual(cor.Dispatch(OTHER, worker, 1), -1)
        self.assertEqual(self.stats()["unmatched"], 1)

    def test_slowed_gaps_count_down_and_deliver_the_pulse_that_fell_inside_them(self):
        cor, image = self.cor, self.image
        for family, step in (("regeneration", 1), ("poison", 2)):
            with self.subTest(family=family):
                self.setUp()
                cor, image = self.cor, self.image
                kappa = 1675 - 33000
                worker = image.worker(WORKERS, family, remaining=100)
                self.at(33000)
                cor.Entry(ACTOR, 1)
                cor.Dispatch(ACTOR, worker, 1)
                for world in range(33002, 33002 + 40, 2):
                    self.at(world)
                    cor.Entry(ACTOR, 1)
                    self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 2)
                    counter = image.counter(worker)
                    boundary_now = (world + kappa + step) % 15 == 0
                    boundary_skipped = (world - 1 + kappa + step) % 15 == 0
                    if boundary_skipped:
                        self.assertEqual(counter, world - 1 + kappa)
                    else:
                        self.assertEqual(counter, world + kappa)
                    self.assertEqual((counter + step) % 15 == 0, boundary_now or boundary_skipped)

    def test_a_slowed_gap_delivers_nothing_past_the_last_tick(self):
        cor, image = self.cor, self.image
        kappa = 1675 - 33000
        worker = image.worker(WORKERS, "regeneration", remaining=1)
        self.at(33000)
        cor.Entry(ACTOR, 1)
        self.at(33002)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 2)
        self.assertEqual(image.counter(worker), 33001 + kappa)  # the worker's last tick, nextT + 1 - 1

    def test_a_new_effect_gets_no_pulse_from_before_it_existed(self):
        kappa = 1675 - 33000
        # A skipped tick whose counter is a boundary: (world + kappa + 1) % 15 == 0.
        skipped = next(world for world in range(33002, 33100) if (world + kappa + 1) % 15 == 0)
        # Applied on the tick before it, the effect gets that boundary; applied on it, not.
        for applied, counter in ((skipped - 1, skipped + kappa), (skipped, skipped + 1 + kappa)):
            with self.subTest(applied=applied - skipped):
                self.setUp()
                cor, image = self.cor, self.image
                parent = image.effect(EFFECTS, opcode=98, deadline=34000, origin=applied)
                self.at(33000)
                cor.Entry(ACTOR, 1)  # anchors the grid
                self.at(skipped - 1)
                cor.Entry(ACTOR, 1)
                self.at(skipped + 1)
                worker = image.worker(WORKERS, "regeneration", remaining=999)
                cor.Construct(ACTOR, parent, worker, 1)
                cor.Entry(ACTOR, 1)
                self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)
                self.assertEqual(image.counter(worker), counter)
        # Fifteen ticks later the skipped tick is a boundary again. The same parent rebuilt then
        # gets it; a new parent built in the same pass does not.
        self.at(skipped + 14)
        cor.Entry(ACTOR, 1)
        self.at(skipped + 16)
        rebuilt = image.worker(WORKERS + 0x40, "regeneration", remaining=999)
        cor.Construct(ACTOR, parent, rebuilt, 1)
        other = image.effect(EFFECTS + 0x200, opcode=98, deadline=34000, origin=skipped + 15)
        new = image.worker(WORKERS + 0x80, "regeneration", remaining=999)
        cor.Construct(ACTOR, other, new, 1)
        cor.Entry(ACTOR, 1)
        cor.Dispatch(ACTOR, rebuilt, 1)
        cor.Dispatch(ACTOR, new, 1)
        self.assertEqual(image.counter(rebuilt), skipped + 15 + kappa)
        self.assertEqual(image.counter(new), skipped + 16 + kappa)

    def test_a_parent_rebuilt_long_after_its_last_rebuild_is_still_known(self):
        cor, image = self.cor, self.image
        parent = image.effect(EFFECTS, opcode=98, deadline=40000, origin=33000)
        self.at(33000)
        cor.Construct(ACTOR, parent, image.worker(WORKERS, "regeneration"), 1)
        for world in range(33000, 33000 + 600):
            self.at(world)
            cor.Entry(ACTOR, 1)
        cor.Construct(ACTOR, parent, image.worker(WORKERS + 0x40, "regeneration"), 1)
        self.assertEqual(self.stats()["fresh"], 1)
        # A parent not rebuilt for STALE_AGE active ticks is forgotten by the sweep.
        for world in range(33600, 33600 + int(self.cor.STALE_AGE) + 2 * 900, 300):
            self.at(world)
            cor.Entry(ACTOR, 1)
        self.assertEqual(self.actor()["parents"], 0)

    def test_a_construct_on_another_class_changes_nothing(self):
        cor, image = self.cor, self.image
        parent = image.effect(EFFECTS, opcode=98, deadline=34000, origin=33000)
        worker = image.worker(WORKERS, "poison", phase=1, remaining=50)
        self.at(33010)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.Construct(ACTOR, parent, worker, 1), 0)  # a regeneration site
        self.assertEqual((image.read_worker(worker)["phase"], image.read_worker(worker)["remaining"]), (1, 50))
        self.assertEqual((self.stats()["unmatched"], self.stats()["constructs"]), (1, 0))

    def test_a_reused_parent_address_with_another_origin_is_a_new_effect(self):
        cor, image = self.cor, self.image
        parent = image.effect(EFFECTS, opcode=98, deadline=34000, origin=33000)
        self.at(33010)
        cor.Construct(ACTOR, parent, image.worker(WORKERS, "regeneration"), 1)
        self.assertEqual(self.stats()["fresh"], 1)
        cor.Construct(ACTOR, parent, image.worker(WORKERS + 0x40, "regeneration"), 1)
        self.assertEqual(self.stats()["fresh"], 1)  # rebuilt
        image.effect(EFFECTS, opcode=98, deadline=34100, origin=33010)
        cor.Construct(ACTOR, parent, image.worker(WORKERS + 0x80, "regeneration"), 1)
        self.assertEqual(self.stats()["fresh"], 2)
        # Frozen ticks move a rebuilt parent's origin; it stays the same effect.
        image.link([parent])
        cor.Frozen(ACTOR)
        cor.Construct(ACTOR, parent, image.worker(WORKERS + 0xC0, "regeneration"), 1)
        self.assertEqual(self.stats()["fresh"], 2)

    def test_a_worker_built_after_the_delivery_seeds_for_the_next_active_tick(self):
        cor, image = self.cor, self.image
        parent = image.effect(EFFECTS, opcode=98, deadline=34000, origin=32990)
        for world, ahead in ((33010, 1), (33009, 2)):  # second hasted update; paused (stepped back)
            with self.subTest(ahead=ahead):
                self.setUp()
                cor, image = self.cor, self.image
                image.effect(EFFECTS, opcode=98, deadline=34000, origin=32990)
                self.at(33010)
                cor.Entry(ACTOR, 1)
                self.at(world)
                for period in (3, -5, 0):
                    worker = image.worker(WORKERS, "regeneration", period=period,
                                          phase=native_seed(world, 32990, period), remaining=34000 - world)
                    cor.Construct(ACTOR, parent, worker, 1)
                    fields = image.read_worker(worker)
                    self.assertEqual(fields["phase"], native_seed(world + ahead, 32990, period))
                    self.assertEqual(fields["remaining"], 34000 - world - ahead)
                self.assertEqual(self.actor()["next_t"], 33011)
                self.at(33011)
                cor.Entry(ACTOR, 1)
                self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)

    def test_a_worker_built_before_the_delivery_keeps_the_native_seed(self):
        cor, image = self.cor, self.image
        parent = image.effect(EFFECTS, opcode=25, deadline=34000, origin=32990)
        self.at(33010)
        cor.Entry(ACTOR, 1)
        self.at(33012)  # slowed: the next pass rebuilds before its dispatch
        worker = image.worker(WORKERS, "poison", period=3, phase=native_seed(33012, 32990, 3), remaining=988)
        cor.Construct(ACTOR, parent, worker, 2)
        self.assertEqual((image.read_worker(worker)["phase"], image.read_worker(worker)["remaining"]),
                         (native_seed(33012, 32990, 3), 988))
        self.assertEqual(self.actor()["next_t"], 33012)
        cor.Entry(ACTOR, 1)
        self.assertEqual(cor.Dispatch(ACTOR, worker, 1), 1)

    def test_state_resets_on_a_new_object_id_and_stale_creatures_are_swept(self):
        cor, image = self.cor, self.image
        self.at(33000)
        cor.Entry(ACTOR, 1)
        cor.Entry(OTHER, 1)
        image.mem.put(ACTOR + 0x48, "I", 0x9999)
        cor.Entry(ACTOR, 1)
        self.assertEqual(self.actor()["id"], 0x9999)
        self.assertEqual(self.actor()["last_t"], 33000)  # a fresh clock, delivered this pass
        self.assertEqual(self.stats()["actors_created"], 3)
        self.at(33000 + 9000 + 900)
        cor.Entry(ACTOR, 1)
        self.assertIsNone(self.actor(OTHER))
        self.assertEqual(self.stats()["actors_swept"], 1)
        cor.Reset()
        self.assertIsNone(self.actor())

    def test_no_target_returns_the_gate_error_value(self):
        cor, image = self.cor, self.image
        worker = image.worker(WORKERS, "repeat")
        parent = image.effect(EFFECTS, opcode=272, deadline=34000, origin=33000)
        results = [cor.Frozen(ACTOR), cor.Entry(ACTOR, 1), cor.Dispatch(ACTOR, worker, 1),
                   cor.Construct(ACTOR, parent, worker, 4), cor.Dispatch(OTHER, worker, 1)]
        self.assertNotIn(-2, results)
        image.mem.put(GLOBAL, "Q", 0)  # no game object: nothing happens
        self.assertEqual([cor.Frozen(ACTOR), cor.Entry(ACTOR, 1), cor.Construct(ACTOR, parent, worker, 4)],
                         [0, 0, 0])


class RecorderTests(unittest.TestCase):
    """The lab recorder: in observe mode the targets record and change nothing; corrected, they
    record their decisions; only watched creatures, while recording, within the limit."""

    def setUp(self):
        self.image = Image()
        self.lua, self.cor = load_cor(self.image.mem)

    def at(self, world):
        self.image.world(world)

    def watch(self, *ids):
        self.cor.Watch(self.lua.table(*ids))
        self.cor.Record(True)

    def events(self):
        recorder = self.cor.recorder
        return [json.loads(recorder.lines[index]) for index in range(1, recorder.n + 1)]

    def test_observe_records_every_target_and_writes_nothing(self):
        image, cor = self.image, self.cor
        effect = image.effect(EFFECTS, opcode=98, deadline=34000, origin=33000)
        image.link([effect])
        worker = image.worker(WORKERS, "regeneration", phase=1, counter=1680, remaining=900)
        image.mem.put(ACTOR + 0x57C, "h", 40)
        image.mem.put(ACTOR + 0x3A0, "I", 777)
        image.stop(True)
        cor.observe = True
        self.watch(ACTOR_ID)
        self.at(33100)
        image.mem.writes.clear()
        self.assertEqual([cor.Frozen(ACTOR), cor.Entry(ACTOR, 1), cor.Dispatch(ACTOR, worker, 1),
                          cor.Construct(ACTOR, effect, worker, 1)], [0, 0, -1, 0])
        self.assertEqual(image.mem.writes, [])
        self.assertIsNone(cor.ActorState(ACTOR))
        self.assertEqual(self.events(), [
            ["F", ACTOR_ID, 33100, None],
            ["E", ACTOR_ID, 33100, 1, 1675, 777, 40, 1, None, None, None, None, 0],
            ["D", ACTOR_ID, 33100, worker, 1, 1, -1, 1680, 1680, 2, 1, 3, 0, 1, 900, 0],
            ["C", ACTOR_ID, 33100, effect, worker, 1, 33000, 34000, 0x1000, 2, 1, 1, 900, 900, None, None],
        ])

    def test_the_corrected_mode_records_its_decisions(self):
        image, cor = self.image, self.cor
        effect = image.effect(EFFECTS, opcode=98, deadline=33300, origin=33100)
        image.link([effect])
        self.watch(ACTOR_ID)
        self.at(33100)
        cor.Entry(ACTOR, 1)
        worker = image.worker(WORKERS, "regeneration", remaining=200)
        cor.Construct(ACTOR, effect, worker, 1)  # after this tick's delivery: ahead
        image.mem.put(ACTOR + LIST_COUNTER, "I", 1676)
        image.mem.put(worker + 0x1C, "I", 1676)
        self.at(33101)
        cor.Entry(ACTOR, 1)
        result = cor.Dispatch(ACTOR, worker, 1)
        events = self.events()
        self.assertEqual([event[0] for event in events], ["E", "C", "E", "D"])
        self.assertEqual(events[0][7:], [0, DELIVER, 33100, 1675 - 33100, 0, 0])
        self.assertEqual(events[1][12:], [200, 199, 1, 1])  # counted down one tick ahead; new
        self.assertEqual(events[3][5:9], [1, result, 1676, 1676])  # normal speed: the native counter

    def test_frozen_passes_record_the_ticks_they_counted(self):
        self.image.link([self.image.effect(EFFECTS, deadline=34000)])
        self.watch(ACTOR_ID)
        for world in (33100, 33100, 33102):  # a second hasted pass, then a slowed gap
            self.at(world)
            self.cor.Frozen(ACTOR)
            self.cor.Entry(ACTOR, 1)
        self.assertEqual([event[3] for event in self.events() if event[0] == "F"], [1, 0, 2])

    def test_only_watched_creatures_are_recorded_while_recording(self):
        cor = self.cor
        self.watch(OTHER_ID)
        self.at(33000)
        cor.Entry(ACTOR, 1)
        self.assertEqual(self.events(), [])
        cor.Entry(OTHER, 1)
        cor.Record(False)
        cor.Entry(OTHER, 1)
        self.assertEqual([event[1] for event in self.events()], [OTHER_ID])

    def test_events_past_the_limit_are_counted_not_kept(self):
        self.watch(ACTOR_ID)
        self.cor.recorder.limit = 2
        for world in range(33000, 33005):
            self.at(world)
            self.cor.Entry(ACTOR, 1)
        self.assertEqual((self.cor.recorder.n, self.cor.recorder.dropped), (2, 3))


class Creature:
    """One synthetic creature driven the way the engine drives it, with the correction's targets
    at their sites. Each ProcessEffectList call runs the frozen target while Time Stop holds the
    creature, the expiry check at its once-per-second tick, a rebuild of every worker through the
    native seed and the construct target when the list changed (an application, a unit submitted
    by a worker, a removal, Haste or Slow, the end of a stop), then the dispatch: the entry target
    and, per worker, the list counter copy, the dispatch target and the worker model unless
    frozen; then the list counter rises. With corrected=False no target runs: the native engine."""

    def __init__(self, case, *, corrected=True, world=33000, counter=1675, ident=ACTOR_ID, duration=180,
                 period=2, families=("regeneration",), witness=None):
        self.case, self.corrected, self.witness = case, corrected, witness
        self.image = Image(world)
        self.image.mem.put(ACTOR + 0x48, "I", ident)
        self.image.mem.put(ACTOR + LIST_COUNTER, "I", counter)
        self.lua, self.cor = load_cor(self.image.mem) if corrected else (None, None)
        if corrected:
            self.cor.Reset()
            self.image.mem.put(GLOBAL, "Q", CHITIN)
        self.world, self.list_counter, self.ident, self.ai = world, counter, ident, 0
        self.duration, self.period, self.families = duration, period, families
        self.speed, self.slow_parity = "normal", 0
        self.stop_from = self.stop_until = None
        self.immune = False
        self.stopped_ticks = set()  # every tick a stop held the creature, with a call or not
        self.parents = []  # dicts: address, family, alive
        self.workers = []  # dicts: address, family, parent
        self.rebuild_due = False
        self.next_effect, self.next_worker = EFFECTS, WORKERS
        self.units = {family: [] for family in FAMILIES}
        self.unit_worlds = {family: [] for family in FAMILIES}
        self.ends = {family: [] for family in FAMILIES}
        self.expires = {}  # family: the active tick its effect runs out

    def sync(self):
        self.image.world(self.world)
        self.image.mem.put(ACTOR + LIST_COUNTER, "I", u32(self.list_counter))
        self.image.mem.put(ACTOR + 0x20A0, "I", int(self.immune))  # the Time Stop immunity stat
        self.image.stop(self.stopped())

    def active(self):
        return self.world - sum(1 for tick in self.stopped_ticks if tick <= self.world)

    def stopped(self):
        return self.stop_until is not None and self.stop_from <= self.world < self.stop_until

    def frozen(self):
        return self.stopped() and not self.immune

    def calls(self):
        return {"normal": 1, "haste": 2, "slow": int(self.world % 2 == self.slow_parity)}[self.speed]

    def link(self):
        alive = [parent["address"] for parent in self.parents if parent["alive"]]
        self.image.link(alive)

    def apply(self, *, outside=False, families=None, duration=None):
        """Adds one timed effect per family. Outside the creature's calls (the console while
        paused, another creature's action) its worker is built at once, else in the next call."""
        added = []
        for family in families or self.families:
            address = self.next_effect
            self.next_effect += 0x200
            self.image.effect(address, opcode=FAMILIES[family]["opcode"],
                              deadline=self.world + (duration or self.duration), origin=self.world)
            parent = {"address": address, "family": family, "alive": True}
            self.parents.append(parent)
            added.append(parent)
            self.expires[family] = self.active() + (duration or self.duration)
        self.link()
        if outside:
            for parent in added:
                self.construct(parent)
        self.rebuild_due = True
        return added

    def touch(self):
        """Another effect is applied or removed (Haste starting or ending is one): the next call
        rebuilds every worker."""
        self.rebuild_due = True

    def remove(self, family=None):
        """Explicit removal (op321): the next call's rebuild drops the workers."""
        for parent in self.parents:
            if family is None or parent["family"] == family:
                parent["alive"] = False
        self.link()
        self.rebuild_due = True

    def construct(self, parent):
        address = self.next_worker
        self.next_worker += 0x40
        if self.next_worker >= WORKERS + 0x400:
            self.next_worker = WORKERS  # addresses are reused, as the allocator does
        deadline, origin = self.image.deadline(parent["address"]), self.image.origin(parent["address"])
        self.image.worker(address, parent["family"], period=self.period,
                          phase=native_seed(self.world, origin, self.period), counter=0,
                          remaining=s32(deadline - self.world))
        if self.corrected:
            self.cor.Construct(ACTOR, parent["address"], address, FAMILIES[parent["family"]]["id"])
        self.workers = [worker for worker in self.workers if worker["address"] != address]
        self.workers.append({"address": address, "family": parent["family"], "parent": parent})

    def rebuild(self):
        self.workers = []
        for parent in self.parents:
            if parent["alive"]:
                self.construct(parent)

    def pel(self, elapsed=1):
        """One ProcessEffectList call at the current world value (or a time compression with
        elapsed > 1, which only dispatches)."""
        self.sync()
        if elapsed == 1:
            self.ai += 1
            frozen = self.frozen()
            if self.stop_until is not None and self.world >= self.stop_until:
                self.stop_from = self.stop_until = None  # the stop's end forces a rebuild
                self.rebuild_due = True
                self.sync()
            if frozen and self.corrected:
                self.cor.Frozen(ACTOR)
            if self.rebuild_due or self.ai % 15 == self.ident % 15:
                for parent in self.parents:
                    if parent["alive"] and self.world >= self.image.deadline(parent["address"]):
                        parent["alive"] = False
                        self.rebuild_due = True
                if self.rebuild_due:
                    self.rebuild_due = False
                    self.link()
                    self.rebuild()
        else:
            frozen = self.frozen()
        if self.corrected:
            self.cor.Entry(ACTOR, elapsed)
        for worker in list(self.workers):
            address, family = worker["address"], worker["family"]
            self.image.mem.put(address + 0x1C, "I", u32(self.list_counter))
            used = elapsed
            if self.corrected:
                result = self.cor.Dispatch(ACTOR, address, elapsed)
                if result >= 0:
                    used = result
            if not frozen:
                fields = self.image.read_worker(address)
                units = worker_step(fields, used, family)
                self.image.write_worker(address, fields)
                if units:
                    self.units[family] += [self.active()] * units
                    self.unit_worlds[family] += [self.world] * units
                    self.rebuild_due = True  # the submitted effect changes the list
            if self.image.read_worker(address)["done"]:
                self.ends[family].append(self.active())
                self.workers.remove(worker)
        self.list_counter += 1
        self.sync()

    def tick(self, calls=None):
        """One world tick. A witness is another creature at normal speed that the same stop
        freezes, updated before or after this one."""
        self.world += 1
        if self.witness == "before":
            self.mark()
        for _ in range(self.calls() if calls is None else calls):
            self.pel()
        if self.witness == "after":
            self.mark()

    def mark(self):
        if self.corrected and self.stopped():
            self.sync()
            self.cor.Frozen(OTHER)

    def ticks(self, count):
        for _ in range(count):
            self.tick()
        return self

    def set_speed(self, speed, parity=0):
        """Haste or Slow starts or ends: its effect changes the list, so the next call rebuilds."""
        self.speed, self.slow_parity = speed, parity
        self.touch()

    def stop(self, length, *, now=False):
        """Time Stop by another creature, from the next tick or, with now, this tick's later calls."""
        self.stop_from = self.world if now else self.world + 1
        self.stop_until = self.stop_from + length
        if not self.immune:
            self.stopped_ticks.update(range(self.stop_from, self.stop_until))

    def pause(self, during=None):
        """A pause after this tick's calls steps world time back one tick. After unpausing a
        hasted creature gets an extra call at the paused value, then the paused tick runs again."""
        self.world -= 1
        self.sync()
        if during:
            during()
        if self.speed == "haste":
            self.pel()
        self.tick()

    def rest(self, span):
        """AdvanceCurrentTime moves world time, then CompressTime dispatches the whole span and
        sets m_newEffect."""
        self.world += span
        self.pel(elapsed=span)
        self.rebuild_due = True

    def leave(self, span):
        """The creature's area is not processed for `span` ticks."""
        self.world += span

    def finish(self, limit=900):
        for _ in range(limit):
            if all(not parent["alive"] for parent in self.parents) and not self.workers:
                return self
            self.tick()
        raise AssertionError("the effects never ended")

    def record(self):
        return {family: (self.units[family], self.ends[family]) for family in self.families}


ALL = tuple(FAMILIES)


class ScenarioTests(unittest.TestCase):
    """The targets against a creature's call order, compared in active time with the native
    engine driving a creature that is never hasted, slowed, paused or stopped, runs on the same
    list counter grid and sees the same effect applications (Haste starting or ending is one)."""

    def creature(self, **options):
        return Creature(self, **options)

    def native(self, **options):
        return Creature(self, corrected=False, **options)

    def assertSame(self, corrected, reference, *, early=0, late=0, families=None):
        """Every family submits as many units as the reference, each at most `early` ticks before
        and `late` ticks after it, and none after its effect ran out."""
        for family in families or corrected.families:
            got, want = corrected.units[family], reference.units[family]
            detail = f"{family}: corrected {got}, reference {want}"
            self.assertGreater(len(want), 0, detail)
            self.assertEqual(len(got), len(want), detail)
            for unit, wanted in zip(got, want):
                self.assertTrue(-early <= unit - wanted <= late, detail)
            self.assertTrue(all(unit <= corrected.expires[family] + late for unit in got), detail)

    def test_normal_speed_is_native_for_every_family(self):
        corrected = self.creature(families=ALL).ticks(5)
        native = self.native(families=ALL).ticks(5)
        for creature in (corrected, native):
            creature.apply()
            creature.finish()
        self.assertEqual(corrected.record(), native.record())
        stats = dict(corrected.cor.stats.items())
        self.assertEqual({key: stats[key] for key in ("suppressed", "stretched", "boundaries", "restarts",
                                                      "ahead", "behind", "carried")},
                         dict.fromkeys(("suppressed", "stretched", "boundaries", "restarts", "ahead", "behind",
                                        "carried"), 0))
        for family in ALL:
            self.assertIn(len(native.units[family]), (5, 6, 7), family)

    def test_applications_outside_the_creatures_calls_keep_the_native_pattern(self):
        corrected = self.creature(families=ALL).ticks(6)
        native = self.native(families=ALL).ticks(6)
        for creature in (corrected, native):
            creature.apply(outside=True)
            creature.finish()
        self.assertEqual(corrected.record(), native.record())

    def test_an_application_in_a_pause_counts_from_the_tick_the_pause_began(self):
        """A pause steps world time back, so the effect is stamped one tick earlier, natively too;
        its first update comes on the tick after the pause began."""
        for speed in ("normal", "haste"):
            with self.subTest(speed=speed):
                corrected = self.creature(families=ALL).ticks(5)
                native = self.native(families=ALL).ticks(5)
                if speed == "haste":
                    corrected.set_speed("haste")
                    native.touch()
                corrected.tick()
                native.tick()
                corrected.pause(during=lambda: corrected.apply(outside=True))
                native.world -= 1
                native.apply(outside=True)
                native.world += 1
                corrected.finish()
                native.finish()
                self.assertSame(corrected, native)

    def test_haste_runs_every_family_in_world_time(self):
        for start in ("with the effect", "before it"):
            with self.subTest(haste=start):
                corrected = self.creature(families=ALL).ticks(5)
                native = self.native(families=ALL).ticks(5)
                if start == "before it":
                    corrected.set_speed("haste")
                    native.touch()
                    corrected.ticks(3)
                    native.ticks(3)
                corrected.apply()
                native.apply()
                if start == "with the effect":
                    corrected.set_speed("haste")
                corrected.finish()
                native.finish()
                self.assertSame(corrected, native)

    def test_entering_and_leaving_haste(self):
        for during in (20, 50, 51):
            with self.subTest(hasted=during):
                corrected = self.creature(families=ALL).ticks(5)
                native = self.native(families=ALL).ticks(5)
                for creature in (corrected, native):
                    creature.apply()
                    creature.ticks(40)
                corrected.set_speed("haste")
                native.touch()
                corrected.ticks(during)
                native.ticks(during)
                corrected.set_speed("normal")
                native.touch()
                corrected.finish()
                native.finish()
                self.assertSame(corrected, native)

    def test_native_haste_changes_the_unit_counts(self):
        native = self.native(families=ALL).ticks(5)
        reference = self.native(families=ALL).ticks(5)
        native.set_speed("haste")
        reference.touch()
        for creature in (native, reference):
            creature.apply()
            creature.finish()
        self.assertGreater(sum(len(native.units[f]) for f in ALL), sum(len(reference.units[f]) for f in ALL))

    def slowed(self, families, offset, parity, *, stop=None, witness=None):
        corrected = self.creature(families=families, witness=witness).ticks(5 + offset)
        native = self.native(families=families).ticks(5 + offset)
        corrected.set_speed("slow", parity)
        native.touch()
        corrected.ticks(4)
        native.ticks(4)
        corrected.apply()
        native.apply()
        if stop:
            corrected.ticks(stop[0])
            native.ticks(stop[0])
            corrected.stop(stop[1])
            corrected.ticks(stop[1])
        corrected.finish()
        native.finish()
        return corrected, native

    def test_slow_runs_each_family_within_one_tick_of_world_time(self):
        for family in ALL:
            for offset in range(15):
                for parity in (0, 1):
                    with self.subTest(family=family, offset=offset, parity=parity):
                        corrected, native = self.slowed((family,), offset, parity)
                        self.assertSame(corrected, native, late=1)

    def test_slow_with_every_family_keeps_the_counts_within_one_pulse(self):
        """A unit one family submits on a skipped tick reseeds the others before their pulse on
        the next tick natively; a slowed creature updates them in one call, so a phase can move
        by one pulse. The counts stay, except that an effect's last pulse on the last tick the
        creature skipped is lost when another unit's rebuild expires the effect first."""
        for offset in range(15):
            for parity in (0, 1):
                with self.subTest(offset=offset, parity=parity):
                    corrected, native = self.slowed(ALL, offset, parity)
                    for family in ALL:
                        got, want = corrected.units[family], native.units[family]
                        if len(got) == len(want) - 1 and want[-1] >= native.expires[family] - 2:
                            native.units[family] = want[:-1]
                    self.assertSame(corrected, native, early=15, late=15)

    def test_native_slow_loses_units(self):
        native = self.native(families=ALL).ticks(5)
        reference = self.native(families=ALL).ticks(5)
        native.set_speed("slow")
        reference.touch()
        for creature in (native, reference):
            creature.apply()
            creature.finish()
        self.assertLess(sum(len(native.units[f]) for f in ALL), sum(len(reference.units[f]) for f in ALL))

    def test_time_stop_keeps_active_time_for_every_family(self):
        for speed in ("normal", "haste"):
            for before in (37, 44, 50):
                with self.subTest(speed=speed, before=before):
                    corrected = self.creature(families=ALL).ticks(5)
                    native = self.native(families=ALL).ticks(5)
                    if speed == "haste":
                        corrected.set_speed(speed)
                        native.touch()
                        corrected.ticks(2)
                        native.ticks(2)
                    corrected.apply()
                    native.apply()
                    corrected.ticks(before)
                    native.ticks(before)
                    corrected.stop(89)
                    corrected.ticks(89)
                    corrected.finish()
                    native.finish()
                    self.assertSame(corrected, native)

    def test_time_stop_on_a_slowed_creature(self):
        """Another frozen creature at normal speed shows a slowed one whether the stop began or
        ended on a tick it skipped; alone, it can be wrong by a tick at each end."""
        for family in ALL:
            for parity in (0, 1):
                for before in (37, 38):
                    for witness, early in (("before", 0), ("after", 0), (None, 2)):
                        with self.subTest(family=family, parity=parity, before=before, witness=witness):
                            corrected, native = self.slowed((family,), 0, parity, stop=(before, 89),
                                                            witness=witness)
                            self.assertSame(corrected, native, early=early, late=1)

    def test_native_time_stop_loses_the_frozen_time(self):
        native = self.native(families=ALL).ticks(5)
        reference = self.native(families=ALL).ticks(5)
        for creature in (native, reference):
            creature.apply()
            creature.ticks(37)
        native.stop(89)
        native.ticks(89)
        for creature in (native, reference):
            creature.finish()
        self.assertLess(sum(len(native.units[f]) for f in ALL), sum(len(reference.units[f]) for f in ALL))

    def test_consecutive_stops(self):
        corrected = self.creature(families=ALL).ticks(5)
        native = self.native(families=ALL).ticks(5)
        for creature in (corrected, native):
            creature.apply()
            creature.ticks(20)
        corrected.stop(30)
        corrected.ticks(30 + 16)
        corrected.stop(41)
        corrected.ticks(41)
        native.ticks(16)
        corrected.finish()
        native.finish()
        self.assertSame(corrected, native)
        self.assertEqual(corrected.cor.ActorState(ACTOR)["frozen"], 71)
        self.assertGreater(dict(corrected.cor.stats.items())["carried"], 0)

    def test_pauses_do_not_move_the_corrected_grid(self):
        for speed in ("normal", "haste"):
            with self.subTest(speed=speed):
                corrected = self.creature(families=ALL).ticks(5)
                native = self.native(families=ALL).ticks(5)
                corrected.apply()
                native.apply()
                if speed == "haste":
                    corrected.set_speed("haste")
                for _ in range(9):
                    corrected.ticks(7)
                    corrected.pause()
                    native.ticks(7)
                corrected.finish()
                native.finish()
                self.assertSame(corrected, native)

    def test_application_during_a_stop_runs_its_whole_duration_after_it(self):
        corrected = self.creature(families=ALL).ticks(5)
        native = self.native(families=ALL).ticks(5)
        corrected.stop(60)
        corrected.ticks(20)
        corrected.apply()
        corrected.ticks(40)
        corrected.finish()
        native.apply()
        native.finish()
        self.assertSame(corrected, native)

    def test_an_application_in_a_pause_during_a_stop_runs_its_whole_duration_after_it(self):
        """The pause steps back to a tick the stop already froze and counted; the effect is stamped
        one tick earlier, natively too, and the stop's end rebuilds its workers like every other."""
        for speed in ("normal", "haste"):
            with self.subTest(speed=speed):
                corrected = self.creature(families=ALL).ticks(5)
                native = self.native(families=ALL).ticks(5)
                if speed == "haste":
                    corrected.set_speed("haste")
                    native.touch()
                corrected.stop(60)
                corrected.ticks(20)
                corrected.pause(during=lambda: corrected.apply(outside=True))
                corrected.finish()
                native.world -= 1
                native.apply(outside=True)
                native.world += 1
                native.finish()
                self.assertSame(corrected, native)

    def test_removal_during_a_stop_stays_removal(self):
        corrected = self.creature(families=ALL).ticks(5)
        corrected.apply()
        corrected.ticks(30)
        corrected.stop(50)
        corrected.ticks(10)
        before = {family: len(corrected.units[family]) for family in ALL}
        corrected.remove()
        corrected.ticks(60)
        self.assertEqual({family: len(corrected.units[family]) for family in ALL}, before)
        self.assertEqual(corrected.workers, [])

    def test_rest_passes_natively(self):
        corrected = self.creature(families=ALL, duration=2400).ticks(5)
        native = self.native(families=ALL, duration=2400).ticks(5)
        for creature in (corrected, native):
            creature.apply()
            creature.ticks(40)
            creature.rest(900)
            creature.finish(limit=3000)
        self.assertEqual(corrected.record(), native.record())
        self.assertEqual(dict(corrected.cor.stats.items())["compressed"], 1)

    def test_an_area_left_alone_restarts_without_a_burst(self):
        corrected = self.creature(families=ALL, duration=900).ticks(5)
        native = self.native(families=ALL, duration=900).ticks(5)
        for creature in (corrected, native):
            creature.apply()
            creature.ticks(40)
            creature.leave(300)
            creature.finish(limit=1500)
        self.assertEqual(corrected.record(), native.record())
        self.assertEqual(dict(corrected.cor.stats.items())["restarts"], 1)

    def test_a_new_effect_on_a_slowed_creature_starts_on_its_own_ticks(self):
        for family in ALL:
            for offset in range(15):
                with self.subTest(family=family, offset=offset):
                    corrected = self.creature(families=(family,)).ticks(5 + offset)
                    native = self.native(families=(family,)).ticks(5 + offset)
                    corrected.set_speed("slow", parity=offset % 2)
                    native.touch()
                    corrected.ticks(2)
                    native.ticks(2)
                    corrected.apply()
                    native.apply()
                    corrected.finish()
                    native.finish()
                    self.assertSame(corrected, native, late=1)

    def test_caster_and_immune_creatures_run_in_world_time(self):
        corrected = self.creature(families=ALL).ticks(5)
        native = self.native(families=ALL).ticks(5)
        for creature in (corrected, native):
            creature.immune = True
            creature.apply()
            creature.ticks(30)
            creature.stop(60)
            creature.finish()
        self.assertEqual(corrected.record(), native.record())
        self.assertEqual(corrected.cor.ActorState(ACTOR)["frozen"], 0)

    def test_a_maintenance_group_moves_together(self):
        """Holy-Power-like: op272 upkeep, a timed child and a delayed op321 cleanup."""
        corrected = self.creature(families=("repeat",)).ticks(5)
        upkeep, = corrected.apply(families=("repeat",), duration=300)
        child = corrected.image.effect(EFFECTS + 0x10000, opcode=44, deadline=corrected.world + 300 + 31)
        cleanup = corrected.image.effect(EFFECTS + 0x10200, opcode=321, timing=6, deadline=corrected.world + 300)
        corrected.image.link([upkeep["address"], child, cleanup])
        offsets = (corrected.image.deadline(child) - corrected.image.deadline(upkeep["address"]),
                   corrected.image.deadline(cleanup) - corrected.image.deadline(upkeep["address"]))
        corrected.link = lambda: None  # the group's list is linked by hand
        corrected.ticks(20)
        corrected.stop(70)
        corrected.ticks(70)
        corrected.ticks(10)
        self.assertEqual((corrected.image.deadline(child) - corrected.image.deadline(upkeep["address"]),
                          corrected.image.deadline(cleanup) - corrected.image.deadline(upkeep["address"])), offsets)
        self.assertEqual(corrected.image.deadline(cleanup), 33005 + 300 + 70)

    def test_two_creatures_keep_separate_clocks(self):
        image = Image()
        lua, cor = load_cor(image.mem)
        image.link([image.effect(EFFECTS, deadline=34000)])
        image.link([image.effect(EFFECTS + 0x200, deadline=34000)], actor=OTHER)
        image.stop(True)
        for world in range(33000, 33010):
            image.world(world)
            cor.Frozen(ACTOR)
            cor.Entry(ACTOR, 1)
            cor.Entry(OTHER, 1)  # the caster: never frozen
        self.assertEqual((image.deadline(EFFECTS), image.deadline(EFFECTS + 0x200)), (34010, 34000))
        self.assertEqual((cor.ActorState(ACTOR)["frozen"], cor.ActorState(OTHER)["frozen"]), (10, 0))


class DecoderTests(unittest.TestCase):
    """decode_cor.py on what the recorder logs for model creatures: the replayed units are the
    model's own, at its world and active times, and the replay agrees with every worker."""

    def recorded(self, creature):
        creature.cor.Watch(creature.lua.table(ACTOR_ID))
        creature.cor.Record(True)
        return creature

    def text(self, creature):
        recorder = creature.cor.recorder
        header = {"schema": 1, "name": "model", "observe": bool(creature.cor.observe), "events": recorder.n,
                  "dropped": recorder.dropped, "watch": [ACTOR_ID], "stats": {}}
        return json.dumps(header) + "\n" + "".join(recorder.lines[index] + "\n"
                                                   for index in range(1, recorder.n + 1))

    def decoded(self, creature):
        result = decode_cor.decode_record(*decode_cor.read_record(self.text(creature)))
        self.assertEqual((result["issues"], result["mismatch_count"]), ([], 0))
        units = {}
        for effect in result["creatures"][0]["effects"]:
            worlds, active = units.setdefault(effect["family"], ([], []))
            for world, T, count in effect["units"]:
                worlds.extend([world] * count)
                active.extend([T] * count)
        return result, units

    def scenarios(self):
        def haste(creature):
            creature.apply()
            creature.set_speed("haste")
            creature.ticks(40)
            creature.pause()
            creature.ticks(30)
            creature.set_speed("normal")

        def stop(creature):
            creature.apply()
            creature.ticks(25)
            creature.stop(70)
            creature.ticks(80)

        def plain(creature):
            creature.apply()

        return {"normal": plain, "haste and a pause": haste, "time stop": stop}

    def test_corrected_records_replay_to_the_models_units(self):
        for name, scenario in self.scenarios().items():
            with self.subTest(scenario=name):
                creature = self.recorded(Creature(self, families=ALL).ticks(5))
                scenario(creature)
                creature.finish()
                result, units = self.decoded(creature)
                for family in ALL:
                    self.assertEqual(units[family], (creature.unit_worlds[family], creature.units[family]), family)
                self.assertGreater(result["creatures"][0]["dispatch"].get("native", 0), 0)

    def test_observed_records_replay_to_the_native_units(self):
        for name, scenario in self.scenarios().items():
            with self.subTest(scenario=name):
                creature = Creature(self, families=ALL).ticks(5)
                creature.cor.observe = True
                self.recorded(creature)
                scenario(creature)
                creature.finish()
                result, units = self.decoded(creature)
                for family in ALL:
                    self.assertEqual(units[family][0], creature.unit_worlds[family], family)
                self.assertEqual(result["creatures"][0]["dispatch"], {})
                if name == "time stop":
                    self.assertGreater(result["creatures"][0]["frozen_passes"], 60)
                    self.assertEqual(result["creatures"][0]["frozen_ticks"], 0)

    def test_a_record_that_disagrees_with_the_replay_is_reported(self):
        creature = self.recorded(Creature(self, families=("regeneration",)).ticks(5))
        creature.apply()
        creature.finish()
        lines = self.text(creature).splitlines()
        dispatches = [index for index, line in enumerate(lines) if line.startswith('["D"')]
        event = json.loads(lines[dispatches[5]])
        event[14] -= 3  # the remaining duration
        lines[dispatches[5]] = json.dumps(event)
        result = decode_cor.decode_record(*decode_cor.read_record("\n".join(lines)))
        self.assertEqual(result["mismatch_count"], 2)  # against the update before and after it
        self.assertIn("2 replay disagreements", result["issues"])

    def test_malformed_records_are_refused(self):
        header = json.dumps({"schema": 1, "events": 1})
        for text, message in ((header + '\n["E", 1, 2]', "E event with 3 fields"),
                              (header + '\n["X", 1]', "unknown event"),
                              (header, "header names 1 events"),
                              ('{"schema": 2}', "not a schema 1"), ("", "empty record")):
            with self.subTest(message=message):
                with self.assertRaises(decode_cor.RecordFormatError) as caught:
                    decode_cor.read_record(text)
                self.assertIn(message, str(caught.exception))


def stub_call(sites):
    """The test Lua call: a 32-byte shadow space and a call to a per-function stub address."""
    names = sorted({site["fn"] for site in sites})
    addresses = {name: STUBS + 0x10 * index for index, name in enumerate(names)}

    def call(fn, _nargs, _prefix):
        return f"sub rsp, 32\nmov rax, {addresses[fn]:#x}\ncall rax\nadd rsp, 32\n"
    return call, addresses


CODE, BLOCK, STUBS, STACK, SENTINEL = 0x100000, 0x200000, 0x210000, 0x600000, 0x700000
INITIAL_RSP = STACK + 0x3000


@functools.lru_cache(maxsize=None)
def compiled_gates():
    lua, cor = load_cor()
    sites = lua_sites(cor)
    call, addresses = stub_call(sites)
    assembler = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    opts = lua.table_from({"block": BLOCK, "base": BASE, "macros": False, "luaCall": call})
    code = {}
    for index in range(1, len(cor.sites) + 1):
        site = sites[index - 1]
        parts = cor.BuildGate(cor.sites[index], opts)
        text = "".join(parts[i] for i in range(1, len(parts) + 1))
        address = CODE + 0x1000 * (site["id"] - 1)
        encoded, _ = assembler.asm(text, address)
        assert len(encoded) < 0x1000, "gate outgrew its synthetic code slot"
        code[site["id"]] = (address, bytes(encoded), text)
    return sites, code, addresses


class GateTests(unittest.TestCase):
    """The assembly gates in Unicorn: a stub stands in for the Lua call, records its arguments,
    checks the stack alignment, clobbers every volatile register and returns a scripted value."""

    @classmethod
    def setUpClass(cls):
        cls.sites, cls.code, cls.addresses = compiled_gates()
        cls.by_id = {site["id"]: site for site in cls.sites}

    def machine(self):
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        for address, size in ((CODE, 0x10000), (BLOCK, 0x1000), (STUBS, 0x1000), (STACK, 0x4000),
                              (WORKERS, 0x1000)):
            uc.mem_map(address, size)
        for address, encoded, _ in self.code.values():
            uc.mem_write(address, encoded)
        uc.mem_write(STUBS, b"\xC3" * 0x1000)  # each stub returns
        return uc

    def run_gate(self, site_id, *, enabled=1, result=0, vtable=None, error=False):
        uc = self.machine()
        site = self.by_id[site_id]
        uc.mem_write(BLOCK, struct.pack("<II", enabled, 5))
        values = {name: 0x0101010101010101 * (index + 1) for index, name in enumerate(REG_NAMES[:-1])}
        worker = WORKERS + 0x40
        uc.mem_write(worker, struct.pack("<Q", vtable if vtable is not None else BASE + 0x598B18))
        if site.get("filter") == "vtable":
            values[site["args"][1]] = worker
        for name, value in values.items():
            uc.reg_write(REGS[name], value)
        uc.reg_write(REGS["rsp"], INITIAL_RSP)
        for index, reg in enumerate(XMMS):
            uc.reg_write(reg, 0x11111111111111112222222222222222 * (index + 1))
        uc.reg_write(x86.UC_X86_REG_EFLAGS, 0x202)
        calls = []

        def stub(uc_, address, _size, _user):
            if not STUBS <= address < STUBS + 0x1000:
                return
            rsp = uc_.reg_read(REGS["rsp"])
            calls.append({"fn": next(name for name, at in self.addresses.items() if at == address),
                          "args": [uc_.reg_read(REGS[name]) for name in ("r12", "r13", "r14", "r15")],
                          "aligned": (rsp + 8) % 16 == 0, "shadow": rsp + 8})
            for name in ("rcx", "rdx", "r8", "r9", "r10", "r11"):
                uc_.reg_write(REGS[name], 0xDEADBEEF)
            for reg in XMMS:
                uc_.reg_write(reg, 0xFEEDFACE)
            uc_.reg_write(x86.UC_X86_REG_EFLAGS, 0x8D7)
            uc_.reg_write(REGS["rax"], u32(-2) | 0xFFFFFFFF00000000 if error else result & 0xFFFFFFFFFFFFFFFF)

        uc.hook_add(unicorn.UC_HOOK_CODE, stub)
        writes = []
        uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                    lambda _uc, _access, address, size, _value, _user: writes.append((address, size)))
        start, encoded, _ = self.code[site_id]
        uc.emu_start(start, start + len(encoded), count=100000)
        self.assertEqual(uc.reg_read(x86.UC_X86_REG_RIP), start + len(encoded))
        final = {name: uc.reg_read(REGS[name]) for name in REG_NAMES}
        xmm = [uc.reg_read(reg) for reg in XMMS]
        flags = uc.reg_read(x86.UC_X86_REG_EFLAGS)
        block = struct.unpack("<II", uc.mem_read(BLOCK, 8))
        for address, size in writes:
            self.assertTrue(BLOCK <= address < BLOCK + 8 or INITIAL_RSP - 0x200 <= address < INITIAL_RSP,
                            f"write outside the block and the scratch stack: {address:#x}+{size}")
        return values, final, xmm, flags, block, calls

    def test_every_gate_passes_its_registers_in_order_and_restores_everything(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                values, final, xmm, flags, block, calls = self.run_gate(site["id"])
                self.assertEqual(len(calls), 1)
                call = calls[0]
                self.assertEqual(call["fn"], site["fn"])
                self.assertTrue(call["aligned"], "rsp must be 16-byte aligned at the call")
                expected = [values[reg] for reg in site["args"]]
                if site.get("family"):
                    expected.append(site["family"])
                self.assertEqual(call["args"][:len(expected)], expected)
                restored = dict(values)
                if site.get("result"):
                    restored[site["result"]] = 0  # the stub's result
                for name in REG_NAMES[:-1]:
                    self.assertEqual(final[name], restored[name], name)
                self.assertEqual(final["rsp"], INITIAL_RSP)
                self.assertEqual(xmm, [0x11111111111111112222222222222222 * (i + 1) for i in range(6)])
                self.assertEqual(flags & 0xFD5, 0x202 & 0xFD5)
                self.assertEqual(block, (1, 5))

    def test_the_dispatch_gate_writes_a_nonnegative_result_into_r8(self):
        for result, expected in ((0, 0), (2, 2), (1, 1)):
            values, final, _, _, _, _ = self.run_gate(3, result=result)
            self.assertEqual(final["r8"], expected)
        values, final, _, _, _, _ = self.run_gate(3, result=-1)
        self.assertEqual(final["r8"], values["r8"])

    def test_a_disabled_gate_never_calls_lua(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                values, final, _, _, block, calls = self.run_gate(site["id"], enabled=0)
                self.assertEqual(calls, [])
                self.assertEqual({name: final[name] for name in values}, values)
                self.assertEqual(block, (0, 5))

    def test_only_the_four_periodic_worker_classes_reach_lua(self):
        for name, family in FAMILIES.items():
            _, _, _, _, _, calls = self.run_gate(3, vtable=BASE + family["vtable"])
            self.assertEqual(len(calls), 1, name)
        for vtable in (BASE + 0x598B30, BASE + 0x598A70, 0):  # CPersistantEffectMove, a death visual
            values, final, _, _, _, calls = self.run_gate(3, vtable=vtable)
            self.assertEqual(calls, [])
            self.assertEqual(final["r8"], values["r8"])

    def test_a_lua_error_turns_every_gate_off_and_leaves_registers_native(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                values, final, xmm, _, block, calls = self.run_gate(site["id"], error=True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(block, (0, 6))
                for name in REG_NAMES[:-1]:
                    self.assertEqual(final[name], values[name], name)

    def test_the_in_game_build_balances_eeex_stack_bookkeeping(self):
        lua, cor = load_cor()
        marker = lua.eval("function(fn, nargs, prefix) return {'#LUA_CALL(' .. fn .. ',' .. nargs .. ')\\n'} end")
        for index in range(1, len(cor.sites) + 1):
            site = dict(cor.sites[index].items())
            with self.subTest(site=site["name"]):
                parts = cor.BuildGate(cor.sites[index], lua.table_from(
                    {"block": BLOCK, "base": BASE, "macros": True, "luaCall": marker}))
                text = "".join(parts[i] if isinstance(parts[i], str) else
                               "".join(parts[i][j] for j in range(1, len(parts[i]) + 1))
                               for i in range(1, len(parts) + 1))
                depth, pushed = 0, 0
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("#STACK_MOD("):
                        depth += int(line[len("#STACK_MOD("):-1])
                    elif line in ("pushfq",) or line.startswith("push "):
                        pushed += 8
                    elif line == "popfq" or line.startswith("pop "):
                        pushed -= 8
                    elif line.startswith("#LUA_CALL"):
                        self.assertEqual(depth, 224, "EEex must know the 128 pushed and 96 saved bytes")
                        self.assertEqual(depth % 16, 0)
                self.assertEqual((depth, pushed), (0, 0))


class LabStepTests(unittest.TestCase):
    """Install/Enable/Disable/Status against stub EEex bindings over real FFI memory."""

    def runtime(self, *, paused=1):
        lua, _ = load_cor()
        lua.execute("""
            local ffi = require("ffi")
            MEM = ffi.new("uint8_t[?]", 0x4000)
            BASE = tonumber(ffi.cast("uintptr_t", MEM))
            EEex_Read32 = function(a) return ffi.cast("int32_t*", a)[0] end
            EEex_ReadU32 = function(a) return ffi.cast("uint32_t*", a)[0] end
            EEex_Read16 = function(a) return ffi.cast("int16_t*", a)[0] end
            EEex_Write32 = function(a, v) ffi.cast("int32_t*", a)[0] = v end
            EEex_WriteU32 = function(a, v) ffi.cast("uint32_t*", a)[0] = v end
            EEex_WriteU16 = function(a, v) ffi.cast("uint16_t*", a)[0] = v end
            EEex_ReadPtr = function(a) return tonumber(ffi.cast("uint64_t*", a)[0]) end
            EEex_WritePtr = function(a, v) ffi.cast("uint64_t*", a)[0] = v end
            EEex_UDToPtr = function(v) return v._ptr end
            ITERATED = {timed = {}, equipped = {}}
            EEex_Utility_IterateCPtrList = function(list, f)
                for _, effect in ipairs(ITERATED[list.kind]) do f({_ptr = effect}) end
            end
            SPRITE = {_ptr = BASE + 0x400, m_id = 0x1234,
                m_timedEffectList = {_ptr = BASE + 0x700, kind = "timed"},
                m_equipedEffectList = {_ptr = BASE + 0x760, kind = "equipped"}}
            EEex_Sprite_GetInPortrait = function(slot) if slot == 0 then return SPRITE end end
            function LINK(kind, list, effects)
                ITERATED[kind] = effects
                local previous = 0
                for i = #effects, 1, -1 do
                    local node = BASE + 0x800 + 0x20 * i + (kind == "equipped" and 0x400 or 0)
                    EEex_WritePtr(node, previous)
                    EEex_WritePtr(node + 0x10, effects[i])
                    previous = node
                end
                EEex_WritePtr(list + 8, previous)
            end
            CBRTC.UseMemory({r32=EEex_Read32, u32=EEex_ReadU32, s16=EEex_Read16, w32=EEex_Write32,
                wu32=EEex_WriteU32, w16=EEex_WriteU16, ptr=EEex_ReadPtr})
            CBRTC.installed = true
            CBRTC.block = BASE
        """)
        lua.execute(f"EngineGlobals = {{g_pBaldurChitin = {{m_pEngineWorld = "
                    f"{{m_bPaused = {paused}, m_bHardPaused = 0}}}}}}")
        return lua

    def test_enable_finds_both_lists_and_clears_the_state(self):
        lua = self.runtime()
        lua.execute("""
            LINK("timed", BASE + 0x700, {BASE + 0x1000, BASE + 0x1200})
            LINK("equipped", BASE + 0x760, {BASE + 0x1400})
            CBRTC.actors[12345] = {id = 1}
        """)
        status = lua.eval("CBRTC.Enable(0)")
        self.assertTrue(status["enabled"])
        self.assertEqual((status["timed_offset"], status["equipped_offset"], status["actors"]), (0x300, 0x360, 0))
        self.assertEqual(lua.eval("EEex_Read32(BASE)"), 1)

    def test_enable_fails_closed(self):
        cases = {"mismatch": ('LINK("timed", BASE + 0x700, {BASE + 0x1000}); ITERATED.timed = {}',
                              "Effect list layout mismatch"),
                 "empty": ("", "No effect on that creature proves the list layout"),
                 "portrait": ('LINK("timed", BASE + 0x700, {BASE + 0x1000}); SPRITE = nil',
                              "No creature in that portrait")}
        for case, (setup, message) in cases.items():
            with self.subTest(case=case):
                lua = self.runtime()
                lua.execute(setup + "\nEEex_Write32(BASE, 1)")
                ok, why = lua.eval("function() return pcall(CBRTC.Enable, 0) end")()
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual(lua.eval("EEex_Read32(BASE)"), 0)

    def test_enable_requires_install_and_a_pause(self):
        lua = self.runtime(paused=0)
        lua.execute('LINK("timed", BASE + 0x700, {BASE + 0x1000}); EEex_Write32(BASE, 1)')
        ok, why = lua.eval("function() return pcall(CBRTC.Enable, 0) end")()
        self.assertFalse(ok)
        self.assertIn("Pause the lab", why)
        self.assertEqual(lua.eval("EEex_Read32(BASE)"), 1)  # refused before touching anything
        lua = self.runtime()
        lua.execute("CBRTC.installed = false")
        ok, why = lua.eval("function() return pcall(CBRTC.Enable, 0) end")()
        self.assertFalse(ok)
        self.assertIn("Install the correction first", why)

    def test_observe_runs_the_gates_without_the_correction_and_modes_switch_only_unrecorded(self):
        lua = self.runtime(paused=0)
        ok, why = lua.eval("function() return pcall(CBRTC.Observe) end")()
        self.assertFalse(ok)
        self.assertIn("Pause the lab", why)
        lua = self.runtime()
        lua.execute("CBRTC.actors[12345] = {id = 1}")
        status = lua.eval("CBRTC.Observe()")
        self.assertEqual((status["observe"], status["enabled"], status["actors"]), (True, True, 0))
        lua.execute("CBRTC.Watch({1}); CBRTC.Record(true)")
        for call in ("Observe", "Enable"):
            with self.subTest(call=call):
                ok, why = lua.eval(f"function() return pcall(CBRTC.{call}, 0) end")()
                self.assertFalse(ok)
                self.assertIn("Stop recording before switching modes", why)
                self.assertEqual(lua.eval("EEex_Read32(BASE)"), 1)
        lua.execute('CBRTC.Record(false); LINK("timed", BASE + 0x700, {BASE + 0x1000})')
        status = lua.eval("CBRTC.Enable(0)")
        self.assertEqual((status["observe"], status["enabled"]), (False, True))

    def test_export_writes_a_header_and_one_event_per_line_once(self):
        lua = self.runtime()
        lua.execute("""
            CBRTC.Watch({7, 3})
            CBRTC.Record(true)
            CBRTC.recorder.lines = {'["E",3,1]', '["F",7,2,1]'}
            CBRTC.recorder.n = 2
            CBRTC.stats.delivered = 5
        """)
        export = lua.eval("function(name) return pcall(CBRTC.ExportRecord, name) end")
        with tempfile.TemporaryDirectory(prefix="cbr-record-test-") as directory:
            root = Path(directory)
            (root / "cbr-timestop-output").mkdir()
            previous = os.getcwd()
            os.chdir(root)
            try:
                ok, why = export("case_1")
                self.assertFalse(ok)
                self.assertIn("Stop recording before the export", why)
                lua.execute("CBRTC.Record(false)")
                ok, why = lua.eval("function() return pcall(CBRTC.Record, true) end")()
                self.assertFalse(ok)
                self.assertIn("Export the previous record first", why)
                for name in ("../case", "a b", ""):
                    ok, why = export(name)
                    self.assertFalse(ok)
                    self.assertIn("simple unique record name", why)
                ok, result = export("case_1")
                self.assertTrue(ok, result)
                self.assertEqual((result["events"], result["dropped"]), (2, 0))
                lines = (root / "cbr-timestop-output" / "case_1.jsonl").read_text(encoding="utf-8").splitlines()
                header = json.loads(lines[0])
                self.assertEqual((header["schema"], header["name"], header["observe"], header["events"],
                                  header["watch"], header["stats"]["delivered"]), (1, "case_1", False, 2, [3, 7], 5))
                self.assertEqual([json.loads(line) for line in lines[1:]], [["E", 3, 1], ["F", 7, 2, 1]])
                ok, why = export("case_1")
                self.assertFalse(ok)
                self.assertIn("Record already exists", why)
                status = lua.eval("CBRTC.Record(true)")  # exported: a new record may start
                self.assertEqual((status["recorder"]["on"], status["recorder"]["events"]), (True, 0))
                lua.execute("CBRTC.Record(false)")
                status = lua.eval("CBRTC.Record(true, true)")  # an unexported one only when discarded
                self.assertTrue(status["recorder"]["on"])
            finally:
                os.chdir(previous)
        lua = self.runtime(paused=0)
        ok, why = lua.eval("function() return pcall(CBRTC.ExportRecord, 'x') end")()
        self.assertFalse(ok)
        self.assertIn("Pause the lab", why)

    def test_disable_works_unpaused_and_status_reports_errors_and_stats(self):
        lua = self.runtime(paused=0)
        lua.execute("EEex_Write32(BASE, 1); EEex_Write32(BASE + 4, 3); CBRTC.stats.delivered = 7")
        status = lua.eval("CBRTC.Disable()")
        self.assertFalse(status["enabled"])
        self.assertEqual((status["errors"], status["stats"]["delivered"]), (3, 7))

    def test_install_refuses_outside_the_fresh_main_menu_or_beside_the_prototype(self):
        for state, message in ((("0", "start", "false"), "Missing lab guard: CBRTSLab.id"),
                               (("1", "start", "false"), "Install only at the fresh main menu"),
                               (("0", "world", "false"), "Install only at the fresh main menu"),
                               (("0", "start", "true"), "The step-5 prototype is installed")):
            with self.subTest(state=state):
                lua, _ = load_cor()
                attempt = lua.eval("""function(loaded, active, prototype)
                    local function object(pointer, fields) fields = fields or {}; fields._ptr = pointer; return fields end
                    local start, world = object(0x1000), object(0x2000)
                    local game = object(0x3000, {m_bGameLoaded = tonumber(loaded), m_bInLoadGame = 0,
                        m_bInLoadArea = 0})
                    EngineGlobals = {g_pBaldurChitin = object(0x4000, {m_pObjectGame = game,
                        m_pEngineStart = start, m_pEngineWorld = world,
                        pActiveEngine = active == "world" and world or start})}
                    EEex_UDToPtr = function(value) return value._ptr end
                    CBRTF = {installed = prototype == "true"}
                    local allocated = false
                    EEex_Malloc = function() allocated = true; return 0 end
                    io.open = function() return nil end
                    local ok, why = pcall(CBRTC.Install)
                    return ok, tostring(why), CBRTC.installed, allocated
                end""")
                ok, why, installed, allocated = attempt(*state)
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual((installed, allocated), (False, False))


class NativeWorkerTests(unittest.TestCase):
    """The pinned executable's four periodic AIUpdates on synthetic memory, against worker_step."""

    GLOBAL_RVA = 0x667548
    # Calls skipped per family: allocations return a scratch object, constructors are skipped and
    # each submission (from where its paths join, before it reads the sprite's vtable or the
    # executable's data) is counted. The repeated EFF's whole application loop is skipped and its
    # count read from eax.
    ALLOCATE = {"regeneration": (0x1A5E42, 0x1A5E8B), "poison": (0x1A5BA5, 0x1A5BEA),
                "disease": (0x1A4F6B, 0x1A506B, 0x1A50B0), "repeat": ()}
    CONSTRUCT = {"regeneration": (0x1A5E52, 0x1A5E9B), "poison": (0x1A5BB5, 0x1A5BFA),
                 "disease": (0x1A4F7B, 0x1A507B, 0x1A50C0), "repeat": ()}
    SUBMIT = {"regeneration": {0x1A5EB7: 0x1A5EDC}, "poison": {0x1A5C15: 0x1A5C53},
              "disease": {0x1A50DB: 0x1A5119, 0x1A4F8F: 0x1A5119}, "repeat": {}}
    REPEAT_LOOP, REPEAT_AFTER = 0x1A496C, 0x1A4A7F
    UPDATES = (0x1A47B0, 0x1A5F20)  # the four AIUpdates lie in this range
    SCRATCH = 0x800000

    @classmethod
    def setUpClass(cls):
        data = EXE.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXE_SHA256:
            raise unittest.SkipTest("CBRTS_TEST_EXE is not the pinned 2.7.3.0 executable")
        pe = pefile.PE(data=data, fast_load=True)
        cls.base = pe.OPTIONAL_HEADER.ImageBase
        assert cls.base == BASE
        text = next(section for section in pe.sections if section.Name.rstrip(b"\0") == b".text")
        rva, code = text.VirtualAddress, text.get_data()
        cls.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        cls.uc.mem_map(cls.base + rva, (len(code) + 0xFFF) & ~0xFFF)
        cls.uc.mem_write(cls.base + rva, code)
        cls.data = [(cls.base + 0x664000, 0x4000), (CHITIN, 0x2000), (GAME, 0xA000), (ACTOR, 0x6000),
                    (WORKERS, 0x1000), (STACK, 0x4000), (SENTINEL, 0x1000), (cls.SCRATCH, 0x1000)]
        for address, size in cls.data:
            cls.uc.mem_map(address, size)
        cls.state = {}

        def code_hook(uc, address, _size, _user):
            state = cls.state
            family, rva_ = state.get("family"), address - cls.base
            if family is None:
                return
            if rva_ in cls.ALLOCATE[family]:
                uc.reg_write(x86.UC_X86_REG_RAX, cls.SCRATCH)
                uc.reg_write(x86.UC_X86_REG_RIP, address + 5)
            elif rva_ in cls.CONSTRUCT[family]:
                uc.reg_write(x86.UC_X86_REG_RIP, address + 5)
            elif rva_ in cls.SUBMIT[family]:
                state["units"] += 1
                uc.reg_write(x86.UC_X86_REG_RIP, cls.base + cls.SUBMIT[family][rva_])
            elif family == "repeat" and rva_ == cls.REPEAT_LOOP:
                state["units"] += s32(uc.reg_read(x86.UC_X86_REG_RAX))
                uc.reg_write(x86.UC_X86_REG_RIP, cls.base + cls.REPEAT_AFTER)

        cls.uc.hook_add(unicorn.UC_HOOK_CODE, code_hook, begin=cls.base + cls.UPDATES[0],
                        end=cls.base + cls.UPDATES[1])

    def emulate(self, family, *, counter, elapsed, phase=0, period=2, remaining=100, mode=3, amount22=0,
                amount24=1, time_stop=0, immunity=0, hp=50):
        uc = self.uc
        for address, size in self.data:
            uc.mem_write(address, bytes(size))
        put = lambda address, format_, *values: uc.mem_write(address, struct.pack("<" + format_, *values))
        put(self.base + self.GLOBAL_RVA, "Q", CHITIN)
        put(CHITIN + 0x1090, "Q", GAME)
        put(GAME + 0x9690, "II", time_stop, ACTOR_ID + 1)
        put(ACTOR + 0x48, "I", ACTOR_ID)
        put(ACTOR + 0x20A0, "I", immunity)
        put(ACTOR + 0x57C, "h", hp)
        put(ACTOR + 0x1124, "h", 83)
        worker = WORKERS
        put(worker, "QII", self.base + FAMILIES[family]["vtable"], 0, 0)
        put(worker + 0x18, "HHI", period & 0xFFFF, phase, u32(counter))
        put(worker + 0x20, "HHH", mode, amount22, amount24)
        put(worker + 0x28, "i", remaining)
        put(INITIAL_RSP, "Q", SENTINEL)
        for name in REG_NAMES:
            uc.reg_write(REGS[name], 0)
        uc.reg_write(REGS["rsp"], INITIAL_RSP)
        uc.reg_write(REGS["rcx"], worker)
        uc.reg_write(REGS["rdx"], ACTOR)
        uc.reg_write(REGS["r8"], u32(elapsed))
        self.state.clear()
        self.state.update(family=family, units=0)
        uc.emu_start(self.base + FAMILIES[family]["update"], SENTINEL, count=400000)
        self.assertEqual(uc.reg_read(x86.UC_X86_REG_RIP), SENTINEL)
        fields = dict(zip(("period", "phase", "counter"), struct.unpack("<HHI", uc.mem_read(worker + 0x18, 8))))
        fields.update(zip(("mode", "amount22", "amount24"), struct.unpack("<HHH", uc.mem_read(worker + 0x20, 6))))
        fields["remaining"], = struct.unpack("<i", uc.mem_read(worker + 0x28, 4))
        fields["done"], = struct.unpack("<I", uc.mem_read(worker + 8, 4))
        self.state["family"] = None
        return fields, self.state["units"]

    def test_the_python_worker_models_match_the_executable(self):
        for family in FAMILIES:
            modes = [(3, 0, 1), (2, 0, 1), (0, 1, 1), (0, 0, 1), (1, 0, 1)]
            if family == "repeat":
                modes.append((3, 0, 2))
            if family == "disease":
                modes += [(11, 6, 1), (12, 6, 1)]
            for counter in (13, 14, 28, 29, 1679):
                for elapsed in (0, 1, 2, 15, 31):
                    for phase, period in ((0, 1), (0, 2), (1, 2), (2, 3), (3, 2)):
                        for remaining in (-3, 1, 2, 16, 100):
                            for mode, amount22, amount24 in modes:
                                with self.subTest(family=family, counter=counter, elapsed=elapsed, phase=phase,
                                                  period=period, remaining=remaining, mode=mode, amount22=amount22):
                                    native, units = self.emulate(family, counter=counter, elapsed=elapsed,
                                                                 phase=phase, period=period, remaining=remaining,
                                                                 mode=mode, amount22=amount22, amount24=amount24)
                                    model = {"period": period, "phase": phase, "counter": counter, "mode": mode,
                                             "amount22": amount22, "amount24": amount24,
                                             "remaining": remaining, "done": 0}
                                    self.assertEqual(worker_step(model, elapsed, family), units)
                                    self.assertEqual(model, native)

    def test_the_pulse_caps_match_the_executable(self):
        """A long time compression: at most 1000 pulses per update, 100 for the repeated EFF."""
        for family in FAMILIES:
            for elapsed in (1600, 15100):
                for mode, period in ((2, 1), (3, 30000)):
                    with self.subTest(family=family, elapsed=elapsed, mode=mode):
                        native, units = self.emulate(family, counter=3, elapsed=elapsed, phase=0, period=period,
                                                     remaining=20000, mode=mode)
                        model = {"period": period, "phase": 0, "counter": 3, "mode": mode, "amount22": 0,
                                 "amount24": 1, "remaining": 20000, "done": 0}
                        self.assertEqual(worker_step(model, elapsed, family), units)
                        self.assertEqual(model, native)

    def test_a_frozen_worker_returns_untouched(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                fields, units = self.emulate(family, counter=14, elapsed=1, phase=1, time_stop=90)
                self.assertEqual((fields["phase"], fields["counter"], fields["remaining"], units), (1, 14, 100, 0))
                fields, _ = self.emulate(family, counter=14, elapsed=1, phase=0, time_stop=90, immunity=1)
                self.assertNotEqual(fields["counter"], 14)  # immune to Time Stop: not frozen

    def test_a_suppressed_dispatch_is_a_no_op(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                fields, units = self.emulate(family, counter=0, elapsed=0, phase=1, remaining=100)
                self.assertEqual((fields["phase"], fields["remaining"], fields["done"], units), (1, 100, 0, 0))


def normalize(register):
    names = {"bl": "rbx", "bh": "rbx", "bx": "rbx", "ebx": "rbx", "bpl": "rbp", "bp": "rbp", "ebp": "rbp",
             "sil": "rsi", "si": "rsi", "esi": "rsi", "dil": "rdi", "di": "rdi", "edi": "rdi"}
    if register in names:
        return names[register]
    if register.startswith("r") and register[-1] in "dwb" and register[1:-1].isdigit():
        return register[:-1]
    return register


class PinnedExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = EXE.read_bytes()
        if hashlib.sha256(cls.data).hexdigest() != EXE_SHA256:
            raise unittest.SkipTest("CBRTS_TEST_EXE is not the pinned 2.7.3.0 executable")
        cls.pe = pefile.PE(data=cls.data, fast_load=True)
        cls.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
        cls.base = cls.pe.OPTIONAL_HEADER.ImageBase
        cls.decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        cls.decoder.detail = True
        cls.sites = lua_sites(load_cor()[1])
        observer = LuaRuntime(unpack_returned_tuples=True)
        observer.execute((HERE / "CBRTObs.lua").read_text(encoding="utf-8"))
        cls.observer_sites = lua_sites(observer.globals().CBRTS)
        cls.windows = [(site["rva"], site["rva"] + len(bytes.fromhex(site["bytes"])), site["name"])
                       for site in cls.sites]

    def decode(self, start, end):
        return list(self.decoder.disasm(self.pe.get_data(start, end - start), self.base + start))

    def at(self, rva):
        instruction = self.decode(rva, rva + 16)[0]
        return f"{instruction.mnemonic} {instruction.op_str}"

    def written(self, start, end):
        out = {}
        for instruction in self.decode(start, end):
            _, written = instruction.regs_access()
            for register in written:
                out.setdefault(normalize(instruction.reg_name(register)), []).append(instruction.address - self.base)
        return out

    def direct_calls_to(self, target):
        text = next(section for section in self.pe.sections if section.Name.rstrip(b"\0") == b".text")
        code, rva = text.get_data(), text.VirtualAddress
        return [rva + index for index in range(len(code) - 5)
                if code[index] in (0xE8, 0xE9)
                and rva + index + 5 + int.from_bytes(code[index + 1:index + 5], "little", signed=True) == target]

    def test_sites_are_whole_windows_without_relative_operands(self):
        self.assertEqual(self.pe.FILE_HEADER.TimeDateStamp, 0x6A18D73D)
        for site in self.sites:
            with self.subTest(site=site["name"]):
                expected = bytes.fromhex(site["bytes"])
                self.assertGreaterEqual(len(expected), 5, "room for EEex's 5-byte jump")
                offset = self.pe.get_offset_from_rva(site["rva"])
                self.assertEqual(self.data[offset:offset + len(expected)], expected)
                instructions = self.decode(site["rva"], site["rva"] + len(expected))
                self.assertEqual(sum(item.size for item in instructions), len(expected))
                for instruction in instructions:
                    self.assertFalse(instruction.group(capstone.CS_GRP_JUMP))
                    self.assertFalse(instruction.group(capstone.CS_GRP_CALL))
                    self.assertFalse(instruction.group(capstone.CS_GRP_RET))
                    self.assertFalse(any(operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
                                         for operand in instruction.operands))

    def test_windows_start_on_boundaries_and_no_direct_branch_lands_inside(self):
        lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        text = next(section for section in self.pe.sections if section.Name.rstrip(b"\0") == b".text")
        code, text_rva = text.get_data(), text.VirtualAddress
        boundaries = {name: set() for _, _, name in self.windows}
        landing = []
        for entry in self.pe.DIRECTORY_ENTRY_EXCEPTION:
            begin, end = entry.struct.BeginAddress, entry.struct.EndAddress
            for low, high, name in self.windows:
                if low < begin < high:
                    landing.append((name, "function entry", begin))
            owners = [name for low, high, name in self.windows if begin <= low < end]
            for address, size, mnemonic, operands in lite.disasm_lite(
                    code[begin - text_rva:end - text_rva], self.base + begin):
                rva = address - self.base
                for name in owners:
                    boundaries[name].add(rva)
                if (mnemonic.startswith("j") or mnemonic == "call") and operands.startswith("0x"):
                    target = int(operands, 16) - self.base
                    for low, high, name in self.windows:
                        if low < target < high:
                            landing.append((name, mnemonic, rva))
        self.assertEqual(landing, [])
        for low, high, name in self.windows:
            with self.subTest(site=name):
                self.assertIn(low, boundaries[name])
                self.assertIn(high, boundaries[name])
                inside = sorted(address for address in boundaries[name] if low <= address < high)
                self.assertEqual(inside, [item.address - self.base for item in self.decode(low, high)])

    def test_no_table_or_pointer_refers_inside_a_window(self):
        interior = {address for low, high, _ in self.windows for address in range(low + 1, high)}
        targets = {"rva": (4, "I", interior), "va": (8, "Q", {self.base + address for address in interior})}
        hits = []
        for section in self.pe.sections:
            raw = section.get_data()
            for kind, (width, code, wanted) in targets.items():
                values = memoryview(raw[:len(raw) // width * width]).cast(code)
                if wanted & set(values):
                    hits += [(section.Name.rstrip(b"\0"), section.VirtualAddress + index * width, kind)
                             for index, value in enumerate(values) if value in wanted]
        self.assertEqual(hits, [])

    def runtime_functions(self):
        """The .pdata entries (begin, end, unwind info RVA), sorted."""
        if not hasattr(self, "_functions"):
            directory = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
            raw = self.pe.get_data(directory.VirtualAddress, directory.Size)
            type(self)._functions = sorted(struct.iter_unpack("<III", raw[:len(raw) // 12 * 12]))
        return self._functions

    def function_at(self, rva):
        for begin, end, unwind in self.runtime_functions():
            if begin <= rva < end:
                return begin, end, unwind
        self.fail(f"{rva:#x} lies in no .pdata function")

    def frame(self, unwind):
        """(bytes the prologue moves rsp by, prologue size, chained) from UNWIND_INFO, version 1,
        following a chained entry to its parent."""
        header = self.pe.get_data(unwind, 4)
        self.assertEqual(header[0] & 7, 1, "unwind info version")
        flags, prologue, count = header[0] >> 3, header[1], header[2]
        codes = self.pe.get_data(unwind + 4, 2 * count)
        size, index = 0, 0
        while index < count:
            operation, info = codes[2 * index + 1] & 0xF, codes[2 * index + 1] >> 4
            if operation == 0:  # UWOP_PUSH_NONVOL
                size, index = size + 8, index + 1
            elif operation == 1 and info == 0:  # UWOP_ALLOC_LARGE, size / 8 in the next slot
                size, index = size + 8 * struct.unpack_from("<H", codes, 2 * index + 2)[0], index + 2
            elif operation == 1:  # UWOP_ALLOC_LARGE, size in the next two slots
                size, index = size + struct.unpack_from("<I", codes, 2 * index + 2)[0], index + 3
            elif operation == 2:  # UWOP_ALLOC_SMALL
                size, index = size + 8 * info + 8, index + 1
            elif operation == 3:  # UWOP_SET_FPREG
                index += 1
            elif operation in (4, 8):  # UWOP_SAVE_NONVOL, UWOP_SAVE_XMM128
                index += 2
            elif operation in (5, 9):  # their _FAR forms
                index += 3
            else:
                self.fail(f"unexpected unwind operation {operation} at {unwind:#x}")
        chained = bool(flags & 4)
        if chained:
            parent = unwind + 4 + 2 * (count + (count & 1))
            size += self.frame(struct.unpack("<III", self.pe.get_data(parent, 12))[2])[0]
        return size, prologue, chained

    def root(self, unwind):
        """The begin of the primary entry a chained .pdata entry belongs to (itself if primary)."""
        header = self.pe.get_data(unwind, 4)
        if not header[0] >> 3 & 4:
            return None
        parent = unwind + 4 + 2 * (header[2] + (header[2] & 1))
        begin, _, parent_unwind = struct.unpack("<III", self.pe.get_data(parent, 12))
        return self.root(parent_unwind) or begin

    def function_ranges(self, rva):
        """Every .pdata range of the function holding `rva`: its primary entry and the chunks
        MSVC split off with chained unwind info."""
        begin, _, unwind = self.function_at(rva)
        primary = self.root(unwind) or begin
        return primary, sorted((low, high) for low, high, info in self.runtime_functions()
                               if (self.root(info) or low) == primary)

    def reaching_writes(self, site, register):
        """The instructions that last wrote `register` on any path that reaches `site` within its
        function ("entry" when a path reaches the entry without a write). Every chunk of the
        function counts, and direct branches from other functions must not land in it except at
        its entry; an indirect jump may reach any instruction of the function; calls keep the
        callee-saved registers this is used for."""
        primary, ranges = self.function_ranges(site)
        instructions = [item for low, high in ranges for item in self.decode(low, high)]
        order = [item.address - self.base for item in instructions]
        by_address = dict(zip(order, instructions))
        predecessors = {address: [] for address in order}
        indirect = []
        for index, item in enumerate(instructions):
            address = order[index]
            if item.group(capstone.CS_GRP_RET) or item.mnemonic == "int3":
                continue
            following = address + item.size
            if item.mnemonic != "jmp" and following in predecessors:
                predecessors[following].append(address)
            if item.group(capstone.CS_GRP_JUMP):
                operand = item.operands[0]
                if operand.type == X86_OP_IMM:
                    target = operand.imm - self.base
                    if target in predecessors:
                        predecessors[target].append(address)
                else:
                    indirect.append(address)
        for low, high in ranges:
            for source, target in self.branches_into(low, high):
                if source in predecessors or target == primary:
                    continue  # within the function, or a tail call to its entry
                self.fail(f"{source:#x} outside the function branches to {target:#x}")
        found, seen, work = set(), set(), list(predecessors[site]) + indirect
        while work:
            address = work.pop()
            if address in seen:
                continue
            seen.add(address)
            _, written = by_address[address].regs_access()
            if register in {normalize(by_address[address].reg_name(r)) for r in written}:
                found.add(address)
                continue
            if address == primary:
                found.add("entry")
            work += predecessors[address] + indirect
        return found

    def branches_into(self, begin, end):
        """Direct jumps from other .pdata ranges into [begin, end)."""
        if not hasattr(self, "_branches"):
            lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
            branches = []
            for low, high, _ in self.runtime_functions():
                for address, _size, mnemonic, operands in lite.disasm_lite(
                        self.pe.get_data(low, high - low), self.base + low):
                    if mnemonic.startswith("j") and operands.startswith("0x"):
                        target = int(operands, 16) - self.base
                        if not low <= target < high:
                            branches.append((address - self.base, target))
            type(self)._branches = branches
        return [(source, target) for source, target in self._branches if begin <= target < end]

    def test_hook_sites_lie_in_function_bodies_with_an_aligned_stack(self):
        """Every site is past its function's prologue, where MSVC keeps rsp 16-byte aligned for
        the calls the body makes; the gates and EEex's shadow space macros rely on that."""
        for site in self.sites:
            with self.subTest(site=site["name"]):
                begin, _, unwind = self.function_at(site["rva"])
                size, prologue, _ = self.frame(unwind)  # a chained chunk adds its parent's frame
                self.assertGreaterEqual(site["rva"] - begin, prologue)
                self.assertEqual((8 + size) % 16, 0)

    def test_role_registers_hold_what_the_gates_assume(self):
        # frozen: rsi is the sprite being processed.
        self.assertEqual(self.at(0x3ABA9D), "mov dword ptr [rsi + 0x520c], r13d")
        self.assertEqual(self.at(0x3AB9FA), "mov rsi, rcx")
        self.assertEqual(self.reaching_writes(0x3ABA9D, "rsi"), {0x3AB9FA})
        # entry and dispatch: r15 sprite, r14d elapsed, rbx worker, r8d the elapsed passed on.
        self.assertEqual([f"{item.mnemonic} {item.op_str}" for item in self.decode(0x226513, 0x226523)],
                         ["mov rdi, qword ptr [rcx + 8]", "mov r14d, r8d", "mov r15, rdx", "mov rsi, rcx",
                          "mov rbp, rdi"])
        self.assertNotIn("rdx", self.written(0x226500, 0x226513))
        self.assertEqual(self.at(0x226530), "mov rbx, qword ptr [rdi + 0x10]")
        self.assertEqual(self.at(0x226540), "mov r8d, r14d")
        self.assertEqual(self.at(0x22654F), "call qword ptr [rax + 8]")
        self.assertNotIn("r15", self.written(0x22651D, 0x22654F))
        self.assertNotIn("rbx", self.written(0x226534, 0x22654F))
        self.assertNotIn("r8", self.written(0x226543, 0x22654F))
        # Constructs: on every path to each site the sprite and parent registers still hold the
        # ApplyEffect arguments (this = the effect in rcx, the sprite in rdx).
        for site_rva, sprite, parent, moves in (
                (0x1BEDD6, "rbp", "rdi", {"rbp": 0x1BEC6D, "rdi": 0x1BEC6A}),
                (0x1BBB09, "rbp", "rdi", {"rbp": 0x1BB98D, "rdi": 0x1BB98A}),
                (0x1B1894, "rdi", "rsi", {"rdi": 0x1B1808, "rsi": 0x1B180B}),
                (0x1B1AC1, "rdi", "rsi", {"rdi": 0x1B1808, "rsi": 0x1B180B}),
                (0x1BFEC8, "rsi", "rdi", {"rsi": 0x1BFD94, "rdi": 0x1BFD91})):
            with self.subTest(construct=hex(site_rva)):
                self.assertEqual(self.at(moves[sprite]), f"mov {sprite}, rdx")
                self.assertEqual(self.at(moves[parent]), f"mov {parent}, rcx")
                self.assertEqual(self.reaching_writes(site_rva, sprite), {moves[sprite]})
                self.assertEqual(self.reaching_writes(site_rva, parent), {moves[parent]})
        # The worker is rbx at every construct: the AddTail argument after each site.
        for site_rva, after in ((0x1BEDD6, 0x1BEDDD), (0x1BBB09, 0x1BBB10), (0x1B1894, 0x1B189B),
                                (0x1B1AC1, 0x1B1AC8), (0x1BFEC8, 0x1BFEF1)):
            self.assertEqual(self.at(after), "mov rdx, rbx")
            self.assertEqual(self.at(after + 3).split()[0], "call")
            self.assertNotIn("rbx", self.written(site_rva, after))
        # Each worker's phase and remaining duration are final when its gate runs: the seed and the
        # countdown precede the site, and SlowPoison, which follows it for disease and the
        # repeated EFF, writes neither (only amounts, mode and period).
        self.assertEqual(self.at(0x1BED97), "movzx r8d, word ptr [rbx + 0x18]")
        self.assertEqual(self.at(0x1BBACA), "movzx r8d, word ptr [rbx + 0x18]")
        self.assertEqual(self.at(0x1BFE8C), "movzx r8d, word ptr [rbx + 0x18]")
        self.assertEqual(self.at(0x1E87A3), "movzx ecx, word ptr [rcx + 0x18]")  # SetPeriodCounter
        self.assertEqual(self.at(0x1B188F), "call 0x1401e87a0")
        self.assertEqual(self.at(0x1B1ABC), "call 0x1401e87a0")
        self.assertEqual(self.at(0x1BED83), "call 0x1401e8840")  # before the regeneration seed
        self.assertEqual(self.at(0x1BBAB6), "call 0x1401e8840")  # before the poison seed
        self.assertEqual(self.at(0x1BFED6), "call 0x1401e8840")  # after the repeated EFF's site
        self.assertEqual(self.at(0x1B1AF0), "call 0x1401e8840")  # after disease's sites
        slow_writes = set()
        for instruction in self.decode(0x1E8840, 0x1E88D5):
            for operand in instruction.operands:
                if (operand.type == X86_OP_MEM and operand.access & capstone.CS_AC_WRITE
                        and instruction.reg_name(operand.mem.base) == "rbx"):
                    slow_writes.add(operand.mem.disp)
        self.assertEqual(slow_writes, {0x18, 0x20, 0x22, 0x24})

    def test_the_dispatcher_has_two_callers_and_compression_moves_world_time_first(self):
        self.assertEqual(self.direct_calls_to(0x226500), [0x39D5DD, 0x3ADFF7])
        self.assertEqual(self.direct_calls_to(0x39D520), [0x350212])  # only CGameSprite::CompressTime
        self.assertEqual([f"{item.mnemonic} {item.op_str}" for item in self.decode(0x3ADFEA, 0x3ADFFC)],
                         ["lea rcx, [rsi + 0x1a08]", "mov r8d, r13d", "mov rdx, rsi", "call 0x140226500"])
        # CTimerWorld::AddCurrentTime/AdvanceCurrentTime add to world time, then leave the span for
        # CScreenWorld::AsynchronousUpdate, the only caller of CGameArea::CompressTime.
        self.assertEqual(self.at(0x251255), "mov dword ptr [rcx], edx")
        self.assertEqual(self.at(0x25129C), "mov dword ptr [rcx + 0x9e0], ebx")
        self.assertEqual(self.at(0x25133A), "mov dword ptr [rdi], edx")
        self.assertEqual(self.at(0x251381), "mov dword ptr [rcx + 0x9e0], ebx")
        self.assertEqual(self.direct_calls_to(0x17DBB0), [0x2EC272])

    def test_vtables_point_at_the_family_updates(self):
        for name, family in FAMILIES.items():
            with self.subTest(family=name):
                offset = self.pe.get_offset_from_rva(family["vtable"] + 8)
                self.assertEqual(struct.unpack_from("<Q", self.data, offset)[0], self.base + family["update"])

    def test_correction_and_observer_windows_do_not_overlap(self):
        spans = list(self.windows)
        for site in self.observer_sites:
            spans.append((site["rva"], site["rva"] + len(bytes.fromhex(site["bytes"])), "observer " + site["name"]))
        spans.sort()
        for (_, end, name), (start, _, following) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start, f"{name} overlaps {following}")


if __name__ == "__main__":
    unittest.main()
