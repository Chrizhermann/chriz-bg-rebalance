from __future__ import annotations

import dataclasses
import hashlib
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
PRIVATE_STATE_SYMBOLS = (
    "CBR_TEMPUS_IH",
    "CBR_TEMPUS_APR_HALF",
    "CBR_TEMPUS_APR_ONE",
    "CBR_TEMPUS_APR_ONE_HALF",
)
IH_STATE_SYMBOL = PRIVATE_STATE_SYMBOLS[0]
APR_STATE_SYMBOL_BY_KEY = {
    6: PRIVATE_STATE_SYMBOLS[1],
    1: PRIVATE_STATE_SYMBOLS[2],
    7: PRIVATE_STATE_SYMBOLS[3],
}
ACTIVE_SPLSTATE_SEMANTIC = (0x112, -1, 1)


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


def _make_holy_fixture(divine_resref: str, holy_layout: str = "original") -> SplFile:
    spell = read_spl(ORIGINALS / "OHTMPS1.spl.orig")
    spell = _rename_spell_resources(spell, "SPPR412", divine_resref)
    abilities = list(spell.abilities)
    abilities[9] = dataclasses.replace(
        abilities[9], effects=abilities[9].effects + (_sentinel_effect(),)
    )
    if holy_layout == "stale_30":
        donor = abilities[-1]
        abilities.extend(
            dataclasses.replace(donor, required_level=level)
            for level in range(21, 31)
        )
    elif holy_layout != "original":
        raise ValueError(f"unknown Holy Power fixture layout: {holy_layout}")
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

    headers = []
    for required_level, duration_delta, rotation in ((1, 0, 0), (10, 6, 1), (20, 12, 2)):
        header_effects = [
            dataclasses.replace(effect, duration=effect.duration + duration_delta)
            if (
                (effect.opcode == 1 and effect.parameter1 == 1 and effect.parameter2 == 0)
                or (effect.opcode in (16, 317) and effect.parameter2 == 1)
            )
            else effect
            for effect in effects
        ]
        rotation %= len(header_effects)
        if rotation:
            header_effects = header_effects[rotation:] + header_effects[:rotation]
        headers.append(
            dataclasses.replace(
                ability,
                effects=tuple(header_effects),
                required_level=required_level,
            )
        )
    return dataclasses.replace(base, abilities=tuple(headers)), helpers


