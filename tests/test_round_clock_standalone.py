"""Exercise the distributed 361 archive, reciprocal backup ownership and path spellings."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from tests import test_round_clock_installer as main
from tests.test_round_clock_installer import PACKAGE, PAYLOAD, ROOT, TAIL_EXE, TAIL_TP2, TP2, WEIDU, tree
from tools import package_timestop as packager

TAIL = ROOT/"live-patch"/PACKAGE
SOURCE = ROOT/"chriz-bg-rebalance"
VERSION = packager.version_of(ROOT/TP2)
ARCHIVE_NAME = f"{PACKAGE}-{VERSION}-windows.zip"
MEMBERS = {
    "LICENSE": ROOT/"LICENSE", "WEIDU-LICENSE.txt": ROOT/"WEIDU-LICENSE.txt", TAIL_EXE: WEIDU,
    TAIL_TP2: TAIL/"setup-cbr_round_clock.tp2", f"{PACKAGE}/README.md": TAIL/"README.md",
    f"{PACKAGE}/languages/english/setup.tra": SOURCE/"languages/english/setup.tra",
    f"{PACKAGE}/lib/round_clock.tpa": SOURCE/"lib/round_clock.tpa",
    f"{PACKAGE}/lua/CBRRC.lua": SOURCE/"lua/CBRRC.lua",
    f"{PACKAGE}/lua/M_CBRRC.lua": SOURCE/"lua/M_CBRRC.lua",
}


def setUpModule():
    holder = tempfile.TemporaryDirectory(prefix="cbr-361-build-")
    unittest.addModuleCleanup(holder.cleanup)
    paths = packager.build(Path(holder.name))
    StandaloneTests.package = next(p for p in paths if p.name == ARCHIVE_NAME)


class StandaloneTests(main.RoundClockInstallerTests):
    def test_archive_bytes_checksum_and_reproducibility(self):
        first = self.package
        with tempfile.TemporaryDirectory(prefix="cbr-361-repeat-") as tmp:
            second = next(p for p in packager.build(Path(tmp)) if p.name == ARCHIVE_NAME)
            self.assertEqual(first.read_bytes(), second.read_bytes())
        digest = hashlib.sha256(first.read_bytes()).hexdigest()
        self.assertEqual(first.with_suffix(".zip.sha256").read_bytes(), f"{digest}  {first.name}\n".encode())
        with zipfile.ZipFile(first) as z:
            self.assertCountEqual(z.namelist(), MEMBERS.keys())
            for name, source in MEMBERS.items():
                self.assertEqual(z.read(name), source.read_bytes(), name)
            self.assertIn(f"VERSION ~{VERSION}~", z.read(TAIL_TP2).decode())

    def test_refuses_version_mismatch_before_creating_any_archive(self):
        with tempfile.TemporaryDirectory(prefix="cbr-361-version-") as tmp:
            root = Path(tmp)
            for name in (TP2, "live-patch/CBR_TRUE_TIMESTOP/setup-cbr_true_timestop.tp2", "live-patch/"+TAIL_TP2):
                dest = root/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT/name, dest)
            setup = root/"live-patch"/TAIL_TP2
            text = setup.read_text().replace(f"VERSION ~{VERSION}~", f"// VERSION ~{VERSION}~\nVERSION ~v9~")
            setup.write_text(text, encoding="utf-8")
            with patch.object(packager, "ROOT", root), self.assertRaisesRegex(ValueError, "versions must agree"):
                packager.build(root/"dist")
            self.assertFalse((root/"dist").exists())

    def test_reciprocal_guard_in_all_four_path_forms(self):
        for first_tail in (False, True):
            for form in ("auto", "slash", "backslash", "absolute"):
                with self.subTest(first_tail=first_tail, form=form):
                    game = self.game()
                    game.install_sources()
                    self.success(game, tail=first_tail, form=form)
                    logged = game.active_log()
                    owner = ("SETUP-CBR_ROUND_CLOCK.TP2" if first_tail else TP2.upper())
                    self.assertIn(owner, logged)
                    before = tree(game.override)
                    result = game.invoke(tail=not first_tail, form=form)
                    output = result.stdout + result.stderr
                    self.assertIn("SKIPPING", output, output)
                    self.assertIn("already installed by the other CBR installer", output)
                    self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                    self.assertEqual((logged,before), (game.active_log(),tree(game.override)))
                    removed = game.invoke(tail=first_tail, form=form, uninstall=True)
                    self.assertEqual(removed.returncode, 0, removed.stdout+removed.stderr)
                    self.assertEqual(tree(game.override), game.before)
                    self.success(game, tail=not first_tail, form=form)
                    self.assertEqual(tree(game.override), game.before | PAYLOAD)

    def test_standalone_and_main_beside_installed_340_and_360(self):
        for tail in (True,False):
            with self.subTest(tail=tail):
                game = self.game()
                game.install_sources()
                self.success(game, tail=False, component=340)
                self.success(game, tail=False, component=360)
                siblings = tree(game.override), game.active_log()
                self.success(game, tail=tail)
                self.assertEqual(tree(game.override), siblings[0] | PAYLOAD)
                result = game.invoke(tail=tail, uninstall=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((tree(game.override),game.active_log()), siblings)

    def test_linux_case_sensitive_package_paths_and_lowercased_game(self):
        # ZIP paths use POSIX case-sensitive equality even on a Windows test host.
        with zipfile.ZipFile(self.package) as z:
            exact = {PurePosixPath(name) for name in z.namelist()}
            self.assertEqual(len(exact), len({str(p).lower() for p in exact}))
            setup = z.read(TAIL_TP2).decode()
            root, = re.findall(r"source_dir = ~([^~]+)~", setup)
            includes = re.findall(r"~(CBR_ROUND_CLOCK/[^~]+\.(?:tpa|tra))~", setup)
            self.assertEqual(len(includes), 2)
            tpa = z.read(next(p for p in includes if p.endswith(".tpa"))).decode()
            sources = re.findall(r"~%source_dir%/([^~]+)~", tpa)
            self.assertCountEqual(sources, ["CBRRC.lua", "M_CBRRC.lua"])
            for relative in includes+[f"{root}/{p}" for p in sources]:
                self.assertIn(PurePosixPath(relative), exact)
        # Exercise WeiDU with the lowercase tree used by Linux mod installers.
        game = self.game(edition="iwdee")
        with tempfile.TemporaryDirectory(prefix="cbr-361-lower-") as tmp:
            lower = Path(tmp)
            for source in game.root.rglob("*"):
                dest = lower/source.relative_to(game.root).as_posix().lower()
                if source.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
            result = subprocess.run([str(lower/TAIL_EXE.lower()), TAIL_TP2.lower(), "--game", str(lower),
                                     "--language", "0", "--use-lang", "en_US", "--force-install-list", "361",
                                     "--no-exit-pause", "--quick-log"], cwd=lower, capture_output=True,
                                    text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("SUCCESSFULLY INSTALLED", result.stdout+result.stderr)
            self.assertEqual(tree(lower/"override"), game.before | PAYLOAD)
