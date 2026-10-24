"""Component 340, Chris Revisions: Aid, Luck, Bless, Chaotic Commands, Prayer and Recitation.

Real WeiDU on disposable synthetic games only. The fixtures mirror the shapes
seen in an installed EET game (native and Spell Revisions Aid/Luck/Bless, Bardic
Wonders' byte copy of Aid, SCS's instant prebuff copy of Bless, the Luck scroll,
SR's druid exclusion, IWDification's Prayer and Recitation with their sub-spells
and priest scrolls) plus layouts the component must also handle: relocated
SPELL.IDS slots, shared effect slices, casting effects, an opcode-22 Luck bonus,
a Bless with its own level table, reordered refreshes, saving throws and
unrecognized text. Descriptions are short stand-ins that contain only the
phrases the installer rewrites.
"""
from __future__ import annotations

import dataclasses
import functools
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
PRAYER = ("Prayer\nDuration: 1 round/level\n\nAll attacks, damage, and Saving Throws by friendly "
          "characters gain a +1 bonus, while enemy attacks, damage rolls, and saves get a -1 penalty.")
RECITATION = ("Recitation\nDuration: 1 round/level\n\nThe priest's allies gain a +2 bonus to their "
              "attack rolls and Saving Throws, and the priest's enemies receive a -2 penalty to the "
              "same. Recitation does not nullify a Prayer spell—the two can be cast in tandem, "
              "and the effects are cumulative.")
OTHER_RECITATION = ("Recitation\nDuration: 1 round/level\n\nAllies gain +2 to attack rolls and "
                    "saving throws; enemies suffer -2.")
GERMAN_RECITATION = "Rezitation\nDauer: 1 Runde/Stufe\n\nVerbuendete erhalten +2."
PRAYER_NOTE = ("Prayer does not stack with Recitation. A creature with Recitation's bonus gains no "
               "bonus from Prayer, a creature with Recitation's penalty suffers no penalty from "
               "Prayer, and a later Recitation replaces Prayer's bonus or penalty.")
RECITATION_NOTE = ("Recitation does not stack with Prayer. On each creature, Recitation's bonus "
                   "replaces a Prayer bonus and its penalty replaces a Prayer penalty; while "
                   "Recitation lasts, Prayer adds no bonus or penalty of the same kind.")
PRAYER_NEW = PRAYER + "\n\n" + PRAYER_NOTE
RECITATION_NEW = RECITATION.split(" Recitation does not")[0] + " " + RECITATION_NOTE
SR_BLESS = ("Bless\nRange: Long\nDuration: 5 turns\nCasting Time: 5\n\nUpon uttering the Bless spell, "
            "the caster raises the morale of friendly creatures by +1.")
NATIVE_BLESS = ("Bless\nRange: 40 ft.\nDuration: 6 rounds\nCasting Time: 9\n\nUpon uttering the Bless "
                "spell, the caster raises the morale of friendly creatures by +1.")
BLESS_DURATION = "Duration: 5 rounds + 1 round/level (maximum 25 rounds)"
SR_BLESS_NEW = SR_BLESS.replace("Duration: 5 turns", BLESS_DURATION)
NATIVE_BLESS_NEW = NATIVE_BLESS.replace("Duration: 6 rounds", BLESS_DURATION)
TEXTS = ["Unrelated shared text.", SR_AID, NATIVE_AID, SR_LUCK, NATIVE_LUCK, GERMAN,
         PRAYER, RECITATION, RECITATION, OTHER_RECITATION, GERMAN_RECITATION, SR_BLESS, NATIVE_BLESS]
(SR_AID_REF, NATIVE_AID_REF, SR_LUCK_REF, NATIVE_LUCK_REF, GERMAN_REF, PRAYER_REF, RECITATION_REF,
 RECITATION_COPY_REF, OTHER_RECITATION_REF, GERMAN_RECITATION_REF, SR_BLESS_REF, NATIVE_BLESS_REF) = range(1, 13)
# Each part's spell gets its SPELL.IDS entry when the game has it.
DEFAULT_IDS = {"SPPR201.SPL": "1201 CLERIC_AID", "SPWI209.SPL": "2209 WIZARD_LUCK",
               "SPPR101.SPL": "1101 CLERIC_BLESS", "SPPR508.SPL": "1508 CLERIC_CHAOTIC_COMMANDS",
               "SPPR327.SPL": "1327 CLERIC_PRAYER", "SPPR422.SPL": "1422 CLERIC_RECITATION"}


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


def bless_raw(range_, speed):
    """Ability fields besides level and effects, which every new ability keeps."""
    raw = bytearray(0x28)
    raw[0] = 1
    struct.pack_into("<HH", raw, 0x0E, range_, 1)
    struct.pack_into("<HH", raw, 0x12, speed, 1)
    struct.pack_into("<H", raw, 0x24, 3)
    return bytes(raw)


SR_BLESS_RAW, NATIVE_BLESS_RAW = bless_raw(30, 5), bless_raw(40, 9)


