"""Exact quota arithmetic and small real graphs; no billion-record allocation.

Boundary cases call the actual private merge helpers (Lua through debug
upvalues), not replacement formulas. Public compiler cases exercise nested,
shared and repeated original routes and compare complete Python/Lua manifests.
"""
from dataclasses import replace
import unittest

from lupa.luajit21 import LuaError
from tests.test_potion_admission_manifest import compiler, fx, potion
from tests.test_potion_admission_lua_compiler import LuaCompiler, ROOT
from tests.test_potion_payload_audit import container


MAX = 0xFFFFFFFF


def cast(resource):
    return replace(fx(146, 0, parameter2=1, resource=resource), timing=1)


class LinkedQuotaBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()
        find = cls.port.lua.eval(b"""function(root, wanted)
            local seen={}
            local function visit(fn)
                if seen[fn] then return end
                seen[fn]=true
                for index=1,math.huge do
                    local name,value=debug.getupvalue(fn,index)
                    if not name then break end
                    if name==wanted then return value end
                    if type(value)=='function' then
                        local found=visit(value)
                        if found then return found end
                    end
                end
            end
            local found=visit(root)
            assert(found,'private quota helper not reachable')
            return found
        end""")
        cls.lua_merge = find(cls.port.compile, b"addQuotas")
        cls.lua_add = find(cls.port.compile, b"addQuota")
        cls.core = cls.port.lua.execute((ROOT / "CBRPQCore.lua").read_bytes())

    def test_core_accepts_exact_maximum_after_ordinary_duplicate_merge(self):
        # Two valid previously expanded child counts plus an ordinary final
        # duplicate land exactly on the public Core capacity.
        py, lua = {}, self.port.lua.table()
        for count in (MAX - 2, 1, 1):
            compiler._add_quotas(py, {"key": count}, "fixture")
            self.lua_merge(lua, self.port.lua.table_from({b"key": count}), b"fixture")
        self.assertEqual({"key": MAX}, py)
        self.assertEqual(py, self.port.convert(lua))
        dose = self.core[b"newDose"](self.port.lua.table(), b"FAMILY", lua)
        self.assertEqual(MAX, dose[b"quotas"][b"key"])
        self.assertEqual(MAX, lua[b"key"])

    def test_one_more_duplicate_rejects_before_mutating_count(self):
        py, lua = {"key": MAX}, self.port.lua.table_from({b"key": MAX})
        with self.assertRaises(compiler.ManifestError) as error:
            compiler._add_quota(py, "key", 1, "root effect7")
        self.assertEqual("QUOTA_CAPABILITY", error.exception.code)
        self.assertIn("root effect7", str(error.exception))
        with self.assertRaisesRegex(LuaError, "QUOTA_CAPABILITY: root effect7"):
            self.lua_add(lua, b"key", 1, b"root effect7")
        self.assertEqual({"key": MAX}, py)
        self.assertEqual(py, self.port.convert(lua))

    def test_full_u16_route_count_remains_exact_and_next_merge_fails(self):
        # 65535 * 65537 == UINT32_MAX. This models the actual per-original
        # route merge loop without allocating enormous semantic descriptors.
        py, lua = {}, self.port.lua.table()
        child = self.port.lua.table_from({b"key": 65537})
        run = self.port.lua.eval(b"""function(merge,target,child)
            for ordinal=1,65535 do merge(target,child,'route '..ordinal) end
        end""")
        for _ in range(65535):
            compiler._add_quotas(py, {"key": 65537}, "route")
        run(self.lua_merge, lua, child)
        self.assertEqual({"key": MAX}, py)
        self.assertEqual(py, self.port.convert(lua))
        with self.assertRaises(compiler.ManifestError):
            compiler._add_quotas(py, {"key": 65537}, "overflow route")
        with self.assertRaisesRegex(LuaError, "QUOTA_CAPABILITY"):
            self.lua_merge(lua, child, b"overflow route")
        self.assertEqual(py, self.port.convert(lua))

    def test_oversized_and_inexact_counts_fail_without_number_precision_drift(self):
        for count in (0, -1, MAX + 1, 2**53, 2**53 + 1, 1.5, float("inf"), float("nan")):
            with self.subTest(count=count):
                py, lua = {}, self.port.lua.table()
                with self.assertRaises(compiler.ManifestError) as error:
                    compiler._add_quotas(py, {"key": count}, "child")
                self.assertEqual("QUOTA_CAPABILITY", error.exception.code)
                with self.assertRaisesRegex(LuaError, "QUOTA_CAPABILITY"):
                    self.lua_merge(lua, self.port.lua.table_from({b"key": count}), b"child")
                self.assertEqual({}, py)
                self.assertEqual({}, self.port.convert(lua))
        # Distinct keys each retain the Core's per-key limit; no accidental
        # aggregate quota cap is imposed on unrelated logical effects.
        py, lua = {}, self.port.lua.table()
        values = {"first": MAX, "second": MAX}
        compiler._add_quotas(py, values, "distinct")
        self.lua_merge(lua, self.port.lua.table_from({k.encode(): v for k, v in values.items()}), b"distinct")
        self.assertEqual(values, py)
        self.assertEqual(py, self.port.convert(lua))

    def compare(self, items, spells):
        before = dict(items, **spells)
        py = compiler.build_manifest(items, read_resource=spells.__getitem__)
        lua = self.port.build(items, read_resource=spells.__getitem__)
        self.assertEqual(py, lua)
        self.assertEqual(before, dict(items, **spells))
        return py

    def test_nested_shared_graph_adds_each_route_and_each_duplicate_once(self):
        spells = {
            "LEAF.SPL": container("SPL", groups=[[fx(), fx()]]),
            "LEFT.SPL": container("SPL", groups=[[cast("LEAF"), cast("LEAF")]]),
            "RIGHT.SPL": container("SPL", groups=[[cast("LEAF"), cast("LEFT")]]),
            "TOP.SPL": container("SPL", groups=[[cast("LEFT"), cast("RIGHT")]]),
        }
        items = {"POTN36.ITM": potion([cast("TOP"), cast("LEAF"), cast("TOP")],
                                       [cast("LEAF"), cast("TOP"), cast("TOP")])}
        manifest = self.compare(items, spells)
        source = manifest["sources"]["POTN36"]
        self.assertEqual(1, len(source["keys"]))
        key = next(iter(source["keys"]))
        for name, count in (("LEAF", 2), ("LEFT", 4), ("RIGHT", 6), ("TOP", 10)):
            self.assertEqual({key: count}, source["calls"][name]["quotas"])
        for ability in source["abilities"].values():
            self.assertEqual({key: 22}, ability["quotas"])

    def test_header_maximum_is_not_sum_and_direct_keys_stay_distinct(self):
        spells = {"CHILD.SPL": container("SPL", groups=[[fx()], [fx(), fx(), fx()]])}
        manifest = self.compare({"POTN36.ITM": potion([fx(), cast("CHILD"), cast("CHILD")])}, spells)
        source = manifest["sources"]["POTN36"]
        call = source["calls"]["CHILD"]
        child_key = next(iter(call["quotas"]))
        direct_key = source["abilities"]["0"]["effects"]["0"]
        self.assertNotEqual(child_key, direct_key)
        self.assertEqual({child_key: 3}, call["quotas"])
        self.assertEqual({direct_key: 1, child_key: 6}, source["abilities"]["0"]["quotas"])


