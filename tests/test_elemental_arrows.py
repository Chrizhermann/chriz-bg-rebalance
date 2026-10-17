"""Component 130 behavior variants on disposable synthetic EET games only.

The fixtures name the owned records explicitly (header index, effect index),
so the byte oracle below is independent of the installer's own classifier.
Each test runs the public setup with real WeiDU; it never touches a real game.
These are automated installer checks, not in-game verification.
"""
from __future__ import annotations

import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplEffect
from tests.test_cloud_forms import Game, WEIDU
from tests.test_flail_of_ages import strings
from tests.test_release_components import TEXTS, arrow_resources, run_public

SCS_LOG = "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000\n"
ACID, COLD, FIRE = 1, 2, 8
FIRE_TEXT = "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell negates)\nTHAC0: +2"
REPEAT_TP2 = """BACKUP ~cbr_arrow_repeat/backup~
AUTHOR ~synthetic test~
BEGIN ~repeat elemental arrows~
INCLUDE ~chriz-bg-rebalance/lib/elemental_arrows.tpa~
"""


def damage(kind, n, s, *, mode=0, target=2, save=0, **fields):
    return SplEffect(opcode=12, target=target, parameter2=(kind << 16) | mode,
                     dice_number=n, dice_size=s, save_type=save, **fields)


def troll(resource):
    return SplEffect(opcode=177, target=2, parameter1=129, parameter2=4, timing=1,
                     resource=resource)


def header(effects, *, kind=2, hit=0, dmg=0):
    raw = bytearray(56)
    raw[0] = kind
    struct.pack_into("<h", raw, 0x14, hit)
    struct.pack_into("<h", raw, 0x1a, dmg)
    raw[0x16] = 6  # physical dice size: never owned, must survive
    return ItmAbility(raw=bytes(raw), effects=tuple(effects))


def arrow(headers, name, desc):
    raw = bytearray(0x72)
    struct.pack_into("<H", raw, 0x1c, 5)
    raw[0x60] = 2  # enchantment: never owned
    return ItmFile(abilities=tuple(headers), header_raw=bytes(raw),
                   identified_name=name, identified_description=desc).to_bytes()


def offsets(blob, h, k=None):
    abilities, = struct.unpack_from("<I", blob, 0x64)
    effects, = struct.unpack_from("<I", blob, 0x6a)
    a = abilities + h * 56
    if k is None:
        return a
    first, = struct.unpack_from("<H", blob, a + 0x20)
    return effects + (first + k) * 48


def expected(old, new, size, packages, bonus_headers=(), *, name=False, desc=False):
    """Old bytes plus exactly the owned writes; pointers only where allowed."""
    raw = bytearray(old)
    for h, k in packages:
        struct.pack_into("<II", raw, offsets(old, h, k) + 0x1c, 1, size)
    for h in bonus_headers:
        a = offsets(old, h)
        struct.pack_into("<h", raw, a + 0x14, 0)
        struct.pack_into("<h", raw, a + 0x1a, 0)
    if name:
        raw[12:16] = new[12:16]
    if desc:
        raw[84:88] = new[84:88]
    return bytes(raw)


def pointer(blob, offset):
    return struct.unpack_from("<i", blob, offset)[0]


