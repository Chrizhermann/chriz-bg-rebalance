"""Hermetic WeiDU tests for component 121's runtime-manifest compiler.

Every invocation runs under ``--nogame`` against a synthetic resource tree.
The active BG2:EE install is never consulted or written.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import (
    SplAbility,
    SplEffect,
    SplFile,
    make_spl_header,
    write_spl,
)
from tests.test_ambient_readiness_listener import _find_lua


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "ambient_readiness_harness.tp2"
WEAPON_TPA = (
    ROOT / "chriz-bg-rebalance" / "lib" / "scs_weapon_protection_semantics.tpa"
)
PRODUCTION_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "ambient_readiness.tpa"
SPELL_TABLE = ROOT / "chriz-bg-rebalance" / "data" / "ambient_readiness_spells.2da"
OVERRIDE_TABLE = (
    ROOT / "chriz-bg-rebalance" / "data" / "ambient_readiness_overrides.2da"
)


AMBIENT = (
    ("CLERIC_IMPERVIOUS_SANCTITY_OF_MIND", 1735, "SPPR735", "DWSP735", 206, 0, 2880),
    ("CLERIC_IRONSKIN", 1506, "SPPR506", "DWSP506", 218, 0, 2400),
    ("WIZARD_ARMOR", 2102, "SPWI102", "DWSW102", 0, 16, 2400),
    ("WIZARD_MIND_BLANK", 2802, "SPWI802", "DWSW802", 101, 213, 7200),
    ("WIZARD_NON_DETECTION", 2310, "SPWI310", "DWSW310", 69, 0, 2400),
    ("WIZARD_STONE_SKIN", 2408, "SPWI408", "DWSW408", 218, 0, 2400),
)

URGENT = (
    ("WIZARD_ABSOLUTE_IMMUNITY", 2907, "SPWI907", True),
    ("WIZARD_IMPROVED_MANTLE", 2808, "SPWI808", False),
    ("WIZARD_MANTLE", 2708, "SPWI708", True),
    ("WIZARD_PROTECTION_FROM_MAGIC_WEAPONS", 2611, "SPWI611", True),
)


@dataclasses.dataclass
class Fixture:
    temporary: tempfile.TemporaryDirectory[str]
    root: Path
    spell_table: Path
    override_table: Path
    spell_ids: Path
    prebuff_map: Path
    output: Path


def _ambient_spell(
    *,
    symbol: str,
    opcode: int,
    parameter2: int,
    duration: int,
    ability_target: int = 5,
    effect_target: int = 1,
    spell_type: int | None = None,
) -> SplFile:
    if spell_type is None:
        spell_type = 2 if symbol.startswith("CLERIC_") else 1
    return SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=ability_target,
                projectile=1,
                effects=(
                    SplEffect(
                        opcode=opcode,
                        target=effect_target,
                        power=1,
                        parameter2=parameter2,
                        timing=0,
                        resist_dispel=3,
                        duration=duration,
                        probability1=100,
                        probability2=0,
                    ),
                ),
            ),
        ),
        header_raw=make_spl_header(spell_type=spell_type, level=1),
    )


def _urgent_spell(*, genuine: bool) -> SplFile:
    effect = SplEffect(
        opcode=120 if genuine else 0,
        target=1,
        power=8,
        parameter1=0 if genuine else -4,
        parameter2=2 if genuine else 0,
        timing=0,
        resist_dispel=3,
        duration=24,
        probability1=100,
        probability2=0,
    )
    return SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=5,
                projectile=1,
                effects=(effect,),
            ),
        ),
        header_raw=make_spl_header(spell_type=1, level=8),
    )


def _build_fixture(
    temporary: tempfile.TemporaryDirectory[str],
    *,
    missing_symbol: str | None = None,
    missing_delivery: str | None = None,
    unsupported: str | None = None,
    duplicate_override: bool = False,
    duplicate_required_symbol: bool = False,
    future_improved_mantle: bool = False,
) -> Fixture:
    root = Path(temporary.name) / "fixture"
    root.mkdir()
    spell_table = root / "ambient_readiness_spells.2da"
    override_table = root / "ambient_readiness_overrides.2da"
    shutil.copy2(SPELL_TABLE, spell_table)
    shutil.copy2(OVERRIDE_TABLE, override_table)

    ids_lines = ["IDS V1.0"]
    for symbol, value, _, _, _, _, _ in AMBIENT:
        if symbol != missing_symbol:
            ids_lines.append(f"{value} {symbol}")
    for symbol, value, _, _ in URGENT:
        ids_lines.append(f"{value} {symbol}")
        if duplicate_required_symbol and symbol == "WIZARD_PROTECTION_FROM_MAGIC_WEAPONS":
            ids_lines.append(f"{value + 1} {symbol}")
    spell_ids = root / "SPELL.IDS"
    spell_ids.write_text("\n".join(ids_lines) + "\n", encoding="ascii", newline="\n")

    mapping_lines = []
    for symbol, _, resref, delivery, opcode, parameter2, duration in AMBIENT:
        mapping_lines.append(f"{symbol}_PREBUFF {delivery.lower()}")
        source_kwargs: dict[str, object] = {}
        delivery_kwargs: dict[str, object] = {}
        marker_opcode = opcode
        marker_duration = duration
        if symbol == "WIZARD_ARMOR":
            if unsupported == "short_duration":
                marker_duration = 300
            elif unsupported == "non_self":
                source_kwargs.update(ability_target=4, effect_target=2)
                delivery_kwargs.update(ability_target=4, effect_target=2)
            elif unsupported == "non_defensive":
                marker_opcode = 12
            elif unsupported == "no_memorized_delivery":
                source_kwargs.update(spell_type=0)
        write_spl(
            root / f"{resref}.SPL",
            _ambient_spell(
                symbol=symbol,
                opcode=marker_opcode,
                parameter2=parameter2,
                duration=marker_duration,
                **source_kwargs,
            ),
        )
        if delivery != missing_delivery:
            write_spl(
                root / f"{delivery}.SPL",
                _ambient_spell(
                    symbol=symbol,
                    opcode=marker_opcode,
                    parameter2=parameter2,
                    duration=marker_duration,
                    **delivery_kwargs,
                ),
            )
    prebuff_map = root / "instant_prebuff_spells.2da"
    prebuff_map.write_text(
        "\n".join(mapping_lines) + "\n", encoding="ascii", newline="\n"
    )

    for symbol, _, resref, genuine in URGENT:
        write_spl(
            root / f"{resref}.SPL",
            _urgent_spell(
                genuine=(True if symbol == "WIZARD_IMPROVED_MANTLE" and future_improved_mantle else genuine)
            ),
        )

    if duplicate_override:
        override_table.write_text(
            """2DA V1.0
