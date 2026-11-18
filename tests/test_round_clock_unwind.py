"""Use the Windows unwinder on BG2's recorded EEex call sites and on fresh EEex frames.

The recorded AsmJit call windows and unwind records run with the normal suite dependencies.
Set CBR_EEEX_SCRIPTS to one or more release script directories (separated by os.pathsep)
and install research/timestop-lab/requirements-native.txt to also assemble and execute
the current source under both Lua interpreters and unwind its instruction-built stack.
"""

import ctypes as ct
import hashlib
import os
from pathlib import Path
import re
import struct
import sys
import unittest

from tests.test_round_clock import CORE, PATTERN, Host, Lua52, LuaJIT

REG_NAMES = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15 rip".split()
NONVOL = "rbx rbp rsi rdi r12 r13 r14 r15".split()
LUA_LABELS = (
    "Hardcoded_InternalLuaState",
    "Hardcoded_lua_getglobal",
    "Hardcoded_lua_getfield",
    "Hardcoded_lua_pushinteger",
    "Hardcoded_lua_pcallk",
    "EEex_CheckCallError",
    "Hardcoded_lua_settop",
    "Hardcoded_lua_tointegerx",
    "Hardcoded_lua_pushboolean",
)

# BG2:EE 2.7.3.0, EEex v1.3.1, Phase 2D. Offsets are relative to the registered
# function start. Keep the actual instruction bytes around each PC so Windows can
# inspect it for an epilogue. The chain descriptor is relocated when registered.
CAPTURE = {
    "checker": (360, "010f06000f6407000f3406000f320b70", {}),
    "gate": (19, "21000000", {0: "40e886feffff8b39b8716eb03640e9abb0cffc"}),
    "dispatch": (345, "0123010005e20000", {240: "40e852fdffff4883f8fe0f8510000000"}),
    "bridge": (413, "010f03000a340e0005e20000", {254: "40e80006b8fc4889d940e87fa0ffff"}),
    "refresh": (
        133,
        "010a03000a34040005420000",
        {
            91: "40e87618d1fcba01000000e90200000031d24889d9",
            112: "40e811feb7fcb801000000488b5c2420488d642428",
        },
    ),
}