def bless_effects(d, *, amount=1, visual=1):
    """Spell Revisions' Bless: bonus, visual, feedback, spell state, icon, end sound."""
    e = functools.partial(fx, pw=1)
    return (e(130, amount, du=d), e(215, 0, 1, du=visual, res="ICBLESAI"), e(139, 14123, tm=1),
            e(328, 1, 68, du=d, special=1), e(142, 0, 17, du=d), e(174, tm=4, du=d, res="EFF_E01"))


def native_bless_effects(d):
    e = functools.partial(fx, pw=1)
    return (e(130, 1, du=d), e(139, 14123, tm=1), e(142, 0, 17, du=d), e(174, tm=4, du=d, res="EFF_E01"),
            e(215, 0, 1, rd=2, du=2, res="ICBLESAI"), e(50, 1264876800, 983040, tm=1))


def prebuff_bless_effects(d):
    """SCS's instant prebuff copy: Bless without its cosmetic effects."""
    return tuple(e for e in bless_effects(d) if e.opcode in (130, 328, 142))


def bless_ability(level, effects, raw=SR_BLESS_RAW):
    return SplAbility(level, 4, 162, effects, icon="SPPR101B", raw=raw)


def sr_bless(*, spell_type=2, desc=SR_BLESS_REF, effects=None):
    return spell([bless_ability(1, effects or bless_effects(300))], spell_type=spell_type, level=1,
                 desc=desc, excl=0x80000000)


def bless_duration(level):
    return 30 + 6 * min(level, 20)


def scs_prebuff_map(game, *rows):
    """SCS's own map of instant prebuff copies, as its installer writes it."""
    path = game.root / "weidu_external/data/stratagems/instant_prebuff_spells.2da"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\r\n" + b"".join(f"{key} {resref}\r\n".encode() for key, resref in rows))
    return path


# IWDification's Prayer and Recitation: the spell casts a bonus sub-spell for
# allies and a penalty sub-spell for enemies, each with its own refresh first.
PRAYER_LEVELS = (1, 6, 20)
RECITATION_LEVELS = (1, 8, 20)


def prayer_duration(level):
    return 6 * max(level, 5)


def recitation_duration(level):
    return 6 * max(level, 7)


def prayer_effects(own, d, sign):
    e = functools.partial(fx, pw=3, rd=3 if sign > 0 else 1)
    markers = (e(328, 1, 12, du=d, special=1), e(328, 1, 68, du=d, special=1)) if sign > 0 else ()
    return (e(321, tm=1, res=own), e(215, tm=1, res=own[1:]), e(174, tm=1, res="#EFF_P31"),
            e(139, 232766, tm=1), e(54, sign, du=d), e(73, sign, du=d), e(325, sign, du=d),
            *markers, e(142, 0, 336 if sign > 0 else 33, du=d), e(9, 8692992, 3932415, du=d),
            e(174, tm=4, du=d, res="EFF_E03"))


def recitation_effects(own, d, sign, *, save=0):
    e = functools.partial(fx, pw=4, rd=3 if sign > 0 else 1)
    markers = (e(328, 1, 14, du=d, special=1), e(328, 1, 68, du=d, special=1)) if sign > 0 else ()
    return (e(321, tm=1, res=own), e(215, tm=1, res="RECITAG"), e(174, tm=1, res="#EFF_P44"),
            e(139, 232766, tm=1), e(54, 2 * sign, du=d, save_type=save, save_bonus=-save),
            e(325, 2 * sign, du=d, save_type=save, save_bonus=-save), *markers,
            e(142, 0, 340 if sign > 0 else 33, du=d), e(9, 11982592, 3932415, du=d),
            e(174, tm=4, du=d, res="EFF_E03"))


def sub_spell(build, own, levels, duration, sign, level, casting=(), **kwargs):
    return spell([SplAbility(lvl, 4, 337 if sign > 0 else 338, build(own, duration(lvl), sign, **kwargs))
                  for lvl in levels], level=level, casting=casting)


# SCS gives hostile spells casting effects for the caster (invisibility animations).
SCS_CASTING = (fx(146, 0, 1, tg=1, pw=0, tm=1, rd=0, res="DW#BLHDA"),
               fx(321, tg=1, pw=0, tm=1, rd=0, res="DW#HDANI"))


def casting_spell(bonus, penalty, *, level, desc, extra=()):
    cast = functools.partial(fx, 146, 0, 1, tg=1, pw=0, tm=1, rd=0)
    return spell([SplAbility(1, 5, 1, (cast(res=bonus), cast(res=penalty), *extra))],
                 level=level, desc=desc, excl=0x80000000)


