"""Core behavior of the physical-resistance soft cap, without a live game.

The Lua simulator deliberately calls the production Apply entry point directly.
It proves the curve, party scope, and rebuild marker semantics, NOT that a native
engine hook reaches this entry point before the engine's 100% clamp. In particular,
the 95% cases pass untruncated inputs; engine integration needs separate evidence.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_cbrapr_listener import _find_lua


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "chriz-bg-rebalance/lua/M_CBRRES.lua"
SIM = ROOT / "tests/lua/physical_resistance_sim.lua"


class PhysicalResistanceCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lua = _find_lua()
        if cls.lua is None:
            raise unittest.SkipTest("no Lua interpreter found (set CBR_LUA to enable)")

    def run_scenario(self, scenario: str, cap: int = 90, state: int = 242) -> dict[str, str]:
        with tempfile.TemporaryDirectory(prefix="cbr-resistance-core-") as temporary:
            root = Path(temporary)
            listener = root / "M_CBRRES.lua"
            source = TEMPLATE.read_text(encoding="ascii")
            source = source.replace("%CBR_RES_CAP%", str(cap))
            source = source.replace("%CBR_RES_STATE%", str(state))
            listener.write_text(source, encoding="ascii", newline="\n")
            process = subprocess.run(
                [self.lua, str(SIM), str(listener), str(state), scenario],
                cwd=root, capture_output=True, text=True, timeout=30, check=False,
            )
            transcript = f"{process.stdout}\n{process.stderr}"
            self.assertEqual(process.returncode, 0, transcript)
            observations = dict(
                line.split("\t", 1) for line in process.stdout.splitlines() if "\t" in line
            )
            self.assertEqual(observations.get("forbidden_calls"), "0", transcript)
            return observations

    def test_half_effectiveness_above_eighty_and_ninety_cap(self) -> None:
        seen = self.run_scenario("curve")
        expected = {
            -100: -100, -1: -1, 0: 0, 79: 79, 80: 80, 81: 80,
            82: 81, 89: 84, 90: 85, 99: 89, 100: 90,
            101: 90, 109: 90, 110: 90, 200: 90,
        }
        for raw, result in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(seen[f"raw_{raw}"], str(result))
        self.assertEqual(seen["monotonic"], "true")

    def test_optional_ninety_five_cap_requires_untruncated_110_input(self) -> None:
        seen = self.run_scenario("curve", cap=95)
        for raw, result in {80: 80, 90: 85, 100: 90, 101: 90, 109: 94, 110: 95, 200: 95}.items():
            with self.subTest(raw=raw):
                self.assertEqual(seen[f"raw_{raw}"], str(result))
        self.assertEqual(seen["monotonic"], "true")

    def test_four_damage_types_are_transformed_independently(self) -> None:
        seen = self.run_scenario("mixed")
        self.assertEqual(seen["physical"], "80,85,90,-20")
        self.assertEqual(seen["other_unchanged"], "true")
        self.assertEqual(seen["base_unchanged"], "true")
        self.assertEqual(seen["temp_unchanged"], "true")
        self.assertEqual(seen["effects_unchanged"], "true")

    def test_fast_passes_do_not_repeatedly_reduce_resistance(self) -> None:
        seen = self.run_scenario("cadence")
        self.assertEqual(seen["first"], "85,85,85,85")
        self.assertEqual(seen["after_200_passes"], seen["first"])
        self.assertEqual(seen["same_value_fresh_rebuild"], "82,82,82,82")
        self.assertEqual(seen["buff_applied"], "90,90,90,90")
        self.assertEqual(seen["buff_expired"], "70,70,70,70")

    def test_marker_survives_passes_and_clears_with_stats_rebuild(self) -> None:
        seen = self.run_scenario("marker")
        self.assertEqual(seen["after_apply"], "1")
        self.assertEqual(seen["before_reapply"], "0")
        self.assertEqual(seen["after_reapply"], "1")
        self.assertEqual(seen["sibling_states_preserved"], "true")

    def test_alternate_allocated_marker_including_bit31(self) -> None:
        for state in (1, 31, 32, 127, 255):
            with self.subTest(state=state):
                seen = self.run_scenario("marker", state=state)
                self.assertEqual(seen["after_reapply"], "1")
                self.assertEqual(seen["sibling_states_preserved"], "true")

    def test_enemies_neutrals_summons_and_clones_are_not_party_members(self) -> None:
        seen = self.run_scenario("nonparty")
        self.assertEqual(seen["writes"], "0")
        self.assertEqual(seen["markers"], "0")
        self.assertEqual(seen["all_unchanged"], "true")

    def test_join_exit_and_rejoin_use_current_membership(self) -> None:
        seen = self.run_scenario("membership")
        self.assertEqual(seen["before_join"], "100,100,100,100")
        self.assertEqual(seen["after_join"], "90,90,90,90")
        self.assertEqual(seen["writes_after_exit"], "0")
        self.assertEqual(seen["exit_without_rebuild"], "90,90,90,90")
        self.assertEqual(seen["exit_after_rebuild"], "100,100,100,100")
        self.assertEqual(seen["after_rejoin"], "90,90,90,90")

    def test_new_sprite_after_save_load_does_not_reuse_old_derived_state(self) -> None:
        seen = self.run_scenario("save_load")
        self.assertEqual(seen["before_load"], "90,90,90,90")
        self.assertEqual(seen["after_load"], "85,85,85,85")
        self.assertEqual(seen["old_untouched"], "true")

    def test_missing_or_invalid_required_fields_fail_before_partial_writes(self) -> None:
        for scenario in (
            "missing_field", "string_field", "nan_field", "infinite_field",
            "missing_stats", "missing_states", "missing_get", "missing_set",
            "copy_states", "bad_portrait_index",
        ):
            with self.subTest(scenario=scenario):
                seen = self.run_scenario(scenario)
                self.assertEqual(seen["writes"], "0")
                self.assertEqual(seen["failed"], "true")
                self.assertEqual(seen["failure_logs"], "1")
                self.assertEqual(seen["later_healthy_unchanged"], "true")

    def test_failed_callback_stays_disabled_when_module_is_reloaded(self) -> None:
        seen = self.run_scenario("failure_reload")
        self.assertEqual(seen["failed"], "true")
        self.assertEqual(seen["failure_logs"], "1")
        self.assertEqual(seen["writes"], "0")

    def test_registered_callback_applies_once_per_rebuild(self) -> None:
        seen = self.run_scenario("registered_callback")
        self.assertEqual(seen["listeners"], "1")
        self.assertEqual(seen["physical"], "90,90,90,90")
        self.assertEqual(seen["after_fast_passes"], seen["physical"])

    def test_successful_module_reload_keeps_one_live_callback(self) -> None:
        seen = self.run_scenario("successful_reload")
        self.assertEqual(seen["listeners"], "1")
        self.assertEqual(seen["after_reload"], "90,90,90,90")
        self.assertEqual(seen["fresh_after_reload"], "85,85,85,85")

    def test_charmed_hostile_party_member_still_uses_the_player_rule(self) -> None:
        seen = self.run_scenario("party_hostile_ea")
        self.assertEqual(seen["physical"], "90,90,90,90")
        self.assertEqual(seen["marker"], "1")

    def test_setter_failure_rolls_back_partial_stat_writes_and_marker(self) -> None:
        seen = self.run_scenario("setter_failure")
        self.assertEqual(seen["physical"], "100,100,100,100")
        self.assertEqual(seen["marker"], "0")
        self.assertEqual(seen["failed"], "true")
        self.assertEqual(seen["failure_logs"], "1")
        self.assertEqual(seen["later_healthy_unchanged"], "true")


if __name__ == "__main__":
    unittest.main()
