"""Synthetic alternate-layout contracts for component 302, not live acceptance.

Reuse the existing disposable WeiDU game without inheriting its TestCase: doing
so would discover all baseline tests a second time.  Expected bytes describe the
owned change, independently of the production matcher's implementation.
"""

from __future__ import annotations

import dataclasses
import subprocess
import unittest

from tests import test_flail_of_ages as baseline
from tests.ie_formats import EffV2, ItmAbility, ItmFile, SplAbility, SplEffect, make_spl, read_itm


def saved(effect):
    """The only fields owned by the +3 Slow save rebalance."""
    return dataclasses.replace(effect, save_type=(effect.save_type & ~31) | 2, save_bonus=-2)


def ability(kind, effects, *, marker=0):
    raw = bytearray(0x38)
    raw[0] = kind
    raw[0x10] = marker
    raw[0x35] = 0xA7  # An unowned field must survive rebuilding the ability table.
    return ItmAbility(effects=tuple(effects), raw=bytes(raw))


class FlailVariantTests(unittest.TestCase):
    game = baseline.FlailTests.game
    assert_installed = baseline.FlailTests.assert_installed

    def put(self, game, name, data):
        """Record a fixture's pre-install bytes for exact uninstall assertions."""
        game.original[name] = data
        (game.override / name).write_bytes(data)

    def with_abilities(self, game, abilities, name="BLUN14.ITM"):
        before = ItmFile.from_bytes(game.original[name])
        changed = dataclasses.replace(before, abilities=tuple(abilities))
        self.put(game, name, changed.to_bytes())
        return ItmFile.from_bytes(game.original[name])

    def assert_item_bytes(self, game, expected, name="BLUN14.ITM"):
        actual = (game.override / name).read_bytes()
        # Updating the owned description may allocate a fresh TLK string.  No
        # other item-header/ability/effect byte is exempted from this comparison.
        expected = dataclasses.replace(expected, identified_description=read_itm(game.override / name).identified_description)
        self.assertEqual(expected.to_bytes(), actual, name)

    def assert_foreign_and_sources_unchanged(self, game, *names):
        for name in ("FOREIGN.ITM", "BLUN14A.ITM", *names):
            self.assertEqual(game.original[name], (game.override / name).read_bytes(), name)
        for path, data in game.stable.items():
            self.assertEqual(data, path.read_bytes(), str(path))

    def assert_no_helpers_created(self, game):
        # Resource identity is gameplay semantics: cloning can bypass another
        # mod's resource immunities or split self-refresh/exclusion identities.
        self.assertEqual(set(game.original), {p.name.upper() for p in game.override.iterdir() if p.is_file()})

    def test_multiple_proc_windows_reordered_effects_extra_melee_and_magic(self):
        for variant in ("vanilla", "sr"):
            with self.subTest(variant=variant):
                game = self.game(variant)
                slow_a = SplEffect(opcode=40, target=2, power=7, duration=17, probability1=68, probability2=29, save_type=0x1000001, save_bonus=4, special=9)
                slow_b = dataclasses.replace(slow_a, duration=31, probability1=91, probability2=73, save_type=0x2000004, save_bonus=-1)
                feedback_a = dataclasses.replace(slow_a, opcode=139, parameter1=14000, timing=9, duration=0)
                feedback_b = dataclasses.replace(slow_b, opcode=139, parameter1=14000, timing=9, duration=0)
                foreign_feedback = dataclasses.replace(feedback_a, probability1=22, probability2=11)
                foreign_damage = SplEffect(opcode=12, target=2, parameter1=23, parameter2=65536, timing=1, probability1=83, probability2=9, save_type=4, save_bonus=5, special=0x102)
                effects = [feedback_b, foreign_damage, slow_a, foreign_feedback, slow_b, feedback_a]
                owned = {0, 2, 4, 5}
                if variant == "sr":
                    # The two matching Haste-removal companions belong to their
                    # own Slow proc windows; a third window remains foreign.
                    effects.extend((dataclasses.replace(slow_b, opcode=221, parameter1=9, parameter2=20), dataclasses.replace(slow_a, opcode=221, parameter1=9, parameter2=20), dataclasses.replace(slow_a, opcode=221, parameter2=20, probability1=22, probability2=11)))
                    owned.update((6, 7))
                else:
                    # In non-SR the same opcode/window is not evidence that
                    # this foreign secondary-type removal belongs to Slow.
                    effects.append(dataclasses.replace(slow_a, opcode=221, parameter1=9, parameter2=20))
                extra_slow = dataclasses.replace(slow_a, probability1=47, probability2=4)
                magic_slow = dataclasses.replace(slow_a, duration=99)
                before = self.with_abilities(game, (ability(1, effects, marker=3), ability(3, (magic_slow, foreign_damage), marker=8), ability(1, (foreign_damage, extra_slow), marker=4)))
                self.assert_installed(game)
                expected_abilities = (
                    dataclasses.replace(before.abilities[0], effects=tuple(saved(effect) if index in owned else effect for index, effect in enumerate(before.abilities[0].effects))),
                    before.abilities[1],
                    dataclasses.replace(before.abilities[2], effects=(foreign_damage, saved(extra_slow))),
                )
                self.assert_item_bytes(game, dataclasses.replace(before, abilities=expected_abilities))
                self.assert_foreign_and_sources_unchanged(game)

    def test_pure_shared_spl_keeps_identity_and_reapplies_and_uninstalls(self):
        game = self.game()
        slow = SplEffect(opcode=40, target=2, power=4, duration=26, probability1=73, probability2=17, special=6)
        damage = SplEffect(opcode=12, target=2, parameter1=11, parameter2=131072, timing=1, probability1=87, probability2=9, save_type=4, save_bonus=1, special=0x102)
        helper = make_spl((SplAbility(1, 1, 0, (slow,)), SplAbility(12, 1, 1, (dataclasses.replace(slow, duration=39),))))
        self.put(game, "FXSHARED.SPL", helper.to_bytes())
        link = SplEffect(opcode=146, target=2, power=6, timing=1, duration=5, probability1=68, probability2=29, resource="FXSHARED", save_type=0x1000004, save_bonus=3, special=12)
        before = self.with_abilities(game, (ability(1, (damage, link)),))
        self.with_abilities(game, (ability(1, (link, damage)),), "FOREIGN.ITM")
        first_snapshot = self.assert_installed(game)
        self.assert_item_bytes(game, dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=(damage, saved(link))),)))
        self.assert_foreign_and_sources_unchanged(game, "FXSHARED.SPL")
        self.assert_no_helpers_created(game)

        # A second identity forces the production patch to see already-patched
        # resources, rather than WeiDU considering the component installed.
        second = game.root / "setup-flail-variants-second.tp2"
        second.write_text((game.root / "setup-chriz-bg-rebalance.tp2").read_text(encoding="utf-8").replace("weidu_external/backup/chriz-bg-rebalance", "weidu_external/backup/flail-variants-second"), encoding="utf-8")
        first_tlk = game.lang_tlk.read_bytes()
        for uninstall in (False, True):
            process = subprocess.run([str(baseline.WEIDU), second.name, "--force-uninstall-list" if uninstall else "--force-install-list", "302", "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log"], cwd=game.root, capture_output=True, text=True, timeout=40)
            output = process.stdout + process.stderr
            self.assertEqual(0, process.returncode, output)
            self.assertIn("SUCCESSFULLY REMOVED" if uninstall else "SUCCESSFULLY INSTALLED", output)
            self.assertEqual(first_snapshot, {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()})
            self.assertEqual(first_tlk, game.lang_tlk.read_bytes())
        process, output = game.run(uninstall=True)
        self.assertEqual(0, process.returncode, output)
        self.assertIn("SUCCESSFULLY REMOVED", output)
        self.assertEqual(game.original, {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()})
        self.assertEqual(game.texts, baseline.strings(game.lang_tlk)[:len(game.texts)])

    def test_direct_eff_v2_slow_preserves_unknown_bytes_and_delivery(self):
        game = self.game("vanilla")
        raw = bytearray(0x110)
        raw[0x80:0x88] = b"SENTINEL"
        slow = EffV2(opcode=40, target=2, power=5, parameter1=7, parameter2=3, duration=34, probability1=79, probability2=23, special=17, flags=0xC4, raw=bytes(raw))
        self.put(game, "FXDIRECT.EFF", slow.to_bytes())
        damage = SplEffect(opcode=12, target=2, parameter1=21, timing=1)
        link = SplEffect(opcode=177, target=2, power=3, parameter2=2, timing=1, probability1=83, probability2=19, resource="FXDIRECT", save_type=8, save_bonus=7)
        before = self.with_abilities(game, (ability(1, (link, damage)),))
        self.with_abilities(game, (ability(1, (link, damage)),), "FOREIGN.ITM")
        self.assert_installed(game)
        self.assert_item_bytes(game, dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=(saved(link), damage)),)))
        self.assert_foreign_and_sources_unchanged(game, "FXDIRECT.EFF")
        self.assert_no_helpers_created(game)

    def test_repeated_shared_helper_retains_self_and_external_resource_identity(self):
        game = self.game("vanilla")
        slow = SplEffect(opcode=40, target=2, duration=28, probability1=87, probability2=13)
        self_references = tuple(SplEffect(opcode=opcode, target=2, timing=1, resource="FXSELF", parameter1=5, parameter2=7, probability1=73, probability2=11, special=3) for opcode in (321, 206, 318, 324))
        helper = make_spl((SplAbility(1, 1, 1, (self_references[0], slow, *self_references[1:])),))
        self.put(game, "FXSELF.SPL", helper.to_bytes())
        link_a = SplEffect(opcode=146, target=2, timing=1, resource="FXSELF", probability1=69, probability2=27, save_type=0x1000004, save_bonus=3)
        link_b = dataclasses.replace(link_a, probability1=89, probability2=3, save_type=0x2000008, save_bonus=7)
        before = self.with_abilities(game, (ability(1, (link_a,), marker=3), ability(1, (link_b,), marker=9)))
        foreign = self.with_abilities(game, (ability(1, (link_a,)),), "FOREIGN.ITM")
        external_immunity = SplEffect(opcode=206, target=1, resource="FXSELF", timing=2)
        self.put(game, "FOREIGN.ITM", dataclasses.replace(foreign, global_effects=(*foreign.global_effects, external_immunity)).to_bytes())
        self.assert_installed(game)
        expected_item = dataclasses.replace(before, abilities=tuple(dataclasses.replace(old, effects=(saved(link),)) for old, link in zip(before.abilities, (link_a, link_b))))
        self.assert_item_bytes(game, expected_item)
        self.assert_foreign_and_sources_unchanged(game, "FXSELF.SPL")
        self.assert_no_helpers_created(game)

    def test_pure_nested_eff_to_spl_to_eff_keeps_all_helpers_and_gates_only_parent(self):
        game = self.game()
        leaf = EffV2(opcode=40, target=2, duration=43, probability1=59, probability2=13, flags=0x14)
        self.put(game, "FXLEAF.EFF", leaf.to_bytes())
        nested_link = SplEffect(opcode=177, target=2, parameter2=2, timing=1, duration=8, probability1=91, probability2=2, resource="FXLEAF")
        direct_slow = SplEffect(opcode=40, target=2, duration=16, probability1=89, probability2=7)
        damage = SplEffect(opcode=12, target=2, parameter1=31, timing=1, save_type=8, save_bonus=-1)
        middle = make_spl((SplAbility(1, 1, 0, (nested_link, direct_slow)),))
        self.put(game, "FXMIDDLE.SPL", middle.to_bytes())
        root = EffV2(opcode=146, target=2, power=7, timing=1, duration=3, probability1=81, probability2=5, resource="FXMIDDLE", flags=0x24)
        self.put(game, "FXROOT.EFF", root.to_bytes())
        link = SplEffect(opcode=177, target=2, parameter2=2, timing=1, probability1=69, probability2=27, resource="FXROOT", save_type=16, save_bonus=2)
        before = self.with_abilities(game, (ability(1, (link, damage)),))
        self.with_abilities(game, (ability(1, (link, damage)),), "FOREIGN.ITM")
        self.assert_installed(game)
        self.assert_item_bytes(game, dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=(saved(link), damage)),)))
        self.assert_foreign_and_sources_unchanged(game, "FXROOT.EFF", "FXMIDDLE.SPL", "FXLEAF.EFF")
        self.assert_no_helpers_created(game)

    def test_mixed_slow_and_damage_helper_rejects_and_rolls_back_without_cloning(self):
        game = self.game("vanilla")
        slow = SplEffect(opcode=40, target=2, duration=26, probability1=73, probability2=17)
        damage = SplEffect(opcode=12, target=2, parameter1=11, parameter2=131072, timing=1, probability1=87, probability2=9, save_type=4, save_bonus=1, special=0x102)
        helper = make_spl((SplAbility(1, 1, 0, (damage, slow)),))
        self.put(game, "FXMIXED.SPL", helper.to_bytes())
        link = SplEffect(opcode=146, target=2, timing=1, resource="FXMIXED", probability1=68, probability2=29)
        self.with_abilities(game, (ability(1, (damage, link)),))
        self.with_abilities(game, (ability(1, (link, damage)),), "FOREIGN.ITM")
        original_tlk = game.lang_tlk.read_bytes()
        process, output = game.run()
        self.assertNotEqual(0, process.returncode, output)
        self.assertIn("mixes Slow with other effects", output)
        self.assertIn("FXMIXED", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(game.original, {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()})
        self.assertEqual(original_tlk, game.lang_tlk.read_bytes())
        self.assert_foreign_and_sources_unchanged(game, "FXMIXED.SPL")

    def test_localized_and_multiple_slow_description_lines_do_not_abort(self):
        descriptions = (
            "Unberuehrte Geschichte.\r\nKampf: Verlangsamt das Ziel 20 Sekunden (kein Rettungswurf).\r\nSchaden: 1W6+4",
            "Original lore remains.\r\nCombat abilities:\r\n- 33% chance of slowing target for 20 seconds (No Save)\r\n- 17% chance of slowing target for 31 seconds (No Saving Throw)\r\nDamage: 1d6+4\r\nA foreign paragraph about slow travel remains.",
        )
        for index, description in enumerate(descriptions):
            with self.subTest(description=index):
                game = self.game("vanilla")
                game.texts[1] = description
                game.lang_tlk.write_bytes(baseline.tlk(game.texts))
                before = read_itm(game.override / "BLUN14.ITM")
                if index == 1:
                    second_slow = SplEffect(opcode=40, target=2, duration=31, probability1=17)
                    before = self.with_abilities(game, (dataclasses.replace(before.abilities[0], effects=(*before.abilities[0].effects, second_slow)),))
                self.assert_installed(game)
                expected = dataclasses.replace(before, abilities=(dataclasses.replace(before.abilities[0], effects=tuple(saved(e) if e.opcode == 40 or (e.opcode == 139 and e.parameter1 == 14000) else e for e in before.abilities[0].effects)),))
                self.assert_item_bytes(game, expected)
                text = baseline.strings(game.lang_tlk)[read_itm(game.override / "BLUN14.ITM").identified_description]
                if index == 0:
                    self.assertIn("Unberuehrte Geschichte.", text)
                    self.assertIn("Schaden: 1W6+4", text)
                else:
                    for line in ("Original lore remains.", "Damage: 1d6+4", "A foreign paragraph about slow travel remains."):
                        self.assertIn(line, text)
                    self.assertNotRegex(text, r"(?i)no sav(?:e|ing throw)")
                    self.assertEqual(2, text.count("(Save vs. Breath at -2 negates)"))
                self.assert_foreign_and_sources_unchanged(game)

    def test_no_slow_warns_without_claiming_a_nerf_or_altering_foreign_effects(self):
        game = self.game("vanilla")
        damage = SplEffect(opcode=12, target=2, parameter1=19, parameter2=65536, timing=1, probability1=76, probability2=11, save_type=4, save_bonus=3)
        unrelated = SplEffect(opcode=139, target=2, parameter1=12345, timing=1, probability1=33)
        before = self.with_abilities(game, (ability(1, (damage, unrelated)),))
        process, output = game.run()
        self.assertEqual(0, process.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertRegex(output, r"(?im)^.*BLUN14[^\r\n]*(?:no|missing|not found)[^\r\n]*Slow[^\r\n]*$")
        self.assertEqual(before.to_bytes(), (game.override / "BLUN14.ITM").read_bytes())
        text = baseline.strings(game.lang_tlk)[read_itm(game.override / "BLUN14.ITM").identified_description]
        self.assertEqual(game.texts[1], text)
        self.assertNotIn("Save vs. Breath", text)
        self.assert_foreign_and_sources_unchanged(game)


if __name__ == "__main__":
    unittest.main()
