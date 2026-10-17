"""Offline native opcode 18/19/54 follow-up to probe_native_admission.py.

Reads a hash-pinned BG2EE image into Unicorn; never launches a game/native DLL
or changes game/save files. The admission callback is a Python test double.
Inherited stubs, synthetic lists and modelled derived-stat resets are reported
in JSON; these assertions are not native hook, dose matching or live acceptance.

Example:
  python -B probe_native_potion_opcodes.py --exe PATH --python-libs LIB_DIRECTORY

Source evidence (all addresses are RVAs in the pinned executable):
* INT Apply 1B6250: finite additive 1B63CD-1B63D8 adds to actor+2AC2.
  Finite set/percentage calculate from parameter/base INT into actor+1172.
* THAC0 Apply 1C8F90: finite additive 1C9115-1C9123 subtracts at actor+2A80;
  finite percentage 1C8FB0-1C907F reads base+5AA and writes derived+1130.
  These paths do not read or reset firstCall, Special, or another phase field.
* HP Apply 1B5600: zero dice bypasses the RNG loop; percentage 1B58FC-1B598D
  grants current HP only when maximum increases, private+158==1, Special bit0=0.
  It sets Special bit0. That original first-use state must never be recreated.
* CheckAdd success 1CD1AF precedes OnAdd/DisplayString; redirect to1CC9A5 with
  noSave=false rejects the new effect before ResolveEffect/ApplyEffect.
* ResolveEffect active timing4096 compares unsigned now >= effect+28 at
  1E8478-1E8487. Thus changing only +28 changes the deadline without replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import probe_native_admission as shared


# Extend the imported probe's in-memory dispatch table only. Its file is not
# changed, and all admission/timing/engine-service instrumentation is reused.
APPLICATIONS = {18: 0x1B5600, 19: 0x1B6250, 54: 0x1C8F90}
shared.APPLY.update(APPLICATIONS)
OBJECT_SIZE = 0x180  # Includes HP's private first-use field at +158.
require = shared.require


class OpcodeMachine(shared.Machine):
    def __init__(self, image, unicorn, registers, opcode, amount, mode):
        self.hp_ignore = False
        self.amount, self.mode = amount, mode
        super().__init__(image, unicorn, registers, opcode)
        for address in (shared.EFFECT, shared.ACTIVE, shared.OTHER):
            self.configure(address)

    def configure(self, address):
        self.put(address + 0x1C, "II", self.amount, self.mode)
        self.put(address + 0x38, "II", 0, 0)  # Zero dice, no mutable rolled amount.
        self.put(address + 0x158, "I", 1 if self.opcode == 18 else 0)

    def incoming(self):
        self.u.mem_write(shared.EFFECT, bytes(OBJECT_SIZE))
        self.make_effect(shared.EFFECT, self.opcode)
        self.configure(shared.EFFECT)

    def candidate_callback(self):
        if not self.hp_ignore:
            return super().candidate_callback()
        require(self.reg_read("RDI") == shared.EFFECT, "incoming ABI changed")
        require(self.reg_read("R14") == shared.ACTOR, "target ABI changed")
        self.events["candidate_hook"] += 1
        # The fixture supplies an already-latched repeated-family decision.
        # No matching, effect edits, removals or refresh happen on this branch.
        self.reg_write("RIP", shared.BASE + shared.REJECT)

    def seed_stats(self):
        self.put(shared.ACTOR + 0x792, "B", 12)  # Base INT.
        self.put(shared.ACTOR + 0x1172, "h", 12)
        self.put(shared.ACTOR + 0x2AC2, "h", 0)
        self.put(shared.ACTOR + 0x5AA, "b", 20)  # Base THAC0.
        self.put(shared.ACTOR + 0x1130, "h", 20)
        self.put(shared.ACTOR + 0x2A80, "h", 0)

    def benefit(self):
        if self.opcode == 19:
            field = 0x2AC2 if self.mode == 0 else 0x1172
        else:
            field = 0x2A80 if self.mode == 0 else 0x1130
        return self.get(shared.ACTOR + field, "h")

    def hp(self):
        return {
            "current": self.get(shared.ACTOR + 0x57C, "h"),
            "base_maximum": self.get(shared.ACTOR + 0x57E, "h"),
            "derived_maximum": self.get(shared.ACTOR + 0x1124, "h"),
        }


def no_new_application(p, before):
    for event in ("on_add", "display_string", "resolve_incoming", "apply_incoming", "on_remove"):
        require(p.events[event] == before[event], f"duplicate received {event}")
    require(p.events["destroy_incoming"] == before["destroy_incoming"] + 1,
            "rejected incoming effect was not disposed by native AddEffect")
    require(p.check_add_result == 0, "CheckAdd did not return native rejection")


def safe_case(image, unicorn, registers, opcode, amount, mode, expected):
    p = OpcodeMachine(image, unicorn, registers, opcode, amount, mode)
    p.seed_stats()
    p.put(shared.GAME + 0x3FA0, "I", 550)
    p.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 0, 1)
    require(p.events["apply_incoming"] == 1, "first original opcode was not applied")
    require(p.benefit() == expected, "first native benefit differs from source arithmetic")
    require(p.get(shared.EFFECT + 0x28, "I") == 1450, "first native expiry is wrong")
    # The native list allocator is stubbed. Place the just-accepted object in
    # the synthetic active-list slot; this is not engine object-copy testing.
    p.u.mem_write(shared.ACTIVE, p.read(shared.EFFECT, OBJECT_SIZE))
    p.incoming()
    p.put(shared.GAME + 0x3FA0, "I", 1000)
    old = p.read(shared.ACTIVE, OBJECT_SIZE)
    actor = p.read(shared.ACTOR, 0x6000)
    lists = p.list_snapshot()
    events = p.events.copy()
    p.refresh = True
    p.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 0, 1)
    no_new_application(p, events)
    expected_object = bytearray(old)
    struct.pack_into("<I", expected_object, 0x28, 1900)
    require(p.read(shared.ACTIVE, OBJECT_SIZE) == expected_object,
            "refresh changed a field other than active expiry")
    require(p.callback_writes == [(shared.ACTIVE + 0x28, 4, 1900)], "extra policy write")
    require(p.read(shared.ACTOR, 0x6000) == actor, "rejection altered actor state")
    require(p.list_snapshot() == lists, "refresh changed synthetic list state")

    observations = []
    for now in (1450, 1500, 1899):
        p.put(shared.GAME + 0x3FA0, "I", now)
        p.seed_stats()  # Explicit synthetic replacement for a full stat reload.
        before = p.read(shared.ACTIVE, OBJECT_SIZE)
        p.run(shared.RESOLVE, shared.ACTIVE, shared.ACTOR)
        require(p.benefit() == expected, "extended original did not recalculate benefit")
        require(p.read(shared.ACTIVE, OBJECT_SIZE) == before,
                "recalculation consumed or reset an active effect field")
        observations.append({"world_time": now, "native_benefit": p.benefit()})
    p.put(shared.GAME + 0x3FA0, "I", 1900)
    p.seed_stats()
    calls = p.events["apply_active"]
    p.run(shared.RESOLVE, shared.ACTIVE, shared.ACTOR)
    require(p.get(shared.ACTIVE + 0x114, "I") == 1, "extended effect did not expire")
    require(p.events["apply_active"] == calls, "expired effect applied again")
    return {"opcode": opcode, "amount": amount, "mode": mode,
            "old_expiry": 1450, "new_expiry": 1900, "observations": observations,
            "only_policy_write": "active+28 (absolute expiry)",
            "effect_fields_unchanged_during_recalculation": True}


def hp_case(image, unicorn, registers, percent, repeat_current):
    p = OpcodeMachine(image, unicorn, registers, 18, percent, 2)
    p.put(shared.ACTOR + 0x57C, "hh", 80, 100)
    p.put(shared.ACTOR + 0x1124, "h", 100)
    p.put(shared.ACTOR + 0x1DCC, "h", 100)  # Previous maximum.
    p.put(shared.GAME + 0x3FA0, "I", 550)
    first_input = p.read(shared.EFFECT, OBJECT_SIZE)
    p.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 0, 1)
    first = p.hp()
    require(first == {"current": percent - 20, "base_maximum": 100,
                      "derived_maximum": percent}, "native percentage HP grant differs")
    require(p.get(shared.EFFECT + 0x48, "I") & 1, "native first-use flag was not set")
    require(p.get(shared.EFFECT + 0x1C, "I") == percent, "zero-dice HP amount changed")
    require(p.events["apply_incoming"] == 1 and not p.callback_writes,
            "first dose did not use original native application")
    # The candidate made no first-dose edits; only native timing and opcode state
    # may change. Retain the complete accepted native object for the repeat.
    require(p.read(shared.EFFECT + 0x90, 0x44) == first_input[0x90:0xD4],
            "first-dose native source/level metadata changed")
    p.u.mem_write(shared.ACTIVE, p.read(shared.EFFECT, OBJECT_SIZE))
    p.incoming()
    p.put(shared.GAME + 0x3FA0, "I", 1000)
    p.put(shared.ACTOR + 0x57C, "h", repeat_current)
    p.put(shared.ACTOR + 0x1DCC, "h", percent)
    old = p.read(shared.ACTIVE, OBJECT_SIZE)
    actor = p.read(shared.ACTOR, 0x6000)
    lists = p.list_snapshot()
    events = p.events.copy()
    p.hp_ignore = True
    p.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 0, 1)
    no_new_application(p, events)
    require(p.read(shared.ACTIVE, OBJECT_SIZE) == old,
            "HP repeat modified old expiry or first-use/native fields")
    require(p.read(shared.ACTOR, 0x6000) == actor, "HP repeat healed or clamped actor state")
    require(p.list_snapshot() == lists and not p.callback_writes,
            "HP repeat mutated list or effect")
    return {"opcode": 18, "mode": 2, "amount": percent, "dice": 0,
            "first_application": first, "repeat_current_hp": repeat_current,
            "repeat_actor_bytes_unchanged": True, "repeat_active_bytes_unchanged": True,
            "unchanged_expiry": p.get(shared.ACTIVE + 0x28, "I")}


def hp_negative_control(image, unicorn, registers):
    p = OpcodeMachine(image, unicorn, registers, 18, 120, 2)
    p.put(shared.ACTOR + 0x57C, "hh", 50, 100)
    p.put(shared.ACTOR + 0x1124, "h", 120)
    p.put(shared.ACTOR + 0x1DCC, "h", 120)
    p.hp_ignore = True
    p.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 1, 1)
    require(p.check_add_result == 0 and p.events["apply_incoming"] == 1,
            "noSave=true did not reproduce the rejection override")
    require(p.hp()["current"] == 70 and p.hp()["derived_maximum"] == 140,
            "unchecked HP duplicate negative control changed")
    return {"noSave": True, "native_rejection_overridden": True, "hp_after": p.hp()}


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
    require(hashlib.sha256(binary).hexdigest() == shared.SHA256, "unsupported executable hash")
    pe = pefile.PE(data=binary)
    require(pe.OPTIONAL_HEADER.ImageBase == shared.BASE, "unexpected image base")
    image = pe.get_memory_mapped_image()
    for rva, value in shared.SIGNATURES.items():
        signature = bytes.fromhex(value)
        require(image[rva:rva + len(signature)] == signature, f"signature mismatch at {rva:X}")
    safe = [safe_case(image, unicorn, registers, *case) for case in (
        (19, 4, 0, 4), (19, 3, 0, 3), (19, 18, 1, 18), (19, 150, 2, 18),
        (54, 2, 0, -2), (54, 3, 0, -3), (54, 15, 1, 15),
        (54, 90, 2, 18), (54, 80, 2, 16),
    )]
    hp = [hp_case(image, unicorn, registers, percent, current)
          for percent in (110, 120) for current in (1, 50, percent)]
    result = {
        "status": "passed", "executable_sha256": shared.SHA256,
        "scope": "copied native opcode/admission/timing instructions with synthetic services",
        "expiry_only_cases": safe, "hp_ignore_cases": hp,
        "negative_control": hp_negative_control(image, unicorn, registers),
        "native_apply_rvas": {str(k): f"{v:X}" for k, v in APPLICATIONS.items()},
        "stubs": {f"{rva:X}": text for rva, text in shared.STUBS.items()},
        "limitations": [
            "Python admission callback test double; no EEex hook or native process was executed.",
            "Read-only exact active match and HP family decision are supplied by fixtures, not derived by a runtime registry.",
            "Native list allocation, OnAdd/display/destruction services and full derived-stat reload are substituted as in the shared probe.",
            "Stat accumulator reset before each revisit is explicit synthetic preparation, not a proof of full ProcessEffectList ordering.",
            "NoSave must be false; true overrides rejection and reproduces an HP duplicate grant.",
            "Finite immediate direct records only; no rolled HP, linked177, save/load, dispel, multiplayer, or live-game acceptance.",
            "The tested 19/54 state mechanics do not establish family identity, beneficial polarity, or blanket eligibility for all parameter modes.",
        ],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
