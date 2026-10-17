"""Offline IR/IRR 86/120/130/206 behavior and original-field evidence.

Executes pinned DecodeEffect/constructors, Apply/Resolve and native immunity
consumers. Allocation, list insertion/rebuild and actor baselines are controlled
services. No game, installer, resource, save or production module is changed.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exe", required=True, type=Path)
parser.add_argument("--python-libs", type=Path)
args = parser.parse_args()
if args.python_libs:
    sys.path.insert(0, str(args.python_libs))
import pefile, unicorn
from unicorn import x86_const
import probe_native_admission as n
import probe_native_linked_construction as construction
from probe_native_potion_stats import StatsMachine, vtable_evidence

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256, "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
CLASSES = {86: (0x1A1D80, 0x1C19C0), 120: (0x1A0200, 0x1B6420),
           130: (0x1A0F00, 0x1BAAB0), 206: (0x1A0380, 0x1B6900)}
n.APPLY.update({opcode: pair[1] for opcode, pair in CLASSES.items()})
n.STUBS.pop(0x1F8C90)
results = []


def signed(value, bits):
    return (value + (1 << (bits - 1))) % (1 << bits) - (1 << (bits - 1))


for opcode, (ctor, apply) in CLASSES.items():
    lifecycle = vtable_evidence(image, ctor)
    for raw_size in (0, 19, 0xFFFFFFFF):
        raw = construction.raw_effect(opcode, p1=0xFFFFFF80, p2=2,
                                      dice_count=11, dice_size=raw_size, special=17)
        m = construction.Machine(image, unicorn, x86_const, records=[raw])
        row = m.ability_effect()
        pointer = m.reg_read("RAX")
        n.require(m.get(m.get(pointer, "Q") + 0x10, "Q") == n.BASE + apply,
                  "DecodeEffect chose a different native class")
        n.require((row["p1"], row["p2"], row["special"]) == (0xFFFFFF80, 2, 17),
                  "constructor changed matching operands")
        n.require((row["dice_count"], row["dice_size"], row["max_level"], row["min_level"])
                  == (0, 0, 11, 0 if raw_size == 0xFFFFFFFF else raw_size),
                  "unexpected non-dice constructor field mapping")
        results.append(dict(case="native_construction", opcode=opcode, raw_size=raw_size,
                            uses_dice=False, lifecycle=lifecycle))


def expire(p):
    count = p.events["apply_active"]
    p.put(n.GAME + 0x3FA0, "I", 1900)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.events["apply_active"] == count and p.get(n.ACTIVE + 0x114, "I") == 1,
              "effect reapplied at new expiry")


# Actual IR20/IRR25 plus width, adverse, zero and overflow controls. The finite
# add is LOW16, signed-compare cap100 AFTER the WORD addition (not saturating).
for amount in (-2147483648, -65535, -129, -1, 0, 1, 20, 25, 100, 128,
               32767, 32768, 65535, 65536, 65537, 2147483647):
    p = StatsMachine(image, unicorn, x86_const, 86)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
    p.put(n.ACTIVE + 0x28, "I", 1900)
    original = p.read(n.ACTIVE, 0x180)
    effective = signed(amount, 16)
    for now in (1000, 1450, 1501, 1899):
        p.put(n.GAME + 0x3FA0, "I", now)
        p.put(n.ACTOR + 0x2A9C, "h", 0)
        expected = 0
        for _ in range(2):
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            expected = min(100, signed(expected + effective, 16))
            n.require(p.get(n.ACTOR + 0x2A9C, "h") == expected, "86 add/width/cap mismatch")
            n.require(p.read(n.ACTIVE, 0x180) == original, "86 mutated original fields")
    expire(p)
    results.append(dict(case="finite_add", opcode=86, raw_amount=amount,
                        effective_amount=effective, repeated_result=expected))

for baseline, amount, expected in ((100, 32667, 100), (100, 32668, -32768),
                                   (-32768, -1, 100), (-32768, 1, -32767)):
    p = StatsMachine(image, unicorn, x86_const, 86)
    p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
    p.put(n.ACTOR + 0x2A9C, "h", baseline)
    original = p.read(n.ACTIVE, 0x180)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.get(n.ACTOR + 0x2A9C, "h") == expected, "86 capability boundary changed")
    n.require(p.read(n.ACTIVE, 0x180) == original, "86 boundary mutated original fields")
    results.append(dict(case="slashing_polarity_wrap_boundary", opcode=86,
                        baseline=baseline, amount=amount, result=expected))

# Native 130 is first-winner behind shared bit23, not a max or latest setter.
# Reset only derived fields between rounds; retain the base morale byte so the
# native reapplication side effect is visible instead of hidden by the harness.
for amount in (-257, -129, -128, -1, 0, 2, 127, 128, 255, 256, 258):
    for initially_set in (False, True):
        p = StatsMachine(image, unicorn, x86_const, 130)
        p.verify_self_on_add()
        p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
        p.put(n.ACTIVE + 0x28, "I", 1900)
        p.put(n.ACTOR + 0x797, "B", 10)
        original = p.read(n.ACTIVE, 0x180)
        morale = 10
        for now in (1000, 1450, 1501, 1899):
            p.put(n.GAME + 0x3FA0, "I", now)
            p.put(n.ACTOR + 0x1120, "I", (1 << 23) if initially_set else 0)
            p.put(n.ACTOR + 0x11A0, "h", 5)
            p.put(n.ACTOR + 0x1130, "h", 10)
            expected_amount = 0 if initially_set else signed(amount, 8)
            if not initially_set:
                morale = (morale + amount) & 255
            for _ in range(2):
                p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                n.require(p.get(n.ACTOR + 0x11A0, "h") == 5 + expected_amount,
                          "130 damage did not use signed LOW8/first-winner")
                n.require(p.get(n.ACTOR + 0x1130, "h") == 10 - expected_amount,
                          "130 THAC0 did not use signed LOW8/first-winner")
                n.require(p.get(n.ACTOR + 0x797, "B") == morale, "130 morale side effect differs")
                n.require(p.read(n.ACTIVE, 0x180) == original, "130 mutated original fields")
        expire(p)
        results.append(dict(case="shared_state_first_winner", opcode=130,
                            raw_amount=amount, effective_amount=signed(amount, 8),
                            prior_state_bit=initially_set, morale_after_four_rebuilds=morale))

for first, second in ((2, 7), (7, 2)):
    p = StatsMachine(image, unicorn, x86_const, 130)
    p.put(n.ACTOR + 0x797, "B", 10)
    p.put(n.ACTIVE + 0x1C, "II", first, 0xFFFFFFFF)
    p.put(n.ACTIVE + 0x48, "I", 0xFFFFFFFF)
    p.put(n.OTHER + 0x1C, "II", second, 0)
    for pointer in (n.ACTIVE, n.OTHER):
        before = p.read(pointer, 0x180)
        p.run(n.APPLY[130], pointer, n.ACTOR)
        n.require(p.read(pointer, 0x180) == before, "130 changed first/second original")
    n.require(p.get(n.ACTOR + 0x11A0, "h") == first and
              p.get(n.ACTOR + 0x1130, "h") == -first and
              p.get(n.ACTOR + 0x797, "B") == 10 + first,
              "130 does not preserve first-winner/ignored mode and Special semantics")
    results.append(dict(case="different_bless_order", opcode=130, first=first, second=second,
                        mode_and_special_ignored=True))


class ImmunityMachine(StatsMachine):
    def __init__(self, opcode):
        super().__init__(image, unicorn, x86_const, opcode)
        self.allocation = 0x740000000
        self.u.mem_map(self.allocation, 0x10000)
        self.entries = []
        self.list_offset = 0x14E0 if opcode == 120 else 0x1880

    def allocate(self):
        pointer = self.allocation
        self.allocation += 0x20
        return pointer

    def on_code(self, uc, address, size, data):
        rva = address - n.BASE
        if rva == 0x4F7A88:
            n.require(self.reg_read("RCX") == 16, "unexpected guard allocation")
            self.ret(self.allocate())
            return
        if rva == 0x4075C0:
            n.require(self.reg_read("RCX") == n.ACTOR + self.list_offset, "unexpected immunity list")
            pointer, node = self.reg_read("RDX"), self.allocate()
            self.put(node, "QQQ", 0, self.entries[-1][0] if self.entries else 0, pointer)
            if self.entries:
                self.put(self.entries[-1][0], "Q", node)
            else:
                self.put(n.ACTOR + self.list_offset + 8, "Q", node)
            self.entries.append((node, pointer))
            self.ret(node)
            return
        super().on_code(uc, address, size, data)


# Actual mode2 protects a flag category. All native modes are additionally
# checked as source evidence, not granted compiler capability by this probe.
weapon_shapes = [(0, 0, 3), (0x40, 0x40, 0xFFFFFFFF), (0, 0x40, 0xFFFFFFFF),
                 (0x100, 0x100, 0xFFFFFFFF), (0, 0x100, 0xFFFFFFFF),
                 (0, 0x100, 0), (2, 2, 0xFFFFFFFF), (0, 2, 0xFFFFFFFF),
                 (0x10, 0x10, 0xFFFFFFFF), (0, 0x10, 0xFFFFFFFF),
                 (0x200, 0x200, 0xFFFFFFFF), (0, 0x200, 0xFFFFFFFF), (0, 0, 0)]
for mode in range(13):
    p = ImmunityMachine(120)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0x1C, "II", 3, mode)
    p.put(n.ACTIVE + 0x28, "I", 1900)
    original = p.read(n.ACTIVE, 0x180)
    value, mask, level = weapon_shapes[mode]
    descriptor = struct.pack("<IIII", 0, value, mask, level)
    for now in (1000, 1450, 1501, 1899):
        p.put(n.GAME + 0x3FA0, "I", now)
        p.entries = []
        p.put(n.ACTOR + p.list_offset + 8, "Q", 0)
        for duplicate_count in (1, 2):
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            n.require(p.read(n.ACTIVE, 0x180) == original, "120 mutated original fields")
            n.require(len(p.entries) == duplicate_count, "120 registration count differs")
            n.require(all(p.read(pointer, 16) == descriptor for _, pointer in p.entries),
                      "120 registered wrong predicate")
            before = b"".join(p.read(pointer, 16) for _, pointer in p.entries)
            for query_flags in (0, 2, 0x10, 0x40, 0x100, 0x200, 0xFFFFFFFF):
                for query_level in (0, 3, 4, 0xFFFFFFFF):
                    p.put(n.EFFECT + 0x200, "IIII", 17, query_flags, 0, query_level)
                    p.run(0x1F9040, n.ACTOR + p.list_offset, n.EFFECT + 0x200)
                    expected = (query_flags & mask) == value and query_level <= level
                    n.require(bool(p.reg_read("RAX")) == expected, "120 native predicate mismatch")
            n.require(before == b"".join(p.read(pointer, 16) for _, pointer in p.entries),
                      "weapon immunity consumer mutated/consumed descriptor")
    expire(p)
    results.append(dict(case="weapon_predicate_nonconsuming", opcode=120, mode=mode,
                        value=value, mask=mask, level=level, duplicate_capacity=False))


for amount in (0, -1, 74011):
    for resource in ("POTN14", "SPWI305"):
        p = ImmunityMachine(206)
        p.verify_self_on_add()
        p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
        p.u.mem_write(n.ACTIVE + 0x30, resource.encode().ljust(8, b"\0"))
        p.put(n.ACTIVE + 0x28, "I", 1900)
        original = p.read(n.ACTIVE, 0x180)
        for now in (1000, 1450, 1501, 1899):
            p.put(n.GAME + 0x3FA0, "I", now)
            p.entries = []
            p.put(n.ACTOR + p.list_offset + 8, "Q", 0)
            for duplicate_count in (1, 2):
                p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                n.require(p.read(n.ACTIVE, 0x180) == original, "206 mutated original fields")
                descriptor = resource.encode().ljust(8, b"\0") + struct.pack("<iI", amount or -1, 0)
                n.require(len(p.entries) == duplicate_count and
                          all(p.read(pointer, 16) == descriptor for _, pointer in p.entries),
                          "206 wrong resource/message/item-scope descriptor")
                before = b"".join(p.read(pointer, 16) for _, pointer in p.entries)
                for item_source in (0, 1):
                    for query in (resource, "NOMATCH"):
                        p.u.mem_write(n.EFFECT + 0x94, query.encode().ljust(8, b"\0"))
                        p.run(0x1F8C90, n.ACTOR + p.list_offset, n.EFFECT + 0x94, item_source)
                        expected = query == resource and item_source == 0
                        n.require(bool(p.reg_read("RAX")) == expected, "206 native lookup mismatch")
                        if expected:
                            n.require(p.reg_read("RAX") == p.entries[0][1], "lookup did not return first entry")
                n.require(before == b"".join(p.read(pointer, 16) for _, pointer in p.entries),
                          "resource immunity consumer mutated/consumed descriptor")
        expire(p)
        results.append(dict(case="resource_predicate_nonconsuming", opcode=206,
                            amount=amount, resource=resource, entry_message=amount or -1,
                            includes_item_sources=False, duplicate_capacity=False))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Allocator/list insertion and derived-list/baseline rebuilds are controlled services.",
                 "Native constructors, Apply/Resolve and weapon/resource immunity consumers execute.",
                 "130 rebuild counterexample manually clears derived state; whole ProcessEffectList and morale recomputation are not executed.",
                 "No full attack, CheckAdd/save/MR, generated hook, live load or policy-bypass acceptance.",
                 "No compiler/runtime module changes; no game, resource or save writes."]), indent=2))