def build_fixture(
    root: Path,
    variant: str,
    *,
    divine_id: int = 1499,
    haste_id: int = 2699,
    splstate_layout: str = "free",
    holy_layout: str = "original",
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

    write_spl(
        root / f"{HOLY_RESREF}.SPL",
        _make_holy_fixture(divine_resref, holy_layout),
    )
    write_spl(root / f"{divine_resref}.SPL", _make_divine_fixture(divine_resref))
    haste, helpers = _improved_haste_fixture(variant, haste_resref)
    write_spl(root / f"{haste_resref}.SPL", haste)
    for resref, helper in helpers.items():
        write_spl(root / f"{resref}.SPL", helper)

    shutil.copyfile(ORIGINALS / "OHTEMPUS.2da.orig", root / CLAB_NAME)
    base_states = tuple((value, f"FIXTURE_STATE_{value}") for value in range(32)) + (
        (68, "BUFF_ENHANCEMENT"),
        (200, "FOREIGN_200"),
        (254, "FOREIGN_254"),
    )
    if splstate_layout == "free":
        state_entries = base_states
    elif splstate_layout == "reuse":
        state_entries = base_states + tuple(
            (240 + index, symbol) for index, symbol in enumerate(PRIVATE_STATE_SYMBOLS)
        )
    elif splstate_layout == "partial_clean":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (242, PRIVATE_STATE_SYMBOLS[2]),
        )
    elif splstate_layout == "duplicate_private_symbol":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (241, PRIVATE_STATE_SYMBOLS[0]),
        )
    elif splstate_layout == "shared_private_value":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (240, "FOREIGN_SHARED_240"),
        )
    elif splstate_layout == "exhausted":
        state_entries = tuple((value, f"FOREIGN_STATE_{value}") for value in range(256))
    else:
        raise ValueError(f"unknown SPLSTATE fixture layout: {splstate_layout}")
    write_ids(root / "SPLSTATE.IDS", IdsFile(entries=state_entries))
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
    splstate_layout: str = "free",
    holy_layout: str = "original",
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
        splstate_layout=splstate_layout,
        holy_layout=holy_layout,
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
                self.assertEqual(
                    2 if variant == "inconsistent" else 3,
                    len(spell.abilities),
                    "fixture must exercise every IH header",
                )
                if variant == "additive":
                    donors = [
                        [
                            (index, effect)
                            for index, effect in enumerate(ability.effects)
                            if effect.opcode == 1
                            and effect.parameter1 == 1
                            and effect.parameter2 == 0
                        ]
                        for ability in spell.abilities
                    ]
                    self.assertTrue(all(len(header) == 1 for header in donors))
                    self.assertEqual(3, len({header[0][0] for header in donors}))
                    self.assertEqual(3, len({header[0][1].duration for header in donors}))

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
            flags=0xA5C39E71,
        )
        encoded_eff = effect.to_bytes()
        self.assertEqual(0xA5C39E71, int.from_bytes(encoded_eff[0x5C:0x60], "little"))
        parsed_eff = EffV2.from_bytes(encoded_eff)
        self.assertEqual(effect, parsed_eff)
        self.assertEqual(0xA5C39E71, parsed_eff.flags)

        embedded = SplEffect(opcode=326, resist_dispel=3)
        encoded_embedded = embedded.to_bytes()
        self.assertEqual(3, encoded_embedded[0x0D])
        self.assertEqual(3, SplEffect.from_bytes(encoded_embedded).resist_dispel)
        self.assertFalse(hasattr(parsed_eff, "resist_dispel"))

    def test_tlk_writer_detection_covers_command_families(self) -> None:
        source = """
        // SAY_EVALUATED STRING_SET_EVALUATE REPLACE_SAY
        /* TLK_WRITE_SUFFIX */
        OUTER_SPRINT harmless ~SAY_EVALUATED is only message text~
        SAY_EVALUATED @1
        STRING_SET_EVALUATE 42 @2
        REPLACE_SAY_EVALUATED ~DIALOG~ 0 @3
        TLK_WRITE_EVALUATED ~elsewhere.tlk~
        """
        self.assertEqual(
            [
                "REPLACE_SAY_EVALUATED",
                "SAY_EVALUATED",
                "STRING_SET_EVALUATE",
                "TLK_WRITE_EVALUATED",
            ],
            _tlk_writes(source),
        )

    def test_bridge_condition_reader_rejects_malformed_graphs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-bridge-graph-") as temporary:
            root = Path(temporary)
            helper_resref = "CBRAPR6"
            helper = make_spl(
                (
                    SplAbility(
                        required_level=1,
                        target=5,
                        projectile=0,
                        effects=(
                            SplEffect(opcode=321, target=1, resource=helper_resref),
                            SplEffect(
                                opcode=1,
                                target=1,
                                parameter1=6,
                                parameter2=0,
                                timing=0,
                                resist_dispel=2,
                                duration=1,
                            ),
                        ),
                    ),
                )
            )
            write_spl(root / f"{helper_resref}.SPL", helper)
            valid = EffV2(
                opcode=326,
                target=1,
                parameter1=210,
                parameter2=4,
                timing=1,
                resource=helper_resref,
            )
            (root / "VALID.EFF").write_bytes(valid.to_bytes())
            self.assertEqual(
                6,
                _read_conditional_apr_edge(
                    root,
                    "VALID",
                    expected_state=210,
                    active_row=4,
                    expected_helper=helper_resref,
                ),
            )

            invalid = {
                "ALWAYS": dataclasses.replace(valid, opcode=146),
                "WRONGST": dataclasses.replace(valid, parameter1=211),
                "WRONGROW": dataclasses.replace(valid, parameter2=5),
            }
            for resref, effect in invalid.items():
                (root / f"{resref}.EFF").write_bytes(effect.to_bytes())
                with self.subTest(resref=resref), self.assertRaises(AssertionError):
                    _read_conditional_apr_edge(
                        root,
                        resref,
                        expected_state=210,
                        active_row=4,
                        expected_helper=helper_resref,
                    )
            for resref in (helper_resref, "MISSING"):
                with self.subTest(resref=resref), self.assertRaises(AssertionError):
                    _read_conditional_apr_edge(
                        root,
                        resref,
                        expected_state=210,
                        active_row=4,
                        expected_helper=helper_resref,
                    )

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
        splstate_layout: str = "free",
        holy_layout: str = "original",
    ) -> HarnessResult:
        result = _run_harness(
            variant,
            mode,
            alternate_ids=alternate_ids,
            phase=phase,
            splstate_layout=splstate_layout,
            holy_layout=holy_layout,
        )
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

    def assert_allocation_rejected(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                "cannot verify SPLSTATE rejection because production library is missing: "
                f"{PRODUCTION_TPA}\n{result.transcript}"
            )
        self.assertFalse(result.succeeded, "invalid SPLSTATE layout was accepted")
        self.assertRegex(result.transcript.upper(), r"SPLSTATE|SPELL[ _-]?STATE|COLLIS|EXHAUST")

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
        private = [
            (value, symbol.upper())
            for value, symbol in after_ids.entries
            if symbol.upper() in PRIVATE_STATE_SYMBOLS
        ]
        self.assertEqual(set(PRIVATE_STATE_SYMBOLS), {symbol for _, symbol in private})
        self.assertEqual(4, len(private))
        self.assertEqual(len(private), len({value for value, _ in private}))
        self.assertTrue(all(0 <= value <= 255 for value, _ in private))
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

        reuse = self.run_case(phase="allocate", splstate_layout="reuse")
        self.assert_success(reuse)
        reuse_before = read_ids(reuse.fixture.root / "SPLSTATE.IDS")
        reuse_after = read_ids(reuse.output / "SPLSTATE.IDS")
        for symbol in PRIVATE_STATE_SYMBOLS:
            with self.subTest(layout="reuse", symbol=symbol):
                self.assertEqual(reuse_before.value(symbol), reuse_after.value(symbol))
        self.assertEqual(reuse_before.canonical(), reuse_after.canonical())
        self.assertEqual(
            (reuse.fixture.root / "SPLSTATE.IDS").read_bytes(),
            (reuse.output / "SPLSTATE.IDS").read_bytes(),
            "unique preallocated private states must be reused without rewriting SPLSTATE.IDS",
        )

    def test_doubling_allocation_skips_additive_bridge_states(self) -> None:
        result = self.run_case("doubling", phase="allocate")
        self.assert_success(result)
        before_ids = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after_ids = read_ids(result.output / "SPLSTATE.IDS")
        self.assertEqual(before_ids.canonical(), after_ids.canonical())
        after_symbols = {symbol.upper() for _, symbol in after_ids.entries}
        self.assertTrue(
            set(PRIVATE_STATE_SYMBOLS).isdisjoint(after_symbols),
            "true-doubling Improved Haste must not allocate additive bridge states",
        )
        before_semantics = [
            tuple(int(value, 0) for value in row)
            for _, row in read_2da(result.fixture.root / "SPLPROT.2DA").rows
        ]
        after_semantics = [
            tuple(int(value, 0) for value in row)
            for _, row in read_2da(result.output / "SPLPROT.2DA").rows
        ]
        self.assertEqual(
            before_semantics.count(ACTIVE_SPLSTATE_SEMANTIC),
            after_semantics.count(ACTIVE_SPLSTATE_SEMANTIC),
            "doubling mode must not create active-Improved-Haste SPLSTATE infrastructure",
        )
        for required in ((36, -1, 2), (36, -1, 1), (37, -1, 2)):
            with self.subTest(required=required):
                self.assertEqual(1, after_semantics.count(required))

    def test_partial_clean_splstates_are_reused_and_completed(self) -> None:
        result = self.run_case(phase="allocate", splstate_layout="partial_clean")
        self.assert_success(result)
        before = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after = read_ids(result.output / "SPLSTATE.IDS")
        after_symbols = {symbol.upper() for _, symbol in after.entries}
        self.assertEqual(set(PRIVATE_STATE_SYMBOLS), after_symbols & set(PRIVATE_STATE_SYMBOLS))
        private_values = [after.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS]
        self.assertEqual(4, len(set(private_values)))
        for symbol in (PRIVATE_STATE_SYMBOLS[0], PRIVATE_STATE_SYMBOLS[2]):
            with self.subTest(symbol=symbol):
                self.assertEqual(before.value(symbol), after.value(symbol))
        new_symbols = (PRIVATE_STATE_SYMBOLS[1], PRIVATE_STATE_SYMBOLS[3])
        self.assertTrue(
            {after.value(symbol) for symbol in new_symbols}.isdisjoint(before.values())
        )

    def test_rejects_stale_cloned_30_header_holy_power(self) -> None:
        result = self.run_case(phase="classify", holy_layout="stale_30")
        self.assertFalse(result.succeeded, "stale cloned 30-header Holy Power was accepted")
        self.assertRegex(
            result.transcript.upper(),
            r"OHTMPS1|HOLY[ _-]?POWER|30[ _-]?HEADER|THAC0|DURATION|APR",
        )

    def test_rejects_splstate_collisions_and_exhaustion(self) -> None:
        for layout in (
            "duplicate_private_symbol",
            "shared_private_value",
            "exhausted",
        ):
            with self.subTest(layout=layout):
                self.assert_allocation_rejected(
                    self.run_case(phase="allocate", splstate_layout=layout)
                )

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
                thac0_effects = [effect for effect in effects if effect.opcode == 54]
                hp_effects = [effect for effect in effects if effect.opcode == 18]
                self.assertEqual(1, len(thac0_effects), "THAC0 mechanic must be unique")
                self.assertEqual(1, len(hp_effects), "temporary HP mechanic must be unique")
                thac0_effect = thac0_effects[0]
                hp_effect = hp_effects[0]
                self.assertEqual(
                    (thac0, 1, 0, duration, 3),
                    (
                        thac0_effect.parameter1,
                        thac0_effect.parameter2,
                        thac0_effect.timing,
                        thac0_effect.duration,
                        thac0_effect.resist_dispel,
                    ),
                    "THAC0 must be one flat, temporary, dispellable mechanic",
                )
                self.assertEqual(
                    (hp, 0, 0, duration, 3),
                    (
                        hp_effect.parameter1,
                        hp_effect.parameter2,
                        hp_effect.timing,
                        hp_effect.duration,
                        hp_effect.resist_dispel,
                    ),
                    "HP must be one cumulative, temporary, dispellable mechanic",
                )
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
        state_values = _private_state_values(result.output)
        ih_state = state_values[IH_STATE_SYMBOL]
        tier_state_by_key = {
            key: state_values[symbol] for key, symbol in APR_STATE_SYMBOL_BY_KEY.items()
        }
        active_row = _active_splstate_row(result.output)

        helpers = _strict_apr_helpers(result.output)
        self.assertEqual(3, len(helpers), f"expected one strict APR helper per tier: {helpers}")
        self.assertEqual({1, 6, 7}, set(helpers.values()))
        helper_by_key = {key: resource for resource, key in helpers.items()}
        self.assertEqual(3, len(helper_by_key), "APR helper keys are not one-to-one")
        helper_resrefs = set(helpers)

        conditions = _apr_condition_resources(result.output, helper_resrefs)
        self.assertEqual(
            3,
            len(conditions),
            f"expected one standalone conditional EFF per APR tier: {conditions}",
        )
        condition_by_key = {}
        for condition_resref, condition in conditions.items():
            helper_resref = condition.resource.upper()
            key = helpers[helper_resref]
            self.assertNotIn(key, condition_by_key, f"duplicate conditional EFF for APR key {key}")
            self.assertEqual(
                key,
                _read_conditional_apr_edge(
                    result.output,
                    condition_resref,
                    expected_state=ih_state,
                    active_row=active_row,
                    expected_helper=helper_resref,
                ),
            )
            condition_by_key[key] = condition_resref
        self.assertEqual({1, 6, 7}, set(condition_by_key))

        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        haste_before = read_spl(result.fixture.root / f"{result.fixture.haste_resref}.SPL")
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        bridge_resources = helper_resrefs | set(conditions)
        bridge_states = {ih_state, *tier_state_by_key.values()}
        for owner, casting_effects in (
            ("Holy Power", holy.casting_effects),
            ("Improved Haste", haste.casting_effects),
        ):
            self.assertFalse(
                any(
                    (effect.opcode == 328 and effect.parameter2 in bridge_states)
                    or (
                        effect.opcode in (272, 326)
                        and effect.resource.upper() in bridge_resources
                    )
                    for effect in casting_effects
                ),
                f"{owner} bridge effects escaped their caster-level headers",
            )

        self.assertEqual(len(haste_before.abilities), len(haste.abilities))
        for header_index, (before_ability, ability) in enumerate(
            zip(haste_before.abilities, haste.abilities)
        ):
            with self.subTest(resource="Improved Haste", header=header_index):
                self.assertEqual(before_ability.required_level, ability.required_level)
                donor_before = [
                    effect
                    for effect in before_ability.effects
                    if effect.opcode == 1
                    and effect.parameter1 == 1
                    and effect.parameter2 == 0
                ]
                donor_after = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 1
                    and effect.parameter1 == 1
                    and effect.parameter2 == 0
                ]
                self.assertEqual(1, len(donor_before))
                self.assertEqual(1, len(donor_after))
                self.assertEqual(donor_before[0].canonical(), donor_after[0].canonical())
                for effect in before_ability.effects:
                    self.assertIn(
                        effect.canonical(),
                        [candidate.canonical() for candidate in ability.effects],
                        "additive bridge replaced a foreign Improved Haste effect",
                    )
                self.assertFalse(
                    any(
                        effect.opcode in (16, 317) and effect.parameter2 == 1
                        for effect in ability.effects
                    )
                )

                markers = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 328 and effect.parameter2 == ih_state
                ]
                self.assertEqual(1, len(markers), "IH header must contain exactly one marker")
                marker = markers[0]
                self.assertEqual(
                    (328, 0, ih_state, 1),
                    (marker.opcode, marker.parameter1, marker.parameter2, marker.special),
                )
                self.assertEqual(donor_after[0].delivery_key(), marker.delivery_key())
                self.assertEqual(
                    ("", 0, 0, 0, 0),
                    (
                        marker.resource,
                        marker.dice_number,
                        marker.dice_size,
                        marker.save_type,
                        marker.save_bonus,
                    ),
                    "IH marker copied non-delivery payload fields from its APR donor",
                )

                kicks = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 326 and effect.resource.upper() in helper_resrefs
                ]
                self.assertEqual(3, len(kicks), "IH header must kick every active Holy APR tier")
                for key, tier_state in tier_state_by_key.items():
                    matched = [effect for effect in kicks if effect.parameter1 == tier_state]
                    self.assertEqual(1, len(matched), f"missing or duplicate IH kick for APR key {key}")
                    kick = matched[0]
                    self.assertEqual(
                        (326, tier_state, active_row, 1, 100, 0, helper_by_key[key]),
                        (
                            kick.opcode,
                            kick.parameter1,
                            kick.parameter2,
                            kick.timing,
                            kick.probability1,
                            kick.probability2,
                            kick.resource.upper(),
                        ),
                    )

        self.assertEqual(30, len(holy.abilities))
        self.assertEqual(list(range(1, 31)), [ability.required_level for ability in holy.abilities])
        tier_state_set = set(tier_state_by_key.values())
        for ability in holy.abilities:
            level = ability.required_level
            duration = _tier_duration(level)
            expected_key = None if level <= 6 else 6 if level <= 12 else 1 if level <= 24 else 7
            with self.subTest(resource=HOLY_RESREF, level=level):
                tier_markers = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 328 and effect.parameter2 in tier_state_set
                ]
                immediate = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 326 and effect.resource.upper() in helper_resrefs
                ]
                pulses = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 272 and effect.resource.upper() in bridge_resources
                ]
                if expected_key is None:
                    self.assertEqual([], tier_markers, "levels 1-6 must not carry an APR tier state")
                    self.assertEqual([], immediate, "levels 1-6 must not carry an APR bridge kick")
                    self.assertEqual([], pulses, "levels 1-6 must not carry an APR bridge pulse")
                    continue

                expected_state = tier_state_by_key[expected_key]
                self.assertEqual(1, len(tier_markers), "Holy header must have one APR tier state")
                marker = tier_markers[0]
                self.assertEqual(
                    (328, 0, expected_state, 0, duration, 3, 1),
                    (
                        marker.opcode,
                        marker.parameter1,
                        marker.parameter2,
                        marker.timing,
                        marker.duration,
                        marker.resist_dispel,
                        marker.special,
                    ),
                )

                self.assertEqual(1, len(immediate), "Holy header must have one immediate IH gate")
                kick = immediate[0]
                self.assertEqual(
                    (326, ih_state, active_row, 1, 100, 0, helper_by_key[expected_key]),
                    (
                        kick.opcode,
                        kick.parameter1,
                        kick.parameter2,
                        kick.timing,
                        kick.probability1,
                        kick.probability2,
                        kick.resource.upper(),
                    ),
                )

                self.assertEqual(1, len(pulses), "Holy header must have one APR heartbeat")
                pulse = pulses[0]
                self.assertEqual(
                    (272, 1, 3, duration, condition_by_key[expected_key]),
                    (
                        pulse.opcode,
                        pulse.parameter1,
                        pulse.parameter2,
                        pulse.duration,
                        pulse.resource.upper(),
                    ),
                )
                self.assertEqual(
                    expected_key,
                    _read_conditional_apr_edge(
                        result.output,
                        pulse.resource,
                        expected_state=ih_state,
                        active_row=active_row,
                        expected_helper=helper_by_key[expected_key],
                    ),
                )

    def test_doubling_needs_no_bridge(self) -> None:
        result = self.run_case("doubling", "auto", phase="bridge")
        self.assert_success(result)
        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        for header_index, ability in enumerate(haste.abilities):
            with self.subTest(header=header_index):
                effects = ability.effects
                self.assertTrue(any(e.opcode in (16, 317) and e.parameter2 == 1 for e in effects))
                self.assertFalse(any(e.opcode == 1 and e.parameter1 == 1 and e.parameter2 == 0 for e in effects))
                self.assertFalse(any(e.opcode == 328 and e.special == 1 for e in effects))
        self.assertEqual({}, _strict_apr_helpers(result.output), "doubling mode created additive bridge resources")
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
                first_files = _raw_file_tree(first.output)
                copied_fixture_files = _raw_file_tree(second.fixture.root)
                second_files = _raw_file_tree(second.output)
                self.assertEqual(
                    first_files,
                    copied_fixture_files,
                    "second-pass fixture copy changed raw production output before WeiDU ran",
                )
                self.assertEqual(
                    set(first_files),
                    set(second_files),
                    "second application changed the recursive output file set",
                )
                for relative in sorted(first_files):
                    with self.subTest(variant=variant, file=relative):
                        first_bytes = first_files[relative]
                        second_bytes = second_files[relative]
                        self.assertEqual(
                            first_bytes,
                            second_bytes,
                            f"raw bytes changed for {relative}: "
                            f"{hashlib.sha256(first_bytes).hexdigest()} != "
                            f"{hashlib.sha256(second_bytes).hexdigest()}",
                        )
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
        source = "\n".join(blocks) + "\n" + PRODUCTION_TPA.read_text(encoding="utf-8")
        self.assertEqual([], _tlk_writes(source), "components 401-403 contain TLK writers")
        harness_source = _strip_weidu_comments(HARNESS.read_text(encoding="utf-8"))
        self.assertEqual([], _tlk_writes(harness_source), "harness contains TLK writers")
        for banned in (r"\bCOPY_EXISTING\b", r"\bFILE_EXISTS_IN_GAME\b"):
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


