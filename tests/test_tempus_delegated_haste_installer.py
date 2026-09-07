"""Component 401 against byte-exact CEBG non-SR resources, without a live game."""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import read_spl, write_spl
from tests.test_tempus_holy_power import (
    APR_CONDITION_RESREFS,
    APR_HELPER_RESREFS,
    Fixture,
    HARNESS,
    HarnessResult,
    PRODUCTION_TPA,
    ROOT,
    SETUP_TP2,
    STRENGTH_HELPER_RESREFS,
    WEIDU,
    _helper_effect,
    _raw_file_tree,
    _rerun_harness,
)
from tests.test_tempus_holy_power_installer import (
    ONE_EMPTY_STRING_TLK,
    SyntheticGame,
    _casefold_tree,
    _sha256,
    _write_key_and_bif,
)


CAPTURED = ROOT / "research/originals/tempus-no-sr"
BASE_GAME = ROOT / "research/originals/tempus-base-game"
MANIFEST = json.loads((CAPTURED / "manifest.json").read_text(encoding="utf-8"))
CHILD_NAME = "SPWI613A.SPL"
STRENGTH_PUBLICATIONS = {
    f"{resref}.EFF" if resref.startswith("CBRSE") else f"{resref}.SPL"
    for resref in STRENGTH_HELPER_RESREFS
}


def _copy_captured(destination: Path, capture: Path = CAPTURED) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
    resources = manifest if isinstance(manifest, list) else manifest["resources"]
    for resource in resources:
        name = resource["file"]
        shutil.copy2(capture / name, destination / name)


def _malform_child(path: Path) -> None:
    """Keep a parseable spell, but invalidate the recognized haste probability."""
    spell = read_spl(path)
    first, *rest = spell.abilities
    first = dataclasses.replace(
        first,
        effects=tuple(
            dataclasses.replace(effect, probability1=50)
            if effect.opcode == 16 else effect
            for effect in first.effects
        ),
    )
    write_spl(path, dataclasses.replace(spell, abilities=(first, *rest)))


def _malform_divine_cleanup(path: Path, fault: str) -> None:
    spell = read_spl(path)
    first, *rest = spell.abilities
    effects = list(first.effects)
    if fault == "duplicate":
        effects.insert(1, effects[0])
    elif fault == "misordered":
        effects[0], effects[1] = effects[1], effects[0]
    elif fault == "mixed_pristine":
        effects.pop(0)
    elif fault == "partial_private":
        effects.insert(1, _helper_effect(321, parameter2=2, resource="CBRST18"))
    elif fault == "duplicate_self":
        effects.append(effects[1])
    elif fault == "self_probability":
        effects[1] = dataclasses.replace(effects[1], probability1=50)
    else:
        bad_fields = {
            "parameter2": {"parameter2": 2},
            "target": {"target": 2},
            "probability": {"probability1": 50},
            "duration": {"duration": 1},
        }
        effects[0] = dataclasses.replace(effects[0], **bad_fields[fault])
    first = dataclasses.replace(first, effects=tuple(effects))
    write_spl(path, dataclasses.replace(spell, abilities=(first, *rest)))


