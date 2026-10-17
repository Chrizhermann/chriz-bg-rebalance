"""Pinned offline crushing/piercing/missile finite resistance proof.

Actual DecodeEffect/constructors, base self OnAdd, Apply/Resolve instructions
execute in Unicorn. Actor baseline/rebuilds are controlled, not a complete
ProcessEffectList or damage simulation. No game, DLL, install or save changes.
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
import pefile
import unicorn
from unicorn import x86_const
import probe_native_admission as n
import probe_native_linked_construction as construction
from probe_native_potion_stats import StatsMachine, vtable_evidence

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256, "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
CLASSES = {
    # opcode: ctor, Apply, base signed-byte, finite additive signed-WORD.
    87: (0x1A1B80, 0x1C0E20, 0x5B9, 0x2A9E),
    88: (0x1A1D40, 0x1C1810, 0x5BA, 0x2AA0),
    89: (0x1A1D00, 0x1C1660, 0x5BB, 0x2AA2),
}
n.APPLY.update({opcode: entry[1] for opcode, entry in CLASSES.items()})
results = []


def signed16(value):
    return (value + 32768) % 65536 - 32768


def refreshed(opcode, amount):
    p = StatsMachine(image, unicorn, x86_const, opcode)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
    p.put(n.ACTIVE + 0x48, "I", 29)
    p.put(n.ACTIVE + 0xCC, "I", 1)
    before = p.read(n.ACTIVE, 0x180)
    n.require(p.get(n.ACTIVE + 0x28, "I") == 1450, "unexpected original deadline")
    p.put(n.ACTIVE + 0x28, "I", 1900)
    expected = bytearray(before)
    struct.pack_into("<I", expected, 0x28, 1900)
    n.require(p.read(n.ACTIVE, 0x180) == expected, "refresh changed more than expiry")
    return p, bytes(expected)


def expire(p):
    count = p.events["apply_active"]
    p.put(n.GAME + 0x3FA0, "I", 1900)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.events["apply_active"] == count and p.get(n.ACTIVE + 0x114, "I") == 1,
              "native effect reapplied at refreshed expiry")


for opcode, (ctor, apply, base, additive) in CLASSES.items():
    lifecycle = vtable_evidence(image, ctor)
    for raw_size in (0, 23, 0xFFFFFFFF):
        raw = construction.raw_effect(opcode, p1=0xFFFF0001, p2=0,
                                      dice_count=17, dice_size=raw_size, special=29)
        m = construction.Machine(image, unicorn, x86_const, records=[raw])
        row = m.ability_effect()
        pointer = m.reg_read("RAX")
        vtable = m.get(pointer, "Q")
        n.require(m.get(vtable + 0x10, "Q") == n.BASE + apply,
                  "actual DecodeEffect selected another class")
        n.require((row["p1"], row["p2"], row["special"]) == (0xFFFF0001, 0, 29),
                  "constructor changed original matching fields")
        n.require((row["dice_count"], row["dice_size"], row["max_level"], row["min_level"])
                  == (0, 0, 17, 0 if raw_size == 0xFFFFFFFF else raw_size),
                  "constructor non-dice field mapping differs")
        results.append(dict(case="construction", opcode=opcode, raw_size=raw_size,
                            vtable=f"{vtable - n.BASE:X}", lifecycle=lifecycle))

    # Native instruction boundary and real IR/IRR amounts; no polarity is
    # assumed from the raw dword sign. Every finite case uses an original
    # already-absolute effect object and preserves its whole 0x180 bytes.
    for amount in (-2147483648, -65535, -129, -1, 0, 1, 20, 25, 100,
                   32667, 32668, 32767, 32768, 65535, 65536, 65537, 2147483647):
        p, original = refreshed(opcode, amount)
        observed = []
        for baseline in (-32768, -128, 0, 75, 100):
            for now in (1000, 1450, 1501, 1899):
                p.put(n.GAME + 0x3FA0, "I", now)
                p.put(n.ACTOR + additive, "h", baseline)
                expected = baseline
                first = None
                for _ in range(2):
                    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                    expected = min(100, signed16(expected + signed16(amount)))
                    n.require(p.get(n.ACTOR + additive, "h") == expected,
                              "native finite LOW16 addition/cap mismatch")
                    n.require(p.read(n.ACTIVE, 0x180) == original,
                              "native finite Apply changed original effect fields")
                    if first is None:
                        first = expected
                if now == 1000:
                    observed.append(dict(baseline=baseline, first=first, second=expected))
        expire(p)
        results.append(dict(case="finite_lifetime", opcode=opcode, raw_amount=amount,
                            effective_amount=signed16(amount), observations=observed))

    # Explicit proof of the conservative finite range endpoints, independent
    # of the loop's model calculation. Native writes WORD before signed cap.
    for baseline, amount, expected in ((100, 32667, 100), (100, 32668, -32768),
                                       (-32768, -1, 100), (-32768, 1, -32767),
                                       (0, 32768, -32768), (0, 65536, 0),
                                       (0, -65535, 1), (0, 65535, -1)):
        p, original = refreshed(opcode, amount)
        p.put(n.ACTOR + additive, "h", baseline)
        p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
        n.require(p.get(n.ACTOR + additive, "h") == expected, "native endpoint counterexample differs")
        n.require(p.read(n.ACTIVE, 0x180) == original, "boundary operation changed effect fields")
        results.append(dict(case="explicit_boundary", opcode=opcode, baseline=baseline,
                            raw_amount=amount, result=expected))

    # Timing1 is a native base-byte operation that sets Done and Repass,
    # distinct from the stable finite original. Never turn it into ownership.
    for amount, expected in ((20, 20), (255, -1), (256, 0), (257, 1)):
        p = StatsMachine(image, unicorn, x86_const, opcode)
        p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
        p.put(n.ACTIVE + 0x24, "I", 1)
        p.put(n.ACTOR + base, "b", 0)
        p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
        n.require(p.get(n.ACTOR + base, "b") == expected, "instant base-byte operand differs")
        n.require(p.get(n.ACTIVE + 0x114, "I") == 1 and p.get(n.ACTIVE + 0x118, "I") == 1,
                  "instant native Done/Repass state differs")
        n.require(p.get(n.ACTOR + additive, "h") == 0, "instant mutated finite accumulator")
        results.append(dict(case="instant_control", opcode=opcode, amount=amount,
                            native_base_result=expected, done=True, repass=True))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Native constructors, base self OnAdd, Apply and Resolve execute; lifecycle vtable slots are byte-verified.",
                 "Synthetic actor/baseline resets replace full ProcessEffectList and damage arithmetic.",
                 "This probe does not establish save/admission success, linked transport, native DLL or generated hooks.",
                 "Signed WORD wrapping is preserved; no engine arithmetic is repaired.",
                 "No game launch, resource/save write or installation."]), indent=2))
