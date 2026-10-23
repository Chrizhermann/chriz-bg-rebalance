"""The observer's lab check for both labs the scripts build (CBR_LAB_VARIANT); lupa only.

Run: python -B research/timestop-lab/test_lab_variant.py -v
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:  # pragma: no cover - the README lists lupa with LuaJIT 2.1
    LuaRuntime = None

HERE = Path(__file__).resolve().parent
TIMESTOP, TIMECLOCKS = "CBR TimeStop Lab 2730", "CBR TimeClocks Lab 2730"


@unittest.skipIf(LuaRuntime is None, "lupa with LuaJIT 2.1 is not installed")
class ObserverLabCheckTests(unittest.TestCase):
    """CBRTS.Inspect() starts with the lab check; past it, it stops at the missing EEex."""

    def inspect(self, lab_id, engine):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute((HERE / "CBRTObs.lua").read_text(encoding="utf-8"))
        attempt = lua.eval("""function(files)
            io.open = function(path)
                local text = files[path]
                if text == nil then return nil end
                return {read = function() return text end, close = function() end}
            end
            local ok, why = pcall(CBRTS.Inspect)
            return ok, tostring(why)
        end""")
        files = {"CBRTSLab.id": lab_id, "engine.lua": engine}
        return attempt(lua.table_from({key: value for key, value in files.items() if value is not None}))

    def test_each_lab_with_its_own_profile_passes_the_lab_check(self):
        for name in (TIMESTOP, TIMECLOCKS):
            with self.subTest(lab=name):
                ok, why = self.inspect(name + "\n", f'engine_name = "{name}"\nother = 1\n')
                self.assertFalse(ok)
                self.assertIn("EEex/LuaJIT unavailable", why)

    def test_a_lab_with_the_other_labs_profile_is_refused(self):
        for lab, profile in ((TIMESTOP, TIMECLOCKS), (TIMECLOCKS, TIMESTOP), (TIMECLOCKS, "Baldur's Gate II")):
            with self.subTest(lab=lab, profile=profile):
                ok, why = self.inspect(lab + "\n", f'engine_name = "{profile}"\n')
                self.assertFalse(ok)
                self.assertIn("Wrong game profile", why)

    def test_unknown_or_malformed_lab_ids_are_refused(self):
        for lab_id in ("CBR TimeStop Lab 2730", "CBR TimeStop Lab 2730\n\n", "CBR Other Lab 2730\n",
                       "cbr timeclocks lab 2730\n", "\n", ""):
            with self.subTest(lab_id=lab_id):
                ok, why = self.inspect(lab_id, f'engine_name = "{TIMESTOP}"\n')
                self.assertFalse(ok)
                self.assertIn("Not the owned lab", why)

    def test_missing_files_are_refused(self):
        ok, why = self.inspect(None, f'engine_name = "{TIMESTOP}"\n')
        self.assertIn("Missing lab guard: CBRTSLab.id", why)
        ok, why = self.inspect(TIMECLOCKS + "\n", None)
        self.assertIn("Missing lab guard: engine.lua", why)


if __name__ == "__main__":
    unittest.main()
