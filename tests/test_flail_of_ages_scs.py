"""SCS without Spell Revisions: component 302 on SCS's Haste/Slow layout.

SCS's "Haste and Slow effects cancel" spell tweak (not_sr) moves each Slow into
an instantly cast helper SPL and Haste/Slow into payloads with their own
secondary types. These fixtures rebuild that layout synthetically from field
values read in a CEBG 2.7.3.0 install with SCS 35.21 and without SR; no game
resource is committed. Real WeiDU 249 runs in disposable games only.
"""

from __future__ import annotations

import dataclasses
import subprocess
import unittest

from tests import test_flail_of_ages as baseline
from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, make_spl, read_itm

WINDOW = {"probability1": 32, "probability2": 0}
TIERS = baseline.TIERS
SPELLS = b"2305 WIZARD_HASTE\n2613 WIZARD_IMPROVED_HASTE\n2312 WIZARD_SLOW\n"
SPLSTATES = "".join(f"{value} {name}\n" for value, name in (
    (0, "DUMMY"), (131, "HOLD_IMMUNITY"), (132, "WEB_IMMUNITY"), (133, "ENTANGLE_IMMUNITY"),
    (138, "HASTE_IMMUNITY"), (139, "SLOW_IMMUNITY")))
MSECTYPES = ["None", *(f"Generic{row}" for row in range(1, 11)), "Disabling", "Combination",
             "Non-combat", *(f"Mod{row}" for row in range(14, 24)), "dw_persistent_16", "dw_persistent_40"]


def fx(opcode, **fields):
    return SplEffect(opcode=opcode, target=fields.pop("target", 2), **fields)


def spl(*abilities, sectype=0, casting=()):
    header = bytearray(make_spl(()).header_raw)
    header[0x27] = sectype
    return SplFile(abilities=tuple(abilities), casting_effects=tuple(casting), header_raw=bytes(header)).to_bytes()


def splprot():
    rows = {55: ("0x103", "1", "27"), 77: ("0x104", "150", "151"),
            110: ("0x112", "-1", "1"), 138: ("0x111", "-1", "8")}
    lines = ["2DA V1.0", "0xffff", "STAT VALUE RELATION"]
    lines += [f"{row}_ROW {' '.join(rows.get(row, ('0x10a', '0', '4')))}" for row in range(139)]
    return ("\n".join(lines) + "\n").encode("ascii")


def msectype():
    lines = ["2DA V1.0", "4294967296", "RES_REF"] + [f"{name} -1" for name in MSECTYPES]
    return ("\n".join(lines) + "\n").encode("ascii")


def slow_helper(owner, *, penalty_duration=20, extra=()):
    """SCS's extracted on-hit Slow: refresh, Haste-cancel branch, penalty, Slow, message."""
    return spl(SplAbility(0, 1, 1, (
        fx(221, parameter1=10, parameter2=25, timing=1),
        fx(326, parameter1=0x8000, parameter2=138, duration=1, resource="DW_NEG16"),
        fx(318, parameter1=0x8000, parameter2=138, duration=1, resource=owner),
        fx(54, parameter1=-4, duration=penalty_duration),
        fx(40, duration=20),
        fx(139, parameter1=14000, timing=9),
        *extra,
    )), sectype=25)


def haste_payload(owner, *extra, slots=0):
    return spl(SplAbility(1, 4, 1, (
        fx(324, parameter1=138, parameter2=110, duration=1, resource=owner),
        fx(221, parameter1=10, parameter2=24, timing=1),
        fx(326, parameter1=0x10000, parameter2=138, timing=1, resource="DW_NEG40"),
        fx(318, parameter1=0x10000, parameter2=138, duration=1, resource=owner),
        *extra,
        fx(16, parameter2=slots, duration=48),
        fx(141, parameter2=4, timing=1),
        fx(139, parameter1=14023, timing=1),
        fx(142, parameter2=38, duration=48),
        fx(93, parameter1=4, timing=4, duration=48),
    )), sectype=24)


def haste_shell(owner, payload, *extra):
    return spl(SplAbility(1, 4, 160, (
        fx(324, parameter1=138, parameter2=110, resource=owner),
        fx(146, power=3, parameter2=1, timing=1, resource=payload),
        fx(221, parameter1=10, parameter2=25, timing=1),
        fx(174, timing=1, resource="EFF_M28"),
        *extra,
    )), sectype=13)


