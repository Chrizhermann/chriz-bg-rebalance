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
from tests.test_flail_of_ages import strings, tlk
from tests.test_release_components import TEXTS, arrow_resources, run_public

SCS_LOG = "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000\n"
ACID, COLD, FIRE = 1, 2, 8
FIRE_TEXT = "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell negates)\nTHAC0: +2"
REPEAT_TP2 = """BACKUP ~cbr_arrow_repeat/backup~
AUTHOR ~synthetic test~
BEGIN ~repeat elemental arrows~
INCLUDE ~chriz-bg-rebalance/lib/elemental_arrows.tpa~
"""
# A later mod patching the arrow with WeiDU's own item-effect functions.
LATER_TP2 = """BACKUP ~cbr_arrow_later/backup~
AUTHOR ~synthetic test~
BEGIN ~later item-effect patches~
COPY_EXISTING ~AROW08.ITM~ ~override~
  LPF ADD_ITEM_EFFECT INT_VAR type = 3 opcode = 139 target = 1 timing = 1 parameter1 = 7 END
  LPF ADD_ITEM_EQEFFECT INT_VAR opcode = 1 target = 1 timing = 2 parameter1 = 1 END
  LPF ADD_ITEM_EFFECT INT_VAR type = 2 opcode = 139 target = 2 timing = 1 parameter1 = 8 END
"""


def damage(kind, n, s, *, mode=0, target=2, save=0, **fields):
    return SplEffect(opcode=12, target=target, parameter2=(kind << 16) | mode,
                     dice_number=n, dice_size=s, save_type=save, **fields)


def troll(resource):
    return SplEffect(opcode=177, target=2, parameter1=129, parameter2=4, timing=1,
                     resource=resource)


def header(effects, *, kind=2, launcher=None, hit=0, dmg=0):
    """ITM extended header; ranged headers default to the bow launcher (byte
    0x10 = 1), as on the reference AROW04/08/09/KC."""
    raw = bytearray(56)
    raw[0] = kind
    raw[0x10] = (1 if kind == 2 else 0) if launcher is None else launcher
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


def point(blob, h, first, count):
    """Repoint header h at an existing effect slice (shared records)."""
    raw = bytearray(blob)
    struct.pack_into("<HH", raw, offsets(raw, h) + 0x1e, count, first)
    return bytes(raw)


def equip(blob, first, count):
    raw = bytearray(blob)
    struct.pack_into("<HH", raw, 0x6e, first, count)
    return bytes(raw)