def _private_state_values(root: Path) -> dict[str, int]:
    ids = read_ids(root / "SPLSTATE.IDS")
    values = {symbol: ids.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS}
    if len(set(values.values())) != len(values):
        raise AssertionError(f"private SPLSTATE values are not unique: {values}")
    return values


def _active_splstate_row(root: Path) -> int:
    table = read_2da(root / "SPLPROT.2DA")
    rows = [
        index
        for index, (_, values) in enumerate(table.rows)
        if tuple(int(value, 0) for value in values) == ACTIVE_SPLSTATE_SEMANTIC
    ]
    if len(rows) != 1:
        raise AssertionError(
            f"active-SPLSTATE semantic row matched {len(rows)} rows, expected one: {rows}"
        )
    return rows[0]


def _read_apr_helper(root: Path, resource: str) -> int:
    resource = resource.upper()
    path = root / f"{resource}.SPL"
    if not path.is_file():
        raise AssertionError(f"APR helper SPL does not exist: {resource}")
    spell = read_spl(path)
    if len(spell.abilities) != 1:
        raise AssertionError(f"APR helper {resource} has {len(spell.abilities)} headers")
    effects = spell.abilities[0].effects
    if not effects or (effects[0].opcode, effects[0].resource.upper()) != (321, resource):
        raise AssertionError(f"APR helper {resource} does not begin with reciprocal self cleanup")
    apr = [effect for effect in effects if effect.opcode == 1 and effect.parameter2 == 0]
    if len(apr) != 1:
        raise AssertionError(f"APR helper {resource} has {len(apr)} cumulative APR effects")
    mechanic = apr[0]
    if (mechanic.timing, mechanic.duration) != (0, 1):
        raise AssertionError(
            f"APR helper {resource} timing/duration is {(mechanic.timing, mechanic.duration)}, expected (0, 1)"
        )
    if mechanic.resist_dispel & 2 != 2:
        raise AssertionError(f"APR helper {resource} does not bypass magic resistance")
    return mechanic.parameter1