def prayer_recitation(**overrides):
    resources = {
        "SPPR327.SPL": casting_spell("#PRAYERG", "#PRAYERB", level=3, desc=PRAYER_REF),
        "SPPR422.SPL": casting_spell("#RECITEG", "#RECITEB", level=4, desc=RECITATION_REF),
        "#PRAYERG.SPL": sub_spell(prayer_effects, "#PRAYERG", PRAYER_LEVELS, prayer_duration, 1, 3),
        "#PRAYERB.SPL": sub_spell(prayer_effects, "#PRAYERB", PRAYER_LEVELS, prayer_duration, -1, 3,
                                  casting=SCS_CASTING),
        "#RECITEG.SPL": sub_spell(recitation_effects, "#RECITEG", RECITATION_LEVELS, recitation_duration, 1, 4),
        "#RECITEB.SPL": sub_spell(recitation_effects, "#RECITEB", RECITATION_LEVELS, recitation_duration, -1, 4,
                                  casting=SCS_CASTING),
        "DW#BLHDA.SPL": spell([SplAbility(0, 1, 1, (fx(321, tg=1, pw=0, rd=0, res="DW#HDANI"),))],
                              spell_type=4, level=1),
        # IWDification's priest scrolls show the spell's own description.
        "CDID327.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR327"), description=PRAYER_REF),
        "CDID422.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR422"), description=RECITATION_REF),
        "CBRCOPY.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR422"), description=RECITATION_COPY_REF),
        "CBRWAND.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR422"), category=35, description=0),
    }
    resources.update(overrides)
    return resources


def like(template, opcode, **fields):
    """A record added to a Recitation payload: delivered like its bonus effect."""
    return SplEffect(opcode=opcode, target=template.target, power=template.power,
                     resist_dispel=template.resist_dispel, probability1=template.probability1,
                     probability2=template.probability2, save_type=template.save_type,
                     save_bonus=template.save_bonus, **fields)


