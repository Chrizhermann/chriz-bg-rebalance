"""Owned mode1 registry fixtures; runtime admission/save wiring is separate."""
from dataclasses import replace
import struct
import unittest

from tests.test_potion_admission_manifest import compiler,fx,potion
from tests.test_potion_payload_audit import container


def cast(name): return replace(fx(146,0,parameter2=1,resource=name),timing=1)


class LinkedManifestTests(unittest.TestCase):
    def compile(self,items,spells):
        before=dict(items,**spells)
        result=compiler.build_manifest(items,read_resource=spells.__getitem__)
        self.assertEqual(before,dict(items,**spells))
        return result

    def test_direct_cast_and_shared_spl_have_separate_native_and_logical_identity(self):
        spell=bytearray(container("SPL",groups=[[fx(),fx(17,5)]],effects_first=True))
        spell[0x25],spell[0x27]=3,7
        struct.pack_into("<I",spell,0x18,0x80001234)
        result=self.compile({"POTN36.ITM":potion([cast("SHARED")]),
                             "DW#PTN36.ITM":potion([cast("SHARED")])},{"SHARED.SPL":bytes(spell)})
        source=result["sources"]["POTN36"]
        self.assertEqual("POTN36",result["sources"]["DW#PTN36"]["family"])
        ability=source["abilities"]["0"]
        self.assertFalse(ability["effects"]["0"])
        self.assertEqual("SHARED",ability["carriers"]["0"]["call"])
        call=source["calls"]["SHARED"]["abilities"]["0"]
        key=call["effects"]["0"]
        self.assertFalse(call["effects"]["1"])
        record=source["records"][key]
        self.assertEqual((1,{"SHARED":True},3,7,0x80001234),
            (record["nativeSourceType"],record["nativeSources"],record["school"],
             record["secondary"],record["sourceFlags"]))
        self.assertEqual({key:1},ability["quotas"])

    def test_two_native_spell_sources_merge_only_declared_semantic_children(self):
        child=container("SPL",groups=[[fx()]])
        result=self.compile({"POTN36.ITM":potion([cast("FIRST"),cast("SECOND")])},
                            {"FIRST.SPL":child,"SECOND.SPL":child})
        source=result["sources"]["POTN36"]
        self.assertEqual(1,len(source["keys"]))
        key=next(iter(source["keys"]))
        self.assertEqual({"FIRST":True,"SECOND":True},source["records"][key]["nativeSources"])
        self.assertEqual({key:2},source["abilities"]["0"]["quotas"])

    def test_different_native_spell_type_or_level_does_not_infer_a_clone(self):
        canonical=bytearray(container("SPL",groups=[[fx()]]))
        struct.pack_into("<H",canonical,0x1C,1)
        struct.pack_into("<I",canonical,0x34,3)
        for spell_type,level in ((4,3),(1,9)):
            with self.subTest(spell_type=spell_type,level=level):
                other=bytearray(canonical)
                struct.pack_into("<H",other,0x1C,spell_type)
                struct.pack_into("<I",other,0x34,level)
                result=self.compile({"POTN36.ITM":potion([cast("CANON")]),
                    "OTHER.ITM":potion([cast("DIFFER")])},
                    {"CANON.SPL":bytes(canonical),"DIFFER.SPL":bytes(other)})
                self.assertEqual("OTHER",result["sources"]["OTHER"]["family"])
                # Native effect metadata remains identical; these header
                # differences belong to graph identity, not invented fields.
                self.assertEqual(result["sources"]["POTN36"]["keys"],result["sources"]["OTHER"]["keys"])

    def test_matching_native_spell_semantics_preserve_clone_and_header_order(self):
        canonical=bytearray(container("SPL",groups=[[fx(),fx(19,4)],[fx(19,4),fx()]],effects_first=True))
        struct.pack_into("<H",canonical,0x1C,1)
        struct.pack_into("<I",canonical,0x34,3)
        copied=bytearray(canonical)
        # The native getter consumes low16 only. Unconsumed high bits do not
        # turn an otherwise exact proven clone into a different policy family.
        struct.pack_into("<I",copied,0x34,0x10003)
        result=self.compile({"POTN36.ITM":potion([cast("CANON")]),
            "COPY36.ITM":potion([cast("COPY")])},
            {"CANON.SPL":bytes(canonical),"COPY.SPL":bytes(copied)})
        self.assertEqual("POTN36",result["sources"]["COPY36"]["family"])
        self.assertEqual(2,len(result["sources"]["COPY36"]["calls"]["COPY"]["abilities"]))

    def test_multiple_headers_reordered_records_duplicate_quotas_and_globals_are_preserved(self):
        child=bytearray(container("SPL",groups=[[fx(),fx(19,4)],[fx(19,4),fx(),fx()]],
            global_indices=[fx(200,6)],effects_first=True))
        aoff=struct.unpack_from("<I",child,0x64)[0]
        struct.pack_into("<H",child,aoff+0x10,1)
        struct.pack_into("<H",child,aoff+0x28+0x10,9)
        result=self.compile({"POTN36.ITM":potion([cast("CHILD")])},{"CHILD.SPL":bytes(child)})
        source=result["sources"]["POTN36"]; call=source["calls"]["CHILD"]
        self.assertEqual((1,9),(call["abilities"]["0"]["minimumLevel"],call["abilities"]["1"]["minimumLevel"]))
        key=call["abilities"]["0"]["effects"]["0"]
        self.assertEqual(key,call["abilities"]["1"]["effects"]["1"])
        self.assertEqual(key,call["abilities"]["1"]["effects"]["2"])
        self.assertEqual(2,source["abilities"]["0"]["quotas"][key])
        self.assertEqual({90,19},{r["opcode"] for r in source["records"].values()})

    def test_nested_mode1_calls_reserve_root_dose_quotas(self):
        spells={"PARENT.SPL":container("SPL",groups=[[cast("CHILD"),cast("CHILD")]]),
                "CHILD.SPL":container("SPL",groups=[[fx(),fx()]])}
        result=self.compile({"POTN36.ITM":potion([cast("PARENT")])},spells)
        source=result["sources"]["POTN36"]; key=next(iter(source["keys"]))
        self.assertEqual({key:4},source["abilities"]["0"]["quotas"])
        self.assertEqual("CHILD",source["calls"]["PARENT"]["abilities"]["0"]["carriers"]["1"]["call"])

    def test_selected_header_potency_change_is_diagnosed_before_advertising_safe_refresh(self):
        child=container("SPL",groups=[[fx(90,10)],[fx(90,20)]])
        with self.assertRaises(compiler.ManifestError) as raised:
            self.compile({"POTN36.ITM":potion([cast("CHILD")])},{"CHILD.SPL":child})
        self.assertEqual("LINK_VARIANT_CAPABILITY",raised.exception.code)

    def test_linked_hp_sets_entire_family_policy_including_non_hp_alias(self):
        spells={"HP.SPL":container("SPL",groups=[[fx(18,10),fx()]]),
                "SKILL.SPL":container("SPL",groups=[[fx()]])}
        result=self.compile({"POTN09.ITM":potion([cast("HP")]),
            "DW#PTN09.ITM":potion([cast("SKILL")])},spells)
        self.assertTrue(result["families"]["POTN09"]["hp"])
        self.assertEqual("POTN09",result["sources"]["DW#PTN09"]["family"])

    def test_constitution_setter_only_copy_is_grouped_before_final_hp_ownership(self):
        bonuses=[fx(44,25,parameter2=1),fx(10,3,parameter2=1),fx(15,3,parameter2=1)]
        for linked in (False,True):
            with self.subTest(linked=linked):
                payload=[cast("CHILD")] if linked else bonuses
                spells={"CHILD.SPL":container("SPL",groups=[bonuses])} if linked else {}
                result=self.compile({"POTN16.ITM":potion(payload),"COPY16.ITM":potion(payload)},spells)
                self.assertEqual("POTN16",result["sources"]["COPY16"]["family"])
                self.assertTrue(result["families"]["POTN16"]["hp"])
                self.assertEqual(3,len(result["sources"]["COPY16"]["keys"]))


if __name__=="__main__": unittest.main()
