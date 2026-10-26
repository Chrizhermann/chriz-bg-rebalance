"""Offline checks of the lab console client and its Lua requests; no game, no files sent."""

from __future__ import annotations

import contextlib
import io
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


class ArgumentTests(unittest.TestCase):
    def test_arguments_follow_directives_and_stay_data(self):
        code = "--@watchdog=2000000\n--@nowatchdog\nreturn ARGS.name\n"
        sent = lab_rc.with_arguments(code, {"name": 'x"]] .. os.exit() --\\'})
        lines = sent.splitlines()
        self.assertEqual(lines[:2], ["--@watchdog=2000000", "--@nowatchdog"])
        self.assertTrue(lines[2].startswith("local ARGS = {name = \"\\120\\034"))
        self.assertNotIn("os.exit", sent.split("\n", 3)[2])
        self.assertEqual(lines[3], "return ARGS.name")

    @unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
    def test_lua_receives_the_exact_strings(self):
        runtime = lupa.LuaRuntime()
        values = {"name": "baseline_01", "character": "Abdel - Fighter - Neutral Good",
                  "odd": 'quote " backslash \\ newline \n umlaut ä'}
        chunk = lab_rc.with_arguments("return ARGS.name, ARGS.character, ARGS.odd\n", values)
        result = runtime.execute(chunk)
        decoded = [value.decode("utf-8") if isinstance(value, bytes) else value for value in result]
        self.assertEqual(decoded, [values["name"], values["character"], values["odd"]])

    def test_labels_and_argument_names_are_simple(self):
        self.assertTrue(lab_rc.LABEL.match("01-start-soa"))
        self.assertFalse(lab_rc.LABEL.match("../escape"))
        self.assertTrue(lab_rc.NAME.match("subject"))
        self.assertFalse(lab_rc.NAME.match("a-b"))
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(lab_rc.main(["lua", "x", "return 1", "--arg", "bad-name=1"]), 2)
        self.assertIn("Invalid --arg", error.getvalue())

    def test_lua_keywords_are_no_argument_names(self):
        for name in ("then", "end", "nil"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    lab_rc.with_arguments("return 1", {name: "x"})
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(lab_rc.main(["lua", "x", "return 1", "--arg", f"{name}=1"]), 2)
                self.assertIn("Invalid --arg", error.getvalue())


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class RequestSyntaxTests(unittest.TestCase):
    def test_every_request_compiles(self):
        runtime = lupa.LuaRuntime()
        compile_only = runtime.eval("function(code, name) local f, e = loadstring(code, name) return f ~= nil, e end")
        files = sorted(REQUESTS.glob("*.lua"))
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            with self.subTest(request=path.name):
                ok, error = compile_only(lab_rc.with_arguments(path.read_text(encoding="utf-8"), {"x": "1"}),
                                         "@" + path.name)
                self.assertTrue(ok, error)

    def test_requests_that_change_state_check_their_preconditions(self):
        for name, guards in {"click.lua": ("EXPECTED_MENU", "QA_ITEM_REQUIRED"),
                             "start-soa.lua": ("UNEXPECTED_MENU", "TRANSITION_IN_PROGRESS"),
                             "queue.lua": ("PAUSE_FIRST", "NOT_THE_SUBJECT", "ARM_FIRST", "DISARMED_ONLY",
                                           "FIXTURES_PRESENT", "NO_CONTROLLER", "NOT_THE_CONTROLLER",
                                           "CONTROLLER_BUSY", "FIXTURES_FIRST", "TIME_STOP_ACTIVE",
                                           "INVALID_WAIT", "UNKNOWN_SPELL", "SUBJECT_BUSY",
                                           "SPEED_PRESENT", "FIXTURES_MIXED", "UNKNOWN_CASTER",
                                           "STEP_NEEDS_CONTROLLER", "UNKNOWN_STEP", "PLAYER1_NOT_THE_SUBJECT",
                                           "INVALID_STEP_WAIT", "IMMUNITY_PRESENT", "INVALID_REAPPLY_WAIT",
                                           "INVALID_POINT", "NOT_A_DUMMY", "DUMMY_HELD", "DUMMY_NOT_HELD",
                                           "ACTIVITY_NOT_ARMED", "UNKNOWN_FIXTURE", "BUFF_ONLY_FIRST"),
                             "activity.lua": ("INSTALL_FIRST", "NOT_THE_SUBJECT", "UNKNOWN_OP"),
                             "save.lua": ("EXPECTED_MENU:LOAD", "NO_SAVE_LIST", "SAVE_MATCHES"),
                             "pause.lua": ("NO_GAME", "PAUSE_STATE_UNCHANGED"),
                             "dialog.lua": ("CONFIRM_MODE_REQUIRED", "DIALOG_BUTTON_NOT_CLICKABLE"),
                             "pick-character.lua": ("AMBIGUOUS_CHARACTER", "CHARACTER_NOT_FOUND"),
                             "fix.lua": ("FIX_NOT_LOADED", "UNKNOWN_OP", "PAUSE_FIRST", "NO_SUBJECT",
                                         "NOT_THE_SUBJECT"),
                             "cor.lua": ("COR_NOT_LOADED", "UNKNOWN_OP", "PAUSE_FIRST", "INVALID_ID",
                                         "NOT_A_CREATURE", "ARGS.on required", "ARGS.name required"),
                             "apply.lua": ("PAUSE_FIRST", "TIME_STOP_ACTIVE", "NOT_A_CREATURE", "ACTOR_BUSY",
                                           "TOO_MANY_STEPS", "INVALID_STEP", "NOT_A_LAB_FIXTURE",
                                           "INVALID_TARGET", "NO_STEPS"),
                             "cloud.lua": ("CLOUD_NOT_LOADED", "UNKNOWN_OP", "PAUSE_FIRST", "NOT_A_CREATURE",
                                           "NOT_A_CLOUD_SPELL", "ARM_FIRST", "TIME_STOP_ACTIVE", "CASTER_BUSY",
                                           "INVALID_POINT", "INVALID_WAIT", "BYSTANDER_IN_REACH"),
                             "quit.lua": ("STOP_FIRST",)}.items():
            text = (REQUESTS / name).read_text(encoding="utf-8")
            for guard in guards:
                self.assertIn(guard, text, f"{name} lacks {guard}")


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class QueueRequestTests(unittest.TestCase):
    """queue.lua against stub bindings: what it queues on whom, and what it refuses."""

    GAME = 0x5000  # Stub CInfGame pointer; +0x9690 is the Time Stop counter.
    DUMMY = 77

    def queue(self, arguments, paused=1, armed=True, fixtures=("CBRTBUF", "CBRTREG"),
              controller=("Imoen", 2), stop=0, action=0, player1=10, dummy=("BATIN01", ("CBRTDUM",) * 2),
              activity=(True, 10)):
        """Runs queue.lua; returns (ok, queued or error, queue count, target name). self.side holds
        the scripting target the request stored on the subject and whether it cleared its actions."""
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, armed, sources, controllerName, controllerID,
                stop, game, action, player1, dummyID, dummyRes, dummySources, activityArmed, activitySubject)
            local queued, side = {}, {}
            local function list(entries)
                local out = {}
                if type(entries) == "table" then return out end  -- No Python list: no effects.
                for source in python.iter(entries) do
                    out[#out + 1] = {m_sourceRes = {get = function() return source end}}
                end
                return out
            end
            local function actor(id, name, entries, resref)
                return {m_id = id, _name = name, m_timedEffectList = list(entries),
                    m_baseStats = {m_hitPoints = 80}, m_curAction = {m_actionID = action},
                    m_resref = {get = function() return resref end},
                    isSprite = function() return true end,
                    setStoredScriptingTarget = function(self, key, target) side.stored = {key, target.m_id} end,
                    virtual_ClearActions = function(self, flag) side.cleared = flag end}
            end
            local actors = {[0] = actor(10, "CBRTS Subject", sources, "CHARBASE")}
            if controllerName then actors[1] = actor(controllerID, controllerName, {}, "IMOEN") end
            local objects = {[10] = actors[0]}
            if dummyRes then objects[dummyID] = actor(dummyID, "Bat", dummySources, dummyRes) end
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = game, m_worldTime = {m_gameTime = 1000}}}}
            CBRTS = {Status = function() return {armed = armed} end}
            CBRTA = {armed = activityArmed, subject = activitySubject}
            EEex_Sprite_GetInPortrait = function(slot) return actors[slot] end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
            EEex_GameObject_Get = function(id) return objects[id] end
            EEex_Object_EvalStringAsAIBase = function(text, caller)
                assert(text == "Player1", "unexpected object")
                return objects[player1] or actors[1]
            end
            EEex_Utility_IterateCPtrList = function(entries, f) for _, e in ipairs(entries) do f(e) end end
            EEex_UDToPtr = function(value) return value._ptr end
            EEex_Read32 = function(address)
                assert(address == game + 0x9690, "unexpected read")
                return stop
            end
            EEex_Action_QueueResponseStringOnAIBase = function(response, target)
                queued[#queued + 1] = {response = response, target = target._name}
            end
            local ok, result = pcall(assert(loadstring(code, "@queue.lua")))
            local stored = side.stored and (side.stored[1] .. "=" .. side.stored[2]) or nil
            if not ok then return false, tostring(result), #queued, nil, stored, side.cleared end
            return true, result.queued, #queued, queued[1].target, stored, side.cleared
        end""")
        code = lab_rc.with_arguments((REQUESTS / "queue.lua").read_text(encoding="utf-8"),
                                     {"subject": "CBRTS Subject", **arguments})
        name, identity = controller if controller else (None, None)
        dummy_res, dummy_sources = dummy if dummy else (None, ())
        active, subject = activity if activity else (False, None)
        *result, stored, cleared = attempt(code, paused, armed, list(fixtures), name, identity, stop, self.GAME,
                                           action, player1, self.DUMMY, dummy_res, list(dummy_sources),
                                           active, subject)
        self.side = {"stored": stored, "cleared": cleared}
        return tuple(result)

    def refused(self, base, cases):
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.queue({**base, **arguments}, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)

    def test_timestop_runs_on_the_controller_after_its_wait(self):
        ok, response, count, target = self.queue({"what": "timestop", "controller": "Imoen", "wait": "66"})
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('SmallWait(66)\nApplySpellRES("CBRTSTP",Myself)', 1, "Imoen"))
        ok, response, _, _ = self.queue({"what": "timestop", "controller": "Imoen", "wait": "0"})
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTSTP",Myself)'))

    def test_timestop_refuses_without_its_case(self):
        base = {"what": "timestop", "controller": "Imoen", "wait": "66"}
        self.refused(base, {
            "PAUSE_FIRST": ({}, {"paused": 0}),
            "ARM_FIRST": ({}, {"armed": False}),
            "NO_CONTROLLER": ({}, {"controller": None}),
            "NOT_THE_CONTROLLER": ({"controller": "Jaheira"}, {}),
            "CONTROLLER_BUSY": ({}, {"action": 23}),
            "FIXTURES_FIRST": ({}, {"fixtures": ("CBRTREG",)}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90}),
            "UNKNOWN_CASTER": ({"caster": "Imoen"}, {}),
        })
        with self.subTest(guard="NOT_THE_CONTROLLER", case="the subject itself"):
            ok, error, count = self.queue(base, controller=("Imoen", 10))[:3]
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("NOT_THE_CONTROLLER", error)
        with self.subTest(guard="FIXTURES_FIRST", case="a second regeneration"):
            ok, error, count = self.queue(base, fixtures=("CBRTBUF", "CBRTREG", "CBRTREG"))[:3]
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("FIXTURES_FIRST", error)
        for wait in ("-1", "301", "2.5", "x"):
            with self.subTest(guard="INVALID_WAIT", wait=wait):
                ok, error, count = self.queue({**base, "wait": wait})[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("INVALID_WAIT", error)

    def test_the_subject_can_cast_its_own_stop(self):
        ok, response, count, target = self.queue({"what": "timestop", "caster": "subject", "wait": "20"},
                                                 controller=None)
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target),
                         ('SmallWait(20)\nApplySpellRES("CBRTSTP",Myself)', 1, "CBRTS Subject"))
        base = {"what": "timestop", "caster": "subject", "wait": "20"}
        self.refused(base, {"SUBJECT_BUSY": ({}, {"action": 23}),
                            "STEP_NEEDS_CONTROLLER": ({"step": "remove", "step_wait": "5"}, {})})

    def test_steps_during_the_stop_follow_on_the_controller(self):
        expected = {
            "stop": 'SmallWait(120)\nApplySpellRES("CBRTSTP",Myself)',
            "remove": 'SmallWait(120)\nApplySpellRES("CBRTRMR",Player1)',
            "refresh": 'SmallWait(120)\nApplySpellRES("CBRTRMR",Player1)\nApplySpellRES("CBRTREG",Player1)',
            "apply": 'SmallWait(120)\nApplySpellRES("CBRTREG",Player1)',
        }
        for step, tail in expected.items():
            with self.subTest(step=step):
                fixtures = ("CBRTBUF",) if step == "apply" else ("CBRTBUF", "CBRTREG")
                ok, response, count, target = self.queue(
                    {"what": "timestop", "controller": "Imoen", "wait": "20", "step": step, "step_wait": "120"},
                    fixtures=fixtures)
                self.assertTrue(ok, response)
                self.assertEqual((response, count, target),
                                 ('SmallWait(20)\nApplySpellRES("CBRTSTP",Myself)\n' + tail, 1, "Imoen"))
        ok, response, _, _ = self.queue({"what": "timestop", "controller": "Imoen", "wait": "20", "step": "remove",
                                         "step_wait": "0"})
        self.assertEqual((ok, response),
                         (True, 'SmallWait(20)\nApplySpellRES("CBRTSTP",Myself)\nApplySpellRES("CBRTRMR",Player1)'))

    def test_steps_during_the_stop_refuse_a_foreign_case(self):
        base = {"what": "timestop", "controller": "Imoen", "wait": "20", "step": "remove", "step_wait": "30"}
        self.refused(base, {
            "UNKNOWN_STEP": ({"step": "dispel"}, {}),
            "INVALID_STEP_WAIT": ({"step_wait": "301"}, {}),
            "PLAYER1_NOT_THE_SUBJECT": ({}, {"player1": 2}),
            "BUFF_ONLY_FIRST": ({"step": "apply"}, {}),
            "FIXTURES_FIRST": ({"step": "refresh"}, {"fixtures": ()}),
        })

    def test_speed_runs_on_the_subject_after_its_wait(self):
        for spell in ("CBRTHST", "CBRTIHS", "CBRTWHS", "CBRTSRH", "CBRTSLW"):
            with self.subTest(spell=spell):
                ok, response, count, target = self.queue({"what": "speed", "spell": spell, "wait": "74"})
                self.assertTrue(ok, response)
                self.assertEqual((response, count, target),
                                 (f'SmallWait(74)\nApplySpellRES("{spell}",Myself)', 1, "CBRTS Subject"))
        ok, response, _, _ = self.queue({"what": "speed", "spell": "CBRTSLW", "wait": "0"}, fixtures=())
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTSLW",Myself)'))

    def test_speed_refuses_without_a_clean_case(self):
        base = {"what": "speed", "spell": "CBRTHST", "wait": "74"}
        self.refused(base, {
            "ARM_FIRST": ({}, {"armed": False}),
            "UNKNOWN_SPELL": ({"spell": "CBRTSTP"}, {}),
            "SUBJECT_BUSY": ({}, {"action": 23}),
            "SPEED_PRESENT": ({}, {"fixtures": ("CBRTBUF", "CBRTREG", "CBRTSLW")}),
            "FIXTURES_MIXED": ({}, {"fixtures": ("CBRTREG",)}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90}),
            "INVALID_WAIT": ({"wait": "301"}, {}),
        })
        for present in ("CBRTHST", "CBRTIHS", "CBRTWHS", "CBRTSRH"):
            with self.subTest(guard="SPEED_PRESENT", present=present):
                ok, error, count = self.queue({**base, "spell": "CBRTSLW"}, fixtures=(present,))[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("SPEED_PRESENT", error)
        with self.subTest(guard="FIXTURES_MIXED", case="two of each"):
            ok, error, count = self.queue(base, fixtures=("CBRTBUF", "CBRTREG") * 2)[:3]
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("FIXTURES_MIXED", error)

    def test_immunity_comes_before_the_fixtures(self):
        ok, response, count, target = self.queue({"what": "immunity"}, fixtures=())
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('ApplySpellRES("CBRTTSI",Myself)', 1, "CBRTS Subject"))
        self.refused({"what": "immunity"}, {
            "ARM_FIRST": ({}, {"armed": False, "fixtures": ()}),
            "SUBJECT_BUSY": ({}, {"action": 23, "fixtures": ()}),
            "IMMUNITY_PRESENT": ({}, {"fixtures": ("CBRTTSI",)}),
            "FIXTURES_PRESENT": ({}, {}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90, "fixtures": ()}),
        })

    def test_removal_and_reapplication_run_on_the_subject(self):
        ok, response, count, target = self.queue({"what": "remove", "spell": "CBRTRMR", "wait": "50",
                                                  "reapply_wait": "30"})
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), (
            'SmallWait(50)\nApplySpellRES("CBRTRMR",Myself)\nSmallWait(30)\nApplySpellRES("CBRTREG",Myself)',
            1, "CBRTS Subject"))
        ok, response, _, _ = self.queue({"what": "remove", "spell": "CBRTRMB", "wait": "0"})
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTRMB",Myself)'))
        self.refused({"what": "remove", "spell": "CBRTRMR", "wait": "50"}, {
            "ARM_FIRST": ({}, {"armed": False}),
            "UNKNOWN_SPELL": ({"spell": "CBRTREG"}, {}),
            "SUBJECT_BUSY": ({}, {"action": 23}),
            "FIXTURES_FIRST": ({}, {"fixtures": ("CBRTBUF",)}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90}),
            "INVALID_REAPPLY_WAIT": ({"reapply_wait": "-1"}, {}),
        })

    def test_dummy_is_created_by_the_idle_controller(self):
        ok, response, count, target = self.queue({"what": "dummy", "controller": "Imoen", "x": "3480", "y": "2850"},
                                                 armed=False)
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('CreateCreature("BATIN01",[3480.2850],0)', 1, "Imoen"))
        self.refused({"what": "dummy", "controller": "Imoen", "x": "3480", "y": "2850"}, {
            "DISARMED_ONLY": ({}, {}),
            "CONTROLLER_BUSY": ({}, {"armed": False, "action": 23}),
            "INVALID_POINT": ({"x": "-1"}, {"armed": False}),
        })

    def test_hold_runs_on_the_dummy_only(self):
        ok, response, count, target = self.queue({"what": "hold", "id": str(self.DUMMY)}, dummy=("BATIN01", ()))
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('ApplySpellRES("CBRTDUM",Myself)', 1, "Bat"))
        self.refused({"what": "hold", "id": str(self.DUMMY)}, {
            "DUMMY_HELD": ({}, {}),
            "NOT_A_DUMMY": ({}, {"dummy": ("RAT", ())}),
        })
        for other in ("10", "999", "x"):
            with self.subTest(guard="NOT_A_DUMMY", id=other):
                ok, error, count = self.queue({"what": "hold", "id": other}, dummy=("BATIN01", ()))[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("NOT_A_DUMMY", error)

    def test_activity_walks_then_attacks_the_held_dummy(self):
        ok, response, count, target = self.queue({"what": "activity", "id": str(self.DUMMY), "x": "3512",
                                                  "y": "2850"})
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target),
                         ('MoveToPoint([3512.2850])\nAttack(EEex_Target("CBRTDummy"))', 1, "CBRTS Subject"))
        self.assertEqual(self.side["stored"], f"CBRTDummy={self.DUMMY}")
        self.refused({"what": "activity", "id": str(self.DUMMY), "x": "3512", "y": "2850"}, {
            "ACTIVITY_NOT_ARMED": ({}, {"activity": (False, 10)}),
            "SUBJECT_BUSY": ({}, {"action": 23}),
            "DUMMY_NOT_HELD": ({}, {"dummy": ("BATIN01", ("CBRTDUM",))}),
            "NOT_A_DUMMY": ({"id": "10"}, {}),
            "INVALID_POINT": ({"y": "2850.5"}, {}),
        })
        with self.subTest(guard="ACTIVITY_NOT_ARMED", case="armed on another actor"):
            ok, error, count = self.queue({"what": "activity", "id": str(self.DUMMY), "x": "1", "y": "1"},
                                          activity=(True, 2))[:3]
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("ACTIVITY_NOT_ARMED", error)

    def test_walk_clears_the_subject_first(self):
        ok, response, count, target = self.queue({"what": "walk", "x": "3704", "y": "2850"}, armed=False,
                                                 action=23)
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ("MoveToPoint([3704.2850])", 1, "CBRTS Subject"))
        self.assertIs(self.side["cleared"], False)
        self.refused({"what": "walk", "x": "3704", "y": "2850"}, {"DISARMED_ONLY": ({}, {})})

    def test_halt_lets_the_controller_clear_the_subject(self):
        ok, response, count, target = self.queue({"what": "halt", "controller": "Imoen"}, armed=False)
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ("ClearActions(Player1)", 1, "Imoen"))
        self.refused({"what": "halt", "controller": "Imoen"}, {
            "DISARMED_ONLY": ({}, {}),
            "PLAYER1_NOT_THE_SUBJECT": ({}, {"armed": False, "player1": 2}),
            "NOT_THE_CONTROLLER": ({"controller": "Jaheira"}, {"armed": False})})

    def test_fixtures_go_only_onto_a_clean_subject(self):
        ok, response, count, target = self.queue({"what": "fixtures"}, fixtures=())
        self.assertTrue(ok, response)
        self.assertEqual((count, target), (1, "CBRTS Subject"))
        self.assertIn('ApplySpellRES("CBRTREG",Myself)', response)
        for leftover in (("CBRTBUF",), ("CBRTREG",)):
            with self.subTest(leftover=leftover):
                ok, error, count = self.queue({"what": "fixtures"}, fixtures=leftover)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("FIXTURES_PRESENT", error)

    def test_one_fixture_alone(self):
        ok, response, count, target = self.queue({"what": "fixtures", "only": "CBRTBUF"}, fixtures=())
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('ApplySpellRES("CBRTBUF",Myself)', 1, "CBRTS Subject"))
        ok, response, _, _ = self.queue({"what": "fixtures", "only": "CBRTREG"}, fixtures=("CBRTBUF",))
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTREG",Myself)'))
        self.refused({"what": "fixtures", "only": "CBRTBUF"}, {
            "FIXTURES_PRESENT": ({}, {"fixtures": ("CBRTBUF",)}),
            "UNKNOWN_FIXTURE": ({"only": "CBRTSTP"}, {"fixtures": ()}),
            "ARM_FIRST": ({}, {"armed": False, "fixtures": ()}),
        })


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class ActivityRequestTests(unittest.TestCase):
    """activity.lua against stub listeners: registration once, recording only the armed subject."""

    def setUp(self):
        self.runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.runtime.execute("""
            listeners = {action = {}, hit = {}}
            world = 500
            subject = {m_id = 10, _name = "CBRTS Subject", m_pos = {x = 3704, y = 2850}}
            other = {m_id = 2, _name = "Imoen", m_pos = {x = 1, y = 1}}
            EngineGlobals = {g_pBaldurChitin = {m_pObjectGame = {m_worldTime = {}}}}
            setmetatable(EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime,
                {__index = function() return world end})
            EEex_Sprite_GetInPortrait = function(slot) if slot == 0 then return subject end end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
            EEex_Action_AddSpriteStartedActionListener = function(f) listeners.action[#listeners.action + 1] = f end
            EEex_Sprite_AddBlockWeaponHitListener = function(f) listeners.hit[#listeners.hit + 1] = f end
            function act(sprite, id) return listeners.action[1](sprite, {m_actionID = id}) end
            function hit(attacker, target)
                return listeners.hit[1]({attackingSprite = attacker, targetSprite = target})
            end
        """)

    def request(self, arguments):
        code = lab_rc.with_arguments((REQUESTS / "activity.lua").read_text(encoding="utf-8"), arguments)
        attempt = self.runtime.eval("""function(code)
            local ok, result = pcall(assert(loadstring(code, "@activity.lua")))
            return ok, ok and result or tostring(result)
        end""")
        return attempt(code)

    def test_install_registers_both_listeners_once(self):
        self.assertFalse(self.request({"op": "arm", "subject": "CBRTS Subject"})[0])
        for _ in range(2):
            ok, result = self.request({"op": "install"})
            self.assertTrue(ok, result)
        self.assertEqual((len(self.runtime.eval("listeners.action")), len(self.runtime.eval("listeners.hit"))), (1, 1))

    def test_records_only_the_armed_subject_and_never_blocks(self):
        self.request({"op": "install"})
        g = self.runtime.globals()
        self.assertIsNone(g.act(g.subject, 23))  # Not armed yet: nothing recorded.
        ok, result = self.request({"op": "arm", "subject": "CBRTS Subject"})
        self.assertTrue(ok, result)
        g.world = 510
        self.assertIsNone(g.act(g.subject, 23))
        self.assertIsNone(g.act(g.other, 3))
        g.world = 530
        self.assertIsNone(g.hit(g.subject, g.other))
        self.assertIsNone(g.hit(g.other, g.subject))
        ok, result = self.request({"op": "disarm"})
        g.world = 540
        g.hit(g.subject, g.other)
        ok, result = self.request({"op": "read"})
        self.assertTrue(ok, result)
        self.assertEqual((result.armed, result.subject, result.overflow, result.game_time), (False, 10, False, 540))
        self.assertEqual([(a.w, a.id, a.x, a.y) for a in result.actions.values()], [(510, 23, 3704, 2850)])
        self.assertEqual([(h.w, h.target) for h in result.hits.values()], [(530, 2)])

    def test_arming_clears_and_overflow_stops_recording(self):
        self.request({"op": "install"})
        self.request({"op": "arm", "subject": "CBRTS Subject"})
        g = self.runtime.globals()
        for _ in range(501):
            g.hit(g.subject, g.other)
        ok, result = self.request({"op": "read"})
        self.assertEqual((len(result.hits), result.armed, result.overflow), (500, False, True))
        ok, result = self.request({"op": "arm", "subject": "CBRTS Subject"})
        self.assertEqual((len(result.hits), result.armed, result.overflow), (0, True, False))

    def test_refusals(self):
        self.assertIn("INSTALL_FIRST", self.request({"op": "read"})[1])
        self.request({"op": "install"})
        self.assertIn("NOT_THE_SUBJECT", self.request({"op": "arm", "subject": "Imoen"})[1])
        self.assertIn("UNKNOWN_OP", self.request({"op": "export"})[1])


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class SaveRequestTests(unittest.TestCase):
    """save.lua against a stub load screen list."""

    def save(self, arguments, names=("Auto-Save", "Quick-Save"), on_stack=True):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, names, onStack)
            gameSaves = {files = {}}
            for name in python.iter(names) do
                -- As in the stock list: slotName is the save's name, sName the party leader's.
                gameSaves.files[#gameSaves.files + 1] = {slotName = name, sName = "CBRTS Subject",
                    fileName = "00000000" .. #gameSaves.files .. "-" .. name}
            end
            currentSave = nil
            Infinity_IsMenuOnStack = function(menu) return onStack and menu == "LOAD" and 1 or 0 end
            local ok, result = pcall(assert(loadstring(code, "@save.lua")))
            if not ok then return false, tostring(result), currentSave end
            return true, #result.saves, currentSave
        end""")
        code = lab_rc.with_arguments((REQUESTS / "save.lua").read_text(encoding="utf-8"), arguments)
        return attempt(code, list(names), on_stack)

    def test_select_sets_the_lists_own_variable(self):
        self.assertEqual(self.save({"op": "list"}), (True, 2, None))
        self.assertEqual(self.save({"op": "select", "prefix": "Quick"}), (True, 2, 2))
        # Rotated quick saves: only the exact folder name tells them apart.
        names = ("Quick-Save", "Auto-Save", "Quick-Save-2")
        self.assertIn("SAVE_MATCHES:2", self.save({"op": "select", "prefix": "Quick"}, names=names)[1])
        self.assertEqual(self.save({"op": "select", "file": "000000002-Quick-Save-2"}, names=names), (True, 3, 3))
        self.assertEqual(self.save({"op": "select", "file": "000000000-Quick-Save"}, names=names), (True, 3, 1))

    def test_select_refuses_no_or_several_matches(self):
        for names, guard in ((("Auto-Save",), "SAVE_MATCHES:0"), (("Quick-Save", "Quick-Save"), "SAVE_MATCHES:2")):
            with self.subTest(names=names):
                ok, error, current = self.save({"op": "select", "prefix": "Quick"}, names=names)
                self.assertEqual((ok, current), (False, None))
                self.assertIn(guard, error)
        self.assertIn("EXPECTED_MENU:LOAD", self.save({"op": "list"}, on_stack=False)[1])
        self.assertIn("ARGS.file or ARGS.prefix required", self.save({"op": "select"})[1])
        both = {"op": "select", "prefix": "Quick", "file": "000000001-Quick-Save"}
        self.assertIn("ARGS.file or ARGS.prefix required", self.save(both)[1])
        self.assertIn("SAVE_MATCHES:0", self.save({"op": "select", "file": "000000001-Quick"})[1])


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class FixRequestTests(unittest.TestCase):
    """fix.lua against a stub CBRTF: which operation it forwards, and what it refuses."""

    def fix(self, arguments, paused=1, loaded=True, subject="CBRTS Subject"):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, loaded, subject)
            local calls = {}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0}}}
            if loaded then
                CBRTF = {}
                for _, op in ipairs({"Install", "Status", "Disable", "Select", "Verify"}) do
                    CBRTF[op] = function(...) calls[#calls + 1] = op; return {op = op, args = {...}} end
                end
            end
            EEex_Sprite_GetInPortrait = function(slot)
                if slot == 0 and subject then return {_name = subject} end
            end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
            local ok, result = pcall(assert(loadstring(code, "@fix.lua")))
            if not ok then return false, tostring(result), #calls end
            return true, result.op, #calls, result.args[1]
        end""")
        code = lab_rc.with_arguments((REQUESTS / "fix.lua").read_text(encoding="utf-8"), arguments)
        return attempt(code, paused, loaded, subject)

    def test_operations_forward_to_the_module(self):
        for op, called in (("install", "Install"), ("status", "Status"), ("disable", "Disable")):
            with self.subTest(op=op):
                self.assertEqual(self.fix({"op": op}, paused=0)[:3], (True, called, 1))
        for op, called in (("select", "Select"), ("verify", "Verify")):
            with self.subTest(op=op):
                self.assertEqual(self.fix({"op": op, "subject": "CBRTS Subject"}), (True, called, 1, 0))

    def test_refusals_call_nothing(self):
        for op in ("select", "verify"):
            cases = {"FIX_NOT_LOADED": ({"op": "status"}, {"loaded": False}),
                     "UNKNOWN_OP": ({"op": "enable"}, {}),
                     "ARGS.subject required": ({"op": op}, {}),
                     "PAUSE_FIRST": ({"op": op, "subject": "CBRTS Subject"}, {"paused": 0}),
                     "NO_SUBJECT": ({"op": op, "subject": "CBRTS Subject"}, {"subject": None}),
                     "NOT_THE_SUBJECT": ({"op": op, "subject": "CBRTS Subject"}, {"subject": "Imoen"})}
            for guard, (arguments, state) in cases.items():
                with self.subTest(op=op, guard=guard):
                    ok, error, count = self.fix(arguments, **state)[:3]
                    self.assertEqual((ok, count), (False, 0))
                    self.assertIn(guard, error)


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class CorRequestTests(unittest.TestCase):
    """cor.lua against a stub CBRTC: which operation it forwards with what, and what it refuses."""

    def cor(self, arguments, paused=1, loaded=True, party=(10, 11), objects=(10, 11, 77)):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, loaded, party, objects)
            local calls = {}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0}}}
            if loaded then
                CBRTC = {}
                for _, op in ipairs({"Install", "Status", "Disable", "Enable", "Observe", "Watch", "Record",
                                     "ExportRecord"}) do
                    CBRTC[op] = function(...) calls[#calls + 1] = op; return {op = op, args = {...}} end
                end
            end
            local members, known, slot = {}, {}, 0
            for id in python.iter(party) do
                members[slot] = {m_id = id}
                slot = slot + 1
            end
            for id in python.iter(objects) do known[id] = {m_id = id, isSprite = function() return true end} end
            EEex_Sprite_GetInPortrait = function(slot) return members[slot] end
            EEex_GameObject_Get = function(id) return known[id] end
            local ok, result = pcall(assert(loadstring(code, "@cor.lua")))
            if not ok then return false, tostring(result), #calls end
            local args = result.args
            if result.op == "Watch" then args = {table.concat(args[1], " ")} end
            return true, result.op, #calls, args[1], args[2]
        end""")
        code = lab_rc.with_arguments((REQUESTS / "cor.lua").read_text(encoding="utf-8"), arguments)
        return attempt(code, paused, loaded, list(party), list(objects))

    def test_operations_forward_to_the_module(self):
        for op, called in (("install", "Install"), ("status", "Status"), ("disable", "Disable")):
            with self.subTest(op=op):
                self.assertEqual(self.cor({"op": op}, paused=0)[:3], (True, called, 1))
        self.assertEqual(self.cor({"op": "record", "on": "1"}, paused=0), (True, "Record", 1, True, False))
        self.assertEqual(self.cor({"op": "record", "on": "1", "discard": "1"}), (True, "Record", 1, True, True))
        self.assertEqual(self.cor({"op": "record", "on": "0"}), (True, "Record", 1, False, False))
        self.assertEqual(self.cor({"op": "enable"}), (True, "Enable", 1, 0, None))
        self.assertEqual(self.cor({"op": "observe"})[:3], (True, "Observe", 1))
        self.assertEqual(self.cor({"op": "export", "name": "cor_01"})[:4], (True, "ExportRecord", 1, "cor_01"))

    def test_watch_follows_the_party_and_the_named_creatures(self):
        self.assertEqual(self.cor({"op": "watch", "ids": " 77 "})[:4], (True, "Watch", 1, "10 11 77"))
        self.assertEqual(self.cor({"op": "watch"})[:4], (True, "Watch", 1, "10 11"))

    def test_refusals_call_nothing(self):
        cases = {"COR_NOT_LOADED": ({"op": "status"}, {"loaded": False}),
                 "UNKNOWN_OP": ({"op": "verify"}, {}),
                 "ARGS.on required": ({"op": "record", "on": "yes"}, {}),
                 "PAUSE_FIRST": ({"op": "enable"}, {"paused": 0}),
                 "ARGS.name required": ({"op": "export"}, {}),
                 "INVALID_ID": ({"op": "watch", "ids": "77 x"}, {}),
                 "NOT_A_CREATURE": ({"op": "watch", "ids": "78"}, {})}
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.cor(arguments, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
        for op in ("observe", "watch", "export"):
            with self.subTest(op=op):
                ok, error, count = self.cor({"op": op, "name": "x"}, paused=0)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("PAUSE_FIRST", error)


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class ApplyRequestTests(unittest.TestCase):
    """apply.lua against stub bindings: the response it queues on which actor, and its refusals."""

    GAME = 0x5000

    def apply(self, actor, steps, paused=1, stop=0, action=0, objects=(10, 11, 77)):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, stop, game, action, objects)
            local queued, stored = {}, {}
            local known = {}
            for id in python.iter(objects) do
                known[id] = {m_id = id, _name = "C" .. id, m_curAction = {m_actionID = action},
                    isSprite = function() return true end,
                    setStoredScriptingTarget = function(self, key, target) stored[#stored + 1] = key .. "=" .. target.m_id end}
            end
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = game, m_worldTime = {m_gameTime = 1000}}}}
            EEex_UDToPtr = function(value) return value._ptr end
            EEex_Read32 = function(address)
                assert(address == game + 0x9690, "unexpected read")
                return stop
            end
            EEex_GameObject_Get = function(id) return known[id] end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
            EEex_Action_QueueResponseStringOnAIBase = function(response, target)
                queued[#queued + 1] = target._name .. ": " .. response
            end
            local ok, result = pcall(assert(loadstring(code, "@apply.lua")))
            if not ok then return false, tostring(result), #queued, table.concat(stored, " ") end
            return true, queued[1], #queued, table.concat(stored, " ")
        end""")
        code = lab_rc.with_arguments((REQUESTS / "apply.lua").read_text(encoding="utf-8"),
                                     {"actor": actor, "steps": steps})
        return attempt(code, paused, stop, self.GAME, action, list(objects))

    def test_steps_queue_waits_and_applications_on_the_actor(self):
        self.assertEqual(self.apply("77", "0:CBRTREG:self; 3:CBRTPSN:self"),
                         (True, 'C77: ApplySpellRES("CBRTREG",Myself)\nSmallWait(3)\nApplySpellRES("CBRTPSN",Myself)',
                          1, ""))
        self.assertEqual(self.apply("11", "5:CBRTSTP:self;40:CBRTREG:10"),
                         (True, 'C11: SmallWait(5)\nApplySpellRES("CBRTSTP",Myself)\nSmallWait(40)\n'
                                'ApplySpellRES("CBRTREG",EEex_Target("CBRTT10"))', 1, "CBRTT10=10"))

    def test_refusals_queue_nothing(self):
        cases = {"PAUSE_FIRST": (("77", "0:CBRTREG:self"), {"paused": 0}),
                 "TIME_STOP_ACTIVE": (("77", "0:CBRTREG:self"), {"stop": 90}),
                 "NOT_A_CREATURE": (("78", "0:CBRTREG:self"), {}),
                 "ACTOR_BUSY": (("77", "0:CBRTREG:self"), {"action": 3}),
                 "INVALID_STEP": (("77", "301:CBRTREG:self"), {}),
                 "NOT_A_LAB_FIXTURE": (("77", "0:SPWI305:self"), {}),
                 "INVALID_TARGET": (("77", "0:CBRTREG:78"), {}),
                 "TOO_MANY_STEPS": (("77", ";".join(["0:CBRTREG:self"] * 13)), {}),
                 "NO_STEPS": (("77", " ; "), {})}
        for guard, ((actor, steps), state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.apply(actor, steps, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
        for steps in ("0:CBRTREG", "x:CBRTREG:self", "0:cbrtreg:self", "0:CBRTREGXX:self"):
            with self.subTest(steps=steps):
                self.assertFalse(self.apply("77", steps)[0])


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class CloudRequestTests(unittest.TestCase):
    """cloud.lua against a stub CBRTCL and stub bindings: what it forwards or queues, and its refusals."""

    GAME = 0x5000
    # id: x, y, resref; 77 casts, 77 and 10 are sampled.
    CREATURES = {77: (3741, 2801, "OH1FIGHT"), 10: (3720, 2826, "IMOEN10"), 30: (3898, 2676, "JAHEIR7")}

    def cloud(self, arguments, paused=1, loaded=True, on=True, stop=0, action=0, creatures=None):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, loaded, on, stop, game, action, creatures)
            local calls, queued, scans = {}, {}, {}
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = game, m_worldTime = {m_gameTime = 1000}}}}
            if loaded then
                CBRTCL = {on = on, caster = 77, watch = {77, 10}}
                for _, op in ipairs({"Install", "Status", "Stop", "Arm", "Export"}) do
                    CBRTCL[op] = function(...) calls[#calls + 1] = op; return {op = op, args = {...}} end
                end
            end
            local known, all = {}, {}
            for id, x, y, resref in python.iter(creatures) do
                known[id] = {m_id = id, m_pArea = "area", m_pos = {x = x, y = y}, m_curAction = {m_actionID = action},
                    m_resref = {get = function() return resref end}, isSprite = function() return true end}
                all[#all + 1] = known[id]
            end
            EEex_GameObject_Get = function(id) return known[id] end
            EEex_UDToPtr = function(value) return value._ptr end
            EEex_Read32 = function(address)
                assert(address == game + 0x9690, "unexpected read")
                return stop
            end
            EEex_Area_GetAllOfTypeStringInRange = function(area, x, y, filter, range, los, nonSprites)
                scans[#scans + 1] = table.concat({area, x, y, filter, range, los, nonSprites}, " ")
                return all
            end
            EEex_Action_QueueResponseStringOnAIBase = function(response, target)
                queued[#queued + 1] = target.m_id .. ": " .. response
            end
            local ok, result = pcall(assert(loadstring(code, "@cloud.lua")))
            if not ok then return false, tostring(result), #calls + #queued end
            if result.op then
                local args = result.args
                if result.op == "Arm" then args = {args[1], table.concat(args[2], " "), args[3]} end
                return true, result.op, #calls, args[1], args[2], args[3]
            end
            local near = {}
            for _, entry in ipairs(result.near) do
                near[#near + 1] = table.concat({entry.id, entry.distance, tostring(entry.sampled),
                                                tostring(entry.inside)}, ":")
            end
            return true, queued[1], #queued, table.concat(near, " "), scans[1], result.reach
        end""")
        code = lab_rc.with_arguments((REQUESTS / "cloud.lua").read_text(encoding="utf-8"), arguments)
        table = [(ident, *values) for ident, values in (creatures or self.CREATURES).items()]
        return attempt(code, paused, loaded, on, stop, self.GAME, action, table)

    CAST = {"op": "cast", "spell": "SPWI810", "x": "3590", "y": "2845"}

    def test_operations_forward_to_the_module(self):
        for op, called in (("install", "Install"), ("status", "Status"), ("stop", "Stop")):
            with self.subTest(op=op):
                self.assertEqual(self.cloud({"op": op}, paused=0)[:3], (True, called, 1))
        self.assertEqual(self.cloud({"op": "arm", "caster": "77", "ids": " 77 10 "}),
                         (True, "Arm", 1, 77, "77 10", False))
        self.assertEqual(self.cloud({"op": "arm", "caster": "77", "ids": "10", "discard": "1"}),
                         (True, "Arm", 1, 77, "10", True))
        self.assertEqual(self.cloud({"op": "export", "name": "k7_x"})[:4], (True, "Export", 1, "k7_x"))

    def test_cast_queues_the_cloud_on_the_armed_caster(self):
        # Jaheira (30) stands 382 away (vertical offset scaled by 4/3), outside 256 + 64.
        self.assertEqual(self.cloud(self.CAST),
                         (True, '77: ReallyForceSpellPointRES("SPWI810",[3590.2845])', 1,
                          "10:132:true:true 77:162:true:true 30:382:false:false",
                          "area 3590 2845 [ANYONE] 600 0 0", 256))
        self.assertEqual(self.cloud(dict(self.CAST, wait="5"))[1],
                         '77: SmallWait(5)\nReallyForceSpellPointRES("SPWI810",[3590.2845])')

    def test_a_bystander_within_reach_refuses_the_cast(self):
        base = {77: (3590, 2845, "OH1FIGHT"), 10: (3590 + 300, 2845, "IMOEN10")}  # sampled: never refused
        for position, refused in (((3590 + 320, 2845), True), ((3590 + 321, 2845), False),
                                  ((3590, 2845 + 240), True), ((3590, 2845 + 241), False)):
            with self.subTest(position=position):
                ok, result, count = self.cloud(self.CAST, creatures={**base, 40: (*position, "X")})[:3]
                self.assertEqual((ok, count), (not refused, 0 if refused else 1))
                if refused:
                    self.assertIn("BYSTANDER_IN_REACH 40", result)

    def test_refusals_queue_nothing(self):
        cases = {"CLOUD_NOT_LOADED": ({"op": "status"}, {"loaded": False}),
                 "UNKNOWN_OP": ({"op": "enable"}, {}),
                 "ARGS.name required": ({"op": "export"}, {}),
                 "NOT_A_CREATURE": ({"op": "arm", "caster": "78", "ids": "10"}, {}),
                 "NOT_A_CLOUD_SPELL": (dict(self.CAST, spell="SPWI305"), {}),
                 "ARM_FIRST": (self.CAST, {"on": False}),
                 "TIME_STOP_ACTIVE": (self.CAST, {"stop": 90}),
                 "CASTER_BUSY": (self.CAST, {"action": 3}),
                 "INVALID_POINT": (dict(self.CAST, x="3590.5"), {}),
                 "INVALID_WAIT": (dict(self.CAST, wait="301"), {})}
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.cloud(arguments, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
        for arguments in ({"op": "arm", "caster": "77", "ids": "10 78"}, dict(self.CAST, x="-1"),
                          dict(self.CAST, y="40000"), {"op": "cast", "spell": "SPWI810", "x": "1"},
                          dict(self.CAST, wait="x")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.cloud(arguments)[0::2], (False, 0))
        for op in ("arm", "cast", "export"):
            with self.subTest(op=op):
                ok, error, count = self.cloud(dict(self.CAST, op=op, caster="77", name="x"), paused=0)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn("PAUSE_FIRST", error)


class ExitTests(unittest.TestCase):
    """A game that exits can never answer: requests end as "exited", never stay pending."""

    PATHS = ("LAB", "OVERRIDE", "LOG", "PENDING", "COMMAND", "CLAIM", "RESULT", "EXIT_POLL", "processes")
    GAME = {"ProcessId": 1, "Name": "Baldur.exe", "ExecutablePath": "lab", "ours": True}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "override").mkdir()
        (root / "CBRTSLab.id").write_bytes(b"CBR TimeStop Lab 2730\n")
        self.saved = {name: getattr(lab_rc, name) for name in self.PATHS}
        lab_rc.LAB, lab_rc.OVERRIDE = root, root / "override"
        lab_rc.LOG = root / "cbr-timestop-output" / "rc-log"
        lab_rc.PENDING = lab_rc.LOG / "pending.json"
        lab_rc.COMMAND = lab_rc.OVERRIDE / "eeex_remote_cmd.lua"
        lab_rc.CLAIM = lab_rc.OVERRIDE / "eeex_remote_cmd.lua.run"
        lab_rc.RESULT = lab_rc.OVERRIDE / "eeex_remote_result.json"
        lab_rc.EXIT_POLL = 0.05
        self.calls = 0

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(lab_rc, name, value)
        self.temp.cleanup()

    def game(self, after_send):
        """Fake process list: running for the send check, then `after_send` decides."""
        def processes():
            self.calls += 1
            return [dict(self.GAME)] if self.calls == 1 else after_send()
        lab_rc.processes = processes

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = lab_rc.main(argv)
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None)

    def claim_and_exit(self):
        lab_rc.COMMAND.unlink(missing_ok=True)
        return []

    def test_quit_request_ends_as_exited_without_pending(self):
        self.game(self.claim_and_exit)
        code, result = self.run_main(["lua", "quit", "return 1", "--expect-exit", "--timeout", "5"])
        self.assertEqual(code, 0)
        self.assertEqual(result["response"]["status"], "exited")
        self.assertTrue(result["response"]["claimed"])
        self.assertFalse(lab_rc.PENDING.exists())
        self.assertEqual(list(lab_rc.OVERRIDE.iterdir()), [])

    def test_unclaimed_request_leaves_override_after_exit(self):
        self.game(lambda: [])
        code, result = self.run_main(["lua", "quit", "return 1", "--expect-exit", "--timeout", "5"])
        self.assertEqual(code, 0)
        self.assertFalse(result["response"]["claimed"])
        self.assertFalse(lab_rc.COMMAND.exists())
        moved = [Path(path) for path in result["response"]["retired"]]
        self.assertEqual(len(moved), 1)
        self.assertTrue(moved[0].name.endswith("-quit.unclaimed.lua"))
        self.assertIn("return 1", moved[0].read_text(encoding="utf-8"))

    def test_answer_before_exit_is_an_ordinary_result(self):
        def answer():
            if lab_rc.COMMAND.exists():
                request = lab_rc.COMMAND.read_text(encoding="utf-8").split("\n", 1)[0].removeprefix("--@id=")
                lab_rc.COMMAND.unlink()
                lab_rc.RESULT.write_text(json.dumps({"id": request, "status": "error", "error": "STOP_FIRST"}),
                                         encoding="utf-8")
            return [dict(self.GAME)]
        self.game(answer)
        code, result = self.run_main(["lua", "quit", "return 1", "--expect-exit", "--timeout", "5"])
        self.assertEqual(code, 1)
        self.assertEqual(result["response"]["error"], "STOP_FIRST")

    def test_without_expect_exit_a_silent_request_stays_pending(self):
        self.game(lambda: [dict(self.GAME)])
        code, result = self.run_main(["lua", "slow", "return 1", "--timeout", "0.3"])
        self.assertEqual((code, result["response"]["status"]), (1, "timeout"))
        self.assertTrue(lab_rc.PENDING.exists())

    def test_collect_resolves_a_request_of_an_exited_game(self):
        lab_rc.LOG.mkdir(parents=True)
        lab_rc.PENDING.write_text(json.dumps({"id": "abc", "label": "quit"}), encoding="utf-8")
        lab_rc.CLAIM.write_text("--@id=abc\nreturn 1\n", encoding="utf-8")
        lab_rc.processes = lambda: []
        code, result = self.run_main(["collect", "quit-collect", "--timeout", "5"])
        self.assertEqual((code, result["response"]["status"]), (1, "exited"))
        self.assertFalse(lab_rc.PENDING.exists())
        self.assertFalse(lab_rc.CLAIM.exists())
        self.assertTrue(result["response"]["retired"][0].endswith("-quit-collect.claimed.lua"))

    def test_foreign_request_file_is_never_moved(self):
        lab_rc.LOG.mkdir(parents=True)
        lab_rc.PENDING.write_text(json.dumps({"id": "abc", "label": "quit"}), encoding="utf-8")
        lab_rc.COMMAND.write_text("--@id=other\nreturn 1\n", encoding="utf-8")
        lab_rc.processes = lambda: []
        with contextlib.redirect_stderr(io.StringIO()):
            code, _ = self.run_main(["collect", "quit-collect", "--timeout", "5"])
        self.assertEqual(code, 2)
        self.assertTrue(lab_rc.COMMAND.exists())
        self.assertTrue(lab_rc.PENDING.exists())


if __name__ == "__main__":
    unittest.main()
