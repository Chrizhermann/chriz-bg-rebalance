from __future__ import annotations

import dataclasses
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import (
    EffV2,
    IdsFile,
    SplAbility,
    SplEffect,
    SplFile,
    TwoDA,
    canonical_resource_tree,
    make_spl,
    read_eff_v2,
    read_ids,
    read_spl,
    read_2da,
    spell_resref,
    write_ids,
    write_spl,
    write_2da,
)


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "tempus_holy_power_harness.tp2"
PRODUCTION_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_holy_power.tpa"
SETUP_TP2 = ROOT / "setup-chriz-bg-rebalance.tp2"
ORIGINALS = ROOT / "research" / "originals"

HOLY_RESREF = "OHTMPS1"
CLAB_NAME = "OHTEMPUS.2DA"
PRIVATE_PREFIX = "CBR"
SENTINEL_RESOURCE = "CBRSENT"


@dataclasses.dataclass
class Fixture:
    root: Path
    divine_resref: str
    haste_resref: str


@dataclasses.dataclass
class HarnessResult:
    temporary: tempfile.TemporaryDirectory[str]
    fixture: Fixture
    output: Path
    run_dir: Path
    mode: str
    variant: str
    process: subprocess.CompletedProcess[str]

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}".strip()

    @property
    def succeeded(self) -> bool:
        return (
            self.process.returncode == 0
            and (self.output / "CBR_TEST.OK").is_file()
            and "SUCCESSFULLY INSTALLED" in self.transcript
        )


def _replace_resource(effect: SplEffect, old: str, new: str) -> SplEffect:
    if effect.resource.upper() == old.upper():
        return dataclasses.replace(effect, resource=new)
    return effect


def _sentinel_effect() -> SplEffect:
    return SplEffect(
        opcode=400,
        target=1,
        power=4,
        parameter1=0x13579,
        parameter2=0x24680,
        timing=1,
        resist_dispel=2,
        duration=0,
        probability1=100,
        probability2=0,
        resource=SENTINEL_RESOURCE,
        save_type=0x1020304,
        save_bonus=-7,
        special=0x55667788,
    )


def _rename_spell_resources(spell: SplFile, old: str, new: str) -> SplFile:
    abilities = []
    for ability in spell.abilities:
        effects = tuple(_replace_resource(effect, old, new) for effect in ability.effects)
        abilities.append(dataclasses.replace(ability, effects=effects))
    casting = tuple(_replace_resource(effect, old, new) for effect in spell.casting_effects)
    return dataclasses.replace(spell, abilities=tuple(abilities), casting_effects=casting)


def _make_holy_fixture(divine_resref: str) -> SplFile:
    spell = read_spl(ORIGINALS / "OHTMPS1.spl.orig")
    spell = _rename_spell_resources(spell, "SPPR412", divine_resref)
    abilities = list(spell.abilities)
    abilities[9] = dataclasses.replace(
        abilities[9], effects=abilities[9].effects + (_sentinel_effect(),)
    )
    return dataclasses.replace(spell, abilities=tuple(abilities))


def _make_divine_fixture(divine_resref: str) -> SplFile:
    spell = read_spl(ORIGINALS / "SPPR412.spl.orig")
    spell = _rename_spell_resources(spell, "SPPR412", divine_resref)
    abilities = list(spell.abilities)
    abilities[3] = dataclasses.replace(
        abilities[3], effects=abilities[3].effects + (_sentinel_effect(),)
    )
    return dataclasses.replace(spell, abilities=tuple(abilities))


