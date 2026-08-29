"""Hermetic binary and BCS tests for component 120.

The checked-in BCS donors contain live-byte-identical target blocks.  Every
WeiDU invocation in this module uses a temporary resource tree plus minimal
IDS maps under --nogame; the active game is never consulted.
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import SplAbility, SplEffect, SplFile, read_spl, write_spl


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "scs_weapon_semantics_harness.tp2"
PRODUCTION_TPA = (
    ROOT / "chriz-bg-rebalance" / "lib" / "scs_weapon_protection_semantics.tpa"
)
FIXTURES = ROOT / "tests" / "fixtures" / "scs_weapon_semantics"
ORIGINALS = ROOT / "research" / "originals"

FIXTURE_HASHES = {
    "first_round.bcs": "ce006369bb4d91a70efeffbc26a65323f2a004af822e3e8ec17e032d65da04cf",
    "renew.bcs": "29898cbd182a2a9aff0ea8a6dec64083f6378b2897d2a9b5bced7a2eec3ff124",
    "chain_contingency.bcs": "6e483114daf63063ed6665998748026e59906cf5ce4ad21bec51f90660f93824",
    "unrelated_mop.bcs": "8144895116c8ed3d5b8566087d38b66d33b982a0129ee88a2e9577c4bd1774ee",
}

DEFAULT_IDS = {
    "pfmw": (2611, "SPWI611"),
    "mantle": (2708, "SPWI708"),
    "improved": (2808, "SPWI808"),
    "mop": (2808, "SPWI808"),
    "absolute": (2907, "SPWI907"),
    "breach": (2513, "SPWI513"),
    "dispel": (2302, "SPWI302"),
}

COMMON_SCRIPT_MAP = {
    "first_round.bcs": "dw#mg100.bcs",
    "renew.bcs": "dw#mg101.bcs",
    "chain_contingency.bcs": "dw#mg102.bcs",
    "unrelated_mop.bcs": "dw#mg103.bcs",
}

PHASE_COMPONENT = {
    "classify": "1",
    "metadata": "2",
    "scripts": "3",
    "full": "4",
    "preflight": "5",
}


@dataclasses.dataclass
class Fixture:
    temporary: tempfile.TemporaryDirectory[str]
    root: Path
    ids: dict[str, tuple[int, str]]


@dataclasses.dataclass
class HarnessResult:
    process: subprocess.CompletedProcess[str]
    run_temporary: tempfile.TemporaryDirectory[str]
    run_dir: Path
    fixture: Fixture
    component: str
    probe_resref: str

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}".strip()

    @property
    def succeeded(self) -> bool:
        return (
            self.process.returncode == 0
            and (self.fixture.root / "CBR_TEST.OK").is_file()
            and "SUCCESSFULLY INSTALLED" in self.transcript
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_bcs_blocks(path: Path) -> list[bytes]:
    """Split the textual compiled-BCS container exactly as SCS SFO does."""
    data = path.read_bytes()
    blocks: list[bytes] = []
    start = data.find(b"CR\n")
    while start > 0:
        end = data.find(b"RS\nCR\n", start)
        if end < 0:
            raise ValueError(f"unterminated BCS block in {path} at {start}")
        end += len(b"RS\nCR\n")
        blocks.append(data[start:end])
        start = data.find(b"CR\n", end)
    if not blocks:
        raise ValueError(f"no compiled blocks in {path}")
    return blocks


def _weapon_effect(*, power: int = 8) -> SplEffect:
    return SplEffect(
        opcode=120,
        target=1,
        power=power,
        parameter1=0,
        parameter2=2,
        timing=0,
        resist_dispel=3,
        duration=24,
        probability1=100,
        probability2=0,
    )


def _replace_ability_effects(spell: SplFile, effects: tuple[SplEffect, ...]) -> SplFile:
    abilities = list(spell.abilities)
    abilities[0] = dataclasses.replace(abilities[0], effects=effects)
    return dataclasses.replace(spell, abilities=tuple(abilities))


def _mop_variant(layout: str) -> SplFile:
    base = read_spl(ORIGINALS / "SPWI808.spl.orig")
    effects = list(base.abilities[0].effects)
    if layout == "current":
        return base
    if layout == "future_true":
        effects.insert(1, _weapon_effect())
    elif layout == "dispellable":
        effects = [
            dataclasses.replace(effect, resist_dispel=3)
            if effect.opcode in (0, 33, 34, 35, 36, 37)
            else effect
            for effect in effects
        ]
    elif layout == "near_markers":
        effects.extend(
            (
                dataclasses.replace(effects[11], parameter2=129),
                dataclasses.replace(effects[11], parameter1=3),
                dataclasses.replace(effects[12], parameter2=65),
            )
        )
    elif layout == "duplicate_markers":
        effects.append(effects[11])
    else:
        raise ValueError(f"unknown Moment of Prescience layout: {layout}")
    return _replace_ability_effects(base, tuple(effects))


def _remove_weapon_effects(spell: SplFile) -> SplFile:
    return _replace_ability_effects(
        spell, tuple(effect for effect in spell.abilities[0].effects if effect.opcode != 120)
    )


def _breach_graph(secondary_type: int) -> tuple[SplFile, SplFile]:
    root = SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=1,
                projectile=55,
                effects=(
                    SplEffect(
                        opcode=146,
                        target=2,
                        power=5,
                        parameter2=1,
                        timing=1,
                        probability1=100,
                        resource="CBRBRH1",
                    ),
                ),
            ),
        ),
        header_raw=_empty_spl_header(secondary_type=4, level=5),
    )
    helper = SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=1,
                projectile=1,
                effects=(
                    SplEffect(
                        opcode=221,
                        target=2,
                        power=5,
                        parameter1=9,
                        parameter2=secondary_type,
                        timing=1,
                        probability1=100,
                    ),
                ),
            ),
        ),
        header_raw=_empty_spl_header(secondary_type=4, level=5),
    )
    return root, helper


def _dispel_spell() -> SplFile:
    return SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=4,
                projectile=177,
                effects=(
                    SplEffect(
                        opcode=58,
                        target=2,
                        power=0,
                        parameter1=0,
                        parameter2=0x20001,
                        timing=1,
                        probability1=100,
                    ),
                ),
            ),
        ),
        header_raw=_empty_spl_header(secondary_type=4, level=3),
    )


def _empty_spl_header(*, secondary_type: int, level: int) -> bytes:
    data = bytearray(0x72)
    data[:8] = b"SPL V1  "
    data[0x1C] = 1
    data[0x25] = 1
    data[0x27] = secondary_type
    data[0x34] = level
    return bytes(data)


def _ids_text(ids: dict[str, tuple[int, str]], *, sr_absent: bool = False) -> str:
    entries = [
        ids["pfmw"][0:1] + ("WIZARD_PROTECTION_FROM_MAGIC_WEAPONS",),
        ids["mantle"][0:1] + ("WIZARD_MANTLE",),
        ids["improved"][0:1] + ("WIZARD_IMPROVED_MANTLE",),
        ids["mop"][0:1] + ("WIZARD_MOMENT_OF_PRESCIENCE",),
        ids["absolute"][0:1] + ("WIZARD_ABSOLUTE_IMMUNITY",),
        ids["breach"][0:1] + ("WIZARD_BREACH",),
        ids["dispel"][0:1] + ("WIZARD_DISPEL_MAGIC",),
    ]
    if sr_absent:
        # In this layout the old symbol truthfully resolves to the real Mantle resource.
        entries[2] = (ids["mantle"][0], "WIZARD_IMPROVED_MANTLE")
    return "IDS V1.0\n" + "".join(f"{value} {symbol}\n" for value, symbol in entries)


def _write_minimal_script_ids(root: Path, spell_ids: str) -> None:
    files = {
        "ACTION.IDS": """90
