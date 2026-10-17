"""Actual Lua manifest/reader/runtime/core decisions inside copied native code.

This offline probe reads a hash-pinned executable into Unicorn. It never starts
the game or writes an executable, installed resource, or save. Native predicate
and engine-service stubs remain explicit. Delivery lifecycle callbacks are
invoked by the harness; generated EEex assembly is not executed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import build_manifest
import probe_native_admission as shared
from probe_native_potion_opcodes import OpcodeMachine

ROOT = Path(__file__).resolve().parent
SIZE = 0x180
require = shared.require


def fixture_item(opcode, amount, mode=0, *, upper=100, lower=0):
    """One direct original record, with native constructor metadata expectations."""
    raw = bytearray(0x72 + 0x38 + 0x30)
    raw[:8] = b"ITM V1  "
    struct.pack_into("<H", raw, 0x1C, 9)
    struct.pack_into("<IHIHH", raw, 0x64, 0x72, 1, 0xAA, 0, 0)
    raw[0x72], raw[0x72 + 0xC] = 3, 1
    struct.pack_into("<HH", raw, 0x72 + 0x1E, 1, 0)
    struct.pack_into("<HBBiiBBI", raw, 0xAA, opcode, 1, 2, amount, mode, 0, 1, 60)
    raw[0xAA + 0x12], raw[0xAA + 0x13] = upper, lower
    return bytes(raw)


class LuaMachine(OpcodeMachine):
    def __init__(self, image, unicorn, registers, lua_class, opcode, case):
        amount, mode = (110, 2) if opcode == 18 else (4, 0) if opcode == 19 else (20, 0)
        super().__init__(image, unicorn, registers, opcode, amount, mode)
        self.case = case
        self.gate = case if case in {"save", "opcode_immunity", "check_effect"} else "accept"
        self.reports, self.lua_calls = [], 0
        self.lua = lua_class(unpack_returned_tuples=True)
        self.objects = {}
        self.source = "POTN09" if opcode == 18 else "POTN29" if opcode == 19 else "POTN36"
        upper, lower = (49, 0) if case == "probability_high" else (100, 51) if case == "probability_low" else (100, 0)
        item = fixture_item(opcode, amount, mode, upper=upper, lower=lower)
        inputs = {self.source + ".ITM": item}
        if case == "alias":
            inputs["COPY.ITM"] = item
        if case == "different_family":
            inputs["POTN41.ITM"] = item
        compiled = build_manifest.build_manifest(inputs)
        self.manifest = self.lua.execute(build_manifest.lua_manifest(compiled))
        for pointer in (shared.EFFECT, shared.ACTIVE):
            self.u.mem_write(pointer + 0x94, self.source.encode().ljust(8, b"\0"))
            self.put(pointer + 0x2C, "HH", upper, lower)
        # Unowned list neighbours must remain byte-exact, including metadata.
        self.u.mem_write(shared.OTHER + 0x94, b"FOREIGN\0")
        if case == "alias":
            self.u.mem_write(shared.ACTIVE + 0x94, b"COPY\0\0\0\0")
        if case == "different_family":
            self.u.mem_write(shared.ACTIVE + 0x94, b"POTN41\0\0")
        if case == "different_source_type":
            self.put(shared.ACTIVE + 0x90, "I", 1)
        if case == "expired":
            self.put(shared.ACTIVE + 0x28, "I", 1000)
        if case == "first":
            self.put(shared.ACTOR + shared.LISTS[1] + 8, "QQI", 0, 0, 0)
        if opcode == 18:
            self.put(shared.ACTIVE + 0x48, "I", 1)  # Native first application has run.
            self.put(shared.ACTOR + 0x57C, "hh", 50, 100)
            self.put(shared.ACTOR + 0x1124, "h", 100 if case == "first" else 110)
            self.put(shared.ACTOR + 0x1DCC, "h", 100 if case == "first" else 110)
        self.seed_stats()
        if opcode in shared.BONUS:
            self.put(shared.ACTOR + shared.BONUS[opcode], "H", 0 if case == "first" else amount)
        self.install_lua()

    def wrapper(self, pointer):
        if pointer not in self.objects:
            self.objects[pointer] = self.lua.eval("""function(pointer, read, write)
                return setmetatable({_ptr=pointer}, {
                    __index=function(_,key)
                        assert(key=='m_duration', 'unexpected native read '..tostring(key))
                        return read(pointer)
                    end,
                    __newindex=function(_,key,value)
                        assert(key=='m_duration', 'unexpected native write '..tostring(key))
                        write(pointer,value)
                    end})
                end""")(pointer, lambda p: self.get(p + 0x28, "I"), self.expiry_write)
        return self.objects[pointer]

    def expiry_write(self, pointer, value):
        require(pointer == shared.ACTIVE, "Lua tried to write an unowned native object")
        require(isinstance(value, (int, float)) and int(value) == value, "expiry is not integral")
        self.put(pointer + 0x28, "I", int(value))
        self.callback_writes.append((pointer + 0x28, 4, int(value)))

    def iterate(self, list_pointer, callback):
        require(list_pointer == shared.ACTOR + shared.LISTS[1], "reader selected wrong native list")
        node, seen = self.get(list_pointer + 8, "Q"), set()
        while node:
            require(node not in seen and len(seen) < 32, "malformed list")
            seen.add(node)
            callback(self.wrapper(self.get(node + 0x10, "Q")))
            node = self.get(node, "Q")

    def install_lua(self):
        wrap = self.lua.eval("function(f) return function(...) return f(...) end end")
        api = self.lua.table()
        for name, fmt in (("EEex_ReadU32", "I"), ("EEex_ReadU16", "H"),
                          ("EEex_ReadU8", "B"), ("EEex_Read32", "i")):
            api[name] = wrap(lambda address, f=fmt: self.get(address, f))
        api.EEex_UDToPtr = self.lua.eval("function(o) return o._ptr end")
        api.EEex_Utility_IterateCPtrList = wrap(self.iterate)
        clock = self.lua.eval("""function(read)
            return setmetatable({}, {__index=function(_,key)
                assert(key=='m_gameTime'); return read() end}) end""")(
                    lambda: self.get(shared.GAME + 0x3FA0, "I"))
        api.EngineGlobals = self.lua.table_from({"g_pBaldurChitin": self.lua.table_from({
            "m_pObjectGame": self.lua.table_from({"m_worldTime": clock})})})
        self.sprite = self.lua.table_from({"_ptr": shared.ACTOR,
                                          "m_timedEffectList": shared.ACTOR + shared.LISTS[1]})
        load = lambda name: self.lua.execute((ROOT / name).read_text(encoding="utf-8"))
        core, messages = load("CBRPQCore.lua"), load("CBRPQMessages.lua")
        env = load("CBRPQNative.lua")(api, self.manifest)
        self.runtime = load("CBRPQRuntime.lua")(core, messages, env, self.manifest, wrap(self.reports.append))

    def candidate_callback(self):
        require(self.reg_read("RDI") == shared.EFFECT and self.reg_read("R14") == shared.ACTOR,
                "native success registers changed")
        self.events["candidate_hook"] += 1
        self.lua_calls += 1
        before, lists = self.read(shared.ACTIVE, SIZE), self.list_snapshot()
        reject = self.runtime.admit(self.wrapper(shared.EFFECT), self.sprite)
        require(self.runtime.status()[0], "Lua runtime disabled: " + repr(self.reports))
        self.active_before_callback, self.active_after_callback = before, self.read(shared.ACTIVE, SIZE)
        require(self.list_snapshot() == lists, "Lua policy mutated native list metadata")
        if reject:
            self.reg_write("RIP", shared.BASE + shared.REJECT)

    def deliver(self):
        # Real lifecycle module, explicitly harness-driven callbacks. This does
        # not assert native hook placement/order by calling those callbacks here.
        frame, message = 101, 201
        self.runtime.fireBegin(frame, 0)
        self.runtime.fireQueue(frame, message, self.wrapper(shared.EFFECT), 0)
        self.runtime.fireEnd(frame)
        self.runtime.messageEnter(message, shared.EFFECT, 0)
        require(self.runtime.status()[0], "Lua preparation disabled: " + repr(self.reports))
        self.run(shared.ADD_EFFECT, shared.ACTOR, shared.EFFECT, 1, 0, 1)
        self.runtime.messageLeave(message)
        self.runtime.destroy(message)
        require(self.runtime.status()[0], "Lua lifecycle disabled: " + repr(self.reports))


def run_probes(image, unicorn, registers, lua_class):
    cases = []
    for opcode in (90, 92, 19, 18):
        for case in ("repeat", "first", "save", "opcode_immunity", "check_effect",
                     "probability_high", "probability_low", "alias", "different_family",
                     "different_source_type", "expired"):
            probe = LuaMachine(image, unicorn, registers, lua_class, opcode, case)
            old = probe.read(shared.ACTIVE, SIZE)
            neighbour = probe.read(shared.OTHER, SIZE)
            actor = probe.read(shared.ACTOR, 0x6000)
            incoming = probe.read(shared.EFFECT, SIZE)
            lists = probe.list_snapshot()
            probe.deliver()
            native_reject = case in {"save", "opcode_immunity", "check_effect", "probability_high", "probability_low"}
            policy_reject = case in {"repeat", "alias"}
            refresh = policy_reject and opcode != 18
            require(probe.lua_calls == int(not native_reject), "native rejection incorrectly invoked Lua")
            require(probe.check_add_result == int(not native_reject and not policy_reject), "wrong native continuation")
            require(probe.events["apply_incoming"] == int(not native_reject and not policy_reject), "unexpected native application")
            expected = bytearray(old)
            if refresh:
                struct.pack_into("<I", expected, 0x28, 1900)
            require(probe.read(shared.ACTIVE, SIZE) == expected, "Lua modified more than the existing expiry")
            require(probe.callback_writes == ([(shared.ACTIVE + 0x28, 4, 1900)] if refresh else []),
                    "unexpected Lua write set")
            require(probe.read(shared.OTHER, SIZE) == neighbour, "unrelated list neighbour changed")
            require(probe.list_snapshot() == lists, "list metadata changed")
            require(probe.events["native_active_write"] == 0, "native applied/changed old active object")
            if policy_reject or native_reject:
                require(probe.read(shared.ACTOR, 0x6000) == actor, "rejected dose changed actor")
                require(probe.events["destroy_incoming"] == 1, "native caller did not dispose rejected incoming")
            # Source, original dispel level10, flags and source metadata are
            # untouched on either native acceptance or policy rejection.
            for start, end in ((0x5C, 0x60), (0x90, 0xD4), (0x110, 0x114)):
                require(probe.read(shared.EFFECT + start, end - start) == incoming[start:end],
                        "delivery metadata changed")
            if opcode == 18 and case == "first":
                require(probe.hp()["current"] == 60 and probe.hp()["derived_maximum"] == 110,
                        "first HP dose no longer uses original native application")
            cases.append({"opcode": opcode, "case": case, "lua_admissions": probe.lua_calls,
                          "native_apply_calls": probe.events["apply_incoming"],
                          "lua_writes": probe.callback_writes,
                          "old_expiry": probe.get(shared.ACTIVE + 0x28, "I")})
    return {"cases": cases, "case_count": len(cases),
            "stubs": {f"{rva:X}": text for rva, text in shared.STUBS.items()},
            "limitations": [
                "Generated EEex assembly/trampolines are not executed; callbacks are harness-driven.",
                "Save/MR/immunity predicates, allocation and full derived-stat rebuild retain explicit stubs.",
                "Constructed native objects model delivery fields; native CItem constructors are not replayed here.",
                "No game, save/load, live object lifetime, multiplayer, nested delivery or linked payload acceptance.",
                "Single-record dose fixtures complement separate Lua multi-record/lifecycle tests.",
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    import unicorn.x86_const as registers
    from lupa import LuaRuntime

    binary = args.exe.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    require(digest == shared.SHA256, "unsupported executable hash: " + digest)
    pe = pefile.PE(data=binary)
    require(pe.OPTIONAL_HEADER.ImageBase == shared.BASE, "unexpected image base")
    image = pe.get_memory_mapped_image()
    for rva, value in shared.SIGNATURES.items():
        require(image[rva:rva + len(bytes.fromhex(value))] == bytes.fromhex(value), f"signature mismatch {rva:X}")
    result = run_probes(image, unicorn, registers, LuaRuntime)
    result.update(status="passed", executable_sha256=digest,
                  scope="actual Lua decisions inside copied native instructions with synthetic services")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