def _improved_haste_fixture(
    variant: str, haste_resref: str
) -> tuple[SplFile, dict[str, SplFile]]:
    base = read_spl(ORIGINALS / "SPWI613.spl.orig")
    base = _rename_spell_resources(base, "SPWI613", haste_resref)
    ability = base.abilities[0]
    effects = list(ability.effects)
    additive_index = next(
        i
        for i, effect in enumerate(effects)
        if effect.opcode == 1 and effect.parameter1 == 1 and effect.parameter2 == 0
    )
    additive = effects[additive_index]
    true_haste = dataclasses.replace(additive, opcode=16, parameter1=0, parameter2=1)
    helpers: dict[str, SplFile] = {}

    if variant == "additive":
        pass
    elif variant == "doubling":
        effects[additive_index] = true_haste
    elif variant == "doubling317":
        effects[additive_index] = dataclasses.replace(true_haste, opcode=317)
    elif variant == "mixed":
        effects.insert(additive_index + 1, true_haste)
    elif variant == "duplicate_additive":
        effects.insert(additive_index + 1, additive)
    elif variant == "missing":
        del effects[additive_index]
    elif variant == "probabilistic":
        effects[additive_index] = dataclasses.replace(additive, probability1=50)
    elif variant == "conditional":
        helper_resref = "CBRIHCON"
        effects[additive_index] = dataclasses.replace(
            additive,
            opcode=326,
            parameter1=9,
            parameter2=0,
            timing=1,
            duration=0,
            resource=helper_resref,
        )
        helpers[helper_resref] = make_spl(
            (
                SplAbility(
                    required_level=1,
                    target=5,
                    projectile=0,
                    effects=(additive,),
                ),
            )
        )
    elif variant == "inconsistent":
        first = dataclasses.replace(ability, effects=tuple(effects), required_level=1)
        second_effects = list(effects)
        second_effects[additive_index] = true_haste
        second = dataclasses.replace(
            ability, effects=tuple(second_effects), required_level=10
        )
        return dataclasses.replace(base, abilities=(first, second)), helpers
    else:
        raise ValueError(f"unknown Improved Haste variant: {variant}")

    return (
        dataclasses.replace(
            base, abilities=(dataclasses.replace(ability, effects=tuple(effects)),)
        ),
        helpers,
    )


def build_fixture(
    root: Path,
    variant: str,
    *,
    divine_id: int = 1499,
    haste_id: int = 2699,
) -> Fixture:
    root.mkdir(parents=True, exist_ok=True)
    ids = IdsFile(
        entries=(
            (divine_id, "CLERIC_HOLY_POWER"),
            (haste_id, "WIZARD_IMPROVED_HASTE"),
            (2998, "WIZARD_FIXTURE_SENTINEL"),
        )
    )
    write_ids(root / "SPELL.IDS", ids)
    divine_resref = spell_resref(divine_id, "CLERIC_HOLY_POWER")
    haste_resref = spell_resref(haste_id, "WIZARD_IMPROVED_HASTE")

    write_spl(root / f"{HOLY_RESREF}.SPL", _make_holy_fixture(divine_resref))
    write_spl(root / f"{divine_resref}.SPL", _make_divine_fixture(divine_resref))
    haste, helpers = _improved_haste_fixture(variant, haste_resref)
    write_spl(root / f"{haste_resref}.SPL", haste)
    for resref, helper in helpers.items():
        write_spl(root / f"{resref}.SPL", helper)

    shutil.copyfile(ORIGINALS / "OHTEMPUS.2da.orig", root / CLAB_NAME)
    write_ids(
        root / "SPLSTATE.IDS",
        IdsFile(
            entries=tuple((value, f"FIXTURE_STATE_{value}") for value in range(32))
            + ((68, "BUFF_ENHANCEMENT"), (200, "FOREIGN_200"), (254, "FOREIGN_254"))
        ),
    )
    write_2da(
        root / "SPLPROT.2DA",
        TwoDA(
            default="0xffff",
            columns=("STAT", "VALUE", "RELATION"),
            rows=(
                ("0_KEEP", ("0x10a", "0", "4")),
                ("1_STATE_N", ("0x112", "-1", "1")),
                ("2_STR_LT_N", ("36", "-1", "2")),
                ("3_SENTINEL", ("999", "123", "5")),
            ),
        ),
    )
    return Fixture(root=root, divine_resref=divine_resref, haste_resref=haste_resref)


PHASE_COMPONENT = {"full": "1", "classify": "2", "allocate": "3", "progression": "4", "bridge": "5"}


