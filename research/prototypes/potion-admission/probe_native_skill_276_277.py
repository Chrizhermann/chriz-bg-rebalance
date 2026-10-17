"""Pinned offline skill276/277 lifecycle, widths and final-limit evidence.

Native Apply/Resolve, three exact CDerivedStats merge pairs and full
CheckLimits execute. Baseline/reset, allocation and unrelated engine services
are controlled; no game, DLL, resource, installation or save mutation occurs.
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
CLASSES = {275: (0x19FF70, 0x1B54F0, 0x59D, 0x1194, 0x2AE4, 0x2D08),
           276: (0x19F4A0, 0x1B14F0, 0x5BC, 0x1198, 0x2AE8, 0x2D0C),
           277: (0x1A2740, 0x1C60D0, 0x5BD, 0x119C, 0x2AEC, 0x2D10)}
n.APPLY.update({opcode: entry[1] for opcode, entry in CLASSES.items()})
results = []


def signed(value, bits):
    return (value + (1 << (bits - 1))) % (1 << bits) - (1 << (bits - 1))


class SkillMachine(StatsMachine):
    segment_stop = None

    def on_code(self, uc, address, size, data):
        if address == self.segment_stop:
            self.reg_write("RIP", n.RETURN)
            return
        super().on_code(uc, address, size, data)

    def merge_and_limit(self):
        # Execute exactly operator+=15040E..15041D for these DWORD fields.
        # The surrounding derived-list assignments are deliberately omitted.
        self.reg_write("RBX", n.ACTOR + 0x1120)
        self.reg_write("RDI", n.ACTOR + 0x2A70)
        self.segment_stop = n.BASE + 0x150420
        self.run(0x15040E)
        self.segment_stop = None
        self.run(0x1514B0, n.ACTOR + 0x1120)


for opcode, (ctor, apply, base, derived, additive, permanent) in CLASSES.items():
    lifecycle = vtable_evidence(image, ctor)
    for raw_size in (0, 23, 0xFFFFFFFF):
        m = construction.Machine(image, unicorn, x86_const, records=[construction.raw_effect(
            opcode, p1=0xFFFFFFFF, p2=2, dice_count=17, dice_size=raw_size, special=29)])
        row = m.ability_effect()
        pointer = m.reg_read("RAX")
        n.require(m.get(m.get(pointer, "Q") + 0x10, "Q") == n.BASE + apply, "wrong decoded class")
        n.require((row["p1"], row["p2"], row["special"]) == (0xFFFFFFFF, 2, 29),
                  "constructor changed raw matching fields")
        n.require((row["dice_count"], row["dice_size"], row["max_level"], row["min_level"])
                  == (0, 0, 17, 0 if raw_size == 0xFFFFFFFF else raw_size), "wrong non-dice fields")
        results.append(dict(case="constructor", opcode=opcode, raw_size=raw_size, lifecycle=lifecycle))

    for mode in (0, 1, 2):
        for amount in (-2147483648, -65535, -129, -1, 0, 1, 20, 100, 150,
                       255, 256, 32767, 32768, 65535, 65536, 65537, 2147483647):
            p = SkillMachine(image, unicorn, x86_const, opcode)
            p.verify_self_on_add()
            p.put(n.ACTIVE + 0x1C, "iI", amount, mode)
            p.put(n.ACTIVE + 0x48, "I", 29)
            p.put(n.ACTIVE + 0xCC, "I", 1)
            before_refresh = p.read(n.ACTIVE, 0x180)
            p.put(n.ACTIVE + 0x28, "I", 1900)
            expected_refresh = bytearray(before_refresh)
            struct.pack_into("<I", expected_refresh, 0x28, 1900)
            original = p.read(n.ACTIVE, 0x180)
            n.require(original == expected_refresh, "refresh changed fields other than expiry")
            observed = []
            for baseline in (0, 50, 255):
                for now in (1000, 1450, 1501, 1899):
                    p.put(n.GAME + 0x3FA0, "I", now)
                    p.put(n.ACTOR + base, "B", baseline)
                    p.put(n.ACTOR + derived, "i", baseline)
                    p.put(n.ACTOR + additive, "i", 0)
                    for repeat in (1, 2):
                        p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                        if mode == 0:
                            expected = signed(amount, 16) * repeat
                            value = p.get(n.ACTOR + additive, "i")
                        else:
                            product = baseline * signed(amount, 16)
                            expected = amount % 256 if mode == 1 else (abs(product) // 100) * (-1 if product < 0 else 1)
                            value = p.get(n.ACTOR + derived, "i")
                        n.require(value == expected, "native amount width/operation mismatch")
                        n.require(p.read(n.ACTIVE, 0x180) == original, "original fields changed")
                    p.merge_and_limit()
                    final = p.get(n.ACTOR + derived, "i")
                    expected_final = max(0, min(255, baseline + expected if mode == 0 else expected))
                    n.require(final == expected_final, "native merge/final clamp mismatch")
                    n.require(p.read(n.ACTIVE, 0x180) == original, "merge/limits changed original effect")
                    if now == 1000:
                        observed.append(dict(baseline=baseline, raw_after_two=expected, final=final))
            count = p.events["apply_active"]
            p.put(n.GAME + 0x3FA0, "I", 1900)
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            n.require(p.events["apply_active"] == count and p.get(n.ACTIVE + 0x114, "I") == 1,
                      "original reapplied after new expiry")
            results.append(dict(case="finite_lifetime", opcode=opcode, mode=mode, raw_amount=amount,
                                effective_amount=signed(amount, 16), observations=observed))

    for baseline, amount, derived_base, expected_add, expected_final in (
        (2147483647, 1, 0, -2147483648, 0),
        (-2147483648, -1, 0, 2147483647, 255),
        (2147483647, 0, 1, 2147483647, 0),
    ):
        p = SkillMachine(image, unicorn, x86_const, opcode)
        p.put(n.ACTIVE + 0x1C, "iI", amount, 0)
        p.put(n.ACTOR + additive, "i", baseline)
        p.put(n.ACTOR + derived, "i", derived_base)
        original = p.read(n.ACTIVE, 0x180)
        p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
        n.require(p.get(n.ACTOR + additive, "i") == expected_add, "native accumulator wrap counterexample missing")
        p.merge_and_limit()
        n.require(p.get(n.ACTOR + derived, "i") == expected_final, "native final merge/clamp wrap differs")
        n.require(p.read(n.ACTIVE, 0x180) == original, "wrap changed original fields")
        results.append(dict(case="wrap_boundary", opcode=opcode, accumulator=baseline, amount=amount,
                            derived_base=derived_base, after_add=expected_add, final=expected_final))

    # Timing9 has a distinct raw32 persistent accumulator. It is not part of
    # the finite0/10 uniqueness classification and must remain native.
    p = SkillMachine(image, unicorn, x86_const, opcode)
    p.put(n.ACTIVE + 0x1C, "iI", 65537, 0)
    p.put(n.ACTIVE + 0x24, "I", 9)
    original = p.read(n.ACTIVE, 0x180)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.get(n.ACTOR + permanent, "i") == 65537 and p.get(n.ACTOR + additive, "i") == 0,
              "timing9 raw32 persistent branch differs")
    n.require(p.read(n.ACTIVE, 0x180) == original, "timing9 changed original matching fields")
    results.append(dict(case="timing9_control", opcode=opcode, raw_amount=65537))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Synthetic actor baselines/list resets; no complete ProcessEffectList run.",
                 "Native constructors, original Apply/Resolve, exact three DWORD merge pairs and full CheckLimits execute.",
                 "Boundary accumulator states are controlled counterexamples, not evidence of typical gameplay frequency.",
                 "No compiler classification is inferred solely from a raw positive amount.",
                 "No game, native DLL, installed resources, save or generated-hook execution."]), indent=2))
