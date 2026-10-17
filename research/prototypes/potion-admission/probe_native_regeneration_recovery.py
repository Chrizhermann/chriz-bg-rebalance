"""Bounded naturally-expired98 recovery scheduling candidate, offline only.

No hook installation. Recovery runs the pinned native inline cache initializer
1BEC70..1BECC3 and native InsertBefore/AddTail/RemoveAt with allocation services.
It never creates/applies a CGameEffect98 or invokes a healing opcode itself.
Native list update and all emitted17 ctor/Apply instructions still execute.
There is no callable cache ctor at this fragment: a real adapter is NOT supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native
from probe_native_regeneration import REGEN_LIST, HEAL_CALL
from probe_native_regeneration_cache import CacheMachine


class RecoveryMachine(CacheMachine):
    def __init__(self, image, unicorn, registers, mode, amount, positional=True):
        self.active_passes = []
        self.natural = set()
        self.snapshot = None
        self.trigger_cache = None
        self.pending = False
        self.original_new_expiry = None
        self.emissions = []
        self.native_append = False
        self.recoveries = []
        self.positional = positional
        self.removal_position = None
        self.list_lifetime = object()
        self.original_lifetime = object()
        self.retired_node_for_test = None
        super().__init__(image, unicorn, registers, mode, amount)

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva in (0x1F8990, 0x2265A0) and self.reg_read("RCX") == REGEN_LIST:
            if rva == 0x1F8990 or self.reg_read("RDX") == 5:
                self.snapshot = None
                self.removal_position = None
                self.list_lifetime = object()
        if rva == 0x226500:
            self.active_passes.append(self.reg_read("RCX"))
        elif rva == 0x22658B:
            native.require(self.active_passes and self.active_passes[-1] == self.reg_read("RSI"),
                           "unbalanced exact list update frame")
            self.active_passes.pop()
            # The common boundary follows the counter increment. Actual recovery
            # is orchestrated just after this function returns; its remaining
            # instructions only restore registers/return and do not touch lists.
        elif rva == 0x1A5D40:
            self.natural.add(self.reg_read("RBX"))
        elif rva == 0x22655E:
            cache = self.reg_read("RBX")
            association = self.associations.get(cache)
            if cache in self.natural and association and association[0] == native.ACTIVE:
                native.require(self.reg_read("RSI") == REGEN_LIST and
                               self.get(cache + 0xC, "I") == 0, "wrong/canceled natural removal")
                entries = self.entries()
                old_index = next(i for i, entry in enumerate(entries) if entry[0] == cache)
                self.retired_node_for_test = entries[old_index][2]
                self.removal_position = {
                    "order": [(pointer, token) for pointer, token, _ in entries],
                    "old_index": old_index,
                    "original_lifetime": self.original_lifetime,
                    "list_lifetime": self.list_lifetime,
                }
        elif rva == 0x1A4750:
            cache = self.reg_read("RCX")
            association = self.associations.get(cache)
            if cache in self.natural and association and association[0] == native.ACTIVE:
                native.require(self.get(cache + 0xC, "I") == 0, "canceled cache is not recoverable")
                native.require(self.removal_position is not None, "no exact pre-removal position")
                self.snapshot = {"bytes": self.read(cache, 0x30),
                                 "processed_counter": self.get(REGEN_LIST + 0x38, "I") + 1,
                                 "old_expiry": self.get(native.ACTIVE + 0x28, "I"),
                                 "death_time": self.get(native.GAME + 0x3FA0, "I"),
                                 **self.removal_position}
                self.removal_position = None
            self.natural.discard(cache)
        if address == HEAL_CALL:
            cache = self.reg_read("RBX")
            association = self.associations.get(cache)
            self.emissions.append({"original": association[0] if association else None,
                                   "counter": self.get(REGEN_LIST + 0x38, "I"),
                                   "world": self.get(native.GAME + 0x3FA0, "I")})
            if cache == self.trigger_cache and self.original_new_expiry is not None:
                native.require(self.snapshot is not None, "natural death has not happened")
                native.require(self.active_passes and self.active_passes[-1] == REGEN_LIST,
                               "trigger not in expected list pass")
                self.put(native.ACTIVE + 0x28, "I", self.original_new_expiry)
                self.pending = True
                self.original_new_expiry = None
        if self.native_append and rva == 0x4075C0:
            return  # Execute the real AddTail body instead of shared probe stub.
        if self.native_append and rva == 0x407890:
            # Supply a free node only when none exists. Native NewNode itself
            # executes, including reusing a node retired by native RemoveAt.
            list_pointer = self.reg_read("RCX")
            if self.get(list_pointer + 0x20, "Q") == 0:
                node, self.node_alloc = self.node_alloc, self.node_alloc + 0x30
                self.put(node, "QQQ", 0, 0, 0)
                self.put(list_pointer + 0x20, "Q", node)
            return
        if rva == 0x407970 and self.reg_read("RCX") == REGEN_LIST:
            return  # Execute the actual native RemoveAt and free-node writes.
        super().on_code(uc, address, size, data)

    def entries(self):
        entries, seen = [], set()
        node = self.get(REGEN_LIST + 8, "Q")
        while node:
            native.require(node not in seen and len(seen) < 32, "malformed recovery list")
            seen.add(node)
            pointer = self.get(node + 0x10, "Q")
            association = self.associations.get(pointer)
            native.require(association is not None, "untracked current cache lifetime")
            entries.append((pointer, association[1], node))
            node = self.get(node, "Q")
        return entries

    def insertion_node(self, snapshot):
        native.require(snapshot["list_lifetime"] is self.list_lifetime and
                       snapshot["original_lifetime"] is self.original_lifetime,
                       "original/list lifetime changed")
        current = self.entries()  # Never dereference a retained old node pointer.
        keys = [(pointer, token) for pointer, token, _ in current]
        expected = [key for key in snapshot["order"] if key in keys]
        native.require(keys == expected, "new/reordered/reused current cache lifetime")
        for pointer, _, _ in current:
            native.require(self.get(pointer, "Q") == native.BASE + 0x598B18 and
                           self.get(pointer + 8, "I") == self.get(pointer + 0xC, "I") == 0,
                           "current successor/predecessor not active regeneration")
        successors = snapshot["order"][snapshot["old_index"] + 1:]
        for key in successors:
            for pointer, token, node in current:
                if key == (pointer, token):
                    return node
        return 0

    def recover(self):
        native.require(not self.active_passes, "cannot append during any exact list update")
        native.require(self.snapshot is not None and not self.current_caches(native.ACTIVE),
                       "missing/ambiguous recovery snapshot")
        snapshot = self.snapshot
        insertion_node = self.insertion_node(snapshot)
        now = self.get(native.GAME + 0x3FA0, "I")
        native.require(snapshot["old_expiry"] - snapshot["death_time"] == 1 and
                       now == snapshot["death_time"], "outside proved expiry-minus-one window")
        native.require(self.get(native.ACTIVE + 0x114, "I") == 0 and
                       self.get(native.ACTIVE + 0x28, "I") > now,
                       "original no longer live")
        counter = self.get(REGEN_LIST + 0x38, "I")
        elapsed = counter - snapshot["processed_counter"]
        native.require(0 <= elapsed < 15 and counter < 0x7FFFFFFF,
                       "outside bounded no-wrap elapsed-pass proof")
        old = bytearray(snapshot["bytes"])
        native.require(struct.unpack_from("<i", old, 0x28)[0] == 0,
                       "not normal delta-one natural expiry")
        remaining = (self.get(native.ACTIVE + 0x28, "I") - snapshot["old_expiry"]) - elapsed
        native.require(0 < remaining <= 0x7FFFFFFF, "invalid recovery countdown")
        mode, interval = struct.unpack_from("<H", old, 0x20)[0], struct.unpack_from("<H", old, 0x18)[0]
        native.require(mode in (2, 3) and 0 < interval <= 32767, "unsupported recovery mode")
        phase = struct.unpack_from("<H", old, 0x1A)[0]
        if mode == 3:
            eligible_seconds = counter // 15 - snapshot["processed_counter"] // 15
            phase = (phase + eligible_seconds) % interval
        struct.pack_into("<I", old, 8, 0)
        struct.pack_into("<H", old, 0x1A, phase)
        struct.pack_into("<i", old, 0x28, remaining)
        # Execute only the native inline allocation/initializer. It has no
        # exported/callable standalone ctor; real adapter construction is open.
        self.fragment(0x1BEC70, (0x1BECC3,))
        cache = self.reg_read("RBX")
        native.require(self.get(cache, "Q") == native.BASE + 0x598B18, "native cache initialization wrong")
        self.u.mem_write(cache + 8, bytes(old[8:]))
        self.native_append = True
        if self.positional and insertion_node:
            self.run(0x4077F0, REGEN_LIST, insertion_node, cache)
        else:
            self.run(0x4075C0, REGEN_LIST, cache)
        self.native_append = False
        self.bind(cache, native.ACTIVE)
        restored_node = next(node for pointer, _, node in self.entries() if pointer == cache)
        self.pending, self.snapshot = False, None
        self.recoveries.append({"counter": counter, "elapsed_updates": elapsed,
                                "remaining": remaining, "phase": phase,
                                "heal_amount": self.get(cache + 0x24, "H"),
                                "insert_before_surviving_successor": bool(self.positional and insertion_node),
                                "native_reused_old_node_address": restored_node == self.retired_node_for_test})

    def tick(self, now):
        super().tick(now)
        if self.pending:
            before = len(self.heals)
            self.recover()
            native.require(len(self.heals) == before, "recovery emitted healing")


def run_probes(image, unicorn, registers):
    cases = []
    for mode, amount in ((2, 5), (3, 3)):
        for counter in (0, 7, 14):
            for tail in (True, False):
                # Trigger must emit at this pass to request an in-iterator
                # recovery; for off-second counters use a direct post-pass dose.
                baseline = RecoveryMachine(image, unicorn, registers, mode, amount)
                restored = RecoveryMachine(image, unicorn, registers, mode, amount)
                for p in (baseline, restored):
                    p.put(native.ACTIVE + 0x28, "I", 1100 if p is baseline else 1017)
                    p.rebuild()
                    p.put(p.current_caches(native.ACTIVE)[0] + 0x28, "i", 84 if p is baseline else 1)
                    p.trigger_cache = p.install_second(2, 1, 1200)
                    if not tail:
                        p.make_effect(native.EFFECT, 98)
                        p.put(native.EFFECT + 0x1C, "II", 1, 2)
                        p.put(native.EFFECT + 0x24, "II", 4096, 1200)
                        p.run(native.RESOLVE, native.EFFECT, native.ACTOR)
                    p.put(REGEN_LIST + 0x38, "I", counter)
                if counter == 14: restored.original_new_expiry = 1100
                baseline.tick(1016)
                restored.tick(1016)
                if counter != 14:
                    restored.put(native.ACTIVE + 0x28, "I", 1100)
                    restored.recover()
                before = [x for x in restored.emissions if x["original"] == native.ACTIVE]
                control_before = [x for x in baseline.emissions if x["original"] == native.ACTIVE]
                native.require(before == control_before, "same-pass recovery added/lost own heal")
                for now in range(1017, 1081):
                    baseline.tick(now)
                    restored.tick(now)
                native.require(restored.emissions == baseline.emissions and restored.heals == baseline.heals,
                               f"restored future native cadence differs from live control: mode={mode} counter={counter} tail={tail}; "
                               f"control={baseline.emissions}; recovered={restored.emissions}; "
                               f"heals={baseline.heals}/{restored.heals}")
                native.require(restored.get(native.ACTOR + 0x57C, "h") == baseline.get(native.ACTOR + 0x57C, "h"),
                               "restored native HP differs")
                cases.append({"mode": mode, "counter": counter, "trigger_is_tail": tail,
                              "deferred": counter == 14, "recovery": restored.recoveries[0],
                              "same_native_heal_history": True})

    # One absent-cache update can cross a second boundary. Preserve the future
    # phase without backfilling a heal before the replacement dose existed.
    elapsed_cases = []
    for mode, amount in ((2, 5), (3, 3)):
        baseline = RecoveryMachine(image, unicorn, registers, mode, amount)
        restored = RecoveryMachine(image, unicorn, registers, mode, amount)
        for p in (baseline, restored):
            p.put(native.ACTIVE + 0x28, "I", 1100 if p is baseline else 1017)
            p.rebuild()
            p.put(p.current_caches(native.ACTIVE)[0] + 0x28, "i", 84 if p is baseline else 1)
            p.put(REGEN_LIST + 0x38, "I", 13)
            p.tick(1016)
            p.tick(1016)
        restored.put(native.ACTIVE + 0x28, "I", 1100)
        before = len(restored.heals)
        restored.recover()
        native.require(len(restored.heals) == before, "recovery backfilled a past heal")
        base_start, new_start = len(baseline.heals), len(restored.heals)
        for now in range(1017, 1081):
            baseline.tick(now)
            restored.tick(now)
        native.require(baseline.heals[base_start:] == restored.heals[new_start:],
                       "elapsed pass recovery changed future cadence")
        elapsed_cases.append({"mode": mode, "recovery": restored.recoveries[0],
                              "past_heals_not_backfilled": True, "future_native_cadence_matches": True})

    def setup(p, long_original=False, position="head"):
        p.put(native.ACTIVE + 0x28, "I", 1100 if long_original else 1017)
        p.rebuild()
        own = p.current_caches(native.ACTIVE)[0]
        p.put(own + 0x28, "i", 84 if long_original else 1)
        p.install_second(2, 1, 1200)
        p.make_effect(native.EFFECT, 98)
        p.put(native.EFFECT + 0x1C, "II", 2, 2)
        p.put(native.EFFECT + 0x24, "II", 4096, 1200)
        p.run(native.RESOLVE, native.EFFECT, native.ACTOR)
        if position != "head":
            node = next(node for pointer, _, node in p.entries() if pointer == own)
            p.run(0x407970, REGEN_LIST, node)
            p.native_append = True
            if position == "middle":
                p.run(0x4077F0, REGEN_LIST, p.entries()[-1][2], own)
            else:
                p.run(0x4075C0, REGEN_LIST, own)
            p.native_append = False
        p.put(REGEN_LIST + 0x38, "I", 14)

    # Exact list position must survive disappearance of some/all successors.
    # All original emission ordering assertions remain strict.
    positions = []
    for position in ("head", "middle", "tail"):
        for removal in ("none", "first", "all"):
            baseline = RecoveryMachine(image, unicorn, registers, 2, 5)
            restored = RecoveryMachine(image, unicorn, registers, 2, 5)
            for p in (baseline, restored):
                setup(p, p is baseline, position)
                own_index = next(i for i, (pointer, _, _) in enumerate(p.entries())
                                 if p.associations[pointer][0] == native.ACTIVE)
                successors = p.entries()[own_index + 1:]
                for pointer, _, _ in successors[:1] if removal == "first" else successors if removal == "all" else []:
                    # Native cancellation removes successors in this same pass.
                    p.put(pointer + 0xC, "I", 1)
                p.tick(1016)
            restored.put(native.ACTIVE + 0x28, "I", 1100)
            restored.recover()
            for now in range(1017, 1081):
                baseline.tick(now)
                restored.tick(now)
            native.require(restored.emissions == baseline.emissions and restored.heals == baseline.heals,
                           "positional recovery changed full ordered native history")
            positions.append({"original_position": position, "successors_canceled": removal,
                              "same_ordered_history": True, "recovery": restored.recoveries[0]})

    # Append-only is kept as a required failing-equivalence control, not accepted
    # on the strength of a weaker per-source or final-HP comparison.
    append_control = []
    for mode, amount in ((2, 5), (3, 3)):
        baseline = RecoveryMachine(image, unicorn, registers, mode, amount)
        restored = RecoveryMachine(image, unicorn, registers, mode, amount, positional=False)
        setup(baseline, True)
        setup(restored)
        baseline.tick(1016)
        restored.tick(1016)
        restored.put(native.ACTIVE + 0x28, "I", 1100)
        restored.recover()
        for now in range(1017, 1081):
            baseline.tick(now)
            restored.tick(now)
        native.require(restored.emissions != baseline.emissions and restored.heals != baseline.heals,
                       "append-only order counterexample disappeared")
        for source in (native.ACTIVE, native.OTHER, native.EFFECT):
            native.require([e for e in baseline.emissions if e["original"] == source] ==
                           [e for e in restored.emissions if e["original"] == source],
                           "append control also changed per-source cadence")
        append_control.append({"mode": mode, "same_ordered_history": False,
                               "same_per_source_cadence_only": True, "acceptable_recovery": False})

    negatives = []
    for case in ("original_lifetime", "list_lifetime", "done_original", "expired_original",
                 "new_cache", "cache_address_reuse", "reordered_successors", "canceled_successor",
                 "clear_all", "cancel_type", "outside_window"):
        p = RecoveryMachine(image, unicorn, registers, 2, 5)
        setup(p)
        p.tick(1016)
        p.put(native.ACTIVE + 0x28, "I", 1100)
        if case == "original_lifetime": p.original_lifetime = object()
        elif case == "list_lifetime": p.list_lifetime = object()
        elif case == "done_original": p.put(native.ACTIVE + 0x114, "I", 1)
        elif case == "expired_original": p.put(native.ACTIVE + 0x28, "I", 1016)
        elif case == "new_cache": p.run(native.RESOLVE, native.OTHER, native.ACTOR)
        elif case == "cache_address_reuse":
            pointer, _, node = p.entries()[0]
            p.run(0x407970, REGEN_LIST, node)
            p.run(0x1A4750, pointer, 1)
            p.alloc = pointer  # Same address is deliberately a new cache lifetime.
            p.run(native.RESOLVE, native.OTHER, native.ACTOR)
        elif case == "reordered_successors":
            pointer, _, node = p.entries()[0]
            p.run(0x407970, REGEN_LIST, node)
            p.native_append = True
            p.run(0x4075C0, REGEN_LIST, pointer)
            p.native_append = False
        elif case == "canceled_successor": p.put(p.entries()[0][0] + 0xC, "I", 1)
        elif case == "clear_all": p.run(0x1F8990, REGEN_LIST)
        elif case == "cancel_type": p.run(0x2265A0, REGEN_LIST, 5)
        elif case == "outside_window": p.put(native.GAME + 0x3FA0, "I", 1017)
        before = (p.read(native.ACTIVE, 0x158), p.read(REGEN_LIST, 0x40),
                  [(pointer, p.read(pointer, 0x30)) for pointer, _, _ in p.entries()], len(p.heals))
        try:
            p.recover()
        except AssertionError:
            pass
        else:
            raise AssertionError(f"unsupported recovery accepted: {case}")
        after = (p.read(native.ACTIVE, 0x158), p.read(REGEN_LIST, 0x40),
                 [(pointer, p.read(pointer, 0x30)) for pointer, _, _ in p.entries()], len(p.heals))
        native.require(before == after, "rejected recovery changed native state")
        negatives.append({"case": case, "rejected_before_recovery_write": True})

    return {"same_pass_cases": cases, "elapsed_pass_cases": elapsed_cases,
            "position_cases": positions, "append_order_negative_controls": append_control,
            "rejection_cases": negatives,
            "limits": ["Pinned inline cache initializer is a fragment, not an available callable native constructor.",
                       "Post-iterator recovery is orchestrated immediately after native return, equivalent to the no-list-work epilogue boundary.",
                       "Only naturally expired mode2/3, remaining0, original expiry-minus-one window; counter<INT32MAX and fewer15elapsed updates.",
                       "No newly inserted/reordered list members during the recovery window; known removed successors may be skipped using lifetime tokens.",
                       "Position uses fresh node traversal; original/list generation and cache lifetime guards here are test-double bookkeeping, not installed hooks.",
                       "No real hook, allocation failure, full ProcessEffectList, TimeStop/Haste or save/load acceptance.",
                       "Recovery snapshot bookkeeping/cancellation/token validation must be implemented and verified separately."]}


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
    output = json.dumps(result, indent=2) + "\n"
    if args.output: args.output.write_text(output, encoding="utf-8")
    else: print(output)


if __name__ == "__main__": main()
