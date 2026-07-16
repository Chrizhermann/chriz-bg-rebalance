"""Hermetic --nogame tests for the tempus-completion libraries (400/404/405).

Fixture principle: live-shaped captures over hand-built models. The Chaos of
Battle fixtures are the real vanilla BIF payloads (research/originals/*.orig)
and the real live override copies carrying EE Fixpack's tier-1 chrome trim and
SCS's hostile-AoE casting hooks (*.live). Weapon-training fixtures model both
the pristine Artisan state and the 2026-07-14 live-hotfixed state.
"""

from __future__ import annotations

import shutil
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
ORIGINALS = ROOT / "research" / "originals"

COMPONENT = {"training": "0", "tides": "1", "toll": "2", "specapr": "3"}
COMPONENT_TPA = {
    "training": TRAINING_TPA,
    "tides": TIDES_TPA,
    "toll": TOLL_TPA,
    "specapr": SPEC_APR_TPA,
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
        for name in ("WEAPPROF.2DA", "C0PR#C4.SPL"):
            self.assertEqual(
                (run.fixture / name).read_bytes(),
                (run.output / name).read_bytes(),
                f"{name} must stay byte-identical over the live-hotfixed state",
            )

    def test_semantic_splprot_reuse_skips_append(self) -> None:
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
        self.assertEqual(len(rows), len(SPLPROT_BASE_ROWS) + len(seeded))
        migration = read_spl(run.output / "CBRTMG2.spl")
        base = len(SPLPROT_BASE_ROWS)
        self.assertEqual(
            [effect.parameter2 for effect in migration.abilities[0].effects],
            [base, base + 1, base + 2],
        )

    def test_missing_ohtempus_column_fails_before_writes(self) -> None:
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(root, drop_ohtempus_column=True),
            extra_args=(str(LS_PERM_STAT),),
            expect_success=False,
        )
        self.assertIn("no OHTEMPUS column header", run.transcript)

    def test_missing_axe_pair_fails(self) -> None:
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(root, grant_shape="no_axe_pair"),
            extra_args=(str(LS_PERM_STAT),),
            expect_success=False,
        )
        self.assertIn("exactly one Artisan axe permission gate", run.transcript)

    def test_duplicated_longsword_gate_fails(self) -> None:
        run = self.run_component(
            "training",
            lambda root: build_training_fixture(root, grant_shape="duplicate_longsword_gate"),
            extra_args=(str(LS_PERM_STAT),),
            expect_success=False,
        )
        self.assertIn("duplicated longsword/crossbow grants", run.transcript)


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

    def test_foreign_dispatcher_fails(self) -> None:
        def build(root: Path) -> None:
            build_tides_fixture(root)
            dispatcher = read_spl(root / "OHTMPS2.SPL")
            patched = dispatcher.abilities[0].effects[0].to_bytes()
            data = bytearray((root / "OHTMPS2.SPL").read_bytes())
            offset = data.find(patched)
            data[offset + 0x14 : offset + 0x1C] = b"FOREIGN\0"
            (root / "OHTMPS2.SPL").write_bytes(bytes(data))

        run = self.run_component(
            "tides", build, extra_args=TIDE_STRREFS, expect_success=False
        )
        self.assertIn("not the recognized vanilla", run.transcript)

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

    def test_conflicting_clab_row_fails(self) -> None:
        run = self.run_component(
            "toll",
            lambda root: build_toll_fixture(root, conflicting_row=True),
            extra_args=("5", *TOLL_SPELLS),
            expect_success=False,
        )
        self.assertIn("CBR_DIVTOLL level 1 holds", run.transcript)

    def test_zero_count_fails(self) -> None:
        run = self.run_component(
            "toll",
            lambda root: build_toll_fixture(root),
            extra_args=("0",),
            expect_success=False,
        )
        self.assertIn("between 1 and 99", run.transcript)

    def test_oversized_resref_fails(self) -> None:
        run = self.run_component(
            "toll",
            lambda root: build_toll_fixture(root),
            extra_args=("1", "WAYTOOLONGNAME"),
            expect_success=False,
        )
        self.assertIn("is not a valid resref", run.transcript)


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
        self.assertIn(
            "OHTEMPUS GETS_PROF_APR was 0 (cells changed: 1; row appended: 0); "
            "CLERIC was 0 (cells changed: 1)",
            run.transcript,
        )

    def test_already_granted_is_byte_identical(self) -> None:
        fixture_bytes: dict[str, bytes] = {}

        def build(root: Path) -> None:
            build_specapr_fixture(root, shape="done")
            fixture_bytes["clswpbon"] = (root / "CLSWPBON.2DA").read_bytes()

        run = self.run_component("specapr", build, extra_args=())
        self.assertEqual(
            (run.output / "CLSWPBON.2DA").read_bytes(), fixture_bytes["clswpbon"]
        )
        self.assertIn(
            "OHTEMPUS GETS_PROF_APR was 1 (cells changed: 0; row appended: 0); "
            "CLERIC was 1 (cells changed: 0)",
            run.transcript,
        )

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
        self.assertIn(
            "OHTEMPUS GETS_PROF_APR was absent (cells changed: 0; row appended: 1); "
            "CLERIC was 0 (cells changed: 1)",
            run.transcript,
        )

    def test_missing_cleric_row_fails(self) -> None:
        run = self.run_component(
            "specapr",
            lambda root: build_specapr_fixture(root, shape="missing_cleric"),
            extra_args=(),
            expect_success=False,
        )
        self.assertIn("no CLERIC row", run.transcript)

    def test_missing_column_fails(self) -> None:
        run = self.run_component(
            "specapr",
            lambda root: build_specapr_fixture(root, shape="no_column"),
            extra_args=(),
            expect_success=False,
        )
        self.assertIn("no GETS_PROF_APR header column", run.transcript)

    def test_non_boolean_value_fails(self) -> None:
        run = self.run_component(
            "specapr",
            lambda root: build_specapr_fixture(root, shape="garbage"),
            extra_args=(),
            expect_success=False,
        )
        self.assertIn("holds yes (expected 0 or 1)", run.transcript)


if __name__ == "__main__":
    unittest.main()
