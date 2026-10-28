"""Real WeiDU tests of component 360 on disposable games, never on an installed playthrough.

The executable is a synthetic PE header: the installer reads only its signature, machine and
timestamp. Whether a real executable's patch windows match is decided by the correction at game
start (tests/test_time_stop_haste_clocks.py). tests/test_time_stop_haste_clocks_standalone.py runs
every test here once more with the standalone package instead of BG Rebalance's installer.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.test_tempus_holy_power_installer import ONE_EMPTY_STRING_TLK, _write_key_and_bif

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
TP2 = "setup-chriz-bg-rebalance.tp2"
PACKAGE_EXE = "Setup-cbr_true_timestop.exe"
SOURCES = {"CBRTC.LUA": ROOT / "chriz-bg-rebalance/lua/CBRTC.lua",
           "M_CBRTC.LUA": ROOT / "chriz-bg-rebalance/lua/M_CBRTC.lua"}
STAMP_2730, STAMP_2660 = 0x6A18D73D, 0x609437B3


def executable(*, timestamp: int = STAMP_2730, machine: int = 0x8664, pe: bool = True) -> bytes:
    header = bytearray(0x200)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = (0x80).to_bytes(4, "little")
    if pe:
        header[0x80:0x84] = b"PE\0\0"
    header[0x84:0x86] = machine.to_bytes(2, "little")
    header[0x88:0x8C] = timestamp.to_bytes(4, "little")
    return bytes(header)


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


class ClocksGame:
    """A synthetic game with one installer for 360: BG Rebalance's (the default) or, with
    `package`, the standalone archive extracted over the game folder as a player would."""

    def __init__(self, root: Path, *, exes: dict[str, bytes] | None = None, eeex: bool = True,
                 bg2ee: bool = True, eet: bool = False, patch27: bool = True,
                 package: Path | None = None) -> None:
        self.root = root
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        self.package = package
        if package is None:
            shutil.copy2(ROOT / TP2, root / TP2)
            shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
        else:
            with zipfile.ZipFile(package) as bundle:
                for name in bundle.namelist():
                    if not (root / name).resolve().is_relative_to(root.resolve()):
                        raise ValueError(f"archive member escapes the game: {name}")
                bundle.extractall(root)
        resources = [("OH6000" if bg2ee else "AR0000", "ARE", b"synthetic game marker"),
                     ("SPELL", "IDS", b"IDS V1.0\n1 EMPTY_SPELL\n"),
                     ("STATS", "IDS", b"IDS V1.0\n1 MAXHITPOINTS\n"),
                     ("KIT", "IDS", b"IDS V1.0\n0 TRUECLASS\n")]
        _write_key_and_bif(root, tuple(resources))
        for path in (root / "dialog.tlk", root / "lang/en_us/dialog.tlk"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ONE_EMPTY_STRING_TLK)
        if patch27:
            # As the 2.7.3.0 games ship it.
            (root / "data/PATCH27.bif").write_bytes(b"BIFFV1  synthetic patch marker")
        for name, payload in (exes if exes is not None else {"Baldur.exe": executable()}).items():
            (root / name).write_bytes(payload)
        if eeex:
            (self.override / "M___EEex.lua").write_text("-- fixture bootstrap\n", encoding="ascii")
        if eet:
            (self.override / "EET.FLAG").write_bytes(b"1")
        (self.override / "SENTINEL.CRE").write_bytes(b"unrelated creature: must not change")
        (self.override / "M_OTHER.lua").write_bytes(b"-- another mod's autoload: must not change\n")
        self.before = tree(self.override)
        self.outside = {name: payload for name, payload in tree(root).items()
                        if not name.startswith("OVERRIDE/")}

    def weidu(self, *args: str) -> subprocess.CompletedProcess[str]:
        # The package's own setup executable finds its tp2 by its name, as a double click does.
        command = [str(WEIDU), TP2] if self.package is None else [str(self.root / PACKAGE_EXE)]
        return subprocess.run(
            [*command, "--game", str(self.root), *args, "360",
             "--language", "0", "--use-lang", "en_US", "--no-exit-pause", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=90, check=False,
        )

    def active_log(self) -> str:
        path = self.root / "WeiDU.log"
        if not path.exists():
            return ""
        return "\n".join(line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                         if not line.lstrip().startswith("//"))


class TimeStopHasteClocksInstallerTests(unittest.TestCase):
    def game(self, **kwargs: object) -> ClocksGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-clocks-installer-")
        self.addCleanup(temporary.cleanup)
        return ClocksGame(Path(temporary.name) / "game", **kwargs)

    def assert_outside_unchanged(self, game: ClocksGame) -> None:
        after = {name: payload for name, payload in tree(game.root).items()
                 if not name.startswith(("OVERRIDE/", "WEIDU_EXTERNAL/")) and name not in
                 ("WEIDU.LOG", "SETUP-CHRIZ-BG-REBALANCE.DEBUG", "SETUP-CBR_TRUE_TIMESTOP.DEBUG",
                  "WEIDU.CONF")}
        self.assertEqual(after, game.outside)

    def assert_installed(self, game: ClocksGame) -> str:
        process = game.weidu("--force-install-list")
        transcript = process.stdout + "\n" + process.stderr
        self.assertEqual(process.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertIn("switches itself on whenever the game starts", transcript)
        self.assertRegex(game.active_log(), r"(?m)#0\s+#360\b")
        after = tree(game.override)
        self.assertEqual(set(after), set(game.before) | set(SOURCES))
        for name, payload in game.before.items():
            self.assertEqual(after[name], payload, name)
        for name, source in SOURCES.items():
            self.assertEqual(hashlib.sha256(after[name]).digest(),
                             hashlib.sha256(source.read_bytes()).digest(), name)
        self.assert_outside_unchanged(game)
        return transcript

    def assert_refused(self, game: ClocksGame, text: str) -> None:
        process = game.weidu("--force-install-list")
        transcript = process.stdout + "\n" + process.stderr
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#360\b")
        self.assertIn(text.lower(), transcript.lower(), transcript)
        self.assertEqual(tree(game.override), game.before)
        self.assert_outside_unchanged(game)

    def test_installs_only_the_correction_and_its_autoload(self) -> None:
        self.assert_installed(self.game())

    def test_eet(self) -> None:
        self.assert_installed(self.game(eet=True))

    def test_gog_executable_name(self) -> None:
        # GOG's 2.7.3.0 ships the same file as BaldurII.exe.
        self.assert_installed(self.game(exes={"BaldurII.exe": executable()}))

    def test_checks_the_executable_the_loader_starts(self) -> None:
        # InfinityLoader starts Baldur.exe before BaldurII.exe.
        self.assert_refused(self.game(exes={"Baldur.exe": executable(timestamp=STAMP_2660),
                                            "BaldurII.exe": executable()}),
                            "Baldur.exe is a different build")
        self.assert_installed(self.game(exes={"Baldur.exe": executable(),
                                              "BaldurII.exe": executable(timestamp=STAMP_2660)}))

    def test_uninstall_restores_the_override(self) -> None:
        game = self.game()
        self.assert_installed(game)
        process = game.weidu("--force-uninstall-list")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(tree(game.override), game.before)
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#360\b")

    def test_refuses_another_game(self) -> None:
        self.assert_refused(self.game(bg2ee=False), "supports BG2:EE / EET only")

    def test_refuses_without_eeex(self) -> None:
        self.assert_refused(self.game(eeex=False), "requires EEex. Install EEex before this component")

    def test_refuses_earlier_game_versions(self) -> None:
        self.assert_refused(self.game(patch27=False, exes={"Baldur.exe": executable(timestamp=STAMP_2660)}),
                            "requires game version 2.7.3.0")

    def test_refuses_other_executables(self) -> None:
        for label, payload in (("2.6.6.0", executable(timestamp=STAMP_2660)),
                               ("32-bit", executable(machine=0x14C)),
                               ("no PE image", executable(pe=False)),
                               ("truncated", b"MZ")):
            with self.subTest(executable=label):
                self.assert_refused(self.game(exes={"Baldur.exe": payload}),
                                    "supports only the 64-bit BG2:EE 2.7.3.0 executable (Steam and "
                                    "GOG ship the same file); Baldur.exe is a different build. "
                                    "Nothing was installed.")

    def test_refuses_without_an_executable(self) -> None:
        self.assert_refused(self.game(exes={}), "could not find the game's executable")


if __name__ == "__main__":
    unittest.main()
