"""Public 130/220 entry points: disposable fixtures only, never a live game."""
from __future__ import annotations

import dataclasses
import hashlib
import re
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplEffect
from tests.test_cloud_forms import Game, ROOT, WEIDU, form, expected_form
from tests.test_flail_of_ages import strings
from tests.test_sr_bracers import Game as BracersGame, synthetic as bracers_resources

TEXTS = [
    "Unrelated shared text.",
    "Arrow of Acid +1", "Damage: 1d6+1, +2d6 acid damage\nTHAC0: +1",
    "Arrow of Ice", "Damage: 1d6, +1d6 cold damage\nTHAC0: +0",
    "Arrow of Fire +2", "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell negates)\nTHAC0: +2",
]


def arrow_resources():
    result = {"SPELL.IDS": b"IDS V1.0\n", "EET.FLAG": b"1"}
    for name, damage_type, size, bonus, desc, save in (
        ("AROW04", 65536, 6, 1, 2, 0),
        ("AROW09", 131072, 6, 0, 4, 0),
        ("AROW08", 524288, 6, 2, 6, 1),
        ("AROWKC", 524288, 6, 2, 6, 2),
    ):
        header = bytearray(0x72)
        struct.pack_into("<H", header, 0x1c, 5)
        struct.pack_into("<I", header, 0x0c, desc - 1)
        struct.pack_into("<I", header, 0x54, desc)
        ab = bytearray(56)
        ab[0] = 2
        struct.pack_into("<H", ab, 0x14, bonus)
        struct.pack_into("<H", ab, 0x1a, bonus)
        result[name + ".ITM"] = ItmFile(
            abilities=(ItmAbility(raw=bytes(ab), effects=(
                SplEffect(opcode=12, target=2, parameter2=damage_type,
                          dice_number=2 if name == "AROW04" else 1,
                          dice_size=size, save_type=save),
                SplEffect(opcode=177, target=2, resource="DWTROLL", timing=1),
            )),), header_raw=bytes(header), identified_name=desc - 1,
            identified_description=desc).to_bytes()
    result["ARROPHE2.ITM"] = result["AROW08.ITM"]
    return result