30 SetGlobal(S:Name*,S:Area*,I:Value*)
31 Spell(O:Target*,I:Spell*Spell)
36 Continue()
115 SetGlobalTimer(S:Name*,S:Area*,I:Time*GTimes)
181 ReallyForceSpell(O:Target,I:Spell*Spell)
181 ReallyForceSpellRES(S:RES*,O:Target)
""",
        "TRIGGER.IDS": """IDS V1.0
0x400B Allegiance(O:Object*,I:Allegience*EA)
0x400F Global(S:Name*,S:Area*,I:Value*)
0x4018 Range(O:Object*,I:Range*)
0x401C See(O:Object*)
0x4031 HaveSpell(I:Spell*Spell)
0x4034 GlobalGT(S:Name*,S:Area*,I:Value*)
0x4037 StateCheck(O:Object*,I:State*State)
0x4041 GlobalTimerNotExpired(S:Name*,S:Area*)
0x4045 CheckStatGT(O:Object*,I:Value*,I:StatNum*Stats)
0x4046 CheckStatLT(O:Object*,I:Value*,I:StatNum*Stats)
0x4074 Detect(O:Object*)
0x4089 OR(I:OrCount*)
0x40D2 DifficultyLT(I:Amount*DIFFLEV)
0x40E2 CheckSpellState(O:Object*,I:State*splstate)
0x40ED INI(S:Name*,I:Number*)
""",
        "OBJECT.IDS": """IDS V1.0
