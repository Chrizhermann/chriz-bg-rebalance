"""Real WeiDU 249 tests; all writes are to disposable synthetic games."""
from __future__ import annotations

import dataclasses
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, make_spl, read_itm
from tests.test_tempus_holy_power_installer import RESOURCE_TYPE, _write_key_and_bif

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
CAPTURES = ROOT / "research/originals/flail-ages"
TIERS = {"BLUN14": 2, "BLUN30C": 4, "BLUN30D": 4, "BLUN30": 6}
RESOURCE_TYPE["ITM"] = 1005


def tlk(strings: list[str]) -> bytes:
    rows, data = bytearray(), bytearray()
    for text in strings:
        raw = text.encode("utf-8")
        rows.extend(struct.pack("<H8siiII", 1, bytes(8), 0, 0, len(data), len(raw)))
        data.extend(raw)
    return struct.pack("<8sHII", b"TLK V1  ", 0, len(strings), 18 + 26 * len(strings)) + rows + data


def strings(path: Path) -> list[str]:
    raw = path.read_bytes()
    count, start = struct.unpack_from("<II", raw, 10)
    result = []
    for i in range(count):
        offset, size = struct.unpack_from("<II", raw, 18 + 26 * i + 18)
        result.append(raw[start + offset:start + offset + size].decode("utf-8"))
    return result


def item(plus5: bool, sr: bool) -> bytes:
    # A deliberately foreign usability effect and Slow-immune icon must survive.
    equip = [SplEffect(opcode=319, target=2, power=3, parameter2=454, timing=2)]
    if plus5:
        equip += [SplEffect(opcode=163, target=1, timing=1)]
        equip += [SplEffect(opcode=101, target=1, parameter2=op, timing=2)
                  for op in (16, 40, 109, 126, 154, 157, 158, 175)]
        equip += [SplEffect(opcode=169, target=1, parameter2=icon, timing=2)
                  for icon in (13, 38, 41)]
        equip += [SplEffect(opcode=240, target=1, parameter2=38, timing=2),
                  SplEffect(opcode=337, target=1, parameter1=-1, parameter2=16, timing=2),
                  SplEffect(opcode=267, target=1, parameter1=14023, timing=2),
                  SplEffect(opcode=126, target=1, parameter1=100, parameter2=2, timing=2),
                  SplEffect(opcode=206, target=1, resource="ALT385", timing=2),
                  SplEffect(opcode=206, target=1, resource="SPWI677", timing=2),
                  SplEffect(opcode=206, target=1, resource="SPWI355", timing=2),
                  SplEffect(opcode=206, target=1, resource="NOTHASTE", timing=2)]
    probability = 32 if sr else 33
    slow = SplEffect(opcode=40, target=2, duration=20, probability1=probability)
    hit = [SplEffect(opcode=12, target=2, parameter1=2, parameter2=65536, timing=1), slow,
           dataclasses.replace(slow, opcode=139, parameter1=14000, timing=9, duration=0),
           SplEffect(opcode=177, target=2, resource="DWTROLAC", timing=1)]
    if sr:
        hit.insert(1, dataclasses.replace(slow, opcode=221, parameter1=9, parameter2=20))
    raw = bytearray(0x38)
    raw[0] = 1
    return ItmFile(abilities=(ItmAbility(effects=tuple(hit), raw=bytes(raw)),),
                   global_effects=tuple(equip)).to_bytes()


