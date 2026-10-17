"""Offline318 linked-branch guard registration and non-consuming native lookup.

Predicate outcomes and list allocation are controlled services. Native Apply,
Resolve, resource copying and FindRes execute. No game, resources or saves change.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exe", type=Path, required=True)
parser.add_argument("--python-libs", type=Path)
args = parser.parse_args()
if args.python_libs:
    sys.path.insert(0, str(args.python_libs))
import pefile, unicorn
from unicorn import x86_const
import probe_native_admission as n
from probe_native_potion_stats import StatsMachine, vtable_evidence

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == n.SHA256, "unreviewed executable")
image = pefile.PE(str(args.exe)).get_memory_mapped_image()
n.APPLY[318] = 0x1B69A0
n.STUBS.pop(0x1F8C90)


class GuardMachine(StatsMachine):
    def __init__(self, condition):
        super().__init__(image, unicorn, x86_const, 318)
        self.condition = condition
        self.allocation = 0x740000000
        self.u.mem_map(self.allocation, 0x10000)
        self.entries = []
        self.put(n.ACTIVE + 0x1C, "II", 0, 0)
        self.put(n.ACTIVE + 0x110, "I", 0xFFFFFFFF)

    def allocate(self):
        pointer = self.allocation
        self.allocation += 0x20
        return pointer

    def on_code(self, uc, address, size, data):
        rva = address - n.BASE
        if rva in (0x40D580, 0x40D740, 0x3FD740):
            self.ret(0)  # Local CString/CPoint-list setup/cleanup services.
            return
        if rva == 0x24A3C0:
            n.require(self.reg_read("EDX") == 0 and self.reg_read("R8") == n.ACTOR,
                      "unexpected protection predicate arguments")
            n.require(self.get(self.reg_read("RSP") + 0x28, "I") == 0,
                      "unexpected predicate operand")
            self.ret(int(self.condition))
            return
        if rva == 0x4F7A88:
            n.require(self.reg_read("RCX") == 0x10, "unexpected guard allocation")
            self.ret(self.allocate())
            return
        if rva == 0x4075C0:
            n.require(self.reg_read("RCX") == n.ACTOR + 0x1880, "unexpected resource immunity list")
            pointer, node = self.reg_read("RDX"), self.allocate()
            self.put(node, "QQQ", 0, self.entries[-1][0] if self.entries else 0, pointer)
            if self.entries:
                self.put(self.entries[-1][0], "Q", node)
            else:
                self.put(n.ACTOR + 0x1888, "Q", node)
            self.entries.append((node, pointer))
            self.ret(node)
            return
        super().on_code(uc, address, size, data)


results = []
lifecycle = vtable_evidence(image, 0x1A03C0)
for resource in ("DWTRRG2", "DWTRRG4", "DWTRRG12", "DWTFRG2", "OTHER"):
    for condition in (False, True):
        p = GuardMachine(condition)
        p.verify_self_on_add()
        p.u.mem_write(n.ACTIVE + 0x30, resource.encode().ljust(8, b"\0"))
        p.put(n.ACTIVE + 0xCC, "I", 1)
        p.put(n.ACTIVE + 0x28, "I", 1900)
        original = p.read(n.ACTIVE, 0x180)
        if not condition:
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            expected = bytearray(original)
            struct.pack_into("<I", expected, 0x114, 1)
            n.require(p.read(n.ACTIVE, 0x180) == expected, "failed guard changed more than Done")
            n.require(not p.entries, "failed predicate registered protection")
        else:
            for now in (1000, 1450, 1501, 1899):
                p.put(n.GAME + 0x3FA0, "I", now)
                p.entries = []
                p.put(n.ACTOR + 0x1888, "Q", 0)  # Synthetic derived-list rebuild.
                for count in (1, 2):
                    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                    n.require(p.read(n.ACTIVE, 0x180) == original, "successful guard mutated original")
                    n.require(len(p.entries) == count, "wrong registration count")
                    expected = resource.encode().ljust(8, b"\0") + struct.pack("<iI", -1, 1)
                    n.require(all(p.read(pointer, 16) == expected for _, pointer in p.entries),
                              "wrong guard descriptor or item-source scope")
                    before = b"".join(p.read(pointer, 16) for _, pointer in p.entries)
                    for item_source in (0, 1):
                        for query, match in ((resource, True), ("NOMATCH", False)):
                            p.u.mem_write(n.EFFECT + 0x94, query.encode().ljust(8, b"\0"))
                            p.run(0x1F8C90, n.ACTOR + 0x1880, n.EFFECT + 0x94, item_source)
                            n.require(bool(p.reg_read("RAX")) == match, "native resource lookup mismatch")
                    n.require(before == b"".join(p.read(pointer, 16) for _, pointer in p.entries),
                              "resource lookup consumed/mutated guard")
            count = p.events["apply_active"]
            p.put(n.GAME + 0x3FA0, "I", 1900)
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            n.require(p.events["apply_active"] == count, "guard reapplied at expiry")
        results.append(dict(resource=resource, predicate=condition, lifecycle=lifecycle,
                            duplicate_capacity=False, lookup_consumes=False))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Protection predicate and local string lifecycle/allocation are controlled services; no fixed SPLPROT row meaning is assumed.",
                 "The source-object lookup is bypassed with sourceID=-1; both predicate outcomes execute native post-predicate branches.",
                 "Native resource constructor/copy, Apply/Resolve and FindRes execute; list insertion/rebuild is synthetic.",
                 "No native CheckAdd/complete linked spell delivery, full actor rebuild or save/load is executed.",
                 "This supports only native preservation of proved-unowned branches, not318 HP ownership or immunity bypass."]), indent=2))
