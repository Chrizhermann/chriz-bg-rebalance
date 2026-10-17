"""Copied native Marshal + actual EEex Lua serializer: count/offset repair proof.

Never launches the game, loads a native DLL, installs a hook or writes a save.
Native allocation, Lua ABI calls and EEex hook dispatch are explicit services.
Actual x64 ADD sets the stock hook's flags, including a negative Lua return.
The original native count, JLE, allocation call, filtered copy and return execute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as native
from probe_native_potion_save import SaveMachine, LIST, BUFFER, OUT

MASK = (1 << 64) - 1
ADD_SERVICE = native.FAKE_CALLS + 0xA00


class RepairMachine(SaveMachine):
    def __init__(self, image, unicorn, registers, eeex, before, after, nine, two,
                 *, repair=True, collector_error=False, large=False):
        super().__init__(image, unicorn, registers)
        from lupa.luajit21 import LuaRuntime
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.before, self.after = before, after
        self.nine, self.two = nine, two
        self.repair, self.collector_error = repair, collector_error
        self.old_normal = self.new_normal = self.extra = self.calculate_return = None
        self.allocated = 0
        self.writes_outside_allocation = []
        self.footer_before_native = None
        self.writer_address = None
        self.writer_calls = 0
        self.seed(before)
        self.u.mem_write(BUFFER, b"\xCC" * 0x2000)
        # ADD RBX,RAX; JMP [RIP] to the unchanged native JLE. The source EEex
        # hook performs this exact 64-bit ADD, not a 32-bit TEST of old EBX.
        self.u.mem_write(ADD_SERVICE, b"\x48\x01\xC3\xFF\x25\0\0\0\0"
                         + struct.pack("<Q", native.BASE + 0x1E5384))
        globals_ = self.lua.globals()
        globals_[b"memory_write"] = self.write_lua
        globals_[b"memory_read"] = self.read_lua
        globals_[b"memory_string"] = self.read_string
        globals_[b"mutate_native_list"] = lambda: self.seed(self.after)
        globals_[b"eligible_bytes"] = lambda: len(self.selected(self.after)) * 0x108
        globals_[b"large"] = large
        globals_[b"repair"] = repair
        globals_[b"collector_error"] = collector_error
        self.lua.execute(b'''
            local formats={[8]='b',[16]='h',[32]='i',[64]='q'}
            for width,fmt in pairs(formats) do
                _G['EEex_Write'..width]=function(p,v) memory_write(p,fmt,v) end
                _G['EEex_Read'..width]=function(p) return memory_read(p,fmt) end
                local unsigned=fmt:upper()
                _G['EEex_WriteU'..width]=function(p,v) memory_write(p,unsigned,v) end
                _G['EEex_ReadU'..width]=function(p) return memory_read(p,unsigned) end
            end
            EEex_WriteString=function(p,s) memory_write(p,'bytes',s..'\0') end
            EEex_WriteLString=function(p,s,n) memory_write(p,'bytes',s:sub(1,n)) end
            EEex_ReadString=function(p) return memory_string(p) end
            EEex_Memset=function(p,v,n) memory_write(p,'bytes',string.rep(string.char(v),n)) end
            EEex_RoundUp=function(n,m) return math.ceil(n/m)*m end
            EEex_Error=error
            ignoredErrors={}
            EEex_Utility_TryIgnore=function(fn,...)
                local ok,result=pcall(fn,...)
                if not ok then ignoredErrors[#ignoredErrors+1]=tostring(result); return nil end
                return result
            end
            EEex_GetUDAux=function(sprite) return sprite.aux end
            EEex_Utility_GetOrCreateTable=function(t,k) t[k]=t[k] or {}; return t[k] end
            CGameEffectBase={sizeof=0x108}
            sprite={aux={}}; loaded={aux={}}
        ''')
        source = (eeex / "EEex_Sprite.lua").read_bytes()
        start = source.index(b"EEex_Sprite_Private_MarshalHandlers = {}")
        end = source.index(b"EEex_Sprite_Private_CustomConcentrationCheckFuncName = nil", start)
        self.lua.execute(source[start:end])
        self.lua.execute(b'''
            foreignCalls=0; importCalls=0
            payload={preserved='foreign metadata',nested={answer=1234,enabled=true},
                padding=string.rep('Z',large and 900 or 0)}
            EEex_Sprite_AddMarshalHandlers('FOREIGN',function()
                foreignCalls=foreignCalls+1
                mutate_native_list()
                return payload
            end,function(_,value)
                importCalls=importCalls+1
                assert(value.preserved==payload.preserved)
                assert(value.nested.answer==1234 and value.nested.enabled)
                assert(value.padding==payload.padding)
            end)
            local calculate=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize
            local write=EEex_Sprite_Hook_WriteExtraEffectListMarshal
            function proposedCalculate(oldNormal)
                extra=calculate(sprite)
                newNormal=eligible_bytes()
                delta=newNormal-oldNormal
                if collector_error then error('failure after original collector') end
                return extra+(repair and delta or 0)
            end
            function proposedWrite(passedMemory)
                write(passedMemory+(repair and delta or 0))
            end
        ''')

    def selected(self, timings):
        return [i for i, timing in enumerate(timings)
                if (not self.nine or timing == 9) and (not self.two or timing != 2)]

    def seed(self, timings):
        native.require(len(timings) <= 12, "probe object bound")
        for ordinal, timing in enumerate(timings):
            pointer = native.EFFECT + ordinal * 0x300
            body = bytearray((i * 17 + ordinal * 11) % 256 for i in range(0x158))
            struct.pack_into("<I", body, 0x24, timing)
            self.u.mem_write(pointer, bytes(body))
            node = native.NODES + ordinal * 0x30
            self.put(node, "QQQ", node + 0x30 if ordinal + 1 < len(timings) else 0,
                     node - 0x30 if ordinal else 0, pointer)
        self.put(LIST + 8, "QQI", native.NODES if timings else 0,
                 native.NODES + (len(timings) - 1) * 0x30 if timings else 0, len(timings))

    def audit_write(self, address, size, origin):
        if BUFFER <= address < BUFFER + 0x2000:
            if address + size > BUFFER + self.allocated:
                self.writes_outside_allocation.append((origin, address - BUFFER, size))

    def write_lua(self, address, fmt, value):
        fmt = fmt.decode()
        value = value if fmt == "bytes" else struct.pack("<" + fmt, int(value))
        address = int(address)
        self.audit_write(address, len(value), "EEex Lua writer")
        native.require(BUFFER <= address and address + len(value) <= BUFFER + 0x2000,
                       "probe metadata memory bound")
        self.u.mem_write(address, value)

    def read_lua(self, address, fmt):
        fmt = fmt.decode()
        return struct.unpack("<" + fmt, self.read(int(address), struct.calcsize(fmt)))[0]

    def read_string(self, address):
        data = self.read(int(address), min(0x1000, BUFFER + 0x2000 - int(address)))
        return data.split(b"\0", 1)[0]

    def on_write(self, uc, access, address, size, value, data):
        if hasattr(self, "allocated"):
            self.audit_write(address, size, "native copy")
        return super().on_write(uc, access, address, size, value, data)

    def on_code(self, uc, address, size, data):
        if address == native.BASE + 0x1E5382 and self.old_normal is None:
            self.old_normal = self.reg_read("EBX")
            ok, value = self.lua.eval(b"function(n) return pcall(proposedCalculate,n) end")(self.old_normal)
            self.extra = int(self.lua.globals()[b"extra"])
            self.new_normal = int(self.lua.globals()[b"newNormal"])
            self.calculate_return = int(value) if ok else 0  # stock call_error XOR RAX,RAX
            native.require(ok != self.collector_error, "unexpected collector status")
            self.reg_write("RAX", self.calculate_return & MASK)
            self.reg_write("RIP", ADD_SERVICE)
            return
        if address == native.BASE + 0x1E5392:
            self.writer_calls += 1
            self.writer_address = BUFFER + self.old_normal + (self.new_normal - self.old_normal if self.repair else 0)
            self.lua.globals()[b"proposedWrite"](BUFFER + self.old_normal)
            self.footer_before_native = self.read(self.writer_address, self.extra)
        return super().on_code(uc, address, size, data)

    def verify_repair(self):
        self.run(0x1E50E0, LIST, OUT, 1, self.nine, self.two)
        expected = b"".join(self.read(native.EFFECT + i * 0x300 + 8, 0x108)
                            for i in self.selected(self.after))
        native.require(self.old_normal == len(self.selected(self.before)) * 0x108, "native original count")
        native.require(self.new_normal == len(expected), "final eligible count")
        native.require(self.allocated == self.new_normal + self.extra == self.reg_read("EAX"),
                       "allocation/native return differ from repaired total")
        native.require(self.get(OUT, "Q") == BUFFER, "wrong returned allocation pointer")
        native.require(self.writer_calls == 1, "writer count")
        native.require(self.read(BUFFER, len(expected)) == expected, "native bytes/order changed")
        native.require(self.read(BUFFER + self.new_normal, self.extra) == self.footer_before_native,
                       "normal copy damaged metadata")
        native.require(self.footer_before_native.startswith(b"X-BIV1.0"), "missing footer")
        native.require(not self.writes_outside_allocation, "write outside repaired allocation")
        native.require(self.read(BUFFER + self.allocated, 32) == b"\xCC" * 32, "post-buffer canary")
        consumed = self.lua.globals()[b"EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal"](
            self.lua.globals()[b"loaded"], BUFFER + self.new_normal)
        native.require(consumed * 0x108 == self.extra, "reader metadata consumption")
        self.lua.execute(b"assert(foreignCalls==1 and importCalls==1 and #ignoredErrors==0)")
        return {"before": self.before, "after": self.after, "only9": self.nine, "exclude2": self.two,
                "old_normal": self.old_normal, "new_normal": self.new_normal,
                "extra": self.extra, "signed_calculate_return": self.calculate_return,
                "allocated_and_native_return": self.allocated,
                "metadata_intact": True, "foreign_roundtrip": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--eeex-dir", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    import unicorn.x86_const as registers
    raw = args.exe.read_bytes()
    native.require(hashlib.sha256(raw).hexdigest() == native.SHA256, "unsupported executable")
    image = pefile.PE(data=raw).get_memory_mapped_image()
    transitions = [([], []), ([], [4096, 9, 2]), ([4096, 9, 2], []),
                   ([4096], [4096, 9, 2]), ([4096, 9, 2], [9]),
                   ([4096, 9, 2, 9, 4096, 9], []),
                   ([2, 2], [4096, 9]), ([4096, 9], [2, 2]),
                   ([4096, 9, 2], [9, 2, 4096])]
    cases = [RepairMachine(image, unicorn, registers, args.eeex_dir, before, after, nine, two,
                           large=large).verify_repair()
             for before, after in transitions
             for nine, two in ((0, 0), (1, 0), (0, 1), (1, 1), (7, 11))
             for large in (False, True)]
    native.require(any(c["signed_calculate_return"] < 0 for c in cases), "negative-return case missing")
    # Retain both failures, using the same actual collector and writer services.
    append = RepairMachine(image, unicorn, registers, args.eeex_dir, [4096], [4096, 4096], 0, 0,
                           repair=False)
    append.run(0x1E50E0, LIST, OUT, 1, 0, 0)
    native.require(append.read(BUFFER + append.old_normal, 8) != b"X-BIV1.0",
                   "unrepaired appended record no longer overwrites footer")
    error = RepairMachine(image, unicorn, registers, args.eeex_dir, [4096], [4096], 0, 0,
                          repair=False, collector_error=True)
    error.run(0x1E50E0, LIST, OUT, 1, 0, 0)
    native.require(error.calculate_return == 0 and error.extra > 0 and error.writes_outside_allocation,
                   "post-collector error must retain unsafe writer state")
    print(json.dumps({"executable_sha256": native.SHA256, "cases": cases,
        "retained_counterexamples": {"unrepaired_append_overwrites_footer": True,
            "post_collector_error_allocated": error.allocated, "stale_extra": error.extra,
            "out_of_allocation_writes": error.writes_outside_allocation},
        "limits": "Actual native count/allocation dispatch/filtered copy/return and stock Lua serializer; "
                  "allocator, Lua ABI dispatch, EEex hook dispatch and list mutations substituted; "
                  "actual x64 stock ADD reproduced. No DLL, hook installation, save or game execution. "
                  "No reentrant marshal or post-final-count mutation support established."}, indent=2))


if __name__ == "__main__":
    main()