def expected_recitation(old, prayer_payload, d, *, lead=1, keep_block=None):
    template = next(e for e in old if e.opcode in (54, 325))
    added = (like(template, 321, timing=1, resource=prayer_payload),
             *(() if keep_block else (like(template, 206, parameter1=-1, duration=d, resource=prayer_payload),)))
    rest = tuple(dataclasses.replace(e, duration=d) if e is keep_block else e for e in old[lead:])
    return (*old[:lead], *added, *rest)


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
        ids = "IDS V1.0\n" + "".join(f"{line}\n" for name, line in DEFAULT_IDS.items() if name in resources)
        return Game(Path(holder.name), {"SPELL.IDS": ids.encode(), **resources}, public=True, texts=TEXTS)

    def install(self, game, warnings=False):
        code, output = run(game, 340)
        # WeiDU exits with 3 after an installation with warnings.
        self.assertEqual(3 if warnings else 0, code, output)
        self.assertIn("INSTALLED WITH WARNINGS" if warnings else "SUCCESSFULLY INSTALLED", output)
        return output

    def left_unchanged(self, game, message, *names):
        """The part that cannot be changed safely warns; its files stay as they were."""
        output = self.install(game, warnings=True)
        self.assertIn(message, output)
        after = game.snapshot()
        for name in names:
            self.assertEqual(game.original[name], after[name], name)
        return output

    def changed(self, game):
        after = game.snapshot()
        return {name for name in after if after[name] != game.original.get(name)}

    def uninstall(self, game):
        code, output = run(game, 340, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(game.original, game.snapshot())
        # WeiDU keeps appended strings; the original entries must be intact.
        self.assertEqual(TEXTS, strings(game.tlk)[:len(TEXTS)])

    def repeat(self, game):
        installed, installed_tlk = game.snapshot(), game.tlk.read_bytes()
        (game.root / "repeat.tp2").write_text(
            "BACKUP ~repeat-backup~\nAUTHOR ~test~\n"
            "ALWAYS\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/chris_revisions.tpa~\n"
            "END\n"
            "LANGUAGE ~English~ ~english~ ~chriz-bg-rebalance/languages/english/setup.tra~\n"
            "BEGIN ~repeat~\nLAF cbr_install_chris_revisions END\n")
        code, output = run(game, 0, tp2="repeat.tp2")
        self.assertEqual(0, code, output)
        self.assertEqual(installed, game.snapshot())
        self.assertEqual(installed_tlk, game.tlk.read_bytes())


class CombinedTests(Fixture):
    def all_parts(self):
        return self.game({
            "SPPR201.SPL": sr_aid(),
            "C0TRBS2.SPL": sr_aid(spell_type=1),
            "SPWI209.SPL": luck(),
            "SCRL93.ITM": item(fx(147, tg=1, tm=1, res="SPWI209"), description=SR_LUCK_REF),
            "SPPR101.SPL": sr_bless(),
            "SPPR508.SPL": chaotic_commands(0x80000020),
            **prayer_recitation(),
        })

    def test_every_part_applies_in_one_component_and_a_second_run_changes_nothing(self):
        game = self.all_parts()
        output = self.install(game)
        self.assertEqual({"SPPR201.SPL", "C0TRBS2.SPL", "SPWI209.SPL", "SCRL93.ITM", "SPPR101.SPL",
                          "SPPR508.SPL", "SPPR327.SPL", "SPPR422.SPL", "#RECITEG.SPL", "#RECITEB.SPL",
                          "CDID327.ITM", "CDID422.ITM", "CBRCOPY.ITM"}, self.changed(game))
        for text in ("Aid installed", "Luck installed", "Bless installed", "Bless: druids can learn and cast it again",
                     "Chaotic Commands: druids can learn and cast it again", "Prayer and Recitation installed"):
            self.assertIn(text, output)
        self.assertNotIn("skipped", output)
        self.repeat(game)

    def test_uninstall_restores_every_file(self):
        game = self.all_parts()
        self.install(game)
        self.uninstall(game)

    def test_a_part_that_cannot_be_changed_safely_leaves_the_others_applied(self):
        abilities = [sr_aid_ability(level) for level in SR_LEVELS]
        abilities[-1] = sr_aid_ability(20, fx(129, 1, du=1200))
        game = self.game({"SPPR201.SPL": sr_aid(abilities=abilities), "SPWI209.SPL": luck(),
                          "SPPR508.SPL": chaotic_commands(0x80000020)})
        self.left_unchanged(game, "Chris Revisions: Aid left unchanged: SPPR201.spl (ability for level 20) "
                            "does not have exactly one Aid payload", "SPPR201.SPL")
        self.assertEqual({"SPWI209.SPL", "SPPR508.SPL"}, self.changed(game))

    def test_parts_without_their_spell_are_skipped(self):
        game = self.game({"SPELL.IDS": b"IDS V1.0\n2209 WIZARD_LUCK\n1327 CLERIC_PRAYER\n",
                          "SPPR201.SPL": sr_aid(), "SPWI209.SPL": luck(), "SPPR101.SPL": sr_bless(),
                          **prayer_recitation()})
        output = self.install(game)
        self.assertIn("Aid skipped; SPELL.IDS has no CLERIC_AID entry", output)
        self.assertIn("Bless skipped; SPELL.IDS has no CLERIC_BLESS entry", output)
        self.assertIn("Bless for druids skipped; SPELL.IDS has no CLERIC_BLESS entry", output)
        self.assertIn("Chaotic Commands skipped; SPELL.IDS has no CLERIC_CHAOTIC_COMMANDS entry", output)
        self.assertIn("Prayer and Recitation skipped; SPELL.IDS has no CLERIC_RECITATION entry", output)
        self.assertEqual({"SPWI209.SPL"}, self.changed(game))


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
        output = self.install(game)
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
        self.uninstall(game)

    def test_native_aid_converts_the_aid_effect_and_follows_its_duration(self):
        game = self.game({"SPPR201.SPL": native_aid(),
                          # An item that shows the spell's description shows the new one.
                          "CBRAID.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR201"), description=NATIVE_AID_REF)})
        self.install(game)
        after = game.snapshot()
        self.assertEqual({"SPPR201.SPL", "CBRAID.ITM"}, self.changed(game))
        levels = effects_by_level(after["SPPR201.SPL"])
        for level in NATIVE_LEVELS:
            self.assertEqual(expected_native_aid(level), levels[level], level)
        self.assertEqual(NATIVE_AID_NEW, description(game, after["SPPR201.SPL"]))
        self.assertEqual(after["SPPR201.SPL"][0x50:0x54], after["CBRAID.ITM"][0x54:0x58])
        self.uninstall(game)

    def test_second_application_changes_nothing(self):
        game = self.sr_game()
        self.install(game)
        self.repeat(game)

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
        self.install(game)
        self.assertEqual({"SPPR222.SPL"}, self.changed(game))
        result = SplFile.from_bytes(game.snapshot()["SPPR222.SPL"])
        self.assertEqual((effects[0],), result.casting_effects)
        for ability, level in zip(result.abilities, (1, 12)):
            d = 60 * caster_level(level)
            self.assertEqual((refresh("SPPR222"), hit_points(effects[1], level),
                              dataclasses.replace(effects[2], duration=d)), ability.effects)
        self.assertEqual(7, len(result.all_effects()))

    def test_ambiguous_payload_is_left_unchanged(self):
        abilities = [sr_aid_ability(level) for level in SR_LEVELS]
        abilities[-1] = sr_aid_ability(20, fx(129, 1, du=1200))
        game = self.game({"SPPR201.SPL": sr_aid(abilities=abilities), "C0TRBS2.SPL": sr_aid(spell_type=1)})
        # The copy is not an exact copy any more, so only SPPR201 is the family.
        self.left_unchanged(game, "does not have exactly one Aid payload", "SPPR201.SPL", "C0TRBS2.SPL")
        self.assertEqual(set(), self.changed(game))
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_unrecognized_description_warns_and_keeps_the_text(self):
        game = self.game({"SPPR201.SPL": sr_aid(desc=GERMAN_REF)})
        output = self.install(game, warnings=True)
        self.assertIn("SPPR201.spl has different or untranslated text", output)
        after = game.snapshot()["SPPR201.SPL"]
        self.assertEqual(GERMAN_REF, struct.unpack_from("<i", after, 0x50)[0])
        self.assertEqual(expected_sr_aid(20, ("SPPR201",)), effects_by_level(after)[20])


