"""Optional ML64 + Unicorn execution of real EEex-generated trampoline code.

Set EEEX_LUA_DIR, EEEX_POTION_PYLIBS (unicorn), and EEEX_POTION_ML64. Uses a local
assembler only; neither Baldur.exe nor EEex/native Lua DLL functions execute.
Actual generated instructions, including watchdog assembly helpers, run under
Unicorn. External Lua/watchdog/native callees are deliberately clobbering stubs.
Generated source/objects stay in a new temp directory for failure inspection.
"""
from pathlib import Path
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from tests.test_potion_hook_preprocessor import PreprocessorHarness, EEEX, ALLOW, REJECT
from tests.test_potion_transport_preprocessor import TransportHarness, read_image, SITES

LIBS = os.environ.get("EEEX_POTION_PYLIBS")
ML64 = os.environ.get("EEEX_POTION_ML64")
if LIBS:
    sys.path.insert(0, LIBS)
if LIBS and ML64 and EEEX:
    import unicorn
    from unicorn import x86_const as x86


def assemble(text, address, directory, name):
    externs = {}
    def external(match):
        mnemonic, number = match[1], int(match[2])
        label = "external_" + str(number)
        externs[label] = number
        return mnemonic + " " + label
    text = re.sub(r"(?m)^(call|jmp|jz|jnz) (?:short )?(\d+)\s*$", external, text)
    text = re.sub(r"0x([0-9A-Fa-f]+)", lambda m: "0" + m[1] + "h", text)
    # MASM rejects EEex's redundant DS/SS qualifiers in 64-bit mode. These
    # segment bases are architecturally zero here; FS/GS are never stripped.
    text = text.replace("ss:[", "[").replace("ds:[", "[")
    text = text.replace(".DB ", "DB ")
    source = "option casemap:none\n" + "\n".join("EXTERN " + n + ":PROC" for n in externs)
    source += "\n.code\nentry PROC\n" + text + "\nentry ENDP\nEND\n"
    asm, obj = directory / (name + ".asm"), directory / (name + ".obj")
    asm.write_text(source, encoding="ascii")
    result = subprocess.run([ML64, "/nologo", "/c", "/Fo" + str(obj), str(asm)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr + "\nsource: " + str(asm)
    data = obj.read_bytes()
    machine, nsections, _, symptr, nsymbols, optsize, _ = struct.unpack_from("<HHIIIHH", data)
    assert machine == 0x8664 and optsize == 0
    string_base = symptr + nsymbols * 18
    def symbol(index):
        at = symptr + index * 18
        raw = data[at:at + 8]
        if raw[:4] == b"\0\0\0\0":
            start = string_base + struct.unpack_from("<I", raw, 4)[0]
            return data[start:data.index(0, start)].decode()
        return raw.rstrip(b"\0").decode()
    for section in range(nsections):
        at = 20 + section * 40
        if not data[at:at + 8].startswith(b".text"):
            continue
        length, offset, reloc = struct.unpack_from("<III", data, at + 16)
        count = struct.unpack_from("<H", data, at + 32)[0]
        code = bytearray(data[offset:offset + length])
        for i in range(count):
            position, sym, kind = struct.unpack_from("<IIH", data, reloc + i * 10)
            assert kind == 4, f"unsupported COFF relocation {kind}"
            target = externs[symbol(sym)]
            addend = struct.unpack_from("<i", code, position)[0]
            struct.pack_into("<i", code, position, target + addend - (address + position + 4))
        return bytes(code)
    raise AssertionError("assembler emitted no .text")


class GeneratedMachine:
    STACK = 0x20000000
    DATA = 0x21000000
    GPRS = ("RAX", "RCX", "RDX", "RBX", "RSP", "RBP", "RSI", "RDI",
            "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15")
    VOLATILE = ("RAX", "RCX", "RDX", "R8", "R9", "R10", "R11")

    def __init__(self, harness, directory, entry_index, destination, lua_result=0,
                 lua_error=False, native_call=False, initial_flags=0x202, initializer=None):
        self.h = harness
        self.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        self.uc.mem_map(0x140800000, 0x200000)
        self.uc.mem_map(0x180000000, 0x20000)
        self.uc.mem_map(self.STACK, 0x40000)
        self.uc.mem_map(self.DATA, 0x10000)
        self.destinations = set(destination)
        for dest in self.destinations:
            self.uc.mem_map(dest & ~0xFFF, 0x1000)
        self.uc.mem_write(0x180000000, b"\xc3" * 0x20000)
        self.lua_result, self.lua_error = lua_result, lua_error
        self.watchdog_frames, self.watchdog_checks = [], 0
        self.lua_calls, self.lua_arguments, self.native_calls = [], [], 0
        self.native_result = None
        self.native_target = 0x180010000
        self.stop = None
        self.code = []
        for index, (text, _) in enumerate(harness.assemblies):
            address = 0x140800000 + (index + 1) * 0x10000
            code = assemble(text, address, directory, f"{entry_index}_assembly_{index}")
            self.uc.mem_write(address, code)
            self.code.append(address)
        for i, name in enumerate(self.GPRS):
            self.write(name, 0x123000000 + i * 0x1100)
        self.initial_rsp = self.STACK + 0x20000
        if entry_index in (9, 10, 11, 12):  # watchdog helpers occupy first2 entries
            self.initial_rsp += 8
        self.write("RSP", self.initial_rsp)
        self.uc.mem_write(self.initial_rsp, bytes(range(128)))
        for i in range(6):
            self.uc.reg_write(getattr(x86, f"UC_X86_REG_XMM{i}"), (0x1122334455667788 + i) << 64 | (0xAABBCCDDEEFF0000 + i))
        self.uc.reg_write(x86.UC_X86_REG_EFLAGS, initial_flags)
        if native_call:
            self.write("RAX", self.DATA)
            self.write("R9", 0)
            self.uc.mem_write(self.DATA + 0xE8, struct.pack("<Q", self.native_target))
            self.uc.mem_write(self.initial_rsp + 0x20, struct.pack("<Q", 1))
        if initializer:
            initializer(self)
        self.initial = self.snapshot()
        self.initial_stack = bytes(self.uc.mem_read(self.initial_rsp, 128))
        self.uc.hook_add(unicorn.UC_HOOK_CODE, self.hook)
        self.uc.emu_start(self.code[entry_index], 0, count=50000)
        assert self.stop in self.destinations, f"failed to reach native continuation: {self.stop}"
        assert not self.watchdog_frames, "unbalanced runtime watchdog frames"

    def read(self, name):
        return self.uc.reg_read(getattr(x86, "UC_X86_REG_" + name))

    def write(self, name, value):
        self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)

    def snapshot(self):
        result = {name: self.read(name) for name in self.GPRS}
        result.update({f"XMM{i}": self.uc.reg_read(getattr(x86, f"UC_X86_REG_XMM{i}")) for i in range(6)})
        result["FLAGS"] = self.uc.reg_read(x86.UC_X86_REG_EFLAGS)
        return result

    def clobber(self, retval=0):
        for i, name in enumerate(self.VOLATILE):
            self.write(name, 0x777000000 + i * 0x111)
        self.write("RAX", retval)
        for i in range(6):
            self.uc.reg_write(getattr(x86, f"UC_X86_REG_XMM{i}"), (i + 1) * 0x987654321)
        self.uc.reg_write(x86.UC_X86_REG_EFLAGS, 0xAD7)

    def hook(self, uc, address, size, _):
        if address in self.destinations:
            self.stop = address
            uc.emu_stop()
            return
        if address == self.native_target:
            assert self.read("RSP") == self.initial_rsp - 8
            for name in ("RCX", "RDX", "R8", "R9"):
                assert self.read(name) == self.initial[name], "native argument changed: " + name
            assert struct.unpack("<Q", uc.mem_read(self.read("RSP") + 0x28, 8))[0] == 1
            self.clobber(0xABCDEF)
            self.native_calls += 1
            self.native_result = self.snapshot()
            self.native_result["RSP"] = self.initial_rsp
            return
        reverse = {value: key for key, value in self.h.addresses.items()}
        name = reverse.get(address)
        if name is None and address == 0x180003000:
            name = "Hardcoded_lua_pushinteger"
        if name is None:
            return
        assert self.read("RSP") % 16 == 8, f"unaligned external call: {name}"
        if name.startswith("EEex::HookIntegrityWatchdog"):
            snapshot_pointer = self.read("RDX" if name.endswith("Enter") else "R8")
            registers = struct.unpack("<16Q", uc.mem_read(snapshot_pointer, 128))
            assert registers[5] == self.initial_rsp, "watchdog received scratch RSP instead of native RSP"
            stack = bytes(uc.mem_read(registers[5], 64))
            if name.endswith("Enter"):
                self.watchdog_frames.append((registers, stack, self.read("RCX")))
            else:
                before, before_stack, hook_address = self.watchdog_frames.pop()
                assert registers == before, "watchdog detected changed GPRs"
                assert stack == before_stack, "watchdog detected changed original stack"
                assert self.read("RCX") == hook_address and self.read("RDX") == 0
                self.watchdog_checks += 1
            self.clobber()
        else:
            self.lua_calls.append(name)
            if name in ("Hardcoded_lua_pushinteger", "Hardcoded_tolua_pushusertype"):
                self.lua_arguments.append((name, self.read("RDX")))
            value = (int(self.lua_error) if name == "EEex_CheckCallError" else
                     self.lua_result if name == "Hardcoded_lua_toboolean" else 0)
            self.clobber(value)


@unittest.skipUnless(EEEX and LIBS and ML64, "optional: EEEX_LUA_DIR, EEEX_POTION_PYLIBS and EEEX_POTION_ML64")
class GeneratedPotionTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="cbr-potion-generated-trampoline-"))
        cls.image = read_image()

    def test_admission_watchdog_preserves_all_registers_flags_and_original_stack(self):
        for result, error, flags in ((0, False, 0x202), (1, False, 0x202),
                                     (0, True, 0x202), (0, False, 0x242)):
            with self.subTest(result=result, error=error, flags=flags):
                h = PreprocessorHarness(watchdog=True)
                h.install()
                m = GeneratedMachine(h, self.directory, 2, {ALLOW, REJECT}, result, error, initial_flags=flags)
                self.assertEqual(m.initial, m.snapshot())
                self.assertEqual(m.initial_stack, bytes(m.uc.mem_read(m.initial_rsp, 128)))
                self.assertEqual(REJECT if result or flags & 0x40 else ALLOW, m.stop)
                self.assertEqual(0 if flags & 0x40 else 1, m.watchdog_checks)

    def test_run_checks_callbacks_separately_and_preserves_native_callee_outputs(self):
        for error in (False, True):
            h = TransportHarness(self.image, watchdog=True)
            h.install()
            m = GeneratedMachine(h, self.directory, 8, {0x14020FE64}, lua_error=error, native_call=True)
            self.assertEqual(1, m.native_calls)
            self.assertEqual(2, m.watchdog_checks)
            self.assertEqual(m.native_result, m.snapshot())

    def test_destructor_and_reset_entry_alignment_and_native_replay(self):
        h = TransportHarness(self.image, watchdog=True)
        h.install()
        for index in (9, 10, 11, 12):
            with self.subTest(index=index):
                m = GeneratedMachine(h, self.directory, index, {0x140000000 + SITES[index - 2] + 5})
                expected = dict(m.initial)
                if index == 12:
                    expected["RAX"], expected["RSP"] = m.initial_rsp, m.initial_rsp - 16
                self.assertEqual(expected, m.snapshot())
                self.assertEqual(1, m.watchdog_checks)

    def test_unprotected_watchdog_negative_control_reproduces_xmm_corruption(self):
        h = PreprocessorHarness(watchdog=True)
        unsafe = h.lua.eval("{validate=function() end, withPreservation=function(api,fn) return fn() end}")
        h.hook.install(h.lua.globals(), "CBRPQTestCallback", unsafe)
        m = GeneratedMachine(h, self.directory, 2, {ALLOW, REJECT})
        self.assertNotEqual(m.initial["XMM0"], m.snapshot()["XMM0"])
        self.assertEqual(1, m.watchdog_checks)

    def test_projectile_callbacks_capture_identity_and_replay_before_unmodified_calls(self):
        h = TransportHarness(self.image, watchdog=True)
        h.install()
        def initialize(m):
            m.write("RBX", m.DATA + 0x200)
            m.write("RSI", 22)
            m.write("RDI", 33)
            m.uc.mem_write(m.DATA + 0x200 + 0x4AD8, struct.pack("<Q", m.DATA + 0x300))
        for index, destination in ((13, 0x1403BBBD7), (14, 0x14016A675)):
            with self.subTest(index=index):
                m = GeneratedMachine(h, self.directory, index, {destination}, initializer=initialize)
                expected = dict(m.initial)
                expected["RCX"] = m.DATA + 0x300 if index == 13 else m.initial["R14"]
                if index == 14:
                    expected["RDX"] = m.initial["RBX"]
                self.assertEqual(expected, m.snapshot())
                self.assertEqual(1, m.watchdog_checks)
                self.assertEqual([m.initial["RBP"] if index == 13 else m.initial_rsp,
                                  m.initial["RDI"] if index == 13 else m.initial["RBX"],
                                  22 if index == 13 else 33,
                                  m.DATA + 0x300 if index == 13 else m.initial["R14"]],
                                 [arg[1] for arg in m.lua_arguments])


if __name__ == "__main__":
    unittest.main()
