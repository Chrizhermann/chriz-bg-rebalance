"""Copied native opcode142 lifecycle/expiry probe; no game or DLL execution.

Runs ResolveEffect, Apply142, AddPortraitIcon and its native duplicate scan.
Resource/string/render constructors and allocator/list-node services are test
doubles. This proves descriptor/lifetime behavior, not icon art/UI rendering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import probe_native_admission as native
from probe_native_potion_stats import StatsMachine, vtable_evidence

native.APPLY[142] = 0x1BC5E0
HEAP = 0x700000000
ICON_LIST = native.ACTOR + 0x4CC0


class IconMachine(StatsMachine):
    def __init__(self, image, unicorn, registers):
        super().__init__(image, unicorn, registers, 142)
        self.u.mem_map(HEAP, 0x10000)
        self.alloc = HEAP
        self.nodes = HEAP + 0x8000

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x4F7A88:
            pointer = self.alloc
            self.alloc += (self.reg_read("RCX") + 0xFF) & ~0xFF
            self.events["allocated_icon"] += 1
            self.ret(pointer)
            return
        if rva == 0x4075C0 and self.reg_read("RCX") == ICON_LIST:
            node = self.nodes
            self.nodes += 0x30
            tail = self.get(ICON_LIST + 0x10, "Q")
            self.put(node, "QQQ", 0, tail, self.reg_read("RDX"))
            self.put(tail if tail else ICON_LIST + 8, "Q", node)
            self.put(ICON_LIST + 0x10, "Q", node)
            self.put(ICON_LIST + 0x18, "I", self.get(ICON_LIST + 0x18, "I") + 1)
            self.ret(node)
            return
        if rva in (0x3FE9C0, 0x3FD6B0, 0x3FD640, 0x3FD810, 0x3FF710):
            self.put(self.reg_read("RCX"), "Q", HEAP + 0xF000)
            self.ret(self.reg_read("RCX"))
            return
        if rva == 0x410E10:
            self.u.mem_write(self.reg_read("RCX"), bytes(0x138))
            self.ret(self.reg_read("RCX"))
            return
        if rva == 0x1151E0:
            self.ret(HEAP + 0xF000)
            return
        if rva == 0x503D4C:
            self.ret(1)
            return
        if rva in (0x410F70, 0x3FD740, 0x411200, 0x3FF880, 0x276570, 0x407B40):
            self.ret()
            return
        super().on_code(uc, address, size, data)


def run_probes(image, unicorn, registers):
    lifecycle = vtable_evidence(image, 0x1A1300)
    cases = []
    for icon in (0, 16, 22, 79, 200):
        for amount in (0, 7):
            p = IconMachine(image, unicorn, registers)
            p.verify_self_on_add()
            p.put(native.ACTIVE + 0x1C, "II", amount, icon)
            original = p.read(native.ACTIVE, 0x158)
            p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
            native.require(p.read(native.ACTIVE, 0x158) == original, "first Apply142 changed descriptor")
            native.require(p.get(ICON_LIST + 0x18, "I") == int(icon != 79), "native icon count wrong")
            allocations = p.events["allocated_icon"]
            p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
            native.require(p.events["allocated_icon"] == allocations,
                           "native duplicate icon scan allocated another icon")
            p.put(native.ACTIVE + 0x28, "I", 1900)
            extended = p.read(native.ACTIVE, 0x158)
            # Actual ProcessEffectList does RemoveAll4CC0 at3AC4A7 before its
            # timed-list applications. Run that native list clear each pass.
            for now in (1450, 1899):
                p.put(native.GAME + 0x3FA0, "I", now)
                p.run(0x407930, ICON_LIST)
                p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
                native.require(p.read(native.ACTIVE, 0x158) == extended, "expiry refresh changed state")
                native.require(p.get(ICON_LIST + 0x18, "I") == int(icon != 79), "icon not rebuilt")
            p.put(native.GAME + 0x3FA0, "I", 1900)
            p.run(0x407930, ICON_LIST)
            before_apply = p.events["apply_active"]
            p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
            native.require(p.events["apply_active"] == before_apply and p.get(ICON_LIST + 0x18, "I") == 0,
                           "expired icon was reapplied")
            native.require(p.get(native.ACTIVE + 0x114, "I") == 1, "expired icon not marked done")
            cases.append({"icon": icon, "amount_ignored": amount, "special_case_inert": icon == 79,
                          "original_stable": True, "native_duplicate_singular": True,
                          "expiry_extension_survives_old_deadline": True})
    return {"constructor": "1A1300", "usesDice": False, "lifecycle": lifecycle,
            "cases": cases,
            "limitations": ["UI resource/string/render helper results are synthetic.",
                            "No full ProcessEffectList or live UI execution.",
                            "Icons are package metadata, not proof of beneficial polarity or active HP duration."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    from unicorn import x86_const
    data = args.exe.read_bytes()
    native.require(hashlib.sha256(data).hexdigest() == native.SHA256, "unreviewed executable")
    result = run_probes(pefile.PE(data=data).get_memory_mapped_image(), unicorn, x86_const)
    result["exe_sha256"] = native.SHA256
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
