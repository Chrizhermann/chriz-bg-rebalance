"""Component 130 behavior variants on disposable synthetic EET games only.

The fixtures name the owned records explicitly (header index, effect index),
so the byte oracle below is independent of the installer's own classifier.
Each test runs the public setup with real WeiDU; it never touches a real game.
These are automated installer checks, not in-game verification.
"""
from __future__ import annotations

import json
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


def decoded(blob):
    """Read referenced slices without assuming table order or EOF padding."""
    ab = struct.unpack_from('<I', blob, 0x64)[0]
    fx = struct.unpack_from('<I', blob, 0x6a)[0]
    def effects(first, count):
        records = [blob[fx+(first+i)*48:fx+(first+i+1)*48] for i in range(count)]
        assert all(len(record) == 48 for record in records)
        return tuple(SplEffect.from_bytes(record) for record in records)
    abilities = []
    for i in range(struct.unpack_from('<H', blob, 0x68)[0]):
        at = ab+i*56
        count, first = struct.unpack_from('<HH', blob, at+30)
        abilities.append(ItmAbility(raw=blob[at:at+56], effects=effects(first, count)))
    first, count = struct.unpack_from('<HH', blob, 0x6e)
    return ItmFile(abilities=tuple(abilities), global_effects=effects(first, count))


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
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
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


    def check_package(self, blob, header_index, kind, size):
        item = decoded(blob)
        ability = item.abilities[header_index]
        owned = [e for e in ability.effects if e.opcode == 12 and e.target == 2 and e.parameter2 == kind << 16]
        self.assertEqual(1, len(owned))
        self.assertEqual((1, size), (owned[0].dice_number, owned[0].dice_size))
        if kind == FIRE:
            self.assertEqual((0, 0), (struct.unpack_from('<h', ability.raw, 20)[0], struct.unpack_from('<h', ability.raw, 26)[0]))
        return item

    def test_normal_and_changed_dice_preserve_all_other_binary_fields(self):
        resources = arrow_resources()
        resources['AROW08.ITM'] = arrow([header((troll('DWTROLFI'), damage(FIRE, 5, 99, save=0x1000001,
            save_bonus=-3, timing=1, probability1=90, probability2=3, parameter1=1, power=4)), hit=7, dmg=9)], 5, 6)
        g = self.game(resources); self.install(g); after = g.snapshot()
        old, new = g.original['AROW08.ITM'], after['AROW08.ITM']
        self.assertEqual(expected(old,new,2,[(0,1)],[0],name=True,desc=True),new)
        self.check_package(new,0,FIRE,2)
        self.reference_others_patched(g,after,skip=('AROW08',)); self.uninstall_restores(g)

    def test_missing_duplicate_and_extra_effects_each_receive_one_package(self):
        resources=arrow_resources()
        foreign=damage(ACID,2,9,resource='FOREIGN')
        resources['AROW08.ITM']=arrow([header((troll('DWTROLFI'),)),
            header((damage(FIRE,9,99),foreign,damage(FIRE,3,3)),hit=2,dmg=2)],5,6)
        g=self.game(resources);self.install(g)
        blob=g.snapshot()['AROW08.ITM']
        item=self.check_package(blob,0,FIRE,2);self.check_package(blob,1,FIRE,2)
        self.assertIn(foreign,item.abilities[1].effects)
        self.assertEqual(troll('DWTROLFI'),item.abilities[0].effects[0])

    def test_other_ability_and_delivery_effects_remain_unchanged(self):
        resources=arrow_resources()
        foreign=(damage(FIRE,4,8,target=1),damage(FIRE,8,8,mode=1),damage(ACID,1,9),troll('DWTROLFI'))
        activate=header((damage(FIRE,2,20),),kind=3,hit=8,dmg=9)
        resources['AROW08.ITM']=arrow([activate,header((damage(FIRE,9,9),*foreign),hit=6,dmg=6)],5,6)
        g=self.game(resources);self.install(g);blob=g.snapshot()['AROW08.ITM']
        item=self.check_package(blob,1,FIRE,2)
        self.assertEqual(activate.effects,item.abilities[0].effects)
        self.assertEqual(activate.raw[:30],item.abilities[0].raw[:30])
        self.assertEqual(foreign,item.abilities[1].effects[1:])

    def test_missing_bow_header_is_supplied_including_empty_item(self):
        for abilities in ([],[header((damage(COLD,8,8),),kind=3)], [header((damage(COLD,8,8),),launcher=2)]):
            resources=arrow_resources();resources['AROW09.ITM']=arrow(abilities,3,4)
            g=self.game(resources);self.install(g)
            item=self.check_package(g.snapshot()['AROW09.ITM'],len(abilities),COLD,2)
            self.assertEqual(len(abilities)+1,len(item.abilities))
            for i,old in enumerate(abilities):self.assertEqual(old.effects,item.abilities[i].effects)

    def test_empty_tables_ignore_unused_addresses(self):
        for abilities in ([], [header(())]):
            raw = bytearray(arrow(abilities, 3, 4))
            struct.pack_into('<H', raw, 0x6e, 0xffff)
            if abilities:
                struct.pack_into('<H', raw, offsets(raw, 0) + 0x20, 0xffff)
            else:
                struct.pack_into('<I', raw, 0x64, 0xffffff)
            resources = arrow_resources(); resources['AROW09.ITM'] = bytes(raw)
            g = self.game(resources); self.install(g)
            self.check_package(g.snapshot()['AROW09.ITM'], 0, COLD, 2)

    def test_shared_slice_is_separated_from_activation_and_equipped_effects(self):
        for global_ref in (False,True):
            resources=arrow_resources()
            blob=arrow([header((damage(FIRE,1,6),troll('DWTROLFI')),hit=2,dmg=2),header((),kind=3)],5,6)
            blob=equip(blob,0,1) if global_ref else point(blob,1,0,1)
            resources['AROW08.ITM']=blob
            g=self.game(resources);self.install(g);new=g.snapshot()['AROW08.ITM']
            item=self.check_package(new,0,FIRE,2)
            unchanged=item.global_effects if global_ref else item.abilities[1].effects
            self.assertEqual(6,unchanged[0].dice_size)
            self.assertEqual(copied(blob,new,2,[(0,0)],bonus_headers=[0]),new)

    def test_padding_and_effect_table_before_abilities_are_supported(self):
        for reorder in (False,True):
            resources=arrow_resources()
            blob=point(arrow([header((damage(FIRE,1,6),),hit=2,dmg=2),header((),kind=3)],5,6),1,0,1)
            ab,fx=struct.unpack_from('<I',blob,0x64)[0],struct.unpack_from('<I',blob,0x6a)[0]
            if reorder:
                raw=bytearray(blob[:0x72]+blob[fx:]+blob[ab:fx]);struct.pack_into('<I',raw,0x64,0x72+len(blob)-fx);struct.pack_into('<I',raw,0x6a,0x72);blob=bytes(raw)
            blob+=b'TRAILER'+bytes(48*0x10000)
            resources['AROW08.ITM']=blob
            g=self.game(resources);self.install(g);new=g.snapshot()['AROW08.ITM']
            item=self.check_package(new,0,FIRE,2)
            self.assertEqual(6,item.abilities[1].effects[0].dice_size)
            self.assertTrue(new.endswith(b'TRAILER'+bytes(48*0x10000)))

    def test_damaged_one_item_does_not_stop_others(self):
        resources=arrow_resources();resources['AROWKC.ITM']=b'broken'
        g=self.game(resources);output=self.install(g);after=g.snapshot()
        self.assertIn('unreadable resource bounds',output)
        self.assertEqual(b'broken',after['AROWKC.ITM'])
        self.reference_others_patched(g,after,skip=('AROWKC',))

    def test_changed_category_and_wording_receive_owned_result(self):
        resources=arrow_resources();raw=bytearray(resources['AROW08.ITM']);struct.pack_into('<H',raw,0x1c,22);resources['AROW08.ITM']=bytes(raw)
        g=self.game(resources,['Foreign or translated text '+str(i) for i in range(7)]);self.install(g)
        golden=json.loads((Path(__file__).parent/'fixtures/elemental_arrow_descriptions.json').read_text(encoding='utf8'))
        for name in ('AROW04','AROW09','AROW08','AROWKC'):
            blob=g.snapshot()[name+'.ITM'];self.assertEqual(golden['descriptions'][name],strings(g.tlk)[pointer(blob,84)].replace('\r\n','\n'))
        self.assertEqual(5,struct.unpack_from('<H',g.snapshot()['AROW08.ITM'],0x1c)[0])

    def test_other_game_language_preserves_text_and_female_english_is_complete(self):
        for lang in ('en_us','de_de'):
            g=self.game(arrow_resources())
            target=g.root/f'lang/{lang}/dialog.tlk';target.parent.mkdir(exist_ok=True)
            target.write_bytes(g.tlk.read_bytes())
            female=target.with_name('dialogf.tlk');female.write_bytes(tlk(['Other female text '+str(i) for i in range(7)]))
            folder=g.root/'cbr_arrow_repeat';folder.mkdir();(folder/'cbr_arrow_repeat.tp2').write_text(REPEAT_TP2)
            result=subprocess.run([str(WEIDU),'cbr_arrow_repeat/cbr_arrow_repeat.tp2','--force-install-list','0','--use-lang',lang,'--no-exit-pause','--quick-log'],cwd=g.root,capture_output=True,text=True,timeout=60)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            blob=g.snapshot()['AROW08.ITM'];self.check_package(blob,0,FIRE,2)
            if lang=='en_us':self.assertEqual(strings(target)[pointer(blob,84)],strings(female)[pointer(blob,84)])
            else:self.assertEqual(6,pointer(blob,84));self.assertIn('existing text retained',result.stdout)

    def test_second_install_is_byte_identical_with_rebuilt_and_shared_slices(self):
        resources=arrow_resources()
        resources['AROW09.ITM']=arrow([],3,4)
        resources['AROW08.ITM']=point(arrow([header((damage(FIRE,9,99),),hit=8,dmg=9),header((),kind=3)],5,6),1,0,1)
        g=self.game(resources);self.install(g);before=g.snapshot();before_tlk=g.tlk.read_bytes()
        folder=g.root/'cbr_arrow_repeat';folder.mkdir();(folder/'cbr_arrow_repeat.tp2').write_text(REPEAT_TP2)
        result=subprocess.run([str(WEIDU),'cbr_arrow_repeat/cbr_arrow_repeat.tp2','--force-install-list','0','--use-lang','en_us','--no-exit-pause','--quick-log'],cwd=g.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertEqual(before,g.snapshot());self.assertEqual(before_tlk,g.tlk.read_bytes())

    def test_later_item_effect_functions_can_patch_separated_slices(self):
        resources=arrow_resources();resources['AROW08.ITM']=point(arrow([header((damage(FIRE,1,6),),hit=2,dmg=2),header((),kind=3)],5,6),1,0,1)
        g=self.game(resources);self.install(g)
        folder=g.root/'later';folder.mkdir();(folder/'later.tp2').write_text(LATER_TP2)
        result=subprocess.run([str(WEIDU),'later/later.tp2','--force-install-list','0','--use-lang','en_us','--no-exit-pause','--quick-log'],cwd=g.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.check_package(g.snapshot()['AROW08.ITM'],0,FIRE,2)