class ElementalArrowVariantTests(unittest.TestCase):
    def game(self, resources, texts=TEXTS):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-elemental-arrows-")
        self.addCleanup(temporary.cleanup)
        g = Game(Path(temporary.name), resources, public=True, texts=texts)
        (g.root / "WeiDU.log").write_text(SCS_LOG)
        return g

    def install(self, g, *, warnings=()):
        code, output = run_public(g, 130)
        self.assertNotIn("NOT INSTALLED", output)
        if warnings:
            self.assertIn("INSTALLED WITH WARNINGS", output)
            for text in warnings:
                self.assertIn(text, output)
        else:
            self.assertEqual(0, code, output)
            self.assertIn("SUCCESSFULLY INSTALLED", output)
        return output

    def uninstall_restores(self, g):
        code, output = run_public(g, 130, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(g.original, g.snapshot())
        self.assertEqual(g.original_texts, strings(g.tlk)[:len(g.original_texts)])

    def reference_others_patched(self, g, after, skip=()):
        for name, size, bonus in (("AROW04", 3, False), ("AROW09", 2, False),
                                  ("AROW08", 2, True), ("AROWKC", 2, True)):
            if name in skip:
                continue
            old, new = g.original[name + ".ITM"], after[name + ".ITM"]
            self.assertEqual(expected(old, new, size, [(0, 0)], [0] if bonus else (),
                                      name=bonus, desc=True), new, name)

    def test_real_shaped_order_helper_first_and_preserved_delivery(self):
        """Live-shaped layout: troll helper before the package, timing 1, saves."""
        resources = arrow_resources()
        resources["AROW08.ITM"] = arrow([header((
            troll("DWTROLFI"),
            damage(FIRE, 1, 6, save=0x01000001, save_bonus=-1, special=0x100,
                   timing=1, probability1=90, probability2=3, parameter1=1, power=4),
        ), hit=2, dmg=2)], 5, 6)
        g = self.game(resources)
        self.install(g)
        after = g.snapshot()
        old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
        self.assertEqual(expected(old, new, 2, [(0, 1)], [0], name=True, desc=True), new)
        fire = ItmFile.from_bytes(new).abilities[0].effects[1]
        self.assertEqual((1, 2, 0x01000001, -1, 0x100, 90, 3, 1, 4),
                         (fire.dice_number, fire.dice_size, fire.save_type, fire.save_bonus,
                          fire.special, fire.probability1, fire.probability2,
                          fire.parameter1, fire.power))
        texts = strings(g.tlk)
        self.assertEqual("Damage: 1d6, +1d2 fire damage (Save vs. Spell negates)\nTHAC0: +0",
                         texts[pointer(new, 0x54)])
        self.assertEqual("Arrow of Fire", texts[pointer(new, 0x0c)])
        self.reference_others_patched(g, after, skip=("AROW08",))
        self.uninstall_restores(g)

    def test_acid_rider_on_fire_arrow_stays_byte_identical(self):
        resources = arrow_resources()
        rider = damage(ACID, 1, 4, timing=1, resource="RIDERX")
        resources["AROW08.ITM"] = arrow([header((
            damage(FIRE, 1, 6, save=1), rider, troll("DWTROLFI")), hit=2, dmg=2)], 5, 6)
        g = self.game(resources)
        self.install(g)
        after = g.snapshot()
        old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
        self.assertEqual(expected(old, new, 2, [(0, 0)], [0], name=True, desc=True), new)
        e = offsets(old, 0, 1)
        self.assertEqual(old[e:e + 48], new[e:e + 48])
        self.assertEqual(rider, ItmFile.from_bytes(new).abilities[0].effects[1])
        self.reference_others_patched(g, after, skip=("AROW08",))
        self.uninstall_restores(g)

    def test_unrelated_extra_headers_keep_type_effects_and_bonuses(self):
        resources = arrow_resources()
        # Fire: an extra melee header and a magic header with an unrelated effect.
        resources["AROW08.ITM"] = arrow([
            header((SplEffect(opcode=139, target=2, parameter1=4321, timing=1),), kind=3,
                   hit=3, dmg=1),
            header((damage(FIRE, 1, 6, save=1), troll("DWTROLFI")), hit=2, dmg=2),
            header((), kind=1, hit=1, dmg=3),
        ], 5, 6)
        # Cold: an unrelated melee header without any effect before the package.
        resources["AROW09.ITM"] = arrow([
            header((damage(FIRE, 2, 4),), kind=1, hit=1, dmg=1),
            header((damage(COLD, 1, 6), troll("DWTROLCO"))),
        ], 3, 4)
        g = self.game(resources)
        self.install(g)
        after = g.snapshot()
        new8, new9 = after["AROW08.ITM"], after["AROW09.ITM"]
        self.assertEqual(expected(g.original["AROW08.ITM"], new8, 2, [(1, 0)], [1],
                                  name=True, desc=True), new8)
        self.assertEqual(expected(g.original["AROW09.ITM"], new9, 2, [(1, 0)], desc=True), new9)
        item = ItmFile.from_bytes(new8)
        self.assertEqual([3, 2, 1], [a.raw[0] for a in item.abilities])
        self.assertEqual((3, 1), struct.unpack_from("<h4xh", item.abilities[0].raw, 0x14))
        self.assertEqual((1, 3), struct.unpack_from("<h4xh", item.abilities[2].raw, 0x14))
        self.reference_others_patched(g, after, skip=("AROW08", "AROW09"))
        self.uninstall_restores(g)

    def test_same_element_records_with_other_delivery_are_not_owned(self):
        resources = arrow_resources()
        # Percent-mode cold, caster-targeted cold and magic-cold (another type).
        foreign = (damage(COLD, 3, 8, mode=3), damage(COLD, 2, 6, target=1),
                   damage(1024, 2, 6))
        resources["AROW09.ITM"] = arrow([header((
            foreign[0], troll("DWTROLCO"), foreign[1], damage(COLD, 1, 6), foreign[2]))], 3, 4)
        g = self.game(resources)
        self.install(g)
        after = g.snapshot()
        old, new = g.original["AROW09.ITM"], after["AROW09.ITM"]
        self.assertEqual(expected(old, new, 2, [(0, 3)], desc=True), new)
        effects = ItmFile.from_bytes(new).abilities[0].effects
        self.assertEqual(foreign, (effects[0], effects[2], effects[4]))
        self.reference_others_patched(g, after, skip=("AROW09",))
        self.uninstall_restores(g)

    def test_package_on_each_of_several_projectile_headers(self):
        resources = arrow_resources()
        resources["AROW04.ITM"] = arrow([
            header((damage(ACID, 2, 6), troll("DWTROLAC")), hit=1, dmg=1),
            header((troll("DWTROLAC"), damage(ACID, 2, 6)), hit=1, dmg=1),
        ], 1, 2)
        g = self.game(resources)
        self.install(g)
        after = g.snapshot()
        old, new = g.original["AROW04.ITM"], after["AROW04.ITM"]
        # Acid keeps its bonuses: only fire owns them.
        self.assertEqual(expected(old, new, 3, [(0, 0), (1, 1)], desc=True), new)
        self.assertEqual("Damage: 1d6+1, +1d3 acid damage\nTHAC0: +1",
                         strings(g.tlk)[pointer(new, 0x54)])
        self.uninstall_restores(g)

    def test_two_packages_in_one_header_fail_without_writing(self):
        resources = arrow_resources()
        resources["AROW08.ITM"] = arrow([
            header((troll("DWTROLFI"),)),
            header((damage(FIRE, 1, 6), troll("DWTROLFI"), damage(FIRE, 1, 4)), hit=2, dmg=2),
        ], 5, 6)
        g = self.game(resources)
        code, output = run_public(g, 130)
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn("AROW08.ITM extended header 1 (0-based) has 2 fire damage records", output)
        self.assertIn("would multiply the damage", output)
        self.assertEqual(g.original, g.snapshot())
        self.assertEqual(g.original_tlk, g.tlk.read_bytes())

    def test_malformed_last_item_fails_before_any_write(self):
        resources = arrow_resources()
        raw = bytearray(resources["AROWKC.ITM"])
        a = offsets(raw, 0)
        struct.pack_into("<H", raw, a + 0x1e, 9)  # effect slice runs past the file
        resources["AROWKC.ITM"] = bytes(raw)
        g = self.game(resources)
        code, output = run_public(g, 130)
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn("AROWKC.ITM extended header 0 (0-based) has an effect slice outside", output)
        self.assertEqual(g.original, g.snapshot())
        self.assertEqual(g.original_tlk, g.tlk.read_bytes())

    def test_item_without_package_warns_and_others_install(self):
        for label, headers in (
            ("set-damage mode", [header((damage(COLD, 1, 6, mode=1), troll("DWTROLCO")))]),
            ("caster target", [header((damage(COLD, 1, 6, target=1),))]),
            ("magic cold type", [header((damage(1024, 1, 6),))]),
            ("no headers", []),
        ):
            with self.subTest(label):
                resources = arrow_resources()
                resources["AROW09.ITM"] = arrow(headers, 3, 4)
                g = self.game(resources)
                self.install(g, warnings=("AROW09.ITM has no cold damage package",
                                          "this item was left unchanged"))
                after = g.snapshot()
                self.assertEqual(g.original["AROW09.ITM"], after["AROW09.ITM"])
                self.reference_others_patched(g, after, skip=("AROW09",))
                self.uninstall_restores(g)

    def test_description_variants_never_publish_false_text(self):
        extra = TEXTS + [
            "Schaden: 1W6+2, +1W6 Feuerschaden\nETW0: +2",                       # 7
            "Damage: 1d6+2, +1d6 fire damage\nTHAC0: +3",                         # 8
            "Damage: 1d6+2, +1d8 fire damage\nTHAC0: +2",                         # 9
            "Damage: 1d6, +1d2 fire damage (Save vs. Spell for none)",            # 10
            "Arrow of Fire +3",                                                   # 11
        ]
        cases = (
            # label, AROW08 headers, name, desc, warning, desc updated, new text
            ("other language", [header((damage(FIRE, 1, 6),), hit=2, dmg=2)], 5, 7,
             "different wording or language", False, None),
            ("other THAC0 value", [header((damage(FIRE, 1, 6),), hit=2, dmg=2)], 5, 8,
             "matches neither the old nor the new bonus", False, None),
            ("other fire dice", [header((damage(FIRE, 1, 6),), hit=2, dmg=2)], 5, 9,
             "match neither the old nor the new package", False, None),
            ("shared bonus on an unrelated header",
             [header((damage(FIRE, 1, 6),), hit=2, dmg=2), header((), kind=1, hit=2)], 5, 6,
             "cannot be attributed", False, None),
            ("already-correct text without THAC0, breath save with EE flag",
             [header((troll("DWTROLFI"), damage(FIRE, 1, 6, save=0x01000002)), hit=2, dmg=2)],
             5, 10, None, True, "Damage: 1d6, +1d2 fire damage (Save vs. Breath for none)"),
        )
        for label, headers, name, desc, warning, updated, text in cases:
            with self.subTest(label):
                resources = arrow_resources()
                resources["AROW08.ITM"] = arrow(headers, name, desc)
                g = self.game(resources, extra)
                output = self.install(g, warnings=(warning,) if warning else ())
                after = g.snapshot()
                old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
                pkg = next(k for k, fx in enumerate(headers[0].effects) if fx.opcode == 12)
                self.assertEqual(expected(old, new, 2, [(0, pkg)], [0], name=True, desc=updated),
                                 new)
                if updated:
                    self.assertEqual(text, strings(g.tlk)[pointer(new, 0x54)])
                else:
                    self.assertIn("AROW08.ITM description was not updated", output)
                    self.assertEqual(desc, pointer(new, 0x54))
                # The name pointer may only point at the stripped original name.
                self.assertEqual("Arrow of Fire", strings(g.tlk)[pointer(new, 0x0c)])
                self.reference_others_patched(g, after, skip=("AROW08",))
                self.uninstall_restores(g)

        with self.subTest("name suffix states another value"):
            resources = arrow_resources()
            resources["AROW08.ITM"] = arrow([header((damage(FIRE, 1, 6),), hit=2, dmg=2)], 11, 6)
            g = self.game(resources, extra)
            self.install(g, warnings=("AROW08.ITM name was not updated",))
            new = g.snapshot()["AROW08.ITM"]
            self.assertEqual(expected(g.original["AROW08.ITM"], new, 2, [(0, 0)], [0], desc=True),
                             new)
            self.assertEqual(11, pointer(new, 0x0c))
            self.uninstall_restores(g)

        with self.subTest("package headers disagree on the removed bonus"):
            resources = arrow_resources()
            resources["AROW08.ITM"] = arrow([header((damage(FIRE, 1, 6),), hit=2, dmg=2),
                                             header((damage(FIRE, 1, 6),), hit=1, dmg=1)], 5, 6)
            g = self.game(resources, extra)
            self.install(g, warnings=("differ between extended headers",
                                      "AROW08.ITM name was not updated"))
            new = g.snapshot()["AROW08.ITM"]
            self.assertEqual(expected(g.original["AROW08.ITM"], new, 2, [(0, 0), (1, 0)], [0, 1]),
                             new)
            self.uninstall_restores(g)

    def test_repeat_application_is_byte_identical(self):
        resources = arrow_resources()
        resources["AROW08.ITM"] = arrow([
            header((SplEffect(opcode=139, target=2, parameter1=4321),), kind=3, hit=3),
            header((troll("DWTROLFI"), damage(FIRE, 1, 6, save=1),
                    damage(ACID, 1, 4)), hit=2, dmg=2),
        ], 5, 6)
        resources["AROW09.ITM"] = arrow([header((damage(COLD, 1, 6, mode=1),))], 3, 4)
        g = self.game(resources)
        self.install(g, warnings=("AROW09.ITM has no cold damage package",))
        first, first_tlk = g.snapshot(), g.tlk.read_bytes()
        folder = g.root / "cbr_arrow_repeat"
        folder.mkdir()
        (folder / "cbr_arrow_repeat.tp2").write_text(REPEAT_TP2)
        p = subprocess.run([str(WEIDU), "cbr_arrow_repeat/cbr_arrow_repeat.tp2",
                            "--force-install-list", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        output = p.stdout + p.stderr
        self.assertNotIn("NOT INSTALLED", output)
        self.assertIn("AROW09.ITM has no cold damage package", output)
        self.assertNotIn("was not updated", output)
        self.assertEqual(first, g.snapshot())
        self.assertEqual(first_tlk, g.tlk.read_bytes())
        p = subprocess.run([str(WEIDU), "cbr_arrow_repeat/cbr_arrow_repeat.tp2",
                            "--force-uninstall-list", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertEqual(first, g.snapshot())
        self.uninstall_restores(g)


if __name__ == "__main__":
    unittest.main()