def _run_captured_harness(capture: Path = CAPTURED) -> HarnessResult:
    temporary = tempfile.TemporaryDirectory(prefix="cbr-no-sr-captured-")
    base = Path(temporary.name)
    fixture_root = base / "fixture"
    _copy_captured(fixture_root, capture)
    run_dir = base / "run"
    run_dir.mkdir()
    output = base / "output"
    output.mkdir()
    process = subprocess.run(
        [
            str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", "1",
            "--args", str(PRODUCTION_TPA), "--args", str(fixture_root),
            "--args", str(output), "--args", "auto",
            "--args", "SPPR412", "--args", "SPWI613",
            "--no-exit-pause", "--quick-log",
        ],
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    return HarnessResult(
        temporary=temporary,
        fixture=Fixture(fixture_root, "SPPR412", "SPWI613"),
        output=output,
        run_dir=run_dir,
        mode="auto",
        variant="captured-no-sr-delegation",
        process=process,
    )


class CapturedGame(SyntheticGame):
    """The public tp2 in a tiny synthetic KEY/BIFF/TLK environment."""

    def __init__(
        self,
        temporary: tempfile.TemporaryDirectory[str],
        *,
        child_in_key: bool = False,
        child_in_override: bool = True,
        malformed_key: bool = False,
        malformed_override: bool = False,
        divine_fault: str | None = None,
        capture: Path = CAPTURED,
    ):
        self.temporary = temporary
        self.capture = capture
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        _copy_captured(self.override, capture)
        # WeiDU evaluates sibling components' predicates even when only 401
        # is requested. Synthetic identifiers avoid unrelated missing-IDS
        # errors; they are not claimed to be captured game data.
        (self.override / "STATS.IDS").write_text(
            "IDS V1.0\n500 C0_PROFICIENCYLONGSWORD\n", encoding="ascii"
        )
        (self.override / "KIT.IDS").write_text(
            "IDS V1.0\n0x4020 OHTEMPUS\n", encoding="ascii"
        )
        self.fixture_root = Path(temporary.name) / "fixture"
        _copy_captured(self.fixture_root, capture)
        self.fixture = Fixture(self.fixture_root, "SPPR412", "SPWI613")
        if divine_fault is not None:
            _malform_divine_cleanup(self.override / "SPPR412.SPL", divine_fault)

        shutil.copy2(SETUP_TP2, self.root / SETUP_TP2.name)
        shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")

        resources = [("OH6000", "ARE", b"synthetic BG2EE marker")]
        if child_in_key:
            child_source = self.fixture_root / CHILD_NAME
            if malformed_key:
                _malform_child(child_source)
            resources.append(("SPWI613A", "SPL", child_source.read_bytes()))
        if not child_in_override and (self.override / CHILD_NAME).exists():
            (self.override / CHILD_NAME).unlink()
        elif malformed_override:
            _malform_child(self.override / CHILD_NAME)
        self.bif_path = _write_key_and_bif(self.root, tuple(resources))

        self.lang_tlk = self.root / "lang/en_us/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.pre_override = _raw_file_tree(self.override)
        self.stable_hashes = {
            "key": _sha256(self.root / "chitin.key"),
            "bif": _sha256(self.bif_path),
            "lang_tlk": _sha256(self.lang_tlk),
            "root_tlk": _sha256(self.root_tlk),
        }


class TempusCapturedDelegatedHasteTests(unittest.TestCase):
    def _make_game(self, **kwargs) -> CapturedGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-no-sr-installer-")
        self.addCleanup(temporary.cleanup)
        return CapturedGame(temporary, **kwargs)

    def _assert_doubling_publication(self, game: CapturedGame) -> None:
        actual = _casefold_tree(_raw_file_tree(game.override))
        before = _casefold_tree(game.pre_override)
        self.assertEqual(set(before) | STRENGTH_PUBLICATIONS, set(actual))
        for name in ("SPWI613.SPL", "SPLSTATE.IDS", "SPELL.IDS"):
            self.assertEqual(before[name], actual[name], name)
        if "DW_NEG40.SPL" in before:
            self.assertEqual(before["DW_NEG40.SPL"], actual["DW_NEG40.SPL"])
        if CHILD_NAME in before:
            self.assertEqual(before[CHILD_NAME], actual[CHILD_NAME])
        else:
            self.assertNotIn(CHILD_NAME, actual, "read-only KEY child was materialized")
        for resref in (*APR_HELPER_RESREFS, *APR_CONDITION_RESREFS):
            self.assertNotIn(f"{resref}.SPL", actual)
            self.assertNotIn(f"{resref}.EFF", actual)
        self.assertEqual(30, len(read_spl(game.override / "OHTMPS1.SPL").abilities))
        self._assert_divine_cleanup_normalized(game.override / "SPPR412.SPL", game.capture)
        self.assertFalse(game.scratch.exists())
        game.assert_stable_inputs(self)

    def _assert_divine_cleanup_normalized(self, output: Path, capture: Path = CAPTURED) -> None:
        original = read_spl(capture / "SPPR412.SPL")
        transformed = read_spl(output)
        self.assertEqual(len(original.abilities), len(transformed.abilities))
        self.assertEqual(original.header_raw[:0x64], transformed.header_raw[:0x64])
        expected_cleanup = tuple(
            _helper_effect(321, parameter2=2, resource=resource).to_bytes()
            for resource in ("OHTMPS1", "CBRST18", "CBRST19", "CBRST20", "CBRST21")
        )
        for before, after in zip(original.abilities, transformed.abilities):
            self.assertEqual(before.raw[:0x1E], after.raw[:0x1E])
            self.assertEqual(before.raw[0x22:], after.raw[0x22:])
            self.assertEqual(expected_cleanup, tuple(effect.to_bytes() for effect in after.effects[:5]))
            self.assertEqual(
                tuple(effect.to_bytes() for effect in before.effects[1:]),
                tuple(effect.to_bytes() for effect in after.effects[5:]),
                "legacy self-cleanup or unrelated Divine Power effects changed",
            )

    def _assert_installs(self, game: CapturedGame) -> None:
        process = game.run_install(401)
        transcript = game.transcript(process)
        self.assertEqual(0, process.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        self._assert_doubling_publication(game)

    def test_captured_resource_hashes_and_actual_delegation_shape(self) -> None:
        for resource in MANIFEST["resources"]:
            with self.subTest(resource=resource["file"]):
                path = CAPTURED / resource["file"]
                self.assertEqual(resource["size"], path.stat().st_size)
                self.assertEqual(resource["sha256"], _sha256(path))
        wrapper = read_spl(CAPTURED / "SPWI613.SPL")
        child = read_spl(CAPTURED / CHILD_NAME)
        self.assertEqual((1, *range(13, 21)), tuple(a.required_level for a in wrapper.abilities))
        self.assertEqual(9, len(child.abilities))
        self.assertFalse(wrapper.casting_effects)
        self.assertFalse(child.casting_effects)
        for index, (parent_ability, child_ability) in enumerate(zip(wrapper.abilities, child.abilities)):
            casts = [effect for effect in parent_ability.effects if effect.opcode == 146]
            haste = [effect for effect in child_ability.effects if effect.opcode in (1, 16, 317)]
            self.assertEqual(1, len(casts))
            self.assertEqual(("SPWI613A", 0, 1, 1, 0, 100, 0), (
                casts[0].resource, casts[0].parameter1, casts[0].parameter2,
                casts[0].timing, casts[0].duration, casts[0].probability1, casts[0].probability2,
            ))
            self.assertEqual(1, len(haste))
            self.assertEqual((16, 1, 0, 90 + index * 6, 100, 0), (
                haste[0].opcode, haste[0].parameter2, haste[0].timing,
                haste[0].duration, haste[0].probability1, haste[0].probability2,
            ))

    def test_captured_full_transform_is_byte_exactly_idempotent(self) -> None:
        first = _run_captured_harness()
        self.addCleanup(first.temporary.cleanup)
        self.assertTrue(first.succeeded, first.transcript)
        second = _rerun_harness(first)
        self.addCleanup(second.temporary.cleanup)
        self.assertTrue(second.succeeded, second.transcript)
        self.assertEqual(_raw_file_tree(first.output), _raw_file_tree(second.output))
        for name in ("SPWI613.SPL", CHILD_NAME, "DW_NEG40.SPL", "SPLSTATE.IDS"):
            self.assertEqual((CAPTURED / name).read_bytes(), (first.output / name).read_bytes(), name)
        self._assert_divine_cleanup_normalized(first.output / "SPPR412.SPL")

    def test_actual_base_game_without_scs_or_sr_installs_and_is_idempotent(self) -> None:
        manifest = json.loads((BASE_GAME / "manifest.json").read_text(encoding="utf-8"))
        resources = manifest if isinstance(manifest, list) else manifest["resources"]
        for resource in resources:
            self.assertEqual(resource["sha256"], _sha256(BASE_GAME / resource["file"]))
        haste = read_spl(BASE_GAME / "SPWI613.SPL")
        self.assertTrue(all(
            any(effect.opcode == 16 and effect.parameter2 == 1 for effect in ability.effects)
            and not any(effect.opcode == 146 for effect in ability.effects)
            for ability in haste.abilities
        ))
        game = self._make_game(capture=BASE_GAME)
        self._assert_installs(game)
        first = _run_captured_harness(BASE_GAME)
        self.addCleanup(first.temporary.cleanup)
        self.assertTrue(first.succeeded, first.transcript)
        second = _rerun_harness(first)
        self.addCleanup(second.temporary.cleanup)
        self.assertTrue(second.succeeded, second.transcript)
        self.assertEqual(_raw_file_tree(first.output), _raw_file_tree(second.output))
        self._assert_divine_cleanup_normalized(first.output / "SPPR412.SPL", BASE_GAME)
        self.assertEqual(
            (BASE_GAME / "SPWI613.SPL").read_bytes(),
            (first.output / "SPWI613.SPL").read_bytes(),
        )

    def test_component_401_installs_captured_no_sr_override_resources(self) -> None:
        self._assert_installs(self._make_game())

    def test_synthetic_uninstall_restores_captured_resources_byte_exactly(self) -> None:
        game = self._make_game(child_in_key=True, child_in_override=False)
        self._assert_installs(game)
        process = game.run_uninstall(401)
        self.assertEqual(0, process.returncode, game.transcript(process))
        self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))
        self.assertFalse(game.scratch.exists())
        game.assert_stable_inputs(self)

    def test_component_401_reads_key_only_child_without_publishing_it(self) -> None:
        self._assert_installs(self._make_game(child_in_key=True, child_in_override=False))

    def test_valid_override_child_takes_precedence_over_malformed_key_child(self) -> None:
        self._assert_installs(self._make_game(child_in_key=True, malformed_key=True))

    def test_malformed_override_child_cannot_fall_back_to_valid_key_child(self) -> None:
        game = self._make_game(child_in_key=True, malformed_override=True)
        process = game.run_install(401)
        transcript = game.transcript(process)
        self.assertNotEqual(0, process.returncode, transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        self.assertRegex(transcript, r"(?i)SPWI613A.*(?:unsafe|probability|semantics)")
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))
        game.assert_stable_inputs(self)

    def test_malformed_legacy_divine_cleanup_fails_atomically(self) -> None:
        for fault in (
            "parameter2", "target", "probability", "duration", "duplicate",
            "misordered", "mixed_pristine", "partial_private", "duplicate_self",
            "self_probability",
        ):
            with self.subTest(fault=fault):
                game = self._make_game(divine_fault=fault)
                process = game.run_install(401)
                transcript = game.transcript(process)
                self.assertNotEqual(0, process.returncode, transcript)
                self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
                self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
                self.assertRegex(transcript, r"(?i)Divine Power SPPR412.*(?:cleanup|headers)")
                self.assertEqual(game.pre_override, _raw_file_tree(game.override))
                game.assert_stable_inputs(self)


if __name__ == "__main__":
    unittest.main()
