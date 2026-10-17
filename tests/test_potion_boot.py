"""Connected portable compiler/startup ordering, with engine and hook doubles."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime, LuaError
from tests.test_potion_admission_manifest import fx, potion, compiler

ROOT = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


class PotionBootTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        parts = self.lua.table()
        for key, filename in ((b"compiler", "CBRPQCompile.lua"), (b"hash", "CBRPQHash.lua")):
            parts[key] = self.lua.execute((ROOT / filename).read_bytes())
        self.lua.globals()[b"parts"] = parts
        self.lua.globals()[b"boot"] = self.lua.execute((ROOT / "CBRPQBoot.lua").read_bytes())
        self.lua.execute(b'''
            bytes, reads, diagnostics, prepared, armed = {}, {}, {}, 0, 0
            parts.resources=function(api) return function(name)
                reads[#reads+1]=name
                return bytes[name], "missing current resource: "..name
            end end
            parts.lab={prepare=function(api,p,manifest,report)
                prepared=prepared+1
                assert(manifest.sources.POTN36.records~=nil)
                return {arm=function() armed=armed+1 end}
            end}
            report=function(reason) diagnostics[#diagnostics+1]=reason end
            options={version=1,policy="unique",names={"POTN36.ITM","DW#PTN36.ITM"}}
            function prepare() return boot.prepare(_G,parts,options,report) end
        ''')

    def data(self, resources):
        self.lua.globals()[b"bytes"] = self.lua.table_from({k.encode(): v for k, v in resources.items()})

    def test_compiles_effective_resources_before_prepare_and_never_arms_itself(self):
        resources = {"POTN36.ITM": potion([fx(90, 33)]), "DW#PTN36.ITM": potion([fx(90, 33)])}
        self.data(resources)
        lab, manifest = self.lua.globals()[b"prepare"]()
        self.assertEqual(1, self.lua.globals()[b"prepared"])
        self.assertEqual(0, self.lua.globals()[b"armed"])
        source = manifest[b"sources"][b"POTN36"]
        key = next(iter(source[b"records"].keys()))
        self.assertEqual(33, source[b"records"][key][b"amount"])
        self.assertEqual(compiler.build_manifest(resources)["sources"]["POTN36"]["records"][key.decode()]["amount"], 33)
        lab[b"arm"]()
        self.assertEqual(1, self.lua.globals()[b"armed"])
        self.lua.execute(b'assert(#diagnostics==0)')

    def test_unsupported_or_missing_current_data_never_prepares_any_hook(self):
        for resources in ({}, {"POTN36.ITM": potion([fx(999,1)]), "DW#PTN36.ITM": potion([fx(999,1)])}):
            with self.subTest(resources=bool(resources)):
                self.setUp()
                self.data(resources)
                with self.assertRaises(LuaError):
                    self.lua.globals()[b"prepare"]()
                self.lua.execute(b'assert(prepared==0 and armed==0 and #diagnostics==1)')

    def test_reader_is_consistent_for_revisited_hp_sources(self):
        resources = {"POTN36.ITM": potion([fx(18,110,parameter2=2)]),
                     "DW#PTN36.ITM": potion([fx(18,110,parameter2=2)])}
        self.data(resources)
        self.lua.globals()[b"prepare"]()
        self.lua.execute(b'assert(#reads==2)')


if __name__ == "__main__":
    unittest.main()