class LuckTests(Fixture):
    def test_spell_revisions_luck_copies_and_scroll_last_90_seconds(self):
        game = self.game({
            "SPWI209.SPL": luck(),
            "C0LUCK.SPL": luck(spell_type=4),             # exact copy
            "C0NEAR.SPL": luck(glow=2),                   # not an exact copy
            "SCRL93.ITM": item(fx(147, tg=1, tm=1, res="SPWI209"), description=SR_LUCK_REF),
            "SCRL99.ITM": item(fx(147, tg=1, tm=1, res="SPWI999"), description=NATIVE_LUCK_REF),
            "BOW99.ITM": item(fx(146, 10, 1, tg=1, tm=1, res="SPWI209"), category=15),
        })
        output = self.install(game)
        after = game.snapshot()
        self.assertEqual({"SPWI209.SPL", "C0LUCK.SPL", "SCRL93.ITM"}, self.changed(game))
        self.assertIn("Changed: SPWI209 C0LUCK", output)
        for name in ("SPWI209.SPL", "C0LUCK.SPL"):
            self.assertEqual(luck_effects("SPWI209", 90), SplFile.from_bytes(after[name]).abilities[0].effects)
            self.assertEqual(SR_LUCK_NEW, description(game, after[name]))
        self.assertEqual(SR_LUCK_NEW, description(game, after["SCRL93.ITM"], 0x54))
        self.assertEqual(game.original["SCRL93.ITM"][0x50:0x54], after["SCRL93.ITM"][0x50:0x54])
        self.uninstall(game)

    def test_native_luck_and_an_opcode_22_variant(self):
        game = self.game({"SPWI209.SPL": luck(18, desc=NATIVE_LUCK_REF)})
        self.install(game)
        after = game.snapshot()
        self.assertEqual(luck_effects("SPWI209", 90), SplFile.from_bytes(after["SPWI209.SPL"]).abilities[0].effects)
        self.assertEqual(NATIVE_LUCK_NEW, description(game, after["SPWI209.SPL"]))
        self.assertEqual({"SPWI209.SPL"}, self.changed(game))

        # The same rule through an opcode-22 luck bonus when it is the resolved spell.
        variant = self.game({"SPELL.IDS": b"IDS V1.0\n2901 WIZARD_LUCK\n",
                             "SPWI901.SPL": luck(300, resref="SPWI901", payload=22)})
        self.install(variant)
        self.assertEqual(luck_effects("SPWI901", 90, payload=22),
                         SplFile.from_bytes(variant.snapshot()["SPWI901.SPL"]).abilities[0].effects)

    def test_second_application_changes_nothing(self):
        game = self.game({"SPWI209.SPL": luck(),
                          "SCRL93.ITM": item(fx(147, tg=1, tm=1, res="SPWI209"), description=SR_LUCK_REF)})
        self.install(game)
        self.repeat(game)

    def test_conflicting_or_missing_luck_bonus_is_left_unchanged(self):
        conflict = self.game({"SPWI209.SPL": spell([SplAbility(1, 1, 48, (
            *luck_effects("SPWI209", 300), fx(133, 1, du=60)))], spell_type=1)})
        self.left_unchanged(conflict, "Luck bonuses with different durations", "SPWI209.SPL")
        missing = self.game({"SPWI209.SPL": spell([SplAbility(1, 1, 48, (fx(33, 1, du=300),))],
                                                  spell_type=1)})
        self.left_unchanged(missing, "has no timed Luck bonus", "SPWI209.SPL")

    def test_scs_prebuff_copy_changes_with_the_spell(self):
        cosmetic = {139, 141, 174, 50}
        prebuff = spell([SplAbility(1, 1, 48, tuple(e for e in luck_effects("SPWI209", 300)
                                                    if e.opcode not in cosmetic))], spell_type=1)
        game = self.game({"SPWI209.SPL": luck(), "DWSW209.SPL": prebuff})
        scs_prebuff_map(game, ("WIZARD_LUCK_PREBUFF", "dwsw209"))
        output = self.install(game)
        self.assertIn("Changed: SPWI209 DWSW209", output)
        self.assertEqual(tuple(e for e in luck_effects("SPWI209", 90) if e.opcode not in cosmetic),
                         SplFile.from_bytes(game.snapshot()["DWSW209.SPL"]).abilities[0].effects)


