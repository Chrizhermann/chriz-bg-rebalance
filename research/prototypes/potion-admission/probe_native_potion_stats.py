"""Bounded offline expiry-state check for additional direct potion opcodes.

Reads only a pinned PE; executes copied instructions in Unicorn. No game or DLL
execution, hooks, resource writes or save edits. Each test runs the actual
ResolveEffect/ApplyEffect with a synthetic fresh stat accumulator. It is NOT a
whole ProcessEffectList simulation, admission test or policy classifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native


# opcode: (class name, ctor RVA, Apply RVA, actor accumulator, width, sign)
STATS = {
    6: ("CHR", 0x19E7E0, 0x1A8090, 0x2ACA, "h", 1),
    10: ("CON", 0x19E820, 0x1A8230, 0x2AC8, "h", 1),
    15: ("DEX", 0x19F1A0, 0x1ACEF0, 0x2AC6, "h", 1),
    21: ("Lore", 0x1A0940, 0x1B9910, 0x2AA4, "h", 1),
    22: ("Luck", 0x1A0980, 0x1B9A90, 0x2AB2, "h", 1),
    27: ("ResistAcid", 0x1A1B00, 0x1C0B40, 0x2A94, "h", 1),
    28: ("ResistCold", 0x1A1B40, 0x1C0CB0, 0x2A90, "h", 1),
    29: ("ResistElectricity", 0x1A1BC0, 0x1C0FD0, 0x2A92, "h", 1),
    30: ("ResistFire", 0x1A1C00, 0x1C1140, 0x2A8E, "h", 1),
    31: ("ResistMagic", 0x1A1C40, 0x1C12B0, 0x2B2E, "h", 1),
    33: ("SaveVsDeath", 0x1A2100, 0x1C3280, 0x2A84, "h", -1),
    34: ("SaveVsWands", 0x1A2200, 0x1C3800, 0x2A86, "h", -1),
    35: ("SaveVsPoly", 0x1A2140, 0x1C3430, 0x2A88, "h", -1),
    36: ("SaveVsBreath", 0x1A20C0, 0x1C30E0, 0x2A8A, "h", -1),
    37: ("SaveVsSpell", 0x1A21C0, 0x1C3650, 0x2A8C, "h", -1),
    44: ("STR", 0x1A2000, 0x1C2B50, 0x2ABE, "h", 1),
    49: ("WIS", 0x1A3340, 0x1CAD20, 0x2AC4, "h", 1),
    59: ("SkillStealth", 0x1A29C0, 0x1C6C90, 0x2AA8, "h", 1),
    73: ("DamageMod", 0x19F260, 0x1AE760, 0x2AF0, "h", 1),
    91: ("SkillTraps", 0x1A2A40, 0x1C6F20, 0x2AAA, "h", 1),
    275: ("HideInShadows", 0x19FF70, 0x1B54F0, 0x2AE4, "i", 1),
}
native.APPLY.update({opcode: data[2] for opcode, data in STATS.items()})
native.APPLY.update({328: 0x1C6080})

# opcode: (ctor, base value offset, derived value offset, derived field format)
# Traps91 intentionally multiplies the current derived value in percentage mode;
# the other three skills read a base byte. This is NOT a blanket nonstacking list.
SKILLS = {
    90: (0x1A2940, 0x5BF, 0x1156, "h"),
    91: (0x1A2A40, 0x5C1, 0x115A, "h"),
    92: (0x1A2980, 0x5C2, 0x115C, "h"),
    275: (0x19FF70, 0x59D, 0x1194, "i"),
}
ABILITY_STATS = {
    6: (0x19E7E0, 0x796, 0x117A, "h"),
    10: (0x19E820, 0x795, 0x1178, "h"),
    15: (0x19F1A0, 0x794, 0x1176, "h"),
    44: (0x1A2000, 0x790, 0x116E, "h"),
    49: (0x1A3340, 0x793, 0x1174, "h"),
}


def vtable_evidence(image, ctor):
    """Read the ctor-installed real vtable; do not substitute probe vtable slots."""
    native.require(image[ctor + 0x16:ctor + 0x1E] == bytes.fromhex("C744242800000000"),
                   "UsesDice=false ctor signature changed")
    native.require(image[ctor + 0x28:ctor + 0x2B] == bytes.fromhex("488D05"),
                   "constructor vtable LEA changed")
    vtable = ctor + 0x2F + struct.unpack_from("<i", image, ctor + 0x2B)[0]
    result = {name: struct.unpack_from("<Q", image, vtable + slot)[0] - native.BASE
              for name, slot in (("destructor", 0), ("on_add_specific", 0x28),
                                 ("on_remove", 0x50))}
    native.require(result == {"destructor": 0x14C8E0, "on_add_specific": 0x1E1E0,
                              "on_remove": 0x1E1E0}, "unreviewed lifecycle callback")
    return {name: f"{rva:X}" for name, rva in result.items()}


class StatsMachine(native.Machine):
    def verify_self_on_add(self):
        # Real base OnAdd and the constructor-verified no-op class callback.
        self.put(native.EFFECT_VTABLE + 0x28, "Q", native.BASE + 0x1E1E0)
        for source_flags in (0, 0x400):
            self.put(native.ACTIVE + 0x9C, "I", source_flags)
            before = self.read(native.ACTIVE, 0x180)
            actor = self.read(native.ACTOR, 0x6000)
            self.run(0x1E5500, native.ACTIVE, native.ACTOR)
            native.require(self.read(native.ACTIVE, 0x180) == before, "self OnAdd changed effect")
            native.require(self.read(native.ACTOR, 0x6000) == actor, "self OnAdd changed actor")

    def on_code(self, uc, address, size, data):
        # Direct stat application must not recursively deliver an effect.
        if address in (native.BASE + native.ADD_EFFECT, native.BASE + native.CHECK_ADD,
                       native.BASE + 0x204EC0):
            raise AssertionError("unexpected nested native delivery")
        super().on_code(uc, address, size, data)


def check_stat(image, unicorn, registers, opcode, amount, mode=0):
    name, ctor, apply, offset, fmt, sign = STATS[opcode]
    # Every reviewed additional class uses non-dice constructor semantics.
    lifecycle = vtable_evidence(image, ctor)
    p = StatsMachine(image, unicorn, registers, opcode)
    p.verify_self_on_add()
    p.put(native.ACTIVE + 0x1C, "iI", amount, mode)
    p.put(native.ACTIVE + 0xCC, "I", 1)
    # Save mode3's first immediate derived update is native. Observe once then
    # retain that first-call state; a refresh must not reset it.
    if mode == 3:
        p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        native.require(p.get(native.ACTIVE + 0xCC, "I") == 0, "save mode3 did not consume firstCall")
    original = p.read(native.ACTIVE, 0x180)
    p.put(native.ACTIVE + 0x28, "I", 1900)
    changed = bytearray(original)
    struct.pack_into("<I", changed, 0x28, 1900)
    native.require(p.read(native.ACTIVE, 0x180) == changed, "test setup changed more than expiry")
    cases = []
    for now in (1000, 1450, 1501, 1899):
        p.put(native.GAME + 0x3FA0, "I", now)
        p.put(native.ACTOR + offset, fmt, 0)  # Synthetic stat reload, not native scheduler.
        before = p.read(native.ACTIVE, 0x180)
        p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        value = p.get(native.ACTOR + offset, fmt)
        native.require(value == amount * sign, f"{opcode}/{mode}: wrong native accumulator {value}")
        native.require(p.read(native.ACTIVE, 0x180) == before,
                       f"{opcode}/{mode}: Apply mutated original effect state")
        cases.append({"tick": now, "accumulator": value})
    p.put(native.GAME + 0x3FA0, "I", 1900)
    count = p.events["apply_active"]
    p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
    native.require(p.events["apply_active"] == count and p.get(native.ACTIVE + 0x114, "I") == 1,
                   "new expiry did not stop native application")
    return {"opcode": opcode, "class": name, "mode": mode, "amount": amount,
            "constructor_rva": f"{ctor:X}", "uses_dice": False, "apply_rva": f"{apply:X}",
            "actor_accumulator": f"{offset:X}", "recalculations": cases,
            "lifecycle_callbacks": lifecycle,
            "hp_sensitive_policy": opcode == 10,
            "native_effect_unchanged_after_each_recalculation": True}


def check_companion(image, unicorn, registers, opcode, amount, mode, special=0):
    """Repeated native Resolve calls after expiry-only edit, including state328."""
    fields = ABILITY_STATS[opcode] if opcode in ABILITY_STATS else SKILLS.get(opcode)
    ctor = 0x1A2700 if opcode == 328 else fields[0]
    lifecycle = vtable_evidence(image, ctor)
    p = StatsMachine(image, unicorn, registers, opcode)
    p.verify_self_on_add()
    p.put(native.ACTIVE + 0x1C, "II", amount, mode)
    p.put(native.ACTIVE + 0x48, "I", special)
    original = p.read(native.ACTIVE, 0x180)
    p.put(native.ACTIVE + 0x28, "I", 1900)
    expected_object = bytearray(original)
    struct.pack_into("<I", expected_object, 0x28, 1900)
    if opcode == 328:
        offset, fmt = 0x1120 + 0xC88 + ((mode // 32) * 4 if mode < 256 else 0), "I"
        expected = (1 << (mode % 32)) if special and mode < 256 else 0
    else:
        _, base_offset, offset, fmt = fields
        base_stat = 12 if opcode in ABILITY_STATS else 50
        p.put(native.ACTOR + base_offset, "B", base_stat)
        expected = amount if mode == 1 else base_stat * amount // 100
    for now in (1000, 1450, 1501, 1899):
        p.put(native.GAME + 0x3FA0, "I", now)
        p.put(native.ACTOR + offset, fmt, 0 if opcode == 328 else 50)
        p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        native.require(p.get(native.ACTOR + offset, fmt) == expected,
                       f"{opcode}/{mode}: companion output differs")
        native.require(p.read(native.ACTIVE, 0x180) == expected_object,
                       f"{opcode}/{mode}: companion mutated original effect state")
    # A second call without stat reload establishes that traps percentage can
    # accumulate; this must not be silently advertised as native nonstacking.
    p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
    duplicate_value = p.get(native.ACTOR + offset, fmt)
    duplicate_expected = expected * amount // 100 if opcode == 91 and mode == 2 else expected
    native.require(duplicate_value == duplicate_expected, "unexpected duplicate arithmetic")
    native.require(p.read(native.ACTIVE, 0x180) == expected_object, "duplicate mutated effect")
    return {"opcode": opcode, "amount": amount, "mode": mode, "special": special,
            "native_output": expected, "duplicate_without_reload": duplicate_value,
            "lifecycle_callbacks": lifecycle, "effect_fields_stable": True,
            "ownership": "HP family companion; polarity and family policy are separate"}


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
    native.require(hashlib.sha256(binary).hexdigest() == native.SHA256, "unsupported image hash")
    pe = pefile.PE(data=binary)
    native.require(pe.OPTIONAL_HEADER.ImageBase == native.BASE, "unsupported image base")
    image = pe.get_memory_mapped_image()
    cases = [check_stat(image, unicorn, registers, opcode, amount)
             for opcode in STATS for amount in (1, 7)]
    cases += [check_stat(image, unicorn, registers, opcode, 3, 3) for opcode in range(33, 38)]
    companions = [check_companion(image, unicorn, registers, opcode, amount, mode)
                  for opcode in SKILLS for amount, mode in ((40, 1), (120, 2))]
    companions += [check_companion(image, unicorn, registers, 328, amount, 68, special)
                   for amount in (0, 1) for special in (0, 1)]
    companions += [check_companion(image, unicorn, registers, 328, 7, state, special)
                   for state in (0, 1, 127, 255, 256, 4294967295) for special in (1, 9)]
    companions += [check_companion(image, unicorn, registers, opcode, amount, mode)
                   for opcode in ABILITY_STATS for amount, mode in ((18, 1), (150, 2))]
    companions += [check_companion(image, unicorn, registers, 44, amount, 1)
                   for amount in range(19, 25)]
    print(json.dumps({"status": "passed", "sha256": native.SHA256, "cases": cases,
        "companion_cases": companions,
        "limitations": [
            "Only copied ResolveEffect/ApplyEffect; no native admission, messaging, callback trampoline or game execution.",
            "Derived-stat accumulator reset is synthetic; not proof of whole stat scheduling or all interactions.",
            "Constructor UsesDice=false is byte-verified but constructors are not invoked by these cases.",
            "CON10 state stability does not remove downstream HP sensitivity; user policy remains HP-family ignore.",
            "Safe first-call preservation for save mode3 is not permission to recreate or reset its effect.",
            "Direct application does not recursively deliver effects; outer AddEffect may still process other effects.",
            "Other modes, links, durations, protection lists, regeneration and live acceptance are separate evidence.",
        ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
