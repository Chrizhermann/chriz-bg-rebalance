"""Quarantined potion prototype in disposable games using real WeiDU.

The fixture TP2 exists only inside each temporary game. There are no released
potion components. These research regressions intentionally expose known draft
failures; a passing resource model would not prove native delivery preservation.
No game executable, save, or installed-game directory is used by this module.
"""
from __future__ import annotations

import dataclasses
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import EffV2, ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, TwoDA
from tests.test_emotion_hope_courage_installer import _write_key_and_bif
from tests.test_flail_of_ages import strings, tlk


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
PROTOTYPE = "research/prototypes/potion-uniqueness"
LIBRARY = PROTOTYPE + "/potion_uniqueness.tpa"
RESEARCH_TP2 = "setup-cbr_potion_research.tp2"
RESEARCH_SETUP = f"""BACKUP ~cbr_potion_research/backup~
AUTHOR ~Disposable research fixture; not a released mod~
VERSION ~research-only~
BEGIN ~Research potion draft: all unique~ DESIGNATED 330
REQUIRE_PREDICATE (GAME_IS ~bgee bg2ee eet~) ~Research fixture requires an EE game.~
REQUIRE_PREDICATE NOT (MOD_IS_INSTALLED ~{RESEARCH_TP2}~ 331) ~Choose one research policy.~
ACTION_IF MOD_IS_INSTALLED ~{RESEARCH_TP2}~ 331 BEGIN FAIL ~Choose one research policy.~ END
INCLUDE ~{LIBRARY}~
LAF cbr_install_potion_uniqueness INT_VAR genius_exception = 0 END
BEGIN ~Research potion draft: Genius exception~ DESIGNATED 331
REQUIRE_PREDICATE (GAME_IS ~bgee bg2ee eet~) ~Research fixture requires an EE game.~
REQUIRE_PREDICATE NOT (MOD_IS_INSTALLED ~{RESEARCH_TP2}~ 330) ~Choose one research policy.~
ACTION_IF MOD_IS_INSTALLED ~{RESEARCH_TP2}~ 330 BEGIN FAIL ~Choose one research policy.~ END
INCLUDE ~{LIBRARY}~
LAF cbr_install_potion_uniqueness INT_VAR genius_exception = 1 END
"""
ORIGINAL_TEXT = ["Unrelated shared text.", "Flacon localise", "Original potion description."]
SPLPROT = b"2DA V1.0\n0\nSTAT VALUE RELATION\n0 0x10a 0 4\n"


def fx(opcode, p1=0, p2=0, *, duration=120, timing=0, resource="", **kwargs):
    return SplEffect(opcode=opcode, target=1, parameter1=p1, parameter2=p2,
                     duration=duration, timing=timing, resource=resource,
                     resist_dispel=2, **kwargs)


def ability(effects, *, target=5, charges=1, location=3):
    raw = bytearray(56)
    raw[0], raw[2], raw[12] = 3, location, target
    raw[13] = 1
    struct.pack_into("<H", raw, 34, charges)
    struct.pack_into("<H", raw, 36, 1)  # remove exhausted item
    struct.pack_into("<H", raw, 42, 1)  # no projectile
    return ItmAbility(tuple(effects), icon="POTICON", raw=bytes(raw))


def potion(effects=(), *, abilities=None, global_effects=(), category=9, name=1):
    raw = bytearray(114)
    struct.pack_into("<H", raw, 0x1C, category)
    struct.pack_into("<H", raw, 0x38, 37)  # inventory stack size is out of scope
    struct.pack_into("<I", raw, 0x34, 177)  # price is out of scope
    return ItmFile(abilities=tuple(abilities or [ability(effects)]),
                   global_effects=tuple(global_effects), header_raw=bytes(raw),
                   unidentified_name=name, identified_name=name,
                   unidentified_description=2, identified_description=2).to_bytes()


def spell(effects, *, target=1, casting=()):
    return SplFile((SplAbility(1, target, 1, tuple(effects)),),
                   casting_effects=tuple(casting)).to_bytes()


def resources():
    return {
        "POTN36.ITM": potion((fx(90, 40, duration=1260), fx(92, 40, duration=1260))),
        "POTN29.ITM": potion((fx(19, 4, duration=900),)),
        "POTN37.ITM": potion((fx(19, 3, duration=43200), fx(15, 3, duration=43200))),
        "POTN09.ITM": potion((fx(18, 110, 2, duration=600), fx(54, 90, 2, duration=600))),
        "POTN41.ITM": potion((fx(18, 120, 2, duration=240), fx(54, 80, 2, duration=240),
                                fx(90, 120, 2, duration=240))),
        "POTN14.ITM": potion((fx(16, duration=300),)),
        "HEALING.ITM": potion((fx(17, 8, timing=1, duration=0),)),
        "ANTIDOTE.ITM": potion((fx(11, timing=1, duration=0),)),
        "PERMANNT.ITM": potion((fx(19, 1, timing=1, duration=0),)),
        "HARMFUL.ITM": potion((fx(19, -1, duration=600),)),
        "QUEST.ITM": potion((fx(187, timing=1, duration=0, resource="QUESTVAR"),)),
        "EQUIP.ITM": potion((fx(90, 40),), category=3),
        "FOREIGN.SPL": spell((fx(90, 40),)),
    }


