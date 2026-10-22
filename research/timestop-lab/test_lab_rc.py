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
                                           "HASTE_PRESENT", "FIXTURES_MIXED"),
                             "pause.lua": ("NO_GAME", "PAUSE_STATE_UNCHANGED"),
                             "dialog.lua": ("CONFIRM_MODE_REQUIRED", "DIALOG_BUTTON_NOT_CLICKABLE"),
                             "pick-character.lua": ("AMBIGUOUS_CHARACTER", "CHARACTER_NOT_FOUND"),
                             "fix.lua": ("FIX_NOT_LOADED", "UNKNOWN_OP", "PAUSE_FIRST", "NO_SUBJECT",
                                         "NOT_THE_SUBJECT"),
                             "quit.lua": ("STOP_FIRST",)}.items():
            text = (REQUESTS / name).read_text(encoding="utf-8")
            for guard in guards:
                self.assertIn(guard, text, f"{name} lacks {guard}")


@unittest.skipIf(lupa is None, "lupa with LuaJIT 2.1 is not installed")
class QueueRequestTests(unittest.TestCase):
    """queue.lua against stub bindings: what it queues on whom, and what it refuses."""

    GAME = 0x5000  # Stub CInfGame pointer; +0x9690 is the Time Stop counter.

    def queue(self, arguments, paused=1, armed=True, fixtures=("CBRTBUF", "CBRTREG"),
              controller=("Imoen", 2), stop=0, action=0):
        runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
        attempt = runtime.eval("""function(code, paused, armed, sources, controllerName, controllerID,
                stop, game, action)
            local queued = {}
            local function actor(id, name, list)
                return {m_id = id, _name = name, m_timedEffectList = list or {},
                    m_baseStats = {m_hitPoints = 80}, m_curAction = {m_actionID = action}}
            end
            local list = {}
            for source in python.iter(sources) do
                list[#list + 1] = {m_sourceRes = {get = function() return source end}}
            end
            local actors = {[0] = actor(10, "CBRTS Subject", list)}
            if controllerName then actors[1] = actor(controllerID, controllerName) end
            EngineGlobals = {g_pBaldurChitin = {m_pEngineWorld = {m_bPaused = paused, m_bHardPaused = 0},
                m_pObjectGame = {_ptr = game, m_worldTime = {m_gameTime = 1000}}}}
            CBRTS = {Status = function() return {armed = armed} end}
            EEex_Sprite_GetInPortrait = function(slot) return actors[slot] end
            EEex_Sprite_GetName = function(sprite) return sprite._name end
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
            if not ok then return false, tostring(result), #queued end
            return true, result.queued, #queued, queued[1].target
        end""")
        code = lab_rc.with_arguments((REQUESTS / "queue.lua").read_text(encoding="utf-8"),
                                     {"subject": "CBRTS Subject", **arguments})
        name, identity = controller if controller else (None, None)
        return attempt(code, paused, armed, list(fixtures), name, identity, stop, self.GAME, action)

    def test_timestop_runs_on_the_controller_after_its_wait(self):
        ok, response, count, target = self.queue({"what": "timestop", "controller": "Imoen", "wait": "66"})
        self.assertTrue(ok, response)
        self.assertEqual((response, count, target), ('SmallWait(66)\nApplySpellRES("CBRTSTP",Myself)', 1, "Imoen"))
        ok, response, _, _ = self.queue({"what": "timestop", "controller": "Imoen", "wait": "0"})
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTSTP",Myself)'))

    def test_timestop_refuses_without_its_case(self):
        base = {"what": "timestop", "controller": "Imoen", "wait": "66"}
        cases = {
            "PAUSE_FIRST": ({}, {"paused": 0}),
            "ARM_FIRST": ({}, {"armed": False}),
            "NO_CONTROLLER": ({}, {"controller": None}),
            "NOT_THE_CONTROLLER": ({"controller": "Jaheira"}, {}),
            "CONTROLLER_BUSY": ({}, {"action": 23}),
            "FIXTURES_FIRST": ({}, {"fixtures": ("CBRTREG",)}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90}),
        }
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.queue({**base, **arguments}, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
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

    def test_haste_runs_on_the_subject_after_its_wait(self):
        for spell in ("CBRTHST", "CBRTIHS"):
            with self.subTest(spell=spell):
                ok, response, count, target = self.queue({"what": "haste", "spell": spell, "wait": "74"})
                self.assertTrue(ok, response)
                self.assertEqual((response, count, target),
                                 (f'SmallWait(74)\nApplySpellRES("{spell}",Myself)', 1, "CBRTS Subject"))
        ok, response, _, _ = self.queue({"what": "haste", "spell": "CBRTHST", "wait": "0"}, fixtures=())
        self.assertEqual((ok, response), (True, 'ApplySpellRES("CBRTHST",Myself)'))

    def test_haste_refuses_without_a_clean_case(self):
        base = {"what": "haste", "spell": "CBRTHST", "wait": "74"}
        cases = {
            "ARM_FIRST": ({}, {"armed": False}),
            "UNKNOWN_SPELL": ({"spell": "CBRTSTP"}, {}),
            "SUBJECT_BUSY": ({}, {"action": 23}),
            "HASTE_PRESENT": ({}, {"fixtures": ("CBRTBUF", "CBRTREG", "CBRTIHS")}),
            "FIXTURES_MIXED": ({}, {"fixtures": ("CBRTREG",)}),
            "TIME_STOP_ACTIVE": ({}, {"stop": 90}),
            "INVALID_WAIT": ({"wait": "301"}, {}),
        }
        for guard, (arguments, state) in cases.items():
            with self.subTest(guard=guard):
                ok, error, count = self.queue({**base, **arguments}, **state)[:3]
                self.assertEqual((ok, count), (False, 0))
                self.assertIn(guard, error)
        with self.subTest(guard="FIXTURES_MIXED", case="two of each"):
            ok, error, count = self.queue(base, fixtures=("CBRTBUF", "CBRTREG") * 2)[:3]
            self.assertEqual((ok, count), (False, 0))
            self.assertIn("FIXTURES_MIXED", error)

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