@unittest.skipUnless(sys.platform == "win32" and ct.sizeof(ct.c_void_p) == 8, "Win64 unwind API required")
class WindowsUnwindTests(unittest.TestCase):
    def setUp(self):
        k = ct.WinDLL("kernel32")
        ptr, u32, u64 = ct.c_void_p, ct.c_uint32, ct.c_uint64
        self.add = ct.WINFUNCTYPE(ct.c_ubyte, ptr, u32, u64)(("RtlAddFunctionTable", k))
        self.delete = ct.WINFUNCTYPE(ct.c_ubyte, ptr)(("RtlDeleteFunctionTable", k))
        self.lookup = ct.WINFUNCTYPE(ptr, u64, ct.POINTER(u64), ptr)(("RtlLookupFunctionEntry", k))
        self.unwind = ct.WINFUNCTYPE(ptr, u32, u64, u64, ptr, ptr, ct.POINTER(ptr), ct.POINTER(u64), ptr)(
            ("RtlVirtualUnwind", k)
        )
        self.arena = ct.create_string_buffer(0x31000)
        self.base = (ct.addressof(self.arena) + 4095) & ~4095
        self.registered = []
        self.addCleanup(self.remove_tables)

    def remove_tables(self):
        while self.registered:
            self.assertTrue(self.delete(self.registered.pop()))

    def register(self, address, count, base):
        self.assertTrue(self.add(address, count, base))
        self.registered.append(address)
        return True

    def entry(self, pc):
        base = ct.c_uint64()
        entry = self.lookup(pc, ct.byref(base), None)
        self.assertTrue(entry, f"missing runtime function at {pc - self.base:#x}")
        self.assertEqual(base.value, self.base)
        return entry

    def check_walk(self, registers, frames, original):
        context = ct.create_string_buffer(1232 + 15)
        address = (ct.addressof(context) + 15) & ~15
        values = (ct.c_uint64 * len(REG_NAMES)).from_address(address + 0x78)
        for name, value in registers.items():
            values[REG_NAMES.index(name)] = value
        # CONTEXT.FltSave.XmmRegisters[6..15] are the nonvolatile vector registers.
        vector_state = bytes(range(160))
        nonvolatile_xmm = address + 0x1A0 + 6 * 16
        ct.memmove(nonvolatile_xmm, vector_state, len(vector_state))
        for expected_pc, expected_rsp in frames:
            pc = values[REG_NAMES.index("rip")]
            self.unwind(
                0,
                self.base,
                pc,
                self.entry(pc),
                address,
                ct.byref(ct.c_void_p()),
                ct.byref(ct.c_uint64()),
                None,
            )
            self.assertEqual((values[16], values[4]), (expected_pc, expected_rsp))
            self.assertEqual({n: values[REG_NAMES.index(n)] for n in NONVOL}, original)
            self.assertEqual(ct.string_at(nonvolatile_xmm, len(vector_state)), vector_state)

    def check_captured_calls(self):
        # Invalidate this capture when our emitted instructions change. Whitespace
        # and unrelated Lua/installer edits do not change the instruction signature.
        host = Host()
        host.synthetic_pe()
        host.start()
        stubs = (host.g.gate, host.g.dispatchAsm, host.g.bridgeAsm, host.g.refreshAsm)
        assembly = "\n".join(
            " ".join(line.split()) for stub in stubs for line in stub.splitlines() if line.strip()
        )
        self.assertEqual(
            hashlib.sha256(assembly.encode()).hexdigest(),
            "8a808536aef0e129f6b46f2d41a9fa08288b82b994f5c3c0e87dc95c344468cb",
            "Regenerate the Win64 call-site capture for the changed instructions",
        )

        starts = {}
        table = self.base + 0x100
        for i, (name, (size, xdata, windows)) in enumerate(CAPTURE.items()):
            start_rva, unwind_rva = 0x1000 * (i + 1), 0x200 + 32 * i
            starts[name] = self.base + start_rva
            record = struct.pack("<III", start_rva, start_rva + size, unwind_rva)
            ct.memmove(table + 12 * i, record, 12)
            data = bytes.fromhex(xdata)
            if name == "gate":
                data += ct.string_at(table, 12)  # chain into the original checker
            ct.memmove(self.base + unwind_rva, data, len(data))
            for offset, window in windows.items():
                code = bytes.fromhex(window)
                ct.memmove(starts[name] + offset, code, len(code))
        self.register(table, len(CAPTURE), self.base)

        entry, caller = self.base + 0x2F008, self.base + 0x800
        original = {n: 0xA0130000 + i for i, n in enumerate(NONVOL)}
        checker_rsp = entry - 40
        dispatch_rsp = checker_rsp - 8 - 120
        bridge_rsp = dispatch_rsp - 8 - 120
        gate_return = starts["gate"] + 6
        dispatch_return = starts["dispatch"] + 246
        stack = {
            entry: caller,
            entry + 8: original["rbx"],
            entry + 16: original["rsi"],
            entry - 8: original["rdi"],
            checker_rsp - 8: gate_return,
            dispatch_rsp - 8: dispatch_return,
            bridge_rsp + 112: original["rbx"],
        }
        for address, value in stack.items():
            ct.c_uint64.from_address(address).value = value
        for name, offset in (("bridge", 254), ("refresh", 91), ("refresh", 112)):
            call = starts[name] + offset
            self.assertEqual(ct.string_at(call, 2), b"\x40\xe8")
            frames = []
            if name == "bridge":
                rsp = bridge_rsp
                frames = [(dispatch_return, dispatch_rsp), (gate_return, checker_rsp)]
            else:
                rsp = entry - 40
                ct.c_uint64.from_address(rsp + 32).value = original["rbx"]
            for pc in (call, call + 6):  # full CALL instruction and real return PC
                with self.subTest(frame=name, pc=pc - starts[name]):
                    self.check_walk(
                        dict(original, rbx=0xFEED, rsp=rsp, rip=pc),
                        frames + [(caller, entry + 8)],
                        original,
                    )
        self.remove_tables()

    def assemble(self, pc, source):
        # LLVM/Keystone spell the EEex AsmTK byte directive .byte. Emit the symbol addresses
        # after the code, so EEex receives the final label map even when a branch relaxes.
        source = re.sub(r";[^\n]*", "", source).replace(".DB ", ".byte ").replace("jmp short ", "jmp ")
        labels = re.findall(r"(?m)^(\w+):", source)
        trailer = "\n.quad " + ",".join(labels) if labels else ""
        code, _ = self.ks.asm(source + trailer, addr=pc, as_bytes=True)
        if not labels:
            return code, {}
        split = len(code) - 8 * len(labels)
        return code[:split], dict(zip(labels, struct.unpack_from(f"<{len(labels)}Q", code, split)))

    def generate(self, runtime):
        h = Host(runtime)
        lua, g, base = h.lua, h.g, self.base
        base_fn = base + 0x200
        update = base + 0x900
        self.native_calls = {name: base + 0x1000 + 32 * i for i, name in enumerate(LUA_LABELS)}
        self.native_calls["UpdateButtons"] = update
        self.sites = {}
        self.functions = {}
        ct.memset(base, 0, 0x30000)
        ct.memmove(base_fn, PATTERN, len(PATTERN))
        # The native checker's actual RUNTIME_FUNCTION prologue actions on all three 2.7.3.0
        # builds: save RBX and RSI in incoming home space, push RDI, allocate 32 bytes.
        original = struct.pack("<III", 0x200, 0x368, 0x180)
        ct.memmove(base + 0x100, original, len(original))
        ct.memmove(base + 0x180, bytes.fromhex("010f06000f6407000f3406000f320b70"), 16)
        self.register(base + 0x100, 1, base)

        def regex(text, pattern, visit):
            for m in re.finditer(pattern, text, re.MULTILINE):
                groups = lua.table_from({i: v for i, v in enumerate(m.groups(), 1) if v is not None})
                if visit(m.start() + 1, m.end(), m.group(), groups):
                    break

        def jit(pc, relocate, asm):
            while True:
                code, labels = self.assemble(pc, asm)
                next_pc = relocate(len(code))
                if not next_pc:
                    break
                pc = next_pc
            self.assertTrue(base <= pc < pc + len(code) < base + 0x18000)
            ct.memmove(pc, code, len(code))
            for ins in self.decoder.disasm(code, pc):
                if ins.mnemonic == "call":
                    self.sites.setdefault(ins.operands[0].imm, []).append((ins.address, ins.size))
            if "hook_start" in labels:
                self.functions[pc] = labels
            return lua.table(labelAddresses=lua.table_from(labels))

        def load_script(name):
            lua.execute((self.scripts / (name + ".lua")).read_text(encoding="utf-8-sig"))

        g.EEex_DoFile = load_script
        lua.execute('EEex_Architecture="x86-64"; function EEex_GetPatternMap() return {} end')
        load_script("EEex_Assembly")
        g.EEex_IterateRegex, g.EEex_JITAtInternal = regex, jit
        g.EEex_JITGetSize = lambda pc, s: len(self.assemble(pc, s)[0])
        g.base, g.block = base, base + 0x3000
        g.EEex_AllocCodePageInternal = lambda: (base + 0x5000, 0x10000)
        g.EEex_RtlAddFunctionTable, g.EEex_RtlLookupFunctionEntry = self.register, self.entry
        g.EEex_Memcpy = lambda dest, src, n: ct.memmove(dest, src, n) and None
        g.bytes_at = lambda a, n: ct.string_at(a, n)
        g.native_read = lambda a, n, signed: int.from_bytes(ct.string_at(a, n), "little", signed=signed)
        g.native_write = lambda a, n, v: (
            ct.memmove(a, (int(v) % (1 << (8 * n))).to_bytes(n, "little"), n) and None
        )
        callee = base + 0x2100
        clobbers = ["xor eax, eax", "mov r11d, 0xbad"]
        clobbers.extend(f"pxor xmm{i}, xmm{i}" for i in range(6))
        callee_code, _ = self.assemble(callee, "\n".join(clobbers + ["ret"]))
        ct.memmove(callee, callee_code, len(callee_code))
        for name, address in self.native_calls.items():
            g.EEex_DefineAssemblyLabel(name, address)
            if name == "Hardcoded_InternalLuaState":
                ct.c_uint64.from_address(address).value = base + 0x2200
            else:
                jump = b"\xe9" + struct.pack("<i", callee - (address + 5))
                ct.memmove(address, jump, len(jump))
        lua.execute("""
            function EEex_ToDecStr(n) return string.format("%.0f",n) end
            function EEex_DistanceToMultiple(n,m) return m==0 and 0 or (m-n%m)%m end
            function EEex_WriteStringCache() return base+0x2000 end
            function EEex_BOr(a,b) return a+b end -- writer combines disjoint bitfields
            function EEex_LShift(a,b) return a*2^b end
            function EEex_ReadLString(a,n) return bytes_at(a,n) end
            function EEex_ReadU8(a) return native_read(a,1,false) end
            function EEex_Read32(a) return native_read(a,4,true) end
            function EEex_ReadU32(a) return native_read(a,4,false) end
            function EEex_WriteU8(a,v) native_write(a,1,v) end
            function EEex_WriteU16(a,v) native_write(a,2,v) end
            function EEex_Write32(a,v) native_write(a,4,v) end
            function EEex_WritePtr(a,v) native_write(a,8,v) end
            function EEex_Malloc() return block end
            function EEex_ExposeToLua(a,name)
                if name=="CBRRC_CaptureThread" then
                    _G[name]=function() EEex_Write32(block+8,1234) end
                else
                    refresh=a; _G[name]=function() end
                end
            end
        """)
        lua.execute(CORE)
        g.CBRRC.Inspect = lua.eval("""function() return {name="fixture",base=base,imageSize=0x4000,
            site=base+0x20f,chitin=base+0x2800,
            returns={base+0x400,base+0x410,base+0x420,base+0x430}} end""")
        g.CBRRC.InspectToolbar = lua.eval("function() return base+0x900 end")
        status = g.CBRRC.Start()
        self.assertTrue(status.enabled, list(g.logs.values()))
        gate = base_fn + 20 + g.EEex_Read32(base_fn + 16)

        def generated_call(start):
            end = self.functions[start]["hook_end"]
            ((dest, pc, length),) = [
                (dest, pc, length)
                for dest, sites in self.sites.items()
                for pc, length in sites
                if dest in self.functions and start <= pc < end
            ]
            return dest, pc + length

        dispatcher, gate_return = generated_call(gate)
        _, dispatch_return = generated_call(dispatcher)
        return base_fn, dispatch_return, gate_return, int(g.refresh)

    def test_virtual_unwind_from_commit_and_both_toolbar_calls(self):
        self.check_captured_calls()
        for scripts in os.environ.get("CBR_EEEX_SCRIPTS", "").split(os.pathsep):
            if scripts:
                self.scripts = Path(scripts)
                with self.subTest(eeex=self.scripts):
                    self.check_fresh_calls()

    def check_fresh_calls(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        from keystone import Ks, KS_ARCH_X86, KS_MODE_64
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
        from unicorn import x86_const as x86

        self.ks = Ks(KS_ARCH_X86, KS_MODE_64)
        self.decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        self.decoder.detail = True
        base = self.base
        regs = {n: getattr(x86, "UC_X86_REG_" + n.upper()) for n in REG_NAMES}
        for runtime in (Lua52, LuaJIT):
            with self.subTest(lua=runtime):
                fn, dispatch_return, gate_return, refresh = self.generate(runtime)
                for target in ("Hardcoded_lua_pcallk", "UpdateButtons", "Hardcoded_lua_pushboolean"):
                    with self.subTest(target=target):
                        (pc,) = [addr for addr, _ in self.sites[self.native_calls[target]]]
                        cpu = Uc(UC_ARCH_X86, UC_MODE_64)
                        cpu.mem_map(base, 0x30000)
                        cpu.mem_write(base, ct.string_at(base, 0x30000))
                        cpu.reg_write(x86.UC_X86_REG_GS_BASE, base + 0x4000)
                        cpu.mem_write(base + 0x4048, struct.pack("<I", 1234))
                        cpu.mem_write(base + 0x2800, struct.pack("<Q", base + 0x18000))
                        cpu.mem_write(base + 0x19090, struct.pack("<Q", base + 0x1A000))
                        entry_rsp, caller = base + 0x2F008, base + 0x400
                        cpu.mem_write(entry_rsp, struct.pack("<Q", caller))
                        original = {n: 0xA0130000 + i for i, n in enumerate(NONVOL)}
                        for n, v in original.items():
                            cpu.reg_write(regs[n], v)
                        cpu.reg_write(regs["rsp"], entry_rsp)
                        cpu.reg_write(regs["rcx"], base + 0x2800)
                        is_gate = target == "Hardcoded_lua_pcallk"
                        if is_gate:
                            cpu.emu_start(fn, fn + 15)
                            cpu.reg_write(x86.UC_X86_REG_EFLAGS, 0x8D7)
                            cpu.reg_write(regs["r11"], 0xC011)
                            xmm = {
                                getattr(x86, f"UC_X86_REG_XMM{i}"): ((0xABCD + i) << 112) + i
                                for i in range(16)
                            }
                            for reg, value in xmm.items():
                                cpu.reg_write(reg, value)
                            before = {n: cpu.reg_read(regs[n]) for n in REG_NAMES[:-1]}
                        cpu.emu_start(fn + 15 if is_gate else refresh, pc, count=1000)
                        self.assertEqual(cpu.reg_read(regs["rip"]), pc)
                        self.assertEqual(cpu.reg_read(regs["rsp"]) % 16, 0)
                        # The stack is built by the instructions themselves. Windows reads the
                        # same virtual addresses in this process; no saved slots are synthesized.
                        ct.memmove(base + 0x2C000, bytes(cpu.mem_read(base + 0x2C000, 0x4000)), 0x4000)
                        saved = {n: cpu.reg_read(regs[n]) for n in REG_NAMES}
                        self.assertNotEqual(saved["rbx"], original["rbx"])
                        frames = (
                            [(dispatch_return, entry_rsp - 40 - 8 - 120), (gate_return, entry_rsp - 40)]
                            if is_gate
                            else []
                        )
                        self.check_walk(saved, frames + [(caller, entry_rsp + 8)], original)
                        if is_gate:
                            cpu.emu_start(pc, fn + 22, count=1000)
                            self.assertEqual(cpu.reg_read(regs["rip"]), fn + 22)
                            self.assertEqual(cpu.reg_read(x86.UC_X86_REG_EFLAGS), 0x8D7)
                            self.assertEqual({reg: cpu.reg_read(reg) for reg in xmm}, xmm)
                            before.update(rax=0x36B06E71, rdi=base + 0x18000 & 0xFFFFFFFF)
                            self.assertEqual({n: cpu.reg_read(regs[n]) for n in before}, before)
                self.remove_tables()