def _strict_apr_helpers(root: Path) -> dict[str, int]:
    helpers = {}
    for path in root.glob("*.SPL"):
        try:
            key = _read_apr_helper(root, path.stem)
        except AssertionError:
            continue
        if key in APR_STATE_SYMBOL_BY_KEY:
            helpers[path.stem.upper()] = key
    return helpers


def _apr_condition_resources(
    root: Path, helper_resrefs: set[str]
) -> dict[str, EffV2]:
    conditions = {}
    for path in root.glob("*.EFF"):
        effect = read_eff_v2(path)
        if effect.resource.upper() in helper_resrefs:
            conditions[path.stem.upper()] = effect
    return conditions


def _read_conditional_apr_edge(
    root: Path,
    resource: str,
    *,
    expected_state: int,
    active_row: int,
    expected_helper: str,
) -> int:
    resource = resource.upper()
    expected_helper = expected_helper.upper()
    path = root / f"{resource}.EFF"
    if not path.is_file():
        raise AssertionError(
            f"heartbeat {resource} must be a standalone conditional EFF, not a direct or missing helper"
        )
    effect = read_eff_v2(path)
    actual = (
        effect.opcode,
        effect.parameter1,
        effect.parameter2,
        effect.timing,
        effect.probability1,
        effect.probability2,
        effect.resource.upper(),
    )
    expected = (326, expected_state, active_row, 1, 100, 0, expected_helper)
    if actual != expected:
        raise AssertionError(
            f"conditional EFF {resource} has {actual}, expected active-SPLSTATE edge {expected}"
        )
    return _read_apr_helper(root, expected_helper)


