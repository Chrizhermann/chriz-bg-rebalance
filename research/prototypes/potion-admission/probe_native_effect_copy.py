"""Copied native live-effect Copy versus DecodeEffectFromBase boundary evidence.

Actual opcode constructors, virtual Copy, GetItemEffect and CopyFromBase execute
in Unicorn. Allocation/free, resource/sound services and cookie helpers use the
documented linked-construction harness doubles. No game, native DLL or hook runs.
This probe observes provenance candidates; it does not propagate ownership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import probe_native_admission as native
import probe_native_linked_construction as construction
from probe_native_potion_save import projection

OPCODES = (0, 1, 10, 18, 19, 54, 83, 90, 92, 98, 142, 146, 206)


class Machine(construction.Machine):
    def __init__(self, *args, **kwargs):
        self.copy_calls, self.copy_exits, self.allocations = [], [], {}
        super().__init__(*args, **kwargs)

    def allocate(self, size):
        pointer = super().allocate(size)
        self.allocations[pointer] = size
        return pointer

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x1DCAF0:
            self.copy_calls.append({"destination": self.reg_read("RCX"),
                                    "source_base": self.reg_read("RDX"),
                                    "return_rva": self.get(self.reg_read("RSP"), "Q") - native.BASE})
        elif rva == 0x1DCCB0:
            self.copy_exits.append({"destination": self.reg_read("RDI"),
                                    "source_base": self.reg_read("RSI"),
                                    "return_rva": self.get(self.reg_read("RSP") + 0x38, "Q") - native.BASE})
        super().on_code(uc, address, size, data)


def run_probes(image, unicorn, registers):
    cases = []
    for opcode in OPCODES:
        m = Machine(image, unicorn, registers, records=[construction.raw_effect(opcode)])
        m.ability_effect()
        source = m.reg_read("RAX")
        vtable = m.get(source, "Q")
        copy_rva = m.get(vtable + 8, "Q") - native.BASE
        size = m.allocations[source]
        native.require(size in (0x158, 0x160), "unexpected class size; inspect before extending scope")
        # Active native values and intentionally different private state expose
        # reconstruction rather than raw object memcpy. No actor apply occurs.
        m.put(source + 0x24, "II", 4096, 1450)
        m.put(source + 0xCC, "I", 0)
        m.put(source + 0x110, "IIII", 123, 1, 27, 61)
        m.put(source + 0x150, "I", 456)
        for offset in (0x30, 0x70, 0x78):
            m.u.mem_write(source + offset, b"aB\0stuff")
        if opcode == 18:
            m.put(source + 0x158, "I", 77)
        original = m.read(source, size)
        m.run(copy_rva, source)
        destination = m.reg_read("RAX")
        final = m.read(destination, size)
        call, exit_ = m.copy_calls[-1], m.copy_exits[-1]
        native.require(call == exit_, "entry/exit copy boundary context differs")
        native.require(call["source_base"] == source + 8 and call["destination"] == destination,
                       "virtual Copy did not pass original object+8/new destination")
        native.require(call["return_rva"] != 0x1E2DB1, "live copy used decode-only caller")
        native.require(m.get(destination, "Q") == vtable and m.allocations[destination] == size,
                       "copy did not retain native class/layout")
        native.require(projection(final) == projection(original), "stable base projection changed")
        native.require(m.read(source, size) == original, "copy mutated original")
        native.require(m.get(destination + 0x110, "I") == 123, "source id not constructor-preserved")
        native.require(m.get(destination + 0x114, "I") == 0, "done must reset at construction")
        native.require(m.get(destination + 0x11C, "I") == 1450, "original duration reconstructed from current duration")
        native.require(m.get(destination + 0x150, "I") == 0xFFFFFFFF, "target id constructor default")
        if opcode == 18:
            native.require(m.get(destination + 0x158, "I") == 1, "HP private state constructor reset")
        cases.append({"case": "native_virtual_live_copy", "opcode": opcode,
                      "copy_rva": copy_rva, "vtable_rva": vtable - native.BASE,
                      "allocation_size": size, "copyfrombase_return_rva": call["return_rva"],
                      "source_base_is_original_plus8": True, "source_unchanged": True,
                      "source_id": m.get(destination + 0x110, "I"),
                      "done": m.get(destination + 0x114, "I"),
                      "private118": m.get(destination + 0x118, "I"),
                      "original_duration": m.get(destination + 0x11C, "I"),
                      "target_id": m.get(destination + 0x150, "I"),
                      "hp_private158": m.get(destination + 0x158, "I") if opcode == 18 else None})

        # Normal saved-buffer decode has no live source object. A second control
        # deliberately passes a live object's base to show that numeric lookup
        # alone does not distinguish the DecodeEffectFromBase caller semantics.
        for live_base in (False, True):
            buffer = source + 8 if live_base else construction.DATA + 0x10000
            if not live_base:
                m.u.mem_write(buffer, original[8:0x110])
            m.run(0x1E2D30, buffer)
            decoded = m.reg_read("RAX")
            call = m.copy_calls[-1]
            native.require(call == m.copy_exits[-1] and call["return_rva"] == 0x1E2DB1,
                           "decode exclusion return address changed")
            native.require(call["source_base"] == buffer and call["destination"] == decoded,
                           "decode CopyFromBase arguments changed")
            native.require(projection(m.read(decoded, size)) == projection(original), "decode projection changed")
            native.require(m.get(decoded + 0x110, "I") == 0xFFFFFFFF and
                           m.get(decoded + 0x11C, "I") == 0 and
                           m.get(decoded + 0x150, "I") == 0xFFFFFFFF,
                           "decode-only constructor defaults changed")
            cases.append({"case": "decode_saved_base" if not live_base else "decode_live_base_negative_control",
                          "opcode": opcode, "copyfrombase_return_rva": 0x1E2DB1,
                          "numeric_source_minus8_matches_known_live": live_base,
                          "requires_decode_exclusion": True})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    import unicorn.x86_const as registers
    data = args.exe.read_bytes()
    native.require(hashlib.sha256(data).hexdigest() == native.SHA256, "unsupported executable hash")
    cases = run_probes(pefile.PE(data=data).get_memory_mapped_image(), unicorn, registers)
    print(json.dumps({"executable_sha256": native.SHA256, "cases": cases,
                      "limits": "Native copied instructions only; successful allocator/free/resource/sound/cookie services substituted; no ownership propagation or game/DLL execution."}, indent=2))


if __name__ == "__main__":
    main()
