"""Small offline check of table policy and EEex hook preparation, not game acceptance."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "chriz-bg-rebalance/bard"
RUNTIME = ROOT / "chriz-bg-rebalance/lua/M_CBRSP.lua"


def rows(name):
    return [line.split() for line in (DATA / f"{name}.2da").read_text().splitlines()[3:] if line.strip()]


class BardProgressionTests(unittest.TestCase):
    def test_caps_unlocks_and_level32_counts(self):
        expected = {
            "CBRBG6": [5, 5, 5, 5, 5, 4, 0, 0, 0],
            "CBRIWD7": [6, 6, 6, 6, 6, 5, 5, 0, 0],
            "CBRIWD8": [6, 6, 6, 6, 6, 5, 5, 1, 0],
        }
        tables = {name: {int(r[0]): list(map(int, r[1:])) for r in rows(name)} for name in expected}
        for name, counts in expected.items():
            self.assertEqual(tables[name][32], counts)
            self.assertEqual(tables[name][1], [0] * 9)
            self.assertEqual(set(tables[name]), set(range(1, 51)))
        self.assertEqual(tables["CBRIWD7"][20][6], 0)
        self.assertEqual(tables["CBRIWD7"][21][6], 1)
        self.assertEqual(tables["CBRIWD8"][28][7], 0)
        self.assertEqual(tables["CBRIWD8"][29][7], 1)
        self.assertTrue(all(r[7:] == [0, 0] for r in tables["CBRIWD7"].values()))

    def runtime(self, *, bad_signature=False, conflict=False, iwdee=False):
        lua = LuaRuntime()
        lua.execute(r'''
            EEex_Active = true
            hooks, disabled, enabled, loads = 0, 0, 0, 0
            resources = {}
            function resource(name, columns, records)
                local r = {name=name, columns=columns, records=records}
                function r:findColumnLabel(label)
                    for i,c in ipairs(self.columns) do if c == label then return i-1 end end
                    return -1
                end
                function r:getDimensions() return #self.columns+1, #self.records end
                function r:getAtLabels(col, row)
                    for _,record in ipairs(self.records) do
                        if record[1] == row then return record[self:findColumnLabel(col)+2] end
                    end
                    return "0"
                end
                resources[name] = r
            end
            function EEex_Resource_Load2DA(name) loads=loads+1; return resources[name] end
            function EEex_Resource_Get2DARowTableIterator(r)
                local i=0
                return function() i=i+1; return r.records[i] end
            end
            function EEex_TryLabel() return 4096 end
            signature={0x48,0x8D,0x8E,0x38,0x07,0,0,0x4C,0x8D,0x45,0xF0,0x48,
                0x8D,0x55,0xF8,0xE8,0x98,0x30,0xED,0xFF,0x4C,0x8D,0x45,0xE4}
            function EEex_ReadU8(p) return signature[p-4095] end
            function EEex_UDToPtr(r) return ({CBRBG6=10000,CBRIWD7=20000,CBRIWD8=30000})[r.name] end
            function EEex_DisableCodeProtection() disabled=disabled+1 end
            function EEex_EnableCodeProtection() enabled=enabled+1 end
            EEex_HookIntegrityWatchdogRegister={RCX=1}
            function EEex_HookAfterRestoreWithLabels(site,delay,size,back,labels,assembly)
                assert(site==4096 and delay==0 and size==7 and back==7)
                hooks=hooks+1; generated=table.concat(assembly,"\n")
            end
            function EEex_GameState_AddInitializedListener(f) listener=f end
            resource("CBRSPVER", {"VALUE"}, {{"API","1"}})
            resource("CBRSPKIT", {"CLASS","KIT","TABLE"}, {
                {"5","16384","CBRIWD7"}, {"5","16389","CBRBG6"}, {"5","16500","CBRIWD8"},
                {"2","99999","UNRELATED"}})
        ''')
        for name in ("CBRBG6", "CBRIWD7", "CBRIWD8"):
            lua.globals().resource(name, lua.table_from([str(i) for i in range(1, 10)]),
                                   lua.table_from(rows(name), recursive=True))
        if bad_signature:
            lua.execute("signature[1]=0xE9")
        if iwdee:
            lua.execute("signature[17]=0x28")
        if conflict:
            lua.execute('table.insert(resources.CBRSPKIT.records, {"5","16384","CBRIWD8"})')
        lua.execute(RUNTIME.read_text())
        lua.execute("listener()")
        return lua

    def test_prepares_one_hook_and_keeps_tables_alive_on_reload(self):
        lua = self.runtime()
        g = lua.globals()
        self.assertEqual(g.CBRSpellProgression.Status, "active")
        self.assertEqual((g.hooks, g.disabled, g.enabled), (1, 1, 1))
        self.assertIn("mov rcx, 30000", g.generated)
        self.assertEqual(g.CBRSpellProgression.GetBaseSlots(16500, 32, 8), 1)
        self.assertIsNone(g.CBRSpellProgression.GetBaseSlots(99999, 32, 8))
        before = g.loads
        lua.execute(RUNTIME.read_text())
        self.assertEqual((g.hooks, g.loads), (1, before))

    def test_changed_instructions_do_not_install_hook(self):
        g = self.runtime(bad_signature=True).globals()
        self.assertEqual((g.hooks, g.disabled), (0, 0))
        self.assertIn("lookup changed", g.CBRSpellProgression.Status)

    def test_iwdee_call_displacement_uses_the_same_hook(self):
        g = self.runtime(iwdee=True).globals()
        self.assertEqual(g.CBRSpellProgression.Status, "active")
        self.assertEqual(g.hooks, 1)
        self.assertEqual(g.CBRSpellProgression.GetBaseSlots(16500, 32, 8), 1)

    def test_conflicting_registration_does_not_install_hook(self):
        g = self.runtime(conflict=True).globals()
        self.assertEqual((g.hooks, g.disabled), (0, 0))
        self.assertIn("conflicting tables", g.CBRSpellProgression.Status)


if __name__ == "__main__":
    unittest.main()
