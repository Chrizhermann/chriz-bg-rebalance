"""Offline check of M_CBRKP.lua's hook preparation (411) against a fake EEex, not game acceptance.

The generated block is also run through a small interpreter: it may only compare
and branch, a registered class/kit pair must reach the native kit-column path
(jmp_fail) and every other pair must fall through to the native class-column jump.
"""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "chriz-bg-rebalance/lua/M_CBRKP.lua"
DB = ROOT / "chriz-bg-rebalance/kitprof/CBRKP.db"
START = 0x140245000


def pattern():
    fields = dict(line.split("=", 1) for line in DB.read_text().splitlines()
                  if "=" in line and not line.startswith(";"))
    text = fields["Pattern"].strip()
    operation, offset = fields["Operations"].split()
    assert operation == "ADD"
    return [None if text[i:i + 2] == "??" else int(text[i:i + 2], 16) for i in range(0, len(text), 2)], int(offset)


def takes_kit_column(assembly, kit_index, klass):
    """True when the block, entered with EBX = kit index and EBP = class, jumps to
    jmp_fail; False when it falls through to the native class-column jump."""
    lines = [part.strip() for part in assembly.split("#ENDL") if part.strip()]
    labels = {line[:-1]: i for i, line in enumerate(lines) if line.endswith(":")}
    registers = {"ebx": kit_index, "ebp": klass}
    equal, pc = None, 0
    for _ in range(10000):
        if pc >= len(lines):
            return False
        op, _, args = lines[pc].partition(" ")
        if op == "cmp":
            register, value = (a.strip() for a in args.split(","))
            equal = registers[register] == int(value, 0)
        elif op in ("je", "jne"):
            assert equal is not None, "branch before a compare"
            if (op == "je") == equal:
                if args.strip() == "jmp_fail":
                    return True
                pc = labels[args.strip()]
                continue
        elif not op.endswith(":"):
            raise AssertionError(f"the hook may only compare and branch: {lines[pc]!r}")
        pc += 1
    raise AssertionError("the hook does not terminate")


