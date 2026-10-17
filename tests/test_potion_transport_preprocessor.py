"""Optional real-EEex preprocessing tests for the opt-in transport preparation.

Set EEEX_LUA_DIR to local EEex 1.3 EEex_scripts. By default the pinned Baldur.exe
is read beside that directory; EEEX_POTION_EXE can select another pinned copy.
Reads only: no game/DLL execution, native assembler, executable-memory writes,
installation or save edits. Regex/memory/JIT services are explicitly stubbed.
"""
from pathlib import Path
import hashlib
import os
import re
import struct
import unittest

from tests.test_potion_hook_preprocessor import PreprocessorHarness, EEEX, ROOT, instructions


MODULE = ROOT / "research/prototypes/potion-admission/CBRPQTransport.lua"
EXE_SHA256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
BASE = 0x140000000
CALLBACKS = ("useBegin", "useQueue", "useEnd", "fireBegin", "fireQueue", "fireEnd",
             "messageEnter", "messageLeave", "destroy", "effectDestroy", "reset",
             "useProjectile", "fireProjectile")
SITES = (0x3BBA88, 0x3BBB7D, 0x3BBCF6, 0x16A538, 0x16A623, 0x16A79E, 0x20FE5E,
         0x1551B0, 0x14C8E0, 0x1A45A0, 0x2930C0, 0x3BBBD0, 0x16A66F)
GUARDS = SITES + (0x3BAF2A, 0x3BBB54, 0x16A5FA, 0x20FE42)


def read_image():
    path = Path(os.environ.get("EEEX_POTION_EXE", str(Path(EEEX).parent / "Baldur.exe")))
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXE_SHA256, "requires pinned BG2EE 2.7.3.0 executable"
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0"
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    assert struct.unpack_from("<Q", data, optional + 24)[0] == BASE
    image = bytearray(struct.unpack_from("<I", data, optional + 56)[0])
    headers = struct.unpack_from("<I", data, optional + 60)[0]
    image[:headers] = data[:headers]
    for i in range(sections):
        header = optional + optional_size + i * 40
        _, rva, length, offset = struct.unpack_from("<IIII", data, header + 8)
        image[rva:rva + length] = data[offset:offset + length]
    return image


class TransportHarness(PreprocessorHarness):
    def __init__(self, image, watchdog=False):
        super().__init__(watchdog=watchdog)
        self.image = bytearray(image)
        g = self.lua.globals()
        g.EEex_GetImageBase = lambda: BASE
        g.EEex_ReadU8 = lambda address: self.image[int(address) - BASE]
        g.EEex_Read32 = lambda address: struct.unpack_from("<i", self.image, int(address) - BASE)[0]
        # Lupa exposes Python callables as userdata; actual native EEex APIs are
        # Lua-visible C functions. Wrap only these substituted native services.
        wrap = self.lua.eval("function(f) return function(...) return f(...) end end")
        for key in ("EEex_GetImageBase", "EEex_ReadU8", "EEex_DisableCodeProtection",
                    "EEex_EnableCodeProtection"):
            g[key] = wrap(g[key])
        g.EEex_GlobalAssemblyLabels.Hardcoded_lua_pushinteger = 0x180003000
        for key in CALLBACKS:
            self.lua.execute(f"function CBRPQTransport_{key}(...) end")
        self.config = self.lua.table_from({"callbacks": self.lua.table_from(
            {key: "CBRPQTransport_" + key for key in CALLBACKS})})
        self.hook = self.lua.execute(MODULE.read_text(encoding="utf-8"))

    def install(self):
        return self.hook.install(self.lua.globals(), self.config, self.watchdog)

    def validate(self):
        return self.hook.validate(self.lua.globals(), self.config, self.watchdog)


