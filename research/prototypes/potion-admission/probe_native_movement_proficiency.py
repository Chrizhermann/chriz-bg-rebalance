"""Offline native126 movement setters and233 proficiency setter proof.

Pinned Apply/Resolve and animation getter/setter instructions, synthetic actors
and stat rebuilds. No game launch, installation, resources or save changes.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path

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

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256, "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
n.APPLY.update({126: 0x1BA6C0, 233: 0x1BCBB0})
ANIMATION, ANIMATION_VTABLE = 0x730000000, 0x730003000
results = []


def make(opcode, amount, mode, special=0):
    lifecycle = vtable_evidence(image, 0x1A0D40 if opcode == 126 else 0x1A1480)
    p = StatsMachine(image, unicorn, x86_const, opcode)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0x1C, "iI", amount, mode)
    p.put(n.ACTIVE + 0x48, "I", special)
    p.put(n.ACTIVE + 0xCC, "I", 1)
    return p, lifecycle


def stable(p, reset, check):
    expected = bytearray(p.read(n.ACTIVE, 0x180))
    struct.pack_into("<I", expected, 0x28, 1900)
    p.put(n.ACTIVE + 0x28, "I", 1900)
    for now in (1000, 1450, 1501, 1899):
        p.put(n.GAME + 0x3FA0, "I", now)
        reset()
        for _ in range(2):
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            check()
            n.require(p.read(n.ACTIVE, 0x180) == expected, "native effect state changed")
    count = p.events["apply_active"]
    p.put(n.GAME + 0x3FA0, "I", 1900)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.events["apply_active"] == count, "original reapplied at new expiry")


def animation(p, variant, base):
    p.u.mem_map(ANIMATION, 0x4000)
    p.put(n.ACTOR + 0x3C40, "Q", ANIMATION)
    p.put(ANIMATION, "Q", ANIMATION_VTABLE)
    p.put(ANIMATION + 0xA, "BB", base, 7)
    p.put(ANIMATION + 0x1BAC, "I", 1 if variant == "ankheg_hidden" else 0)
    p.put(ANIMATION_VTABLE + 0x88, "Q", n.BASE + (0x11DC40 if variant == "base" else 0x327A70))
    p.put(ANIMATION_VTABLE + 0x90, "Q", n.BASE + 0x3373D0)
    p.put(ANIMATION_VTABLE + 0xA0, "Q", n.BASE + (0x327A90 if variant == "base" else 0x327AA0))


for mode in (1, 2):
    for variant in ("base", "ankheg_visible", "ankheg_hidden"):
        for base in (0, 9, 255):
            for amount in (-65535, -1, 0, 1, 100, 150, 256, 65535, 65536, 65537):
                p, lifecycle = make(126, amount, mode)
                animation(p, variant, base)
                effective = (amount + 32768) % 65536 - 32768
                product = effective * base
                quotient = (abs(product) // 100) * (-1 if product < 0 else 1)
                expected = amount % 256 if mode == 1 else quotient % 256
                if base == 0 or variant == "ankheg_hidden":
                    expected = 7
                def reset():
                    p.put(ANIMATION + 0xB, "B", 7)
                def check():
                    n.require(p.get(ANIMATION + 0xB, "B") == expected, "movement setter width/result mismatch")
                stable(p, reset, check)
                results.append(dict(opcode=126, mode=mode, amount=amount, variant=variant,
                                    default_speed=base, result=expected, stable=True, lifecycle=lifecycle))

for mode in (3, 4, 6, 0xFFFFFFFF):
    p, lifecycle = make(126, 100, mode)
    animation(p, "base", 9)
    stable(p, lambda: None,
           lambda: n.require(p.get(ANIMATION + 0xB, "B") == 7, "unimplemented movement mode changed speed"))
    results.append(dict(opcode=126, mode=mode, native_noop=True, stable=True, lifecycle=lifecycle))

# Modes0/5 read the current speed: explicit counterexamples, not setter support.
for mode, amount, expected in ((0, 1, (10, 11)), (5, 200, (18, 36))):
    p, lifecycle = make(126, amount, mode)
    animation(p, "base", 9)
    p.put(ANIMATION + 0xB, "B", 9)
    observed = []
    for _ in range(2):
        p.run(n.APPLY[126], n.ACTIVE, n.ACTOR)
        observed.append(p.get(ANIMATION + 0xB, "B"))
    n.require(tuple(observed) == expected, "movement accumulation counterexample changed")
    results.append(dict(opcode=126, mode=mode, amount=amount, repeat_values=observed, supported=False))

for index in range(89, 135):
    for amount in (-1, 1):
        p, lifecycle = make(233, amount, index, special=9)
        before = bytes([0x55]) * (46 * 4)
        expected = bytearray(before)
        struct.pack_into("<i", expected, (index - 89) * 4, amount)
        def reset():
            p.u.mem_write(n.ACTOR + 0x1218, before)
        def check():
            n.require(p.read(n.ACTOR + 0x1218, len(before)) == expected, "proficiency setter slot/value mismatch")
        stable(p, reset, check)
        results.append(dict(opcode=233, index=index, amount=amount, stable=True, lifecycle=lifecycle))

for index in (0, 88, 135, 65535, 65536, 0x10000 + 135, 0xFFFFFFFF):
    p, lifecycle = make(233, 1, index)
    before = p.read(n.ACTOR, 0x6000)
    stable(p, lambda: None, lambda: n.require(p.read(n.ACTOR, 0x6000) == before, "out-of-range setter modified actor"))
    results.append(dict(opcode=233, index=index, native_noop=True, stable=True, lifecycle=lifecycle))

# High16!=0 selects the additive/first-call branch; the common131 case proves
# it must not inherit the high16==0 setter classification.
p, _ = make(233, 1, 0x10000 + 131)
p.put(n.ACTOR + 0x2C10, "I", 0)
observed = []
for _ in range(2):
    p.run(n.APPLY[233], n.ACTIVE, n.ACTOR)
    observed.append(p.get(n.ACTOR + 0x2C10, "I"))
n.require(observed == [1, 2], "proficiency additive counterexample changed")
n.require(p.get(n.ACTIVE + 0xCC, "I") == 0 and p.get(n.ACTIVE + 0x60, "I") == 1,
          "proficiency first-call state changed")
results.append(dict(opcode=233, mode=0x10000 + 131, repeat_values=observed,
                    first_call_consumed=True, supported=False))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Native class Apply/Resolve and animation getter/setter functions execute.",
                 "Synthetic actor/animation allocation and derived-stat rebuilds; no complete actor processing or movement path execution.",
                 "233 additive counterexample does not establish all additive slots or their Special-dependent behavior.",
                 "No game launch, installation, resource edits, hook assembly or saves."]), indent=2))
