"""Exact original98/cache association candidate, offline copied instructions.

No game/native DLL or real hooks. Python callbacks at reviewed native boundaries
model ephemeral lineage. Native98 creation, native cache Copy/destruction/ticks,
original CheckAdd rejection and generated native17 arithmetic execute. Updating
the selected cache countdown is a proposed test-double commit, not production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native
from probe_native_regeneration import RegenMachine, REGEN_LIST, HEAP, HEAL_CALL


class CacheMachine(RegenMachine):
    def __init__(self, image, unicorn, registers, mode=3, amount=3):
        self.associations = {}
        self.lifetime = 0
        self.cache_commit = False
        self.selected_cache = None
        super().__init__(image, unicorn, registers, mode, amount)

    def bind(self, cache, original):
        native.require(cache not in self.associations, "live cache address reused")
        self.lifetime += 1
        self.associations[cache] = (original, self.lifetime)

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x1BEDE5:
            native.require(self.reg_read("RBP") == native.ACTOR, "creation sprite ABI drift")
            self.bind(self.reg_read("RBX"), self.reg_read("RDI"))
        elif rva == 0x1DCAE9:
            source = self.associations.get(self.reg_read("RBX"))
            if source:
                self.bind(self.reg_read("RAX"), source[0])
        elif rva == 0x1A4750:
            self.associations.pop(self.reg_read("RCX"), None)
        super().on_code(uc, address, size, data)

    def current_caches(self, original):
        found = []
        node = self.get(REGEN_LIST + 8, "Q")
        seen = set()
        while node:
            native.require(node not in seen and len(seen) < 32, "malformed cache list")
            seen.add(node)
            pointer = self.get(node + 0x10, "Q")
            record = self.associations.get(pointer)
            if record and record[0] == original:
                found.append(pointer)
            node = self.get(node, "Q")
        return found

    def commit(self, original, new_expiry):
        # Lifetime-token validation is modelled by exact constructor/Copy and
        # destructor callbacks. Original-effect token validation belongs to the
        # existing reader; do not pretend native pointer equality replaces it.
        now = self.get(native.GAME + 0x3FA0, "I")
        old_expiry = self.get(original + 0x28, "I")
        native.require(self.get(original + 0x114, "I") == 0 and old_expiry > now,
                       "original effect is done/expired")
        caches = self.current_caches(original)
        native.require(len(caches) == 1, "missing/ambiguous live cache lineage")
        cache = caches[0]
        native.require(self.get(cache, "Q") == native.BASE + 0x598B18, "wrong cache class")
        native.require(self.get(cache + 8, "I") == self.get(cache + 0xC, "I") == 0,
                       "cache is done/canceled")
        remaining = self.get(cache + 0x28, "i")
        delta = new_expiry - old_expiry
        native.require(0 < remaining <= 0x7FFFFFFF and 0 <= delta <= 0x7FFFFFFF - remaining,
                       "invalid/overflowing exact countdown extension")
        # Two scalar writes only. Preserve phase+1A, per-list counter+38,
        # original phase input6C, heal amount and every unrelated cache.
        self.put(cache + 0x28, "i", remaining + delta)
        self.put(original + 0x28, "I", new_expiry)
        self.selected_cache = cache

    def candidate_callback(self):
        if not self.cache_commit:
            return super().candidate_callback()
        native.require(self.reg_read("RDI") == native.EFFECT and self.reg_read("R14") == native.ACTOR,
                       "admission ABI drift")
        new_expiry = native.deadline(self.get(native.GAME + 0x3FA0, "I"),
                                     self.get(native.EFFECT + 0x28, "I"),
                                     self.get(native.EFFECT + 0x24, "I"))
        self.commit(native.ACTIVE, new_expiry)
        self.reg_write("RIP", native.BASE + native.REJECT)

    def install_second(self, mode, amount, expiry):
        self.make_effect(native.OTHER, 98)
        self.put(native.OTHER + 0x1C, "II", amount, mode)
        self.put(native.OTHER + 0x24, "II", 4096, expiry)
        self.u.mem_write(native.OTHER + 0x94, b"OTHERREG")
        self.run(native.RESOLVE, native.OTHER, native.ACTOR)
        return self.current_caches(native.OTHER)[0]


class RecoveryVisibilityMachine(CacheMachine):
    """Negative control: candidate restoration inside the native cache iterator.

    Snapshot allocation/initialization/AddTail are modelled, not proposed as
    executable EEex recovery code. The iterator and all resulting heals are
    actual native instructions; it demonstrates why immediate append is unsafe.
    """
    def __init__(self, image, unicorn, registers):
        self.expired_snapshot = None
        self.trigger_cache = None
        self.restored = None
        self.emissions = []
        super().__init__(image, unicorn, registers, 2, 1)

    def on_code(self, uc, address, size, data):
        if address == native.BASE + 0x1A4750:
            ptr = self.reg_read("RCX")
            lineage = self.associations.get(ptr)
            if lineage and lineage[0] == native.ACTIVE:
                self.expired_snapshot = self.read(ptr, 0x30)
        if address == HEAL_CALL:
            current_cache = self.reg_read("RBX")
            lineage = self.associations.get(current_cache)
            self.emissions.append(lineage[0] if lineage else None)
            if current_cache == self.trigger_cache and self.restored is None:
                native.require(self.expired_snapshot is not None, "target has not naturally expired yet")
                ptr, self.alloc = self.alloc, self.alloc + 0x100
                self.u.mem_write(ptr, self.expired_snapshot)
                self.put(ptr + 8, "I", 0)
                self.put(ptr + 0x28, "i", 83)
                self.bind(ptr, native.ACTIVE)
                node, self.node_alloc = self.node_alloc, self.node_alloc + 0x30
                tail = self.get(REGEN_LIST + 0x10, "Q")
                self.put(node, "QQQ", 0, tail, ptr)
                self.put(tail, "Q", node)
                self.put(REGEN_LIST + 0x10, "Q", node)
                self.put(REGEN_LIST + 0x18, "I", self.get(REGEN_LIST + 0x18, "I") + 1)
                self.restored = ptr
        super().on_code(uc, address, size, data)


def run_probes(image, unicorn, registers):
    cases = []
    for mode, amount in ((2, 2), (3, 3)):
        for counter in (0, 7, 14):
            for when in (1001, 1015, 1016, 1027, 1039):
                baseline = CacheMachine(image, unicorn, registers, mode, amount)
                refreshed = CacheMachine(image, unicorn, registers, mode, amount)
                for p in (baseline, refreshed):
                    p.put(native.ACTIVE + 0x28, "I", 1100 if p is baseline else 1040)
                    p.put(REGEN_LIST + 0x38, "I", counter)
                    p.rebuild()
                    p.install_second(3, 4, 1200)
                for now in range(1001, 1091):
                    if now == when:
                        refreshed.put(native.GAME + 0x3FA0, "I", now)
                        original_before = refreshed.read(native.ACTIVE, 0x158)
                        cache = refreshed.current_caches(native.ACTIVE)[0]
                        cache_before = refreshed.read(cache, 0x30)
                        unrelated = refreshed.current_caches(native.OTHER)[0]
                        unrelated_before = refreshed.read(unrelated, 0x30)
                        list_before = refreshed.read(REGEN_LIST, 0x40)
                        # Use incoming timing10 so this bounded admitted dose
                        # proposes the same absolute1100 deadline in every case.
                        refreshed.put(native.EFFECT + 0x24, "II", 10, 1100 - now)
                        refreshed.cache_commit = True
                        before_heals = list(refreshed.heals)
                        for _ in range(2):
                            refreshed.run(native.ADD_EFFECT, native.ACTOR, native.EFFECT, 1, 0, 1)
                        expected = bytearray(original_before)
                        struct.pack_into("<I", expected, 0x28, 1100)
                        native.require(refreshed.read(native.ACTIVE, 0x158) == expected,
                                       "non-expiry original bytes changed")
                        expected_cache = bytearray(cache_before)
                        struct.pack_into("<i", expected_cache, 0x28,
                                         struct.unpack_from("<i", cache_before, 0x28)[0] + 60)
                        native.require(refreshed.read(cache, 0x30) == expected_cache,
                                       "cache phase/amount changed or duplicate overextended")
                        native.require(refreshed.read(unrelated, 0x30) == unrelated_before and
                                       refreshed.read(REGEN_LIST, 0x40) == list_before,
                                       "unrelated cache/list changed")
                        native.require(refreshed.heals == before_heals and
                                       refreshed.get(native.ACTOR + 0x4BA4, "I") == 0,
                                       "candidate healed or forced broad reload")
                    baseline.tick(now)
                    refreshed.tick(now)
                native.require(refreshed.heals == baseline.heals, "native cadence differs from unchanged long effect")
                native.require(refreshed.get(native.ACTOR + 0x57C, "h") ==
                               baseline.get(native.ACTOR + 0x57C, "h"), "native HP differs")
                cases.append({"mode": mode, "counter": counter, "refresh_tick": when,
                              "native_heals": refreshed.heals,
                              "same_as_long_original": True, "unrelated_cache_unchanged": True})

    lifecycle = []
    p = CacheMachine(image, unicorn, registers, 2, 5)
    p.rebuild()
    original_cache = p.current_caches(native.ACTIVE)[0]
    token = p.associations[original_cache][1]
    p.run(0x1DCA40, original_cache)
    copy = p.reg_read("RAX")
    native.require(p.associations[copy][0] == native.ACTIVE and
                   p.associations[copy][1] != token, "native Copy lineage missing")
    native.require(p.get(copy + 0x24, "H") == 1 and p.get(original_cache + 0x24, "H") == 5,
                   "native Copy's omitted healamount observation changed")
    native.require(p.current_caches(native.ACTIVE) == [original_cache], "snapshot copy mistaken for active cache")
    p.run(0x1F8990, REGEN_LIST)
    native.require(original_cache not in p.associations and copy in p.associations,
                   "ClearAll destructor lifetime removal failed")
    # Restore a copied cache into the actual timed cache list, analogous to the
    # destination of list operator=; list insertion is an explicit service stub.
    p.run(0x4075C0, REGEN_LIST, copy)
    p.commit(native.ACTIVE, 1600)
    native.require(p.selected_cache == copy, "restored cache copy not selected exactly")
    lifecycle.append({"case": "copy_restore", "actual_native_copy_heal_amount": 1,
                      "original_heal_amount": 5, "snapshot_not_live_until_list_member": True})
    p.run(0x1F8990, REGEN_LIST)
    p.alloc = original_cache  # Deliberate allocator address reuse after native destructor.
    p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
    native.require(p.current_caches(native.ACTIVE) == [original_cache] and
                   p.associations[original_cache][1] != token, "same-address cache ABA was not distinguished")
    lifecycle.append({"case": "address_reuse", "fresh_lifetime": True})

    for reason in ("natural_expiry", "native_type_cancel"):
        p = CacheMachine(image, unicorn, registers)
        p.put(native.ACTIVE + 0x28, "I", 1001 if reason == "natural_expiry" else 1450)
        p.rebuild()
        cache = p.current_caches(native.ACTIVE)[0]
        if reason == "native_type_cancel":
            p.run(0x2265A0, REGEN_LIST, 5)
            native.require(p.get(cache + 0xC, "I") == 1, "native type cancel did not flag cache")
        p.tick(1001)
        native.require(cache not in p.associations and not p.current_caches(native.ACTIVE),
                       "native AIUpdate removal failed to retire lineage")
        lifecycle.append({"case": reason, "native_destructor_retired_lineage": True})

    # ProcessEffectList applies timed effects before AIUpdate in the same world
    # tick. This produces a real one-tick early cache-expiry window; do not call
    # missing lineage a permanently unsupported resource or silently revive it.
    p = CacheMachine(image, unicorn, registers, 2, 2)
    p.put(native.ACTIVE + 0x28, "I", 1017)
    p.rebuild()
    for now in range(1000, 1017):
        p.tick(now)
    native.require(p.get(native.ACTIVE + 0x28, "I") == 1017 and
                   p.get(native.ACTIVE + 0x114, "I") == 0 and
                   p.get(native.GAME + 0x3FA0, "I") == 1016 and
                   not p.current_caches(native.ACTIVE),
                   "same-pass decrement did not expose live-original/missing-cache boundary")
    before = p.read(native.ACTIVE, 0x158)
    try:
        p.commit(native.ACTIVE, 1100)
    except AssertionError:
        pass
    else:
        raise AssertionError("unproved missing-cache refresh was accepted")
    native.require(p.read(native.ACTIVE, 0x158) == before, "missing-cache rejection changed original")
    lifecycle.append({"case": "same_pass_cache_expiry", "world_time": 1016,
                      "original_expiry": 1017, "original_still_live": True,
                      "cache_absent": True, "refresh_diagnoses_without_write": True})

    recovery_visibility = []
    for trigger_is_tail in (True, False):
        p = RecoveryVisibilityMachine(image, unicorn, registers)
        p.put(native.ACTIVE + 0x28, "I", 1017)
        p.rebuild()
        p.trigger_cache = p.install_second(2, 1, 1200)
        if not trigger_is_tail:
            # A third unrelated native cache after the triggering cache makes
            # the newly appended tail visible later in this same iterator pass.
            p.make_effect(native.EFFECT, 98)
            p.put(native.EFFECT + 0x1C, "II", 1, 2)
            p.put(native.EFFECT + 0x24, "II", 4096, 1200)
            p.run(native.RESOLVE, native.EFFECT, native.ACTOR)
        p.put(p.current_caches(native.ACTIVE)[0] + 0x28, "i", 1)
        p.put(REGEN_LIST + 0x38, "I", 14)
        p.tick(1016)
        own_heals = p.emissions.count(native.ACTIVE)
        native.require(own_heals == (1 if trigger_is_tail else 2),
                       "native same-pass append visibility counterexample changed")
        recovery_visibility.append({"trigger_is_tail": trigger_is_tail,
                                    "old_family_native_heals_in_same_pass": own_heals,
                                    "list_counter_after": p.get(REGEN_LIST + 0x38, "I"),
                                    "immediate_append_not_order_independent": True})

    negatives = []
    for case in ("done", "canceled", "missing", "duplicate", "overflow", "expired_original"):
        p = CacheMachine(image, unicorn, registers)
        p.rebuild()
        cache = p.current_caches(native.ACTIVE)[0]
        if case == "done": p.put(cache + 8, "I", 1)
        if case == "canceled": p.put(cache + 0xC, "I", 1)
        if case == "missing": p.associations.clear()
        if case == "duplicate": p.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        if case == "overflow": p.put(cache + 0x28, "I", 0x7FFFFFFF)
        if case == "expired_original": p.put(native.ACTIVE + 0x28, "I", 1000)
        old, oldcache = p.read(native.ACTIVE, 0x158), p.read(cache, 0x30)
        try:
            p.commit(native.ACTIVE, 1900)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"unsafe cache commit accepted: {case}")
        native.require(p.read(native.ACTIVE, 0x158) == old and p.read(cache, 0x30) == oldcache,
                       "rejected preflight partially wrote")
        negatives.append({"case": case, "rejected_before_write": True})
    return {"cadence_cases": cases, "lifecycle_cases": lifecycle, "negative_cases": negatives,
            "recovery_append_visibility": recovery_visibility,
            "limits": ["Ephemeral original/cache lineage callbacks are test doubles, not EEex hooks.",
                       "Original-effect lifetime tokens/actor destruction/reset are supplied by existing reader design, not re-proved here.",
                       "Only immediate original98 modes2/3 with zero extended parameters are considered.",
                       "No linked177, slow-poison mutation, TimeStop/Haste acceptance or full save/load execution.",
                       "Existing engine Copy heal-amount behavior is observed and preserved, not fixed."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.python_libs: sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    from unicorn import x86_const
    data = args.exe.read_bytes()
    native.require(hashlib.sha256(data).hexdigest() == native.SHA256, "unreviewed executable")
    result = run_probes(pefile.PE(data=data).get_memory_mapped_image(), unicorn, x86_const)
    result["exe_sha256"] = native.SHA256
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output: args.output.write_text(encoded, encoding="utf-8")
    else: print(encoded)


if __name__ == "__main__":
    main()
