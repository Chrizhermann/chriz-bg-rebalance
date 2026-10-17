"""Bounded offline BG2EE 2.7.3 admission/expiry probe; never starts the game.

Requires pefile and unicorn. Supply --python-libs for an existing dependency
directory if needed. The pinned executable is read, hashed, and copied into
Unicorn memory. No process, save, installed resource, or executable is modified.

Native instructions cover AddEffect, CheckAdd control flow, ResolveEffect,
timing conversion, and additive op90/op92. Admission predicates and engine
services listed in STUBS are deliberately substituted. The candidate callback
is a Python test double at the proposed native boundary, NOT an EEex hook.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path


SHA256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
BASE = 0x140000000
ADD_EFFECT = 0x387310
CHECK_ADD = 0x1CC6C0
AFTER_CHECK_SAVE = 0x1CD1AF
REJECT = 0x1CC9A5
RESOLVE = 0x1E83D0
APPLY = {90: 0x1C6940, 92: 0x1C6B00}
BONUS = {90: 0x2AA6, 92: 0x2AAC}

EFFECT = 0x200000000
ACTIVE = EFFECT + 0x1000
OTHER = EFFECT + 0x2000
ACTOR = 0x300000000
STACK = 0x400000000
META = 0x500000000
EFFECT_VTABLE = META
ACTOR_VTABLE = META + 0x100
AI_TYPE = META + 0x200
CHITIN = META + 0x1000
GAME = META + 0x3000
NODES = META + 0x8000
FAKE_CALLS = 0x600000000
RETURN = FAKE_CALLS + 0xF00
LISTS = (0x49B0, 0x4A00)

# Pin the exact entry and success/failure branches, not just the PE version text.
SIGNATURES = {
    ADD_EFFECT: "488974241848897c2420488954241041564883ec50",
    0x1CC733: "0fb608663b4f2c0f8765020000663b4f2e0f825b020000",
    0x1CD1A4: "ff503885c00f84f6f7ffff8b47243d00100000",
    REJECT: "33c0488b8d200100004833cce8eaad3200",
    0x38740B: "85c0753585f675194885db",
    0x1E84B6: "c7432400100000c744243888888808",
}

STUBS = {
    0x38F8D0: "CheckSevenEyes: no replacement",
    0x1F8FD0: "secondary-decrementing immunity: absent",
    0x1F8C90: "resource immunity: absent",
    0x38BAB0: "CheckEffect: configurable acceptance",
    0x1F8E30: "opcode immunity: configurable presence",
    0x1CD330: "CheckSave: configurable result (save/MR arithmetic NOT emulated)",
    0x4F77A0: "security-cookie check",
    0x14F290: "derived-stat snapshot assignment",
    0x1F8910: "immunity snapshot comparison: equal",
    0x4075C0: "list AddTail: records invocation, does not allocate",
    0x3AB9D0: "ProcessEffectList: records invocation, no full rebuild",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def deadline(now: int, duration: int, timing: int) -> int:
    """Candidate arithmetic, checked against the copied native conversion below."""
    if timing == 0:
        signed = struct.unpack("<i", struct.pack("<I", duration))[0]
        return (now + min(signed, 0x08888888) * 15) & 0xFFFFFFFF
    if timing == 10:
        return (now + duration) & 0xFFFFFFFF
    if timing == 4096:
        return duration
    raise ValueError("Only already-absolute or immediate finite timing is probed")


class Machine:
    """Synthetic objects plus real mapped instructions, fresh for every case."""

    def __init__(self, image: bytes, uc_module, registers, opcode: int = 90):
        self.uc_module = uc_module
        self.reg = registers
        self.u = uc_module.Uc(uc_module.UC_ARCH_X86, uc_module.UC_MODE_64)
        self.u.mem_map(BASE, (len(image) + 4095) & ~4095)
        self.u.mem_write(BASE, image)
        for address, size in ((EFFECT, 0x4000), (ACTOR, 0x6000),
                              (STACK, 0x8000), (META, 0x10000),
                              (FAKE_CALLS, 0x1000)):
            self.u.mem_map(address, size)
        self.u.mem_write(FAKE_CALLS, b"\xC3" * 0x1000)
        self.events = Counter()
        self.gate = "accept"
        self.refresh = False
        self.opcode = opcode
        self.callback_writes: list[tuple[int, int, int]] = []
        self.visited: list[int] = []
        self.check_add_result = None
        self.returned = False
        self.active_before_callback = None
        self.active_after_callback = None
        self.list_before_callback = None
        self.list_after_callback = None
        self.callback_candidate = None
        self.u.hook_add(uc_module.UC_HOOK_CODE, self.on_code)
        self.u.hook_add(uc_module.UC_HOOK_MEM_WRITE, self.on_write)

        # Synthetic vtables retain native ResolveEffect/ApplyEffect addresses.
        for slot, function in ((0, FAKE_CALLS), (0x10, BASE + APPLY[opcode]),
                               (0x18, BASE + RESOLVE), (0x20, FAKE_CALLS + 0x10),
                               (0x38, BASE + 0x1CD330), (0x40, FAKE_CALLS + 0x20),
                               (0x48, FAKE_CALLS + 0x30), (0x50, FAKE_CALLS + 0x40)):
            self.put(EFFECT_VTABLE + slot, "Q", function)
        self.put(ACTOR_VTABLE + 0x20, "Q", FAKE_CALLS + 0x50)
        self.put(ACTOR, "Q", ACTOR_VTABLE)
        self.put(ACTOR + 0x48, "I", 123)
        self.put(ACTOR + 0x4EA4, "I", 1)
        self.put(ACTOR + 0x4C86, "B", 50)  # The native probability roll argument.
        self.put(AI_TYPE + 8, "B", 0xFE)  # Avoid synthetic "anything" type shortcut.
        self.put(BASE + 0x667548, "Q", CHITIN)
        self.put(CHITIN + 0x1090, "Q", GAME)
        self.put(GAME + 0x3FA0, "I", 1000)
        self.put(GAME + 0x3FA4, "B", 0)
        for address in (EFFECT, ACTIVE, OTHER):
            self.make_effect(address, opcode)
        self.put(ACTIVE + 0x24, "II", 4096, 1450)
        self.put(ACTIVE + 0xCC, "I", 0)
        self.put(OTHER + 0x1C, "I", 21)  # Different benefit must not be refreshed.
        self.seed_lists()

    def put(self, address: int, fmt: str, *values: int) -> None:
        self.u.mem_write(address, struct.pack("<" + fmt, *values))

    def get(self, address: int, fmt: str) -> int:
        return struct.unpack("<" + fmt, self.u.mem_read(address, struct.calcsize(fmt)))[0]

    def read(self, address: int, length: int) -> bytes:
        return bytes(self.u.mem_read(address, length))

    def reg_read(self, name: str) -> int:
        return self.u.reg_read(getattr(self.reg, "UC_X86_REG_" + name))

    def reg_write(self, name: str, value: int) -> None:
        self.u.reg_write(getattr(self.reg, "UC_X86_REG_" + name), value)

    def make_effect(self, address: int, opcode: int) -> None:
        self.put(address, "Q", EFFECT_VTABLE)
        self.put(address + 0x10, "IIIIIII", opcode, 1, 2, 20, 0, 0, 60)
        self.put(address + 0x2C, "HH", 100, 0)
        self.put(address + 0x5C, "I", 9)
        self.put(address + 0x90, "I", 2)
        self.u.mem_write(address + 0x94, b"POTN36\0\0")
        self.put(address + 0xC8, "II", 10, 1)
        self.put(address + 0x110, "I", 123)
        self.put(address + 0x11C, "I", 60)
        self.put(address + 0x150, "I", 123)

    def seed_lists(self, reverse: bool = False) -> None:
        # CGameEffectList derives from CObList: head+8; node next+0/data+0x10.
        ordered = (ACTIVE, OTHER) if reverse else (OTHER, ACTIVE)
        for index, pointer in enumerate(ordered):
            node = NODES + index * 0x30
            following = NODES + (index + 1) * 0x30 if index == 0 else 0
            previous = NODES if index else 0
            self.put(node, "QQQ", following, previous, pointer)
        self.put(ACTOR + LISTS[1] + 8, "QQI", NODES, NODES + 0x30, 2)
        # Nonzero native iterator cursors prove read traversal does not repoint them.
        self.put(ACTOR + LISTS[1] + 0x38, "QQ", NODES + 0x30, NODES)

    def iter_effects(self):
        """Read-only bounded CObList traversal, not native list insertion/removal."""
        for offset in LISTS:
            node = self.get(ACTOR + offset + 8, "Q")
            seen = set()
            while node:
                require(node not in seen and len(seen) < 32, "malformed synthetic list")
                seen.add(node)
                yield self.get(node + 0x10, "Q")
                node = self.get(node, "Q")

    def list_snapshot(self) -> bytes:
        return self.read(ACTOR + LISTS[0], 0xA0) + self.read(NODES, 0x60)

    def ret(self, value: int = 0) -> None:
        rsp = self.reg_read("RSP")
        destination = self.get(rsp, "Q")
        self.reg_write("RAX", value)
        self.reg_write("RSP", rsp + 8)
        self.reg_write("RIP", destination)

    def on_write(self, uc, access, address, size, value, _data):
        # Native writes in the existing active object's body are separately audited.
        if ACTIVE <= address < ACTIVE + 0x158:
            self.events["native_active_write"] += 1

    def candidate_callback(self) -> None:
        require(self.reg_read("RDI") == EFFECT, "success ABI effect register changed")
        require(self.reg_read("R14") == ACTOR, "success ABI sprite register changed")
        self.events["candidate_hook"] += 1
        if not self.refresh:
            return
        # Identity/classification is deliberately NOT implemented here. The selected
        # synthetic pointer represents one exact match supplied by the lead's manifest.
        self.active_before_callback = self.read(ACTIVE, 0x158)
        self.list_before_callback = self.list_snapshot()
        matches = [p for p in self.iter_effects() if p == ACTIVE]
        require(matches == [ACTIVE], "test fixture must identify one exact active effect")
        now = self.get(GAME + 0x3FA0, "I")
        require(self.get(ACTIVE + 0x24, "I") == 4096, "active timing must be absolute")
        require(self.get(ACTIVE + 0x28, "I") > now, "expired record must not be revived")
        require(self.get(ACTIVE + 0x114, "I") == 0, "done record must not be revived")
        new_end = deadline(now, self.get(EFFECT + 0x28, "I"),
                           self.get(EFFECT + 0x24, "I"))
        self.put(ACTIVE + 0x28, "I", new_end)
        self.callback_writes.append((ACTIVE + 0x28, 4, new_end))
        self.active_after_callback = self.read(ACTIVE, 0x158)
        self.list_after_callback = self.list_snapshot()
        self.callback_candidate = new_end
        self.reg_write("RIP", BASE + REJECT)

    def on_code(self, uc, address, size, _data):
        self.visited.append(address)
        self.visited = self.visited[-24:]
        if address == RETURN:
            self.returned = True
            self.u.emu_stop()
            return
        rva = address - BASE
        if rva == AFTER_CHECK_SAVE:
            self.candidate_callback()
        if rva == 0x38740B:
            self.check_add_result = self.reg_read("EAX")
        if rva == RESOLVE:
            key = "resolve_active" if self.reg_read("RCX") == ACTIVE else "resolve_incoming"
            self.events[key] += 1
        if rva == APPLY[self.opcode]:
            key = "apply_active" if self.reg_read("RCX") == ACTIVE else "apply_incoming"
            self.events[key] += 1
        if rva in (0x1E7710, 0x407970, 0x1E7AD0):
            raise AssertionError("unexpected native effect/list removal")
        if rva in STUBS:
            self.events[STUBS[rva]] += 1
            result = 0
            if rva == 0x38BAB0:
                result = int(self.gate != "check_effect")
            elif rva == 0x1F8E30:
                result = int(self.gate == "opcode_immunity")
            elif rva == 0x1CD330:
                result = int(self.gate != "save")
            elif rva == 0x1F8910:
                result = 1
            elif rva == 0x4F77A0:
                # MSVC's cookie helper preserves the pending function return value.
                result = self.reg_read("RAX")
            self.ret(result)
        elif FAKE_CALLS <= address < FAKE_CALLS + 0x100:
            names = {0: "destroy_incoming", 0x10: "on_add", 0x20: "uses_dice",
                     0x30: "display_string", 0x40: "on_remove", 0x50: "get_ai_type"}
            name = names[address - FAKE_CALLS]
            if name == "destroy_incoming":
                require(self.reg_read("RCX") == EFFECT, "active object destroyed")
            self.events[name] += 1
            self.ret(AI_TYPE if name == "get_ai_type" else int(name == "uses_dice"))

    def run(self, rva: int, *arguments: int) -> None:
        self.returned = False
        rsp = STACK + 0x6000 - 8
        self.put(rsp, "Q", RETURN)
        for index, value in enumerate(arguments[:4]):
            self.reg_write(("RCX", "RDX", "R8", "R9")[index], value)
        for index, value in enumerate(arguments[4:]):
            self.put(rsp + 0x28 + index * 8, "Q", value)
        self.reg_write("RSP", rsp)
        try:
            self.u.emu_start(BASE + rva, RETURN + 1, count=10000)
        except self.uc_module.UcError as exc:
            recent = ", ".join(f"{address - BASE:X}" for address in self.visited)
            raise RuntimeError(f"{exc}; RIP={self.reg_read('RIP'):X}; recent RVAs={recent}") from exc
        require(self.returned, "instruction bound exceeded or native function did not return")


def run_probes(image: bytes, unicorn, registers) -> dict:
    cases = []
    for opcode in (90, 92):
        for gate in ("accept", "probability_high", "probability_low",
                     "opcode_immunity", "check_effect", "save"):
            p = Machine(image, unicorn, registers, opcode)
            p.gate = gate
            p.refresh = True
            if gate == "probability_high":
                p.put(EFFECT + 0x2C, "H", 49)
            elif gate == "probability_low":
                p.put(EFFECT + 0x2E, "H", 51)
            p.put(ACTOR + BONUS[opcode], "H", 20)
            old = p.read(ACTIVE, 0x158)
            before_nodes = p.list_snapshot()
            p.run(ADD_EFFECT, ACTOR, EFFECT, 1, 0, 1)
            require(p.check_add_result == 0, f"{gate}: expected native rejection")
            require(p.events["candidate_hook"] == int(gate == "accept"),
                    f"{gate}: failure incorrectly reached candidate callback")
            expected_save_calls = int(gate in ("accept", "save"))
            require(p.events[STUBS[0x1CD330]] == expected_save_calls,
                    f"{gate}: CheckSave called more than once or after earlier rejection")
            for event in ("on_add", "display_string", "resolve_incoming", "apply_incoming", "on_remove"):
                require(p.events[event] == 0, f"{gate}: unexpected {event}")
            require(p.events["destroy_incoming"] == 1, "caller must dispose rejected new effect")
            require(p.events["native_active_write"] == 0, "native code wrote old active effect")
            require(p.get(ACTOR + BONUS[opcode], "H") == 20, "duplicate changed skill bonus")
            require(p.list_snapshot() == before_nodes, "rejection changed list or iterator metadata")
            expected = bytearray(old)
            if gate == "accept":
                struct.pack_into("<I", expected, 0x28, 1900)
                require(p.callback_writes == [(ACTIVE + 0x28, 4, 1900)], "unexpected callback write")
            else:
                require(not p.callback_writes, "failed admission refreshed active effect")
            require(p.read(ACTIVE, 0x158) == expected, "unowned active effect bytes changed")
            cases.append({"opcode": opcode, "gate": gate,
                          "hook_calls": p.events["candidate_hook"],
                          "old_expiry_after": p.get(ACTIVE + 0x28, "I"),
                          "incoming_destroyed": p.events["destroy_incoming"]})

        # Baseline proves the success continuation really reaches native application.
        p = Machine(image, unicorn, registers, opcode)
        p.run(ADD_EFFECT, ACTOR, EFFECT, 1, 0, 1)
        require(p.check_add_result == 1, "unmodified accepted effect should succeed")
        require(p.events["on_add"] == p.events["display_string"] == 1, "baseline callbacks missing")
        require(p.events["apply_incoming"] == 1, "baseline native opcode did not run")
        require(p.get(ACTOR + BONUS[opcode], "H") == 20, "native additive benefit wrong")
        require(p.get(EFFECT + 0x24, "I") == 4096 and p.get(EFFECT + 0x28, "I") == 1900,
                "baseline timing conversion wrong")

        # Refresh creates no second effect/application. Revisit the old object at its
        # former and new deadlines with a modelled fresh derived-stat accumulator.
        p = Machine(image, unicorn, registers, opcode)
        p.refresh = True
        p.seed_lists(reverse=True)
        p.run(ADD_EFFECT, ACTOR, EFFECT, 1, 0, 1)
        p.put(GAME + 0x3FA0, "I", 1450)
        p.put(ACTOR + BONUS[opcode], "H", 0)
        p.run(RESOLVE, ACTIVE, ACTOR)
        require(p.get(ACTOR + BONUS[opcode], "H") == 20, "old record expired before new deadline")
        p.put(GAME + 0x3FA0, "I", 1900)
        p.put(ACTOR + BONUS[opcode], "H", 0)
        before = p.events["apply_active"]
        p.run(RESOLVE, ACTIVE, ACTOR)
        require(p.get(ACTIVE + 0x114, "I") == 1, "absolute expiry is not inclusive")
        require(p.events["apply_active"] == before, "expired old record reapplied")
        cases.append({"opcode": opcode, "gate": "reordered_list_expiry_boundary",
                      "active_apply_calls": p.events["apply_active"]})

    conversions = []
    for timing, duration, now in ((0, 60, 1000), (10, 31, 1000), (0, 0, 1000),
                                 (0, 0x7FFFFFFF, 1000), (0, 0xFFFFFFFF, 1000),
                                 (10, 100, 0xFFFFFFF0), (4096, 1900, 1000)):
        p = Machine(image, unicorn, registers)
        p.put(EFFECT + 0x24, "II", timing, duration)
        p.put(GAME + 0x3FA0, "I", now)
        before = p.read(EFFECT, 0x158)
        p.run(RESOLVE, EFFECT, ACTOR)
        actual = p.get(EFFECT + 0x28, "I")
        require(actual == deadline(now, duration, timing), "candidate/native deadline mismatch")
        require(p.get(EFFECT + 0x24, "I") == 4096, "native did not normalize timing")
        # Native op90 may write Done; timing conversion itself must not rewrite origin.
        for lo, hi in ((0x90, 0xD4), (0x110, 0x114), (0x11C, 0x120), (0x150, 0x154)):
            require(p.read(EFFECT + lo, hi - lo) == before[lo:hi], "native origin field changed")
        conversions.append({"timing_in": timing, "duration_in": duration,
                            "world_time": now, "absolute_expiry": actual})

    # Negative control: callers requesting noSave can override native rejection.
    # Such callers are outside this candidate's proven rejection contract.
    p = Machine(image, unicorn, registers)
    p.refresh = True
    p.put(ACTOR + BONUS[90], "H", 20)
    p.run(ADD_EFFECT, ACTOR, EFFECT, 1, 1, 1)
    require(p.check_add_result == 0 and p.events["apply_incoming"] == 1,
            "noSave override negative control no longer reproduces")
    require(p.events["candidate_hook"] == 1 and p.get(ACTOR + BONUS[90], "H") == 40,
            "noSave=true must demonstrate the duplicate application hazard")
    return {"admission_cases": cases, "native_timing_cases": conversions,
            "no_save_true_bypasses_rejection": True,
            "stubs": {f"{rva:X}": description for rva, description in STUBS.items()},
            "limitations": [
                "Python callback test double; no EEex-generated trampoline installed or executed.",
                "Immunity, CheckEffect and CheckSave predicates return controlled results; their internal correctness is not tested.",
                "List allocation, full derived-stat rebuilding, Seven Eyes and engine services are stubbed.",
                "Exact active pointer is supplied by fixture; no production manifest matching or dose correlation is implemented.",
                "Read-only synthetic CObList traversal and byte preservation do not prove threaded/native lifetime safety.",
                "No live game, native EEex callback reentrancy, persistence, HP/CON/regen or linked EFF acceptance.",
            ]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    import unicorn.x86_const as registers

    binary = args.exe.read_bytes()
    actual_hash = hashlib.sha256(binary).hexdigest()
    require(actual_hash == SHA256, f"unsupported executable hash: {actual_hash}")
    pe = pefile.PE(data=binary)
    require(pe.OPTIONAL_HEADER.ImageBase == BASE, "unexpected PE image base")
    image = pe.get_memory_mapped_image()
    for rva, value in SIGNATURES.items():
        expected = bytes.fromhex(value)
        require(image[rva:rva + len(expected)] == expected, f"signature mismatch at {rva:X}")
    result = run_probes(image, unicorn, registers)
    result.update({"status": "passed", "executable_sha256": actual_hash,
                   "candidate_rva": f"{AFTER_CHECK_SAVE:X}",
                   "scope": "copied native instructions with explicit synthetic predicates/services"})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