class LinkedCarrierTimingBoundsTests(unittest.TestCase):
    """Native Resolve1E8516..1E8649 delays3..8, losing the delivery frame.

    Mode146/1 Apply queues1A8594 and marks Done1A886E. Other raw-byte timing
    modes fall through Apply1E8668 while the original delivery is still live.
    The native timing probe uses controlled allocation/queue services, not a
    live game or full Lua/native composition. These tests assert preflight.
    """
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()

    def compare(self, items, spells, code=None):
        before = dict(items, **spells)
        if code:
            with self.assertRaises(compiler.ManifestError) as error:
                compiler.build_manifest(items, read_resource=spells.__getitem__)
            self.assertEqual(code, error.exception.code)
            with self.assertRaisesRegex(LuaError, code + ":"):
                self.port.build(items, read_resource=spells.__getitem__)
            result = None
        else:
            result = compiler.build_manifest(items, read_resource=spells.__getitem__)
            self.assertEqual(result, self.port.build(items, read_resource=spells.__getitem__))
        self.assertEqual(before, dict(items, **spells))
        return result

    def test_delayed_root_and_cached_nested_owned_carriers_diagnose(self):
        leaf = container("SPL", groups=[[fx()]])
        for timing in range(3, 9):
            for duration in (0, 600):
                with self.subTest(timing=timing, duration=duration):
                    delayed = replace(cast("LEAF"), timing=timing, duration=duration)
                    self.compare({"POTN36.ITM": potion([cast("LEAF"), delayed])},
                                 {"LEAF.SPL": leaf}, "LINK_TIMING_CAPABILITY")
                    # The immediate first use caches LEAF; the second delayed
                    # carrier must still be checked before returning that cache.
                    spells = {"LEAF.SPL": leaf,
                              "PARENT.SPL": container("SPL", groups=[[cast("LEAF"), delayed]])}
                    self.compare({"POTN36.ITM": potion([cast("PARENT")])}, spells,
                                 "LINK_TIMING_CAPABILITY")

    def test_immediate_native_timings_preserve_carrier_fields_and_quotas(self):
        for timing in (0, 1, 2, 9, 10, 11, 255):
            with self.subTest(timing=timing):
                carrier = replace(cast("LEAF"), timing=timing, duration=123)
                spells = {"LEAF.SPL": container("SPL", groups=[[fx()]]),
                          "PARENT.SPL": container("SPL", groups=[[carrier]])}
                result = self.compare({"POTN36.ITM": potion([carrier, cast("PARENT")])}, spells)
                source = result["sources"]["POTN36"]
                key = next(iter(source["keys"]))
                self.assertEqual({key: 2}, source["abilities"]["0"]["quotas"])
                root = source["abilities"]["0"]["carriers"]["0"]["fields"]
                nested = source["calls"]["PARENT"]["abilities"]["0"]["carriers"]["0"]["fields"]
                for descriptor in (root, nested):
                    self.assertEqual((timing, 123), (descriptor["timing"], descriptor["duration"]))

    def test_equipped_global_has_no_dose_even_when_native_timing_is_immediate(self):
        self.compare({"POTN36.ITM": potion([], globals=[replace(cast("LEAF"), timing=2)])},
                     {"LEAF.SPL": container("SPL", groups=[[fx()]])}, "EQUIPPED_CAPABILITY")

    def test_harmless_delayed_branch_remains_native_in_mixed_graph(self):
        for timing in range(3, 9):
            delayed = replace(cast("CURE"), timing=timing)
            spells = {"CURE.SPL": container("SPL", groups=[[replace(fx(17, 8), timing=1)]]),
                      "PARENT.SPL": container("SPL", groups=[[delayed, fx()]])}
            result = self.compare({"POTN36.ITM": potion([delayed, cast("PARENT")])}, spells)
            source = result["sources"]["POTN36"]
            self.assertEqual({"PARENT"}, set(source["calls"]))
            self.assertIs(False, source["abilities"]["0"]["effects"]["0"])
            self.assertNotIn("0", source["abilities"]["0"]["carriers"])
            child = source["calls"]["PARENT"]["abilities"]["0"]
            self.assertIs(False, child["effects"]["0"])
            self.assertFalse(child["carriers"])


if __name__ == "__main__":
    unittest.main()
