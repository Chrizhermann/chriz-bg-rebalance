"""The public component on disposable WeiDU games. The standalone repeats these cases."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_tempus_holy_power_installer import RESOURCE_TYPE, _write_key_and_bif
from tests.test_time_stop_haste_clocks_installer import ClocksGame, ROOT, TP2, WEIDU, executable, tree

PACKAGE = "CBR_ROUND_CLOCK"
TAIL_TP2 = f"{PACKAGE}/setup-cbr_round_clock.tp2"
TAIL_EXE = "Setup-cbr_round_clock.exe"
PAYLOAD = {name.upper(): (ROOT / "chriz-bg-rebalance/lua" / name).read_bytes()
           for name in ("CBRRC.lua", "M_CBRRC.lua")}
STAMPS = {"bgee": 0x6A18D6DC, "sod": 0x6A18D6DC, "bg2ee": 0x6A18D73D,
          "eet": 0x6A18D73D, "iwdee": 0x6A18D7E9}


class RoundGame(ClocksGame):
    def __init__(self, root, *, edition="bg2ee", exes=None, package=None, eeex=True):
        if exes is None:
            name = "icewind.exe" if edition == "iwdee" else "Baldur.exe"
            exes = {name: executable(timestamp=STAMPS.get(edition, STAMPS["bg2ee"]))}
        super().__init__(root, exes=exes, eeex=False, bg2ee=edition in ("bg2ee","eet"),
                         eet=edition=="eet", patch27=False, package=package)
        if package is None:
            self.install_sources()
        if edition in ("bgee","sod","iwdee"):
            marker = ("HOWPARTY","2DA") if edition == "iwdee" else ("OH1000","ARE")
            resources = [(*marker,b"fixture"), ("SPELL","IDS",b"IDS V1.0\n"), ("KIT","IDS",b"IDS V1.0\n"),
                         ("STATS","IDS",b"IDS V1.0\n")]
            if edition == "sod":
                resources.append(("CAMPAIGN","2DA",b"2DA V1.0\n*\n CAMPAIGN\n1 SOD\n"))
            with patch.dict(RESOURCE_TYPE, {"2DA": 1012}):
                _write_key_and_bif(root, tuple(resources))
        if eeex:
            # A real EEex installation already has a WeiDU log. Let WeiDU establish
            # that prerequisite and its backup ownership in this synthetic game too.
            marker = root / "setup-fixture-eeex.tp2"
            marker.write_text('BACKUP ~weidu_external/backup/fixture-eeex~\nAUTHOR ~fixture~\n'
                              'BEGIN ~Synthetic EEex bootstrap~\n'
                              'COPY ~fixture-eeex.lua~ ~override/M___EEex.lua~\n', encoding="ascii")
            (root/"fixture-eeex.lua").write_bytes(b"-- synthetic EEex bootstrap\n")
            subprocess.run([str(WEIDU), marker.name, "--force-install-list", "0", "--language", "0",
                            "--use-lang", "en_US", "--no-exit-pause", "--quick-log"], cwd=root,
                           capture_output=True, timeout=90, check=True)
        self.before = tree(self.override)

    def install_sources(self):
        shutil.copy2(WEIDU, self.root / "Setup-chriz-bg-rebalance.exe")
        if not (self.root / TP2).exists():
            shutil.copy2(ROOT / TP2, self.root / TP2)
            shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")

    def invoke(self, *, tail=None, form="auto", component=361, uninstall=False):
        if tail is None:
            tail = self.package is not None
        tp2 = TAIL_TP2 if tail else TP2
        setup = self.root / (TAIL_EXE if tail else "Setup-chriz-bg-rebalance.exe")
        if form == "auto":
            args = [str(setup)]
        else:
            spelling = {"slash": tp2 if tail else "./"+tp2,
                        "backslash": tp2.replace("/", "\\") if tail else ".\\"+tp2,
                        "absolute": str(self.root / tp2)}[form]
            args = [str(WEIDU), spelling]
        mode = "--force-uninstall-list" if uninstall else "--force-install-list"
        return subprocess.run([*args, "--game", str(self.root), mode, str(component), "--language", "0",
                               "--use-lang", "en_US", "--no-exit-pause", "--quick-log"],
                              cwd=self.root, capture_output=True, text=True, timeout=90)

    def stable_files(self):
        # Include package sources, the executable read by the installer, dialog, KEY and BIFF.
        return {name: contents for name, contents in tree(self.root).items()
                if not name.startswith(("OVERRIDE/","WEIDU_EXTERNAL/"))
                and not name.endswith(".DEBUG") and name not in ("WEIDU.CONF","WEIDU.LOG")}


class RoundClockInstallerTests(unittest.TestCase):
    package = None

    def game(self, **options):
        holder = tempfile.TemporaryDirectory(prefix="cbr-361-")
        self.addCleanup(holder.cleanup)
        return RoundGame(Path(holder.name)/"game", package=self.package, **options)

    def success(self, game, **options):
        result = game.invoke(**options)
        log = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, log)
        self.assertIn("SUCCESSFULLY INSTALLED", log)
        self.assertNotRegex(log.upper(), r"\bWARNING(?:S)?\b")
        self.assertRegex(game.active_log(), rf"#0\s+#{options.get('component',361)}\b")

    def test_full_payload_and_byte_exact_uninstall_on_every_game(self):
        for edition in STAMPS:
            with self.subTest(edition=edition):
                game = self.game(edition=edition)
                stable = game.stable_files()
                self.success(game)
                self.assertEqual(tree(game.override), game.before | PAYLOAD)
                backup = "cbr_round_clock" if self.package else "chriz-bg-rebalance"
                self.assertTrue((game.root / "weidu_external/backup" / backup / "361").is_dir())
                self.assertEqual(game.stable_files(), stable)
                result = game.invoke(uninstall=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual(tree(game.override), game.before)
                self.assertEqual(game.stable_files(), stable)
                self.assertNotRegex(game.active_log(), r"#361\b")

    def test_reinstall_over_mutated_lua_and_restore_original_bytes(self):
        game = self.game()
        for i, name in enumerate(PAYLOAD):
            (game.override/name).write_bytes(bytes([i,255,0,13,10])+b"old Lua from another install")
        # Deliberately unrelated game content, including missing/extra effects and edited text.
        from tests.ie_formats import SplAbility, SplEffect, SplFile
        for i, effects in enumerate(((), (SplEffect(opcode=12), SplEffect(opcode=206)))):
            ability = SplAbility(required_level=1, target=1, projectile=1, effects=effects)
            (game.override/f"EDITED{i}.SPL").write_bytes(SplFile(abilities=(ability,)).to_bytes())
        (game.override/"STRINGS.2DA").write_bytes(b"2DA V1.0\n*\n NAME\n0 ~other wording~\n")
        before, stable = tree(game.override), game.stable_files()
        self.success(game)
        self.assertEqual(tree(game.override), before | PAYLOAD)
        for name in PAYLOAD:
            (game.override/name).write_bytes(b"-- hand edit after install\n")
        self.success(game)
        self.assertEqual(tree(game.override), before | PAYLOAD)
        result = game.invoke(uninstall=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree(game.override), before)
        self.assertEqual(game.stable_files(), stable)

    def test_loader_filename_precedence(self):
        good, bad = executable(), executable(timestamp=0x609437B3)
        self.success(self.game(exes={"BaldurII.exe":good}))
        self.success(self.game(exes={"Baldur.exe":good,"BaldurII.exe":bad}))
        self.refused(self.game(exes={"Baldur.exe":bad,"BaldurII.exe":good}), "Baldur.exe is a different build")
        self.refused(self.game(edition="iwdee", exes={"Baldur.exe":good}), "requires icewind.exe")
        self.refused(self.game(edition="iwdee", exes={"Baldur.exe":good,"icewind.exe":bad}),
                     "icewind.exe is a different build")

    def refused(self, game, reason):
        stable, before, logged = game.stable_files(), tree(game.override), game.active_log()
        result = game.invoke()
        log = result.stdout + result.stderr
        self.assertIn(reason.lower(), log.lower(), log)
        self.assertNotIn("SUCCESSFULLY INSTALLED", log)
        self.assertEqual((stable,before,logged), (game.stable_files(), tree(game.override), game.active_log()))

    def test_genuine_requirements_and_malformed_executables(self):
        self.refused(self.game(edition="other"), "requires BG:EE")
        self.refused(self.game(eeex=False), "requires EEex")
        self.refused(self.game(exes={}), "could not find")
        for label,data in (("2.6.6.0",executable(timestamp=0x609437B3)), ("32-bit",executable(machine=0x14C)),
                           ("non-PE",executable(pe=False)), ("short DOS",b"MZ"),
                           ("short COFF",executable()[:0x8C]), ("out-of-bounds NT",b"MZ"+bytes(58)+b"\xff"*4)):
            with self.subTest(label=label):
                self.refused(self.game(exes={"Baldur.exe":data}), "Baldur.exe is a different build")
