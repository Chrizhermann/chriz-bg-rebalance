"""Hermetic --nogame tests for the tempus-completion libraries (400-407).

Fixture principle: live-shaped captures over hand-built models. The Chaos of
Battle fixtures are the real vanilla BIF payloads (research/originals/*.orig)
and the real live override copies carrying EE Fixpack's tier-1 chrome trim and
SCS's hostile-AoE casting hooks (*.live). Weapon-training fixtures model both
the pristine Artisan state and the 2026-07-14 live-hotfixed state.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import (
    SplAbility,
    SplEffect,
    SplFile,
    make_spl,
    read_2da,
    read_eff_v2,
    read_spl,
    write_spl,
)

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "tempus_completion_harness.tp2"
HOLY_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_holy_power.tpa"
TRAINING_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_weapon_training.tpa"
TIDES_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_chaos_tides.tpa"
TOLL_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_divination_toll.tpa"
SPEC_APR_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_spec_apr.tpa"
SPEC_APR_EEEX_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_spec_apr_eeex.tpa"
LUA_TEMPLATE = ROOT / "chriz-bg-rebalance" / "lua" / "M_CBRAPR.lua"
DESCRIPTIONS_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_descriptions.tpa"
ORIGINALS = ROOT / "research" / "originals"

COMPONENT = {
    "training": "0",
    "tides": "1",
    "toll": "2",
    "specapr": "3",
    "specapr_eeex": "4",
    "descriptions": "5",
}
COMPONENT_TPA = {
    "training": TRAINING_TPA,
    "tides": TIDES_TPA,
    "toll": TOLL_TPA,
    "specapr": SPEC_APR_TPA,
    "specapr_eeex": SPEC_APR_EEEX_TPA,
    "descriptions": DESCRIPTIONS_TPA,
}

LS_PERM_STAT = 204
TIDE_STRREFS = ("111111", "222222", "333333")
TIDE_ALLY = ("CBRCHT1D", "CBRCHT2D", "CBRCHT3D")
TIDE_ENEMY = ("CBRCHT1E", "CBRCHT2E", "CBRCHT3E")
TIDE_WINDOWS = ((33, 0), (66, 34), (100, 67))
ONSLAUGHT_OPS = (54, 285, 286)
BULWARK_OPS = (0, 33, 34, 35, 36, 37)
MAGNITUDES = (2, 2, 3, 3, 4)
LUCK_MAGNITUDES = (1, 1, 1, 2, 2)
TOLL_SPELLS = ("SPPR104", "SPPR205", "SPPR209", "SPPR415", "SPPR505")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

WEAPPROF_COLUMNS = ("FIGHTER", "CLERIC", "OHTEMPUS")
# (row, fighter, cleric, ohtempus_pristine, ohtempus_expected)
WEAPPROF_ROWS = (
    ("BASTARDSWORD", "5", "0", "0", "0"),
    ("LONGSWORD", "5", "0", "0", "2"),
    ("AXE", "5", "0", "0", "2"),
    ("WARHAMMER", "5", "1", "1", "2"),
    ("MACE", "5", "1", "1", "2"),
    ("QUARTERSTAFF", "5", "1", "0", "2"),
    ("CROSSBOW", "5", "0", "0", "2"),
    ("SLING", "5", "1", "1", "2"),
    ("HALBERD", "5", "0", "1", "2"),
    ("BLUNT_BG1", "5", "1", "1", "1"),
    ("LARGE_SWORD_BG1", "5", "0", "0", "0"),
    ("2HANDED", "1", "1", "1", "2"),
    ("SWORDANDSHIELD", "1", "1", "1", "2"),
    ("SINGLEWEAPON", "1", "1", "1", "2"),
    ("2WEAPON", "1", "1", "1", "2"),
    ("EXTRA2", "0", "0", "0", "0"),
)

SPLPROT_BASE_ROWS = (
    "0_ANYONE 0x106 0 1",
    "1_UNUSED 60 1 1",
    "43_SOURCE 0x100 * *",
    "44_!SOURCE 0x101 * *",
)


def _axe_gate() -> SplEffect:
    return SplEffect(opcode=326, target=1, power=0, timing=0, resource="C0PR#92")


def _pip(proficiency: int) -> SplEffect:
    return SplEffect(opcode=233, target=1, power=0, parameter1=1, parameter2=proficiency, timing=9)


def _tempus_grant(effects: tuple[SplEffect, ...]) -> SplFile:
    return make_spl([SplAbility(required_level=1, target=1, projectile=1, effects=effects)])


def _hotfixed_effects() -> tuple[SplEffect, ...]:
    return (
        _axe_gate(),
        _pip(92),
        SplEffect(opcode=326, target=1, power=0, timing=0, resource="C0PR#90"),
        _pip(90),
        _pip(103),
    )


def build_training_fixture(
    root: Path,
    *,
    grant_shape: str = "pristine",
    weapprof_shape: str = "pristine",
    splprot_extra_rows: tuple[str, ...] = (),
    drop_ohtempus_column: bool = False,
) -> None:
    root.mkdir(parents=True)
    columns = list(WEAPPROF_COLUMNS)
    if drop_ohtempus_column:
        # Rename rather than remove so the table keeps its width and the
        # specific missing-column diagnostic (not the minimum-width guard)
        # is what fires.
        columns[columns.index("OHTEMPUS")] = "OTHERKIT"
    lines = ["2DA V1.0", "0", "\t".join(columns)]
    for name, fighter, cleric, pristine, expected in WEAPPROF_ROWS:
        cells = {"FIGHTER": fighter, "CLERIC": cleric, "OTHERKIT": pristine,
                 "OHTEMPUS": expected if weapprof_shape == "hotfixed" else pristine}
        lines.append(name + "\t" + "\t".join(cells[c] for c in columns))
    (root / "WEAPPROF.2DA").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")

    if grant_shape == "pristine":
        effects: tuple[SplEffect, ...] = (_axe_gate(), _pip(92))
    elif grant_shape == "hotfixed":
        effects = _hotfixed_effects()
    elif grant_shape == "no_axe_pair":
        effects = (_pip(103),)
    elif grant_shape == "duplicate_longsword_gate":
        gate90 = SplEffect(opcode=326, target=1, power=0, timing=0, resource="C0PR#90")
        effects = (_axe_gate(), _pip(92), gate90, gate90)
    else:
        raise ValueError(grant_shape)
    write_spl(root / "C0PR#C4.SPL", _tempus_grant(effects))

    rows = list(SPLPROT_BASE_ROWS) + list(splprot_extra_rows)
    text = "\n".join(["2DA V1.0", "0", "        STAT VALUE RELATION", *rows]) + "\n"
    (root / "SPLPROT.2DA").write_text(text, encoding="ascii", newline="\n")


def build_tides_fixture(root: Path, *, shape: str = "vanilla") -> None:
    root.mkdir(parents=True)
    suffix = ".spl.orig" if shape == "vanilla" else ".spl.live"
    shutil.copy2(ORIGINALS / "OHTMPS2.spl.orig", root / "OHTMPS2.SPL")
    for name in ("OHTMPS2D", "OHTMPS2E"):
        shutil.copy2(ORIGINALS / f"{name}{suffix}", root / f"{name}.SPL")


# Live-shaped CLSWPBON slice: base classes, the EET-merged OH kits, and an
# Artisan kit that already holds the per-kit APR grant (the engine-supported
# precedent component 406 relies on).
CLSWPBON_ROWS_LIVE = (
    ("MAGE", "0", "0", "5"),
    ("FIGHTER", "1", "0", "2"),
    ("CLERIC", "0", "0", "3"),
    ("FIGHTER_CLERIC", "1", "0", "2"),
    ("OHTYR", "0", "0", "3"),
    ("OHTEMPUS", "0", "0", "3"),
    ("C0_NINJA", "1", "0", "2"),
)


def build_specapr_fixture(root: Path, *, shape: str = "live") -> None:
    root.mkdir(parents=True)
    header = "GETS_PROF_APR\tUNARMED_DIVISOR\tZERO_SKILL_THAC0"
    if shape == "no_column":
        header = "GETS_PROF_APRX\tUNARMED_DIVISOR\tZERO_SKILL_THAC0"
    rows = []
    for name, apr, divisor, thac0 in CLSWPBON_ROWS_LIVE:
        if name == "OHTEMPUS":
            if shape == "missing_row":
                continue
            if shape == "done":
                apr = "1"
            elif shape == "garbage":
                apr = "yes"
        elif name == "CLERIC":
            if shape == "missing_cleric":
                continue
            if shape == "done":
                apr = "1"
        rows.append(f"{name}\t{apr}\t{divisor}\t{thac0}")
    lines = ["2DA V1.0", "0", header, *rows]
    (root / "CLSWPBON.2DA").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")


def build_toll_fixture(root: Path, *, conflicting_row: bool = False) -> None:
    root.mkdir(parents=True)
    columns = "\t".join(str(level) for level in range(1, 51))
    ability1 = ["GA_OHTMPS1" if level in (1, 6, 11, 16, 21) else "****" for level in range(1, 51)]
    ability2 = ["GA_OHTMPS2" if level in (1, 11, 21, 31, 41) else "****" for level in range(1, 51)]
    lines = [
        "2DA V1.0",
        "****",
        columns,
        "ABILITY1\t" + "\t".join(ability1),
        "ABILITY2\t" + "\t".join(ability2),
    ]
    if conflicting_row:
        lines.append("CBR_DIVTOLL\t" + "\t".join(["AP_SOMETHN"] * 50))
    (root / "OHTEMPUS.2DA").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")


# Live strrefs of the texts component 408 repoints away from: KITLIST HELP
# (kit description), OHTMPS1 desc (SHARED with the standard Holy Power priest
# spell - the reason 408 appends + repoints instead of editing in place), and
# OHTMPS2 desc (kit-owned).
KITLIST_HELP_LIVE = "103223"
OHTMPS1_DESC_LIVE = 6088
OHTMPS2_DESC_LIVE = 103225

KITLIST_HEADER = "ROWNAME\tLOWER\tMIXED\tHELP\tABILITIES\tPROFICIENCY\tUNUSABLE\tCLASS\tKITIDS"


def _spl_with_desc(desc: int) -> bytes:
    data = bytearray(make_spl([]).to_bytes())
    struct.pack_into("<i", data, 0x50, desc)
    return bytes(data)


def build_descriptions_fixture(
    root: Path,
    *,
    shape: str = "live",
    help_value: str = KITLIST_HELP_LIVE,
    hp_desc: int = OHTMPS1_DESC_LIVE,
    cob_desc: int = OHTMPS2_DESC_LIVE,
) -> None:
    root.mkdir(parents=True)
    header = KITLIST_HEADER
    if shape == "no_help_column":
        header = header.replace("HELP", "HLPX")
    rows = ["0\tTRUECLASS\t1\t2\t3\t****\t0\t0x00000000\t0\t0x00004000"]
    ohtempus = f"41\tOHTEMPUS\t103221\t103222\t{help_value}\tOHTEMPUS\t62\t0x00004000\t3\t0x00004029"
    if shape != "missing_row":
        rows.append(ohtempus)
    if shape == "dup_row":
        rows.append(ohtempus)
    rows.append("58\tC0_NINJA\t500\t501\t502\tC0NINJA\t20\t0x00004000\t4\t0x0000402E")
    (root / "KITLIST.2DA").write_text(
        "\n".join(["2DA V1.0", "0", header, *rows]) + "\n", encoding="ascii", newline="\n"
    )
    spl1 = _spl_with_desc(hp_desc)
    if shape == "bad_spl":
        spl1 = b"ITM V1  " + spl1[8:]
    (root / "OHTMPS1.SPL").write_bytes(spl1)
    (root / "OHTMPS2.SPL").write_bytes(_spl_with_desc(cob_desc))


# ---------------------------------------------------------------------------
# Harness driver
# ---------------------------------------------------------------------------


class HarnessRun:
    def __init__(self, component: str, fixture_dir: Path, extra_args: tuple[str, ...]):
        self.temporary = tempfile.TemporaryDirectory(prefix="cbr-completion-")
        base = Path(self.temporary.name)
        self.fixture = fixture_dir
        self.output = base / "output"
        run_dir = base / "weidu-run"
        run_dir.mkdir()
        command = [
            str(WEIDU), str(HARNESS), "--nogame",
            "--force-install-list", COMPONENT[component],
            "--args", str(HOLY_TPA),
            "--args", str(COMPONENT_TPA[component]),
            "--args", str(self.fixture),
            "--args", str(self.output),
        ]
        for value in extra_args:
            command.extend(["--args", value])
        command.extend(["--no-exit-pause", "--quick-log"])
        self.process = subprocess.run(
            command, cwd=run_dir, capture_output=True, text=True, timeout=60, check=False
        )

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}"

    @property
    def succeeded(self) -> bool:
        return (self.output / "CBR_TEST.OK").exists() and "SUCCESSFULLY INSTALLED" in self.transcript

    def cleanup(self) -> None:
        self.temporary.cleanup()


def _raw_tree(root: Path) -> dict[str, bytes]:
    # CBR_TEST.OK is the harness completion marker (a copy of one fixture
    # input), not library output — it legitimately differs between a first
    # pass and a pass re-run on the first pass's output.
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name.upper() != "CBR_TEST.OK"
    }


class TempusCompletionTestCase(unittest.TestCase):
    def run_component(
        self,
        component: str,
        build,
        *,
        extra_args: tuple[str, ...],
        expect_success: bool = True,
        rerun_on_output: bool = False,
    ) -> HarnessRun:
        fixture_holder = tempfile.TemporaryDirectory(prefix="cbr-completion-fixture-")
        self.addCleanup(fixture_holder.cleanup)
        fixture_dir = Path(fixture_holder.name) / "fixture"
        build(fixture_dir)
        run = HarnessRun(component, fixture_dir, extra_args)
        self.addCleanup(run.cleanup)
        if expect_success and not run.succeeded:
            self.fail(f"harness run failed unexpectedly:\n{run.transcript}")
        if not expect_success:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", run.transcript)
            self.assertFalse((run.output / "CBR_TEST.OK").exists())
        if rerun_on_output:
            second = HarnessRun(component, run.output, extra_args)
            self.addCleanup(second.cleanup)
            if not second.succeeded:
                self.fail(f"second pass failed:\n{second.transcript}")
            first_tree = _raw_tree(run.output)
            second_tree = _raw_tree(second.output)
            self.assertEqual(first_tree, second_tree, "library is not byte-idempotent")
        return run


# ---------------------------------------------------------------------------
# Component 400 — weapon training
# ---------------------------------------------------------------------------


class WeaponTrainingTests(TempusCompletionTestCase):
    def _splprot_rows(self, path: Path) -> list[tuple[str, ...]]:
        lines = [line.split() for line in path.read_text(encoding="ascii").splitlines()]
        return [tuple(tokens) for tokens in lines if len(tokens) == 4 and tokens[0] != "STAT"]

    def test_pristine_transform_full_matrix(self) -> None:
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(root),
            extra_args=(str(LS_PERM_STAT),),
            rerun_on_output=True,
        )
        table = read_2da(run.output / "WEAPPROF.2DA")
        for name, fighter, _cleric, _pristine, expected in WEAPPROF_ROWS:
            self.assertEqual(
                table.cell(name, "OHTEMPUS"), expected, f"OHTEMPUS cap for {name}"
            )
            self.assertEqual(table.cell(name, "FIGHTER"), fighter, f"foreign column for {name}")

        grant = read_spl(run.output / "C0PR#C4.SPL")
        effects = grant.abilities[0].effects
        self.assertEqual(
            [(e.opcode, e.parameter2, e.resource) for e in effects],
            [
                (326, 0, "C0PR#92"),
                (233, 92, ""),
                (326, 0, "C0PR#90"),
                (233, 90, ""),
                (233, 103, ""),
            ],
        )
        for effect in effects:
            if effect.opcode == 233:
                self.assertEqual((effect.parameter1, effect.timing), (1, 9))

        rows = self._splprot_rows(run.output / "SPLPROT.2DA")
        base = len(SPLPROT_BASE_ROWS)
        self.assertEqual(
            rows[base:],
            [
                ("CBR_TEMPUS_C0LS_LE0", str(LS_PERM_STAT), "0", "0"),
                ("CBR_TEMPUS_PROFLS_LE0", "90", "0", "0"),
                ("CBR_TEMPUS_PROFXB_LE0", "103", "0", "0"),
            ],
        )

        migration = read_spl(run.output / "CBRTMG2.spl")
        gates = migration.abilities[0].effects
        self.assertEqual(
            [(e.opcode, e.parameter2, e.resource) for e in gates],
            [
                (326, base, "C0PR#90"),
                (326, base + 1, "CBRTMG2L"),
                (326, base + 2, "CBRTMG2X"),
            ],
        )
        for helper, proficiency in (("CBRTMG2L", 90), ("CBRTMG2X", 103)):
            spl = read_spl(run.output / f"{helper}.spl")
            (effect,) = spl.abilities[0].effects
            self.assertEqual(
                (effect.opcode, effect.parameter1, effect.parameter2, effect.timing),
                (233, 1, proficiency, 9),
            )

    def test_hotfixed_inputs_stay_byte_identical(self) -> None:
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(
                root, grant_shape="hotfixed", weapprof_shape="hotfixed"
            ),
            extra_args=(str(LS_PERM_STAT),),
        )
        self.assertEqual((run.fixture / "C0PR#C4.SPL").read_bytes(), (run.output / "C0PR#C4.SPL").read_bytes())
        table = read_2da(run.output / "WEAPPROF.2DA")
        for name, fighter, _cleric, _pristine, expected in WEAPPROF_ROWS:
            self.assertEqual(expected, table.cell(name, "OHTEMPUS"))
            self.assertEqual(fighter, table.cell(name, "FIGHTER"))

    def test_owned_splprot_rows_preserve_foreign_equivalents(self) -> None:
        seeded = (
            f"FOREIGN_LSPERM {LS_PERM_STAT} 0 0",
            "FOREIGN_LSPIPS 90 0 0",
            "FOREIGN_XBPIPS 103 0 0",
        )
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(root, splprot_extra_rows=seeded),
            extra_args=(str(LS_PERM_STAT),),
        )
        rows = self._splprot_rows(run.output / "SPLPROT.2DA")
        self.assertEqual(rows[len(SPLPROT_BASE_ROWS):len(SPLPROT_BASE_ROWS) + 3], [tuple(row.split()) for row in seeded])
        self.assertEqual(len(rows), len(SPLPROT_BASE_ROWS) + len(seeded) + 3)
        migration = read_spl(run.output / "CBRTMG2.spl")
        base = len(SPLPROT_BASE_ROWS) + len(seeded)
        self.assertEqual(
            [effect.parameter2 for effect in migration.abilities[0].effects],
            [base, base + 1, base + 2],
        )

    def test_missing_ohtempus_column_is_created(self):
        run = self.run_component("training", lambda root: build_training_fixture(root, drop_ohtempus_column=True),
                                 extra_args=(str(LS_PERM_STAT),), rerun_on_output=True)
        table = read_2da(run.output / "WEAPPROF.2DA")
        for name in ("LONGSWORD", "AXE", "CROSSBOW", "MACE", "SLING", "2WEAPON"):
            self.assertEqual("2", table.cell(name, "OHTEMPUS"))

    def test_missing_axe_pair_still_receives_the_decided_grants(self):
        run = self.run_component("training", lambda root: build_training_fixture(root, grant_shape="no_axe_pair"),
                                 extra_args=(str(LS_PERM_STAT),), rerun_on_output=True)
        effects = read_spl(run.output / "C0PR#C4.SPL").abilities[0].effects
        self.assertEqual([(326,0,"C0PR#90"),(233,90,""),(233,103,"")], [(e.opcode,e.parameter2,e.resource) for e in effects])

    def test_duplicate_owned_longsword_gates_are_replaced(self):
        run = self.run_component("training", lambda root: build_training_fixture(root, grant_shape="duplicate_longsword_gate"),
                                 extra_args=(str(LS_PERM_STAT),), rerun_on_output=True)
        effects = read_spl(run.output / "C0PR#C4.SPL").abilities[0].effects
        self.assertEqual(1, sum(e.opcode == 326 and e.resource == "C0PR#90" for e in effects))
        self.assertEqual([(233,90,1,9),(233,103,1,9)], [(e.opcode,e.parameter2,e.parameter1,e.timing) for e in effects[-2:]])

    def test_missing_rows_changed_caps_and_helpers_are_overwritten(self):
        def build(root):
            build_training_fixture(root)
            (root / "WEAPPROF.2DA").write_text("2DA V1.0\n0\nOHTEMPUS FOREIGN CLERIC\nMACE edited keep 0\nLONGSWORD 9 stay 0\n")
            for name in ("CBRTMG2", "CBRTMG2L", "CBRTMG2X"):
                (root / f"{name}.spl").write_bytes(b"foreign helper")
        run = self.run_component("training", build, extra_args=(str(LS_PERM_STAT),), rerun_on_output=True)
        table = read_2da(run.output / "WEAPPROF.2DA")
        self.assertEqual("keep", table.cell("MACE", "FOREIGN"))
        for name in ("MACE", "LONGSWORD", "AXE", "CROSSBOW", "2WEAPON"):
            self.assertEqual("2", table.cell(name, "OHTEMPUS"))
        for name in ("CBRTMG2", "CBRTMG2L", "CBRTMG2X"):
            self.assertTrue(read_spl(run.output / f"{name}.spl").abilities[0].effects)

    def test_missing_foreign_grant_and_tables_do_not_omit_owned_resources(self):
        def build(root):
            root.mkdir(parents=True)
        run = self.run_component("training", build, extra_args=("-1",), rerun_on_output=True)
        self.assertFalse((run.output / "C0PR#C4.SPL").exists())
        table = read_2da(run.output / "WEAPPROF.2DA")
        self.assertEqual("2", table.cell("MACE", "OHTEMPUS"))
        gates = read_spl(run.output / "CBRTMG2.spl").abilities[0].effects
        self.assertEqual(["CBRTMG2L", "CBRTMG2X"], [e.resource for e in gates])
        self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_duplicate_owned_columns_are_all_written(self):
        def build(root):
            build_training_fixture(root)
            (root / "WEAPPROF.2DA").write_text("2DA V1.0\n0\nOHTEMPUS FOREIGN OHTEMPUS\nMACE 9 kept broken\n")
        run = self.run_component("training", build, extra_args=(str(LS_PERM_STAT),), rerun_on_output=True)
        cells = next(line.split() for line in (run.output / "WEAPPROF.2DA").read_text().splitlines() if line.startswith("MACE "))
        self.assertEqual(["MACE","2","kept","2"], cells)


# ---------------------------------------------------------------------------
# Component 404 — Chaos of Battle tides
# ---------------------------------------------------------------------------


class ChaosTidesTests(TempusCompletionTestCase):
    def _assert_dispatcher(self, path: Path) -> None:
        dispatcher = read_spl(path)
        self.assertEqual(len(dispatcher.abilities), 1)
        effects = dispatcher.abilities[0].effects
        self.assertEqual(len(effects), 9)
        for window in range(3):
            high, low = TIDE_WINDOWS[window]
            announce, ally, enemy = effects[window * 3 : window * 3 + 3]
            self.assertEqual(
                (announce.opcode, announce.parameter1, announce.timing),
                (139, int(TIDE_STRREFS[window]), 1),
            )
            self.assertEqual((ally.opcode, ally.resource), (146, TIDE_ALLY[window]))
            self.assertEqual((enemy.opcode, enemy.resource), (146, TIDE_ENEMY[window]))
            for effect in (announce, ally, enemy):
                self.assertEqual(
                    (effect.probability1, effect.probability2), (high, low), "window bounds"
                )
            for cast in (ally, enemy):
                self.assertEqual(cast.parameter2, 1, "cast-at-level semantics inherited")

    def _assert_tide_magnitudes(
        self, path: Path, ops: tuple[int, ...], magnitudes: tuple[int, ...], sign: int,
        resets: tuple[str, ...],
    ) -> None:
        spell = read_spl(path)
        self.assertEqual(len(spell.abilities), 5)
        for tier, ability in enumerate(spell.abilities):
            self.assertEqual(ability.required_level, 1 + tier * 6)
            trio = ability.effects[:3]
            self.assertEqual([e.opcode for e in trio], [321, 321, 321])
            self.assertEqual([e.resource for e in trio], list(resets))
            stats = [e for e in ability.effects if e.opcode in ops and e.timing == 0]
            self.assertEqual(len(stats), len(ops), f"tier {tier} stat set")
            for effect in stats:
                self.assertEqual(effect.parameter1, magnitudes[tier] * sign)
                self.assertEqual(effect.duration, 30)
                self.assertEqual((effect.probability1, effect.probability2), (100, 0))
            for chrome_opcode in (142, 9):
                chrome = [e for e in ability.effects if e.opcode == chrome_opcode]
                self.assertEqual(len(chrome), 1)
                self.assertEqual(chrome[0].duration, 30)

    def test_vanilla_donors_full_matrix(self) -> None:
        run = self.run_component(
            "tides",
            lambda root: build_tides_fixture(root),
            extra_args=TIDE_STRREFS,
            rerun_on_output=True,
        )
        self._assert_dispatcher(run.output / "OHTMPS2.SPL")
        self._assert_tide_magnitudes(
            run.output / "CBRCHT1D.SPL", ONSLAUGHT_OPS, MAGNITUDES, 1, TIDE_ALLY
        )
        self._assert_tide_magnitudes(
            run.output / "CBRCHT1E.SPL", ONSLAUGHT_OPS, MAGNITUDES, -1, TIDE_ENEMY
        )
        self._assert_tide_magnitudes(
            run.output / "CBRCHT2D.SPL", BULWARK_OPS, MAGNITUDES, 1, TIDE_ALLY
        )
        self._assert_tide_magnitudes(
            run.output / "CBRCHT2E.SPL", BULWARK_OPS, MAGNITUDES, -1, TIDE_ENEMY
        )
        self._assert_tide_magnitudes(
            run.output / "CBRCHT3D.SPL", (22,), LUCK_MAGNITUDES, 1, TIDE_ALLY
        )
        self._assert_tide_magnitudes(
            run.output / "CBRCHT3E.SPL", (22,), LUCK_MAGNITUDES, -1, TIDE_ENEMY
        )
        for name in ("OHTMPS2D.SPL", "OHTMPS2E.SPL"):
            self.assertEqual(
                (run.fixture / name).read_bytes(),
                (run.output / name).read_bytes(),
                "donors are read-only inputs",
            )
        for name in TIDE_ALLY + TIDE_ENEMY:
            spell = read_spl(run.output / f"{name}.SPL")
            self.assertEqual(spell.casting_effects, (), "vanilla donors carry no casting slice")
            projectile = 162 if name.endswith("D") else 171
            for ability in spell.abilities:
                self.assertEqual(ability.projectile, projectile)

    def test_live_donors_preserve_scs_casting_hooks_and_eefp_chrome(self) -> None:
        run = self.run_component(
            "tides",
            lambda root: build_tides_fixture(root, shape="live"),
            extra_args=TIDE_STRREFS,
        )
        for name in TIDE_ENEMY:
            spell = read_spl(run.output / f"{name}.SPL")
            self.assertEqual(
                [(e.opcode, e.resource.lower()) for e in spell.casting_effects],
                [(146, "dw#blhda"), (321, "dw#hdani")],
                "SCS hostile-AoE casting hooks must survive the rebuild",
            )
        ally = read_spl(run.output / "CBRCHT1D.SPL")
        tier_visuals = [
            len([e for e in ability.effects if e.opcode == 215]) for e_i, ability in enumerate(ally.abilities)
        ]
        self.assertEqual(tier_visuals, [1, 2, 2, 2, 2], "EE Fixpack tier-1 chrome trim inherited")

    def test_foreign_dispatcher_is_rebuilt(self) -> None:
        def build(root: Path) -> None:
            build_tides_fixture(root)
            dispatcher = read_spl(root / "OHTMPS2.SPL")
            patched = dispatcher.abilities[0].effects[0].to_bytes()
            data = bytearray((root / "OHTMPS2.SPL").read_bytes())
            offset = data.find(patched)
            data[offset + 0x14 : offset + 0x1C] = b"FOREIGN\0"
            (root / "OHTMPS2.SPL").write_bytes(bytes(data))

        run = self.run_component(
            "tides", build, extra_args=TIDE_STRREFS, rerun_on_output=True
        )
        self._assert_dispatcher(run.output / "OHTMPS2.SPL")

    def test_missing_strref_fails(self) -> None:
        run = self.run_component(
            "tides",
            lambda root: build_tides_fixture(root),
            extra_args=("111111", "222222", "-1"),
            expect_success=False,
        )
        self.assertIn("three resolved announce strrefs", run.transcript)


# ---------------------------------------------------------------------------
# Component 405 — Divination toll
# ---------------------------------------------------------------------------


class DivinationTollTests(TempusCompletionTestCase):
    def test_toll_shape_full(self) -> None:
        run = self.run_component(
            "toll",
            lambda root: build_toll_fixture(root),
            extra_args=("5", *TOLL_SPELLS),
            rerun_on_output=True,
        )
        table = read_2da(run.output / "OHTEMPUS.2DA")
        for level in range(1, 51):
            self.assertEqual(table.cell("CBR_DIVTOLL", str(level)), "AP_CBRTMDV")
        self.assertEqual(table.cell("ABILITY1", "1"), "GA_OHTMPS1", "existing rows untouched")

        toll = read_spl(run.output / "CBRTMDV.spl")
        effects = toll.abilities[0].effects
        self.assertEqual(len(effects), 11)
        self.assertEqual(
            (effects[0].opcode, effects[0].resource, effects[0].timing), (321, "CBRTMDV", 1)
        )
        self.assertEqual(
            [(e.opcode, e.resource, e.timing) for e in effects[1:6]],
            [(172, name, 1) for name in TOLL_SPELLS],
        )
        self.assertEqual(
            [
                (e.opcode, e.resource, e.timing, e.parameter1, e.parameter2)
                for e in effects[6:]
            ],
            [(272, f"CBRTMD{i}", 9, 1, 3) for i in range(5)],
        )
        for index, name in enumerate(TOLL_SPELLS):
            eff = read_eff_v2(run.output / f"CBRTMD{index}.eff")
            self.assertEqual(
                (eff.opcode, eff.resource, eff.timing, eff.probability1), (172, name, 1, 100)
            )

    def test_conflicting_clab_row_is_overwritten(self):
        run = self.run_component("toll", lambda root: build_toll_fixture(root, conflicting_row=True),
                                 extra_args=("5", *TOLL_SPELLS), rerun_on_output=True)
        table = read_2da(run.output / "OHTEMPUS.2DA")
        self.assertTrue(all(table.cell("CBR_DIVTOLL", str(level)) == "AP_CBRTMDV" for level in range(1,51)))

    def test_zero_discovered_spells_installs_an_inert_self_reset(self):
        run = self.run_component("toll", build_toll_fixture, extra_args=("0",), rerun_on_output=True)
        self.assertEqual([321], [e.opcode for e in read_spl(run.output / "CBRTMDV.spl").abilities[0].effects])
        self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_unaddressable_resref_only_costs_that_entry(self):
        run = self.run_component("toll", build_toll_fixture, extra_args=("2", "WAYTOOLONGNAME", "SPPR104"), rerun_on_output=True)
        effects = read_spl(run.output / "CBRTMDV.spl").abilities[0].effects
        self.assertEqual([(321,"CBRTMDV"),(172,"SPPR104"),(272,"CBRTMD0")], [(e.opcode,e.resource) for e in effects])
        self.assertEqual(1, run.transcript.count("cannot address Divination"))
        self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_missing_table_and_foreign_helpers_are_replaced(self):
        def build(root):
            root.mkdir(parents=True)
            (root / "CBRTMDV.spl").write_bytes(b"foreign spell")
            (root / "CBRTMD0.eff").write_bytes(b"foreign effect")
            (root / "CBRTMD0.itm").write_bytes(b"unrelated item")
        run = self.run_component("toll", build, extra_args=("1", "SPPR104"), rerun_on_output=True)
        self.assertEqual("SPPR104", read_eff_v2(run.output / "CBRTMD0.eff").resource)
        self.assertEqual(3, len(read_spl(run.output / "CBRTMDV.spl").abilities[0].effects))
        self.assertEqual(b"unrelated item", (run.output / "CBRTMD0.itm").read_bytes())
        self.assertEqual("AP_CBRTMDV", read_2da(run.output / "OHTEMPUS.2DA").cell("CBR_DIVTOLL", "50"))

    def test_reordered_duplicate_rows_and_extra_levels_are_written(self):
        def build(root):
            root.mkdir(parents=True)
            (root / "OHTEMPUS.2DA").write_text("2DA V1.0\n****\n51 FOREIGN 2 1\nABILITY1 GA_X keep GA_Y GA_Z\nCBR_DIVTOLL old keep old old\nCBR_DIVTOLL wrong stay wrong wrong\n")
        run = self.run_component("toll", build, extra_args=("1", "SPPR104"), rerun_on_output=True)
        table = read_2da(run.output / "OHTEMPUS.2DA")
        self.assertEqual("GA_X", table.cell("ABILITY1", "51"))
        for name,cells in table.rows:
            if name == "CBR_DIVTOLL":
                for level in range(1,52):
                    self.assertEqual("AP_CBRTMDV", cells[table.columns.index(str(level))])
                self.assertIn(cells[table.columns.index("FOREIGN")], ("keep", "stay"))

    def test_more_than_99_spells_receive_removal_and_heartbeat(self):
        run = self.run_component("toll", build_toll_fixture, extra_args=("105", "generated"), rerun_on_output=True)
        effects = read_spl(run.output / "CBRTMDV.spl").abilities[0].effects
        self.assertEqual(211, len(effects))
        for index in range(105):
            self.assertEqual((172, f"DV{index:06}"), (effects[1+index].opcode,effects[1+index].resource))
            helper = effects[106+index].resource
            self.assertLessEqual(len(helper),8)
            self.assertEqual(f"DV{index:06}", read_eff_v2(run.output / f"{helper}.eff").resource)


# ---------------------------------------------------------------------------
# Component 406 — specialization APR (CLSWPBON)
# ---------------------------------------------------------------------------


class SpecAprTests(TempusCompletionTestCase):
    @staticmethod
    def _rows(path: Path) -> dict[str, tuple[str, ...]]:
        table: dict[str, tuple[str, ...]] = {}
        for line in path.read_text(encoding="ascii").splitlines()[3:]:
            tokens = line.split()
            if len(tokens) == 4:
                table[tokens[0]] = tuple(tokens[1:])
        return table

    def test_flip_live_shape(self) -> None:
        run = self.run_component(
            "specapr",
            lambda root: build_specapr_fixture(root),
            extra_args=(),
            rerun_on_output=True,
        )
        rows = self._rows(run.output / "CLSWPBON.2DA")
        self.assertEqual(rows["OHTEMPUS"], ("1", "0", "3"))
        self.assertEqual(rows["CLERIC"], ("1", "0", "3"))
        # Every other row is untouched (values, not formatting — the
        # legitimate SET_2DA_ENTRY re-render may change whitespace).
        for name, apr, divisor, thac0 in CLSWPBON_ROWS_LIVE:
            if name not in ("OHTEMPUS", "CLERIC"):
                self.assertEqual(rows[name], (apr, divisor, thac0), name)

    def test_already_granted_is_byte_identical(self) -> None:
        fixture_bytes: dict[str, bytes] = {}

        def build(root: Path) -> None:
            build_specapr_fixture(root, shape="done")
            fixture_bytes["clswpbon"] = (root / "CLSWPBON.2DA").read_bytes()

        run = self.run_component("specapr", build, extra_args=())
        self.assertEqual(self._rows(run.fixture / "CLSWPBON.2DA"), self._rows(run.output / "CLSWPBON.2DA"))

    def test_missing_row_appends_cleric_shaped_row(self) -> None:
        run = self.run_component(
            "specapr",
            lambda root: build_specapr_fixture(root, shape="missing_row"),
            extra_args=(),
            rerun_on_output=True,
        )
        rows = self._rows(run.output / "CLSWPBON.2DA")
        self.assertEqual(rows["OHTEMPUS"], ("1", "0", "3"))
        self.assertEqual(rows["CLERIC"], ("1", "0", "3"))

    def test_missing_cleric_column_and_changed_values_receive_the_decided_apr(self):
        for shape in ("missing_cleric", "no_column", "garbage"):
            with self.subTest(shape=shape):
                run = self.run_component("specapr", lambda root: build_specapr_fixture(root, shape=shape), extra_args=(), rerun_on_output=True)
                table = read_2da(run.output / "CLSWPBON.2DA")
                for name in ("CLERIC", "OHTEMPUS"):
                    self.assertEqual("1", table.cell(name, "GETS_PROF_APR"))
                self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_missing_table_creates_the_owned_rows(self):
        run = self.run_component("specapr", lambda root: root.mkdir(parents=True), extra_args=(), rerun_on_output=True)
        self.assertEqual({"OHTEMPUS":("1","0","3"), "CLERIC":("1","0","3")}, self._rows(run.output / "CLSWPBON.2DA"))

    def test_reordered_extra_and_duplicate_cells_preserve_unrelated_values(self):
        def build(root):
            root.mkdir(parents=True)
            (root / "CLSWPBON.2DA").write_text("2DA V1.0\n0\nFOREIGN GETS_PROF_APR ZERO_SKILL_THAC0 GETS_PROF_APR\nOHTEMPUS keep bad 9 6\nCLERIC stay 3 8 no\nOHTEMPUS again 0 7 4\nMAGE other 0 5 0\n")
        run = self.run_component("specapr", build, extra_args=(), rerun_on_output=True)
        rows = [line.split() for line in (run.output / "CLSWPBON.2DA").read_text().splitlines()[3:]]
        self.assertEqual([["OHTEMPUS","keep","1","9","1"],["CLERIC","stay","1","8","1"],
                          ["OHTEMPUS","again","1","7","1"],["MAGE","other","0","5","0"]], rows)


# ---------------------------------------------------------------------------
# Component 407 — specialization APR (EEex listener)
# ---------------------------------------------------------------------------

# The live install's OHTEMPUS kit id (KIT.IDS 0x4029). Any positive value
# works for the harness — the library stamps whatever it is handed.
EEEX_KIT_ID = "16425"
# Private SPLSTATE.IDS marker the listener uses to make its write idempotent
# per derived-stats rebuild (research/07). 242 is the planned value; the
# library falls back to the next free value below it when it is taken.
PLANNED_STATE = "242"
MARKER_SYMBOL = "CBR_TEMPUS_SPEC_APR"
SPLSTATE_BASE_ROWS = ("9 HOLY_POWER", "246 CBR_TEMPUS_IH", "255 CYNICISM_EQUIPPED")

# Machine-local fallback: EET ships a standalone Lua 5.3 interpreter inside
# the game directory (read-only use). CBR_LUA overrides; PATH is scanned too;
# the compile test skips with a reason when no interpreter is available.
GAME_LUA = Path(r"C:\Games\Baldur's Gate II Enhanced Edition modded\EET\bin\win32\x86_64\lua.exe")


def _find_lua() -> str | None:
    override = os.environ.get("CBR_LUA")
    if override and Path(override).exists():
        return override
    if GAME_LUA.exists():
        return str(GAME_LUA)
    for name in ("lua", "lua5.3", "lua5.1", "luajit"):
        found = shutil.which(name)
        if found:
            return found
    return None


class SpecAprEeexTests(TempusCompletionTestCase):
    """Component 407 takes its file input via argv (the Lua template), not
    from a fixture directory, so it runs HarnessRun directly instead of the
    fixture-copying run_component path."""

    def _run_eeex(
        self,
        kit_id: str,
        template: Path,
        *,
        planned_state: str = PLANNED_STATE,
        splstate_rows: tuple[str, ...] = SPLSTATE_BASE_ROWS,
        expect_success: bool = True,
        rerun_on_output: bool = False,
    ) -> HarnessRun:
        fixture_holder = tempfile.TemporaryDirectory(prefix="cbr-completion-fixture-")
        self.addCleanup(fixture_holder.cleanup)
        fixture_dir = Path(fixture_holder.name) / "fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "SPLSTATE.IDS").write_text(
            "IDS V1.0\n" + "".join(f"{row}\n" for row in splstate_rows),
            encoding="ascii", newline="\n",
        )
        extra = (kit_id, str(template), planned_state)
        run = HarnessRun("specapr_eeex", fixture_dir, extra)
        self.addCleanup(run.cleanup)
        if expect_success and not run.succeeded:
            self.fail(f"harness run failed unexpectedly:\n{run.transcript}")
        if not expect_success:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", run.transcript)
            self.assertFalse((run.output / "CBR_TEST.OK").exists())
        if rerun_on_output:
            second = HarnessRun("specapr_eeex", run.output, extra)
            self.addCleanup(second.cleanup)
            if not second.succeeded:
                self.fail(f"second pass failed:\n{second.transcript}")
            self.assertEqual(
                _raw_tree(run.output), _raw_tree(second.output),
                "library is not byte-idempotent",
            )
        return run

    def test_stamps_kit_id_and_is_idempotent(self) -> None:
        template_text = LUA_TEMPLATE.read_text(encoding="ascii")
        self.assertIn(
            "local CBR_APR_TEMPUS_KIT = %CBR_TEMPUS_KIT_ID%", template_text,
            "the committed template must keep the install-time placeholder",
        )
        self.assertIn(
            "local CBR_APR_MARKER_STATE = %CBR_TEMPUS_SPEC_APR_STATE%", template_text,
            "the committed template must keep the marker-state placeholder",
        )
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, rerun_on_output=True)
        shipped = (run.output / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertIn(f"local CBR_APR_TEMPUS_KIT = {EEEX_KIT_ID}", shipped)
        self.assertIn(f"local CBR_APR_MARKER_STATE = {PLANNED_STATE}", shipped)
        self.assertNotIn("CBR_TEMPUS_KIT_ID", shipped)
        self.assertNotIn("CBR_TEMPUS_SPEC_APR_STATE", shipped)
        ids_text = (run.output / "SPLSTATE.IDS").read_text(encoding="ascii")
        self.assertIn(f"{PLANNED_STATE} {MARKER_SYMBOL}", ids_text)
        self.assertEqual(ids_text.count(MARKER_SYMBOL), 1)
        # The output path renders with platform separators — assert the
        # stable pieces of the summary line instead of the full path.
        self.assertIn("cbr 407: shipped", run.transcript)
        self.assertIn(f"with OHTEMPUS kit id {EEEX_KIT_ID}", run.transcript)
        self.assertIn(f"marker state {PLANNED_STATE}", run.transcript)

    def test_reuses_an_existing_private_state_symbol(self) -> None:
        rows = SPLSTATE_BASE_ROWS + (f"200 {MARKER_SYMBOL}",)
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, splstate_rows=rows, rerun_on_output=True)
        shipped = (run.output / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertIn("local CBR_APR_MARKER_STATE = 200", shipped)
        ids_text = (run.output / "SPLSTATE.IDS").read_text(encoding="ascii")
        self.assertEqual(ids_text.count(MARKER_SYMBOL), 1, "must not append a second row")
        self.assertNotIn(f"{PLANNED_STATE} {MARKER_SYMBOL}", ids_text)

    def test_occupied_planned_state_falls_back_to_next_free_value(self) -> None:
        rows = SPLSTATE_BASE_ROWS + (f"{PLANNED_STATE} SOMEBODY_ELSE",)
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, splstate_rows=rows)
        shipped = (run.output / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertIn("local CBR_APR_MARKER_STATE = 241", shipped)
        ids_text = (run.output / "SPLSTATE.IDS").read_text(encoding="ascii")
        self.assertIn(f"241 {MARKER_SYMBOL}", ids_text)
        self.assertIn(f"{PLANNED_STATE} SOMEBODY_ELSE", ids_text, "foreign row untouched")

    def test_duplicate_or_shared_state_is_reallocated_and_canonicalized(self):
        for rows in ((f"200 {MARKER_SYMBOL}", f"201 {MARKER_SYMBOL}"),
                     (f"200 {MARKER_SYMBOL}", "200 FOREIGN"),
                     (f"999 {MARKER_SYMBOL}",), ()):
            with self.subTest(rows=rows):
                run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, splstate_rows=rows, rerun_on_output=True)
                ids = (run.output / "SPLSTATE.IDS").read_text(encoding="ascii")
                self.assertEqual(1, ids.count(MARKER_SYMBOL))
                chosen = next(int(line.split()[0]) for line in ids.splitlines() if MARKER_SYMBOL in line)
                self.assertTrue(0 <= chosen <= 255)
                if "200 FOREIGN" in rows:
                    self.assertNotEqual(200, chosen)
                    self.assertIn("200 FOREIGN", ids)
                self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_exhaustion_omits_only_the_listener_without_aliasing(self):
        rows = tuple(f"{i} FOREIGN_{i}" for i in range(256)) + (f"242 {MARKER_SYMBOL}",)
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, splstate_rows=rows, rerun_on_output=True)
        self.assertEqual((run.fixture / "SPLSTATE.IDS").read_bytes(), (run.output / "SPLSTATE.IDS").read_bytes())
        shipped = (run.output / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertNotIn("AddListsResolvedListener", shipped)
        self.assertEqual(1, run.transcript.count("no unused SPLSTATE slot"))
        self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_allocator_uses_slots_above_preference_when_lower_slots_are_full(self):
        rows = tuple(f"{i} FOREIGN_{i}" for i in range(243))
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE, splstate_rows=rows, rerun_on_output=True)
        self.assertIn("local CBR_APR_MARKER_STATE = 255", (run.output / "M_CBRAPR.lua").read_text())

    def test_shipped_listener_compiles_and_guards_without_eeex(self) -> None:
        lua = _find_lua()
        if lua is None:
            self.skipTest("no Lua interpreter found (set CBR_LUA to enable)")
        run = self._run_eeex(EEEX_KIT_ID, LUA_TEMPLATE)
        shipped = run.output / "M_CBRAPR.lua"
        compile_check = subprocess.run(
            [lua, "-e", f"assert(loadfile([[{shipped}]]))"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(
            compile_check.returncode, 0,
            f"shipped listener does not compile:\n{compile_check.stderr}",
        )
        # Without EEex globals the file must bow out cleanly at load.
        guard_run = subprocess.run(
            [lua, str(shipped)], capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(guard_run.returncode, 0, guard_run.stderr)
        self.assertIn("EEex not detected", guard_run.stdout)

    def test_bundled_template_is_present(self):
        self.assertTrue(LUA_TEMPLATE.is_file())
        source = LUA_TEMPLATE.read_text(encoding="ascii")
        self.assertIn("%CBR_TEMPUS_KIT_ID%", source)
        self.assertIn("%CBR_TEMPUS_SPEC_APR_STATE%", source)

    def test_missing_kit_omits_only_its_listener(self):
        run = self._run_eeex("0", LUA_TEMPLATE, rerun_on_output=True)
        self.assertNotIn("AddListsResolvedListener", (run.output / "M_CBRAPR.lua").read_text())
        self.assertIn("kit is absent", run.transcript)
        self.assertNotIn("WITH WARNINGS", run.transcript)


# ---------------------------------------------------------------------------
# Component 408 — updated descriptions (KITLIST HELP + SPL desc repoints)
# ---------------------------------------------------------------------------

NEW_REFS = ("700001", "700002", "700003")


class DescriptionsTests(TempusCompletionTestCase):
    @staticmethod
    def _kitlist_help(path: Path) -> dict[str, str]:
        cells: dict[str, str] = {}
        for line in path.read_text(encoding="ascii").splitlines()[3:]:
            tokens = line.split()
            if len(tokens) == 10:
                cells[tokens[1]] = tokens[4]
        return cells

    @staticmethod
    def _spl_desc(path: Path) -> int:
        return struct.unpack_from("<i", path.read_bytes(), 0x50)[0]

    def test_repoint_live_shape(self) -> None:
        run = self.run_component(
            "descriptions",
            lambda root: build_descriptions_fixture(root),
            extra_args=NEW_REFS,
            rerun_on_output=True,
        )
        helps = self._kitlist_help(run.output / "KITLIST.2DA")
        self.assertEqual(helps["OHTEMPUS"], NEW_REFS[0])
        self.assertEqual(helps["TRUECLASS"], "3", "foreign rows untouched")
        self.assertEqual(helps["C0_NINJA"], "502", "foreign rows untouched")
        self.assertEqual(self._spl_desc(run.output / "OHTMPS1.SPL"), int(NEW_REFS[1]))
        self.assertEqual(self._spl_desc(run.output / "OHTMPS2.SPL"), int(NEW_REFS[2]))


    def test_already_repointed_is_byte_identical(self) -> None:
        fixture_bytes: dict[str, bytes] = {}

        def build(root: Path) -> None:
            build_descriptions_fixture(
                root,
                help_value=NEW_REFS[0],
                hp_desc=int(NEW_REFS[1]),
                cob_desc=int(NEW_REFS[2]),
            )
            for name in ("KITLIST.2DA", "OHTMPS1.SPL", "OHTMPS2.SPL"):
                fixture_bytes[name] = (root / name).read_bytes()

        run = self.run_component("descriptions", build, extra_args=NEW_REFS)
        for name in ("OHTMPS1.SPL", "OHTMPS2.SPL"):
            self.assertEqual(fixture_bytes[name], (run.output / name).read_bytes())
        self.assertEqual(NEW_REFS[0], self._kitlist_help(run.output / "KITLIST.2DA")["OHTEMPUS"])

    def test_missing_or_duplicate_kit_rows_and_columns_are_written(self):
        for shape in ("missing_row", "dup_row", "no_help_column"):
            with self.subTest(shape=shape):
                run = self.run_component("descriptions", lambda root: build_descriptions_fixture(root, shape=shape),
                                         extra_args=NEW_REFS, rerun_on_output=True)
                table = read_2da(run.output / "KITLIST.2DA")
                values = [cells[table.columns.index("HELP")] for _,cells in table.rows if cells[table.columns.index("ROWNAME")] == "OHTEMPUS"]
                self.assertTrue(values)
                self.assertTrue(all(value == NEW_REFS[0] for value in values))
                self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_changed_spell_signature_does_not_block_description_write(self):
        run = self.run_component("descriptions", lambda root: build_descriptions_fixture(root, shape="bad_spl"),
                                 extra_args=NEW_REFS, rerun_on_output=True)
        self.assertEqual(int(NEW_REFS[1]), self._spl_desc(run.output / "OHTMPS1.SPL"))
        before = bytearray((run.fixture / "OHTMPS1.SPL").read_bytes())
        struct.pack_into("<I", before, 0x50, int(NEW_REFS[1]))
        self.assertEqual(before, (run.output / "OHTMPS1.SPL").read_bytes())

    def test_zero_is_a_valid_resolved_strref(self):
        run = self.run_component("descriptions", build_descriptions_fixture, extra_args=("0", "0", "0"), rerun_on_output=True)
        self.assertEqual("0", self._kitlist_help(run.output / "KITLIST.2DA")["OHTEMPUS"])
        self.assertEqual(0, self._spl_desc(run.output / "OHTMPS1.SPL"))

    def test_absent_or_unreadable_spell_does_not_block_other_descriptions(self):
        for absent in (False, True):
            with self.subTest(absent=absent):
                def build(root):
                    build_descriptions_fixture(root, help_value="foreign", hp_desc=999, cob_desc=888)
                    path = root / "OHTMPS1.SPL"
                    path.unlink() if absent else path.write_bytes(b"unreadable")
                run = self.run_component("descriptions", build, extra_args=NEW_REFS, rerun_on_output=True)
                self.assertEqual(int(NEW_REFS[2]), self._spl_desc(run.output / "OHTMPS2.SPL"))
                self.assertEqual(NEW_REFS[0], self._kitlist_help(run.output / "KITLIST.2DA")["OHTEMPUS"])
                self.assertNotIn("WITH WARNINGS", run.transcript)

    def test_unsupported_translation_keeps_existing_text_and_logs_once(self):
        run = self.run_component("descriptions", build_descriptions_fixture, extra_args=(*NEW_REFS, "german"), rerun_on_output=True)
        for name in ("KITLIST.2DA", "OHTMPS1.SPL", "OHTMPS2.SPL"):
            self.assertEqual((run.fixture / name).read_bytes(), (run.output / name).read_bytes())
        self.assertEqual(1, run.transcript.count("no german translation"))


if __name__ == "__main__":
    unittest.main()
