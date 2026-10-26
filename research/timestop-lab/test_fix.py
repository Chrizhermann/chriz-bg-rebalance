"""Offline validation of the clock-correction prototype (CBRTFix.lua).

Never runs the game or reads process memory. The five hook bodies run in Unicorn against
synthetic memory. A scenario driver feeds them one actor's ProcessEffectList calls, pauses and
Time Stop around a Python model of the regeneration worker; one group checks that model against
the pinned executable's own worker on synthetic memory. Set CBRTS_TEST_DEPS as for
test_observer.py; CBRTS_TEST_EXE optionally selects a copy of the exact pinned BG2:EE executable.
Run: python -B research/timestop-lab/test_fix.py -v
"""

from __future__ import annotations

import functools
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
STACK, SENTINEL, HEAL = 0x600000, 0x700000, 0x800000
INITIAL_RSP = STACK + 0x2000
LIST_OFFSET, ACTOR_ID, VTABLE, SIZE = 0x3000, 0x1234, 0x140598B18, 256
PARENT, BUFF = EFFECTS + 0x1000, EFFECTS + 0x1200
WORKER, WORKER2, WORKER3 = WORKERS, WORKERS + 0x100, WORKERS + 0x200
POINTERS = {"subject", "chitin", "regenVtable", "parent", "worker"}
CALL, LIST_COUNTER = 0x3A0, 0x1A40  # ProcessEffectList's call counter; the regenerated list's counter
SHIFTED = [(effect + 0x28, effect + 0x2C) for effect in (BUFF, PARENT)] + [(PARENT + 0x6C, PARENT + 0x70)]


def u32(value):
    return value & 0xFFFFFFFF


def s32(value):
    value = u32(value)
    return value - (1 << 32) if value & 0x80000000 else value


def s16(value):
    value &= 0xFFFF
    return value - (1 << 16) if value & 0x8000 else value


def trunc15(value):
    """C's signed division by 15, as the worker's 0x88888889 multiplications compute it."""
    return abs(value) // 15 * (1 if value >= 0 else -1)


