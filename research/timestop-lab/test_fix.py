"""Offline validation of the clock-correction prototype (CBRTFix.lua).

Never runs the game or reads process memory. The four hook bodies run in Unicorn against
synthetic memory; one group also emulates the pinned executable's regeneration worker on
synthetic memory. Set CBRTS_TEST_DEPS as for test_observer.py; CBRTS_TEST_EXE optionally
selects a copy of the exact pinned BG2:EE executable.
Run: python -B research/timestop-lab/test_fix.py -v
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

sys.dont_write_bytecode = True
dependency_path = os.environ.get("CBRTS_TEST_DEPS")
if not dependency_path or not Path(dependency_path).is_dir():
    raise SystemExit("Set CBRTS_TEST_DEPS to the installed offline test dependencies directory")
sys.path.insert(0, dependency_path)

import capstone
from capstone.x86_const import X86_OP_MEM, X86_REG_RIP
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
CODE, BLOCK, GLOBAL, CHITIN, GAME = 0x100000, 0x200000, 0x300000, 0x310000, 0x320000
ACTOR, OTHER_ACTOR, EFFECTS, NODES, WORKERS = 0x400000, 0x480000, 0x500000, 0x510000, 0x520000
STACK, SENTINEL = 0x600000, 0x700000
INITIAL_RSP = STACK + 0x2000
LIST_OFFSET, ACTOR_ID, VTABLE, SIZE = 0x3000, 0x1234, 0x140598B18, 256
PARENT, BUFF = EFFECTS + 0x1000, EFFECTS + 0x1200
WORKER, WORKER2, WORKER3 = WORKERS, WORKERS + 0x100, WORKERS + 0x200
POINTERS = {"subject", "chitin", "regenVtable", "parent", "worker"}


def u32(value):
    return value & 0xFFFFFFFF


def reseed(world, frozen, active_origin, period):
    """The phase a native, un-hasted rebuild one tick after the heal seeds (0x1BEDA2)."""
    return (u32(world - frozen + 1 - active_origin) // 15) % period


def load_fix():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((HERE / "CBRTFix.lua").read_text(encoding="utf-8"))
    return lua


def lua_sites(module):
    return [dict(module.sites[index].items()) for index in range(1, len(module.sites) + 1)]


class Machine:
    """All four bodies against one synthetic process image with persistent state."""

    def __init__(self, bodies, layout, sites):
        self.layout, self.sites = layout, sites
        self.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        self.regions = [(CODE, 0x4000), (BLOCK, 0x1000), (GLOBAL, 0x1000), (CHITIN, 0x2000),
                        (GAME, 0x5000), (ACTOR, 0x6000), (OTHER_ACTOR, 0x6000), (EFFECTS, 0x2000),
                        (NODES, 0x1000), (WORKERS, 0x1000), (STACK, 0x4000)]
        for address, size in self.regions:
            self.uc.mem_map(address, size)
        assembler = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
        self.code = {}
        for site_id, text in bodies.items():
            address = CODE + 0x1000 * (site_id - 1)
            encoded, _ = assembler.asm(text, address)
            assert len(encoded) < 0x1000, "body outgrew its synthetic code slot"
            self.uc.mem_write(address, bytes(encoded))
            self.code[site_id] = (address, len(encoded))
        self.writes, self.reads = [], []
        self.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                         lambda _uc, _access, address, size, _value, _user: self.writes.append((address, size)))
        self.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                         lambda _uc, _access, address, size, _value, _user: self.reads.append((address, size)))
        # What Install() and Select() leave in the block.
        for name, value in (("enabled", 1), ("subject", ACTOR), ("subjectID", ACTOR_ID),
                            ("listOffset", LIST_OFFSET), ("chitin", GLOBAL), ("regenVtable", VTABLE)):
            self.set(name, value)
        self.put(GLOBAL, "Q", CHITIN)
        self.put(CHITIN + 0x1090, "Q", GAME)
        self.world(9001)
        for actor in (ACTOR, OTHER_ACTOR):
            self.put(actor + 0x48, "I", ACTOR_ID)
        self.link([])

    def put(self, address, format_, *values):
        self.uc.mem_write(address, struct.pack("<" + format_, *values))

    def get(self, address, format_):
        return struct.unpack("<" + format_, self.uc.mem_read(address, struct.calcsize("<" + format_)))[0]

    def set(self, name, value):
        format_ = "Q" if name in POINTERS else "I"
        self.put(BLOCK + self.layout[name], format_, value & (2 ** (8 * struct.calcsize(format_)) - 1))

    def field(self, name):
        return self.get(BLOCK + self.layout[name], "Q" if name in POINTERS else "I")

    def block(self):
        return bytes(self.uc.mem_read(BLOCK, SIZE))

    def world(self, value):
        self.put(GAME + 0x3FA0, "I", value)

    def effect(self, address, source, opcode=0, timing=0x1000, deadline=0, origin=0):
        self.put(address + 0x10, "I", opcode)
        self.put(address + 0x24, "II", timing, deadline)
        self.put(address + 0x6C, "I", origin)
        self.uc.mem_write(address + 0x94, source.ljust(8, b"\0"))

    def deadline(self, effect):
        return self.get(effect + 0x28, "I")

    def origin(self, effect):
        return self.get(effect + 0x6C, "I")

    def link(self, effects, actor=ACTOR):
        """CPtrList at actor+LIST_OFFSET: m_pNodeHead +8; CNode pNext +0, pPrev +8, data +0x10."""
        nodes = [NODES + 0x20 * index for index in range(len(effects))]
        for index, (node, effect) in enumerate(zip(nodes, effects)):
            following = nodes[index + 1] if index + 1 < len(nodes) else 0
            self.put(node, "QQQ", following, nodes[index - 1] if index else 0, effect)
        self.put(actor + LIST_OFFSET + 8, "Q", nodes[0] if nodes else 0)
        return nodes

    def worker(self, address, period=2, phase=0, counter=0, remaining=180, vtable=VTABLE):
        self.put(address, "Q", vtable)
        self.put(address + 8, "II", 0, 0)
        self.put(address + 0x18, "HHI", period, phase, counter)
        self.put(address + 0x20, "HHH", 3, 1, 1)  # op98 mode 3: 1 HP every `period` pulses
        self.put(address + 0x28, "i", remaining)

    def phase(self, worker):
        return self.get(worker + 0x1A, "H")

    def counter(self, worker):
        return self.get(worker + 0x1C, "I")

    def track(self, *, origin0, frozen0=0, phase=0, period=2, kappa=None, last_admitted=0,
              phase_before=None, parent=PARENT, worker=WORKER):
        """An entry as the construct body leaves it, optionally after admitted passes."""
        for name, value in (("valid", 1), ("parent", parent), ("worker", worker), ("origin0", origin0),
                            ("frozen0", frozen0), ("activeOrigin", origin0 - frozen0), ("phase", phase),
                            ("phaseBefore", phase if phase_before is None else phase_before),
                            ("period", period), ("kappa", kappa or 0), ("kappaSet", int(kappa is not None)),
                            ("lastAdmitted", last_admitted)):
            self.set(name, value)

    def run(self, case, site_id, *, actor=ACTOR, parent=PARENT, worker=WORKER, elapsed=1,
            flags=0x202, allowed=(), changed=None):
        site = self.sites[site_id]
        for index, name in enumerate(REG_NAMES[:-1]):
            self.uc.reg_write(REGS[name], 0x0101010101010101 * (index + 1))
        self.uc.reg_write(REGS["rsp"], INITIAL_RSP)
        for role, value in (("actor", actor), ("parent", parent), ("worker", worker)):
            if site.get(role):
                self.uc.reg_write(REGS[site[role]], value)
        if site["name"] == "dispatch":
            self.uc.reg_write(REGS["r8"], elapsed)  # the elapsed argument, set at 0x226540
        self.uc.reg_write(x86.UC_X86_REG_EFLAGS, flags)
        before_regs = {name: self.uc.reg_read(reg) for name, reg in REGS.items()}
        before = {address: bytes(self.uc.mem_read(address, size)) for address, size in self.regions}
        self.writes.clear()
        self.reads.clear()
        start, length = self.code[site_id]
        self.uc.emu_start(start, start + length, count=400000)
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_RIP), start + length, "body did not complete")
        expected = dict(before_regs, **(changed or {}))
        case.assertEqual({name: self.uc.reg_read(reg) for name, reg in REGS.items()}, expected)
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_EFLAGS), flags)
        permitted = ((BLOCK, BLOCK + SIZE), (INITIAL_RSP - 128, INITIAL_RSP), *allowed)
        for address, size in self.writes:
            case.assertTrue(any(low <= address and address + size <= high for low, high in permitted),
                            f"write outside the block, scratch stack and owned fields: {address:#x}+{size}")
        # The hook above also catches a forbidden write that restored the old value.
        for address, size in self.regions:
            after = bytes(self.uc.mem_read(address, size))
            for low, high in permitted:
                low, high = max(address, low), min(address + size, high)
                if low < high:
                    after = after[:low - address] + before[address][low - address:high - address] + after[high - address:]
            case.assertEqual(after, before[address], f"foreign memory changed at {address:#x}")
        return list(self.reads)


class FixBodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No EEex globals exist here: any engine API call during load would fail.
        lua = load_fix()
        fix = lua.globals().CBRTF
        cls.layout = dict(fix.layout.items())
        cls.sites = {}
        cls.bodies = {}
        for index in range(1, len(fix.sites) + 1):
            site = dict(fix.sites[index].items())
            cls.sites[site["id"]] = site
            cls.bodies[site["id"]] = fix.BuildAssembly(fix.sites[index], BLOCK)
        cls.fix = fix

    def machine(self):
        return Machine(self.bodies, self.layout, self.sites)

    def test_load_defines_four_inert_sites(self):
        self.assertEqual({site["name"] for site in self.sites.values()},
                         {"frozen", "dispatch", "construct", "worker_exit"})
        self.assertFalse(self.fix.installed)
        status = dict(self.fix.Status().items())
        self.assertEqual((status["installed"], status["enabled"]), (False, False))

    def test_block_layout_is_disjoint_and_grouped_for_select(self):
        spans = sorted((offset, offset + (8 if name in POINTERS else 4), name)
                       for name, offset in self.layout.items())
        for (_, end, name), (start, _, following) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start, f"{name} overlaps {following}")
        self.assertLessEqual(spans[-1][1], SIZE)
        for name, offset in self.layout.items():
            if name in POINTERS:
                self.assertEqual(offset % 8, 0, name)
        # Select() clears [shifts, 128) and [parent, SIZE) and writes everything below shifts.
        counters = {"shifts", "admitted", "suppressed", "unmatched", "restored", "newParents",
                    "healReseeds", "phaseRecords"}
        for name, offset in self.layout.items():
            if name in counters:
                self.assertTrue(self.layout["shifts"] <= offset < 128, name)
            elif offset >= 128:
                self.assertGreaterEqual(offset, self.layout["parent"], name)
            else:
                self.assertLess(offset, self.layout["shifts"], name)

    def test_disabled_bodies_read_only_the_enable_flag(self):
        for site_id, site in self.sites.items():
            for flags in (0x202, 0xED7):
                with self.subTest(site=site["name"], flags=hex(flags)):
                    machine = self.machine()
                    machine.set("enabled", 0)
                    reads = machine.run(self, site_id, flags=flags)
                    for address, size in reads:
                        self.assertTrue(BLOCK <= address and address + size <= BLOCK + 4
                                        or INITIAL_RSP - 128 <= address and address + size <= INITIAL_RSP)

    # Site 1: ProcessEffectList marks a frozen noncaster.

    def test_frozen_tick_moves_fixture_parents_once_per_world_tick(self):
        machine = self.machine()
        regen, icon, foreign, longer, untimed = (EFFECTS + 0x200 * index for index in range(5))
        machine.effect(BUFF, b"CBRTBUF", deadline=5000, origin=7)
        machine.effect(regen, b"CBRTREG", opcode=98, deadline=5100, origin=4000)
        machine.effect(icon, b"CBRTREG", opcode=142, deadline=5100, origin=11)
        machine.effect(foreign, b"SPWI305", deadline=5200, origin=13)
        machine.effect(longer, b"CBRTBUFX", deadline=5300, origin=15)
        machine.effect(untimed, b"CBRTBUF", timing=0, deadline=60, origin=17)
        machine.link([BUFF, regen, icon, foreign, longer, untimed])
        owned = [(effect + 0x28, effect + 0x2C) for effect in (BUFF, regen, icon)] + [(regen + 0x6C, regen + 0x70)]
        unchanged = {foreign: (5200, 13), longer: (5300, 15), untimed: (60, 17), icon: (None, 11), BUFF: (None, 7)}

        def expect(shifted, frozen, last):
            self.assertEqual([machine.deadline(effect) for effect in (BUFF, regen, icon)],
                             [5000 + shifted, 5100 + shifted, 5100 + shifted])
            self.assertEqual(machine.origin(regen), 4000 + shifted)
            for effect, (deadline, origin) in unchanged.items():
                if deadline is not None:
                    self.assertEqual(machine.deadline(effect), deadline)
                self.assertEqual(machine.origin(effect), origin)
            self.assertEqual((machine.field("frozen"), machine.field("lastFrozen"), machine.field("shifts")),
                             (frozen, last, 3 * shifted))

        machine.run(self, 1, allowed=owned)
        expect(1, 1, 9001)
        # A hasted second pass in the same tick, a pause stepping world time back, and the
        # re-run of the paused tick all leave the moved deadlines alone.
        for world in (9001, 9000, 9001):
            machine.world(world)
            machine.run(self, 1, allowed=owned, flags=0xED7)
            expect(1, 1, 9001)
        machine.world(9002)
        machine.run(self, 1, allowed=owned)
        expect(2, 2, 9002)

    def test_frozen_tick_ignores_other_actors_and_missing_game(self):
        for case in ("pointer", "actor_id", "game", "chitin", "disabled"):
            with self.subTest(case=case):
                machine = self.machine()
                machine.effect(BUFF, b"CBRTBUF", deadline=5000)
                machine.link([BUFF])
                machine.link([BUFF], actor=OTHER_ACTOR)
                actor = ACTOR
                if case == "pointer":
                    actor = OTHER_ACTOR
                elif case == "actor_id":
                    machine.put(ACTOR + 0x48, "I", ACTOR_ID + 15)
                elif case == "game":
                    machine.put(CHITIN + 0x1090, "Q", 0)
                elif case == "chitin":
                    machine.put(GLOBAL, "Q", 0)
                else:
                    machine.set("enabled", 0)
                machine.run(self, 1, actor=actor)
                self.assertEqual((machine.field("frozen"), machine.field("shifts"), machine.deadline(BUFF)),
                                 (0, 0, 5000))

    def test_frozen_walk_is_bounded_on_a_corrupt_cyclic_list(self):
        machine = self.machine()
        machine.effect(EFFECTS, b"SPWI305", deadline=5000)
        (node,) = machine.link([EFFECTS])
        machine.put(node, "Q", node)
        machine.run(self, 1)
        self.assertEqual((machine.field("frozen"), machine.field("shifts")), (1, 0))

    # Site 2: the periodic dispatcher has copied its list counter into the worker.

    def test_dispatch_admits_one_pass_per_world_tick_on_active_time(self):
        machine = self.machine()
        machine.track(origin0=9000, phase=1)
        machine.worker(WORKER, phase=1, counter=1675)
        counter = [(WORKER + 0x1C, WORKER + 0x20)]
        machine.run(self, 2, allowed=counter)
        kappa = u32(1675 - 9001)
        self.assertEqual(machine.counter(WORKER), 1675)  # the first pass keeps the native grid
        self.assertEqual((machine.field("kappa"), machine.field("kappaSet"), machine.field("lastAdmitted"),
                          machine.field("admitted"), machine.field("phaseBefore")), (kappa, 1, 9001, 1, 1))
        # Hasted: a second update in the same tick runs as a no-op call.
        machine.put(WORKER + 0x1C, "I", 1676)
        machine.run(self, 2, allowed=counter, changed={"r8": 0}, flags=0xED7)
        self.assertEqual((machine.counter(WORKER), machine.field("suppressed"), machine.field("admitted")),
                         (0, 1, 1))
        # Frozen ticks do not advance the counter; the next tick continues from active time.
        machine.set("frozen", 3)
        machine.world(9005)
        machine.put(WORKER + 0x1C, "I", 1684)
        machine.run(self, 2, allowed=counter)
        self.assertEqual(machine.counter(WORKER), u32(kappa + 9005 - 3))
        self.assertEqual(machine.counter(WORKER), 1676)
        self.assertEqual((machine.field("lastAdmitted"), machine.field("admitted")), (9005, 2))

    def test_dispatch_leaves_other_workers_native(self):
        for case, unmatched in (("pointer", 0), ("actor_id", 0), ("vtable", 0), ("untracked", 1),
                                ("invalid", 1), ("game", 0), ("disabled", 0)):
            with self.subTest(case=case):
                machine = self.machine()
                machine.track(origin0=9000)
                machine.worker(WORKER, counter=1675)
                actor, worker = ACTOR, WORKER
                if case == "pointer":
                    actor = OTHER_ACTOR
                elif case == "actor_id":
                    machine.put(ACTOR + 0x48, "I", ACTOR_ID + 15)
                elif case == "vtable":
                    machine.put(WORKER, "Q", VTABLE + 8)
                elif case == "untracked":
                    machine.worker(WORKER2, counter=1675)
                    worker = WORKER2
                elif case == "invalid":
                    machine.set("valid", 0)
                elif case == "game":
                    machine.put(CHITIN + 0x1090, "Q", 0)
                else:
                    machine.set("enabled", 0)
                machine.run(self, 2, actor=actor, worker=worker)
                self.assertEqual(machine.counter(worker), 1675)
                self.assertEqual((machine.field("admitted"), machine.field("suppressed"),
                                  machine.field("unmatched"), machine.field("kappaSet")), (0, 0, unmatched, 0))

    # Site 3: regeneration ApplyEffect has seeded a new worker's phase.

    def test_construct_tracks_a_new_regeneration_parent_with_the_native_seed(self):
        machine = self.machine()
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9181, origin=9001)
        machine.worker(WORKER, phase=1, remaining=180)
        machine.set("frozen", 5)
        machine.run(self, 3)
        self.assertEqual(machine.phase(WORKER), 1)
        expected = {"valid": 1, "parent": PARENT, "worker": WORKER, "origin0": 9001, "frozen0": 5,
                    "activeOrigin": 8996, "kappa": 0, "kappaSet": 0, "lastAdmitted": 0, "phase": 1,
                    "phaseBefore": 1, "period": 2, "newParents": 1, "restored": 0}
        self.assertEqual({name: machine.field(name) for name in expected}, expected)

    def test_rebuild_of_the_tracked_parent_restores_its_phase(self):
        machine = self.machine()
        # Four frozen ticks since tracking moved the origin from 9001 to 9005.
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9185, origin=9005)
        machine.track(origin0=9001, frozen0=5, phase=0, kappa=123, last_admitted=9100)
        machine.set("frozen", 9)
        machine.worker(WORKER2, phase=1)  # the native seed of the rebuilt worker
        machine.run(self, 3, worker=WORKER2, allowed=[(WORKER2 + 0x1A, WORKER2 + 0x1C)])
        self.assertEqual(machine.phase(WORKER2), 0)
        expected = {"worker": WORKER2, "restored": 1, "newParents": 0, "kappa": 123, "kappaSet": 1,
                    "lastAdmitted": 9100, "origin0": 9001, "frozen0": 5}
        self.assertEqual({name: machine.field(name) for name in expected}, expected)

    def test_reused_parent_address_with_another_origin_is_a_new_parent(self):
        machine = self.machine()
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9300, origin=9006)
        machine.track(origin0=9001, frozen0=5, phase=0, kappa=123, last_admitted=9100)
        machine.set("frozen", 9)
        machine.worker(WORKER2, phase=1)
        machine.run(self, 3, worker=WORKER2)
        self.assertEqual(machine.phase(WORKER2), 1)
        expected = {"worker": WORKER2, "restored": 0, "newParents": 1, "kappaSet": 0, "lastAdmitted": 0,
                    "origin0": 9006, "frozen0": 9, "activeOrigin": 8997, "phase": 1}
        self.assertEqual({name: machine.field(name) for name in expected}, expected)

    def test_construct_ignores_other_effects_and_actors(self):
        cases = {"buff": (b"CBRTBUF", 98, 0x1000), "opcode": (b"CBRTREG", 17, 0x1000),
                 "timing": (b"CBRTREG", 98, 0), "pointer": (b"CBRTREG", 98, 0x1000),
                 "actor_id": (b"CBRTREG", 98, 0x1000)}
        for case, (source, opcode, timing) in cases.items():
            with self.subTest(case=case):
                machine = self.machine()
                machine.effect(PARENT, source, opcode=opcode, timing=timing, deadline=9300, origin=9001)
                machine.track(origin0=9001, phase=0, worker=WORKER3)
                machine.worker(WORKER2, phase=1)
                actor = OTHER_ACTOR if case == "pointer" else ACTOR
                if case == "actor_id":
                    machine.put(ACTOR + 0x48, "I", ACTOR_ID + 15)
                before = machine.block()
                machine.run(self, 3, actor=actor, worker=WORKER2)
                self.assertEqual(machine.block(), before)
                self.assertEqual(machine.phase(WORKER2), 1)

    def test_any_new_worker_at_the_tracked_address_is_untracked(self):
        machine = self.machine()
        machine.effect(PARENT + 0x100, b"OTHERREG", opcode=98, deadline=9300, origin=9050)
        machine.track(origin0=9001, phase=1, kappa=7)
        machine.worker(WORKER, phase=0)
        machine.run(self, 3, parent=PARENT + 0x100)
        self.assertEqual((machine.field("worker"), machine.field("valid"), machine.field("parent"),
                          machine.field("phase"), machine.field("kappa")), (0, 1, PARENT, 1, 7))
        machine.worker(WORKER, counter=1675)
        machine.run(self, 2)
        self.assertEqual((machine.counter(WORKER), machine.field("unmatched")), (1675, 1))

    # Site 4: the worker's AIUpdate epilog.

    def test_heal_keeps_the_phase_of_a_native_unhasted_rebuild(self):
        # (world, frozen, origin0, frozen0, period); origin0 33172 is baseline_01's regeneration.
        cases = ((33192, 0, 33172, 0, 2), (33207, 0, 33172, 0, 2), (33186, 0, 33172, 0, 2),
                 (33315, 89, 33172, 0, 2), (33300, 89, 33250, 40, 2), (40035, 7, 39000, 3, 3))
        for world, frozen, origin0, frozen0, period in cases:
            with self.subTest(world=world, frozen=frozen, period=period):
                machine = self.machine()
                machine.track(origin0=origin0, frozen0=frozen0, phase=period - 1, period=period)
                machine.set("frozen", frozen)
                machine.world(world)
                machine.worker(WORKER, period=period, phase=0)  # period - 1 -> 0: this call healed
                machine.run(self, 4)
                expected = reseed(world, frozen, origin0 - frozen0, period)
                self.assertEqual((machine.field("phase"), machine.field("healReseeds"),
                                  machine.field("phaseRecords")), (expected, 1, 1))
        self.assertEqual([reseed(*case[:2], case[2] - case[3], case[4]) for case in cases], [1, 0, 1, 1, 0, 2])

    def test_exit_without_a_heal_records_the_worker_phase(self):
        # (period, phase before, phase after, game present)
        for period, before, after, game in ((2, 0, 1, True), (2, 1, 1, True), (1, 0, 0, True),
                                            (0, 0, 0, True), (3, 1, 2, True), (2, 1, 0, False)):
            with self.subTest(period=period, before=before, after=after, game=game):
                machine = self.machine()
                machine.track(origin0=33172, phase=before, period=period)
                machine.worker(WORKER, period=period, phase=after)
                if not game:
                    machine.put(CHITIN + 0x1090, "Q", 0)
                machine.run(self, 4)
                self.assertEqual((machine.field("phase"), machine.field("healReseeds"),
                                  machine.field("phaseRecords")), (after, 0, 1))

    def test_exit_ignores_untracked_workers(self):
        for case in ("invalid", "worker", "pointer", "disabled"):
            with self.subTest(case=case):
                machine = self.machine()
                machine.track(origin0=33172, phase=1)
                machine.worker(WORKER, phase=0)
                machine.worker(WORKER2, phase=0)
                actor, worker = ACTOR, WORKER
                if case == "invalid":
                    machine.set("valid", 0)
                elif case == "worker":
                    worker = WORKER2
                elif case == "pointer":
                    actor = OTHER_ACTOR
                else:
                    machine.set("enabled", 0)
                before = machine.block()
                machine.run(self, 4, actor=actor, worker=worker)
                self.assertEqual(machine.block(), before)

    def test_hooks_hand_over_state_through_a_hasted_heal_and_a_time_stop(self):
        machine = self.machine()
        origin = 33163
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=33352, origin=origin)
        machine.effect(BUFF, b"CBRTBUF", deadline=33262)
        machine.link([BUFF, PARENT])
        counter = lambda worker: [(worker + 0x1C, worker + 0x20)]

        def dispatch(world, native, worker=WORKER, suppressed=False):
            machine.world(world)
            machine.put(worker + 0x1C, "I", native)
            machine.run(self, 2, worker=worker, allowed=counter(worker), changed={"r8": 0} if suppressed else None)
            return machine.counter(worker)

        def worker_exit(world, worker=WORKER):
            machine.world(world)
            machine.run(self, 4, worker=worker)
            return machine.field("phase")

        machine.world(33172)
        machine.worker(WORKER, phase=0)  # native seed: (33172 - 33163) // 15 % 2 = 0
        machine.run(self, 3)
        self.assertEqual(dispatch(33173, 1675), 1675)
        kappa = u32(1675 - 33173)
        self.assertEqual(worker_exit(33173), 0)
        self.assertEqual(dispatch(33173, 1676, suppressed=True), 0)
        self.assertEqual(worker_exit(33173), 0)
        # Counter 1679 pulses (1680 % 15 == 0): phase 0 -> 1, no heal.
        self.assertEqual(dispatch(33177, 1688), 1679)
        machine.put(WORKER + 0x1A, "H", 1)
        self.assertEqual(worker_exit(33177), 1)
        # Counter 1694 pulses and heals (1 -> 0) where world - origin = 29: an un-hasted rebuild
        # one tick later seeds 30 // 15 % 2 = 0, the native same-tick hasted rebuild 1.
        self.assertEqual(dispatch(33192, 1718), 1694)
        machine.put(WORKER + 0x1A, "H", 0)
        self.assertEqual(worker_exit(33192), 0)
        self.assertEqual(machine.field("healReseeds"), 1)
        # The heal's rebuild in the same tick's second update restores 0 over the native 1.
        machine.worker(WORKER2, phase=1)
        machine.run(self, 3, worker=WORKER2, allowed=[(WORKER2 + 0x1A, WORKER2 + 0x1C)])
        self.assertEqual((machine.phase(WORKER2), machine.field("restored")), (0, 1))
        self.assertEqual(dispatch(33192, 1719, worker=WORKER2, suppressed=True), 0)
        self.assertEqual(worker_exit(33192, worker=WORKER2), 0)
        # Time Stop: three frozen ticks (one hasted twice) move both parents and the origin.
        shifted = [(effect + 0x28, effect + 0x2C) for effect in (BUFF, PARENT)] + [(PARENT + 0x6C, PARENT + 0x70)]
        for world in (33193, 33193, 33194, 33195):
            machine.world(world)
            machine.run(self, 1, allowed=shifted)
        self.assertEqual((machine.field("frozen"), machine.deadline(BUFF), machine.deadline(PARENT),
                          machine.origin(PARENT)), (3, 33265, 33355, origin + 3))
        # A gated dispatch in the stop keeps the last active counter.
        self.assertEqual(dispatch(33195, 1730, worker=WORKER2), u32(kappa + 33192))
        self.assertEqual(worker_exit(33195, worker=WORKER2), 0)
        # The stop ends: the rebuild matches the moved origin and the counter resumes.
        machine.worker(WORKER3, phase=0)
        machine.run(self, 3, worker=WORKER3, allowed=[(WORKER3 + 0x1A, WORKER3 + 0x1C)])
        self.assertEqual((machine.field("worker"), machine.field("restored"), machine.field("newParents")),
                         (WORKER3, 2, 1))
        self.assertEqual(dispatch(33196, 1731, worker=WORKER3), 1695)


class FixLuaTests(unittest.TestCase):
    """Install/Select/Disable/Status against stub EEex bindings over real FFI memory."""

    def runtime(self, *, paused=1):
        lua = load_fix()
        lua.execute("""
            local ffi = require("ffi")
            MEM = ffi.new("uint8_t[?]", 8192)
            BASE = tonumber(ffi.cast("uintptr_t", MEM))
            EEex_Read32 = function(a) return ffi.cast("uint32_t*", a)[0] end
            EEex_Write32 = function(a, v) ffi.cast("uint32_t*", a)[0] = v end
            EEex_ReadPtr = function(a) return tonumber(ffi.cast("uint64_t*", a)[0]) end
            EEex_WritePtr = function(a, v) ffi.cast("uint64_t*", a)[0] = v end
            EEex_UDToPtr = function(v) return v._ptr end
            ITERATED = {}
            EEex_Utility_IterateCPtrList = function(list, f)
                for _, effect in ipairs(ITERATED) do f({_ptr = effect}) end
            end
            SPRITE = {_ptr = BASE + 0x400, m_id = 0x1234, m_timedEffectList = {_ptr = BASE + 0x700}}
            EEex_Sprite_GetInPortrait = function(slot) if slot == 0 then return SPRITE end end
            function LINK(effects)
                ITERATED = effects
                local previous = 0
                EEex_WritePtr(BASE + 0x708, 0)
                for i = #effects, 1, -1 do
                    local node = BASE + 0x800 + 0x20 * i
                    EEex_WritePtr(node, previous)
                    EEex_WritePtr(node + 0x10, effects[i])
                    previous = node
                end
                EEex_WritePtr(BASE + 0x708, previous)
            end
            CBRTF.installed = true
            CBRTF.block = BASE
        """)
        lua.execute(f"EngineGlobals = {{g_pBaldurChitin = {{m_pEngineWorld = "
                    f"{{m_bPaused = {paused}, m_bHardPaused = 0}}}}}}")
        return lua

    def test_select_writes_the_subject_and_clears_counters_and_entry(self):
        lua = self.runtime()
        layout = dict(lua.globals().CBRTF.layout.items())
        lua.execute("""
            for offset = 0, 255, 4 do EEex_Write32(BASE + offset, 0xA5A5A5A5) end
            LINK({BASE + 0x1000, BASE + 0x1200})
        """)
        status = lua.eval("CBRTF.Select(0)")
        read = lua.eval("function(offset) return EEex_Read32(BASE + offset) end")
        read_ptr = lua.eval("function(offset) return EEex_ReadPtr(BASE + offset) end")
        base = lua.eval("BASE")
        self.assertTrue(status["enabled"])
        self.assertEqual(read_ptr(layout["subject"]), base + 0x400)
        self.assertEqual((read(layout["subjectID"]), read(layout["listOffset"]), read(layout["frozen"]),
                          read(layout["lastFrozen"])), (0x1234, 0x300, 0, 0))
        for offset in range(layout["shifts"], 128, 4):
            self.assertEqual(read(offset), 0, f"counter at {offset}")
        for offset in range(layout["parent"], SIZE, 4):
            self.assertEqual(read(offset), 0, f"entry at {offset}")
        # Install() owns these two; Select() keeps them.
        self.assertEqual((read(layout["chitin"]), read(layout["regenVtable"])), (0xA5A5A5A5, 0xA5A5A5A5))

    def test_select_fails_closed(self):
        cases = {"mismatch": ("LINK({BASE + 0x1000, BASE + 0x1200}); ITERATED = {BASE + 0x1000}",
                              "Timed effect list layout mismatch"),
                 "order": ("LINK({BASE + 0x1000, BASE + 0x1200}); ITERATED = {BASE + 0x1200, BASE + 0x1000}",
                           "Timed effect list layout mismatch"),
                 "empty": ("LINK({})", "Apply the fixtures before selecting"),
                 "portrait": ("LINK({BASE + 0x1000}); SPRITE = nil", "No subject in that portrait")}
        for case, (setup, message) in cases.items():
            with self.subTest(case=case):
                lua = self.runtime()
                lua.execute(setup + "; EEex_Write32(BASE, 1)")
                ok, why = lua.eval("function() return pcall(CBRTF.Select, 0) end")()
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual(lua.eval("EEex_Read32(BASE)"), 0)

    def test_select_requires_install_and_a_pause(self):
        lua = self.runtime(paused=0)
        lua.execute("LINK({BASE + 0x1000}); EEex_Write32(BASE, 1)")
        ok, why = lua.eval("function() return pcall(CBRTF.Select, 0) end")()
        self.assertFalse(ok)
        self.assertIn("Pause the lab", why)
        self.assertEqual(lua.eval("EEex_Read32(BASE)"), 1)  # refused before touching anything
        lua = self.runtime()
        lua.execute("CBRTF.installed = false")
        ok, why = lua.eval("function() return pcall(CBRTF.Select, 0) end")()
        self.assertFalse(ok)
        self.assertIn("Install the correction first", why)

    def test_disable_works_unpaused_and_status_reports_the_entry(self):
        lua = self.runtime(paused=0)
        layout = dict(lua.globals().CBRTF.layout.items())
        lua.execute(f"""
            EEex_Write32(BASE, 1)
            EEex_Write32(BASE + {layout["admitted"]}, 7)
            EEex_Write32(BASE + {layout["valid"]}, 1)
            EEex_Write32(BASE + {layout["period"]}, 2)
        """)
        status = lua.eval("CBRTF.Disable()")
        self.assertFalse(status["enabled"])
        self.assertEqual((status["admitted"], status["entry"]["valid"], status["entry"]["period"]), (7, True, 2))

    def test_install_refuses_outside_the_fresh_main_menu_before_allocating(self):
        for state, message in ((("0", "start"), "Missing lab guard: CBRTSLab.id"),
                               (("1", "start"), "Install only at the fresh main menu"),
                               (("0", "world"), "Install only at the fresh main menu")):
            with self.subTest(state=state):
                lua = load_fix()
                attempt = lua.eval("""function(loaded, active)
                    local function object(pointer, fields) fields = fields or {}; fields._ptr = pointer; return fields end
                    local start, world = object(0x1000), object(0x2000)
                    local game = object(0x3000, {m_bGameLoaded = tonumber(loaded), m_bInLoadGame = 0,
                        m_bInLoadArea = 0})
                    EngineGlobals = {g_pBaldurChitin = object(0x4000, {m_pObjectGame = game,
                        m_pEngineStart = start, m_pEngineWorld = world,
                        pActiveEngine = active == "world" and world or start})}
                    EEex_UDToPtr = function(value) return value._ptr end
                    local allocated = false
                    EEex_Malloc = function() allocated = true; return 0 end
                    io.open = function() return nil end
                    local ok, why = pcall(CBRTF.Install)
                    return ok, tostring(why), CBRTF.installed, allocated
                end""")
                ok, why, installed, allocated = attempt(*state)
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual((installed, allocated), (False, False))


class NativeWorkerTests(unittest.TestCase):
    """The pinned executable's regeneration AIUpdate (0x1A5CA0) on synthetic memory."""

    WORKER_RVA, EPILOG_RVA, END_RVA, GLOBAL_RVA = 0x1A5CA0, 0x1A5F19, 0x1A5F20, 0x667548

    @classmethod
    def setUpClass(cls):
        data = EXE.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXE_SHA256:
            raise unittest.SkipTest("CBRTS_TEST_EXE is not the pinned 2.7.3.0 executable")
        pe = pefile.PE(data=data, fast_load=True)
        cls.base = pe.OPTIONAL_HEADER.ImageBase
        text = next(section for section in pe.sections if section.Name.rstrip(b"\0") == b".text")
        cls.text = (text.VirtualAddress, text.get_data())

    def emulate(self, *, counter, elapsed, phase=0, period=2, remaining=100, time_stop=0, immunity=0):
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        rva, code = self.text
        uc.mem_map(self.base + rva, (len(code) + 0xFFF) & ~0xFFF)
        uc.mem_write(self.base + rva, code)
        global_page = (self.base + self.GLOBAL_RVA) & ~0xFFF
        for address, size in ((global_page, 0x1000), (CHITIN, 0x2000), (GAME, 0xA000), (ACTOR, 0x6000),
                              (WORKERS, 0x1000), (STACK, 0x4000), (SENTINEL, 0x1000)):
            uc.mem_map(address, size)
        put = lambda address, format_, *values: uc.mem_write(address, struct.pack("<" + format_, *values))
        put(self.base + self.GLOBAL_RVA, "Q", CHITIN)
        put(CHITIN + 0x1090, "Q", GAME)
        put(GAME + 0x9690, "II", time_stop, ACTOR_ID + 1)  # the caster is someone else
        put(ACTOR + 0x48, "I", ACTOR_ID)
        put(ACTOR + 0x4EA4, "I", 0)
        put(ACTOR + 0x20A0, "I", immunity)  # +0x4EA4 == 0 selects this stats block
        put(ACTOR + 0x57C, "h", 50)
        put(ACTOR + 0x1124, "h", 83)
        put(WORKER, "QII", VTABLE, 0, 0)
        put(WORKER + 0x18, "HHI", period, phase, counter)
        put(WORKER + 0x20, "HHH", 3, 1, 1)
        put(WORKER + 0x28, "i", remaining)
        put(INITIAL_RSP, "Q", SENTINEL)
        uc.reg_write(REGS["rsp"], INITIAL_RSP)
        uc.reg_write(REGS["rcx"], WORKER)
        uc.reg_write(REGS["rdx"], ACTOR)
        uc.reg_write(REGS["r8"], elapsed)
        visited, outside, writes = [], [], []
        start, end = self.base + self.WORKER_RVA, self.base + self.END_RVA
        uc.hook_add(unicorn.UC_HOOK_CODE, lambda _uc, address, _size, _user:
                    (visited if address == self.base + self.EPILOG_RVA else
                     outside if not start <= address < end else []).append(address))
        uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                    lambda _uc, _access, address, size, _value, _user: writes.append((address, size)))
        uc.emu_start(start, SENTINEL, count=5000)
        self.assertEqual(uc.reg_read(x86.UC_X86_REG_RIP), SENTINEL)
        self.assertEqual(len(visited), 1, "every return path passes the patched epilog")
        fields = dict(zip(("period", "phase", "counter"), struct.unpack("<HHI", uc.mem_read(WORKER + 0x18, 8))))
        fields["remaining"], = struct.unpack("<i", uc.mem_read(WORKER + 0x28, 4))
        fields["done"], = struct.unpack("<I", uc.mem_read(WORKER + 8, 4))
        worker_writes = sorted({address - WORKER for address, _ in writes if WORKERS <= address < WORKERS + 0x1000})
        return fields, worker_writes, outside

    def test_a_suppressed_dispatch_is_a_no_op(self):
        fields, worker_writes, outside = self.emulate(counter=0, elapsed=0, phase=1, remaining=100)
        self.assertEqual((fields["phase"], fields["remaining"], fields["done"]), (1, 100, 0))
        self.assertEqual(worker_writes, [0x1C, 0x28])  # counter + 1 and an unchanged remaining
        self.assertEqual(outside, [])  # no pulse, no call

    def test_elapsed_drives_the_countdown_without_a_pulse(self):
        fields, _, outside = self.emulate(counter=13, elapsed=1, phase=0, remaining=100)
        self.assertEqual((fields["phase"], fields["counter"], fields["remaining"]), (0, 14, 99))
        self.assertEqual(outside, [])

    def test_a_pulse_comes_exactly_when_counter_plus_one_is_a_multiple_of_15(self):
        fields, _, outside = self.emulate(counter=14, elapsed=1, phase=0, remaining=100)
        self.assertEqual((fields["phase"], fields["counter"], fields["remaining"]), (1, 0, 99))
        self.assertEqual(sorted({address - self.base for address in outside}), [0x407BC0, 0x407BC2, 0x407BC4, 0x407BC7])

    def test_a_frozen_worker_returns_through_the_patched_epilog_untouched(self):
        fields, worker_writes, outside = self.emulate(counter=14, elapsed=1, phase=1, time_stop=90)
        self.assertEqual((fields["phase"], fields["counter"], fields["remaining"]), (1, 14, 100))
        self.assertEqual((worker_writes, outside), ([], []))
        fields, _, _ = self.emulate(counter=14, elapsed=1, phase=0, time_stop=90, immunity=1)
        self.assertEqual(fields["phase"], 1)  # immune to Time Stop: not frozen


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
        cls.fix_sites = lua_sites(load_fix().globals().CBRTF)
        observer = LuaRuntime(unpack_returned_tuples=True)
        observer.execute((HERE / "CBRTObs.lua").read_text(encoding="utf-8"))
        cls.observer_sites = lua_sites(observer.globals().CBRTS)
        cls.windows = [(site["rva"], site["rva"] + len(bytes.fromhex(site["bytes"])), site["name"])
                       for site in cls.fix_sites]

    def decode(self, start, end):
        return list(self.decoder.disasm(self.pe.get_data(start, end - start), self.base + start))

    def at(self, rva):
        instruction = self.decode(rva, rva + 16)[0]
        return f"{instruction.mnemonic} {instruction.op_str}"

    def written(self, start, end):
        """Registers explicitly or implicitly written by the instructions in [start, end)."""
        out = {}
        for instruction in self.decode(start, end):
            _, written = instruction.regs_access()
            for register in written:
                out.setdefault(normalize(instruction.reg_name(register)), []).append(instruction.address - self.base)
        return out

    def test_sites_are_whole_windows_without_relative_operands(self):
        self.assertEqual(self.pe.FILE_HEADER.TimeDateStamp, 0x6A18D73D)
        for site in self.fix_sites:
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

    def test_role_registers_hold_what_the_bodies_assume(self):
        # frozen: rsi is the sprite being processed; r13d is always 1 at the marker store.
        self.assertEqual(self.at(0x3ABA9D), "mov dword ptr [rsi + 0x520c], r13d")
        self.assertEqual(self.at(0x3ABA78), "mov eax, dword ptr [rsi + 0x48]")
        self.assertEqual(self.at(0x3ABA59), "mov r13d, 1")
        self.assertNotIn("r13", self.written(0x3ABA5F, 0x3ABA9D))
        self.assertNotIn("rsi", self.written(0x3ABA5F, 0x3ABA9D))
        # dispatch: r15 sprite, rbx worker, r8d the elapsed argument passed to the worker.
        self.assertEqual(self.at(0x22651A), "mov r15, rdx")
        self.assertEqual(self.at(0x226530), "mov rbx, qword ptr [rdi + 0x10]")
        self.assertEqual(self.at(0x226540), "mov r8d, r14d")
        self.assertEqual(self.at(0x22654F), "call qword ptr [rax + 8]")
        self.assertNotIn("r15", self.written(0x22651D, 0x22654F))
        self.assertNotIn("rbx", self.written(0x226534, 0x22654F))
        self.assertNotIn("r8", self.written(0x226543, 0x22654F))
        # construct: rdi parent effect, rbp sprite, rbx new worker; the seed read the period.
        self.assertEqual(self.at(0x1BEC6A), "mov rdi, rcx")
        self.assertEqual(self.at(0x1BEC6D), "mov rbp, rdx")
        self.assertEqual(self.at(0x1BED97), "movzx r8d, word ptr [rbx + 0x18]")
        written = self.written(0x1BEC70, 0x1BEDD2)
        self.assertNotIn("rdi", written)
        self.assertNotIn("rbp", written)
        # 0x1BECC0 is the failed-allocation path, which dereferences rbx = 0 natively first.
        self.assertEqual(written["rbx"], [0x1BEC7C, 0x1BECC0])
        # worker_exit: rbx worker and rsi sprite for the whole function body.
        self.assertEqual(self.at(0x1A5CAE), "mov rbx, rcx")
        self.assertEqual(self.at(0x1A5CB4), "mov rsi, rdx")
        written = self.written(0x1A5CB7, 0x1A5F19)
        self.assertNotIn("rbx", written)
        self.assertNotIn("rsi", written)

    def test_fix_and_observer_windows_do_not_overlap(self):
        spans = list(self.windows)
        for site in self.observer_sites:
            size = {"call": 5, "branch": 6}.get(site["kind"], len(bytes.fromhex(site["bytes"])))
            spans.append((site["rva"], site["rva"] + size, "observer " + site["name"]))
        spans.sort()
        for (_, end, name), (start, _, following) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start, f"{name} overlaps {following}")


if __name__ == "__main__":
    unittest.main()
