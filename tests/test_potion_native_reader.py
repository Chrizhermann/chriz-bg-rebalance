"""Offline LuaJIT reader tests against byte-addressed mock native memory.

The reader itself runs unchanged. No game, native DLL, EEex hook or save is
accessed. Field offsets/signedness and lifetime tokens are exercised separately
from native admission safety, which has its own pinned-instruction probes.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import struct
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "research/prototypes/potion-admission"
BASE = 0x200000000
FIELDS = {
    "opcode": (0x10, "I"), "target": (0x14, "I"), "power": (0x18, "I"),
    "amount": (0x1C, "i"), "mode": (0x20, "I"), "timing": (0x24, "I"),
    "duration": (0x28, "I"), "probUpper": (0x2C, "H"), "probLower": (0x2E, "H"),
    "diceCount": (0x38, "i"), "diceSize": (0x3C, "i"), "saveType": (0x40, "I"),
    "saveBonus": (0x44, "i"), "special": (0x48, "I"), "school": (0x4C, "I"),
    "minLevel": (0x54, "I"), "maxLevel": (0x58, "I"), "flags": (0x5C, "I"),
    "sourceFlags": (0x9C, "I"), "secondary": (0xD0, "I"),
}


def descriptor(**changes):
    fields = dict(opcode=90, target=1, power=2, amount=40, mode=0, resource="",
                  diceCount=0, diceSize=0, saveType=0x01000008, saveBonus=-3,
                  special=0x80000000, flags=1, school=0, secondary=7,
                  sourceFlags=0x80000100, probUpper=100, probLower=0,
                  timing=0, duration=120, minLevel=0, maxLevel=0)
    fields.update(changes)
    return fields


def manifest(records=None, source="POTN36"):
    records = records or {"k": descriptor()}
    return {"policy": "unique", "families": {source: {"hp": False, "genius": False}},
            "sources": {source: {"family": source, "keys": {k: True for k in records},
                                  "records": records}}}


class NativeReaderTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.memory = {}
        self.reads = []
        self.lua.globals().read_memory = self.read
        self.lua.execute("""
            api = {
                EEex_ReadU32=function(p) return read_memory(p, 'I') end,
                EEex_Read32=function(p) return read_memory(p, 'i') end,
                EEex_ReadU16=function(p) return read_memory(p, 'H') end,
                EEex_ReadU8=function(p) return read_memory(p, 'B') end,
                EEex_UDToPtr=function(object) return object.pointer end,
                EEex_Utility_IterateCPtrList=function(list, callback)
                    for _, effect in ipairs(list) do if callback(effect) then break end end
                end,
                EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_worldTime={m_gameTime=1000}}}},
            }
            function mockObject(pointer)
                return setmetatable({}, {
                    __index=function(_,key) if key=='pointer' then return pointer end end,
                    __newindex=function() error('native object write') end,
                })
            end
            function same(a,b) return rawequal(a,b) end
            function count(t) local n=0; for _ in pairs(t) do n=n+1 end; return n end
        """)
        self.factory = self.lua.execute((PROTOTYPE / "CBRPQNative.lua").read_text())
        self.api = self.lua.globals().api
        self.reader = self.factory(self.api, self.table(manifest()))

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k: self.table(v) for k, v in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(v) for v in value])
        return value

    def put(self, address, fmt, value):
        for offset, byte in enumerate(struct.pack("<" + fmt, value)):
            self.memory[address + offset] = byte

    def resref(self, address, value):
        raw = value.encode("ascii").ljust(8, b"\0")
        assert len(raw) == 8
        for offset, byte in enumerate(raw):
            self.memory[address + offset] = byte

    def read(self, address, fmt):
        self.reads.append((address, fmt))
        data = bytes(self.memory[address + offset] for offset in range(struct.calcsize(fmt)))
        return struct.unpack("<" + fmt, data)[0]

    def effect(self, fields=None, pointer=BASE, source="POTN36", active=False):
        fields = fields or descriptor()
        for offset in range(0x180):
            self.memory[pointer + offset] = 0
        for name, (offset, fmt) in FIELDS.items():
            self.put(pointer + offset, fmt, fields[name])
        self.resref(pointer + 0x30, fields["resource"])
        self.put(pointer + 0x90, "I", 2)
        self.resref(pointer + 0x94, source)
        self.put(pointer + 0xC8, "I", 10)
        self.put(pointer + 0xCC, "I", 1)
        self.put(pointer + 0x110, "I", 123)
        self.put(pointer + 0x150, "I", 999)  # Selected target may differ from drinker.
        if active:
            self.put(pointer + 0x24, "I", 4096)
            self.put(pointer + 0x28, "I", 1700)
        return self.lua.globals().mockObject(pointer)

    def same(self, left, right):
        return self.lua.globals().same(left, right)

    def sprite(self, effects):
        return self.table({"m_timedEffectList": effects, "pointer": BASE + 0xF000})

    def assert_unchanged(self, before):
        self.assertEqual(before, self.memory)

    def test_exact_runtime_fields_and_signed_unsigned_reads(self):
        fields = descriptor(amount=-123, mode=0x80000001, diceCount=-2, diceSize=-6,
                            minLevel=2, maxLevel=17, resource="ABCDEFGH", probUpper=65535)
        reader = self.factory(self.api, self.table(manifest({"exact": fields})))
        effect = self.effect(fields)
        before = dict(self.memory)
        result = reader.identify(effect, "exact", True)
        self.assertEqual((result.sourceType, result.source, result.key, result.timing, result.expiry,
                          result.done), (2, "POTN36", "exact", 0, 120, False))
        self.assertTrue(self.same(result.object, effect))
        self.assertIsNotNone(result.identity)
        for field, (offset, fmt) in FIELDS.items():
            self.assertIn((BASE + offset, fmt), self.reads, field)
        self.assert_unchanged(before)

    def test_each_gameplay_field_drift_rejects_explicit_key(self):
        for field, (offset, fmt) in FIELDS.items():
            with self.subTest(field=field):
                effect = self.effect()
                self.put(BASE + offset, fmt, descriptor()[field] + 1)
                before = dict(self.memory)
                with self.assertRaisesRegex(Exception, "key mismatch"):
                    self.reader.identify(effect, "k", True)
                self.assert_unchanged(before)

    def test_resource_is_case_insensitive_bounded_to_eight_bytes(self):
        fields = descriptor(resource="ABCDEFGH")
        reader = self.factory(self.api, self.table(manifest({"k": fields}, "ABCDEFGH")))
        effect = self.effect(fields, source="abcdefgh")
        self.resref(BASE + 0x30, "abcdefgh")
        self.assertEqual(reader.source(effect), ("ABCDEFGH", 2))
        self.assertEqual(reader.identify(effect, None, True).key, "k")
        resource_reads = [p for p, kind in self.reads if kind == "B"]
        self.assertNotIn(BASE + 0x38, resource_reads)
        self.assertNotIn(BASE + 0x9C, resource_reads)

    def test_source_reads_only_source_and_terminates_at_nul(self):
        effect = self.effect(source="AB")
        self.reads.clear()
        self.assertEqual(self.reader.source(effect), ("AB", 2))
        self.assertEqual(self.reads, [(BASE + 0x90, "I"), (BASE + 0x94, "B"),
                                     (BASE + 0x95, "B"), (BASE + 0x96, "B")])

    def projectile_api(self, image_base=0x140000000):
        self.lua.globals().projectile_image_base = image_base
        self.lua.execute("""
            api.EEex_ReadPtr=function(pointer) return read_memory(pointer, 'Q') end
            api.EEex_GetImageBase=function() return projectile_image_base end
        """)

    def test_instant_projectile_checks_actual_pointer_sized_vtable_only(self):
        self.projectile_api()
        self.put(BASE, "Q", 0x14059BFF0)
        before = dict(self.memory)
        self.assertTrue(self.reader.isInstantProjectile(BASE))
        self.assertEqual(self.reads, [(BASE, "Q")])
        self.assert_unchanged(before)

    def test_instant_projectile_rejects_replaced_class_and_same_low_dword(self):
        self.projectile_api()
        for vtable in (0, 0x14059BFE8, 0x24059BFF0):
            with self.subTest(vtable=vtable):
                self.put(BASE, "Q", vtable)
                before = dict(self.memory)
                self.assertFalse(self.reader.isInstantProjectile(BASE))
                self.assert_unchanged(before)

    def test_instant_projectile_uses_actual_relocated_image_base(self):
        self.projectile_api(0x180000000)
        self.put(BASE, "Q", 0x18059BFF0)
        self.assertTrue(self.reader.isInstantProjectile(BASE))
        self.put(BASE, "Q", 0x14059BFF0)
        self.assertFalse(self.reader.isInstantProjectile(BASE))

    def test_projectile_capabilities_are_lazy_and_fail_before_native_read(self):
        effect = self.effect()
        self.assertEqual(self.reader.identify(effect, "k", True).key, "k")
        self.reads.clear()
        with self.assertRaisesRegex(Exception, "missing API EEex_ReadPtr"):
            self.reader.isInstantProjectile(BASE)
        self.lua.execute("api.EEex_ReadPtr=function() error('must not read') end")
        with self.assertRaisesRegex(Exception, "missing API EEex_GetImageBase"):
            self.reader.isInstantProjectile(BASE)
        self.assertEqual(self.reads, [])

    def test_projectile_pointer_and_image_base_are_exact_numbers_before_read(self):
        self.projectile_api()
        for pointer in (0, -1, 1.5, float("nan"), float("inf"), 2**53, "123"):
            with self.subTest(pointer=pointer):
                with self.assertRaisesRegex(Exception, "invalid projectile pointer"):
                    self.reader.isInstantProjectile(pointer)
        for image_base in (0, -1, float("inf"), 2**53):
            self.lua.globals().projectile_image_base = image_base
            with self.assertRaisesRegex(Exception, "invalid image base"):
                self.reader.isInstantProjectile(BASE)
        self.assertEqual(self.reads, [])

    def test_projectile_vtable_reader_requires_exact_numeric_pointer(self):
        self.projectile_api()
        self.lua.execute("api.EEex_ReadPtr=function() return '5368709120' end")
        with self.assertRaisesRegex(Exception, "invalid projectile vtable"):
            self.reader.isInstantProjectile(BASE)

    def test_unowned_source_type_source_and_record_are_ignored(self):
        effect = self.effect()
        self.put(BASE + 0x90, "I", 1)
        self.assertIsNone(self.reader.identify(effect, "k", True))
        self.effect(source="FOREIGN")
        self.assertIsNone(self.reader.identify(effect, "k", True))
        self.effect()
        self.put(BASE + 0x10, "I", 17)
        self.assertIsNone(self.reader.identify(effect, None, True))
        with self.assertRaisesRegex(Exception, "key mismatch"):
            self.reader.identify(effect, "k", True)

    def test_caster_level_drift_and_unknown_key_are_diagnostics(self):
        effect = self.effect()
        self.put(BASE + 0xC8, "I", 20)
        with self.assertRaisesRegex(Exception, "caster level"):
            self.reader.identify(effect, None, True)
        with self.assertRaisesRegex(Exception, "absent"):
            self.reader.identify(effect, "wrong", True)

    def test_incoming_timing_and_duration_required_active_deadline_is_not_identity(self):
        effect = self.effect(active=True)
        self.assertIsNone(self.reader.identify(effect, None, True))
        record = self.reader.identify(effect, None, False)
        self.assertEqual((record.key, record.timing, record.expiry), ("k", 4096, 1700))
        self.put(BASE + 0x28, "I", 999)
        self.put(BASE + 0x114, "I", 1)
        record = self.reader.identify(effect, None, False)
        self.assertTrue(record.done)
        self.assertEqual(record.expiry, 999)  # Core decides liveness; reader never revives.

    def test_native_self_identification_flags_only_are_normalized(self):
        effect = self.effect()
        self.put(BASE + 0x5C, "I", 0x80000009)
        self.assertEqual(self.reader.identify(effect, "k", True).key, "k")
        self.put(BASE + 0x5C, "I", 0x8000000D)
        with self.assertRaisesRegex(Exception, "key mismatch"):
            self.reader.identify(effect, "k", True)

    def test_hp_special_first_use_bit_normalized_only_when_active(self):
        fields = descriptor(opcode=18, amount=110, mode=2, special=0)
        reader = self.factory(self.api, self.table(manifest({"hp": fields})))
        effect = self.effect(fields)
        reader.identify(effect, "hp", True)
        self.put(BASE + 0x48, "I", 1)
        with self.assertRaisesRegex(Exception, "key mismatch"):
            reader.identify(effect, "hp", True)
        self.assertEqual(reader.identify(effect, "hp", False).key, "hp")
        self.put(BASE + 0x48, "I", 3)
        self.assertIsNone(reader.identify(effect, None, False))

    def test_specialist_save_bonus_variant_requires_school_and_exact_minus_two(self):
        effect = self.effect()
        self.put(BASE + 0x44, "i", -5)
        self.assertIsNone(self.reader.identify(effect, None, True))
        fields = descriptor(school=2)
        reader = self.factory(self.api, self.table(manifest({"k": fields})))
        effect = self.effect(fields)
        self.put(BASE + 0x44, "i", -5)
        self.assertEqual(reader.identify(effect, "k", True).key, "k")
        self.put(BASE + 0x44, "i", -4)
        self.assertIsNone(reader.identify(effect, None, True))

    def test_ambiguous_active_lifetime_and_specialist_keys_raise(self):
        records = {"a": descriptor(duration=120), "b": descriptor(duration=240)}
        reader = self.factory(self.api, self.table(manifest(records)))
        effect = self.effect()
        self.assertEqual(reader.identify(effect, None, True).key, "a")
        with self.assertRaisesRegex(Exception, "ambiguous"):
            reader.identify(effect, "a", False)
        records = {"a": descriptor(school=1, saveBonus=-3),
                   "b": descriptor(school=1, saveBonus=-5)}
        reader = self.factory(self.api, self.table(manifest(records)))
        effect = self.effect(records["b"])
        with self.assertRaisesRegex(Exception, "ambiguous"):
            reader.identify(effect, "b", True)

    def test_active_fresh_objects_share_lifetime_token_until_retired(self):
        effect = self.effect(active=True)
        incoming = self.reader.identify(effect, None, False)
        cache = self.lua.table()
        first = self.reader.active(self.sprite([effect]), cache)[1]
        replacement_wrapper = self.lua.globals().mockObject(BASE)
        self.put(BASE + 0x28, "I", 1800)
        second = self.reader.active(self.sprite([replacement_wrapper]), cache)[1]
        self.assertTrue(self.same(first.identity, second.identity))
        self.assertTrue(self.same(incoming.identity, second.identity))
        self.assertTrue(self.same(second.object, replacement_wrapper))
        self.assertEqual(second.expiry, 1800)
        self.assertFalse(self.same(second.object, first.object))
        self.reads.clear()
        self.reader.retire(BASE)
        self.assertEqual(self.reads, [])
        third = self.reader.active(self.sprite([replacement_wrapper]), cache)[1]
        self.assertFalse(self.same(first.identity, third.identity))
        self.assertTrue(self.same(cache[BASE].identity, third.identity))

    def test_reset_tokens_changes_identity_without_native_reads_or_cached_userdata_access(self):
        effect = self.effect(active=True)
        old = self.reader.identify(effect, None, False)
        cache = self.lua.table()
        cache[BASE] = self.lua.eval("setmetatable({}, {__index=function() error('stale userdata') end})")
        self.reads.clear()
        self.reader.resetTokens()
        self.assertEqual(self.reads, [])
        current = self.reader.active(self.sprite([effect]), cache)[1]
        self.assertFalse(self.same(old.identity, current.identity))

    def test_weak_tokens_do_not_retain_unreferenced_effect_history(self):
        effect = self.effect()
        self.lua.globals().record = self.reader.identify(effect, None, True)
        self.lua.execute("w=setmetatable({record.identity},{__mode='v'}); record=nil; collectgarbage(); collectgarbage()")
        self.assertIsNone(self.lua.globals().w[1])

    def test_active_ignores_unowned_and_never_touches_equipped_list(self):
        effect = self.effect(active=True)
        unowned = self.effect(pointer=BASE + 0x1000, source="FOREIGN", active=True)
        sprite = self.sprite([unowned, effect])
        sprite.m_equipedEffectList = self.lua.eval("setmetatable({}, {__index=function() error('equipped read') end})")
        cache = self.lua.table()
        before = dict(self.memory)
        records = self.reader.active(sprite, cache)
        self.assertEqual(len(records), 1)
        self.assertEqual(self.lua.globals().count(cache), 1)
        self.assert_unchanged(before)

    def test_failed_active_scan_does_not_publish_partial_cache(self):
        good = self.effect(active=True)
        bad = self.effect(pointer=BASE + 0x1000, active=True)
        self.put(BASE + 0x1000 + 0xC8, "I", 11)
        cache = self.lua.table()
        with self.assertRaisesRegex(Exception, "caster level"):
            self.reader.active(self.sprite([good, bad]), cache)
        self.assertEqual(self.lua.globals().count(cache), 0)
        with self.assertRaisesRegex(Exception, "duplicate pointer"):
            self.reader.active(self.sprite([good, good]), cache)
        self.assertEqual(self.lua.globals().count(cache), 0)

    def test_is_self_uses_source_id_not_selected_target_id(self):
        effect = self.effect()
        sprite = self.sprite([])
        self.put(BASE + 0xF000 + 0x48, "I", 123)
        self.assertTrue(self.reader.isSelf(effect, sprite))
        self.put(BASE + 0xF000 + 0x48, "I", 999)
        self.assertFalse(self.reader.isSelf(effect, sprite))

    def test_world_time_is_readonly_and_validated(self):
        self.assertEqual(self.reader.now(), 1000)
        clock = self.api.EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime
        clock.m_gameTime = 0xFFFFFFFF
        self.assertEqual(self.reader.now(), 0xFFFFFFFF)
        clock.m_gameTime = -1
        with self.assertRaisesRegex(Exception, "world time"):
            self.reader.now()

    def test_compiler_fields_match_native_non_dice_constructor_layout(self):
        spec = importlib.util.spec_from_file_location("reader_test_manifest", PROTOTYPE / "build_manifest.py")
        compiler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compiler)
        from tests.test_potion_payload_audit import container
        from tests.ie_formats import SplEffect

        item = bytearray(container(groups=((SplEffect(opcode=90, target=1, parameter1=37,
                             duration=123, save_bonus=-3),),)))
        fx = struct.unpack_from("<I", item, 0x6A)[0]
        struct.pack_into("<II", item, fx + 0x1C, 20, 3)  # max/min for non-dice90.
        compiled = compiler.build_manifest({"POTN36.ITM": bytes(item)})
        records = compiled["sources"]["POTN36"]["records"]
        key, fields = next(iter(records.items()))
        self.assertEqual((fields["diceCount"], fields["diceSize"], fields["minLevel"], fields["maxLevel"]),
                         (0, 0, 3, 20))
        reader = self.factory(self.api, self.table(compiled))
        effect = self.effect(fields)
        self.assertEqual(reader.identify(effect, key, True).key, key)
        self.put(BASE + 0x58, "I", 21)
        with self.assertRaisesRegex(Exception, "key mismatch"):
            reader.identify(effect, key, True)

    def linked(self, pointer=BASE, caster=17, duration=180):
        fields=descriptor(nativeSourceType=1,nativeSource="SHARED")
        effect=self.effect(fields,pointer=pointer,source="SHARED")
        self.put(pointer+0x90,"I",1)
        self.put(pointer,"Q",0x140590000)
        self.put(pointer+0xC8,"I",caster)
        self.put(pointer+0x11C,"I",fields["duration"])
        self.put(pointer+0x28,"I",duration)
        return fields,effect

    def test_linked_identity_requires_explicit_provenance_and_keeps_native_source_and_level(self):
        fields,effect=self.linked()
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        before=dict(self.memory)
        self.assertIsNone(reader.identify(effect,None,True))
        reader.bindLinked(effect,"POTN36","linked")
        incoming=reader.identify(effect,"linked",True)
        self.assertEqual((incoming.ownerSource,incoming.source,incoming.sourceType,incoming.expiry),
                         ("POTN36","SHARED",1,180))
        self.put(BASE+0x24,"I",4096)
        self.put(BASE+0x28,"I",3700)
        active=reader.active(self.sprite([effect]),self.lua.table())[1]
        self.assertTrue(self.same(incoming.identity,active.identity))
        self.assertEqual((active.ownerSource,active.source,active.expiry),("POTN36","SHARED",3700))
        expected=dict(before)
        for offset,data in ((0x24,struct.pack('<I',4096)),(0x28,struct.pack('<I',3700))):
            expected.update({BASE+offset+i:b for i,b in enumerate(data)})
        self.assertEqual(expected,self.memory)

    def test_identical_ordinary_spell_is_not_inferred_to_be_potion_owned(self):
        fields,owned=self.linked()
        _,foreign=self.linked(pointer=BASE+0x1000)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(owned,"POTN36","linked")
        for pointer in (BASE,BASE+0x1000):
            self.put(pointer+0x24,"I",4096)
            self.put(pointer+0x28,"I",3700)
        active=reader.active(self.sprite([foreign,owned]),self.lua.table())
        self.assertEqual(1,len(active))
        self.assertTrue(self.same(active[1].object,owned))

    def test_linked_binding_validates_original_duration_and_all_admission_fields(self):
        for offset,value,message in ((0x11C,999,"duration"),(0x10,91,"fields"),
                                     (0xC8,0x8000,"signed16"),(0x90,2,"source"),(0x114,1,"done")):
            with self.subTest(offset=offset):
                fields,effect=self.linked()
                reader=self.factory(self.api,self.table(manifest({"linked":fields})))
                self.put(BASE+offset,"I",value)
                before=dict(self.memory)
                with self.assertRaisesRegex(Exception,message):
                    reader.bindLinked(effect,"POTN36","linked")
                self.assert_unchanged(before)
        fields,effect=self.linked(caster=0xFFFFFFFF,duration=0)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(effect,"POTN36","linked")
        # Construction's signed16/zero-duration semantics are preserved; Core
        # subsequently diagnoses a zero lifetime before any repeat mutation.
        self.assertEqual(0,reader.identify(effect,"linked",True).expiry)

    def test_linked_lifetime_retirement_reset_and_native_mutations_are_not_ignored(self):
        fields,effect=self.linked()
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(effect,"POTN36","linked")
        old=reader.identify(effect,"linked",True)
        with self.assertRaisesRegex(Exception,"already bound"):
            reader.bindLinked(effect,"POTN36","linked")
        self.put(BASE+0xC8,"I",18)
        with self.assertRaisesRegex(Exception,"caster level changed"):
            reader.identify(effect,"linked",True)
        reader.retire(BASE)
        self.assertIsNone(reader.identify(effect,None,True))
        reader.bindLinked(effect,"POTN36","linked")
        new=reader.identify(effect,"linked",True)
        self.assertFalse(self.same(old.identity,new.identity))
        reader.resetTokens()
        self.assertIsNone(reader.identify(effect,None,True))

    def test_direct_item_cannot_match_a_linked_only_descriptor(self):
        fields=descriptor(nativeSourceType=1,nativeSource="SHARED")
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        self.assertIsNone(reader.identify(self.effect(fields),None,True))

    def saved_module(self):
        return self.lua.execute((PROTOTYPE / "CBRPQSaved.lua").read_text())

    def test_saved_linked_owner_restores_new_lifetime_without_claiming_identical_foreign_spell(self):
        fields,potion=self.linked()
        _,foreign=self.linked(pointer=BASE+0x1000)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(potion,"POTN36","linked")
        for p in (BASE,BASE+0x1000):
            self.put(p+0x24,"I",4096)
            self.put(p+0x28,"I",3700)
        saved=self.saved_module()
        data=saved.export(reader.savedRecords(self.sprite([foreign,potion])),reader.savedOwners())
        for old,new in ((BASE,BASE+0x4000),(BASE+0x1000,BASE+0x5000)):
            for i in range(0x180):
                self.memory[new+i]=self.memory[old+i]
            self.put(new+0x50,"I",0xAABBCCDD)  # Native V2 does not restore this padding.
            self.put(new+0x11C,"I",0)  # Nor the original resource duration.
        p=self.lua.globals().mockObject(BASE+0x4000)
        f=self.lua.globals().mockObject(BASE+0x5000)
        reader.resetTokens()
        sprite=self.sprite([f,p])
        before=dict(self.memory)
        reader.restoreSaved(reader.savedRecords(sprite),data,saved)
        active=reader.active(sprite,self.lua.table())
        self.assertEqual(1,len(active))
        self.assertTrue(self.same(active[1].object,p))
        self.assertEqual((active[1].ownerSource,active[1].source,active[1].expiry),("POTN36","SHARED",3700))
        with self.assertRaisesRegex(Exception,"not a newly constructed child"):
            reader.identify(p,"linked",True)
        self.assert_unchanged(before)

    def test_saved_import_rejects_stale_snapshot_before_publishing_any_owner(self):
        fields,potion=self.linked()
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(potion,"POTN36","linked")
        self.put(BASE+0x24,"I",4096)
        self.put(BASE+0x28,"I",3700)
        saved=self.saved_module()
        sprite=self.sprite([potion])
        data=saved.export(reader.savedRecords(sprite),reader.savedOwners())
        reader.resetTokens()
        records=reader.savedRecords(sprite)
        self.put(BASE+0x28,"I",3800)
        before=dict(self.memory)
        with self.assertRaisesRegex(Exception,"changed after snapshot"):
            reader.restoreSaved(records,data,saved)
        self.assertIsNone(reader.identify(potion,None,False))
        self.assert_unchanged(before)

    def test_saved_bad_owner_does_not_partially_bind_other_valid_occurrences(self):
        fields,a=self.linked()
        _,b=self.linked(pointer=BASE+0x1000)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        for pointer,effect in ((BASE,a),(BASE+0x1000,b)):
            reader.bindLinked(effect,"POTN36","linked")
            self.put(pointer+0x24,"I",4096)
            self.put(pointer+0x28,"I",3700)
        sprite=self.sprite([a,b])
        saved=self.saved_module()
        data=saved.export(reader.savedRecords(sprite),reader.savedOwners())
        group=next(iter(data.groups.values()))
        group.owned[2].source="UNKNOWN"
        reader.resetTokens()
        before=dict(self.memory)
        with self.assertRaisesRegex(Exception,"differs from manifest"):
            reader.restoreSaved(reader.savedRecords(sprite),data,saved)
        self.assertIsNone(reader.identify(a,None,False))
        self.assertIsNone(reader.identify(b,None,False))
        self.assert_unchanged(before)

    def live_copy(self, source=BASE, destination=BASE+0x4000):
        # Byte-memory service double for the separately proven native virtual
        # Copy -> CopyFromBase contract, including its nontrivial constructor
        # defaults. The native probe, not this helper, establishes those fields.
        for offset in range(0x180):
            self.memory[destination+offset]=self.memory[source+offset]
        self.put(destination+0x114,"I",0)
        self.put(destination+0x11C,"I",self.read(source+0x28,"I"))
        self.put(destination+0x150,"I",0xFFFFFFFF)
        return self.lua.globals().mockObject(destination)

    def test_live_copy_retains_only_proven_owner_and_uses_a_fresh_lifetime(self):
        fields,original=self.linked(caster=0xFFFFFFFF,duration=180)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(original,"POTN36","linked")
        source=reader.identify(original,"linked",True)
        duplicate=self.live_copy()
        before=dict(self.memory)
        self.assertTrue(reader.copyLinked(duplicate,BASE))
        copy_record=reader.identify(duplicate,"linked",True)
        self.assertEqual((copy_record.ownerSource,copy_record.source,copy_record.expiry),
                         ("POTN36","SHARED",180))
        self.assertFalse(self.same(source.identity,copy_record.identity))
        reader.retire(BASE)
        self.assertIsNone(reader.identify(original,None,True))
        self.assertIsNotNone(reader.identify(duplicate,"linked",True))
        self.assert_unchanged(before)

    def test_active_live_copy_is_not_a_new_dose_and_keeps_hp_consumption_bit(self):
        fields=descriptor(opcode=18,amount=110,mode=2,special=0,
                          nativeSourceType=1,nativeSource="SHARED")
        original=self.effect(fields,source="SHARED")
        self.put(BASE,"Q",0x140590000)
        self.put(BASE+0x90,"I",1)
        self.put(BASE+0x11C,"I",120)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(original,"POTN36","linked")
        self.put(BASE+0x24,"I",4096)
        self.put(BASE+0x28,"I",3700)
        self.put(BASE+0x48,"I",1)
        duplicate=self.live_copy()
        before=dict(self.memory)
        self.assertTrue(reader.copyLinked(duplicate,BASE))
        self.assertEqual(reader.identify(duplicate,"linked",False).expiry,3700)
        with self.assertRaisesRegex(Exception,"not a newly constructed child"):
            reader.identify(duplicate,"linked",True)
        self.assert_unchanged(before)

    def test_unknown_copy_source_does_not_read_native_memory_or_infer_shared_spell_owner(self):
        _,foreign=self.linked()
        fields,owned=self.linked(pointer=BASE+0x1000)
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(owned,"POTN36","linked")
        duplicate=self.live_copy()
        self.reads.clear()
        self.assertFalse(reader.copyLinked(duplicate,BASE))
        self.assertFalse(reader.copyLinked(None,BASE+0xF000))
        self.assertEqual(self.reads,[])
        self.assertIsNone(reader.identify(duplicate,None,False))

    def test_copy_rejects_drift_and_does_not_publish_partial_ownership(self):
        for offset,value,reason in ((0,0x140590001,"class"),(0x90,2,"source"),
                (0x1C,41,"field amount"),(0x28,999,"timing/caster"),
                (0xC8,19,"timing/caster"),(0x110,555,"constructor"),
                (0x114,1,"constructor"),(0x11C,120,"constructor"),
                (0x150,123,"constructor")):
            with self.subTest(offset=offset):
                fields,original=self.linked()
                reader=self.factory(self.api,self.table(manifest({"linked":fields})))
                reader.bindLinked(original,"POTN36","linked")
                duplicate=self.live_copy()
                self.put(BASE+0x4000+offset,"Q" if offset==0 else "I",value)
                before=dict(self.memory)
                with self.assertRaisesRegex(Exception,reason):
                    reader.copyLinked(duplicate,BASE)
                self.assertIsNone(reader.identify(duplicate,None,False))
                self.assert_unchanged(before)

    def test_copy_rejects_duplicate_binding_and_retirement_blocks_address_reuse(self):
        fields,original=self.linked()
        reader=self.factory(self.api,self.table(manifest({"linked":fields})))
        reader.bindLinked(original,"POTN36","linked")
        with self.assertRaisesRegex(Exception,"destination already owned"):
            reader.copyLinked(original,BASE)
        duplicate=self.live_copy()
        self.assertTrue(reader.copyLinked(duplicate,BASE))
        with self.assertRaisesRegex(Exception,"destination already owned"):
            reader.copyLinked(duplicate,BASE)
        reader.retire(BASE)
        self.linked()  # Reused address, byte-identical unrelated effect.
        self.reads.clear()
        self.assertFalse(reader.copyLinked(duplicate,BASE))
        self.assertEqual(self.reads,[])


if __name__ == "__main__":
    unittest.main()