0 Nothing
1 Myself
12 NearestEnemyOf
21 Player1
22 Player2
23 Player3
24 Player4
25 Player5
26 Player6
""",
        "STATS.IDS": """IDS V1.0
51 SPELLFAILUREMAGE
128 WIZARD_PROTECTION_FROM_MAGIC_WEAPONS
""",
        "STATE.IDS": """IDS V1.0
0 STATE_NORMAL
0x10 STATE_INVISIBLE
0xFC0 STATE_REALLY_DEAD
""",
        "SPLSTATE.IDS": """IDS V1.0
64 BUFF_PRO_WEAPONS
180 TIME_STOP
187 PRIORITY_BREACH
188 PRIORITY_DISPEL
""",
        "EA.IDS": """IDS V1.0
0 ANYONE
255 ENEMY
""",
        "GTIMES.IDS": """IDS V1.0
6 ONE_ROUND
""",
        "DIFFLEV.IDS": """IDS V1.0
2 EASY
3 NORMAL
4 HARD
""",
        "GENERAL.IDS": "IDS V1.0\n0 GENERAL_NONE\n",
        "RACE.IDS": "IDS V1.0\n0 NO_RACE\n",
        "CLASS.IDS": "IDS V1.0\n0 NO_CLASS\n",
        "SPECIFIC.IDS": "IDS V1.0\n0 SPECIFIC_NONE\n",
        "GENDER.IDS": "IDS V1.0\n0 GENDER_NONE\n",
        "ALIGN.IDS": "IDS V1.0\n0 NO_ALIGNMENT\n",
        "SPELL.IDS": spell_ids,
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="ascii", newline="\n")


def _copy_spell(source_name: str, destination: Path) -> None:
    shutil.copy2(ORIGINALS / f"{source_name}.spl.orig", destination)


def build_fixture(
    root: Path,
    *,
    mop_layout: str = "current",
    breach_layout: str = "valid",
    scripts: bool = True,
    sr_absent: bool = False,
    all_replacements_false: bool = False,
    alternate_ids: bool = False,
) -> dict[str, tuple[int, str]]:
    root.mkdir(parents=True)
    ids = dict(DEFAULT_IDS)
    if alternate_ids:
        ids.update(
            {
                "pfmw": (2644, "SPWI644"),
                "mantle": (2755, "SPWI755"),
                "improved": (2855, "SPWI855"),
                "mop": (2855, "SPWI855"),
                "absolute": (2966, "SPWI966"),
            }
        )
    spell_ids = _ids_text(ids, sr_absent=sr_absent)
    _write_minimal_script_ids(root, spell_ids)

    donors = {
        "pfmw": "SPWI611",
        "mantle": "SPWI708",
        "absolute": "SPWI907",
    }
    for key, donor in donors.items():
        destination = root / f"{ids[key][1]}.SPL"
        spell = read_spl(ORIGINALS / f"{donor}.spl.orig")
        if all_replacements_false:
            write_spl(destination, _remove_weapon_effects(spell))
        else:
            _copy_spell(donor, destination)

    improved_destination = root / f"{ids['improved'][1]}.SPL"
    if sr_absent:
        # The improved symbol resolves to the already-written real Mantle resource,
        # while Moment of Prescience remains independently available at SPWI808.
        write_spl(root / f"{ids['mop'][1]}.SPL", _mop_variant("current"))
    else:
        write_spl(improved_destination, _mop_variant(mop_layout))

    breach, breach_helper = _breach_graph(7 if breach_layout == "valid" else 3)
    write_spl(root / f"{ids['breach'][1]}.SPL", breach)
    if breach_layout != "missing":
        write_spl(root / "CBRBRH1.SPL", breach_helper)
    write_spl(root / f"{ids['dispel'][1]}.SPL", _dispel_spell())

    if scripts:
        for source, destination in COMMON_SCRIPT_MAP.items():
            shutil.copy2(FIXTURES / source, root / destination)
        # Same target bytes under names outside the allowlist.
        shutil.copy2(FIXTURES / "first_round.bcs", root / "bheye.bcs")
        shutil.copy2(FIXTURES / "first_round.bcs", root / "dw#mgx.bcs")
    return ids


def _snapshot(
    root: Path,
    *,
    exclude_harness: bool = True,
    casefold_paths: bool = False,
) -> dict[str, bytes]:
    result = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if exclude_harness and relative.upper().startswith("CBR_TEST."):
            continue
        # WeiDU v249 restores backed-up resource filenames in uppercase on
        # Windows.  Resource lookup is case-insensitive, so uninstall checks
        # normalize only the path spelling while retaining the full file set
        # and exact bytes.
        if casefold_paths:
            relative = relative.casefold()
        result[relative] = path.read_bytes()
    return result


def _parse_report(root: Path) -> dict[str, str]:
    report = root / "CBR_TEST.REPORT"
    result = {}
    for line in report.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _run_harness(
    fixture: Fixture,
    phase: str,
    *,
    probe_resref: str = "NONE",
    run_temporary: tempfile.TemporaryDirectory[str] | None = None,
    operation: str = "--force-install-list",
) -> HarnessResult:
    if run_temporary is None:
        run_temporary = tempfile.TemporaryDirectory(prefix="cbr-scs-weidu-")
    run_dir = Path(run_temporary.name)
    component = PHASE_COMPONENT[phase]
    process = subprocess.run(
        [
            str(WEIDU),
            str(HARNESS),
            "--nogame",
            "--search-ids",
            str(fixture.root),
            operation,
            component,
            "--args",
            str(PRODUCTION_TPA),
            "--args",
            str(fixture.root),
            "--args",
            probe_resref,
            "--no-exit-pause",
            "--quick-log",
        ],
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return HarnessResult(
        process=process,
        run_temporary=run_temporary,
        run_dir=run_dir,
        fixture=fixture,
        component=component,
        probe_resref=probe_resref,
    )


def _roundtrip_bcs(source: Path, ids_root: Path) -> tuple[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="cbr-scs-bcs-") as temporary:
        scratch = Path(temporary)
        decompile = subprocess.run(
            [
                str(WEIDU),
                "--nogame",
                "--search-ids",
                str(ids_root),
                str(source),
                "--no-exit-pause",
            ],
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if decompile.returncode != 0:
            raise AssertionError(f"fixture decompile failed:\n{decompile.stdout}\n{decompile.stderr}")
        baf = scratch / f"{source.stem}.baf"
        if not baf.is_file():
            raise AssertionError(f"WeiDU did not emit {baf}")
        text = baf.read_text(encoding="utf-8", errors="replace")
        compile_result = subprocess.run(
            [
                str(WEIDU),
                "--nogame",
                "--search-ids",
                str(ids_root),
                str(baf),
                "--no-exit-pause",
            ],
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if compile_result.returncode != 0:
            raise AssertionError(
                f"fixture recompile failed:\n{compile_result.stdout}\n{compile_result.stderr}"
            )
        compiled = scratch / f"{source.stem}.bcs"
        if not compiled.is_file():
            raise AssertionError(
                f"WeiDU did not emit {compiled}:\n"
                f"{compile_result.stdout}\n{compile_result.stderr}"
            )
        return text, compiled.read_bytes()


class ScsWeaponFixtureTests(unittest.TestCase):
    def test_bcs_fixtures_are_live_shaped_and_hermetic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-scs-ids-") as temporary:
            ids_root = Path(temporary)
            _write_minimal_script_ids(ids_root, _ids_text(DEFAULT_IDS))
            expected_context = {
                "first_round.bcs": "Global(\"instantprep\",\"LOCALS\",0)",
                "renew.bcs": "SetGlobalTimer(\"justdonepmw\",\"LOCALS\",7)",
                "chain_contingency.bcs": "ReallyForceSpellRES(\"dw#cc23\",Myself)",
                "unrelated_mop.bcs": "Global(\"instantprep\",\"LOCALS\",2)",
            }
            for name, expected_hash in FIXTURE_HASHES.items():
                with self.subTest(name=name):
                    source = FIXTURES / name
                    self.assertEqual(_sha256(source), expected_hash)
                    baf, roundtripped = _roundtrip_bcs(source, ids_root)
                    self.assertIn(expected_context[name], baf)
                    self.assertEqual(roundtripped, source.read_bytes())
                    self.assertFalse(source.with_suffix(".baf").exists())

        donor_by_fixture = {
            "first_round.bcs": ORIGINALS / "dw#mg144.bcs.orig",
            "renew.bcs": ORIGINALS / "dw#mg148.bcs.orig",
            "chain_contingency.bcs": ORIGINALS / "dw#mg14.bcs.orig",
        }
        for name, donor in donor_by_fixture.items():
            target = [block for block in _raw_bcs_blocks(FIXTURES / name) if b"2808" in block]
            self.assertEqual(len(target), 1, name)
            self.assertIn(target[0], _raw_bcs_blocks(donor), name)

    def test_spell_fixture_semantics_and_metadata_helpers(self) -> None:
        mop = _mop_variant("current")
        self.assertEqual(mop.metadata_key(), (349223, 349224, 1, 3, 7, 8, "DVWI808C"))
        self.assertFalse(any(effect.opcode == 120 for effect in mop.all_effects()))
        self.assertTrue(any(effect.opcode == 233 and effect.parameter2 == 128 for effect in mop.all_effects()))
        self.assertTrue(any(effect.opcode == 328 and effect.parameter2 == 64 for effect in mop.all_effects()))
        future = _mop_variant("future_true")
        self.assertEqual(future.metadata_key(), mop.metadata_key())
        self.assertTrue(any(effect.opcode == 120 for effect in future.all_effects()))
        for name in ("SPWI611", "SPWI708", "SPWI907"):
            self.assertTrue(
                any(effect.opcode == 120 for effect in read_spl(ORIGINALS / f"{name}.spl.orig").all_effects()),
                name,
            )


class ProductionLibraryGateTests(unittest.TestCase):
    def test_component_120_library_exists(self) -> None:
        self.assertTrue(
            PRODUCTION_TPA.is_file(),
            "intentional RED: missing production library "
            "chriz-bg-rebalance/lib/scs_weapon_protection_semantics.tpa",
        )


@unittest.skipUnless(
    PRODUCTION_TPA.is_file(),
    "component-120 production library is intentionally absent during Task 2 RED",
)
class ScsWeaponSemanticsTests(unittest.TestCase):
    def _fixture(self, **kwargs: object) -> Fixture:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-scs-semantics-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "working"
        ids = build_fixture(root, **kwargs)
        return Fixture(temporary=temporary, root=root, ids=ids)

    def _run(self, fixture: Fixture, phase: str, *, probe: str = "NONE") -> HarnessResult:
        result = _run_harness(fixture, phase, probe_resref=probe)
        self.addCleanup(result.run_temporary.cleanup)
        self.assertTrue(result.succeeded, result.transcript)
        return result

    def test_spell_classification(self) -> None:
        expected = {
            "SPWI611": "1",
            "SPWI708": "1",
            "SPWI808": "0",
            "SPWI907": "1",
        }
        for resref, classification in expected.items():
            with self.subTest(resref=resref):
                fixture = self._fixture(scripts=False)
                self._run(fixture, "classify", probe=resref)
                self.assertEqual(_parse_report(fixture.root)["is_weapon_protection"], classification)

        future = self._fixture(mop_layout="future_true", scripts=False)
        self._run(future, "classify", probe="SPWI808")
        future_report = _parse_report(future.root)
        self.assertEqual(future_report["is_weapon_protection"], "1")
        self.assertEqual(future_report["mismatch"], "0")

        alternate = self._fixture(alternate_ids=True, scripts=False)
        self._run(alternate, "classify", probe="SPWI855")
        alternate_report = _parse_report(alternate.root)
        self.assertEqual(alternate_report["is_weapon_protection"], "0")
        self.assertEqual(alternate_report["candidates"], "SPWI966,SPWI755,SPWI644")

    def test_metadata_patch_is_surgical_and_counter_aware(self) -> None:
        fixture = self._fixture(mop_layout="near_markers")
        target = fixture.root / "SPWI808.SPL"
        before = read_spl(target)
        before_scripts = {name: (fixture.root / name).read_bytes() for name in COMMON_SCRIPT_MAP.values()}
        self._run(fixture, "metadata")
        after = read_spl(target)

        def removed(effect: SplEffect) -> bool:
            return (
                (effect.opcode == 233 and effect.parameter1 == 2 and effect.parameter2 == 128)
                or (effect.opcode == 328 and effect.parameter1 == 1 and effect.parameter2 in (64, 188))
            )

        self.assertEqual(after.metadata_key(), before.metadata_key())
        self.assertEqual(after.casting_effects, before.casting_effects)
        self.assertEqual(after.abilities[0].required_level, before.abilities[0].required_level)
        self.assertEqual(after.abilities[0].target, before.abilities[0].target)
        self.assertEqual(after.abilities[0].projectile, before.abilities[0].projectile)
        self.assertEqual(
            tuple(effect.canonical() for effect in after.abilities[0].effects),
            tuple(effect.canonical() for effect in before.abilities[0].effects if not removed(effect)),
        )
        self.assertTrue(any(effect.opcode == 328 and effect.parameter2 == 187 for effect in after.all_effects()))
        self.assertTrue(any(effect.opcode == 233 and effect.parameter2 == 129 for effect in after.all_effects()))
        self.assertTrue(any(effect.opcode == 233 and effect.parameter1 == 3 for effect in after.all_effects()))
        self.assertTrue(any(effect.opcode == 328 and effect.parameter2 == 65 for effect in after.all_effects()))
        self.assertEqual(_parse_report(fixture.root)["metadata_removed"], "3")
        for name, raw in before_scripts.items():
            self.assertEqual((fixture.root / name).read_bytes(), raw)

        dispellable = self._fixture(mop_layout="dispellable")
        self._run(dispellable, "metadata")
        dispellable_after = read_spl(dispellable.root / "SPWI808.SPL")
        self.assertTrue(
            any(effect.opcode == 328 and effect.parameter2 == 188 for effect in dispellable_after.all_effects())
        )

        not_breachable = self._fixture(breach_layout="wrong")
        self._run(not_breachable, "metadata")
        not_breachable_after = read_spl(not_breachable.root / "SPWI808.SPL")
        self.assertFalse(
            any(effect.opcode == 328 and effect.parameter2 == 187 for effect in not_breachable_after.all_effects())
        )

    def test_first_round_and_renewal_blocks(self) -> None:
        fixture = self._fixture()
        unrelated_before = (fixture.root / "dw#mg103.bcs").read_bytes()
        bheye_before = (fixture.root / "bheye.bcs").read_bytes()
        invalid_name_before = (fixture.root / "dw#mgx.bcs").read_bytes()
        self._run(fixture, "scripts")
        report = _parse_report(fixture.root)
        self.assertEqual(report["first_round_removed"], "1")
        self.assertEqual(report["renewal_removed"], "1")

        for name, before_sentinel, after_sentinel in (
            ("dw#mg100.bcs", "cbr_fr_before", "cbr_fr_after"),
            ("dw#mg101.bcs", "cbr_renew_before", "cbr_renew_after"),
        ):
            baf, _ = _roundtrip_bcs(fixture.root / name, fixture.root)
            self.assertNotIn("WIZARD_MOMENT_OF_PRESCIENCE", baf)
            self.assertIn("WIZARD_MANTLE", baf)
            self.assertIn(before_sentinel, baf)
            self.assertIn(after_sentinel, baf)

        self.assertEqual((fixture.root / "dw#mg103.bcs").read_bytes(), unrelated_before)
        self.assertEqual((fixture.root / "bheye.bcs").read_bytes(), bheye_before)
        self.assertEqual((fixture.root / "dw#mgx.bcs").read_bytes(), invalid_name_before)

    def test_chain_contingency(self) -> None:
        fixture = self._fixture()
        self._run(fixture, "scripts")
        report = _parse_report(fixture.root)
        self.assertEqual(report["chain_replaced"], "1")
        self.assertEqual(report["replacement"], "SPWI708")
        baf, _ = _roundtrip_bcs(fixture.root / "dw#mg102.bcs", fixture.root)
        self.assertIn('ReallyForceSpellRES("dw#cc23",Myself)', baf)
        self.assertIn("ReallyForceSpell(Myself,WIZARD_MANTLE)", baf)
        self.assertNotIn("WIZARD_MOMENT_OF_PRESCIENCE", baf)
        self.assertIn("cbr_chain_before", baf)
        self.assertIn("cbr_chain_after", baf)

    def test_unknown_scope_and_noop_matrix(self) -> None:
        fixture = self._fixture()
        unrelated_before = (fixture.root / "dw#mg103.bcs").read_bytes()
        self._run(fixture, "scripts")
        self.assertEqual(_parse_report(fixture.root)["unknown_blocks"], "1")
        self.assertEqual((fixture.root / "dw#mg103.bcs").read_bytes(), unrelated_before)

        for kwargs in (
            {"scripts": False},
            {"mop_layout": "future_true"},
            {"sr_absent": True},
        ):
            with self.subTest(kwargs=kwargs):
                noop = self._fixture(**kwargs)
                before = _snapshot(noop.root)
                self._run(noop, "full")
                self.assertEqual(_snapshot(noop.root), before)

    def test_preflight_rejects_unsafe_graphs_atomically(self) -> None:
        cases = (
            {"mop_layout": "duplicate_markers"},
            {"breach_layout": "missing"},
            {"all_replacements_false": True},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                fixture = self._fixture(**kwargs)
                before = _snapshot(fixture.root)
                result = _run_harness(fixture, "full")
                self.addCleanup(result.run_temporary.cleanup)
                self.assertFalse(result.succeeded, result.transcript)
                self.assertEqual(_snapshot(fixture.root), before)

        malformed = self._fixture()
        target = malformed.root / "SPWI808.SPL"
        target.write_bytes(target.read_bytes()[:0x80])
        before = _snapshot(malformed.root)
        result = _run_harness(malformed, "full")
        self.addCleanup(result.run_temporary.cleanup)
        self.assertFalse(result.succeeded, result.transcript)
        self.assertEqual(_snapshot(malformed.root), before)

    def test_second_application_is_byte_identical(self) -> None:
        fixture = self._fixture()
        first = self._run(fixture, "full")
        first_snapshot = _snapshot(fixture.root)
        second = self._run(fixture, "full")
        self.assertEqual(_snapshot(fixture.root), first_snapshot, second.transcript)
        self.assertNotEqual(first.run_dir, second.run_dir)

    def test_uninstall_restores_every_prior_byte(self) -> None:
        fixture = self._fixture()
        before = _snapshot(
            fixture.root,
            exclude_harness=False,
            casefold_paths=True,
        )
        run_temporary = tempfile.TemporaryDirectory(prefix="cbr-scs-uninstall-")
        self.addCleanup(run_temporary.cleanup)
        installed = _run_harness(fixture, "full", run_temporary=run_temporary)
        self.assertTrue(installed.succeeded, installed.transcript)
        removed = _run_harness(
            fixture,
            "full",
            run_temporary=run_temporary,
            operation="--force-uninstall-list",
        )
        self.assertNotIn("NOT UNINSTALLED", removed.transcript, removed.transcript)
        self.assertEqual(
            _snapshot(
                fixture.root,
                exclude_harness=False,
                casefold_paths=True,
            ),
            before,
        )


if __name__ == "__main__":
    unittest.main()
