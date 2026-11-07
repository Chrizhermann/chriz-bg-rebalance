"""Small offline check of table policy and EEex hook preparation, not game acceptance."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from lupa.luajit21 import LuaRuntime
from tests.test_cloud_forms import Game, WEIDU
from tests.test_flail_of_ages import strings
from tests.ie_formats import TwoDA

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

    def runtime(self, *, bad_signature=False, conflict=False, iwdee=False, edit=None):
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
        if edit:
            lua.execute(edit)
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

    def test_last_registration_wins_without_blocking_hook(self):
        g = self.runtime(conflict=True).globals()
        self.assertEqual((g.hooks, g.disabled), (1, 1))
        self.assertEqual("CBRIWD8", g.CBRSpellProgression.kits[16384])

    def test_reordered_extra_columns_and_changed_api_marker_are_accepted(self):
        g = self.runtime(edit='''
            resources.CBRSPVER = nil
            resources.CBRSPKIT.columns = {"EXTRA", "TABLE", "KIT", "CLASS"}
            resources.CBRSPKIT.records = {{"ignored", "CBRIWD7", "16384", "5"}}
        ''').globals()
        self.assertEqual("active", g.CBRSpellProgression.Status)
        self.assertEqual("CBRIWD7", g.CBRSpellProgression.kits[16384])

    def test_missing_table_is_local_and_empty_table_does_not_block_registration(self):
        g = self.runtime(edit='''
            resources.CBRBG6 = nil
            resources.CBRIWD8.records = {}
            resources.CBRIWD8.columns = {"3"}
        ''').globals()
        self.assertEqual("active", g.CBRSpellProgression.Status)
        self.assertEqual("CBRIWD7", g.CBRSpellProgression.kits[16384])
        self.assertEqual("CBRIWD8", g.CBRSpellProgression.kits[16500])


class BardInstallerTests(unittest.TestCase):
    def game(self, resources=None):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-bard-")
        self.addCleanup(temporary.cleanup)
        base = {
            "KIT.IDS": b"IDS V1.0\n0x400D BLADE\n0x400E JESTER\n0x400F SKALD\n",
            "KITLIST.2DA": b"2DA V1.0\n0\n ROWNAME HELP CLASS\n13 BLADE nonsense 99\n14 JESTER -1 5\n15 SKALD 1 5\n",
            "CLASTEXT.2DA": b"2DA V1.0\n0\n DESCSTR ID\nBARD -1 5\nJESTER rubbish 5\n",
        }
        if resources:
            base.update(resources)
        return Game(Path(temporary.name), base, public=True, texts=["Shared foreign text.", "Hand edited."])

    def install(self, game, name="bard", language="en_us", extra=""):
        (game.root / f"{name}.tp2").write_text('''BACKUP ~backup/''' + name + '''~
AUTHOR ~offline~
BEGIN ~bard overwrite~
INCLUDE ~chriz-bg-rebalance/lib/bard_progression.tpa~
LAF cbr_sp_validate_provider END
LAF cbr_sp_register INT_VAR class_id = 5 kit_id = 0 STR_VAR slot_table = ~CBRIWD7~ END
LAF cbr_sp_register_bard STR_VAR kit_symbol = ~BARD~ slot_table = ~CBRIWD7~ progression_text = ~IWD7 fixture~ END
LAF cbr_sp_register_bard STR_VAR kit_symbol = ~JESTER~ slot_table = ~CBRIWD7~ progression_text = ~IWD7 fixture~ END
LAF cbr_sp_register_bard STR_VAR kit_symbol = ~BLADE~ slot_table = ~CBRBG6~ progression_text = ~BG6 fixture~ END
LAF cbr_sp_register_bard STR_VAR kit_symbol = ~SKALD~ slot_table = ~CBRBG6~ progression_text = ~BG6 fixture~ END
''' + extra, encoding="utf8")
        result = subprocess.run([str(WEIDU), f"{name}.tp2", "--force-install-list", "0", "--use-lang", language,
                                 "--no-exit-pause", "--quick-log"], cwd=game.root, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        return output

    def check_result(self, game):
        table = TwoDA.from_text((game.override / "CBRSPKIT.2DA").read_text())
        entries = {(int(r[1][0]), int(r[1][1])): r[1][2] for r in table.rows}
        self.assertEqual("CBRIWD7", entries[5, 0])
        for kit in (0x4000, 0x400e):
            self.assertEqual("CBRIWD7", entries[5, kit])
        for kit in (0x400d, 0x400f):
            self.assertEqual("CBRBG6", entries[5, kit])
        self.assertEqual(len(entries), len(table.rows))
        for name in ("CBRSPVER", "CBRBG6", "CBRIWD7", "CBRIWD8"):
            self.assertEqual((DATA / f"{name}.2da").read_text().split(), (game.override / f"{name}.2DA").read_text().split())
        expected = json.loads((ROOT / "tests/fixtures/bard_progression_descriptions.json").read_text(encoding="utf8"))
        descriptions = strings(game.tlk)
        table = TwoDA.from_text((game.override / "CLASTEXT.2DA").read_text())
        for kit, text in expected.items():
            self.assertEqual(text.replace("%progression_text%", "IWD7 fixture" if kit in ("BARD", "JESTER") else "BG6 fixture"),
                             descriptions[int(table.cell(kit, "DESCSTR"))].replace("\r\n", "\n"))
        self.assertEqual(["Shared foreign text.", "Hand edited."], descriptions[:2])

    def test_missing_provider_and_complete_text_then_second_install(self):
        game = self.game()
        self.install(game)
        self.check_result(game)
        before = game.snapshot()
        self.install(game, "repeat")
        self.assertEqual(before, game.snapshot())

    def test_edited_provider_ragged_registry_duplicate_pairs_and_missing_rows(self):
        game = self.game({
            "CBRSPVER.2DA": b"2DA V1.0\n*\n VALUE\nAPI bad\nAPI 99\n",
            "CBRSPKIT.2DA": b"2DA V1.0\n*\n TABLE EXTRA KIT CLASS\na CBRBG6 x 16384 5\nb CBRIWD8 x 16384 5\nc CBRBG6 x\nd FOREIGN x 9 2\n",
            "CBRIWD7.2DA": b"Hand edited table",
            "KITLIST.2DA": b"2DA V1.0\n0\n ROWNAME\n",
            "CLASTEXT.2DA": b"2DA V1.0\n0\n ID\n",
        })
        self.install(game)
        self.check_result(game)
        self.assertIn("FOREIGN", (game.override / "CBRSPKIT.2DA").read_text())

    def test_other_game_language_keeps_text_but_writes_registrations(self):
        game = self.game()
        target = game.root / "lang/de_de/dialog.tlk"
        target.parent.mkdir(parents=True)
        target.write_bytes(game.tlk.read_bytes())
        original = (game.override / "CLASTEXT.2DA").read_bytes()
        output = self.install(game, language="de_de")
        self.assertIn("existing description retained", output)
        self.assertEqual(original, (game.override / "CLASTEXT.2DA").read_bytes())
        self.assertIn("CBRIWD7", (game.override / "CBRSPKIT.2DA").read_text())


if __name__ == "__main__":
    unittest.main()
