"""Offline two-original98 positional recovery; no installed native adapter.

Native cache initialization, list insertion/removal/update and generated17 Apply
execute. Allocation/free-pool services and lifetime/order bookkeeping are mocks.
The matching Lua module is tested separately, not called from this native probe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native
from probe_native_regeneration import REGEN_LIST
from probe_native_regeneration_recovery import RecoveryMachine

TAIL = native.EFFECT + 0x3000


class BatchMachine(RecoveryMachine):
    def __init__(self, image, unicorn, registers, mode):
        self.order = None
        self.batch = {}
        self.before_remove = {}
        self.batch_operations = []
        super().__init__(image, unicorn, registers, mode, 5 if mode == 2 else 3)

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva == 0x22655E:
            cache = self.reg_read("RBX")
            association = self.associations.get(cache)
            if cache in self.natural and association and association[0] in (native.ACTIVE, native.OTHER):
                current = [(p, t) for p, t, _ in self.entries()]
                if self.order is None:
                    self.order = current
                index = self.order.index((cache, association[1]))
                self.before_remove[cache] = {"index": index, "original": association[0],
                    "processed_counter": self.get(REGEN_LIST + 0x38, "I") + 1}
        elif rva == 0x1A4750:
            cache = self.reg_read("RCX")
            capture = self.before_remove.pop(cache, None)
            if capture:
                original = capture["original"]
                capture.update({"state": self.read(cache, 0x30),
                                "old_expiry": self.get(original + 0x28, "I"),
                                "death_time": self.get(native.GAME + 0x3FA0, "I")})
                self.batch[original] = capture
        super().on_code(uc, address, size, data)
        if rva == 0x1BEDE5 and self.order is not None:
            current = self.entries()
            cache = self.reg_read('RBX')
            native.require(current[-1][0] == cache, 'native append callback is not tail')
            existing = [(p,t) for p,t,_ in current[:-1]]
            native.require(existing == [key for key in self.order if key in existing],
                           'native append contains another unknown mutation')
            self.order.append((cache,self.associations[cache][1]))

    def extra(self, original, amount=1):
        self.make_effect(original, 98)
        self.put(original + 0x1C, "II", amount, 2)
        self.put(original + 0x24, "II", 4096, 1200)
        self.native_append = True
        self.run(native.RESOLVE, original, native.ACTOR)
        self.native_append = False

    def reconstruct_batch(self):
        native.require(not self.active_passes and self.batch, "bad batch entry")
        current = [(p, t) for p, t, _ in self.entries()]
        native.require(current == [e for e in self.order if e in current], "ambiguous current order")
        now, counter = self.get(native.GAME + 0x3FA0, "I"), self.get(REGEN_LIST + 0x38, "I")
        staged = []
        for original, snapshot in self.batch.items():
            native.require(not self.current_caches(original), "original already cached")
            native.require(now == snapshot["death_time"] == snapshot["old_expiry"] - 1,
                           "outside natural expiry-minus-one window")
            saved = bytearray(snapshot["state"])
            native.require(struct.unpack_from("<III", saved, 8)[:2] == (1, 0) and
                           struct.unpack_from("<i", saved, 0x28)[0] == 0, "not natural normal death")
            elapsed = counter - snapshot["processed_counter"]
            native.require(0 <= elapsed < 15, "unbounded elapsed counter")
            remaining = self.get(original + 0x28, "I") - snapshot["old_expiry"] - elapsed
            mode, interval = struct.unpack_from("<H", saved, 0x20)[0], struct.unpack_from("<H", saved, 0x18)[0]
            phase = struct.unpack_from("<H", saved, 0x1A)[0]
            if mode == 3:
                phase = (phase + counter // 15 - snapshot["processed_counter"] // 15) % interval
            struct.pack_into("<I", saved, 8, 0)
            struct.pack_into("<H", saved, 0x1A, phase)
            struct.pack_into("<i", saved, 0x28, remaining)
            self.fragment(0x1BEC70, (0x1BECC3,))
            cache = self.reg_read("RBX")
            self.u.mem_write(cache + 8, bytes(saved[8:]))
            staged.append((snapshot["index"], original, cache))
            self.batch_operations.append("allocate")
        # Insert the latest logical position first. Each earlier insertion sees
        # known replacements for its retired successors, with fresh node reads.
        for index, original, cache in sorted(staged, reverse=True):
            current = self.entries()
            keys = [(p, t) for p, t, _ in current]
            native.require(keys == [e for e in self.order if e in keys], "batch changed unrelated order")
            successor = 0
            for key in self.order[index + 1:]:
                for p, token, node in current:
                    if key == (p, token):
                        successor = node
                        break
                if successor:
                    break
            self.native_append = True
            if successor:
                self.run(0x4077F0, REGEN_LIST, successor, cache)
            else:
                self.run(0x4075C0, REGEN_LIST, cache)
            self.native_append = False
            self.bind(cache, original)
            self.order[index] = (cache, self.associations[cache][1])
            self.batch_operations.append("insert")
        self.batch.clear()


def run_probes(image, unicorn, registers):
    cases = []
    for mode_a in (2, 3):
        for mode_b in (2, 3):
            for counter in (0, 7, 14):
                for separate_passes in (False, True):
                    baseline = BatchMachine(image, unicorn, registers, mode_a)
                    restored = BatchMachine(image, unicorn, registers, mode_a)
                    for p in (baseline, restored):
                        p.put(native.ACTIVE + 0x28, "I", 1100 if p is baseline else 1017)
                        p.rebuild()
                        p.put(p.current_caches(native.ACTIVE)[0] + 0x28, "i", 84 if p is baseline else 1)
                        p.extra(native.EFFECT, 1)
                        p.install_second(mode_b, 5 if mode_b == 2 else 4, 1100 if p is baseline else 1017)
                        p.put(p.current_caches(native.OTHER)[0] + 0x28, "i",
                              (84 if p is baseline else 1) + int(separate_passes))
                        p.extra(TAIL, 2)
                        p.put(REGEN_LIST + 0x38, "I", counter)
                        p.tick(1016)
                        if separate_passes:
                            p.tick(1016)
                    native.require(len(restored.batch) == 2, "both original lifetimes not captured")
                    before_heals = list(restored.heals)
                    restored.put(native.ACTIVE + 0x28, "I", 1100)
                    restored.put(native.OTHER + 0x28, "I", 1100)
                    restored.reconstruct_batch()
                    native.require(restored.heals == before_heals, "batch reconstruction emitted healing")
                    native.require(restored.batch_operations == ["allocate", "allocate", "insert", "insert"],
                                   "batch did not stage before native insertion")
                    for now in range(1017, 1081):
                        baseline.tick(now)
                        restored.tick(now)
                    native.require(restored.emissions == baseline.emissions and restored.heals == baseline.heals,
                                   f"batch changed ordered native healing: {mode_a}/{mode_b}/{counter}/{separate_passes}")
                    native.require(restored.get(native.ACTOR + 0x57C, "h") == baseline.get(native.ACTOR + 0x57C, "h"),
                                   "batch final native HP differs")
                    cases.append({"mode_a": mode_a, "mode_b": mode_b, "initial_counter": counter,
                                  "different_removal_passes": separate_passes,
                                  "same_full_ordered_native_history": True,
                                  "all_native_allocations_before_insertions": True})
    append_cases = []
    for mode in (2,3):
        for separate_passes in (False,True):
            for retired_tail in (False,True):
                baseline = BatchMachine(image,unicorn,registers,mode)
                restored = BatchMachine(image,unicorn,registers,mode)
                for p in (baseline,restored):
                    p.put(native.ACTIVE+0x28,'I',1100 if p is baseline else 1017)
                    p.rebuild()
                    p.put(p.current_caches(native.ACTIVE)[0]+0x28,'i',84 if p is baseline else 1)
                    p.extra(native.EFFECT,1)
                    p.install_second(2,5,1100 if p is baseline else 1017)
                    p.put(p.current_caches(native.OTHER)[0]+0x28,'i',
                          (84 if p is baseline else 1)+int(separate_passes))
                    if not retired_tail: p.extra(TAIL,2)
                    p.put(REGEN_LIST+0x38,'I',7)
                    p.tick(1016)
                    p.extra(native.EFFECT+0x2800,3)  # Actual native AddTail + observed append.
                    if separate_passes: p.tick(1016)
                restored.put(native.ACTIVE+0x28,'I',1100)
                restored.put(native.OTHER+0x28,'I',1100)
                restored.reconstruct_batch()
                for now in range(1017,1081):
                    baseline.tick(now); restored.tick(now)
                native.require(restored.emissions==baseline.emissions and restored.heals==baseline.heals,
                               'observed native append changed full ordered healing')
                append_cases.append({'mode':mode,'different_removal_passes':separate_passes,
                                     'original_tail_retired':retired_tail,'observed_native_append':True,
                                     'same_full_ordered_native_history':True})
    return {"cases": cases, "observed_append_cases":append_cases, "limits": [
        "No installed hooks or native allocator adapter; free-pool/heap services and bookkeeping are substitutes.",
        "Natural expiry-minus-one window only; elapsed passes do not cross a missed due tick in these full-history comparisons.",
        "Single-recovery probe separately covers phase advancement across a missed boundary without backfilling past healing.",
        "Generated17 admission/full ProcessEffectList side effects are not executed; no live or full save/load acceptance."]}


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
