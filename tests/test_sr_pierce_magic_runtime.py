"""Behavioral checks for Pierce Magic's EEex impact callback.

The fake engine models documented argument names, timed-effect serialization,
and additive MR. It does not prove native callback ordering, spell-protection
delivery, or that a derived-stat snapshot is fresh at an expiration boundary.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_cbrapr_listener import _find_lua


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua"
SIM = ROOT / "tests/lua/sr_pierce_magic_sim.lua"


class PierceMagicRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lua = _find_lua()
        if cls.lua is None:
            raise unittest.SkipTest("no Lua interpreter found (set CBR_LUA to enable)")

    def run_scenario(self, scenario: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory(prefix="cbr-pierce-magic-") as directory:
            temporary = Path(directory)
            runtime = temporary / "M_CBRPM.lua"
            source = TEMPLATE.read_text(encoding="ascii")
            source = source.replace("%CBR_PM_MR_STAT%", "18")
            runtime.write_text(source, encoding="ascii", newline="\n")
            process = subprocess.run(
                [self.lua, str(SIM), str(runtime), scenario],
                cwd=temporary, capture_output=True, text=True,
                timeout=30, check=False,
            )
        transcript = f"{process.stdout}\n{process.stderr}"
        self.assertEqual(process.returncode, 0, transcript)
        observations = dict(
            line.split("\t", 1)
            for line in process.stdout.splitlines() if "\t" in line
        )
        self.assertEqual(observations.get("scenario_ok"), scenario, transcript)
        return observations

    def test_first_hit_curve_zero_through_150_rounds_odd_halves_up(self) -> None:
        seen = self.run_scenario("curve")
        for mr in range(151):
            with self.subTest(mr=mr):
                amount = min(mr, max(10, min(40, (mr + 1) // 2)))
                self.assertEqual(int(seen[f"mr_{mr}"]), mr - amount)
        self.assertEqual(seen["negative_snapshot"], "0")

    def test_same_frame_recasts_never_add_a_second_contribution(self) -> None:
        self.run_scenario("same_frame")

    def test_refresh_extends_both_snapshot_and_icon_from_current_game_time(self) -> None:
        self.run_scenario("refresh")

    def test_refresh_preserves_first_amount_when_other_resistance_changes(self) -> None:
        self.run_scenario("changed_resistance")

    def test_lower_resistance_and_foreign_effects_are_untouched(self) -> None:
        self.run_scenario("foreign_effects")

    def test_zero_snapshot_remains_zero_after_resistance_increases(self) -> None:
        self.run_scenario("zero_snapshot")

    def test_serialized_effects_preserve_snapshot_without_lua_side_state(self) -> None:
        self.run_scenario("save_load")

    def test_expired_effect_is_not_revived_after_stats_rebuild(self) -> None:
        self.run_scenario("expired")

    def test_done_effect_is_not_revived_after_stats_rebuild(self) -> None:
        self.run_scenario("done")

    def test_pending_impact_expires_instead_of_applying_late(self) -> None:
        self.run_scenario("pending_expired")

    def test_foreign_source_with_same_opcodes_does_not_satisfy_owned_snapshot(self) -> None:
        self.run_scenario("foreign_owner_only")

    def test_native_immunity_block_does_not_leave_a_success_icon(self) -> None:
        self.run_scenario("immunity")

    def test_invalid_owned_records_fail_before_stacking_or_refresh(self) -> None:
        for scenario in (
            "duplicate", "wrong_mode", "positive_amount", "invalid_amount",
            "permanent", "relative_timing",
        ):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