def reseed(world, frozen, active_origin, period):
    """The phase a native, un-hasted rebuild one tick after the heal seeds (0x1BEDA2)."""
    return (u32(world - frozen + 1 - active_origin) // 15) % period


def native_seed(world, origin, period):
    """The phase the regeneration construct seeds (0x1BED97..0x1BEDD2)."""
    return (u32(world - origin) // 15) % period if period else 0


def regen_step(worker, elapsed, *, full_hp=False):
    """The regeneration AIUpdate (0x1A5CA0) of an unfrozen op98 mode-3 worker in Python, checked
    against the executable in NativeWorkerTests. `worker` holds period, phase, counter,
    remaining and done; returns the heals submitted."""
    old = worker["remaining"]
    counter = u32(worker["counter"] + 1)
    remaining = s32(old - elapsed)
    worker["counter"], worker["remaining"] = counter, remaining
    pulses, done = trunc15(s32(elapsed)), False  # one pulse per whole 15 ticks of elapsed
    if remaining > old:
        worker["remaining"] = remaining = 0
        done = True
    elif remaining <= 0:
        done = True
    if done:
        worker["done"] = 1
        pulses = trunc15(old)
    boundary = s32(counter) == 15 * trunc15(s32(counter))
    if pulses == 0 and not boundary:
        return 0
    if boundary:
        pulses += 1
        worker["counter"] = 0
    if remaining <= 0:
        pulses += trunc15(remaining)
    heals = 0
    for _ in range(min(1000, pulses)):
        worker["phase"] = (worker["phase"] + 1) & 0xFFFF
        if s16(worker["phase"]) >= s16(worker["period"]):
            worker["phase"] = 0
            heals += 1
        if full_hp:
            break
    return heals


def load_fix():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((HERE / "CBRTFix.lua").read_text(encoding="utf-8"))
    return lua


def lua_sites(module):
    return [dict(module.sites[index].items()) for index in range(1, len(module.sites) + 1)]


@functools.lru_cache(maxsize=None)
def compiled():
    """The layout, sites and bodies, assembled once at their synthetic code slots."""
    fix = load_fix().globals().CBRTF
    assembler = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    sites, code = {}, {}
    for index in range(1, len(fix.sites) + 1):
        site = dict(fix.sites[index].items())
        address = CODE + 0x1000 * (site["id"] - 1)
        encoded, _ = assembler.asm(fix.BuildAssembly(fix.sites[index], BLOCK), address)
        assert len(encoded) < 0x1000, "body outgrew its synthetic code slot"
        sites[site["id"]] = site
        code[site["id"]] = (address, bytes(encoded))
    return dict(fix.layout.items()), sites, code


class Machine:
    """All five bodies against one synthetic process image with persistent state."""

    def __init__(self):
        self.layout, self.sites, code = compiled()
        self.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        self.regions = [(CODE, 0x5000), (BLOCK, 0x1000), (GLOBAL, 0x1000), (CHITIN, 0x2000),
                        (GAME, 0x5000), (ACTOR, 0x6000), (OTHER_ACTOR, 0x6000), (EFFECTS, 0x2000),
                        (NODES, 0x1000), (WORKERS, 0x1000), (STACK, 0x4000)]
        for address, size in self.regions:
            self.uc.mem_map(address, size)
        self.code = {}
        for site_id, (address, encoded) in code.items():
            self.uc.mem_write(address, encoded)
            self.code[site_id] = (address, len(encoded))
        self.writes, self.reads = [], []
        self.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                         lambda _uc, _access, address, size, _value, _user: self.writes.append((address, size)))
        self.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                         lambda _uc, _access, address, size, _value, _user: self.reads.append((address, size)))
        # What Install(), Select() and Verify() leave in the block.
        for name, value in (("enabled", 1), ("subject", ACTOR), ("subjectID", ACTOR_ID),
                            ("listOffset", LIST_OFFSET), ("chitin", GLOBAL), ("regenVtable", VTABLE),
                            ("listVerified", 1), ("lastDispatchWorld", 9000), ("lastDispatchCall", 1675)):
            self.set(name, value)
        self.put(GLOBAL, "Q", CHITIN)
        self.put(CHITIN + 0x1090, "Q", GAME)
        self.world(9001)
        for actor in (ACTOR, OTHER_ACTOR):
            self.put(actor + 0x48, "I", ACTOR_ID)
            self.put(actor + CALL, "II", 1675, 0)
            self.put(actor + LIST_COUNTER, "I", 1675)
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

    def fields(self, *names):
        return {name: self.field(name) for name in names}

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

    def read_worker(self, address):
        period, phase, counter = struct.unpack("<HHI", self.uc.mem_read(address + 0x18, 8))
        return {"period": period, "phase": phase, "counter": counter,
                "remaining": self.get(address + 0x28, "i"), "done": self.get(address + 8, "I")}

    def write_worker(self, address, fields):
        self.put(address + 8, "I", fields["done"])
        self.put(address + 0x18, "HHI", fields["period"], fields["phase"], fields["counter"])
        self.put(address + 0x28, "i", fields["remaining"])

    def phase(self, worker):
        return self.get(worker + 0x1A, "H")

    def counter(self, worker):
        return self.get(worker + 0x1C, "I")

    def track(self, *, origin0, frozen0=0, phase=0, period=2, kappa=None, last_admitted=0,
              phase_before=None, parent=PARENT, worker=WORKER, seed_counter=0, first_t=0, last_t=0,
              next_t=0, dispatch_t=0):
        """An entry as the construct body leaves it, optionally after admitted passes."""
        for name, value in (("valid", 1), ("parent", parent), ("worker", worker), ("origin0", origin0),
                            ("frozen0", frozen0), ("activeOrigin", origin0 - frozen0), ("phase", phase),
                            ("phaseBefore", phase if phase_before is None else phase_before),
                            ("period", period), ("kappa", kappa or 0), ("kappaSet", int(kappa is not None)),
                            ("lastAdmitted", last_admitted), ("seedCounter", seed_counter),
                            ("firstT", first_t), ("lastT", last_t), ("nextT", next_t),
                            ("dispatchT", dispatch_t)):
            self.set(name, value)

    def run(self, case, site_id, *, actor=ACTOR, parent=PARENT, worker=WORKER, elapsed=1,
            flags=0x202, allowed=(), changed=None, free=(), snapshot=True):
        """Runs one body. Registers other than `changed` and `free` must come back unchanged
        (the final ones stay in self.final), and nothing outside the block, the scratch stack
        and `allowed` may be written; `snapshot` also compares every region byte by byte."""
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
        before = {address: bytes(self.uc.mem_read(address, size))
                  for address, size in self.regions} if snapshot else None
        self.writes.clear()
        self.reads.clear()
        start, length = self.code[site_id]
        self.uc.emu_start(start, start + length, count=400000)
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_RIP), start + length, "body did not complete")
        self.final = {name: self.uc.reg_read(reg) for name, reg in REGS.items()}
        expected = dict(before_regs, **(changed or {}))
        case.assertEqual({name: value for name, value in self.final.items() if name not in free},
                         {name: value for name, value in expected.items() if name not in free})
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_EFLAGS), flags)
        permitted = ((BLOCK, BLOCK + SIZE), (INITIAL_RSP - 128, INITIAL_RSP), *allowed)
        for address, size in self.writes:
            case.assertTrue(any(low <= address and address + size <= high for low, high in permitted),
                            f"write outside the block, scratch stack and owned fields: {address:#x}+{size}")
        if snapshot:
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
        cls.fix = load_fix().globals().CBRTF
        cls.layout, cls.sites, _ = compiled()

    def machine(self):
        return Machine()

    def test_load_defines_five_inert_sites(self):
        self.assertEqual({site["name"] for site in self.sites.values()},
                         {"frozen", "dispatch", "construct", "worker_exit", "dispatch_entry"})
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
                    "healReseeds", "phaseRecords", "heldFirst", "stretched", "longGaps"}
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

    def test_frozen_body_stays_idle_until_the_layout_is_verified(self):
        machine = self.machine()
        machine.effect(BUFF, b"CBRTBUF", deadline=5000)
        machine.link([BUFF])
        machine.set("listVerified", 0)
        reads = machine.run(self, 1)
        self.assertEqual((machine.field("frozen"), machine.field("shifts"), machine.deadline(BUFF)), (0, 0, 5000))
        for address, size in reads:
            self.assertTrue(BLOCK <= address and address + size <= BLOCK + SIZE
                            or address == ACTOR + 0x48 and size == 4
                            or INITIAL_RSP - 128 <= address and address + size <= INITIAL_RSP,
                            f"read before verification: {address:#x}+{size}")

    def test_frozen_walk_is_bounded_on_a_corrupt_cyclic_list(self):
        machine = self.machine()
        machine.effect(EFFECTS, b"SPWI305", deadline=5000)
        (node,) = machine.link([EFFECTS])
        machine.put(node, "Q", node)
        machine.run(self, 1)
        self.assertEqual((machine.field("frozen"), machine.field("shifts")), (1, 0))

    # Site 5: the periodic dispatch's entry, at every ProcessEffectList tail.

    def test_dispatch_entry_keeps_the_highest_world_value_and_the_latest_call(self):
        machine = self.machine()
        for world, call, highest in ((9001, 1676, 9001), (9000, 1677, 9001), (9001, 1678, 9001),
                                     (9002, 1679, 9002)):
            machine.world(world)
            machine.put(ACTOR + CALL, "I", call)
            machine.run(self, 5)
            self.assertEqual(machine.fields("lastDispatchWorld", "lastDispatchCall"),
                             {"lastDispatchWorld": highest, "lastDispatchCall": call})

    def test_dispatch_entry_ignores_other_actors_and_missing_game(self):
        for case in ("pointer", "actor_id", "game", "disabled"):
            with self.subTest(case=case):
                machine = self.machine()
                machine.world(9005)
                machine.put(ACTOR + CALL, "I", 1690)
                actor = ACTOR
                if case == "pointer":
                    actor = OTHER_ACTOR
                elif case == "actor_id":
                    machine.put(ACTOR + 0x48, "I", ACTOR_ID + 15)
                elif case == "game":
                    machine.put(CHITIN + 0x1090, "Q", 0)
                else:
                    machine.set("enabled", 0)
                before = machine.block()
                machine.run(self, 5, actor=actor)
                self.assertEqual(machine.block(), before)

    # Site 2: the periodic dispatcher has copied its list counter into the worker.

    def test_dispatch_anchors_the_first_counter_on_its_first_active_tick(self):
        machine = self.machine()
        machine.track(origin0=9000, phase=1, seed_counter=1675, first_t=9001, next_t=9001, dispatch_t=9001)
        machine.worker(WORKER, phase=1, counter=1675)
        counter = [(WORKER + 0x1C, WORKER + 0x20)]
        machine.run(self, 2, allowed=counter)
        kappa = u32(1675 - 9001)
        self.assertEqual(machine.counter(WORKER), 1675)
        self.assertEqual(machine.fields("kappa", "kappaSet", "lastAdmitted", "admitted", "phaseBefore",
                                        "lastT", "nextT", "dispatchT", "stretched"),
                         {"kappa": kappa, "kappaSet": 1, "lastAdmitted": 9001, "admitted": 1, "phaseBefore": 1,
                          "lastT": 9001, "nextT": 9002, "dispatchT": 9001, "stretched": 0})
        # Hasted: a second update in the same tick runs as a no-op call.
        machine.put(WORKER + 0x1C, "I", 1676)
        machine.run(self, 2, allowed=counter, changed={"r8": 0}, flags=0xED7)
        self.assertEqual((machine.counter(WORKER), machine.field("suppressed"), machine.field("admitted")),
                         (0, 1, 1))
        # Frozen ticks do not advance active time; the next tick continues from it.
        machine.set("frozen", 3)
        machine.set("lastFrozen", 9004)
        machine.world(9005)
        machine.put(WORKER + 0x1C, "I", 1684)
        machine.run(self, 2, allowed=counter)
        self.assertEqual(machine.counter(WORKER), u32(kappa + 9005 - 3))
        self.assertEqual(machine.counter(WORKER), 1676)
        self.assertEqual(machine.fields("lastAdmitted", "admitted", "lastT", "nextT"),
                         {"lastAdmitted": 9005, "admitted": 2, "lastT": 9002, "nextT": 9003})

    def test_dispatch_holds_until_the_first_active_tick(self):
        machine = self.machine()
        # An application while paused at 9001: the next tick is the first one.
        machine.track(origin0=9001, seed_counter=1675, first_t=9002, next_t=9001, dispatch_t=9001)
        machine.worker(WORKER, counter=1675)
        counter = [(WORKER + 0x1C, WORKER + 0x20)]
        machine.run(self, 2, allowed=counter, changed={"r8": 0})  # a hasted update at the paused value
        self.assertEqual((machine.counter(WORKER), machine.field("heldFirst"), machine.field("kappaSet"),
                          machine.field("admitted")), (0, 1, 0, 0))
        machine.world(9002)
        machine.put(WORKER + 0x1C, "I", 1676)  # the held dispatch advanced the list
        machine.run(self, 2, allowed=counter)
        self.assertEqual(machine.counter(WORKER), 1675)
        self.assertEqual(machine.fields("kappa", "lastT", "nextT", "heldFirst", "admitted"),
                         {"kappa": u32(1675 - 9002), "lastT": 9002, "nextT": 9003, "heldFirst": 1, "admitted": 1})

    def test_first_slowed_update_a_tick_late_delivers_the_skipped_pulse(self):
        machine = self.machine()
        # 1679 is a pulse boundary (1680 % 15 == 0) at the first active tick 9001.
        machine.track(origin0=9001, seed_counter=1679, first_t=9001, next_t=9001, dispatch_t=9001)
        machine.worker(WORKER, counter=1680)
        machine.world(9002)
        machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 2})
        self.assertEqual(machine.counter(WORKER), 1679)
        self.assertEqual(machine.fields("kappa", "dispatchT", "lastT", "nextT", "stretched"),
                         {"kappa": u32(1679 - 9001), "dispatchT": 9001, "lastT": 9002, "nextT": 9003,
                          "stretched": 1})

    def test_a_rebuild_in_the_second_hasted_update_is_counted_down_next_tick(self):
        machine = self.machine()
        kappa = u32(1675 - 9001)
        # Admitted at 9001, then the heal's rebuild in the same tick's second update reseeded.
        machine.track(origin0=8900, kappa=kappa, seed_counter=1675, first_t=9001, last_t=9001, next_t=9001,
                      dispatch_t=9001)
        machine.worker(WORKER, counter=1677)
        machine.world(9002)
        machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 2})
        self.assertEqual(machine.counter(WORKER), 1676)
        self.assertEqual(machine.fields("lastT", "nextT", "stretched"), {"lastT": 9002, "nextT": 9003, "stretched": 1})

    def test_dispatch_suppresses_ticks_already_delivered(self):
        kappa = u32(1675 - 9001)
        # (case, world, frozen, lastFrozen): T = world - frozen, plus one below a counted frozen tick.
        for case, world, frozen, last_frozen in (("repeated tick after a pause", 9001, 0, 0),
                                                 ("hasted update at the paused value", 9000, 0, 0),
                                                 ("frozen tick", 9002, 1, 9002),
                                                 ("paused value in a stop", 9001, 1, 9002)):
            with self.subTest(case=case):
                machine = self.machine()
                machine.track(origin0=8900, kappa=kappa, seed_counter=1675, first_t=9001, last_t=9001,
                              next_t=9002, dispatch_t=9001, last_admitted=9001)
                machine.set("frozen", frozen)
                machine.set("lastFrozen", last_frozen)
                machine.world(world)
                machine.worker(WORKER, counter=1690)
                machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 0})
                self.assertEqual((machine.counter(WORKER), machine.field("suppressed"), machine.field("admitted"),
                                  machine.field("lastT"), machine.field("nextT")), (0, 1, 0, 9001, 9002))

    def test_slowed_gaps_deliver_the_pulse_that_fell_inside_them(self):
        machine = self.machine()
        for gap in range(2, 15):
            for start in range(1675, 1690):  # the counter delivered at the last tick, 9000
                with self.subTest(gap=gap, start=start):
                    machine.track(origin0=8000, kappa=u32(start - 9000), seed_counter=start, first_t=8500,
                                  last_t=9000, next_t=9001, dispatch_t=9000)
                    machine.world(9000 + gap)
                    machine.worker(WORKER, counter=0)
                    machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": gap},
                                snapshot=False)
                    delivered = machine.counter(WORKER)
                    boundaries = [c for c in range(start + 1, start + gap + 1) if (c + 1) % 15 == 0]
                    if boundaries:
                        self.assertEqual(delivered, boundaries[-1])
                        self.assertEqual(machine.field("dispatchT"), 9000 + boundaries[-1] - start)
                    else:
                        self.assertEqual(delivered, start + gap)
                        self.assertNotEqual((delivered + 1) % 15, 0)
                        self.assertEqual(machine.field("dispatchT"), 9000 + gap)

    def test_a_slowed_gap_delivers_nothing_past_the_last_tick(self):
        # remaining 1 from nextT 9001: an unslowed worker's last call is at 9001.
        for start, delivered, dispatch_t in ((1677, 1678, 9001), (1678, 1679, 9001), (1676, 1677, 9001)):
            with self.subTest(start=start):
                machine = self.machine()
                machine.track(origin0=8000, kappa=u32(start - 9000), seed_counter=start, first_t=8500,
                              last_t=9000, next_t=9001, dispatch_t=9000)
                machine.world(9002)
                machine.worker(WORKER, counter=0, remaining=1)
                machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 2})
                self.assertEqual((machine.counter(WORKER), machine.field("dispatchT")), (delivered, dispatch_t))
                self.assertEqual(machine.fields("lastT", "nextT"), {"lastT": 9002, "nextT": 9003})
        # A remaining already used up delivers the first tick after the last delivered one.
        machine = self.machine()
        machine.track(origin0=8000, kappa=u32(1677 - 9000), seed_counter=1677, first_t=8500, last_t=9000,
                      next_t=9002, dispatch_t=9000)
        machine.world(9003)
        machine.worker(WORKER, counter=0, remaining=-4)
        machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 2})
        self.assertEqual((machine.counter(WORKER), machine.field("dispatchT")), (1678, 9001))

    def test_long_gaps_leave_whole_periods_to_the_worker(self):
        machine = self.machine()
        for gap in range(15, 47):
            for start in range(1675, 1690):
                with self.subTest(gap=gap, start=start):
                    machine.track(origin0=8000, kappa=u32(start - 9000), seed_counter=start, first_t=8500,
                                  last_t=9000, next_t=9001, dispatch_t=9000)
                    machine.set("longGaps", 0)
                    machine.world(9000 + gap)
                    machine.worker(WORKER, counter=0)
                    machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": gap},
                                snapshot=False)
                    boundaries = sum(1 for c in range(start + 1, start + gap + 1) if (c + 1) % 15 == 0)
                    worker = {"period": 0x7FFF, "phase": 0, "counter": machine.counter(WORKER),
                              "remaining": 1000, "done": 0}
                    regen_step(worker, gap)
                    self.assertEqual(worker["phase"], boundaries)  # pulses the worker makes of it
                    self.assertEqual(machine.field("longGaps"), 1)

    def test_native_elapsed_other_than_one_passes_unchanged(self):
        # Time compression: the worker makes its own pulses of the elapsed it was given.
        machine = self.machine()
        machine.track(origin0=8000, kappa=u32(1675 - 9000), seed_counter=1675, first_t=8500, last_t=9000,
                      next_t=9001, dispatch_t=9000)
        machine.world(9005)
        machine.worker(WORKER, counter=0)
        machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], elapsed=37)
        self.assertEqual(machine.counter(WORKER), 1680)  # kappa + T, not the boundary 1679 in the gap
        self.assertEqual(machine.fields("lastT", "nextT", "dispatchT", "stretched", "longGaps"),
                         {"lastT": 9005, "nextT": 9006, "dispatchT": 9005, "stretched": 0, "longGaps": 0})

    def test_elapsed_never_goes_negative(self):
        machine = self.machine()
        machine.track(origin0=8000, kappa=u32(1675 - 9000), seed_counter=1675, first_t=8500, last_t=9000,
                      next_t=9005, dispatch_t=9000)
        machine.world(9002)
        machine.worker(WORKER, counter=0)
        machine.run(self, 2, allowed=[(WORKER + 0x1C, WORKER + 0x20)], changed={"r8": 0})
        self.assertEqual(machine.fields("stretched", "admitted"), {"stretched": 0, "admitted": 1})

    def test_dispatch_leaves_other_workers_native(self):
        for case, unmatched in (("pointer", 0), ("actor_id", 0), ("vtable", 0), ("untracked", 1),
                                ("invalid", 1), ("game", 0), ("disabled", 0)):
            with self.subTest(case=case):
                machine = self.machine()
                machine.track(origin0=9000, seed_counter=1675, first_t=9001, next_t=9001)
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
        # (case, +0x3A0, frozen, lastFrozen, lastDispatchWorld, T, first active tick); world 9001,
        # the last dispatch call 1675. +0x3A0 above it: a ProcessEffectList call is running.
        cases = (("own call", 1676, 0, 0, 9000, 9001, 9001),
                 ("outside, tick not processed yet", 1675, 0, 0, 9000, 9001, 9001),
                 ("outside, tick processed", 1675, 0, 0, 9001, 9001, 9002),
                 ("outside, paused", 1675, 0, 0, 9002, 9001, 9002),
                 ("own call, frozen tick", 1676, 5, 9001, 9000, 8996, 8997),
                 ("outside, frozen tick not counted yet", 1675, 5, 9000, 9000, 8996, 8996),
                 ("outside, frozen tick counted", 1675, 5, 9001, 9001, 8996, 8997),
                 ("outside, paused in a stop", 1675, 5, 9002, 9002, 8997, 8998))
        for case, call, frozen, last_frozen, last_world, active, first in cases:
            with self.subTest(case=case):
                machine = self.machine()
                machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9181, origin=9001)
                machine.worker(WORKER, phase=1, remaining=180)
                machine.put(ACTOR + CALL, "I", call)
                machine.put(ACTOR + LIST_COUNTER, "I", 1680)
                machine.set("frozen", frozen)
                machine.set("lastFrozen", last_frozen)
                machine.set("lastDispatchWorld", last_world)
                machine.run(self, 3)
                self.assertEqual(machine.phase(WORKER), 1)
                expected = {"valid": 1, "parent": PARENT, "worker": WORKER, "origin0": 9001, "frozen0": frozen,
                            "activeOrigin": 9001 - frozen, "kappa": 0, "kappaSet": 0, "lastAdmitted": 0,
                            "phase": 1, "phaseBefore": 1, "period": 2, "newParents": 1, "restored": 0,
                            "seedCounter": 1680, "firstT": first, "nextT": active, "dispatchT": active}
                self.assertEqual(machine.fields(*expected), expected)

    def test_rebuild_of_the_tracked_parent_restores_its_phase(self):
        machine = self.machine()
        # Four frozen ticks since tracking moved the origin from 9001 to 9005.
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9185, origin=9005)
        machine.track(origin0=9001, frozen0=5, phase=0, kappa=123, last_admitted=9100, seed_counter=1680,
                      first_t=8997, last_t=9091, next_t=9092, dispatch_t=9091)
        machine.set("frozen", 9)
        machine.world(9101)
        machine.worker(WORKER2, phase=1)  # the native seed of the rebuilt worker
        machine.run(self, 3, worker=WORKER2, allowed=[(WORKER2 + 0x1A, WORKER2 + 0x1C)])
        self.assertEqual(machine.phase(WORKER2), 0)
        # The reseeded remaining counts from this tick, 9101 - 9.
        expected = {"worker": WORKER2, "restored": 1, "newParents": 0, "kappa": 123, "kappaSet": 1,
                    "lastAdmitted": 9100, "origin0": 9001, "frozen0": 5, "seedCounter": 1680, "firstT": 8997,
                    "lastT": 9091, "nextT": 9092, "dispatchT": 9091}
        self.assertEqual(machine.fields(*expected), expected)

    def test_reused_parent_address_with_another_origin_is_a_new_parent(self):
        machine = self.machine()
        machine.effect(PARENT, b"CBRTREG", opcode=98, deadline=9300, origin=9006)
        machine.track(origin0=9001, frozen0=5, phase=0, kappa=123, last_admitted=9100)
        machine.set("frozen", 9)
        machine.world(9010)
        machine.worker(WORKER2, phase=1)
        machine.put(ACTOR + CALL, "I", 1676)
        machine.run(self, 3, worker=WORKER2)
        self.assertEqual(machine.phase(WORKER2), 1)
        expected = {"worker": WORKER2, "restored": 0, "newParents": 1, "kappaSet": 0, "lastAdmitted": 0,
                    "origin0": 9006, "frozen0": 9, "activeOrigin": 8997, "phase": 1, "firstT": 9001,
                    "nextT": 9001}
        self.assertEqual(machine.fields(*expected), expected)

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
        # (dispatchT, origin0, frozen0, period); origin0 33172 is baseline_01's regeneration.
        cases = ((33192, 33172, 0, 2), (33207, 33172, 0, 2), (33186, 33172, 0, 2),
                 (33226, 33172, 0, 2), (33260, 33250, 40, 2), (40028, 39000, 3, 3))
        for dispatch_t, origin0, frozen0, period in cases:
            with self.subTest(dispatch_t=dispatch_t, period=period):
                machine = self.machine()
                machine.track(origin0=origin0, frozen0=frozen0, phase=period - 1, period=period,
                              dispatch_t=dispatch_t)
                machine.world(dispatch_t + 77)  # the body reads the delivered tick, not world time
                machine.set("frozen", 50)
                machine.worker(WORKER, period=period, phase=0)  # period - 1 -> 0: this call healed
                machine.run(self, 4)
                expected = reseed(dispatch_t, 0, origin0 - frozen0, period)
                self.assertEqual((machine.field("phase"), machine.field("healReseeds"),
                                  machine.field("phaseRecords")), (expected, 1, 1))
        self.assertEqual([reseed(case[0], 0, case[1] - case[2], case[3]) for case in cases], [1, 0, 1, 1, 1, 2])

    def test_exit_without_a_heal_records_the_worker_phase(self):
        # (period, phase before, phase after); a native rebuild after 33186 would seed 1.
        for period, before, after in ((2, 0, 1), (2, 1, 1), (1, 0, 0), (0, 0, 0), (3, 1, 2), (2, 0, 0),
                                      (3, 0, 0)):
            with self.subTest(period=period, before=before, after=after):
                machine = self.machine()
                machine.track(origin0=33172, phase=before, period=period, dispatch_t=33186)
                machine.worker(WORKER, period=period, phase=after)
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