class BlessTests(Fixture):
    def sr_game(self):
        game = self.game({
            "SPPR101.SPL": sr_bless(),
            "C0BLESS.SPL": sr_bless(spell_type=4),                         # exact copy
            "C0NEAR.SPL": sr_bless(effects=bless_effects(300, visual=2)),  # not an exact copy
            "DWSP101.SPL": sr_bless(effects=prebuff_bless_effects(300)),
            # An item that shows the spell's description shows the new one.
            "CBRBLESS.ITM": item(fx(146, 0, 1, tg=1, tm=1, res="SPPR101"), description=SR_BLESS_REF),
        })
        self.prebuff_map = scs_prebuff_map(game, ("WIZARD_SHIELD_PREBUFF", "dwsw114"),
                                           ("CLERIC_BLESS_PREBUFF", "dwsp101"))
        return game

    def assert_bless(self, game, name, build, *, druids=False):
        """Abilities for levels 1-20, each lasting 30 s + 6 s per level, with the old fields."""
        before, after = game.original[name], game.snapshot()[name]
        old, new = SplFile.from_bytes(before), SplFile.from_bytes(after)
        self.assertEqual(tuple(range(1, 21)), tuple(a.required_level for a in new.abilities), name)
        kept = lambda raw: raw[:0x10] + raw[0x12:0x1E] + raw[0x22:]  # noqa: E731
        for ability in new.abilities:
            self.assertEqual(build(bless_duration(ability.required_level)), ability.effects,
                             (name, ability.required_level))
            self.assertEqual(kept(old.abilities[0].raw), kept(ability.raw), name)
        # In the header only the description, the ability count and the effect offset
        # change, and for the resolved spell Spell Revisions' druid exclusion.
        expected = bytearray(before[:0x72])
        if druids:
            struct.pack_into("<I", expected, 0x1E, struct.unpack_from("<I", before, 0x1E)[0] & 0x7FFFFFFF)
        self.assertEqual(bytes(expected[:0x50] + expected[0x54:0x68] + expected[0x6E:0x72]),
                         after[:0x50] + after[0x54:0x68] + after[0x6E:0x72], name)
        self.assertEqual((20, 0x72 + 20 * 0x28), struct.unpack_from("<HI", after, 0x68))

    def test_spell_revisions_bless_lasts_30_seconds_plus_a_round_per_level(self):
        game = self.sr_game()
        prebuff_map = self.prebuff_map.read_bytes()
        output = self.install(game)
        after = game.snapshot()
        self.assertEqual({"SPPR101.SPL", "C0BLESS.SPL", "DWSP101.SPL", "CBRBLESS.ITM"}, self.changed(game))
        self.assertIn("Bless installed", output)
        self.assertIn("Changed: SPPR101 C0BLESS DWSP101", output)
        self.assertIn("Bless: druids can learn and cast it again", output)
        # Only the learnable spell loses the druid exclusion; the copies keep their flags.
        for name, build, druids in (("SPPR101", bless_effects, True), ("C0BLESS", bless_effects, False),
                                    ("DWSP101", prebuff_bless_effects, False)):
            self.assert_bless(game, name + ".SPL", build, druids=druids)
            self.assertEqual(SR_BLESS_NEW, description(game, after[name + ".SPL"]))
        self.assertEqual(0, struct.unpack_from("<I", after["SPPR101.SPL"], 0x1E)[0])
        self.assertEqual(after["SPPR101.SPL"][0x50:0x54], after["CBRBLESS.ITM"][0x54:0x58])
        self.assertEqual(prebuff_map, self.prebuff_map.read_bytes())
        self.uninstall(game)
        self.assertEqual(prebuff_map, self.prebuff_map.read_bytes())

    def test_native_bless_and_a_bless_with_its_own_level_table(self):
        game = self.game({"SPPR101.SPL": spell([bless_ability(1, native_bless_effects(36), NATIVE_BLESS_RAW)],
                                               level=1, desc=NATIVE_BLESS_REF)})
        # A map entry for a file that does not exist is ignored.
        scs_prebuff_map(game, ("CLERIC_BLESS_PREBUFF", "dwsp101"))
        output = self.install(game)
        self.assertIn("Bless is already available to druids; nothing changed", output)
        self.assertEqual({"SPPR101.SPL"}, self.changed(game))
        self.assert_bless(game, "SPPR101.SPL", native_bless_effects)
        self.assertEqual(NATIVE_BLESS_NEW, description(game, game.snapshot()["SPPR101.SPL"]))

        # Relocated, with its own bonuses at levels 3, 10 and 25 and a casting effect.
        cast = (fx(50, tg=1, du=1),)
        own = [bless_ability(3, bless_effects(60)), bless_ability(10, bless_effects(120, amount=2)),
               bless_ability(25, bless_effects(300, amount=3))]
        variant = self.game({"SPELL.IDS": b"IDS V1.0\n1150 CLERIC_BLESS\n",
                             "SPPR150.SPL": spell(own, level=1, casting=cast)})
        self.install(variant)
        result = SplFile.from_bytes(variant.snapshot()["SPPR150.SPL"])
        self.assertEqual(cast, result.casting_effects)
        self.assertEqual((*range(1, 21), 25), tuple(a.required_level for a in result.abilities))
        for ability in result.abilities:
            level = ability.required_level
            # Below level 3 the game used the lowest ability, so the new ones copy it.
            amount = 1 if level < 10 else 2 if level < 25 else 3
            self.assertEqual(bless_effects(bless_duration(level), amount=amount), ability.effects, level)
        self.repeat(variant)

    def test_second_application_changes_nothing(self):
        game = self.sr_game()
        self.install(game)
        self.repeat(game)

    def assert_only_druid_access(self, game, name="SPPR101.SPL"):
        """The duration part left the spell alone; the druid part still applied."""
        expected = bytearray(game.original[name])
        struct.pack_into("<I", expected, 0x1E, struct.unpack_from("<I", expected, 0x1E)[0] & 0x7FFFFFFF)
        self.assertEqual(bytes(expected), game.snapshot()[name])

    def test_conflicting_or_missing_bless_bonus_is_left_unchanged(self):
        conflict = self.game({"SPPR101.SPL": sr_bless(effects=(*bless_effects(300), fx(130, 1, pw=1, du=60))),
                              "SPWI209.SPL": luck()})
        output = self.install(conflict, warnings=True)
        self.assertIn("Chris Revisions: Bless left unchanged: SPPR101.spl (ability for level 1) "
                      "has Bless bonuses with different durations", output)
        self.assertIn("Bless: druids can learn and cast it again", output)
        self.assert_only_druid_access(conflict)
        self.assertEqual({"SPPR101.SPL", "SPWI209.SPL"}, self.changed(conflict))
        # SCS's prebuff copy changes with the spell, so one that cannot stops both.
        missing = self.game({"SPPR101.SPL": sr_bless(),
                             "DWSP101.SPL": sr_bless(effects=(fx(142, 0, 17, pw=1, du=300),))})
        scs_prebuff_map(missing, ("CLERIC_BLESS_PREBUFF", "DWSP101"))
        output = self.install(missing, warnings=True)
        self.assertIn("DWSP101.spl (ability for level 1) has no timed Bless bonus", output)
        self.assert_only_druid_access(missing)
        self.assertEqual(missing.original["DWSP101.SPL"], missing.snapshot()["DWSP101.SPL"])

    def test_unrecognized_description_warns_and_keeps_the_text(self):
        game = self.game({"SPPR101.SPL": sr_bless(desc=GERMAN_REF)})
        output = self.install(game, warnings=True)
        self.assertIn("Bless: the description of SPPR101.spl has different or untranslated text", output)
        after = game.snapshot()["SPPR101.SPL"]
        self.assertEqual(GERMAN_REF, struct.unpack_from("<i", after, 0x50)[0])
        self.assertEqual(bless_effects(150), SplFile.from_bytes(after).abilities[-1].effects)


