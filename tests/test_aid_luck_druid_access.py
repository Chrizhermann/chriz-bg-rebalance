"""Aid (340), Luck (341) and Chaotic Commands for druids (350).

Real WeiDU on disposable synthetic games only. The fixtures mirror the shapes
seen in an installed EET game (native and Spell Revisions Aid/Luck, Bardic
Wonders' byte copy of Aid, the Luck scroll, SR's druid exclusion) plus layouts
the components must also handle: relocated SPELL.IDS slots, shared effect
slices, casting effects, an opcode-22 Luck bonus and unrecognized text.
Descriptions are short stand-ins that contain only the phrases the installer
rewrites.
"""
from __future__ import annotations

import dataclasses
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, make_spl_header
from tests.test_cloud_forms import Game, WEIDU
from tests.test_flail_of_ages import strings

SR_AID = ("Aid\nDuration: 1 turn/level\n\nThe recipient of this spell gains a +1 bonus to attack "
          "rolls, damage rolls, and saving throws, plus 1d8 additional hit points +1 per level of "
          "the caster (up to a maximum of 1d8+10). Recasting it is not cumulative.")
SR_AID_NEW = ("Aid\nDuration: 1 turn/level\n\nThe recipient of this spell gains 1d8 additional hit "
              "points +1 per level of the caster (up to a maximum of 1d8+10). Recasting it is not "
              "cumulative.")
NATIVE_AID = ("Aid\nDuration: 1 round + 1 round/level\n\nThe recipient of this spell gains the "
              "benefits of a Bless spell (+1 to attack rolls and Saving Throws) and a special bonus "
              "of 1d8 additional Hit Points for the duration of the spell.")
NATIVE_AID_NEW = ("Aid\nDuration: 1 turn/level\n\nThe recipient of this spell gains a special bonus "
                  "of 1d8 additional Hit Points +1 per level of the caster (up to a maximum of "
                  "1d8+10) for the duration of the spell.")
SR_LUCK = ("Luck\nDuration: 5 turns\n\nThe recipient is lucky in everything for the next hour. "
           "It receives a 5% or +1 bonus to its actions.")
SR_LUCK_NEW = ("Luck\nDuration: 15 rounds\n\nThe recipient is lucky in everything for the next 15 "
               "rounds. It receives a 5% or +1 bonus to its actions.")
NATIVE_LUCK = ("Luck\nDuration: 3 rounds\n\nThe recipient gains extraordinary luck for the next 3 "
               "rounds, receiving +5% to all thieving skills.")
NATIVE_LUCK_NEW = ("Luck\nDuration: 15 rounds\n\nThe recipient gains extraordinary luck for the next "
                   "15 rounds, receiving +5% to all thieving skills.")
GERMAN = "Hilfe\nDauer: 1 Runde/Stufe\n\nDer Empfaenger erhaelt 1W8 Trefferpunkte."
TEXTS = ["Unrelated shared text.", SR_AID, NATIVE_AID, SR_LUCK, NATIVE_LUCK, GERMAN]
SR_AID_REF, NATIVE_AID_REF, SR_LUCK_REF, NATIVE_LUCK_REF, GERMAN_REF = 1, 2, 3, 4, 5
IDS = b"IDS V1.0\n1201 CLERIC_AID\n2209 WIZARD_LUCK\n1508 CLERIC_CHAOTIC_COMMANDS\n"


def fx(op, p1=0, p2=0, *, tg=2, pw=2, tm=0, rd=3, du=0, res="", **kwargs):
    return SplEffect(opcode=op, target=tg, power=pw, parameter1=p1, parameter2=p2, timing=tm,
                     resist_dispel=rd, duration=du, resource=res, **kwargs)


def refresh(resref):
    """Spell Revisions' self-refresh: non-dispellable, ignores magic resistance."""
    return SplEffect(opcode=321, target=2, timing=1, resource=resref)


def spell(abilities, *, spell_type=2, level=2, desc=-1, excl=0, casting=()):
    header = bytearray(make_spl_header(spell_type=2, level=level))
    struct.pack_into("<H", header, 0x1C, spell_type)  # also innate (4)
    struct.pack_into("<I", header, 0x1E, excl)
    struct.pack_into("<i", header, 0x50, desc)
    return SplFile(abilities=tuple(abilities), casting_effects=tuple(casting),
                   header_raw=bytes(header)).to_bytes()


