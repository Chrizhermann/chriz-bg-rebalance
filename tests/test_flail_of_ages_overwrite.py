"""Output contracts for changed inputs, using real WeiDU in disposable games."""
from __future__ import annotations

import dataclasses
import shutil
import struct
import subprocess
import unittest

from tests import test_flail_of_ages as baseline
from tests import test_flail_of_ages_variants as variants
from tests.ie_formats import ItmFile, SplAbility, SplEffect, SplFile, make_spl, read_itm


class FlailOverwriteTests(unittest.TestCase):
    game = baseline.FlailTests.game
    assert_installed = baseline.FlailTests.assert_installed
    put = variants.FlailVariantTests.put
    with_abilities = variants.FlailVariantTests.with_abilities

    def reapply(self, game):
        expected = {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()}
        tlk = game.lang_tlk.read_bytes()
        second = game.root / "setup-flail-overwrite-second.tp2"
        second.write_text((game.root / "setup-chriz-bg-rebalance.tp2").read_text().replace(
            "weidu_external/backup/chriz-bg-rebalance", "weidu_external/backup/flail-overwrite-second"))
        process = subprocess.run([str(baseline.WEIDU), second.name, "--force-install-list", "302",
                                  "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log"],
                                 cwd=game.root, capture_output=True, text=True, timeout=60)
        output = process.stdout + process.stderr
        self.assertEqual(0, process.returncode, output)
        self.assertNotIn("WARNING", output.upper())
        self.assertNotIn("ERROR", output.upper())
        self.assertEqual(expected, {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()})
        self.assertEqual(tlk, game.lang_tlk.read_bytes())

    def test_missing_melee_ability_is_created_and_reapplication_is_identical(self):
        game = self.game("vanilla")
        old = read_itm(game.override / "BLUN14.ITM")
        self.put(game, "BLUN14.ITM", dataclasses.replace(old, abilities=()).to_bytes())
        self.assert_installed(game)
        after = read_itm(game.override / "BLUN14.ITM")
        slow = next(e for e in after.abilities[0].effects if e.opcode == 40)
        self.assertEqual((20, 32, 2, -2), (slow.duration, slow.probability1, slow.save_type, slow.save_bonus))
        self.assertEqual(old.global_effects, after.global_effects)
        self.reapply(game)

    def test_missing_slow_replaces_orphaned_feedback_with_saved_feedback(self):
        game = self.game("vanilla")
        old = read_itm(game.override / "BLUN14.ITM")
        ability = dataclasses.replace(old.abilities[0], effects=tuple(e for e in old.abilities[0].effects if e.opcode != 40))
        self.put(game, "BLUN14.ITM", dataclasses.replace(old, abilities=(ability,)).to_bytes())
        self.assert_installed(game)
        effects = read_itm(game.override / "BLUN14.ITM").abilities[0].effects
        feedback = [e for e in effects if e.opcode == 139 and e.parameter1 == 14000]
        self.assertEqual(1, len(feedback))
        self.assertEqual((32, 2, -2), (feedback[0].probability1, feedback[0].save_type, feedback[0].save_bonus))
        self.reapply(game)

    def test_effects_before_ability_table_remain_writable(self):
        game = self.game("vanilla")
        for name in baseline.TIERS:
            data = game.original[name + ".ITM"]
            ab = struct.unpack_from("<I", data, 0x64)[0]
            fx = struct.unpack_from("<I", data, 0x6a)[0]
            effects = data[fx:]
            reordered = bytearray(data[:0x72] + effects + data[ab:fx])
            struct.pack_into("<I", reordered, 0x64, 0x72 + len(effects))
            struct.pack_into("<I", reordered, 0x6a, 0x72)
            self.put(game, name + ".ITM", bytes(reordered))
        self.assert_installed(game)
        for name, penalty in baseline.TIERS.items():
            data = (game.override / (name + ".ITM")).read_bytes()
            ab = struct.unpack_from("<I", data, 0x64)[0]
            fx = struct.unpack_from("<I", data, 0x6a)[0]
            n, first = struct.unpack_from("<HH", data, ab + 0x1e)
            effects = [SplEffect.from_bytes(data[fx + i * 48:fx + (i + 1) * 48]) for i in range(first, first + n)]
            slow = next(e for e in effects if e.opcode == 40)
            self.assertEqual((2, -penalty), (slow.save_type, slow.save_bonus))
            self.assertIn(SplEffect(opcode=12, target=2, parameter1=2, parameter2=65536, timing=1), effects)
            self.assertGreater(ab, fx)
            if name == "BLUN30":
                first, n = struct.unpack_from("<HH", data, 0x6e)
                equipped = [SplEffect.from_bytes(data[fx + i * 48:fx + (i + 1) * 48]) for i in range(first, first + n)]
                self.assertFalse(any(e.opcode == 101 and e.parameter2 == 16 for e in equipped))
                self.assertTrue(any(e.opcode == 101 and e.parameter2 == 40 for e in equipped))
        self.reapply(game)

    def test_mixed_payload_is_idempotent_and_preserves_foreign_damage(self):
        game = self.game("vanilla")
        damage = SplEffect(opcode=12, target=2, parameter1=17, timing=1, save_type=4, save_bonus=-3)
        slow = SplEffect(opcode=40, target=2, duration=23, save_type=1, save_bonus=6)
        source = make_spl((SplAbility(1, 1, 94, (damage, slow)),)).to_bytes()
        self.put(game, "FXMIXED.SPL", source)
        self.with_abilities(game, (variants.ability(1, (SplEffect(opcode=146, target=2, resource="FXMIXED"),)),))
        self.assert_installed(game)
        link = read_itm(game.override / "BLUN14.ITM").abilities[0].effects[0]
        self.assertEqual(0, link.save_type & 31)
        copied = SplFile.from_bytes((game.override / (link.resource + ".SPL")).read_bytes())
        self.assertEqual((damage, variants.saved(slow)), copied.abilities[0].effects)
        self.assertEqual(source, (game.override / "FXMIXED.SPL").read_bytes())
        self.reapply(game)

    def test_large_unused_tail_does_not_overflow_new_effect_indexes(self):
        game = self.game("vanilla")
        path = game.override / "BLUN14.ITM"
        old = read_itm(path)
        ability = dataclasses.replace(old.abilities[0], effects=tuple(e for e in old.abilities[0].effects if e.opcode != 40))
        padding = bytes(65536 * 0x30) + b"UNUSED TAIL" + bytes(37)
        self.put(game, "BLUN14.ITM", dataclasses.replace(old, abilities=(ability,)).to_bytes() + padding)
        self.assert_installed(game)
        after = read_itm(path)
        slow = next(e for e in after.abilities[0].effects if e.opcode == 40)
        self.assertEqual((2, -2), (slow.save_type, slow.save_bonus))
        self.assertTrue(path.read_bytes().endswith(padding))
        self.reapply(game)

    def test_long_delivery_chain_is_followed_beyond_the_former_limit(self):
        game = self.game("vanilla")
        slow = SplEffect(opcode=40, target=2, duration=20)
        for i in range(37, -1, -1):
            effect = slow if i == 37 else SplEffect(opcode=146, target=2, resource=f"CHAIN{i + 1:02}", timing=1)
            self.put(game, f"CHAIN{i:02}.SPL", make_spl((SplAbility(1, 1, 0, (effect,)),)).to_bytes())
        self.with_abilities(game, (variants.ability(1, (SplEffect(opcode=146, target=2, resource="CHAIN00"),)),))
        self.assert_installed(game)
        effects = read_itm(game.override / "BLUN14.ITM").abilities[0].effects
        self.assertEqual(1, len(effects))
        self.assertEqual((2, -2), (effects[0].save_type, effects[0].save_bonus))

    def test_other_game_language_keeps_text_and_writes_mechanics(self):
        game = self.game("vanilla")
        game.language = "de_de"
        german = game.root / "lang/de_de/dialog.tlk"
        german.parent.mkdir()
        shutil.copy2(game.lang_tlk, german)
        game.lang_tlk = german
        before = german.read_bytes()
        self.assert_installed(game)
        self.assertEqual(before, german.read_bytes())
        slow = next(e for e in read_itm(game.override / "BLUN14.ITM").abilities[0].effects if e.opcode == 40)
        self.assertEqual((2, -2), (slow.save_type, slow.save_bonus))

    def test_truncated_link_does_not_roll_back_other_items(self):
        game = self.game("vanilla")
        self.put(game, "DAMAGED.SPL", b"SPL V1  ")
        self.with_abilities(game, (variants.ability(1, (SplEffect(opcode=146, target=2, resource="DAMAGED"),)),))
        self.assert_installed(game)
        effects = read_itm(game.override / "BLUN14.ITM").abilities[0].effects
        slow = next(e for e in effects if e.opcode == 40)
        self.assertEqual((2, -2), (slow.save_type, slow.save_bonus))
        self.assertEqual(b"SPL V1  ", (game.override / "DAMAGED.SPL").read_bytes())


if __name__ == "__main__":
    unittest.main()