class DruidAccessTests(Fixture):
    def test_spell_revisions_exclusion_is_lifted_and_restored_on_uninstall(self):
        game = self.game({"SPPR508.SPL": chaotic_commands(0x80000020)})
        output = self.install(game)
        self.assertIn("druids can learn and cast it again", output)
        after = game.snapshot()["SPPR508.SPL"]
        self.assertEqual(0x00000020, struct.unpack_from("<I", after, 0x1E)[0])
        expected = bytearray(game.original["SPPR508.SPL"])
        struct.pack_into("<I", expected, 0x1E, 0x00000020)
        self.assertEqual(bytes(expected), after)
        self.uninstall(game)

    def test_already_available_is_left_alone_and_repeat_is_stable(self):
        game = self.game({"SPELL.IDS": b"IDS V1.0\n1577 CLERIC_CHAOTIC_COMMANDS\n",
                          "SPPR577.SPL": chaotic_commands(0x00000000),
                          "SPPR508.SPL": chaotic_commands(0x80000000)})
        output = self.install(game)
        self.assertIn("already available to druids", output)
        self.assertEqual(set(), self.changed(game))
        self.repeat(game)

    def test_spells_no_priest_or_no_druid_can_learn_are_left_unchanged(self):
        self.left_unchanged(self.game({"SPPR508.SPL": chaotic_commands(0xC0000000)}),
                            "excluded for every priest class", "SPPR508.SPL")
        self.left_unchanged(self.game({"SPPR508.SPL": chaotic_commands(0x80000000, spell_type=1)}),
                            "is not a priest spell", "SPPR508.SPL")