def item(*effects, category=11, description=-1):
    header = bytearray(0x72)
    struct.pack_into("<H", header, 0x1C, category)
    ability = bytearray(0x38)
    ability[0] = 3
    ability[0x0C] = 1
    return ItmFile(abilities=(ItmAbility(raw=bytes(ability), effects=tuple(effects)),),
                   header_raw=bytes(header), identified_description=description).to_bytes()


def caster_level(level):
    return max(level, 3)


def sr_aid_ability(level, *extra):
    d = 60 * caster_level(level)
    return SplAbility(level, 1, 1, (
        refresh("SPPR201"), fx(129, 1, du=d), fx(18, min(caster_level(level), 10), du=d),
        fx(141, 0, 2, tm=1), fx(139, 14122, tm=1), fx(174, tm=4, du=d, res="EFF_E01"),
        fx(215, 0, 1, du=6, res="SPHLYBLS"), *extra))


def native_aid_ability(level):
    d = 6 * (level + 1)
    return SplAbility(level, 1, 1, (
        fx(129, 1, du=d), fx(141, 0, 2, tm=1), fx(61, 7, 1638400, tm=1), fx(139, 14122, tm=1),
        fx(8, 9, 255, du=d), fx(174, tm=4, du=d, res="EFF_E01"),
        fx(215, 0, 1, du=6, res="SPHLYBLS")))


SR_LEVELS = (1, 4, 9, 12, 20)
NATIVE_LEVELS = (1, 2, 3, 5, 12, 20)


def sr_aid(*, spell_type=2, desc=SR_AID_REF, abilities=None):
    return spell(abilities or [sr_aid_ability(level) for level in SR_LEVELS],
                 spell_type=spell_type, desc=desc, excl=0x80000000)


def native_aid(desc=NATIVE_AID_REF):
    return spell([native_aid_ability(level) for level in NATIVE_LEVELS], desc=desc, excl=0x80000000)


def hit_points(base, level):
    """The converted bonus: base's delivery, min(L, 10) + 1d8 for one turn per level."""
    lvl = caster_level(level)
    return dataclasses.replace(base, opcode=18, parameter1=min(lvl, 10), parameter2=0,
                               duration=60 * lvl, dice_number=1, dice_size=8)


def expected_sr_aid(level, family):
    old = sr_aid_ability(level).effects
    return (*(refresh(member) for member in family), hit_points(old[2], level), *old[3:])


def expected_native_aid(level):
    old = native_aid_ability(level).effects
    d = 60 * caster_level(level)
    return (refresh("SPPR201"), hit_points(old[0], level), *old[1:4],
            dataclasses.replace(old[4], duration=d), dataclasses.replace(old[5], duration=d), old[6])


def luck_effects(resref, d, *, payload=133, glow=1):
    return (refresh(resref), fx(payload, 1, du=d),
            *(fx(op, 1, du=d) for op in (33, 34, 35, 36, 37)),
            *(fx(op, 5, du=d) for op in (276, 91, 90, 275, 92, 277, 59)),
            fx(141, 0, 10, tm=1), fx(139, 14019, tm=1), fx(142, 0, 32, du=d),
            fx(174, tm=4, du=d, res="EFF_E01"), fx(50, du=glow))


def luck(d=300, *, resref="SPWI209", desc=SR_LUCK_REF, spell_type=1, **kwargs):
    return spell([SplAbility(1, 1, 48, luck_effects(resref, d, **kwargs))],
                 spell_type=spell_type, desc=desc, excl=0x800)


def chaotic_commands(excl, *, spell_type=2):
    return spell([SplAbility(9, 1, 1, (fx(101, 0, 5, du=540), fx(142, 0, 33, du=540)))],
                 spell_type=spell_type, level=5, excl=excl)


def effects_by_level(blob):
    return {ability.required_level: ability.effects for ability in SplFile.from_bytes(blob).abilities}


def description(game, blob, offset=0x50):
    return strings(game.tlk)[struct.unpack_from("<i", blob, offset)[0]]


