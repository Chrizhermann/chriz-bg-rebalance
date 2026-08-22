"""Behavioral tests for the component 407 EEex listener (M_CBRAPR.lua).

The listener runs inside EEex's ListsResolved hook, which fires once per
ProcessEffectList PASS (every AI tick) while the engine rebuilds CDerivedStats
only on some passes (disassembly evidence: research/07). These tests drive the
stamped listener through that cadence with a fake EEex surface
(tests/lua/cbrapr_sim.lua) under EET's bundled Lua 5.3 interpreter and assert
the one property the live bug violated: exactly +1/2 attack per rebuild, never
more, regardless of how many passes happen in between.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUA_TEMPLATE = ROOT / "chriz-bg-rebalance" / "lua" / "M_CBRAPR.lua"
SIM = ROOT / "tests" / "lua" / "cbrapr_sim.lua"
GAME_LUA = Path(r"C:\Games\Baldur's Gate II Enhanced Edition modded\EET\bin\win32\x86_64\lua.exe")

KIT_ID = "16425"
MARKER_STATE = "242"


def _find_lua() -> str | None:
    override = os.environ.get("CBR_LUA")
    if override and Path(override).exists():
        return override
    if GAME_LUA.exists():
        return str(GAME_LUA)
    for name in ("lua", "lua5.3", "lua5.4"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _stamp(template: Path, destination: Path) -> None:
    text = template.read_text(encoding="ascii")
    text = text.replace("%CBR_TEMPUS_KIT_ID%", KIT_ID)
    text = text.replace("%CBR_TEMPUS_SPEC_APR_STATE%", MARKER_STATE)
    destination.write_text(text, encoding="ascii", newline="\n")


class CbraprListenerTests(unittest.TestCase):
    lua: str

    @classmethod
    def setUpClass(cls) -> None:
        lua = _find_lua()
        if lua is None:
            raise unittest.SkipTest("no Lua interpreter found (set CBR_LUA to enable)")
        cls.lua = lua
        cls.holder = tempfile.TemporaryDirectory(prefix="cbr-cbrapr-")
        cls.listener = Path(cls.holder.name) / "M_CBRAPR.lua"
        _stamp(LUA_TEMPLATE, cls.listener)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.holder.cleanup()

    def _run(self, scenario: str) -> dict[str, str]:
        process = subprocess.run(
            [self.lua, str(SIM), str(self.listener), MARKER_STATE, scenario],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(process.returncode, 0, f"{scenario}:\n{process.stdout}\n{process.stderr}")
        observations: dict[str, str] = {}
        for line in process.stdout.splitlines():
            if "\t" in line:
                key, value = line.split("\t", 1)
                observations[key] = value
        self.assertEqual(observations.get("listeners_registered"), "1", process.stdout)
        return observations

    # -- the live bug ----------------------------------------------------------

    def test_exactly_one_half_attack_per_rebuild(self) -> None:
        seen = self._run("rebuild_then_fast_passes")
        self.assertEqual(seen["after_rebuild"], "7", "1.0 + 1/2 = 1.5 = key 7")
        self.assertEqual(seen["after_14_fast_passes"], "7", "fast passes must not accumulate")
        self.assertEqual(seen["after_second_rebuild"], "7", "a rebuild resets then re-applies once")
        self.assertEqual(seen["after_200_fast_passes"], "7")

    def test_holy_power_baseline_equal_to_previous_write_still_gets_bonus(self) -> None:
        seen = self._run("holy_power_baseline_equals_previous_write")
        self.assertEqual(seen["plain"], "7")
        self.assertEqual(seen["holy_power_tier1"], "2", "1.5 (engine) + 1/2 = 2.0 = key 2")
        self.assertEqual(seen["holy_power_tier1_after_fast_passes"], "2")
        self.assertEqual(seen["holy_power_expired"], "7")

    # -- marker bookkeeping ----------------------------------------------------

    def test_marker_bit_tracks_the_rebuild(self) -> None:
        seen = self._run("marker_lifecycle")
        self.assertEqual(seen["marker_after_bump"], "1")
        self.assertEqual(seen["marker_after_reload_before_hook"], "0")
        self.assertEqual(seen["apr_after_hook"], "7")
        self.assertEqual(seen["marker_after_hook"], "1")

    def test_rebuild_then_fast_passes_sets_marker(self) -> None:
        seen = self._run("rebuild_then_fast_passes")
        self.assertEqual(seen["marker_after_rebuild"], "1")

    # -- gates: no write, no marker --------------------------------------------

    def test_other_kit_is_untouched(self) -> None:
        seen = self._run("not_tempus")
        self.assertEqual((seen["apr"], seen["marker"]), ("1", "0"))

    def test_one_pip_weapon_is_untouched(self) -> None:
        seen = self._run("one_pip")
        self.assertEqual((seen["apr"], seen["marker"]), ("1", "0"))

    def test_bare_fist_is_untouched(self) -> None:
        seen = self._run("fist_selected")
        self.assertEqual((seen["apr"], seen["marker"]), ("1", "0"))

    def test_no_selection_transient_is_untouched(self) -> None:
        seen = self._run("no_selection")
        self.assertEqual((seen["apr"], seen["marker"]), ("1", "0"))

    def test_fighting_style_prof_value_is_rejected(self) -> None:
        seen = self._run("style_prof_rejected")
        self.assertEqual((seen["apr"], seen["marker"]), ("1", "0"))

    # -- weapon swaps between rebuilds ----------------------------------------

    def test_weapon_swap_between_rebuilds_never_accumulates(self) -> None:
        seen = self._run("weapon_swap_on_fast_path")
        self.assertEqual(seen["longsword"], "1")
        self.assertEqual(seen["flail_swap_in_next_pass"], "7", "swap-in lands on the next pass")
        self.assertEqual(seen["flail_after_fast_passes"], "7")
        self.assertEqual(seen["swap_out_before_rebuild"], "7", "bounded lag, no accumulation")
        self.assertEqual(seen["swap_out_after_rebuild"], "1")

    # -- encoding --------------------------------------------------------------

    def test_key_encoding_arithmetic(self) -> None:
        seen = self._run("encoding")
        self.assertEqual(seen["from_2"], "8", "2.0 + 1/2 = 2.5 = key 8")
        self.assertEqual(seen["from_8"], "3", "2.5 + 1/2 = 3.0 = key 3")
        self.assertEqual(seen["from_5"], "5", "5 is the representable ceiling")
        self.assertEqual(seen["from_10"], "5", "4.5 + 1/2 = 5")

    # -- binding surface missing: stay inert ----------------------------------

    def test_missing_spell_state_array_never_writes(self) -> None:
        seen = self._run("missing_spellstates_array")
        self.assertEqual(seen["apr"], "1")

    def test_missing_array_setter_never_writes(self) -> None:
        seen = self._run("missing_set_binding")
        self.assertEqual(seen["apr"], "1")


if __name__ == "__main__":
    unittest.main()
