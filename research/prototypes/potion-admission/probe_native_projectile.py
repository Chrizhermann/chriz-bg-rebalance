"""Read-only BG2EE 2.7.3 instant-projectile ownership probe.

Copies pinned executable instructions into Unicorn; never starts the game or
loads EEex/native DLLs. Real Fire, OnArrival, DeliverEffects, AddEffect and scalar
destructors and linked-list operations execute against synthetic objects. Message
allocation, object lookup, sound/resource services and the queue are test doubles.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

SHA256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
BASE = 0x140000000
FIRE, ARRIVE, DELIVER, ADD = 0x231600, 0x233030, 0x22EFC0, 0x22A270
DESTROY, INSTANT_VTABLE = 0x2280F0, 0x59BFF0
PROJECTILE, EFFECTS, ACTOR = 0x200000000, 0x200001000, 0x300000000
META, NODES, MESSAGES, STACK = 0x400000000, 0x400002000, 0x400004000, 0x500000000
FAKE, RETURN = 0x600000000, 0x600000F00
VTABLES = {18: 0x591E48, 54: 0x592A50, 90: 0x593810}
TARGET_ID, OTHER_ID = 123, 456
ALLOWED_CODE = ((FIRE, 0x231616), (ARRIVE, 0x2330EC), (DELIVER, 0x22F334),
                (ADD, 0x22A283), (DESTROY, 0x228124), (0x227F20, 0x227FAD),
                (0x14C8E0, 0x14C925), (0x1A45A0, 0x1A45E5),
                (0x233320, 0x2333CE), (0x4075C0, 0x40760E),
                (0x407890, 0x407922), (0x407930, 0x407966), (0x407B40, 0x407B6A))
STUBS = {
    0x276700: "GetDeny: synthetic target or controlled lookup failure",
    0x4076F0: "CObList::Find: configurable projectile immunity",
    0x4F7A88: "operator new: deterministic, successful message allocation",
    0x204EC0: "AddMessage: records message bytes, does not run/serialize it",
    0x272420: "object-array removal: succeeds so native scalar destructor runs",
    0x1ECE40: "RemoveFromArea/base object cleanup",
    0x3FFB60: "empty sound resource comparison: no sound playback",
    0x3FD740: "string cleanup", 0x40D740: "sound cleanup",
    0x4073D0: "list destructor storage cleanup",
    0x45E690: "operator delete: records freed identity, does not unmap",
}


def require(value, message):
    if not value:
        raise AssertionError(message)


class Machine:
    def __init__(self, image, unicorn, registers, *, mode="normal", opcodes=(54, 90, 18)):
        self.reg, self.um = registers, unicorn
        self.u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        self.u.mem_map(BASE, (len(image) + 4095) & ~4095)
        self.u.mem_write(BASE, image)
        for start, size in ((PROJECTILE, 0x8000), (ACTOR, 0x6000),
                            (META, 0x10000), (STACK, 0x10000), (FAKE, 0x1000)):
            self.u.mem_map(start, size)
        self.u.mem_write(FAKE, b"\xc3" * 0x1000)
        self.events, self.freed, self.messages = Counter(), [], []
        self.effect_destroyed, self.visited, self.writes = [], [], []
        self.mode, self.next_message = mode, MESSAGES
        self.put(PROJECTILE, "Q", BASE + INSTANT_VTABLE)
        self.put(PROJECTILE + 0x60, "H", 1)
        # Constructor defaults: no linked visual objects, no extra-op61 flag.
        self.put(PROJECTILE + 0x70, "i", -1)
        self.put(PROJECTILE + 0x180, "i", -1)
        # Preallocated free nodes let native NewNode/AddTail execute without
        # invoking the unrelated CPlex allocator; actual pointer linkage runs.
        self.put(PROJECTILE + 0x78 + 0x20, "Q", NODES)
        for i in range(32):
            self.put(NODES + i * 0x20, "Q", NODES + (i + 1) * 0x20 if i < 31 else 0)
        self.put(BASE + 0x667548, "Q", META + 0x500)
        self.put(META + 0x500 + 0x1090, "Q", META + 0x800)
        self.put(ACTOR, "Q", META)
        self.put(META + 8, "Q", FAKE)
        self.put(ACTOR + 0x48, "I", TARGET_ID)
        self.effects = []
        self.original = {}
        for i, opcode in enumerate(opcodes):
            pointer = EFFECTS + i * 0x400
            self.effects.append(pointer)
            # Distinct nonzero payloads make accidental field rewrites visible.
            self.u.mem_write(pointer, bytes((j * 31 + i * 7) & 255 for j in range(0x160)))
            self.put(pointer, "Q", BASE + VTABLES[opcode])
            self.put(pointer + 8, "I", opcode)
            self.put(pointer + 0x14, "I", 2)
            self.original[pointer] = bytes(self.u.mem_read(pointer, 0x160))
        self.u.hook_add(unicorn.UC_HOOK_CODE, self.on_code)
        self.u.hook_add(unicorn.UC_HOOK_MEM_WRITE, self.on_write)

    def get(self, address, fmt):
        return struct.unpack("<" + fmt, self.u.mem_read(address, struct.calcsize("<" + fmt)))[0]

    def put(self, address, fmt, *values):
        self.u.mem_write(address, struct.pack("<" + fmt, *values))

    def read(self, name):
        return self.u.reg_read(getattr(self.reg, "UC_X86_REG_" + name))

    def write(self, name, value):
        self.u.reg_write(getattr(self.reg, "UC_X86_REG_" + name), value)

    def ret(self, value=None):
        if value is not None:
            self.write("RAX", value)
        sp = self.read("RSP")
        self.write("RIP", self.get(sp, "Q"))
        self.write("RSP", sp + 8)

    def on_write(self, u, access, address, size, value, _):
        if any(pointer <= address < pointer + 0x160 for pointer in self.effects):
            self.writes.append((address, size, value))

    def on_code(self, u, address, size, _):
        if address == RETURN:
            self.returned = True
            u.emu_stop()
            return
        if address == FAKE:
            self.events["GetObjectType"] += 1
            self.ret(0 if self.mode == "non_sprite" else self.get(BASE + 0x59971F, "B"))
            return
        rva = address - BASE
        self.visited.append(rva)
        if rva in (0x14C8E0, 0x1A45A0):
            self.effect_destroyed.append(self.read("RCX"))
        if rva not in STUBS:
            require(any(lo <= rva < hi for lo, hi in ALLOWED_CODE),
                    f"unexpected native instruction/copy/service at {rva:X}")
            return
        self.events[STUBS[rva].split(":")[0]] += 1
        if rva == 0x276700:
            require(self.read("RCX") & 0xFFFFFFFF in (TARGET_ID, OTHER_ID), "unexpected lookup ID")
            self.put(self.read("RDX"), "Q", ACTOR)
            self.ret(1 if self.mode == "missing_target" else 0)
        elif rva == 0x4076F0:
            self.ret(NODES + 0x100 if self.mode == "projectile_immune" else 0)
        elif rva == 0x4F7A88:
            require(self.read("RCX") == 0x20, "unexpected allocation; extra projectile behavior")
            pointer = self.next_message
            self.next_message += 0x40
            self.ret(pointer)
        elif rva == 0x204EC0:
            pointer = self.read("RDX")
            require(pointer != 0 and self.read("R8") == 0, "unexpected queue invocation")
            self.messages.append({"pointer": pointer, "effect": self.get(pointer + 0x10, "Q"),
                                  "target": self.get(pointer + 8, "I"),
                                  "source": self.get(pointer + 0xC, "I"),
                                  "no_save": self.get(pointer + 0x1A, "B"),
                                  "flags": self.get(pointer + 0x18, "H")})
            self.ret(1)
        elif rva == 0x45E690:
            self.freed.append(self.read("RCX"))
            self.ret()
        else:
            self.ret(0)

    def run(self, rva, rcx, rdx=0, r8=0, r9=0):
        sp = STACK + 0x8008
        self.put(sp, "Q", RETURN)
        for name, value in (("RSP", sp), ("RCX", rcx), ("RDX", rdx), ("R8", r8), ("R9", r9)):
            self.write(name, value)
        self.returned = False
        self.u.emu_start(BASE + rva, 0, count=30000)
        require(self.returned, "native routine did not return within instruction bound")

    def attach(self):
        for pointer in self.effects:
            self.run(ADD, PROJECTILE, pointer)
            before = bytearray(self.original[pointer])
            struct.pack_into("<I", before, 0xA0, 1)
            require(bytes(self.u.mem_read(pointer, 0x160)) == bytes(before),
                    "native AddEffect changed more than projectile type")
        require(self.get(PROJECTILE + 0x80, "Q") == NODES, "incorrect fixture/list head")
        self.attached = {p: bytes(self.u.mem_read(p, 0x160)) for p in self.effects}
        self.writes.clear()


def verify_source(image):
    getq = lambda rva: struct.unpack_from("<Q", image, rva)[0] - BASE
    require(image[0x22EEBC] == 0 and struct.unpack_from("<I", image, 0x22EDDC)[0] == 0x22BFBC,
            "ID1 decode dispatch changed")
    require(image[0x22BFE1:0x22BFE6].hex() == "e82aa9ffff", "ID1 base constructor changed")
    require(0x22BFED + struct.unpack_from("<i", image, 0x22BFE9)[0] == INSTANT_VTABLE,
            "ID1 decoded vtable changed")
    for slot, rva in ((0, DESTROY), (0x90, 0x1ECE40), (0xD0, FIRE), (0xD8, ARRIVE), (0xE8, DELIVER)):
        require(getq(INSTANT_VTABLE + slot) == rva, f"instant vtable slot {slot:X} changed")
    require(image[0x226AF2:0x226AF9].hex() == "4589af88010000", "constructor flag initialization changed")
    require(image[0x226961:0x226964].hex() == "4533ed", "constructor zero register changed")


def run_probes(image, unicorn, registers):
    verify_source(image)
    results = []
    for mode in ("normal", "projectile_immune", "missing_target", "non_sprite", "cancel_before_fire"):
        m = Machine(image, unicorn, registers, mode=mode)
        m.attach()
        if mode == "cancel_before_fire":
            m.run(DESTROY, PROJECTILE, 1)
        else:
            m.run(FIRE, PROJECTILE, META + 0x900, TARGET_ID, TARGET_ID)
            require(m.get(PROJECTILE + 0x68, "I") == TARGET_ID and
                    m.get(PROJECTILE + 0x6C, "I") == TARGET_ID, "Fire changed supplied source/target")
            require(ARRIVE in m.visited and DELIVER in m.visited, "instant virtual dispatch not exercised")
        require(PROJECTILE in m.freed, "native projectile destructor did not free projectile")
        require(m.get(PROJECTILE + 0x80, "Q") == 0, "projectile kept effect-list ownership")
        if mode == "normal":
            require([message["effect"] for message in m.messages] == m.effects, "copy/reorder in transfer")
            require(all(message["source"] == message["target"] == TARGET_ID and
                        message["no_save"] == 0 and message["flags"] == 1 for message in m.messages),
                    "message target or admission flags changed")
            require(not m.effect_destroyed and all(p not in m.freed for p in m.effects),
                    "projectile destroyed transferred effect")
            require(not m.writes and all(bytes(m.u.mem_read(p, 0x160)) == m.attached[p] for p in m.effects),
                    "Fire/delivery rewrote native effect fields")
        else:
            require(not m.messages, "cancelled effect was queued")
            require(m.effect_destroyed == m.effects and all(m.freed.count(p) == 1 for p in m.effects),
                    "cancelled original effect not destroyed exactly once")
        results.append({"case": mode, "queued_originals": len(m.messages),
                        "destroyed_originals": len(m.effect_destroyed),
                        "native_instructions_and_stubs": len(m.visited)})

    # Negative control: ID1 does not itself force source == selected target.
    # Runtime admission must still validate the actual drinker identity.
    m = Machine(image, unicorn, registers, opcodes=(54,))
    m.attach()
    m.run(FIRE, PROJECTILE, META + 0x900, TARGET_ID, OTHER_ID)
    require(m.messages[0]["source"] == TARGET_ID and m.messages[0]["target"] == OTHER_ID,
            "different-target negative control no longer reproduces")
    results.append({"case": "different_selected_target", "runtime_self_guard_required": True})
    return {"cases": results, "stubs": {f"{rva:X}": text for rva, text in STUBS.items()},
            "limitations": [
                "Unicorn executes copied native instructions, not a running game or EEex DLL.",
                "Object lookup, message allocation, queue scheduling, immunity lookup and audio/base cleanup are synthetic.",
                "Native AddTail/NewNode/RemoveAll execute using preallocated synthetic free nodes; CPlex allocation is not exercised.",
                "Effect objects use native vtables but synthetic field payloads; no CheckAdd/Apply or save/load occurs here.",
                "UseItem/FireItem full action target selection is not emulated; the supplied self target and a different-target negative control are tested.",
                "Default instant fields only: no linked VVC objects or flag-generated extra op61. Source review shows the extra op61 uses a distinct new effect.",
                "EEex type/projectile/effect mutators are not executed. Actual class and native effect fingerprint require runtime guards.",
                "Other projectile classes, copying, bounce, area routes, allocation failure and exceptional native unwinding remain unproved.",
            ]}


def main():
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
    digest = hashlib.sha256(binary).hexdigest()
    require(digest == SHA256, f"unsupported executable hash: {digest}")
    pe = pefile.PE(data=binary)
    require(pe.OPTIONAL_HEADER.ImageBase == BASE, "unexpected PE image base")
    result = run_probes(pe.get_memory_mapped_image(), unicorn, registers)
    result.update(status="passed", executable_sha256=digest,
                  scope="instant projectile original-pointer transfer and native cancellation, offline only")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
