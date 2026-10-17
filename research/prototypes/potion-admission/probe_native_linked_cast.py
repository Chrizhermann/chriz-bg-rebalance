"""Bounded offline op146 mode1 lineage probe; never launches a game or DLL.

Native parent Apply, cast-message Run/destructor, FireSpell through its child
loop, AddEffect/CheckAdd/Resolve/op90 and instant projectile delivery execute in
Unicorn. Resource construction, engine predicates and scheduler services are
explicit doubles. FireSpell's feedback/area tail is omitted at 16B348 and its
native epilogue is used. Sidecar observations model a proposed contract, not an
installed hook. All input reads are pinned to the documented executable hash.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as admission

SHA256 = admission.SHA256
HEAP = 0x700000000
ABILITY = HEAP + 0x70000
NODES = HEAP + 0x71000
STRING = HEAP + 0x72000
CAST_RUN, FIRE_SPELL, PARENT_APPLY = 0x212DD0, 0x16ABC0, 0x1A84B0
CAST_VTABLE, CAST_DESTROY = 0x590D90, 0x165200
CHILD_READY, CHILD_LOOP_END = 0x16B047, 0x16B348
SIGNATURES = {
    0x1A8594: "4881c168170000498bd6e81dc90500",
    CAST_RUN: "40534883ec60", 0x212E84: "e8377df5ff488b4c2458",
    CAST_DESTROY: "48895c2408574883ec20",
    FIRE_SPELL: "48895c24205556574154415541564157",
    CHILD_READY: "8b4314ffc8", 0x16B100: "e8bb9d0900",
    0x16B1D8: "ff90e8000000", 0x16B252: "ff90e8000000",
    0x16B1EC: "488bd3498bcde879f00b00",
    0x20FE5E: "ff90e800000048c7431000000000",
}
SERVICES = {
    **admission.STUBS,
    0x4F7A88: "deterministic successful allocation, no address reuse",
    0x45E690: "delete records lifetime only; memory remains mapped",
    0x3FFF70: "parent resref to CString (synthetic POTN36)",
    0x3FFE40: "resref to CString (synthetic POTN36)",
    0x3FD770: "CString assignment", 0x3FF710: "CString to CResRef",
    0x3FD740: "CString cleanup", 0x164F90: "CSpell constructor",
    0x24ED30: "resource Demand: synthetic SPL exists",
    0x24F010: "synthetic caster type 1", 0x39CC30: "synthetic caster level 12",
    0x24EDD0: "synthetic ability count", 0x24ED80: "synthetic ability lookup",
    0x24EE30: "synthetic original child constructor (90, source type 1, level 12)",
    0x22BF00: "synthetic default CProjectileInstant, native class vtable",
    0x276700: "GetDeny: synthetic actor or controlled missing actor",
    0x204EC0: "local scheduler: same message pointer, optional reentrant Run",
    0x4075C0: "list AddTail: links synthetic allocated nodes",
    0x11BA20: "CAIObjectType constructor", 0x11EA00: "CAIObjectType assignment",
    0x11E300: "CAIObjectType::OfType: true",
    0x4076F0: "projectile immunity: absent", 0x272420: "object-array removal",
    0x1ECE40: "base object cleanup", 0x3FFB60: "no projectile sound resource",
    0x40D740: "sound cleanup", 0x4073D0: "list storage cleanup",
}


def require(value, message):
    if not value:
        raise AssertionError(message)


class Machine(admission.Machine):
    def __init__(self, image, unicorn, registers, *, base, route="direct", gate="accept",
                 target=1, reentrant=False, nested=False, duration_scale=100,
                 relocated_cast_call=False):
        admission.BASE = base
        self.base = base
        super().__init__(image, unicorn, registers)
        self.u.mem_map(HEAP, 0x80000)
        self.route, self.gate, self.target = route, gate, target
        self.reentrant, self.nested, self.nested_done = reentrant, nested, False
        self.relocated_cast_call = relocated_cast_call
        if relocated_cast_call:
            # Negative control: execute an actual CALL from another code address.
            # The RSP relation is unchanged but the pushed return address differs.
            self.u.mem_write(admission.FAKE_CALLS + 0xA00,
                             b"\x48\xb8" + struct.pack("<Q", base+FIRE_SPELL) + b"\xff\xd0" +
                             b"\x48\xb8" + struct.pack("<Q", base+0x212E89) + b"\xff\xe0")
        self.next_alloc, self.next_node = HEAP, NODES
        self.parent_tags, self.cast_tags, self.child_tags = {}, {}, {}
        self.cast_queue, self.effect_queue, self.projectiles = [], [], []
        self.run_stack, self.fire_frames, self.injections = [], [], []
        self.observations, self.admissions, self.applied, self.destroyed = [], [], [], []
        self.freed, self.canceled, self.missing_id = [], [], None
        self.effect_messages, self.parent_queue_snapshots = {}, []
        self.put(admission.ACTOR_VTABLE + 8, "Q", admission.FAKE_CALLS + 0x100)
        self.put(admission.ACTOR_VTABLE + 0xE8, "Q", base + admission.ADD_EFFECT)
        self.put(admission.ACTOR + 0x11A6, "h", duration_scale)
        # The native engine-state comparison chooses direct or delayed delivery.
        self.put(admission.CHITIN + 0x208, "Q", 1)
        self.put(admission.CHITIN + 0x10B0, "Q", 1 if route == "direct" else 2)
        self.put(admission.CHITIN + 0x10B8, "Q", 3)
        for offset in admission.LISTS:
            self.u.mem_write(admission.ACTOR + offset, bytes(0x50))
        self.put(ABILITY + 0x10, "H", 1)
        self.put(ABILITY + 0x1E, "H", 1)
        self.put(ABILITY + 0x26, "H", 1)
        self.u.mem_write(STRING, b"POTN36\0\0")

    def allocate(self, size):
        result = self.next_alloc
        self.next_alloc += (size + 0xFF) & ~0xFF
        require(self.next_alloc < HEAP + 0x60000, "fixture heap exhausted")
        return result

    def origin(self, message):
        return self.cast_tags.get(message)

    def inject(self, rva, arguments, *, finish_service):
        """A scheduler double invokes native code while its service is pending.

        Saves/restores the interrupted CPU context like a correctly implemented
        host service; the injected native function has its own real stack frame.
        This is not evidence the actual scheduler reenters at this frequency.
        """
        context = self.u.context_save()
        sp = self.reg_read("RSP") - 0x400
        sp = (sp & ~0xF) + 8
        self.put(sp, "Q", admission.FAKE_CALLS + 0x800)
        for index, value in enumerate(arguments[:4]):
            self.reg_write(("RCX", "RDX", "R8", "R9")[index], value)
        for index, value in enumerate(arguments[4:]):
            self.put(sp + 0x28 + index * 8, "Q", value)
        self.injections.append((context, finish_service))
        self.reg_write("RSP", sp)
        self.reg_write("RIP", self.base + rva)

    def candidate_callback(self):
        pointer = self.reg_read("RDI")
        require(self.reg_read("R14") == admission.ACTOR, "admission target register")
        self.admissions.append((pointer, self.child_tags.get(pointer)))

    def on_write(self, *_):
        pass

    def on_code(self, uc, address, size, _):
        self.visited.append(address)
        self.visited = self.visited[-32:]
        if address == admission.RETURN:
            self.returned = True
            uc.emu_stop()
            return
        if address == admission.FAKE_CALLS + 0x800:
            context, finish_service = self.injections.pop()
            uc.context_restore(context)
            if finish_service:
                self.ret(1)
            else:
                # context_restore alone does not invalidate Unicorn's current
                # translated RET block. Explicit PC write resumes the suspended
                # observation instruction instead of executing that stale RET.
                self.reg_write("RIP", self.reg_read("RIP"))
            return
        rva = address - self.base
        if rva == 0x1A8594:
            parent, message = self.reg_read("RSI"), self.reg_read("R14")
            require(self.reg_read("R15") == admission.ACTOR, "parent target changed")
            require(self.get(message, "Q") == self.base + CAST_VTABLE, "cast class changed")
            tag = self.parent_tags.get(parent)
            if tag is not None:
                self.cast_tags[message] = tag
            self.parent_queue_snapshots.append((parent, message, tag))
        elif rva == CAST_RUN:
            self.run_stack.append((self.reg_read("RCX"), self.reg_read("RSP")))
        elif rva == 0x212E84 and self.relocated_cast_call:
            self.reg_write("RIP", admission.FAKE_CALLS + 0xA00)
            return
        elif rva == 0x212E89:
            require(self.run_stack[-1][0] == self.reg_read("RBX"), "unbalanced cast Run")
            self.run_stack.pop()
        elif rva == FIRE_SPELL:
            self.fire_frames.append(self.reg_read("RSP"))
        elif rva == CHILD_READY:
            frame = self.reg_read("RBP") + 0xB8
            pointer = self.reg_read("RBX")
            caller = self.get(frame, "Q")
            require(frame == self.fire_frames[-1], "native FireSpell frame expression changed")
            tag = None
            if self.run_stack:
                message, entry = self.run_stack[-1]
                if frame == entry - 0x70 and caller == self.base + 0x212E89:
                    tag = self.origin(message)
            if tag is not None:
                self.child_tags[pointer] = tag
            self.observations.append({
                "effect": pointer, "tag": tag, "frame": frame, "caller_rva": caller-self.base,
                "ability": self.get(self.reg_read("RSP") + 0x50, "I"),
                "ordinal": self.reg_read("EDI"), "caster": self.reg_read("R14"),
                "target": self.reg_read("RSI"), "source_type": self.get(pointer+0x90, "I"),
                "caster_level": self.get(pointer+0xC8, "I"),
                "duration": self.get(pointer+0x28, "I"),
            })
            if self.nested and not self.nested_done:
                self.nested_done = True
                self.inject(FIRE_SPELL, (admission.ACTOR, STRING, admission.ACTOR, 0,
                                        0xFFFFFFFF, 0, 1, 1), finish_service=False)
                return
        elif rva == CHILD_LOOP_END:
            # Explicit boundary: feedback, trigger and area registration tail is
            # outside this lineage probe. Use the real balanced native epilogue.
            self.events["omitted_fire_spell_tail"] += 1
            self.reg_write("RIP", self.base + 0x16ADDF)
            return
        elif rva == 0x16AE18:
            self.fire_frames.pop()
        elif rva == CAST_DESTROY:
            pointer = self.reg_read("RCX")
            if pointer in self.cast_tags:
                self.canceled.append((pointer, self.cast_tags.pop(pointer)))
        elif rva in (0x14C8E0, 0x1A45A0):
            pointer = self.reg_read("RCX")
            self.parent_tags.pop(pointer, None)
            self.child_tags.pop(pointer, None)
            self.destroyed.append(pointer)
        elif rva == admission.ADD_EFFECT:
            require(self.reg_read("R9") == 0, "native child noSave must be false")
            self.events["native_child_AddEffect"] += 1
        elif rva == admission.AFTER_CHECK_SAVE:
            self.candidate_callback()
        elif rva == admission.APPLY[90]:
            self.applied.append(self.reg_read("RCX"))

        if admission.FAKE_CALLS <= address < admission.FAKE_CALLS + 0x200:
            offset = address - admission.FAKE_CALLS
            if offset == 0:
                pointer = self.reg_read("RCX")
                self.destroyed.append(pointer)
                self.child_tags.pop(pointer, None)
            value = admission.AI_TYPE if offset == 0x50 else 0
            if offset == 0x100:
                value = self.get(self.base + 0x59971F, "B")
            self.ret(value)  # op90 UsesDice=false, native constructor-proven.
            return
        if rva not in SERVICES:
            return
        self.events[SERVICES[rva]] += 1
        rcx, rdx = self.reg_read("RCX"), self.reg_read("RDX")
        if rva == 0x4F7A88:
            self.ret(self.allocate(rcx))
        elif rva == 0x45E690:
            self.freed.append(rcx)
            self.ret()
        elif rva in (0x3FFF70, 0x3FFE40):
            self.put(rdx, "Q", STRING)
            self.ret(rdx)
        elif rva == 0x3FD770:
            self.put(rcx, "Q", STRING)
            self.ret(rcx)
        elif rva == 0x3FF710:
            self.u.mem_write(rcx, b"POTN36\0\0")
            self.ret(rcx)
        elif rva == 0x164F90:
            self.put(rcx, "Q", ABILITY)
            self.u.mem_write(rcx + 8, b"POTN36\0\0")
            self.ret(rcx)
        elif rva in (0x24F010, 0x24EDD0, 0x11E300):
            self.ret(1)
        elif rva == 0x39CC30:
            self.ret(12)
        elif rva == 0x24ED80:
            self.ret(ABILITY if rdx == 0 else 0)
        elif rva == 0x24EE30:
            require(rdx == 0 and self.reg_read("R8") == 0, "unexpected selected ability/ordinal")
            pointer = self.allocate(0x180)
            self.make_effect(pointer, 90)
            self.put(pointer+0x14, "I", self.target)
            self.put(pointer+0x90, "I", 1)
            self.put(pointer+0xC8, "I", 12)
            if self.gate == "probability":
                self.put(pointer+0x2C, "H", 49)
            self.ret(pointer)
        elif rva == 0x22BF00:
            require(rcx == 1, "unsupported projectile request")
            pointer = self.allocate(0x200)
            self.put(pointer, "Q", self.base+0x59BFF0)
            self.put(pointer+0x60, "H", 1)
            self.put(pointer+0x70, "i", -1)
            self.put(pointer+0x180, "i", -1)
            self.projectiles.append(pointer)
            self.ret(pointer)
        elif rva == 0x276700:
            self.put(rdx, "Q", admission.ACTOR)
            self.ret(int((rcx & 0xFFFFFFFF) == self.missing_id))
        elif rva == 0x4075C0:
            node = self.next_node
            self.next_node += 0x20
            tail = self.get(rcx+0x10, "Q")
            self.put(node, "QQQ", 0, tail, rdx)
            if tail:
                self.put(tail, "Q", node)
            else:
                self.put(rcx+8, "Q", node)
            self.put(rcx+0x10, "QI", node, self.get(rcx+0x18, "I")+1)
            self.ret(node)
        elif rva == 0x204EC0:
            require(self.reg_read("R8") == 0, "unexpected AddMessage flags")
            if self.get(rdx, "Q") == self.base + CAST_VTABLE:
                self.cast_queue.append(rdx)
                require(rdx in self.cast_tags, "queue observation occurred too late")
                if self.reentrant:
                    self.inject(CAST_RUN, (rdx,), finish_service=True)
                    return
            else:
                effect = self.get(rdx+0x10, "Q")
                require(self.get(rdx+0x1A, "B") == 0, "queued child noSave")
                self.effect_queue.append(rdx)
                self.effect_messages[rdx] = (effect, self.child_tags.get(effect))
                if self.reentrant:
                    self.inject(0x20FE10, (rdx,), finish_service=True)
                    return
            self.ret(1)
        elif rva == 0x38BAB0:
            self.ret(int(self.gate != "check_effect"))
        elif rva == 0x1F8E30:
            self.ret(int(self.gate == "opcode_immunity"))
        elif rva == 0x1CD330:
            self.ret(int(self.gate != "save"))
        elif rva == 0x1F8910:
            self.ret(1)
        elif rva == 0x4F77A0:
            self.ret(self.reg_read("RAX"))
        elif rva == 0x11BA20:
            self.u.mem_write(rcx, bytes(0x20))
            self.ret(rcx)
        else:
            self.ret(0)

    def dose(self, tag, *, parent_destroy=True):
        parent = self.allocate(0x180)
        self.make_effect(parent, 146)
        self.put(parent+0x20, "I", 1)
        self.u.mem_write(parent+0x30, b"POTN36\0\0")
        self.parent_tags[parent] = tag
        self.run(PARENT_APPLY, parent, admission.ACTOR)
        require(self.get(parent+0x114, "I") == 1, "original parent did not finish")
        message = self.parent_queue_snapshots[-1][1]
        require(self.get(message+8, "I") == 123 and self.get(message+0x18, "I") == 123,
                "parent source/target changed")
        if parent_destroy:
            self.run(0x14C8E0, parent, 1)
            require(message in self.cast_tags, "parent destruction lost queued cast lineage")
        return message

    def dispatch(self, message):
        self.run(CAST_RUN, message)
        self.run(CAST_DESTROY, message, 1)

    def deliver(self):
        # This replaces only omitted FireSpell tail scheduling: native instant
        # Fire/OnArrival/DeliverEffects perform the original pointer hand-off.
        for projectile in self.projectiles:
            if self.get(projectile+0x80, "Q"):
                self.run(0x231600, projectile, HEAP+0x73000, 123, 123)
        for message in self.effect_queue:
            effect, tag = self.effect_messages[message]
            if self.get(message+0x10, "Q") == 0:
                continue  # The adversarial scheduler already ran it reentrantly.
            require(self.get(message+0x10, "Q") == effect, "queued effect pointer changed")
            self.run(0x20FE10, message)
            require(self.get(message+0x10, "Q") == 0, "Run did not relinquish effect ownership")


def run_probes(image, unicorn, registers, base):
    for rva, expected in SIGNATURES.items():
        require(image[rva:rva+len(expected)//2].hex() == expected, f"signature {rva:X}")
    results = []
    for route, target in (("direct", 1), ("queued", 1), ("direct", 2), ("projectile", 2)):
        for gate in ("accept", "probability", "opcode_immunity", "check_effect", "save"):
            m = Machine(image, unicorn, registers, base=base, route=route, target=target, gate=gate)
            message = m.dose("dose-A")
            m.dispatch(message)
            m.deliver()
            require(len(m.observations) == 1 and m.observations[0]["tag"] == "dose-A", "child lineage")
            require(len(m.admissions) == len(m.applied) == int(gate == "accept"), "failed child admission leak")
            require(m.events["native_child_AddEffect"] == 1, "child was delivered twice or not delivered")
            require(not m.run_stack and not m.fire_frames and not m.cast_tags, "cast lifetime leak")
            observation = m.observations[0]
            require(observation["caster_level"] == 12 and observation["source_type"] == 1,
                    "original child source/level lost")
            require(observation["ability"] == observation["ordinal"] == 0, "child-site ABI changed")
            results.append({"route": route, "target": target, "gate": gate,
                            "admissions": len(m.admissions), "applied": len(m.applied)})
    m = Machine(image, unicorn, registers, base=base, route="queued")
    message = m.dose("cancel")
    m.run(CAST_DESTROY, message, 1)
    require(not m.cast_tags and not m.observations and message in m.freed, "canceled cast leaked")
    results.append({"case": "cast_canceled_before_Run", "children": 0})
    for field in (8, 0x18):
        m = Machine(image, unicorn, registers, base=base)
        message = m.dose("missing")
        m.put(message+field, "I", 456)
        m.missing_id = 456
        m.dispatch(message)
        require(not m.observations and not m.run_stack and not m.cast_tags, "failed lookup leaked")
        results.append({"case": "missing_cast_actor", "message_field": field, "children": 0})
    m = Machine(image, unicorn, registers, base=base, route="queued")
    first, second = m.dose("same-tick-A"), m.dose("same-tick-B")
    for message in (second, first):
        m.dispatch(message)
    m.deliver()
    require([tag for _, tag in m.admissions] == ["same-tick-B", "same-tick-A"], "same-tick doses conflated")
    results.append({"case": "two_same_tick_doses_reverse_dispatch", "tags": [t for _, t in m.admissions]})
    m = Machine(image, unicorn, registers, base=base, reentrant=True, nested=True, duration_scale=150)
    message = m.dose("reentrant")
    m.run(CAST_DESTROY, message, 1)
    # Resuming the original observation site sees it again after the injected
    # nested FireSpell returns. Distinct effect pointers are what matter here.
    by_pointer = {row["effect"]: row for row in m.observations}
    require(len(by_pointer) == 2, "nested FireSpell did not produce distinct original children")
    require(sorted((row["tag"] or "unowned") for row in by_pointer.values()) == ["reentrant", "unowned"],
            "unrelated nested FireSpell inherited outer cast provenance")
    require(len(m.applied) == 2 and all(row["duration"] == 90 for row in by_pointer.values()),
            "native op99 duration scaling or nested execution changed")
    require(not m.run_stack and not m.fire_frames and not m.injections, "reentrant stack leaked")
    results.append({"case": "reentrant_send_with_unrelated_nested_FireSpell",
                    "owned_children": 1, "unowned_children": 1, "native_scaled_duration": 90})
    m = Machine(image, unicorn, registers, base=base, route="queued", reentrant=True)
    message = m.dose("reentrant-queued-child")
    m.run(CAST_DESTROY, message, 1)
    m.deliver()
    require(len(m.applied) == 1 and m.admissions[0][1] == "reentrant-queued-child",
            "nested AddMessage/Run lost lineage or delivered twice")
    require(not m.run_stack and not m.fire_frames and not m.injections, "nested scheduler stack leaked")
    results.append({"case": "cast_and_child_messages_both_run_during_AddMessage", "applied": 1})
    m = Machine(image, unicorn, registers, base=base, relocated_cast_call=True)
    message = m.dose("relocated-call")
    m.dispatch(message)
    require(len(m.observations) == 1 and m.observations[0]["tag"] is None and len(m.applied) == 1,
            "copied CALL return-address negative control no longer rejects ownership")
    require(m.observations[0]["caller_rva"] == admission.FAKE_CALLS+0xA0C-base,
            "copied CALL did not push its actual trampoline return address")
    results.append({"case": "copied_cast_CALL_changes_return_address", "native_effect_applied": 1,
                    "ownership_rejected": True})
    return {"image_base": hex(base), "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    from unicorn import x86_const
    data = args.exe.read_bytes()
    require(hashlib.sha256(data).hexdigest() == SHA256, "unsupported executable hash")
    runs = []
    for base in (0x140000000, 0x180000000):
        pe = pefile.PE(data=data)
        original_base = pe.OPTIONAL_HEADER.ImageBase
        image = bytearray(pe.get_memory_mapped_image())
        require(pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].VirtualAddress == 0 and
                pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].Size == 0, "pinned relocation assumption changed")
        if base != original_base:
            # This image has NO relocation directory. This alternate mapping is
            # only a frame/return-address arithmetic fixture, never an ASLR claim.
            # Fix up the actual instant vtable used by these bounded instructions;
            # synthetic effect/actor vtables are already based on `base`.
            for offset in range(0, 0x128, 8):
                pointer = struct.unpack_from("<Q", image, 0x59BFF0 + offset)[0]
                if original_base <= pointer < original_base + len(image):
                    struct.pack_into("<Q", image, 0x59BFF0 + offset, pointer + base-original_base)
        run = run_probes(bytes(image), unicorn, x86_const, base)
        run["mapping"] = "native fixed image base" if base == original_base else "synthetic alternate mapping; selected vtable fixups"
        runs.append(run)
    print(json.dumps({"executable_sha256": SHA256, "runs": runs,
                      "services": {f"{rva:X}": name for rva, name in SERVICES.items()},
                      "limitations": [
                          "Copied instructions only; no game, EEex DLL, real scheduler or installed hook executed.",
                          "Resource lookup and child construction use synthetic fixtures, not a complete SPL loader.",
                          "FireSpell feedback, triggers, area registration and cleanup tail after16B348 omitted; real native epilogue executes.",
                          "Projectile delivery is invoked explicitly after this omitted scheduling tail.",
                          "CheckSave/MR and immunity predicates are controlled services; their branch ordering is native.",
                          "Reentrant scheduler and nested-cast injection are adversarial doubles, not measured scheduling frequency.",
                          "Pinned PE has no relocation directory; alternate-base run uses explicit selected-vtable fixture fixups, not OS ASLR loading.",
                          "No remote message serialization, copied/area projectile, save/load, allocation failure or exception-unwind proof.",
                          "The sidecar lineage model is a proposed observation contract, not product runtime verification.",
                      ]}, indent=2))


if __name__ == "__main__":
    main()