def _run_harness(
    variant: str,
    mode: str,
    *,
    alternate_ids: bool = False,
    phase: str = "full",
) -> HarnessResult:
    temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-")
    base = Path(temporary.name)
    fixture_root = base / "fixture"
    output = base / "output"
    run_dir = base / "weidu-run"
    output.mkdir()
    run_dir.mkdir()
    fixture = build_fixture(
        fixture_root,
        variant,
        divine_id=1388 if alternate_ids else 1499,
        haste_id=2788 if alternate_ids else 2699,
    )
    command = [
        str(WEIDU),
        str(HARNESS),
        "--nogame",
        "--force-install-list",
        PHASE_COMPONENT[phase],
        "--args",
        str(PRODUCTION_TPA),
        "--args",
        str(fixture.root),
        "--args",
        str(output),
        "--args",
        mode,
        "--args",
        fixture.divine_resref,
        "--args",
        fixture.haste_resref,
        "--no-exit-pause",
        "--quick-log",
    ]
    process = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    return HarnessResult(
        temporary=temporary,
        fixture=fixture,
        output=output,
        run_dir=run_dir,
        mode=mode,
        variant=variant,
        process=process,
    )


def _rerun_harness(previous: HarnessResult, *, phase: str = "full") -> HarnessResult:
    temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-second-")
    base = Path(temporary.name)
    fixture_root = base / "fixture"
    output = base / "output"
    run_dir = base / "weidu-run"
    shutil.copytree(previous.output, fixture_root)
    output.mkdir()
    run_dir.mkdir()
    fixture = Fixture(
        root=fixture_root,
        divine_resref=previous.fixture.divine_resref,
        haste_resref=previous.fixture.haste_resref,
    )
    command = [
        str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", PHASE_COMPONENT[phase],
        "--args", str(PRODUCTION_TPA), "--args", str(fixture_root), "--args", str(output),
        "--args", previous.mode, "--args", fixture.divine_resref, "--args", fixture.haste_resref,
        "--no-exit-pause", "--quick-log",
    ]
    process = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    return HarnessResult(
        temporary=temporary,
        fixture=fixture,
        output=output,
        run_dir=run_dir,
        mode=previous.mode,
        variant=previous.variant,
        process=process,
    )


class FixtureFormatTests(unittest.TestCase):
    def test_preserved_spl_and_2da_fixtures_parse(self) -> None:
        holy = read_spl(ORIGINALS / "OHTMPS1.spl.orig")
        divine = read_spl(ORIGINALS / "SPPR412.spl.orig")
        haste = read_spl(ORIGINALS / "SPWI613.spl.orig")
        clab = read_2da(ORIGINALS / "OHTEMPUS.2da.orig")

        self.assertEqual(20, len(holy.abilities))
        self.assertEqual(list(range(1, 21)), [a.required_level for a in holy.abilities])
        self.assertEqual(14, len(divine.abilities))
        self.assertEqual(1, len(haste.abilities))
        self.assertEqual(
            1,
            sum(
                effect.opcode == 1
                and effect.parameter1 == 1
                and effect.parameter2 == 0
                for effect in haste.abilities[0].effects
            ),
        )
        self.assertEqual("GA_OHTMPS1", clab.cell("ABILITY1", "26"))
        self.assertEqual("AP_CDHLYSYM", clab.cell("ABILITY1", "25"))

    def test_semantic_spl_variants_and_eff_v2_round_trip(self) -> None:
        for variant in (
            "additive",
            "doubling",
            "doubling317",
            "mixed",
            "duplicate_additive",
            "missing",
            "probabilistic",
            "conditional",
            "inconsistent",
        ):
            with self.subTest(variant=variant):
                spell, _ = _improved_haste_fixture(variant, "SPWI699")
                self.assertEqual(spell, SplFile.from_bytes(spell.to_bytes()))

        effect = EffV2(
            opcode=326,
            target=1,
            power=0,
            parameter1=201,
            parameter2=7,
            timing=1,
            duration=0,
            probability1=100,
            probability2=0,
            resource="CBRTEST",
        )
        self.assertEqual(effect, EffV2.from_bytes(effect.to_bytes()))

    def test_ids_resolution_uses_fixture_symbols(self) -> None:
        ids = IdsFile(entries=((1388, "CLERIC_HOLY_POWER"), (2788, "WIZARD_IMPROVED_HASTE")))
        self.assertEqual(1388, ids.value("cleric_holy_power"))
        self.assertEqual("SPPR388", spell_resref(ids.value("CLERIC_HOLY_POWER"), "CLERIC_HOLY_POWER"))
        self.assertEqual("SPWI788", spell_resref(ids.value("WIZARD_IMPROVED_HASTE"), "WIZARD_IMPROVED_HASTE"))