class PrayerRecitationTests(Fixture):
    def test_recitation_replaces_and_blocks_prayer_of_the_same_kind(self):
        game = self.game(prayer_recitation())
        output = self.install(game)
        self.assertIn("(#RECITEG replaces #PRAYERG, #RECITEB replaces #PRAYERB)", output)
        after = game.snapshot()
        self.assertEqual({"SPPR327.SPL", "SPPR422.SPL", "#RECITEG.SPL", "#RECITEB.SPL",
                          "CDID327.ITM", "CDID422.ITM", "CBRCOPY.ITM"}, self.changed(game))
        bonus, penalty = effects_by_level(after["#RECITEG.SPL"]), effects_by_level(after["#RECITEB.SPL"])
        self.assertEqual(RECITATION_LEVELS, tuple(bonus))
        for level in RECITATION_LEVELS:
            d = recitation_duration(level)
            # Spell states stay Recitation's own (no BENEFICIAL_PRAYER).
            self.assertEqual(expected_recitation(recitation_effects("#RECITEG", d, 1), "#PRAYERG", d),
                             bonus[level], level)
            self.assertEqual(expected_recitation(recitation_effects("#RECITEB", d, -1), "#PRAYERB", d),
                             penalty[level], level)
        self.assertEqual(SCS_CASTING, SplFile.from_bytes(after["#RECITEB.SPL"]).casting_effects)
        # Prayer and the casting spells keep their effects; only descriptions change.
        for name in ("SPPR327.SPL", "SPPR422.SPL"):
            self.assertEqual(game.original[name][:0x50] + game.original[name][0x54:],
                             after[name][:0x50] + after[name][0x54:])
        self.assertEqual(PRAYER_NEW, description(game, after["SPPR327.SPL"]))
        self.assertEqual(RECITATION_NEW, description(game, after["SPPR422.SPL"]))
        self.assertEqual(after["SPPR327.SPL"][0x50:0x54], after["CDID327.ITM"][0x54:0x58])
        for scroll in ("CDID422.ITM", "CBRCOPY.ITM"):
            self.assertEqual(after["SPPR422.SPL"][0x50:0x54], after[scroll][0x54:0x58])
        self.uninstall(game)

    def test_refresh_order_saves_and_an_existing_block_are_respected(self):
        d = recitation_duration
        reordered = []
        for level in RECITATION_LEVELS:
            old = recitation_effects("#RECITEG", d(level), 1)
            block = fx(206, -1, pw=4, du=6, res="#PRAYERG")
            reordered.append(SplAbility(level, 4, 337, (old[1], old[0], *old[2:], block)))
        # A block between two refreshes of the payload itself is synchronized too.
        old = recitation_effects("#RECITEG", d(20), 1)
        early = fx(206, -1, pw=4, du=6, res="#PRAYERG")
        reordered[-1] = SplAbility(20, 4, 337, (old[0], early, old[0], *old[1:]))
        game = self.game(prayer_recitation(**{
            "#RECITEG.SPL": spell(reordered, level=4),
            "#RECITEB.SPL": sub_spell(recitation_effects, "#RECITEB", RECITATION_LEVELS, d, -1, 4, save=1)}))
        self.install(game)
        after = game.snapshot()
        bonus, penalty = effects_by_level(after["#RECITEG.SPL"]), effects_by_level(after["#RECITEB.SPL"])
        for ability in reordered:
            level, old = ability.required_level, ability.effects
            if level == 20:
                template = next(e for e in old if e.opcode == 54)
                self.assertEqual((old[0], dataclasses.replace(old[1], duration=d(20)), old[2],
                                  like(template, 321, timing=1, resource="#PRAYERG"), *old[3:]), bonus[20])
                continue
            # The new records follow the payload's own refresh, wherever it is, and
            # the existing block now lasts as long as the bonus.
            self.assertEqual(expected_recitation(old, "#PRAYERG", d(level), lead=2, keep_block=old[-1]),
                             bonus[level], level)
            old_penalty = recitation_effects("#RECITEB", d(level), -1, save=1)
            expected = expected_recitation(old_penalty, "#PRAYERB", d(level))
            self.assertEqual(expected, penalty[level], level)
            # A creature that saves against the penalty keeps Prayer's penalty.
            self.assertEqual({1}, {e.save_type for e in expected[1:3]})

    def test_payloads_that_cannot_be_kept_apart_are_left_unchanged(self):
        mixed = spell([SplAbility(1, 5, 1, (fx(54, 1, tg=3, du=30), fx(54, -1, tg=5, du=30)))],
                      level=3, desc=PRAYER_REF)
        game = self.game({**prayer_recitation(**{"SPPR327.SPL": mixed}), "SPWI209.SPL": luck()})
        self.left_unchanged(game, "Prayer and Recitation left unchanged: SPPR327.spl gives both bonuses "
                            "and penalties", *(n for n in prayer_recitation()))
        self.assertEqual({"SPWI209.SPL"}, self.changed(game))

        casts = [SplAbility(lvl, 4, 337, (*prayer_effects("#PRAYERG", prayer_duration(lvl), 1),
                                          fx(146, 0, 1, tg=1, tm=1, res="CBRPRAY")))
                 for lvl in PRAYER_LEVELS]
        game = self.game(prayer_recitation(**{"#PRAYERG.SPL": spell(casts, level=3),
                                              "CBRPRAY.SPL": spell([SplAbility(1, 1, 1, (fx(50, du=1),))])}))
        self.left_unchanged(game, "#PRAYERG.spl carries Prayer's bonus or penalty and also casts other spells",
                            *(n for n in prayer_recitation()))

        uneven = [SplAbility(lvl, 4, 337, tuple(dataclasses.replace(e, duration=60) if e.opcode == 325 else e
                                                for e in recitation_effects("#RECITEG", recitation_duration(lvl), 1)))
                  for lvl in RECITATION_LEVELS]
        game = self.game(prayer_recitation(**{"#RECITEG.SPL": spell(uneven, level=4)}))
        self.left_unchanged(game, "has no single timed bonus duration", *(n for n in prayer_recitation()))

    def test_other_wording_gets_the_note_and_untranslated_text_is_kept(self):
        game = self.game(prayer_recitation(**{
            "SPPR422.SPL": casting_spell("#RECITEG", "#RECITEB", level=4, desc=OTHER_RECITATION_REF)}))
        output = self.install(game, warnings=True)
        self.assertIn("SPPR422.spl does not have the expected sentence about Prayer; the note was added", output)
        after = game.snapshot()
        self.assertEqual(OTHER_RECITATION + "\n\n" + RECITATION_NOTE, description(game, after["SPPR422.SPL"]))
        self.assertIn("#RECITEG.SPL", self.changed(game))

        game = self.game(prayer_recitation(**{
            "SPPR422.SPL": casting_spell("#RECITEG", "#RECITEB", level=4, desc=GERMAN_RECITATION_REF)}))
        output = self.install(game, warnings=True)
        self.assertIn("SPPR422.spl has different or untranslated text; left unchanged", output)
        after = game.snapshot()
        self.assertEqual(game.original["SPPR422.SPL"], after["SPPR422.SPL"])
        self.assertEqual(game.original["CDID422.ITM"], after["CDID422.ITM"])
        self.assertIn("#RECITEG.SPL", self.changed(game))


if __name__ == "__main__":
    unittest.main()
