"""The standalone True Time Stop package (live-patch/CBR_TRUE_TIMESTOP) next to BG Rebalance's 360.

Disposable synthetic games only, never an installed playthrough. Every test of
tests/test_time_stop_haste_clocks_installer.py runs once more with the package extracted over the
game folder and started through its own setup executable. The tests below cover the packager, the
path WeiDU logs for the package, the guards between the two installers and uninstalling either.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests import test_time_stop_haste_clocks_installer as main_installer
from tests.test_time_stop_haste_clocks_installer import (PACKAGE_EXE, ROOT, SOURCES, TP2, WEIDU,
                                                         ClocksGame, tree)

PACKAGE = ROOT / "live-patch/CBR_TRUE_TIMESTOP"
PACKAGE_TP2 = "CBR_TRUE_TIMESTOP/setup-cbr_true_timestop.tp2"
GUARD = "REQUIRE_PREDICATE NOT (MOD_IS_INSTALLED ~cbr_true_timestop/setup-cbr_true_timestop.tp2~ 360) @9366"
GUARD_TEXT = "is already installed by the other CBR installer"
VERSION = re.search(r"VERSION ~([^~]+)~", (ROOT / TP2).read_text(encoding="utf-8")).group(1)
ARCHIVE = f"CBR_TRUE_TIMESTOP-{VERSION}-windows.zip"
MEMBERS = {
    "LICENSE": ROOT / "LICENSE",
    "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
    PACKAGE_EXE: WEIDU,
    PACKAGE_TP2: PACKAGE / "setup-cbr_true_timestop.tp2",
    "CBR_TRUE_TIMESTOP/README.md": PACKAGE / "README.md",
    "CBR_TRUE_TIMESTOP/languages/english/setup.tra": ROOT / "chriz-bg-rebalance/languages/english/setup.tra",
    "CBR_TRUE_TIMESTOP/lib/time_stop_haste_clocks.tpa": ROOT / "chriz-bg-rebalance/lib/time_stop_haste_clocks.tpa",
    "CBR_TRUE_TIMESTOP/lua/CBRTC.lua": ROOT / "chriz-bg-rebalance/lua/CBRTC.lua",
    "CBR_TRUE_TIMESTOP/lua/M_CBRTC.lua": ROOT / "chriz-bg-rebalance/lua/M_CBRTC.lua",
}
_built: dict[str, Path] = {}


def setUpModule() -> None:
    from tools.package_timestop import build
    holder = tempfile.TemporaryDirectory(prefix="cbr-timestop-packages-")
    unittest.addModuleCleanup(holder.cleanup)
    for path in build(Path(holder.name)):
        _built[path.name] = path


def run_packager(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(ROOT / "tools/package_timestop.py"), "--output", str(output)],
                          cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)


def component(text: str, number: int) -> list[str]:
    """The lines of one component of a tp2, from its BEGIN to the next BEGIN or the end."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"BEGIN @\d+ DESIGNATED {number}\b", line))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("BEGIN ")), len(lines))
    return [line.strip() for line in lines[start:end] if line.strip() and not line.strip().startswith("//")]


class StandaloneInstallerTests(main_installer.TimeStopHasteClocksInstallerTests):
    """The package makes BG Rebalance's checks and installs the same two files."""

    def game(self, **kwargs: object) -> ClocksGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-clocks-standalone-")
        self.addCleanup(temporary.cleanup)
        return ClocksGame(Path(temporary.name) / "game", package=_built[ARCHIVE], **kwargs)