class Actor:
    """One synthetic actor driven the way the engine drives it, with the correction's bodies at
    their sites. Each ProcessEffectList call raises +0x3A0, runs the frozen body while Time Stop
    holds the actor, rebuilds through the native seed and the construct body when the list
    changed, and ends in the periodic dispatch: the entry body, then for the regeneration worker
    the list counter copy, the dispatch body, regen_step unless frozen and the exit body; then
    the list counter rises. Applications can also come outside the actor's own calls. With
    corrected=False no body runs: the native engine."""

    def __init__(self, case, *, corrected=True, world=33000, counter=1675, duration=180, period=2):
        self.case, self.corrected = case, corrected
        self.m = Machine()
        self.world, self.call, self.list_counter = world, counter, counter
        self.duration, self.period = duration, period
        self.speed, self.slow_parity = "normal", 0
        self.stop_from = self.stop_until = None
        self.frozen_ticks = set()
        self.worker, self.parent_alive, self.rebuild_due = None, False, False
        self.rotation = 0
        self.heals, self.end, self.applied, self.seed = [], None, None, None
        self.m.set("lastDispatchWorld", world)
        self.m.set("lastDispatchCall", counter)
        self.sync()

    def sync(self):
        self.m.world(self.world)
        self.m.put(ACTOR + CALL, "I", self.call)
        self.m.put(ACTOR + LIST_COUNTER, "I", self.list_counter)

    def active(self):
        return self.world - sum(1 for tick in self.frozen_ticks if tick <= self.world)

    def frozen(self):
        return self.stop_until is not None and self.stop_from <= self.world < self.stop_until

    def calls(self):
        return {"normal": 1, "haste": 2, "slow": int(self.world % 2 == self.slow_parity)}[self.speed]

    def apply(self, *, outside):
        """Adds the fixtures. Outside the actor's calls (the console while paused, another
        actor's action) the regeneration is built at once, else in the actor's next call."""
        self.m.effect(PARENT, b"CBRTREG", opcode=98, deadline=self.world + self.duration, origin=self.world)
        self.m.effect(BUFF, b"CBRTBUF", deadline=self.world + self.duration // 2)
        self.m.link([BUFF, PARENT])
        self.parent_alive, self.applied, self.seed = True, self.active(), None
        if outside:
            self.construct()
        else:
            self.rebuild_due = True

    def remove(self):
        """Explicit removal of the regeneration (op321): the next call's rebuild drops it."""
        self.parent_alive = False
        self.rebuild_due = True

    def construct(self):
        old, self.worker = self.worker, None
        if not self.parent_alive:
            return
        address = (WORKER, WORKER2, WORKER3)[self.rotation % 3]
        self.rotation += 1
        if address == old:
            address = (WORKER, WORKER2, WORKER3)[self.rotation % 3]
            self.rotation += 1
        self.m.worker(address, period=self.period, counter=0,
                      phase=native_seed(self.world, self.m.origin(PARENT), self.period),
                      remaining=s32(self.m.deadline(PARENT) - self.world))
        if self.corrected:
            self.m.run(self.case, 3, worker=address, allowed=[(address + 0x1A, address + 0x1C)], snapshot=False)
        if self.seed is None:
            self.seed = self.list_counter  # the list counter the first worker starts from
        self.worker = address

    def pel(self):
        """One ProcessEffectList call at the current world value."""
        self.call += 1
        self.sync()
        frozen = self.frozen()
        if self.stop_until is not None and self.world >= self.stop_until:
            self.stop_from = self.stop_until = None  # the stop's end forces a rebuild
            self.rebuild_due = True
        if frozen:
            self.frozen_ticks.add(self.world)
            if self.corrected:
                self.m.run(self.case, 1, allowed=SHIFTED, snapshot=False)
        if self.rebuild_due:
            self.rebuild_due = False
            self.construct()
        if self.corrected:
            self.m.run(self.case, 5, snapshot=False)
        worker = self.worker
        if worker is not None:
            self.m.put(worker + 0x1C, "I", self.list_counter)
            elapsed = 1
            if self.corrected:
                self.m.run(self.case, 2, worker=worker, allowed=[(worker + 0x1C, worker + 0x20)], free={"r8"},
                           snapshot=False)
                elapsed = s32(self.m.final["r8"])
            if not frozen:
                fields = self.m.read_worker(worker)
                heals = regen_step(fields, elapsed)
                self.m.write_worker(worker, fields)
                if heals:
                    self.heals += [self.active()] * heals
                    self.rebuild_due = True  # the heal's op17 changes the list
            if self.corrected:
                self.m.run(self.case, 4, worker=worker, snapshot=False)
            if self.m.read_worker(worker)["done"]:
                self.end, self.worker = self.active(), None
        self.list_counter += 1
        self.sync()

    def tick(self, calls=None):
        self.world += 1
        for _ in range(self.calls() if calls is None else calls):
            self.pel()

    def ticks(self, count):
        for _ in range(count):
            self.tick()

    def set_speed(self, speed, parity=0):
        """Haste or Slow starts or ends: the effect list changes, so the next call rebuilds."""
        self.speed, self.slow_parity = speed, parity
        self.rebuild_due = True

    def stop(self, length, *, now=False):
        """Time Stop by another actor, from the next tick or, with now, this tick's later calls."""
        self.stop_from = self.world if now else self.world + 1
        self.stop_until = self.stop_from + length

    def pause(self, during=None):
        """A pause after this tick's calls steps world time back one tick (EEex's B3TimeStep
        notes it too). After unpausing a hasted actor gets an extra call at the paused value,
        then the paused tick runs again."""
        self.world -= 1
        self.sync()
        if during:
            during()
        if self.speed == "haste":
            self.pel()
        self.tick()

    def finish(self, limit=600):
        for _ in range(limit):
            if self.end is not None:
                return self
            self.tick()
        raise AssertionError("the regeneration never ended")


class ScenarioTests(unittest.TestCase):
    """The bodies against one actor's call order, compared in active time with the native engine
    driving an un-hasted actor that is never paused or stopped and starts its regeneration from
    the same list counter."""

    def actor(self, **options):
        return Actor(self, **options)

    def native(self, **options):
        return Actor(self, corrected=False, **options)

    def assertSameRegeneration(self, corrected, reference, *, slack=0):
        detail = f"corrected {corrected.heals} end {corrected.end}, reference {reference.heals} end {reference.end}"
        self.assertEqual(len(corrected.heals), len(reference.heals), detail)
        for got, want in zip(corrected.heals + [corrected.end], reference.heals + [reference.end]):
            self.assertTrue(0 <= got - want <= slack, detail)

    @staticmethod
    def lead_in(actor, ticks=5):
        actor.ticks(ticks)
        return actor

    def apply(self, actor, how):
        """inside: built in the actor's next call, the next tick's first; within: just before a
        tick's calls and built in the first; second: built in a hasted tick's second call;
        before/after: outside, before or after the actor's first call of a tick; paused: while
        paused."""
        if how == "inside":
            actor.apply(outside=False)
            actor.tick()
        elif how == "within":
            actor.world += 1
            actor.apply(outside=False)
            for _ in range(actor.calls()):
                actor.pel()
        elif how == "second":
            actor.world += 1
            actor.pel()
            actor.apply(outside=False)
            actor.pel()
        elif how in ("before", "after"):
            actor.world += 1
            calls = actor.calls()
            if how == "after":
                actor.pel()
                calls -= 1
            actor.apply(outside=True)
            for _ in range(calls):
                actor.pel()
        else:
            actor.pause(during=lambda: actor.apply(outside=True))
        return actor

    def reference(self, how, applied, seed):
        """An un-hasted native actor applied `how` at active tick `applied`, whose regeneration
        starts from list counter `seed`."""
        native = self.native(world=applied - {"inside": 5, "within": 6, "before": 6, "after": 6, "paused": 4}[how],
                             counter=seed - (6 if how == "after" else 5))
        self.apply(self.lead_in(native), how).finish()
        self.assertEqual((native.applied, native.seed), (applied, seed))
        return native

    def matching(self, corrected, how):
        self.assertEqual(corrected.m.field("seedCounter"), corrected.seed)
        return self.reference(how, corrected.applied, corrected.seed)

    def test_unhasted_correction_keeps_the_native_pattern(self):
        for how in ("inside", "before", "after", "paused"):
            with self.subTest(application=how):
                corrected = self.apply(self.lead_in(self.actor()), how).finish()
                native = self.apply(self.lead_in(self.native()), how).finish()
                self.assertEqual((corrected.heals, corrected.end), (native.heals, native.end))
                self.assertIn(len(native.heals), (5, 6))
                self.assertEqual(corrected.m.fields("heldFirst", "suppressed", "stretched", "longGaps"),
                                 {"heldFirst": 0, "suppressed": 0, "stretched": 0, "longGaps": 0})

    def test_haste_regenerates_like_an_unhasted_actor(self):
        # Applied between a hasted actor's two calls of a tick, it matches an un-hasted actor
        # applied after its call; applied while paused, the extra call at the paused value is
        # held (R7).
        for how, reference in (("inside", "inside"), ("second", "within"), ("before", "before"),
                               ("after", "after"), ("paused", "paused")):
            with self.subTest(application=how):
                actor = self.lead_in(self.actor())
                actor.speed = "haste"
                corrected = self.apply(actor, how).finish()
                self.assertSameRegeneration(corrected, self.matching(corrected, reference))
                self.assertEqual(corrected.m.field("heldFirst"), int(how in ("after", "paused")))

    def test_entering_and_leaving_haste(self):
        for enter, leave in ((68, None), (None, 85), (20, 120), (67, 68)):
            with self.subTest(enter=enter, leave=leave):
                actor = self.apply(self.lead_in(self.actor()), "inside")
                if enter is None:
                    actor.set_speed("haste")
                for tick in range(1, 400):
                    if actor.end is not None:
                        break
                    if tick == enter:
                        actor.set_speed("haste")
                    if tick == leave:
                        actor.set_speed("normal")
                    actor.tick()
                self.assertSameRegeneration(actor, self.matching(actor, "inside"))

    def test_hasted_worker_ends_with_the_unhasted_one(self):
        # R8: the heal rebuilds in a second hasted update reseed deadline - world.
        actor = self.apply(self.lead_in(self.actor()), "inside")
        actor.speed = "haste"
        actor.finish()
        reference = self.matching(actor, "inside")
        self.assertEqual(actor.end, reference.end)
        self.assertEqual(reference.end, reference.applied + reference.duration - 1)  # deadline - 1
        self.assertGreater(actor.m.field("stretched"), 0)

    def test_slow_regenerates_within_one_tick_of_an_unslowed_actor(self):
        # Applications built at once. One built in a slowed actor's own call, as "inside" here,
        # starts its grid at that call, which can come a tick after an unslowed actor's.
        for parity in (0, 1):
            for how in ("before", "after", "paused"):
                with self.subTest(parity=parity, application=how):
                    actor = self.lead_in(self.actor())
                    actor.speed, actor.slow_parity = "slow", parity
                    corrected = self.apply(actor, how).finish()
                    self.assertSameRegeneration(corrected, self.matching(corrected, how), slack=1)
                    self.assertGreater(corrected.m.field("stretched"), 50)
                    self.assertEqual(corrected.m.field("longGaps"), 0)

    def test_entering_and_leaving_slow(self):
        for enter, leave in ((30, None), (None, 90), (20, 121)):
            with self.subTest(enter=enter, leave=leave):
                actor = self.apply(self.lead_in(self.actor()), "inside")
                if enter is None:
                    actor.set_speed("slow")
                for tick in range(1, 400):
                    if actor.end is not None:
                        break
                    if tick == enter:
                        actor.set_speed("slow", parity=1)
                    if tick == leave:
                        actor.set_speed("normal")
                    actor.tick()
                self.assertSameRegeneration(actor, self.matching(actor, "inside"), slack=1)

    def test_native_slow_and_haste_change_the_heal_count(self):
        for speed in ("haste", "slow"):
            with self.subTest(speed=speed):
                native = self.lead_in(self.native())
                native.speed = speed
                self.apply(native, "inside").finish()
                reference = self.reference("inside", native.applied, native.seed)
                if speed == "haste":
                    self.assertGreater(len(native.heals), len(reference.heals))
                else:
                    self.assertLess(len(native.heals), len(reference.heals))

    def test_time_stop_keeps_active_time(self):
        for speed, start, length in (("normal", 70, 89), ("normal", 1, 30), ("normal", 150, 89),
                                     ("haste", 70, 89), ("haste", 33, 47)):
            with self.subTest(speed=speed, start=start, length=length):
                actor = self.apply(self.lead_in(self.actor()), "inside")
                actor.speed = speed
                actor.ticks(start)
                actor.stop(length)
                corrected = actor.finish()
                self.assertSameRegeneration(corrected, self.matching(corrected, "inside"))
                self.assertEqual(corrected.m.field("frozen"), length)

    def test_time_stop_between_two_hasted_updates(self):
        # The stop starts after the hasted actor's first call of a tick; that tick counts frozen.
        actor = self.apply(self.lead_in(self.actor()), "inside")
        actor.speed = "haste"
        actor.ticks(69)
        actor.world += 1
        actor.pel()
        actor.stop(89, now=True)
        actor.pel()
        actor.finish()
        self.assertEqual(actor.m.field("frozen"), 89)
        self.assertSameRegeneration(actor, self.matching(actor, "inside"))

    def test_consecutive_stops(self):
        actor = self.apply(self.lead_in(self.actor()), "inside")
        actor.ticks(40)
        actor.stop(30)
        actor.ticks(31)
        actor.stop(45)
        actor.ticks(60)
        actor.stop(12)
        corrected = actor.finish()
        self.assertSameRegeneration(corrected, self.matching(corrected, "inside"))
        self.assertEqual(corrected.m.field("frozen"), 30 + 45 + 12)

    def test_pauses_do_not_move_the_corrected_grid(self):
        for speed, stop in (("normal", False), ("haste", False), ("normal", True), ("haste", True)):
            with self.subTest(speed=speed, stop=stop):
                actor = self.apply(self.lead_in(self.actor()), "inside")
                actor.speed = speed
                for tick in range(1, 600):
                    if actor.end is not None:
                        break
                    if stop and tick == 60:
                        actor.stop(40)
                    if tick in (14, 29, 61, 75, 99, 100, 140):
                        actor.pause()
                    else:
                        actor.tick()
                self.assertSameRegeneration(actor, self.matching(actor, "inside"))

    def test_native_pauses_move_the_grid(self):
        native = self.apply(self.lead_in(self.native()), "inside")
        for tick in range(1, 300):
            if native.end is not None:
                break
            if tick in (14, 29, 44, 59):
                native.pause()
            else:
                native.tick()
        self.assertNotEqual(native.heals, self.reference("inside", native.applied, native.seed).heals)

    def test_application_during_a_stop(self):
        # The stop holds ticks 33096..33145. Applied before the actor's frozen call of a tick,
        # the regeneration starts on the first tick after the stop; applied after that call, it
        # starts like an application after the call of the last tick before the stop.
        for speed in ("normal", "haste"):
            for how, applied in (("before", 33096), ("after", 33095)):
                with self.subTest(speed=speed, application=how):
                    actor = self.lead_in(self.actor(), 95)
                    actor.speed = speed
                    actor.stop(50)
                    actor.ticks(20)
                    self.apply(actor, how).finish()
                    self.assertEqual(actor.applied, applied)
                    self.assertGreater(actor.m.field("heldFirst"), 0)
                    self.assertSameRegeneration(actor, self.matching(actor, how))

    def test_application_while_paused_in_a_stop_misses_the_repeated_frozen_tick(self):
        # Documented residual: parents applied at the paused value miss the shift for the frozen
        # tick the pause repeats, so they behave as if applied one active tick earlier.
        actor = self.lead_in(self.actor(), 95)
        actor.stop(50)
        actor.ticks(20)
        self.apply(actor, "paused").finish()
        self.assertEqual(actor.applied, 33095)
        early = self.native(world=33095 - 6, counter=actor.seed - 6)
        self.apply(self.lead_in(early), "after")
        self.assertEqual(early.applied, 33095)
        early.m.put(PARENT + 0x28, "I", early.m.deadline(PARENT) - 1)
        early.m.put(PARENT + 0x6C, "I", early.m.origin(PARENT) - 1)
        early.finish()
        self.assertSameRegeneration(actor, early)

    def test_removal_and_reapplication(self):
        for speed in ("normal", "haste"):
            with self.subTest(speed=speed):
                actor = self.apply(self.lead_in(self.actor()), "inside")
                actor.speed = speed
                actor.ticks(50)
                actor.remove()
                actor.ticks(30)
                self.assertIsNone(actor.worker)
                self.assertIsNone(actor.end)
                actor.heals = []
                self.apply(actor, "inside").finish()
                self.assertEqual(actor.m.field("newParents"), 2)
                self.assertSameRegeneration(actor, self.matching(actor, "inside"))


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
            EEex_Write32(BASE + 0x400 + 0x3A0, 4321)
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
                    f"{{m_bPaused = {paused}, m_bHardPaused = 0}}, "
                    f"m_pObjectGame = {{m_worldTime = {{m_gameTime = 34397}}}}}}}}")
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
        self.assertTrue(status["layout_verified"])
        self.assertEqual(read_ptr(layout["subject"]), base + 0x400)
        self.assertEqual((read(layout["subjectID"]), read(layout["listOffset"]), read(layout["frozen"]),
                          read(layout["lastFrozen"]), read(layout["listVerified"])), (0x1234, 0x300, 0, 0, 1))
        # Paused, world time stands one tick behind the last processed tick.
        self.assertEqual((read(layout["lastDispatchWorld"]), read(layout["lastDispatchCall"])), (34398, 4321))
        self.assertEqual((status["last_dispatch_world"], status["last_dispatch_call"]), (34398, 4321))
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
                 "portrait": ("LINK({BASE + 0x1000}); SPRITE = nil", "No subject in that portrait")}
        for case, (setup, message) in cases.items():
            with self.subTest(case=case):
                lua = self.runtime()
                lua.execute(setup + "; EEex_Write32(BASE, 1)")
                ok, why = lua.eval("function() return pcall(CBRTF.Select, 0) end")()
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual(lua.eval("EEex_Read32(BASE)"), 0)

    def test_select_before_the_fixtures_leaves_the_frozen_body_idle_until_verify(self):
        lua = self.runtime()
        layout = dict(lua.globals().CBRTF.layout.items())
        lua.execute("LINK({})")
        status = lua.eval("CBRTF.Select(0)")
        self.assertEqual((status["enabled"], status["layout_verified"]), (True, False))
        self.assertEqual(lua.eval(f"EEex_Read32(BASE + {layout['listVerified']})"), 0)
        lua.execute("LINK({BASE + 0x1000, BASE + 0x1200})")
        status = lua.eval("CBRTF.Verify(0)")
        self.assertEqual((status["enabled"], status["layout_verified"]), (True, True))

    def test_verify_refuses_and_a_layout_mismatch_disables(self):
        cases = {"unselected": ("EEex_Write32(BASE, 0)", "Select a subject first", 0),
                 "other subject": ("SPRITE = {_ptr = BASE + 0x500, m_id = 0x1234, m_timedEffectList = {_ptr = BASE + 0x700}}",
                                   "Not the selected subject", 1),
                 "other id": ("SPRITE.m_id = 0x4321", "Not the selected subject", 1),
                 "empty": ("LINK({})", "No timed effect on the subject yet", 1),
                 "mismatch": ("ITERATED = {BASE + 0x1200}", "Timed effect list layout mismatch", 0)}
        for case, (setup, message, enabled) in cases.items():
            with self.subTest(case=case):
                lua = self.runtime()
                lua.execute("LINK({}); CBRTF.Select(0); LINK({BASE + 0x1000, BASE + 0x1200})")
                lua.execute(setup)
                ok, why = lua.eval("function() return pcall(CBRTF.Verify, 0) end")()
                self.assertFalse(ok)
                self.assertIn(message, why)
                self.assertEqual(lua.eval("EEex_Read32(BASE)"), enabled)
                self.assertFalse(lua.eval("CBRTF.Status()")["layout_verified"])
        lua = self.runtime()
        lua.execute("LINK({}); CBRTF.Select(0); LINK({BASE + 0x1000})")
        lua.execute("EngineGlobals.g_pBaldurChitin.m_pEngineWorld.m_bPaused = 0")
        ok, why = lua.eval("function() return pcall(CBRTF.Verify, 0) end")()
        self.assertFalse(ok)
        self.assertIn("Pause the lab", why)

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
            EEex_Write32(BASE + {layout["firstT"]}, 34398)
        """)
        status = lua.eval("CBRTF.Disable()")
        self.assertFalse(status["enabled"])
        self.assertEqual((status["admitted"], status["entry"]["valid"], status["entry"]["period"],
                          status["entry"]["first_t"]), (7, True, 2, 34398))

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
    # The heal path allocates and submits an op17 effect; these skip exactly those calls.
    ALLOCATE, CONSTRUCT, SUBMIT, AFTER_SUBMIT = 0x1A5E42, 0x1A5E52, 0x1A5EB7, 0x1A5EDC

    @classmethod
    def setUpClass(cls):
        data = EXE.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXE_SHA256:
            raise unittest.SkipTest("CBRTS_TEST_EXE is not the pinned 2.7.3.0 executable")
        pe = pefile.PE(data=data, fast_load=True)
        cls.base = pe.OPTIONAL_HEADER.ImageBase
        text = next(section for section in pe.sections if section.Name.rstrip(b"\0") == b".text")
        rva, code = text.VirtualAddress, text.get_data()
        cls.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        cls.uc.mem_map(cls.base + rva, (len(code) + 0xFFF) & ~0xFFF)
        cls.uc.mem_write(cls.base + rva, code)
        cls.data = [((cls.base + cls.GLOBAL_RVA) & ~0xFFF, 0x1000), (CHITIN, 0x2000), (GAME, 0xA000),
                    (ACTOR, 0x6000), (WORKERS, 0x1000), (STACK, 0x4000), (SENTINEL, 0x1000), (HEAL, 0x1000)]
        for address, size in cls.data:
            cls.uc.mem_map(address, size)
        cls.state = {}
        start, end = cls.base + cls.WORKER_RVA, cls.base + cls.END_RVA

        def code_hook(uc, address, _size, _user):
            state = cls.state
            if address == cls.base + cls.EPILOG_RVA:
                state["visited"].append(address)
            elif not start <= address < end:
                state["outside"].append(address)
            if state.get("stub"):
                if address == cls.base + cls.ALLOCATE:
                    uc.reg_write(x86.UC_X86_REG_RAX, HEAL)
                    uc.reg_write(x86.UC_X86_REG_RIP, address + 5)
                elif address == cls.base + cls.CONSTRUCT:
                    uc.reg_write(x86.UC_X86_REG_RIP, address + 5)
                elif address == cls.base + cls.SUBMIT:
                    state["heals"] += 1
                    uc.reg_write(x86.UC_X86_REG_RIP, cls.base + cls.AFTER_SUBMIT)

        cls.uc.hook_add(unicorn.UC_HOOK_CODE, code_hook)
        cls.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                        lambda _uc, _access, address, size, _value, _user: cls.state["writes"].append((address, size)))

    def emulate(self, *, counter, elapsed, phase=0, period=2, remaining=100, time_stop=0, immunity=0,
                hp=50, stub=False):
        uc = self.uc
        for address, size in self.data:
            uc.mem_write(address, bytes(size))
        put = lambda address, format_, *values: uc.mem_write(address, struct.pack("<" + format_, *values))
        put(self.base + self.GLOBAL_RVA, "Q", CHITIN)
        put(CHITIN + 0x1090, "Q", GAME)
        put(GAME + 0x9690, "II", time_stop, ACTOR_ID + 1)  # the caster is someone else
        put(ACTOR + 0x48, "I", ACTOR_ID)
        put(ACTOR + 0x4EA4, "I", 0)
        put(ACTOR + 0x20A0, "I", immunity)  # +0x4EA4 == 0 selects this stats block
        put(ACTOR + 0x57C, "h", hp)
        put(ACTOR + 0x1124, "h", 83)
        put(WORKER, "QII", VTABLE, 0, 0)
        put(WORKER + 0x18, "HHI", period, phase, u32(counter))
        put(WORKER + 0x20, "HHH", 3, 1, 1)
        put(WORKER + 0x28, "i", remaining)
        put(INITIAL_RSP, "Q", SENTINEL)
        for name in REG_NAMES:
            uc.reg_write(REGS[name], 0)
        uc.reg_write(REGS["rsp"], INITIAL_RSP)
        uc.reg_write(REGS["rcx"], WORKER)
        uc.reg_write(REGS["rdx"], ACTOR)
        uc.reg_write(REGS["r8"], u32(elapsed))
        self.state.clear()
        self.state.update(visited=[], outside=[], writes=[], heals=0, stub=stub)
        uc.emu_start(self.base + self.WORKER_RVA, SENTINEL, count=200000)
        self.assertEqual(uc.reg_read(x86.UC_X86_REG_RIP), SENTINEL)
        self.assertEqual(len(self.state["visited"]), 1, "every return path passes the patched epilog")
        fields = dict(zip(("period", "phase", "counter"), struct.unpack("<HHI", uc.mem_read(WORKER + 0x18, 8))))
        fields["remaining"], = struct.unpack("<i", uc.mem_read(WORKER + 0x28, 4))
        fields["done"], = struct.unpack("<I", uc.mem_read(WORKER + 8, 4))
        worker_writes = sorted({address - WORKER for address, _ in self.state["writes"]
                                if WORKERS <= address < WORKERS + 0x1000})
        if stub:
            return fields, self.state["heals"]
        return fields, worker_writes, self.state["outside"]

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

    def test_the_python_worker_model_matches_the_executable(self):
        for counter in (13, 14, 29, 1679):
            for elapsed in (0, 1, 2, 14, 15, 16, 31):
                for phase, period in ((0, 1), (0, 2), (1, 2), (1, 3), (2, 3)):
                    for remaining in (-3, 1, 2, 16, 100):
                        with self.subTest(counter=counter, elapsed=elapsed, phase=phase, period=period,
                                          remaining=remaining):
                            native, heals = self.emulate(counter=counter, elapsed=elapsed, phase=phase,
                                                         period=period, remaining=remaining, stub=True)
                            model = {"period": period, "phase": phase, "counter": counter,
                                     "remaining": remaining, "done": 0}
                            self.assertEqual(regen_step(model, elapsed), heals)
                            self.assertEqual(model, native)
        # At full HP the worker stops after its first pulse.
        native, heals = self.emulate(counter=14, elapsed=31, period=1, hp=83, stub=True)
        model = {"period": 1, "phase": 0, "counter": 14, "remaining": 100, "done": 0}
        self.assertEqual((regen_step(model, 31, full_hp=True), model), (heals, native))
        self.assertEqual(heals, 1)


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

    def direct_calls_to(self, target):
        text = next(section for section in self.pe.sections if section.Name.rstrip(b"\0") == b".text")
        code, rva = text.get_data(), text.VirtualAddress
        return [rva + index for index in range(len(code) - 5)
                if code[index] in (0xE8, 0xE9)
                and rva + index + 5 + int.from_bytes(code[index + 1:index + 5], "little", signed=True) == target]

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
        # dispatch_entry: the replayed prologue window leaves the sprite (rdx) in r15.
        self.assertEqual([f"{item.mnemonic} {item.op_str}" for item in self.decode(0x226513, 0x226523)],
                         ["mov rdi, qword ptr [rcx + 8]", "mov r14d, r8d", "mov r15, rdx", "mov rsi, rcx",
                          "mov rbp, rdi"])
        self.assertNotIn("rdx", self.written(0x226500, 0x226513))
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

    def test_dispatch_entry_sees_every_caller_with_the_sprite_in_rdx(self):
        # ProcessEffectList's tail and time compression, both passing the sprite.
        self.assertEqual(self.direct_calls_to(0x226500), [0x39D5DD, 0x3ADFF7])
        self.assertEqual([f"{item.mnemonic} {item.op_str}" for item in self.decode(0x3ADFEA, 0x3ADFFC)],
                         ["lea rcx, [rsi + 0x1a08]", "mov r8d, r13d", "mov rdx, rsi", "call 0x140226500"])
        self.assertEqual(self.at(0x226588), "inc dword ptr [rcx + 0x38]")  # empty list: the counter still rises
        self.assertEqual(self.at(0x22657E), "inc dword ptr [rsi + 0x38]")

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