class PotionGame:
    def __init__(self, root, data, *, game="bg2ee", biff_only=(), tlk_bytes=None):
        self.root = root
        self.override = root / "override"
        self.override.mkdir(parents=True)
        (root / RESEARCH_TP2).write_text(RESEARCH_SETUP, encoding="ascii")
        libraries = root / PROTOTYPE
        libraries.mkdir(parents=True)
        for name in ("potion_uniqueness.tpa", "potion_identity.tpa"):
            shutil.copy2(ROOT / PROTOTYPE / name, libraries / name)
        indexed = [(name, "IDS", b"IDS V1.0\n") for name in ("SPELL", "STATS", "KIT", "SPLSTATE")]
        indexed.append(("OH1000" if game == "bgee" else "OH6000", "ARE", b"synthetic game marker"))
        if game == "eet":
            (self.override / "EET.FLAG").write_bytes(b"synthetic EET marker")
        for name, blob in data.items():
            if name.upper() in biff_only:
                resref, extension = name.rsplit(".", 1)
                indexed.append((resref, extension, blob))
            else:
                (self.override / name).write_bytes(blob)
        if "SPLPROT.2DA" not in {name.upper() for name in data}:
            (self.override / "SPLPROT.2DA").write_bytes(SPLPROT)
        self.bif = _write_key_and_bif(root, tuple(indexed))
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(tlk(ORIGINAL_TEXT) if tlk_bytes is None else tlk_bytes)
        (root / "dialog.tlk").write_bytes(self.tlk.read_bytes())
        self.before = self.snapshot()
        self.resources = data
        self.stable = {p: p.read_bytes() for p in (self.bif, root / "chitin.key", root / "dialog.tlk")}

    def snapshot(self):
        return {p.name.upper(): p.read_bytes() for p in self.override.iterdir() if p.is_file()}

    def run(self, *components, target=RESEARCH_TP2, uninstall=False):
        return subprocess.run([str(WEIDU), target, "--game", str(self.root),
                               "--force-uninstall-list" if uninstall else "--force-install-list",
                               *map(str, components), "--language", "0", "--use-lang", "en_us",
                               "--no-exit-pause", "--quick-log"], cwd=self.root,
                              capture_output=True, text=True, timeout=90, check=False)

    def install_sr_marker(self):
        # WeiDU owns even the synthetic log: do not fabricate installed history.
        folder = self.root / "spell_rev"
        folder.mkdir()
        (folder / "setup-spell_rev.tp2").write_text(
            "BACKUP ~spell_rev/backup~\nAUTHOR ~synthetic test~\n"
            "BEGIN ~Synthetic SR provider~ DESIGNATED 0\n", encoding="ascii")
        return self.run(0, target="spell_rev/setup-spell_rev.tp2")

    def repeat(self, genius_exception):
        folder = self.root / "CBR_POTION_REPEAT"
        folder.mkdir()
        path = folder / "setup-cbr_potion_repeat.tp2"
        path.write_text(
            "BACKUP ~CBR_POTION_REPEAT/backup~\nAUTHOR ~synthetic test~\n"
            "BEGIN ~Repeat the potion transformation~ DESIGNATED 0\n"
            f"INCLUDE ~{LIBRARY}~\n"
            f"LAF cbr_install_potion_uniqueness INT_VAR genius_exception = {int(genius_exception)} END\n",
            encoding="ascii")
        return self.run(0, target="CBR_POTION_REPEAT/setup-cbr_potion_repeat.tp2")


@dataclasses.dataclass
class ActiveRecord:
    effect: SplEffect | EffV2
    source: str
    applied: int
    expires: int
    source_type: int = 1


class PotionGraphModel:
    """Independent, deliberately small single-recipient resource interpreter.

    Tests feed it the actual installed ITM/SPL/EFF graph. It models immediate
    op146 delivery, op177 delegation with inherited source, source-specific
    op321 removal, and per-incoming-effect resource admission. Opcode206 guards
    spell sources;318 guards both spell and item sources. The current-stats,
    sequential admission branch is modeled; queued/multiplayer ordering and the
    engine's previous-stats branch are not. Original timed
    effects are a ledger, not reimplemented HP/THAC0/engine arithmetic. Unknown
    delivery or conditional guards raise instead of producing a false pass.
    This is synthetic control-flow evidence, never native-engine acceptance.
    """
    def __init__(self, blobs):
        self.blobs = {k.upper(): v for k, v in blobs.items()}
        self.now = 0
        self.active = []
        self.native_events = []
        self.blocked = []
        self.doses = 0

    def advance(self, now):
        if now < self.now:
            raise ValueError("model time cannot move backwards")
        self.now = now
        self.active = [r for r in self.active if r.expires > now]

    def records(self, opcode):
        return [r for r in self.active if r.effect.opcode == opcode]

    def additive(self, opcode):
        values = self.records(opcode)
        if any(r.effect.parameter2 != 0 for r in values):
            raise ValueError("only additive arithmetic is modeled")
        return sum(r.effect.parameter1 for r in values)

    def successful_dispel(self):
        """Remove eligible records; do not simulate level rolls or success odds."""
        self.active = [r for r in self.active
                       if not (getattr(r.effect, "resist_dispel", getattr(r.effect, "flags", 0)) & 1)]

    def use(self, item, index=0):
        self.doses += 1  # use attempt; native inventory consumption is not modeled
        parsed = ItmFile.from_bytes(self.blobs[item.upper() + ".ITM"])
        self._effects(parsed.abilities[index].effects, item.upper(), (), source_type=2)

    def cast(self, resource, chain=()):
        key = resource.upper()
        if key in chain or len(chain) >= 16:
            raise ValueError(f"model cyclic delivery: {chain!r} -> {key}")
        parsed = SplFile.from_bytes(self.blobs[key + ".SPL"])
        self._effects(parsed.casting_effects, key, chain + (key,))
        self._effects(parsed.ability_for_level(1).effects, key, chain + (key,))

    def _effects(self, effects, source, chain, source_type=1):
        for e in effects:
            # Native AddEffect calls CheckAdd for each incoming effect before
            # ResolveEffect. A self-source guard applied earlier in this very
            # helper can therefore reject later alias guards. A cast-entry
            # check incorrectly treats all helper records as one admission.
            if any(r.effect.resource.upper() == source.upper() and
                   (r.effect.opcode == 318 or (r.effect.opcode == 206 and source_type == 1))
                   for r in self.active):
                self.blocked.append((self.now, source.upper(), e.opcode, e.resource))
                continue
            if e.probability1 != 100 or e.probability2 != 0 or e.save_type:
                raise ValueError("model does not guess probability/save outcomes")
            if e.opcode == 146:
                if e.parameter2 not in (0, 1) or e.timing not in (0, 1):
                    raise ValueError("unsupported model cast mode/timing")
                self.cast(e.resource, chain)
            elif e.opcode == 177:
                key = e.resource.upper() + ".EFF"
                if key in chain:
                    raise ValueError("model EFF cycle")
                child = EffV2.from_bytes(self.blobs[key])
                # Native UseEFF copies the carrier's effective timing/duration;
                # raw EFF duration is not the lifetime of this invocation.
                child = dataclasses.replace(child, timing=e.timing, duration=e.duration)
                self._effects((child,), source, chain + (key,), source_type=source_type)
            elif e.opcode == 321:
                self.active = [r for r in self.active if r.source != e.resource.upper()]
            elif e.opcode in (206, 318):
                if e.opcode == 318:
                    table = TwoDA.from_text(self.blobs["SPLPROT.2DA"].decode("ascii"))
                    row = table.rows[e.parameter2][1]
                    if tuple(int(v, 0) for v in row) != (0x10A, 0, 4):
                        raise ValueError("conditional op318 is outside this model")
                if e.timing not in (0, 10) or e.duration <= 0:
                    raise ValueError("model expects a finite unconditional potion guard")
                lifetime = e.duration / 15 if e.timing == 10 else e.duration
                self.active.append(ActiveRecord(e, source, self.now, self.now + lifetime, source_type))
            elif e.opcode in (232, 248, 249, 272, 326, 333):
                raise ValueError(f"unmodeled delivery opcode {e.opcode}")
            else:
                self.native_events.append((self.now, source, e))
                if e.timing in (0, 10) and e.duration > 0:
                    lifetime = e.duration / 15 if e.timing == 10 else e.duration
                    self.active.append(ActiveRecord(e, source, self.now, self.now + lifetime, source_type))


