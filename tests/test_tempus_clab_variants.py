"""Variation tests for the Holy Power five-use CLAB cap (components 401-403).

The cap owns only GA_OHTMPS1 cells (case-insensitive). It keeps the first five
uses ordered by (level, row order) and replaces every later one with ****,
byte-surgically. Row names, table width, level-25 symbols, Artisan's packed
AP_C0PR#CL grants, and other mods' cells are neither required nor touched.

Three layers are exercised:
  * a focused --nogame harness (tests/weidu/tempus_clab_harness.tp2) calling
    the production classification/cap/post-validation sequence directly;
  * the full Holy Power progression harness with a variant CLAB; and
  * the public setup-chriz-bg-rebalance.tp2 component 401 on a synthetic game
    (install, byte-exact uninstall, and atomic rollback on failure).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import read_2da
from tests.test_tempus_holy_power import (
    HARNESS as HOLY_HARNESS,
    LATE_HOLY_POWER_LEVELS,
    ORIGINALS,
    PHASE_COMPONENT,
    PRODUCTION_TPA,
    ROOT,
    WEIDU,
    _clear_clab_holy_power_grants,
    _pack_clab_ability1_with_artisan_permissions,
    _raw_file_tree,
    build_fixture,
)
from tests.test_tempus_holy_power_installer import SyntheticGame

CLAB_HARNESS = ROOT / "tests" / "weidu" / "tempus_clab_harness.tp2"
CLAB_NAME = "OHTEMPUS.2DA"
TOKEN = b"GA_OHTMPS1"


# ---------------------------------------------------------------------------
# Table builders and an independent oracle
# ---------------------------------------------------------------------------


def make_clab(
    levels: int,
    rows: list[tuple[str, dict[int, str]]],
    *,
    newline: str = "\r\n",
    separator: str = "  ",
    trailing_newline: bool = True,
) -> bytes:
    """Build a CLAB with `levels` level columns; unspecified cells are ****."""
    lines = ["2DA V1.0", "****", separator.join(str(level) for level in range(1, levels + 1))]
    for name, cells in rows:
        values = [cells.get(level, "****") for level in range(1, levels + 1)]
        lines.append(name + separator + separator.join(values))
    text = newline.join(lines) + (newline if trailing_newline else "")
    return text.encode("ascii")


def _grant_cells(raw: bytes) -> list[tuple[int, int, int, int]]:
    """(level, row, start, end) of every GA_OHTMPS1 data cell, in file order."""
    cells = []
    line_index = 0
    for match in re.finditer(rb"[^\r\n]+", raw):
        tokens = list(re.finditer(rb"[^ \t]+", match.group()))
        if not tokens:
            continue
        if line_index >= 3:
            for column, token in enumerate(tokens[1:], start=1):
                if token.group().upper() == TOKEN:
                    cells.append(
                        (column, line_index - 3, match.start() + token.start(), match.start() + token.end())
                    )
        line_index += 1
    return cells


def expected_cap(raw: bytes) -> bytes:
    """Oracle: keep the first five uses by (level, row); clear the rest."""
    cells = _grant_cells(raw)
    ranked = sorted(cells, key=lambda cell: (cell[0], cell[1]))
    cleared = sorted(ranked[5:], key=lambda cell: cell[2], reverse=True)
    out = bytearray(raw)
    for _level, _row, start, end in cleared:
        out[start:end] = b"****"
    return bytes(out)


ARTISAN_FILL = {level: "AP_C0PR#CL" for level in range(1, 51)}


# ---------------------------------------------------------------------------
# Focused harness
# ---------------------------------------------------------------------------


class ClabRun:
    def __init__(self, fixture_dir: Path):
        self.temporary = tempfile.TemporaryDirectory(prefix="cbr-clab-")
        base = Path(self.temporary.name)
        self.fixture = fixture_dir
        self.output = base / "output"
        run_dir = base / "weidu-run"
        run_dir.mkdir()
        self.process = subprocess.run(
            [
                str(WEIDU), str(CLAB_HARNESS), "--nogame",
                "--force-install-list", "0",
                "--args", str(PRODUCTION_TPA),
                "--args", str(fixture_dir),
                "--args", str(self.output),
                "--no-exit-pause", "--quick-log",
            ],
            cwd=run_dir, capture_output=True, text=True, timeout=60, check=False,
        )

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}"

    @property
    def succeeded(self) -> bool:
        return (self.output / "CBR_TEST.OK").exists() and "SUCCESSFULLY INSTALLED" in self.transcript

    def preflight(self) -> tuple[int, int]:
        match = re.search(r"CBR_CLAB_PREFLIGHT capped_shape=(\d+) grants=(\d+)", self.transcript)
        if match is None:
            raise AssertionError(f"no preflight line:\n{self.transcript}")
        return int(match.group(1)), int(match.group(2))

    def cleanup(self) -> None:
        self.temporary.cleanup()


class ClabCapVariantTests(unittest.TestCase):
    def run_clab(self, raw: bytes, *, expect_success: bool = True) -> ClabRun:
        holder = tempfile.TemporaryDirectory(prefix="cbr-clab-fixture-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        fixture.mkdir()
        (fixture / CLAB_NAME).write_bytes(raw)
        run = ClabRun(fixture)
        self.addCleanup(run.cleanup)
        if expect_success:
            self.assertTrue(run.succeeded, run.transcript)
        else:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", run.transcript)
            self.assertFalse((run.output / "CBR_TEST.OK").exists())
        return run

    def assert_capped(self, raw: bytes, *, preflight: tuple[int, int]) -> bytes:
        """Run, compare to the oracle, check preflight and idempotence."""
        run = self.run_clab(raw)
        self.assertEqual(preflight, run.preflight())
        after = (run.output / CLAB_NAME).read_bytes()
        self.assertEqual(expected_cap(raw), after)
        self.assertLessEqual(len(_grant_cells(after)), 5)
        second = ClabRun(run.output)
        self.addCleanup(second.cleanup)
        self.assertTrue(second.succeeded, second.transcript)
        self.assertEqual((1, min(preflight[1], 5)), second.preflight())
        self.assertEqual(after, (second.output / CLAB_NAME).read_bytes(), "cap is not idempotent")
        return after

    # -- captured fixtures ---------------------------------------------------

    def test_captured_original_caps_exactly_the_five_late_grants(self) -> None:
        raw = (ORIGINALS / "OHTEMPUS.2da.orig").read_bytes()
        after = self.assert_capped(raw, preflight=(0, 10))
        self.assertEqual(_clear_clab_holy_power_grants(raw, LATE_HOLY_POWER_LEVELS), after)

    def test_base_game_and_non_sr_captures(self) -> None:
        for capture in ("tempus-base-game", "tempus-no-sr"):
            with self.subTest(capture=capture):
                raw = (ORIGINALS / capture / CLAB_NAME).read_bytes()
                after = self.assert_capped(raw, preflight=(0, 10))
                self.assertEqual(_clear_clab_holy_power_grants(raw, LATE_HOLY_POWER_LEVELS), after)

    def test_artisan_packed_fixture_stays_exact(self) -> None:
        raw = _pack_clab_ability1_with_artisan_permissions(
            (ORIGINALS / "OHTEMPUS.2da.orig").read_bytes()
        )
        after = self.assert_capped(raw, preflight=(0, 10))
        self.assertEqual(_clear_clab_holy_power_grants(raw, LATE_HOLY_POWER_LEVELS), after)
        table = read_2da_bytes(after)
        for level in (2, 5, 7, 24, 27, 50):
            self.assertEqual("AP_C0PR#CL", table.cell("ABILITY1", str(level)))
        self.assertEqual("AP_CDHLYSYM", table.cell("ABILITY1", "25"))

    # -- row placement and order ---------------------------------------------

    def test_grants_in_other_rows_are_ordered_by_level_then_row(self) -> None:
        raw = make_clab(
            50,
            [
                ("ABILITY1", ARTISAN_FILL),
                ("ABILITY2", {16: "GA_OHTMPS1", 21: "GA_OHTMPS1", 26: "GA_OHTMPS1", 31: "GA_OHTMPS1"}),
                ("ABILITY3", {1: "GA_OHTMPS1", 6: "GA_OHTMPS1", 11: "GA_OHTMPS1", 25: "AP_CDHLYSYM"}),
                ("ABILITY4", {}),
                ("ABILITY5", {36: "GA_OHTMPS1"}),
            ],
        )
        after = self.assert_capped(raw, preflight=(0, 8))
        table = read_2da_bytes(after)
        for row, level in (("ABILITY3", 1), ("ABILITY3", 6), ("ABILITY3", 11), ("ABILITY2", 16), ("ABILITY2", 21)):
            self.assertEqual("GA_OHTMPS1", table.cell(row, str(level)))
        for row, level in (("ABILITY2", 26), ("ABILITY2", 31), ("ABILITY5", 36)):
            self.assertEqual("****", table.cell(row, str(level)))
        self.assertEqual("AP_CDHLYSYM", table.cell("ABILITY3", "25"))
        for level in range(1, 51):
            self.assertEqual("AP_C0PR#CL", table.cell("ABILITY1", str(level)))

    def test_same_level_uses_in_several_rows_follow_row_order(self) -> None:
        raw = make_clab(
            10,
            [
                ("ABILITY1", {1: "GA_OHTMPS1", 5: "GA_OHTMPS1"}),
                ("ABILITY2", {3: "GA_OHTMPS1", 5: "GA_OHTMPS1"}),
                ("ABILITY3", {1: "GA_OHTMPS1"}),
                ("ABILITY4", {3: "GA_OHTMPS1"}),
            ],
        )
        after = self.assert_capped(raw, preflight=(0, 6))
        table = read_2da_bytes(after)
        self.assertEqual("GA_OHTMPS1", table.cell("ABILITY1", "5"))
        self.assertEqual("****", table.cell("ABILITY2", "5"), "second level-5 use is the sixth")

    # -- table widths --------------------------------------------------------

    def test_narrower_forty_level_table(self) -> None:
        grants = {level: "GA_OHTMPS1" for level in range(1, 41, 5)}
        raw = make_clab(40, [("ABILITY1", {**grants, 25: "AP_CDHLYSYM"}), ("ABILITY2", {})])
        after = self.assert_capped(raw, preflight=(0, 8))
        table = read_2da_bytes(after)
        self.assertEqual(
            [table.cell("ABILITY1", str(level)) for level in range(1, 41, 5)],
            ["GA_OHTMPS1"] * 5 + ["****"] * 3,
        )

    def test_wider_sixty_level_table(self) -> None:
        grants = {level: "GA_OHTMPS1" for level in range(1, 61, 5)}
        raw = make_clab(60, [("ABILITY1", grants), ("ABILITY2", {60: "GA_FOREIGN"})])
        after = self.assert_capped(raw, preflight=(0, 12))
        table = read_2da_bytes(after)
        self.assertEqual(
            [table.cell("ABILITY1", str(level)) for level in range(1, 61, 5)],
            ["GA_OHTMPS1"] * 5 + ["****"] * 7,
        )
        self.assertEqual("GA_FOREIGN", table.cell("ABILITY2", "60"))

    def test_single_level_column_table(self) -> None:
        # Width 2 (row label + one level): WeiDU's "at least N tokens" row
        # filter would count the signature line as data; the scanner must not.
        raw = make_clab(1, [(f"ABILITY{index}", {1: "GA_OHTMPS1"}) for index in range(1, 8)])
        after = self.assert_capped(raw, preflight=(0, 7))
        self.assertEqual(
            [cell[1] for cell in _grant_cells(after)], [0, 1, 2, 3, 4], "first five rows keep their use"
        )

    # -- unrelated cells and near misses -------------------------------------

    def test_unrelated_cells_and_near_miss_tokens_are_preserved(self) -> None:
        raw = make_clab(
            50,
            [
                ("ABILITY1", {
                    **{level: "GA_OHTMPS1" for level in (1, 6, 11, 16, 21, 26, 31)},
                    25: "AP_CDHLYSYM",
                    2: "GA_OHTMPS10",
                    3: "XGA_OHTMPS1",
                    4: "AP_OHTMPS1",
                }),
                ("ABILITY2", {26: "GA_OTHERMOD", 25: "AP_C0PR#CL"}),
                ("GA_OHTMPS1", {7: "AP_FOREIGN"}),
            ],
        )
        after = self.assert_capped(raw, preflight=(0, 7))
        table = read_2da_bytes(after)
        for level, value in ((2, "GA_OHTMPS10"), (3, "XGA_OHTMPS1"), (4, "AP_OHTMPS1"), (25, "AP_CDHLYSYM")):
            self.assertEqual(value, table.cell("ABILITY1", str(level)))
        self.assertEqual("GA_OTHERMOD", table.cell("ABILITY2", "26"))
        self.assertEqual("AP_FOREIGN", table.cell("GA_OHTMPS1", "7"), "row label is not a cell")
        self.assertEqual(["****", "****"], [table.cell("ABILITY1", "26"), table.cell("ABILITY1", "31")])

    def test_mixed_whitespace_lf_and_missing_final_newline(self) -> None:
        raw = make_clab(
            30,
            [("ABILITY1", {level: "GA_OHTMPS1" for level in (1, 6, 11, 16, 21, 26)})],
            newline="\n",
            separator=" \t ",
            trailing_newline=False,
        )
        self.assert_capped(raw, preflight=(0, 6))

    # -- already capped and counts --------------------------------------------

    def test_already_capped_table_is_byte_identical(self) -> None:
        for count in (5, 3, 1):
            with self.subTest(count=count):
                grants = {level: "GA_OHTMPS1" for level in (1, 6, 11, 16, 21)[:count]}
                raw = make_clab(50, [("ABILITY1", {**grants, 25: "AP_CDHLYSYM"}), ("ABILITY2", {})])
                run = self.run_clab(raw)
                self.assertEqual((1, count), run.preflight())
                self.assertEqual(raw, (run.output / CLAB_NAME).read_bytes())

    def test_seven_grants_are_capped_to_five(self) -> None:
        grants = {level: "GA_OHTMPS1" for level in (2, 5, 9, 14, 20, 27, 35)}
        raw = make_clab(50, [("ABILITY1", grants)])
        after = self.assert_capped(raw, preflight=(0, 7))
        table = read_2da_bytes(after)
        self.assertEqual("****", table.cell("ABILITY1", "27"))
        self.assertEqual("****", table.cell("ABILITY1", "35"))
        self.assertEqual("GA_OHTMPS1", table.cell("ABILITY1", "20"))

    def test_lowercase_tokens_are_owned(self) -> None:
        grants = {1: "ga_ohtmps1", 6: "GA_OHTMPS1", 11: "Ga_OhTmPs1", 16: "GA_OHTMPS1",
                  21: "GA_OHTMPS1", 26: "ga_ohtmps1"}
        raw = make_clab(50, [("ABILITY1", grants)])
        after = self.assert_capped(raw, preflight=(0, 6))
        table = read_2da_bytes(after)
        self.assertEqual("ga_ohtmps1", table.cell("ABILITY1", "1"), "kept use keeps its spelling")
        self.assertEqual("Ga_OhTmPs1", table.cell("ABILITY1", "11"))
        self.assertEqual("****", table.cell("ABILITY1", "26"))

    # -- honest failures -----------------------------------------------------

    def test_zero_grants_fail_with_a_clear_message(self) -> None:
        raw = make_clab(50, [("ABILITY1", {1: "GA_SPCL900", 25: "AP_CDHLYSYM"})])
        run = self.run_clab(raw, expect_success=False)
        self.assertIn("grants no GA_OHTMPS1 use", run.transcript)
        self.assertIn("OHTEMPUS.2DA", run.transcript)

    def test_non_2da_input_fails(self) -> None:
        run = self.run_clab(b"\xff\xff\x00binary payload GA_OHTMPS1\r\n", expect_success=False)
        self.assertIn("cannot be parsed", run.transcript)

    def test_truncated_table_without_level_rows_header_fails(self) -> None:
        run = self.run_clab(b"2DA V1.0\r\n****\r\n", expect_success=False)
        self.assertIn("cannot be parsed", run.transcript)

    def test_grant_beyond_declared_columns_is_ambiguous(self) -> None:
        raw = make_clab(5, [("ABILITY1", {1: "GA_OHTMPS1"})]) + b"ABILITY2  ****  ****  ****  ****  ****  GA_OHTMPS1\r\n"
        run = self.run_clab(raw, expect_success=False)
        self.assertIn("beyond the 5 level columns", run.transcript)


def read_2da_bytes(raw: bytes):
    with tempfile.TemporaryDirectory(prefix="cbr-clab-read-") as holder:
        path = Path(holder) / CLAB_NAME
        path.write_bytes(raw)
        return read_2da(path)


# ---------------------------------------------------------------------------
# Full Holy Power progression harness with a variant CLAB
# ---------------------------------------------------------------------------


class ClabProgressionVariantTests(unittest.TestCase):
    def _run_progression(self, clab: bytes) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
        holder = tempfile.TemporaryDirectory(prefix="cbr-clab-progression-")
        self.addCleanup(holder.cleanup)
        base = Path(holder.name)
        fixture = build_fixture(base / "fixture", "additive")
        (fixture.root / CLAB_NAME).write_bytes(clab)
        output = base / "output"
        output.mkdir()
        run_dir = base / "weidu-run"
        run_dir.mkdir()
        process = subprocess.run(
            [
                str(WEIDU), str(HOLY_HARNESS), "--nogame",
                "--force-install-list", PHASE_COMPONENT["progression"],
                "--args", str(PRODUCTION_TPA), "--args", str(fixture.root),
                "--args", str(output), "--args", "auto",
                "--args", fixture.divine_resref, "--args", fixture.haste_resref,
                "--no-exit-pause", "--quick-log",
            ],
            cwd=run_dir, capture_output=True, text=True, timeout=90, check=False,
        )
        return fixture.root, output, process

    def test_progression_caps_a_wide_table_with_grants_outside_ability1(self) -> None:
        grants = {level: "GA_OHTMPS1" for level in range(1, 61, 5)}
        clab = make_clab(
            60, [("ABILITY1", {**ARTISAN_FILL, 25: "AP_CDHLYSYM"}), ("ABILITY2", grants)]
        )
        _fixture, output, process = self._run_progression(clab)
        transcript = process.stdout + process.stderr
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertEqual(expected_cap(clab), (output / CLAB_NAME).read_bytes())

    def test_progression_leaves_an_already_capped_narrow_table_untouched(self) -> None:
        clab = make_clab(40, [("ABILITY1", {1: "GA_OHTMPS1", 7: "GA_OHTMPS1", 25: "AP_CDHLYSYM"})])
        _fixture, output, process = self._run_progression(clab)
        transcript = process.stdout + process.stderr
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertEqual(clab, (output / CLAB_NAME).read_bytes())


# ---------------------------------------------------------------------------
# Public installer (component 401) on a synthetic game
# ---------------------------------------------------------------------------


class ClabInstallerVariantTests(unittest.TestCase):
    def _game(self, clab: bytes) -> SyntheticGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-clab-installer-")
        self.addCleanup(temporary.cleanup)
        game = SyntheticGame(temporary, "additive")
        (game.override / CLAB_NAME).write_bytes(clab)
        game.pre_override = _raw_file_tree(game.override)
        return game

    def test_component_401_caps_variant_clab_and_uninstalls_exactly(self) -> None:
        clab = make_clab(
            50,
            [
                ("ABILITY1", ARTISAN_FILL),
                ("ABILITY2", {level: "ga_ohtmps1" for level in (1, 6, 11, 16, 21, 26, 31)}),
                ("ABILITY3", {25: "AP_CDHLYSYM"}),
            ],
            newline="\n",
        )
        game = self._game(clab)
        install = game.run_install(401)
        transcript = game.transcript(install)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        game.assert_stable_inputs(self)
        self.assertEqual(expected_cap(clab), (game.override / CLAB_NAME).read_bytes())

        uninstall = game.run_uninstall(401)
        self.assertEqual(0, uninstall.returncode, game.transcript(uninstall))
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))
        game.assert_stable_inputs(self)

    def test_component_401_rolls_back_when_no_holy_power_grant_exists(self) -> None:
        clab = make_clab(50, [("ABILITY1", {1: "GA_SPCL900", 25: "AP_CDHLYSYM"})])
        game = self._game(clab)
        process = game.run_install(401)
        transcript = game.transcript(process)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertIn("grants no GA_OHTMPS1 use", transcript)
        self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))
        self.assertFalse(game.scratch.exists())
        game.assert_stable_inputs(self)


if __name__ == "__main__":
    unittest.main()
