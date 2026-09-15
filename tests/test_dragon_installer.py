"""Public 110/111 installation on a disposable BG2EE KEY/BIFF/TLK game."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_dragon_wing_buffet import (
    CAPTURE_AVAILABLE, CAPTURE_REQUIRED, ORIGINALS, ROOT, ROSTER, WEIDU,
    blocks, snapshot, write_ids,
)
from tests.test_tempus_holy_power_installer import ONE_EMPTY_STRING_TLK, RESOURCE_TYPE, _write_key_and_bif

SETUP = ROOT / "setup-chriz-bg-rebalance.tp2"
SCRIPTS = {script + ".bcs" for script, _, _ in ROSTER.values()}
PAYLOADS = {"cbrdv05.spl", "cbrdv10.spl", "cbrdv15.spl", "cbrdvrem.spl",
            "cbrdve05.eff", "cbrdve10.eff", "cbrdve15.eff", "m_cbrdvg.lua"}


class DragonGame:
    def __init__(self, root: Path, *, scs: bool = True, eeex: bool = True) -> None:
        self.root = root
        self.root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        write_ids(self.override)
        (self.override / "KIT.IDS").write_text("IDS V1.0\n0 NONE\n", encoding="ascii")
        if eeex:
            (self.override / "M___EEex.lua").write_text("-- synthetic EEex footprint\n", encoding="ascii")
        shutil.copy2(SETUP, root / SETUP.name)
        shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
        resources = [("OH6000", "ARE", b"synthetic BG2EE marker")]
        for cre, (script, _, _) in ROSTER.items():
            resources.append((cre, "CRE", (ORIGINALS / f"{cre}.cre.orig").read_bytes()))
            resources.append((script, "BCS", (ORIGINALS / f"{script}.bcs.orig").read_bytes()))
        with patch.dict(RESOURCE_TYPE, {"CRE": 1009, "BCS": 1007}):
            _write_key_and_bif(root, tuple(resources))
        for path in (root / "dialog.tlk", root / "lang/en_us/dialog.tlk"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ONE_EMPTY_STRING_TLK)
        self.stable = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
                       if p.is_file() and p.suffix.lower() in (".key", ".bif", ".tlk")}
        if scs:
            # Let WeiDU create its own log; no manual log edits or real mod data.
            marker = root / "stratagems/setup-stratagems.tp2"
            marker.parent.mkdir()
            marker.write_text('BACKUP ~fixture-backup~\nAUTHOR ~fixture~\n'
                              'BEGIN ~Synthetic Smarter Dragons prerequisite~ DESIGNATED 6540\n',
                              encoding="ascii")
            result = self.run("--force-install-list", "6540", tp2="stratagems/setup-stratagems.tp2")
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
        self.before = snapshot(self.override)

    def run(self, *operation: str, tp2: str = SETUP.name) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            str(WEIDU), tp2, "--game", str(self.root), *operation, "--language", "0",
            "--use-lang", "en_US", "--no-exit-pause", "--quick-log",
        ], cwd=self.root, capture_output=True, text=True, timeout=90, check=False)


@unittest.skipUnless(WEIDU.exists(), "WeiDU executable not available")
@unittest.skipUnless(CAPTURE_AVAILABLE, CAPTURE_REQUIRED)
class DragonInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cbr-dragon-installer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def game(self, **kwargs: object) -> DragonGame:
        return DragonGame(self.root / "game", **kwargs)

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"SUCCESSFULLY (INSTALLED|REMOVED)")

    def assert_stable(self, game: DragonGame) -> None:
        for name, data in game.stable.items():
            self.assertEqual((game.root / name).read_bytes(), data, name)

    def test_vorpal_public_install_warning_scope_and_biff_only_inputs(self) -> None:
        game = self.game()
        result = game.run("--force-install-list", "110")
        self.assert_success(result)
        for disclosure in ("permanent death", "cannot be raised", "15%", "10%", "5%",
                           "Death Ward", "gore", "EEex"):
            self.assertIn(disclosure, result.stdout)
        after = snapshot(game.override)
        self.assertEqual(after.keys() - game.before.keys(), SCRIPTS | PAYLOADS)
        for name, original in game.before.items():
            self.assertEqual(after[name], original, name)
        expected = {"dragred": b"CBRDV15", "shadra01": b"CBRDV05",
                    "dragblac": b"CBRDV10", "gorsal": b"CBRDV10", "draggree": b"CBRDV05"}
        for script, package in expected.items():
            current = blocks(after[script + ".bcs"])
            old = blocks((ORIGINALS / f"{script}.bcs.orig").read_bytes())
            self.assertEqual(current[4:], old)
            self.assertEqual(b"".join(current[:4]).count(package), 2)
        self.assert_stable(game)
        self.assert_success(game.run("--force-uninstall-list", "110"))
        self.assertEqual(snapshot(game.override), game.before)
        self.assert_stable(game)

    def test_wing_buffet_public_component_is_independent_of_eeex(self) -> None:
        game = self.game(eeex=False)
        self.assert_success(game.run("--force-install-list", "111"))
        after = snapshot(game.override)
        self.assertEqual(after.keys() - game.before.keys(), SCRIPTS)
        for script in SCRIPTS:
            self.assertEqual(after[script].count(b'18 0 0 0 0"LOCALSBuffet"'), 3)
        self.assert_stable(game)
        self.assert_success(game.run("--force-uninstall-list", "111"))
        self.assertEqual(snapshot(game.override), game.before)

    def test_combined_install_and_restore(self) -> None:
        game = self.game()
        self.assert_success(game.run("--force-install-list", "110", "111"))
        after = snapshot(game.override)
        for script in SCRIPTS:
            self.assertEqual(after[script].count(b'18 0 0 0 0"LOCALSBuffet"'), 3)
            self.assertEqual(len(blocks(after[script])),
                             len(blocks((ORIGINALS / f"{script}.orig").read_bytes())) + 6)
        self.assert_success(game.run("--force-uninstall-list", "111"))
        self.assertEqual(snapshot(game.override).keys() - game.before.keys(), SCRIPTS | PAYLOADS)
        self.assert_success(game.run("--force-uninstall-list", "110"))
        self.assertEqual(snapshot(game.override), game.before)
        self.assert_stable(game)

    def test_reverse_install_order_produces_same_bytes_and_preserves_111_on_removal(self) -> None:
        forward = DragonGame(self.root / "forward")
        self.assert_success(forward.run("--force-install-list", "110", "111"))
        combined = snapshot(forward.override)

        reverse = DragonGame(self.root / "reverse")
        self.assert_success(reverse.run("--force-install-list", "111"))
        wing_only = snapshot(reverse.override)
        self.assert_success(reverse.run("--force-install-list", "110"))
        self.assertEqual(snapshot(reverse.override), combined)
        self.assert_stable(forward)
        self.assert_stable(reverse)

        # Removing the last installed component must restore the other one's
        # exact blocks, not merely preserve the same file publication set.
        self.assert_success(reverse.run("--force-uninstall-list", "110"))
        self.assertEqual(snapshot(reverse.override), wing_only)
        self.assert_success(reverse.run("--force-uninstall-list", "111"))
        self.assertEqual(snapshot(reverse.override), reverse.before)
        self.assert_stable(reverse)

    def test_formal_install_over_complete_preapplied_hotfix_is_byte_idempotent(self) -> None:
        donor = DragonGame(self.root / "donor")
        self.assert_success(donor.run("--force-install-list", "110", "111"))
        installed = snapshot(donor.override)

        game = DragonGame(self.root / "preapplied")
        # Model a direct override hotfix in this synthetic game. Its WeiDU log
        # contains only the prerequisite, so the formal run executes both
        # components rather than silently skipping already-installed entries.
        for name in SCRIPTS | PAYLOADS:
            (game.override / name).write_bytes(installed[name])
        preapplied = snapshot(game.override)
        for _ in range(2):
            self.assert_success(game.run("--force-install-list", "110", "111"))
            self.assertEqual(snapshot(game.override), preapplied)
            self.assert_stable(game)
            self.assert_success(game.run("--force-uninstall-list", "111"))
            self.assert_success(game.run("--force-uninstall-list", "110"))
            self.assertEqual(snapshot(game.override), preapplied)
            self.assert_stable(game)

    def test_missing_eeex_skips_vorpal_without_writes(self) -> None:
        game = self.game(eeex=False)
        result = game.run("--force-install-list", "110")
        self.assertIn("SKIPPING", result.stdout)
        self.assertNotIn("SUCCESSFULLY INSTALLED", result.stdout)
        self.assertEqual(snapshot(game.override), game.before)
        self.assert_stable(game)

    def test_missing_scs_skips_both_components_without_writes(self) -> None:
        game = self.game(scs=False)
        result = game.run("--force-install-list", "110", "111")
        self.assertIn("SKIPPING", result.stdout)
        self.assertNotIn("SUCCESSFULLY INSTALLED", result.stdout)
        self.assertEqual(snapshot(game.override), game.before)

    def test_foreign_last_cre_rolls_back_before_any_payload(self) -> None:
        game = self.game()
        data = bytearray((ORIGINALS / "shadra01.cre.orig").read_bytes())
        data[0x280:0x288] = b"FOREIGN1"
        (game.override / "shadra01.cre").write_bytes(data)
        before = snapshot(game.override)
        result = game.run("--force-install-list", "110")
        self.assertIn("NOT INSTALLED DUE TO ERRORS", result.stdout + result.stderr)
        self.assertEqual(snapshot(game.override), before)
        self.assert_stable(game)

    def test_reserved_resource_collision_preserves_everything(self) -> None:
        game = self.game()
        (game.override / "CBRDV15.SPL").write_bytes(b"unrelated reserved-name owner")
        before = snapshot(game.override)
        result = game.run("--force-install-list", "110")
        self.assertIn("NOT INSTALLED DUE TO ERRORS", result.stdout + result.stderr)
        self.assertEqual(snapshot(game.override), before)
        self.assert_stable(game)


if __name__ == "__main__":
    unittest.main()