def run(game, *components, uninstall=False, tp2="setup-chriz-bg-rebalance.tp2"):
    p = subprocess.run([str(WEIDU), tp2, "--force-uninstall-list" if uninstall else "--force-install-list",
                        *map(str, components), "--language", "0", "--use-lang", "en_us",
                        "--no-exit-pause", "--quick-log"],
                       cwd=game.root, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


class Fixture(unittest.TestCase):
    def game(self, resources):
        holder = tempfile.TemporaryDirectory(prefix="cbr-chris-revisions-")
        self.addCleanup(holder.cleanup)
        return Game(Path(holder.name), {"SPELL.IDS": IDS, **resources}, public=True, texts=TEXTS)

    def install(self, game, *components, warnings=False):
        code, output = run(game, *components)
        # WeiDU exits with 3 after an installation with PATCH_WARN.
        self.assertEqual(3 if warnings else 0, code, output)
        self.assertIn("INSTALLED WITH WARNINGS" if warnings else "SUCCESSFULLY INSTALLED", output)
        return output

    def rejected(self, game, component, message):
        code, output = run(game, component)
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn(message, output)
        self.assertEqual(game.original, game.snapshot(), output)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def changed(self, game):
        after = game.snapshot()
        return {name for name in after if after[name] != game.original.get(name)}

    def uninstall(self, game, component):
        code, output = run(game, component, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(game.original, game.snapshot())
        # WeiDU keeps appended strings; the original entries must be intact.
        self.assertEqual(TEXTS, strings(game.tlk)[:len(TEXTS)])

    def repeat(self, game, call):
        installed, installed_tlk = game.snapshot(), game.tlk.read_bytes()
        (game.root / "repeat.tp2").write_text(
            "BACKUP ~repeat-backup~\nAUTHOR ~test~\n"
            "ALWAYS\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/buff_spells.tpa~\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/druid_access.tpa~\n"
            "END\n"
            "LANGUAGE ~English~ ~english~ ~chriz-bg-rebalance/languages/english/setup.tra~\n"
            f"BEGIN ~repeat~\n{call}\n")
        code, output = run(game, 0, tp2="repeat.tp2")
        self.assertEqual(0, code, output)
        self.assertEqual(installed, game.snapshot())
        self.assertEqual(installed_tlk, game.tlk.read_bytes())


class AidTests(Fixture):
    def sr_game(self):
        near = [sr_aid_ability(level) for level in SR_LEVELS]
        near[2] = sr_aid_ability(9, fx(50, du=1, tg=1))
        return self.game({
            "SPPR201.SPL": sr_aid(),
            # Bardic Wonders' Troubadour: a byte copy with another spell type.
            "C0TRBS2.SPL": sr_aid(spell_type=1),
            # Not an exact copy, and a spell that only removes Aid: both untouched.
            "C0NEAR.SPL": sr_aid(abilities=near),
            "CBRDISP.SPL": spell([SplAbility(1, 1, 1, (fx(321, res="SPPR201", tm=1),))]),
        })

    def test_spell_revisions_aid_and_its_copy_become_hit_points_only(self):
        game = self.sr_game()
        output = self.install(game, 340)
        after = game.snapshot()
        self.assertEqual({"SPPR201.SPL", "C0TRBS2.SPL"}, self.changed(game))
        self.assertIn("Changed: SPPR201 C0TRBS2", output)
        family = ("SPPR201", "C0TRBS2")
        for name in family:
            levels = effects_by_level(after[name + ".SPL"])
            self.assertEqual(SR_LEVELS, tuple(levels))
            for level in SR_LEVELS:
                self.assertEqual(expected_sr_aid(level, family), levels[level], (name, level))
            self.assertEqual(SR_AID_NEW, description(game, after[name + ".SPL"]))
            # Only the description pointer changes in the header.
            before_header, after_header = game.original[name + ".SPL"][:0x72], after[name + ".SPL"][:0x72]
            self.assertEqual(before_header[:0x50] + before_header[0x54:], after_header[:0x50] + after_header[0x54:])
        self.assertEqual(effects_by_level(after["SPPR201.SPL"]), effects_by_level(after["C0TRBS2.SPL"]))
        self.uninstall(game, 340)

    def test_native_aid_converts_the_aid_effect_and_follows_its_duration(self):
        game = self.game({"SPPR201.SPL": native_aid()})
        self.install(game, 340)
        after = game.snapshot()
        self.assertEqual({"SPPR201.SPL"}, self.changed(game))
        levels = effects_by_level(after["SPPR201.SPL"])
        for level in NATIVE_LEVELS:
            self.assertEqual(expected_native_aid(level), levels[level], level)
        self.assertEqual(NATIVE_AID_NEW, description(game, after["SPPR201.SPL"]))
        self.uninstall(game, 340)

    def test_second_application_changes_nothing(self):
        game = self.sr_game()
        self.install(game, 340)
        self.repeat(game, "LAF cbr_install_aid_hp END")

    def test_relocated_symbol_shared_slices_and_casting_effects(self):
        # CLERIC_AID lives in SPPR222; SPPR201 is a different (native) spell.
        effects = [fx(50, du=1, tg=1),                       # casting effect
                   fx(129, 1, du=12), fx(174, tm=4, du=12, res="EFF_E01"),  # shared by both abilities
                   fx(139, 1, tm=1)]                         # referenced by nothing
        header = bytearray(make_spl_header(spell_type=2, level=2))
        struct.pack_into("<IHI", header, 0x64, 0x72, 2, 0x72 + 2 * 0x28)
        struct.pack_into("<HH", header, 0x6E, 0, 1)
        struct.pack_into("<i", header, 0x50, -1)
        abilities = b""
        for level in (1, 12):
            ability = bytearray(0x28)
            ability[0x0C] = 1
            struct.pack_into("<H", ability, 0x10, level)
            struct.pack_into("<HH", ability, 0x1E, 2, 1)
            abilities += bytes(ability)
        shared = bytes(header) + abilities + b"".join(e.to_bytes() for e in effects)
        game = self.game({"SPELL.IDS": b"IDS V1.0\n1222 CLERIC_AID\n", "SPPR222.SPL": shared,
                          "SPPR201.SPL": native_aid()})
        self.install(game, 340)
        self.assertEqual({"SPPR222.SPL"}, self.changed(game))
        result = SplFile.from_bytes(game.snapshot()["SPPR222.SPL"])
        self.assertEqual((effects[0],), result.casting_effects)
        for ability, level in zip(result.abilities, (1, 12)):
            d = 60 * caster_level(level)
            self.assertEqual((refresh("SPPR222"), hit_points(effects[1], level),
                              dataclasses.replace(effects[2], duration=d)), ability.effects)
        self.assertEqual(7, len(result.all_effects()))

    def test_ambiguous_payload_rolls_back(self):
        abilities = [sr_aid_ability(level) for level in SR_LEVELS]
        abilities[-1] = sr_aid_ability(20, fx(129, 1, du=1200))
        game = self.game({"SPPR201.SPL": sr_aid(abilities=abilities)})
        self.rejected(game, 340, "does not have exactly one Aid payload")

    def test_unrecognized_description_warns_and_keeps_the_text(self):
        game = self.game({"SPPR201.SPL": sr_aid(desc=GERMAN_REF)})
        output = self.install(game, 340, warnings=True)
        self.assertIn("SPPR201.spl has different or untranslated text", output)
        after = game.snapshot()["SPPR201.SPL"]
        self.assertEqual(GERMAN_REF, struct.unpack_from("<i", after, 0x50)[0])
        self.assertEqual(expected_sr_aid(20, ("SPPR201",)), effects_by_level(after)[20])

    def test_missing_symbol_skips_without_changes(self):
        game = self.game({"SPELL.IDS": b"IDS V1.0\n2209 WIZARD_LUCK\n", "SPPR201.SPL": sr_aid()})
        code, output = run(game, 340)
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(game.original, game.snapshot())


class LuckTests(Fixture):
    def test_spell_revisions_luck_copies_and_scroll_last_90_seconds(self):
        game = self.game({
            "SPWI209.SPL": luck(),
            "C0LUCK.SPL": luck(spell_type=4),             # exact copy
            "C0NEAR.SPL": luck(glow=2),                   # not an exact copy
            "SCRL93.ITM": item(fx(147, tg=1, tm=1, res="SPWI209"), description=SR_LUCK_REF),
            "SCRL99.ITM": item(fx(147, tg=1, tm=1, res="SPWI999"), description=SR_LUCK_REF),
            "BOW99.ITM": item(fx(146, 10, 1, tg=1, tm=1, res="SPWI209"), category=15),
        })
        output = self.install(game, 341)
        after = game.snapshot()
        self.assertEqual({"SPWI209.SPL", "C0LUCK.SPL", "SCRL93.ITM"}, self.changed(game))
        self.assertIn("Changed: SPWI209 C0LUCK", output)
        for name in ("SPWI209.SPL", "C0LUCK.SPL"):
            self.assertEqual(luck_effects("SPWI209", 90), SplFile.from_bytes(after[name]).abilities[0].effects)
            self.assertEqual(SR_LUCK_NEW, description(game, after[name]))
        self.assertEqual(SR_LUCK_NEW, description(game, after["SCRL93.ITM"], 0x54))
        self.assertEqual(game.original["SCRL93.ITM"][0x50:0x54], after["SCRL93.ITM"][0x50:0x54])
        self.uninstall(game, 341)

    def test_native_luck_and_an_opcode_22_variant(self):
        game = self.game({"SPWI209.SPL": luck(18, desc=NATIVE_LUCK_REF)})
        self.install(game, 341)
        after = game.snapshot()
        self.assertEqual(luck_effects("SPWI209", 90), SplFile.from_bytes(after["SPWI209.SPL"]).abilities[0].effects)
        self.assertEqual(NATIVE_LUCK_NEW, description(game, after["SPWI209.SPL"]))
        self.assertEqual({"SPWI209.SPL"}, self.changed(game))

        # The same rule through an opcode-22 luck bonus when it is the resolved spell.
        variant = self.game({"SPELL.IDS": b"IDS V1.0\n2901 WIZARD_LUCK\n",
                             "SPWI901.SPL": luck(300, resref="SPWI901", payload=22)})
        self.install(variant, 341)
        self.assertEqual(luck_effects("SPWI901", 90, payload=22),
                         SplFile.from_bytes(variant.snapshot()["SPWI901.SPL"]).abilities[0].effects)

    def test_second_application_changes_nothing(self):
        game = self.game({"SPWI209.SPL": luck(),
                          "SCRL93.ITM": item(fx(147, tg=1, tm=1, res="SPWI209"), description=SR_LUCK_REF)})
        self.install(game, 341)
        self.repeat(game, "LAF cbr_install_luck_duration END")

    def test_conflicting_or_missing_luck_bonus_rolls_back(self):
        conflict = self.game({"SPWI209.SPL": spell([SplAbility(1, 1, 48, (
            *luck_effects("SPWI209", 300), fx(133, 1, du=60)))], spell_type=1)})
        self.rejected(conflict, 341, "Luck bonuses with different durations")
        missing = self.game({"SPWI209.SPL": spell([SplAbility(1, 1, 48, (fx(33, 1, du=300),))],
                                                  spell_type=1)})
        self.rejected(missing, 341, "has no timed Luck bonus")


class DruidAccessTests(Fixture):
    def test_spell_revisions_exclusion_is_lifted_and_restored_on_uninstall(self):
        game = self.game({"SPPR508.SPL": chaotic_commands(0x80000020)})
        output = self.install(game, 350)
        self.assertIn("druids can learn and cast it again", output)
        after = game.snapshot()["SPPR508.SPL"]
        self.assertEqual(0x00000020, struct.unpack_from("<I", after, 0x1E)[0])
        expected = bytearray(game.original["SPPR508.SPL"])
        struct.pack_into("<I", expected, 0x1E, 0x00000020)
        self.assertEqual(bytes(expected), after)
        self.uninstall(game, 350)

    def test_already_available_is_left_alone_and_repeat_is_stable(self):
        game = self.game({"SPELL.IDS": b"IDS V1.0\n1577 CLERIC_CHAOTIC_COMMANDS\n",
                          "SPPR577.SPL": chaotic_commands(0x00000000),
                          "SPPR508.SPL": chaotic_commands(0x80000000)})
        output = self.install(game, 350)
        self.assertIn("already available to druids", output)
        self.assertEqual(set(), self.changed(game))
        self.repeat(game, "LAF cbr_install_druid_access STR_VAR symbol = ~CLERIC_CHAOTIC_COMMANDS~ END")

    def test_spells_no_priest_or_no_druid_can_learn_are_rejected(self):
        self.rejected(self.game({"SPPR508.SPL": chaotic_commands(0xC0000000)}), 350,
                      "excluded for every priest class")
        self.rejected(self.game({"SPPR508.SPL": chaotic_commands(0x80000000, spell_type=1)}), 350,
                      "is not a priest spell")


if __name__ == "__main__":
    unittest.main()
