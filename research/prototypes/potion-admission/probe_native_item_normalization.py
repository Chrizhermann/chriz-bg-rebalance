"""Pinned direct-ITM DecodeEffect sentinel proof; no game/resource/save writes.

Uses the shared construction harness but executes actual CResItem::Parse,
CItem::GetAbilityEffect, DecodeEffect and opcode/base constructors.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

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

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256, "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
ITEM = construction.SPELL + 0x500
cases = []
for opcode in (18, 19, 90, 142):
    for raw_size in (0, 65535, 65536, 0xFFFFFFFE, 0xFFFFFFFF):
        raw = construction.raw_effect(opcode, dice_count=0, dice_size=raw_size)
        original = bytes(raw)
        m = construction.Machine(image, unicorn, x86_const, records=[raw])
        m.u.mem_write(construction.DATA, b"ITM V1  ")
        m.u.mem_write(m.header_address, bytes(0x38))
        m.put(m.header_address, "B", 3)
        m.put(m.header_address + 0xC, "B", 5)
        m.put(m.header_address + 0x1E, "HH", 1, 0)
        m.put(ITEM + 8, "Q", construction.RESOURCE)
        m.u.mem_write(ITEM + 0x10, b"POTN36\0\0")
        m.run(0x114CF0, construction.RESOURCE, construction.DATA)
        n.require(m.reg_read("AL") == 1, "synthetic ITM parse failed")
        m.run(0x1FB410, ITEM, 0, 0, 0)
        pointer = m.reg_read("RAX")
        n.require(pointer != 0 and m.decoded == [0], "item did not reach original DecodeEffect")
        row = m.snapshot(pointer)
        expected = 0 if raw_size == 0xFFFFFFFF else raw_size
        n.require(m.get(m.fx_address + 0x20, "I") == expected, "wrong exact raw sentinel normalization")
        n.require(row["source_type"] == 2 and row["caster_level"] == 10, "not native ITM delivery")
        n.require(row["source_resource_hex"] == b"POTN36\0\0".hex(), "item source identity changed")
        n.require(row["dice_size"] == (expected if opcode == 18 else 0), "dice size mapping wrong")
        n.require(row["min_level"] == (0 if opcode == 18 else expected), "minimum level mapping wrong")
        n.require(bytes(raw) == original, "immutable source fixture was changed")
        cases.append(dict(opcode=opcode, raw_dword20=raw_size,
                          runtime_dice_size=row["dice_size"], runtime_min_level=row["min_level"],
                          source_type=row["source_type"], caster_level=row["caster_level"]))
print(json.dumps(dict(exe_sha256=n.SHA256, count=len(cases), cases=cases,
    limitations=["Native item selection, DecodeEffect and constructors execute; surrounding allocator/resource demand services are test doubles.",
                 "Synthetic in-memory resource buffer is natively normalized; original fixture bytes and all disk resources remain unchanged.",
                 "No Apply/admission, game process, generated hook, installation or save/load execution."]), indent=2))
