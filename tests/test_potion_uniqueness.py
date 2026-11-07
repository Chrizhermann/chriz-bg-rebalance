"""Potion uniqueness (330/331) and the Heroism family (332).

Real WeiDU on disposable synthetic games only. The fixtures mirror the shapes
seen in an installed EET game (vanilla/SCS potion copies, a native refresh, a
leading self-guard, Bardic Wonders' Heroism spells) plus Item Revisions-style
linked spells, so the tests cover what can break at install time: which
resources change, that original effects survive, the reserved spell state, and
a clean uninstall.
"""
from __future__ import annotations

import struct
import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import IdsFile, ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, make_spl
from tests.test_cloud_forms import Game, ROOT, WEIDU
from tests.test_flail_of_ages import strings

OLD = ("This spell and Heroism are non-cumulative with each other, and the more "
       "recently applied spell will remove the effects of the other.")
NEW = ("This spell, Heroism and the Potion of Heroism are non-cumulative: while one "
       "of them is active on a creature, the others have no effect on it until it ends.")
TEXTS = [
    "Unrelated shared text.",
    "Greater Heroism\n\nA +15% bonus to Hit Points and THAC0 set to 85% of base. " + OLD,
    "Scroll of Greater Heroism\n\n" + OLD,
]
SPLSTATE = "IDS V1.0\n0 HOPELESSNESS\n68 BUFF_ENHANCEMENT\n240 FOREIGN_240\n"
SPLPROT_ROWS = ("0_ANYONE 0x106 0 1", "1_UNUSED 60 1 1", "2_SOURCE 0x100 * *")
STATE_ROW = "3_SPLSTATE=n 0x112 -1 1"


def fx(op, tg=1, p1=0, p2=0, *, tm=0, du=0, res="", rs=1, **kwargs):
    return SplEffect(opcode=op, target=tg, power=4, parameter1=p1, parameter2=p2,
                     timing=tm, resist_dispel=rs, duration=du, resource=res, **kwargs)


def refresh(resref):
    return SplEffect(opcode=321, target=1, parameter2=2, timing=1, resist_dispel=2, resource=resref)


def item(*effects, category=9, target=5, description=0):
    header = bytearray(0x72)
    struct.pack_into("<H", header, 0x1C, category)
    ability = bytearray(0x38)
    ability[0] = 3
    ability[0x0C] = target
    return ItmFile(abilities=(ItmAbility(raw=bytes(ability), effects=tuple(effects)),),
                   header_raw=bytes(header), identified_description=description).to_bytes()


def spell(*effects, description=-1, target=1):
    raw = bytearray(make_spl((SplAbility(1, target, 48, tuple(effects)),)).to_bytes())
    struct.pack_into("<i", raw, 0x50, description)
    return bytes(raw)


COSMETIC = (fx(142, 1, 0, 22, du=600), fx(139, 1, 16233, tm=1), fx(174, 1, tm=4, du=600, res="EFF_E04"))
HEROISM = (fx(18, 1, 110, 2, du=600), fx(54, 2, 90, 2, du=600),
           fx(328, 1, 1, 68, du=600, special=1), *COSMETIC)


def heroism_spell(hp, thac0, controls, *extra, description=-1):
    return spell(*(fx(321, 2, tm=1, res=r, rs=3) for r in controls),
                 fx(18, 2, hp, 2, du=600, rs=3), fx(54, 2, thac0, 2, du=600, rs=3), *extra,
                 fx(142, 2, 0, 22, du=600, rs=3), fx(328, 2, 0, 68, du=600, rs=3, special=1),
                 fx(139, 2, 217413, tm=1, rs=3), description=description)


