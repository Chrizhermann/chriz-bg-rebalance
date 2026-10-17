"""Optional offline check using the real local EEex 1.3 Lua preprocessor.

Set EEEX_LUA_DIR to the EEex_scripts directory to run. No engine/DLL code,
assembler, executable-memory allocation or installation is performed. The
generator, macro expansion, branch wrapper and (when enabled) watchdog Lua
templates are real; regex/native memory/JIT services are explicit test doubles.
The resulting assembly is inspected, not assembled or executed.
"""
from pathlib import Path
import os
import re
import struct
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "research/prototypes/potion-admission/CBRPQHook.lua"
EEEX = os.environ.get("EEEX_LUA_DIR")
BASE = 0x1401CC6C0
SITE = BASE + 0xAE9
REJECT = 0x1401CC9A5
ALLOW = SITE + 6
SIGNATURE = bytes.fromhex("0f84f6f7ffff8b47243d00100000740d83f802")


class PreprocessorHarness:
    def __init__(self, watchdog=False, hook_source=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.assemblies = []
        self.patches = []
        self.protection = []
        self.warnings = []
        self.watchdog_metadata = []
        g = self.lua.globals()
        labels = self.lua.table_from({"CGameEffect::CheckAdd": BASE})
        names = (
            "Hardcoded_lua_getglobal", "Hardcoded_lua_getfield",
            "Hardcoded_tolua_pushusertype", "Hardcoded_lua_pcallk",
            "EEex_CheckCallError", "Hardcoded_lua_settop",
            "Hardcoded_lua_toboolean", "Hardcoded_InternalLuaState",
            "EEex::HookIntegrityWatchdogEnter", "EEex::HookIntegrityWatchdogExit",
        )
        self.addresses = {name: 0x180001000 + i * 0x100 for i, name in enumerate(names)}
        for name, address in self.addresses.items():
            labels[name] = address
        g.EEex_Architecture = "x86-64"
        g.EEex_GetPatternMap = lambda: labels
        g.EEex_ToDecStr = lambda n: str(int(n))
        g.EEex_DoFile = lambda name: self.lua.execute(
            (Path(EEEX) / (name + ".lua")).read_text(encoding="utf-8-sig"))
        g.EEex_ReplaceRegex = self.replace_regex
        g.EEex_IterateRegex = self.iterate_regex
        g.print = lambda value: self.warnings.append(str(value))
        self.lua.execute((Path(EEEX) / "EEex_Assembly.lua").read_text(encoding="utf-8-sig"))

        # These replace native services only, after the real Lua files load.
        cache = {}
        def cache_string(text):
            if text not in cache:
                cache[text] = 0x190000000 + len(cache) * 0x100
            return cache[text]
        g.EEex_WriteStringCache = cache_string
        g.EEex_JITNear = self.capture_near
        g.EEex_JITAt = self.capture_at
        g.EEex_ReadU8 = lambda address: SIGNATURE[int(address) - SITE]
        g.EEex_Read32 = lambda address: struct.unpack_from("<i", SIGNATURE, int(address) - SITE)[0]
        g.EEex_DisableCodeProtection = lambda: self.protection.append("disable")
        g.EEex_EnableCodeProtection = lambda: self.protection.append("enable")
        self.lua.execute("function CBRPQTestCallback(effect, sprite) return false end")

        if watchdog:
            # Enable the genuine optional templates in memory only. Their native
            # DLL operations and code allocation remain capture-only services.
            self.lua.execute("EEex = {}; EEex_BOr = bit.bor")
            g.EEex.HookIntegrityWatchdogIgnoreRegisters = lambda *args: self.watchdog_metadata.append(args)
            g.EEex.HookIntegrityWatchdogIgnoreStackRange = lambda *args: self.watchdog_metadata.append(args)
            source = (Path(EEEX) / "EEex_HookIntegrityWatchdog.lua").read_text(encoding="utf-8-sig")
            assert source.count("EEex_HookIntegrityWatchdog_Load = false") == 1
            self.lua.execute(source.replace("EEex_HookIntegrityWatchdog_Load = false",
                                           "EEex_HookIntegrityWatchdog_Load = true", 1))
        else:
            g.EEex_HookIntegrityWatchdog_Load = False
        self.hook = self.lua.execute(hook_source or HOOK.read_text(encoding="utf-8"))
        self.watchdog = self.lua.execute((HOOK.parent / "CBRPQWatchdog.lua").read_text(encoding="utf-8"))

    def groups(self, match):
        result = self.lua.table()
        for i, value in enumerate(match.groups(), 1):
            result[i] = value
        return result

    def replace_regex(self, text, pattern, callback):
        def replace(match):
            value = callback(match.start(), match.end(), match.group(), self.groups(match))
            return "" if value is None else str(value)
        return re.sub(pattern, replace, text, flags=re.MULTILINE)

    def iterate_regex(self, text, pattern, callback):
        for match in re.finditer(pattern, text, flags=re.MULTILINE):
            # Native EEex string positions are one-based and end-inclusive.
            callback(match.start() + 1, match.end(), match.group(), self.groups(match))

    def capture_near(self, assembly):
        # Mirror real JITNear's stack_mod preprocessing, including function-entry
        # misalignment outside the callback (watchdog templates run there too).
        stack_mod = self.lua.globals().EEex_TryLabel("stack_mod")
        if stack_mod is not None:
            assembly = self.lua.globals().EEex_FlattenTable(self.lua.table_from([
                self.lua.table_from([f"#STACK_MOD({int(stack_mod)}) #ENDL"]), assembly]))
        text, state = self.lua.globals().EEex_PreprocessAssembly(assembly)
        self.assemblies.append((text, state))
        return 0x140800000 + len(self.assemblies) * 0x10000

    def capture_at(self, address, assembly):
        text, state = self.lua.globals().EEex_PreprocessAssembly(assembly)
        self.patches.append((address, text, state))

    def install(self):
        return self.hook.install(self.lua.globals(), "CBRPQTestCallback", self.watchdog)


def instructions(text):
    return [line.split(";", 1)[0].strip() for line in text.splitlines()
            if line.split(";", 1)[0].strip()]


def stack_paths(text):
    """Bounded control-flow inspection; all external calls assumed ABI-compliant.

    Check stack deltas and call alignment, following both sides of every local
    conditional branch. This is not a machine-code or register-state emulator.
    """
    code = instructions(text)
    labels = {line[:-1]: i for i, line in enumerate(code) if line.endswith(":")}
    todo = [(0, 0)]
    seen, exits, calls = set(), set(), set()
    while todo:
        i, delta = todo.pop()
        if (i, delta) in seen:
            continue
        seen.add((i, delta))
        assert len(seen) < 1000, "unexpected unbounded branch/stack loop"
        assert i < len(code), "assembly fell through without a destination"
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
            assert delta % 16 == 0, f"unaligned call at delta {delta}: {line}"
            assert delta <= -32, f"missing caller shadow space: {line}"
            calls.add((line, delta))
        branch = re.fullmatch(r"(jmp|jz|jnz) (\S+)", line)
        if branch:
            target = branch[2]
            if target in labels:
                todo.append((labels[target], delta))
            else:
                assert target.isdecimal(), f"unresolved external label {target}"
                assert delta == 0, f"unbalanced external exit {target}: {delta}"
                exits.add(int(target))
            if branch[1] == "jmp":
                continue
        todo.append((i + 1, delta))
    return exits, calls


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR to local EEex 1.3 EEex_scripts")
class PotionHookPreprocessorTests(unittest.TestCase):
    def test_real_generation_expands_and_balances_all_normal_and_error_exits(self):
        h = PreprocessorHarness()
        self.assertEqual(SITE, h.install())
        self.assertEqual(["disable", "enable"], h.protection)
        self.assertEqual([], h.warnings)
        text, state = h.assemblies[-1]
        self.assertNotIn("#", text)
        for key in ("curStackTop", "shadowSpaceStackTop", "alignModStackTop", "prologStackTop"):
            self.assertEqual(0, state[key], key)
        exits, calls = stack_paths(text)
        self.assertEqual({ALLOW, REJECT}, exits)
        self.assertEqual({-240}, {delta for _, delta in calls})
        self.assertTrue(text.startswith(f"jz {REJECT}\n"))
        self.assertIn("mov qword ptr ss:[rsp+64], rdi", text)
        self.assertIn("mov qword ptr ss:[rsp+72], r14", text)
        self.assertIn("lea rsp, qword ptr ss:[rsp-80]", text)
        self.assertEqual(2, text.count("lea rsp, qword ptr ss:[rsp+80]"))
        self.assertIn("jmp call_error", text)
        for register in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
            self.assertEqual(1, instructions(text).count(f"push {register}"))
            self.assertEqual(2, instructions(text).count(f"pop {register}"))
        self.assertEqual(1, instructions(text).count("pushfq"))
        self.assertEqual(2, instructions(text).count("popfq"))
        for i in range(6):
            offset = f"{i * 16:02x}h"
            self.assertEqual(1, text.count(f"movdqu xmmword ptr ss:[rsp+{offset}], xmm{i}"))
            self.assertEqual(2, text.count(f"movdqu xmm{i}, xmmword ptr ss:[rsp+{offset}]"))
        self.assertEqual(SITE, h.patches[0][0])
        self.assertRegex(h.patches[0][1], r"^jmp short \d+\nnop\n$")

    def test_missing_alternate_stack_reset_is_rejected_by_real_macro_engine(self):
        source = HOOK.read_text(encoding="utf-8")
        broken = source.replace("cbrpq_allow:\n        #STACK_MOD(160)", "cbrpq_allow:")
        self.assertNotEqual(source, broken)
        h = PreprocessorHarness(hook_source=broken)
        with self.assertRaisesRegex(Exception, "stack top not where it should be"):
            h.install()
        self.assertEqual([], h.patches)
        self.assertEqual(["disable", "enable"], h.protection)

    def test_watchdog_requires_helper_and_retains_original_checks(self):
        h = PreprocessorHarness(watchdog=True)
        before = len(h.assemblies)
        with self.assertRaisesRegex(Exception, "preservation helper required"):
            h.hook.install(h.lua.globals(), "CBRPQTestCallback")
        self.assertEqual([], h.warnings)
        self.assertEqual(before, len(h.assemblies))
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)
        # Prior expansion found balanced watchdog frames, but its native helper
        # calls occur outside the custom save area and do not save XMM state.
        for helper, _ in h.assemblies[:2]:
            self.assertNotIn("xmm", helper.lower())
        original_enter = h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter
        original_exit = h.lua.globals().EEex_HookIntegrityWatchdog_HookExit
        h.install()
        same = h.lua.eval("function(a,b) return rawequal(a,b) end")
        self.assertTrue(same(original_enter, h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter))
        self.assertTrue(same(original_exit, h.lua.globals().EEex_HookIntegrityWatchdog_HookExit))
        text, state = h.assemblies[-1]
        self.assertEqual(0, state.curStackTop)
        self.assertEqual(0, state.shadowSpaceStackTop)
        self.assertIn("lea rsp, qword ptr ss:[rsp-112]", text)
        self.assertIn("lea rax, qword ptr ss:[rsp+176]", text)
        self.assertEqual({ALLOW, REJECT}, stack_paths(text)[0])
        self.assertTrue(h.lua.globals().EEex_HookIntegrityWatchdog_Load)
        self.assertTrue(h.watchdog_metadata)

    def test_watchdog_scope_restores_templates_after_generation_error(self):
        h = PreprocessorHarness(watchdog=True)
        h.lua.globals().tested_watchdog = h.watchdog
        h.lua.execute('''
            local enter, exit = EEex_HookIntegrityWatchdog_HookEnter, EEex_HookIntegrityWatchdog_HookExit
            local ok = pcall(function() tested_watchdog.withPreservation(_G, function()
                assert(EEex_HookIntegrityWatchdog_HookEnter ~= enter)
                error('injected generator failure')
            end) end)
            assert(not ok and EEex_HookIntegrityWatchdog_HookEnter == enter)
            assert(EEex_HookIntegrityWatchdog_HookExit == exit and EEex_HookIntegrityWatchdog_Load)
        ''')


if __name__ == "__main__":
    unittest.main()
