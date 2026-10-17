"""Offline83 boolean membership,30 setter and200 duplicate-consumption checks.

Executes pinned class Apply/Resolve, actual CObList::Find and the actual original
effect debit helper. Synthetic list allocation/rebuilds and declared services;
no game process, resource installation or save writes.
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
n.APPLY.update({30: 0x1C1140, 83: 0x1B6DE0, 200: 0x1A7C20})
results = []


class ProjectileMachine(StatsMachine):
    def __init__(self):
        super().__init__(image, unicorn, x86_const, 83)
        self.nodes = []
        self.allocation = 0x730000000
        self.u.mem_map(self.allocation, 0x10000)

    def on_code(self, uc, address, size, data):
        if address == n.BASE + 0x4075C0:
            n.require(self.reg_read("RCX") == n.ACTOR + 0x1410, "unexpected immunity list")
            value = self.reg_read("RDX")
            node = self.allocation
            self.allocation += 0x20
            self.put(node, "QQQ", 0, self.nodes[-1] if self.nodes else 0, value)
            if self.nodes:
                self.put(self.nodes[-1], "Q", node)
            else:
                self.put(n.ACTOR + 0x1418, "Q", node)
            self.nodes.append(node)
            self.ret(node)
            return
        super().on_code(uc, address, size, data)


for mode in (0, 1, 64, 65535, 65536, 0xFFFFFFFF):
    for amount in (0, 9):
        lifecycle = vtable_evidence(image, 0x1A0500)
        p = ProjectileMachine()
        p.verify_self_on_add()
        p.put(n.ACTIVE + 0x1C, "iI", amount, mode)
        p.put(n.ACTIVE + 0xCC, "I", 1)
        p.put(n.ACTIVE + 0x28, "I", 1900)
        original = p.read(n.ACTIVE, 0x180)
        for now in (1000, 1450, 1501, 1899):
            p.put(n.GAME + 0x3FA0, "I", now)
            p.nodes = []
            p.put(n.ACTOR + 0x1418, "Q", 0)  # Synthetic derived-list rebuild.
            for duplicate_count in (1, 2):
                p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
                n.require(p.read(n.ACTIVE, 0x180) == original, "83 original fields changed")
                snapshot = b"".join(p.read(node, 0x18) for node in p.nodes)
                for query, expected in ((mode, True), (mode & 0xFFFF, mode <= 65535), (0x100000000, False)):
                    p.run(0x4076F0, n.ACTOR + 0x1410, query, 0)
                    n.require(bool(p.reg_read("RAX")) == expected, "native membership mismatch")
                n.require(b"".join(p.read(node, 0x18) for node in p.nodes) == snapshot, "membership consumed/mutated entry")
                n.require(len(p.nodes) == duplicate_count, "list registration count wrong")
        count = p.events["apply_active"]
        p.put(n.GAME + 0x3FA0, "I", 1900)
        p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
        n.require(p.events["apply_active"] == count, "83 reapplied at new expiry")
        results.append(dict(opcode=83, mode=mode, amount=amount, stable=True,
                            membership_consumes=False, lifecycle=lifecycle))

for amount in (-2147483648, -65535, -129, -1, 0, 1, 100, 127, 128, 32767, 32768,
               65535, 65536, 65537, 2147483647):
    lifecycle = vtable_evidence(image, 0x1A1C00)
    p = StatsMachine(image, unicorn, x86_const, 30)
    p.verify_self_on_add()
    p.put(n.ACTIVE + 0x1C, "iI", amount, 1)
    p.put(n.ACTIVE + 0xCC, "I", 1)
    p.put(n.ACTIVE + 0x28, "I", 1900)
    original = p.read(n.ACTIVE, 0x180)
    effective = (amount + 32768) % 65536 - 32768
    expected = max(-128, min(127, effective))
    for now in (1000, 1450, 1501, 1899):
        p.put(n.GAME + 0x3FA0, "I", now)
        p.put(n.ACTOR + 0x113E, "h", -50)
        for _ in range(2):
            p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
            n.require(p.get(n.ACTOR + 0x113E, "h") == expected, "fire setter width/clamp mismatch")
            n.require(p.read(n.ACTIVE, 0x180) == original, "fire setter original fields changed")
    count = p.events["apply_active"]
    p.put(n.GAME + 0x3FA0, "I", 1900)
    p.run(n.RESOLVE, n.ACTIVE, n.ACTOR)
    n.require(p.events["apply_active"] == count, "fire setter reapplied at expiry")
    results.append(dict(opcode=30, mode=1, raw_amount=amount, effective_amount=effective,
                        result=expected, stable=True, lifecycle=lifecycle))


class BounceMachine(n.Machine):
    def __init__(self):
        super().__init__(image, unicorn, x86_const, 200)
        self.casts = []

    def on_code(self, uc, address, size, data):
        if address == n.BASE + 0x349120:
            n.require(self.reg_read("RDX") == 65, "unexpected bounce icon")
            self.ret(1)
            return
        if address == n.BASE + 0x1E4570:
            self.casts.append(self.read(self.reg_read("RDX"), 8).hex())
            self.ret(1)
            return
        super().on_code(uc, address, size, data)


ctor = 0x19E620
vt = ctor + 0x2F + struct.unpack_from("<i", image, ctor + 0x2B)[0]
n.require(struct.unpack_from("<Q", image, vt + 0x50)[0] == n.BASE + 0x1E6BA0,
          "200 nontrivial removal callback changed")
for old_count, new_count, debit in ((1, 6, 1), (6, 6, 6)):
    p = BounceMachine()
    p.seed_lists(reverse=True)
    for pointer, count, source in ((n.ACTIVE, old_count, b"OLD\0\0\0\0\0"),
                                   (n.OTHER, new_count, b"NEW\0\0\0\0\0")):
        p.put(pointer + 0x1C, "iI", count, 1)
        p.put(pointer + 0x24, "I", 4096)
        p.u.mem_write(pointer + 0x30, b"BTEST1B\0")
        p.u.mem_write(pointer + 0x94, source)
        p.run(n.APPLY[200], pointer, n.ACTOR)
    n.require(p.get(n.ACTOR + 0x1694 + 8, "I") == new_count, "200 derived table is not last writer")
    # Exact helper/arguments selected by native CBounceList::Process14CCA1.
    p.run(0x1E5480, n.ACTOR + 0x4A00, 200, (-debit) & 0xFFFFFFFF, 1, 0, 0, 0)
    n.require([p.get(pointer + 0x1C, "i") for pointer in (n.ACTIVE, n.OTHER)]
              == [old_count - debit, new_count - debit], "200 debit did not affect both original sources")
    exhausted = 0
    for pointer in (n.ACTIVE, n.OTHER):
        if p.get(pointer + 0x1C, "i") <= 0:
            p.run(n.APPLY[200], pointer, n.ACTOR)
            n.require(p.get(pointer + 0x114, "I") == 1, "exhausted200 not marked done")
            exhausted += 1
    n.require(len(p.casts) == exhausted and all(x == b"BTEST1B\0".hex() for x in p.casts),
              "each exhausted original did not dispatch its native resource")
    results.append(dict(opcode=200, old_count=old_count, incoming_count=new_count, debit=debit,
                        remaining=[old_count-debit, new_count-debit], exhausted_resource_dispatches=exhausted,
                        supported=False, on_remove_rva="1E6BA0"))

print(json.dumps(dict(exe_sha256=n.SHA256, count=len(results), cases=results,
    limitations=["Synthetic list insertion/rebuild and actor baselines;83 native Apply/Resolve and Find execute.",
                 "Native projectile caller branches were inspected; this probe does not replay complete projectile paths.",
                 "200 native Apply and ModifyAllOfType execute; full bounce scheduling, reflected projectiles, exhaustion child payload and OnRemove sound are not executed.",
                 "No game process, installation, resource or save writes."]), indent=2))
