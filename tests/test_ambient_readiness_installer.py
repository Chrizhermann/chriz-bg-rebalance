"""Hermetic WeiDU tests for component 121's runtime-manifest compiler.

Every invocation runs under ``--nogame`` against a synthetic resource tree.
The active BG2:EE install is never consulted or written.
"""

from __future__ import annotations

import dataclasses
import re
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
from tests.test_tempus_holy_power_installer import (
    ONE_EMPTY_STRING_TLK,
    _write_key_and_bif,
)


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
SETUP_TP2 = ROOT / "setup-chriz-bg-rebalance.tp2"
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

PROJECT_IMAGE = ("WIZARD_PROJECT_IMAGE", 2703, "SPWI703")


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
    project_image_number: int = PROJECT_IMAGE[1],
    missing_project_image_symbol: bool = False,
    missing_project_image_resource: bool = False,
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
    if not missing_project_image_symbol:
        ids_lines.append(f"{project_image_number} {PROJECT_IMAGE[0]}")
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

    project_image_resref = f"SPWI{project_image_number - 2000:03d}"
    if not missing_project_image_resource:
        write_spl(root / f"{project_image_resref}.SPL", _urgent_spell(genuine=False))

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


def _tree(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix().upper(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


class AmbientReadinessGame:
    """Minimal BG2EE game for the real public component 121 transaction."""

    def __init__(
        self,
        temporary: tempfile.TemporaryDirectory[str],
        *,
        scs_installed: bool = True,
        eeex_base: bool = True,
        eeex_luajit: bool = True,
        autoload_marker: bool = True,
        prebuff_map: bool = True,
        malformed_mapping: bool = False,
        missing_required_mapping: bool = False,
        existing_runtime: bool = False,
        **fixture_kwargs: object,
    ) -> None:
        self.temporary = temporary
        self.fixture = _build_fixture(temporary, **fixture_kwargs)
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        self.override.mkdir()

        shutil.copy2(SETUP_TP2, self.root / SETUP_TP2.name)
        shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")
        if missing_required_mapping:
            table_path = (
                self.root
                / "chriz-bg-rebalance"
                / "data"
                / "ambient_readiness_spells.2da"
            )
            table_text = table_path.read_text(encoding="ascii")
            table_text = table_text.replace(
                "WIZARD_STONE_SKIN 1 2400 218 0 0",
                "WIZARD_STONE_SKIN 1 2400 218 0 1",
            )
            table_path.write_text(table_text, encoding="ascii", newline="\n")
        for source in self.fixture.root.iterdir():
            if source.is_file() and (
                source.suffix.upper() == ".SPL" or source.name.upper() == "SPELL.IDS"
            ):
                shutil.copy2(source, self.override / source.name)
        (self.override / "KIT.IDS").write_text(
            "IDS V1.0\n0 NONE\n", encoding="ascii", newline="\n"
        )
        (self.override / "STATS.IDS").write_text(
            "IDS V1.0\n1 STREXTRA\n", encoding="ascii", newline="\n"
        )
        (self.override / "dw#mg100.bcs").write_bytes(
            b"synthetic SCS common-mage script sentinel\r\n"
        )
        if autoload_marker:
            (self.override / "M___EEex.lua").write_text(
                "if not EEex_Active then error('EEex not active') end\n",
                encoding="ascii",
                newline="\n",
            )
        if existing_runtime:
            (self.override / "M_CBRRDY.lua").write_bytes(
                b"-- prior ambient-readiness runtime to restore on uninstall\r\n"
            )

        external = self.root / "weidu_external" / "data" / "stratagems"
        if prebuff_map:
            external.mkdir(parents=True)
            mapping = self.fixture.prebuff_map.read_text(encoding="ascii")
            if malformed_mapping:
                mapping += "WIZARD_STONE_SKIN_PREBUFF DWSW999\n"
            if missing_required_mapping:
                mapping = "\n".join(
                    line
                    for line in mapping.splitlines()
                    if not line.startswith("WIZARD_STONE_SKIN_PREBUFF ")
                ) + "\n"
            (external / "instant_prebuff_spells.2da").write_text(
                mapping, encoding="ascii", newline="\n"
            )

        log_lines: list[str] = []
        if eeex_base:
            log_lines.extend(
                (
                    "~EEEX/EEEX.TP2~ #0 #0 // Quick Menu Core: v1.2.0",
                    "~EEEX/EEEX.TP2~ #0 #1 // EEex: v1.2.0",
                )
            )
        if eeex_luajit:
            log_lines.append(
                "~EEEX/EEEX.TP2~ #0 #8 // Experimental - Use LuaJIT: v1.2.0"
            )
        if scs_installed:
            log_lines.append(
                "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #6030 // Smarter Mages: 35.21"
            )
        if log_lines:
            (self.root / "WeiDU.log").write_text(
                "\n".join(log_lines) + "\n", encoding="ascii", newline="\n"
            )

        self.bif_path = _write_key_and_bif(
            self.root,
            (("OH6000", "ARE", b"synthetic BG2EE marker"),),
        )
        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.before_override = _tree(self.override)
        self.before_spell_and_script = {
            key: value
            for key, value in self.before_override.items()
            if key.endswith((".SPL", ".BCS"))
        }

    def run(self, *operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(WEIDU),
                str(self.root / SETUP_TP2.name),
                "--game",
                str(self.root),
                *operation,
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    @staticmethod
    def transcript(process: subprocess.CompletedProcess[str]) -> str:
        return _transcript(process)

    def active_weidu_log(self) -> str:
        path = self.root / "WeiDU.log"
        if not path.exists():
            return ""
        return "\n".join(
            line
            for line in path.read_text(
                encoding="ascii", errors="replace"
            ).splitlines()
            if not line.lstrip().startswith("//")
        )


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
                "m.urgent_candidates[2].genuine_weapon_immunity, '\\t', "
                "m.project_image_resref",
            ),
            "6\t4\t0\tspwi703",
        )
        positions = [text.index(f'key = "{row[0]}"') for row in AMBIENT]
        self.assertEqual(positions, sorted(positions))

    def test_project_image_identity_is_resolved_from_installed_spell_ids(self) -> None:
        fixture = self._fixture(project_image_number=2903)
        self._run_success(fixture)
        self.assertEqual(
            self._read_with_lua(fixture, "m.project_image_resref"), "spwi903"
        )

    def test_missing_project_image_identity_fails_before_output(self) -> None:
        for kwargs, diagnostic in (
            ({"missing_project_image_symbol": True}, "WIZARD_PROJECT_IMAGE"),
            ({"missing_project_image_resource": True}, "SPWI703.SPL"),
        ):
            with self.subTest(kwargs=kwargs):
                fixture = self._fixture(**kwargs)
                fixture.output.write_bytes(b"sentinel-before-project-image-preflight")
                process = _run_harness(fixture)
                self.assertNotEqual(process.returncode, 0, _transcript(process))
                self.assertIn(diagnostic, _transcript(process))
                self.assertEqual(
                    fixture.output.read_bytes(),
                    b"sentinel-before-project-image-preflight",
                )

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


class AmbientReadinessPublicInstallerTests(unittest.TestCase):
    def _game(self, **kwargs: object) -> AmbientReadinessGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-rdy-public-")
        self.addCleanup(temporary.cleanup)
        return AmbientReadinessGame(temporary, **kwargs)

    def _install(self, game: AmbientReadinessGame) -> str:
        process = game.run("--force-install-list", "121")
        transcript = game.transcript(process)
        self.assertEqual(process.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertRegex(game.active_weidu_log(), r"(?m)#0\s+#121\b")
        return transcript

    def _runtime(self, game: AmbientReadinessGame) -> str:
        path = game.override / "M_CBRRDY.lua"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="ascii")
        self.assertNotIn("%CBR_RDY_MANIFEST%", source)
        self.assertIn('target_eeex_version = "1.2.0"', source)
        self.assertNotIn("requires_base_component", source)
        self.assertNotIn("requires_luajit_component", source)
        self.assertIn('project_image_resref = "spwi703"', source)
        self.assertNotIn("CBR_TEST", source)
        self.assertNotIn("RDY_PROBE", source)
        self.assertNotIn("C:\\", source)
        self.assertNotIn("/mnt/", source)
        self.assertNotIn(" << ", source)
        self.assertNotIn(" & ", source)
        self.assertNotIn(" | ", source)
        lua = _find_lua()
        if lua is not None:
            parsed = subprocess.run(
                [lua, "-e", f"assert(loadfile([[{path.resolve().as_posix()}]]))"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
        return source

    @staticmethod
    def _urgent_genuine(source: str, symbol: str) -> int:
        match = re.search(
            rf'key = "{re.escape(symbol)}".*?genuine_weapon_immunity = ([01])',
            source,
            flags=re.DOTALL,
        )
        if match is None:
            raise AssertionError(f"missing urgent manifest entry for {symbol}")
        return int(match.group(1))

    def test_current_scs_sr_install_ships_only_a_stamped_runtime(self) -> None:
        game = self._game()
        transcript = self._install(game)
        source = self._runtime(game)
        self.assertIn("ambient=6", transcript)
        self.assertIn("urgent=4", transcript)
        self.assertEqual(
            self._urgent_genuine(source, "WIZARD_IMPROVED_MANTLE"), 0
        )
        self.assertEqual(
            {
                key: value
                for key, value in _tree(game.override).items()
                if key.endswith((".SPL", ".BCS"))
            },
            game.before_spell_and_script,
            "component 121 must not patch SCS scripts or spell mechanics",
        )
        self.assertEqual(
            set(_tree(game.override)) - set(game.before_override),
            {"M_CBRRDY.LUA"},
        )

    def test_v12_bootstrap_is_authoritative_not_version_specific_component_ids(self) -> None:
        game = self._game(
            eeex_base=False,
            eeex_luajit=False,
            autoload_marker=True,
        )
        self._install(game)
        self._runtime(game)

    def test_future_genuine_improved_mantle_is_enabled_semantically(self) -> None:
        game = self._game(future_improved_mantle=True)
        self._install(game)
        source = self._runtime(game)
        self.assertEqual(
            self._urgent_genuine(source, "WIZARD_IMPROVED_MANTLE"), 1
        )

    def test_missing_optional_ambient_candidate_still_installs(self) -> None:
        game = self._game(missing_symbol="WIZARD_ARMOR")
        transcript = self._install(game)
        source = self._runtime(game)
        self.assertIn("missing SPELL.IDS symbol", transcript)
        self.assertIn("ambient=5", transcript)
        self.assertNotIn('key = "WIZARD_ARMOR"', source)

    def test_missing_prerequisites_skip_without_override_mutation(self) -> None:
        cases = (
            ("scs", {"scs_installed": False}, "Smarter Mages"),
            (
                "eeex",
                {
                    "eeex_base": False,
                    "eeex_luajit": False,
                    "autoload_marker": False,
                },
                "EEex",
            ),
            ("autoload", {"autoload_marker": False}, "autoload"),
            ("mapping", {"prebuff_map": False}, "prebuff"),
        )
        for name, kwargs, diagnostic in cases:
            with self.subTest(name=name):
                game = self._game(**kwargs)
                process = game.run("--force-install-list", "121")
                transcript = game.transcript(process)
                self.assertEqual(process.returncode, 0, transcript)
                self.assertIn("SKIPPING", transcript, transcript)
                self.assertIn(diagnostic.lower(), transcript.lower())
                self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#121\b")
                self.assertEqual(_tree(game.override), game.before_override)

    def test_malformed_recognized_mapping_fails_before_override_mutation(self) -> None:
        for name, kwargs, diagnostic in (
            ("duplicate", {"malformed_mapping": True}, "maps more than once"),
            (
                "missing_required",
                {"missing_required_mapping": True},
                "required candidate WIZARD_STONE_SKIN has no unique SCS prebuff mapping",
            ),
            (
                "missing_project_image",
                {"missing_project_image_resource": True},
                "required Project Image resource SPWI703.SPL is missing",
            ),
        ):
            with self.subTest(name=name):
                game = self._game(**kwargs)
                process = game.run("--force-install-list", "121")
                transcript = game.transcript(process)
                self.assertNotEqual(process.returncode, 0, transcript)
                self.assertIn(diagnostic, transcript)
                self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#121\b")
                self.assertEqual(_tree(game.override), game.before_override)

    def test_reinstall_is_deterministic_and_uninstall_restores_every_byte(self) -> None:
        game = self._game(existing_runtime=True)
        prior_runtime = (game.override / "M_CBRRDY.lua").read_bytes()
        self._install(game)
        installed = _tree(game.override)
        runtime = (game.override / "M_CBRRDY.lua").read_bytes()
        self.assertNotEqual(runtime, prior_runtime)

        process = game.run(
            "--force-uninstall-list",
            "121",
            "--force-install-list",
            "121",
        )
        transcript = game.transcript(process)
        self.assertEqual(process.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertEqual(_tree(game.override), installed)
        self.assertEqual((game.override / "M_CBRRDY.lua").read_bytes(), runtime)

        removed = game.run("--force-uninstall-list", "121")
        transcript = game.transcript(removed)
        self.assertEqual(removed.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#121\b")
        self.assertEqual(_tree(game.override), game.before_override)

    def test_component_boundaries_are_explicit(self) -> None:
        tp2 = SETUP_TP2.read_text(encoding="utf-8")
        block_120 = re.search(
            r"(?ms)^BEGIN @120\b.*?(?=^BEGIN\b|\Z)", tp2
        )
        block_121 = re.search(
            r"(?ms)^BEGIN @121\b.*?(?=^BEGIN\b|\Z)", tp2
        )
        self.assertIsNotNone(block_120)
        self.assertIsNotNone(block_121, "intentional RED: public component 121 is absent")
        self.assertNotRegex(block_120.group(0), r"(?i)EEex|M___EEex")
        self.assertNotRegex(block_121.group(0), r"(?i)MOD_IS_INSTALLED\s+~eeex/")
        self.assertNotIn("cbr_apply_scs_weapon_protection_semantics", block_121.group(0))
        self.assertNotRegex(block_121.group(0), r"(?i)COPY_EXISTING.*\.(?:SPL|BCS)")


if __name__ == "__main__":
    unittest.main()