RIDERS = (fx(177, parameter1=129, parameter2=4, timing=1, resource="DWTROLAC"),
          fx(12, parameter1=1, parameter2=65536, timing=1))


def hit_effects(name):
    delivery = (fx(146, parameter2=1, timing=1, resource=name, **WINDOW),
                fx(221, parameter1=10, parameter2=24, timing=1, **WINDOW))
    poison = (fx(318, parameter2=55, resource=name), fx(318, parameter2=77, resource=name),
              fx(12, parameter1=1, parameter2=2097152, timing=1))
    return {
        "BLUN14": RIDERS + (fx(324, parameter1=139, parameter2=110, resource=name, **WINDOW),) + delivery,
        "BLUN30C": RIDERS + delivery + poison,
        "BLUN30D": RIDERS + delivery + (fx(12, parameter1=1, parameter2=262144, timing=1),),
        "BLUN30": RIDERS + delivery + (fx(12, parameter1=2, parameter2=262144, timing=1),) + poison,
    }[name]


def equipped(name):
    common = (fx(319, target=2, power=3, parameter2=569, timing=2),
              fx(7, target=1, parameter1=244, parameter2=20, timing=2))
    if name != "BLUN30":
        return common
    # Field values of the +5's equipped list: five spell states, then the
    # Haste blockers 302 removes, between harmful-condition protections.
    states = tuple(fx(328, target=1, parameter2=state, timing=2, resist_dispel=2, special=1)
                   for state in (139, 138, 133, 132, 131))
    return common + states + (
        fx(206, target=1, parameter1=-1, parameter2=16, timing=2, resist_dispel=2, resource="SPIN572"),
        fx(267, target=1, parameter1=14023, parameter2=16, timing=2, resist_dispel=2),
        fx(267, target=1, parameter1=14000, parameter2=40, timing=2, resist_dispel=2),
        fx(240, target=1, parameter2=41, timing=2, resist_dispel=2),
        fx(240, target=1, parameter2=38, timing=2, resist_dispel=2),
        fx(337, target=1, parameter1=-1, parameter2=40, timing=2, resist_dispel=2),
        fx(337, target=1, parameter1=-1, parameter2=16, timing=2, resist_dispel=2),
        fx(146, target=1, parameter2=2, timing=1, resist_dispel=2, resource="#CUREHOL"),
        fx(101, target=1, parameter2=16, timing=2, resist_dispel=2),
        fx(206, target=1, timing=2, resist_dispel=2, resource="FINGLAB"),
        fx(163, target=1, timing=1, resist_dispel=2),
        fx(328, target=1, parameter2=139, timing=2, resist_dispel=2, special=1),
        fx(101, target=1, parameter2=40, timing=2, resist_dispel=2),
        fx(101, target=1, parameter2=175, timing=2, resist_dispel=2),
        fx(169, target=1, parameter2=38, timing=2, resist_dispel=2),
        fx(296, target=1, timing=2, resist_dispel=2, resource="SPMINDAT"),
    )


def haste_blocker(effect):
    return effect.target == 1 and (
        (effect.opcode in (101, 337) and effect.parameter2 == 16)
        or (effect.opcode in (169, 240) and effect.parameter2 == 38)
        or (effect.opcode == 267 and effect.parameter1 == 14023)
        or (effect.opcode == 206 and effect.resource == "SPIN572")
        or (effect.opcode == 328 and effect.special == 1 and effect.parameter2 == 138))


def innate_haste_payload(*extra):
    """SCS's SPIN572A (Potion of Haste, Haste rings): the innate Haste's op16 payload."""
    return spl(SplAbility(1, 1, 1, (
        fx(324, parameter1=138, parameter2=110, duration=1, resource="SPIN572A"),
        fx(221, parameter1=10, parameter2=24, timing=1),
        fx(326, parameter1=0x10000, parameter2=138, timing=1, resource="DW_NEG40"),
        fx(318, parameter1=0x10000, parameter2=138, duration=1, resource="SPIN572A"),
        *extra,
        fx(16, power=3, duration=48),
        fx(93, power=3, parameter1=4, timing=4, duration=48),
    )), sectype=24)


