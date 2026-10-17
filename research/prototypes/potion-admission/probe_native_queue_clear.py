"""Offline native ClearMessages/destructor evidence for potion dose cleanup.

Runs copied BG2EE instructions in Unicorn, never a game process or native DLL.
Native ClearMessages and message/effect destructors execute. CPtrList RemoveHead,
string destruction and heap release are explicit synthetic service substitutes.
This establishes cancellation behavior, not a complete game load simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import probe_native_admission as native


HANDLER = native.META + 0xB000
MESSAGE = native.META + 0xB100
VTABLE = native.META + 0xB500
HP_VTABLE = native.META + 0xB600


class QueueMachine(native.Machine):
    def __init__(self, image, unicorn, registers):
        super().__init__(image, unicorn, registers, 90)
        self.queue = []
        self.order = []
        self.freed = []
        self.put(VTABLE, "Q", native.BASE + 0x1551B0)
        self.put(native.EFFECT_VTABLE, "Q", native.BASE + 0x14C8E0)
        self.put(HP_VTABLE, "Q", native.BASE + 0x1A45A0)

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x4079F0:
            native.require(self.reg_read("RCX") == HANDLER, "wrong cancellation queue")
            value = self.queue.pop(0)
            self.put(HANDLER + 0x18, "I", len(self.queue))
            self.order.append(["remove_head", value])
            self.ret(value)
            return
        if rva == 0x1551B0:
            self.order.append(["message_destroy", self.reg_read("RCX")])
        if rva in (0x14C8E0, 0x1A45A0):
            self.order.append(["effect_destroy", self.reg_read("RCX")])
        if rva in (0x20FE10, native.ADD_EFFECT, native.CHECK_ADD, native.RESOLVE):
            raise AssertionError("canceled queued effect was delivered")
        if rva == 0x40D740:
            self.ret()  # CString member destruction, no owned payload in fixture.
            return
        if rva == 0x45E690:
            self.freed.append([self.reg_read("RCX"), self.reg_read("RDX")])
            self.ret()
            return
        super().on_code(uc, address, size, data)


def run_case(image, unicorn, registers, populated):
    p = QueueMachine(image, unicorn, registers)
    entries = (native.EFFECT, native.ACTIVE, 0) if populated else ()
    if populated:
        p.put(native.ACTIVE, "Q", HP_VTABLE)
        for ordinal, effect in enumerate(entries):
            message = MESSAGE + ordinal * 0x40
            p.put(message, "Q", VTABLE)
            p.put(message + 0x10, "Q", effect)
            p.queue.append(message)
        p.queue.insert(1, 0)  # Native ClearMessages also handles null queue entries.
    p.put(HANDLER + 0x18, "I", len(p.queue))
    p.run(0x209970, HANDLER)
    native.require(not p.queue and p.get(HANDLER + 0x18, "I") == 0, "queue not emptied")
    if populated:
        destroyed = [pointer for event, pointer in p.order if event == "effect_destroy"]
        native.require(destroyed == [native.EFFECT, native.ACTIVE], "wrong effect destruction")
        native.require([size for _, size in p.freed] == [0x158, 0x20, 0x160, 0x20, 0x20],
                       "wrong original native deallocation sequence")
        for ordinal in range(len(entries)):
            native.require(p.get(MESSAGE + ordinal * 0x40 + 0x10, "Q") == 0,
                           "message retained consumed payload pointer")
    else:
        native.require(not p.freed and not p.order, "empty queue did work")
    return {"populated": populated, "cancellation_order": p.order,
            "native_heap_releases": p.freed, "delivered_effects": 0}


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
    native.require(hashlib.sha256(binary).hexdigest() == native.SHA256, "unsupported PE hash")
    image = pefile.PE(data=binary).get_memory_mapped_image()
    cases = [run_case(image, unicorn, registers, populated) for populated in (False, True)]
    print(json.dumps({"status": "passed", "sha256": native.SHA256, "cases": cases,
        "scope": "native ClearMessages/message/effect destructor cancellation only",
        "stubs": ["CPtrList RemoveHead with exact queue count", "CString member destruction",
                  "heap release recorded without freeing Unicorn synthetic memory"],
        "limitations": ["No whole LoadGame/SaveGame, Lua callbacks, network queue or engine scheduling.",
                        "LoadGame ordering is separate static call/branch evidence."]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