class KitProficiencyRuntimeTests(unittest.TestCase):
    def runtime(self, rows=(("8", "16432"),), *, columns=("CLASS", "KIT"), eeex=True, label=True,
                patch=None, hook_error=None):
        lua = LuaRuntime()
        g = lua.globals()
        lua.execute(r'''
            hooks, disabled, enabled, listeners = 0, 0, 0, 0
            memory = {}
            function EEex_ReadU8(address) return memory[address] end
            function EEex_TryLabel(name)
                if name == "CBR-KitProficiencyColumn" then return label end
            end
            function EEex_DisableCodeProtection() disabled = disabled + 1 end
            function EEex_EnableCodeProtection() enabled = enabled + 1 end
            function EEex_HookConditionalJumpOnSuccess(address, restoreSize, assembly)
                if hook_error then error(hook_error) end
                hooks = hooks + 1
                hooked_at, restored = address, restoreSize
                generated = table.concat(assembly, " ")
            end
            function EEex_GameState_AddInitializedListener(f)
                listeners = listeners + 1
                listener = f
            end
            registry = {columns = {}, records = {}}
            function registry:findColumnLabel(name)
                for i, column in ipairs(self.columns) do if column == name then return i - 1 end end
                return -1
            end
            function EEex_Resource_Load2DA(name)
                assert(name == "CBRKPKIT")
                return registry
            end
            function EEex_Resource_Get2DARowTableIterator(r, includeLabel)
                assert(includeLabel == false)
                local i = 0
                return function() i = i + 1; return r.records[i] end
            end
        ''')
        g.EEex_Active = eeex or None
        g.hook_error = hook_error
        g.registry.columns = lua.table_from(columns)
        g.registry.records = lua.table_from([lua.table_from(row) for row in rows])
        bytes_, offset = pattern()
        for i, byte in enumerate(bytes_):
            g.memory[START + i] = 0x11 if byte is None else byte
        for i, byte in (patch or {}).items():
            g.memory[START + offset + i] = byte
        g.label = START + offset if label else None
        lua.execute(RUNTIME.read_text())
        if g.listener is not None:
            lua.execute("listener()")
        return lua

    def test_registered_pair_takes_the_kit_column_and_every_other_pair_keeps_the_class_column(self):
        lua = self.runtime()
        g = lua.globals()
        _, offset = pattern()
        self.assertEqual("active", g.CBRKitProficiency.Status)
        self.assertEqual((1, 1, 1), (g.hooks, g.disabled, g.enabled))
        self.assertEqual((START + offset, 7), (g.hooked_at, g.restored))
        self.assertTrue(takes_kit_column(g.generated, 0x30, 8))
        for kit_index, klass in ((0x30, 14), (0x30, 3), (0x31, 8), (0x2B, 8)):
            self.assertFalse(takes_kit_column(g.generated, kit_index, klass), (kit_index, klass))
        lua.execute(RUNTIME.read_text())  # a second load neither queues nor hooks again
        self.assertEqual((1, 1), (g.listeners, g.hooks))

    def test_several_pairs_and_duplicate_rows(self):
        g = self.runtime((("8", "16432"), ("14", "0x4074"), ("8", "16432"))).globals()
        self.assertEqual("active", g.CBRKitProficiency.Status)
        self.assertEqual(1, g.hooks)
        self.assertEqual(2, g.generated.count("je jmp_fail"))
        self.assertTrue(takes_kit_column(g.generated, 0x30, 8))
        self.assertTrue(takes_kit_column(g.generated, 0x74, 14))
        self.assertFalse(takes_kit_column(g.generated, 0x74, 8))
        self.assertFalse(takes_kit_column(g.generated, 0x30, 14))

    def test_changed_or_hooked_lookup_is_left_alone(self):
        for name, patch in (("jump replaced", {0: 0xE9}), ("compare changed", {-4: 0x38}),
                            ("restored instruction changed", {8: 0x90})):
            with self.subTest(name):
                g = self.runtime(patch=patch).globals()
                self.assertEqual((0, 0), (g.hooks, g.disabled))
                self.assertIn("kit lookup changed or another mod already hooked it", g.CBRKitProficiency.Status)

    def test_missing_label_is_reported(self):
        g = self.runtime(label=False).globals()
        self.assertEqual(0, g.hooks)
        self.assertIn("signature was not loaded", g.CBRKitProficiency.Status)

    def test_no_registrations_install_nothing(self):
        g = self.runtime(()).globals()
        self.assertEqual("no registered kits", g.CBRKitProficiency.Status)
        self.assertEqual((0, 0), (g.hooks, g.disabled))

    def test_invalid_registry_installs_nothing(self):
        for name, rows, columns, message in (
            ("columns", (("8", "16432"),), ("KIT", "CLASS"), "invalid CBRKPKIT registry"),
            ("class 0", (("0", "16432"),), ("CLASS", "KIT"), "invalid class identifier"),
            ("class text", (("FIGHTER", "16432"),), ("CLASS", "KIT"), "invalid class identifier"),
            ("true class", (("8", "16384"),), ("CLASS", "KIT"), "invalid kit identifier"),
            ("outside the kit range", (("8", "99999"),), ("CLASS", "KIT"), "invalid kit identifier"),
        ):
            with self.subTest(name):
                g = self.runtime(rows, columns=columns).globals()
                self.assertEqual((0, 0), (g.hooks, g.disabled))
                self.assertIn(message, g.CBRKitProficiency.Status)

    def test_hook_error_restores_code_protection(self):
        g = self.runtime(hook_error="jit failed").globals()
        self.assertEqual((0, 1, 1), (g.hooks, g.disabled, g.enabled))
        self.assertIn("jit failed", g.CBRKitProficiency.Status)
        self.assertIsNone(g.CBRKitProficiency.installed)

    def test_without_eeex_nothing_is_queued(self):
        g = self.runtime(eeex=False).globals()
        self.assertEqual("EEex is required", g.CBRKitProficiency.Status)
        self.assertEqual((0, 0), (g.listeners, g.hooks))


if __name__ == "__main__":
    unittest.main()