def copied(old, new, size, copies, in_place=(), bonus_headers=(), *, name=True, desc=True):
    """Copy-on-write oracle: every header in `copies` (h, package index in its
    slice), in header order, gets its whole old slice appended as a private
    copy with the package dice patched; nothing else moves or changes."""
    raw = bytearray(expected(old, new, size, in_place, bonus_headers, name=name, desc=desc))
    effects, = struct.unpack_from("<I", old, 0x6a)
    for h, k in copies:
        a = offsets(old, h)
        count, first = struct.unpack_from("<HH", old, a + 0x1e)
        total = (len(raw) - effects) // 48
        block = bytearray(old[effects + first * 48:effects + (first + count) * 48])
        struct.pack_into("<II", block, k * 48 + 0x1c, 1, size)
        raw += block
        struct.pack_into("<H", raw, a + 0x20, total)
    return bytes(raw)


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

    def test_only_bow_fired_ranged_headers_are_owned(self):
        """Review finding A: a magical activation dealing the element is not the
        arrow's hit. Only attack type 2 (ranged) with launcher 1 (bow) is owned;
        activations, melee and ranged headers without the bow launcher keep
        every byte, in any order and however many there are."""
        activation = header((damage(FIRE, 3, 6, save=1),
                             SplEffect(opcode=139, target=2, parameter1=4321)),
                            kind=3, hit=1, dmg=3)
        hit = header((damage(FIRE, 1, 6, save=1), troll("DWTROLFI")), hit=2, dmg=2)
        melee = header((damage(FIRE, 1, 6),), kind=1, hit=1, dmg=1)
        thrown = header((damage(FIRE, 1, 6),), kind=2, launcher=0, hit=3)
        crossbow = header((damage(FIRE, 1, 6),), kind=2, launcher=2, dmg=3)
        for label, headers, owned in (
            ("activation after the hit header", [hit, activation], 0),
            ("activation before the hit header", [activation, hit], 1),
            ("several foreign headers around the hit header",
             [melee, activation, hit, thrown, crossbow], 2),
            ("second bow-fired header without the package",
             [hit, header((troll("DWTROLFI"),), hit=1, dmg=1), activation], 0),
        ):
            with self.subTest(label):
                resources = arrow_resources()
                resources["AROW08.ITM"] = arrow(headers, 5, 6)
                g = self.game(resources)
                self.install(g)
                after = g.snapshot()
                old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
                self.assertEqual(expected(old, new, 2, [(owned, 0)], [owned],
                                          name=True, desc=True), new)
                before, item = ItmFile.from_bytes(old), ItmFile.from_bytes(new)
                for h, ability in enumerate(item.abilities):
                    if h != owned:
                        self.assertEqual(before.abilities[h].raw, ability.raw, h)
                        self.assertEqual(before.abilities[h].effects, ability.effects, h)
                self.assertEqual("Damage: 1d6, +1d2 fire damage (Save vs. Spell negates)\n"
                                 "THAC0: +0", strings(g.tlk)[pointer(new, 0x54)])
                self.reference_others_patched(g, after, skip=("AROW08",))
                self.uninstall_restores(g)

    def test_package_only_on_a_foreign_header_warns_and_keeps_the_item(self):
        resources = arrow_resources()
        resources["AROW09.ITM"] = arrow([
            header((troll("DWTROLCO"),)),
            header((damage(COLD, 1, 6),), kind=3),
        ], 3, 4)
        g = self.game(resources)
        self.install(g, warnings=(
            "AROW09.ITM has no cold damage package",
            "bow-fired extended header (attack type ranged, launcher bow)",
            "1 such record(s) on other extended headers were not changed",
            "this item was left unchanged"))
        after = g.snapshot()
        self.assertEqual(g.original["AROW09.ITM"], after["AROW09.ITM"])
        self.reference_others_patched(g, after, skip=("AROW09",))
        self.uninstall_restores(g)

    def described(self, item, headers, desc, *, warnings=(), save=None):
        """Install with one custom description for `item`; return the new text
        (None when the description pointer was kept) and the install output."""
        resources = arrow_resources()
        name = 1 if item == "AROW04" else 5 if item in ("AROW08", "AROWKC") else 3
        resources[item + ".ITM"] = arrow(headers, name, len(TEXTS))
        g = self.game(resources, TEXTS + [desc])
        output = self.install(g, warnings=warnings)
        after = g.snapshot()
        new = after[item + ".ITM"]
        kept = pointer(new, 0x54) == len(TEXTS)
        if kept:
            self.assertIn(item + ".ITM description was not updated", output)
        self.reference_others_patched(g, after, skip=(item,))
        self.uninstall_restores(g)
        return (None if kept else strings(g.tlk)[pointer(new, 0x54)]), output

    def test_description_keeps_other_riders_text(self):
        """Review finding B: only the weapon-damage bonus, the fire clause and
        the fire clause's own save are owned. Other riders' "+K" survive."""
        fire_acid = [header((damage(FIRE, 1, 6, save=1),
                             damage(ACID, 1, 4, parameter1=2)), hit=2, dmg=2)]
        for label, desc, text in (
            ("added rider", "Damage: 1d6+2, +1d6 fire damage, +1d4+2 acid damage\nTHAC0: +2",
             "Damage: 1d6, +1d2 fire damage, +1d4+2 acid damage\nTHAC0: +0"),
            ("rider written without a plus",
             "Damage: 1d6+2, +1d6 fire damage, plus 1d4+2 Acid Damage\nTHAC0: +2",
             "Damage: 1d6, +1d2 fire damage, plus 1d4+2 Acid Damage\nTHAC0: +0"),
            ("weapon damage named piercing",
             "Damage: 1d6+2 piercing damage, +1d6 fire damage, +1d4+2 acid damage",
             "Damage: 1d6 piercing damage, +1d2 fire damage, +1d4+2 acid damage"),
        ):
            with self.subTest(label):
                self.assertEqual(text, self.described("AROW08", fire_acid, desc)[0])

    def test_breath_save_text_changes_only_the_fire_clause(self):
        kobold = [header((troll("DWTROLFI"), damage(FIRE, 1, 6, save=2)), hit=2, dmg=2)]
        with self.subTest("save attached to the fire clause; another Spell save"):
            text, _ = self.described("AROWKC", kobold,
                                     "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell for none)\n"
                                     "Special: Save vs. Spell or be dazed\nTHAC0: +2")
            self.assertEqual("Damage: 1d6, +1d2 fire damage (Save vs. Breath for none)\n"
                             "Special: Save vs. Spell or be dazed\nTHAC0: +0", text)
        with self.subTest("unattributable Spell save is kept with a warning"):
            text, _ = self.described(
                "AROWKC", kobold,
                "Damage: 1d6+2, +1d6 fire damage\nSave vs. Spell for no fire damage\nTHAC0: +2",
                warnings=("AROWKC.ITM description states \"Save vs. Spell\" outside its fire "
                          "damage clause",))
            self.assertEqual("Damage: 1d6, +1d2 fire damage\nSave vs. Spell for no fire damage\n"
                             "THAC0: +0", text)
        with self.subTest("a spell save on a spell-save package is never touched"):
            spell = [header((damage(FIRE, 1, 6, save=1),), hit=2, dmg=2)]
            text, _ = self.described("AROW08", spell,
                                     "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell for none)")
            self.assertEqual("Damage: 1d6, +1d2 fire damage (Save vs. Spell for none)", text)

    def test_unattributable_owned_claims_keep_the_text(self):
        fire = [header((damage(FIRE, 1, 6),), hit=2, dmg=2)]
        cold = [header((damage(COLD, 1, 6),))]
        for label, item, headers, desc in (
            ("two fire clauses", "AROW08", fire,
             "Damage: 1d6+2, +1d6 fire damage\nWhen charged: +1d6 fire damage\nTHAC0: +2"),
            ("two cold clauses", "AROW09", cold,
             "Damage: 1d6, +1d6 cold damage\nVs. fire creatures: +1d6 cold damage"),
            ("two THAC0 claims", "AROW08", fire,
             "Damage: 1d6+2, +1d6 fire damage\nTHAC0: +2\nOff-hand THAC0: +2"),
            ("two weapon-damage bonuses", "AROW08", fire,
             "Damage: 1d6+2, +1d6 fire damage\nWith a long bow: 1d6+2\nTHAC0: +2"),
        ):
            with self.subTest(label):
                text, _ = self.described(item, headers, desc, warnings=(
                    "description was not updated", "cannot be identified"))
                self.assertIsNone(text)

    def test_female_text_is_rewritten_from_its_own_string(self):
        """SAY writes both dialog.tlk and dialogf.tlk. Each gendered string is
        rewritten on its own, or neither is changed."""
        male = TEXTS[6]
        for label, female_name, female_desc, warning, new_name, new_desc in (
            ("gendered variant", "Feuerpfeil der Hexe +2",
             "Her arrow.\nDamage: 1d6+2, +1d6 fire damage (Save vs. Spell negates)\nTHAC0: +2",
             None, "Feuerpfeil der Hexe",
             "Her arrow.\nDamage: 1d6, +1d2 fire damage (Save vs. Spell negates)\nTHAC0: +0"),
            ("female wording not recognized", "Arrow of Fire +2",
             "Schaden: 1W6+2, +1W6 Feuerschaden\nETW0: +2",
             "female (dialogF.tlk) text: no \"+NdM fire damage\" text", "Arrow of Fire", None),
        ):
            with self.subTest(label):
                resources = arrow_resources()
                g = self.game(resources)
                female = g.root / "lang/en_us/dialogf.tlk"
                female_texts = list(TEXTS)
                female_texts[5], female_texts[6] = female_name, female_desc
                female.write_bytes(tlk(female_texts))
                self.install(g, warnings=(warning,) if warning else ())
                after = g.snapshot()
                new = after["AROW08.ITM"]
                males, females = strings(g.tlk), strings(female)
                self.assertEqual(female_texts, females[:len(female_texts)])
                self.assertEqual(("Arrow of Fire", new_name),
                                 (males[pointer(new, 0x0c)], females[pointer(new, 0x0c)]))
                if new_desc is None:
                    self.assertEqual(6, pointer(new, 0x54))
                else:
                    self.assertEqual(
                        ("Damage: 1d6, +1d2 fire damage (Save vs. Spell negates)\nTHAC0: +0",
                         new_desc), (males[pointer(new, 0x54)], females[pointer(new, 0x54)]))
                self.assertEqual(male, males[6])
                self.reference_others_patched(g, after, skip=("AROW08",) if new_desc is None else ())
                self.uninstall_restores(g)
                self.assertEqual(female_texts, strings(female)[:len(female_texts)])

    def rerun(self, g):
        """Apply the library again in an independent tail transaction."""
        folder = g.root / "cbr_arrow_repeat"
        folder.mkdir()
        (folder / "cbr_arrow_repeat.tp2").write_text(REPEAT_TP2)
        p = subprocess.run([str(WEIDU), "cbr_arrow_repeat/cbr_arrow_repeat.tp2",
                            "--force-install-list", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        output = p.stdout + p.stderr
        self.assertNotIn("NOT INSTALLED", output)
        p = subprocess.run([str(WEIDU), "cbr_arrow_repeat/cbr_arrow_repeat.tp2",
                            "--force-uninstall-list", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        return output

    def test_shared_package_records_are_copied_on_write(self):
        """Re-review of finding A: a foreign slice that references the owned
        package record keeps the original; the owned header gets a private
        copy of its whole slice appended to the effect table."""
        bow = header((damage(FIRE, 1, 6, save=1), troll("DWTROLFI")), hit=2, dmg=2)
        bare_bow = header((), hit=2, dmg=2)
        activation = header((), kind=3, hit=1, dmg=3)
        base = arrow([bow, activation], 5, 6)
        cases = (
            # label, AROW08 bytes, copies (header, package index in its slice), in place
            ("activation shares the whole bow slice", point(base, 1, 0, 2), [(0, 0)], []),
            ("activation shares only the package record", point(base, 1, 0, 1), [(0, 0)], []),
            ("activation listed first", point(arrow([activation, bow], 5, 6), 0, 0, 1),
             [(1, 0)], []),
            ("equipped effects share the package", equip(base, 0, 1), [(0, 0)], []),
            ("two bow headers share one slice, nothing foreign",
             point(arrow([bow, bare_bow, activation], 5, 6), 1, 0, 2), [], [(0, 0), (1, 0)]),
            ("two bow headers and an activation share one slice",
             point(point(arrow([bow, bare_bow, activation], 5, 6), 1, 0, 2), 2, 0, 1),
             [(0, 0), (1, 0)], []),
            ("helper is shared, the package is not", point(base, 1, 1, 1), [], [(0, 0)]),
        )
        for label, blob, copies, in_place in cases:
            with self.subTest(label):
                resources = arrow_resources()
                resources["AROW08.ITM"] = blob
                g = self.game(resources)
                self.install(g)
                after = g.snapshot()
                old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
                bows = sorted({h for h, _ in copies + in_place})
                self.assertEqual(copied(old, new, 2, copies, in_place, bows), new)
                # Every foreign slice still reads the original records.
                before, item = ItmFile.from_bytes(old), ItmFile.from_bytes(new)
                for h, ability in enumerate(item.abilities):
                    if h not in bows:
                        self.assertEqual(before.abilities[h].effects, ability.effects, h)
                    else:
                        fire = ability.effects[0]
                        self.assertEqual((1, 2, 1), (fire.dice_number, fire.dice_size,
                                                     fire.save_type), h)
                self.assertEqual(before.global_effects, item.global_effects)
                self.assertEqual("Damage: 1d6, +1d2 fire damage (Save vs. Spell negates)\n"
                                 "THAC0: +0", strings(g.tlk)[pointer(new, 0x54)])
                self.reference_others_patched(g, after, skip=("AROW08",))
                tlk_before = g.tlk.read_bytes()
                output = self.rerun(g)
                self.assertNotIn("was not updated", output)
                self.assertNotIn("cannot be separated", output)
                self.assertEqual(after, g.snapshot())
                self.assertEqual(tlk_before, g.tlk.read_bytes())
                self.uninstall_restores(g)

    def test_copied_records_stay_patchable_by_later_mods(self):
        """The private copy ends the effect table. WeiDU's ADD_ITEM_EFFECT and
        ADD_ITEM_EQEFFECT in a later mod shift every slice by its index, so the
        bow header keeps its patched copy and the activation its original."""
        bow = header((damage(FIRE, 1, 6, save=1), troll("DWTROLFI")), hit=2, dmg=2)
        activation = header((), kind=3, hit=1, dmg=3)
        for label, blob, h_bow in (
            ("bow header first", point(arrow([bow, activation], 5, 6), 1, 0, 1), 0),
            ("activation listed first", point(arrow([activation, bow], 5, 6), 0, 0, 1), 1),
        ):
            with self.subTest(label):
                resources = arrow_resources()
                resources["AROW08.ITM"] = blob
                g = self.game(resources)
                self.install(g)
                after = g.snapshot()
                patched = ItmFile.from_bytes(after["AROW08.ITM"])
                foreign = ItmFile.from_bytes(blob).abilities[1 - h_bow].effects
                folder = g.root / "cbr_arrow_later"
                folder.mkdir()
                (folder / "cbr_arrow_later.tp2").write_text(LATER_TP2)
                command = [str(WEIDU), "cbr_arrow_later/cbr_arrow_later.tp2", "--use-lang",
                           "en_us", "--no-exit-pause", "--quick-log"]
                p = subprocess.run(command + ["--force-install-list", "0"], cwd=g.root,
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(0, p.returncode, p.stdout + p.stderr)
                later = ItmFile.from_bytes((g.override / "AROW08.ITM").read_bytes())
                fire, helper = patched.abilities[h_bow].effects
                self.assertEqual((1, 2), (fire.dice_number, fire.dice_size))
                self.assertEqual((fire, helper),
                                 later.abilities[h_bow].effects[:2])
                self.assertEqual((139, 8), (later.abilities[h_bow].effects[2].opcode,
                                            later.abilities[h_bow].effects[2].parameter1))
                self.assertEqual(foreign, later.abilities[1 - h_bow].effects[:1])
                self.assertEqual((1, 6), (foreign[0].dice_number, foreign[0].dice_size))
                self.assertEqual((139, 7), (later.abilities[1 - h_bow].effects[1].opcode,
                                            later.abilities[1 - h_bow].effects[1].parameter1))
                self.assertEqual([(1, 1)], [(e.opcode, e.parameter1)
                                            for e in later.global_effects])
                p = subprocess.run(command + ["--force-uninstall-list", "0"], cwd=g.root,
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(0, p.returncode, p.stdout + p.stderr)
                self.assertEqual(after, g.snapshot())
                self.uninstall_restores(g)

    def test_shared_records_without_a_trailing_effect_table_warn_and_keep_the_item(self):
        bow = header((damage(FIRE, 1, 6, save=1), troll("DWTROLFI")), hit=2, dmg=2)
        activation = header((), kind=3)
        shared = point(arrow([bow, activation], 5, 6), 1, 0, 1) + b"TRAILER"
        unshared = arrow([bow, activation], 5, 6) + b"TRAILER"
        with self.subTest("shared package"):
            resources = arrow_resources()
            resources["AROW08.ITM"] = shared
            g = self.game(resources)
            self.install(g, warnings=(
                "AROW08.ITM extended header 0 (0-based) shares its fire damage record",
                "cannot be separated because the effect table is not at the end of the file",
                "this item was left unchanged"))
            after = g.snapshot()
            self.assertEqual(g.original["AROW08.ITM"], after["AROW08.ITM"])
            self.reference_others_patched(g, after, skip=("AROW08",))
            self.uninstall_restores(g)
        with self.subTest("copies would pass the 16-bit first-effect index"):
            blob = point(arrow([bow, activation], 5, 6), 1, 0, 1)
            effects, = struct.unpack_from("<I", blob, 0x6a)
            blob += bytes(48 * (0xffff - (len(blob) - effects) // 48))  # unreferenced
            resources = arrow_resources()
            resources["AROW08.ITM"] = blob
            g = self.game(resources)
            self.install(g, warnings=(
                "cannot be separated because the copies would exceed the 16-bit first-effect index",
                "this item was left unchanged"))
            self.assertEqual(g.original["AROW08.ITM"], g.snapshot()["AROW08.ITM"])
            self.uninstall_restores(g)
        with self.subTest("nothing shared: patched in place despite the trailer"):
            resources = arrow_resources()
            resources["AROW08.ITM"] = unshared
            g = self.game(resources)
            self.install(g)
            after = g.snapshot()
            old, new = g.original["AROW08.ITM"], after["AROW08.ITM"]
            self.assertEqual(expected(old, new, 2, [(0, 0)], [0], name=True, desc=True), new)
            self.uninstall_restores(g)

    def test_repeat_application_is_byte_identical(self):
        resources = arrow_resources()
        resources["AROW08.ITM"] = arrow([
            header((SplEffect(opcode=139, target=2, parameter1=4321),), kind=3, hit=3),
            header((damage(FIRE, 3, 6, save=1),), kind=3),
            header((troll("DWTROLFI"), damage(FIRE, 1, 6, save=1),
                    damage(ACID, 1, 4, parameter1=2)), hit=2, dmg=2),
        ], 5, 7)
        resources["AROW09.ITM"] = arrow([header((damage(COLD, 1, 6, mode=1),))], 3, 4)
        desc = "Damage: 1d6+2, +1d6 fire damage (Save vs. Spell negates), +1d4+2 acid damage"
        g = self.game(resources, TEXTS + [desc + "\nTHAC0: +2"])
        female = g.root / "lang/en_us/dialogf.tlk"
        female.write_bytes(tlk(TEXTS + ["Hers. " + desc]))
        self.install(g, warnings=("AROW09.ITM has no cold damage package",))
        first, first_tlk, first_female = g.snapshot(), g.tlk.read_bytes(), female.read_bytes()
        new = first["AROW08.ITM"]
        self.assertEqual(expected(g.original["AROW08.ITM"], new, 2, [(2, 1)], [2],
                                  name=True, desc=True), new)
        text = "Damage: 1d6, +1d2 fire damage (Save vs. Spell negates), +1d4+2 acid damage"
        self.assertEqual((text + "\nTHAC0: +0", "Hers. " + text),
                         (strings(g.tlk)[pointer(new, 0x54)], strings(female)[pointer(new, 0x54)]))
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
        self.assertEqual(first_female, female.read_bytes())
        p = subprocess.run([str(WEIDU), "cbr_arrow_repeat/cbr_arrow_repeat.tp2",
                            "--force-uninstall-list", "0", "--use-lang", "en_us",
                            "--no-exit-pause", "--quick-log"],
                           cwd=g.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertEqual(first, g.snapshot())
        self.uninstall_restores(g)


if __name__ == "__main__":
    unittest.main()
