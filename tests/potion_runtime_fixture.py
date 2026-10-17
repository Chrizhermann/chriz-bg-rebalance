"""Whole-resource bridge to actual Lua modules using explicit engine doubles.

ITM construction, native predicate outcome, effect insertion and the V2 save copy
are simulated. No native code, hooks, game, HP arithmetic or full save is run.
This catches disagreements between compiler/reader/transport policy for complete
abilities, including unowned records, rather than proving engine acceptance.
"""
from __future__ import annotations

from pathlib import Path
import struct

from lupa.luajit21 import LuaRuntime
from tests.test_potion_admission_manifest import compiler
from tests.test_potion_native_reader import FIELDS

MODULES = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


class ResourceRuntimeFixture:
    def __init__(self, resources, policy="unique", read_resource=None):
        self.resources = {name.upper(): bytes(data) for name, data in resources.items()}
        self.manifest = compiler.build_manifest(self.resources, policy, read_resource=read_resource)
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.memory, self.objects, self.meta = {}, {}, {}
        self.writes, self.trace, self.diagnostics = [], [], []
        self.next_pointer = 0x200000000
        self.next_message = 0x300000000
        self.now = 1000
        self.lua.globals().fixture_read = self.read
        self.lua.globals().fixture_write = self.write
        self.lua.globals().fixture_report = self.diagnostics.append
        self.lua.globals().fixture_clock = lambda: self.now
        self.lua.execute('''
            function native_object(pointer)
                return setmetatable({}, {
                    __index=function(_, key)
                        if key == "pointer" then return pointer end
                        if key == "m_duration" then return fixture_read(pointer+0x28, "I") end
                        error("unexpected native field " .. tostring(key))
                    end,
                    __newindex=function(_, key, value)
                        assert(key == "m_duration", "unexpected native write")
                        fixture_write(pointer+0x28, value)
                    end,
                })
            end
            api = {
                EEex_ReadU32=function(p) return fixture_read(p, "I") end,
                EEex_Read32=function(p) return fixture_read(p, "i") end,
                EEex_ReadU16=function(p) return fixture_read(p, "H") end,
                EEex_ReadU8=function(p) return fixture_read(p, "B") end,
                EEex_ReadPtr=function(p) return fixture_read(p, "Q") end,
                EEex_GetImageBase=function() return 0x140000000 end,
                EEex_UDToPtr=function(o) return o.pointer end,
                EEex_Utility_IterateCPtrList=function(list, fn)
                    for _, effect in ipairs(list) do if fn(effect) then break end end
                end,
                EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_worldTime=setmetatable({}, {
                    __index=function(_, key) assert(key=="m_gameTime"); return fixture_clock() end,
                })}}},
            }
            function load_parts(folder, manifest, extra)
                local core = dofile(folder .. "/CBRPQCore.lua")
                local messages = dofile(folder .. "/CBRPQMessages.lua")
                local reader = dofile(folder .. "/CBRPQNative.lua")(api, manifest)
                return dofile(folder .. "/CBRPQRuntime.lua")(core, messages, reader, manifest,
                    function(reason) fixture_report(reason) end,extra),reader
            end
        ''')
        self.runtime, self.reader = self.load_runtime()
        self.sprite_pointer = self.allocate()
        self.put(self.sprite_pointer + 0x48, "I", 42)
        self.sprite = self.table({"pointer": self.sprite_pointer, "m_timedEffectList": []})
        self.projectile_pointer = self.allocate()
        self.put(self.projectile_pointer, "Q", 0x14059BFF0)

    def load_runtime(self):
        return self.lua.globals().load_parts(MODULES.as_posix(), self.table(self.manifest))

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({key: self.table(item) for key, item in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(item) for item in value])
        return value

    def allocate(self):
        pointer = self.next_pointer
        self.next_pointer += 0x1000
        for offset in range(0x200):
            self.memory[pointer + offset] = 0
        return pointer

    def put(self, address, fmt, value):
        for offset, byte in enumerate(struct.pack("<" + fmt, value)):
            self.memory[address + offset] = byte

    def read(self, address, fmt):
        return struct.unpack("<" + fmt, bytes(self.memory[address + offset]
                             for offset in range(struct.calcsize("<" + fmt))))[0]

    def write(self, address, value):
        self.writes.append((address, self.read(address, "I"), value))
        self.put(address, "I", value)

    def resref(self, address, value):
        for offset, byte in enumerate(value.encode("ascii").ljust(8, b"\0")):
            self.memory[address + offset] = byte

    def bytes(self, pointer, start=0, end=0x180):
        return bytes(self.memory[pointer + offset] for offset in range(start, end))

    def effects(self):
        return [int(obj.pointer) for obj in self.sprite.m_timedEffectList.values()]

    def queue(self, source, ability_index=0):
        source = source.upper()
        node = compiler.audit.parse_resource(source + ".ITM", self.resources[source + ".ITM"])
        ability = next(part for part in node["slices"] if part["kind"] == f"ability:{ability_index}")
        raw_ability = bytes.fromhex(ability["raw_ability_hex"])
        frame, queued = self.next_message, []
        self.runtime.useBegin(frame, ability_index)
        for ordinal, effect in enumerate(ability["effects"]):
            fields = compiler._fields(effect, raw_ability, strict_resource=False)
            pointer = self.allocate()
            for key, (offset, fmt) in FIELDS.items():
                self.put(pointer + offset, fmt, fields[key])
            self.resref(pointer + 0x30, fields["resource"])
            self.put(pointer + 0x90, "I", 2)
            self.resref(pointer + 0x94, source)
            self.put(pointer + 0xC8, "I", 10)
            self.put(pointer + 0xCC, "I", 1)
            self.put(pointer + 0x110, "I", 42)
            self.put(pointer + 0x150, "I", 99)  # Selected target differs from self.
            self.objects[pointer] = self.lua.globals().native_object(pointer)
            self.meta[pointer] = (source, ordinal, fields)
            self.next_message += 1
            queued.append((self.next_message, pointer))
            if fields["target"] == 2:
                self.runtime.useProjectile(frame, self.objects[pointer], ordinal, self.projectile_pointer)
            else:
                self.runtime.useQueue(frame, self.next_message, self.objects[pointer], ordinal)
        self.runtime.useEnd(frame)
        self.assert_enabled()
        return queued

    def deliver(self, queued, rejected_ordinals=()):
        outcomes = []
        for message, pointer in queued:
            obj = self.objects[pointer]
            source, ordinal, fields = self.meta[pointer]
            self.runtime.messageEnter(message, pointer, 0)
            # Native failures never call the success-boundary callback.
            reject = ordinal in rejected_ordinals
            if not reject:
                reject = bool(self.runtime.admit(obj, self.sprite))
            self.assert_enabled()
            self.trace.append((source, ordinal, not reject))
            if not reject and fields["timing"] in (0, 10) and fields["duration"] > 0:
                self.put(pointer + 0x24, "I", 4096)
                self.put(pointer + 0x28, "I", self.now + fields["duration"] * (15 if fields["timing"] == 0 else 1))
                if fields["opcode"] == 18:
                    self.put(pointer + 0x48, "I", fields["special"] | 1)
                self.sprite.m_timedEffectList[len(self.sprite.m_timedEffectList) + 1] = obj
            elif reject:
                self.runtime.effectDestroy(pointer)
            self.runtime.messageLeave(message)
            self.runtime.destroy(message)
            outcomes.append(not reject)
        return outcomes

    def remove(self, pointer):
        self.runtime.effectDestroy(pointer)
        remaining = [self.objects[p] for p in self.effects() if p != pointer]
        self.sprite.m_timedEffectList = self.table(remaining)

    def saved_active_roundtrip(self):
        """Only the source-proven V2 +08..10F field copy; no real save/load."""
        images = [(self.bytes(p, 8, 0x110), self.meta[p]) for p in self.effects()]
        self.runtime.reset()
        self.sprite.m_timedEffectList = self.table([])
        for image, meta in images:
            pointer = self.allocate()
            for offset, byte in enumerate(image, 8):
                self.memory[pointer + offset] = byte
            self.meta[pointer] = meta
            self.objects[pointer] = self.lua.globals().native_object(pointer)
            self.sprite.m_timedEffectList[len(self.sprite.m_timedEffectList) + 1] = self.objects[pointer]

    def assert_enabled(self):
        status = self.runtime.status()
        enabled, reason = status if isinstance(status, tuple) else (status, None)
        if not enabled:
            raise AssertionError(reason)
