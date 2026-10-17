"""Offline copied-instruction regeneration/cache probe, pinned BG2EE 2.7.3.

No executable or DLL is launched. Native Apply98, regenerated-list AIUpdate,
regeneration AIUpdate, generated Heal17 ctor/Apply, ClearAll/RemoveAll, and
AddEffect admission/tail run in Unicorn. ProcessEffectList is NOT run whole:
its decisive scheduling/dirty fragments are executed independently, with the
documented ClearAll -> Resolve98 sequence orchestrated by this harness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import probe_native_admission as native

native.APPLY[98] = 0x1BEC50
HEAP = 0x700000000
REGEN_LIST = native.ACTOR + 0x1A08
HEAL_CALL = native.FAKE_CALLS + 0x100


class RegenMachine(native.Machine):
    def __init__(self, image, unicorn, registers, mode=3, amount=3):
        self.fragment_stops = set()
        self.fragment_hit = None
        self.alloc = HEAP
        self.node_alloc = HEAP + 0x10000
        self.heals = []
        self.dirty_refresh = False
        super().__init__(image, unicorn, registers, 98)
        self.u.mem_map(HEAP, 0x40000)
        self.put(native.ACTOR_VTABLE + 0xE8, "Q", HEAL_CALL)
        self.put(native.EFFECT_VTABLE + 0x20, "Q", native.BASE + 0x1E5500)
        self.put(native.EFFECT_VTABLE + 0x28, "Q", native.BASE + 0x1E69D0)
        self.put(native.EFFECT_VTABLE + 0x40, "Q", native.BASE + 0x1E1E0)
        for ptr in (native.ACTIVE, native.EFFECT):
            self.put(ptr + 0x1C, "II", amount, mode)
            self.u.mem_write(ptr + 0x94, b"POTN42\0\0")
        self.put(native.ACTOR + 0x57C, "h", 10)
        self.put(native.ACTOR + 0x1124, "h", 10000)
        self.put(native.ACTOR + 0x1DCC, "h", 10000)
        self.put(native.BASE + 0x667560, "Q", native.META + 0xE000)
        # Only the one original regeneration record is active. Other fixture
        # records from the shared skill probe must not force incidental reloads.
        self.put(native.NODES, "QQQ", 0, 0, native.ACTIVE)
        self.put(native.ACTOR + 0x4A08, "QQI", native.NODES, native.NODES, 1)

    def candidate_callback(self):
        super().candidate_callback()
        if self.refresh and self.dirty_refresh:
            self.put(native.ACTOR + 0x4BA4, "I", 1)
            self.callback_writes.append((native.ACTOR + 0x4BA4, 4, 1))

    def on_code(self, uc, address, size, data):
        rva = address - native.BASE
        if rva in self.fragment_stops:
            self.fragment_hit = rva
            self.returned = True
            uc.emu_stop()
            return
        if address == HEAL_CALL:
            ptr = self.reg_read("RDX")
            native.require(self.get(ptr + 0x10, "I") == 17, "not native healing opcode")
            self.heals.append({"tick": self.get(native.GAME + 0x3FA0, "I"),
                               "amount": self.get(ptr + 0x1C, "i")})
            # Preserve the native-generated descriptor. Execute the real healer
            # body; only AddEffect admission/dispatch of this generated heal is
            # bypassed (noSave=true in the native call). No generic HP arithmetic.
            self.reg_write("RCX", ptr)
            self.reg_write("RDX", native.ACTOR)
            self.reg_write("RIP", native.BASE + 0x1B50E0)
            return
        if rva == 0x4F7A88:
            count = self.reg_read("RCX")
            ptr = self.alloc
            self.alloc += (count + 0xFF) & ~0xFF
            native.require(self.alloc < HEAP + 0x10000, "bounded heap exhausted")
            self.ret(ptr)
            return
        if rva == 0x4075C0 and self.reg_read("RCX") == REGEN_LIST:
            node = self.node_alloc
            self.node_alloc += 0x30
            tail = self.get(REGEN_LIST + 0x10, "Q")
            self.put(node, "QQQ", 0, tail, self.reg_read("RDX"))
            if tail:
                self.put(tail, "Q", node)
            else:
                self.put(REGEN_LIST + 8, "Q", node)
            self.put(REGEN_LIST + 0x10, "Q", node)
            self.put(REGEN_LIST + 0x18, "I", self.get(REGEN_LIST + 0x18, "I") + 1)
            self.ret(node)
            return
        if rva == 0x407970 and self.reg_read("RCX") == REGEN_LIST:
            node = self.reg_read("RDX")
            nxt, prev = self.get(node, "Q"), self.get(node + 8, "Q")
            self.put(prev if prev else REGEN_LIST + 8, "Q", nxt)
            self.put(nxt + 8 if nxt else REGEN_LIST + 0x10, "Q", prev)
            self.put(REGEN_LIST + 0x18, "I", self.get(REGEN_LIST + 0x18, "I") - 1)
            self.ret()
            return
        # Native cache destructor is trivial heap release; the actual ClearAll
        # traversal and CObList RemoveAll run. These are service substitutions.
        if rva in (0x45E690, 0x407B40, 0x40D580, 0x276570):
            self.ret()
            return
        if rva == 0x3FF870:
            self.put(self.reg_read("RCX"), "Q", 0)
            self.ret(self.reg_read("RCX"))
            return
        if rva == 0x3FF960:
            self.put(self.reg_read("RCX"), "Q", 0)
            self.ret(self.reg_read("RCX"))
            return
        if rva == 0x4FAB70:
            ptr, value, length = (self.reg_read(n) for n in ("RCX", "RDX", "R8"))
            self.u.mem_write(ptr, bytes([value & 255]) * length)
            self.ret(ptr)
            return
        super().on_code(uc, address, size, data)

    def fragment(self, entry, stops, **registers):
        self.fragment_hit = None
        self.fragment_stops = set(stops)
        for name, value in registers.items():
            self.reg_write(name, value)
        self.run(entry)
        self.fragment_stops.clear()
        return self.fragment_hit

    def cache(self):
        head = self.get(REGEN_LIST + 8, "Q")
        return self.get(head + 0x10, "Q") if head else None

    def rebuild(self):
        before_counter = self.get(REGEN_LIST + 0x38, "I")
        before_heals = len(self.heals)
        before_effect = self.read(native.ACTIVE, 0x158)
        self.run(0x1F8990, REGEN_LIST)
        native.require(self.get(REGEN_LIST + 0x38, "I") == before_counter,
                       "native ClearAll/RemoveAll reset list tick counter")
        self.run(native.RESOLVE, native.ACTIVE, native.ACTOR)
        native.require(len(self.heals) == before_heals, "rebuild unexpectedly healed")
        native.require(self.read(native.ACTIVE, 0x158) == before_effect,
                       "live Resolve98 mutated original descriptor")
        native.require(self.get(REGEN_LIST + 0x18, "I") == 1, "cache not singular")

    def tick(self, now):
        self.put(native.GAME + 0x3FA0, "I", now)
        self.run(0x226500, REGEN_LIST, native.ACTOR, 1)

    def scheduling_gate(self):
        hit = self.fragment(0x3ABAFC, (0x3ABB19, 0x3AE02E), RSI=native.ACTOR,
                            R12=0, R13=1, R9=self.get(native.ACTOR + 0x4EA2, "H"))
        if hit == 0x3AE02E:
            return "deferred_reentrant"
        hit = self.fragment(0x3ABB7C, (0x3ABBCB, 0x3ADECF), RSI=native.ACTOR)
        if hit == 0x3ADECF:
            return "cached_only"
        # Execute native CheckDuration on both actual synthetic lists. An
        # unexpired finite effect does not itself force a scheduled full reload.
        hit = self.fragment(0x3ABF97, (0x3ABFF1, 0x3ADDA0), RSI=native.ACTOR,
                            RDI=0, R12=0)
        return "rebuild" if hit == 0x3ABFF1 else "no_rebuild_second_gate"


def lifecycle(image):
    ctor = 0x1A16C0
    native.require(image[ctor + 0x16:ctor + 0x1E] == bytes.fromhex("C744242800000000"),
                   "98 constructor UsesDice signature drift")
    table = ctor + 0x2F + struct.unpack_from("<i", image, ctor + 0x2B)[0]
    callbacks = {name: struct.unpack_from("<Q", image, table + offset)[0] - native.BASE
                 for name, offset in (("destructor", 0), ("OnAddSpecific", 0x28),
                                      ("OnRemove", 0x50))}
    native.require(callbacks == {"destructor": 0x14C8E0,
                                 "OnAddSpecific": 0x1E69D0, "OnRemove": 0x1E1E0},
                   "unreviewed regeneration lifecycle")
    native.require(image[0x38744C:0x387456] == bytes.fromhex("C787A44B000001000000"),
                   "AddEffect native dirty write drift")
    return {"usesDice": False, "callbacks": {k: f"{v:X}" for k, v in callbacks.items()}}


def run_probes(image, unicorn, registers):
    evidence = lifecycle(image)
    boundaries = []
    for dirty in (False, True):
        for global_tick, processing in ((0, 1), (1, 1), (0, 0)):
            p = RegenMachine(image, unicorn, registers)
            p.put(native.ACTOR + 0x3A0, "I", 124)  # Deliberately off actor modulo15.
            p.put(native.GAME + 0x3FA4, "B", global_tick)
            p.put(native.ACTOR + 0x4EA4, "I", processing)
            p.refresh = True
            p.dirty_refresh = dirty
            p.rebuild()
            cache = p.cache()
            before = p.read(cache, 0x30)
            p.run(native.ADD_EFFECT, native.ACTOR, native.EFFECT, 1, 0, 1)
            native.require(p.get(native.ACTIVE + 0x28, "I") == 1900, "refresh failed")
            native.require(p.check_add_result == 0, "incoming repeat was not rejected")
            native.require(p.read(cache, 0x30) == before, "callback/tail unexpectedly touched cache")
            native.require(len(p.heals) == 0, "admission refresh healed")
            native.require(p.get(native.ACTOR + 0x4BA4, "I") == int(dirty), "dirty write mismatch")
            process_calls = p.events[native.STUBS[0x3AB9D0]]
            native.require(process_calls == int(global_tick == 0), "AddEffect common tail drift")
            gate = p.scheduling_gate()
            expected = "deferred_reentrant" if not processing else "rebuild" if dirty else "cached_only"
            native.require(gate == expected, f"wrong native dirty scheduling: {gate}/{expected}")
            boundaries.append({"dirty_write": dirty, "global_tick": global_tick,
                               "processing_available": processing, "tail_process_calls": process_calls,
                               "next_native_gate": gate,
                               "dirty_after_gate": p.get(native.ACTOR + 0x4BA4, "I")})

    # Passing the once-per-15 scheduler does not mean an unexpired effect is
    # rebuilt: with unchanged unrelated stats, the second native gate skips it.
    scheduled = RegenMachine(image, unicorn, registers)
    scheduled.put(native.ACTOR + 0x3A0, "I", 123)
    native.require(scheduled.scheduling_gate() == "no_rebuild_second_gate",
                   "ordinary scheduled check unexpectedly requires full reload")

    on_add = []
    for mode in (2, 3):
        for timing, expiry in ((0, 60), (10, 31), (4096, 1450)):
            p = RegenMachine(image, unicorn, registers, mode)
            p.put(native.ACTIVE + 0x24, "II", timing, expiry)
            before = p.read(native.ACTIVE, 0x158)
            p.run(0x1E5500, native.ACTIVE, native.ACTOR)
            native.require(p.read(native.ACTIVE, 0x158) == before, "finite native OnAdd changed descriptor")
            native.require(p.get(native.ACTOR + 0x57C, "h") == 10 and not p.heals,
                           "finite native OnAdd healed")
            on_add.append({"mode": mode, "timing": timing, "unchanged": True})

    cadence = []
    # Arbitrary list-counter offsets matter: world time and regenerated-list
    # update count are separate fields. Do not silently assume they are aligned.
    for mode, amount in ((2, 2), (3, 3)):
        for counter in (0, 7, 14):
            for anchor in (0, 991):
                control = RegenMachine(image, unicorn, registers, mode, amount)
                refreshed = RegenMachine(image, unicorn, registers, mode, amount)
                for p in (control, refreshed):
                    p.put(native.ACTIVE + 0x28, "I", 1900)
                    p.put(native.ACTIVE + 0x6C, "I", anchor)
                    p.put(REGEN_LIST + 0x38, "I", counter)
                    p.rebuild()
                for now in range(1001, 1091):
                    if now == 1027:
                        # Extra dirty rebuild without changing native source,
                        # phase anchor or list counter, executed before this tick.
                        refreshed.put(native.GAME + 0x3FA0, "I", now)
                        refreshed.rebuild()
                        refreshed.rebuild()  # duplicate same-time accepted refresh
                    control.tick(now)
                    refreshed.tick(now)
                cadence.append({"mode": mode, "amount": amount, "initial_counter": counter,
                                "phase_anchor": anchor, "control": control.heals,
                                "extra_dirty_rebuild": refreshed.heals,
                                "same_cadence": control.heals == refreshed.heals,
                                "control_hp": control.get(native.ACTOR + 0x57C, "h"),
                                "refreshed_hp": refreshed.get(native.ACTOR + 0x57C, "h")})
    native.require(all(row["same_cadence"] for row in cadence if row["mode"] == 2),
                   "mode2 cadence regression")
    native.require(any(not row["same_cadence"] for row in cadence if row["mode"] == 3),
                   "negative mode3 phase counterexample no longer reproduced")

    cached_deadline = []
    for dirty in (False, True):
        p = RegenMachine(image, unicorn, registers, 2, 2)
        p.put(native.ACTIVE + 0x28, "I", 1017)
        p.rebuild()
        for now in range(1001, 1011):
            p.tick(now)
        cache = p.cache()
        p.put(native.ACTIVE + 0x28, "I", 1100)
        if dirty:
            p.rebuild()
        old_countdown = p.get(cache + 0x28, "i")
        for now in range(1011, 1061):
            p.tick(now)
        cached_deadline.append({"dirty_rebuild": dirty, "old_cache_countdown": old_countdown,
                                "remaining_sources": p.get(REGEN_LIST + 0x18, "I"),
                                "heals": p.heals})
    native.require(cached_deadline[0]["remaining_sources"] == 0, "negative cached-expiry case missed")
    native.require(cached_deadline[1]["remaining_sources"] == 1, "dirty rebuild did not extend cached source")
    return {"lifecycle": evidence, "native_scheduling_boundaries": boundaries,
            "ordinary_scheduler_can_skip_reload": True, "finite_OnAdd_cases": on_add,
            "cadence_comparisons": cadence, "cached_deadline_cases": cached_deadline,
            "limitations": ["Not whole ProcessEffectList execution; native scheduling fragments and rebuild sequence are separated.",
                            "Synthetic objects and allocator/list-node/UI service substitutions.",
                            "Generated native17 ctor and Apply execute; its AddEffect admission is bypassed.",
                            "No live game, save/load, EEex hook, multiplayer or TimeStop acceptance."]}


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
    image = pefile.PE(data=data).get_memory_mapped_image()
    result = run_probes(image, unicorn, x86_const)
    result["exe_sha256"] = native.SHA256
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
