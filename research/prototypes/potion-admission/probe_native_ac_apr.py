"""Pinned, offline AC0/APR1 instruction and finite-expiry-state probe.

No game, DLL or hook execution. Uses the existing admission probe's synthetic
objects and the stat probe's no-recursive-delivery check. Actual Apply, Resolve,
APR encoding helpers and base OnAdd execute in Unicorn. This is not a complete
stat rebuild/admission or classifier implementation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native
from probe_native_potion_stats import StatsMachine, vtable_evidence

APPLY = {0: 0x1A5F70, 1: 0x1A7330}
CTORS = {0: 0x19DE10, 1: 0x19E110}
AC_FIELDS = {0: 0x2A76, 1: 0x2A78, 2: 0x2A7A, 4: 0x2A7C, 8: 0x2A7E, 16: 0x1126}
APR_FIELD = 0x2A82
native.APPLY.update(APPLY)


def signed16(value):
    return struct.unpack("<h", struct.pack("<H", value & 0xFFFF))[0]


def decode_apr(value):
    value = signed16(value)
    magnitude = abs(value)
    result = magnitude if magnitude <= 5 else magnitude - 5.5 if 6 <= magnitude <= 10 else 0
    return -result if value < 0 else result


def encode_apr(value):
    magnitude = float(min(abs(value), 5))
    encoded = int(magnitude) if magnitude.is_integer() else int(magnitude + 5.5)
    return -encoded if value < 0 else encoded


def unchanged_except(before, after, offset, width, expected, fmt="h"):
    permitted = bytearray(before)
    struct.pack_into("<" + fmt, permitted, offset, expected)
    native.require(after == bytes(permitted), f"unrelated actor data changed, expected field {offset:X}")


def machine(image, unicorn, registers, opcode, amount, mode):
    p = StatsMachine(image, unicorn, registers, opcode)
    p.verify_self_on_add()
    p.put(native.ACTIVE + 0x1C, "II", amount & 0xFFFFFFFF, mode)
    p.put(native.ACTIVE + 0xCC, "I", 1)
    return p


def check_case(image, unicorn, registers, opcode, amount, mode):
    p = machine(image, unicorn, registers, opcode, amount, mode)
    field = AC_FIELDS[mode] if opcode == 0 else APR_FIELD
    start = 10 if opcode == 0 and mode == 16 else 0
    p.put(native.ACTOR + field, "h", start)
    effect_before = p.read(native.ACTIVE, 0x180)
    outputs = []
    expected = start
    for call in range(2):
        actor_before = p.read(native.ACTOR, 0x6000)
        p.run(APPLY[opcode], native.ACTIVE, native.ACTOR)
        if opcode == 0:
            expected = min(expected, signed16(amount)) if mode == 16 else signed16(expected - signed16(amount))
        else:
            expected = encode_apr(float(decode_apr(expected) + decode_apr(amount)))
        actual = p.get(native.ACTOR + field, "h")
        native.require(actual == expected, f"wrong native {opcode}/{mode}/{amount} result: {actual} != {expected}")
        unchanged_except(actor_before, p.read(native.ACTOR, 0x6000), field, 2, expected)
        native.require(p.read(native.ACTIVE, 0x180) == effect_before,
                       f"finite Apply mutated effect state for {opcode}/{mode}/{amount}")
        outputs.append(actual)

    # Change only native expiry; re-evaluate with a fresh synthetic stat base.
    # The same native effect record survives all these resolutions.
    p.put(native.ACTIVE + 0x28, "I", 1900)
    expected_effect = bytearray(effect_before)
    struct.pack_into("<I", expected_effect, 0x28, 1900)
    # The expiry test represents an already-processed effect. Do not reset its
    # native firstCall field as part of a refresh.
    p.put(native.ACTIVE + 0xCC, "I", 0)
    struct.pack_into("<I", expected_effect, 0xCC, 0)
    for now in (1000, 1501, 1899):
        p.put(native.GAME + 0x3FA0, "I", now)
        p.put(native.ACTOR + field, "h", start)
        actor_before = p.read(native.ACTOR, 0x6000)
        p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        native.require(p.get(native.ACTOR + field, "h") == outputs[0], "refresh changed stat result")
        unchanged_except(actor_before, p.read(native.ACTOR, 0x6000), field, 2, outputs[0])
        native.require(p.read(native.ACTIVE, 0x180) == bytes(expected_effect), "Resolve changed processed effect")
    p.put(native.GAME + 0x3FA0, "I", 1900)
    calls = p.events["apply_active"]
    p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
    native.require(p.events["apply_active"] == calls and p.get(native.ACTIVE + 0x114, "I") == 1,
                   "expiry boundary reapplied stat")
    return {"opcode": opcode, "mode": mode, "raw_amount": amount,
            "native_signed16": signed16(amount), "field": f"{field:X}",
            "first_and_repeat": outputs,
            "decoded_apr": [decode_apr(v) for v in outputs] if opcode == 1 else None,
            "finite_effect_stable": True, "expiry_only_rebuild_stable": True}


def controls(image, unicorn, registers):
    result = []
    for mode in (3, 5, 6, 7, 9, 15, 17, 0xFFFFFFFF):
        p = machine(image, unicorn, registers, 0, 10, mode)
        effect, actor = p.read(native.ACTIVE, 0x180), p.read(native.ACTOR, 0x6000)
        p.run(APPLY[0], native.ACTIVE, native.ACTOR)
        native.require(p.read(native.ACTIVE, 0x180) == effect and p.read(native.ACTOR, 0x6000) == actor,
                       "unsupported AC combination unexpectedly applied")
        result.append({"case": "AC_exact_mode_not_bitmask", "mode": mode, "native_noop": True})
    # A mode3 APR record elsewhere suppresses this additive Apply. Preserve the
    # native interaction; it does not turn ordinary mode0 into a no-op generally.
    for list_offset in (0x49B0, 0x4A00):
        p = machine(image, unicorn, registers, 1, 1, 0)
        p.put(native.OTHER + 0x20, "I", 3)
        p.put(native.ACTOR + 0x4A08, "Q", 0)
        p.put(native.ACTOR + list_offset + 8, "Q", native.NODES)
        p.put(native.NODES, "QQQ", 0, 0, native.OTHER)
        effect, actor = p.read(native.ACTIVE, 0x180), p.read(native.ACTOR, 0x6000)
        p.run(APPLY[1], native.ACTIVE, native.ACTOR)
        native.require(p.read(native.ACTIVE, 0x180) == effect and p.read(native.ACTOR, 0x6000) == actor,
                       "native APR mode3 suppression lost")
        result.append({"case": "APR_mode3_present", "list": f"{list_offset:X}", "native_suppression": True})
    # Permanent timing is explicitly outside finite refresh. Show the distinct
    # base-stat mutation and done/repass fields instead of extrapolating safety.
    for opcode, mode, amount, offset, fmt, initial, expected in (
            (0, 0, 10, 0x5A0, "h", 10, 0), (0, 16, 2, 0x5A0, "h", 10, 2),
            (1, 0, 1, 0x5AB, "B", 1, 2)):
        p = machine(image, unicorn, registers, opcode, amount, mode)
        p.put(native.ACTIVE + 0x24, "I", 1)
        p.put(native.ACTOR + offset, fmt, initial)
        p.run(APPLY[opcode], native.ACTIVE, native.ACTOR)
        native.require(p.get(native.ACTOR + offset, fmt) == expected and
                       p.get(native.ACTIVE + 0x114, "I") == p.get(native.ACTIVE + 0x118, "I") == 1,
                       "permanent timing negative control changed")
        result.append({"case": "permanent_base_mutation", "opcode": opcode, "mode": mode})
    return result


def run_probes(image, unicorn, registers):
    lifecycle = {str(op): vtable_evidence(image, ctor) for op, ctor in CTORS.items()}
    table = [struct.unpack_from("<I", image, 0x1A6208 + i * 4)[0] for i in range(17)]
    expected = {0: 0x1A5F91, 1: 0x1A5FF7, 2: 0x1A605D, 4: 0x1A60C3, 8: 0x1A6129, 16: 0x1A618F}
    native.require(table == [expected.get(i, 0x1A6201) for i in range(17)], "AC dispatch table changed")
    cases = []
    for mode in (0, 1, 2, 4, 8):
        for amount in (0, 1, -1, 10, -10, 65537, -65535, 65535):
            cases.append(check_case(image, unicorn, registers, 0, amount, mode))
    for amount in (0, 2, -10, 12, 65538, 65535):
        cases.append(check_case(image, unicorn, registers, 0, amount, 16))
    for amount in (*range(-11, 12), 65537, -65535, 65535, 32767, -32768):
        cases.append(check_case(image, unicorn, registers, 1, amount, 0))
    return {"cases": cases, "controls": controls(image, unicorn, registers),
            "lifecycle": lifecycle, "uses_dice": False,
            "limits": [
                "Synthetic actors/effects/stat bases and prior probe stubs; actual Apply/Resolve/OnAdd and APR numeric helpers execute.",
                "No whole ProcessEffectList, admission, scheduler, native effect destruction or save/load emulation here.",
                "Destructor/OnRemove/class OnAdd identity verified from constructor-installed native vtables, not replaced as evidence.",
                "AC finite modes0/1/2/4/8/16 and APR finite mode0 are tested; APR1/2/3 policy is not established by this probe.",
                "Signed16 arithmetic/encoding is native. Extreme accumulator overflow and global final-stat clamping are not classified here.",
                "No game process, EEex DLL, install, source resource or save modification.",
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
    native.require(hashlib.sha256(binary).hexdigest() == native.SHA256, "unsupported executable")
    pe = pefile.PE(data=binary)
    native.require(pe.OPTIONAL_HEADER.ImageBase == native.BASE, "unsupported image base")
    result = run_probes(pe.get_memory_mapped_image(), unicorn, registers)
    result.update(status="passed", executable_sha256=native.SHA256,
                  native_stat_cases=len(result["cases"]), control_cases=len(result["controls"]))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
