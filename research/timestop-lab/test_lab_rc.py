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
                             "queue.lua": ("PAUSE_FIRST", "NOT_THE_SUBJECT", "ARM_FIRST", "DISARMED_ONLY"),
                             "pause.lua": ("NO_GAME", "PAUSE_STATE_UNCHANGED"),
                             "dialog.lua": ("CONFIRM_MODE_REQUIRED", "DIALOG_BUTTON_NOT_CLICKABLE"),
                             "pick-character.lua": ("AMBIGUOUS_CHARACTER", "CHARACTER_NOT_FOUND"),
                             "quit.lua": ("STOP_FIRST",)}.items():
            text = (REQUESTS / name).read_text(encoding="utf-8")
            for guard in guards:
                self.assertIn(guard, text, f"{name} lacks {guard}")


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