def run_public(game, component, *, uninstall=False):
    p = subprocess.run([
        str(WEIDU), "setup-chriz-bg-rebalance.tp2",
        "--force-uninstall-list" if uninstall else "--force-install-list", str(component),
        "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log",
    ], cwd=game.root, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


class ReleaseComponentsTests(unittest.TestCase):
    def game(self, resources, *, log="", texts=TEXTS):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-release-components-")
        self.addCleanup(temporary.cleanup)
        g = Game(Path(temporary.name), resources, public=True, texts=texts)
        (g.root / "WeiDU.log").write_text(log)
        return g

    def installed(self, g, component):
        code, output = run_public(g, component)
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)

    def test_arrows_public_values_preservation_and_exact_uninstall(self):
        g = self.game(arrow_resources(), log="~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000\n")
        self.installed(g, 130)
        after = g.snapshot()
        for name in ("AROW04", "AROW09", "AROW08", "AROWKC"):
            old, new = g.original[name + ".ITM"], after[name + ".ITM"]
            before_item, item = ItmFile.from_bytes(old), ItmFile.from_bytes(new)
            damage = item.abilities[0].effects[0]
            self.assertEqual((1, 3 if name == "AROW04" else 2),
                             (damage.dice_number, damage.dice_size))
            self.assertEqual(before_item.abilities[0].effects[0].save_type, damage.save_type)
            expected = bytearray(old)
            ab, = struct.unpack_from("<I", old, 0x64)
            fx, = struct.unpack_from("<I", old, 0x6a)
            struct.pack_into("<II", expected, fx + 28, 1, damage.dice_size)
            if name in ("AROW08", "AROWKC"):
                struct.pack_into("<H", expected, ab + 20, 0)
                struct.pack_into("<H", expected, ab + 26, 0)
            # Only local name/description pointers may differ in addition.
            expected[12:16], expected[84:88] = new[12:16], new[84:88]
            self.assertEqual(bytes(expected), new)
        self.assertEqual(g.original["ARROPHE2.ITM"], after["ARROPHE2.ITM"])
        texts = strings(g.tlk)
        self.assertEqual(TEXTS, texts[:len(TEXTS)])
        for name in ("AROW08", "AROWKC"):
            desc, = struct.unpack_from("<I", after[name + ".ITM"], 84)
            self.assertIn("+1d2 fire damage", texts[desc])
            self.assertIn("Save vs. Breath" if name == "AROWKC" else "Save vs. Spell", texts[desc])
        code, output = run_public(g, 130, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(g.original, g.snapshot())

    def test_arrows_missing_scs_skips_without_changes(self):
        g = self.game(arrow_resources())
        code, output = run_public(g, 130)
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(g.original, g.snapshot())

    def test_arrows_malformed_last_item_rolls_back(self):
        resources = arrow_resources()
        item = ItmFile.from_bytes(resources["AROWKC.ITM"])
        ability = item.abilities[0]
        wrong = dataclasses.replace(ability.effects[0], parameter2=12345)
        resources["AROWKC.ITM"] = dataclasses.replace(item, abilities=(
            dataclasses.replace(ability, effects=(wrong, *ability.effects[1:])),)).to_bytes()
        g = self.game(resources, log="~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000\n")
        code, output = run_public(g, 130)
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(g.original, g.snapshot())

    def test_bracers_public_matches_tail_and_uninstalls(self):
        g = self.game(bracers_resources(), log="~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0\n")
        temporary = tempfile.TemporaryDirectory(prefix="cbr-bracers-parity-")
        self.addCleanup(temporary.cleanup)
        tail = BracersGame(Path(temporary.name), bracers_resources())
        p, output = tail.run()
        self.assertEqual(0, p.returncode, output)
        self.installed(g, 220)
        self.assertEqual(tail.snapshot(), g.snapshot())
        code, output = run_public(g, 220, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(g.original, g.snapshot())

    def test_bracers_without_sr_skips(self):
        g = self.game(bracers_resources())
        code, output = run_public(g, 220)
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(g.original, g.snapshot())

    def test_extracted_full_archive_installs_new_public_components(self):
        from tools.package_sr_antimagic import build
        holder = tempfile.TemporaryDirectory(prefix="cbr-full-package-")
        self.addCleanup(holder.cleanup)
        output = Path(holder.name)
        archives = build(output)
        full = next(p for p in archives if p.name.startswith("chriz-bg-rebalance-"))
        digest = hashlib.sha256(full.read_bytes()).hexdigest()
        self.assertEqual(f"{digest}  {full.name}",
                         full.with_suffix(".zip.sha256").read_text().strip())
        resources = arrow_resources()
        resources.update(bracers_resources())
        resources["DVGASFRM.ITM"] = form("DVGASFRM.ITM")
        g = self.game(resources, log="~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000\n"
                                    "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0\n")
        with zipfile.ZipFile(full) as bundle:
            allowed = {"LICENSE", "WEIDU-LICENSE.txt", "README.md", "CHANGELOG.md",
                       "setup-chriz-bg-rebalance.tp2", "Setup-chriz-bg-rebalance.exe"}
            allowed.update(p.relative_to(ROOT).as_posix()
                           for p in (ROOT / "chriz-bg-rebalance").rglob("*") if p.is_file())
            self.assertEqual(allowed, set(bundle.namelist()))
            for name in bundle.namelist():
                source = ROOT / ("weidu.exe" if name == "Setup-chriz-bg-rebalance.exe" else name)
                self.assertEqual(source.read_bytes(), bundle.read(name), name)
            setup = bundle.read("setup-chriz-bg-rebalance.tp2").decode("utf-8")
            ids = [int(x) for x in re.findall(r"DESIGNATED\s+(\d+)", setup)]
            for component in (130, 200, 201, 202, 210, 211, 220, 310, 320):
                self.assertEqual(1, ids.count(component))
            self.assertNotIn(311, ids)
            self.assertEqual([130, 220, 320], ids[-3:])
            bundle.extractall(g.root)
        # Execute the package's own WeiDU and staged sources, not repo files.
        p = subprocess.run([str(g.root / "Setup-chriz-bg-rebalance.exe"),
                            "setup-chriz-bg-rebalance.tp2", "--force-install-list",
                            "130", "220", "320", "--language", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        log = (g.root / "WeiDU.log").read_text()
        for component in (130, 220, 320):
            self.assertRegex(log, rf"#0\s+#{component}\b")
        self.assertTrue((g.override / "CBRBIH.SPL").exists())
        self.assertEqual(expected_form(resources["DVGASFRM.ITM"]),
                         g.snapshot()["DVGASFRM.ITM"])
