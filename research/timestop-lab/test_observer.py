"""Offline observer validation. Never executes game code or reads process memory.

Set CBRTS_TEST_DEPS to the explicitly selected directory containing Keystone,
Unicorn, pefile and Capstone. Lupa's luajit21 runtime must also be importable.
Run: python -B research/timestop-lab/test_observer.py -v
CBRTS_TEST_EXE optionally selects a copy of the exact pinned BG2:EE executable.
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
CODE, BUFFER, GLOBAL, CHITIN, GAME = 0x100000, 0x200000, 0x300000, 0x310000, 0x320000
ACTOR, PARENT, WORKER, RELATED, LIST, STACK = 0x400000, 0x410000, 0x420000, 0x430000, 0x440000, 0x500000
VTABLE, INITIAL_RSP, CAPACITY = 0x140598B18, STACK + 0x2000, 4
ALLOCATION_SIZE = 128 + CAPACITY * 128


class SyntheticHook:
    def __init__(self, site, assembly, *, flags=0xED7, armed=True, game_memory=True):
        self.site = site
        self.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        self.regions = [(CODE, 0x2000), (BUFFER, 0x1000), (STACK, 0x4000)]
        if game_memory:
            self.regions += [(GLOBAL, 0x1000), (CHITIN, 0x2000), (GAME, 0xA000),
                             (ACTOR, 0x6000), (PARENT, 0x1000), (WORKER, 0x1000),
                             (RELATED, 0x1000), (LIST, 0x1000)]
        for address, size in self.regions:
            self.uc.mem_map(address, size)
        encoded, _ = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64).asm(assembly, CODE)
        self.code = bytes(encoded)
        self.uc.mem_write(CODE, self.code)
        self.put(BUFFER, "IIII", int(armed), CAPACITY, 0, 0)
        self.put(BUFFER + 16, "Q", ACTOR)
        self.put(BUFFER + 24, "I", 0x1234)
        self.put(BUFFER + 32, "QQ", VTABLE, GLOBAL)
        for index, (name, register) in enumerate(REGS.items()):
            self.uc.reg_write(register, 0x101010101010101 * (index + 1))
        self.uc.reg_write(REGS["rsp"], INITIAL_RSP)
        self.uc.reg_write(x86.UC_X86_REG_EFLAGS, flags)
        roles = {"actor": ACTOR, "parent": PARENT, "worker": WORKER,
                 "related": RELATED, "elapsed": 7, "list": LIST}
        for role, value in roles.items():
            if site.get(role):
                self.uc.reg_write(REGS[site[role]], value)
        if game_memory:
            self.put(GLOBAL, "Q", CHITIN)
            self.put(CHITIN + 0x1090, "Q", GAME)
            self.put(GAME + 0x3FA0, "I", 9001)
            self.put(GAME + 0x9690, "II", 90, 0x4567)
            self.put(ACTOR + 0x48, "I", 0x1234)
            self.put(ACTOR + 0x58, "B", 0x31)
            self.put(ACTOR + 0x57C, "h", -37)
            self.put(ACTOR + 0x1120, "I", 0xAABBCCDD)
            self.put(ACTOR + 0x20A0, "I", 19)
            self.put(ACTOR + 0x13F8, "I", 23)
            self.put(PARENT + 0x10, "I", 98)
            self.put(PARENT + 0x24, "II", 4096, 123456)
            self.put(PARENT + 0x6C, "I", 123000)
            self.uc.mem_write(PARENT + 0x94, b"CBRTREG\0")
            self.put(WORKER, "Q", VTABLE)
            self.put(WORKER + 8, "II", 3, 5)
            self.put(WORKER + 0x18, "hhI", 2, 11, 0x13579)
            self.put(WORKER + 0x28, "I", 999)
            self.put(RELATED + 0x10, "I", 17)
            self.put(LIST + 0x38, "I", 456)

    def put(self, address, format_, *values):
        self.uc.mem_write(address, struct.pack("<" + format_, *values))

    def get(self, address, format_):
        return struct.unpack("<" + format_, self.uc.mem_read(address, struct.calcsize("<" + format_)))[0]

    def run(self, case):
        before_regs = {name: self.uc.reg_read(reg) for name, reg in REGS.items()}
        before_flags = self.uc.reg_read(x86.UC_X86_REG_EFLAGS)
        before = {address: bytes(self.uc.mem_read(address, size)) for address, size in self.regions}
        writes, reads = [], []
        self.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,
                         lambda _uc, _access, address, size, _value, _user: writes.append((address, size)))
        self.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                         lambda _uc, _access, address, size, _value, _user: reads.append((address, size)))
        self.uc.emu_start(CODE, CODE + len(self.code), count=2000)
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_RIP), CODE + len(self.code), "body did not complete")
        case.assertEqual({name: self.uc.reg_read(reg) for name, reg in REGS.items()}, before_regs)
        case.assertEqual(self.uc.reg_read(x86.UC_X86_REG_EFLAGS), before_flags)
        allowed = ((BUFFER, BUFFER + ALLOCATION_SIZE), (INITIAL_RSP - 128, INITIAL_RSP))
        for address, size in writes:
            case.assertTrue(any(start <= address and address + size <= end for start, end in allowed),
                            f"write outside log/scratch stack: {address:#x}+{size}")
        # Independently compare the full mapped regions. The write hook above also
        # catches a forbidden write that was subsequently restored to its old value.
        for address, size in self.regions:
            after = bytes(self.uc.mem_read(address, size))
            for start, end in allowed:
                low, high = max(address, start), min(address + size, end)
                if low < high:
                    after = after[:low - address] + before[address][low - address:high - address] + after[high - address:]
            case.assertEqual(after, before[address], f"foreign memory changed at {address:#x}")
        return reads


class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No EEex globals exist here: any engine API call during load would fail.
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.lua.execute((HERE / "CBRTObs.lua").read_text(encoding="utf-8"))
        observer = cls.lua.globals().CBRTS
        cls.sites = []
        cls.assemblies = {}
        for index in range(1, len(observer.sites) + 1):
            site_lua = observer.sites[index]
            site = dict(site_lua.items())
            cls.sites.append(site)
            cls.assemblies[site["id"]] = observer.BuildAssembly(site_lua, BUFFER)

    def machine(self, site, **kwargs):
        return SyntheticHook(site, self.assemblies[site["id"]], **kwargs)

    @staticmethod
    def install_attempt(loaded=0, in_load_game=0, in_load_area=0, active="start"):
        """Install() in a fresh runtime with EEex 1.3.1-shaped bindings and no lab files.

        Observed in the 2.7.3.0 lab on 2026-10-20: g_pBaldurChitin has no GetActiveEngine
        method; pActiveEngine is a bound field. Native BOOL fields are numbers.
        """
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute((HERE / "CBRTObs.lua").read_text(encoding="utf-8"))
        attempt = lua.eval("""function(loaded, inLoadGame, inLoadArea, active)
            local function object(pointer, fields) fields = fields or {}; fields._ptr = pointer; return fields end
            local start, world = object(0x1000), object(0x2000)
            local game = object(0x3000, {m_bGameLoaded = loaded, m_bInLoadGame = inLoadGame,
                m_bInLoadArea = inLoadArea})
            EngineGlobals = {g_pBaldurChitin = object(0x4000, {m_pObjectGame = game,
                m_pEngineStart = start, m_pEngineWorld = world,
                pActiveEngine = active == "world" and world or start})}
            EEex_UDToPtr = function(value) return value._ptr end
            io.open = function() return nil end
            local ok, why = pcall(CBRTS.Install)
            return ok, tostring(why), CBRTS.installed, CBRTS.failed == true, CBRTS.buffer ~= nil
        end""")
        return attempt(loaded, in_load_game, in_load_area, active)

    def test_install_precondition_reads_the_bound_active_engine(self):
        ok, why, installed, failed, buffered = self.install_attempt()
        self.assertFalse(ok)
        # Past the fresh-menu check, Install stops at the lab identity before any allocation.
        self.assertIn("Missing lab guard: CBRTSLab.id", why)
        self.assertEqual((installed, failed, buffered), (False, False, False))

    def test_install_refuses_outside_the_fresh_main_menu(self):
        for state in ({"loaded": 1}, {"in_load_game": 1}, {"in_load_area": 1}, {"active": "world"}):
            with self.subTest(**state):
                ok, why, installed, failed, buffered = self.install_attempt(**state)
                self.assertFalse(ok)
                self.assertIn("Install only at the fresh main menu", why)
                self.assertEqual((installed, failed, buffered), (False, False, False))

    def test_all_eight_bodies_preserve_registers_flags_and_write_boundaries(self):
        self.assertEqual({site["id"] for site in self.sites}, set(range(1, 9)))
        for site in self.sites:
            for flags in (0x202, 0xED7):
                with self.subTest(site=site["name"], flags=hex(flags)):
                    machine = self.machine(site, flags=flags)
                    machine.run(self)
                    self.assertEqual(machine.get(BUFFER + 8, "I"), 1)
                    self.assertEqual(machine.get(BUFFER + 128, "I"), site["id"])

    def test_disarmed_never_dereferences_game_pointers(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                machine = self.machine(site, armed=False, game_memory=False)
                reads = machine.run(self)
                for address, size in reads:
                    self.assertTrue(BUFFER <= address and address + size <= BUFFER + 128
                                    or INITIAL_RSP - 128 <= address and address + size <= INITIAL_RSP)
                self.assertEqual(machine.get(BUFFER + 8, "I"), 0)
                self.assertEqual(bytes(machine.uc.mem_read(BUFFER + 128, CAPACITY * 128)), bytes(CAPACITY * 128))

    def test_actor_source_and_worker_filters_reject_without_reservation(self):
        for site in self.sites:
            changes = []
            if site.get("actor"):
                changes += [("actor_pointer", BUFFER + 16, "Q", ACTOR + 0x100),
                            ("actor_id", ACTOR + 0x48, "I", 0x9876)]
            if site.get("parent"):
                changes.append(("source", PARENT + 0x94, "Q", 0xDEADBEEF))
            if site.get("worker"):
                changes.append(("vtable", WORKER, "Q", VTABLE + 8))
            for reason, address, format_, value in changes:
                with self.subTest(site=site["name"], reason=reason):
                    machine = self.machine(site)
                    machine.put(address, format_, value)
                    machine.run(self)
                    self.assertEqual(machine.get(BUFFER + 8, "I"), 0)
                    self.assertEqual(machine.get(BUFFER + 12, "I"), 0)
                    self.assertEqual(bytes(machine.uc.mem_read(BUFFER + 128, CAPACITY * 128)), bytes(CAPACITY * 128))

    def test_buff_source_is_accepted_only_by_parent_lifetime_sites(self):
        for site in (site for site in self.sites if site.get("parent")):
            with self.subTest(site=site["name"]):
                machine = self.machine(site)
                machine.uc.mem_write(PARENT + 0x94, b"CBRTBUF\0")
                machine.run(self)
                self.assertEqual(machine.get(BUFFER + 8, "I"), 0 if site["id"] == 3 else 1)

    def test_overflow_disarms_and_drops_without_overwriting_records(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                machine = self.machine(site)
                machine.put(BUFFER + 8, "I", CAPACITY)
                marker = bytes([0xA5]) * (CAPACITY * 128)
                machine.uc.mem_write(BUFFER + 128, marker)
                machine.run(self)
                self.assertEqual(machine.get(BUFFER, "I"), 0)
                self.assertEqual(machine.get(BUFFER + 8, "I"), CAPACITY + 1)
                self.assertEqual(machine.get(BUFFER + 12, "I"), 1)
                self.assertEqual(bytes(machine.uc.mem_read(BUFFER + 128, CAPACITY * 128)), marker)

    def test_records_capture_synthetic_fields_and_zero_absent_actor(self):
        for site in self.sites:
            with self.subTest(site=site["name"]):
                machine = self.machine(site)
                machine.run(self)
                record = BUFFER + 128
                expected = {0: site["id"], 4: 0, 8: 9001, 12: 90, 16: 0x4567, 120: 0xED7}
                if site.get("actor"):
                    expected.update({20: 0x1234, 100: -37, 104: 0xAABBCCDD, 108: 0x31, 112: 19})
                else:
                    expected.update({20: 0, 100: 0, 104: 0, 108: 0, 112: 0})
                if site.get("parent"):
                    expected.update({64: 4096, 68: 98, 72: 123456, 76: 123000})
                    self.assertEqual(bytes(machine.uc.mem_read(record + 56, 8)), b"CBRTREG\0")
                if site.get("worker"):
                    expected.update({80: 0x13579, 84: (11 << 16) | 2, 88: 999, 92: 3, 96: 5})
                if site["id"] == 7:
                    expected[68] = 17
                if site.get("elapsed"):
                    expected[116] = 7
                if site.get("list"):
                    expected[124] = 456
                for offset, value in expected.items():
                    self.assertEqual(machine.get(record + offset, "i" if value < 0 else "I"), value,
                                     f"record field +{offset:#x}")
                for offset, role, pointer in ((24, "actor", ACTOR), (32, "parent", PARENT),
                                              (40, "worker", WORKER), (48, "related", RELATED)):
                    self.assertEqual(machine.get(record + offset, "Q"), pointer if site.get(role) else 0)

    def test_active_stats_immunity_branch(self):
        for site in (site for site in self.sites if site.get("actor")):
            with self.subTest(site=site["name"]):
                machine = self.machine(site)
                machine.put(ACTOR + 0x4EA4, "I", 1)
                machine.run(self)
                self.assertEqual(machine.get(BUFFER + 128 + 112, "I"), 23)

    def test_postworker_body_preserves_conditional_zero_flag(self):
        site = next(site for site in self.sites if site["id"] == 6)
        for zero_flag in (0, 0x40):
            with self.subTest(zero_flag=bool(zero_flag)):
                machine = self.machine(site, flags=0x202 | zero_flag)
                machine.run(self)
                self.assertEqual(machine.uc.reg_read(x86.UC_X86_REG_EFLAGS) & 0x40, zero_flag)

    def test_pinned_executable_sites_have_whole_instructions_and_safe_replay(self):
        data = EXE.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), EXE_SHA256)
        pe = pefile.PE(data=data, fast_load=True)
        self.assertEqual(pe.FILE_HEADER.Machine, 0x8664)
        self.assertEqual(pe.FILE_HEADER.TimeDateStamp, 0x6A18D73D)
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoder.detail = True
        for site in self.sites:
            with self.subTest(site=site["name"]):
                expected = bytes.fromhex(site["bytes"])
                offset = pe.get_offset_from_rva(site["rva"])
                self.assertEqual(data[offset:offset + len(expected)], expected)
                instructions = list(decoder.disasm(expected, pe.OPTIONAL_HEADER.ImageBase + site["rva"]))
                self.assertEqual(sum(item.size for item in instructions), len(expected))
                if site["kind"] == "call":
                    self.assertEqual(len(instructions), 1)
                    self.assertEqual(instructions[0].mnemonic, "call")
                    replay = []
                elif site["kind"] == "branch":
                    self.assertIn(instructions[0].mnemonic, ("jne", "jnz"))
                    self.assertEqual(instructions[0].size, 2)
                    replay = instructions[1:]
                    self.assertEqual(sum(item.size for item in replay), 4)
                else:
                    replay = instructions
                for instruction in replay:
                    self.assertFalse(instruction.group(capstone.CS_GRP_JUMP))
                    self.assertFalse(instruction.group(capstone.CS_GRP_CALL))
                    self.assertFalse(any(operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
                                         for operand in instruction.operands))


if __name__ == "__main__":
    unittest.main()