def synthetic(*, bardic=True, state_row=True):
    resources = {
        "POTN09.ITM": item(*HEROISM),
        # SCS's copy: same gameplay, other order and cosmetics.
        "DW#PTN09.ITM": item(HEROISM[1], HEROISM[0], HEROISM[2]),
        # Oil of Speed: a leading self-guard must keep rejecting before removal.
        "POTN14.ITM": item(fx(324, 1, 138, 110, res="POTN14"), fx(16, 1, du=300), COSMETIC[1]),
        # Native refresh on the original only.
        "POTN60.ITM": item(fx(321, 1, tm=1, res="POTN60", rs=0), fx(6, 1, 4, du=900), COSMETIC[1]),
        "DW#PTN60.ITM": item(fx(6, 1, 4, du=900)),
        "POTN29.ITM": item(fx(19, 1, 1, du=300), fx(49, 1, 1, du=300), COSMETIC[1]),
        "POTN08.ITM": item(fx(17, 1, 9, tm=1), COSMETIC[1]),
        # A Potion of Power variant with independent instant damage.
        "PTION41.ITM": item(fx(18, 1, 10, du=240), fx(12, 2, 0, 524288, tm=1, dice_number=6, dice_size=6)),
        # Item Revisions style: payload in a same-named spell with its own ward.
        "POTN24.ITM": item(fx(146, 1, 0, 1, tm=1, res="POTN24"), COSMETIC[1]),
        "POTN24.SPL": spell(fx(206, 1, res="POTN24", du=300), fx(18, 1, 10, du=300), target=5),
        # Same style without a ward: keep-first through the item.
        "POTN45.ITM": item(fx(146, 1, 0, 1, tm=1, res="POTN45"), COSMETIC[1]),
        "POTN45.SPL": spell(fx(18, 1, 10, du=300), fx(44, 1, 18, 1, du=300), target=5),
        # The Red Potion and its helper: refresh covers both.
        "POTN15.ITM": item(COSMETIC[1], fx(146, 1, 0, 1, tm=1, res="POTN15"), fx(31, 1, 50, du=7200)),
        "POTN15.SPL": spell(fx(0, 1, 5, du=7200), target=5),
        "POTN13.ITM": item(fx(12, 2, 0, 524288, tm=1, dice_number=5, dice_size=6), target=4),
        "AIDLIKE.SPL": spell(fx(18, 2, 8, 0, du=600, rs=3), fx(54, 2, 90, 2, du=600, rs=3)),
        "SPLSTATE.IDS": SPLSTATE.encode(),
        "SPLPROT.2DA": ("\n".join(["2DA V1.0", "0", "        STAT VALUE RELATION", *SPLPROT_ROWS,
                                   *([STATE_ROW] if state_row else [])]) + "\n").encode(),
    }
    if bardic:
        resources.update({
            "C0BW202.SPL": heroism_spell(110, 90, ("C0BW202", "C0BW502")),
            "C0BW502.SPL": heroism_spell(115, 85, ("C0BW202", "C0BW502"), fx(325, 2, 2, du=600, rs=3),
                                         description=1),
            # A Gallant copy names its sibling copies.
            "C0GA202.SPL": heroism_spell(110, 90, ("C0GA202", "C0GA502")),
            "C0BWSC5.ITM": item(fx(147, 1, tm=1, res="C0BW502"), category=11, target=1, description=2),
        })
    return resources


def effects_of(blob):
    if blob[:4] == b"ITM ":
        return list(ItmFile.from_bytes(blob).abilities[0].effects)
    return list(SplFile.from_bytes(blob).abilities[0].effects)


