"""Host tests of the shipped Time Stop and Haste correction (component 360), not game acceptance.

CBRTC.lua and its autoload M_CBRTC.lua run under LuaJIT (lupa) against a fake EEex over synthetic
memory: the start without a console, loads, every refusal and a gate's runtime error. The gates'
arithmetic, assembly and native worker behaviour are covered by research/timestop-lab/test_cor.py,
the game itself by the labs (research/timestop-lab/README.md).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "chriz-bg-rebalance/lua/CBRTC.lua"
AUTOLOAD = ROOT / "chriz-bg-rebalance/lua/M_CBRTC.lua"
PREFIX = "[CBR Time Stop/Haste] "
OFF = PREFIX + "off, the game stays native: "
BASE = 0x140000000
NT = 0x108

# The fake EEex. Memory holds one byte per address; reading or writing an address nothing mapped
# raises, as a bad pointer would fault in the game.
HARNESS = r"""
LOG, NOTICES, HOOKS, INITIALIZED, DESTROYED = {}, {}, {}, {}, {}
CALLS = {jit = 0, hooks = 0, protect = 0, unprotect = 0, malloc = 0}
FAKE = {}
function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
    LOG[#LOG + 1] = table.concat(parts, "\t")
end

MEM = {}
local function byte(a)
    local b = MEM[a]
    if b == nil then error(string.format("unmapped read at 0x%X", a), 0) end
    return b
end
function fill(a, n) for i = 0, n - 1 do MEM[a + i] = 0 end end
function wr(a, v, n)
    v = v % 2 ^ (8 * n)
    for i = 0, n - 1 do
        if MEM[a + i] == nil then error(string.format("unmapped write at 0x%X", a + i), 0) end
        MEM[a + i] = v % 256
        v = math.floor(v / 256)
    end
end
local function rd(a, n)
    local v = 0
    for i = 0, n - 1 do v = v + byte(a + i) * 256 ^ i end
    return v
end
local heap = 0x20000000
function alloc(n)
    local a = heap
    heap = heap + n + 0x100
    fill(a, n)
    return a
end

EEex_Active = true
EEex_LuaCallReturnType = {Number = 2}
function EEex_ReadU8(a) return byte(a) end
function EEex_Read16(a) local v = rd(a, 2); return v >= 32768 and v - 65536 or v end
function EEex_Read32(a) local v = rd(a, 4); return v >= 2147483648 and v - 4294967296 or v end
function EEex_ReadU32(a) return rd(a, 4) end
function EEex_ReadPtr(a) return rd(a, 8) end
function EEex_Write32(a, v) wr(a, v, 4) end
function EEex_WriteU32(a, v) wr(a, v, 4) end
function EEex_WriteU16(a, v) wr(a, v, 2) end
function EEex_Malloc(n)
    CALLS.malloc = CALLS.malloc + 1
    if FAKE.malloc_zero then return 0 end
    return alloc(n)
end
function EEex_Label(name)
    if name ~= "Data-CGameEffect::vftable" then error("unknown label "..name) end
    return FAKE.label or EFFECT_VTABLE
end
function EEex_GetImageBase() return FAKE.image_base or IMAGE_BASE end
OFFSETS = {["CGameSprite.m_timedEffectList"] = 0x4A00, ["CGameSprite.m_equipedEffectList"] = 0x49B0,
    ["CPtrList.m_pNodeHead"] = 0x8, ["CPtrList::CNode.pNext"] = 0x0, ["CPtrList::CNode.data"] = 0x10}
function EEex_OffsetOf(name)
    local offset = OFFSETS[name]
    if offset == nil then error("EEex_OffsetOf: unknown field "..name) end
    return offset
end
function EEex_FlattenTable(t)
    local out = {}
    local function flatten(x)
        if type(x) == "table" then for _, v in ipairs(x) do flatten(v) end else out[#out + 1] = x end
    end
    flatten(t)
    return out
end
function EEex_GenLuaCall(fn, opts) return {"; call "..fn.." #ENDL"} end
function EEex_JITNear(t)
    CALLS.jit = CALLS.jit + 1
    if FAKE.jit_error == CALLS.jit then error("assembler: invalid operand", 0) end
    return alloc(16)
end
function EEex_DisableCodeProtection() CALLS.unprotect = CALLS.unprotect + 1 end
function EEex_EnableCodeProtection() CALLS.protect = CALLS.protect + 1 end
local function hook(kind)
    return function(address, delay, size, back, labels, body)
        CALLS.hooks = CALLS.hooks + 1
        if FAKE.hook_error == CALLS.hooks then error("hook rejected", 0) end
        HOOKS[#HOOKS + 1] = {kind = kind, address = address, delay = delay, size = size, back = back,
            body = table.concat(body, "\n")}
    end
end
EEex_HookAfterRestoreWithLabels = hook("after")
EEex_HookBeforeRestoreWithLabels = hook("before")
function EEex_GameState_AddInitializedListener(f) INITIALIZED[#INITIALIZED + 1] = f end
function EEex_GameState_AddDestroyedListener(f) DESTROYED[#DESTROYED + 1] = f end
function initialize() for _, f in ipairs(INITIALIZED) do f() end end
function destroy() for _, f in ipairs(DESTROYED) do f() end end

-- What a refusal or a failure must never use: anything shown in the game.
for _, name in ipairs({"Infinity_DisplayString", "Infinity_PushMenu", "Infinity_SetFeedback",
        "EEex_GameObject_ApplyEffect", "EEex_Action_QueueResponseStringOnAIBase"}) do
    _G[name] = function() NOTICES[#NOTICES + 1] = name end
end

FILES = {}
function Infinity_DoFile(name)
    local chunk = assert(loadfile(FILES[name] or ("missing/"..name..".lua")))
    return chunk()
end
"""


def _core_tables() -> dict:
    """The pinned build as the core states it, read from the core itself."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(CORE.read_text(encoding="ascii"))
    core = lua.globals().CBRTC
    build = core.build
    return {
        "build": {key: int(build[key]) for key in ("timestamp", "effectVtable", "chitin",
                                                   "timedList", "equippedList")},
        "families": [(f.name, int(f.vtable), int(f.update)) for f in core.families.values()],
        "sites": [(s.name, int(s.rva), bytes.fromhex(s.bytes), s.kind) for s in core.sites.values()],
        "required": list(core.requiredFunctions.values()),
        "layout": [(entry[1], int(entry[2])) for entry in core.layout.values()],
    }


TABLES = _core_tables()
BUILD = TABLES["build"]


class Game:
    """One process: the fake EEex, the pinned executable's image and, on request, a world."""

    def __init__(self, *, timestamp: int = BUILD["timestamp"], machine: int = 0x8664,
                 eeex_active: bool = True, core_file: bool = True) -> None:
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        lua = self.lua
        lua.execute(HARNESS)
        g = lua.globals()
        g.IMAGE_BASE = BASE
        g.EFFECT_VTABLE = BASE + BUILD["effectVtable"]
        g.EEex_Active = eeex_active
        if core_file:
            g.FILES["CBRTC"] = CORE.as_posix()
        self.g = g
        self.write(BASE, b"MZ" + bytes(0x3A) + NT.to_bytes(4, "little"))
        self.write(BASE + NT, b"PE\0\0" + machine.to_bytes(2, "little") + bytes(2)
                   + timestamp.to_bytes(4, "little"))
        for _, vtable, update in TABLES["families"]:
            self.write(BASE + vtable + 8, (BASE + update).to_bytes(8, "little"))
        for _, rva, window, _ in TABLES["sites"]:
            self.write(BASE + rva, window)
        self.write(BASE + BUILD["chitin"], bytes(8))
        self.game = None

    def write(self, address: int, data: bytes) -> None:
        mem = self.g.MEM
        for i, b in enumerate(data):
            mem[address + i] = b

    def u32(self, address: int, value: int) -> None:
        self.g.wr(address, value, 4)

    def ptr(self, address: int, value: int) -> None:
        self.g.wr(address, value, 8)

    def read_u32(self, address: int) -> int:
        return int(self.g.EEex_ReadU32(address))

    def start(self) -> None:
        """The engine runs the autoload among the M_ files, then EEex reports the game state."""
        self.lua.execute(AUTOLOAD.read_text(encoding="ascii"))
        self.g.initialize()

    def log(self) -> list[str]:
        return list(self.g.LOG.values())

    def status(self):
        return self.g.CBRTC.Status()

    # A session: chitin -> game with world time, Time Stop state and caster.
    def session(self, world: int) -> None:
        chitin, game = self.g.alloc(0x1100), self.g.alloc(0x9700)
        self.ptr(BASE + BUILD["chitin"], chitin)
        self.ptr(chitin + 0x1090, game)
        self.game = game
        self.at(world)

    def at(self, world: int, *, stop: bool = False, caster: int = 99) -> None:
        self.u32(self.game + 0x3FA0, world)
        self.u32(self.game + 0x9690, 1 if stop else 0)
        self.u32(self.game + 0x9694, caster)

    def creature(self, object_id: int, effects: list[dict]) -> int:
        """A sprite whose timed list holds the given effects; its equipped list is empty."""
        sprite = self.g.alloc(0x5300)
        self.u32(sprite + 0x48, object_id)
        previous = 0
        for fields in reversed(effects):
            effect = self.g.alloc(0x100)
            self.u32(effect + 0x10, fields.get("opcode", 0))
            self.u32(effect + 0x24, fields.get("timing", 0))
            self.u32(effect + 0x28, fields.get("deadline", 0))
            self.u32(effect + 0x6C, fields.get("origin", 0))
            fields["address"] = effect
            node = self.g.alloc(0x18)
            self.ptr(node, previous)
            self.ptr(node + 0x10, effect)
            previous = node
        self.ptr(sprite + BUILD["timedList"] + 8, previous)
        return sprite


def _assert_no_notice(test: unittest.TestCase, game: Game) -> None:
    test.assertEqual(list(game.g.NOTICES.values()), [])


class StartTests(unittest.TestCase):
    def test_switches_on_at_game_start_without_a_console(self) -> None:
        game = Game()
        game.lua.execute(AUTOLOAD.read_text(encoding="ascii"))
        self.assertEqual(len(game.g.INITIALIZED), 1)
        self.assertEqual(len(game.g.HOOKS), 0, "nothing changes before EEex reports the game state")
        game.g.initialize()

        status = game.status()
        self.assertTrue(status.installed)
        self.assertTrue(status.enabled)
        self.assertEqual((status.errors, status.timed_offset, status.equipped_offset),
                         (0, BUILD["timedList"], BUILD["equippedList"]))
        hooks = sorted((int(h.address) - BASE, h.kind, h.size, h.back, h.delay)
                       for h in game.g.HOOKS.values())
        expected = sorted((rva, kind, len(window), len(window), 0) for _, rva, window, kind in TABLES["sites"])
        self.assertEqual(hooks, expected)
        self.assertEqual(len(hooks), 8)
        calls = game.g.CALLS
        self.assertEqual((calls.jit, calls.unprotect, calls.protect, calls.malloc), (8, 1, 1, 1))
        destroyed = list(game.g.DESTROYED.values())
        self.assertEqual(len(destroyed), 1)
        self.assertEqual(game.log(), [PREFIX + "on (BG2:EE/EET 2.7.3.0): effects of creatures frozen "
                                      "by Time Stop wait; Haste and Slow leave periodic effects at "
                                      "the normal rate"])
        _assert_no_notice(self, game)

    def test_each_gate_reads_the_enable_flag_and_calls_its_target(self) -> None:
        game = Game()
        game.start()
        block = int(game.g.CBRTC.block)
        for h in game.g.HOOKS.values():
            self.assertIn("mov rax, 0x%X" % block, h.body)
            self.assertIn("cmp dword ptr [rax], 1", h.body)
            self.assertRegex(h.body, r"; call CBRTC_(Frozen|Entry|Dispatch|Construct) ")

    def test_start_is_idempotent(self) -> None:
        game = Game()
        game.start()
        game.start()
        game.g.CBRTC.Start()
        self.assertEqual(len(game.g.INITIALIZED), 1)
        self.assertEqual(len(game.g.HOOKS), 8)
        self.assertEqual(len(game.g.DESTROYED), 1)
        self.assertEqual(len(game.log()), 1)

    def test_a_listener_error_stays_in_the_log(self) -> None:
        game = Game()
        game.lua.execute(AUTOLOAD.read_text(encoding="ascii"))
        game.lua.execute("CBRTC.Start = function() error('unforeseen', 0) end")
        game.g.initialize()
        self.assertEqual(game.log(), [OFF + "unforeseen"])
        _assert_no_notice(self, game)

    def test_shipped_files_have_no_lab_or_in_game_output(self) -> None:
        game = Game()
        game.start()
        core = game.g.CBRTC
        for lab_only in ("Install", "Enable", "Observe", "Watch", "Record", "ExportRecord", "recorder"):
            self.assertIsNone(core[lab_only], lab_only)
        for path in (CORE, AUTOLOAD):
            source = path.read_text(encoding="ascii")
            code = re.sub(r"--[^\n]*", "", source)
            self.assertEqual(set(re.findall(r"\bInfinity_\w+", code)) - {"Infinity_DoFile"}, set(), path.name)
            for forbidden in ("DisplayString", "MessageBox", "PushMenu", "Feedback", "io.open",
                              "io.write", "os.execute", "EEex_Opcode", "ApplyEffect"):
                self.assertNotIn(forbidden, code, f"{path.name}: {forbidden}")


class LoadTests(unittest.TestCase):
    """EEex's destroyed-session listener runs on quit and before every load."""

    def test_loads_keep_the_gates_on_and_restart_each_clock(self) -> None:
        game = Game()
        game.start()
        game.session(100)
        timed = {"timing": 0x1000, "deadline": 200}
        poison = {"opcode": 25, "timing": 1, "origin": 50}
        sprite = game.creature(7, [timed, poison])

        game.at(100, stop=True)
        self.assertEqual(game.g.CBRTC_Frozen(sprite), 0)
        self.assertEqual(game.g.CBRTC_Entry(sprite, 1), 0)
        game.at(101, stop=True)
        game.g.CBRTC_Frozen(sprite)
        self.assertEqual(game.read_u32(timed["address"] + 0x28), 202)
        self.assertEqual(game.read_u32(poison["address"] + 0x6C), 52)
        before = game.status()
        self.assertEqual((before.actors, before.stats.frozen_ticks, before.sessions), (1, 2, 0))

        # A save keeps the moved deadline; loading it destroys the session first.
        game.g.destroy()
        after = game.status()
        self.assertTrue(after.enabled)
        self.assertEqual((after.actors, after.stats.frozen_ticks, after.sessions), (0, 0, 1))

        game.session(101)
        loaded = {"timing": 0x1000, "deadline": 202}
        sprite = game.creature(7, [loaded])
        game.g.CBRTC_Entry(sprite, 1)
        self.assertEqual(game.read_u32(loaded["address"] + 0x28), 202, "a load moves nothing")
        game.at(105, stop=True)
        game.g.CBRTC_Frozen(sprite)
        self.assertEqual(game.read_u32(loaded["address"] + 0x28), 203)
        self.assertEqual(game.status().stats.actors_created, 1)

        game.g.destroy()
        self.assertEqual(game.status().sessions, 2)
        calls = game.g.CALLS
        self.assertEqual((len(game.g.HOOKS), calls.jit, calls.malloc, calls.unprotect), (8, 8, 1, 1),
                         "loads never patch again")
        self.assertEqual(len(game.log()), 1)
        _assert_no_notice(self, game)

    def test_main_menu_without_a_session_changes_nothing(self) -> None:
        game = Game()
        game.start()
        self.assertEqual(game.g.CBRTC_Entry(0x30000000, 1), 0)
        self.assertEqual(game.g.CBRTC_Frozen(0x30000000), 0)
        self.assertEqual(game.status().errors, 0)


class RefusalTests(unittest.TestCase):
    """Anything unexpected leaves the game native, says why once in the log and nowhere else."""

    def refused(self, reason: str, game: Game, *, queued: bool = True) -> Game:
        game.start()
        self.assertEqual(len(game.g.HOOKS), 0)
        log = game.log()
        self.assertEqual(len(log), 1, log)
        self.assertTrue(log[0].startswith(OFF), log)
        self.assertIn(reason, log[0])
        self.assertEqual(len(game.g.INITIALIZED), 1 if queued else 0)
        self.assertEqual(len(game.g.DESTROYED), 0)
        if game.g.CBRTC is not None:
            status = game.status()
            self.assertFalse(status.enabled)
            self.assertFalse(status.installed)
        _assert_no_notice(self, game)
        return game

    def test_without_eeex(self) -> None:
        game = self.refused("EEex is not active; start the game through InfinityLoader",
                            Game(eeex_active=False), queued=False)
        self.assertIsNone(game.g.CBRTC)

    def test_eeex_without_the_game_state_listener(self) -> None:
        game = Game()
        game.g.EEex_GameState_AddInitializedListener = None
        self.refused("this EEex lacks EEex_GameState_AddInitializedListener", game, queued=False)

    def test_core_file_missing(self) -> None:
        game = self.refused("CBRTC.lua did not load", Game(core_file=False), queued=False)
        self.assertIsNone(game.g.CBRTC)

    def test_each_required_eeex_function(self) -> None:
        self.assertEqual(len(TABLES["required"]), 20)
        for name in TABLES["required"]:
            with self.subTest(name=name):
                game = Game()
                game.g[name] = None
                self.refused("this EEex lacks " + name, game)
                self.assertEqual(game.g.CALLS.malloc, 0)

    def test_eeex_without_number_returns(self) -> None:
        game = Game()
        game.g.EEex_LuaCallReturnType = None
        self.refused("this EEex lacks EEex_LuaCallReturnType.Number", game)

    def test_image_base(self) -> None:
        game = Game()
        game.g.FAKE.image_base = BASE + 0x10000
        self.refused("image base disagrees with EEex", game)
        game = Game()
        game.g.FAKE.label = BASE + BUILD["effectVtable"] + 8
        self.refused("unexpected image base", game)

    def test_another_build(self) -> None:
        # BG2:EE 2.6.6.0 x64 and a 32-bit image.
        self.refused("not BG2:EE/EET 2.7.3.0 (PE timestamp 0x609437B3); only that executable is "
                     "supported", Game(timestamp=0x609437B3))
        self.refused("unexpected code at 0x%X (PE header)" % (BASE + NT + 4), Game(machine=0x14C))

    def test_each_worker_vtable(self) -> None:
        for name, vtable, update in TABLES["families"]:
            with self.subTest(family=name):
                game = Game()
                game.ptr(BASE + vtable + 8, BASE + update + 0x10)
                self.refused(f"unexpected {name} vtable", game)

    def test_each_patch_window(self) -> None:
        # Another mod's hook leaves a jump at the start of a window; one changed byte anywhere refuses.
        for name, rva, window, _ in TABLES["sites"]:
            for index, value in ((0, 0xE9), (len(window) - 1, window[-1] ^ 0xFF)):
                with self.subTest(site=name, index=index):
                    game = Game()
                    game.write(BASE + rva + index, bytes([value]))
                    self.refused("unexpected code at 0x%X (%s): another mod may have patched it, or "
                                 "this is not BG2:EE/EET 2.7.3.0" % (BASE + rva + index, name), game)
                    self.assertEqual(game.g.CALLS.unprotect, 0)

    def test_each_list_field(self) -> None:
        for field, offset in TABLES["layout"]:
            with self.subTest(field=field):
                game = Game()
                game.g.OFFSETS[field] = offset + 8
                self.refused("EEex places %s at 0x%X instead of 0x%X" % (field, offset + 8, offset), game)
                game = Game()
                game.g.OFFSETS[field] = None
                self.refused("EEex places %s at no known offset instead of 0x%X" % (field, offset), game)

    def test_no_memory_for_the_enable_flag(self) -> None:
        game = Game()
        game.g.FAKE.malloc_zero = True
        self.refused("Cannot allocate correction block", game)
        self.assertIsNone(game.g.CBRTC.block)

    def test_an_assembly_error_stops_before_the_first_change(self) -> None:
        game = Game()
        game.g.FAKE.jit_error = 3
        self.refused("assembler: invalid operand", game)
        calls = game.g.CALLS
        self.assertEqual((calls.unprotect, calls.protect), (0, 0))
        self.assertFalse(game.g.CBRTC.failed)

    def test_a_failed_hook_leaves_every_gate_off(self) -> None:
        game = Game()
        game.g.FAKE.hook_error = 5
        game.start()
        log = game.log()
        self.assertEqual(log, [OFF + "Correction install incomplete; restart the game: hook rejected"])
        status = game.status()
        self.assertTrue(status.failed)
        self.assertFalse(status.enabled)
        self.assertEqual(len(game.g.HOOKS), 4)
        calls = game.g.CALLS
        self.assertEqual((calls.unprotect, calls.protect), (1, 1), "code protection comes back")
        self.assertEqual(len(game.g.DESTROYED), 0)
        _assert_no_notice(self, game)


class RuntimeErrorTests(unittest.TestCase):
    def test_an_error_in_a_gate_turns_every_gate_off_until_restart(self) -> None:
        game = Game()
        game.start()
        game.session(100)
        sprite = game.creature(7, [])
        game.g.CBRTC_Entry(sprite, 1)

        self.assertEqual(game.g.CBRTC_Dispatch(sprite, 0x30000000, 1), -1, "native elapsed")
        status = game.status()
        self.assertFalse(status.enabled)
        self.assertEqual(status.errors, 1)
        self.assertEqual(game.g.CBRTC_Entry(0x30000000, 1), 0)
        self.assertEqual(game.g.CBRTC_Construct(sprite, 0, 0x30000000, 1), 0)
        self.assertEqual(game.status().errors, 3)
        log = game.log()
        self.assertEqual(len(log), 2, log)
        self.assertEqual(log[1], PREFIX + "off until the game restarts; the game continues natively. "
                                  "unmapped read at 0x30000000")

        game.g.destroy()
        self.assertFalse(game.status().enabled, "a load does not switch it back on")
        _assert_no_notice(self, game)


if __name__ == "__main__":
    unittest.main()