class Game:
    def __init__(self, root: Path, variant="sr", captures=False):
        self.root = root
        self.override = root / "override"
        self.override.mkdir(parents=True)
        shutil.copy2(ROOT / "setup-chriz-bg-rebalance.tp2", root)
        shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
        sr = variant != "vanilla"
        self.original = {}
        texts = ["Untouched sentinel shared description."]
        for index, name in enumerate(TIERS, start=1):
            original = (CAPTURES / variant / (name + ".ITM")).read_bytes() if captures else item(name == "BLUN30", sr)
            original = bytearray(original)
            struct.pack_into("<I", original, 0x54, index)
            # Keep unrelated names pointing at the sentinel to prove no STRING_SET.
            struct.pack_into("<II", original, 8, 0, 0)
            self.original[name + ".ITM"] = bytes(original)
            texts.append("Original lore remains.\r\nSTATISTICS:\r\n"
                         + ("Equipped abilities:\r\n- Free Action\r\n" if name == "BLUN30" else "")
                         + "Combat abilities:\r\n- 33% chance of slowing target for 20 seconds (No Save)\r\n"
                         + "Damage: 1d6+4, +1 acid damage\r\nWeight: 10")
        self.original["BLUN14A.ITM"] = item(False, sr)  # lower tier untouched
        self.original["FOREIGN.ITM"] = item(True, sr)
        for name, data in self.original.items():
            (self.override / name).write_bytes(data)
        # Canonical Haste is deliberately relocated; the +5 immunity must follow IDS.
        native = make_spl((SplAbility(1, 1, 0, (SplEffect(opcode=16, target=1),)),)).to_bytes()
        revised = make_spl((SplAbility(1, 1, 0, (SplEffect(opcode=176, target=1, parameter1=6),
                                                       SplEffect(opcode=1, target=1, parameter1=1))),)).to_bytes()
        revised = bytearray(revised)
        revised[0x27] = 20  # Actual SR-shaped MSECTYPE.2DA row, not an IDS symbol.
        revised = bytes(revised)
        neutral = make_spl((SplAbility(1, 1, 0, (SplEffect(opcode=101, target=1, parameter2=40),)),)).to_bytes()
        self.bif = _write_key_and_bif(root, (
            ("OH6000", "ARE", b"BG2EE marker"),
            ("SPELL", "IDS", b"2355 WIZARD_HASTE\n2677 WIZARD_IMPROVED_HASTE\n"),
            ("STATS", "IDS", b"1 DUMMY\n"),
            ("SPLSTATE", "IDS", b"1 DUMMY\n"),
            ("ALT385", "SPL", native), ("SPWI355", "SPL", revised if sr else native),
            ("SPWI677", "SPL", revised if sr else native), ("NOTHASTE", "SPL", neutral),
            # Native captured immunities not canonical in this test still have real Haste.
            *((name, "SPL", native) for name in ("SPWI305", "SPWI613", "SPRA301", "SPIN572", "SPIN828")),
        ))
        self.lang_tlk = root / "lang/en_us/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(tlk(texts))
        (root / "dialog.tlk").write_bytes(tlk(texts))
        self.texts = texts
        self.stable = {p: p.read_bytes() for p in (self.bif, root / "chitin.key")}

    def run(self, uninstall=False):
        process = subprocess.run([str(WEIDU), "setup-chriz-bg-rebalance.tp2",
            "--force-uninstall-list" if uninstall else "--force-install-list", "302",
            "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=40)
        return process, process.stdout + process.stderr


class FlailTests(unittest.TestCase):
    def game(self, variant="sr", captures=False):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-flail-")
        self.addCleanup(temporary.cleanup)
        return Game(Path(temporary.name), variant, captures)

    def assert_installed(self, g):
        p, output = g.run()
        self.assertEqual(0, p.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        return {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()}

    def assert_effect_contract(self, g):
        for name, penalty in TIERS.items():
            before = ItmFile.from_bytes(g.original[name + ".ITM"])
            after = read_itm(g.override / (name + ".ITM"))
            old, new = before.abilities[0].effects, after.abilities[0].effects
            self.assertEqual(len(old), len(new))
            self.assertEqual(before.abilities[0].raw[:0x20], after.abilities[0].raw[:0x20])
            self.assertEqual(before.abilities[0].raw[0x22:], after.abilities[0].raw[0x22:])
            for a, b in zip(old, new):
                if a.opcode == 40 or (a.opcode == 139 and a.parameter1 == 14000) or (a.opcode == 221 and a.parameter2 == 20):
                    self.assertEqual(dataclasses.replace(a, save_type=(a.save_type & ~31) | 2, save_bonus=-penalty).to_bytes(), b.to_bytes())
                else:
                    self.assertEqual(a.to_bytes(), b.to_bytes(), f"{name}: unrelated rider {a.opcode}")
            if name != "BLUN30":
                self.assertEqual(before.global_effects, after.global_effects)
            else:
                def haste_blocker(e):
                    return e.target == 1 and (
                        (e.opcode in (101, 337) and e.parameter2 == 16)
                        or (e.opcode in (169, 240) and e.parameter2 == 38)
                        or (e.opcode == 267 and e.parameter1 == 14023)
                        or (e.opcode == 126 and e.parameter1 == 100 and e.parameter2 == 2)
                        or (e.opcode == 206 and e.resource in (
                            "ALT385", "SPWI355", "SPWI677", "SPIN572", "SPRA301", "SPIN828", "SPWI305", "SPWI613")))
                # Every other equipment effect (including all harmful-condition
                # protections, MR and mod-added usability/detection) is exact.
                self.assertEqual(tuple(e for e in before.global_effects if not haste_blocker(e)), after.global_effects)
            text = strings(g.lang_tlk)[after.identified_description]
            self.assertEqual(1, text.count(f"(Save vs. Breath at -{penalty} negates)"))
            self.assertNotIn("No Save", text)
            original_text = g.texts[before.identified_description]
            unowned_lines = lambda value: [line for line in value.splitlines() if not re.search(r"slow|free action", line, re.I)]
            self.assertEqual(unowned_lines(original_text), unowned_lines(text))
            if name == "BLUN30": self.assertIn("Free Action (allows Haste and Improved Haste)", text)
        self.assertEqual(g.texts, strings(g.lang_tlk)[:len(g.texts)])
        self.assertEqual(g.original["BLUN14A.ITM"], (g.override / "BLUN14A.ITM").read_bytes())
        self.assertEqual(g.original["FOREIGN.ITM"], (g.override / "FOREIGN.ITM").read_bytes())
        for path, data in g.stable.items(): self.assertEqual(data, path.read_bytes())

    def test_sr_native_installer_save_gates_slow_haste_removal_and_feedback_only(self):
        g = self.game()
        self.assert_installed(g)
        self.assert_effect_contract(g)

    def test_non_sr_native_installer(self):
        g = self.game("vanilla")
        self.assert_installed(g)
        self.assert_effect_contract(g)

    def test_hit_first_effect_order_is_preserved_and_uninstalls_exactly(self):
        g = self.game()
        for name in TIERS:
            path = g.override / (name + ".ITM")
            data = bytearray(path.read_bytes())
            ability = struct.unpack_from("<I", data, 0x64)[0]
            effect_start = struct.unpack_from("<I", data, 0x6a)[0]
            first_equip, equip_count = struct.unpack_from("<HH", data, 0x6e)
            hit_count, first_hit = struct.unpack_from("<HH", data, ability + 0x1e)
            self.assertEqual(0, first_equip)
            self.assertEqual(equip_count, first_hit)
            equip_bytes = data[effect_start:effect_start + equip_count * 0x30]
            hit_bytes = data[effect_start + first_hit * 0x30:]
            data[effect_start:] = hit_bytes + equip_bytes
            struct.pack_into("<H", data, 0x6e, hit_count)
            struct.pack_into("<H", data, ability + 0x20, 0)
            path.write_bytes(data)
            g.original[path.name] = bytes(data)
        self.assert_installed(g)
        self.assert_effect_contract(g)
        p, output = g.run(uninstall=True)
        self.assertEqual(0, p.returncode, output)
        self.assertEqual(g.original, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})

    def test_unfinished_business_plus5_no_saving_throw_wording_is_replaced(self):
        g = self.game()
        # Exact relevant line shapes from the installed UB 20 description.
        g.texts[-1] = g.texts[-1].replace("- Free Action", "   Free Action ").replace(
            "- 33% chance of slowing target for 20 seconds (No Save)",
            "   33% chance each hit that target will be slowed (no saving throw)")
        g.lang_tlk.write_bytes(tlk(g.texts))
        self.assert_installed(g)
        self.assert_effect_contract(g)
        result = strings(g.lang_tlk)[read_itm(g.override / "BLUN30.ITM").identified_description]
        self.assertNotIn("no saving throw", result.lower())

    def test_unknown_haste_secondary_type_fails_and_rolls_back(self):
        g = self.game()
        (g.override / "SPELL.IDS").write_text("2677 WIZARD_IMPROVED_HASTE\n", encoding="ascii")
        expected = {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()}
        _, output = g.run()
        self.assertIn("cannot resolve the Slow package's Haste-removal secondary type", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})

    def test_ambiguous_description_fails_and_rolls_back(self):
        g = self.game()
        g.texts[-1] += "\nA second Slow effect from an unreviewed overhaul."
        g.lang_tlk.write_bytes(tlk(g.texts))
        expected = {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()}
        _, output = g.run()
        self.assertIn("cannot safely identify the English Slow description line", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})

    def test_uninstall_restores_every_override_byte(self):
        g = self.game()
        self.assert_installed(g)
        p, output = g.run(uninstall=True)
        self.assertEqual(0, p.returncode, output)
        self.assertEqual(g.original, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})
        self.assertEqual(g.texts, strings(g.lang_tlk)[:len(g.texts)])

    def test_already_patched_inputs_are_byte_identical_and_do_not_append_text_again(self):
        g = self.game()
        expected = self.assert_installed(g)
        expected_tlk = g.lang_tlk.read_bytes()
        # Synthetic-only: a second TP2 identity exercises the same production
        # patch functions on their own output without WeiDU silently skipping.
        second = g.root / "setup-flail-second.tp2"
        second.write_text((g.root / "setup-chriz-bg-rebalance.tp2").read_text(encoding="utf-8").replace(
            "weidu_external/backup/chriz-bg-rebalance", "weidu_external/backup/flail-second"), encoding="utf-8")
        p = subprocess.run([str(WEIDU), second.name, "--force-install-list", "302", "--language", "0",
                            "--use-lang", "en_us", "--no-exit-pause", "--quick-log"], cwd=g.root,
                           capture_output=True, text=True, timeout=40)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertIn("SUCCESSFULLY INSTALLED", p.stdout)
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})
        self.assertEqual(expected_tlk, g.lang_tlk.read_bytes())

    def test_unknown_movement_blocker_fails_and_rolls_back(self):
        g = self.game()
        p = g.override / "BLUN30.ITM"
        old = read_itm(p)
        p.write_bytes(dataclasses.replace(old, global_effects=old.global_effects + (SplEffect(opcode=101, parameter2=176),)).to_bytes())
        expected = {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()}
        _, output = g.run()
        self.assertIn("unreviewed movement immunity", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})

    def test_missing_target_skips_before_writing(self):
        g = self.game()
        (g.override / "BLUN30D.ITM").unlink()
        expected = {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()}
        _, output = g.run()
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in g.override.iterdir() if p.is_file()})

    def test_save_extension_bits_remain(self):
        g = self.game()
        p = g.override / "BLUN14.ITM"
        old = read_itm(p)
        effects = tuple(dataclasses.replace(e, save_type=0x1000001) if e.opcode == 40 else e for e in old.abilities[0].effects)
        p.write_bytes(dataclasses.replace(old, abilities=(dataclasses.replace(old.abilities[0], effects=effects),)).to_bytes())
        self.assert_installed(g)
        self.assertEqual(0x1000002, next(e.save_type for e in read_itm(p).abilities[0].effects if e.opcode == 40))

    @unittest.skipUnless((CAPTURES / "vanilla/BLUN30.ITM").exists(), "local vanilla BIF captures absent")
    def test_captured_vanilla_items(self):
        g = self.game("vanilla", captures=True)
        self.assert_installed(g)
        self.assert_effect_contract(g)

    @unittest.skipUnless((CAPTURES / "cebg/BLUN30.ITM").exists(), "local EET/SR/SCS captures absent")
    def test_captured_default_cebg_items(self):
        g = self.game("cebg", captures=True)
        self.assert_installed(g)
        self.assert_effect_contract(g)


if __name__ == "__main__":
    unittest.main()