*
GRADE INCLUDE EXCLUDE
CBRTEST 1 - -
CBRTEST 0 - -
""",
            encoding="ascii",
            newline="\n",
        )

    return Fixture(
        temporary=temporary,
        root=root,
        spell_table=spell_table,
        override_table=override_table,
        spell_ids=spell_ids,
        prebuff_map=prebuff_map,
        output=root / "manifest.lua",
    )


def _run_harness(fixture: Fixture) -> subprocess.CompletedProcess[str]:
    run_directory = Path(fixture.temporary.name) / "run"
    run_directory.mkdir(exist_ok=True)
    return subprocess.run(
        [
            str(WEIDU),
            str(HARNESS),
            "--nogame",
            "--search-ids",
            str(fixture.root),
            "--force-install-list",
            "0",
            "--args",
            str(WEAPON_TPA),
            "--args",
            str(PRODUCTION_TPA),
            "--args",
            str(fixture.spell_table),
            "--args",
            str(fixture.override_table),
            "--args",
            str(fixture.root),
            "--args",
            str(fixture.spell_ids),
            "--args",
            str(fixture.prebuff_map),
            "--args",
            str(fixture.output),
            "--no-exit-pause",
            "--quick-log",
        ],
        cwd=run_directory,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _transcript(process: subprocess.CompletedProcess[str]) -> str:
    return f"{process.stdout}\n{process.stderr}".strip()


class ProductionManifestGateTests(unittest.TestCase):
    def test_component_121_manifest_assets_exist(self) -> None:
        missing = [
            path.relative_to(ROOT).as_posix()
            for path in (PRODUCTION_TPA, SPELL_TABLE, OVERRIDE_TABLE)
            if not path.is_file()
        ]
        self.assertFalse(
            missing,
            "intentional RED: component 121 manifest assets are absent: "
            + ", ".join(missing),
        )


@unittest.skipUnless(
    PRODUCTION_TPA.is_file() and SPELL_TABLE.is_file() and OVERRIDE_TABLE.is_file(),
    "Task 7 has not created the production manifest compiler and data tables",
)
class AmbientReadinessManifestTests(unittest.TestCase):
    def _fixture(self, **kwargs: object) -> Fixture:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-rdy-manifest-")
        self.addCleanup(temporary.cleanup)
        return _build_fixture(temporary, **kwargs)

    def _run_success(self, fixture: Fixture) -> subprocess.CompletedProcess[str]:
        process = _run_harness(fixture)
        transcript = _transcript(process)
        self.assertEqual(process.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertTrue(fixture.output.is_file(), transcript)
        return process

    def _read_with_lua(self, fixture: Fixture, expression: str) -> str:
        lua = _find_lua()
        if lua is None:
            self.skipTest("no Lua interpreter found")
        script = (
            f"local m=dofile([[{fixture.output.resolve().as_posix()}]]);"
            f"io.write({expression})"
        )
        process = subprocess.run(
            [lua, "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        return process.stdout

    def test_current_scs_sr_manifest_is_complete_sorted_and_ascii(self) -> None:
        fixture = self._fixture()
        self._run_success(fixture)
        raw = fixture.output.read_bytes()
        text = raw.decode("ascii")
        self.assertNotIn("%", text)
        self.assertEqual(text.count("schema_version = 1"), 1)
        self.assertEqual(
            self._read_with_lua(
                fixture,
                "#m.ambient_spells, '\\t', #m.urgent_candidates, '\\t', "
                "m.urgent_candidates[2].genuine_weapon_immunity",
            ),
            "6\t4\t0",
        )
        positions = [text.index(f'key = "{row[0]}"') for row in AMBIENT]
        self.assertEqual(positions, sorted(positions))

    def test_missing_optional_symbol_or_delivery_is_skipped_with_diagnostic(self) -> None:
        cases = (
            ({"missing_symbol": "WIZARD_ARMOR"}, "missing SPELL.IDS symbol"),
            ({"missing_delivery": "DWSW102"}, "missing prebuff delivery resource"),
        )
        for kwargs, diagnostic in cases:
            with self.subTest(kwargs=kwargs):
                fixture = self._fixture(**kwargs)
                process = self._run_success(fixture)
                self.assertIn(diagnostic, _transcript(process))
                self.assertEqual(
                    self._read_with_lua(fixture, "#m.ambient_spells"), "5"
                )

    def test_unsupported_optional_ambient_semantics_are_skipped(self) -> None:
        for unsupported in (
            "short_duration",
            "non_self",
            "non_defensive",
            "no_memorized_delivery",
        ):
            with self.subTest(unsupported=unsupported):
                fixture = self._fixture(unsupported=unsupported)
                process = self._run_success(fixture)
                self.assertIn("unsupported ambient semantics", _transcript(process))
                self.assertEqual(
                    self._read_with_lua(fixture, "#m.ambient_spells"), "5"
                )

    def test_duplicate_override_or_required_symbol_fails_before_output(self) -> None:
        for kwargs, diagnostic in (
            ({"duplicate_override": True}, "duplicate override"),
            ({"duplicate_required_symbol": True}, "maps more than once"),
        ):
            with self.subTest(kwargs=kwargs):
                fixture = self._fixture(**kwargs)
                fixture.output.write_bytes(b"sentinel-before-preflight")
                process = _run_harness(fixture)
                self.assertNotEqual(process.returncode, 0, _transcript(process))
                self.assertIn(diagnostic, _transcript(process))
                self.assertEqual(fixture.output.read_bytes(), b"sentinel-before-preflight")

    def test_future_restored_improved_mantle_is_truthfully_enabled(self) -> None:
        fixture = self._fixture(future_improved_mantle=True)
        self._run_success(fixture)
        self.assertEqual(
            self._read_with_lua(
                fixture, "m.urgent_candidates[2].genuine_weapon_immunity"
            ),
            "1",
        )

    def test_second_application_is_byte_identical(self) -> None:
        fixture = self._fixture()
        self._run_success(fixture)
        first = fixture.output.read_bytes()
        self._run_success(fixture)
        self.assertEqual(fixture.output.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