class PotionResearchInstallerTests(unittest.TestCase):
    def game(self, data=None, **kwargs):
        holder = tempfile.TemporaryDirectory(prefix="cbr-potion-synthetic-")
        self.addCleanup(holder.cleanup)
        return PotionGame(Path(holder.name), resources() if data is None else data, **kwargs)

    def installed(self, result):
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
        return transcript

    def stable(self, game):
        for path, blob in game.stable.items():
            self.assertEqual(blob, path.read_bytes(), path.name)
        self.assertEqual(ORIGINAL_TEXT, strings(game.tlk)[:len(ORIGINAL_TEXT)])

    def preserves_item_metadata(self, before, after):
        old, new = ItmFile.from_bytes(before), ItmFile.from_bytes(after)
        old_header, new_header = bytearray(old.header_raw), bytearray(new.header_raw)
        # Effect packing and an accurately appended description may change.
        old_header[0x54:0x58] = new_header[0x54:0x58]
        old_header[0x64:0x72] = new_header[0x64:0x72]
        self.assertEqual(old_header, new_header, "unowned item header fields changed")
        self.assertEqual([e.to_bytes() for e in old.global_effects],
                         [e.to_bytes() for e in new.global_effects])
        self.assertEqual(len(old.abilities), len(new.abilities))
        for source, result in zip(old.abilities, new.abilities):
            raw = bytearray(source.raw)
            raw[30:34] = result.raw[30:34]
            self.assertEqual(raw, result.raw, "charges/target/projectile/ability metadata changed")

    def test_research_fixture_variants_exist_without_an_sr_dependency(self):
        setup = RESEARCH_SETUP
        blocks = re.split(r"(?m)^BEGIN\s+", setup)[1:]
        selected = [b for b in blocks if re.search(r"\bDESIGNATED\s+(330|331)\b", b)]
        self.assertEqual(2, len(selected))
        for block in selected:
            self.assertNotIn("MOD_IS_INSTALLED ~spell_rev", block)
            self.assertIn("REQUIRE_PREDICATE", block)

    def test_research_fixture_variants_cannot_accumulate_or_replace_each_other(self):
        for first, second in ((330, 331), (331, 330)):
            with self.subTest(first=first, second=second):
                game = self.game()
                self.installed(game.run(first))
                before = game.snapshot()
                before_log = (game.root / "WeiDU.log").read_text()
                result = game.run(second)
                output = result.stdout + result.stderr
                self.assertIn("SKIPPING", output)
                self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                self.assertEqual(before, game.snapshot())
                log = (game.root / "WeiDU.log").read_text()
                self.assertRegex(log, rf"#0\s+#{first}\b")
                self.assertNotRegex(log, rf"#0\s+#{second}\b")
                self.assertNotIn("SUCCESSFULLY UNINSTALLED", output)
                self.assertTrue(before_log)

    def test_requesting_both_variants_in_one_batch_retains_only_first(self):
        # WeiDU executes native declaration order, regardless of argument order.
        # 330 is the first attempted component in both fresh-game requests.
        for request in ((330, 331), (331, 330)):
            with self.subTest(request=request):
                expected, batch = self.game(), self.game()
                self.installed(expected.run(330))
                result = batch.run(*request)
                output = result.stdout + result.stderr
                self.assertEqual(expected.snapshot(), batch.snapshot(), output)
                log = (batch.root / "WeiDU.log").read_text()
                self.assertRegex(log, r"#0\s+#330\b")
                self.assertNotRegex(log, r"#0\s+#331\b")
                self.assertNotIn("SUCCESSFULLY UNINSTALLED", output)
                self.assertRegex(output, r"SKIPPING|NOT INSTALLED DUE TO ERRORS")

    def test_instant_permanent_harmful_and_nonpotion_resources_remain_exact(self):
        for component in (330, 331):
            with self.subTest(component=component):
                game = self.game()
                self.installed(game.run(component))
                after = game.snapshot()
                for name in ("HEALING.ITM", "ANTIDOTE.ITM", "PERMANNT.ITM", "HARMFUL.ITM",
                             "QUEST.ITM", "EQUIP.ITM", "FOREIGN.SPL"):
                    self.assertEqual(game.resources[name], after[name], name)
                self.stable(game)

    def test_sr_presence_does_not_change_potion_policy(self):
        plain, sr = self.game(), self.game()
        self.installed(sr.install_sr_marker())
        self.installed(plain.run(330))
        self.installed(sr.run(330))
        self.assertEqual(plain.snapshot(), sr.snapshot())

    def test_enhanced_edition_and_eet_research_entry_points(self):
        for edition in ("bgee", "bg2ee", "eet"):
            with self.subTest(edition=edition):
                game = self.game(game=edition)
                self.installed(game.run(330))
                self.assertNotEqual(game.resources["POTN36.ITM"], game.snapshot()["POTN36.ITM"])
                self.stable(game)

    def test_genius_exception_is_specific_and_all_variant_covers_it(self):
        all_unique, exception = self.game(), self.game()
        self.installed(all_unique.run(330))
        self.installed(exception.run(331))
        normal, excepted = all_unique.snapshot(), exception.snapshot()
        self.assertNotEqual(all_unique.resources["POTN29.ITM"], normal["POTN29.ITM"])
        self.assertEqual(exception.resources["POTN29.ITM"], excepted["POTN29.ITM"],
                         "Genius should retain its original use/effects under the exception")
        # Mind Focusing also raises INT. That alone must not earn the exception.
        for name in ("POTN36.ITM", "POTN37.ITM", "POTN09.ITM", "POTN41.ITM"):
            self.assertNotEqual(exception.resources[name], excepted[name], name)
            self.preserves_item_metadata(exception.resources[name], excepted[name])

    def test_graph_model_refreshes_safe_bonus_without_accumulating_or_touching_spell(self):
        game = self.game()
        self.installed(game.run(330))
        model = PotionGraphModel(game.snapshot())
        model.cast("FOREIGN")
        foreign = model.records(90)[0]
        model.use("POTN36")
        model.advance(100)
        model.use("POTN36")
        self.assertEqual(80, model.additive(90))  # unrelated spell + one potion
        self.assertIn(foreign, model.active)
        owned = [r for r in model.records(90) if r.source != "FOREIGN"]
        self.assertEqual([(100, 1360)], [(r.applied, r.expires) for r in owned])
        self.assertEqual(40, model.additive(92))
        model.advance(1261)
        self.assertEqual(40, model.additive(90))
        model.advance(1360)
        self.assertEqual([], model.records(90))
        self.assertEqual([], model.records(92))

    def test_graph_model_hp_repeat_is_ignored_without_extension_and_types_overlap(self):
        game = self.game()
        self.installed(game.run(330))
        model = PotionGraphModel(game.snapshot())
        model.use("POTN09")
        model.advance(10)
        model.use("POTN41")
        before = [(r.effect.canonical(), r.source, r.applied, r.expires)
                  for r in model.active if r.effect.opcode not in (206, 318)]
        model.advance(20)
        model.use("POTN09")
        model.use("POTN41")
        after = [(r.effect.canonical(), r.source, r.applied, r.expires)
                 for r in model.active if r.effect.opcode not in (206, 318)]
        self.assertEqual(before, after)
        self.assertEqual({(110, 0, 600), (120, 10, 250)},
                         {(r.effect.parameter1, r.applied, r.expires) for r in model.records(18)})
        self.assertEqual(2, sum(e.opcode == 18 for _, _, e in model.native_events))
        model.advance(590)
        model.use("POTN09")
        self.assertEqual([600], [r.expires for r in model.records(18)])
        model.advance(601)
        model.use("POTN09")
        self.assertEqual([1201], [r.expires for r in model.records(18)])
        self.assertEqual(3, sum(e.opcode == 18 for _, _, e in model.native_events))
        # Damage/healing calculations and physical charge decrement deliberately
        # remain outside the model; native payload and charge bytes are tested.

    def test_graph_model_resolves_guard_predicate_and_preserves_native_effect_order(self):
        data = resources()
        data["SPLPROT.2DA"] = b"2DA V1.0\n0\nSTAT VALUE RELATION\n0 1 777 1\n1 0x10a 0 4\n"
        first, last = fx(139, 1234, timing=1, duration=0), fx(139, 5678, timing=1, duration=0)
        data["POTN09.ITM"] = potion((first, fx(18, 110, 2, duration=600), last,
                                     fx(54, 90, 2, duration=600)))
        game = self.game(data)
        self.installed(game.run(330))
        model = PotionGraphModel(game.snapshot())
        model.use("POTN09")
        self.assertEqual([(139, 1234), (18, 110), (139, 5678), (54, 90)],
                         [(e.opcode, e.parameter1) for _, _, e in model.native_events
                          if e.opcode in (139, 18, 54)])
        model.advance(40)
        model.use("POTN09")
        self.assertEqual(1, len(model.records(18)))
        self.assertEqual([600], [r.expires for r in model.records(18)])

    def test_graph_model_semantic_enemy_and_mod_copies_share_potion_family(self):
        data = resources()
        copied = ItmFile.from_bytes(data["POTN36.ITM"])
        original = copied.abilities[0]
        data["DW#PTN36.ITM"] = dataclasses.replace(copied, abilities=(
            dataclasses.replace(original, effects=tuple(reversed(original.effects))),)).to_bytes()
        data["MODHERO.ITM"] = data["POTN09.ITM"]
        game = self.game(data)
        self.installed(game.run(330))
        model = PotionGraphModel(game.snapshot())
        model.use("POTN36")
        model.use("POTN09")
        model.advance(10)
        model.use("DW#PTN36")
        model.use("MODHERO")
        self.assertEqual(40, model.additive(90))
        self.assertEqual(40, model.additive(92))
        self.assertEqual([1270], [r.expires for r in model.records(90)])
        self.assertEqual([600], [r.expires for r in model.records(18)])
        self.assertEqual(1, sum(e.opcode == 18 for _, _, e in model.native_events))

    def test_graph_model_presentation_changes_do_not_create_another_bonus_family(self):
        data = resources()
        intro = fx(139, 1001, timing=1, duration=0)
        middle = fx(174, timing=1, duration=0, resource="SOUND01")
        final = fx(139, 1002, timing=1, duration=0)
        data["FANFARE.SPL"] = spell((middle,))
        call = fx(146, 0, 1, timing=1, duration=0, resource="FANFARE")
        data["MODTHIEF.ITM"] = potion((intro, fx(92, 40, duration=1260), call,
                                        fx(90, 40, duration=1260), final))
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        self.assertEqual(data["FANFARE.SPL"], after["FANFARE.SPL"])
        self.preserves_item_metadata(data["MODTHIEF.ITM"], after["MODTHIEF.ITM"])
        model = PotionGraphModel(after)
        model.use("POTN36")
        model.advance(10)
        model.use("MODTHIEF")
        self.assertEqual(40, model.additive(90))
        self.assertEqual(40, model.additive(92))
        self.assertEqual([1270], [r.expires for r in model.records(90)])
        self.assertEqual([intro.to_bytes(), fx(92, 40, duration=1260).to_bytes(),
                          middle.to_bytes(), fx(90, 40, duration=1260).to_bytes(), final.to_bytes()],
                         [e.to_bytes() for now, _, e in model.native_events if now == 10])

    def test_graph_model_renamed_linked_spell_and_eff_copies_share_family(self):
        data = resources()
        for item, child, eff in (("POTN36", "PAYLOADA", "BONUSA"),
                                 ("MODTHIEF", "PAYLOADB", "BONUSB")):
            data[item + ".ITM"] = potion((
                fx(146, 0, 1, timing=1, duration=0, resource=child),))
            data[child + ".SPL"] = spell((fx(90, 40, duration=1260),
                fx(177, 0, 2, timing=0, duration=1260, resource=eff)))
            data[eff + ".EFF"] = EffV2(opcode=92, target=1, parameter1=40,
                                         timing=1, duration=0, flags=2).to_bytes()
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        for name in ("PAYLOADA.SPL", "PAYLOADB.SPL", "BONUSA.EFF", "BONUSB.EFF"):
            self.assertEqual(data[name], after[name], name)
        model = PotionGraphModel(after)
        model.use("POTN36")
        model.advance(10)
        model.use("MODTHIEF")
        self.assertEqual(40, model.additive(90))
        self.assertEqual(40, model.additive(92))
        self.assertEqual([1270], [r.expires for r in model.records(92)])

    def test_graph_model_scs_family_without_hp_record_still_uses_hp_ignore_policy(self):
        for first, second in (("POTN09", "DW#PTN09"), ("DW#PTN09", "POTN09")):
            with self.subTest(first=first):
                data = resources()
                data["DW#PTN09.ITM"] = potion((fx(54, 2, duration=600),))
                game = self.game(data)
                self.installed(game.run(330))
                model = PotionGraphModel(game.snapshot())
                model.use(first)
                before = [(r.effect.canonical(), r.source, r.applied, r.expires)
                          for r in model.active]
                model.advance(100)
                model.use(second)
                self.assertEqual(before, [(r.effect.canonical(), r.source, r.applied, r.expires)
                                          for r in model.active])
                model.advance(601)
                model.use("POTN09")
                self.assertEqual([1201], [r.expires for r in model.records(18)])

    def test_research_alias_guards_cover_whole_hp_family_after_either_first_dose(self):
        data = resources()
        data["DW#PTN09.ITM"] = data["POTN09.ITM"]
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        members = ("DW#PTN09", "POTN09")
        helpers = {e.resource.upper() for item in members
                   for a in ItmFile.from_bytes(after[item + ".ITM"]).abilities
                   for e in a.effects if e.opcode == 146}
        self.assertGreaterEqual(len(helpers), 2)
        for first, second in (members, tuple(reversed(members))):
            with self.subTest(first=first):
                model = PotionGraphModel(after)
                model.use(first)
                # Known draft defect: its own guard may reject the later alias
                # guards in this very helper. This requirement must stay red
                # until the implementation actually protects the whole family.
                self.assertEqual(helpers, {r.effect.resource.upper() for r in model.records(318)})
                model.advance(10)
                model.use(second)
                self.assertEqual([(0, 600)], [(r.applied, r.expires) for r in model.records(18)])

    def test_model_rechecks_resource_admission_for_each_incoming_effect(self):
        for targets, admitted in ((["HELPERA", "HELPERB"], {"HELPERA"}),
                                  (["HELPERB", "HELPERA"], {"HELPERA", "HELPERB"})):
            with self.subTest(order=targets):
                data = {"SPLPROT.2DA": SPLPROT, "HELPERA.SPL": spell(tuple(
                    fx(318, duration=600, resource=target) for target in targets))}
                model = PotionGraphModel(data)
                model.cast("HELPERA")
                # This checks the oracle against the native per-effect rule;
                # accepting only the self guard is not a correct potion policy.
                self.assertEqual(admitted, {r.effect.resource for r in model.records(318)})
                self.assertEqual(int(targets[0] == "HELPERA"), len(model.blocked))

    def test_model_318_admits_item_source_check_but_206_is_spell_only(self):
        for opcode, expected in ((318, 0), (206, 1)):
            with self.subTest(opcode=opcode):
                data = {"SPLPROT.2DA": SPLPROT,
                        "WARD.SPL": spell((fx(opcode, duration=600, resource="POTN09"),)),
                        "POTN09.ITM": potion((fx(18, 110, 2, duration=600),))}
                model = PotionGraphModel(data)
                model.cast("WARD")
                model.use("POTN09")
                self.assertEqual(expected, len(model.records(18)))

    def test_shared_native_self_blocking_child_retains_native_no_refresh(self):
        data = resources()
        cast = fx(146, 0, 1, timing=1, duration=0, resource="MTNATIVE")
        data["POTN36.ITM"] = potion((cast,))
        data["DW#PTN36.ITM"] = potion((cast,))
        data["MTNATIVE.SPL"] = spell((fx(90, 40, duration=300),
            fx(92, 40, duration=300), fx(142, p2=16, duration=540),
            fx(206, duration=300, resource="MTNATIVE")))
        game = self.game(data)
        output = self.installed(game.run(330))
        after = game.snapshot()
        self.assertIn("native blocker", output)
        for name in ("POTN36.ITM", "DW#PTN36.ITM", "MTNATIVE.SPL"):
            self.assertEqual(data[name], after[name], name)
        model = PotionGraphModel(after)
        model.use("POTN36")
        model.advance(10)
        model.use("DW#PTN36")
        self.assertEqual(40, model.additive(90))
        self.assertEqual([300], [r.expires for r in model.records(90)])
        model.advance(301)
        model.use("DW#PTN36")
        self.assertEqual([601], [r.expires for r in model.records(90)])

    def test_family_alias_bypassing_native_self_blocker_is_diagnosed_and_rolled_back(self):
        data = resources()
        data["POTN36.ITM"] = potion((fx(146, 0, 1, timing=1, duration=0, resource="MTNATIVE"),))
        data["DW#PTN36.ITM"] = resources()["POTN36.ITM"]
        data["MTNATIVE.SPL"] = spell((fx(90, 40, duration=1260),
            fx(92, 40, duration=1260), fx(206, duration=1260, resource="MTNATIVE")))
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("CBR_POTION_IDENTITY", output)
        self.assertIn("MTNATIVE", output)
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_conditional_owned_bonus_requires_adapter_and_rolls_back(self):
        cases = {
            "chance": (fx(90, 40, duration=1260, probability1=50),),
            "save": (fx(90, 40, duration=1260, save_type=4),),
            "hp_chance": (fx(18, 110, 2, duration=600, probability1=50),),
            "first_link": (fx(146, 0, 1, timing=1, duration=0, resource="CHANCE", probability1=50),
                           fx(92, 40, duration=1260)),
        }
        for name, effects in cases.items():
            with self.subTest(case=name):
                data = resources()
                data["POTN36.ITM"] = potion(effects)
                data["CHANCE.SPL"] = spell((fx(90, 40, duration=1260),))
                game = self.game(data)
                result = game.run(330)
                output = result.stdout + result.stderr
                self.assertNotEqual(0, result.returncode, output)
                self.assertIn("CBR_POTION_CONDITIONAL", output)
                self.assertIn("POTN36", output)
                self.assertEqual(game.before, game.snapshot())
                self.stable(game)

    def test_graph_model_genius_and_proven_copy_stack_only_under_exception(self):
        for component, expected_int in ((330, 4), (331, 12)):
            with self.subTest(component=component):
                data = resources()
                data["GENIUS.ITM"] = data["POTN29.ITM"]
                game = self.game(data)
                self.installed(game.run(component))
                model = PotionGraphModel(game.snapshot())
                model.use("POTN29")
                model.use("GENIUS")
                model.use("POTN29")
                self.assertEqual(expected_int, model.additive(19))

    def test_graph_model_ir_vocalize_and_unknown_int_are_not_genius_by_filename(self):
        data = resources()
        data["GENIUS.ITM"] = data["POTN29.ITM"]
        # Item Revisions repurposes POTN29. Its unrelated mod-added timed bonus
        # makes mistaken resref-only exemption observable, even if Vocalize's
        # native boolean effect already has unique behavior by itself.
        data["POTN29.ITM"] = potion((fx(48, duration=600), fx(54, 1, duration=600)))
        game = self.game(data)
        self.installed(game.run(331))
        model = PotionGraphModel(game.snapshot())
        for _ in range(2):
            model.use("GENIUS")
            model.use("POTN29")
            model.use("POTN37")
        # The canonical Genius anchor was repurposed. A name and an INT-only
        # fingerprint alone cannot prove this unknown item is actually Genius.
        self.assertEqual(7, model.additive(19))  # one unknown INT + one Mind Focusing
        self.assertEqual(3, model.additive(15))
        self.assertEqual(1, model.additive(54))

    def test_second_application_is_byte_exact(self):
        for component in (330, 331):
            with self.subTest(component=component):
                game = self.game()
                self.installed(game.run(component))
                before = game.snapshot()
                self.installed(game.repeat(component == 331))
                self.assertEqual(before, game.snapshot())
                self.stable(game)

    def test_multiple_reordered_abilities_keep_charges_targets_and_foreign_records(self):
        data = resources()
        pick, lock = fx(90, 40, duration=1260), fx(92, 40, duration=1260)
        presentation = fx(139, 2, timing=1, duration=0)
        foreign = fx(12, 3, 65536, timing=1, duration=0, save_type=4, save_bonus=-2,
                     probability1=65, probability2=20)
        global_effect = fx(319, p2=454, timing=2, duration=0)
        data["POTN36.ITM"] = potion(abilities=(
            ability((presentation, lock, pick, foreign), charges=3),
            ability((foreign, pick, presentation, lock), charges=7),
        ), global_effects=(global_effect,))
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        self.preserves_item_metadata(data["POTN36.ITM"], after["POTN36.ITM"])
        # Presentation and adverse native data must not disappear merely because
        # the effect package is repacked into private resources.
        for sentinel in (presentation, foreign):
            self.assertIn(sentinel.to_bytes(), b"".join(after.values()))
        self.stable(game)

    def test_biff_only_input_and_override_input_have_identical_result(self):
        data = resources()
        loose = self.game(data)
        biff = self.game(data, biff_only=("POTN36.ITM",))
        self.installed(loose.run(330))
        self.installed(biff.run(330))
        self.assertEqual(loose.snapshot(), biff.snapshot())
        self.stable(biff)

    def test_linked_spl_eff_payload_preserves_shared_originals_and_other_users(self):
        data = resources()
        cast = fx(146, 0, 1, timing=1, duration=0, resource="MTLINK")
        data["POTN36.ITM"] = potion((cast,))
        data["MTLINK.SPL"] = spell((
            fx(177, 0, 2, timing=0, duration=1260, resource="MTFX"),
            fx(92, 40, duration=1260),
        ))
        data["MTFX.EFF"] = EffV2(opcode=90, target=1, parameter1=40,
                                 timing=1, duration=0, flags=2).to_bytes()
        data["FOREIGN.SPL"] = spell((cast,))
        data["EQUIP.ITM"] = potion((cast,), category=3)
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        self.assertNotEqual(data["POTN36.ITM"], after["POTN36.ITM"])
        self.preserves_item_metadata(data["POTN36.ITM"], after["POTN36.ITM"])
        for name in ("MTLINK.SPL", "MTFX.EFF", "FOREIGN.SPL", "EQUIP.ITM"):
            self.assertEqual(data[name], after[name], f"shared original changed: {name}")
        model = PotionGraphModel(after)
        model.use("POTN36")
        model.advance(10)
        model.use("POTN36")
        self.assertEqual(40, model.additive(90))
        self.assertEqual([1270], [r.expires for r in model.records(90)])
        self.stable(game)

    def test_instant_eff_carrier_preserves_permanent_gain_despite_raw_eff_timer(self):
        data = resources()
        data["PERMEFF.ITM"] = potion((fx(177, 0, 2, timing=1, duration=0, resource="RAWTIMED"),))
        data["RAWTIMED.EFF"] = EffV2(opcode=19, target=1, parameter1=1,
                                      timing=0, duration=900, flags=2).to_bytes()
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        for name in ("PERMEFF.ITM", "RAWTIMED.EFF"):
            self.assertEqual(data[name], after[name], name)
        model = PotionGraphModel(after)
        model.use("PERMEFF")
        model.use("PERMEFF")
        self.assertEqual([], model.records(19))
        self.assertEqual([1, 1], [e.timing for _, _, e in model.native_events if e.opcode == 19])

    def test_one_shared_eff_is_classified_per_carrier_lifetime(self):
        data = resources()
        data["POTN36.ITM"] = potion((fx(177, 0, 2, duration=1260, resource="SHARED"),))
        data["PERMEFF.ITM"] = potion((fx(177, 0, 2, timing=1, duration=0, resource="SHARED"),))
        data["SHARED.EFF"] = EffV2(opcode=90, target=1, parameter1=40,
                                    timing=1, duration=0, flags=2).to_bytes()
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        self.assertEqual(data["PERMEFF.ITM"], after["PERMEFF.ITM"])
        self.assertEqual(data["SHARED.EFF"], after["SHARED.EFF"])
        model = PotionGraphModel(after)
        model.use("POTN36")
        model.advance(10)
        model.use("POTN36")
        model.use("PERMEFF")
        self.assertEqual(40, model.additive(90))
        self.assertEqual([1270], [r.expires for r in model.records(90)])
        self.assertEqual([1], [e.timing for _, source, e in model.native_events
                               if source == "PERMEFF" and e.opcode == 90])

    def test_filtered_eff_carrier_requires_adapter_and_rolls_back(self):
        data = resources()
        data["POTN36.ITM"] = potion((fx(177, 2, 2, duration=1260, resource="FILTERED"),
                                     fx(92, 40, duration=1260)))
        data["FILTERED.EFF"] = EffV2(opcode=90, target=1, parameter1=40,
                                      timing=1, duration=0, flags=2).to_bytes()
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("CBR_POTION", output)
        self.assertRegex(output.lower(), r"filter|conditional")
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_existing_timed_hp_eff_carrier_requires_adapter_and_rolls_back(self):
        data = resources()
        carrier = fx(177, 0, 2, duration=600, resource="HPBONUS")
        data["POTN09.ITM"] = potion((carrier, fx(54, 90, 2, duration=600)))
        data["HPBONUS.EFF"] = EffV2(opcode=18, target=1, parameter1=110, parameter2=2,
                                     timing=1, duration=0, flags=2).to_bytes()
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("CBR_POTION_HP", output)
        self.assertIn("HPBONUS", output)
        self.assertRegex(output.lower(), r"first-use|first.process|adapter")
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_hp_ignore_deadline_excludes_longer_presentation_effect(self):
        data = resources()
        icon = fx(142, p2=16, duration=540)
        data["POTN09.ITM"] = potion((fx(18, 110, 2, duration=300), icon))
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        self.assertIn(icon.to_bytes(), b"".join(after.values()))
        model = PotionGraphModel(after)
        model.use("POTN09")
        model.advance(100)
        model.use("POTN09")
        self.assertEqual([(0, 300)], [(r.applied, r.expires) for r in model.records(18)])
        self.assertEqual(1, sum(e.opcode == 18 for _, _, e in model.native_events))
        model.advance(301)
        model.use("POTN09")
        self.assertEqual([(301, 601)], [(r.applied, r.expires) for r in model.records(18)])
        self.assertTrue(all(e.duration == 540 for _, _, e in model.native_events if e.opcode == 142))

    def test_model_successful_dispel_removes_hp_guard_with_bonus_and_allows_reuse(self):
        for eligibility in (1, 3):
            with self.subTest(resist_dispel=eligibility):
                data = resources()
                effects = (fx(18, 110, 2, duration=300), fx(54, 90, 2, duration=300))
                data["POTN09.ITM"] = potion(tuple(dataclasses.replace(e, resist_dispel=eligibility)
                                                   for e in effects))
                game = self.game(data)
                self.installed(game.run(330))
                model = PotionGraphModel(game.snapshot())
                model.use("POTN09")
                self.assertEqual(1, len(model.records(18)))
                self.assertTrue(model.records(318))
                model.advance(100)
                model.successful_dispel()
                self.assertEqual([], model.records(18))
                self.assertEqual([], model.records(318))
                model.use("POTN09")
                self.assertEqual([(100, 400)], [(r.applied, r.expires) for r in model.records(18)])

    def test_eff_dispatch_and_internal_conditions_require_adapter_and_roll_back(self):
        cases = {
            "independent_spell_source": EffV2(opcode=146, target=1, parameter2=1,
                timing=1, duration=0, resource="PAYLOAD"),
            "conditional_bonus": EffV2(opcode=90, target=1, parameter1=40,
                timing=1, duration=0, probability1=50),
            "nested_filter": EffV2(opcode=177, target=1, parameter1=2, parameter2=2,
                timing=1, duration=0, resource="INNER"),
        }
        for name, effect in cases.items():
            with self.subTest(case=name):
                data = resources()
                timing, duration = (1, 0) if name == "independent_spell_source" else (0, 1260)
                data["POTN36.ITM"] = potion((fx(177, 0, 2, timing=timing,
                                                duration=duration, resource="OUTER"),))
                data["OUTER.EFF"] = effect.to_bytes()
                data["INNER.EFF"] = EffV2(opcode=90, target=1, parameter1=40,
                                            timing=1, duration=0).to_bytes()
                data["PAYLOAD.SPL"] = spell((fx(90, 40, duration=1260),))
                game = self.game(data)
                result = game.run(330)
                output = result.stdout + result.stderr
                self.assertNotEqual(0, result.returncode, output)
                self.assertIn("CBR_POTION", output)
                self.assertIn("OUTER", output)
                self.assertEqual(game.before, game.snapshot())
                self.stable(game)

    def test_native_flat_and_haste_bonuses_retain_original_effects(self):
        data = resources()
        data["FLATSTAT.ITM"] = potion((fx(19, 18, 1, duration=600),))
        game = self.game(data)
        self.installed(game.run(330))
        after = game.snapshot()
        for name in ("POTN14.ITM", "FLATSTAT.ITM"):
            self.assertEqual(data[name], after[name], name)

    def test_unanchored_identical_mod_potions_report_identity_ambiguity_and_rollback(self):
        data = resources()
        bonus = fx(90, 33, duration=333)
        data["MODONE.ITM"] = potion((bonus,))
        data["MODTWO.ITM"] = potion((fx(139, 1234, timing=1, duration=0), bonus))
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("CBR_POTION_IDENTITY", output)
        self.assertIn("MODONE.ITM", output)
        self.assertIn("MODTWO.ITM", output)
        self.assertRegex(output.lower(), r"anchor|copy-versus-distinct|provenance")
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_distinct_unanchored_mod_potions_keep_separate_bonuses(self):
        data = resources()
        data["MODONE.ITM"] = potion((fx(90, 33, duration=333),))
        data["MODTWO.ITM"] = potion((fx(90, 17, duration=555),))
        game = self.game(data)
        self.installed(game.run(330))
        model = PotionGraphModel(game.snapshot())
        model.use("MODONE")
        model.use("MODTWO")
        model.advance(10)
        model.use("MODONE")
        self.assertEqual(50, model.additive(90))
        self.assertEqual({(33, 343), (17, 555)},
                         {(r.effect.parameter1, r.expires) for r in model.records(90)})

    def test_cyclic_potion_delivery_is_diagnosed_without_partial_outputs(self):
        data = resources()
        data["POTN36.ITM"] = potion((fx(146, 0, 1, timing=1, duration=0, resource="CYCLEA"),))
        data["CYCLEA.SPL"] = spell((fx(146, 0, 1, timing=1, duration=0, resource="CYCLEB"),))
        data["CYCLEB.SPL"] = spell((fx(146, 0, 1, timing=1, duration=0, resource="CYCLEA"),))
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertRegex(output.lower(), r"cycl|recurs|depth")
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_relevant_truncated_resource_fails_and_rolls_back(self):
        data = resources()
        # Header identifies a potion, but its required ability table is corrupt.
        malformed = bytearray(data["POTN36.ITM"])
        struct.pack_into("<I", malformed, 0x64, len(malformed) + 100)
        data["POTN36.ITM"] = bytes(malformed)
        game = self.game(data)
        result = game.run(330)
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn("POTN36", output.upper())
        self.assertEqual(game.before, game.snapshot())
        self.stable(game)

    def test_synthetic_uninstall_restores_original_override(self):
        for component in (330, 331):
            with self.subTest(component=component):
                game = self.game()
                self.installed(game.run(component))
                result = game.run(component, uninstall=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(game.before, game.snapshot())
                self.stable(game)


if __name__ == "__main__":
    unittest.main()