class HarnessSmokeTests(unittest.TestCase):
    def test_nogame_smoke_copies_without_game_or_tlk(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-weidu-smoke-") as temporary:
            root = Path(temporary)
            run_dir = root / "run"
            run_dir.mkdir()
            output = root / "smoke.out"
            command = [
                str(WEIDU),
                str(HARNESS),
                "--nogame",
                "--force-install-list",
                "0",
                "--args",
                str(ORIGINALS / "OHTEMPUS.2da.orig"),
                "--args",
                str(output),
                "--no-exit-pause",
                "--quick-log",
            ]
            process = subprocess.run(
                command,
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, process.returncode, process.stdout + process.stderr)
            self.assertEqual(
                (ORIGINALS / "OHTEMPUS.2da.orig").read_bytes(), output.read_bytes()
            )
            self.assertFalse(any(root.rglob("dialog.tlk")))
            self.assertFalse(any(root.rglob("chitin.key")))
            harness_source = HARNESS.read_text(encoding="utf-8").upper()
            self.assertNotIn("COPY_EXISTING", harness_source)
            self.assertNotIn("FILE_EXISTS_IN_GAME", harness_source)


class TempusHolyPowerTests(unittest.TestCase):
    _results: list[HarnessResult] = []

    @classmethod
    def tearDownClass(cls) -> None:
        for result in cls._results:
            result.temporary.cleanup()

    def run_case(
        self,
        variant: str = "additive",
        mode: str = "auto",
        *,
        alternate_ids: bool = False,
        phase: str = "full",
    ) -> HarnessResult:
        result = _run_harness(variant, mode, alternate_ids=alternate_ids, phase=phase)
        self._results.append(result)
        return result

    def assert_success(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                f"{result.variant}/{result.mode}: missing production library "
                f"{PRODUCTION_TPA}; isolated harness transcript:\n{result.transcript}"
            )
        self.assertTrue(
            result.succeeded,
            f"{result.variant}/{result.mode}: transformation failed\n{result.transcript}",
        )

    def assert_rejected(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                f"{result.variant}/{result.mode}: cannot verify semantic rejection because "
                f"production library is missing: {PRODUCTION_TPA}\n{result.transcript}"
            )
        self.assertFalse(
            result.succeeded,
            f"{result.variant}/{result.mode}: malformed Improved Haste was accepted",
        )
        transcript = result.transcript.upper()
        self.assertIn(result.fixture.haste_resref, transcript)
        self.assertRegex(transcript, r"IMPROVED[ _-]?HASTE|HEADER|OPCODE|PROBABIL")

    def test_improved_haste_classification(self) -> None:
        for variant in ("additive", "doubling", "doubling317"):
            with self.subTest(variant=variant, expected="accepted"):
                self.assert_success(self.run_case(variant, "auto", phase="classify"))
        for variant in ("mixed", "duplicate_additive", "missing", "probabilistic", "conditional", "inconsistent"):
            for mode in ("auto", "force_double", "force_additive"):
                with self.subTest(variant=variant, mode=mode, expected="rejected"):
                    self.assert_rejected(self.run_case(variant, mode, phase="classify"))

    def test_auto_vs_forced_modes(self) -> None:
        self.assert_success(self.run_case("additive", "auto", phase="classify"))
        self.assert_success(self.run_case("additive", "force_additive", phase="classify"))
        self.assert_rejected(self.run_case("additive", "force_double", phase="classify"))
        self.assert_success(self.run_case("doubling", "auto", phase="classify"))
        self.assert_success(self.run_case("doubling", "force_double", phase="classify"))
        self.assert_rejected(self.run_case("doubling", "force_additive", phase="classify"))

    def test_state_and_splprot_allocation(self) -> None:
        result = self.run_case(phase="allocate")
        self.assert_success(result)
        before_ids = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after_ids = read_ids(result.output / "SPLSTATE.IDS")
        private = [(value, symbol) for value, symbol in after_ids.entries if symbol.upper().startswith("CBR_")]
        self.assertGreaterEqual(len(private), 4)
        self.assertEqual(len(private), len({value for value, _ in private}))
        self.assertTrue({value for value, _ in private}.isdisjoint(before_ids.values()))

        before = read_2da(result.fixture.root / "SPLPROT.2DA")
        after = read_2da(result.output / "SPLPROT.2DA")
        self.assertEqual(before.rows, after.rows[: len(before.rows)], "SPLPROT must be append-only")
        semantics = [tuple(int(value, 0) for value in row) for _, row in after.rows]
        for required in ((0x112, -1, 1), (36, -1, 2), (36, -1, 1), (37, -1, 2)):
            with self.subTest(required=required):
                self.assertEqual(1, semantics.count(required))
        second = _rerun_harness(result, phase="allocate")
        self._results.append(second)
        self.assert_success(second)
        self.assertEqual(after_ids.canonical(), read_ids(second.output / "SPLSTATE.IDS").canonical())
        self.assertEqual(after.canonical(), read_2da(second.output / "SPLPROT.2DA").canonical())

    def test_progression(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        self.assertEqual(30, len(holy.abilities))
        self.assertEqual(list(range(1, 31)), [a.required_level for a in holy.abilities])
        self.assertEqual(holy.abilities[-1], holy.ability_for_level(31))
        self.assertEqual(holy.abilities[-1], holy.ability_for_level(50))

        for level in range(1, 31):
            with self.subTest(level=level):
                duration = _tier_duration(level)
                thac0 = max(0, 21 - level)
                hp = min(level, 30)
                apr_key = None if level <= 6 else 6 if level <= 12 else 1 if level <= 24 else 7
                effects = holy.ability_for_level(level).effects
                thac0_effect = next(e for e in effects if e.opcode == 54 and e.parameter2 == 1)
                hp_effect = next(e for e in effects if e.opcode == 18 and e.parameter2 == 0)
                self.assertEqual((thac0, duration), (thac0_effect.parameter1, thac0_effect.duration))
                self.assertEqual((hp, duration), (hp_effect.parameter1, hp_effect.duration))
                self.assertEqual(3, thac0_effect.resist_dispel)
                self.assertEqual(3, hp_effect.resist_dispel)
                apr = [e for e in effects if e.opcode == 1 and e.parameter2 == 0]
                if apr_key is None:
                    self.assertEqual([], apr)
                else:
                    self.assertEqual([(apr_key, duration)], [(e.parameter1, e.duration) for e in apr])
                    self.assertTrue(all(e.resist_dispel == 3 for e in apr))

    def test_strength_floor(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        for level, floor, exceptional, duration in ((1, 18, 100, 18), (7, 18, 100, 24), (13, 19, 0, 30), (19, 20, 0, 30), (25, 21, 0, 30)):
            with self.subTest(level=level):
                effects = holy.ability_for_level(level).effects
                self.assertFalse(any(e.opcode in (44, 97) for e in effects), "floor may not be an unconditional flat set")
                pulses = [e for e in effects if e.opcode == 272 and e.parameter1 == 1 and e.parameter2 == 3]
                self.assertTrue(any(e.duration == duration for e in pulses), "missing full-duration one-second floor heartbeat")
                evaluator = _ConditionGraph(result.output)
                immediate = evaluator.apply_immediate(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), immediate, "missing immediate Strength-floor kick")
                low = evaluator.apply_ability(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), low)
                if floor == 18:
                    self.assertEqual(
                        (18, 100),
                        evaluator.apply_immediate(
                            holy.ability_for_level(level), strength=18, exceptional=50
                        ),
                    )
                high = evaluator.apply_ability(holy.ability_for_level(level), strength=floor + 1, exceptional=0)
                self.assertEqual((floor + 1, 0), high, "floor lowered a higher Strength")
                restored = evaluator.apply_heartbeat(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), restored, "heartbeat cannot restore floor after stronger temporary Strength expires")

    def test_clab_cap(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        before = read_2da(result.fixture.root / CLAB_NAME)
        after = read_2da(result.output / CLAB_NAME)
        cleared = {"26", "31", "36", "41", "46"}
        for column in ("1", "6", "11", "16", "21"):
            self.assertEqual("GA_OHTMPS1", after.cell("ABILITY1", column))
        for column in cleared:
            self.assertEqual("****", after.cell("ABILITY1", column))
        self.assertEqual("AP_CDHLYSYM", after.cell("ABILITY1", "25"))
        for row_name, values in before.rows:
            for column, value in zip(before.columns, values):
                if row_name == "ABILITY1" and column in cleared:
                    continue
                self.assertEqual(value, after.cell(row_name, column), f"changed {row_name}/{column}")

    def test_preserves_foreign_effects(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        before = read_spl(result.fixture.root / f"{HOLY_RESREF}.SPL")
        after = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        self.assertEqual(before.spell_icon, after.spell_icon)
        for level in range(1, 31):
            source = before.ability_for_level(min(level, 20))
            target = after.ability_for_level(level)
            self.assertEqual(source.icon, target.icon)
            for effect in source.effects:
                preserved = (
                    effect.opcode in (50, 141, 142, 174, 282)
                    or (effect.opcode == 328 and effect.parameter2 in (9, 68))
                    or effect.resource.upper() == SENTINEL_RESOURCE
                )
                if preserved:
                    if effect.resource.upper() == SENTINEL_RESOURCE:
                        self.assertIn(
                            effect.to_bytes(),
                            [candidate.to_bytes() for candidate in target.effects],
                            "unknown sentinel effect was not byte-preserved",
                        )
                    else:
                        key = effect.preservation_key()
                        self.assertIn(key, [candidate.preservation_key() for candidate in target.effects])

    def test_divine_power_exclusion(self) -> None:
        result = self.run_case(alternate_ids=True, phase="bridge")
        self.assert_success(result)
        ids = read_ids(result.output / "SPELL.IDS")
        divine_resref = spell_resref(ids.value("CLERIC_HOLY_POWER"), "CLERIC_HOLY_POWER")
        self.assertEqual(result.fixture.divine_resref, divine_resref)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        divine_before = read_spl(result.fixture.root / f"{divine_resref}.SPL")
        divine = read_spl(result.output / f"{divine_resref}.SPL")
        self.assertEqual(len(divine_before.abilities), len(divine.abilities))
        for ability in holy.abilities:
            self.assertEqual((321, divine_resref), (ability.effects[0].opcode, ability.effects[0].resource.upper()))
            self.assertEqual((321, HOLY_RESREF), (ability.effects[1].opcode, ability.effects[1].resource.upper()))
        for before_ability, ability in zip(divine_before.abilities, divine.abilities):
            self.assertEqual((321, HOLY_RESREF), (ability.effects[0].opcode, ability.effects[0].resource.upper()))
            self.assertEqual((321, divine_resref), (ability.effects[1].opcode, ability.effects[1].resource.upper()))
            self.assertEqual(
                tuple(effect.canonical() for effect in before_ability.effects),
                tuple(effect.canonical() for effect in ability.effects[1:]),
                "reciprocal cleanup changed an existing Divine Power effect",
            )

    def test_additive_bridge_graph(self) -> None:
        result = self.run_case("additive", "auto", phase="bridge")
        self.assert_success(result)
        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        donor = next(e for e in haste.abilities[0].effects if e.opcode == 1 and e.parameter1 == 1 and e.parameter2 == 0)
        haste_before = read_spl(result.fixture.root / f"{result.fixture.haste_resref}.SPL")
        for effect in haste_before.abilities[0].effects:
            self.assertIn(
                effect.canonical(),
                [candidate.canonical() for candidate in haste.abilities[0].effects],
                "additive bridge replaced a foreign Improved Haste effect",
            )
        self.assertFalse(any(e.opcode in (16, 317) and e.parameter2 == 1 for e in haste.abilities[0].effects))
        markers = [e for e in haste.abilities[0].effects if e.opcode == 328 and e.special == 1]
        self.assertEqual(1, len(markers))
        marker = markers[0]
        self.assertEqual(donor.delivery_key(), marker.delivery_key())
        self.assertEqual(donor.parameter1, marker.parameter1)

        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        state_values = {value for value, symbol in read_ids(result.output / "SPLSTATE.IDS").entries if symbol.upper().startswith("CBR_")}
        tier_states = set()
        for level, apr_key in ((7, 6), (13, 1), (25, 7)):
            ability = holy.ability_for_level(level)
            tier = [e.parameter2 for e in ability.effects if e.opcode == 328 and e.special == 1 and e.parameter2 in state_values]
            self.assertEqual(1, len(tier))
            tier_states.add(tier[0])
            pulses = [e for e in ability.effects if e.opcode == 272 and e.parameter1 == 1 and e.parameter2 == 3]
            self.assertTrue(
                any(
                    e.duration == _tier_duration(level)
                    and _resource_apr_key(result.output, e.resource) == apr_key
                    for e in pulses
                )
            )
            self.assertTrue(
                any(
                    e.opcode == 326
                    and e.timing == 1
                    and e.parameter1 == marker.parameter2
                    and _resource_apr_key(result.output, e.resource) == apr_key
                    for e in ability.effects
                ),
                "Holy cast second lacks an immediate Improved Haste kick",
            )
        kicks = {
            e.parameter1: _resource_apr_key(result.output, e.resource)
            for e in haste.abilities[0].effects
            if e.opcode == 326 and e.timing == 1
        }
        self.assertTrue(tier_states.issubset(kicks), "Improved Haste lacks immediate kicks for active Holy tiers")
        self.assertEqual({1, 6, 7}, {kicks[state] for state in tier_states})

        for helper_resref, apr_key in _apr_helpers(result.output).items():
            helper = read_spl(result.output / f"{helper_resref}.SPL")
            effects = helper.abilities[0].effects
            self.assertEqual((321, helper_resref), (effects[0].opcode, effects[0].resource.upper()))
            apr = next(e for e in effects if e.opcode == 1 and e.parameter1 == apr_key)
            self.assertEqual((0, 1, 0), (apr.timing, apr.duration, apr.parameter2))
            self.assertEqual(2, apr.resist_dispel & 2)

    def test_doubling_needs_no_bridge(self) -> None:
        result = self.run_case("doubling", "auto", phase="bridge")
        self.assert_success(result)
        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        effects = haste.abilities[0].effects
        self.assertTrue(any(e.opcode in (16, 317) and e.parameter2 == 1 for e in effects))
        self.assertFalse(any(e.opcode == 1 and e.parameter1 == 1 and e.parameter2 == 0 for e in effects))
        self.assertFalse(any(e.opcode == 328 and e.special == 1 for e in effects))
        self.assertEqual({}, _apr_helpers(result.output), "doubling mode created additive bridge resources")
        self.assertEqual(
            (result.fixture.root / f"{result.fixture.haste_resref}.SPL").read_bytes(),
            (result.output / f"{result.fixture.haste_resref}.SPL").read_bytes(),
            "doubling mode rewrote Improved Haste",
        )
        self.assertEqual(
            (result.fixture.root / "SPLSTATE.IDS").read_bytes(),
            (result.output / "SPLSTATE.IDS").read_bytes(),
            "doubling mode allocated bridge states",
        )

    def test_idempotent_second_application(self) -> None:
        for variant in ("additive", "doubling"):
            with self.subTest(variant=variant):
                first = self.run_case(variant)
                self.assert_success(first)
                second = _rerun_harness(first)
                self._results.append(second)
                self.assert_success(second)
                self.assertEqual(
                    canonical_resource_tree(first.output), canonical_resource_tree(second.output)
                )

    def test_no_tlk_operations_in_components_401_403(self) -> None:
        setup_source = _strip_weidu_comments(SETUP_TP2.read_text(encoding="utf-8"))
        blocks = []
        for component in (401, 402, 403):
            match = re.search(
                rf"(?ms)^BEGIN\b.*?^DESIGNATED\s+{component}\b.*?(?=^BEGIN\b|\Z)",
                setup_source,
            )
            self.assertIsNotNone(match, f"component {component} does not exist")
            blocks.append(match.group(0))
        self.assertTrue(PRODUCTION_TPA.is_file(), f"missing {PRODUCTION_TPA}")
        source = "\n".join(blocks) + "\n" + _strip_weidu_comments(PRODUCTION_TPA.read_text(encoding="utf-8"))
        for banned in (r"\bSAY\b", r"\bSTRING_SET\b", r"\bRESOLVE_STR_REF\b", r"DIALOG\.TLK", r"\bTLK_(?:APPEND|WRITE|PATCH)\b"):
            with self.subTest(banned=banned):
                self.assertIsNone(re.search(banned, source, re.IGNORECASE))
        harness_source = _strip_weidu_comments(HARNESS.read_text(encoding="utf-8"))
        for banned in (r"\bCOPY_EXISTING\b", r"\bFILE_EXISTS_IN_GAME\b", r"\bSAY\b", r"\bSTRING_SET\b", r"DIALOG\.TLK"):
            self.assertIsNone(re.search(banned, harness_source, re.IGNORECASE))


class _ConditionGraph:
    """Evaluate only fixture SPLPROT/op326 resource branches; this is not engine simulation."""

    def __init__(self, root: Path):
        self.root = root
        self.protection = read_2da(root / "SPLPROT.2DA")

    def _row(self, index: int) -> tuple[int, int, int]:
        _, values = self.protection.rows[index]
        return tuple(int(value, 0) for value in values)  # type: ignore[return-value]

    def _matches(self, effect: SplEffect | EffV2, strength: int, exceptional: int) -> bool:
        stat, table_value, relation = self._row(effect.parameter2)
        actual = {36: strength, 37: exceptional}.get(stat)
        if actual is None:
            return False
        expected = effect.parameter1 if table_value == -1 else table_value
        return {0: actual <= expected, 1: actual == expected, 2: actual < expected, 3: actual > expected, 4: actual >= expected, 5: actual != expected}[relation]

    def _resource_effects(self, resource: str) -> tuple[SplEffect | EffV2, ...]:
        spl_path = self.root / f"{resource}.SPL"
        if spl_path.is_file():
            return read_spl(spl_path).abilities[0].effects
        eff_path = self.root / f"{resource}.EFF"
        if eff_path.is_file():
            return (read_eff_v2(eff_path),)
        return ()

    def _apply(self, effects: tuple[SplEffect | EffV2, ...], strength: int, exceptional: int, depth: int = 0) -> tuple[int, int]:
        if depth > 12:
            raise AssertionError("conditional helper graph cycle")
        for effect in effects:
            if effect.opcode == 326 and self._matches(effect, strength, exceptional):
                strength, exceptional = self._apply(self._resource_effects(effect.resource), strength, exceptional, depth + 1)
            elif effect.opcode == 272:
                strength, exceptional = self._apply(self._resource_effects(effect.resource), strength, exceptional, depth + 1)
            elif effect.opcode == 44 and effect.parameter2 == 1:
                strength = effect.parameter1
            elif effect.opcode == 97 and effect.parameter2 == 1:
                exceptional = effect.parameter1
        return strength, exceptional

    def apply_ability(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        return self._apply(ability.effects, strength, exceptional)

    def apply_immediate(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        checks = tuple(effect for effect in ability.effects if effect.opcode == 326)
        return self._apply(checks, strength, exceptional)

    def apply_heartbeat(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        pulses = tuple(effect for effect in ability.effects if effect.opcode == 272)
        return self._apply(pulses, strength, exceptional)


def _resource_apr_key(root: Path, resource: str, seen: frozenset[str] = frozenset()) -> int | None:
    resource = resource.upper()
    if not resource or resource in seen:
        return None
    seen = seen | {resource}
    spl_path = root / f"{resource}.SPL"
    if spl_path.is_file():
        effects: tuple[SplEffect | EffV2, ...] = read_spl(spl_path).abilities[0].effects
    else:
        eff_path = root / f"{resource}.EFF"
        if not eff_path.is_file():
            return None
        effects = (read_eff_v2(eff_path),)
    for effect in effects:
        if effect.opcode == 1 and effect.parameter2 == 0 and effect.duration == 1:
            return effect.parameter1
        if effect.opcode in (146, 177, 272, 326):
            found = _resource_apr_key(root, effect.resource, seen)
            if found is not None:
                return found
    return None


def _apr_helpers(root: Path) -> dict[str, int]:
    helpers: dict[str, int] = {}
    for path in root.glob("CBR*.SPL"):
        key = _resource_apr_key(root, path.stem)
        if key in (1, 6, 7):
            helpers[path.stem.upper()] = key
    return helpers


def _tier_duration(level: int) -> int:
    if level <= 6:
        return 18
    if level <= 12:
        return 24
    return 30


def _strip_weidu_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*$", "", source, flags=re.MULTILINE)


if __name__ == "__main__":
    unittest.main()
