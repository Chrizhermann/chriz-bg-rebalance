"""Real-compiler tests for actor/difficulty transitions, independent of the kill."""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_dragon_wing_buffet import (
    CAPTURE_AVAILABLE, CAPTURE_REQUIRED, ORIGINALS, ROOT, WEIDU, blocks, write_ids,
)

LIB = ROOT / "chriz-bg-rebalance/lib/dragon_vorpal.tpa"
HARNESS = ROOT / "tests/weidu/dragon_vorpal_scripts_harness.tp2"


def trigger_records(block: bytes) -> list[tuple[int, int, bool, str]]:
    # Read actual compiled trigger records; no textual BAF matching. This lets
    # the behavior grid detect wrong opcodes, OR grouping, negation and scope.
    records = re.findall(
        rb'TR\n(\d+) (-?\d+) (\d+) -?\d+ -?\d+ "([^"]*)" "[^"]*" OB\n'
        rb'[^\n]*\nTR\n', block.split(b"CO\nRS\n", 1)[0]
    )
    return [(int(op), int(value), bool(int(negate)), name.decode())
            for op, value, negate, name in records]


def matches(block: bytes, *, actor: str, active: int, category: int, game: int) -> bool:
    terms: list[bool] = []
    remaining = 0
    group: list[bool] = []
    for opcode, value, negate, name in trigger_records(block):
        if opcode == 0x4089:
            assert remaining == 0, "nested OR unexpectedly generated"
            remaining = value
            group = []
            continue
        if opcode == 0x40A5:
            condition = actor.casefold() == name.casefold()
        elif opcode == 0x400F:
            assert name == "LOCALSCBR_DV_ACTIVE", name
            condition = active == value
        elif opcode == 0x40ED:
            assert name == "DMWW_dragon_difficulty", name
            condition = category == value
        elif opcode == 0x40D1:
            condition = game > value
        elif opcode == 0x40D2:
            condition = game < value
        else:
            raise AssertionError(f"Unexpected trigger {opcode:#x}: {name}")
        condition = not condition if negate else condition
        if remaining:
            group.append(condition)
            remaining -= 1
            if not remaining:
                terms.append(any(group))
        else:
            terms.append(condition)
    assert not remaining and terms
    return all(terms)


@unittest.skipUnless(WEIDU.exists(), "WeiDU executable not available")
@unittest.skipUnless(CAPTURE_AVAILABLE, CAPTURE_REQUIRED)
class DragonVorpalScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cbr-vorpal-scripts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ids = self.root / "ids"
        self.ids.mkdir()
        write_ids(self.ids)
        self.source = self.root / "source.bcs"
        self.source.write_bytes((ORIGINALS / "dragred.bcs.orig").read_bytes())
        self.out = self.root / "out.bcs"
        self.counter = 0

    def run_patch(self, expected_success: bool = True) -> bytes:
        self.counter += 1
        run = self.root / f"run-{self.counter}"
        run.mkdir()
        process = subprocess.run([
            str(WEIDU), str(HARNESS), "--nogame", "--search-ids", str(self.ids),
            "--force-install-list", "1", "--args", str(LIB),
            "--args", str(self.source), "--args", str(self.out),
            "--no-exit-pause", "--quick-log",
        ], cwd=run, text=True, capture_output=True, timeout=60, check=False)
        transcript = process.stdout + process.stderr
        if expected_success:
            self.assertEqual(process.returncode, 0, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            return self.out.read_bytes()
        self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
        return b""

    def test_original_script_bytes_and_all_existing_actions_survive(self) -> None:
        old = self.source.read_bytes()
        result = self.run_patch()
        new_blocks = blocks(result)
        self.assertEqual(new_blocks[4:], blocks(old))
        self.assertEqual(len(new_blocks), len(blocks(old)) + 4)
        self.assertEqual(result.count(b'"CBRDV15"'), 2)
        self.assertEqual(result.count(b'"CBRDVREM"'), 2)
        # Each transition spends no AI round; it must continue to existing SCS.
        for block in new_blocks[:4]:
            self.assertEqual(block.count(b"\n36OB\n"), 1)

    def test_category_slider_identity_and_removal_behavior_grid(self) -> None:
        prefix = blocks(self.run_patch())[:4]
        for actor in ("firkra02", "FIRKRA02", "dragred", "dw#abred", "GorSal"):
            for category in range(-1, 10):
                for game in range(0, 7):
                    for active in (0, 1):
                        with self.subTest(actor=actor, category=category, game=game, active=active):
                            selected = [i for i, block in enumerate(prefix) if matches(
                                block, actor=actor, active=active, category=category, game=game
                            )]
                            enabled = category in (5, 6, 7) or (category == 0 and game in (4, 5))
                            should_change = actor.casefold() == "firkra02" and enabled != bool(active)
                            self.assertEqual(len(selected), int(should_change))
                            if selected:
                                self.assertEqual(selected[0] < 2, enabled)

    def test_repeated_application_is_byte_identical(self) -> None:
        once = self.run_patch()
        self.source.write_bytes(once)
        self.assertEqual(self.run_patch(), once)

    def test_foreign_or_duplicate_prefix_is_rejected(self) -> None:
        once = self.run_patch()
        for bad in (once.replace(b'"CBRDV15"', b'"FOREIGN1"'),
                    b"SC\n" + blocks(once)[0] + once[3:]):
            self.source.write_bytes(bad)
            before = self.out.read_bytes()
            self.run_patch(False)
            self.assertEqual(self.out.read_bytes(), before)

    def test_invalid_script_is_rejected(self) -> None:
        self.source.write_bytes(b"not a compiled script")
        self.run_patch(False)
        self.assertFalse(self.out.exists())

    def test_non_ini_scs_difficulty_family_is_rejected(self) -> None:
        # Old/alternate SCS builds use GLOBAL; the component must not silently
        # ignore their category selector and follow the game slider instead.
        original = self.source.read_bytes()
        self.source.write_bytes(original.replace(b"16621 ", b"16399 "))
        self.run_patch(False)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
