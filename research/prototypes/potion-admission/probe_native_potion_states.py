"""Offline finite state/setter and native morale-cure classification evidence.

Pinned original Apply/Resolve instructions, synthetic actors and baseline resets.
No game process, resource writes, installer, save or generated hook execution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exe", type=Path, required=True)
parser.add_argument("--python-libs", type=Path)
args = parser.parse_args()
if args.python_libs:
    sys.path.insert(0, str(args.python_libs))
import pefile, unicorn
from unicorn import x86_const
import probe_native_admission as n
from probe_native_potion_stats import StatsMachine, vtable_evidence

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256,
          "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
CLASSES = {23: (0x1A0CC0, 0x1BA440), 63: (0x1A06C0, 0x1B7440),
           76: (0x19FB60, 0x1B3B30), 106: (0x1A0D00, 0x1BA520),
           282: (0x1A22C0, 0x1C4230)}
n.APPLY.update({op: spec[1] for op, spec in CLASSES.items()})
results = []


def machine(op, amount, mode, special=0):
    lifecycle = vtable_evidence(image, CLASSES[op][0])
    p = StatsMachine(image, unicorn, x86_const, op)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0xCC, "I", 1)
    p.put(n.ACTIVE + 0x1C, "iI", amount, mode)
    p.put(n.ACTIVE + 0x48, "I", special)
    return p, lifecycle


def stable_rebuilds(p, reset, check):
    original = p.read(n.ACTIVE, 0x180)
    p.put(n.ACTIVE + 0x28, "I", 1900)
    expected = bytearray(original)
    struct.pack_into("<I", expected, 0x28, 1900)
    for now in (1000, 1450, 1501, 1899):
        p.put(n.GAME + 0x3FA0, "I", now)
        reset()
        for _ in range(2):  # Repeat without a derived-stat reset must not accumulate.
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            check()
            n.require(p.read(n.ACTIVE, 0x180) == expected, "original effect fields changed")
    count = p.events["apply_active"]
    p.put(n.GAME + 0x3FA0, "I", 1900)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.events["apply_active"] == count, "effect applied at new expiry")


for op in (63, 76):
    for amount, mode, special in ((0, 0, 0), (7, 3, 9), (-1, 0xFFFFFFFF, 1)):
        p, lifecycle = machine(op, amount, mode, special)
        def reset():
            p.put(n.ACTOR + 0x1120, "I", 0x4000)
            p.put(n.ACTOR + 0x1172, "h", 20)
        def check():
            flag = 0x20000 if op == 63 else 0x100000
            n.require(p.get(n.ACTOR + 0x1120, "I") == 0x4000 | flag, "wrong state bits")
            n.require(p.get(n.ACTOR + 0x1172, "h") == (20 if op == 63 else 3), "wrong INT")
        stable_rebuilds(p, reset, check)
        results.append(dict(opcode=op, amount=amount, mode=mode, special=special,
                            stable=True, lifecycle=lifecycle))

for index in (0, 4, 8, 44, 45, 0xFFFFFFFF):
    for amount in (-1, 0, 1, 2147483647):
        p, lifecycle = machine(282, amount, index)
        before = bytes([0x55]) * (45 * 4)
        expected = bytearray(before)
        if index < 45:
            struct.pack_into("<i", expected, index * 4, amount)
        def reset():
            p.u.mem_write(n.ACTOR + 0x1354, before)
        def check():
            n.require(p.read(n.ACTOR + 0x1354, len(before)) == expected, "scripting state bounds/value mismatch")
        stable_rebuilds(p, reset, check)
        results.append(dict(opcode=282, amount=amount, index=index, stable=True, lifecycle=lifecycle))

for amount in (-2147483648, -1, 0, 1, 14, 20, 21, 2147483647):
    for stats_current in (0, 1):
        for panic in (False, True):
            p, lifecycle = machine(106, amount, 1)
            p.put(n.ACTOR + 0x4EA4, "I", stats_current)
            chosen = 0x1120 if stats_current else 0x1DC8
            other = 0x1DC8 if stats_current else 0x1120
            p.put(n.ACTOR + chosen, "I", 2 if panic else 0)
            p.put(n.ACTOR + other, "I", 0 if panic else 2)  # Prove actual stats selector.
            def reset():
                p.put(n.ACTOR + 0x1188, "I", 17)
            def check():
                expected = 17 if panic else max(0, min(20, amount))
                n.require(p.get(n.ACTOR + 0x1188, "I") == expected, "morale-break setter mismatch")
            stable_rebuilds(p, reset, check)
            results.append(dict(opcode=106, mode=1, amount=amount, panic=panic,
                                stats_current=stats_current, stable=True, lifecycle=lifecycle))

# Special0 is deliberately NOT a stable timed bonus: native rewrites it as a
# one-shot morale cure. Preserve those writes and do not manufacture ownership.
for amount in (-1, 0, 2147483647):
    for mode in (0, 2, 0xFFFFFFFF):
        for stats_current in (0, 1):
            for panic in (False, True):
                p, lifecycle = machine(23, amount, mode)
                p.put(n.ACTOR + 0x4EA4, "I", stats_current)
                chosen = 0x1120 if stats_current else 0x1DC8
                other = 0x1DC8 if stats_current else 0x1120
                p.put(n.ACTOR + chosen, "I", 2 if panic else 0)
                p.put(n.ACTOR + other, "I", 0 if panic else 2)
                p.put(n.ACTOR + 0x797, "B", 5)
                expected = bytearray(p.read(n.ACTIVE, 0x180))
                struct.pack_into("<iI", expected, 0x1C, 10, 1)
                struct.pack_into("<I", expected, 0x114, 1)
                p.run(n.APPLY[23], n.ACTIVE, n.ACTOR)
                n.require(p.read(n.ACTIVE, 0x180) == expected, "native morale-cure field changes differ")
                n.require(p.get(n.ACTOR + 0x797, "B") == (5 if panic else 10), "native morale-cure result differs")
                results.append(dict(opcode=23, special=0, original_amount=amount, original_mode=mode,
                                    panic=panic, stats_current=stats_current, done=True, lifecycle=lifecycle))

# Explicit negative control: Special-nonzero mode0 is a repeated base-stat write.
p, lifecycle = machine(23, 1, 0, 1)
p.put(n.ACTOR + 0x797, "B", 10)
for expected in (11, 12):
    p.run(n.APPLY[23], n.ACTIVE, n.ACTOR)
    n.require(p.get(n.ACTOR + 0x797, "B") == expected, "nonzero-Special morale counterexample missing")
results.append(dict(opcode=23, special=1, mode=0, outputs=[11, 12], unsupported=True))

# Ordinary invisibility's auxiliary message is also executed, rather than
# assumed harmless from its name. Mode1's separate effect-copy route is excluded.
n.APPLY[20] = 0x1B76D0
ctor = 0x1A0780
n.require(image[ctor + 0x16:ctor + 0x1E] == bytes.fromhex("C744242800000000"), "invisibility UsesDice changed")
vt = ctor + 0x2F + struct.unpack_from("<i", image, ctor + 0x2B)[0]
n.require({slot: struct.unpack_from("<Q", image, vt + slot)[0] - n.BASE for slot in (0, 0x28, 0x50)}
          == {0: 0x14C8E0, 0x28: 0x1E5BA0, 0x50: 0x1E1E0}, "invisibility lifecycle changed")


class InvisibleMachine(StatsMachine):
    def __init__(self):
        self.allocation = 0x720000000
        self.messages = []
        super().__init__(image, unicorn, x86_const, 20)
        self.u.mem_map(self.allocation, 0x10000)
        self.put(n.ACTOR_VTABLE + 8, "Q", n.FAKE_CALLS + 0x900)
        self.put(n.EFFECT_VTABLE + 0x28, "Q", n.BASE + 0x1E5BA0)

    def on_code(self, uc, address, size, data):
        rva = address - n.BASE
        if rva == 0x4F7A88:
            n.require(self.reg_read("RCX") == 0x18, "unexpected invisibility allocation")
            pointer = self.allocation
            self.allocation += 0x20
            self.ret(pointer)
            return
        if rva == 0x204EC0:
            self.messages.append(self.reg_read("RDX"))
            self.ret(0)
            return
        if rva == 0x276700:
            n.require(self.reg_read("RCX") == 123, "message changed target actor")
            self.put(self.reg_read("RDX"), "Q", n.ACTOR)
            self.ret(0)
            return
        if address == n.FAKE_CALLS + 0x900:
            self.ret(0x31)
            return
        super().on_code(uc, address, size, data)


for stats_current in (0, 1):
    for already_visible_flag in (0, 1):
        for force_visual in (0, 1):
            p = InvisibleMachine()
            p.put(n.ACTIVE + 0x1C, "iI", -1, 0)
            p.put(n.ACTIVE + 0xCC, "I", 1)
            p.put(n.ACTOR + 0x4EA4, "I", stats_current)
            p.put(n.ACTOR + 0x3F73, "B", already_visible_flag)
            p.put(n.ACTOR + 0x4E88, "I", force_visual)
            original = p.read(n.ACTIVE, 0x180)
            actor_before = p.read(n.ACTOR, 0x6000)
            p.run(0x1E5500, n.ACTIVE, n.ACTOR)  # Real base + class OnAddSpecific.
            n.require(p.read(n.ACTIVE, 0x180) == original, "mode0 OnAdd changed original")
            n.require(p.read(n.ACTOR, 0x6000) == actor_before and not p.messages, "mode0 OnAdd has side effect")
            def reset():
                p.put(n.ACTOR + 0x1120, "I", 0x4000)
                p.put(n.ACTOR + 0x1DC8, "I", 0x8000)
                p.put(n.ACTOR + 0x3F73, "B", already_visible_flag)
            def check():
                n.require(p.get(n.ACTOR + 0x1120, "I") == 0x4010, "invisibility state did not remain boolean")
                while p.messages:
                    message = p.messages.pop(0)
                    n.require(p.get(message, "Q") == n.BASE + 0x598E60, "unexpected message type")
                    n.require(p.read(message + 0x10, 2) == b"\x02\x01", "unexpected visual operation")
                    p.run(0x219470, message)
                    p.events["visual_message_runs"] += 1
                    selected = 0x1120 if stats_current else 0x1DC8
                    n.require(p.get(n.ACTOR + selected, "I") & 0x10, "visual message failed to set selected state")
                    n.require(p.get(n.ACTOR + 0x3F73, "B") == 1, "visual message flag mismatch")
            stable_rebuilds(p, reset, check)
            n.require(bool(p.events["visual_message_runs"]) == bool(force_visual or not already_visible_flag),
                      "visual message queue condition was not exercised")
            results.append(dict(opcode=20, mode=0, stats_current=stats_current,
                                already_invisible=already_visible_flag, force_visual=force_visual,
                                original_fields_stable=True, visual_message_run_executed=True))
print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Original class Apply/Resolve instructions; synthetic actors and baseline resets.",
                 "Constructor/lifecycle signatures checked; no full derived-stat rebuild, general gameplay state consumers or save/load.",
                 "Invisibility message Run executes; message queue, allocator, actor lookup/type services are test doubles.",
                 "No game process, resource/installer writes or generated hook execution."]), indent=2))