class PackageTests(unittest.TestCase):
    def temporary(self, prefix: str) -> Path:
        holder = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def game(self, **kwargs: object) -> ClocksGame:
        return ClocksGame(self.temporary("cbr-clocks-both-") / "game", **kwargs)

    def run_weidu(self, game: ClocksGame, command: list[str], *args: str) -> str:
        done = subprocess.run([*command, "--game", str(game.root), *args, "360", "--language", "0",
                               "--use-lang", "en_US", "--no-exit-pause", "--quick-log"],
                              cwd=game.root, capture_output=True, text=True, timeout=90, check=False)
        return f"exit {done.returncode}\n{done.stdout}\n{done.stderr}"

    def install_package(self, game: ClocksGame, form: str = "auto") -> str:
        exe = str(game.root / PACKAGE_EXE)
        tp2 = {"auto": [], "slash": [PACKAGE_TP2], "backslash": [PACKAGE_TP2.replace("/", "\\")],
               "absolute": [str(game.root / PACKAGE_TP2)]}[form]
        return self.run_weidu(game, [exe, *tp2], "--force-install-list")

    def add_rebalance(self, game: ClocksGame, *, guard: bool = True, lua_suffix: bytes = b"") -> None:
        shutil.copy2(ROOT / TP2, game.root / TP2)
        shutil.copytree(ROOT / "chriz-bg-rebalance", game.root / "chriz-bg-rebalance")
        if not guard:
            # BG Rebalance up to v0.8.6 had no guard against the package.
            text = (game.root / TP2).read_text(encoding="utf-8")
            self.assertEqual(1, text.count(GUARD))
            (game.root / TP2).write_text(text.replace(GUARD, ""), encoding="utf-8")
        if lua_suffix:
            for name in ("CBRTC.lua", "M_CBRTC.lua"):
                path = game.root / "chriz-bg-rebalance/lua" / name
                path.write_bytes(path.read_bytes() + lua_suffix)

    def rebalance(self, game: ClocksGame, mode: str = "--force-install-list", tp2: str = TP2) -> str:
        return self.run_weidu(game, [str(WEIDU), tp2], mode)

    def assert_installed(self, transcript: str, game: ClocksGame, line: str) -> None:
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertRegex(game.active_log(), line)
        after = tree(game.override)
        self.assertEqual(set(after), set(game.before) | set(SOURCES))

    def assert_refused_by_guard(self, transcript: str, game: ClocksGame, before: tuple) -> None:
        self.assertIn("SKIPPING", transcript, transcript)
        self.assertIn(GUARD_TEXT, transcript, transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertEqual(before, (tree(game.override), game.active_log()))

    def test_packager_builds_four_matched_archives_reproducibly(self) -> None:
        first, second = self.temporary("cbr-timestop-build-1-"), self.temporary("cbr-timestop-build-2-")
        for output in (first, second):
            result = run_packager(output)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        expected = {f"{name}-{VERSION}-windows.zip" for name in
                    ("chriz-bg-rebalance", "CBR_SR_HARDINESS", "CBR_SR_ANTIMAGIC", "CBR_TRUE_TIMESTOP")}
        self.assertEqual(expected, {path.name for path in first.glob("*.zip")})
        self.assertEqual({name + ".sha256" for name in expected}, {path.name for path in first.glob("*.sha256")})
        for name in expected:
            archive = first / name
            self.assertEqual(archive.read_bytes(), (second / name).read_bytes(), f"{name} is not reproducible")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            # Exact bytes, LF: sha256sum -c rejects the CRLF that text mode writes on Windows.
            self.assertEqual(f"{digest}  {name}\n".encode(), archive.with_suffix(".zip.sha256").read_bytes())
        with zipfile.ZipFile(first / ARCHIVE) as bundle:
            # An exact allowlist: no other Rebalance component, research file, fixture or save.
            self.assertEqual(set(MEMBERS), set(bundle.namelist()))
            for relative, source in MEMBERS.items():
                self.assertEqual(source.read_bytes(), bundle.read(relative), relative)
            self.assertIn(f"VERSION ~{VERSION}~", bundle.read(PACKAGE_TP2).decode("utf-8"))

    def test_packager_refuses_mismatched_versions(self) -> None:
        import tools.package_timestop as packager
        root = self.temporary("cbr-timestop-version-")
        (root / "live-patch/CBR_TRUE_TIMESTOP").mkdir(parents=True)
        (root / TP2).write_text("VERSION ~v9.9.9~\n", encoding="utf-8")
        shutil.copy2(PACKAGE / "setup-cbr_true_timestop.tp2", root / "live-patch/CBR_TRUE_TIMESTOP/setup-cbr_true_timestop.tp2")
        original = packager.ROOT
        packager.ROOT = root
        try:
            with self.assertRaisesRegex(ValueError, "versions must agree"):
                packager.build(root / "dist")
        finally:
            packager.ROOT = original
        self.assertFalse((root / "dist").exists())

    def test_installers_make_the_same_checks(self) -> None:
        main = component((ROOT / TP2).read_text(encoding="utf-8"), 360)
        package = component((PACKAGE / "setup-cbr_true_timestop.tp2").read_text(encoding="utf-8"), 360)
        def predicates(lines: list[str]) -> list[str]:
            return [line for line in lines if line.startswith("REQUIRE_PREDICATE")]
        self.assertEqual(predicates(main)[:3], predicates(package)[:3])
        self.assertEqual([GUARD], predicates(main)[3:])
        self.assertEqual(["REQUIRE_PREDICATE NOT (MOD_IS_INSTALLED ~setup-chriz-bg-rebalance.tp2~ 360) @9366"],
                         predicates(package)[3:])
        self.assertEqual(["LAF cbr_install_time_stop_haste_component END", "PRINT @9365"], main[-2:])
        self.assertEqual(["LAF cbr_install_time_stop_haste_component STR_VAR source_dir = ~CBR_TRUE_TIMESTOP/lua~ END",
                          "PRINT @9365"], package[-2:])
        # BEGIN, the three shared predicates, the guard, LAF and PRINT: nothing else in either.
        self.assertEqual(7, len(main))
        self.assertEqual(7, len(package))

    def test_weidu_logs_the_package_by_its_folder(self) -> None:
        # A double-click on Setup-cbr_true_timestop.exe finds CBR_TRUE_TIMESTOP/setup-cbr_true_timestop.tp2.
        game = self.game(package=_built[ARCHIVE])
        transcript = self.install_package(game)
        self.assert_installed(transcript, game, r"(?m)^~CBR_TRUE_TIMESTOP/SETUP-CBR_TRUE_TIMESTOP\.TP2~ #0 #360\b")

    def test_rebalance_refuses_while_the_package_is_installed(self) -> None:
        # Mod managers pass the tp2 path in other forms; WeiDU logs each as given.
        for form, line in (("auto", r"~CBR_TRUE_TIMESTOP/SETUP-CBR_TRUE_TIMESTOP\.TP2~"),
                           ("backslash", r"~CBR_TRUE_TIMESTOP\\SETUP-CBR_TRUE_TIMESTOP\.TP2~"),
                           ("absolute", r"~[A-Z]:\\.*\\CBR_TRUE_TIMESTOP\\SETUP-CBR_TRUE_TIMESTOP\.TP2~")):
            with self.subTest(form=form):
                game = self.game(package=_built[ARCHIVE])
                self.add_rebalance(game)
                self.assert_installed(self.install_package(game, form), game, rf"(?m)^{line} #0 #360\b")
                installed = tree(game.override), game.active_log()
                self.assert_refused_by_guard(self.rebalance(game), game, installed)
                # Uninstalling the package leaves the game as before; then Rebalance's 360 installs.
                transcript = self.run_weidu(game, [str(game.root / PACKAGE_EXE)], "--force-uninstall-list")
                self.assertIn("exit 0", transcript, transcript)
                self.assertEqual(game.before, tree(game.override))
                self.assertNotRegex(game.active_log(), r"#360\b")
                self.assert_installed(self.rebalance(game), game, r"(?m)^~SETUP-CHRIZ-BG-REBALANCE\.TP2~ #0 #360\b")

    def test_package_refuses_while_rebalance_360_is_installed(self) -> None:
        for form in ("root", "absolute"):
            with self.subTest(form=form):
                game = self.game(package=_built[ARCHIVE])
                self.add_rebalance(game)
                tp2 = TP2 if form == "root" else str(game.root / TP2)
                self.assert_installed(self.rebalance(game, tp2=tp2), game, r"(?mi)SETUP-CHRIZ-BG-REBALANCE\.TP2~ #0 #360\b")
                installed = tree(game.override), game.active_log()
                self.assert_refused_by_guard(self.install_package(game), game, installed)
                transcript = self.rebalance(game, "--force-uninstall-list", tp2)
                self.assertIn("exit 0", transcript, transcript)
                self.assertEqual(game.before, tree(game.override))
                self.assert_installed(self.install_package(game), game, r"(?m)^~CBR_TRUE_TIMESTOP/SETUP-CBR_TRUE_TIMESTOP\.TP2~ #0 #360\b")

    def test_package_installs_beside_other_rebalance_components(self) -> None:
        game = self.game(package=_built[ARCHIVE])
        (game.root / "WeiDU.log").write_text("~SETUP-CHRIZ-BG-REBALANCE.TP2~ #0 #340 // Chris Revisions\n"
                                             "~SETUP-CHRIZ-BG-REBALANCE.TP2~ #0 #320 // clouds\n", encoding="utf-8")
        self.assert_installed(self.install_package(game), game, r"(?m)^~CBR_TRUE_TIMESTOP/SETUP-CBR_TRUE_TIMESTOP\.TP2~ #0 #360\b")

    def test_either_uninstall_keeps_the_other_when_both_are_logged(self) -> None:
        # Only an installer without the guard, BG Rebalance up to v0.8.6, can follow the package.
        # Its two files are marked here, so the override shows whose files are in place.
        marked = {name: (ROOT / "chriz-bg-rebalance/lua" / name).read_bytes() + b"\n-- v0.8.6\n"
                  for name in ("CBRTC.lua", "M_CBRTC.lua")}
        package = {name: (ROOT / "chriz-bg-rebalance/lua" / name).read_bytes() for name in marked}
        def in_override(game: ClocksGame) -> dict[str, bytes]:
            return {name: (game.override / name).read_bytes() for name in marked if (game.override / name).exists()}
        for first in ("rebalance", "package"):
            with self.subTest(uninstall_first=first):
                game = self.game(package=_built[ARCHIVE])
                self.add_rebalance(game, guard=False, lua_suffix=b"\n-- v0.8.6\n")
                self.assertIn("SUCCESSFULLY INSTALLED", self.install_package(game))
                self.assertIn("SUCCESSFULLY INSTALLED", self.rebalance(game))
                self.assertEqual(marked, in_override(game))
                if first == "rebalance":
                    transcript = self.rebalance(game, "--force-uninstall-list")
                    self.assertIn("exit 0", transcript, transcript)
                    self.assertEqual(package, in_override(game))
                    self.assertRegex(game.active_log(), r"(?m)^~CBR_TRUE_TIMESTOP/SETUP-CBR_TRUE_TIMESTOP\.TP2~ #0 #360\b")
                    self.assertNotRegex(game.active_log(), r"REBALANCE\.TP2~ #0 #360\b")
                else:
                    transcript = self.run_weidu(game, [str(game.root / PACKAGE_EXE)], "--force-uninstall-list")
                    self.assertIn("exit 0", transcript, transcript)
                    self.assertEqual(marked, in_override(game))
                    self.assertRegex(game.active_log(), r"(?m)^~SETUP-CHRIZ-BG-REBALANCE\.TP2~ #0 #360\b")
                    self.assertNotRegex(game.active_log(), r"CBR_TRUE_TIMESTOP\.TP2~ #0 #360\b")
                self.assertEqual(set(game.before) | set(SOURCES), set(tree(game.override)))
                for name, payload in game.before.items():
                    self.assertEqual(payload, tree(game.override)[name], name)


if __name__ == "__main__":
    unittest.main()