def _tier_duration(level: int) -> int:
    if level <= 6:
        return 18
    if level <= 12:
        return 24
    return 30


def _strip_weidu_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*$", "", source, flags=re.MULTILINE)


def _tlk_writes(source: str) -> list[str]:
    uncommented = _strip_weidu_comments(source)
    writers = []
    if re.search(r"DIALOGF?\s*\.\s*TLK", uncommented, re.IGNORECASE):
        writers.append("DIALOG.TLK")
    without_strings = re.sub(r"~.*?~|\".*?\"", " ", uncommented, flags=re.DOTALL)
    tokens = re.findall(r"\b[A-Z][A-Z0-9_]*\b", without_strings.upper())
    for token in tokens:
        if (
            re.fullmatch(r"(?:[A-Z0-9]+_)*SAY(?:_[A-Z0-9]+)*", token)
            or re.fullmatch(r"(?:[A-Z0-9]+_)*STRING_SET(?:_[A-Z0-9]+)*", token)
            or token.startswith("RESOLVE_STR_REF")
            or re.fullmatch(r"(?:TLK_(?:APPEND|WRITE|PATCH|ALTER|SET)|(?:APPEND|WRITE|PATCH|ALTER|SET)_TLK)(?:_[A-Z0-9]+)*", token)
            or token in {"ADD_TRANSLATED_STRING", "REPLACE_SAY"}
        ):
            writers.append(token)
    return sorted(set(writers))


def _raw_file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(
            (candidate for candidate in root.rglob("*") if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(root).as_posix().upper(),
        )
    }


if __name__ == "__main__":
    unittest.main()