def inspect_paths(text, entry_alignment, original_calls):
    """Inspect all generated branch paths; external calls assumed ABI-compliant.

    The two original native call sites already own caller shadow space. The
    copied six-byte indirect call is recognized exactly and must run at delta0.
    No assembler/register-emulation claim is made by this static inspection.
    """
    code = instructions(text)
    labels = {line[:-1]: i for i, line in enumerate(code) if line.endswith(":")}
    todo, seen, exits, calls, copied_call = [(0, 0)], set(), set(), set(), set()
    while todo:
        i, delta = todo.pop()
        if (i, delta) in seen:
            continue
        seen.add((i, delta))
        assert len(seen) < 2000 and i < len(code), "unbounded/fallthrough assembly"
        line = code[i]
        if line.startswith("push"):
            delta -= 8
        elif line.startswith("pop"):
            delta += 8
        elif match := re.fullmatch(r"(sub|add) rsp, ([0-9a-f]+)h", line):
            delta += int(match[2], 16) * (-1 if match[1] == "sub" else 1)
        elif match := re.fullmatch(r"lea rsp, qword ptr ss:\[rsp([+-]\d+)\]", line):
            delta += int(match[1])
        if line.startswith("call "):
            target = line.removeprefix("call ")
            assert (entry_alignment + delta) % 16 == 0, f"unaligned call {line}: {delta}"
            if target in original_calls:
                assert delta == 0, "original call stack moved"
            else:
                assert delta <= -32, "missing callback shadow space"
            calls.add((target, delta))
        elif line == ".DB 255, 144, 232, 0, 0, 0":
            assert delta == 0 and entry_alignment == 0, "indirect AddEffect stack moved"
            copied_call.add(i)
        elif line.startswith(".DB "):
            assert delta == 0, "restored original instructions at wrong stack"
        branch = re.fullmatch(r"(jmp|jz|jnz) (\S+)", line)
        if branch:
            target = branch[2]
            if target in labels:
                todo.append((labels[target], delta))
            else:
                assert target.isdecimal(), f"unresolved target: {target}"
                assert delta == 0, f"unbalanced native return: {delta}"
                exits.add(int(target))
            if branch[1] == "jmp":
                continue
        todo.append((i + 1, delta))
    return exits, calls, copied_call


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR for real EEex preprocessing")
class PotionTransportPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = read_image()

    def test_validate_reads_all_pinned_signatures_without_preparing_or_writing_code(self):
        h = TransportHarness(self.image)
        validated = h.validate()
        self.assertEqual(BASE + 0x20FE5E, validated.sites.messageRun)
        self.assertEqual([], h.assemblies)
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)

    def test_every_site_and_context_mismatch_fails_before_first_write(self):
        for rva in GUARDS:
            with self.subTest(rva=hex(rva)):
                h = TransportHarness(self.image)
                h.image[rva] ^= 1
                with self.assertRaisesRegex(Exception, "unsupported/previously patched site"):
                    h.install()
                self.assertEqual([], h.assemblies)
                self.assertEqual([], h.patches)
                self.assertEqual([], h.protection)

    def test_watchdog_or_missing_callback_fails_before_first_write(self):
        h = TransportHarness(self.image)
        h.lua.globals().EEex_HookIntegrityWatchdog_Load = True
        with self.assertRaisesRegex(Exception, "preservation helper required"):
            h.hook.install(h.lua.globals(), h.config)
        h.lua.globals().EEex_HookIntegrityWatchdog_Load = False
        h.config.callbacks.messageEnter = "absent"
        with self.assertRaisesRegex(Exception, "callback must exist"):
            h.install()
        self.assertEqual([], h.patches)

    def test_real_generator_expands_all_callbacks_and_original_calls_with_balanced_paths(self):
        h = TransportHarness(self.image)
        h.install()
        self.assertEqual(13, len(h.assemblies))
        self.assertEqual([BASE + rva for rva in SITES], [p[0] for p in h.patches])
        self.assertEqual(["disable", "enable"], h.protection)
        self.assertEqual([], h.warnings)
        continuations = (8, 5, 5, 5, 5, 5, 6, 5, 5, 5, 5, 7, 6)
        for index, (text, state) in enumerate(h.assemblies):
            with self.subTest(site=hex(SITES[index])):
                self.assertNotIn("#", text)
                for key in ("curStackTop", "shadowSpaceStackTop", "alignModStackTop", "prologStackTop"):
                    self.assertEqual(8 if index in (7,8,9,10) and key == "curStackTop" else 0, state[key], key)
                exits, calls, indirect = inspect_paths(text, 8 if index in (7,8,9,10) else 0,
                                                       {str(BASE + 0x204EC0)})
                self.assertEqual({BASE + SITES[index] + continuations[index]}, exits)
                self.assertEqual(1 if index == 6 else 0, len(indirect))
                expected_pairs = 2 if index == 6 else 1
                for register in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
                    self.assertEqual(expected_pairs, instructions(text).count(f"push {register}"))
                    self.assertEqual(expected_pairs, instructions(text).count(f"pop {register}"))
                self.assertEqual(expected_pairs, instructions(text).count("pushfq"))
                self.assertEqual(expected_pairs, instructions(text).count("popfq"))
                for i in range(6):
                    offset = f"{i * 16:02x}h"
                    self.assertEqual(expected_pairs, text.count(f"movdqu xmmword ptr ss:[rsp+{offset}], xmm{i}"))
                    self.assertEqual(expected_pairs, text.count(f"movdqu xmm{i}, xmmword ptr ss:[rsp+{offset}]"))
                callback_deltas = {delta for target, delta in calls if target != str(BASE + 0x204EC0)}
                expected_deltas = ({-232} if index in (7, 8, 9, 10) else {-256, -240} if index == 6
                                   else {-256} if index in (1, 4, 11, 12) else {-240})
                self.assertEqual(expected_deltas, callback_deltas)

    def test_argument_capture_and_original_indirect_call_order(self):
        h = TransportHarness(self.image)
        h.install()
        code = [text for text, _ in h.assemblies]
        self.assertIn("movsx rax, word ptr ds:[rbx+4AF2h]", code[0])
        self.assertIn("mov qword ptr ss:[rsp+64], rbp", code[0])
        for index, offset in ((3, 240), (4, 256), (5, 240)):
            self.assertIn(f"lea rax, qword ptr ss:[rsp+{offset}]", code[index])
        self.assertIn("mov eax, esi", code[1])
        self.assertIn("mov qword ptr ss:[rsp+80], rdi", code[1])
        self.assertIn("mov eax, edi", code[4])
        self.assertIn("mov qword ptr ss:[rsp+80], rbx", code[4])
        self.assertIn("mov eax, r9d", code[6])
        self.assertIn("mov qword ptr ss:[rsp+72], rdx", code[6])
        lines = instructions(code[6])
        original = lines.index(".DB 255, 144, 232, 0, 0, 0")
        self.assertEqual("popfq", lines[original - 1])
        self.assertEqual("pushfq", lines[original + 1])
        self.assertNotIn("call short", code[6])
        self.assertEqual(2, code[6].count("mov qword ptr ss:[rsp+64], rbx"))
        self.assertIn("mov qword ptr ss:[rsp+64], rcx", code[7])
        self.assertIn(".DB 72, 137, 92, 36, 8", code[7])
        for index in (8, 9):
            self.assertIn("mov qword ptr ss:[rsp+64], rcx", code[index])
            self.assertIn(".DB 72, 137, 92, 36, 8", code[index])
        self.assertIn(".DB 72, 139, 196, 85, 83", code[10])
        self.assertIn("mov qword ptr ss:[rsp+72], rdi", code[11])
        self.assertIn("mov qword ptr ss:[rsp+72], rbx", code[12])
        self.assertIn("lea rax, qword ptr ss:[rsp+256]", code[12])
        self.assertIn(".DB 72, 139, 139, 216, 74, 0, 0", code[11])
        self.assertIn(".DB 72, 139, 211, 73, 139, 206", code[12])
        self.assertEqual(0xE8, self.image[0x3BBBDA])
        self.assertEqual(0xE8, self.image[0x16A675])
        self.assertNotIn(BASE + 0x3BBBDA, [p[0] for p in h.patches])
        self.assertNotIn(BASE + 0x16A675, [p[0] for p in h.patches])
        self.assertEqual(0x3BBB87, struct.unpack_from("<I", self.image, 0x3BBFD8 + 4)[0])
        self.assertEqual(0x16A62D, struct.unpack_from("<I", self.image, 0x16A87C + 4)[0])

    def test_supported_effect_destructor_vtables_and_existing_eeex_hook_are_separate(self):
        # Opcode dispatch table1E2770 -> constructor calls -> constructor vtable
        # stores -> vtable[0]. This is evidence from the pinned executable, not
        # a general promise that all effect classes share one destructor.
        evidence = {
            18: (0x1DE791, 0x1DE7B8, 0x19FFF0, 0x591E48, 0x1A45A0),
            19: (0x1DE7C2, 0x1DE7E9, 0x1A0100, 0x591EA0, 0x14C8E0),
            54: (0x1DEED7, 0x1DEEFE, 0x1A2F00, 0x592A50, 0x14C8E0),
            90: (0x1DF6B0, 0x1DF6D7, 0x1A2940, 0x593810, 0x14C8E0),
            92: (0x1DF712, 0x1DF739, 0x1A2980, 0x5938C0, 0x14C8E0),
        }
        for opcode, (case, call, constructor, vtable, destructor) in evidence.items():
            with self.subTest(opcode=opcode):
                self.assertEqual(case, struct.unpack_from("<I", self.image, 0x1E2770 + 4 * opcode)[0])
                self.assertEqual(0xE8, self.image[call])
                self.assertEqual(constructor, call + 5 + struct.unpack_from("<i", self.image, call + 1)[0])
                self.assertEqual(BASE + destructor, struct.unpack_from("<Q", self.image, vtable)[0])
                body = self.image[constructor:constructor + 80]
                lea = body.find(bytes.fromhex("488D05"))
                self.assertGreaterEqual(lea, 0)
                self.assertEqual(vtable, constructor + lea + 7 + struct.unpack_from("<i", body, lea + 3)[0])
        self.assertEqual(bytes.fromhex("E83B0E2C00"), self.image[0x14C900:0x14C905])
        self.assertLess(0x14C8E0 + 5, 0x14C900)

    def test_partial_native_patch_failure_is_not_claimed_rolled_back_or_retried(self):
        h = TransportHarness(self.image)
        capture = h.capture_at
        def fail_third(address, assembly):
            if len(h.patches) == 2:
                raise RuntimeError("injected native patch failure")
            capture(address, assembly)
        h.lua.globals().EEex_JITAt = fail_third
        with self.assertRaisesRegex(Exception, "injected native patch failure"):
            h.install()
        self.assertTrue(h.hook.failed)
        self.assertFalse(h.hook.installed)
        self.assertEqual(2, len(h.patches))
        self.assertEqual(["disable", "enable"], h.protection)
        with self.assertRaisesRegex(Exception, "already attempted; do not retry"):
            h.install()
        self.assertEqual(2, len(h.patches))

    def test_watchdog_enabled_checks_all_registers_at_aligned_native_stack_frames(self):
        h = TransportHarness(self.image, watchdog=True)
        h.install()
        self.assertEqual(15, len(h.assemblies))
        for index, (text, state) in enumerate(h.assemblies[2:]):
            with self.subTest(site=hex(SITES[index])):
                self.assertEqual(8 if index in (7,8,9,10) else 0, state.curStackTop)
                self.assertEqual(0, state.shadowSpaceStackTop)
                inspect_paths(text, 8 if index in (7,8,9,10) else 0, {str(BASE + 0x204EC0)})
        register_masks = [args[2] for args in h.watchdog_metadata if len(args) == 3]
        self.assertEqual(13, len(register_masks))
        self.assertEqual({0}, set(register_masks))
        self.assertTrue(h.lua.globals().EEex_HookIntegrityWatchdog_Load)


if __name__ == "__main__":
    unittest.main()
