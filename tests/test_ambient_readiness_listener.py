"""RED contract tests for component 121's EEex readiness runtime.

Task 5 intentionally lands this suite before ``M_CBRRDY.lua`` exists.  Asset
and safety tests must pass; one production gate must fail with a precise
missing-module message; behavioral cases stay skipped until Task 8 creates the
runtime.  The fake engine is deliberately narrow and is revised from the
authorized Task 6 capability spike before production implementation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "chriz-bg-rebalance" / "lua" / "M_CBRRDY.lua"
SIMULATOR = ROOT / "tests" / "lua" / "ambient_readiness_sim.lua"
MANIFEST = ROOT / "tests" / "fixtures" / "ambient_readiness" / "manifest.lua"
PROBE = ROOT / "research" / "scripts" / "ambient_readiness_probe.lua"
GAME_LUA = Path(
    r"C:\Games\Baldur's Gate II Enhanced Edition modded\EET\bin\win32\x86_64\lua.exe"
)


def _find_lua() -> str | None:
    override = os.environ.get("CBR_LUA")
    if override and Path(override).is_file():
        return override
    if GAME_LUA.is_file():
        return str(GAME_LUA)
    for name in ("lua", "lua5.3", "lua5.4", "luajit"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _compile(lua: str, path: Path) -> subprocess.CompletedProcess[str]:
    quoted = path.resolve().as_posix().replace("]]", "] ]")
    expression = f"assert(loadfile([[{quoted}]]))"
    return subprocess.run(
        [lua, "-e", expression],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _manifest_expression() -> str:
    text = MANIFEST.read_text(encoding="ascii")
    match = re.search(r"(?m)^return\s+", text)
    if match is None:
        raise AssertionError("fixture manifest must return one Lua table")
    return text[match.end() :].strip()


def _stamp_runtime(destination: Path, manifest_expression: str | None = None) -> None:
    source = PRODUCTION.read_text(encoding="ascii")
    placeholder = "%CBR_RDY_MANIFEST%"
    if source.count(placeholder) != 1:
        raise AssertionError("M_CBRRDY.lua must contain exactly one manifest placeholder")
    stamped = source.replace(
        placeholder,
        manifest_expression if manifest_expression is not None else _manifest_expression(),
    )
    destination.write_text(stamped, encoding="ascii", newline="\n")


class AmbientReadinessAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        lua = _find_lua()
        if lua is None:
            raise unittest.SkipTest("no Lua interpreter found (set CBR_LUA to enable)")
        cls.lua = lua

    def test_fixture_simulator_and_probe_parse(self) -> None:
        for path in (MANIFEST, SIMULATOR, PROBE):
            with self.subTest(path=path.name):
                process = _compile(self.lua, path)
                self.assertEqual(
                    process.returncode,
                    0,
                    f"{path}:\n{process.stdout}\n{process.stderr}",
                )

    def test_manifest_pins_public_integer_defaults_and_conservative_floor(self) -> None:
        script = (
            f"local m=dofile([[{MANIFEST.resolve().as_posix()}]]);"
            "assert(m.schema_version==1);"
            "assert(m.defaults.ambient_enabled==1);"
            "assert(m.defaults.urgent_enabled==1);"
            "assert(m.defaults.external_owner==0);"
            "assert(m.minimum_duration==2400);"
            "assert(m.project_image_resref=='spwi703');"
            "for _,s in ipairs(m.ambient_spells) do "
            "assert(s.duration>=2400 and s.self_target==1 and s.defensive==1) end;"
            "io.write(#m.ambient_spells, '\\t', #m.urgent_candidates)"
        )
        process = subprocess.run(
            [self.lua, "-e", script],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, "6\t4")

    def test_probe_is_session_only_guarded_and_explicitly_reversible(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        for forbidden in (
            "io.open",
            "os.execute",
            "Infinity_DoFile",
            "Infinity_UpdateLuaStats",
            "override/",
            "override\\",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("CBR_RDY_PROBE", source)
        self.assertRegex(source, r"function\s+probe\.install\s*\(")
        self.assertRegex(source, r"function\s+probe\.teardown\s*\(")
        self.assertIn("probe.active", source)
        self.assertIn("probe.listeners_registered", source)

    def test_probe_updates_quick_lists_with_a_real_ability_id(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn('{ ["name"] = "abilityId", ["struct"] = "CAbilityId" }', source)
        self.assertIn("abilityId.m_itemType = 1", source)
        self.assertIn("abilityId.m_res:set(resref)", source)
        self.assertIn(
            "sprite:CheckQuickLists(abilityId, change_amount, 0, 0)", source
        )
        self.assertIn("update_quick_lists(sprite, resref, -1)", source)
        self.assertIn("update_quick_lists(token.sprite, token.resref, 1)", source)
        self.assertNotIn("sprite:CheckQuickLists(level - 1, -1, 0, 0)", source)

    def test_probe_records_the_engine_spellbook_reset_hook(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn("EEex_Sprite_AddQuickListCountsResetListener", source)
        self.assertIn('log("spellbook_reset", "id=" .. object_id(sprite))', source)
        self.assertIn("probe.reset_listener_registered", source)

    def test_probe_reads_installed_action_resrefs_from_cstring_storage(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn("action.m_string1.m_pchData:get()", source)
        self.assertNotIn("action.m_string1:get()", source)

    def test_probe_inspects_the_installed_queued_action_list(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn("sprite.m_queuedActions", source)
        self.assertNotIn("sprite.m_actionQueue", source)

    def test_probe_logs_the_installed_action_specific_id(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn(
            '" specific=" .. tostring(action and action.m_specificID)', source
        )

    def test_probe_records_the_installed_project_image_relation(self) -> None:
        source = PROBE.read_text(encoding="ascii")
        self.assertIn("effect.m_effectId == 237", source)
        self.assertIn("effect.m_dWFlags == 2", source)
        self.assertIn("effect.m_sourceId", source)
        self.assertIn("EEex_Sprite_GetState(sprite)", source)
        self.assertIn('"project_image=" .. project_image_relation(sprite)', source)


class ProductionRuntimeGateTests(unittest.TestCase):
    def test_runtime_template_exists(self) -> None:
        self.assertTrue(
            PRODUCTION.is_file(),
            "intentional RED: component 121 runtime is absent: "
            "chriz-bg-rebalance/lua/M_CBRRDY.lua",
        )


@unittest.skipUnless(PRODUCTION.is_file(), "Task 8 has not created M_CBRRDY.lua")
class _RuntimeCase(unittest.TestCase):
    lua: str

    @classmethod
    def setUpClass(cls) -> None:
        lua = _find_lua()
        if lua is None:
            raise unittest.SkipTest("no Lua interpreter found (set CBR_LUA to enable)")
        cls.lua = lua
        cls.holder = tempfile.TemporaryDirectory(prefix="cbr-readiness-")
        cls.runtime = Path(cls.holder.name) / "M_CBRRDY.lua"
        _stamp_runtime(cls.runtime)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.holder.cleanup()

    def _run(
        self,
        scenario: str,
        *,
        runtime: Path | None = None,
        expected_reset_listeners: str = "1",
        expected_marshal_handlers: str = "1",
    ) -> dict[str, str]:
        process = subprocess.run(
            [self.lua, str(SIMULATOR), str(runtime or self.runtime), scenario],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            process.returncode,
            0,
            f"{scenario}:\n{process.stdout}\n{process.stderr}",
        )
        observations: dict[str, str] = {}
        for line in process.stdout.splitlines():
            if "\t" in line:
                key, value = line.split("\t", 1)
                observations[key] = value
        self.assertEqual(observations.get("tick_listeners"), "1", process.stdout)
        self.assertEqual(observations.get("started_action_listeners"), "1", process.stdout)
        self.assertEqual(
            observations.get("reset_listeners"),
            expected_reset_listeners,
            process.stdout,
        )
        self.assertEqual(
            observations.get("marshal_handlers"),
            expected_marshal_handlers,
            process.stdout,
        )
        return observations


class AmbientReadinessRuntimeShellTests(_RuntimeCase):
    def test_missing_layer_specific_apis_retire_only_that_layer(self) -> None:
        missing_urgent = self._run("runtime_missing_urgent_api")
        self.assertEqual(missing_urgent["ambient_live"], "1")
        self.assertEqual(missing_urgent["ambient_faulted"], "0")
        self.assertEqual(missing_urgent["urgent_faulted"], "1")
        self.assertEqual(missing_urgent["urgent_unsupported_logs"], "1")

        missing_ambient = self._run(
            "runtime_missing_ambient_api",
            expected_reset_listeners="0",
            expected_marshal_handlers="0",
        )
        self.assertEqual(missing_ambient["urgent_live"], "1")
        self.assertEqual(missing_ambient["urgent_faulted"], "0")
        self.assertEqual(missing_ambient["ambient_faulted"], "1")
        self.assertEqual(missing_ambient["ambient_unsupported_logs"], "1")

    def test_hot_reload_flags_and_independent_fault_fuses(self) -> None:
        seen = self._run("runtime_shell")
        self.assertEqual(seen["listeners_after_reload"], "1")
        self.assertEqual(seen["started_after_reload"], "1")
        self.assertEqual(seen["reset_after_reload"], "1")
        self.assertEqual(seen["ambient_enable_gate"], "1")
        self.assertEqual(seen["ambient_owner_gate"], "1")
        self.assertEqual(seen["urgent_owner_independent"], "1")
        self.assertEqual(seen["urgent_owner_gate"], "1")
        self.assertEqual(seen["ambient_owner_independent"], "1")
        self.assertEqual(seen["ambient_tracebacks"], "1")
        self.assertEqual(seen["ambient_fused"], "1")
        self.assertEqual(seen["urgent_after_ambient_fault"], "1")

    def test_missing_project_image_manifest_identity_retires_only_urgent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-readiness-no-project-image-") as temporary:
            runtime = Path(temporary) / "M_CBRRDY.lua"
            manifest = _manifest_expression().replace(
                'project_image_resref = "spwi703"',
                'project_image_resref = ""',
            )
            self.assertNotEqual(manifest, _manifest_expression())
            _stamp_runtime(runtime, manifest)
            seen = self._run("runtime_missing_project_image_identity", runtime=runtime)
        self.assertEqual(seen["ambient_live"], "1")
        self.assertEqual(seen["ambient_faulted"], "0")
        self.assertEqual(seen["urgent_faulted"], "1")
        self.assertEqual(seen["urgent_unsupported_logs"], "1")

    def test_runtime_uses_the_proven_installed_binding_shapes(self) -> None:
        source = PRODUCTION.read_text(encoding="ascii")
        for required in (
            "EEex_Sprite_AddQuickListCountsResetListener",
            "EEex_RunWithStackManager",
            'struct = "CAbilityId"',
            "m_queuedActions",
            "m_string1.m_pchData:get()",
            "Infinity_GetInCutsceneMode",
            "EEex_Sprite_GetState",
            "effect.m_effectId",
            "opcode == 237",
            "effect.m_dWFlags",
            "effect.m_sourceId",
            "manifest.project_image_resref",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        self.assertNotIn('source == "spwi703"', source)
        for obsolete in (
            "EEex_Sprite_GetSpellbookResetSerial",
            "m_actionQueue",
            "EEex_Sprite_IsInDialogue",
            "EEex_Sprite_IsConscious",
            "EEex_Sprite_IsProjectImageOwnerCertain",
            "EEex_GameState_IsCutsceneMode",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, source)


class AmbientReadinessListenerTests(_RuntimeCase):
    def test_settled_scs_caster_classification_and_grades(self) -> None:
        seen = self._run("ambient_classification")
        self.assertEqual(seen["settled_scs"], "1")
        self.assertEqual(seen["unsettled"], "0")
        self.assertEqual(seen["unrecognized"], "0")
        self.assertEqual(seen["grade_default"], "1")
        self.assertEqual(seen["grade_zero"], "0")
        self.assertEqual(seen["grade_reserved"], "3")
        self.assertEqual(seen["sparse_include"], "1")
        self.assertEqual(seen["sparse_exclude"], "0")

    def test_only_memorized_long_defensive_self_buffs_qualify(self) -> None:
        seen = self._run("ambient_qualification")
        self.assertEqual(seen["long_self_defense"], "1")
        self.assertEqual(seen["short_duration"], "0")
        self.assertEqual(seen["other_target"], "0")
        self.assertEqual(seen["offensive"], "0")
        self.assertEqual(seen["unmemorized"], "0")

    def test_existing_equivalent_defense_is_not_reapplied_or_charged(self) -> None:
        seen = self._run("ambient_existing_defense")
        self.assertEqual(seen["available"], "1")
        self.assertEqual(seen["component_applications"], "0")
        self.assertEqual(seen["ledger_created"], "0")

    def test_priest_memorization_uses_the_same_exact_debit_path(self) -> None:
        seen = self._run("ambient_priest_debit")
        self.assertEqual(seen["available_after"], "0")
        self.assertEqual(seen["active_after"], "1")
        self.assertEqual(seen["quicklist_rebuilds"], "1")

    def test_spellbook_qualification_cache_reopens_only_on_engine_reset(self) -> None:
        seen = self._run("ambient_spellbook_cache")
        self.assertEqual(seen["without_reset"], "0")
        self.assertEqual(seen["after_reset"], "1")

    def test_first_application_debits_once_and_maintenance_is_free(self) -> None:
        seen = self._run("ambient_first_debit_and_refresh")
        self.assertEqual(seen["available_before"], "1")
        self.assertEqual(seen["available_after_first"], "0")
        self.assertEqual(seen["active_after_first"], "1")
        self.assertEqual(seen["ledger_charged"], "1")
        self.assertEqual(seen["quicklist_rebuilds"], "1")
        self.assertEqual(seen["available_after_refresh"], "0")
        self.assertEqual(seen["applications"], "2")

    def test_natural_expiry_refreshes_only_when_safe(self) -> None:
        seen = self._run("ambient_natural_expiry")
        self.assertEqual(seen["visible_blocked"], "1")
        self.assertEqual(seen["combat_blocked"], "1")
        self.assertEqual(seen["safe_refresh"], "1")

    def test_early_removal_suppresses_until_real_reset(self) -> None:
        seen = self._run("ambient_early_removal")
        self.assertEqual(seen["suppressed"], "1")
        self.assertEqual(seen["applications_before_reset"], "1")
        self.assertEqual(seen["suppressed_after_reset"], "0")
        self.assertEqual(seen["applications_after_reset"], "2")

    def test_only_engine_spellbook_refresh_resets_charge(self) -> None:
        seen = self._run("ambient_reset_boundaries")
        self.assertEqual(seen["after_elapsed_time"], "1")
        self.assertEqual(seen["after_save_load"], "1")
        self.assertEqual(seen["after_area_transition"], "1")
        self.assertEqual(seen["after_party_rest_only"], "1")
        self.assertEqual(seen["after_engine_reset"], "2")

    def test_only_exact_initial_scs_prebuff_is_reimbursed(self) -> None:
        seen = self._run("ambient_scs_reimbursement")
        self.assertEqual(seen["exact_initial_reimbursed"], "1")
        self.assertEqual(seen["unrelated_combat_reimbursed"], "0")
        self.assertEqual(seen["renewal_reimbursed"], "0")

    def test_failed_transaction_restores_or_disables_without_looping(self) -> None:
        seen = self._run("ambient_transaction_failure")
        self.assertEqual(seen["apply_availability_restored"], "1")
        self.assertEqual(seen["apply_disabled"], "1")
        self.assertEqual(seen["apply_attempts"], "1")
        self.assertEqual(seen["quick_availability_restored"], "1")
        self.assertEqual(seen["quick_disabled"], "1")
        self.assertEqual(seen["quick_attempts"], "1")

    def test_malformed_saved_record_disables_only_that_spell(self) -> None:
        seen = self._run("ambient_malformed_ledger")
        self.assertEqual(seen["malformed_spell_disabled"], "0")
        self.assertEqual(seen["other_spell_continues"], "1")
        self.assertEqual(seen["legacy_discarded"], "1")

    def test_marshaled_ledger_is_versioned_and_primitive_only(self) -> None:
        seen = self._run("ambient_marshal")
        self.assertEqual(seen["schema_version"], "1")
        self.assertEqual(seen["primitive_only"], "1")
        self.assertEqual(seen["has_userdata"], "0")
        self.assertEqual(seen["has_object_id"], "0")
        self.assertEqual(seen["record_fields_exact"], "1")

    def test_retirement_hot_reload_and_fault_fuses(self) -> None:
        seen = self._run("ambient_runtime_safety")
        self.assertEqual(seen["ambient_disabled_inert"], "1")
        self.assertEqual(seen["ambient_owner_inert"], "1")
        self.assertEqual(seen["listeners_after_reload"], "1")
        self.assertEqual(seen["ambient_tracebacks"], "1")
        self.assertEqual(seen["ambient_inert_after_fault"], "1")

    def test_reused_engine_object_id_gets_fresh_session_state(self) -> None:
        seen = self._run("ambient_sprite_lifetime")
        self.assertEqual(seen["replacement_active"], "1")
        self.assertEqual(seen["replacement_available_after"], "0")

    def test_incomplete_effect_list_view_fails_closed_before_debit(self) -> None:
        seen = self._run("ambient_incomplete_effect_view")
        self.assertEqual(seen["effect_active"], "0")
        self.assertEqual(seen["available_after"], "1")
        self.assertEqual(seen["ambient_faulted"], "1")


class UrgentReadinessListenerTests(_RuntimeCase):
    def test_contact_hard_gates(self) -> None:
        seen = self._run("urgent_hard_gates")
        self.assertEqual(seen["eligible"], "1")
        self.assertEqual(seen["not_hostile"], "0")
        self.assertEqual(seen["not_visible"], "0")
        self.assertEqual(seen["unsettled"], "0")
        self.assertEqual(seen["unrecognized"], "0")
        self.assertEqual(seen["unconscious"], "0")
        self.assertEqual(seen["already_protected"], "0")
        self.assertEqual(seen["unknown_effect_lists"], "0")
        self.assertEqual(seen["partial_effect_lists"], "0")
        self.assertEqual(seen["no_slot"], "0")
        self.assertEqual(seen["dialogue"], "0")
        self.assertEqual(seen["cutscene"], "0")

    def test_candidate_order_filters_false_improved_mantle(self) -> None:
        seen = self._run("urgent_candidates")
        self.assertEqual(seen["all_available"], "spwi907")
        self.assertEqual(seen["without_absolute"], "spwi708")
        self.assertEqual(seen["pfmw_fallback"], "spwi611")
        self.assertEqual(seen["moment_of_prescience_selected"], "0")

    def test_only_proven_passive_work_is_displaced(self) -> None:
        seen = self._run("urgent_action_safety")
        self.assertEqual(seen["idle"], "1")
        self.assertEqual(seen["wander"], "1")
        self.assertEqual(seen["movement"], "1")
        self.assertEqual(seen["cast"], "0")
        self.assertEqual(seen["attack"], "0")
        self.assertEqual(seen["tactical"], "0")
        self.assertEqual(seen["dialogue"], "0")
        self.assertEqual(seen["cutscene"], "0")
        self.assertEqual(seen["passive_queue"], "1")
        self.assertEqual(seen["unsafe_queue"], "0")
        self.assertEqual(seen["unknown_queue"], "0")

    def test_project_image_owner_uncertainty_skips(self) -> None:
        seen = self._run("urgent_project_image")
        self.assertEqual(seen["ordinary_actor"], "1")
        self.assertEqual(seen["owner_uncertain"], "0")
        self.assertEqual(seen["locked_owner"], "0")
        self.assertEqual(seen["valid_clone"], "0")

    def test_normal_cast_owns_slot_aura_time_and_interruption(self) -> None:
        seen = self._run("urgent_normal_cast")
        self.assertEqual(seen["queued_spellres"], "1")
        self.assertEqual(seen["direct_effects"], "0")
        self.assertEqual(seen["engine_slot_debits"], "1")
        self.assertEqual(seen["engine_aura"], "1")
        self.assertEqual(seen["engine_casting_time"], "1")
        self.assertEqual(seen["interruptible"], "1")

    def test_started_then_interrupted_attempt_is_spent(self) -> None:
        seen = self._run("urgent_interrupted_started")
        self.assertEqual(seen["started"], "1")
        self.assertEqual(seen["effect_active"], "0")
        self.assertEqual(seen["engine_slot_debits"], "0")
        self.assertEqual(seen["available_after"], "1")
        self.assertEqual(seen["queues"], "1")
        self.assertEqual(seen["episode_spent"], "1")

    def test_never_started_cast_gets_one_bounded_retry(self) -> None:
        seen = self._run("urgent_never_started_retry")
        self.assertEqual(seen["queues"], "2")
        self.assertEqual(seen["starts"], "0")
        self.assertEqual(seen["episode_spent"], "1")

    def test_never_started_cast_with_an_unsafe_queue_closes_the_episode(self) -> None:
        seen = self._run("urgent_never_started_unsafe_queue")
        self.assertEqual(seen["queues"], "1")
        self.assertEqual(seen["episode_spent"], "1")

    def test_contact_rearms_only_after_one_full_round_out_of_sight(self) -> None:
        seen = self._run("urgent_contact_rearm")
        self.assertEqual(seen["continuous_sight_queues"], "1")
        self.assertEqual(seen["short_loss_queues"], "1")
        self.assertEqual(seen["full_round_loss_queues"], "2")

    def test_urgent_fault_is_independent_and_logs_once(self) -> None:
        seen = self._run("urgent_fault_fuse")
        self.assertEqual(seen["urgent_tracebacks"], "1")
        self.assertEqual(seen["urgent_inert_after_fault"], "1")
        self.assertEqual(seen["ambient_still_active"], "1")


if __name__ == "__main__":
    unittest.main()
