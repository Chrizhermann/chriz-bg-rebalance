"""Actor-scoped wing-buffet checks using real WeiDU and captured compiled BCS.

No live-game inputs, BAF source files, or game launches. The original blocks are
the oracle: every old byte must survive behind the new, exact Name-gated copies.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_scs_weapon_semantics import _write_minimal_script_ids
from tests.test_tempus_holy_power_installer import (
    ONE_EMPTY_STRING_TLK, RESOURCE_TYPE, _write_key_and_bif,
)

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
LIB = ROOT / "chriz-bg-rebalance/lib/dragon_wing_buffet.tpa"
HARNESS = ROOT / "tests/weidu/dragon_wing_buffet_harness.tp2"
FIXTURES = ROOT / "tests/fixtures/dragon_wing_buffet"
ORIGINALS = ROOT / "research/originals/dragon_wing_buffet"
ROSTER = {
    "firkra02": ("dragred", "firkra02", 0x250),
    "shadra01": ("shadra01", "ShaDra01", 0x248),
    "dragblac": ("dragblac", "Dragblac", 0x250),
    "gorsal": ("gorsal", "GorSal", 0x268),
    "fsdragon": ("draggree", "FSdragon", 0x250),
}
SPELLS = {
    "WIZARD_CLOUDKILL": 2502,
    "WIZARD_STINKING_CLOUD": 2213,
    "WIZARD_DEATH_FOG": 2614,
    "WIZARD_INCENDIARY_CLOUD": 2810,
    "DRAGON_WING_BUFFET": 3695,
}

# Captured game resources are deliberately local-only, not redistributable assets.
# With the capture installed, incomplete/changed evidence still fails the tests.
CAPTURE_AVAILABLE = (ORIGINALS / "manifest.json").is_file() and FIXTURES.is_dir()
CAPTURE_REQUIRED = "private dragon capture unavailable; see tests/DRAGON-FIXTURES.md"


def write_ids(root: Path, shift: int = 0) -> None:
    _write_minimal_script_ids(root, "IDS V1.0\n" + "".join(
        f"{number + shift} {symbol}\n" for symbol, number in SPELLS.items()
    ))
    with (root / "TRIGGER.IDS").open("a", encoding="ascii") as f:
        f.write("0x0091 SpellCast(O:Object*,I:Spell*Spell)\n")
        f.write("0x40A5 Name(S:Name*,O:Object*)\n")
    with (root / "ACTION.IDS").open("a", encoding="ascii") as f:
        f.write("160 ApplySpellRES(S:RES*,O:Target)\n")
    with (root / "OBJECT.IDS").open("a", encoding="ascii") as f:
        f.write("29 SecondNearestEnemyOf\n")
    with (root / "EA.IDS").open("a", encoding="ascii") as f:
        f.write("30 GOODCUTOFF\n")


def blocks(data: bytes) -> list[bytes]:
    result = []
    cursor = 3
    assert data.startswith(b"SC\n") and data.endswith(b"SC\n")
    while cursor < len(data) - 3:
        end = data.index(b"RS\nCR\n", cursor) + 6
        result.append(data[cursor:end])
        cursor = end
    return result


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.name.lower(): p.read_bytes() for p in root.iterdir() if p.is_file()}


def simulate_buffet_paths(data: bytes, actor: str, *, cloud: bool, response: int) -> tuple[int, int, int]:
    """Small independent branch model: Name, shared timer, response and Continue.

    Other guards are assumed true. This proves the inserted copies cannot allow
    a second immediate buffet through the original fall-through path; it does
    not claim to simulate combat, visibility, or live engine timing.
    """
    cooldown = castspell = casts = 0
    for block in blocks(data):
        guard = re.search(rb'16549 0 0 0 0 "([^"]+)"', block)
        if guard and guard.group(1).decode().lower() != actor.lower():
            continue
        is_cloud = b"145 " in block
        if is_cloud != cloud or cooldown > 0:
            continue
        choices = re.findall(rb'RE\n(.*?)RE\n', block, re.S)
        chosen = choices[0 if cloud else response]
        cooldown = int(re.search(rb'(\d+) 0 0 0 0"LOCALSBuffet"', chosen).group(1))
        cast = re.search(rb'(\d+) 0 0 0 0"LOCALScastspell"', chosen)
        if cast:
            castspell = int(cast.group(1))
        casts += chosen.count(b"181OB\n")
        if b"36OB\n" not in chosen:  # Continue is the only fall-through response
            break
    return cooldown, castspell, casts


@unittest.skipUnless(WEIDU.exists(), "WeiDU executable not available")
@unittest.skipUnless(CAPTURE_AVAILABLE, CAPTURE_REQUIRED)
class DragonWingBuffetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cbr-wing-buffet-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        for path in FIXTURES.iterdir():
            if path.suffix.lower() in (".cre", ".bcs"):
                shutil.copy2(path, self.fixture / path.name)
        write_ids(self.fixture)
        self.run_number = 0

    def run_library(self, *, success: bool = True) -> subprocess.CompletedProcess[str]:
        self.run_number += 1
        run = self.root / f"run-{self.run_number}"
        run.mkdir()
        result = subprocess.run([
            str(WEIDU), str(HARNESS), "--nogame", "--search-ids", str(self.fixture),
            "--force-install-list", "1", "--args", str(LIB),
            "--args", str(self.fixture), "--no-exit-pause", "--quick-log",
        ], cwd=run, capture_output=True, text=True, timeout=120, check=False)
        transcript = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        else:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
        return result

    def assert_actor_scoped(self, before: bytes, after: bytes, dv: str) -> None:
        old = blocks(before)
        new = blocks(after)
        self.assertEqual(len(new), len(old) + 2)
        original_pair = blocks((FIXTURES / "dragred.bcs").read_bytes())
        index = next(i for i, block in enumerate(old) if b"LOCALSBuffet" in block)
        self.assertEqual(new[:index], old[:index])
        self.assertEqual(new[index + 2:], old[index:])
        for original, gated in zip(original_pair, new[index:index + 2]):
            # Exact bytes of the original behavior, apart from an explicit actor
            # guard and timer assignments. No whole-script recompilation churn.
            guard = re.search(
                rb'TR\n16549 0 0 0 0 "([^"]+)" "" OB\n'
                rb'0 0 0 0 0 0 0 1 0 0 0 0 ""OB\nTR\n', gated,
            )
            self.assertIsNotNone(guard)
            self.assertEqual(guard.group(1).decode().lower(), dv.lower())
            self.assertEqual(gated.count(b"16549 "), 1)
            self.assertEqual(gated.replace(guard.group(0), b"").replace(
                b'18 0 0 0 0"LOCALSBuffet"', b'6 0 0 0 0"LOCALSBuffet"'
            ), original)
        self.assertEqual(sum(b.count(b'18 0 0 0 0"LOCALSBuffet"')
                             for b in new[index:index + 2]), 3)

    def test_captured_evidence_hashes(self) -> None:
        for entry in json.loads((ORIGINALS / "manifest.json").read_text()):
            self.assertEqual(hashlib.sha256((ORIGINALS / entry["original"]).read_bytes())
                             .hexdigest(), entry["sha256"])
            if "fixture_sha256" in entry:
                name = entry["original"].removesuffix(".orig")
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(),
                                 entry["fixture_sha256"])

    def test_five_roster_scripts_and_every_other_resource_are_preserved(self) -> None:
        (self.fixture / "dragsilv.bcs").write_bytes((FIXTURES / "dragred.bcs").read_bytes())
        before = snapshot(self.fixture)
        self.run_library()
        after = snapshot(self.fixture)
        allowed = {script + ".bcs" for script, _, _ in ROSTER.values()}
        self.assertEqual(before.keys(), after.keys())
        for name in before.keys() - allowed:
            self.assertEqual(before[name], after[name], name)
        for script, dv, _ in ROSTER.values():
            self.assert_actor_scoped(before[script + ".bcs"], after[script + ".bcs"], dv)

    def test_second_run_is_byte_identical(self) -> None:
        self.run_library()
        once = snapshot(self.fixture)
        self.run_library()
        self.assertEqual(snapshot(self.fixture), once)

    def test_selected_actors_and_unrelated_script_users_keep_correct_paths(self) -> None:
        self.run_library()
        for script, dv, _ in ROSTER.values():
            data = (self.fixture / (script + ".bcs")).read_bytes()
            for actor, cooldown in ((dv, 18), ("unselected_actor", 6)):
                with self.subTest(script=script, actor=actor):
                    self.assertEqual(simulate_buffet_paths(data, actor, cloud=True, response=0),
                                     (cooldown, 3, 1))
                    self.assertEqual(simulate_buffet_paths(data, actor, cloud=False, response=0),
                                     (cooldown, 3, 1))
                    self.assertEqual(simulate_buffet_paths(data, actor, cloud=False, response=1),
                                     (cooldown, 0, 0))

    def test_complete_captured_scripts_preserve_all_non_buffet_blocks(self) -> None:
        for script, _, _ in ROSTER.values():
            shutil.copy2(ORIGINALS / (script + ".bcs.orig"), self.fixture / (script + ".bcs"))
        before = snapshot(self.fixture)
        self.run_library()
        for script, dv, _ in ROSTER.values():
            self.assert_actor_scoped(before[script + ".bcs"],
                                     (self.fixture / (script + ".bcs")).read_bytes(), dv)

    def test_dynamic_spell_ids_are_used(self) -> None:
        write_ids(self.fixture, 100)
        for script, _, _ in ROSTER.values():
            path = self.fixture / (script + ".bcs")
            data = path.read_bytes()
            for number in SPELLS.values():
                data = data.replace(str(number).encode(), str(number + 100).encode())
            path.write_bytes(data)
        self.run_library()
        data = (self.fixture / "dragred.bcs").read_bytes()
        self.assertEqual(data.count(b'3795 0 0 0 0""'), 4)
        self.assertNotIn(b'3695 0 0 0 0""', data)

    def test_foreign_and_partial_shapes_fail_before_any_publication(self) -> None:
        path = self.fixture / "draggree.bcs"  # last target catches partial-install mistakes
        original = path.read_bytes()
        variants = {
            "timer": original.replace(b'6 0 0 0 0"LOCALSBuffet"', b'12 0 0 0 0"LOCALSBuffet"', 1),
            "partial": original.replace(b'6 0 0 0 0"LOCALSBuffet"', b'18 0 0 0 0"LOCALSBuffet"', 1),
            "range": original.replace(b"16408 12 ", b"16408 13 "),
            "weight": original.replace(b"100AC", b"99AC", 1),
            "missing": b"SC\nSC\n",
            "duplicate": b"SC\n" + original[3:-3] * 2 + b"SC\n",
        }
        for label, data in variants.items():
            with self.subTest(label=label):
                path.write_bytes(data)
                before = snapshot(self.fixture)
                result = self.run_library(success=False)
                self.assertIn("wing-buffet", result.stdout + result.stderr)
                self.assertEqual(snapshot(self.fixture), before)

    def test_foreign_cre_identity_and_script_assignment_fail_closed(self) -> None:
        path = self.fixture / "fsdragon.cre"
        original = path.read_bytes()
        for offset, replacement in ((0x280, b"OtherDra"), (0x250, b"dragred\0")):
            with self.subTest(offset=offset):
                data = bytearray(original)
                data[offset:offset + 8] = replacement
                path.write_bytes(data)
                before = snapshot(self.fixture)
                self.run_library(success=False)
                self.assertEqual(snapshot(self.fixture), before)

    def test_missing_last_target_fails_before_first_script_changes(self) -> None:
        (self.fixture / "fsdragon.cre").unlink()
        before = snapshot(self.fixture)
        self.run_library(success=False)
        self.assertEqual(snapshot(self.fixture), before)

    def build_game(self, *, foreign_last: bool = False) -> tuple[Path, dict[str, bytes]]:
        game = self.root / "game"
        game.mkdir()
        override = game / "override"
        override.mkdir()
        write_ids(override)
        resources = [("OH6000", "ARE", b"synthetic BG2EE marker")]
        for actor, (script, _, _) in ROSTER.items():
            resources.append((actor, "CRE", (FIXTURES / (actor + ".cre")).read_bytes()))
            data = (FIXTURES / (script + ".bcs")).read_bytes()
            if foreign_last and actor == "fsdragon":
                data = data.replace(b'6 0 0 0 0"LOCALSBuffet"', b'7 0 0 0 0"LOCALSBuffet"', 1)
            resources.append((script, "BCS", data))
        with patch.dict(RESOURCE_TYPE, {"CRE": 1009, "BCS": 1007}):
            _write_key_and_bif(game, tuple(resources))
        for path in (game / "dialog.tlk", game / "lang/en_us/dialog.tlk"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ONE_EMPTY_STRING_TLK)
        stable = {str(path.relative_to(game)): path.read_bytes() for path in game.rglob("*")
                  if path.is_file() and "override" not in path.parts}
        return game, stable

    def run_game(self, game: Path, *operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            str(WEIDU), str(HARNESS), "--game", str(game), *operation,
            "--args", str(LIB), "--args", "unused", "--use-lang", "en_US",
            "--no-exit-pause", "--quick-log",
        ], cwd=game, capture_output=True, text=True, timeout=120, check=False)

    def test_game_path_materializes_only_changed_bcs_and_uninstall_restores(self) -> None:
        game, stable = self.build_game()
        before = snapshot(game / "override")
        result = self.run_game(game, "--force-install-list", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SUCCESSFULLY INSTALLED", result.stdout)
        after = snapshot(game / "override")
        self.assertEqual(after.keys() - before.keys(),
                         {script + ".bcs" for script, _, _ in ROSTER.values()})
        for name, data in before.items():
            self.assertEqual(after[name], data)
        for script, dv, _ in ROSTER.values():
            self.assert_actor_scoped((FIXTURES / (script + ".bcs")).read_bytes(),
                                     after[script + ".bcs"], dv)
        for name, data in stable.items():
            self.assertEqual((game / name).read_bytes(), data)
        result = self.run_game(game, "--force-uninstall-list", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(game / "override"), before)
        for name, data in stable.items():
            self.assertEqual((game / name).read_bytes(), data)

    def test_game_path_rejects_last_foreign_target_without_materialization(self) -> None:
        game, stable = self.build_game(foreign_last=True)
        before = snapshot(game / "override")
        result = self.run_game(game, "--force-install-list", "2")
        self.assertIn("NOT INSTALLED DUE TO ERRORS", result.stdout + result.stderr)
        self.assertEqual(snapshot(game / "override"), before)
        for name, data in stable.items():
            self.assertEqual((game / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