def run(game, *components, uninstall=False, tp2="setup-chriz-bg-rebalance.tp2"):
    p = subprocess.run([str(WEIDU), tp2, "--force-uninstall-list" if uninstall else "--force-install-list",
                        *map(str, components), "--language", "0", "--use-lang", "en_us",
                        "--no-exit-pause", "--quick-log"],
                       cwd=game.root, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


class PotionUniquenessTests(unittest.TestCase):
    def library(self, game, *, name="direct", language="en_us"):
        (game.root / f"{name}.tp2").write_text(f'''BACKUP ~{name}-backup~
AUTHOR ~test~
ALWAYS
 INCLUDE ~chriz-bg-rebalance/lib/potion_uniqueness.tpa~
END
LANGUAGE ~English~ ~english~ ~chriz-bg-rebalance/languages/english/setup.tra~
BEGIN ~potion overwrite~
LAF cbr_install_potion_uniqueness INT_VAR potions=1 heroism=1 END
''')
        result=subprocess.run([str(WEIDU),f'{name}.tp2','--force-install-list','0','--language','0','--use-lang',language,'--no-exit-pause','--quick-log'],cwd=game.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertNotIn('INSTALLED WITH WARNINGS',result.stdout+result.stderr)
        return result.stdout+result.stderr

    def test_changed_copy_effects_and_existing_controls_are_overwritten(self):
        resources=synthetic()
        resources['DW#PTN09.ITM']=item(fx(18,1,999,du=600),fx(12,2,tm=1),fx(328,1,p2=68,du=1))
        game=self.game(resources);self.library(game)
        states=self.states(game);own=states['CBR_POTION_POTN09'];family=states['CBR_HEROISM_FAMILY']
        for name in ('POTN09.ITM','DW#PTN09.ITM'):
            effects=effects_of(game.snapshot()[name]);self.assertEqual({own,family},{e.parameter1 for e in effects if e.opcode==324})
        before=game.snapshot()
        for name in ('POTN09.ITM','DW#PTN09.ITM'):
            itm=ItmFile.from_bytes(before[name]);ability=itm.abilities[0]
            effects=tuple(dataclasses.replace(e,duration=1,power=99,probability1=3) if e.opcode in (324,328) and (e.parameter1==own or e.parameter2==own) else e for e in ability.effects)
            (game.override/name).write_bytes(dataclasses.replace(itm,abilities=(dataclasses.replace(ability,effects=effects),)).to_bytes())
        self.library(game,name='repair')
        self.assertEqual(before,game.snapshot())

    def test_missing_effects_headers_and_original_potion_still_get_family(self):
        resources=synthetic(bardic=False)
        resources.pop('POTN09.ITM')
        resources['DW#PTN09.ITM']=ItmFile(abilities=(),header_raw=item()[:0x72]).to_bytes()
        game=self.game(resources);self.library(game)
        effects=effects_of(game.snapshot()['DW#PTN09.ITM'])
        self.assertEqual(2,sum(e.opcode==324 for e in effects));self.assertEqual(2,sum(e.opcode==328 for e in effects))
        self.assertEqual({600},{e.duration for e in effects if e.opcode==328})

    def test_empty_slices_ignore_unused_addresses_and_keep_trailing_data(self):
        resources = synthetic()
        for name, source in (('POTN09.ITM', item()), ('C0BW202.SPL', spell())):
            raw = bytearray(source)
            struct.pack_into('<H', raw, 0x6e, 0xffff)
            ab = struct.unpack_from('<I', raw, 0x64)[0]
            struct.pack_into('<H', raw, ab + 0x20, 0xffff)
            resources[name] = bytes(raw)
        raw = bytearray(ItmFile(abilities=(), header_raw=item()[:0x72]).to_bytes())
        struct.pack_into('<H', raw, 0x6e, 0xffff)
        struct.pack_into('<I', raw, 0x64, 0xffffff)
        resources['DW#PTN09.ITM'] = bytes(raw) + b'TRAILER'
        game = self.game(resources); self.library(game)
        for name in ('POTN09.ITM', 'C0BW202.SPL', 'DW#PTN09.ITM'):
            result = game.snapshot()[name]
            if name == 'DW#PTN09.ITM':
                self.assertTrue(result.endswith(b'TRAILER'))
                result = result[:-7]
            self.assertTrue(any(e.opcode == 324 for e in effects_of(result)), name)
        before = game.snapshot(); self.library(game, name='repeat')
        self.assertEqual(before, game.snapshot())

    def test_missing_and_malformed_marker_tables_are_repaired(self):
        variants=[{}, {'SPLSTATE.IDS':b'IDS V1.0\nbad CBR_POTION_POTN09\n999 CBR_POTION_POTN09\n',
                        'SPLPROT.2DA':b'2DA V1.0\n0\n RELATION STAT VALUE EXTRA\nCBR_SPLSTATE_ACTIVE bad bad bad x\n'}]
        for tables in variants:
            resources=synthetic(bardic=False);resources.pop('SPLSTATE.IDS');resources.pop('SPLPROT.2DA');resources.update(tables)
            game=self.game(resources);self.library(game)
            states=self.states(game)
            values=[v for k,v in states.items() if k.startswith('CBR_POTION_') or k=='CBR_HEROISM_FAMILY']
            self.assertTrue(all(0<=v<=255 for v in values));self.assertEqual(len(values),len(set(values)))
            self.assertIn('274 -1 1',(game.override/'SPLPROT.2DA').read_text())
            before=game.snapshot();self.library(game,name='repeat');self.assertEqual(before,game.snapshot())

    def test_exhaustion_omits_only_unavailable_families_and_keeps_refresh(self):
        for free in (0, 1):
            with self.subTest(free=free):
                resources = synthetic()
                resources["POTN09.ITM"] = item(fx(324, 1, 138, 110, res="POTN09"), *HEROISM)
                full = "IDS V1.0\n" + "".join(f"{i} FOREIGN_{i}\n" for i in range(256-free))
                resources["SPLSTATE.IDS"] = full.encode()
                game = self.game(resources)
                output = self.library(game)
                states = self.states(game)
                owned = {k:v for k,v in states.items() if k.startswith("CBR_POTION_") or k == "CBR_HEROISM_FAMILY"}
                self.assertEqual(free, len(owned))
                self.assertEqual(set(range(256-free, 256)), set(owned.values()))
                for i in range(256-free):
                    self.assertEqual(i, states[f"FOREIGN_{i}"])
                logs = [line for line in output.splitlines() if "no unused SPLSTATE slot for" in line]
                self.assertGreater(len(logs), 1)
                self.assertEqual(len(logs), len(set(logs)))
                self.assertNotIn("WARNING", output)
                self.assertTrue(any(e.opcode == 321 for e in effects_of(game.snapshot()["POTN60.ITM"])))
                if not free:
                    self.assertEqual(full.encode(), (game.override / "SPLSTATE.IDS").read_bytes())
                    for name in ("POTN09.ITM", "DW#PTN09.ITM", "POTN45.ITM", "C0BW202.SPL", "C0BW502.SPL"):
                        self.assertEqual(resources[name], game.snapshot()[name], name)
                before = game.snapshot()
                self.library(game, name="repeat")
                self.assertEqual(before, game.snapshot())

    def test_exhaustion_retires_stale_family_controls(self):
        game = self.game(synthetic())
        self.library(game)
        old = {k:v for k,v in self.states(game).items() if k.startswith("CBR_POTION_") or k == "CBR_HEROISM_FAMILY"}
        full = "IDS V1.0\n" + "".join(f"{i} FOREIGN_{i}\n" for i in range(256))
        full += "".join(f"{v} {k}\n" for k,v in old.items())
        path = game.override / "POTN09.ITM"
        itm = ItmFile.from_bytes(path.read_bytes())
        ability = itm.abilities[0]
        # Orphan markers still need retiring when the owning guard is missing.
        effects = tuple(e for e in ability.effects if e.opcode != 324)
        path.write_bytes(dataclasses.replace(itm, abilities=(dataclasses.replace(ability, effects=effects),)).to_bytes())
        (game.override / "SPLSTATE.IDS").write_text(full, newline="\n")
        self.library(game, name="exhausted")
        self.assertEqual(full.encode(), (game.override / "SPLSTATE.IDS").read_bytes())
        for name in ("POTN09.ITM", "DW#PTN09.ITM", "POTN45.ITM", "C0BW202.SPL", "C0BW502.SPL"):
            effects = effects_of(game.snapshot()[name])
            self.assertFalse(any((e.opcode == 324 and e.parameter1 in old.values()) or
                                 (e.opcode == 328 and e.parameter2 in old.values()) for e in effects), name)
            expected_payload = [e for e in effects_of(synthetic()[name]) if e.opcode not in (321, 324, 328)]
            self.assertEqual(expected_payload, [e for e in effects if e.opcode not in (321, 324, 328)], name)
        before = game.snapshot()
        self.library(game, name="exhausted_repeat")
        self.assertEqual(before, game.snapshot())

    def test_foreign_alias_reallocates_only_its_family(self):
        game = self.game(synthetic())
        self.library(game)
        old = self.states(game)
        prior = old["CBR_POTION_POTN09"]
        path = game.override / "SPLSTATE.IDS"
        path.write_bytes(path.read_bytes() + f"{prior} FOREIGN_ALIAS\n".encode())
        self.library(game, name="reallocated")
        states = self.states(game)
        self.assertNotEqual(prior, states["CBR_POTION_POTN09"])
        self.assertEqual(prior, states["FOREIGN_ALIAS"])
        self.assertEqual(old["CBR_HEROISM_FAMILY"], states["CBR_HEROISM_FAMILY"])
        effects = effects_of(game.snapshot()["POTN09.ITM"])
        self.assertEqual({states["CBR_POTION_POTN09"], states["CBR_HEROISM_FAMILY"]},
                         {e.parameter1 for e in effects if e.opcode == 324})
        self.assertFalse(any(e.opcode == 328 and e.parameter2 == prior for e in effects))

    def test_deep_links_cycles_and_instant_payloads_continue(self):
        resources=synthetic(bardic=False)
        resources['POTN60.ITM']=item(fx(146,1,tm=1,res='LINK1'))
        for i in range(1,5):resources[f'LINK{i}.SPL']=spell(fx(146,1,tm=1,res='LINK1' if i==4 else f'LINK{i+1}'),*( [fx(6,1,4,du=900)] if i==4 else [] ))
        game=self.game(resources);self.library(game)
        effects=effects_of(game.snapshot()['POTN60.ITM'])
        self.assertTrue({'LINK1','LINK2','LINK3','LINK4','POTN60','DW#PTN60'}.issubset({e.resource for e in effects if e.opcode==321}))
        for i in range(1,5):self.assertEqual(resources[f'LINK{i}.SPL'],game.snapshot()[f'LINK{i}.SPL'])
        power=effects_of(game.snapshot()['PTION41.ITM'])
        self.assertEqual(12,power[0].opcode);self.assertTrue(any(e.opcode==324 for e in power[1:]))

    def test_lasting_native_ward_cannot_veto_a_refresh(self):
        resources=synthetic(bardic=False)
        resources['POTN14.ITM']=item(fx(206,1,du=300,res='POTN14'),fx(16,1,du=300))
        game=self.game(resources);self.library(game)
        self.assertEqual([refresh('POTN14'),fx(16,1,du=300)],effects_of(game.snapshot()['POTN14.ITM']))

    def test_saved_probabilistic_and_unusual_targets_receive_controls(self):
        resources=synthetic()
        resources['C0GA202.SPL']=spell(fx(18,3,110,2,du=777,probability1=20,save_type=1,tm=3))
        game=self.game(resources);self.library(game)
        effects=effects_of(game.snapshot()['C0GA202.SPL'])
        self.assertEqual((324,3),(effects[0].opcode,effects[0].target))
        self.assertEqual(777,effects[-1].duration)
        self.assertEqual(effects_of(resources['C0GA202.SPL'])[0],effects[1])

    def test_shared_slices_reverse_table_and_trailer_preserve_foreign_effects(self):
        original=synthetic()['POTN09.ITM'];ab=struct.unpack_from('<I',original,0x64)[0];fxoff=struct.unpack_from('<I',original,0x6a)[0]
        raw=bytearray(original[:0x72]+original[fxoff:]+original[ab:fxoff]+b'TAIL')
        struct.pack_into('<I',raw,0x64,0x72+len(original)-fxoff);struct.pack_into('<I',raw,0x6a,0x72)
        resources=synthetic(bardic=False);resources['POTN09.ITM']=bytes(raw)
        game=self.game(resources);self.library(game)
        after=game.snapshot()['POTN09.ITM'];self.assertTrue(after.endswith(b'TAIL'))
        self.assertEqual(2,sum(e.opcode==324 for e in effects_of(after[:-4]) if e.target==1))

    def test_other_text_and_other_language(self):
        for language in ('en_us','de_de'):
            resources=synthetic();resources['C0BW502.SPL']=spell(fx(18,2,115,2,du=600),description=0)
            game=self.game(resources)
            if language=='de_de':
                target=game.root/'lang/de_de/dialog.tlk';target.parent.mkdir();target.write_bytes(game.tlk.read_bytes())
            self.library(game,language=language)
            blob=game.snapshot()['C0BW502.SPL'];ref=struct.unpack_from('<i',blob,0x50)[0]
            if language=='en_us':
                expected=json.loads((Path(__file__).parent/'fixtures/potion_heroism_descriptions.json').read_text(encoding='utf8'))['C0BW502']
                self.assertEqual(expected,strings(game.tlk)[ref].replace('\r\n','\n'))
            else:self.assertEqual(0,ref)

    def game(self, resources):
        holder = tempfile.TemporaryDirectory(prefix="cbr-potions-")
        self.addCleanup(holder.cleanup)
        return Game(Path(holder.name), resources, public=True, texts=TEXTS)

    def install(self, game, *components):
        code, output = run(game, *components)
        self.assertEqual(0, code, output)
        self.assertNotIn("NOT INSTALLED", output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
        return output

    def states(self, game):
        ids = IdsFile.from_text((game.override / "SPLSTATE.IDS").read_text())
        return {symbol.upper(): value for value, symbol in ids.entries}

    def assert_keep_first(self, before, after, own, states, row, duration):
        """Guards lead every buff batch, markers trail, originals are intact."""
        def guard(e):
            return (e.opcode == 324 and e.resource == own and e.parameter1 in states
                    and e.parameter2 == row and e.duration == 0 and e.timing == 0)

        def marker(e):
            return e.opcode == 328 and e.parameter2 in states and e.special == 1

        self.assertEqual(effects_of(before), [e for e in after if not guard(e) and not marker(e)])
        for target in {e.target for e in effects_of(before) if e.opcode not in (139, 142, 174, 328)}:
            batch = [e for e in after if e.target == target]
            self.assertEqual(states, {e.parameter1 for e in batch[:len(states)] if guard(e)}, own)
        trailing = after[-len(states):]
        self.assertTrue(all(marker(e) for e in trailing), own)
        self.assertEqual(states, {e.parameter2 for e in trailing})
        self.assertEqual({duration}, {e.duration for e in trailing})
        self.assertEqual({max(e.target for e in after if guard(e))}, {e.target for e in trailing})

    def test_330_and_332_patch_only_matching_resources_and_uninstall(self):
        game = self.game(synthetic())
        before = game.original
        output = self.install(game, 330, 332)
        after = game.snapshot()
        states = self.states(game)
        own, family = states["CBR_POTION_POTN09"], states["CBR_HEROISM_FAMILY"]
        power = states["CBR_POTION_POTN45"]
        self.assertTrue({own, family, power}.isdisjoint({0, 68, 240}))
        self.assertEqual(3, len({own, family, power}))
        self.assertEqual(before["SPLPROT.2DA"], after["SPLPROT.2DA"])  # reused row 3

        for potion in ("POTN09.ITM", "DW#PTN09.ITM"):
            self.assert_keep_first(before[potion], effects_of(after[potion]), potion[:-4],
                                   {own, family}, 3, 600)
        self.assert_keep_first(before["POTN45.ITM"], effects_of(after["POTN45.ITM"]), "POTN45",
                               {power}, 3, 300)
        for spl in ("C0BW202.SPL", "C0BW502.SPL", "C0GA202.SPL"):
            self.assert_keep_first(before[spl], effects_of(after[spl]), spl[:-4], {family}, 3, 600)

        oil = effects_of(before["POTN14.ITM"])
        self.assertEqual([oil[0], refresh("POTN14"), *oil[1:]], effects_of(after["POTN14.ITM"]))
        native = effects_of(before["POTN60.ITM"])
        self.assertEqual([refresh("DW#PTN60"), refresh("POTN60"), *native[1:]], effects_of(after["POTN60.ITM"]))
        self.assertEqual([refresh("DW#PTN60"), refresh("POTN60"), *effects_of(before["DW#PTN60.ITM"])],
                         effects_of(after["DW#PTN60.ITM"]))
        self.assertEqual([refresh("POTN15"), *effects_of(before["POTN15.ITM"])],
                         effects_of(after["POTN15.ITM"]))
        self.assertEqual([refresh("POTN29"), *effects_of(before["POTN29.ITM"])],
                         effects_of(after["POTN29.ITM"]))

        for unchanged in ("POTN08.ITM", "POTN24.SPL", "POTN45.SPL",
                          "POTN15.SPL", "POTN13.ITM", "AIDLIKE.SPL"):
            self.assertEqual(before[unchanged], after[unchanged], unchanged)
        self.assertNotEqual(before["PTION41.ITM"], after["PTION41.ITM"])
        self.assertNotEqual(before["POTN24.ITM"], after["POTN24.ITM"])
        self.assertEqual(12, effects_of(after["PTION41.ITM"])[0].opcode)

        texts = strings(game.tlk)
        for resource, offset in (("C0BW502.SPL", 0x50), ("C0BWSC5.ITM", 0x54)):
            text = texts[struct.unpack_from("<i", after[resource], offset)[0]]
            self.assertIn(NEW, text)
            self.assertNotIn(OLD, text)
        self.assertIn("15%", texts[struct.unpack_from("<i", after["C0BW502.SPL"], 0x50)[0]])

        code, output = run(game, 330, 332, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(game.original, game.snapshot())
        # WeiDU keeps appended strings; the original entries must be intact.
        self.assertEqual(game.original_texts, strings(game.tlk)[:len(game.original_texts)])

    def test_331_keeps_genius_stacking(self):
        game = self.game(synthetic())
        self.install(game, 331)
        after = game.snapshot()
        self.assertEqual(game.original["POTN29.ITM"], after["POTN29.ITM"])
        self.assertNotEqual(game.original["POTN14.ITM"], after["POTN14.ITM"])
        self.assertEqual(game.original["C0BW202.SPL"], after["C0BW202.SPL"])

    def test_repeat_application_over_installed_components_changes_nothing(self):
        game = self.game(synthetic())
        self.install(game, 330, 332)
        installed = game.snapshot()
        installed_tlk = game.tlk.read_bytes()
        (game.root / "repeat.tp2").write_text(
            "BACKUP ~repeat-backup~\nAUTHOR ~test~\n"
            "ALWAYS\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/tempus_holy_power.tpa~\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/tempus_spec_apr_eeex.tpa~\n"
            "  INCLUDE ~chriz-bg-rebalance/lib/potion_uniqueness.tpa~\n"
            "END\n"
            "LANGUAGE ~English~ ~english~ ~chriz-bg-rebalance/languages/english/setup.tra~\n"
            "BEGIN ~repeat~\n"
            "LAF cbr_install_potion_uniqueness INT_VAR potions = 1 heroism = 1 END\n")
        code, output = run(game, 0, tp2="repeat.tp2")
        self.assertEqual(0, code, output)
        self.assertEqual(installed, game.snapshot())
        self.assertEqual(installed_tlk, game.tlk.read_bytes())

    def test_332_without_bardic_or_state_row_guards_the_potion(self):
        game = self.game(synthetic(bardic=False, state_row=False))
        self.install(game, 332)
        after = game.snapshot()
        family = self.states(game)["CBR_HEROISM_FAMILY"]
        rows = after["SPLPROT.2DA"].decode().split()
        self.assertEqual(["CBR_SPLSTATE_ACTIVE", "274", "-1", "1"],
                         rows[rows.index("CBR_SPLSTATE_ACTIVE"):][:4])
        for potion in ("POTN09.ITM", "DW#PTN09.ITM"):
            self.assert_keep_first(game.original[potion], effects_of(after[potion]), potion[:-4],
                                   {family}, 3, 600)
        changed = {name for name in after if after[name] != game.original.get(name)}
        self.assertEqual({"POTN09.ITM", "DW#PTN09.ITM", "SPLSTATE.IDS", "SPLPROT.2DA"}, changed)


if __name__ == "__main__":
    unittest.main()
