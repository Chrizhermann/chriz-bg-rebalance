"""The Time Clocks lab's requests (rc/tc-*.lua, sampler, save and load) against stub bindings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
os.environ.setdefault("USERPROFILE", str(Path.home()))
import lab_rc

try:
    import lupa.luajit21 as lupa
except ImportError:  # pragma: no cover - the README lists lupa with LuaJIT 2.1
    lupa = None

REQUESTS = Path(__file__).resolve().parent / "rc"
BASE = 0x140000000
GAME = 0x7000000


def code(name: str, arguments: dict[str, str]) -> str:
    text = (REQUESTS / name).read_text(encoding="utf-8")
    return lab_rc.with_arguments(text, arguments) if arguments else text


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class TcQueueTests(unittest.TestCase):
    """tc-queue.lua: the response it queues on whom, the targets it binds, what it refuses."""

    def queue(self, arguments, paused=1, action=0, stop=0, actors=None):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, action, stop, game, objects)
            local queued, stored = {}, {}
            local byId = {}
            for id, name in pairs(objects) do
                byId[id] = {m_id = id, _name = name, m_objectType = 1, m_curAction = {m_actionID = action}}
            end
            CGameObjectType = {SPRITE = 1}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = game, m_worldTime = {m_gameTime = 1000}}}}
            EEex_Sprite_GetInPortrait = function(slot) return byId[({[0] = 10, [1] = 11})[slot]] end
            EEex_GameObject_Get = function(id) return byId[id] end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
            EEex_UDToPtr = function(value) return value._ptr end
            EEex_Read32 = function(address)
                assert(address == game + 0x9690, "unexpected read")
                return stop
            end
            EEex_AIBase_SetStoredScriptingTarget = function(actor, key, target)
                stored[#stored + 1] = actor._name .. ":" .. key .. "=" .. target.m_id
            end
            EEex_Action_QueueResponseStringOnAIBase = function(response, actor)
                queued[#queued + 1] = {response = response, actor = actor._name}
            end
            local ok, result = pcall(assert(loadstring(code, "@tc-queue.lua")))
            if not ok then return false, tostring(result), #queued, table.concat(stored, ";") end
            return true, result.queued, #queued, queued[1].actor .. "|" .. table.concat(stored, ";")
        end""")
        objects = actors if actors is not None else {10: "CBRTS Subject", 11: "Imoen", 4242: "Bounty Hunter"}
        return attempt(code("tc-queue.lua", arguments), paused, action, stop, GAME, runtime.table_from(objects))

    def test_steps_become_the_matching_actions(self):
        ok, response, count, who = self.queue({
            "actor": "p1", "name": "Imoen", "t1": "4242",
            "steps": "wait:40;apply:CBRTSTP:self;mark:stop_cast;cast:SPWI112:t1;castpoint:SPWI304:900:1200;"
                     "attack:t1;apply:CBRTBUF:p0;damage:5;spawn:BOUNHA02:950:1210;move:800:1100"})
        self.assertTrue(ok, response)
        self.assertEqual(count, 1)
        self.assertEqual(response.split("\n"), [
            "SmallWait(40)", 'ApplySpellRES("CBRTSTP",Myself)', "EEex_LuaAction(\"CBTCLab_Mark('stop_cast')\")",
            'ReallyForceSpellRES("SPWI112",EEex_Target("t1"))', 'ReallyForceSpellPointRES("SPWI304",[900.1200])',
            'AttackOneRound(EEex_Target("t1"))', 'ApplySpellRES("CBRTBUF",Player1)', "ApplyDamage(Myself,5,0)",
            'CreateCreature("BOUNHA02",[950.1210],0)', "MoveToPoint([800.1100])"])
        # The target is bound once, on the acting creature.
        self.assertEqual(who, "Imoen|Imoen:t1=4242")

    def test_an_object_id_names_the_actor(self):
        ok, response, _, who = self.queue({"actor": "4242", "name": "Bounty Hunter", "steps": "apply:CBRTCON:self"})
        self.assertEqual((ok, response, who), (True, 'ApplySpellRES("CBRTCON",Myself)', "Bounty Hunter|"))

    def test_refusals_queue_nothing(self):
        base = {"actor": "p1", "name": "Imoen", "steps": "wait:10"}
        cases = {
            "PAUSE_FIRST": ({}, {"paused": 0}),
            "NO_ACTOR": ({"actor": "p4"}, {}),
            "NOT_THE_ACTOR": ({"name": "Jaheira"}, {}),
            "ACTOR_BUSY": ({"idle": "1"}, {"action": 23}),
            "TIME_STOP_ACTIVE": ({"nostop": "1"}, {"stop": 90}),
            "INVALID_WAIT": ({"steps": "wait:0"}, {}),
            "UNKNOWN_STEP": ({"steps": "wait:10;"}, {}),
            "INVALID_RESREF": ({"steps": "apply:TOOLONGNAME:self"}, {}),
            "INVALID_TARGET": ({"steps": "cast:SPWI112:Player1"}, {}),
            "MISSING_T2": ({"steps": "cast:SPWI112:t2"}, {}),
            "NO_TARGET:t1": ({"steps": "cast:SPWI112:t1", "t1": "999"}, {}),
            "INVALID_LABEL": ({"steps": "mark:a')..os.exit()--"}, {}),
            "INVALID_AMOUNT": ({"steps": "damage:51"}, {}),
            "INVALID_POINT": ({"steps": "move:-5:10"}, {}),
        }
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count, _ = self.queue({**base, **arguments}, **state)
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
        with self.subTest(guard="INVALID_STEP_COUNT"):
            ok, error, count, _ = self.queue({**base, "steps": ";".join(["wait:1"] * 25)})
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("INVALID_STEP_COUNT", error)


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class SamplerTests(unittest.TestCase):
    """sampler.lua and sampler-export.lua against a stub engine: one record per change, projectiles
    found through the object array, marks, and an export that refuses an existing file."""

    def setUp(self):
        self.runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.directory = tempfile.TemporaryDirectory(prefix="cbr-sampler-test-")
        self.addCleanup(self.directory.cleanup)
        out = Path(self.directory.name) / "cbr-timestop-output"
        out.mkdir()
        (Path(self.directory.name) / "CBRTSLab.id").write_bytes(b"CBR TimeClocks Lab 2730\n")
        self.runtime.execute("""
            mem = {}
            local function u(address) return mem[address] or 0 end
            EEex_GetImageBase = function() return %d end
            EEex_Read32 = u
            EEex_ReadU16 = u
            EEex_ReadU8 = u
            EEex_ReadPtr = u
            EEex_BAnd = function(a, b) return bit.band(a, b) end
            EEex_UDToPtr = function(object) return object._ptr end
            frame = 100
            Infinity_GetFrameCounter = function() return frame end
            Infinity_GetClockTicks = function() return frame * 33 end
            CGameObjectType = {SPRITE = 1}
            EEex_Projectile_Type = {Unknown = 1, CProjectile = 2, CProjectileArea = 8, CProjectileBAM = 16}
            EEex_Projectile_Private_Inheritance = {[2] = 2, [8] = 8 + 16 + 2, [16] = 16 + 2}
            EEex_Projectile_GetType = function(projectile) return projectile._type end
            mutators = {}
            EEex_Projectile_RegisterGlobalMutator = function(name) mutators[#mutators + 1] = name end
            polls = 0
            EEexRemote = {Poll = function() polls = polls + 1 return "" end}
            world = {m_bPaused = 1, m_bHardPaused = 0}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = world, m_pObjectGame = {m_bGameLoaded = 1}}}
            sprites = {}
            objects = {}
            EEex_GameObject_Get = function(id) return objects[id] end
            EEex_Sprite_GetInPortrait = function(slot) return sprites[slot] end
            EEex_Utility_IterateCPtrList = function(list, f) for _, e in ipairs(list) do f(e) end end
            function effect(source, opcode, timing, duration)
                return {m_sourceRes = {get = function() return source end}, m_effectId = opcode,
                    m_durationType = timing, m_duration = duration}
            end
            function sprite(id, pointer, hp)
                local s = {m_id = id, _ptr = pointer, m_objectType = 1, m_baseStats = {m_hitPoints = hp},
                    m_curAction = {m_actionID = 0}, m_pos = {x = 10, y = 20}, m_timedEffectList = {}}
                objects[id] = s
                return s
            end
        """ % BASE)
        self.lua = self.runtime.globals()
        self.poke(BASE + 0x27671B, 0x3966)
        self.poke(BASE + 0x276735, 0x8D4C)
        self.poke(BASE + 0x27671E, 0x68F8F4 - 0x276722)
        self.poke(BASE + 0x276738, 0x68F910 - 0x27673C)
        chitin = 0x6000000
        self.poke(BASE + 0x667548, chitin)
        self.poke(chitin + 0x1090, GAME)
        self.poke(BASE + 0x667560, 0x6100000)
        self.poke(0x6100000 + 0xFA0, 4000)
        self.poke(GAME + 0x3FA0, 5000)
        self.poke(GAME + 0x9694, -1)
        self.poke(BASE + 0x68F8F4, 3)  # highest object index in use
        for index in range(4):
            self.poke(BASE + 0x68F910 + 16 * index, 0xFFFF)
        self.subject = self.runtime.eval("function() sprites[0] = sprite(10, 0x8000000, 80) return sprites[0] end")()
        self.runtime.eval("function() sprites[1] = sprite(11, 0x8100000, 40) end")()

    def poke(self, address, value):
        self.lua.mem[address] = value

    def run_request(self, name, arguments=None):
        previous = os.getcwd()
        os.chdir(self.directory.name)
        try:
            run = self.runtime.eval("function(code, name) return pcall(assert(loadstring(code, '@' .. name))) end")
            return run(code(name, arguments or {}), name)
        finally:
            os.chdir(previous)

    def frame(self, world=None, advance=1):
        if world is not None:
            self.poke(GAME + 0x3FA0, world)
        self.lua.frame = self.lua.frame + advance
        self.runtime.execute("EEexRemote.Poll(); EEexRemote.Poll()")  # two polling menus, one frame

    def export(self, name):
        ok, result = self.run_request("sampler-export.lua", {"name": name})
        self.assertTrue(ok, result)
        path = Path(self.directory.name) / result["path"]
        lines = path.read_text(encoding="utf-8").splitlines()
        return result, [json.loads(line) for line in lines]

    def test_records_only_changes_once_per_frame(self):
        ok, result = self.run_request("sampler.lua", {"sources": "CBRTBUF,CBRTREG"})
        self.assertTrue(ok, result)
        self.assertEqual((result["active"], list(result["ids"].values())), (True, [10, 11]))
        self.assertEqual(list(self.lua.mutators.values()), ["CBTCLab_ProjectileWatch"])
        self.runtime.execute("table.insert(sprites[0].m_timedEffectList, effect('CBRTBUF', 0, 4096, 5090))")
        self.runtime.execute("table.insert(sprites[0].m_timedEffectList, effect('SPWI999', 0, 4096, 9999))")
        self.frame()
        self.frame()  # nothing changed
        self.frame(world=5001)
        self.lua.sprites[0].m_baseStats.m_hitPoints = 81
        self.frame()
        self.assertEqual(self.lua.polls, 8)  # the console's own poll still runs every time
        result, records = self.export("case_a")
        self.assertEqual(records[0]["k"], "header")
        self.assertEqual(records[0]["lab"], "CBR TimeClocks Lab 2730\n")
        samples = [r for r in records if r["k"] == "s"]
        self.assertEqual([(r["w"], r["a"][0]["hp"]) for r in samples], [(5000, 80), (5001, 80), (5001, 81)])
        self.assertEqual(samples[0]["a"][0]["fx"], "CBRTBUF/0/4096/5090")
        self.assertEqual((samples[0]["ts"], samples[0]["tc"], samples[0]["au"]), (0, -1, 4000))
        self.assertEqual(result["records"], 3)
        # Export cleared the records; a second export of the same name is refused.
        _, again = self.export("case_b")
        self.assertEqual(len(again), 1)
        ok, error = self.run_request("sampler-export.lua", {"name": "case_a"})
        self.assertFalse(ok)
        self.assertIn("EXISTS", error)

    def test_projectiles_are_followed_from_decode_to_gone(self):
        self.assertTrue(self.run_request("sampler.lua", {})[0])
        decode = self.runtime.eval("""function(pointer, kind)
            mem[pointer + 0x60] = 187
            _G[mutators[1]].projectileMutator({projectile = {_ptr = pointer, _type = kind},
                originatingSprite = sprites[1], decodeSource = 6})
        end""")
        decode(0x9000000, 8)
        self.frame()  # not in the object array yet
        entry = BASE + 0x68F910 + 16 * 2
        self.poke(entry, 7)
        self.poke(entry + 8, 0x9000000)
        object_id = 2 * 65536 + 7
        self.runtime.execute("objects[%d] = {_ptr = 0x9000000, m_pos = {x = 300, y = 400}}" % object_id)
        for address, value in ((0x9000000 + 0x3C8, 1), (0x9000000 + 0x3C6, 10), (0x9000000 + 0x3CC, 75),
                               (0x9000000 + 0x3CE, 30)):
            self.poke(address, value)
        self.frame(world=5001)
        self.poke(0x9000000 + 0x3CE, 29)
        self.frame(world=5002)
        self.runtime.execute("objects[%d] = nil" % object_id)
        self.frame(world=5003)
        _, records = self.export("projectile")
        kinds = [r["k"] for r in records]
        self.assertEqual(kinds[:2], ["header", "decode"])
        self.assertEqual(records[1]["by"], 11)
        self.assertEqual(records[1]["pro"], 187)
        self.assertEqual(records[1]["ty"], "CProjectileArea")
        fired = next(r for r in records if r["k"] == "fired")
        self.assertEqual(fired["id"], object_id)
        tracked = [r["pj"][0] for r in records if r["k"] == "s" and r["pj"]]
        self.assertEqual([(p["ar"], p["rm"], p["rl"], p["cd"]) for p in tracked], [(1, 10, 75, 30), (1, 10, 75, 29)])
        self.assertIn("gone", kinds)

    def test_marks_and_failures_never_break_the_console(self):
        self.assertTrue(self.run_request("sampler.lua", {})[0])
        self.runtime.execute("EEex_LuaAction_Object = sprites[1]; CBTCLab_Mark('stop_cast')")
        self.runtime.execute("EEex_GameObject_Get = function() error('engine trouble') end")
        for _ in range(4):
            self.frame()
        self.assertEqual(self.lua.polls, 8)
        self.assertFalse(self.lua.CBTCLab.active)
        self.assertIn("engine trouble", self.lua.CBTCLab.lastError)
        _, records = self.export("marks")
        mark = next(r for r in records if r["k"] == "mark")
        self.assertEqual((mark["label"], mark["actor"], mark["w"]), ("stop_cast", 11, 5000))
        self.assertEqual(records[0]["errors"], 3)

    def test_a_different_object_array_is_refused(self):
        self.poke(BASE + 0x276738, 0)
        ok, error = self.run_request("sampler.lua", {})
        self.assertFalse(ok)
        self.assertIn("UNEXPECTED_OBJECT_ARRAY", error)


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class TcProbeTests(unittest.TestCase):
    """tc-probe.lua: the tracked effects, clocks, mod and sampler state it reports, read only."""

    def probe(self, arguments, setup=""):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        runtime.execute("""
            mem = {}
            local function u(address) return mem[address] or 0 end
            EEex_GetImageBase = function() return %d end
            EEex_Read32, EEex_ReadU8, EEex_ReadPtr = u, u, u
            EEex_UDToPtr = function(value) return value._ptr end
            EEex_Utility_IterateCPtrList = function(list, f) for _, e in ipairs(list) do f(e) end end
            CGameObjectType = {SPRITE = 1}
            local function effect(source, opcode, deadline, pointer)
                return {_ptr = pointer, m_sourceRes = {get = function() return source end}, m_effectId = opcode,
                    m_durationType = 4096, m_duration = deadline, m_effectAmount = 2, m_dWFlags = 3}
            end
            local function sprite(id, name, pointer, effects)
                return {m_id = id, _name = name, _ptr = pointer, m_objectType = 1, m_baseStats = {m_hitPoints = 50},
                    m_pos = {x = 1, y = 2}, m_curAction = {m_actionID = 0}, m_timedEffectList = effects,
                    m_equipedEffectList = {}, m_pArea = {m_resref = {get = function() return "AR0602" end}}}
            end
            portraits = {[0] = sprite(10, "CBRTS Subject", 0x8000000,
                {effect("CBRTREG", 98, 5180, 0x9000000), effect("SPWI999", 0, 1, 0x9100000)}),
                [1] = sprite(11, "Imoen", 0x8100000, {})}
            objects = {[77] = sprite(77, "Bounty Hunter", 0x8200000, {effect("spwi213", 39, 5135, 0x9200000)})}
            EEex_Sprite_GetInPortrait = function(slot) return portraits[slot] end
            EEex_Sprite_GetName = function(s) return s._name end
            EEex_GameObject_Get = function(id) return objects[id] end
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = 1, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = 0x7000000, m_worldTime = {m_gameTime = 5000}}}}
            mem[0x7000000 + 0x9690] = 120
            mem[0x7000000 + 0x9694] = 11
            mem[0x9000000 + 0x6C] = 4990
            mem[0x8000000 + 0x58] = 1
        """ % BASE)
        runtime.execute(setup)
        run = runtime.eval("function(code) return pcall(assert(loadstring(code))) end")
        return run(code("tc-probe.lua", arguments))

    def test_reports_tracked_effects_clocks_and_the_mod(self):
        ok, result = self.probe({"ids": "77,78"}, """
            CBTC_TimeClocks = {Status = "active: Time Stop", installed = true,
                options = {timeStop = true, chitin = 12345}, core = {stats = {passes = 4}}}
            CBTCLab = {active = true, count = 9, overflow = false, errors = 0, projectiles = {{}, {}},
                pending = {[1] = {}}}""")
        self.assertTrue(ok, result)
        subject = result["actors"]["portrait0"]
        self.assertEqual([(e["source"], e["deadline"], e["origin"]) for e in subject["timed"].values()],
                         [("CBRTREG", 5180, 4990)])
        self.assertEqual(result["actors"]["id77"]["timed"][1]["source"], "SPWI213")
        self.assertFalse(result["actors"]["id78"])
        self.assertEqual((result["time_stop_remaining"], result["time_stop_caster"], result["scheduler"]),
                         (120, 11, None))
        self.assertEqual(dict(result["time_clocks"]["options"]), {"timeStop": True})
        self.assertEqual((result["sampler"]["projectiles"], result["sampler"]["pending"]), (2, 1))

    def test_without_the_mod_or_the_sampler(self):
        ok, result = self.probe({})
        self.assertTrue(ok, result)
        self.assertEqual((result["time_clocks"], result["sampler"]), ("not loaded", "not installed"))
        self.assertEqual(set(result["actors"]), {"portrait0", "portrait1"})  # a Lua table: no key order


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class SaveLoadTests(unittest.TestCase):
    """save.lua, load-save.lua and party-ai.lua: their preconditions and the click they queue."""

    def run_lua(self, name, arguments, setup):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        runtime.execute("""
            clicked = {}
            stack = {}
            Infinity_IsMenuOnStack = function(name) return stack[name] and 1 or 0 end
            Infinity_GetTransitionInProgress = function() return false end
            Infinity_ClickItem = function(item) clicked[#clicked + 1] = item end
            Infinity_GetFrameCounter = function() return 7 end
            nameToItem = {CBRTSQA_QUICKSAVE = 'quick', CBRTSQA_LOAD = 'load'}
            EEex_UDToPtr = function(value) return 0x100 end
            EEex_Read32 = function() return 0 end
            worldScreen = {}
            e = {GetActiveEngine = function() return worldScreen end}
            sidebarsGreyed = 0
            world = {m_bPaused = 1, m_bHardPaused = 0}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = world,
                m_pObjectGame = {m_bGameLoaded = 1, m_worldTime = {m_gameTime = 1234}}}}
            ai = true
            game = {GetPartyAI = function() return ai end, ToggleAI = function() ai = not ai end}
        """)
        runtime.execute(setup)
        run = runtime.eval("function(code) local ok, r = pcall(assert(loadstring(code))) return ok, r, #clicked end")
        return run(code(name, arguments))

    def test_quick_save_only_from_a_quiet_world_screen(self):
        ready = "stack.LEFT_SIDEBAR_BOTTOM = true"
        ok, result, clicks = self.run_lua("save.lua", {}, ready)
        self.assertTrue(ok, result)
        self.assertEqual((result["queued"], result["game_time"], clicks), ("CBRTSQA_QUICKSAVE", 1234, 1))
        for guard, setup in {"PAUSE_FIRST": "world.m_bPaused = 0", "IN_DIALOGUE": "stack.WORLD_DIALOG = true",
                             "NOT_THE_WORLD_SCREEN": "e.GetActiveEngine = function() return {} end",
                             "SIDEBAR_GREYED": "sidebarsGreyed = 1", "NO_GAME": "EngineGlobals.g_pBaldurChitin"
                             ".m_pObjectGame.m_bGameLoaded = 0"}.items():
            with self.subTest(guard=guard):
                ok, error, clicks = self.run_lua("save.lua", {}, ready + "\n" + setup)
                self.assertEqual((ok, clicks), (False, 0))
                self.assertIn(guard, error)
        ok, error, clicks = self.run_lua("save.lua", {}, "")
        self.assertEqual((ok, clicks), (False, 0))
        self.assertIn("EXPECTED_MENU:LEFT_SIDEBAR_BOTTOM", error)

    def test_load_selects_the_named_save_then_clicks_load(self):
        saves = """stack.LOAD = true
            gameSaves = {files = {{fileName = '000000001-Quick-Save', slotName = 'Quick-Save', time = 'x', fileTime = 2},
                {fileName = '000000000-Quick-Save', slotName = 'Quick-Save', time = 'y', fileTime = 1}}}"""
        ok, result, clicks = self.run_lua("load-save.lua", {}, saves)
        self.assertTrue(ok, result)
        self.assertEqual((len(result["saves"]), clicks), (2, 0))
        ok, result, clicks = self.run_lua("load-save.lua", {"file": "000000000-Quick-Save"}, saves)
        self.assertTrue(ok, result)
        self.assertEqual((result["row"], clicks), (2, 1))
        ok, error, clicks = self.run_lua("load-save.lua", {"file": "000000009-Quick-Save"}, saves)
        self.assertEqual((ok, clicks), (False, 0))
        self.assertIn("SAVE_NOT_FOUND", error)
        ok, error, clicks = self.run_lua("load-save.lua", {"file": "x"}, "")
        self.assertEqual((ok, clicks), (False, 0))
        self.assertIn("EXPECTED_MENU:LOAD", error)

    def test_party_ai_toggles_only_when_needed(self):
        ok, result, _ = self.run_lua("party-ai.lua", {"want": "off"}, "")
        self.assertTrue(ok, result)
        self.assertEqual((result["before"], result["after"], result["toggled"]), (True, False, True))
        ok, result, _ = self.run_lua("party-ai.lua", {"want": "off"}, "ai = false")
        self.assertEqual((ok, result["toggled"]), (True, False))
        ok, error, _ = self.run_lua("party-ai.lua", {"want": "maybe"}, "")
        self.assertFalse(ok)
        self.assertIn("ARGS.want required", error)


if __name__ == "__main__":
    unittest.main()
