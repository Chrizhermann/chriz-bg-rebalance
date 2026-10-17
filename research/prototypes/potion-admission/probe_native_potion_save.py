"""Copied-instruction V2 save/copy evidence for future linked-effect provenance.

No game, native DLL, installed resource or save is written or executed. Actual
CGameEffectList::Marshal and CopyFromBase execute in Unicorn. Heap allocation,
memset and the MSVC cookie helper are explicit services. EEex's footer/import
handlers are inspected separately; this probe does not execute their DLL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import probe_native_admission as native

LIST = native.ACTOR + 0x4A00
BUFFER = native.META + 0xA000
OUT = native.META + 0xD000


def projection(body):
    """Runtime10..D3 fields actually restored; normalize native resref uppercase."""
    data = bytearray(body)
    for offset in (0x30, 0x70, 0x78):
        raw = bytes(data[offset:offset + 8])
        text = raw.split(b"\0", 1)[0].upper()
        data[offset:offset + 8] = text.ljust(8, b"\0")
    return bytes(data[0x10:0x50] + data[0x54:0xD4])


class SaveMachine(native.Machine):
    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x4F77C4:
            requested = self.reg_read("RCX")
            native.require(0 < requested <= 0x1000, "unexpected allocation")
            self.allocated = requested
            self.ret(BUFFER)
            return
        if rva == 0x4FAB70:
            destination, value, length = self.reg_read("RCX"), self.reg_read("RDX"), self.reg_read("R8")
            native.require(length <= 0x200, "unbounded memset")
            if length:
                self.u.mem_write(destination, bytes([value & 255]) * length)
            self.ret(destination)
            return
        super().on_code(uc, address, size, data)


def run_case(image, unicorn, registers, timings, only_nine, exclude_two):
    p = SaveMachine(image, unicorn, registers)
    original = []
    for ordinal, timing in enumerate(timings):
        pointer = native.EFFECT + ordinal * 0x400
        data = bytearray((i * 17 + ordinal * 11) % 256 for i in range(0x158))
        p.u.mem_write(pointer, bytes(data))
        p.put(pointer + 0x10, "I", 90)
        p.put(pointer + 0x24, "I", timing)
        p.put(pointer + 0x28, "I", 500)
        p.put(pointer + 0x114, "I", ordinal % 2)  # Done is NOT a marshal filter.
        for offset in (0x30, 0x70, 0x78):
            p.u.mem_write(pointer + offset, b"ab\0stuff")
        p.u.mem_write(pointer + 0x94, b"SOURCE\0\0")
        original.append(p.read(pointer, 0x158))
        node = native.NODES + ordinal * 0x30
        p.put(node, "QQQ", node + 0x30 if ordinal + 1 < len(timings) else 0,
              node - 0x30 if ordinal else 0, pointer)
    p.put(LIST + 8, "QQI", native.NODES if timings else 0,
          native.NODES + (len(timings) - 1) * 0x30 if timings else 0, len(timings))
    p.run(0x1E50E0, LIST, OUT, 1, only_nine, exclude_two)
    selected = [i for i,timing in enumerate(timings)
                if (not only_nine or timing == 9) and (not exclude_two or timing != 2)]
    native.require(p.reg_read("EAX") == len(selected) * 0x108, "wrong serialized size")
    actual = p.read(BUFFER, len(selected) * 0x108) if selected else b""
    expected = b"".join(original[i][8:0x110] for i in selected)
    native.require(actual == expected, "marshal did not preserve selected native order/bytes")
    # Execute the real field restoration, including case/padding normalization.
    for ordinal, source_index in enumerate(selected):
        destination = native.EFFECT + 0x3000
        p.u.mem_write(destination, b"\xa5" * 0x158)
        p.run(0x1DCAF0, destination, BUFFER + ordinal * 0x108)
        restored = p.read(destination, 0x158)
        native.require(projection(restored) == projection(original[source_index]), "restored projection differs")
        native.require(restored[0x50:0x54] == b"\xa5" * 4, "padding unexpectedly restored")
        native.require(restored[0xD4:0x158] == b"\xa5" * (0x158 - 0xD4), "runtime tail unexpectedly restored")
    return {"timings": timings, "only_timing9": bool(only_nine), "exclude_timing2": bool(exclude_two),
            "serialized_indices": selected, "serialized_bytes": len(actual), "restored_projections": len(selected)}


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
    image = pefile.PE(data=data).get_memory_mapped_image()
    cases = [run_case(image, unicorn, registers, timings, nine, two)
             for timings in ([], [4096, 2, 9, 4096], [9, 4096, 4096, 2])
             for nine in (0, 1) for two in (0, 1)]
    print(json.dumps({"executable_sha256": native.SHA256, "cases": cases,
                      "limits": "Unicorn native marshal/copy only; allocator/memset/cookie services substituted; no EEex DLL or game save."}, indent=2))


if __name__ == "__main__":
    main()