def saved(effect, penalty):
    return dataclasses.replace(effect, save_type=(effect.save_type & ~31) | 2, save_bonus=-penalty)


class FlailScsTests(unittest.TestCase):
    game = baseline.FlailTests.game

    def put(self, game, name, data):
        game.original[name] = data
        (game.override / name).write_bytes(data)

    def scs_game(self):
        game = self.game("vanilla")
        raw = bytearray(64)
        raw[0] = 1
        for name in TIERS:
            before = ItmFile.from_bytes(game.original[name + ".ITM"])
            item = dataclasses.replace(before, global_effects=equipped(name), abilities=(
                ItmAbility(effects=hit_effects(name), raw=bytes(raw[:0x38])),))
            self.put(game, name + ".ITM", item.to_bytes())
            self.put(game, name + ".SPL", slow_helper(name))
        resources = {
            "SPELL.IDS": SPELLS, "SPLSTATE.IDS": SPLSTATES.encode("ascii"),
            "SPLPROT.2DA": splprot(), "MSECTYPE.2DA": msectype(),
            "DW_NEG16.SPL": spl(SplAbility(0, 0, 0, (fx(139, parameter1=310313, timing=1),))),
            "DW_NEG40.SPL": spl(SplAbility(0, 0, 0, (fx(139, parameter1=310314, timing=1),))),
            "SPIN572.SPL": spl(SplAbility(1, 1, 1, (
                fx(324, parameter1=138, parameter2=110, resource="SPIN572"),
                fx(146, power=3, parameter2=1, timing=1, resource="SPIN572A"),
                fx(221, power=3, parameter1=10, parameter2=25, timing=1),
            ))),
            "SPIN572A.SPL": innate_haste_payload(),
            "SPWI305.SPL": haste_shell("SPWI305", "SPWI305A"),
            "SPWI305A.SPL": haste_payload("SPWI305A"),
            "SPWI613.SPL": haste_shell("SPWI613", "SPWI613A",
                                       fx(206, power=6, duration=90, resource="SPWI305")),
            "SPWI613A.SPL": haste_payload("SPWI613A", fx(328, parameter2=138, duration=90, special=1), slots=1),
            "SPWI312.SPL": spl(SplAbility(1, 4, 169, (
                fx(321, timing=1, resource="FINSLOW", save_type=1, save_bonus=-4),
                fx(324, parameter1=139, parameter2=110, resource="SPWI312"),
                fx(146, parameter2=1, timing=1, resource="SPWI312A"),
                fx(221, parameter1=10, parameter2=24, timing=1),
                fx(174, timing=1, resource="EFF_M29", save_type=1, save_bonus=-4),
            )), sectype=11, casting=(fx(146, target=1, parameter1=1, parameter2=1, resource="DW#BLHDA"),)),
            "SPWI312A.SPL": spl(SplAbility(1, 4, 1, tuple(
                dataclasses.replace(effect, save_type=1, save_bonus=-4) if effect.opcode not in (326, 318) else effect
                for effect in (
                    fx(221, parameter1=10, parameter2=25, timing=1),
                    fx(326, parameter1=0x8000, parameter2=138, duration=1, resource="DW_NEG16"),
                    fx(318, parameter1=0x8000, parameter2=138, duration=1, resource="SPWI312A"),
                    fx(40, duration=60), fx(0, parameter1=-4, duration=60), fx(54, parameter1=-4, duration=60),
                    fx(141, parameter2=6, timing=1), fx(139, parameter1=14668, timing=1),
                    fx(142, parameter2=41, duration=60), fx(240, parameter2=38, timing=1),
                ))), sectype=25),
        }
        for name, data in resources.items():
            self.put(game, name, data)
        return game

    def snapshot(self, game):
        return {p.name.upper(): p.read_bytes() for p in game.override.iterdir() if p.is_file()}

    def install(self, game, tp2="setup-chriz-bg-rebalance.tp2", uninstall=False):
        process = subprocess.run([str(baseline.WEIDU), tp2,
                                  "--force-uninstall-list" if uninstall else "--force-install-list", "302",
                                  "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log"],
                                 cwd=game.root, capture_output=True, text=True, timeout=60)
        output = process.stdout + process.stderr
        self.assertEqual(0, process.returncode, output)
        self.assertIn("SUCCESSFULLY REMOVED" if uninstall else "SUCCESSFULLY INSTALLED", output)
        return output

    def assert_rollback(self, game, *diagnostics):
        process, output = game.run()
        self.assertNotEqual(0, process.returncode, output)
        for diagnostic in diagnostics:
            self.assertIn(diagnostic, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(game.original, self.snapshot(game))

    def assert_scs_contract(self, game):
        for name, penalty in TIERS.items():
            before = ItmFile.from_bytes(game.original[name + ".ITM"])
            after = read_itm(game.override / (name + ".ITM"))
            # The parent delivery and Slow's Haste removal share the save; the
            # immunity checks, troll riders and damage stay byte-identical.
            expected = tuple(saved(e, penalty) if e.opcode == 146 or (e.opcode == 221 and e.parameter2 == 24) else e
                             for e in before.abilities[0].effects)
            self.assertEqual([e.to_bytes() for e in expected], [e.to_bytes() for e in after.abilities[0].effects], name)
            self.assertEqual(before.abilities[0].raw[0x22:], after.abilities[0].raw[0x22:])
            kept = tuple(e for e in before.global_effects if name != "BLUN30" or not haste_blocker(e))
            self.assertEqual([e.to_bytes() for e in kept], [e.to_bytes() for e in after.global_effects], name)
            text = baseline.strings(game.lang_tlk)[after.identified_description]
            self.assertEqual(1, text.count(f"(Save vs. Breath at -{penalty} negates)"))
            self.assertNotIn("No Save", text)
        plus5 = read_itm(game.override / "BLUN30.ITM").global_effects
        self.assertEqual([139, 133, 132, 131, 139], [e.parameter2 for e in plus5 if e.opcode == 328])
        # Every helper, payload and table keeps its bytes; nothing is cloned.
        for name, data in game.original.items():
            if not name.endswith(".ITM") or name in ("BLUN14A.ITM", "FOREIGN.ITM"):
                self.assertEqual(data, (game.override / name).read_bytes(), name)
        self.assertEqual(set(game.original), set(self.snapshot(game)))

    def test_scs_layout_saves_parent_delivery_allows_haste_reapplies_and_uninstalls(self):
        game = self.scs_game()
        output = self.install(game)
        # Types come from the payloads: SPWI305/SPWI312's own 13/11 are generic.
        self.assertIn("Haste types |24|, Slow types |25|, Slow penalties |0:0|54:0|", output)
        self.assertIn("Haste checks spell states |138|", output)
        self.assert_scs_contract(game)
        first = self.snapshot(game)
        first_tlk = game.lang_tlk.read_bytes()
        second = game.root / "setup-flail-scs-second.tp2"
        second.write_text((game.root / "setup-chriz-bg-rebalance.tp2").read_text(encoding="utf-8").replace(
            "weidu_external/backup/chriz-bg-rebalance", "weidu_external/backup/flail-scs-second"), encoding="utf-8")
        for uninstall in (False, True):
            self.install(game, second.name, uninstall)
            self.assertEqual(first, self.snapshot(game))
            self.assertEqual(first_tlk, game.lang_tlk.read_bytes())
        self.install(game, uninstall=True)
        self.assertEqual(game.original, self.snapshot(game))
        self.assertEqual(game.texts, baseline.strings(game.lang_tlk)[:len(game.texts)])

    def test_mixed_scs_helpers_still_reject_and_roll_back(self):
        cases = {
            "damage": dict(extra=(fx(12, parameter1=3, parameter2=65536, timing=1),)),
            "inner_save": dict(extra=(fx(40, duration=20, save_type=2, save_bonus=-2),)),
            "penalty_outlasts_slow": dict(penalty_duration=30),
        }
        for label, variation in cases.items():
            with self.subTest(case=label):
                game = self.scs_game()
                self.put(game, "BLUN30D.SPL", slow_helper("BLUN30D", **variation))
                self.assert_rollback(game, "BLUN30D.SPL mixes Slow with other effects")
        with self.subTest(case="area_projectile"):
            game = self.scs_game()
            helper = bytearray(slow_helper("BLUN30D"))
            helper[0x72 + 0x26] = 94
            self.put(game, "BLUN30D.SPL", bytes(helper))
            self.assert_rollback(game, "BLUN30D.SPL mixes Slow")
        with self.subTest(case="cancel_branch_is_not_feedback"):
            game = self.scs_game()
            self.put(game, "DW_NEG16.SPL", spl(SplAbility(0, 0, 0, (
                fx(139, parameter1=310313, timing=1), fx(12, parameter1=5, timing=1)))))
            self.assert_rollback(game, "BLUN14.SPL mixes Slow")

    def test_innate_haste_payload_with_another_effect_keeps_its_immunity(self):
        cases = {
            "damage": (innate_haste_payload(fx(12, parameter1=3, parameter2=65536, timing=1)),
                       r"(?i)BLUN30 keeps its immunity to SPIN572\. .*\(opcode 12\)"),
            "missing": (None, r"(?i)BLUN30 keeps its immunity to SPIN572\. .*missing or cannot be read"),
        }
        for label, (payload, diagnostic) in cases.items():
            with self.subTest(case=label):
                game = self.scs_game()
                if payload is None:
                    (game.override / "SPIN572A.SPL").unlink()
                    del game.original["SPIN572A.SPL"]
                else:
                    self.put(game, "SPIN572A.SPL", payload)
                output = self.install(game)
                self.assertRegex(output, diagnostic)
                before = ItmFile.from_bytes(game.original["BLUN30.ITM"]).global_effects
                after = read_itm(game.override / "BLUN30.ITM").global_effects
                kept = tuple(e for e in before if not haste_blocker(e) or e.opcode == 206)
                self.assertEqual([e.to_bytes() for e in kept], [e.to_bytes() for e in after])

    def test_haste_check_on_an_unconfirmed_spell_state_rolls_back(self):
        game = self.scs_game()
        self.put(game, "SPLSTATE.IDS", SPLSTATES.replace("HASTE_IMMUNITY", "MOD_STATE").encode("ascii"))
        self.assert_rollback(game, "BLUN30 sets spell state 138", "does not name it HASTE_IMMUNITY")

    def test_haste_immunity_that_haste_does_not_check_is_kept(self):
        game = self.scs_game()
        # Without the SPLSTATE=n self-checks in shells and payloads, the spell
        # state does not block Haste; it is kept and the log says why.
        for name in ("SPWI305", "SPWI305A", "SPWI613", "SPWI613A"):
            spell = SplFile.from_bytes(game.original[name + ".SPL"])
            ability = spell.abilities[0]
            kept = tuple(e for e in ability.effects if e.opcode != 324)
            self.put(game, name + ".SPL", dataclasses.replace(
                spell, abilities=(dataclasses.replace(ability, effects=kept),)).to_bytes())
        output = self.install(game)
        self.assertIn("keeps spell state HASTE_IMMUNITY (138)", output)
        plus5 = read_itm(game.override / "BLUN30.ITM").global_effects
        self.assertIn(138, [e.parameter2 for e in plus5 if e.opcode == 328])

    def test_direct_slow_shares_save_with_installed_penalty_and_refresh_only(self):
        game = self.scs_game()
        slow = fx(40, duration=20, **WINDOW)
        penalty = fx(54, parameter1=-4, duration=20, **WINDOW)
        refresh = fx(221, parameter1=10, parameter2=25, timing=1, **WINDOW)
        longer = fx(54, parameter1=-4, duration=30, **WINDOW)
        generic = fx(221, parameter1=10, parameter2=11, timing=1, **WINDOW)
        effects = RIDERS + (refresh, slow, penalty, longer, generic)
        before = ItmFile.from_bytes(game.original["BLUN14.ITM"])
        self.put(game, "BLUN14.ITM", dataclasses.replace(before, abilities=(
            dataclasses.replace(before.abilities[0], effects=effects),)).to_bytes())
        self.install(game)
        after = read_itm(game.override / "BLUN14.ITM").abilities[0].effects
        expected = RIDERS + (saved(refresh, 2), saved(slow, 2), saved(penalty, 2), longer, generic)
        self.assertEqual([e.to_bytes() for e in expected], [e.to_bytes() for e in after])


if __name__ == "__main__":
    unittest.main()
